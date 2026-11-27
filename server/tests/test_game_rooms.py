"""Game rooms (logic/rooms.py) and Spy (logic/spy.py): joining by code, the version poll, hidden roles, stale and
duplicate actions, deadlines that move the game on when someone looks, the sweep, the cap and account deletion."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from kbtu import db, logic
from test_core import delete_now, env, tma  # noqa: F401  (env: the fixture)

T0 = 1_800_000_000


def _clock(monkeypatch, t: list[int]) -> None:
    monkeypatch.setattr(logic.rooms, "now", lambda: t[0])


def _room(c, n: int = 4):
    """A room opened by player 1, players 2..n joined by its code: (room id, version, headers by player)."""
    hs = {i: tma(900 + i, f"P{i}") for i in range(1, n + 1)}
    r = c.post("/api/rooms", json={"game": "spy"}, headers=hs[1]).json()
    for i in range(2, n + 1):
        j = c.post("/api/rooms/join", json={"code": r["code"]}, headers=hs[i])
        assert j.status_code == 200, j.text
    return r["id"], hs


def _get(c, rid, h, since=None):
    return c.get(f"/api/rooms/{rid}", params={"v": since} if since is not None else {}, headers=h)


def _act(c, rid, h, act, **kw):
    v = kw.pop("at", None)
    if v is None:
        v = _get(c, rid, h).json()["v"]
    r = c.post(f"/api/rooms/{rid}", json={"id": kw.pop("aid", uuid.uuid4().hex), "v": v, "act": act, **kw}, headers=h)
    return r


def test_lobby_join_and_poll(env, monkeypatch):
    """The code joins; the poll answers nothing while the version holds and the new view when it moves."""
    c, _ = env
    t = [T0]; _clock(monkeypatch, t)
    hs = {i: tma(900 + i, f"P{i}") for i in (1, 2, 3)}
    r = c.post("/api/rooms", json={"game": "spy"}, headers=hs[1]).json()
    assert re.fullmatch(r"\d{4}", r["code"]) and r["phase"] == "lobby" and r["me"] == 0 and r["host"] == 0
    assert _get(c, r["id"], hs[1], r["v"]).status_code == 204
    assert _get(c, r["id"], hs[2]).status_code == 404  # not in it: as if there were no room
    assert c.post("/api/rooms/join", json={"code": "12a4"}, headers=hs[2]).status_code == 400
    j = c.post("/api/rooms/join", json={"code": r["code"]}, headers=hs[2]).json()
    assert j["me"] == 1 and [p["seat"] for p in j["players"]] == [0, 1] and j["players"][1]["name"] == "P2"
    assert c.post("/api/rooms/join", json={"code": r["code"]}, headers=hs[2]).json()["v"] == j["v"]  # again: nothing moves
    moved = _get(c, r["id"], hs[1], r["v"])
    assert moved.status_code == 200 and len(moved.json()["players"]) == 2
    assert c.get("/api/rooms", headers=hs[2]).json()["room"]["id"] == r["id"]
    # too few to start; only the host starts
    assert _act(c, r["id"], hs[1], "start").status_code == 409
    c.post("/api/rooms/join", json={"code": r["code"]}, headers=hs[3])
    assert _act(c, r["id"], hs[2], "start").status_code == 403
    assert _act(c, r["id"], hs[1], "start").json()["room"]["phase"] == "talk"
    assert c.post("/api/rooms/join", json={"code": r["code"]}, headers=tma(950, "Late")).status_code == 409  # started


def test_spy_never_sees_the_place(env, monkeypatch):
    """Every view the spy gets, in every phase until the end, holds no location id; the others' cards hold the place."""
    c, _ = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 5)
    _act(c, rid, hs[1], "start")
    con = db.connect(env[1].db_path)
    st = json.loads(con.execute("SELECT state FROM game_rooms WHERE id = ?", (rid,)).fetchone()[0])
    spy, loc = st["spy"], st["loc"]
    h = {p - 1: hs[p] for p in hs}  # by seat
    ids = re.compile('"(?:' + "|".join(logic.spy.LOCATIONS) + ')"')  # any place's id as a JSON string
    seen = []
    for step in ("talk", "vote"):
        for seat, hh in h.items():
            view = _get(c, rid, hh).json()
            assert view["phase"] == step
            if seat == spy:
                assert view["role"] == {"spy": True} and not ids.search(json.dumps(view)), view
                seen.append(view)
            else:
                assert view["role"] == {"spy": False, "loc": loc}
        if step == "talk":
            _act(c, rid, h[(spy + 1) % 5], "vote_now")
    # the town catches the spy: the guess phase still hides the place from them
    for seat, hh in h.items():
        _act(c, rid, hh, "vote", seat=spy if seat != spy else (spy + 1) % 5)
    view = _get(c, rid, h[spy]).json()
    assert view["phase"] == "guess" and view["accused"] == spy and not ids.search(json.dumps(view))
    wrong = next(x for x in logic.spy.LOCATIONS if x != loc)
    assert _act(c, rid, h[(spy + 1) % 5], "guess", loc=loc).json()["applied"] is False  # only the spy guesses
    end = _act(c, rid, h[spy], "guess", loc=wrong).json()["room"]
    assert end["phase"] == "over" and end["result"]["winner"] == "town" and end["result"]["why"] == "missed"
    assert end["result"]["loc"] == loc and end["result"]["spy"] == spy and end["result"]["guess"] == wrong


