"""Rooms for the games friends play together, each on their own phone (Spy today, chess next): the one layer every such
game stands on. Several uvicorn workers serve the API, so nothing lives in memory: a room is one row, its whole state
JSON under an integer version that every change bumps, and its players with their seats beside it.

- A phone polls GET /api/rooms/<id>?v=<its version> (as the big screen polls its check-in): nothing comes back while
  nothing changed; a change sends that person's own view, built here (a game's secrets never reach the wrong phone).
- Every action carries an action id and the version it was made at, and runs in one write transaction: a version older
  than the phase it was meant for (`pv`, where the game's phase last changed) is stale and changes nothing, so a late
  tap can't vote in a vote that already closed; a duplicate (a retried POST) is recognised by its id. A game whose
  every action is its own phase (a chess move) is strictly one action per version.
- Deadlines are absolute times in the state (`dl`), kept on the row too; the first read or action after one passes
  moves the game on (the game's `tick`), so no timer runs anywhere. The client only draws the countdown.
- Presence (a player's seen_at) is written at most every 10 s, best-effort. A room nobody has looked at for an hour
  closes; any room's state and players go within hours (sweep), the bare row (for the daily cap) a day after.

A game module has MIN, MAX, `new(state)`, `act(state, seat, seats, host, act, body, t)` (True when it changed the state;
ApiError when it may not), `tick(state, t)`, `left(state, seat, seats, t)` and `view(state, seat)`.
"""
from __future__ import annotations

import json
import secrets

from ..db import maybe, tx
from . import spy
from .core import PERSON_COLS, ApiError, Viewer, now, one, person_ref, rows

GAMES = {"spy": spy}
A_DAY = 30         # rooms one person may open a day
IDLE = 3600        # a room nobody has looked at for this long closes
KEEP = 3 * 3600    # a room's state and players go this long after its last change (or an hour after it ended)
SEEN_EVERY = 10    # presence written at most this often
ACTS_KEPT = 64     # the last action ids a room remembers (duplicates)


def _code(con) -> str:
    """Four digits no open room has. ponytail: 10,000 codes; past a few thousand open rooms at once, a fifth digit."""
    for _ in range(50):
        c = f"{secrets.randbelow(10000):04d}"
        if not one(con, "SELECT 1 FROM game_rooms WHERE code = ?", c):
            return c
    raise ApiError("unavailable", "codes")


def _seats(con, rid: int) -> list[dict]:
    return [dict(r) for r in rows(con, f"""SELECT p.seat, p.seen_at, {PERSON_COLS} FROM game_players p JOIN users u ON u.id = p.user_id
        LEFT JOIN students s ON s.user_id = u.id WHERE p.room_id = ? ORDER BY p.seat""", rid)]


def _room(con, rid: int):
    r = one(con, "SELECT * FROM game_rooms WHERE id = ? AND ended_at IS NULL", rid)
    if not r:
        raise ApiError("not_found", "room")
    return r


def _mine(con, v: Viewer, rid: int):
    r = _room(con, rid)
    seat = one(con, "SELECT seat FROM game_players WHERE room_id = ? AND user_id = ?", rid, v.id)
    if not seat:
        raise ApiError("not_found", "room")  # not in it: the same answer as no such room
    return r, seat[0]


def _save(con, r, state: dict, before: dict | None, t: int) -> int:
    """The new state at version+1, guarded by the version it was read at (one writer at a time anyway: db.tx)."""
    v = r["version"] + 1
    if before is None or state.get("phase") != before.get("phase"):
        state["pv"] = v  # the phase changed here: actions made before it are stale
    if not con.execute("UPDATE game_rooms SET state = ?, version = ?, deadline = ?, updated_at = ? WHERE id = ? AND version = ?",
                       (json.dumps(state, separators=(",", ":")), v, state.get("dl"), t, r["id"], r["version"])).rowcount:
        raise ApiError("conflict", "version")
    return v


def _due(con, r, t: int):
    """The room with its passed deadlines applied (the game's tick), written if anything moved."""
    if r["deadline"] is None or r["deadline"] > t:
        return r
    with tx(con):
        r = _room(con, r["id"])  # again, under the write lock: another worker may have moved it already
        if r["deadline"] is not None and r["deadline"] <= t:
            state = json.loads(r["state"])
            before = dict(state)
            GAMES[r["game"]].tick(state, t)
            _save(con, r, state, before, t)
            r = _room(con, r["id"])
    return r


