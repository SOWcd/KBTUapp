"""Double elimination with one grand final. Only opening seeds and played scores are stored."""
from __future__ import annotations

import random
from collections import defaultdict

from ..db import tx
from . import evgroups, evmatches, evteams
from .core import ApiError, Viewer, rows
from .seats import _event

FINAL = ("final", 1, 1)


def _fixtures(con, eid: int, seeds: list[int]) -> None:
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


def draw(con, v: Viewer, eid: int, body: dict) -> dict:
    seed = body.get("seed")
    if seed != "random" and (not isinstance(seed, list) or not all(evmatches.integer(tid, 1) for tid in seed)):
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        if seed == "random" and rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage = 'group' AND home_score IS NOT NULL LIMIT 1", eid):
            return _from_groups(con, eid)  # after a group stage: its playoff, never a fresh random draw over it
        evmatches.unscored(con, eid)
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
        evmatches.remove_bracket(con, eid)
        _fixtures(con, eid, teams)
        return _board(con, eid)


def _from_groups(con, eid: int) -> dict:
    """The playoff from a finished group stage: who advances from each group, seeded rank first then group order
    (A1, B1, A2, B2: the opening pairs A1-B2 and B1-A2, never two of one group); the groups and their scores stay."""
    if rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage != 'group' AND home_score IS NOT NULL LIMIT 1", eid):
        raise ApiError("conflict", "bracket_scored")
    if rows(con, "SELECT 1 FROM ev_matches WHERE event_id = ? AND stage = 'group' AND home_score IS NULL LIMIT 1", eid):
        raise ApiError("conflict", "groups_unfinished")
    groups = evgroups._board(con, eid)["groups"]
    ranked = [[t["team_id"] for t in g["standings"] if t["advance"]] for g in groups]
    teams = [g[rank] for rank in range(max(map(len, ranked), default=0)) for g in ranked if rank < len(g)]
    if len(teams) < 2:
        raise ApiError("bad_input", "bracket_teams")
    evmatches.remove_bracket(con, eid)
    _fixtures(con, eid, teams)
    return _board(con, eid)


def swap(con, v: Viewer, eid: int, body: dict) -> dict:
    a, b = body.get("a"), body.get("b")
    if not evmatches.integer(a, 1) or not evmatches.integer(b, 1) or a == b:
        raise ApiError("bad_input")
    with tx(con):
        evteams.staff_event(con, v, eid)
        evmatches.unscored(con, eid)
        opening = rows(con, "SELECT home, away FROM ev_matches WHERE event_id = ? AND stage = 'upper' AND round = 1", eid)
        if not opening:
            raise ApiError("not_found")
        if not {a, b} <= {team for match in opening for team in match}:
            raise ApiError("bad_input")
        con.execute("""UPDATE ev_matches SET home = CASE home WHEN :a THEN :b WHEN :b THEN :a ELSE home END,
                away = CASE away WHEN :a THEN :b WHEN :b THEN :a ELSE away END
            WHERE event_id = :eid AND stage = 'upper' AND round = 1 AND (home IN (:a, :b) OR away IN (:a, :b))""",
                    {"a": a, "b": b, "eid": eid})
        return _board(con, eid)


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


def _matches(con, eid: int) -> tuple[dict[int, dict], dict[int, str]]:
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


def score(con, v: Viewer, eid: int, mid: int, home: int | None, away: int | None) -> dict:
    matches, _ = _matches(con, eid)
    match = matches[mid]
    if (home, away) == (match["home_score"], match["away_score"]):
        return match
    if home is not None:
        if home == away:
            raise ApiError("bad_input", "bracket_draw")
        if match["home"] is None or match["away"] is None:
            raise ApiError("conflict", "bracket_tbd")
    _check_dependents(matches, match)
    match.update(evmatches.set_score(con, v, mid, home, away))
    match["status"], match["winner"], _ = _outcome(match)
    return match


def board(con, v: Viewer, eid: int) -> dict:
    if not con.in_transaction:
        with con:
            con.execute("BEGIN")
            return board(con, v, eid)
    _event(con, v, eid)
    return _board(con, eid)


def _board(con, eid: int) -> dict:
    matches, teams = _matches(con, eid)
    stages = {stage: defaultdict(list) for stage in ("upper", "lower", "final")}
    winner = None
    for match in matches.values():
        stages[match["stage"]][match["round"]].append(match)
        if match["stage"] == "final":
            winner = match["winner"]
    return {**{stage: [{"round": r, "matches": fixtures} for r, fixtures in stage_rounds.items()]
               for stage, stage_rounds in stages.items()},
            "teams": [{"id": tid, "name": name} for tid, name in sorted(teams.items())], "winner": winner}
