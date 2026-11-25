"""Off-app tickets and age marks for the event's door."""
from __future__ import annotations

import csv
import hmac
import json
import re
from collections.abc import Iterable

from ..db import tx
from . import core, seats
from .core import ApiError, one, rows

KEY = b""  # app.create and the admin CLI derive this key from TOKEN_KEY
_HASH_BYTES = 16


def _name_words(name: str | None) -> set[str]:
    from ..roster import _words

    return _words((name or "").casefold().replace("'", "-").replace("\u2019", "-"))


def _surnames(student) -> set[str]:
    surnames = set()
    for col in ("last_name", "last_lat"):
        words = _name_words(student[col])
        if len(words) == 1:
            surnames.update(words)
    return surnames


def _surname_hash(eid: int, sid: str, word: str) -> bytes:
    # Use the event and student number as the row's salt, and a server key against surname guesses.
    return hmac.digest(KEY, f"{eid}:{sid}:{word}".encode(), "sha256")[:_HASH_BYTES]


def _proves_surname(code: bytes | None, eid: int, sid: str, surnames: set[str]) -> bool:
    if not code:
        return False
    hashes = {code[i:i + _HASH_BYTES] for i in range(0, len(code), _HASH_BYTES)}
    return any(_surname_hash(eid, sid, word) in hashes for word in surnames)


def set_age(con, rid: int, adult: int | bool, by: int | None) -> None:
    con.execute("""INSERT INTO reg_age (registration_id, adult, set_by, set_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (registration_id) DO UPDATE SET adult = excluded.adult, set_by = excluded.set_by,
            set_at = excluded.set_at WHERE excluded.set_by IS NOT NULL
            OR (reg_age.set_by IS NULL AND reg_age.adult != excluded.adult)""", (rid, adult, by, core.now()))


