"""Rooms for games played together, each on their own phone (Spy now, chess next): the host makes one, friends come in
by its 4-digit code (typed, or the QR / shared link startapp=g_<code>, which joins at once).
The app runs several worker processes, so nothing lives in memory: one row per room holds the game's whole state as JSON
and a version every change moves. A phone polls GET /api/rooms/<id>?v=<the version it has> (every second while a phase
has a clock, else every five) and gets nothing back until the version moves. Every write names an action id and the
version it was made on, and lands only on that version (UPDATE ... WHERE version = ?, inside db.tx): a double tap
(the same action id) or a tap on an old screen (another version) changes nothing, and the answer is the room as it is.
Deadlines are absolute moments in the state, resolved by whoever reads or acts after one (the game's tick): no timer runs
anywhere. Each player's view is built here by the game's own view(), so a secret never leaves the server for whom it isn't
meant. Presence (game_players.seen_at) is written at most every SEEN_EVERY seconds of polling and never moves the version;
a rematch (`again`: the same room, code and host, another round) keeps only the players seen in the last AWAY seconds,
and is not a new room for the daily cap.
A room unchanged for KEEP is gone (purge: each new room and the nightly stats_day sweep), and so is one whose host or any
player deletes their account (account.delete_me)."""
from __future__ import annotations

import json
import secrets

from .. import db
from ..db import tx
from . import core, spy
from .core import PERSON, ApiError, Viewer, one, person_ref, rows  # core.now: the tests' clock

GAMES = {"spy": spy}
KEEP = 3 * 3600
SEEN_EVERY = 10
AWAY = 60  # unseen this long at a rematch: gone from the room (a phone at the reveal polls every 5 s)
A_DAY = 30  # rooms a person makes in a day
MISSES = 20  # wrong codes a person may type in an hour: 10,000 codes aren't many to walk through
ACTS_KEPT = 64  # the latest action ids each room remembers (a retry comes within seconds)


def _game(r):
    return GAMES[r["game"]]


def _players(con, rid: int) -> list[int]:
    return [x[0] for x in rows(con, "SELECT user_id FROM game_players WHERE room_id = ? ORDER BY rowid", rid)]


def _view(con, r, s: dict, uid: int, players: list[int]) -> dict:
    by_id = {p["id"]: p for p in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(players))})", *players)} if players else {}
    return {"id": r["id"], "game": r["game"], "code": r["code"], "v": r["version"], "now": core.now(), "me": uid, "host": r["host_id"],
            "live": _game(r).live(s), "players": [person_ref(by_id[p]) for p in players if p in by_id],
            **_game(r).view(s, uid)}


def _row(con, rid: object):
    if not isinstance(rid, int) or isinstance(rid, bool):
        raise ApiError("not_found")
    r = one(con, "SELECT * FROM game_rooms WHERE id = ? AND updated_at > ?", rid, core.now() - KEEP)
    if not r:
        raise ApiError("not_found")
    return r


def _ticked(con, r, players: list[int]):
    """The row with its passed deadlines resolved and written (guarded by the version: when another request got there
    first, its row is read again). Returns (row, state)."""
    for _ in range(5):
        s = json.loads(r["state"])
        t = core.now()
        if not _game(r).tick(s, players, t):
            return r, s
        if con.execute("UPDATE game_rooms SET state = ?, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                       (json.dumps(s), t, r["id"], r["version"])).rowcount:
            return {**dict(r), "state": json.dumps(s), "version": r["version"] + 1, "updated_at": t}, s
        r = _row(con, r["id"])
    raise ApiError("unavailable", "busy")


def purge(con) -> None:
    con.execute("DELETE FROM game_rooms WHERE updated_at <= ?", (core.now() - KEEP,))


def sweep(con) -> None:
    """Nightly (daily.stats_day): rooms left behind, and the counters (each counts its own day or hour only)."""
    with tx(con):
        purge(con)
        con.execute("DELETE FROM meta WHERE (key >= 'games:' AND key < 'games;') OR (key >= 'gmiss:' AND key < 'gmiss;')")


def _bump(con, key: str, window: int, limit: int, why: str) -> None:
    """One more against a per-person limit in this window (a day's or an hour's number), inside the caller's tx; meta,
    not the rooms' own rows: those are gone within hours."""
    n = one(con, "SELECT value FROM meta WHERE key = ?", key)
    used = int(n[0].split(":")[1]) if n and n[0].split(":")[0] == str(window) else 0
    if used >= limit:
        raise ApiError("rate_limited", why)
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, f"{window}:{used + 1}"))


