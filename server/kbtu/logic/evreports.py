"""A club's report after its own event (owner, Nov 11; REPORTS=1): which of its departments ran it, who of the team was
there (present / late / absent / excused), how many guests came by the club's own count beside what the app knows
(signed up, checked in), a short note; who filled it first and who edited it last. One report an event, the host
club's alone (a co-host writes none). It lives in Studio and nowhere else: only the club's people with the "reports"
right read and write it (its President and Vices by level, a role the club gives it, e.g. HR's); never the app's
staff (core.STAFF_RIGHTS). Only once the event has started. The marks are about the team alone: a name is someone in
the club's team, never typed; a mark stays after its person leaves the club and goes with their account.
The feature's own consent (the policy's section 3, CONSENT): one per person, for every club's reports (as appeals':
one version, one row). Without it a person can neither open a report nor be marked in one; withdrawing it takes their
marks from every report and their name off the reports they filled or edited (the note stays)."""
from __future__ import annotations

import sqlite3

from ..db import tx

from . import core
from .core import PERSON, PERSON_COLS, ApiError, Viewer, can, one, person_ref, rows

STATUSES = ("present", "late", "absent", "excused")
NOTE_MAX = 1000
GUESTS_MAX = 100000  # the table's CHECK
CONSENT = "evr1"  # the privacy policy's event-reports clause, agreed to before the first report or mark


