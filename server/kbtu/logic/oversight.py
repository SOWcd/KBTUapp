"""The app's own team and DMP: admins, moderators, bans, the audit log, the admin's clubs, DMP's registry."""
from __future__ import annotations

import calendar
import json
import re
import sqlite3
import time

from ..db import tx

from .core import (ApiError, PERSON, PERSON_COLS, RANK, Viewer, _org, log_action, one, org_ref, overseer, person_ref,
    rows, short_name, shown_name)


# ---------------------------------------------------------------- the clubs registry for DMP (§4.13)

QUIET_FOR = 60 * 86400  # "hasn't come in a while": no check-in at the club's events for this long
DMP_COLS = PERSON_COLS + ", u.tg_username, s.student_id, s.course, s.school, s.email, s.phone"


def _overseer_only(con, v: Viewer) -> None:
    if not overseer(con, v):
        raise ApiError("forbidden")


def _month(back: int = 0) -> tuple[int, int]:
    """A month in Almaty (UTC+5), `back` months before this one: its first second and the next month's."""
    t = time.gmtime(core.now() + 5 * 3600)
    y, m = divmod(t.tm_year * 12 + t.tm_mon - 1 - back, 12)
    start = lambda y, m: calendar.timegm((y, m + 1, 1, 0, 0, 0)) - 5 * 3600  # noqa: E731  (m is 0-based here)
    return start(y, m), start(y + (m == 11), (m + 1) % 12)


def _dmp_person(p: sqlite3.Row, role: str | None = None) -> dict:
    """What DMP sees of a club member (§3): full name, student ID, course, school; contacts only of Presidents and Vices."""
    lead = role in ("president", "vice")
    return {"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "studentId": p["student_id"],
            "course": p["course"], "school": p["school"], "username": p["tg_username"] if lead else None,
            "email": p["email"] if lead else None, "phone": p["phone"] if lead else None}


def registry_memos(con, v: Viewer) -> list[dict]:
    """The memos clubs marked sent in the last 7 days (DMP sees them in the app): the club, its events, who
    said "sent" and when, newest first. One "Yes, sent" stamps its events at once, so one memo is (club, time). It's the
    club's word: the email itself is in DMP's mailbox, not here."""
    _overseer_only(con, v)
    out: dict[tuple[int, int], dict] = {}
    for e in rows(con, """SELECT id, org_id, title, starts_at, memo_sent_at, memo_sent_by FROM events
            WHERE memo_sent_at > ? ORDER BY memo_sent_at DESC, starts_at""", core.now() - 7 * 86400):
        m = out.get((e["org_id"], e["memo_sent_at"]))
        if not m:
            p = one(con, PERSON + " WHERE u.id = ?", e["memo_sent_by"]) if e["memo_sent_by"] else None
            m = out[(e["org_id"], e["memo_sent_at"])] = {"org": org_ref(con, _org(con, e["org_id"])), "sentAt": e["memo_sent_at"],
                                                          "by": short_name(p) if p else None, "events": []}
        m["events"].append({"id": e["id"], "title": e["title"], "startsAt": e["starts_at"]})
    return list(out.values())


def registry(con, v: Viewer, back: int = 0) -> list[dict]:
    """Every club with its live numbers (members; a month's events, registrations, who came; this month or up to a year
    back) and its President — instead of monthly reports, and instead of asking in chats who leads what."""
    _overseer_only(con, v)
    if not 0 <= back <= 12:
        raise ApiError("bad_input")
    m0, m1 = _month(back)
    out = []
    for o in rows(con, "SELECT * FROM orgs WHERE kind IN ('club', 'school', 'council') AND status != 'archived' ORDER BY official DESC, name"):
        pres = one(con, f"SELECT {DMP_COLS} FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id "
                        "WHERE m.org_id = ? AND m.role = 'president'", o["id"])
        st = one(con, """SELECT COUNT(DISTINCT e.id) AS events, COUNT(r.id) AS regs, COUNT(r.checked_in_at) AS came FROM events e
            LEFT JOIN registrations r ON r.event_id = e.id AND r.status = 'going'
            WHERE e.org_id = ? AND e.status = 'published' AND e.guest_host IS NULL AND e.starts_at >= ? AND e.starts_at < ?""", o["id"], m0, m1)  # a partner's isn't the club's work
        out.append({"org": org_ref(con, o), "members": one(con, "SELECT COUNT(*) FROM org_members WHERE org_id = ?", o["id"])[0],
                    "president": _dmp_person(pres, "president") if pres else None,
                    "month": {"events": st["events"], "registrations": st["regs"], "came": st["came"]}})
    return out


