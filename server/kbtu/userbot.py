"""The userbot (PLAN 86 part 2): an old Telegram account, signed in once (tools/userbot_login.py), that joins each org's
main public channel and mirrors its posts into the org's news (mirror.py has the rules). It runs in the bot's process
beside the postman (bot.run), never in a request: one account is one point of failure, and Telegram makes it wait
(FloodWait) when it hurries. TG_API_ID, TG_API_HASH and TG_SESSION in the environment; any missing: off, the app as
before. It reads only the channels it mirrors: updates from anywhere else are dropped unread, it never writes to
anyone, and it keeps nothing but those channels' posts. Patterns from KRI's reader: catch_up off and a catch-up of our
own, FloodWait slept off, a dead session reported once and the userbot left off (a glitch reconnects)."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from . import db, logic, media, mirror
from .config import Config

log = logging.getLogger("kbtu.userbot")

JOIN_GAP = 240          # one join or leave every 4 minutes at most (fresh joins in a row get an account limited)
SWEEP_GAP = 1800        # every 30 minutes: missed posts, edits and deletions, views and reaction counts
RETRY = 60              # after a dropped connection


def missing(cfg: Config) -> str | None:
    """Why the userbot stays off, or None."""
    if not (cfg.tg_api_id and cfg.tg_api_hash and cfg.tg_session):
        return "no TG_API_ID / TG_API_HASH / TG_SESSION"
    if not cfg.tg_api_id.isdigit():
        return "TG_API_ID is not a number"
    return None


async def run(cfg: Config) -> None:
    """Forever, or until it's off for good: one line at start says which ("signed in as id <n>" or "off (<why>)")."""
    if why := missing(cfg):
        log.warning("userbot: off (%s)", why)
        return
    try:
        from telethon import TelegramClient
        from telethon.errors import AuthKeyDuplicatedError, AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError
        from telethon.sessions import StringSession
    except ImportError:
        log.warning("userbot: off (telethon is not installed)")
        return
    dead = (AuthKeyDuplicatedError, AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError)
    said = False
    while True:
        client = TelegramClient(StringSession(cfg.tg_session), int(cfg.tg_api_id), cfg.tg_api_hash, catch_up=False)
        tasks: list[asyncio.Task] = []
        try:
            await client.connect()
            if not await client.is_user_authorized():
                log.warning("userbot: off (the session is not signed in)")
                return
            if not said:
                log.warning("userbot: signed in as id %d", (await client.get_me()).id)  # never the phone or the name
                said = True
            con = db.connect(cfg.db_path)
            await client.get_dialogs()  # the joined channels' access hashes: a StringSession keeps no entities
            work = Mirror(cfg, client, con)
            work.listen()
            tasks = [asyncio.create_task(work.joins()), asyncio.create_task(work.sweeps())]
            await client.run_until_disconnected()
        except dead as exc:
            log.warning("userbot: off (session ended: %s)", type(exc).__name__)
            return
        except Exception:  # noqa: BLE001 - a glitch: connect again in a minute
            log.exception("userbot")
        finally:
            for t in tasks:
                t.cancel()
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(RETRY)


