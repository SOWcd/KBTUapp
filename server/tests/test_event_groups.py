"""Group-stage routes use the event's visibility and team organizer rights."""
from itertools import combinations

from test_core import tma
from test_event_teams import TEAMS, _event, _go, _mine, _people, club, env  # noqa: F401  (fixtures)

ORGANIZER = tma(20)
VIEWER = tma(10)


def _draw(c, path, size=5):
    res = c.post(path, headers=ORGANIZER, json={"size": size, "advance": 2})
    assert res.status_code == 200, res.text
    return res.json()["groups"]


def _seed(club, names):
    c, con = club
    eid = _event(c, **TEAMS)
    con.executemany("INSERT INTO event_teams (event_id, name, name_key, token, created_at) VALUES (?, ?, ?, ?, 0)",
                    ((eid, name, name.lower(), f"{eid}-{name}") for name in names))
    tids = dict(con.execute("SELECT name, id FROM event_teams WHERE event_id = ?", (eid,)).fetchall())
    return c, eid, f"/api/events/{eid}/groups", tids


def _teams(group):
    return {row["team_id"] for row in group["standings"]}


def _assert_fixtures(group):
    pairs = list(combinations(sorted(_teams(group)), 2))
    assert sorted((m["home"], m["away"]) for m in group["matches"]) == pairs


def test_group_draw_balances_and_redraws(club):
    c, _ = club
    eid = _event(c, **TEAMS)
    tids = set()
    for i, tg in enumerate(_people(c, 11)):
        assert _go(c, eid, tg, {"create": f"Team {i + 1}"}).status_code == 200
        tids.add(_mine(c, eid, tg)["id"])
    path = f"/api/events/{eid}/groups"
    groups = _draw(c, path)
    assert [g["name"] for g in groups] == ["A", "B", "C"]
    assert [len(_teams(g)) for g in groups] == [4, 4, 3]
    assert set.union(*(_teams(g) for g in groups)) == tids
    for group in groups:
        _assert_fixtures(group)
        assert [row["advance"] for row in group["standings"]] == [True, True] + [False] * (len(_teams(group)) - 2)
    assert c.get(path, headers=VIEWER).json() == {"groups": groups}

    old = groups[0]["matches"][0]["id"]
    _draw(c, path)
    assert c.put(f"/api/matches/{old}", headers=ORGANIZER, json={"home_score": 1, "away_score": 0}).status_code == 404


def test_group_standings_head_to_head_and_stats(club):
    c, _, path, tids = _seed(club, ["Alpha", "Bravo", "Charlie", "Delta", "Echo"])
    [group] = _draw(c, path)
    matches = {(m["home"], m["away"]): m["id"] for m in group["matches"]}
    results = [("Alpha", "Bravo", 1, 0), ("Alpha", "Charlie", 0, 0), ("Bravo", "Charlie", 1, 1),
               ("Bravo", "Delta", 8, 0), ("Charlie", "Delta", 0, 0), ("Charlie", "Echo", 0, 0)]
    for home, away, a, b in results:
        mid = matches[tids[home], tids[away]]
        res = c.put(f"/api/matches/{mid}", headers=ORGANIZER, json={"home_score": a, "away_score": b})
        assert res.status_code == 200, res.text
        assert res.json()["played_at"] and "updated_by" not in res.json()

    [group] = c.get(path, headers=VIEWER).json()["groups"]
    table = group["standings"]
    # The tied leaders have 4, 2 and 1 points against one another. Echo then beats Delta on goal difference.
    assert [(t["name"], t["points"], t["diff"], t["advance"]) for t in table] == [
        ("Alpha", 4, 1, True), ("Charlie", 4, 0, True), ("Bravo", 4, 7, False),
        ("Echo", 1, 0, False), ("Delta", 1, -8, False)]
    bravo = table[2]
    assert [bravo[k] for k in ("played", "won", "drawn", "lost", "scored", "conceded")] == [3, 1, 1, 1, 9, 2]


