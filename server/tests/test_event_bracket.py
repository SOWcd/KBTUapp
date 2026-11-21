"""Bracket fixtures, result propagation and organizer controls through the API."""
import json

from test_event_groups import ORGANIZER, VIEWER, _draw, _seed
from test_event_teams import TEAMS, _event, club, env  # noqa: F401  (fixtures)


def _launch(club, size):
    c, eid, _, teams = _seed(club, [f"Team {i}" for i in range(size)])
    path = f"/api/events/{eid}/bracket"
    seeds = list(teams.values())
    result = c.post(path, headers=ORGANIZER, json={"seed": seeds})
    assert result.status_code == 200, result.text
    return c, path, seeds, result.json()


def _matches(board):
    return {m["id"]: m for stage in ("upper", "lower", "final") for r in board[stage] for m in r["matches"]}


def _score(c, mid, score=(1, 0), headers=ORGANIZER):
    body = None if score is None else dict(zip(("home_score", "away_score"), score))
    return c.put(f"/api/matches/{mid}", headers={**headers, "Content-Type": "application/json"}, content=json.dumps(body))


def test_bracket_ten_teams_resolves_byes(club):
    c, path, seeds, board = _launch(club, 10)
    assert [len(r["matches"]) for r in board["upper"]] == [8, 4, 2, 1]
    assert [len(r["matches"]) for r in board["lower"]] == [4, 4, 2, 2, 1, 1]
    assert len(board["final"][0]["matches"]) == 1
    opening = board["upper"][0]["matches"]
    byes = [m for m in opening if m["status"] == "bye"]
    assert {m["winner"] for m in byes} == set(seeds[:6])
    assert {m["home"] for m in opening} | {m["away"] for m in opening} == {None, *seeds}
    by_id = _matches(board)
    for match in byes:
        dest = by_id[match["next_win"]]
        assert match["winner"] in (dest["home"], dest["away"])
        assert match["home_score"] is None and match["away_score"] is None
    assert _score(c, byes[0]["id"]).status_code == 409
    assert _score(c, board["final"][0]["matches"][0]["id"]).status_code == 409
    assert c.get(path, headers=VIEWER).json() == board


def test_bracket_full_run_to_lower_champion(club):
    c, path, seeds, board = _launch(club, 10)
    played = 0
    while board["winner"] is None:
        ready = next(m for m in _matches(board).values() if m["status"] == "ready")
        score = (0, 1) if ready["stage"] == "final" else (1, 0)
        result = _score(c, ready["id"], score)
        assert result.status_code == 200, result.text
        assert result.json()["winner"] == ready["away" if ready["stage"] == "final" else "home"]
        board = c.get(path, headers=VIEWER).json()
        played += 1
    [final] = board["final"][0]["matches"]
    assert final["home"] == board["upper"][-1]["matches"][0]["winner"]
    assert board["winner"] == final["away"] == board["lower"][-1]["matches"][0]["winner"]
    assert played == 2 * len(seeds) - 2
    assert all(m["status"] in ("played", "bye", "empty") for m in _matches(board).values())


def test_bracket_drop_and_transitive_score_lock(club):
    c, path, _, board = _launch(club, 10)
    first = board["upper"][0]["matches"][1]
    assert _score(c, first["id"], (0, 0)).status_code == 400
    assert _score(c, first["id"], headers=VIEWER).status_code == 403
    assert _score(c, first["id"]).status_code == 200
    board = c.get(path, headers=VIEWER).json()
    lower = _matches(board)[first["next_lose"]]
    assert lower["stage"] == "lower" and lower["status"] == "bye" and lower["winner"] == first["away"]
    assert first["home"] in (_matches(board)[first["next_win"]][side] for side in ("home", "away"))
    upper = board["upper"][1]["matches"][-1]
    assert upper["next_lose"] == lower["next_win"]
    assert _score(c, upper["id"]).status_code == 200
    next_lower = _matches(c.get(path, headers=VIEWER).json())[lower["next_win"]]
    assert (next_lower["home"], next_lower["away"]) == (first["away"], upper["away"])
    assert _score(c, next_lower["id"]).status_code == 200
    assert _score(c, first["id"]).status_code == 200  # An exact retry is harmless.
    assert _score(c, first["id"], (0, 1)).status_code == 409
    assert _score(c, first["id"], (2, 0)).status_code == 409
    assert _score(c, first["id"], None).status_code == 409
    assert _score(c, next_lower["id"], None).status_code == 200
    assert _score(c, first["id"], (0, 1)).status_code == 200
    matches = _matches(c.get(path, headers=VIEWER).json())
    assert matches[lower["next_win"]]["home"] == first["home"]
    assert _score(c, first["id"], None).status_code == 200
    matches = _matches(c.get(path, headers=VIEWER).json())
    assert matches[lower["next_win"]]["home"] is None
    assert matches[first["next_win"]]["away"] is None


