"""What people tell the app's creator from inside the app: an anonymous line about what is wrong, and a signed
"I want to help" offer. Both land in one list in Admin; the bot tells the creator with a template.

The anonymous line keeps NO author anywhere: no user column, only the Almaty day it came (not the minute: the minute
next to users.seen_at would name the author), no per-person cap (one would have to remember the person), only the
day's total. Admin sees a day's lines once the day is over, shuffled, with no ids: the list's order and its refreshes
say nothing about who wrote when. The creator's push waits for the next morning, one per day.
The offer is signed on purpose (the creator has to reach them): the form's own consent (CONSENT) is kept on the row,
and only the creator (oversight._owner) sees offers, as the form says."""
from __future__ import annotations

from ..db import tx
from . import core
from .core import PERSON, ApiError, Viewer, need_student, one, person_ref, rows
from .seats import notify

CONSENT = "2026-11-24"  # the offer form's own consent line (web help.consent); a new wording: a new value
KINDS = ("code", "design", "ideas", "partner", "lang", "test")
ANON_MAX, NOTE_MAX = 1000, 500
BODY_MOST = 8192     # a request's bytes, capped before parsing (app.json_body): the longest text as \u escapes fits
A_DAY = 3            # offers per person a day
ANON_ALL = 200       # all anonymous lines a day: the table's own rows (there is no per-person cap, see above)
ANON_KEEP, OFFER_KEEP = 90, 180 * 86400  # days (a line is gone before it is 90 days old); seconds


def _day(t: int) -> int:
    return (t + 5 * 3600) // 86400


def _founders(con) -> list[int]:
    return [r[0] for r in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0")]


def send_anon(con, v: Viewer, body: object) -> None:
    need_student(v)
    text = body.get("body") if isinstance(body, dict) else None
    text = text.strip() if isinstance(text, str) else ""
    if not 2 <= len(text) <= ANON_MAX:
        raise ApiError("bad_input", "length")
    day = _day(core.now())
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM anon_feedback WHERE day = ?", day)[0] >= ANON_ALL:
            raise ApiError("rate_limited", "all")
        con.execute("INSERT INTO anon_feedback (body, day) VALUES (?, ?)", (text, day))
        for f in _founders(con):  # tomorrow 09:00 Almaty, once for the day: the push's minute says nothing about the writer
            notify(con, f, "anon_feedback", f"afb:{day}", after=(day + 1) * 86400 + 4 * 3600)


def offer(con, v: Viewer, body: object) -> None:
    need_student(v)
    if not isinstance(body, dict):
        raise ApiError("bad_input")
    kinds, note = body.get("kinds"), body.get("note")
    note = note.strip() if isinstance(note, str) else ""
    if (not isinstance(kinds, list) or not 1 <= len(kinds) <= len(KINDS) or any(k not in KINDS for k in kinds)
            or len(note) > NOTE_MAX or body.get("consent") != CONSENT):
        raise ApiError("bad_input")
    with tx(con):
        # still a student now: an account erased since this request began leaves no offer behind
        if not one(con, "SELECT 1 FROM students WHERE user_id = ? AND manual = 0", v.id):
            raise ApiError("need_student")
        if one(con, "SELECT COUNT(*) FROM helper_offers WHERE user_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "day")
        con.execute("INSERT INTO helper_offers (id, user_id, kinds, note, consent, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (core.next_id(con, "helper_offers"), v.id, ",".join(k for k in KINDS if k in kinds), note or None, CONSENT, core.now()))
        for f in _founders(con):  # one push a day, however many came
            notify(con, f, "helper_offer", f"ho:{_day(core.now())}")


def _seen(con) -> tuple[int, int]:
    """The read marks: the last anonymous day read, the last offer id read (never reused: core.next_id)."""
    r = one(con, "SELECT value FROM meta WHERE key = 'helpus_seen'")
    a, _, o = (r[0] if r else "0,0").partition(",")
    return int(a), int(o)


def unread(con, v: Viewer) -> int:
    a, o = _seen(con)
    t = _day(core.now())
    n = one(con, "SELECT COUNT(*) FROM anon_feedback WHERE day < ? AND day > ?", t, max(a, t - ANON_KEEP))[0]
    if _owner(con, v):
        n += one(con, "SELECT COUNT(*) FROM helper_offers WHERE id > ? AND created_at >= ?", o, core.now() - OFFER_KEEP)[0]
    return n


def listing(con, v: Viewer) -> dict:
    """The admin's list: the anonymous lines of the days already over, newest day first, shuffled within it; the offers
    (the creator's alone) newest first. `new`: since the list was last marked read."""
    if v.role != "admin":
        raise ApiError("forbidden")
    a, o = _seen(con)
    t = _day(core.now())
    return {"anon": [{"body": r["body"], "day": r["day"], "new": r["day"] > a}
                     for r in rows(con, "SELECT body, day FROM anon_feedback WHERE day < ? AND day > ? ORDER BY day DESC, random() LIMIT 300",
                                   t, t - ANON_KEEP)],
            "offers": [{"id": r["oid"], "person": person_ref(r), "username": r["tg_username"], "kinds": r["kinds"].split(","), "note": r["note"],
                        "at": r["offered_at"], "new": r["oid"] > o}
                       for r in rows(con, f"""SELECT p.*, h.id AS oid, h.kinds, h.note, h.created_at AS offered_at, w.tg_username
                           FROM helper_offers h JOIN users w ON w.id = h.user_id JOIN ({PERSON}) p ON p.id = h.user_id
                           WHERE h.created_at >= ? ORDER BY h.id DESC LIMIT 300""", core.now() - OFFER_KEEP)] if _owner(con, v) else []}


def seen(con, v: Viewer, body: object) -> None:
    """The list was read up to what it showed: {day: its newest anonymous day, offer: its newest offer id}.
    ponytail: one mark for all admins (the creator is the reader); per admin if there are more."""
    if v.role != "admin":
        raise ApiError("forbidden")
    day, oid = (body.get("day"), body.get("offer")) if isinstance(body, dict) else (None, None)
    if type(day) is not int or type(oid) is not int:
        raise ApiError("bad_input")
    with tx(con):
        a, o = _seen(con)
        a = max(a, min(day, _day(core.now()) - 1))  # never past the days released
        if _owner(con, v):
            o = max(o, oid)
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('helpus_seen', ?)", (f"{a},{o}",))


def sweep(con) -> None:
    con.execute("DELETE FROM anon_feedback WHERE day <= ?", (_day(core.now()) - ANON_KEEP,))
    con.execute("DELETE FROM helper_offers WHERE created_at < ?", (core.now() - OFFER_KEEP,))


from .oversight import _owner  # noqa: E402  (oversight imports half the logic: last, as the other domains do)