def _ticket(con, eid: int, uid: int, adult: int | None) -> None:
    """Record an off-app ticket without queueing a bot message or running the normal sign-up flow."""
    t = core.now()
    r = one(con, "SELECT id, status FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
    if not r:
        rid = con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at)
            VALUES (?, ?, 'going', ?, ?, ?)""", (eid, uid, seats._ticket_code(con, eid), t, t)).lastrowid
    else:
        rid = r["id"]
        if r["status"] != "going":
            seats.renew_cancelled_ticket(con, eid, r)
            con.execute("""UPDATE registrations SET status = 'going', cancel_reason = NULL,
                hold_until = NULL, waitlisted_at = NULL, updated_at = ? WHERE id = ?""", (t, rid))
    if adult is not None:
        set_age(con, rid, adult, None)


def _carry_door(con, g, uid: int) -> None:
    con.execute("UPDATE registrations SET door_team = COALESCE(door_team, ?) WHERE event_id = ? AND user_id = ?",
                (g["team"], g["event_id"], uid))
    if g["came_at"] is not None:
        con.execute("""UPDATE registrations SET checked_in_at = ?, checkin_manual = 1
            WHERE event_id = ? AND user_id = ? AND checked_in_at IS NULL""", (g["came_at"], g["event_id"], uid))


def import_csv(con, eid: int, source: Iterable[str]) -> tuple[int, int, int, int]:
    from ..roster import tg_of

    parsed = []
    registered = pending = offline = bad = 0
    for i, line in enumerate(source):
        # IDs and age flags are single-line fields. A malformed row cannot consume the next one.
        try:
            row = next(csv.reader([line.lstrip("\ufeff") if i == 0 else line], strict=True))
        except csv.Error:
            bad += 1
            continue
        row = [value.strip() for value in row]
        if i == 0:
            header = [value.lower() for value in row]
            if (len(header) == 4 and header[:2] == ["student_id", "adult"]
                    and header[2] in ("username", "tg_username", "telegram_username")):
                continue
        if len(row) != 4 or row[1] not in ("0", "1", ""):
            bad += 1
            continue
        sid = row[0].upper()
        if not core.STUDENT_ID.fullmatch(sid):
            sid = None
        username = tg_of(row[2]) if sid is None else None
        words = _name_words(row[3])
        if not words or not (sid or username):
            bad += 1
            continue
        parsed.append((sid, int(row[1]) if row[1] else None, username, words))

    if not parsed:
        raise ApiError("bad_input", "guest CSV has no valid rows")

    with tx(con):
        if not one(con, "SELECT 1 FROM users WHERE is_founder = 1"):
            raise ApiError("forbidden")
        registered, pending, offline, _ = _place(con, eid, parsed, age=True)
    return registered, pending, offline, bad


def _place(con, eid: int, parsed: list, age: bool) -> tuple[int, int, int, int]:
    """The list's rows with a student ID or a username, inside the caller's tx: a ticket for whoever is in the app
    under that surname, a pending row (a one-way surname code) for a student ID not in the app yet. The first list
    makes it a guest-list event: app sign-ups the list doesn't name lose their seat. An ended event gives no new
    ticket, only claims those the door let in. (registered, pending, offline, seats dropped)"""
    registered = pending = offline = dropped = 0
    matched = set()
    e = one(con, "SELECT guest_list, COALESCE(ends_at, starts_at + ?) <= ? AS ended FROM events WHERE id = ?",
            core.NO_END, core.now(), eid)
    if not e:
        raise ApiError("not_found")
    con.execute("UPDATE events SET guest_list = 1, age_check = CASE WHEN ? THEN 1 ELSE age_check END WHERE id = ?", (int(age), eid))
    for sid, adult, username, words in parsed:
        if sid:
            u = one(con, "SELECT user_id, last_name, last_lat FROM students WHERE student_id = ? AND manual = 0", sid)
        else:
            # A reused handle can still be cached on the old account, even if only one account is verified.
            found = rows(con, f"""SELECT s.user_id, s.last_name, s.last_lat FROM users u LEFT JOIN students s
                ON s.user_id = u.id AND s.manual = 0 AND NOT {core.staff_sql()}
                WHERE lower(u.tg_username) = ? LIMIT 2""", username)
            u = found[0] if len(found) == 1 and found[0][0] is not None else None
        surnames = _surnames(u) if u else set()
        if words & surnames and not e["ended"]:
            old = one(con, "SELECT * FROM event_guests WHERE event_id = ? AND student_id = ?", eid, sid) if sid else None
            proved = old and _proves_surname(old["surname_hash"], eid, sid, surnames)
            if adult is None and proved:
                adult = old["adult"]
            _ticket(con, eid, u[0], adult)
            if proved:
                _carry_door(con, old, u[0])
            if old and (proved or old["came_at"] is None):
                con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (eid, sid))
            matched.add(u[0])
            registered += 1
        elif sid:
            # Keep the hashes of possible surnames. A reimport cannot change the proof used at the door, nor a row
            # the door already let in (its 18+ is from the ID card).
            code = b"".join(sorted(_surname_hash(eid, sid, word) for word in words))
            pending += con.execute("""INSERT INTO event_guests (event_id, student_id, adult, surname_hash) VALUES (?, ?, ?, ?)
                ON CONFLICT (event_id, student_id) DO UPDATE SET surname_hash = excluded.surname_hash,
                adult = COALESCE(excluded.adult, CASE WHEN excluded.surname_hash = event_guests.surname_hash
                    THEN event_guests.adult END) WHERE event_guests.came_at IS NULL""", (eid, sid, adult, code)).rowcount
        else:
            offline += 1
    if not e["guest_list"] and not e["ended"]:
        # On activation, existing app sign-ups only keep a ticket if the spreadsheet includes them.
        for r in rows(con, "SELECT * FROM registrations WHERE event_id = ? AND status != 'cancelled'", eid):
            if r["user_id"] not in matched:
                dropped += seats._seat_out(con, r, "removed")
    registered += claim_event(con, eid)
    return registered, pending, offline, dropped


def erase_pending(con, uid: int) -> None:
    for g in rows(con, """SELECT g.*, s.last_name, s.last_lat FROM students s JOIN event_guests g ON g.student_id = s.student_id
            WHERE s.user_id = ? AND s.manual = 0""", uid):
        if _proves_surname(g["surname_hash"], g["event_id"], g["student_id"], _surnames(g)):
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))


def claim(con, uid: int) -> None:
    _claim(con, "s.user_id", uid)


def claim_event(con, eid: int) -> int:
    return _claim(con, "g.event_id", eid)


def _claim(con, column: str, key: int) -> int:
    claimed = 0
    with tx(con):
        for g in rows(con, f"""SELECT g.*, s.user_id, s.last_name, s.last_lat FROM students s JOIN event_guests g ON g.student_id = s.student_id
            JOIN events e ON e.id = g.event_id WHERE {column} = ? AND s.manual = 0 AND e.guest_list = 1
            AND e.status != 'cancelled' AND (COALESCE(e.ends_at, e.starts_at + ?) > ?
                OR (e.starts_at IS NULL AND e.ends_at IS NULL) OR g.came_at IS NOT NULL)""", key, core.NO_END, core.now()):
            if not _proves_surname(g["surname_hash"], g["event_id"], g["student_id"], _surnames(g)):
                continue
            uid = g["user_id"]
            _ticket(con, g["event_id"], uid, g["adult"])
            _carry_door(con, g, uid)
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))
            claimed += 1
    return claimed


def need_ticket(con, eid: int, uid: int) -> None:
    if one(con, """SELECT 1 FROM events e WHERE e.id = ? AND e.guest_list = 1 AND NOT EXISTS (
        SELECT 1 FROM registrations r WHERE r.event_id = e.id AND r.user_id = ? AND r.status = 'going')""", eid, uid):
        raise ApiError("guest_list")


def pending_count(con, eid: int) -> dict:
    """The list's buyers not in the app yet: how many, how many let in by hand."""
    n, came = one(con, "SELECT COUNT(*), COUNT(came_at) FROM event_guests WHERE event_id = ?", eid)
    return {"pending": n, "pendingCame": came}


