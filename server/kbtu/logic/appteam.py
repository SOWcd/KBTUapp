"""The app's own team: admins, moderators, bans, the audit log, the admin's clubs."""
from __future__ import annotations

import json
import re
import sqlite3

from ..db import tx

from .core import ApiError, PERSON, PERSON_COLS, RANK, Viewer, log_action, one, rows


# ---------------------------------------------------------------- admin: clubs and their teams (pilot, SPEC §2)

def _admin(v: Viewer) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")


def _mod(v: Viewer) -> None:
    """Moderators filter content (owner, Oct 22): the report queue, taking things down and back; the admin too."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")


# ---------------------------------------------------------------- the app's team (owner, Oct 22)
# The owner (admin + is_founder) has every right and alone gives or takes the admin role; an admin gives the
# moderator role and bans; nobody touches the owner, himself, or (unless the owner) another admin. All of it audited.

STAFF_ROLES = ("user", "moderator", "admin")
_STAFF = f"SELECT {PERSON_COLS}, u.tg_username, u.role, u.ban_reason FROM users u LEFT JOIN students s ON s.user_id = u.id"


def _owner(con, v: Viewer) -> bool:
    return v.role == "admin" and bool(one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)["is_founder"])


def _staff_row(p: sqlite3.Row) -> dict:
    return {"person": person_ref(p), "username": p["tg_username"], "role": p["role"], "owner": bool(p["is_founder"]),
            "banReason": p["ban_reason"]}


def staff(con, v: Viewer) -> dict:
    _admin(v)
    return {"team": [_staff_row(p) for p in rows(con, f"{_STAFF} WHERE u.role IN ('admin', 'moderator') AND u.tg_id > 0 ORDER BY u.is_founder DESC, u.role, u.id")],
            "banned": [_staff_row(p) for p in rows(con, f"{_STAFF} WHERE u.banned_at IS NOT NULL AND u.tg_id > 0 ORDER BY u.banned_at DESC, u.id DESC")],
            "owner": _owner(con, v)}


def find_anyone(con, v: Viewer, username: str) -> dict:
    """Anyone who opened the app, by @username: the team is picked from them."""
    _admin(v)
    name = str(username or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ApiError("bad_input")
    p = one(con, f"{_STAFF} WHERE lower(u.tg_username) = lower(?) AND u.tg_id > 0", name)
    if not p:
        raise ApiError("not_found")
    return {**_staff_row(p), "banned": one(con, "SELECT banned_at FROM users WHERE id = ?", p["id"])["banned_at"] is not None}


def _touchable(con, v: Viewer, uid) -> sqlite3.Row:
    _admin(v)
    if not isinstance(uid, int) or isinstance(uid, bool):
        raise ApiError("bad_input")
    u = one(con, "SELECT id, role, is_founder, banned_at FROM users WHERE id = ? AND tg_id > 0", uid)
    if not u:
        raise ApiError("not_found")
    if u["is_founder"] or u["id"] == v.id or (u["role"] == "admin" and not _owner(con, v)):
        raise ApiError("forbidden")
    return u


def set_staff(con, v: Viewer, uid, role) -> dict:
    if role not in STAFF_ROLES:
        raise ApiError("bad_input")
    with tx(con):
        u = _touchable(con, v, uid)
        if role == "admin" and not _owner(con, v):
            raise ApiError("forbidden")
        if u["banned_at"] is not None and role != "user":
            raise ApiError("conflict", "banned")
        if u["role"] != role:
            con.execute("UPDATE users SET role = ? WHERE id = ?", (role, u["id"]))
            log_action(con, v.id, "staff_role", f"user:{u['id']}", json.dumps({"from": u["role"], "to": role}))
    return staff(con, v)


def set_ban(con, v: Viewer, uid, on, reason=None) -> dict:
    """The platform ban (owner, Oct 22): no mutes, no strikes; the reason is required, he sees it, and the role goes.
    His posts stay (moderators hide what's bad); the bot stops writing to him."""
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    why = " ".join(str(reason or "").split())
    if on and not 3 <= len(why) <= 300:
        raise ApiError("bad_input", "reason")
    with tx(con):
        u = _touchable(con, v, uid)
        if on:
            con.execute("UPDATE users SET banned_at = ?, ban_reason = ?, role = 'user' WHERE id = ?", (core.now(), why, u["id"]))
        else:
            con.execute("UPDATE users SET banned_at = NULL, ban_reason = NULL WHERE id = ?", (u["id"],))
        log_action(con, v.id, "ban" if on else "unban", f"user:{u['id']}", json.dumps({"reason": why} if on else {}, ensure_ascii=False))
    return staff(con, v)


def ban_info(con, uid: int) -> dict:
    """What a banned person sees: why, and whom to write (the owner)."""
    u = one(con, "SELECT ban_reason FROM users WHERE id = ?", uid)
    o = one(con, "SELECT tg_username FROM users WHERE is_founder = 1 AND tg_id > 0")
    return {"reason": u["ban_reason"] if u else None, "contact": o["tg_username"] if o else None}


def audit(con, v: Viewer) -> list[dict]:
    """The owner's log of everything done with power: the last 200."""
    if not _owner(con, v):
        raise ApiError("forbidden")
    out = []
    for a in rows(con, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 200"):
        p = one(con, f"{PERSON} WHERE u.id = ?", a["actor_id"]) if a["actor_id"] else None
        kind, _, tid = a["target"].partition(":")
        named = None  # whom or what, readable: a person or an org by name
        if kind == "user" and tid.isdigit():
            u = one(con, f"{PERSON} WHERE u.id = ?", int(tid))
            named = shown_name(u) if u else None
        elif kind == "org" and tid.isdigit():
            o = one(con, "SELECT name FROM orgs WHERE id = ?", int(tid))
            named = o["name"] if o else None
        out.append({"id": a["id"], "actor": person_ref(p) if p else None, "action": a["action"], "target": a["target"],
                    "targetName": named, "data": json.loads(a["data"] or "{}"), "at": a["at"]})
    return out


def set_role(con, actor: int | None, uid: int, oid: int, role: str, by: str) -> None:
    """One person's role in a club, by the admin (the app or the CLI). One president per club: the old one steps down
    to vice. A role counts once the person has signed in with KBTU (only students act, SPEC §2)."""
    if role not in (*RANK, "none"):
        raise ApiError("bad_input")
    with tx(con):
        if role == "president":
            con.execute("UPDATE org_members SET role = 'vice', role_id = ? WHERE org_id = ? AND role = 'president' AND user_id != ?", (_official(con, oid, "vice"), oid, uid))
        if role == "none":
            con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, uid))
        else:
            con.execute("""INSERT INTO org_members (org_id, user_id, role, joined_at, role_id) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (org_id, user_id) DO UPDATE SET role = excluded.role, role_id = excluded.role_id""", (oid, uid, role, core.now(), _official(con, oid, role)))
        log_action(con, actor, "role_change", f"user:{uid}", json.dumps({"org": oid, "role": role, "by": by}))


