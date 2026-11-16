"""Paid team events made clear (logic/evteams.py, Nov 16): the captain hears when a player leaves his team; Form teams
completes the fullest short team first, and after the sign-up deadline (or "fill all") fills short teams that aren't
open too, still only with checked receipts. No money rule changes (test_paid_teams.py stays as it was)."""
from __future__ import annotations

import time

from kbtu import bot
from test_core import env, set_clock, tma  # noqa: F401  (env is a fixture)
from test_event_teams import _event, _list, _mine, _people
from test_paid_teams import CS2, _pay, _review, _team
from test_team_guests import _club, _uid


def _told(con, tg):
    return con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'team_left' AND user_id = ?", (_uid(con, tg),)).fetchall()


def _join(c, eid, tg, token):
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(tg), json={"token": token}).status_code == 200


def test_captain_hears_a_player_left(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **CS2)
    cap, a, b = _people(c, 3)
    for tg in (cap, a, b):
        _pay(c, eid, tg)
    assert _team(c, eid, cap, "Vision").status_code == 200
    token = _mine(c, eid, cap)["token"]
    _join(c, eid, a, token)
    _join(c, eid, b, token)
    c.delete(f"/api/events/{eid}/registration", headers=tma(a))  # a self-cancel
    (row,) = _told(con, cap)
    text, _, start = bot._render(con, row)
    assert "left your team" in text and start == f"ev_{eid}" and str(_uid(con, a)) not in row["ref"]
    _review(c, con, eid, b, True)  # a rejected receipt (a refund)
    assert len(_told(con, cap)) == 2
    # the captain leaving: the next in line (now alone, so nobody) hears nothing; a captain out of the team: quiet
    c.delete(f"/api/events/{eid}/registration", headers=tma(cap))
    assert bot._render(con, row) is None


def _short_teams(c, con, eid, sizes, first=100):
    """Teams of these sizes, closed (not "find us teammates"), every receipt checked; returns their captains."""
    caps, k = [], first
    for n, size in enumerate(sizes):
        people = _people(c, size, first=k)
        k += size
        for tg in people:
            _pay(c, eid, tg)
            _review(c, con, eid, tg, False)
        assert _team(c, eid, people[0], f"T{first}-{n}").status_code == 200
        for tg in people[1:]:
            _join(c, eid, tg, _mine(c, eid, people[0])["token"])
        caps.append(people[0])
    return caps


def test_form_completes_fullest_open_team_first(env):
    """Codex's point 1: a team of 4 and a team of 1, both open, one soloist: the team of 4 becomes 5."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **CS2)
    four, one = _short_teams(c, con, eid, [4, 1])
    for tg in (four, one):
        c.patch(f"/api/events/{eid}/team", headers=tma(tg), json={"open": True})
    (solo,) = _people(c, 1, first=300)
    _pay(c, eid, solo)
    _review(c, con, eid, solo, False)
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert r["placed"] == 1 and len(_mine(c, eid, four)["members"]) == 5 and len(_mine(c, eid, one)["members"]) == 1


def test_form_fills_closed_short_teams_after_deadline_or_fill_all(env, monkeypatch):
    c, cfg = env
    con = _club(c, cfg)
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    eid = _event(c, **CS2, regUntil=t0 + 3600)
    (four,) = _short_teams(c, con, eid, [4])
    solo, fake, late = _people(c, 3, first=300)
    _pay(c, eid, solo)
    _review(c, con, eid, solo, False)
    _pay(c, eid, fake)  # a receipt nobody checked: never placed
    # before the deadline: the closed team isn't touched; the soloist waits (alone, no new team of one)
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert r["placed"] == 0 and len(_mine(c, eid, four)["members"]) == 4 and not r["regShut"]
    # "fill all" before the deadline: filled, still only the checked one
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20), json={"all": True}).json()
    assert r["placed"] == 1 and _uid(con, solo) in [p["id"] for p in _mine(c, eid, four)["members"]]
    assert _uid(con, fake) in [p["id"] for p in _list(c, eid)["solo"]]
    # after the deadline by itself: another closed short team gets the next checked soloist
    (two,) = _short_teams(c, con, eid, [2], first=400)
    _pay(c, eid, late)
    _review(c, con, eid, late, False)
    clock[0] = t0 + 3601
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert r["regShut"] and r["placed"] == 1 and len(_mine(c, eid, two)["members"]) == 3