def _view(con, r, uid: int) -> dict:
    state, seats = json.loads(r["state"]), _seats(con, r["id"])
    me = next((s["seat"] for s in seats if s["id"] == uid), None)
    host = seats[0]["seat"] if seats else None
    return {"id": r["id"], "game": r["game"], "code": r["code"], "v": r["version"], "now": now(), "me": me, "host": host,
            "players": [{"seat": s["seat"], **person_ref(s)} for s in seats], **GAMES[r["game"]].view(state, me)}


def create(con, v: Viewer, game: object) -> dict:
    mod = GAMES.get(game) if isinstance(game, str) else None
    if not mod:
        raise ApiError("bad_input")
    t = now()
    with tx(con):  # the count and the insert as one: parallel taps can't pass the day's cap
        if one(con, "SELECT COUNT(*) FROM game_rooms WHERE created_by = ? AND created_at > ?", v.id, t - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "rooms")
        _leave_all(con, v.id, t)  # one room at a time: opening a new one leaves the old
        state: dict = {}
        mod.new(state)
        state["pv"] = 1
        rid = con.execute("""INSERT INTO game_rooms (game, code, created_by, state, deadline, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (game, _code(con), v.id, json.dumps(state), state.get("dl"), t, t)).lastrowid
        con.execute("INSERT INTO game_players (room_id, user_id, seat, seen_at) VALUES (?, ?, 0, ?)", (rid, v.id, t))
    return _view(con, _room(con, rid), v.id)


def join(con, v: Viewer, code: object) -> dict:
    """By the room's four digits (typed, or the QR's g_<code> link). Already in: the room as it is."""
    code = str(code or "")
    if not (len(code) == 4 and code.isdigit()):
        raise ApiError("bad_input")
    t = now()
    with tx(con):
        r = one(con, "SELECT * FROM game_rooms WHERE code = ? AND ended_at IS NULL", code)
        if not r:
            raise ApiError("not_found", "room")
        if not one(con, "SELECT 1 FROM game_players WHERE room_id = ? AND user_id = ?", r["id"], v.id):
            mod, state = GAMES[r["game"]], json.loads(r["state"])
            if not mod.joinable(state):
                raise ApiError("closed", "started")
            seats = one(con, "SELECT COUNT(*), MAX(seat) FROM game_players WHERE room_id = ?", r["id"])
            if seats[0] >= mod.MAX:
                raise ApiError("full")
            _leave_all(con, v.id, t)
            con.execute("INSERT INTO game_players (room_id, user_id, seat, seen_at) VALUES (?, ?, ?, ?)",
                        (r["id"], v.id, (seats[1] if seats[1] is not None else -1) + 1, t))
            _save(con, r, state, state, t)  # the others' lobbies see the newcomer
            r = _room(con, r["id"])
    return _view(con, r, v.id)


def share(con, v: Viewer, code: object) -> tuple[str, dict]:
    """The join card's start link and fields (app.share 'gr'): only a room I'm in, while it's open."""
    r = one(con, """SELECT g.code FROM game_rooms g JOIN game_players p ON p.room_id = g.id AND p.user_id = ?
        WHERE g.code = ? AND g.ended_at IS NULL""", v.id, str(code or ""))
    if not r:
        raise ApiError("closed")
    return f"g_{r['code']}", {"code": r["code"]}


def mine(con, v: Viewer) -> dict | None:
    """The room I'm in (the app opened again mid-game), or None."""
    r = one(con, """SELECT g.* FROM game_players p JOIN game_rooms g ON g.id = p.room_id
        WHERE p.user_id = ? AND g.ended_at IS NULL ORDER BY g.id DESC LIMIT 1""", v.id)
    return _view(con, _due(con, r, now()), v.id) if r else None


def _seen(con, rid: int, uid: int, t: int) -> None:
    con.execute("UPDATE game_players SET seen_at = ? WHERE room_id = ? AND user_id = ? AND seen_at <= ?", (t, rid, uid, t - SEEN_EVERY))


