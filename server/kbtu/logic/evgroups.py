"""An event's round-robin groups, fixtures, results and standings."""
from __future__ import annotations

import random
from collections import defaultdict
from itertools import combinations

from ..db import tx
from . import evmatches, evteams
from .core import ApiError, Viewer, one, rows
from .evmatches import integer, unscored
from .seats import _event


def _name(position: int) -> str:
    name = ""
    while position >= 0:
        position, letter = divmod(position, 26)
        name = chr(ord("A") + letter) + name
        position -= 1
    return name


def _fixtures(con, eid: int, gid: int, team_ids) -> None:
    con.executemany("INSERT INTO ev_matches (event_id, group_id, home, away) VALUES (?, ?, ?, ?)",
                    ((eid, gid, a, b) for a, b in combinations(sorted(team_ids), 2)))


def draw(con, v: Viewer, eid: int, body: dict) -> dict:
    size, advance = body.get("size"), body.get("advance", 2)
    if not integer(size, 1) or not integer(advance):
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        unscored(con, eid)
        teams = [t[0] for t in rows(con, "SELECT id FROM event_teams WHERE event_id = ?", eid)]
        random.shuffle(teams)
        evmatches.remove_bracket(con, eid)
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))
        offset = 0
        for position, count in enumerate(evteams.sizes(len(teams), 1, size)):
            group = teams[offset:offset + count]
            offset += count
            gid = con.execute("INSERT INTO ev_groups (event_id, name, advance, position) VALUES (?, ?, ?, ?)",
                              (eid, _name(position), advance, position)).lastrowid
            con.executemany("INSERT INTO ev_group_teams (group_id, team_id) VALUES (?, ?)", ((gid, tid) for tid in group))
            _fixtures(con, eid, gid, group)
        return _board(con, eid)


def move(con, v: Viewer, eid: int, gid: int, body: dict) -> dict:
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
            _fixtures(con, eid, group, remaining[group])
        return _board(con, eid)


def remove(con, v: Viewer, eid: int) -> None:
    with tx(con):
        evteams.staff_event(con, v, eid)
        con.execute("DELETE FROM ev_groups WHERE event_id = ?", (eid,))


def board(con, v: Viewer, eid: int) -> dict:
    # Read visibility, rosters and fixtures in one snapshot while writes can continue in WAL.
    if not con.in_transaction:
        with con:
            con.execute("BEGIN")
            return board(con, v, eid)
    _event(con, v, eid)
    return _board(con, eid)


def _board(con, eid: int) -> dict:
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
