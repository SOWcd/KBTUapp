"""Team events (case championships, hackathons, cybersport): a free event's people sign up in teams of team_min..team_max.

A captain signs up and creates a team, sends its invite link (startapp=et_<token>) to friends, who join by it; a team
short of people asks the app for teammates ("open"); a student without one signs up alone and waits. The organizer's
"Form teams" fills the open teams, then makes new ones of those alone. Every member is an ordinary 'going' registration
(seats, the door, awards work per person); migration 161's triggers take anyone who leaves the event out of their team,
and an empty team goes. The roster is ordered by when each came (the member row's id); its first is the captain.
Teams lock when the event starts, so a later bracket gets a fixed list (a team: id, name, ordered roster, captain).

The feature's own consent (CONSENT, as evreports'): one per person, for every event. Nobody is put into a team without
it: creating, joining, Form teams and the organizer's moves all ask for it; someone signed up before an event became a
team event waits with no team until they agree. Withdrawing it takes me out of my teams on events not started yet.

Who sees what: a team's name and roster, the people signed up for the event (their own team) and its organizers (all);
an invite link's holder sees the team it invites to; anyone else, only that it is a team event and its sizes.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import unicodedata

from .. import texts
from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, full, need_student, one, person_ref, rows

SIZE = (2, 10)    # the editor's bounds for a team's min and max
NAME_MAX = 40
CONSENT = "tm1"   # the privacy policy's teams clause, agreed to before the first team


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
    reason to keep showing me there after I said no (the legal review, Nov 12)."""
    with tx(con):
        con.execute("DELETE FROM team_consents WHERE user_id = ?", (v.id,))
        con.execute("DELETE FROM event_team_members WHERE user_id = ?", (v.id,))
    return summary(con, v)


def _consent(con, uid: int) -> None:
    if not consented(con, uid):
        raise ApiError("forbidden", "team_consent")  # the app asks it then


# ------------------------------------------------------------ the editor's switch

def settings(body: dict) -> dict:
    """teamMin and teamMax from the editor: absent keeps them, both null turns teams off."""
    if "teamMax" not in body and "teamMin" not in body:
        return {}
    lo, hi = body.get("teamMin"), body.get("teamMax")
    if lo is None and hi is None:
        return {"team_min": None, "team_max": None}
    if type(lo) is not int or type(hi) is not int or not SIZE[0] <= lo <= hi <= SIZE[1]:
        raise ApiError("bad_input", "teams")
    return {"team_min": lo, "team_max": hi}


def settings_ok(con, f: dict, e: sqlite3.Row | None = None) -> None:
    """Teams only on a free event of ours, without late sign-up (it would move the roster after the start), never a
    meeting. On an existing event: set before the start only; switching on keeps everyone signed up as "no team yet";
    a smaller max can't cut a team already bigger; switching off lets every team go (the editor confirms)."""
    get = lambda k: f[k] if k in f else e[k] if e else None  # noqa: E731
    if get("team_max") is not None and (get("price") or get("late_signup") or get("meeting") or get("guest_host") or get("external_url")):
        raise ApiError("bad_input", "teams")
    if not e or (get("team_min"), get("team_max")) == (e["team_min"], e["team_max"]):
        return
    if e["status"] != "draft" and e["starts_at"] <= core.now():
        raise ApiError("closed", "locked")
    if get("team_max") is None:
        con.execute("DELETE FROM event_teams WHERE event_id = ?", (e["id"],))
    elif one(con, "SELECT 1 FROM event_team_members WHERE event_id = ? GROUP BY team_id HAVING COUNT(*) > ?", e["id"], get("team_max")):
        raise ApiError("conflict", "team_size")


# ------------------------------------------------------------ reading

def _team_event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = _event(con, v, eid)
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
    out = {"min": e["team_min"], "max": e["team_max"], "locked": e["starts_at"] <= core.now(), "team": None}
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
            "room": len(people) < e["team_max"], "mine": bool(mine and mine[0] == t["id"]), "locked": e["starts_at"] <= core.now()}


def teams_list(con, v: Viewer, eid: int) -> dict:
    """The organizer's screen: every team with its people, then who has none yet (in the order they signed up). The
    "events" right (the admin from Admin too, core.STAFF_RIGHTS). Full names, as in the attendees list."""
    e = _staff_event(con, v, eid, "events")
    if e["team_max"] is None:
        raise ApiError("not_found")
    teams = rows(con, "SELECT * FROM event_teams WHERE event_id = ? ORDER BY id", eid)
    rosters = _rosters(con, eid)
    solo = rows(con, f"""SELECT {PERSON_COLS}, c.user_id IS NOT NULL AS consent FROM registrations r JOIN users u ON u.id = r.user_id
        LEFT JOIN students s ON s.user_id = u.id LEFT JOIN team_consents c ON c.user_id = u.id AND c.version = '{CONSENT}'
        WHERE r.event_id = ? AND r.status = 'going' AND NOT EXISTS (SELECT 1 FROM event_team_members m WHERE m.event_id = r.event_id AND m.user_id = r.user_id)
        ORDER BY r.created_at, r.id""", eid)
    return {"min": e["team_min"], "max": e["team_max"], "locked": e["starts_at"] <= core.now(),
            "teams": [_shape(t, rosters.get(t["id"], [])) for t in teams], "solo": [{**person_ref(p), "consent": bool(p["consent"])} for p in solo]}


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
    """Only a seat counts: someone on the waitlist (or out) has no team until they're in."""
    if not one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", e["id"], uid):
        raise ApiError("closed", "not_going")