def test_stale_and_duplicate_actions(env, monkeypatch):
    """A retried action (the same id) changes nothing twice; an action made before its phase ended changes nothing;
    votes made at the same version all count (the phase, not the version, makes them stale)."""
    c, _ = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 4)
    v0 = _get(c, rid, hs[1]).json()["v"]
    first = _act(c, rid, hs[1], "minutes", minutes=3, aid="a" * 16, at=v0).json()
    assert first["applied"] and first["room"]["minutes"] == 3
    again = _act(c, rid, hs[1], "minutes", minutes=3, aid="a" * 16, at=v0).json()
    assert again["applied"] and again["room"]["v"] == first["room"]["v"]  # the retry: done already, nothing new
    start = _act(c, rid, hs[1], "start").json()["room"]
    # a tap from the lobby's version, after the round began: stale
    assert _act(c, rid, hs[2], "vote_now", at=v0).json()["applied"] is False
    assert _act(c, rid, hs[2], "vote_now", at=start["v"] + 50).json()["applied"] is False  # a version never seen
    vote = _act(c, rid, hs[2], "vote_now", at=start["v"]).json()["room"]
    assert vote["phase"] == "vote"
    # everyone votes from the same version: all four count
    spy = json.loads(db.connect(env[1].db_path).execute("SELECT state FROM game_rooms WHERE id = ?", (rid,)).fetchone()[0])["spy"]
    innocent = next(s for s in range(4) if s != spy)
    for i in range(1, 5):
        seat = i - 1
        r = _act(c, rid, hs[i], "vote", seat=innocent if seat != innocent else spy, at=vote["v"]).json()
        assert r["applied"], r
    over = _get(c, rid, hs[1]).json()
    assert over["phase"] == "over" and over["result"]["why"] == "wrong" and over["result"]["winner"] == "spy"
    # a vote arriving after the end: stale, nothing moves
    assert _act(c, rid, hs[1], "vote", seat=1, at=vote["v"]).json()["applied"] is False
    assert _act(c, rid, hs[1], "vote", seat=0, at=over["v"]).status_code == 200  # wrong phase: a no-op too
    assert c.post(f"/api/rooms/{rid}", json={"id": "x", "v": over["v"], "act": "again"}, headers=hs[1]).status_code == 400  # id too short


def test_deadlines_move_on_when_read(env, monkeypatch):
    """No timer: the first read after a deadline moves the room on, each phase from where the last one ended."""
    c, _ = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 3)
    _act(c, rid, hs[1], "minutes", minutes=3)
    talk = _act(c, rid, hs[1], "start").json()["room"]
    assert talk["deadline"] == T0 + 180 and talk["now"] == T0
    t[0] = T0 + 179
    assert _get(c, rid, hs[2], talk["v"]).status_code == 204
    t[0] = T0 + 181
    vote = _get(c, rid, hs[2], talk["v"]).json()
    assert vote["phase"] == "vote" and vote["deadline"] == T0 + 180 + logic.spy.VOTE_S
    # nobody looks for ten minutes: the vote closed (no votes, a tie: the spy wins) at its own deadline
    t[0] = T0 + 900
    over = _get(c, rid, hs[3]).json()
    assert over["phase"] == "over" and over["result"] == {**over["result"], "winner": "spy", "why": "tie"}
    again = _act(c, rid, hs[1], "again").json()["room"]
    assert again["phase"] == "lobby" and again["minutes"] == 3 and "result" not in again


