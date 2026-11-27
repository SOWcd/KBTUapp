"""The campus map: its graph, places and flaws."""
from __future__ import annotations

import time

import pytest

from kbtu import config, db, logic
from test_core import _board_on, env, login, tma  # noqa: F401  (env: the fixture)


def test_map_graph(env):
    """Indoor routes' graph: anyone reads Claude's draft; nobody saves it (the editor is off)."""
    c, _ = env
    login(c, 20, "ali")
    g = c.get("/api/map/graph", headers=tma(20)).json()
    assert g["n"] and g["e"] and g["ver"] == 0
    assert c.put("/api/map/graph", headers=tma(20), json=g).status_code == 405


def test_map_flaws(env):
    """A long press on the map reports a flaw (the app's team ten a day; students three, with the forum's switch); the
    admin lists and fixes them."""
    c, cfg = env
    ann, boss = login(c, 1, "ann"), login(c, 4, "boss")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    login(c, 2, "bob")
    mine = {"ver": "kbtu", "floor": 1, "u": 0.4, "v": 0.3, "body": "a student"}
    assert c.post("/api/map/flaws", headers=tma(2), json=mine).status_code == 404               # BOARD off
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (ann["id"],))               # the team marks, for now
    flaw = {"ver": "kbtu", "floor": 1, "u": 0.42, "v": 0.31, "px": 540.0, "py": 440.0, "body": "the WC door doesn't exist"}
    assert c.post("/api/map/flaws", headers=tma(9), json=flaw).status_code == 401                 # a guest
    for bad in ({**flaw, "floor": 7}, {**flaw, "u": 2}, {**flaw, "ver": "x"}, {**flaw, "body": "x"}):
        assert c.post("/api/map/flaws", headers=tma(1), json=bad).status_code == 400
    nan = '{"ver": "kbtu", "floor": 1, "u": 0.4, "v": 0.3, "px": Infinity, "py": NaN, "body": "no number"}'
    assert c.post("/api/map/flaws", headers={**tma(1), "content-type": "application/json"}, content=nan).status_code == 400
    assert c.post("/api/map/flaws", headers=tma(1), json=flaw).status_code == 204
    assert c.get("/api/map/flaws", headers=tma(1)).status_code == 403
    got = c.get("/api/map/flaws", headers=tma(4)).json()
    assert [(x["floor"], x["body"], x["done"]) for x in got] == [(1, "the WC door doesn't exist", None)]
    assert [x["body"] for x in c.get("/api/map/flaws/mine", headers=tma(1)).json()] == ["the WC door doesn't exist"]
    assert c.get("/api/map/flaws/mine", headers=tma(4)).json() == []                               # never another's, the admin's either
    c.post(f"/api/map/flaws/{got[0]['id']}/done", headers=tma(4))
    assert c.get("/api/map/flaws", headers=tma(4)).json()[0]["done"]
    assert c.get("/api/map/flaws/mine", headers=tma(1)).json() == []                               # fixed: off the map
    c.post("/api/map/flaws", headers=tma(1), json={**flaw, "body": "\x1b]0;title\x07the\n\u202estair"})   # the admin's terminal
    assert c.get("/api/map/flaws", headers=tma(4)).json()[0]["body"] == "]0;title the stair"
    for _ in range(8):
        assert c.post("/api/map/flaws", headers=tma(1), json=flaw).status_code == 204
    assert c.post("/api/map/flaws", headers=tma(1), json=flaw).status_code == 429
    _board_on(c, cfg)
    assert [c.post("/api/map/flaws", headers=tma(2), json=mine).status_code for _ in range(4)] == [204, 204, 204, 429]
    con.close()


