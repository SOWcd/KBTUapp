"""A club's members mirrored from its Telegram chats (CHAT_SYNC=1; SITE Senate first, owner Nov 10).

The app's creator links a chat (admin chatsync): a club's main chat is its membership, a department's chat that
department. The bot is an admin there (no rights needed) and hears chat_member updates: someone in the chat who is a
verified student (Microsoft, students.manual = 0) on the policy in force joins the club as a Member, or the department
if already in the club; leaving or kicked takes them out the way a manual removal does (teams._remove; set_dept), audited
with actor None and {"sync": chat}. The President is never taken out. A person the club took out by hand (or banned) is
not added back until they join the chat again after that. A sweep (getChatMember for each candidate, paced by the bot)
finds what updates missed; its findings wait in chat_sync_todo and go at its end, unless more than half would leave: then
the link pauses and nothing is removed. Any doubt (the bot not an admin, a Telegram error) pauses the link: no removals at
all until the creator runs it again. Nothing about people without an account, no update or message is stored."""
from __future__ import annotations

import json
import logging

from ..db import tx
from . import core
from .core import ApiError, log_action, one, rows

log = logging.getLogger("kbtu.chatsync")

POLICY = ""   # the privacy policy in force with CHAT_SYNC on (app.create, admin); empty: all of this is off
STEP = 40     # people a sweep checks per step; the bot paces the calls (bot.SYNC_GAP)
ODD = 3       # a sweep may remove this many whatever the club's size; more than half of it pauses instead
GONE = ("user not found", "participant_id_invalid", "user_id_invalid")  # Telegram knows no such user: not in the chat


def in_chat(m: dict) -> bool:
    """A ChatMember is in the chat: restricted ones too while is_member."""
    st = m.get("status")
    return st in ("creator", "administrator", "member") or st == "restricted" and bool(m.get("is_member"))


def _consents() -> tuple[str, str]:
    from .account import CONSENT_VOL
    return POLICY, POLICY + CONSENT_VOL


# who the sync may act on: a verified student (not typed in by hand, not staff), not banned or leaving, on the policy in force
OK = """u.tg_id > 0 AND u.banned_at IS NULL AND u.delete_at IS NULL AND s.manual = 0
    AND s.consent_version IN (?, ?, 'admin')"""


def _student(con, tg_id: int) -> int | None:
    r = one(con, f"SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE u.tg_id = ? AND {OK}", tg_id, *_consents())
    return r[0] if r else None


def _held(con, link, uid: int) -> int:
    """When the club last took them out by hand, if that was the last change by anyone (0: not held). A department's:
    its last hand-made "off"."""
    if link["kind"] == "main":
        r = one(con, """SELECT at, json_extract(data, '$.sync') AS s FROM audit_log WHERE target = ? AND action = 'role_change'
            AND json_extract(data, '$.org') = ? AND json_extract(data, '$.role') = 'none' ORDER BY id DESC LIMIT 1""", f"user:{uid}", link["org_id"])
        return r["at"] if r and r["s"] is None else 0
    r = one(con, """SELECT at, json_extract(data, '$.sync') AS s, json_extract(data, '$.on') AS x FROM audit_log WHERE target = ?
        AND action = 'member_dept' AND json_extract(data, '$.tag') = ? ORDER BY id DESC LIMIT 1""", f"user:{uid}", link["tag_id"])
    return r["at"] if r and r["s"] is None and not r["x"] else 0


def _role(con, oid: int, uid: int) -> str | None:
    r = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)
    return r[0] if r else None


def _has(con, link, uid: int) -> bool:
    return bool(one(con, "SELECT 1 FROM member_tags WHERE tag_id = ? AND user_id = ?", link["tag_id"], uid))


def _wants(con, link, uid: int, inside: bool, at: int | None = None) -> str | None:
    """What the chat says to do with them: 'add', 'drop' or nothing. at: when they joined the chat (an update's date);
    None: a sweep, which never knows it, so one held stays out."""
    oid, role = link["org_id"], _role(con, link["org_id"], uid)
    if link["kind"] == "main":
        if role and not inside:
            return "drop" if role != "president" else None
        if not role and inside and not banned(con, oid, uid):
            h = _held(con, link, uid)
            return "add" if not h or at is not None and at > h else None
        return None
    if not role:
        return None
    has = _has(con, link, uid)
    if has and not inside:
        return "drop"
    if not has and inside:
        h = _held(con, link, uid)
        return "add" if not h or at is not None and at > h else None
    return None


