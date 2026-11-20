"""Team events (case championships, hackathons, cybersport): an event's people sign up in teams of team_min..team_max,
at most team_cap teams (NULL: no cap; a new team can't be made past it, an open one can still be joined).

A captain signs up and creates a team, sends its invite link (startapp=et_<token>) to friends, who join by it; a team
short of people asks the app for teammates ("open"); a student without one signs up alone and waits. The organizer's
"Form teams" fills the open teams, then makes new ones of those alone. Every member is an ordinary 'going' registration
(seats, the door, awards work per person); migration 161's triggers take anyone who leaves the event out of their team,
and an empty team goes. The roster is ordered by when each came (the member row's id); its first is the captain.
Teams lock when the event starts, so a later bracket gets a fixed list (a team: id, name, ordered roster, captain).

A paid event: each player pays their own ticket by the Kaspi receipt, as a solo ticket (seats.py); no team payment, no
captain paying for others. The payment-state rule:
- in a team (made or joined by the player): 'going' only, i.e. the receipt is in (looked at or not yet) or a 1st-year
  free seat (counted as paid on purpose: the club gave it). A 30-min hold or the waitlist never (pay_first): the app
  signs a captain up alone, and he makes the team once the receipt is in. A teammate's invite link on a hold is kept on
  the registration (team_want, checked then: consent, room); the receipt joins them (paid()), or, if the team filled up
  or broke up meanwhile, they keep the paid seat with no team ('-': the sheet says so, and the bot). The seat is held
  only by the hold's 30 minutes; the team's place is not held.
- Form teams places only paid ones the organizer checked: the latest receipt reviewed and accepted, or a free seat; an
  unchecked receipt (maybe a fake) waits, and the organizer's list marks each unchecked member (teams_list `unchecked`).
- out: any status but 'going' (migration 161's triggers): a rejected receipt, a self-cancel, a deleted account. A refund
  happens outside the app and is recorded as rejecting the receipt (works on an accepted one too), which takes them out.
- seats: a paid team event with a cap holds at most cap x max seats (settings_ok), so nobody pays for a place no team
  can take; a team still under min at the deadline loses its slot by the organizer's move (team null), and the captain
  can't remove anyone after the sign-up deadline (Form teams places the rest before the start).
- price: a team event can't turn paid while anyone is signed up (they'd stay in their teams unpaid).
- Form teams completes teams, it doesn't spread people: the fullest short team first (a team of 4 gets the fifth before
  a team of 1 gets anyone). Before the sign-up deadline it fills only teams marked open; once the deadline passed (or
  the organizer confirms "fill all"), every short team, open or not, so closed teams of 4 can't strand paid soloists.
  Still only checked receipts, as above.
- a paid player leaving a team (a self-cancel, a rejected receipt): its captain hears it from the bot (left()); no
  money rule changes with it.

The feature's own consent (CONSENT, as evreports'): one per person, for every event. Nobody is put into a team without
it: creating, joining, Form teams and the organizer's moves all ask for it; someone signed up before an event became a
team event waits with no team until they agree. Signing up is the consent: the app asks one who hasn't agreed
in an alert on the sign-up tap and sends the version with it (signup's consent); a sign-up without it (an old app)
writes none and still signs up. Those signed up without it get the bot's template (consent_ask once, the organizer's remind
once a day), never a consent. Withdrawing it takes me out of my teams on events not started yet.

Who sees what: a team's name and roster, the people signed up for the event (their own team) and its organizers (all);
an invite link's holder sees the team it invites to. Other event viewers see the team settings and the names in a drawn
stage (evgroups.py and evbracket.py).
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import unicodedata

from .. import texts
from ..db import tx
from . import evmatches
from .core import PERSON_COLS, ApiError, Viewer, full, need_student, one, person_ref, rows

SIZE = (2, 10)    # the editor's bounds for a team's min and max
CAP = (2, 500)    # and for the number of teams
NAME_MAX = 40
CONSENT = "tm1"   # the privacy policy's teams clause, agreed to before the first team
OFF = "off"       # its row after a withdrawal: the no is remembered, so nobody asks again (a new yes overwrites it)


# ------------------------------------------------------------ the feature's own consent

def consented(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM team_consents WHERE user_id = ? AND version = ?", uid, CONSENT) is not None


def summary(con, v: Viewer) -> dict:
    """/api/me's part: agreed to teams yet."""
    return {"consent": consented(con, v.id)}


