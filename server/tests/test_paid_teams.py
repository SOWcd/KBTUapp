"""Paid team events (logic/evteams.py): each player pays their own ticket by the Kaspi receipt; only a ticket ('going':
receipt in, or a free seat) counts in a team, a hold doesn't; the cap on teams; a rejected receipt (a refund) leaves the
team; Form teams places only checked receipts and respects the cap; the pre-review's holes (Nov 15), one test each.
The case: a CS2 5x5, 2 000 per player, at most 16 teams."""
from __future__ import annotations

import io
import time

from PIL import Image

from kbtu import logic
from test_core import env, set_clock, tma  # noqa: F401  (env is a fixture)
from test_event_teams import _event, _go, _list, _mine, _people, _sheet
from test_team_guests import PAID, _club, _uid

CS2 = {**PAID, "teamMin": 5, "teamMax": 5, "teamCap": 16, "seats": 80}
_n = [0]


def _pay(c, eid, tg, team=None):
    """A hold (by an invite link: team), then the receipt: the ticket ('going', the receipt not looked at yet)."""
    assert _go(c, eid, tg, team).json()["my"]["status"] == "hold"
    _receipt(c, eid, tg)


def _receipt(c, eid, tg):
    _n[0] += 1
    b = io.BytesIO()
    Image.new("RGB", (600, 1200), (_n[0] % 250, 120, 200)).save(b, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=b.getvalue()).json()["my"]["status"] == "going"


def _rid(con, eid, tg):
    return con.execute("""SELECT MAX(c.id) FROM receipts c JOIN registrations r ON r.id = c.registration_id
        WHERE r.event_id = ? AND r.user_id = ?""", (eid, _uid(con, tg))).fetchone()[0]


def _review(c, con, eid, tg, reject):
    assert c.post(f"/api/receipts/{_rid(con, eid, tg)}/review", headers=tma(20), json={"reject": reject}).status_code == 204


def _team(c, eid, tg, name):
    return c.post(f"/api/events/{eid}/team", headers=tma(tg), json={"name": name})


def test_paid_team_end_to_end(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **CS2)
    assert _sheet(c, eid, 10)["teams"]["cap"] == 16 and _sheet(c, eid, 10)["teamCap"] == 16
    cap, *four = _people(c, 5)

    # a hold can't make or join a team, nor sign up with one in one tap (no sign-up left behind)
    r = _go(c, eid, cap, {"create": "Vision"}).json()
    assert (r["error"], r["message"]) == ("closed", "pay_first") and _sheet(c, eid, cap)["my"] is None
    assert _go(c, eid, cap).json()["my"]["status"] == "hold"
    assert _team(c, eid, cap, "Vision").json()["message"] == "pay_first"

    # each pays their own; the captain makes the team, four join by the link: full at 5
    b = io.BytesIO()
    Image.new("RGB", (600, 1200), (9, 9, 9)).save(b, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(cap), content=b.getvalue()).json()["my"]["status"] == "going"
    assert _team(c, eid, cap, "Vision").status_code == 200
    token = _mine(c, eid, cap)["token"]
    # the owner's flow: a teammate opens the link, "I'm going in this team", pays; the receipt puts them in
    for i, tg in enumerate(four):
        if i % 2:  # by the link's one tap
            assert _go(c, eid, tg, {"join": token}).json()["my"]["status"] == "hold"
        else:      # on hold already, then the link
            assert _go(c, eid, tg).json()["my"]["status"] == "hold"
            assert c.post(f"/api/events/{eid}/team/join", headers=tma(tg), json={"token": token}).status_code == 200
        sheet = _sheet(c, eid, tg)["teams"]
        assert sheet["want"] == "Vision" and sheet["team"] is None  # no place held in the team while paying
        assert len(_mine(c, eid, cap)["members"]) == i + 1
        _receipt(c, eid, tg)
        assert _mine(c, eid, tg)["name"] == "Vision"
    assert len(_mine(c, eid, cap)["members"]) == 5
    (late,) = _people(c, 1, first=200)
    _pay(c, eid, late)
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(late), json={"token": token}).json()["message"] == "team_full"

    # 16 teams at most: 15 more captains, the 17th is refused; an open team can still be joined
    caps = _people(c, 16, first=300)
    for i, tg in enumerate(caps[:15]):
        _pay(c, eid, tg)
        assert _team(c, eid, tg, f"Team {i}").status_code == 200, i
    _pay(c, eid, caps[15])
    r = _team(c, eid, caps[15], "Seventeen").json()
    assert (r["error"], r["message"]) == ("full", "team_cap") and len(_list(c, eid)["teams"]) == 16
    t0 = _mine(c, eid, caps[0])["token"]
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(caps[15]), json={"token": t0}).status_code == 200
    # the cap can't drop below the teams already made
    base = {"title": "Case Cup", "place": "Hall", "startsAt": _sheet(c, eid, 20)["startsAt"], "emoji": "laptop_3d", "color": "#3B6BFF"}
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, **CS2, "teamCap": 15, "seats": 75}).json()["message"] == "team_cap"

    # a rejected receipt takes the player out of the team (the ticket ends: migration 161's trigger)
    out = four[0]
    rid = con.execute("SELECT c.id FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ? AND r.user_id = ?",
                      (eid, _uid(con, out))).fetchone()[0]
    assert c.post(f"/api/receipts/{rid}/review", headers=tma(20), json={"reject": True}).status_code == 204
    assert _uid(con, out) not in [p["id"] for p in _mine(c, eid, cap)["members"]] and len(_mine(c, eid, cap)["members"]) == 4
    # and a player who cancels their own ticket too
    c.delete(f"/api/events/{eid}/registration", headers=tma(four[1]))
    assert len(_mine(c, eid, cap)["members"]) == 3