def test_bracket_swap_reprojects_byes_and_locks_after_score(club):
    c, path, seeds, board = _launch(club, 10)
    a, b = seeds[0], seeds[7]
    opening = board["upper"][0]["matches"]
    swap = f"{path}/swap"
    assert c.put(swap, headers=VIEWER, json={"a": a, "b": b}).status_code == 403
    assert c.put(swap, headers=ORGANIZER, json={"a": a, "b": b + 1000}).status_code == 400
    result = c.put(swap, headers=ORGANIZER, json={"a": a, "b": b})
    assert result.status_code == 200, result.text
    swapped = result.json()
    first, second = swapped["upper"][0]["matches"][:2]
    assert first["id"] == opening[0]["id"] and first["winner"] == b
    assert second["id"] == opening[1]["id"] and second["home"] == a
    assert swapped["upper"][1]["matches"][0]["home"] == b
    assert _score(c, second["id"]).status_code == 200
    assert c.put(swap, headers=ORGANIZER, json={"a": a, "b": b}).status_code == 409
    assert c.post(path, headers=ORGANIZER, json={"seed": "random"}).status_code == 409


def test_bracket_stage_replacement_and_rights(club):
    c, con = club
    draft = _event(c, publish=False, **TEAMS)
    assert c.get(f"/api/events/{draft}/bracket", headers=VIEWER).status_code == 404
    c, eid, groups_path, teams = _seed(club, ["One", "Two"])
    path = f"/api/events/{eid}/bracket"
    assert c.post(path, headers=VIEWER, json={"seed": "random"}).status_code == 403
    assert c.post(path, headers=ORGANIZER, json={"seed": [teams["One"]] * 2}).status_code == 400
    [group] = _draw(c, groups_path)
    old = group["matches"][0]["id"]
    assert _score(c, old).status_code == 200
    assert c.post(path, headers=ORGANIZER, json={"seed": [teams["One"], teams["Two"]]}).status_code == 409  # a hand seed over played groups
    assert _score(c, old, None).status_code == 200
    result = c.post(path, headers=ORGANIZER, json={"seed": "random"})
    assert result.status_code == 200, result.text
    assert c.get(groups_path, headers=VIEWER).json() == {"groups": []}
    assert _score(c, old).status_code == 404
    initial = result.json()
    assert initial["lower"] == []
    _draw(c, groups_path)
    assert c.get(path, headers=VIEWER).json()["upper"] == []
    board = c.post(path, headers=ORGANIZER, json={"seed": "random"}).json()
    [opening] = board["upper"][0]["matches"]
    [final] = board["final"][0]["matches"]
    assert opening["next_win"] == opening["next_lose"] == final["id"]
    assert _score(c, initial["upper"][0]["matches"][0]["id"]).status_code == 404
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 10")
    assert _score(c, opening["id"], headers={**VIEWER, "X-Staff-Event": str(draft)}).status_code == 403
    assert _score(c, opening["id"], headers={**VIEWER, "X-Staff-Event": str(eid)}).status_code == 200
    assert c.post(groups_path, headers=ORGANIZER, json={"size": 2}).status_code == 409
    final = _matches(c.get(path, headers=VIEWER).json())[final["id"]]
    assert (final["home"], final["away"]) == (opening["home"], opening["away"])


def test_bracket_team_removal_keeps_fixtures_and_scores(club):
    c, path, _, board = _launch(club, 4)
    first = board["upper"][0]["matches"][0]
    assert _score(c, first["id"]).status_code == 200
    _, con = club
    con.execute("DELETE FROM event_teams WHERE id = ?", (first["away"],))
    updated = c.get(path, headers=VIEWER).json()
    matches = _matches(updated)
    assert matches.keys() == _matches(board).keys()
    assert matches[first["id"]]["away"] is None and matches[first["id"]]["home_score"] == 1
    assert first["away"] not in {team["id"] for team in updated["teams"]}
    assert matches[first["next_lose"]]["home"] is None


def test_playoff_from_finished_groups(club):
    """Group stage played out: the draw seeds the playoff from each group's advancing teams (A1-B2, B1-A2), groups stay."""
    c, eid, groups_path, teams = _seed(club, [f"T{i}" for i in range(8)])
    path = f"/api/events/{eid}/bracket"
    groups = c.post(groups_path, headers=ORGANIZER, json={"size": 4, "advance": 2}).json()["groups"]
    first = groups[0]["matches"][0]["id"]
    assert _score(c, first).status_code == 200
    assert c.post(path, headers=ORGANIZER, json={"seed": "random"}).json()["message"] == "groups_unfinished"
    for g in groups:
        for m in g["matches"]:
            assert _score(c, m["id"], (2, 1)).status_code == 200
    board = c.post(path, headers=ORGANIZER, json={"seed": "random"})
    assert board.status_code == 200, board.text
    standings = {g["id"]: [t["team_id"] for t in g["standings"] if t["advance"]] for g in c.get(groups_path, headers=VIEWER).json()["groups"]}
    a, b = list(standings.values())
    opening = {frozenset((m["home"], m["away"])) for m in board.json()["upper"][0]["matches"]}
    assert opening == {frozenset((a[0], b[1])), frozenset((b[0], a[1]))}
    assert len(c.get(groups_path, headers=VIEWER).json()["groups"]) == 2