def agree(con, v: Viewer, body: dict) -> dict:
    """Mine given: the app sends the version it showed."""
    need_student(v)
    if not isinstance(body, dict) or body.get("consent") != CONSENT:
        raise ApiError("bad_input")
    with tx(con):
        con.execute("INSERT OR REPLACE INTO team_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))
    return summary(con, v)


def withdraw(con, v: Viewer) -> dict:
    """Mine taken back: out of every team I am in, past events' too (captaincy passes on; the sign-ups stay), and nobody
    places me again until a new yes. A started event's roster loses me as it would with my account: the law gives no
    reason to keep showing me there after I said no."""
    with tx(con):
        con.execute("INSERT OR REPLACE INTO team_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, OFF, core.now()))
        con.execute("DELETE FROM event_team_members WHERE user_id = ?", (v.id,))
    return summary(con, v)


def _consent(con, uid: int) -> None:
    if not consented(con, uid):
        raise ApiError("forbidden", "team_consent")  # the app asks it then


# ------------------------------------------------------------ the editor's switch

def settings(body: dict) -> dict:
    """teamMin, teamMax and teamCap (null: no cap) from the editor: absent keeps them, both sizes null turns teams off."""
    if "teamMax" not in body and "teamMin" not in body:
        return {}
    lo, hi, cap = body.get("teamMin"), body.get("teamMax"), body.get("teamCap")
    if lo is None and hi is None:
        return {"team_min": None, "team_max": None, "team_cap": None}
    if type(lo) is not int or type(hi) is not int or not SIZE[0] <= lo <= hi <= SIZE[1] or \
            cap is not None and (type(cap) is not int or not CAP[0] <= cap <= CAP[1]):
        raise ApiError("bad_input", "teams")
    return {"team_min": lo, "team_max": hi, **({"team_cap": cap} if "teamCap" in body else {})}  # absent: the cap kept


def settings_ok(con, f: dict, e: sqlite3.Row | None = None) -> None:
    """Teams only on an event of ours (free or paid), without late sign-up (it would move the roster after the start),
    never a meeting. On an existing event: set before the start only; switching on keeps everyone signed up as "no team
    yet"; a smaller max can't cut a team already bigger, a smaller cap can't drop teams already made; switching off lets
    every team go (the editor confirms)."""
    get = lambda k: f[k] if k in f else e[k] if e else None  # noqa: E731
    if get("team_max") is not None and get("price") and get("team_cap") and (get("seats") is None or get("seats") > get("team_cap") * get("team_max")):
        raise ApiError("bad_input", "team_seats")  # nobody pays for a place no team can take
    # a paid team event never holds a ticket nobody paid for (signed up while it was free, the price set later, teams
    # on after): whichever of the two changes now, anyone 'going' without a free seat or a receipt not rejected refuses it
    if get("team_max") is not None and get("price") and e and one(con, """SELECT 1 FROM registrations r WHERE r.event_id = ?
            AND r.status = 'going' AND r.free = 0 AND NOT EXISTS (SELECT 1 FROM receipts c WHERE c.registration_id = r.id AND c.status != 'rejected')""", e["id"]):
        raise ApiError("conflict", "team_paid")
    if get("team_max") is not None and (get("late_signup") or get("meeting") or get("guest_host") or get("external_url")):
        raise ApiError("bad_input", "teams")
    if not e or (get("team_min"), get("team_max"), get("team_cap")) == (e["team_min"], e["team_max"], e["team_cap"]):
        return
    if e["status"] != "draft" and e["starts_at"] <= core.now():
        raise ApiError("closed", "locked")
    if get("team_max") is None:
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (e["id"],))
        evmatches.remove_bracket(con, e["id"])
        con.execute("DELETE FROM event_teams WHERE event_id = ?", (e["id"],))
    elif one(con, "SELECT 1 FROM event_team_members WHERE event_id = ? GROUP BY team_id HAVING COUNT(*) > ?", e["id"], get("team_max")):
        raise ApiError("conflict", "team_size")
    elif get("team_cap") is not None and one(con, "SELECT COUNT(*) FROM event_teams WHERE event_id = ?", e["id"])[0] > get("team_cap"):
        raise ApiError("conflict", "team_cap")


# ------------------------------------------------------------ reading

def _team_event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = _event(con, v, eid)
    if e["team_max"] is None:
        raise ApiError("not_found")
    return e


def staff_event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = _staff_event(con, v, eid, "events")
    if e["team_max"] is None:
        raise ApiError("not_found")
    return e


def _open_now(e: sqlite3.Row) -> None:
    """Teams change only on a published event before it starts (then the list is fixed)."""
    if e["status"] != "published":
        raise ApiError("closed")
    if e["starts_at"] <= core.now():
        raise ApiError("closed", "locked")


def _rosters(con, eid: int, team: int | None = None) -> dict[int, list[sqlite3.Row]]:
    """Each team's people in order (the first is the captain), one query for the event (or one team)."""
    out: dict[int, list] = {}
    for p in rows(con, f"""SELECT {PERSON_COLS}, s.last_name AS ln, m.team_id FROM event_team_members m JOIN users u ON u.id = m.user_id
            LEFT JOIN students s ON s.user_id = u.id WHERE m.event_id = ? AND (? IS NULL OR m.team_id = ?) ORDER BY m.id""", eid, team, team):
        out.setdefault(p["team_id"], []).append(p)
    return out


def _shape(t: sqlite3.Row, people: list, captain: bool = False) -> dict:
    """A team as the app gets it; the invite token to its captain alone (never the organizers, never other members)."""
    return {"id": t["id"], "name": t["name"], "open": bool(t["open"]), "captain": people[0]["id"] if people else None,
            "members": [person_ref(p) for p in people], **({"token": t["token"]} if captain else {})}


def view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict | None:
    """The event sheet's part: the sizes for everyone; my own team (or that I wait for one) once I'm signed up."""
    if e["team_max"] is None:
        return None
    out = {"min": e["team_min"], "max": e["team_max"], "cap": e["team_cap"], "locked": e["starts_at"] <= core.now(), "team": None}
    r = one(con, "SELECT status, team_want FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], v.id)
    if r and r["team_want"] == "-" and r["status"] == "going":
        out["missed"] = True  # paid by a link whose team had no room left by then
    elif r and r["team_want"] and r["status"] == "hold":
        w = one(con, "SELECT name FROM event_teams WHERE token = ? AND event_id = ?", r["team_want"], e["id"])
        out["want"] = w["name"] if w else None  # the team I'll be in once my receipt is in
    t = one(con, "SELECT t.* FROM event_team_members m JOIN event_teams t ON t.id = m.team_id WHERE m.event_id = ? AND m.user_id = ?", e["id"], v.id)
    if t:
        people = _rosters(con, e["id"], t["id"]).get(t["id"], [])
        out["team"] = _shape(t, people, people[0]["id"] == v.id)
    if head:
        out["count"] = one(con, "SELECT COUNT(*) FROM event_teams WHERE event_id = ?", e["id"])[0]
    return out


def invite(con, v: Viewer, token: str) -> dict:
    """What an invite link opens to: the event, the team's name, its captain and how many it has, whether there is
    room. Never the other members: a link travels further than the captain meant, and attendees don't see each other.
    A dead link (the team is gone, or the captain made a new one) is not_found."""
    need_student(v)
    t = one(con, "SELECT * FROM event_teams WHERE token = ?", str(token or ""))
    if not t:
        raise ApiError("not_found")
    e = _team_event(con, v, t["event_id"])
    people = _rosters(con, e["id"], t["id"]).get(t["id"], [])
    mine = one(con, "SELECT team_id FROM event_team_members WHERE event_id = ? AND user_id = ?", e["id"], v.id)
    team = {"name": t["name"], "captain": person_ref(people[0]) if people else None, "count": len(people)}
    return {"event": e["id"], "title": e["title"], "team": team, "max": e["team_max"], "min": e["team_min"],
            "room": len(people) < e["team_max"], "mine": bool(mine and mine[0] == t["id"]), "locked": e["starts_at"] <= core.now(),
            "paid": bool(e["price"])}  # "I'm going in this team", then the payment


def teams_list(con, v: Viewer, eid: int) -> dict:
    """The organizer's screen: every team with its people, then who has none yet (in the order they signed up). The
    "events" right (the admin from Admin too, core.STAFF_RIGHTS). Full names, as in the attendees list."""
    e = staff_event(con, v, eid)
    teams = rows(con, "SELECT * FROM event_teams WHERE event_id = ? ORDER BY id", eid)
    rosters = _rosters(con, eid)
    # paid players whose latest receipt nobody checked yet (maybe a fake): the organizer sees them; never the members
    unchecked = [r[0] for r in rows(con, f"""SELECT r.user_id FROM registrations r WHERE r.event_id = ? AND r.status = 'going' AND NOT ({_CHECKED})""", eid)] \
        if e["price"] else []
    solo = rows(con, f"""SELECT {PERSON_COLS}, c.version IS '{CONSENT}' AS consent, c.version IS '{OFF}' AS off FROM registrations r JOIN users u ON u.id = r.user_id
        LEFT JOIN students s ON s.user_id = u.id LEFT JOIN team_consents c ON c.user_id = u.id
        WHERE r.event_id = ? AND r.status = 'going' AND NOT EXISTS (SELECT 1 FROM event_team_members m WHERE m.event_id = r.event_id AND m.user_id = r.user_id)
        ORDER BY r.created_at, r.id""", eid)
    return {"min": e["team_min"], "max": e["team_max"], "cap": e["team_cap"], "locked": e["starts_at"] <= core.now(),
            "regShut": bool(e["reg_until"] and e["reg_until"] <= core.now()),  # Form teams fills every short team now
            "paid": bool(e["price"]),
            "teams": [_shape(t, rosters.get(t["id"], [])) for t in teams], "solo": [{**person_ref(p), "consent": bool(p["consent"]), "off": bool(p["off"])} for p in solo], "unchecked": unchecked}


# a checked paid registration: a free seat, or its latest receipt accepted and reviewed by the app or a person (r: registrations)
_CHECKED = """r.free = 1 OR EXISTS (SELECT 1 FROM receipts c WHERE c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id)
    AND c.status = 'accepted' AND c.reviewed_at IS NOT NULL)"""


# ------------------------------------------------------------ a student's own

def clean_name(raw: object) -> str:
    """2-40 characters of plain text, spaces squeezed, nothing invisible (the forum's filter: format marks, filler
    letters), the blank Braille cell read as a space, something that shows (not only marks), no @handles or links."""
    s = "".join(" " if ch == "\u2800" else ch for ch in str(raw or "") if fchannel._visible(ch) and unicodedata.category(ch)[0] != "C")
    s = " ".join(s.split())
    if not 2 <= len(s) <= NAME_MAX or all(unicodedata.category(ch)[0] in "MZ" for ch in s) or re.search(r"@|https?:|t\.me/|www\.", s, re.I):
        raise ApiError("bad_input", "team_name")
    return s


def name_key(s: str) -> str:
    """What makes two names the same within an event: NFKC, casefolded (Cyrillic and fullwidth too, not SQLite's NOCASE)."""
    return unicodedata.normalize("NFKC", s).casefold()


def _going(con, e: sqlite3.Row, uid: int) -> None:
    """Only a ticket counts: someone on the waitlist (or out) has no team until they're in, a paid seat on hold until
    its receipt is in."""
    r = one(con, "SELECT status FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)
    if not r or r[0] != "going":
        raise ApiError("closed", "pay_first" if r and r[0] == "hold" else "not_going")


def _free(con, e: sqlite3.Row, uid: int) -> None:
    if one(con, "SELECT 1 FROM event_team_members WHERE event_id = ? AND user_id = ?", e["id"], uid):
        raise ApiError("conflict", "in_team")


def _add(con, e: sqlite3.Row, tid: int, uid: int) -> None:
    """One more on the team, under the write lock: never past the max."""
    if one(con, "SELECT COUNT(*) FROM event_team_members WHERE team_id = ?", tid)[0] >= e["team_max"]:
        raise ApiError("full", "team_full")
    con.execute("INSERT INTO event_team_members (team_id, event_id, user_id) VALUES (?, ?, ?)", (tid, e["id"], uid))


def _new_team(con, e: sqlite3.Row, name: str) -> int:
    """Under the write lock: never past the event's cap on teams."""
    if e["team_cap"] is not None and one(con, "SELECT COUNT(*) FROM event_teams WHERE event_id = ?", e["id"])[0] >= e["team_cap"]:
        raise ApiError("full", "team_cap")
    try:
        return con.execute("INSERT INTO event_teams (event_id, name, name_key, token, created_at) VALUES (?, ?, ?, ?, ?)",
                           (e["id"], name, name_key(name), secrets.token_hex(12), core.now())).lastrowid
    except sqlite3.IntegrityError:
        raise ApiError("conflict", "name_taken")


def _create(con, v: Viewer, e: sqlite3.Row, name: str) -> None:
    _open_now(e)
    _going(con, e, v.id)
    _consent(con, v.id)
    _free(con, e, v.id)
    _add(con, e, _new_team(con, e, name), v.id)


def _join(con, v: Viewer, e: sqlite3.Row, token: object) -> None:
    t = one(con, "SELECT * FROM event_teams WHERE token = ? AND event_id = ?", str(token or ""), e["id"])
    if not t:
        raise ApiError("not_found", "team_link")  # gone, replaced by a new one, or another event's link
    _open_now(e)
    if one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'hold'", e["id"], v.id):
        _consent(con, v.id)  # a paid seat on hold: the link kept until the receipt is in (paid()), if the team has room now
        if one(con, "SELECT COUNT(*) FROM event_team_members WHERE team_id = ?", t["id"])[0] >= e["team_max"]:
            raise ApiError("full", "team_full")
        con.execute("UPDATE registrations SET team_want = ? WHERE event_id = ? AND user_id = ?", (t["token"], e["id"], v.id))
        return
    _going(con, e, v.id)
    _consent(con, v.id)
    _free(con, e, v.id)
    _add(con, e, t["id"], v.id)


def paid(con, rid: int) -> None:
    """The receipt is in (seats.add_receipt, under its lock): into the team the invite link was for, if it still has
    room; else the paid seat stays with no team ('-') and the bot says so."""
    r = one(con, "SELECT * FROM registrations WHERE id = ?", rid)
    if not r or not r["team_want"] or r["team_want"] == "-":
        return
    e = one(con, "SELECT * FROM events WHERE id = ?", r["event_id"])
    t = one(con, "SELECT * FROM event_teams WHERE token = ? AND event_id = ?", r["team_want"], e["id"])
    try:
        if not t or e["team_max"] is None:
            raise ApiError("not_found", "team_link")
        _open_now(e)
        _consent(con, r["user_id"])
        _free(con, e, r["user_id"])
        _add(con, e, t["id"], r["user_id"])  # its trigger clears team_want
    except ApiError:
        con.execute("UPDATE registrations SET team_want = '-' WHERE id = ?", (rid,))
        notify(con, r["user_id"], "team_missed", f"tm:{e['id']}:{core.now()}")


def signup(con, v: Viewer, eid: int, team: object, ref=None, phone=None, answers=None, wish=None, consent=None) -> dict:
    """Signing up for a team event in one tap: {"create": name}, {"join": token}, or nothing ("I have no team"). Under one
    lock with the registration: a full event (the waitlist) or a full team leaves no sign-up behind. Already signed up:
    the team part alone.
    consent: the version (CONSENT) the app sends when its sign-up tap showed the alert on what signing up to a team
    event means (signing up is the consent). Written with a ticket or a hold this tap made, never
    inferred: an old app without the marker, a tap on an existing sign-up, or one that lands on the waitlist writes
    nothing."""
    if team is not None and not (isinstance(team, dict) and (isinstance(team.get("create"), str) or isinstance(team.get("join"), str))):
        raise ApiError("bad_input", "team")
    if consent is not None and consent != CONSENT:
        raise ApiError("bad_input", "consent")  # a version this server doesn't know: the line it showed isn't ours
    name = clean_name(team["create"]) if team and "create" in team else None
    sweep_holds(con)  # an expired hold isn't a sign-up: this tap makes a new one
    with tx(con):
        had = one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')", eid, v.id)
        out = register(con, v, eid, ref, phone, answers, wish)
        # a ticket or a hold only: the waitlist isn't a sign-up yet (promoted later, they're "hasn't agreed" and asked)
        if consent and not had and one(con, """SELECT 1 FROM registrations r JOIN events e ON e.id = r.event_id AND e.team_max IS NOT NULL
                WHERE r.event_id = ? AND r.user_id = ? AND r.status IN ('going', 'hold')""", eid, v.id):
            con.execute("INSERT OR REPLACE INTO team_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))
        if team:
            e = _team_event(con, v, eid)
            if name is not None:
                _create(con, v, e, name)
            else:
                _join(con, v, e, team["join"])
    return {**out, "teamsConsent": consented(con, v.id)}  # the server's word: the app's /me follows it


def create(con, v: Viewer, eid: int, name: object) -> dict:
    """Signed up with no team yet: make one, captain of it."""
    need_student(v)
    n = clean_name(name)
    with tx(con):
        e = _team_event(con, v, eid)
        _create(con, v, e, n)
    return full(con, v, e)


def join(con, v: Viewer, eid: int, token: object) -> dict:
    need_student(v)
    with tx(con):
        e = _team_event(con, v, eid)
        _join(con, v, e, token)
    return full(con, v, e)


def _mine(con, v: Viewer, eid: int, captain: bool = False) -> tuple[sqlite3.Row, sqlite3.Row]:
    """(event, my team) before the start; captain: only its captain."""
    need_student(v)
    e = _team_event(con, v, eid)
    _open_now(e)
    t = one(con, "SELECT t.* FROM event_team_members m JOIN event_teams t ON t.id = m.team_id WHERE m.event_id = ? AND m.user_id = ?", eid, v.id)
    if not t:
        raise ApiError("not_found", "team")
    if captain and one(con, "SELECT user_id FROM event_team_members WHERE team_id = ? ORDER BY id LIMIT 1", t["id"])[0] != v.id:
        raise ApiError("forbidden", "captain")
    return e, t


def leave(con, v: Viewer, eid: int) -> dict:
    """Out of my team, still signed up (no team yet). A captain's role passes to who came next."""
    with tx(con):
        e, _ = _mine(con, v, eid)
        con.execute("DELETE FROM event_team_members WHERE event_id = ? AND user_id = ?", (eid, v.id))
    return full(con, v, e)


def edit(con, v: Viewer, eid: int, body: dict) -> dict:
    """The captain's: rename ("name") and "find us teammates" ("open")."""
    if not isinstance(body, dict) or not ("name" in body or "open" in body) or "open" in body and not isinstance(body["open"], bool):
        raise ApiError("bad_input")
    name = clean_name(body["name"]) if "name" in body else None
    with tx(con):
        e, t = _mine(con, v, eid, captain=True)
        if name is not None and name != t["name"]:
            try:
                con.execute("UPDATE event_teams SET name = ?, name_key = ? WHERE id = ?", (name, name_key(name), t["id"]))
            except sqlite3.IntegrityError:
                raise ApiError("conflict", "name_taken")
        if "open" in body:
            con.execute("UPDATE event_teams SET open = ? WHERE id = ?", (int(body["open"]), t["id"]))
    return full(con, v, e)


def new_link(con, v: Viewer, eid: int) -> dict:
    """The captain's "New link": a fresh token; the old link stops working (sent too far, say)."""
    with tx(con):
        e, t = _mine(con, v, eid, captain=True)
        con.execute("UPDATE event_teams SET token = ? WHERE id = ?", (secrets.token_hex(12), t["id"]))
    return full(con, v, e)


def remove(con, v: Viewer, eid: int, uid: int) -> dict:
    """The captain takes someone off the team; they stay signed up with no team, and the bot tells them. Not after the
    sign-up deadline: a paid player kicked at the last minute would have no time to be placed."""
    with tx(con):
        e, t = _mine(con, v, eid, captain=True)
        if e["reg_until"] and e["reg_until"] <= core.now():
            raise ApiError("closed", "locked")
        if uid == v.id or not con.execute("DELETE FROM event_team_members WHERE team_id = ? AND user_id = ?", (t["id"], uid)).rowcount:
            raise ApiError("not_found")
        notify(con, uid, "team_removed", f"tr:{eid}:{core.now()}")
    return full(con, v, e)


# ------------------------------------------------------------ the organizer's

def sizes(n: int, lo: int, hi: int) -> list[int]:
    """New teams for n people alone, each lo..hi, as even as possible, as few as possible; those who can't make a team
    of lo are left (fewer than lo of them). [] when n < lo."""
    k = -(-n // hi)              # the fewest teams that hold everyone
    if k * lo > n:               # too few to fill that many: as many full ones as there are lo's, the rest left
        k = n // lo
        return [hi] * k
    return [n // k + (i < n % k) for i in range(k)]


def _team_word(con, v: Viewer) -> str:
    lang = one(con, "SELECT lang FROM users WHERE id = ?", v.id)
    return texts.pick(texts.TEAM_NAME, lang[0] if lang else "ru")


def form(con, v: Viewer, eid: int, fill_all: object = False) -> dict:
    """"Form teams": the open teams filled up to max from those alone (the fullest short team first, so teams are
    completed rather than spread; people in the order they signed up); after the sign-up deadline every team under min, open
    or not, up to min; with fill_all (the organizer confirmed it) every short team up to max; then new teams of the rest (sizes(), no more than the cap leaves room for), each named "<Team> N" in the organizer's language, its first member
    captain. Existing teams are never broken up, nobody in a team moves; run again, it does what is left. A banned user
    is never placed, nor anyone without the teams consent (`noConsent`: how many), nor on a paid event anyone whose
    receipt the organizer hasn't checked (`unchecked` in the list). Everyone placed hears it from the bot.
    The answer: the list as teams_list, with `placed` and `left` (who couldn't be)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["team_max"] is None:
            raise ApiError("not_found")
        _open_now(e)
        every = fill_all is True or bool(e["reg_until"] and e["reg_until"] <= core.now())
        alone = rows(con, """SELECT r.user_id, c.user_id IS NOT NULL AS ok FROM registrations r JOIN users u ON u.id = r.user_id AND u.banned_at IS NULL
            LEFT JOIN team_consents c ON c.user_id = r.user_id AND c.version = ?
            WHERE r.event_id = ? AND r.status = 'going' AND (? OR {_CHECKED})
            AND NOT EXISTS (SELECT 1 FROM event_team_members m WHERE m.event_id = r.event_id AND m.user_id = r.user_id)
            ORDER BY r.created_at, r.id""".replace("{_CHECKED}", _CHECKED), CONSENT, eid, int(not e["price"]))
        solo = [r[0] for r in alone if r[1]]
        placed: list[tuple[int, int]] = []
        teams = [dict(t) for t in rows(con, """SELECT t.id, t.open, COUNT(m.id) AS n FROM event_teams t JOIN event_team_members m ON m.team_id = t.id
                WHERE t.event_id = ? GROUP BY t.id ORDER BY n DESC, t.id""", eid)]
        # first every team under min up to min (a closed one only once sign-up closed or on "fill all": it can't play as
        # it is), then up to max the teams that asked (open), a closed one only on the explicit "fill all" (so
        # three friends' closed team of 3 of 3..5 gets no strangers by the deadline alone)
        for upto, who in ((e["team_min"], lambda t: t["open"] or every), (e["team_max"], lambda t: t["open"] or fill_all is True)):
            for t in sorted(teams, key=lambda t: (-t["n"], t["id"])):
                while who(t) and t["n"] < upto and solo:
                    placed.append((t["id"], solo.pop(0)))
                    t["n"] += 1
        word, n = _team_word(con, v), 0
        taken = {r[0] for r in rows(con, "SELECT name_key FROM event_teams WHERE event_id = ?", eid)}
        room = len(solo) if e["team_cap"] is None else max(0, e["team_cap"] - len(taken))
        for size in sizes(len(solo), e["team_min"], e["team_max"])[:room]:
            n += 1
            while name_key(f"{word} {n}") in taken:
                n += 1
            tid = _new_team(con, e, f"{word} {n}")
            placed += [(tid, solo.pop(0)) for _ in range(size)]
        con.executemany("INSERT INTO event_team_members (team_id, event_id, user_id) VALUES (?, ?, ?)", [(t, eid, u) for t, u in placed])
        for t, u in placed:
            notify(con, u, "team_placed", f"tp:{eid}:{t}")
    return {**teams_list(con, v, eid), "placed": len(placed), "left": len(solo), "noConsent": len(alone) - len(placed) - len(solo)}


def move(con, v: Viewer, eid: int, uid: int, team: object) -> dict:
    """The organizer moves one person into a team (not past its max; the bot tells them) or out to no team (team null).
    A banned user is not moved anywhere, nor into a team anyone without the teams consent."""
    if team is not None and type(team) is not int:
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["team_max"] is None:
            raise ApiError("not_found")
        _open_now(e)
        _going(con, e, uid)
        if one(con, "SELECT 1 FROM users WHERE id = ? AND banned_at IS NOT NULL", uid):
            raise ApiError("not_found")
        now_in = one(con, "SELECT team_id FROM event_team_members WHERE event_id = ? AND user_id = ?", eid, uid)
        if team is not None and not one(con, "SELECT 1 FROM event_teams WHERE id = ? AND event_id = ?", team, eid):
            raise ApiError("not_found", "team")
        if (now_in[0] if now_in else None) == team:
            return teams_list(con, v, eid)
        if team is not None and not consented(con, uid):
            raise ApiError("conflict", "team_consent")
        if team is not None and one(con, "SELECT COUNT(*) FROM event_team_members WHERE team_id = ?", team)[0] >= e["team_max"]:
            raise ApiError("full", "team_full")  # checked before the move: leaving its own last place mustn't drop the target
        con.execute("DELETE FROM event_team_members WHERE event_id = ? AND user_id = ?", (eid, uid))
        if team is not None:
            con.execute("INSERT INTO event_team_members (team_id, event_id, user_id) VALUES (?, ?, ?)", (team, eid, uid))
            notify(con, uid, "team_placed", f"tp:{eid}:{team}")
        elif now_in:
            notify(con, uid, "team_removed", f"tr:{eid}:{core.now()}")  # as the captain's remove
    return teams_list(con, v, eid)


# ------------------------------------------------------------ consent requests for registrations without consent

def consent_ask(con, dry: bool = False) -> int:
    """`python -m kbtu.admin team-consent-ask [--dry]`: everyone signed up to a coming team event without the teams
    consent (signed up before the sign-up became the consent) gets the bot's template once, for their soonest
    such event (the consent is one for all events), a button to it with the consent sheet open (tc_<event>). Never a
    consent written for them; nobody who withdrew it (OFF), nobody ever asked before. By hand, never on deploy."""
    to = rows(con, """SELECT r.user_id, r.event_id, MIN(e.starts_at) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE e.team_max IS NOT NULL AND e.status = 'published' AND e.hidden_at IS NULL AND e.starts_at > ?
          AND r.status IN ('going', 'hold', 'waitlist')
          AND NOT EXISTS (SELECT 1 FROM team_consents c WHERE c.user_id = r.user_id)
          AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = r.user_id AND b.kind = 'team_consent')
        GROUP BY r.user_id ORDER BY r.user_id""", core.now())  # SQLite: the bare event_id is MIN's row
    if not dry:
        with tx(con):
            for r in to:
                notify(con, r["user_id"], "team_consent", f"tc:{r['event_id']}")
    return len(to)


def remind(con, v: Viewer, eid: int, uid: int) -> dict:
    """The organizer's "Remind about consent" on someone with a ticket and no team consent: the same template, at most
    once a day per person (the consent is one for all events), whoever queued the last one. queued: false when asked
    within the day, agreed meanwhile (consent) or withdrew it (off: never asked again until they say yes)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["team_max"] is None:
            raise ApiError("not_found")
        _open_now(e)
        if not one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", eid, uid):
            raise ApiError("not_found")  # as the board: only a ticket waits for a team
        c = one(con, "SELECT version FROM team_consents WHERE user_id = ?", uid)
        if c:
            return {"queued": False, "consent": c[0] == CONSENT, "off": c[0] == OFF}
        if one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'team_consent' AND send_after > ?", uid, core.now() - 86400):
            return {"queued": False, "consent": False, "off": False}
        notify(con, uid, "team_consent", f"tc:{eid}:{core.now()}")
    return {"queued": True, "consent": False, "off": False}


def left(con, eid: int, uid: int) -> None:
    """Before a player's ticket ends (a self-cancel, a rejected receipt; the trigger then takes them out): the team's
    captain hears a player left (the next in line if the captain is the one leaving). Who left isn't in the message."""
    m = one(con, "SELECT id, team_id FROM event_team_members WHERE event_id = ? AND user_id = ?", eid, uid)
    cap = m and one(con, "SELECT user_id FROM event_team_members WHERE team_id = ? AND user_id != ? ORDER BY id LIMIT 1", m["team_id"], uid)
    if cap:  # the ref's last part: the membership row that ended (one message per leaving, no user id)
        notify(con, cap[0], "team_left", f"tl:{eid}:{m['team_id']}:{m['id']}")


def cancelled(con, eid: int) -> None:
    """The event is called off: its teams go (the sign-ups stay, as for every cancelled event)."""
    con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))
    evmatches.remove_bracket(con, eid)
    con.execute("DELETE FROM event_teams WHERE event_id = ?", (eid,))


# the other domains', imported last: they import this one too
from . import core, fchannel  # noqa: E402
from .organizing import _staff_event  # noqa: E402
from .seats import _event, notify, register, sweep_holds  # noqa: E402
