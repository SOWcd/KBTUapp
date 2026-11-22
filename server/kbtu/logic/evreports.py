"""A club's report after its own or co-hosted event (REPORTS=1): which of its departments ran it, who of the team was
there (present / late / absent / excused), how many guests came by the club's own count beside what the app knows
(signed up, checked in), a short note; who filled it first and who edited it last. One report per club on an event:
the host's and its accepted co-host's (cohosts.py), each about its own team. Only the club's people with the
"reports" right read and write it in Studio, once the event has started. Staff authority grants no access.
Each mark can carry a comment and its authorship and edit dates. People see their own marks and comments in their
profiles, including after leaving the club.
The feature's own consent (the policy's section 3, CONSENT): one per person, for every club's reports (as appeals':
one version, one row). Without it a person can neither open a report nor be marked in one; withdrawing it takes their
marks and their comments from every report and clears their author and editor links (the other text stays)."""
from __future__ import annotations

import json

from ..db import tx

from . import account, cohosts, core
from .core import PERSON, PERSON_COLS, ApiError, Viewer, can, log_action, one, person_ref, rows

STATUSES = ("present", "late", "absent", "excused")
NOTE_MAX = 1000
COMMENT_MAX = 300
LOG_LIMIT = 10
GUESTS_MAX = 100000  # the table's CHECK
CONSENT = "evr2"  # the privacy policy's event-reports clause: marks, comments, personal log and club export


