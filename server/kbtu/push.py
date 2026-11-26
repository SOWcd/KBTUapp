"""Personal notifications on ONE channel per person, never both (owner, Nov 25). The postman (bot.send_due) renders
each queued message once; while the person has a live app token and keeps "Notifications: app" (users.notify_via,
the default), it goes as a push only. If no device takes it, the postman falls back to the bot. A provider's explicit
token rejection drops that token (the app's next launch registers it again); a token unseen for STALE counts for
nothing. Group things (/all, the channel's posts, replies in groups) never come here: they stay Telegram.

Providers are plain modules with on(cfg) and send(cfg, token, text, start) -> 'ok' | 'gone' | 'down'
('down': no word about the token, e.g. the provider unreachable): apns.py for the iPhone app; the Android app's FCM
goes in PROVIDERS beside it, nothing else changes."""
from __future__ import annotations

import asyncio

import anyio

from . import apns
from .config import Config
from .logic import web_auth
from .logic.core import rows

PROVIDERS = {"apns": apns}
STALE = 60 * 86400  # the app registers its token on every launch: two months unopened, the bot again

# a live token: seen within STALE, and its session still signs in (web_auth.lookup's idle and age limits) at this very
# moment, not only once the night's sweep (web_auth.forget) drops it
_FROM = "push_devices p JOIN web_sessions s ON s.digest = p.session AND s.user_id = p.user_id " \
        "JOIN users u ON u.id = s.user_id LEFT JOIN students st ON st.user_id = u.id"
_VALID = f"""p.dead_at IS NULL AND p.created_at > ? AND s.last_used_at > ?
    AND s.created_at > ? - ({web_auth._AGE_LIMIT}) AND u.banned_at IS NULL AND u.tg_id > 0"""
# this user has a live token (format with the user's id column; bind *bounds(now)): the postman's and Settings' test
LIVE = f"EXISTS (SELECT 1 FROM {_FROM} WHERE p.user_id = {{}} AND {_VALID})"


def bounds(at: int) -> tuple[int, int, int]:
    return at - STALE, at - web_auth.IDLE, at


def on(cfg: Config) -> bool:
    return any(p.on(cfg) for p in PROVIDERS.values())


def live(con, uid: int, at: int) -> list[tuple[str, str]]:
    """(token, provider) of each live device of this person."""
    return [(r[0], r[1]) for r in rows(con, f"SELECT p.token, p.provider FROM {_FROM} WHERE p.user_id = ? AND {_VALID}",
                                       uid, *bounds(at))]


def _gone(con, token: str) -> None:
    con.execute("DELETE FROM push_devices WHERE token = ?", (token,))


async def deliver(cfg: Config, con, uid: int, text: str, start: str, at: int, lock: asyncio.Lock) -> bool:
    """To each live device of this person; True when at least one took it (else the caller sends it to the bot)."""
    sent = False
    async with lock:
        devices = await anyio.to_thread.run_sync(live, con, uid, at)
    for token, provider in devices:
        p = PROVIDERS.get(provider)
        if p is None or not p.on(cfg):
            continue
        got = await p.send(cfg, token, text, start)
        if got == "gone":
            async with lock:
                await anyio.to_thread.run_sync(_gone, con, token)
        sent = sent or got == "ok"
    return sent