def create(con, v: Viewer, body: dict) -> dict:
    game = body.get("game")
    if game not in GAMES:
        raise ApiError("bad_input", "game")
    t = core.now()
    with tx(con):
        purge(con)
        _bump(con, f"games:{v.id}", t // 86400, A_DAY, "rooms")
        for _ in range(50):
            code = f"{secrets.randbelow(10_000):04d}"
            if not one(con, "SELECT 1 FROM game_rooms WHERE code = ?", code):
                break
        else:
            raise ApiError("unavailable", "codes")
        rid = con.execute("INSERT INTO game_rooms (game, code, host_id, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (game, code, v.id, json.dumps({**GAMES[game].new(), "acts": []}), t, t)).lastrowid
        con.execute("INSERT INTO game_players (room_id, user_id, seen_at) VALUES (?, ?, ?)", (rid, v.id, t))
    r = _row(con, rid)
    return _view(con, r, json.loads(r["state"]), v.id, [v.id])


def join(con, v: Viewer, code: object) -> dict:
    """In by the code: a player already in gets their room back (at any phase); a new one only while it's open."""
    t = core.now()
    found = isinstance(code, str) and len(code) == 4 and code.isascii() and code.isdigit() \
        and one(con, "SELECT id FROM game_rooms WHERE code = ? AND updated_at > ?", code, t - KEEP)
    if not found:
        with tx(con):  # its own transaction: the error below must not roll the count back
            _bump(con, f"gmiss:{v.id}", t // 3600, MISSES, "codes")
        raise ApiError("not_found", "code")
    with tx(con):
        r = _row(con, found[0])
        players = _players(con, r["id"])
        if v.id not in players:
            s = json.loads(r["state"])
            if not _game(r).joinable(s):
                raise ApiError("closed", "started")
            if len(players) >= _game(r).MAX:
                raise ApiError("full")
            con.execute("INSERT INTO game_players (room_id, user_id, seen_at) VALUES (?, ?, ?)", (r["id"], v.id, t))
            con.execute("UPDATE game_rooms SET version = version + 1, updated_at = ? WHERE id = ?", (t, r["id"]))
            players.append(v.id)
            r = one(con, "SELECT * FROM game_rooms WHERE id = ?", r["id"])
    r, s = _ticked(con, r, players)
    return _view(con, r, s, v.id, players)


def get(con, v: Viewer, rid: int, have: int | None = None) -> dict | None:
    """The room as this player sees it; None when it is still at version `have` (the phone keeps what it has)."""
    r = _row(con, rid)
    seen = one(con, "SELECT seen_at FROM game_players WHERE room_id = ? AND user_id = ?", rid, v.id)
    if not seen:
        raise ApiError("not_found")
    t = core.now()
    if seen[0] <= t - SEEN_EVERY:
        db.maybe(con, con.execute, "UPDATE game_players SET seen_at = ? WHERE room_id = ? AND user_id = ?", (t, rid, v.id))
    players = _players(con, rid)
    r, s = _ticked(con, r, players)
    return None if have == r["version"] else _view(con, r, s, v.id, players)


def act(con, v: Viewer, rid: int, body: dict) -> dict:
    """One move: {id: the action's own id, v: the version it was made on, type, ...the game's fields}. Answers
    {applied, room}: applied false for a move made on another version (the room as it is now comes back; the phone may
    send it again on that one if it still means it). The same id twice: applied once, the second answer as the first."""
    aid, have = body.get("id"), body.get("v")
    if not isinstance(aid, str) or not 8 <= len(aid) <= 64 or not isinstance(have, int) or isinstance(have, bool):
        raise ApiError("bad_input", "action")
    with tx(con):
        r = _row(con, rid)
        players = _players(con, rid)
        if v.id not in players:
            raise ApiError("not_found")
        r, s = _ticked(con, r, players)
        if body.get("type") == "leave":  # on any version: whatever the phone shows, it means out
            _leave(con, r, s, v.id, players)
            return {"applied": True, "room": None}
        key = f"{v.id}:{aid}"  # each player's own: another's id never swallows my move
        applied = key in s["acts"]
        if not applied and have == r["version"]:
            t = core.now()
            if body.get("type") == "again":  # one more round: whoever stopped polling is out (the game's checks roll it back)
                away = [x[0] for x in rows(con, "SELECT user_id FROM game_players WHERE room_id = ? AND user_id != ?"
                                           " AND seen_at <= ?", rid, v.id, t - AWAY)]
                con.executemany("DELETE FROM game_players WHERE room_id = ? AND user_id = ?", [(rid, p) for p in away])
                players = [p for p in players if p not in away]
            _game(r).act(s, players, r["host_id"], v.id, body, t)
            s["acts"] = [*s["acts"], key][-ACTS_KEPT:]
            con.execute("UPDATE game_rooms SET state = ?, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                        (json.dumps(s), t, rid, r["version"]))  # the write lock is held: the version is still the one read
            r, applied = {**dict(r), "version": r["version"] + 1}, True
    return {"applied": applied, "room": _view(con, r, s, v.id, players)}


def _leave(con, r, s: dict, uid: int, players: list[int]) -> None:
    """Out of a room still open (later the game goes on without asking them); the host's leaving passes the room to who
    came next, the last one's leaving ends it."""
    if not _game(r).joinable(s):
        raise ApiError("conflict", "started")
    rest = [p for p in players if p != uid]
    if not rest:
        con.execute("DELETE FROM game_rooms WHERE id = ?", (r["id"],))
        return
    con.execute("DELETE FROM game_players WHERE room_id = ? AND user_id = ?", (r["id"], uid))
    con.execute("UPDATE game_rooms SET host_id = ?, version = version + 1, updated_at = ? WHERE id = ?",
                (rest[0] if r["host_id"] == uid else r["host_id"], core.now(), r["id"]))


def gone(con, uid: int) -> None:
    """An account deleted: every room it hosts or plays in goes whole (a game's state names its players)."""
    con.execute("DELETE FROM game_rooms WHERE host_id = ?1 OR id IN (SELECT room_id FROM game_players WHERE user_id = ?1)", (uid,))
    con.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"games:{uid}", f"gmiss:{uid}"))