def find_user(con, who: str) -> sqlite3.Row | None:
    """A Telegram account by @username or Telegram ID: the person must have opened the app once."""
    who = who.strip()
    if who.isdigit():
        return one(con, "SELECT * FROM users WHERE tg_id = ?", int(who))
    return one(con, "SELECT * FROM users WHERE lower(tg_username) = lower(?)", who.lstrip("@")) if who.lstrip("@") else None


def _admin_org(con, o: sqlite3.Row) -> dict:
    """A club as the admin sees it: the leaders (Telegram names only, as the CLI prints them) and the member count."""
    team = rows(con, """SELECT m.role, u.id, u.tg_username, u.tg_first_name, u.tg_last_name, s.user_id IS NOT NULL AS student
        FROM org_members m JOIN users u ON u.id = m.user_id LEFT JOIN students s ON s.user_id = u.id
        WHERE m.org_id = ? AND m.role != 'member'""", o["id"])
    return {**org_ref(con, o), "hidden": o["status"] == "hidden", "members": one(con, "SELECT COUNT(*) FROM org_members WHERE org_id = ?", o["id"])[0],
            "team": sorted(({"id": m["id"], "role": m["role"], "username": m["tg_username"], "name": f"{m['tg_first_name']} {m['tg_last_name']}".strip(),
                             "student": bool(m["student"])} for m in team), key=lambda m: (-RANK[m["role"]], m["name"])),
            "shortLinks": [r[0] for r in rows(con, "SELECT slug FROM short_links WHERE org_id = ? ORDER BY slug", o["id"])]}


