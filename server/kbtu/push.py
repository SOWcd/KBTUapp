"""Personal notifications on ONE channel per person, never both (owner, Nov 25). The postman (bot.send_due) renders
each queued message once; while the person has a live app token and keeps "Notifications: app" (users.notify_via,
the default), it goes as a push only. A push that fails sends it to the bot at once and marks the token dead (the
app's next launch registers it again); a token unseen for STALE counts for nothing. Group things (/all, the channel's
posts, replies in groups) never come here: they stay Telegram.

Providers are plain modules with on(cfg) and send(cfg, token, text, start) -> 'ok' | 'gone' | 'failed' | 'down'
('down': no word about the token, e.g. the provider unreachable): apns.py for the iPhone app; the Android app's FCM
goes in PROVIDERS beside it, nothing else changes."""
from __future__ import annotations

import anyio

from . import apns
from .config import Config
from .logic.core import rows

PROVIDERS = {"apns": apns}
STALE = 60 * 86400  # the app registers its token on every launch: two months unopened, the bot again

# this user has a live token (format with the user's id column; bind now - STALE): the postman's and Settings' test
LIVE = "EXISTS (SELECT 1 FROM push_devices p WHERE p.user_id = {} AND p.dead_at IS NULL AND p.created_at > ?)"


def on(cfg: Config) -> bool:
    return any(p.on(cfg) for p in PROVIDERS.values())


def live(con, uid: int, at: int) -> list[tuple[str, str]]:
    """(token, provider) of each live device of this person."""
    return [(r[0], r[1]) for r in rows(con, """SELECT token, provider FROM push_devices
        WHERE user_id = ? AND dead_at IS NULL AND created_at > ?""", uid, at - STALE)]


def _gone(con, token: str, got: str, at: int) -> None:
    if got == "gone":  # dead for good (the app deleted): dropped
        con.execute("DELETE FROM push_devices WHERE token = ?", (token,))
    else:
        con.execute("UPDATE push_devices SET dead_at = ? WHERE token = ?", (at, token))


async def deliver(cfg: Config, con, uid: int, text: str, start: str, at: int) -> bool:
    """To each live device of this person; True when at least one took it (else the caller sends it to the bot)."""
    sent = False
    for token, provider in await anyio.to_thread.run_sync(live, con, uid, at):
        p = PROVIDERS.get(provider)
        if p is None or not p.on(cfg):
            continue
        got = await p.send(cfg, token, text, start)
        if got in ("gone", "failed"):
            await anyio.to_thread.run_sync(_gone, con, token, got, at)
        sent = sent or got == "ok"
    return sent