def test_form_teams_skips_unpaid_and_keeps_the_cap(env):
    c, cfg = env
    con = _club(c, cfg)
    con.execute("UPDATE users SET lang = 'en' WHERE tg_id = 20")
    eid = _event(c, **PAID, teamMin=2, teamMax=2, teamCap=4, seats=8)
    cap, *solo = _people(c, 6)
    (hold, fake) = _people(c, 2, first=200)
    _pay(c, eid, cap)
    assert _team(c, eid, cap, "Vision").status_code == 200
    for tg in solo:
        _pay(c, eid, tg)
        _review(c, con, eid, tg, False)
    _pay(c, eid, fake)  # a receipt nobody checked (maybe a fake): never placed by Form teams
    assert _go(c, eid, hold).json()["my"]["status"] == "hold"
    assert _list(c, eid)["unchecked"] == [_uid(con, cap), _uid(con, fake)]
    assert "unchecked" not in str(_sheet(c, eid, cap)["teams"])  # members never see it
    con.execute("UPDATE events SET team_cap = 2 WHERE id = ?", (eid,))
    assert _uid(con, hold) not in [p["id"] for p in _list(c, eid)["solo"]]
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    # five paid alone make two teams of 2 (one left), but the cap leaves room for one: two placed, three left
    assert (r["placed"], r["left"], len(r["teams"])) == (2, 3, 2), r
    placed = {p["id"] for t in r["teams"] for p in t["members"]}
    assert _uid(con, hold) not in placed and _uid(con, fake) not in placed and placed <= {_uid(con, t) for t in [cap, *solo]}
    assert logic.evteams.sizes(5, 2, 2) == [2, 2]


def _base(c, eid):
    return {"title": "Case Cup", "place": "Hall", "startsAt": _sheet(c, eid, 20)["startsAt"], "emoji": "laptop_3d", "color": "#3B6BFF"}


def test_seats_held_to_cap_times_max(env):
    """Nobody pays for a place no team can take: a paid team event with a cap has seats, at most cap x max."""
    c, cfg = env
    _club(c, cfg)
    start = int(time.time()) + 5 * 3600
    body = {"title": "Cup", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", **CS2}
    for seats in (None, 81):
        r = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": seats}).json()
        assert r["message"] == "team_seats", seats
    eid = _event(c, **CS2)
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**_base(c, eid), **CS2, "teamCap": 10}).json()["message"] == "team_seats"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**_base(c, eid), **CS2, "teamCap": 10, "seats": 50}).status_code == 200


def test_free_team_event_cant_turn_paid_with_sign_ups(env):
    """They'd stay in their teams with no receipt."""
    c, cfg = env
    _club(c, cfg)
    eid = _event(c, teamMin=2, teamMax=4)
    (a,) = _people(c, 1)
    assert _go(c, eid, a).json()["my"]["status"] == "going"
    r = c.patch(f"/api/events/{eid}", headers=tma(20), json={**_base(c, eid), "teamMin": 2, "teamMax": 4, **PAID}).json()
    assert r["message"] == "team_paid"
    c.delete(f"/api/events/{eid}/registration", headers=tma(a))
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**_base(c, eid), "teamMin": 2, "teamMax": 4, **PAID}).json()["price"] == 2000


