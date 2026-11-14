"""An event's temporary door helpers (owner, Nov 4; .claude/reports/collab-review.md H1-H6): a President or Vice of a
club running the event (the host, or its accepted co-host) lets a KBTU student help at this one event's door, a friend
from another club say. "scan": the scanner only, tickets and badges of people already going, no list. "door": the
door as a Member works it (the list of short names, by name, typed guests). At most 3 an event. The right lives while
its club runs the event and the event isn't over (checked at use, no cleanup job); it never makes the helper someone
who runs the event (runs(): no self check-in, no full names). Granting and taking back go to the audit log."""
from __future__ import annotations

import json
import sqlite3

from ..db import tx

from .core import DOOR_LATE, PERSON_COLS, ApiError, Viewer, at_least, log_action, one, person_ref, role_in, rows

CREW_MAX = 3
KINDS = ("scan", "door")
# the clubs running an event now: the host (active) and its accepted, active co-host
_RUNNING = """SELECT e.org_id FROM events e JOIN orgs o ON o.id = e.org_id AND o.status = 'active' WHERE e.id = :e
    UNION SELECT x.org_id FROM event_cohosts x JOIN orgs o ON o.id = x.org_id AND o.status = 'active'
    WHERE x.event_id = :e AND x.status = 'accepted'"""


def _open(e: sqlite3.Row) -> bool:
    """Ahead or under way: helpers can be given, and work, until the door closes (the scanner's own window)."""
    return e["status"] != "cancelled" and core.now() <= (e["ends_at"] or e["starts_at"] + DOOR_LATE)


def kind(con, v: Viewer, e: sqlite3.Row) -> str | None:
    """My helper's right at this event, if it still holds: its club still runs it, neither club banned me since."""
    if not v.student or not _open(e) or e["visibility"] != "public" or e["meeting"] or e["guest_host"]:
        return None  # made team-only or a partner's since: the team's own door (adversarial review 1)
    r = con.execute(f"""SELECT kind FROM event_crew WHERE event_id = :e AND user_id = :u AND org_id IN ({_RUNNING})
        AND NOT EXISTS (SELECT 1 FROM org_bans WHERE user_id = :u AND org_id IN ({_RUNNING}))""", {"e": e["id"], "u": v.id}).fetchone()
    if r:
        return r["kind"]
    s = one(con, "SELECT * FROM qr_sessions WHERE event_id = ?", e["id"])
    return "scan" if s and qr_helping(con, v, s) else None  # let in by the organizer's QR: the scanner alone, while the session runs


def barred(con, uid: int, s: sqlite3.Row) -> bool:
    """A check-in session (checkin.py) closed to this person: a club running it banned them, or no club runs its event now."""
    clubs = _running(con, s["event_id"]) if s["event_id"] else [s["org_id"]]
    return not clubs or bool(one(con, f"SELECT 1 FROM org_bans WHERE user_id = ? AND org_id IN ({','.join('?' * len(clubs))})", uid, *clubs))


def qr_helping(con, v: Viewer, s: sqlite3.Row) -> bool:
    """My QR helper's right at this session, checked at use: it ends with the session, on removal, with a ban, with the student."""
    return v.student and s["started_at"] is not None and s["ended_at"] is None and not barred(con, v.id, s) \
        and bool(one(con, "SELECT 1 FROM qr_helpers WHERE session_id = ? AND user_id = ?", s["id"], v.id))


# qr_helping's person and club checks as SQL over a qr_sessions row `s` (checkin.running, a query for all of them); binds the user twice
_CLUBS = _RUNNING.replace(":e", "s.event_id")
QR_HELPING = f"""(s.id IN (SELECT session_id FROM qr_helpers WHERE user_id = ?) AND (s.event_id IS NULL OR EXISTS ({_CLUBS}))
    AND NOT EXISTS (SELECT 1 FROM org_bans b WHERE b.user_id = ? AND (s.event_id IS NULL AND b.org_id = s.org_id OR b.org_id IN ({_CLUBS}))))"""


def _running(con, eid: int) -> list[int]:
    """The clubs running it, the host first."""
    host = one(con, "SELECT org_id FROM events WHERE id = ?", eid)
    return sorted((r[0] for r in con.execute(_RUNNING, {"e": eid})), key=lambda o: o != (host and host[0]))


def _lead(con, v: Viewer, eid: int) -> int | None:
    """The club running the event that I am President or Vice of (the host first)."""
    return next((o for o in _running(con, eid) if at_least(role_in(con, v, o), "vice")), None)


