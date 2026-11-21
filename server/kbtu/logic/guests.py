"""Off-app tickets and age marks for the event's door."""
from __future__ import annotations

import csv
import hmac
from collections.abc import Iterable

from ..db import tx
from . import core, seats
from .core import ApiError, one, rows

KEY = b""  # app.create and the import CLI derive this key from TOKEN_KEY
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

    matched = set()
    with tx(con):
        if not one(con, "SELECT 1 FROM users WHERE is_founder = 1"):
            raise ApiError("forbidden")
        e = one(con, "SELECT guest_list FROM events WHERE id = ?", eid)
        if not e:
            raise ApiError("not_found")
        con.execute("UPDATE events SET guest_list = 1, age_check = 1 WHERE id = ?", (eid,))
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
            if words & surnames:
                old = one(con, """DELETE FROM event_guests WHERE event_id = ? AND student_id = ?
                    RETURNING adult, surname_hash""", eid, sid) if sid else None
                if adult is None and old and _proves_surname(old["surname_hash"], eid, sid, surnames):
                    adult = old["adult"]
                _ticket(con, eid, u[0], adult)
                matched.add(u[0])
                registered += 1
            elif sid:
                # The surname can be in any position. Keep only the codes of the possible surname words.
                code = b"".join(sorted(_surname_hash(eid, sid, word) for word in words))
                con.execute("""INSERT INTO event_guests (event_id, student_id, adult, surname_hash) VALUES (?, ?, ?, ?)
                    ON CONFLICT (event_id, student_id) DO UPDATE SET surname_hash = excluded.surname_hash,
                    adult = COALESCE(excluded.adult, CASE WHEN excluded.surname_hash = event_guests.surname_hash
                        THEN event_guests.adult END)""", (eid, sid, adult, code))
                pending += 1
            else:
                offline += 1
        if not e["guest_list"]:
            # On activation, existing app sign-ups only keep a ticket if the spreadsheet includes them.
            for r in rows(con, "SELECT * FROM registrations WHERE event_id = ? AND status != 'cancelled'", eid):
                if r["user_id"] not in matched:
                    seats._seat_out(con, r, "removed")
    return registered, pending, offline, bad


def erase_pending(con, uid: int) -> None:
    for g in rows(con, """SELECT g.*, s.last_name, s.last_lat FROM students s JOIN event_guests g ON g.student_id = s.student_id
            WHERE s.user_id = ? AND s.manual = 0""", uid):
        if _proves_surname(g["surname_hash"], g["event_id"], g["student_id"], _surnames(g)):
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))


def claim(con, uid: int) -> None:
    with tx(con):
        for g in rows(con, """SELECT g.*, s.last_name, s.last_lat FROM students s JOIN event_guests g ON g.student_id = s.student_id
            JOIN events e ON e.id = g.event_id WHERE s.user_id = ? AND s.manual = 0 AND e.guest_list = 1
            AND e.status != 'cancelled' AND (COALESCE(e.ends_at, e.starts_at + ?) > ?
                OR (e.starts_at IS NULL AND e.ends_at IS NULL))""", uid, core.NO_END, core.now()):
            if not _proves_surname(g["surname_hash"], g["event_id"], g["student_id"], _surnames(g)):
                continue
            _ticket(con, g["event_id"], uid, g["adult"])
            con.execute("UPDATE registrations SET door_team = COALESCE(door_team, ?) WHERE event_id = ? AND user_id = ?", (g["team"], g["event_id"], uid))
            if g["came_at"]:  # let in by hand before signing in: the ticket is a checked-in one
                con.execute("""UPDATE registrations SET checked_in_at = COALESCE(checked_in_at, ?), checkin_manual = 1
                    WHERE event_id = ? AND user_id = ?""", (g["came_at"], g["event_id"], uid))
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))


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


def door_names(con, eid: int, lines) -> tuple[int, int]:
    """The organizers' sheet (student_id,name,adult,username) gives the door its list by name: a pending buyer's row
    gets the name; someone with no ticket in the app and no student ID on the list gets a row of their own."""
    named = added = 0
    with tx(con):
        n = one(con, "SELECT COUNT(*) FROM event_guests WHERE event_id = ? AND student_id LIKE 'x%'", eid)[0]
        for row in csv.reader(lines):
            if len(row) < 2 or not row[1].strip():
                continue
            sid, name = row[0].strip().upper(), " ".join(row[1].split())[:120]
            adult = {"1": 1, "\u0434\u0430": 1, "yes": 1, "0": 0, "\u043d\u0435\u0442": 0, "no": 0}.get((row[2] if len(row) > 2 else "").strip().casefold())
            user = (row[3] if len(row) > 3 else "").strip().lstrip("@").casefold()
            team = " ".join((row[4] if len(row) > 4 else "").split())[:80] or None
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


def door_list(con, eid: int) -> list[dict]:
    return [{"key": r["student_id"], "name": r["name"], "adult": None if r["adult"] is None else bool(r["adult"]), "came": bool(r["came_at"]), "at": r["came_at"], "team": r["team"]}
            for r in rows(con, "SELECT student_id, name, adult, came_at, team FROM event_guests WHERE event_id = ? AND name IS NOT NULL ORDER BY name", eid)]


def tick(con, eid: int, key: object, t: int, adult: object = None, came: bool = True) -> dict:
    """The door taps a name on its list: let in (the door saw the ID card), 18+ there if given."""
    if not isinstance(key, str) or not 0 < len(key) <= 20 or (adult is not None and not isinstance(adult, bool)):
        raise ApiError("bad_input")
    g = one(con, "SELECT * FROM event_guests WHERE event_id = ? AND student_id = ? AND name IS NOT NULL", eid, key)
    if not g:
        raise ApiError("not_found")
    con.execute("UPDATE event_guests SET came_at = CASE WHEN ? THEN COALESCE(came_at, ?) END, adult = COALESCE(?, adult) WHERE event_id = ? AND student_id = ?",
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
            con.execute("UPDATE registrations SET door_team = COALESCE(door_team, ?) WHERE event_id = ? AND user_id = ?", (g["team"], g["event_id"], uid))
            if g["came_at"]:
                con.execute("""UPDATE registrations SET checked_in_at = COALESCE(checked_in_at, ?), checkin_manual = 1
                    WHERE event_id = ? AND user_id = ?""", (g["came_at"], g["event_id"], uid))
            con.execute("DELETE FROM event_guests WHERE event_id = ? AND student_id = ?", (g["event_id"], g["student_id"]))