def registry_roster(con, v: Viewer, oid: int) -> list[dict]:
    """A club's roster for DMP, leaders first; who hasn't come to the club's events in 60 days is marked (§4.13). A look at
    personal data: audit-logged (§9)."""
    _overseer_only(con, v)
    if not _org(con, oid):
        raise ApiError("not_found")
    log_action(con, v.id, "registry_roster", f"org:{oid}")
    out = []
    for p in rows(con, f"""SELECT {DMP_COLS}, m.role, m.joined_at, (SELECT MAX(r.checked_in_at) FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE e.org_id = m.org_id AND r.user_id = u.id) AS seen FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
            WHERE m.org_id = ?""", oid):
        out.append({**_dmp_person(p, p["role"]), "role": p["role"], "joinedAt": p["joined_at"], "lastCame": p["seen"],
                    "quiet": (p["seen"] or p["joined_at"]) < core.now() - QUIET_FOR})
    return sorted(out, key=lambda x: (-RANK[x["role"]], x["fullName"]))


def registry_search(con, v: Viewer, q: str) -> list[dict]:
    """A club member by name or student ID → their clubs and roles (only people in some club: DMP sees club members)."""
    _overseer_only(con, v)
    q = str(q or "").strip()
    if len(q) < 2 or len(q) > 60:
        raise ApiError("bad_input")
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    found = rows(con, f"""SELECT DISTINCT {DMP_COLS} FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        WHERE s.student_id LIKE ? OR (s.last_name || ' ' || s.first_name) LIKE ? OR (s.first_name || ' ' || s.last_name) LIKE ? LIMIT 30""", like, like, like)
    log_action(con, v.id, "registry_search", "registry", json.dumps({"q": q, "found": len(found)}))  # a look at personal data (§9)
    out = []
    for p in found:
        clubs = rows(con, "SELECT o.*, m.role FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ? ORDER BY o.name", p["id"])
        top = max((c["role"] for c in clubs), key=lambda r: RANK[r], default=None)
        out.append({**_dmp_person(p, top), "clubs": [{"org": org_ref(con, c), "role": c["role"]} for c in clubs]})
    return out


def set_official(con, v: Viewer, oid: int, on: object) -> dict:
    """DMP marks a club official ✓ or takes it back (DMP Head+ and the admin, §2) — the growth path's last step (§4.6):
    a student initiative becomes an official club. Its President hears it from the bot (once); the audit log keeps who."""
    _overseer_only(con, v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND kind = 'club' AND status != 'archived'", oid)
    if not o:
        raise ApiError("not_found")
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    if bool(o["official"]) != on:
        with tx(con):
            con.execute("UPDATE orgs SET official = ? WHERE id = ?", (int(on), oid))
            log_action(con, v.id, "official", f"org:{oid}", json.dumps({"on": on}))
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", oid) if on else []:
                notify(con, uid, "club_official", f"off:{oid}")
    return org_ref(con, _org(con, oid))


def registry_export(con, v: Viewer) -> list[sqlite3.Row]:
    """Every roster at once for the CSV the bot sends (contacts of Presidents and Vices only, as on screen). Personal
    data leaving the app: every export goes to the audit log (§2)."""
    _overseer_only(con, v)
    out = rows(con, f"""SELECT o.name AS club, m.role, m.joined_at, {DMP_COLS} FROM org_members m JOIN orgs o ON o.id = m.org_id
        JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        WHERE o.kind IN ('club', 'school', 'council') AND o.status != 'archived' ORDER BY o.name, m.role, s.last_name""")
    log_action(con, v.id, "registry_export", "registry", json.dumps({"rows": len(out)}))
    return out




# ---------------------------------------------------------------- admin: clubs and their teams (pilot, SPEC §2)

def _admin(v: Viewer) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")


def _mod(v: Viewer) -> None:
    """Moderators filter content: the report queue, taking things down and back; the admin too."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")


# ---------------------------------------------------------------- the app's team
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
    """The platform ban: no mutes, no strikes; the reason is required, he sees it, and the role goes.
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
    """What a banned person sees: why, and whom to write."""
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
    """Hide a club, or bring it back: never a delete, so a lost phone can't wipe the clubs. Hidden, it
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
    # a school is never made by hand: KBTU's come from its site (seed_schools)
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
from .clubs import _official, create_org  # noqa: E402
from .seats import notify  # noqa: E402
from .teams import team  # noqa: E402