def let_in(con, eid: int, sid: object, surname: object, t: int) -> dict:
    """A buyer not in the app: the door types the student ID and the surname from their ID card; only a row whose
    one-way surname code matches is let in (a guessed ID alone opens nothing). Their 18+ from the list, if any."""
    if not isinstance(sid, str) or not isinstance(surname, str) or not 0 < len(sid) <= 20 or not 0 < len(surname) <= 80:
        raise ApiError("bad_input")
    sid = sid.strip().upper()
    g = one(con, "SELECT * FROM event_guests WHERE event_id = ? AND student_id = ?", eid, sid)
    if not g or not _proves_surname(g["surname_hash"], eid, sid, _name_words(surname)):
        raise ApiError("not_found")
    if not g["came_at"]:
        con.execute("UPDATE event_guests SET came_at = ? WHERE event_id = ? AND student_id = ?", (t, eid, sid))
    return {"already": bool(g["came_at"]), "adult": None if g["adult"] is None else bool(g["adult"]), **pending_count(con, eid)}


def set_pending_age(con, eid: int, sid: str, adult: bool) -> None:
    con.execute("UPDATE event_guests SET adult = ? WHERE event_id = ? AND student_id = ? AND came_at IS NOT NULL", (int(adult), eid, sid.strip().upper()))


ADULT = {"1": 1, "\u0434\u0430": 1, "yes": 1, "0": 0, "\u043d\u0435\u0442": 0, "no": 0}


def door_names(con, eid: int, lines) -> tuple[int, int]:
    """The organizers' sheet (student_id,name,adult,username,team) gives the door its list by name: a pending buyer's
    row gets the name; someone with no ticket in the app and no student ID on the list gets a row of their own."""
    items = []
    for row in csv.reader(lines):
        if len(row) < 2 or not row[1].strip():
            continue
        items.append((row[0].strip().upper(), " ".join(row[1].split())[:120],
                      ADULT.get((row[2] if len(row) > 2 else "").strip().casefold()),
                      (row[3] if len(row) > 3 else "").strip().lstrip("@").casefold(),
                      " ".join((row[4] if len(row) > 4 else "").split())[:80] or None))
    with tx(con):
        return _name(con, eid, items)


def _next_key(con, eid: int) -> int:
    """The next free number of a row with no student ID (x1, x2, ...): the highest, not a count (a corrected list
    removes rows)."""
    return one(con, """SELECT COALESCE(MAX(CAST(substr(student_id, 2) AS INTEGER)), 0) + 1 FROM event_guests
        WHERE event_id = ? AND student_id LIKE 'x%'""", eid)[0]


