"""The clubs registry for DMP (§4.13)."""
from __future__ import annotations

import calendar
import json
import sqlite3
import time

from ..db import tx

from .core import ApiError, PERSON, PERSON_COLS, RANK, Viewer, log_action, one, overseer, rows


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
    """The memos clubs marked sent in the last 7 days (owner, Oct 13: DMP sees them in the app): the club, its events, who
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
            WHERE e.org_id = ? AND e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ?""", o["id"], m0, m1)
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


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .seats import notify  # noqa: E402
from .shapes import _org, org_ref, person_ref, short_name  # noqa: E402