class Mirror:
    """One connection's work: the handlers for new, edited and deleted posts, the joins and the sweeps."""

    def __init__(self, cfg: Config, client, con) -> None:
        self.client, self.con, self.root = client, con, Path(cfg.db_path).resolve().parent / "media"

    def listen(self) -> None:
        from telethon import events

        async def fresh(ev) -> None:
            await self.guard(self.post(ev.message))

        async def deleted(ev) -> None:
            channel = getattr(ev.original_update, "channel_id", None)  # a deletion elsewhere has none: not ours
            if channel and mirror.source(self.con, channel) is not None:
                mirror.gone(self.con, channel, list(ev.deleted_ids))

        self.client.add_event_handler(fresh, events.NewMessage())
        self.client.add_event_handler(fresh, events.MessageEdited())
        self.client.add_event_handler(deleted, events.MessageDeleted())

    async def guard(self, job) -> None:
        """One post's work; FloodWait slept off, a bad post logged, never the listener down."""
        from telethon.errors import FloodWaitError
        try:
            await job
        except FloodWaitError as exc:
            log.warning("userbot: flood wait %ds", exc.seconds)
            await asyncio.sleep(exc.seconds + 5)
        except Exception:  # noqa: BLE001
            log.exception("userbot post")

    async def post(self, m) -> None:
        """A channel post (new or edited) into its org's news; anything from a chat we don't mirror is dropped unread."""
        channel = getattr(m.peer_id, "channel_id", None)
        if not channel or m.action is not None or mirror.source(self.con, channel) is None:
            return
        msg = await self.read(channel, m)
        mirror.take(self.con, channel, msg)
        if msg.photo and logic.photo_free(self.con, msg.photo["path"]):  # an album's second photo, an edit's same one
            self.drop(msg.photo["path"])

    async def read(self, channel: int, m) -> mirror.Msg:
        """A Telethon message as mirror.Msg: its photo copied (only when the post needs one), a video or a file only named."""
        photo, kind = None, None
        if m.photo and mirror.needs_photo(self.con, channel, m.id, m.grouped_id):
            data = await self.client.download_media(m, bytes)
            if data and len(data) <= media.MAX_BYTES:
                try:
                    photo = await asyncio.to_thread(media.save, data, self.root)
                except media.BadImage:
                    pass
        elif m.video or m.gif or m.video_note:
            kind = "video"
        elif m.media is not None and not m.photo and not getattr(m, "web_preview", None):
            kind = "file"  # a document, a voice, a poll: in Telegram
        res = getattr(m.reactions, "results", None)
        reactions = [(getattr(r.reaction, "emoticon", None) or "★", r.count) for r in res] if res is not None else ([] if m.reactions is None else None)
        return mirror.Msg(id=m.id, date=int(m.date.timestamp()), text=m.message or "", grouped=m.grouped_id, photo=photo, media=kind,
                          views=m.views, reactions=reactions)

    def drop(self, path: str) -> None:
        for ext in (".webp", ".t.webp", ".jpg"):
            (self.root / f"{path}{ext}").unlink(missing_ok=True)

    async def joins(self) -> None:
        """Every few minutes one step: leave a channel that stopped being a mirror, or join the next one and take its
        last few posts. Public channels only (mirror.wanted); a megagroup or a dead name is skipped for a day."""
        from telethon.errors import FloodWaitError
        from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
        from telethon.tl.types import Channel, PeerChannel
        skip: dict[str, float] = {}
        while True:
            try:
                if out := mirror.to_leave(self.con):
                    channel, name = out[0]
                    try:
                        await self.client(LeaveChannelRequest(await self.client.get_input_entity(PeerChannel(channel))))
                    except (ValueError, TypeError):
                        pass  # not in it any more: forget it all the same
                    mirror.left(self.con, channel)
                    log.warning("userbot: left @%s", name)
                elif todo := [n for n in mirror.to_join(self.con) if skip.get(n, 0) < time.time()]:
                    name = todo[0]
                    try:
                        ent = await self.client.get_entity(name)
                    except (ValueError, TypeError):
                        ent = None
                    if not isinstance(ent, Channel) or not ent.broadcast:
                        skip[name] = time.time() + 86400  # no such channel, or a group: the bot keeps its card, nothing to mirror
                    else:
                        await self.client(JoinChannelRequest(ent))
                        mirror.joined(self.con, ent.id, name)
                        log.warning("userbot: joined @%s", name)
                        await self.first(ent)
            except FloodWaitError as exc:
                log.warning("userbot: flood wait %ds", exc.seconds)
                await asyncio.sleep(exc.seconds + 5)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("userbot joins")
            await asyncio.sleep(JOIN_GAP)

    async def first(self, ent) -> None:
        """A first link: the channel's last few posts of the last month (an album is one), oldest first."""
        since, picked, groups = time.time() - mirror.FIRST_DAYS * 86400, [], set()
        async for m in self.client.iter_messages(ent, limit=mirror.FIRST_TAKE * 10):
            if m.date.timestamp() < since:
                break
            if m.action is not None:
                continue
            key = m.grouped_id or -m.id
            if key not in groups:
                if len(groups) == mirror.FIRST_TAKE:
                    break
                groups.add(key)
            picked.append(m)
        for m in reversed(picked):
            await self.guard(self.post(m))

    async def sweeps(self) -> None:
        """Every half hour, per mirrored channel: the posts missed while away, then the last week's posts again (views,
        reactions, an edit missed; one Telegram no longer has was deleted)."""
        from telethon.errors import FloodWaitError
        from telethon.tl.types import PeerChannel
        while True:
            try:
                for (channel,) in logic.rows(self.con, "SELECT id FROM tg_channels ORDER BY id"):
                    if mirror.source(self.con, channel) is None:
                        continue
                    try:
                        ent = await self.client.get_input_entity(PeerChannel(channel))
                    except (ValueError, TypeError):
                        continue  # not among its dialogs (left by hand?): the joins put it right
                    since = time.time() - mirror.FIRST_DAYS * 86400
                    async for m in self.client.iter_messages(ent, min_id=mirror.last(self.con, channel), reverse=True, limit=50):
                        if m.date.timestamp() >= since:
                            await self.guard(self.post(m))
                    ids = mirror.recent(self.con, channel)
                    for i in range(0, len(ids), 100):
                        chunk = ids[i:i + 100]
                        got = await self.client.get_messages(ent, ids=chunk)
                        mirror.gone(self.con, channel, [n for n, m in zip(chunk, got) if m is None])
                        for m in got:
                            if m is not None:
                                await self.guard(self.post(m))
                    await asyncio.sleep(2)
            except FloodWaitError as exc:
                log.warning("userbot: flood wait %ds", exc.seconds)
                await asyncio.sleep(exc.seconds + 5)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("userbot sweep")
            await asyncio.sleep(SWEEP_GAP)