def _name(con, eid: int, items) -> tuple[int, int]:
    """door_names' rows (sid, name, adult, username, team), inside the caller's tx: (named, added)."""
    named = added = 0
    n = _next_key(con, eid) - 1
    for sid, name, adult, user, team in items:
        if sid and con.execute("UPDATE event_guests SET name = ?, username = COALESCE(?, username), team = COALESCE(?, team) WHERE event_id = ? AND student_id = ?",
                               (name, user or None, team, eid, sid)).rowcount:
            named += 1
            continue
        reg = (sid and one(con, """SELECT r.id FROM registrations r JOIN students s ON s.user_id = r.user_id
                WHERE r.event_id = ? AND s.student_id = ? AND r.status = 'going'""", eid, sid)) or (user and one(con, """SELECT r.id
                FROM registrations r JOIN users u ON u.id = r.user_id WHERE r.event_id = ? AND lower(u.tg_username) = ? AND r.status = 'going'""", eid, user))
        if reg:
            if team:
                con.execute("UPDATE registrations SET door_team = ? WHERE id = ?", (team, reg[0]))
            continue
        if sid and core.STUDENT_ID.fullmatch(sid):
            continue  # a student ID the import already placed (ticket or pending): never a second row
        if one(con, "SELECT 1 FROM event_guests WHERE event_id = ? AND name = ?", eid, name):
            if user or team:  # loaded before usernames and teams were kept: add them now
                con.execute("UPDATE event_guests SET username = COALESCE(username, ?), team = COALESCE(?, team) WHERE event_id = ? AND name = ?",
                            (user or None, team, eid, name))
            continue
        n += 1
        con.execute("INSERT INTO event_guests (event_id, student_id, adult, name, username, team) VALUES (?, ?, ?, ?, ?, ?)", (eid, f"x{n}", adult, name, user or None, team))
        added += 1
    return named, added


LIST_ROWS, LIST_CHARS, CELL = 3000, 600_000, 200  # one event's sheet; a bigger one is refused, not cut
WALK_INS = 1000  # an event's guests added at the door


def _cell(v: object) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ApiError("bad_input")
    return v


def load(con, eid: int, table: object) -> dict:
    """Studio's guest list (inside the caller's tx and rights): the organizers' sheet as rows of [name, student ID,
    18+, Telegram username, team], the columns already picked in the app. The same placing as the admin's `guests`
    and `guest-names` (_place, _name). A corrected file again: rows it no longer has go, except whoever came already
    and the guests added at the door; a ticket in the app stays (its holder may be at the door now). Every value is
    stored as typed: plain text, never run (the CSV out quotes a formula, texts._cell)."""
    from ..roster import tg_of

    if not isinstance(table, list) or not table:
        raise ApiError("bad_input")
    if len(table) > LIST_ROWS:
        raise ApiError("bad_input", "too_many")
    if not all(isinstance(r, list) and len(r) == 5 for r in table):
        raise ApiError("bad_input")
    cells = [[_cell(v) for v in r] for r in table]
    if sum(len(v) for r in cells for v in r) > LIST_CHARS:
        raise ApiError("bad_input", "too_big")
    bad, seen, dupes, parsed, items, adults = [], set(), 0, [], [], False
    for i, (name, sid, adult, user, team) in enumerate(cells, 1):
        if any(len(v) > CELL for v in (name, sid, adult, user, team)):
            bad.append({"row": i, "why": "long"})
            continue
        name, sid, team = " ".join(name.split())[:120], sid.strip().upper(), " ".join(team.split())[:80] or None
        words = _name_words(name)
        handle = tg_of(user) if user.strip() else None
        age = ADULT.get(adult.strip().casefold(), -1) if adult.strip() else None
        why = ("name" if not words else "student_id" if sid and not core.STUDENT_ID.fullmatch(sid)
               else "username" if user.strip() and not handle else "adult" if age == -1 else None)
        if why:
            bad.append({"row": i, "why": why})
            continue
        key = sid or (handle and "@" + handle) or "n:" + name.casefold()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        adults = adults or age is not None
        if sid or handle:
            parsed.append((sid or None, age, None if sid else handle, words))
        items.append((sid, name, age, handle or "", team))
    if not items:
        raise ApiError("bad_input", "no_rows")
    registered, pending, offline, dropped = _place(con, eid, parsed, age=adults)
    _name(con, eid, items)
    keep_ids = sorted({x[0] for x in items if x[0]})
    keep_names = sorted({x[1] for x in items})
    removed = con.execute("""DELETE FROM event_guests WHERE event_id = ? AND came_at IS NULL AND walk_in = 0
        AND student_id NOT IN (SELECT value FROM json_each(?)) AND (name IS NULL OR name NOT IN (SELECT value FROM json_each(?)))""",
        (eid, json.dumps(keep_ids), json.dumps(keep_names))).rowcount
    return {"rows": len(items), "inApp": registered, "onList": len(items) - registered, "dupes": dupes,
            "bad": bad[:50], "badCount": len(bad), "dropped": dropped, "removed": removed}


