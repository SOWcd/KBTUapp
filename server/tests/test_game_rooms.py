"""Game rooms (logic/rooms.py) and Spy (logic/spy.py): in by a code, one row per room with a version, moves that land
only on the version they were made on (a double tap or an old screen changes nothing), deadlines resolved by whoever
reads next, and the spy's every answer without the place until the reveal."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from kbtu import db, logic
from test_core import env, set_clock, tma  # noqa: F401  (env: the fixture)

HOST, P2, P3, P4 = 50, 51, 52, 53


def _room(c, tgs=(HOST, P2, P3)):
    r = c.post("/api/rooms", headers=tma(tgs[0]), json={"game": "spy"}).json()
    for tg in tgs[1:]:
        r = c.post("/api/rooms/join", headers=tma(tg), json={"code": r["code"]}).json()
    return r


def _get(c, tg, rid, v=None):
    return c.get(f"/api/rooms/{rid}" + (f"?v={v}" if v is not None else ""), headers=tma(tg))


def _act(c, tg, room, aid, **body):
    return c.post(f"/api/rooms/{room['id']}", headers=tma(tg), json={"id": aid, "v": room["v"], **body})


def _state(cfg, rid):
    con = db.connect(cfg.db_path)
    try:
        return json.loads(con.execute("SELECT state FROM game_rooms WHERE id = ?", (rid,)).fetchone()[0])
    finally:
        con.close()


def _start(c, room, minutes=5, tg=HOST):
    r = _act(c, tg, room, "start-0001", type="start", minutes=minutes)
    assert r.status_code == 200 and r.json()["applied"], r.text
    return r.json()["room"]


def _to_vote(c, room, tgs=(HOST, P2)):
    """More than half of a room of three call the vote: the talk is over."""
    for i, tg in enumerate(tgs):
        room = _act(c, tg, _get(c, tg, room["id"]).json(), f"call-vote-{i}", type="vote_now").json()["room"]
    assert room["phase"] == "vote"
    return _get(c, tgs[0], room["id"]).json()


def test_lobby_join_and_start(env):
    c, cfg = env
    r = c.post("/api/rooms", headers=tma(HOST), json={"game": "spy"}).json()
    assert re.fullmatch(r"\d{4}", r["code"]) and r["phase"] == "lobby" and len(r["players"]) == 1 and not r["live"]
    assert c.post("/api/rooms", headers=tma(HOST), json={"game": "poker"}).status_code == 400
    two = c.post("/api/rooms/join", headers=tma(P2), json={"code": r["code"]}).json()
    assert len(two["players"]) == 2 and two["host"] == r["me"]
    assert _act(c, HOST, two, "start-0001", type="start").json()["message"] == "players"  # three at least
    assert _act(c, P2, two, "start-0002", type="start").status_code == 403  # the host starts
    three = c.post("/api/rooms/join", headers=tma(P3), json={"code": r["code"]}).json()
    assert _get(c, P3, r["id"], three["v"]).status_code == 204  # nothing new: nothing sent
    assert _get(c, P4, r["id"]).status_code == 404  # not in it
    assert c.post("/api/rooms/join", headers=tma(P4), json={"code": "abcd"}).status_code == 404
    room = _start(c, three)
    assert room["phase"] == "play" and room["live"] and room["deadline"] - room["now"] in (299, 300)
    late = c.post("/api/rooms/join", headers=tma(P4), json={"code": r["code"]})
    assert late.status_code == 409 and late.json()["message"] == "started"
    assert c.post("/api/rooms/join", headers=tma(P2), json={"code": r["code"]}).json()["phase"] == "play"  # back in, by the code
    assert _act(c, P2, room, "leave-0001", type="leave").status_code == 409  # no leaving a round under way


def test_spy_never_gets_the_place(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(logic.spy, "LOCATIONS", ("submarine", "space_station"))
    room = _start(c, _room(c, (HOST, P2, P3, P4)))
    s = _state(cfg, room["id"])
    tg_of = {room["me"]: HOST}
    for tg in (P2, P3, P4):
        tg_of[_get(c, tg, room["id"]).json()["me"]] = tg
    spy, others = tg_of[s["spy"]], [tg for uid, tg in tg_of.items() if uid != s["spy"]]

    def check(phase):
        mine = _get(c, spy, room["id"]).json()
        assert mine["phase"] == phase and mine["role"] == "spy" and "location" not in mine and s["loc"] not in json.dumps(mine)
        for tg in others:
            theirs = _get(c, tg, room["id"]).json()
            assert theirs["role"] == "local" and theirs["location"] == s["loc"] and "result" not in theirs
        return mine

    check("play")
    room = _to_vote(c, room, others)  # any three of the four: the spy's call isn't needed, nor the host's
    check("vote")
    # all three locals vote for the spy and confirm: caught, and the spy has a guess
    for i, tg in enumerate(others):
        room = _get(c, tg, room["id"]).json()
        assert _act(c, tg, room, f"conf-000{i}", type="confirm").json()["message"] == "vote"  # nothing picked yet
        room = _act(c, tg, room, f"vote-000{i}", type="vote", target=s["spy"]).json()["room"]
        assert room["myVote"] == s["spy"] and room["me"] not in room["voted"]  # a pick: mine alone until confirmed
        room = _act(c, tg, room, f"sure-000{i}", type="confirm").json()["room"]
        assert room["me"] in room["voted"]
        assert _act(c, tg, room, f"late-000{i}", type="vote", target=s["spy"]).json()["message"] == "confirmed"  # final
        assert _act(c, tg, room, f"twice-00{i}", type="confirm").json()["message"] == "confirmed"
    room = _get(c, spy, room["id"]).json()
    assert room["phase"] == "vote" and len(room["voted"]) == 3  # everyone confirms before the count, the spy too
    assert _act(c, spy, room, "vote-spy-01", type="vote", target=room["me"]).status_code == 400  # not for oneself
    target, other = [p["id"] for p in room["players"] if p["id"] != room["me"]][:2]
    room = _act(c, spy, room, "vote-spy-02", type="vote", target=other).json()["room"]
    room = _act(c, spy, room, "vote-spy-03", type="vote", target=target).json()["room"]  # a change of mind
    assert room["phase"] == "vote" and room["myVote"] == target
    assert _act(c, spy, room, "sure-spy-01", type="confirm").json()["applied"]
    mine = check("guess")
    assert mine["accused"] == s["spy"] and 0 < mine["deadline"] - mine["now"] <= logic.spy.GUESS_S
    wrong = next(x for x in logic.spy.LOCATIONS if x != s["loc"])
    assert _act(c, others[0], mine, "guess-0001", type="guess", location=wrong).json()["message"] == "phase"  # the spy's alone
    end = _act(c, spy, mine, "guess-0002", type="guess", location=wrong).json()["room"]
    assert end["phase"] == "reveal" and end["location"] == s["loc"] and not end["live"]
    assert end["result"] == {"spy": s["spy"], "accused": s["spy"], "guess": wrong, "winner": "locals", "why": "wrong_guess",
                             "votes": end["result"]["votes"]} and len(end["result"]["votes"]) == 4


def test_stale_and_duplicate_moves(env):
    c, cfg = env
    room = _start(c, _room(c))
    again = _act(c, HOST, {**room, "v": room["v"] - 1}, "start-0001", type="start", minutes=5).json()
    assert again["applied"] and again["room"]["v"] == room["v"]  # the same id: once, the answer as the first
    s = _state(cfg, room["id"])
    v = room["v"]
    stale = _act(c, HOST, {**room, "v": v - 1}, "vote-now-02", type="vote_now").json()
    assert not stale["applied"] and stale["room"]["phase"] == "play" and stale["room"]["v"] == v  # an old screen: nothing
    moved = _act(c, HOST, room, "vote-now-03", type="vote_now").json()
    assert moved["applied"] and moved["room"]["phase"] == "play" and moved["room"]["v"] == v + 1
    assert moved["room"]["calls"] == [room["me"]]  # one of three: a call, not the vote yet
    dup = _act(c, HOST, room, "vote-now-03", type="vote_now").json()
    assert dup["applied"] and dup["room"]["v"] == v + 1  # sent twice: moved once
    assert _act(c, HOST, moved["room"], "vote-now-04", type="vote_now").json()["message"] == "called"  # one call each
    assert _get(c, HOST, room["id"]).json()["v"] == v + 1  # and a refused one moves nothing
    p2 = _act(c, P2, _get(c, P2, room["id"]).json(), "vote-now-05", type="vote_now").json()["room"]
    assert p2["phase"] == "vote" and "calls" not in p2  # the second of three, not the host: more than half
    assert _state(cfg, room["id"])["spy"] == s["spy"]
    assert c.post(f"/api/rooms/{room['id']}", headers=tma(HOST), json={"type": "vote_now"}).status_code == 400  # no id, no version


def test_action_ids_are_each_players_own(env):
    """One player's action id can't swallow another's move (applied: true for a move that never landed)."""
    c, cfg = env
    room = _to_vote(c, _act(c, HOST, _start(c, _room(c)), "same-id-01", type="vote_now").json()["room"], (P2,))
    p2 = _get(c, P2, room["id"]).json()
    target = next(p["id"] for p in p2["players"] if p["id"] != p2["me"])
    assert _act(c, P2, p2, "same-id-01", type="vote", target=target).json()["applied"]
    assert _state(cfg, room["id"])["votes"] == {str(p2["me"]): target}