def admin_orgs(con, v: Viewer) -> list[dict]:
    _admin(v)
    return [_admin_org(con, o) for o in rows(con, "SELECT * FROM orgs WHERE status != 'archived' ORDER BY id DESC")]


def admin_hide_org(con, v: Viewer, oid: int, hidden: bool) -> dict:
    """Hide a club, or bring it back: never a delete, so a lost phone can't wipe the clubs (owner, Oct 16). Hidden, it
    leaves the lists, search and its members' profiles, and its events and posts go with it; nothing is removed."""
    _admin(v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND status != 'archived'", oid)
    if not o:
        raise ApiError("not_found")
    with tx(con):
        con.execute("UPDATE orgs SET status = ? WHERE id = ?", ("hidden" if hidden else "active", oid))
        log_action(con, v.id, "org_hide", f"org:{oid}", json.dumps({"hidden": hidden}))
    return _admin_org(con, one(con, "SELECT * FROM orgs WHERE id = ?", oid))


def admin_org_events(con, v: Viewer, oid: int) -> list[dict]:
    """A club's events for Admin's delete, each with what deleting it takes along (the confirm names it)."""
    _admin(v)
    return [{"id": e["id"], "title": e["title"], "status": e["status"], "startsAt": e["starts_at"], "people": e["people"],
             "came": e["came"], "paid": e["paid"], "photos": e["photos"]} for e in rows(con, """SELECT e.id, e.title, e.status, e.starts_at,
        (SELECT COUNT(*) FROM registrations WHERE event_id = e.id AND status != 'cancelled') AS people,
        (SELECT COUNT(*) FROM registrations WHERE event_id = e.id AND checked_in_at IS NOT NULL) AS came,
        (SELECT COUNT(*) FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = e.id) AS paid,
        (SELECT COUNT(*) FROM event_photos WHERE event_id = e.id) AS photos
        FROM events e WHERE e.org_id = ? ORDER BY COALESCE(e.starts_at, 0) DESC, e.id DESC""", oid)]


def admin_create_org(con, v: Viewer, body: dict) -> dict:
    _admin(v)
    name, short, emoji = str(body.get("name") or "").strip(), str(body.get("short") or "").strip().upper(), str(body.get("emoji") or "")
    # a school is never made by hand: KBTU's come from its site (seed_schools, owner Oct 14)
    if not (2 <= len(name) <= 60 and 1 <= len(short) <= 2 and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and body.get("kind", "club") == "club"):
        raise ApiError("bad_input")
    return _admin_org(con, _org(con, create_org(con, v.id, name, short, emoji, bool(body.get("official")))))


def admin_set_role(con, v: Viewer, oid: int, body: dict) -> dict:
    _admin(v)
    o = _org(con, oid)
    if not o:
        raise ApiError("not_found")
    u = find_user(con, str(body.get("who") or ""))
    if not u:
        raise ApiError("not_found", "who")
    set_role(con, v.id, u["id"], oid, str(body.get("role") or ""), "app")
    return _admin_org(con, o)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .orgnames import _official, create_org  # noqa: E402
from .shapes import _org, org_ref, person_ref, shown_name  # noqa: E402
from .teams import team  # noqa: E402
