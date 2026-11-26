"""The app's own Telegram channel and topics group (@KBTUappNews, @KBTUappTop): whether I am in them, so Profile shows
their rows only to who isn't. The bot is an admin in both and hears their joins and leaves (chat_member updates);
besides, /api/me asks Telegram (getChatMember) at most once a day per person, after its answer, never the app itself.
Two yes/no facts for the UI and nothing else: no message, no list of the chat; gone with the account."""
from __future__ import annotations

import time
from typing import Awaitable, Callable

from .core import one

CHATS = {"channel": "KBTUappNews", "group": "KBTUappTop"}  # their t.me names (web AppCard, lib/feedback TALK)
_COL = {"channel": "channel", "group": "grp"}
DAY = 86400


def _kind(chat: dict) -> str | None:
    name = str(chat.get("username") or "").lower()
    return next((k for k, n in CHATS.items() if n.lower() == name), None)


def _in(m: dict) -> bool:
    """A ChatMember is in the chat (as logic.chatsync.in_chat): restricted ones too while is_member."""
    st = m.get("status")
    return st in ("creator", "administrator", "member") or st == "restricted" and bool(m.get("is_member"))


def _set(con, uid: int, kind: str, member: bool) -> None:
    col = _COL[kind]
    con.execute(f"INSERT INTO app_chats (user_id, {col}) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET {col} = excluded.{col}",
                (uid, int(member)))


def mine(con, uid: int) -> dict:
    """/api/me's two flags."""
    r = one(con, "SELECT channel, grp FROM app_chats WHERE user_id = ?", uid)
    return {"inChannel": bool(r and r["channel"]), "inGroup": bool(r and r["grp"])}


def heard(con, upd: dict) -> bool:
    """A chat_member update: True when it was one of ours (recorded for whoever has an account; nobody else is kept)."""
    kind = _kind(upd.get("chat") or {})
    if not kind:
        return False
    new = upd.get("new_chat_member") or {}
    tg = int((new.get("user") or {}).get("id") or 0)
    if tg > 0 and (u := one(con, "SELECT id FROM users WHERE tg_id = ?", tg)):
        _set(con, u["id"], kind, _in(new))
    return True


def due(con, uid: int, now: float | None = None) -> int | None:
    """My Telegram id when a look is due (none in the last day), the look claimed at once so a burst of /api/me asks
    once; None otherwise. Inside a write transaction (db.maybe)."""
    now = int(now if now is not None else time.time())
    r = one(con, "SELECT checked_at FROM app_chats WHERE user_id = ?", uid)
    if r and now - r["checked_at"] < DAY:
        return None
    u = one(con, "SELECT tg_id FROM users WHERE id = ?", uid)
    if not u or u["tg_id"] <= 0:
        return None
    con.execute("INSERT INTO app_chats (user_id, checked_at) VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET checked_at = excluded.checked_at",
                (uid, now))
    return u["tg_id"]


async def look(call: Callable[[str, dict], Awaitable[dict | None]], tg: int) -> dict[str, bool]:
    """Telegram's answer for both chats; a chat it didn't answer for (the network, the bot not an admin) is left out."""
    out = {}
    for kind, name in CHATS.items():
        r = await call("getChatMember", {"chat_id": f"@{name}", "user_id": tg})
        if r and r.get("ok"):
            out[kind] = _in(r.get("result") or {})
        elif r and r.get("error_code") == 400 and "not found" in str(r.get("description") or "").lower():
            out[kind] = False  # never was there
    return out


def save(con, uid: int, got: dict[str, bool]) -> None:
    for kind, member in got.items():
        _set(con, uid, kind, member)