def test_campus_places(env, monkeypatch, capsys):
    """Oct 30: the assistant's campus facts are a table, seeded from the list that was in the code: the brief reads it in
    the student's language (else English), a button opens only a room from it; an edit (by hand since the editor routes
    went, Nov 14) is in the next brief; stale = never checked or 180+ days ago; `kbtu.admin places` prints it for the owner."""
    from kbtu import admin
    from kbtu.logic import assistant
    c, cfg = env
    ann, mod = login(c, 1, "ann"), login(c, 2, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 2")
    v = logic.Viewer(ann["id"], "user", True)
    places = lambda: assistant.places(con, logic.Viewer(mod["id"], "moderator", True))  # noqa: E731
    got = places()                                                                             # the old list, never checked
    by = {p["code"]: p for p in got}
    assert len(got) == 20 and all(p["stale"] and p["verifiedAt"] is None and p["nameRu"] is None and p["updatedBy"] is None for p in got)
    assert (by["library"]["room"], by["canteen"]["location"], by["site"]["kind"], by["site"]["school"]) == ("158", "the basement, floor 0", "dean", "SITE")
    text, rooms, *_ = assistant.brief(con, v, "ru")
    assert "Library: room 158" in text and "Canteen: the basement, floor 0" in text and "school SITE (School of IT and Engineering)" in text
    assert "KMA (Kazakhstan Maritime Academy): room 255. Other schools' dean's offices: unknown." in text and {"158", "400a", "180", "1"} <= rooms
    lib = by["library"]["id"]
    with pytest.raises(logic.ApiError):
        assistant.places(con, v)                                                                # a student, not the app's staff
    # moved, named in Russian, what students call it, checked on campus: the next brief has it, the old room opens nothing
    lib_ru = "\u0411\u0438\u0431\u043b\u0438\u043e\u0442\u0435\u043a\u0430"
    con.execute("UPDATE campus_places SET room = '160a', name_ru = ?, aliases = 'lib, books', verified_at = ?, updated_by = ? WHERE id = ?",
                (lib_ru, int(time.time()), mod["id"], lib))
    p = next(x for x in places() if x["id"] == lib)
    assert (p["room"], p["aliases"], p["stale"], p["updatedBy"]["id"], p["code"]) == ("160a", "lib, books", False, mod["id"], "library")
    text, rooms, *_ = assistant.brief(con, v, "ru")
    assert f"{lib_ru} (also: lib, books): room 160a" in text and "160a" in rooms and "158" not in rooms
    assert "Library (also: lib, books): room 160a" in assistant.brief(con, v, "kk")[0]           # no Kazakh name: the English one
    assert assistant.answer('{"text": "160a", "actions": [{"type": "map", "room": "160A"}, {"type": "map", "room": "158"}]}', {"map": rooms})["actions"] == [
        {"type": "map", "room": "160a"}]
    con.execute("UPDATE campus_places SET verified_at = ? WHERE id = ?", (int(time.time()) - 181 * 86400, lib))
    assert next(x for x in places() if x["id"] == lib)["stale"]                                # checked too long ago
    # a dean's office the old list didn't know: the student's school is named from it
    con.execute("""INSERT INTO campus_places (kind, code, name_en, room, school, verified_at, updated_by, updated_at)
        VALUES ('dean', 'business-school', 'Business School', '312', 'BS', NULL, ?, 0)""", (mod["id"],))
    con.execute("UPDATE students SET school = 'bs' WHERE user_id = ?", (ann["id"],))
    text = assistant.brief(con, v)[0]
    assert "school bs (Business School)" in text and "BS (Business School): room 312" in text
    con.execute("""INSERT INTO campus_places (kind, code, name_en, location, verified_at, updated_by, updated_at)
        VALUES ('place', 'gym', 'Gym', 'the sports block', ?, ?, 0)""", (int(time.time()), mod["id"]))
    monkeypatch.setattr(config, "load", lambda: cfg)
    capsys.readouterr()
    admin.main(["places"])
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "22 facts, 21 stale" and any(x.startswith("STALE  library") and "room 160a" in x and lib_ru in x for x in out)
    assert any(x.startswith("       gym") and "never" not in x for x in out)                            # checked: no mark
    con.close()