def test_vote_target_is_a_person_id(env):
    c, cfg = env
    room = _to_vote(c, _start(c, _room(c)))
    other = next(p["id"] for p in room["players"] if p["id"] != room["me"])
    for bad in (float(other), str(other)):
        assert _act(c, HOST, room, "vote-0001", type="vote", target=bad).status_code == 400
    assert _state(cfg, room["id"])["votes"] == {}


def test_deadlines_resolve_on_the_next_read(env, monkeypatch):
    c, cfg = env
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    room = _start(c, _room(c), minutes=1)
    set_clock(monkeypatch, lambda: t0 + 60)
    r = _get(c, P2, room["id"], room["v"]).json()  # the timer ran out while nobody looked: the vote, from its own moment
    assert r["phase"] == "vote" and r["deadline"] == t0 + 60 + logic.spy.VOTE_S and r["v"] == room["v"] + 1
    set_clock(monkeypatch, lambda: t0 + 60 + logic.spy.VOTE_S + 1)
    end = _get(c, P3, room["id"]).json()  # nobody voted: no majority, the spy wins
    assert end["phase"] == "reveal" and end["result"]["winner"] == "spy" and end["result"]["why"] == "missed"
    # picks nobody confirmed count when the vote's time is up
    set_clock(monkeypatch, lambda: t0)
    room = _start(c, _room(c, (70, 71, 72)), tg=70)
    s = _state(cfg, room["id"])
    room = _to_vote(c, room, (70, 71))
    for i, tg in enumerate((70, 71, 72)):
        mine = _get(c, tg, room["id"]).json()
        if mine["me"] != s["spy"]:
            assert _act(c, tg, mine, f"pick-000{i}", type="vote", target=s["spy"]).json()["room"]["phase"] == "vote"
    set_clock(monkeypatch, lambda: t0 + logic.spy.VOTE_S)
    assert _get(c, 70, room["id"]).json()["phase"] == "guess"  # two of three on the spy, unconfirmed: caught
    # a caught spy who says nothing in time: the locals win
    set_clock(monkeypatch, lambda: t0)
    room = _start(c, _room(c, (60, 61, 62)), tg=60)
    s = _state(cfg, room["id"])
    room = _to_vote(c, room, (60, 61))
    tg_of = {room["me"]: 60, **{_get(c, tg, room["id"]).json()["me"]: tg for tg in (61, 62)}}
    for i, (uid, tg) in enumerate(tg_of.items()):
        room = _get(c, tg, room["id"]).json()
        target = s["spy"] if uid != s["spy"] else next(x for x in tg_of if x != uid)
        room = _act(c, tg, room, f"vote-000{i}", type="vote", target=target).json()["room"]
        _act(c, tg, room, f"sure-000{i}", type="confirm")
    assert _get(c, 60, room["id"]).json()["phase"] == "guess"
    set_clock(monkeypatch, lambda: t0 + logic.spy.GUESS_S)
    assert _get(c, 61, room["id"]).json()["result"]["why"] == "no_guess"
    # rooms unchanged for hours are gone
    set_clock(monkeypatch, lambda: t0 + logic.rooms.KEEP + logic.spy.GUESS_S + 1)
    assert _get(c, 61, room["id"]).status_code == 404