def _free(con, e: sqlite3.Row, uid: int) -> None:
    if one(con, "SELECT 1 FROM event_team_members WHERE event_id = ? AND user_id = ?", e["id"], uid):
        raise ApiError("conflict", "in_team")


def _add(con, e: sqlite3.Row, tid: int, uid: int) -> None:
    """One more on the team, under the write lock: never past the max."""
    if one(con, "SELECT COUNT(*) FROM event_team_members WHERE team_id = ?", tid)[0] >= e["team_max"]:
        raise ApiError("full", "team_full")
    con.execute("INSERT INTO event_team_members (team_id, event_id, user_id) VALUES (?, ?, ?)", (tid, e["id"], uid))


def _new_team(con, e: sqlite3.Row, name: str) -> int:
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
    _going(con, e, v.id)
    _consent(con, v.id)
    _free(con, e, v.id)
    _add(con, e, t["id"], v.id)


def signup(con, v: Viewer, eid: int, team: object, ref=None, phone=None, answers=None) -> dict:
    """Signing up for a team event in one tap: {"create": name}, {"join": token}, or nothing ("I have no team"). Under one
    lock with the registration: a full event (the waitlist) or a full team leaves no sign-up behind. Already signed up:
    the team part alone."""
    if team is not None and not (isinstance(team, dict) and (isinstance(team.get("create"), str) or isinstance(team.get("join"), str))):
        raise ApiError("bad_input", "team")
    name = clean_name(team["create"]) if team and "create" in team else None
    with tx(con):
        out = register(con, v, eid, ref, phone, answers)
        if team:
            e = _team_event(con, v, eid)
            if name is not None:
                _create(con, v, e, name)
            else:
                _join(con, v, e, team["join"])
    return out


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
    """The captain takes someone off the team; they stay signed up with no team, and the bot tells them."""
    with tx(con):
        e, t = _mine(con, v, eid, captain=True)
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


def form(con, v: Viewer, eid: int) -> dict:
    """"Form teams": the open teams filled up to max from those alone (the smallest team first, people in the order they
    signed up), then new teams of the rest (sizes()), each named "<Team> N" in the organizer's language, its first member
    captain. Existing teams are never broken up, nobody in a team moves; run again, it does what is left. A banned user
    is never placed, nor anyone without the teams consent (`noConsent`: how many). Everyone placed hears it from the bot.
    The answer: the list as teams_list, with `placed` and `left` (who couldn't be)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["team_max"] is None:
            raise ApiError("not_found")
        _open_now(e)
        alone = rows(con, """SELECT r.user_id, c.user_id IS NOT NULL AS ok FROM registrations r JOIN users u ON u.id = r.user_id AND u.banned_at IS NULL
            LEFT JOIN team_consents c ON c.user_id = r.user_id AND c.version = ?
            WHERE r.event_id = ? AND r.status = 'going'
            AND NOT EXISTS (SELECT 1 FROM event_team_members m WHERE m.event_id = r.event_id AND m.user_id = r.user_id)
            ORDER BY r.created_at, r.id""", CONSENT, eid)
        solo = [r[0] for r in alone if r[1]]
        placed: list[tuple[int, int]] = []
        for t in rows(con, """SELECT t.id, COUNT(m.id) AS n FROM event_teams t JOIN event_team_members m ON m.team_id = t.id
                WHERE t.event_id = ? AND t.open = 1 GROUP BY t.id ORDER BY n, t.id""", eid):
            for _ in range(min(e["team_max"] - t["n"], len(solo))):
                placed.append((t["id"], solo.pop(0)))
        word, n = _team_word(con, v), 0
        taken = {r[0] for r in rows(con, "SELECT name_key FROM event_teams WHERE event_id = ?", eid)}
        for size in sizes(len(solo), e["team_min"], e["team_max"]):
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


def cancelled(con, eid: int) -> None:
    """The event is called off: its teams go (the sign-ups stay, as for every cancelled event)."""
    con.execute("DELETE FROM event_teams WHERE event_id = ?", (eid,))


# the other domains', imported last: they import this one too
from . import core, fchannel  # noqa: E402
from .organizing import _staff_event  # noqa: E402
from .seats import _event, notify, register  # noqa: E402