def test_group_standings_scored_then_name(club):
    c, _, path, tids = _seed(club, ["Zulu", "Bravo", "Alpha"])
    [group] = _draw(c, path)
    assert [t["name"] for t in group["standings"]] == ["Alpha", "Bravo", "Zulu"]
    for m in group["matches"]:
        goals = int(tids["Zulu"] in (m["home"], m["away"]))
        res = c.put(f"/api/matches/{m['id']}", headers=ORGANIZER, json={"home_score": goals, "away_score": goals})
        assert res.status_code == 200, res.text
    [group] = c.get(path, headers=VIEWER).json()["groups"]
    assert [t["name"] for t in group["standings"]] == ["Zulu", "Alpha", "Bravo"]


def test_group_moves_and_score_lock(club):
    c, eid, path, _ = _seed(club, ["One", "Two", "Three", "Four", "Five", "Six"])
    first, second = _draw(c, path, 3)
    move = f"{path}/{first['id']}/teams"
    moved = min(_teams(second))
    new_teams = sorted(_teams(first) | {moved})
    _, _, _, foreign = _seed(club, ["Other"])
    for bad in (new_teams + list(foreign.values()), [moved, moved], [True]):
        assert c.put(move, headers=ORGANIZER, json={"team_ids": bad}).status_code == 400
    assert c.get(path, headers=VIEWER).json()["groups"] == [first, second]
    res = c.put(move, headers=ORGANIZER, json={"team_ids": new_teams})
    assert res.status_code == 200, res.text
    a, b = res.json()["groups"]
    assert _teams(a) == set(new_teams) and _teams(b) == _teams(second) - {moved}
    _assert_fixtures(a)
    _assert_fixtures(b)

    match = f"/api/matches/{a['matches'][0]['id']}"
    result = {"home_score": 0, "away_score": 0}
    assert c.put(match, headers=VIEWER, json=result).status_code == 403
    assert c.put(match, headers=ORGANIZER, json={"home_score": True, "away_score": 0}).status_code == 400
    assert c.put(match, headers=ORGANIZER, json=result).status_code == 200
    assert c.post(path, headers=ORGANIZER, json={"size": 3, "advance": 2}).status_code == 409
    assert c.put(f"{path}/{b['id']}/teams", headers=ORGANIZER, json={"team_ids": []}).status_code == 409
    assert c.delete(path, headers=VIEWER).status_code == 403
    assert c.put(match, headers=ORGANIZER).status_code == 400
    cleared = c.put(match, headers={**ORGANIZER, "Content-Type": "application/json"}, content="null")
    assert cleared.status_code == 200, cleared.text
    assert [cleared.json()[k] for k in ("home_score", "away_score", "played_at")] == [None, None, None]
    _draw(c, path)
    assert c.delete(path, headers=ORGANIZER).status_code == 204
    assert c.get(path, headers=VIEWER).json() == {"groups": []}
    _, con = club
    assert con.execute("SELECT COUNT(*) FROM event_teams WHERE event_id = ?", (eid,)).fetchone()[0] == 6


def test_group_visibility_and_admin_match_scope(club):
    c, con = club
    eid = _event(c, publish=False, **TEAMS)
    path = f"/api/events/{eid}/groups"
    assert c.get(path, headers=VIEWER).status_code == 404
    assert c.get(path, headers=ORGANIZER).json() == {"groups": []}
    c, eid, path, _ = _seed(club, ["One", "Two"])
    other = _event(c, **TEAMS)
    [group] = _draw(c, path)
    match = f"/api/matches/{group['matches'][0]['id']}"
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 10")
    result = {"home_score": 2, "away_score": 1}
    assert c.put(match, headers={**VIEWER, "X-Staff-Event": str(other)}, json=result).status_code == 403
    assert c.put(match, headers={**VIEWER, "X-Staff-Event": str(eid)}, json=result).status_code == 200


def test_admin_groups_draw(club, env, monkeypatch, capsys):
    from kbtu import admin
    _, cfg = env
    c, eid, _, _ = _seed(club, [f"T{i}" for i in range(11)])
    con = club[1]
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = (SELECT MIN(id) FROM users)")
    admin.main(["groups-draw", str(eid), "6", "2"])
    assert capsys.readouterr().out.strip() == "groups A:6 B:5"