def consented(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM report_consents WHERE user_id = ? AND version = ?", uid, CONSENT) is not None


def summary(con, v: Viewer) -> dict:
    """/api/me's part: agreed to the clause yet."""
    row = one(con, "SELECT version FROM report_consents WHERE user_id = ?", v.id)
    if row and row["version"] != CONSENT:
        return {"consent": False, "legacy": True}
    return {"consent": bool(row)}


def own_log(con, v: Viewer) -> list[dict]:
    """Recent entries for the signed-in person, independent of their current club roles."""
    return [dict(r) for r in rows(con, """SELECT m.event_id AS event, m.org_id AS org, e.title, o.name AS club,
            e.starts_at AS date, m.status, m.comment
        FROM club_report_marks m JOIN events e ON e.id = m.event_id JOIN orgs o ON o.id = m.org_id
        JOIN report_consents c ON c.user_id = m.user_id AND c.version = ?
        WHERE m.user_id = ? ORDER BY e.starts_at DESC, m.event_id DESC, m.org_id LIMIT ?""", CONSENT, v.id, LOG_LIMIT)]


def agree(con, v: Viewer, body: dict) -> dict:
    """Mine given: the app sends the version it showed."""
    if not isinstance(body, dict) or body.get("consent") != CONSENT:
        raise ApiError("bad_input")
    with tx(con):
        con.execute("INSERT OR REPLACE INTO report_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))
        return {"consent": True, "reportLog": own_log(con, v)}


def withdraw(con, v: Viewer) -> dict:
    """Erase my marks and their comments, and unlink my authorship of remaining reports and comments."""
    with tx(con):
        if erase(con, v.id):
            account._deletion_log(con, v.id, reports=True)
    return {"consent": False}


def erase(con, uid: int) -> bool:
    """Erase report data within the caller's transaction, including when replaying a withdrawal."""
    before = con.total_changes
    con.execute("DELETE FROM report_consents WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM club_report_marks WHERE user_id = ?", (uid,))
    con.execute("UPDATE club_reports SET filled_by = NULL WHERE filled_by = ?", (uid,))
    con.execute("UPDATE club_reports SET edited_by = NULL WHERE edited_by = ?", (uid,))
    con.execute("UPDATE club_report_marks SET comment_by = NULL WHERE comment_by = ?", (uid,))
    con.execute("UPDATE club_report_marks SET comment_edited_by = NULL WHERE comment_edited_by = ?", (uid,))
    return con.total_changes != before


def _need_access(con, v: Viewer, oid: int) -> None:
    if v.staff_org or not can(con, v, oid, "reports"):
        raise ApiError("forbidden")
    if not consented(con, v.id):
        raise ApiError("forbidden", "report_consent")


def _event_org(con, v: Viewer, eid: int, oid: int | None) -> int:
    """The club whose report it is (`oid`: the host's by default, or its accepted co-host's), if I may
    report on it: that club gave me the right, the event was published and it has started. A co-host that is pending,
    declined, removed or no longer shown gets nothing (its old report stays, unreachable, until it co-hosts again)."""
    e = one(con, "SELECT org_id, status, starts_at FROM events WHERE id = ?", eid)
    if not e:
        raise ApiError("not_found")
    oid = e["org_id"] if oid is None else oid
    if oid != e["org_id"] and not ((x := one(con, cohosts.ACCEPTED, eid)) and x["org_id"] == oid):
        raise ApiError("forbidden")
    _need_access(con, v, oid)
    if e["status"] != "published" or e["starts_at"] is None or e["starts_at"] > core.now():
        raise ApiError("conflict", "not_started")
    return oid


def _touch(con, v: Viewer, eid: int, oid: int) -> None:
    """The report exists from its first write; whoever writes is its last editor."""
    t = core.now()
    con.execute("""INSERT INTO club_reports (event_id, org_id, filled_by, filled_at, edited_by, edited_at) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_id, org_id) DO UPDATE SET edited_by = excluded.edited_by, edited_at = excluded.edited_at""", (eid, oid, v.id, t, v.id, t))


def get(con, v: Viewer, eid: int, oid: int | None = None) -> dict:
    with tx(con, write=False):
        return _report(con, eid, _event_org(con, v, eid, oid))


def _full_name(p) -> str:
    return f"{p['last_name'] or ''} {p['first_name'] or ''}".strip() or core.short_name(p)


def export(con, v: Viewer, oid: int, tg_id: int) -> tuple[str, str, list[tuple]]:
    """The club's report marks and comments for the CSV, with the same access as in Studio."""
    with tx(con):
        # Keep the destination tied to the signed requester if their account moves during the request.
        requester = one(con, "SELECT lang FROM users WHERE id = ? AND tg_id = ?", v.id, tg_id)
        if not requester:
            raise ApiError("forbidden")
        _need_access(con, v, oid)
        org = one(con, "SELECT name, status FROM orgs WHERE id = ?", oid)
        found = rows(con, """SELECT s.last_name, s.first_name, u.tg_first_name, e.title, e.starts_at, m.status, m.comment
            FROM club_report_marks m JOIN events e ON e.id = m.event_id JOIN users u ON u.id = m.user_id
            JOIN report_consents c ON c.user_id = m.user_id AND c.version = ?
            LEFT JOIN students s ON s.user_id = m.user_id
            LEFT JOIN event_cohosts x ON x.event_id = m.event_id AND x.org_id = m.org_id AND x.status = 'accepted'
            WHERE m.org_id = ?
                AND (e.org_id = m.org_id OR (x.event_id IS NOT NULL AND ? = 'active'))
            ORDER BY e.starts_at DESC, m.event_id DESC, s.last_name, s.first_name, m.user_id""",
            CONSENT, oid, org["status"])
        log_action(con, v.id, "team_log_export", f"org:{oid}", json.dumps({"rows": len(found)}))
    return requester["lang"], org["name"], [(_full_name(p), p["title"], p["starts_at"], p["status"], p["comment"]) for p in found]


def _report(con, eid: int, oid: int) -> dict:
    """The report (empty until someone writes), the club's departments and its team with each one's departments and
    mark, plus those marked who have left the team since. Each fact read once for the whole list."""
    r = one(con, "SELECT * FROM club_reports WHERE event_id = ? AND org_id = ?", eid, oid)
    depts = rows(con, "SELECT id, name, color FROM org_tags WHERE org_id = ? AND department = 1 ORDER BY id", oid)
    people = con.execute(f"""SELECT {PERSON_COLS}, m.user_id IS NOT NULL AS team, k.status, k.comment, c.user_id IS NOT NULL AS consent,
            (SELECT group_concat(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id
                WHERE g.org_id = :o AND g.department = 1 AND mt.user_id = u.id) AS depts
        FROM users u LEFT JOIN students s ON s.user_id = u.id
        LEFT JOIN org_members m ON m.org_id = :o AND m.user_id = u.id
        LEFT JOIN report_consents c ON c.user_id = u.id AND c.version = :v
        LEFT JOIN club_report_marks k ON k.event_id = :e AND k.org_id = :o AND k.user_id = c.user_id
        WHERE u.id IN (SELECT user_id FROM org_members WHERE org_id = :o UNION
            SELECT m.user_id FROM club_report_marks m JOIN report_consents c ON c.user_id = m.user_id AND c.version = :v
            WHERE m.event_id = :e AND m.org_id = :o)""",
        {"o": oid, "e": eid, "v": CONSENT}).fetchall()  # from the team and the marked, never a scan of every user
    by = {p["id"]: person_ref(p) for p in rows(con, PERSON + """
        JOIN report_consents c ON c.user_id = u.id AND c.version = ? WHERE u.id IN (?, ?)""",
        CONSENT, r["filled_by"], r["edited_by"])} if r else {}
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
        "people": [{"person": person_ref(p), "fullName": _full_name(p),
                    "depts": sorted(int(x) for x in (p["depts"] or "").split(",") if x), "team": bool(p["team"]), "status": p["status"],
                    "comment": p["comment"] or "", "consent": bool(p["consent"])}
                   for p in sorted(people, key=lambda p: (p["last_name"] or "", p["first_name"] or ""))],
    }


def save(con, v: Viewer, eid: int, body: dict, oid: int | None = None) -> dict:
    """The report's fields, any of them: `dept` (one of the club's departments, or null), `guests` (the club's own
    count, or null), `note` (plain text, NOTE_MAX). What isn't in the body stays."""
    with tx(con):
        oid = _event_org(con, v, eid, oid)
        _save_fields(con, v, eid, oid, body)
        return _report(con, eid, oid)


def _save_fields(con, v: Viewer, eid: int, oid: int, body: dict) -> None:
    if not isinstance(body, dict):
        raise ApiError("bad_input")
    sets: dict = {}
    if "dept" in body:
        d = body["dept"]
        if d is not None and (type(d) is not int or not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", d, oid)):
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
    _touch(con, v, eid, oid)
    if sets:
        con.execute(f"UPDATE club_reports SET {', '.join(f'{k} = ?' for k in sets)} WHERE event_id = ? AND org_id = ?", (*sets.values(), eid, oid))


def mark(con, v: Viewer, eid: int, uid: int, body: dict, oid: int | None = None) -> dict:
    """Patch one person's status or comment. An explicit null status removes the entire mark."""
    with tx(con):
        oid = _event_org(con, v, eid, oid)
        _save_mark(con, v, eid, oid, uid, body)
        return _report(con, eid, oid)


def _save_mark(con, v: Viewer, eid: int, oid: int, uid: int, body: dict) -> None:
    status = body.get("status")
    comment = body.get("comment")
    if ("status" not in body and "comment" not in body) or (status is not None and status not in STATUSES):
        raise ApiError("bad_input")
    if "comment" in body:
        if (not isinstance(comment, str) or len(comment) > COMMENT_MAX or "\0" in comment
                or any(0xD800 <= ord(ch) <= 0xDFFF for ch in comment) or ("status" in body and status is None)):
            raise ApiError("bad_input")
        comment = comment.strip()

    key = (eid, oid, uid)
    old = one(con, "SELECT * FROM club_report_marks WHERE event_id = ? AND org_id = ? AND user_id = ?", *key)
    if "status" in body and status is None:
        if old:
            _touch(con, v, eid, oid)
            con.execute("DELETE FROM club_report_marks WHERE event_id = ? AND org_id = ? AND user_id = ?", key)
        return
    changed_comment = comment is not None and comment != (old["comment"] if old else "")
    if (status is not None or not old or (comment and changed_comment)) and not one(
            con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
        raise ApiError("not_found")
    if not consented(con, uid):
        raise ApiError("conflict", "no_consent")
    if status is None and not old:
        raise ApiError("not_found")

    _touch(con, v, eid, oid)
    if status is not None:
        con.execute("""INSERT INTO club_report_marks (event_id, org_id, user_id, status) VALUES (?, ?, ?, ?)
            ON CONFLICT (event_id, org_id, user_id) DO UPDATE SET status = excluded.status""", (*key, status))
    if changed_comment:
        author, at = (old["comment_by"], old["comment_at"]) if old and old["comment"] else (v.id, core.now())
        metadata = (author, at, v.id, core.now()) if comment else (None, None, None, None)
        con.execute("""UPDATE club_report_marks SET comment = ?, comment_by = ?, comment_at = ?,
            comment_edited_by = ?, comment_edited_at = ? WHERE event_id = ? AND org_id = ? AND user_id = ?""",
            (comment, *metadata, *key))