def test_free_first_year_seat_counts_as_paid(env):
    """A 1st-year free seat (the club gave it): in a team and placed by Form teams, with no receipt."""
    c, cfg = env
    con = _club(c, cfg)
    con.execute("UPDATE users SET lang = 'en' WHERE tg_id = 20")
    eid = _event(c, **PAID, freeFirst=5, teamMin=2, teamMax=2)
    a, b = _people(c, 2)
    con.execute("UPDATE students SET course = 1 WHERE user_id IN (?, ?)", (_uid(con, a), _uid(con, b)))
    for tg in (a, b):
        assert _go(c, eid, tg).json()["my"]["status"] == "going"
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert r["placed"] == 2 and r["unchecked"] == []


def test_refund_is_a_reject_even_after_accept(env):
    """A refund happens outside the app; the organizer records it by rejecting the (already accepted) receipt: out of
    the team. An old receipt from before a cancel and a new sign-up doesn't end the new ticket."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **CS2)
    a, b = _people(c, 2)
    _pay(c, eid, a)
    assert _team(c, eid, a, "Vision").status_code == 200
    _pay(c, eid, b)
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(b), json={"token": _mine(c, eid, a)["token"]}).status_code == 200
    _review(c, con, eid, b, False)
    _review(c, con, eid, b, True)  # refunded
    assert len(_mine(c, eid, a)["members"]) == 1 and _sheet(c, eid, b)["my"]["status"] == "cancelled"
    # a's old receipt, then a cancel, a new ticket: rejecting the old one leaves the new
    old = _rid(con, eid, a)
    c.delete(f"/api/events/{eid}/registration", headers=tma(a))
    _pay(c, eid, a)
    assert c.post(f"/api/receipts/{old}/review", headers=tma(20), json={"reject": True}).status_code == 204
    assert _sheet(c, eid, a)["my"]["status"] == "going"


def test_captain_cant_kick_after_deadline_and_short_team_loses_slot(env, monkeypatch):
    """No last-minute kicks after the sign-up deadline; a team under min at the deadline is disbanded by the organizer's
    move, which frees its slot under the cap."""
    c, cfg = env
    con = _club(c, cfg)
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    eid = _event(c, **{**CS2, "teamCap": 2, "seats": 10}, regUntil=t0 + 3600)
    a, b, x = _people(c, 3)
    for tg in (a, b, x):
        _pay(c, eid, tg)
    assert _team(c, eid, a, "Vision").status_code == 200
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(b), json={"token": _mine(c, eid, a)["token"]}).status_code == 200
    assert _team(c, eid, x, "Solo").status_code == 200
    clock[0] = t0 + 3601
    r = c.delete(f"/api/events/{eid}/team/members/{_uid(con, b)}", headers=tma(a)).json()
    assert r["message"] == "locked", r
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, x)}", headers=tma(20), json={"team": None}).status_code == 200
    assert len(_list(c, eid)["teams"]) == 1


def test_link_team_filled_while_paying(env):
    """The team filled up (or broke up) while a teammate paid: they keep the paid seat with no team and are told so."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **{**CS2, "teamMin": 2, "teamMax": 2, "teamCap": 4, "seats": 8})
    cap, slow, fast = _people(c, 3)
    _pay(c, eid, cap)
    assert _team(c, eid, cap, "Vision").status_code == 200
    token = _mine(c, eid, cap)["token"]
    assert _go(c, eid, slow, {"join": token}).json()["my"]["status"] == "hold"
    _pay(c, eid, fast, {"join": token})  # paid first: the last place
    assert len(_mine(c, eid, cap)["members"]) == 2
    _receipt(c, eid, slow)
    sheet = _sheet(c, eid, slow)
    assert sheet["my"]["status"] == "going" and sheet["teams"]["team"] is None and sheet["teams"]["missed"] is True
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'team_missed' AND user_id = ?", (_uid(con, slow),)).fetchone()
    # a team of their own clears it
    assert _team(c, eid, slow, "Second").status_code == 200 and "missed" not in _sheet(c, eid, slow)["teams"]
    # a team that broke up meanwhile: the same
    t2 = _mine(c, eid, slow)["token"]
    (late,) = _people(c, 1, first=200)
    assert _go(c, eid, late, {"join": t2}).json()["my"]["status"] == "hold"
    c.delete(f"/api/events/{eid}/team", headers=tma(slow))  # the captain alone leaves: the team goes
    _receipt(c, eid, late)
    assert _sheet(c, eid, late)["teams"]["missed"] is True
