"""/all's member list (owner, Nov 18: call everyone, as other tag bots do): the Bot API lists no members, but our bot
signed in over MTProto (Telethon, with its own token) may read a group's participants. Never the userbot (userbot.py,
a person's account): a separate client, signed in as the bot. It only ever lists the participants of the chat an /all
was just typed in, at that moment: connected for that read and disconnected right after (no idle connection, so
Telethon never asks for missed updates), every request without updates, no handlers, no catch-up; it reads no
messages. Names and usernames Telegram returns are not cached (_NoNames). The list is used for that run and kept
nowhere (a two-minute memory per chat so a lone caller can't make it read Telegram on every message); only Telegram
ids, the deleted ones and whether members are hidden leave this module.
TG_API_ID and TG_API_HASH unset, Telethon missing, the sign-in refused or a long FloodWait: no list, one log line,
/all calls whom the app knows and the bot saw, as before."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import NamedTuple

from .config import Config

log = logging.getLogger("kbtu.mtbot")

TIMEOUT = 10        # a hung MTProto call never holds /all longer than this
FLOOD_SLEEP = 5     # a FloodWait this short is slept off (Telethon's own), a longer one: no list until it ends
RETRY = 600         # after a failed sign-in or a dead session, tried again no sooner
KEEP = 120          # a chat's list (or its failure) remembered this long, per process
MEMO_MAX = 1000


class Roster(NamedTuple):
    ids: list[int]      # people in the chat (never a bot or a deleted account), at most the cap
    hidden: bool        # the chat hides its members from members (only its admins may see them)
    skip: set[int]      # bots and deleted accounts Telegram listed: never called this run, whatever else knows them


# ponytail: signed in once per process start, the session in memory only (never in the database or its backups);
# a session file outside the backups if deploys grow too many for Telegram's limit on bot sign-ins
_client = None
_loop = None
_lock: asyncio.Lock | None = None
_down_until = 0.0
_said: set[str] = set()     # each reason it's off logged once a process
_memo: dict[int, tuple[float, Roster | None]] = {}


def _off(why: str) -> None:
    if why not in _said:
        _said.add(why)
        log.warning("mtbot: off (%s)", why)


def _new_client(cfg: Config):
    from telethon import TelegramClient
    from telethon.sessions import MemorySession

    class _NoNames(MemorySession):
        def process_entities(self, tlo) -> None:  # Telethon would keep every name and username it saw: nothing
            pass
    return TelegramClient(_NoNames(), int(cfg.tg_api_id), cfg.tg_api_hash, receive_updates=False, catch_up=False,
                          flood_sleep_threshold=FLOOD_SLEEP)


async def members(cfg: Config, chat: int, cap: int) -> Roster | None:
    """The people in a group now by Telegram's own list (Bot API chat id: a supergroup -100<id>, a basic group -<id>),
    at most `cap` of them, read no further. None: no list (off, no right to see the members, a FloodWait, a timeout).
    One read at a time a process (they share the connection), each bounded by TIMEOUT."""
    global _client, _loop, _lock, _down_until
    t = time.monotonic()
    for k in [k for k, (at, _) in _memo.items() if t - at >= KEEP]:
        del _memo[k]
    if chat in _memo:
        return _memo[chat][1]
    if not (cfg.tg_api_id.isdigit() and cfg.tg_api_hash):
        _off("no TG_API_ID / TG_API_HASH")
        return None
    try:
        from telethon.errors import AuthKeyError, FloodWaitError, UnauthorizedError
    except ImportError:
        _off("telethon is not installed")
        return None
    loop = asyncio.get_running_loop()
    if _loop is not loop:  # one client per event loop (the bot's one); a new loop (tests) starts afresh
        _client, _loop, _lock = None, loop, asyncio.Lock()
    got = None
    async with _lock:
        if time.monotonic() < _down_until:
            return None
        try:
            got = await asyncio.wait_for(_session(cfg, chat, cap), TIMEOUT)
        except FloodWaitError as exc:  # longer than FLOOD_SLEEP: no list until Telegram's wait ends
            _down_until = time.monotonic() + exc.seconds
            log.warning("mtbot: FloodWait %d s, /all without the member list", exc.seconds)
        except (UnauthorizedError, AuthKeyError) as exc:  # refused, revoked, duplicated: a fresh sign-in after RETRY
            _down_until = time.monotonic() + RETRY
            log.warning("mtbot: session dropped (%s)", type(exc).__name__)  # never the token
            await close()
        except Exception as exc:  # noqa: BLE001 - hidden members, kicked meanwhile, a timeout, the network: no list
            log.warning("mtbot: members: %s", type(exc).__name__)
        finally:
            await _hang_up()
    if len(_memo) >= MEMO_MAX:
        _memo.clear()
    _memo[chat] = (time.monotonic(), got)
    return got


async def _session(cfg: Config, chat: int, cap: int) -> Roster:
    global _client
    if _client is None:
        _client = _new_client(cfg)
    await _client.connect()
    if not await _client.is_user_authorized():
        await _client.sign_in(bot_token=cfg.bot_token)
        log.warning("mtbot: signed in as the bot")
    return await _read(_client, chat, cap)


async def _read(client, chat: int, cap: int) -> Roster:
    from telethon import utils
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.types import PeerChannel
    pid, kind = utils.resolve_id(chat)
    ent = await client.get_input_entity(kind(pid))
    hidden = kind is PeerChannel and bool((await client(GetFullChannelRequest(ent))).full_chat.participants_hidden)
    ids, skip = [], set()
    async for u in client.iter_participants(ent, limit=cap):
        if u.bot or u.deleted:
            skip.add(u.id)
        else:
            ids.append(u.id)
    return Roster(ids, hidden, skip)


async def _hang_up() -> None:
    """Disconnected between reads (the session stays signed in, in memory)."""
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def close() -> None:
    """The bot's shutdown, or a dead session: disconnected and forgotten."""
    global _client
    await _hang_up()
    _client = None