def test_spy_guesses_during_the_talk(env):
    c, cfg = env
    room = _start(c, _room(c))
    s = _state(cfg, room["id"])
    tg = next(tg for tg in (HOST, P2, P3) if _get(c, tg, room["id"]).json()["me"] == s["spy"])
    room = _get(c, tg, room["id"]).json()
    end = _act(c, tg, room, "guess-0001", type="guess", location=s["loc"]).json()["room"]
    assert end["phase"] == "reveal" and end["result"]["winner"] == "spy" and end["result"]["why"] == "guessed"


def test_one_more_round_in_the_same_room(env, monkeypatch):
    """After the reveal the host plays again: the same room and code, those still there, a new place; not a new room."""
    c, cfg = env
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    monkeypatch.setattr(logic.rooms, "A_DAY", 1)
    monkeypatch.setattr(logic.spy, "LOCATIONS", ("submarine", "space_station"))
    room = _start(c, _room(c, (HOST, P2, P3, P4)))
    first = _state(cfg, room["id"])
    assert _act(c, HOST, room, "again-0000", type="again").json()["message"] == "phase"  # not before the reveal
    assert _act(c, P2, _get(c, P2, room["id"]).json(), "call-0001", type="vote_now").json()["room"]["calls"]  # one of four
    set_clock(monkeypatch, lambda: t0 + 300 + logic.spy.VOTE_S)  # nobody voted: the spy wins
    for tg in (HOST, P2, P3):  # P4 put the phone away a while ago
        end = _get(c, tg, room["id"]).json()
    assert end["phase"] == "reveal"
    assert _act(c, P2, end, "again-0001", type="again").status_code == 403  # the host's move
    assert _act(c, HOST, end, "again-0002", type="again", minutes=99).status_code == 400
    assert len(_get(c, HOST, room["id"]).json()["players"]) == 4  # a refused move drops nobody
    lobby = _act(c, HOST, end, "again-0003", type="again").json()
    assert lobby["applied"] and lobby["room"]["v"] == end["v"] + 1
    r = lobby["room"]
    assert (r["id"], r["code"], r["host"], r["phase"], r["deadline"], r["live"]) == (room["id"], room["code"], room["host"], "lobby", None, False)
    assert len(r["players"]) == 3 and not {"role", "location", "result", "first"} & r.keys()
    assert _get(c, P4, room["id"]).status_code == 404  # away: out
    assert _act(c, HOST, end, "again-0003", type="again").json()["room"]["v"] == r["v"]  # a double tap: once
    assert _act(c, HOST, end, "again-0004", type="again").json()["applied"] is False  # an old screen: nothing
    assert c.post("/api/rooms/join", headers=tma(P4), json={"code": room["code"]}).json()["phase"] == "lobby"  # in again
    # the room keeps its action ids across rounds: the first round's start-0001 would be a double tap
    nxt = _act(c, HOST, _get(c, HOST, room["id"]).json(), "start-0002", type="start", minutes=5).json()["room"]
    assert nxt["phase"] == "play" and _state(cfg, room["id"])["loc"] != first["loc"]  # never the same place twice in a row
    assert nxt["calls"] == [] and _state(cfg, room["id"])["sure"] == []  # the last round's calls are not this one's
    # straight into the next round with minutes, and no room counted against the day's cap (A_DAY 1, used)
    set_clock(monkeypatch, lambda: t0 + 2 * (300 + logic.spy.VOTE_S))
    for tg in (HOST, P2, P3, P4):
        end = _get(c, tg, room["id"]).json()
    played = _state(cfg, room["id"])["loc"]
    again = _act(c, HOST, end, "again-0005", type="again", minutes=3).json()["room"]
    assert again["phase"] == "play" and again["deadline"] - again["now"] == 180 and len(again["players"]) == 4
    assert _state(cfg, room["id"])["loc"] != played and "last" not in again
    assert c.post("/api/rooms", headers=tma(HOST), json={"game": "spy"}).status_code == 429  # the one room of the day