def state(con, v: Viewer, rid: int, since: object = None) -> dict | None:
    """The poll: None while the room is still at the version the phone has (`since`), else my view of it."""
    t = now()
    r, _ = _mine(con, v, rid)
    if r["deadline"] is not None and r["deadline"] <= t:
        r = _due(con, r, t)
    else:
        seen = one(con, "SELECT seen_at FROM game_players WHERE room_id = ? AND user_id = ?", rid, v.id)
        if seen and seen[0] <= t - SEEN_EVERY:
            maybe(con, _seen, con, rid, v.id, t)  # never makes a poll wait behind someone's write
    if str(since) == str(r["version"]):
        return None
    return _view(con, r, v.id)


def act(con, v: Viewer, rid: int, body: dict) -> dict:
    """One action: {id, v, act, ...}. Stale or duplicate: nothing changes, and the answer says so (`applied`)."""
    aid, at, what = body.get("id"), body.get("v"), body.get("act")
    if not (isinstance(aid, str) and 8 <= len(aid) <= 64) or not isinstance(at, int) or isinstance(at, bool) or not isinstance(what, str):
        raise ApiError("bad_input")
    t = now()
    with tx(con):
        r, seat = _mine(con, v, rid)
        r = _due(con, r, t)
        state = json.loads(r["state"])
        acts = state.get("acts", [])
        if aid in acts:
            applied = True  # done already: this is the retry of a lost answer
        elif not state.get("pv", 0) <= at <= r["version"]:
            applied = False  # made before the phase it was meant for ended (or a version this room never had)
        else:
            mod, before = GAMES[r["game"]], dict(state)
            seats = [s[0] for s in rows(con, "SELECT seat FROM game_players WHERE room_id = ? ORDER BY seat", rid)]
            applied = mod.act(state, seat, seats, seat == seats[0], what, body, t)
            if applied:
                state["acts"] = (acts + [aid])[-ACTS_KEPT:]
                _save(con, r, state, before, t)
        _seen(con, rid, v.id, t)
        r = _room(con, rid)
    return {"applied": applied, "room": _view(con, r, v.id)}


def _leave(con, r, uid: int, t: int) -> None:
    seat = one(con, "SELECT seat FROM game_players WHERE room_id = ? AND user_id = ?", r["id"], uid)
    if not seat:
        return
    con.execute("DELETE FROM game_players WHERE room_id = ? AND user_id = ?", (r["id"], uid))
    seats = [s[0] for s in rows(con, "SELECT seat FROM game_players WHERE room_id = ? ORDER BY seat", r["id"])]
    if not seats:
        con.execute("UPDATE game_rooms SET ended_at = ?, code = NULL, updated_at = ? WHERE id = ?", (t, t, r["id"]))
        return
    state = json.loads(r["state"])
    before = dict(state)
    GAMES[r["game"]].left(state, seat[0], seats, t)
    _save(con, r, state, before, t)


def _leave_all(con, uid: int, t: int) -> None:
    for r in rows(con, """SELECT g.* FROM game_players p JOIN game_rooms g ON g.id = p.room_id
            WHERE p.user_id = ? AND g.ended_at IS NULL""", uid):
        _leave(con, r, uid, t)


def leave(con, v: Viewer, rid: int) -> None:
    t = now()
    with tx(con):
        r, _ = _mine(con, v, rid)
        _leave(con, r, v.id, t)


def sweep(con) -> None:
    """Hourly (chores._chores): rooms nobody looks at close; a room's state and players go KEEP after its last change
    (an hour after it ended), the bare row a day after it was opened (the daily cap counts it till then)."""
    t = now()
    with tx(con):
        con.execute("""UPDATE game_rooms SET ended_at = ?, code = NULL WHERE ended_at IS NULL AND updated_at < ?
            AND NOT EXISTS (SELECT 1 FROM game_players p WHERE p.room_id = game_rooms.id AND p.seen_at >= ?)""", (t, t - IDLE, t - IDLE))
        gone = "(updated_at < ? OR ended_at < ?)"
        con.execute(f"DELETE FROM game_players WHERE room_id IN (SELECT id FROM game_rooms WHERE {gone})", (t - KEEP, t - 3600))
        con.execute(f"""UPDATE game_rooms SET state = '{{}}', code = NULL, ended_at = COALESCE(ended_at, ?)
            WHERE {gone} AND state != '{{}}'""", (t, t - KEEP, t - 3600))
        con.execute("DELETE FROM game_rooms WHERE created_at < ?", (t - 86400,))