def consented(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM report_consents WHERE user_id = ? AND version = ?", uid, CONSENT) is not None


def summary(con, v: Viewer) -> dict:
    """/api/me's part: agreed to the clause yet."""
    return {"consent": consented(con, v.id)}


def agree(con, v: Viewer, body: dict) -> dict:
    """Mine given: the app sends the version it showed."""
    if not isinstance(body, dict) or body.get("consent") != CONSENT:
        raise ApiError("bad_input")
    with tx(con):
        con.execute("INSERT OR REPLACE INTO report_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))
    return summary(con, v)


def withdraw(con, v: Viewer) -> dict:
    """Mine taken back, without deleting the account: my marks go from every report, my name off what I filled or
    edited; the reports and their notes stay (a name inside a note is the operator's to handle, the policy says)."""
    with tx(con):
        con.execute("DELETE FROM report_consents WHERE user_id = ?", (v.id,))
        con.execute("DELETE FROM report_marks WHERE user_id = ?", (v.id,))
        con.execute("UPDATE event_reports SET filled_by = NULL WHERE filled_by = ?", (v.id,))
        con.execute("UPDATE event_reports SET edited_by = NULL WHERE edited_by = ?", (v.id,))
    return summary(con, v)


def _event(con, v: Viewer, eid: int) -> sqlite3.Row:
    """The event, if I may report on it: its host club gave me the right, it was published and it has started."""
    e = one(con, "SELECT id, org_id, status, starts_at FROM events WHERE id = ?", eid)
    if not e:
        raise ApiError("not_found")
    if not can(con, v, e["org_id"], "reports"):
        raise ApiError("forbidden")
    if not consented(con, v.id):
        raise ApiError("forbidden", "consent")  # the app asks it then
    if e["status"] != "published" or e["starts_at"] is None or e["starts_at"] > core.now():
        raise ApiError("conflict", "not_started")
    return e


def _touch(con, v: Viewer, eid: int) -> None:
    """The report exists from its first write; whoever writes is its last editor."""
    t = core.now()
    con.execute("""INSERT INTO event_reports (event_id, filled_by, filled_at, edited_by, edited_at) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_id) DO UPDATE SET edited_by = excluded.edited_by, edited_at = excluded.edited_at""", (eid, v.id, t, v.id, t))


def get(con, v: Viewer, eid: int) -> dict:
    """The report (empty until someone writes), the club's departments and its team with each one's departments and
    mark, plus those marked who have left the team since. Each fact read once for the whole list."""
    e = _event(con, v, eid)
    oid = e["org_id"]
    r = one(con, "SELECT * FROM event_reports WHERE event_id = ?", eid)
    depts = rows(con, "SELECT id, name, color FROM org_tags WHERE org_id = ? AND department = 1 ORDER BY id", oid)
    people = con.execute(f"""SELECT {PERSON_COLS}, m.user_id IS NOT NULL AS team, k.status, c.user_id IS NOT NULL AS consent,
            (SELECT group_concat(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id
                WHERE g.org_id = :o AND g.department = 1 AND mt.user_id = u.id) AS depts
        FROM users u LEFT JOIN students s ON s.user_id = u.id
        LEFT JOIN org_members m ON m.org_id = :o AND m.user_id = u.id
        LEFT JOIN report_marks k ON k.event_id = :e AND k.user_id = u.id
        LEFT JOIN report_consents c ON c.user_id = u.id AND c.version = :v
        WHERE u.id IN (SELECT user_id FROM org_members WHERE org_id = :o UNION SELECT user_id FROM report_marks WHERE event_id = :e)""",
        {"o": oid, "e": eid, "v": CONSENT}).fetchall()  # from the team and the marked, never a scan of every user
    by = {p["id"]: person_ref(p) for p in rows(con, PERSON + " WHERE u.id IN (?, ?)", r["filled_by"], r["edited_by"])} if r else {}
    counts = one(con, """SELECT COALESCE(SUM(status = 'going'), 0) AS signed, COALESCE(SUM(checked_in_at IS NOT NULL), 0) AS came
        FROM registrations WHERE event_id = ?""", eid)
    ids = {d["id"] for d in depts}
    return {
        "depts": [{"id": d["id"], "name": d["name"], "color": d["color"]} for d in depts],
        "dept": r["dept_id"] if r and r["dept_id"] in ids else None,
        "guests": r["guests"] if r else None, "note": r["note"] if r else "",
        "signed": counts["signed"], "came": counts["came"],
        "filledBy": by.get(r["filled_by"]) if r else None, "filledAt": r["filled_at"] if r else None,
        "editedBy": by.get(r["edited_by"]) if r else None, "editedAt": r["edited_at"] if r else None,
        "people": [{"person": person_ref(p), "fullName": f"{p['last_name'] or ''} {p['first_name'] or ''}".strip() or core.short_name(p),
                    "depts": sorted(int(x) for x in (p["depts"] or "").split(",") if x), "team": bool(p["team"]), "status": p["status"],
                    "consent": bool(p["consent"])}
                   for p in sorted(people, key=lambda p: (p["last_name"] or "", p["first_name"] or ""))],
    }


def save(con, v: Viewer, eid: int, body: dict) -> dict:
    """The report's fields, any of them: `dept` (one of the club's departments, or null), `guests` (the club's own
    count, or null), `note` (plain text, NOTE_MAX). What isn't in the body stays."""
    e = _event(con, v, eid)
    if not isinstance(body, dict):
        raise ApiError("bad_input")
    sets: dict = {}
    if "dept" in body:
        d = body["dept"]
        if d is not None and (type(d) is not int or not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", d, e["org_id"])):
            raise ApiError("bad_input")
        sets["dept_id"] = d
    if "guests" in body:
        g = body["guests"]
        if g is not None and (type(g) is not int or not 0 <= g <= GUESTS_MAX):
            raise ApiError("bad_input")
        sets["guests"] = g
    if "note" in body:
        n = body["note"]
        if not isinstance(n, str) or len(n := n.strip()) > NOTE_MAX:
            raise ApiError("bad_input")
        sets["note"] = n
    with tx(con):
        _touch(con, v, eid)
        if sets:
            con.execute(f"UPDATE event_reports SET {', '.join(f'{k} = ?' for k in sets)} WHERE event_id = ?", (*sets.values(), eid))
    return get(con, v, eid)


def mark(con, v: Viewer, eid: int, uid: int, status: object) -> dict:
    """One person's mark: someone in the club's team now who has given the consent (a name is never typed); null takes
    the mark off (anyone's, one who left the team too)."""
    e = _event(con, v, eid)
    if status is not None and status not in STATUSES:
        raise ApiError("bad_input")
    with tx(con):
        if status is None:
            if one(con, "SELECT 1 FROM report_marks WHERE event_id = ? AND user_id = ?", eid, uid):
                _touch(con, v, eid)
                con.execute("DELETE FROM report_marks WHERE event_id = ? AND user_id = ?", (eid, uid))
        else:
            if not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", e["org_id"], uid):
                raise ApiError("not_found")
            if not consented(con, uid):
                raise ApiError("conflict", "no_consent")  # marked only after their own yes (the policy's section 3)
            _touch(con, v, eid)
            con.execute("""INSERT INTO report_marks (event_id, user_id, status) VALUES (?, ?, ?)
                ON CONFLICT (event_id, user_id) DO UPDATE SET status = excluded.status""", (eid, uid, status))
    return get(con, v, eid)
