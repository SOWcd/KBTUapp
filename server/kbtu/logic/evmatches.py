"""Shared match IDs, score input and stage locking for team events."""
from __future__ import annotations

from ..db import tx
from . import core
from .core import ApiError, Viewer, one

MAX_SAFE_INT = (1 << 53) - 1  # Integers that round-trip through the web client.


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
    from . import evbracket, evteams

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
            return evbracket.score(con, v, match["event_id"], mid, home, away)
        result = set_score(con, v, mid, home, away)
        return {"id": mid, "group_id": match["group_id"], "home": match["home"], "away": match["away"], **result}
