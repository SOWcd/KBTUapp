"""Studio → Chats → "Roles and admins" (owner, Nov 13): where a club's roles in the app and the admins of its linked group
drift apart. Read-only: asked of Telegram when the sheet opens (the bot's own status, the group's admins, then each of the
club's people with a role who isn't one of them, at most ASK_CAP a request) and kept per worker for FRESH. Nothing stored,
nothing changed in Telegram. The client gets app names (and app ids of the club's own people), never a Telegram id; the
admins without the app only as a count; bots and anonymous admins not at all."""
from __future__ import annotations

import time

from .chatlist import may_chats
from .core import PERSON_COLS, ApiError, Viewer, one, rows, shown_name

FRESH = 300      # seconds a chat's answer is kept (per worker: another worker asks Telegram itself)
ASK_CAP = 60     # getChatMember calls for the club's people a request
_seen: dict[int, tuple[float, tuple, dict]] = {}  # Telegram chat id -> (until, the people asked about, Telegram's side)


def target(con, v: Viewer, oid: int, cid: int) -> int:
    """The Telegram id of this club's group where our bot sits; for whoever manages the club's chats in Studio."""
    may_chats(con, v, oid)
    c = one(con, "SELECT tg_chat_id FROM chats WHERE id = ? AND org_id = ? AND kind = 'group' AND tg_chat_id IS NOT NULL", cid, oid)
    if not c:
        raise ApiError("not_found")
    return c[0]


def leaders(con, oid: int) -> list:
    """The club's people with a role (a level above member, or one of the club's own), highest first."""
    return rows(con, f"""SELECT u.tg_id, {PERSON_COLS} FROM org_members m JOIN users u ON u.id = m.user_id LEFT JOIN students s ON s.user_id = u.id
        WHERE m.org_id = ? AND (m.role != 'member' OR m.role_id IS NOT NULL)
        ORDER BY CASE m.role WHEN 'president' THEN 0 WHEN 'vice' THEN 1 WHEN 'head' THEN 2 ELSE 3 END, u.id""", oid)


async def ask(call, bot_id: int, chat: int, people: list[int]) -> dict:
    """Telegram's side: {"state": "ok", "admins": [shown admins' ids], "status": {id: "admin" | "in" | "out"}, "capped"},
    or {"state": "gone" | "notAdmin" | "unavailable"} (not kept). call(method, params): bot._call's answer or None."""
    key, hit = tuple(people), _seen.get(chat)
    if hit and hit[0] > time.monotonic() and hit[1] == key:
        return hit[2]
    me = await call("getChatMember", {"chat_id": chat, "user_id": bot_id})
    if not me:
        return {"state": "unavailable"}
    st = (me.get("result") or {}).get("status") if me.get("ok") else None
    if st in (None, "left", "kicked"):  # removed from the group, or the group is gone
        return {"state": "gone"}
    if st != "administrator":
        return {"state": "notAdmin"}
    r = await call("getChatAdministrators", {"chat_id": chat})
    if not (r and r.get("ok")):
        return {"state": "unavailable"}
    humans = [a for a in r["result"] if not (a.get("user") or {}).get("is_bot")]
    every = {a["user"]["id"] for a in humans}
    status: dict[int, str] = {tg: "admin" for tg in people if tg in every}
    rest = [tg for tg in people if tg not in every]
    for tg in rest[:ASK_CAP]:
        m = await call("getChatMember", {"chat_id": chat, "user_id": tg})
        if not m:
            return {"state": "unavailable"}
        x = (m.get("result") or {}) if m.get("ok") else {}  # not ok: Telegram doesn't know them there
        s = x.get("status")
        status[tg] = "admin" if s in ("creator", "administrator") else "in" if s == "member" or (s == "restricted" and x.get("is_member")) else "out"
    out = {"state": "ok", "admins": [a["user"]["id"] for a in humans if not a.get("is_anonymous")], "status": status, "capped": len(rest) > ASK_CAP}
    _seen[chat] = (time.monotonic() + FRESH, key, out)
    return out


def hint(con, oid: int, got: dict) -> dict:
    """The sheet: admins with no role in the app (an app id only for the club's own people; the rest of them a count),
    and the club's people with a role who aren't admins there, in the group or not."""
    if got["state"] != "ok":
        return {"state": got["state"]}
    tgs = got["admins"]
    known = {p["tg_id"]: p for p in rows(con, f"""SELECT u.tg_id, {PERSON_COLS}, m.role AS club_role, m.role_id FROM users u
        LEFT JOIN students s ON s.user_id = u.id LEFT JOIN org_members m ON m.user_id = u.id AND m.org_id = ?
        WHERE u.tg_id IN ({",".join("?" * len(tgs))})""", oid, *tgs)} if tgs else {}
    admins = [{"id": p["id"] if p["club_role"] else None, "name": shown_name(p)} for tg in tgs if (p := known.get(tg))
              and (p["club_role"] is None or (p["club_role"] == "member" and p["role_id"] is None))]
    lead = [{"id": p["id"], "name": shown_name(p), "inGroup": got["status"][p["tg_id"]] == "in"}
            for p in leaders(con, oid) if got["status"].get(p["tg_id"]) in ("in", "out")]
    return {"state": "ok", "admins": sorted(admins, key=lambda x: x["name"]), "others": len(tgs) - len(known), "leaders": lead, "capped": got["capped"]}