def _do(con, link, uid: int, op: str) -> bool:
    """One change, inside the caller's transaction, exactly as by hand."""
    oid, chat = link["org_id"], link["chat_id"]
    if link["kind"] == "dept":
        return set_dept(con, None, oid, uid, link["tag_id"], op == "add", sync=chat)
    if op == "drop":
        if _role(con, oid, uid) in (None, "president"):
            return False
        _remove(con, None, oid, uid, False, "sync", {"sync": chat})
        return True
    if not con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (oid, uid, core.now())).rowcount:
        return False
    joined(con, oid, uid)
    con.execute("UPDATE join_requests SET status = 'accepted', decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'", (core.now(), oid, uid))
    log_action(con, None, "role_change", f"user:{uid}", json.dumps({"org": oid, "role": "member", "by": "sync", "sync": chat}))
    return True


def pause(con, chat: int, why: str) -> None:
    """Something's off: no more changes from this chat until the creator runs it again; a sweep's findings go."""
    with tx(con):
        if con.execute("UPDATE chat_sync SET paused = ?, sweep = NULL, sweep_pos = 0, result = ? WHERE chat_id = ?", (why, f"paused: {why}", chat)).rowcount:
            con.execute("DELETE FROM chat_sync_todo WHERE chat_id = ?", (chat,))
            log_action(con, None, "chat_sync_pause", f"chat:{chat}", json.dumps({"why": why}))
            log.warning("chat sync %d paused: %s", chat, why)


def bot_status(con, chat: int, status: str | None) -> None:
    """my_chat_member: the bot demoted, kicked or gone from a linked chat pauses it (updates stop, a sweep can't see)."""
    if POLICY and status != "administrator" and one(con, "SELECT 1 FROM chat_sync WHERE chat_id = ? AND paused IS NULL", chat):
        pause(con, chat, "the bot is not an admin")


def member_update(con, upd: dict) -> None:
    """A chat_member update: someone joined or left a linked chat. Strangers, bots and changes inside the chat are ignored."""
    if not POLICY:
        return
    chat = (upd.get("chat") or {}).get("id")
    new, old = upd.get("new_chat_member") or {}, upd.get("old_chat_member") or {}
    user = new.get("user") or {}
    link = one(con, "SELECT * FROM chat_sync WHERE chat_id = ? AND paused IS NULL", chat) if chat else None
    if not link or user.get("is_bot") or in_chat(old) == in_chat(new):
        return
    uid = _student(con, int(user.get("id") or 0))
    if not uid:
        return
    with tx(con):
        con.execute("DELETE FROM chat_sync_todo WHERE chat_id = ? AND user_id = ?", (link["chat_id"], uid))  # newer than a sweep's look
        if op := _wants(con, link, uid, in_chat(new), int(upd.get("date") or 0)):
            _do(con, link, uid, op)


# ---------------------------------------------------------------- the sweep (bot._chat_sync runs it, admin chatsync run starts it)

def _candidates(con, link, after: int, n: int) -> list:
    """Whom a sweep checks next, by id: for a main chat every verified student (the nightly look: only the club's members),
    for a department's chat only the club's members."""
    members = link["kind"] == "dept" or link["sweep"] == "night"
    return rows(con, f"""SELECT u.id, u.tg_id FROM users u JOIN students s ON s.user_id = u.id
        {"JOIN org_members m ON m.user_id = u.id AND m.org_id = " + str(int(link["org_id"])) if members else ""}
        WHERE {OK} AND u.id > ? ORDER BY u.id LIMIT ?""", *_consents(), after, n)


async def step(con, call, bot_id: int, n: int = STEP) -> bool:
    """One sweep a few people further. call(method, params): Telegram's answer (a dict), None when it couldn't be asked
    (the network: the same people next time). False: no sweep waiting."""
    link = one(con, "SELECT * FROM chat_sync WHERE sweep IS NOT NULL AND paused IS NULL ORDER BY chat_id LIMIT 1") if POLICY else None
    if not link:
        return False
    chat = link["chat_id"]
    me = await call("getChatMember", {"chat_id": chat, "user_id": bot_id})
    if me is None:
        return True
    if not me.get("ok") or (me.get("result") or {}).get("status") != "administrator":
        pause(con, chat, "the bot is not an admin")
        return True
    batch = _candidates(con, link, link["sweep_pos"], n)
    for u in batch:
        r = await call("getChatMember", {"chat_id": chat, "user_id": u["tg_id"]})
        if r is None:
            return True
        if r.get("ok"):
            inside = in_chat(r.get("result") or {})
        elif any(g in str(r.get("description")).lower() for g in GONE):
            inside = False
        else:
            pause(con, chat, f"getChatMember: {str(r.get('description'))[:80]}")
            return True
        with tx(con):
            now_link = one(con, "SELECT * FROM chat_sync WHERE chat_id = ? AND paused IS NULL AND sweep IS NOT NULL", chat)
            if not now_link:  # paused or unlinked meanwhile
                return True
            if op := _wants(con, now_link, u["id"], inside):
                con.execute("INSERT OR REPLACE INTO chat_sync_todo (chat_id, user_id, op) VALUES (?, ?, ?)", (chat, u["id"], op))
            con.execute("UPDATE chat_sync SET sweep_pos = ? WHERE chat_id = ?", (u["id"], chat))
    if len(batch) < n:
        finish(con, chat)
    return True