def view(con, v: Viewer, e: sqlite3.Row) -> list[dict] | None:
    """The helpers, for the running clubs' Presidents and Vices (None for everyone else)."""
    if not _lead(con, v, e["id"]):
        return None
    named = [{"person": person_ref(p), "kind": p["kind"], "org": p["org_id"]} for p in rows(con, f"""SELECT {PERSON_COLS}, c.kind, c.org_id
        FROM event_crew c JOIN users u ON u.id = c.user_id LEFT JOIN students s ON s.user_id = u.id WHERE c.event_id = ? ORDER BY c.created_at""", e["id"])]
    # and whom the helper's QR let in (checkin.py qr_helpers): the scanner, until Finish; one list of helpers (owner, Nov 14)
    seen = {x["person"]["id"] for x in named}
    return named + [{"person": person_ref(p), "kind": "qr", "org": e["org_id"]} for p in rows(con, f"""SELECT {PERSON_COLS} FROM qr_helpers h
        JOIN qr_sessions q ON q.id = h.session_id AND q.event_id = ? AND q.ended_at IS NULL JOIN users u ON u.id = h.user_id
        LEFT JOIN students s ON s.user_id = u.id ORDER BY h.created_at""", e["id"]) if p["id"] not in seen]


def put(con, v: Viewer, eid: int, uid: object, what: object) -> list[dict]:
    """Give (or change) a helper's right: a KBTU student, not me, banned by neither club; a public event of ours ahead."""
    if not isinstance(uid, int) or isinstance(uid, bool) or what not in KINDS:
        raise ApiError("bad_input")
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        oid = e and _lead(con, v, eid)
        if not oid:
            raise ApiError("forbidden")
        if not _open(e):
            raise ApiError("closed")
        if e["visibility"] != "public" or e["guest_host"] or uid == v.id:  # a team's own event: its people work the door
            raise ApiError("bad_input")
        if not one(con, "SELECT 1 FROM students WHERE user_id = ?", uid):
            raise ApiError("bad_input", "student")
        running = _running(con, eid)
        if one(con, f"SELECT 1 FROM org_bans WHERE user_id = ? AND org_id IN ({','.join('?' * len(running))})", uid, *running):
            raise ApiError("forbidden", "banned")
        was = one(con, "SELECT * FROM event_crew WHERE event_id = ? AND user_id = ?", eid, uid)
        if was and was["org_id"] != oid and was["org_id"] in running:
            raise ApiError("conflict")  # the other club's helper: theirs to change
        if not was and one(con, "SELECT COUNT(*) FROM event_crew WHERE event_id = ?", eid)[0] >= CREW_MAX:
            raise ApiError("rate_limited")
        con.execute("""INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (event_id, user_id) DO UPDATE SET org_id = excluded.org_id, kind = excluded.kind, added_by = excluded.added_by""",
                    (eid, uid, oid, what, v.id, core.now()))
        log_action(con, v.id, "crew_put", f"user:{uid}", json.dumps({"event": eid, "org": oid, "kind": what}))
        if not was:
            notify(con, uid, "crew_added", f"cw:{eid}")  # a template; quiet once the right is gone (bot._render)
        return view(con, v, e) or []


def drop(con, v: Viewer, eid: int, uid: int) -> list[dict]:
    """Take a helper's right back: the President or Vice of the club that gave it, or of the host."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        r = e and one(con, "SELECT * FROM event_crew WHERE event_id = ? AND user_id = ?", eid, uid)
        if not r and e and _lead(con, v, eid):  # let in by the helper's QR: out of its session's helpers
            if not con.execute("DELETE FROM qr_helpers WHERE user_id = ? AND session_id IN (SELECT id FROM qr_sessions WHERE event_id = ?)", (uid, eid)).rowcount:
                raise ApiError("not_found")
            log_action(con, v.id, "crew_drop", f"user:{uid}", json.dumps({"event": eid, "kind": "qr"}))
            return view(con, v, e) or []
        if not r:
            raise ApiError("not_found")
        if not (at_least(role_in(con, v, r["org_id"]), "vice") or at_least(role_in(con, v, e["org_id"]), "vice")):
            raise ApiError("forbidden")
        con.execute("DELETE FROM event_crew WHERE event_id = ? AND user_id = ?", (eid, uid))
        log_action(con, v.id, "crew_drop", f"user:{uid}", json.dumps({"event": eid, "org": r["org_id"], "kind": r["kind"]}))
        return view(con, v, e) or []


from . import core  # noqa: E402
from .seats import notify  # noqa: E402
