"""Spy, a party game for friends sitting together, each on their own phone (rooms.py holds the room). Everyone but one
gets the same place; the spy gets none and tries to work it out from the talk. One round: the host starts it with a
discussion timer, then everyone votes whom they think is the spy. A majority on the spy: caught, and the spy names the
place (right: the spy wins after all); anyone else or no majority: the spy wins. The spy may also name the place at any
moment of the talk, which ends the round either way.
The place lives in the state alone: view() gives it to the locals, never to the spy before the reveal (a test reads the
spy's every answer). Location ids here; their names in web/src/lib/i18n (spy.loc.<id>), the list in web/src/lib/games."""
from __future__ import annotations

import secrets

from .core import ApiError

MIN, MAX = 3, 12
MINUTES = (1, 15)  # the discussion timer the host picks
VOTE_S, GUESS_S = 60, 30  # the vote's and the caught spy's guess's time
LIVE = ("play", "vote", "guess")
# campus places first, then the city's and the classic ones
LOCATIONS = ("library", "canteen", "lecture_hall", "dorm", "gym", "dean_office", "lab", "coworking", "exam", "graduation",
             "hackathon", "assembly_hall", "club_fair", "career_fair", "metro", "bus", "coffee_shop", "hospital", "airport",
             "train", "cinema", "museum", "bank", "restaurant", "theater", "space_station", "submarine", "zoo",
             "supermarket", "shymbulak", "green_bazaar", "wedding", "concert", "beach", "police_station", "pirate_ship")


def new() -> dict:
    return {"phase": "lobby", "minutes": 5, "deadline": None}


def joinable(s: dict) -> bool:
    return s["phase"] == "lobby"


def live(s: dict) -> bool:
    """A phase with a clock: the phones ask every second (else every five)."""
    return s["phase"] in LIVE


def _end(s: dict, winner: str, why: str) -> None:
    s.update(phase="reveal", deadline=None, winner=winner, why=why)


def _count(s: dict, players: list[int], at: int) -> None:
    """The vote's end: a strict majority of the players on one person accuses them."""
    tally: dict[int, int] = {}
    for x in s["votes"].values():
        tally[x] = tally.get(x, 0) + 1
    top = max(tally, key=tally.get, default=None)
    s["accused"] = top if top is not None and tally[top] * 2 > len(players) else None
    if s["accused"] == s["spy"]:
        s.update(phase="guess", deadline=at + GUESS_S)
    else:
        _end(s, "spy", "missed")


def tick(s: dict, players: list[int], t: int) -> bool:
    """Resolves every deadline passed by `t`, each from its own moment (a room nobody read for a while catches up the
    same way it would have live). True: the state changed."""
    changed = False
    while s["deadline"] is not None and t >= s["deadline"]:
        at, changed = s["deadline"], True
        if s["phase"] == "play":
            s.update(phase="vote", deadline=at + VOTE_S)
        elif s["phase"] == "vote":
            _count(s, players, at)
        else:  # the caught spy said nothing
            _end(s, "locals", "no_guess")
    return changed


def act(s: dict, players: list[int], host: int, uid: int, body: dict, t: int) -> None:
    kind = body.get("type")
    if kind == "start":
        minutes = body.get("minutes", 5)
        if uid != host:
            raise ApiError("forbidden", "host")
        if s["phase"] != "lobby":
            raise ApiError("conflict", "started")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not MINUTES[0] <= minutes <= MINUTES[1]:
            raise ApiError("bad_input", "minutes")
        if not MIN <= len(players) <= MAX:
            raise ApiError("conflict", "players")
        s.update(phase="play", minutes=minutes, deadline=t + minutes * 60, spy=secrets.choice(players),
                 loc=secrets.choice(LOCATIONS), first=secrets.choice(players), votes={}, accused=None, guess=None)
    elif kind == "vote_now":  # the talk is over before the timer: the host takes everyone to the vote
        if uid != host:
            raise ApiError("forbidden", "host")
        if s["phase"] != "play":
            raise ApiError("conflict", "phase")
        s.update(phase="vote", deadline=t + VOTE_S)
    elif kind == "vote":
        target = body.get("target")
        if s["phase"] != "vote":
            raise ApiError("conflict", "phase")
        if target not in players or target == uid or isinstance(target, bool):
            raise ApiError("bad_input", "target")
        s["votes"][str(uid)] = target  # a change of mind is allowed until everyone has voted
        if len(s["votes"]) == len(players):
            _count(s, players, t)
    elif kind == "guess":
        loc = body.get("location")
        if uid != s.get("spy") or s["phase"] not in ("play", "guess"):
            raise ApiError("conflict", "phase")
        if loc not in LOCATIONS:
            raise ApiError("bad_input", "location")
        s["guess"] = loc
        if loc == s["loc"]:
            _end(s, "spy", "guessed")
        else:
            _end(s, "locals", "wrong_guess")
    else:
        raise ApiError("bad_input", "type")


def view(s: dict, uid: int) -> dict:
    """What this player sees. Before the reveal the spy's view has no place in it at all."""
    out = {"phase": s["phase"], "minutes": s["minutes"], "deadline": s["deadline"]}
    if s["phase"] == "lobby":
        return out
    spy = uid == s["spy"]
    out.update(role="spy" if spy else "local", first=s["first"])
    if not spy:
        out["location"] = s["loc"]
    if s["phase"] == "vote":
        out.update(voted=sorted(int(x) for x in s["votes"]), myVote=s["votes"].get(str(uid)))
    elif s["phase"] == "guess":
        out["accused"] = s["accused"]  # caught: the spy is everyone's now, and has GUESS_S to name the place
    elif s["phase"] == "reveal":
        out.update(location=s["loc"], result={"spy": s["spy"], "accused": s["accused"], "guess": s["guess"], "winner": s["winner"],
                                              "why": s["why"], "votes": [{"from": int(k), "to": x} for k, x in s["votes"].items()]})
    return out