def finish(con, chat: int) -> str | None:
    """A sweep's end: a dry run counts, otherwise the findings go in one transaction; an implausible drop pauses."""
    link = one(con, "SELECT * FROM chat_sync WHERE chat_id = ? AND sweep IS NOT NULL AND paused IS NULL", chat)
    if not link:
        return None
    todo = rows(con, "SELECT user_id, op FROM chat_sync_todo WHERE chat_id = ? ORDER BY user_id", chat)
    drops = sum(t["op"] == "drop" for t in todo)
    base = one(con, "SELECT COUNT(*) FROM org_members WHERE org_id = ?", link["org_id"])[0] if link["kind"] == "main" else \
        one(con, "SELECT COUNT(*) FROM member_tags WHERE tag_id = ?", link["tag_id"])[0]
    if drops > ODD and drops * 2 > base:
        pause(con, chat, f"implausible drop: {drops} of {base} would leave")
        return None
    with tx(con):
        if link["sweep"] == "dry":
            result = f"dry run: would add {len(todo) - drops}, would remove {drops}"
        else:
            done = {"add": 0, "drop": 0}
            for t in todo:
                if _wants(con, link, t["user_id"], t["op"] == "add") == t["op"] and _do(con, link, t["user_id"], t["op"]):
                    done[t["op"]] += 1
            result = f"{link['sweep']}: added {done['add']}, removed {done['drop']}"
        con.execute("DELETE FROM chat_sync_todo WHERE chat_id = ?", (chat,))
        con.execute("UPDATE chat_sync SET sweep = NULL, sweep_pos = 0, result = ? WHERE chat_id = ?", (result, chat))
    return result


def night(con) -> None:
    """Nightly (daily.stats_day): every live link looks at the club's current members again, for updates missed while the
    bot was down (Telegram keeps them 24 hours)."""
    if POLICY:
        con.execute("UPDATE chat_sync SET sweep = 'night', sweep_pos = 0 WHERE paused IS NULL AND sweep IS NULL")


# ---------------------------------------------------------------- the creator's commands (admin chatsync)

def link(con, slug: str, chat: int, kind: str, tag: str | None = None) -> None:
    o = one(con, "SELECT id FROM orgs WHERE slug = ?", slug)
    if not o or kind not in ("main", "dept") or (kind == "dept") != bool(tag):
        raise ApiError("bad_input")
    t = one(con, "SELECT id FROM org_tags WHERE org_id = ? AND lower(name) = lower(?) AND department = 1", o[0], tag) if tag else None
    if tag and not t:
        raise ApiError("not_found", "department")
    with tx(con):
        try:
            con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, tag_id, created_at) VALUES (?, ?, ?, ?, ?)", (chat, o[0], kind, t and t[0], core.now()))
        except Exception as exc:  # noqa: BLE001 - sqlite3.IntegrityError: the chat or the club's main chat linked already
            raise ApiError("conflict") from exc
        log_action(con, None, "chat_sync_link", f"chat:{chat}", json.dumps({"org": o[0], "kind": kind, "tag": t and t[0]}))


def unlink(con, chat: int) -> bool:
    with tx(con):
        if con.execute("DELETE FROM chat_sync WHERE chat_id = ?", (chat,)).rowcount:
            log_action(con, None, "chat_sync_unlink", f"chat:{chat}")
            return True
    return False


def start(con, chat: int, apply: bool) -> bool:
    """A sweep from the start (a paused link runs again: the creator looked)."""
    with tx(con):
        con.execute("DELETE FROM chat_sync_todo WHERE chat_id = ?", (chat,))
        n = con.execute("UPDATE chat_sync SET sweep = ?, sweep_pos = 0, paused = NULL, result = NULL WHERE chat_id = ?",
                        ("apply" if apply else "dry", chat)).rowcount
        if n:
            log_action(con, None, "chat_sync_run", f"chat:{chat}", json.dumps({"apply": apply}))
    return bool(n)


def links(con) -> list:
    return rows(con, """SELECT c.*, o.slug, g.name AS tag FROM chat_sync c JOIN orgs o ON o.id = c.org_id
        LEFT JOIN org_tags g ON g.id = c.tag_id ORDER BY o.slug, c.kind DESC, g.name""")


def live(con) -> bool:
    """Any link to hear: the bot asks Telegram for chat_member updates then."""
    return bool(POLICY) and bool(one(con, "SELECT 1 FROM chat_sync LIMIT 1"))


from .teams import _remove, banned, set_dept  # noqa: E402
from .seats import joined  # noqa: E402