def test_leaving_and_the_sweep(env, monkeypatch):
    """The spy leaving ends the round; a room nobody looks at closes; within hours its state and players go, a day on
    the row itself. The daily cap counts the rooms opened, gone or not."""
    c, cfg = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 3)
    _act(c, rid, hs[1], "start")
    con = db.connect(cfg.db_path)
    spy = json.loads(con.execute("SELECT state FROM game_rooms WHERE id = ?", (rid,)).fetchone()[0])["spy"]
    assert c.delete(f"/api/rooms/{rid}/me", headers=hs[spy + 1]).status_code == 204
    other = hs[(spy + 1) % 3 + 1]
    assert _get(c, rid, other).json()["result"]["why"] == "fled"
    t[0] = T0 + logic.rooms.IDLE + 60
    logic.rooms.sweep(con)
    assert _get(c, rid, other).status_code == 404  # closed: nobody looked for an hour
    assert con.execute("SELECT COUNT(*) FROM game_players WHERE room_id = ?", (rid,)).fetchone()[0] == 2
    t[0] = T0 + logic.rooms.IDLE + 60 + 3601  # an hour after it closed
    logic.rooms.sweep(con)
    assert con.execute("SELECT state, code FROM game_rooms WHERE id = ?", (rid,)).fetchone() == ("{}", None)
    assert not con.execute("SELECT 1 FROM game_players WHERE room_id = ?", (rid,)).fetchone()
    monkeypatch.setattr(logic.rooms, "A_DAY", 2)
    c.post("/api/rooms", json={"game": "spy"}, headers=hs[1])
    assert c.post("/api/rooms", json={"game": "spy"}, headers=hs[1]).status_code == 429  # the stripped room still counts
    t[0] = T0 + 86401
    logic.rooms.sweep(con)
    assert not con.execute("SELECT 1 FROM game_rooms WHERE id = ?", (rid,)).fetchone()


def test_one_room_at_a_time_and_deletion(env, monkeypatch):
    """Opening or joining another room leaves the one I was in; deleting my account takes my seats and my rooms."""
    c, cfg = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 3)
    other = c.post("/api/rooms", json={"game": "spy"}, headers=hs[2]).json()
    assert [p["seat"] for p in _get(c, rid, hs[1]).json()["players"]] == [0, 2]
    assert c.get("/api/rooms", headers=hs[2]).json()["room"]["id"] == other["id"]
    delete_now(c, cfg, hs[1])
    con = db.connect(cfg.db_path)
    assert not con.execute("SELECT 1 FROM game_rooms WHERE id = ?", (rid,)).fetchone()
    assert ("game_players", "user_id") in logic.account._DEL_GONE and ("game_rooms", "created_by") in logic.account._DEL_GONE


def test_share_card(env, monkeypatch):
    """The room's card: our bot's words with the code and a button straight into the room; only for those in it."""
    c, cfg = env
    t = [T0]; _clock(monkeypatch, t)
    rid, hs = _room(c, 1)
    code = _get(c, rid, hs[1]).json()["code"]
    card = c.post("/api/share", json={"kind": "gr", "code": code, "link": True}, headers=hs[1]).json()
    assert card["link"].endswith(f"?startapp=g_{code}") and code in card["text"] and "P1" in card["text"]
    assert c.post("/api/share", json={"kind": "gr", "code": code, "link": True}, headers=tma(990, "X")).json()["error"] == "closed"


def test_every_place_has_its_name():
    """Each location id the server deals has its name in all three languages of the web."""
    i18n = Path(__file__).parents[2] / "web/src/lib/i18n"
    for lang in ("ru", "kk", "en"):
        text = (i18n / f"{lang}.ts").read_text()
        missing = [x for x in logic.spy.LOCATIONS if f"'spy.loc.{x}'" not in text]
        assert not missing, (lang, missing)