def test_limits_leaving_and_account_deletion(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(logic.rooms, "A_DAY", 2)
    _room(c)
    lobby = _room(c, (HOST, P2))
    r = c.post("/api/rooms", headers=tma(HOST), json={"game": "spy"})
    assert r.status_code == 429 and r.json()["message"] == "rooms"
    monkeypatch.setattr(logic.rooms, "MISSES", 2)
    for code, status in (("abcd", 404), ("12", 404), ("x", 429)):
        assert c.post("/api/rooms/join", headers=tma(P4), json={"code": code}).status_code == status
    # the host leaves the lobby: the room passes on; the last one out ends it
    left = _act(c, HOST, lobby, "leave-0001", type="leave").json()
    assert left == {"applied": True, "room": None} and _get(c, HOST, lobby["id"]).status_code == 404
    mine = _get(c, P2, lobby["id"]).json()
    assert mine["host"] == mine["me"] and len(mine["players"]) == 1
    _act(c, P2, mine, "leave-0002", type="leave")
    assert _get(c, P2, lobby["id"]).status_code == 404
    con = db.connect(cfg.db_path)
    uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (P2,)).fetchone()[0]
    logic.rooms.gone(con, uid)  # account.delete_me's step: every room P2 is in goes whole
    assert con.execute("SELECT COUNT(*) FROM game_rooms").fetchone()[0] == 0
    assert ("game_players", "user_id") in logic.account._DEL_GONE and ("game_rooms", "host_id") in logic.account._DEL_GONE


def test_postman_round_purges_after_three_hours(env):
    c, cfg = env
    r = _room(c)
    con = db.connect(cfg.db_path)
    logic.rooms.purge_round(con)  # fresh: kept
    assert con.execute("SELECT COUNT(*) FROM game_rooms").fetchone()[0] == 1
    con.execute("UPDATE game_rooms SET updated_at = updated_at - ? WHERE id = ?", (logic.rooms.KEEP, r["id"]))
    logic.rooms.purge_round(con)
    assert con.execute("SELECT COUNT(*) FROM game_rooms").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM game_players").fetchone()[0] == 0  # with its players


def test_locations_match_the_app():
    """Every place the server deals has its id in the app's list and a name in each language."""
    web = Path(__file__).parents[2] / "web/src/lib"
    listed = re.findall(r"'([a-z_]+)'", (web / "games/spy.ts").read_text().split("SPY_LOCATIONS", 1)[1].split("]", 1)[0])
    assert tuple(listed) == logic.spy.LOCATIONS
    words = (web / "i18n/games.ts").read_text()  # ru, kk, en in one file
    assert all(words.count(f"'spy.loc.{x}':") == 3 for x in listed)
