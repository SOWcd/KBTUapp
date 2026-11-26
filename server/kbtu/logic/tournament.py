"""A team event's tournament (beside evteams.py): shared match IDs, score input and stage locking; round-robin groups
with their fixtures, results and standings; double elimination with one grand final, where only opening seeds and
played scores are stored."""
from __future__ import annotations

import random
from collections import defaultdict
from itertools import combinations

from ..db import tx
from . import core, evteams, seats
from .core import ApiError, Viewer, one, rows

MAX_SAFE_INT = (1 << 53) - 1  # Integers that round-trip through the web client.
FINAL = ("final", 1, 1)


# ---------------------------------------------------------------- matches: IDs, scores, locking

def integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= MAX_SAFE_INT


def unscored(con, eid: int) -> None:
    stage = one(con, "SELECT stage FROM ev_matches WHERE event_id = ? AND home_score IS NOT NULL LIMIT 1", eid)
    if stage:
        raise ApiError("conflict", "groups_scored" if stage[0] == "group" else "bracket_scored")


def remove_bracket(con, eid: int) -> None:
    con.execute("DELETE FROM ev_matches WHERE event_id = ? AND stage != 'group'", (eid,))


def _valid_match_id(mid: int) -> bool:
    return 0 < mid < 1 << 63


def match_event(con, mid: int) -> int | None:
    match = one(con, "SELECT event_id FROM ev_matches WHERE id = ?", mid) if _valid_match_id(mid) else None
    return match[0] if match else None


def set_score(con, v: Viewer, mid: int, home: int | None, away: int | None) -> dict:
    played_at = core.now() if home is not None else None
    con.execute("UPDATE ev_matches SET home_score = ?, away_score = ?, played_at = ?, updated_by = ? WHERE id = ?",
                (home, away, played_at, v.id if home is not None else None, mid))
    return {"home_score": home, "away_score": away, "played_at": played_at}


def score(con, v: Viewer, mid: int, body: dict | None) -> dict:
    home = away = None
    if body is not None:
        home, away = body.get("home_score"), body.get("away_score")
        if not integer(home) or not integer(away):
            raise ApiError("bad_input")
    with tx(con):
        match = one(con, "SELECT event_id, stage, group_id, home, away FROM ev_matches WHERE id = ?", mid) if _valid_match_id(mid) else None
        if match is None:
            raise ApiError("not_found")
        evteams.staff_event(con, v, match["event_id"])
        if match["stage"] != "group":
            return _bracket_score(con, v, match["event_id"], mid, home, away)
        result = set_score(con, v, mid, home, away)
        return {"id": mid, "group_id": match["group_id"], "home": match["home"], "away": match["away"], **result}


# ---------------------------------------------------------------- groups: round-robin and standings

def _group_name(position: int) -> str:
    name = ""
    while position >= 0:
        position, letter = divmod(position, 26)
        name = chr(ord("A") + letter) + name
        position -= 1
    return name


def _group_fixtures(con, eid: int, gid: int, team_ids) -> None:
    con.executemany("INSERT INTO ev_matches (event_id, group_id, home, away) VALUES (?, ?, ?, ?)",
                    ((eid, gid, a, b) for a, b in combinations(sorted(team_ids), 2)))


def groups_draw(con, v: Viewer, eid: int, body: dict) -> dict:
    size, advance = body.get("size"), body.get("advance", 2)
    if not integer(size, 1) or not integer(advance):
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        unscored(con, eid)
        teams = [t[0] for t in rows(con, "SELECT id FROM event_teams WHERE event_id = ?", eid)]
        random.shuffle(teams)
        remove_bracket(con, eid)
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))
        offset = 0
        for position, count in enumerate(evteams.sizes(len(teams), 1, size)):
            group = teams[offset:offset + count]
            offset += count
            gid = con.execute("INSERT INTO ev_groups (event_id, name, advance, position) VALUES (?, ?, ?, ?)",
                              (eid, _group_name(position), advance, position)).lastrowid
            con.executemany("INSERT INTO ev_group_teams (group_id, team_id) VALUES (?, ?)", ((gid, tid) for tid in group))
            _group_fixtures(con, eid, gid, group)
        return _groups_board(con, eid)


