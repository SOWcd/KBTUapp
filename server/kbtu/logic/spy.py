"""Spy, the party game (rooms.py runs the room): friends sitting together, each with their phone. Everyone's card shows
the same place but one: the spy's says only that they are the spy. They talk, asking each other about the place, for
the host's minutes; then everyone votes for who they think the spy is. Caught (the most votes, no tie), the spy may
still win by naming the place; anyone else caught, or a tie, and the spy wins. The spy may also name the place at any
time while they talk: right, they win; wrong, they lose. One round; the host may start another.

The place's id never leaves the server before the round ends, except on the cards of those who aren't the spy (view).
The names are the web's (web/src/lib/i18n: spy.loc.<id>, ru/kk/en; a test checks every id has one)."""
from __future__ import annotations

import secrets

from .core import ApiError

MIN, MAX = 3, 12
MINUTES = (3, 5, 7, 10)
VOTE_S = 60     # to vote
GUESS_S = 45    # the caught spy's last word
ROUND = ("talk", "vote", "guess")

LOCATIONS = (
    # KBTU and Almaty
    "kbtu_canteen", "kbtu_library", "kbtu_dorm", "kbtu_lecture", "kbtu_gym", "kbtu_deans", "kbtu_lab", "kbtu_atrium",
    "kbtu_graduation", "kbtu_exam", "kbtu_hackathon", "kbtu_club_fair",
    "medeu", "shymbulak", "kok_tobe", "green_bazaar", "metro", "mountain_lake", "toi",
    # anywhere
    "airport", "train", "hospital", "bank", "cinema", "theatre", "beach", "restaurant", "supermarket", "hotel",
    "police", "school", "museum", "zoo", "space_station", "submarine", "circus", "concert", "pirate_ship",
    "film_set", "barbershop", "gas_station", "coffee_shop", "embassy", "polar_station",
)


def new(state: dict) -> None:
    state.update(phase="lobby", minutes=5, dl=None)


def joinable(state: dict) -> bool:
    return state.get("phase") in ("lobby", "over")


def _pick(seq):
    return seq[secrets.randbelow(len(seq))]


def act(state: dict, seat: int, seats: list[int], host: bool, what: str, body: dict, t: int) -> bool:
    phase = state["phase"]
    playing = phase in ROUND and seat in state.get("in", ())
    if what == "minutes":
        m = body.get("minutes")
        if not host or phase not in ("lobby", "over") or m not in MINUTES or isinstance(m, bool):
            raise ApiError("forbidden" if not host else "bad_input")
        if state["minutes"] == m:
            return False
        state["minutes"] = m
        return True
    if what == "start":
        if not host or phase not in ("lobby", "over"):
            raise ApiError("forbidden")
        if not MIN <= len(seats) <= MAX:
            raise ApiError("conflict", "players")
        state.update(phase="talk", loc=_pick(LOCATIONS), spy=_pick(seats), **{"in": list(seats)}, votes={}, guess=None,
                     result=None, dl=t + state["minutes"] * 60)
        return True
    if what == "vote_now":  # the talk ends early: anyone playing may call the vote
        if phase != "talk" or not playing:
            return False
        state.update(phase="vote", dl=t + VOTE_S)
        return True
    if what == "vote":
        to = body.get("seat")
        if phase != "vote" or not playing:
            return False
        if to == seat or to not in state["in"] or isinstance(to, bool):
            raise ApiError("bad_input")
        if state["votes"].get(str(seat)) == to:
            return False
        state["votes"][str(seat)] = to
        if len(state["votes"]) == len(state["in"]):
            _count(state, t)
        return True
    if what == "guess":
        loc = body.get("loc")
        if phase not in ("talk", "guess") or seat != state.get("spy"):
            return False
        if loc not in LOCATIONS:
            raise ApiError("bad_input")
        state["guess"] = loc
        _over(state, "spy" if loc == state["loc"] else "town", "guessed" if loc == state["loc"] else "missed")
        return True
    if what == "again":
        if not host or phase != "over":
            raise ApiError("forbidden")
        new_state = {"phase": "lobby", "minutes": state["minutes"], "dl": None}
        state.clear()
        state.update(new_state)
        return True
    raise ApiError("bad_input")


def _count(state: dict, at: int) -> None:
    """The votes in: the one with the most, unless tied (then nobody is caught and the spy wins)."""
    tally: dict[int, int] = {}
    for to in state["votes"].values():
        tally[to] = tally.get(to, 0) + 1
    top = max(tally.values(), default=0)
    lead = [s for s, n in tally.items() if n == top]
    state["accused"] = lead[0] if top and len(lead) == 1 else None
    if state["accused"] is None:
        _over(state, "spy", "tie")
    elif state["accused"] != state["spy"]:
        _over(state, "spy", "wrong")
    else:
        state.update(phase="guess", dl=at + GUESS_S)


def _over(state: dict, winner: str, why: str) -> None:
    state.update(phase="over", dl=None, result={"winner": winner, "why": why})


def tick(state: dict, t: int) -> None:
    """Every deadline passed by now, one after another, each from where the last one ended (never from `t`)."""
    while state.get("dl") is not None and state["dl"] <= t:
        at = state["dl"]
        if state["phase"] == "talk":
            state.update(phase="vote", dl=at + VOTE_S)
        elif state["phase"] == "vote":
            _count(state, at)
        else:  # the caught spy said nothing in time
            _over(state, "town", "silent")


def left(state: dict, seat: int, seats: list[int], t: int) -> None:
    """Someone left the room. Mid-round: the spy leaving ends it; anyone else leaves the round, their vote and the
    votes for them with them; fewer than MIN left ends it with no winner."""
    if state["phase"] not in ROUND or seat not in state["in"]:
        return
    if seat == state["spy"]:
        _over(state, "town", "fled")
        return
    state["in"] = [s for s in state["in"] if s != seat]
    state["votes"] = {k: to for k, to in state["votes"].items() if k != str(seat) and to != seat}
    if len(state["in"]) < MIN:
        _over(state, "none", "few")
    elif state["phase"] == "vote" and len(state["votes"]) == len(state["in"]):
        _count(state, t)


def view(state: dict, seat: int | None) -> dict:
    """What this seat may know. The place only on the cards of those playing who aren't the spy, until the end."""
    phase = state.get("phase", "lobby")
    out: dict = {"phase": phase, "minutes": state.get("minutes"), "deadline": state.get("dl")}
    if phase in ROUND:
        out["round"] = state["in"]
        if seat in state["in"]:
            out["role"] = {"spy": True} if seat == state["spy"] else {"spy": False, "loc": state["loc"]}
        if phase == "vote":
            out["voted"] = sorted(int(k) for k in state["votes"])
            out["myVote"] = state["votes"].get(str(seat))
        if phase == "guess":
            out["accused"] = state["accused"]  # the town caught the spy: who it is is out; the place is not
    elif phase == "over":
        out["round"] = state["in"]
        out["result"] = {**state["result"], "spy": state["spy"], "loc": state["loc"], "guess": state.get("guess"),
                         "accused": state.get("accused"), "votes": {int(k): to for k, to in state["votes"].items()}}
    return out