def walk_in(con, eid: int, name: object, team: object, adult: int | None, t: int) -> dict:
    """Someone not on the list let in at the door (inside the caller's tx and rights): a row of the door's own,
    checked in at once; a corrected list never removes it."""
    if not isinstance(name, str) or (team is not None and not isinstance(team, str)):
        raise ApiError("bad_input")
    name, team = " ".join(name.split()), " ".join((team or "").split()) or None
    if not _name_words(name) or len(name) > 120 or (team and len(team) > 80):
        raise ApiError("bad_input")
    if one(con, "SELECT COUNT(*) FROM event_guests WHERE event_id = ? AND walk_in = 1", eid)[0] >= WALK_INS:
        raise ApiError("rate_limited", "walk_ins")
    sid = f"x{_next_key(con, eid)}"
    con.execute("""INSERT INTO event_guests (event_id, student_id, adult, name, team, came_at, walk_in)
        VALUES (?, ?, ?, ?, ?, ?, 1)""", (eid, sid, adult, name, team, t))
    key = one(con, "SELECT door_key FROM event_guests WHERE event_id = ? AND student_id = ?", eid, sid)[0]  # set by trigger event_guests_key
    return {"key": key, "name": name, "adult": None if adult is None else bool(adult), "came": True, "at": t, "team": team,
            "walkIn": True, **pending_count(con, eid)}


def export(con, eid: int) -> list[dict]:
    """The list's rows for the CSV after the event: name, team, came at, a walk-in."""
    return [{"name": r["name"], "team": r["team"], "at": r["came_at"], "walkIn": bool(r["walk_in"])}
            for r in rows(con, "SELECT name, team, came_at, walk_in FROM event_guests WHERE event_id = ? AND name IS NOT NULL ORDER BY name", eid)]


def door_list(con, eid: int, full: bool = False) -> list[dict]:
    from ..checkin import _short
    return [{"key": r["door_key"], "name": r["name"] if full else _short(r["name"]), "adult": None if r["adult"] is None else bool(r["adult"]),
             "came": bool(r["came_at"]), "at": r["came_at"], "team": r["team"], **({"walkIn": True} if r["walk_in"] else {})}
            for r in rows(con, "SELECT door_key, name, adult, came_at, team, walk_in FROM event_guests WHERE event_id = ? AND name IS NOT NULL ORDER BY name", eid)]


def tick(con, eid: int, key: object, t: int, adult: object = None, came: bool = True) -> dict:
    """The door taps a name on its list: let in (the door saw the ID card), 18+ there if given."""
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key) or (adult is not None and not isinstance(adult, bool)):
        raise ApiError("bad_input")
    g = one(con, "SELECT * FROM event_guests WHERE event_id = ? AND door_key = ? AND name IS NOT NULL", eid, key)
    if not g:
        raise ApiError("not_found")
    con.execute("UPDATE event_guests SET came_at = CASE WHEN ? THEN COALESCE(came_at, ?) END, adult = COALESCE(?, adult) WHERE event_id = ? AND door_key = ?",
                (int(came), t, None if adult is None else int(adult), eid, key))
    return pending_count(con, eid)


def claim_username(con, uid: int) -> None:
    """Opening the app with a Telegram username on an event's list hands that row's ticket over at once (no KBTU
    sign-in): the username is Telegram's, one account at a time. Checked in already if the door ticked them."""
    name = one(con, "SELECT lower(tg_username) FROM users WHERE id = ?", uid)
    if not name or not name[0]:
        return
    with tx(con):
        for g in rows(con, """SELECT g.* FROM event_guests g JOIN events e ON e.id = g.event_id WHERE g.username = ? AND e.guest_list = 1
                AND e.status != 'cancelled' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""", name[0], core.NO_END, core.now()):
            _ticket(con, g["event_id"], uid, g["adult"])
            _carry_door(con, g, uid)
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))
