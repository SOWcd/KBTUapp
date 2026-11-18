"""/all's member list (owner, Nov 18: call everyone, as other tag bots do): the Bot API lists no members, but our bot
signed in over MTProto (Telethon, with its own token) may read a group's participants. Never the userbot (userbot.py,
a person's account): a separate client, signed in as the bot. It only ever lists the participants of the chat an /all
was just typed in, at that moment; it registers no handlers and asks for no updates (receive_updates off), so it reads
no messages. The list is used for that run and kept nowhere (a two-minute memory per chat so a lone caller can't make
it read Telegram on every message); only Telegram ids leave this module, never names. Its session (a credential:
never logged) is kept in meta `mtbot:<bot id>` so it signs in once, not each time (Telegram limits bot sign-ins).
TG_API_ID and TG_API_HASH unset, Telethon missing or the sign-in refused: off, one log line, /all calls whom the
app knows and the bot saw, as before."""
from __future__ import annotations

import asyncio
import logging
import time

from . import db
from .config import Config

log = logging.getLogger("kbtu.mtbot")

TIMEOUT = 10        # a hung MTProto call never holds /all longer than this
FLOOD_SLEEP = 5     # a FloodWait this short is slept off (Telethon's own), a longer one: no list this time
RETRY = 600         # after a failed sign-in or connect, tried again no sooner (bot sign-ins are rate-limited)
KEEP = 120          # a chat's list (or its failure) remembered this long, per process
_client = None
_loop = None
_lock: asyncio.Lock | None = None
_down_until = 0.0
_said: set[str] = set()     # each reason it's off logged once a process
_memo: dict[int, tuple[float, list[int] | None]] = {}


def _off(why: str) -> None:
    if why not in _said:
        _said.add(why)
        log.warning("mtbot: off (%s)", why)


async def _connect(cfg: Config):
    """The process's one client, signed in as the bot; its session saved after a fresh sign-in."""
    global _client, _loop, _lock, _down_until
    loop = asyncio.get_running_loop()
    if _loop is not loop:  # ponytail: one client per event loop (the bot's one); a new loop (a restart in tests) starts afresh
        _client, _loop, _lock = None, loop, asyncio.Lock()
    async with _lock:
        if _client is not None and _client.is_connected():
            return _client
        if time.monotonic() < _down_until:
            return None
        if not (cfg.tg_api_id.isdigit() and cfg.tg_api_hash):
            _off("no TG_API_ID / TG_API_HASH")
            return None
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
        except ImportError:
            _off("telethon is not installed")
            return None
        key = f"mtbot:{cfg.bot_token.split(':')[0]}"  # per bot: a new token for another bot never reuses the old session
        con = db.connect(cfg.db_path)
        try:
            row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            client = _client or TelegramClient(StringSession(row[0] if row else None), int(cfg.tg_api_id), cfg.tg_api_hash,
                                               receive_updates=False, flood_sleep_threshold=FLOOD_SLEEP)
            try:
                await asyncio.wait_for(client.start(bot_token=cfg.bot_token), TIMEOUT)
            except Exception as exc:  # noqa: BLE001 - refused, revoked, a long FloodWait, the network: off for a while
                _down_until = time.monotonic() + RETRY
                log.warning("mtbot: sign-in failed (%s), /all without the member list", type(exc).__name__)  # never the token
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                _client = None
                return None
            if (s := client.session.save()) != (row[0] if row else None):
                con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, s))
                log.warning("mtbot: signed in as the bot")
            _client = client
            return client
        finally:
            con.close()


async def members(cfg: Config, chat: int, cap: int) -> list[int] | None:
    """The people in a group now by Telegram's own list (Bot API chat id: a supergroup -100<id>, a basic group -<id>),
    at most `cap` of them, read no further; never a bot or a deleted account. None: no list (off, no right to see the
    members, a long FloodWait, a timeout)."""
    t = time.monotonic()
    if (m := _memo.get(chat)) and t - m[0] < KEEP:
        return m[1]
    got = None
    try:
        if client := await _connect(cfg):
            got = await asyncio.wait_for(_read(client, chat, cap), TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - hidden members, kicked meanwhile, FloodWait, timeout: as if off
        log.warning("mtbot: members: %s", type(exc).__name__)
    if len(_memo) > 1000:  # a few hundred ids a chat, the bot sits in few
        _memo.clear()
    _memo[chat] = (t, got)
    return got


async def _read(client, chat: int, cap: int) -> list[int]:
    from telethon import utils
    pid, kind = utils.resolve_id(chat)
    out = []
    async for u in client.iter_participants(await client.get_input_entity(kind(pid)), limit=cap):
        if not (u.bot or u.deleted):
            out.append(u.id)
    return out