def groups_move(con, v: Viewer, eid: int, gid: int, body: dict) -> dict:
    team_ids = body.get("team_ids")
    if not isinstance(team_ids, list) or not all(integer(tid, 1) for tid in team_ids) or len(set(team_ids)) != len(team_ids):
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        if not one(con, "SELECT 1 FROM ev_groups WHERE id = ? AND event_id = ?", gid, eid):
            raise ApiError("not_found")
        unscored(con, eid)
        assigned = dict(rows(con, """SELECT t.id, gt.group_id FROM event_teams t
            LEFT JOIN ev_group_teams gt ON gt.team_id = t.id WHERE t.event_id = ?""", eid))
        if not set(team_ids) <= assigned.keys():
            raise ApiError("bad_input")
        moving = {tid: assigned[tid] for tid in team_ids if assigned[tid] not in (None, gid)}
        affected = {gid, *moving.values()}
        # The submitted list replaces the target roster. Teams it omits can be assigned on a later move.
        con.execute("DELETE FROM ev_group_teams WHERE group_id = ?", (gid,))
        con.executemany("DELETE FROM ev_group_teams WHERE team_id = ?", ((tid,) for tid in moving))
        con.executemany("INSERT INTO ev_group_teams (group_id, team_id) VALUES (?, ?)", ((gid, tid) for tid in team_ids))
        remaining = defaultdict(list)
        for tid, group in assigned.items():
            if group in affected and group != gid and tid not in moving:
                remaining[group].append(tid)
        remaining[gid] = team_ids
        for group in sorted(affected):
            con.execute("DELETE FROM ev_matches WHERE group_id = ?", (group,))
            _group_fixtures(con, eid, group, remaining[group])
        return _groups_board(con, eid)


def groups_remove(con, v: Viewer, eid: int) -> None:
    with tx(con):
        evteams.staff_event(con, v, eid)
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))


def groups_board(con, v: Viewer, eid: int) -> dict:
    # Read visibility, rosters and fixtures in one snapshot while writes can continue in WAL.
    if not con.in_transaction:
        with con:
            con.execute("BEGIN")
            return groups_board(con, v, eid)
    seats._event(con, v, eid)
    return _groups_board(con, eid)


def _groups_board(con, eid: int) -> dict:
    groups = [dict(g) for g in rows(con, "SELECT id, name, advance, position FROM ev_groups WHERE event_id = ? ORDER BY position", eid)]
    standings, matches = defaultdict(dict), defaultdict(list)
    for t in rows(con, """SELECT gt.group_id, t.id, t.name FROM ev_groups g JOIN ev_group_teams gt ON gt.group_id = g.id
            JOIN event_teams t ON t.id = gt.team_id WHERE g.event_id = ?""", eid):
        standings[t["group_id"]][t["id"]] = {"team_id": t["id"], "name": t["name"], "played": 0, "won": 0, "drawn": 0,
                                             "lost": 0, "scored": 0, "conceded": 0, "diff": 0, "points": 0}
    for m in rows(con, """SELECT m.id, m.group_id, m.home, m.away, m.home_score, m.away_score, m.played_at
            FROM ev_groups g JOIN ev_matches m ON m.group_id = g.id WHERE g.event_id = ? ORDER BY m.group_id, m.id""", eid):
        matches[m["group_id"]].append(dict(m))
    for group in groups:
        gid = group["id"]
        group["matches"] = matches[gid]
        group["standings"] = _standings(standings[gid], matches[gid], group["advance"])
    return {"groups": groups}


def _standings(teams: dict, matches: list[dict], advance: int) -> list[dict]:
    results = []
    for match in matches:
        a, b = match["home_score"], match["away_score"]
        if a is None:
            continue
        home, away = teams[match["home"]], teams[match["away"]]
        home_points, away_points = (3, 0) if a > b else (0, 3) if b > a else (1, 1)
        for team, scored, conceded, points in ((home, a, b, home_points), (away, b, a, away_points)):
            team["played"] += 1
            team["won"] += points == 3
            team["drawn"] += points == 1
            team["lost"] += points == 0
            team["scored"] += scored
            team["conceded"] += conceded
            team["diff"] += scored - conceded
            team["points"] += points
        results.append((home, away, home_points, away_points))

    head_to_head = defaultdict(int)
    for home, away, home_points, away_points in results:
        if home["points"] == away["points"]:
            head_to_head[home["team_id"]] += home_points
            head_to_head[away["team_id"]] += away_points
    table = sorted(teams.values(), key=lambda t: (-t["points"], -head_to_head[t["team_id"]], -t["diff"], -t["scored"],
                                                  evteams.name_key(t["name"]), t["team_id"]))
    for i, team in enumerate(table):
        team["advance"] = i < advance
    return table


# ---------------------------------------------------------------- bracket: double elimination

def _bracket_fixtures(con, eid: int, seeds: list[int]) -> None:
    rounds = (len(seeds) - 1).bit_length()
    last_lower = 2 * (rounds - 1)
    order = [0]
    for r in range(1, rounds + 1):
        order = [position for seed in order for position in (seed, (1 << r) - 1 - seed)]
    opening = [seeds[position] if position < len(seeds) else None for position in order]

    ids = {}

    def insert(stage, r, slot, win=None, lose=None, home=None, away=None):
        next_win = ids[win] if win is not None else None
        next_lose = ids[lose] if lose is not None else None
        ids[stage, r, slot] = con.execute("""INSERT INTO ev_matches (event_id, stage, round, slot, next_win, next_lose, home, away)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (eid, stage, r, slot, next_win, next_lose, home, away)).lastrowid

    # Build backward so every destination ID is available when its feeders are inserted.
    insert(*FINAL)
    for r in range(last_lower, 0, -1):
        width = 1 << (rounds - 1 - (r + 1) // 2)
        for slot in range(1, width + 1):
            win = FINAL if r == last_lower else ("lower", r + 1, slot if r % 2 else (slot + 1) // 2)
            insert("lower", r, slot, win)
    for r in range(rounds, 0, -1):
        width = 1 << (rounds - r)
        for slot in range(1, width + 1):
            win = FINAL if r == rounds else ("upper", r + 1, (slot + 1) // 2)
            if r == 1:
                lose = FINAL if rounds == 1 else ("lower", 1, (slot + 1) // 2)
                home, away = opening[2 * (slot - 1):2 * slot]
            else:
                # Cross the upper drops into the lower slots.
                lose = ("lower", 2 * r - 2, width + 1 - slot)
                home = away = None
            insert("upper", r, slot, win, lose, home, away)


def bracket_draw(con, v: Viewer, eid: int, body: dict) -> dict:
    seed = body.get("seed")
    if seed != "random" and (not isinstance(seed, list) or not all(integer(tid, 1) for tid in seed)):
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        if seed == "random" and rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage = 'group' AND home_score IS NOT NULL LIMIT 1", eid):
            return _from_groups(con, eid)  # after a group stage: its playoff, never a fresh random draw over it
        unscored(con, eid)
        teams = [t[0] for t in rows(con, "SELECT id FROM event_teams WHERE event_id = ? ORDER BY id", eid)]
        if len(teams) < 2:
            raise ApiError("bad_input", "bracket_teams")
        if seed == "random":
            random.shuffle(teams)
        elif len(seed) != len(teams) or set(seed) != set(teams):
            raise ApiError("bad_input", "bracket_teams")
        else:
            teams = seed
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))
        remove_bracket(con, eid)
        _bracket_fixtures(con, eid, teams)
        return _bracket_board(con, eid)


def _from_groups(con, eid: int) -> dict:
    """The playoff from a finished group stage: who advances from each group, seeded rank first then group order
    (A1, B1, A2, B2: the opening pairs A1-B2 and B1-A2, never two of one group); the groups and their scores stay."""
    if rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage != 'group' AND home_score IS NOT NULL LIMIT 1", eid):
        raise ApiError("conflict", "bracket_scored")
    if rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage = 'group' AND home_score IS NULL LIMIT 1", eid):
        raise ApiError("conflict", "groups_unfinished")
    groups = _groups_board(con, eid)["groups"]
    ranked = [[t["team_id"] for t in g["standings"] if t["advance"]] for g in groups]
    teams = [g[rank] for rank in range(max(map(len, ranked), default=0)) for g in ranked if rank < len(g)]
    if len(teams) < 2:
        raise ApiError("bad_input", "bracket_teams")
    remove_bracket(con, eid)
    _bracket_fixtures(con, eid, teams)
    return _bracket_board(con, eid)


def bracket_swap(con, v: Viewer, eid: int, body: dict) -> dict:
    a, b = body.get("a"), body.get("b")
    if not integer(a, 1) or not integer(b, 1) or a == b:
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        unscored(con, eid)
        opening = rows(con, "SELECT home, away FROM ev_matches WHERE event_id = ? AND stage = 'upper' AND round = 1", eid)
        if not opening:
            raise ApiError("not_found")
        if not {a, b} <= {team for match in opening for team in match}:
            raise ApiError("bad_input")
        con.execute("""UPDATE ev_matches SET home = CASE home WHEN :a THEN :b WHEN :b THEN :a ELSE home END,
                away = CASE away WHEN :a THEN :b WHEN :b THEN :a ELSE away END
            WHERE event_id = :eid AND stage = 'upper' AND round = 1 AND (home IN (:a, :b) OR away IN (:a, :b))""",
                    {"a": a, "b": b, "eid": eid})
        return _bracket_board(con, eid)


def _outcome(match: dict, waiting: bool = False) -> tuple[str, int | None, int | None]:
    home, away = match["home"], match["away"]
    a, b = match["home_score"], match["away_score"]
    if a is not None:
        return ("played", home, away) if a > b else ("played", away, home)
    if waiting:
        return "pending", None, None
    if home is not None and away is not None:
        return "ready", None, None
    winner = home if home is not None else away
    return ("bye", winner, None) if winner is not None else ("empty", None, None)


def _bracket_matches(con, eid: int) -> tuple[dict[int, dict], dict[int, str]]:
    matches, teams, feeds = {}, {}, defaultdict(list)
    for row in rows(con, """SELECT m.id, m.stage, m.round, m.slot, m.home, m.away, m.home_score, m.away_score,
            m.played_at, m.next_win, m.next_lose, h.name AS home_name, a.name AS away_name
        FROM ev_matches m LEFT JOIN event_teams h ON h.id = m.home LEFT JOIN event_teams a ON a.id = m.away
        WHERE m.event_id = ? AND m.stage != 'group'
        ORDER BY CASE m.stage WHEN 'upper' THEN 1 WHEN 'lower' THEN 2 ELSE 3 END, m.round, m.slot""", eid):
        match = dict(row)
        mid = match["id"]
        home_name, away_name = match.pop("home_name"), match.pop("away_name")
        waiting = False
        if match["stage"] == "upper" and match["round"] == 1:
            for team, name in ((match["home"], home_name), (match["away"], away_name)):
                if team is not None:
                    teams[team] = name
        else:
            # Winners feed the home side before drops. Two feeds of the same kind follow slot order.
            (_, match["home"], home_waits), (_, match["away"], away_waits) = sorted(feeds.pop(mid), key=lambda feed: feed[0])
            waiting = home_waits or away_waits
        status, winner, loser = _outcome(match, waiting)
        settled = status in ("played", "bye", "empty")
        match.update(status=status, winner=winner)
        matches[mid] = match
        for drop, dest, team in ((False, match["next_win"], winner), (True, match["next_lose"], loser)):
            if dest is not None:
                feeds[dest].append((drop, team, not settled))
    return matches, teams


def _check_dependents(matches: dict, match: dict) -> None:
    remaining, seen = [match], {match["id"]}
    while remaining:
        current = remaining.pop()
        for mid in (current["next_win"], current["next_lose"]):
            if mid is None or mid in seen:
                continue
            later = matches[mid]
            if later["home_score"] is not None:
                raise ApiError("conflict", "bracket_dependent_scored")
            remaining.append(later)
            seen.add(mid)


def _bracket_score(con, v: Viewer, eid: int, mid: int, home: int | None, away: int | None) -> dict:
    matches, _ = _bracket_matches(con, eid)
    match = matches[mid]
    if (home, away) == (match["home_score"], match["away_score"]):
        return match
    if home is not None:
        if home == away:
            raise ApiError("bad_input", "bracket_draw")
        if match["home"] is None or match["away"] is None:
            raise ApiError("conflict", "bracket_tbd")
    _check_dependents(matches, match)
    match.update(set_score(con, v, mid, home, away))
    match["status"], match["winner"], _ = _outcome(match)
    return match


def bracket_board(con, v: Viewer, eid: int) -> dict:
    if not con.in_transaction:
        with con:
            con.execute("BEGIN")
            return bracket_board(con, v, eid)
    seats._event(con, v, eid)
    return _bracket_board(con, eid)


def _bracket_board(con, eid: int) -> dict:
    matches, teams = _bracket_matches(con, eid)
    stages = {stage: defaultdict(list) for stage in ("upper", "lower", "final")}
    winner = None
    for match in matches.values():
        stages[match["stage"]][match["round"]].append(match)
        if match["stage"] == "final":
            winner = match["winner"]
    return {**{stage: [{"round": r, "matches": fixtures} for r, fixtures in stage_rounds.items()]
               for stage, stage_rounds in stages.items()},
            "teams": [{"id": tid, "name": name} for tid, name in sorted(teams.items())], "winner": winner}
