"""Team events (logic/evteams.py): the editor's switch, the three ways to sign up (create, join by link, no team), the
captain's tools, who sees rosters, the organizer's "Form teams" and moves, the lock at the start, and every way out
(leaving, a captain leaving, a cancelled or deleted event, a deleted account).

The waitlist rule: a team holds only people with a seat ('going'). Creating or joining a team on a full event is
refused and leaves no sign-up behind; "I have no team" may wait in line as any sign-up does, and is a person alone once
the waitlist moves them in."""
from __future__ import annotations

import time

import pytest

from kbtu import bot, db, logic
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)
from test_team_guests import PAID, _club, _uid

TEAMS = {"teamMin": 2, "teamMax": 4}


def _event(c, start=None, publish=True, **extra):
    start = start or int(time.time()) + 5 * 3600
    body = {"title": "Case Cup", "place": "Hall", "startsAt": start, "endsAt": start + 7200, "emoji": "laptop_3d", "color": "#3B6BFF", **extra}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert "id" in ev, ev
    if publish:
        assert c.post(f"/api/events/{ev['id']}/publish", headers=tma(20)).status_code == 200
    return ev["id"]


def _people(c, n, first=100, consent=True):
    """n students; consent: each has agreed to teams (evteams.CONSENT) as the app asks before the first team."""
    for tg in range(first, first + n):
        login(c, tg, f"p{tg}")
        if consent:
            assert c.post("/api/teams/consent", headers=tma(tg), json={"consent": logic.evteams.CONSENT}).json() == {"consent": True}
    return list(range(first, first + n))


def _go(c, eid, tg, team=None):
    return c.post(f"/api/events/{eid}/registration", headers=tma(tg), json={"team": team} if team is not None else {})


def _sheet(c, eid, tg):
    return c.get(f"/api/events/{eid}", headers=tma(tg)).json()


def _mine(c, eid, tg):
    return _sheet(c, eid, tg)["teams"]["team"]


def _list(c, eid, tg=20):
    return c.get(f"/api/events/{eid}/teams", headers=tma(tg)).json()


def _ids(con, tgs):
    return [_uid(con, t) for t in tgs]


@pytest.fixture
def club(env):
    c, cfg = env
    con = _club(c, cfg)
    con.execute("UPDATE users SET lang = 'en' WHERE tg_id = 20")  # the organizer's language names "Form teams"' teams
    return c, con


def test_editor_switch(club):
    c, con = club
    eid = _event(c, **TEAMS)
    card = _sheet(c, eid, 10)
    assert (card["teamMin"], card["teamMax"]) == (2, 4) and card["teams"] == {"min": 2, "max": 4, "locked": False, "team": None}
    assert "teamMin" not in _sheet(c, _event(c), 10)  # an ordinary event says nothing
    base = {"title": "X", "place": "Hall", "startsAt": int(time.time()) + 9000, "emoji": "laptop_3d", "color": "#3B6BFF"}
    for bad in ({"teamMin": 1, "teamMax": 4}, {"teamMin": 5, "teamMax": 4}, {"teamMin": 2, "teamMax": 11}, {"teamMin": 2},
                {"teamMin": "2", "teamMax": 4}, {**TEAMS, **PAID}, {**TEAMS, "lateSignup": True}):
        r = c.post("/api/orgs/1/events", headers=tma(20), json={**base, **bad})
        assert r.status_code in (400, 403), (bad, r.text)
    # a paid event can't become one, a team event can't become paid
    paid = _event(c, **PAID)
    edit = {**base, "title": "Case Cup"}
    assert c.patch(f"/api/events/{paid}", headers=tma(20), json={**edit, **TEAMS}).json()["message"] == "teams"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**edit, **PAID}).json()["message"] == "teams"


def test_switch_on_and_off_with_sign_ups(club):
    """Switching on keeps everyone signed up, with no team yet; a smaller max can't cut a bigger team; off lets the teams go."""
    c, con = club
    a, b, x = _people(c, 3)
    eid = _event(c)
    base = {"title": "Case Cup", "place": "Hall", "startsAt": int(time.time()) + 5 * 3600, "emoji": "laptop_3d", "color": "#3B6BFF"}
    assert _go(c, eid, a).json()["my"]["status"] == "going"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, "teamMin": 2, "teamMax": 3}).status_code == 200
    assert _mine(c, eid, a) is None and [p["id"] for p in _list(c, eid)["solo"]] == _ids(con, [a])
    assert c.post(f"/api/events/{eid}/team", headers=tma(a), json={"name": "Owls"}).status_code == 200
    _go(c, eid, b, {"join": _mine(c, eid, a)["token"]})
    _go(c, eid, x, {"join": _mine(c, eid, a)["token"]})
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, "teamMin": 2, "teamMax": 2}).json()["message"] == "team_size"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json=base).status_code == 200  # absent: kept
    assert len(_mine(c, eid, a)["members"]) == 3
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, "teamMin": None, "teamMax": None}).status_code == 200
    assert _sheet(c, eid, a)["teams"] is None and con.execute("SELECT COUNT(*) FROM event_teams").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM event_team_members").fetchone()[0] == 0
    assert _sheet(c, eid, b)["my"]["status"] == "going"  # everyone still signed up


def test_create_join_and_the_bad_cases(club):
    c, con = club
    cap, m1, m2, m3, other = _people(c, 5)
    eid, eid2 = _event(c, teamMin=2, teamMax=3), _event(c, **TEAMS)
    r = _go(c, eid, cap, {"create": "  Night   Owls "}).json()
    assert r["my"]["status"] == "going"
    t = _mine(c, eid, cap)
    assert t["name"] == "Night Owls" and t["captain"] == _uid(con, cap) and len(t["token"]) == 24 and not t["open"]
    assert _go(c, eid, m1, {"create": "night owls"}).json()["message"] == "name_taken"  # unique within the event, any case
    assert _sheet(c, eid, m1)["my"] is None  # refused: no sign-up left behind
    # blank-looking: zero-width, Hangul filler letters, the blank Braille cell, combining marks alone
    for bad in ("x", "a" * 41, "@owls", "t.me/owls", "see https://x.kz", "\u200b\u200b", "\u3164\u3164", "a\u3164", "\u2800\u2800\u2800",
                "\u115f\u1160", "\u0301\u0301", " \u2800 \u3164 "):
        assert _go(c, eid, m1, {"create": bad}).status_code == 400, bad
    assert _go(c, eid, m1, {"join": 5}).status_code == 400
    # the invite link: who holds it sees the team's name, its captain and how many, joins in one tap
    inv = c.get(f"/api/team-invites/{t['token']}", headers=tma(m1)).json()
    assert inv["event"] == eid and inv["team"]["name"] == "Night Owls" and inv["room"] and not inv["mine"]
    assert inv["team"]["captain"]["id"] == _uid(con, cap) and inv["team"]["count"] == 1 and inv["max"] == 3
    assert c.get("/api/team-invites/nope", headers=tma(m1)).status_code == 404
    assert _go(c, eid, m1, {"join": t["token"]}).json()["my"]["status"] == "going"
    assert _go(c, eid2, m2, {"join": t["token"]}).json()["message"] == "team_link"  # another event's link
    assert _sheet(c, eid2, m2)["my"] is None
    assert _go(c, eid, m2, {"join": t["token"]}).status_code == 200
    assert _go(c, eid, m3, {"join": t["token"]}).json()["message"] == "team_full"  # 3 of 3
    assert _sheet(c, eid, m3)["my"] is None
    inv = c.get(f"/api/team-invites/{t['token']}", headers=tma(m3)).json()
    assert inv["room"] is False and inv["team"]["count"] == 3
    # a link travels further than the captain meant: never the members besides the captain
    assert set(inv["team"]) == {"name", "captain", "count"} and f"P{cap}" in str(inv)
    assert f"P{m1}" not in str(inv) and f"P{m2}" not in str(inv) and t["token"] not in str(inv)
    # one team per person per event
    assert c.post(f"/api/events/{eid}/team", headers=tma(m1), json={"name": "Second"}).json()["message"] == "in_team"
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(m1), json={"token": t["token"]}).json()["message"] == "in_team"
    # "I have no team", then a team of my own later
    assert _go(c, eid, other).json()["my"]["status"] == "going" and _mine(c, eid, other) is None
    assert c.post(f"/api/events/{eid}/team", headers=tma(other), json={"name": "Solo"}).status_code == 200
    assert _mine(c, eid, other)["name"] == "Solo"
    # not signed up: no team of one's own
    assert c.post(f"/api/events/{eid}/team", headers=tma(m3), json={"name": "Nope"}).json()["message"] == "not_going"
    # a token of a team that's gone is dead
    old = _mine(c, eid, other)["token"]
    assert c.delete(f"/api/events/{eid}/team", headers=tma(other)).status_code == 200
    assert c.get(f"/api/team-invites/{old}", headers=tma(m3)).status_code == 404
    assert _go(c, eid, m3, {"join": old}).status_code == 404 and _sheet(c, eid, m3)["my"] is None


def test_who_sees_rosters(club):
    c, con = club
    cap, mate, outsider = _people(c, 3)
    eid = _event(c, **TEAMS)
    _go(c, eid, cap, {"create": "Owls"})
    _go(c, eid, mate, {"join": _mine(c, eid, cap)["token"]})
    out = _sheet(c, eid, outsider)
    assert out["teams"] == {"min": 2, "max": 4, "locked": False, "team": None} and "Owls" not in str(out)
    assert c.get(f"/api/events/{eid}/teams", headers=tma(outsider)).status_code == 403
    assert c.get(f"/api/events/{eid}/teams", headers=tma(mate)).status_code == 403  # the whole list: organizers
    mine = _mine(c, eid, mate)
    assert mine["name"] == "Owls" and "token" not in mine and [p["id"] for p in mine["members"]] == _ids(con, [cap, mate])
    assert set(mine["members"][0]) <= {"id", "name", "nick", "avatar", "founder", "mark", "staff", "realName", "i18n"}  # a person's reference, nothing more
    assert _sheet(c, eid, 20)["teams"]["count"] == 1 and _list(c, eid)["teams"][0]["name"] == "Owls"
    # leaving the event: no roster any more
    c.delete(f"/api/events/{eid}/registration", headers=tma(mate))
    assert _mine(c, eid, mate) is None and [p["id"] for p in _mine(c, eid, cap)["members"]] == _ids(con, [cap])


def test_captain_tools_and_handover(club):
    c, con = club
    cap, a, b = _people(c, 3)
    eid = _event(c, teamMin=2, teamMax=5)
    _go(c, eid, cap, {"create": "Owls"})
    tok = _mine(c, eid, cap)["token"]
    _go(c, eid, a, {"join": tok}), _go(c, eid, b, {"join": tok})
    assert c.patch(f"/api/events/{eid}/team", headers=tma(a), json={"name": "Mine"}).json()["message"] == "captain"
    assert c.delete(f"/api/events/{eid}/team/members/{_uid(con, b)}", headers=tma(a)).json()["message"] == "captain"
    t = c.patch(f"/api/events/{eid}/team", headers=tma(cap), json={"name": "Hawks", "open": True}).json()["teams"]["team"]
    assert t["name"] == "Hawks" and t["open"]
    assert c.patch(f"/api/events/{eid}/team", headers=tma(cap), json={"open": "yes"}).status_code == 400
    # removing a member: still signed up, no team, the bot says so (a template, the app's button)
    assert c.delete(f"/api/events/{eid}/team/members/{_uid(con, cap)}", headers=tma(cap)).status_code == 404  # not myself
    assert c.delete(f"/api/events/{eid}/team/members/{_uid(con, b)}", headers=tma(cap)).status_code == 200
    assert _mine(c, eid, b) is None and _sheet(c, eid, b)["my"]["status"] == "going"
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_removed' AND user_id = ?", (_uid(con, b),)).fetchone()
    text, _, start = bot._render(con, m)
    assert start == f"ev_{eid}" and "Hawks" not in text and "Case Cup" in text
    # the captain leaves the event: the one who came next leads; the last one out: the team is gone
    c.delete(f"/api/events/{eid}/registration", headers=tma(cap))
    t = _mine(c, eid, a)
    assert t["captain"] == _uid(con, a) and t["token"] == tok and [p["id"] for p in t["members"]] == _ids(con, [a])
    c.delete(f"/api/events/{eid}/team", headers=tma(a))
    assert con.execute("SELECT COUNT(*) FROM event_teams WHERE event_id = ?", (eid,)).fetchone()[0] == 0


def test_waitlist(club):
    """Seats: a team only of those with one; "no team" waits as anyone, alone once the line moves them in."""
    c, con = club
    a, b, x, y = _people(c, 4)
    eid = _event(c, seats=2, **TEAMS)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b)
    tok = _mine(c, eid, a)["token"]
    assert _go(c, eid, x, {"join": tok}).json()["message"] == "not_going"
    assert _sheet(c, eid, x)["my"] is None  # no waitlist place left behind either
    assert _go(c, eid, x, {"create": "Late"}).json()["message"] == "not_going"
    assert _go(c, eid, x).json()["my"]["status"] == "waitlist"
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(x), json={"token": tok}).json()["message"] == "not_going"
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert [p["id"] for p in r["solo"]] == _ids(con, [b]) and r["left"] == 1  # the waitlist isn't placed
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))  # a seat frees, x moves in, alone
    assert _sheet(c, eid, x)["my"]["status"] == "going" and _mine(c, eid, x) is None
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(x), json={"token": tok}).status_code == 200
    _ = y


@pytest.mark.parametrize("lo,hi,solos,open_teams,want_new,want_left", [
    (2, 5, 7, [], [4, 3], 0),             # 7 alone, 2..5: two teams as even as can be
    (2, 5, 1, [], [], 1),                 # one alone: nobody to pair with
    (2, 5, 0, [], [], 0),                 # nothing to do
    (4, 5, 7, [], [5], 2),                # 7 alone, 4..5: one full team, two left (fewer than 4)
    (3, 3, 10, [], [3, 3, 3], 1),
    (2, 4, 6, [3, 1], [2], 0),            # open teams first, smallest first (1 -> 4, then 3 -> 4), the rest new
    (2, 4, 2, [1, 3], [], 0),             # both go to the open teams: the one of 1 takes them (smallest first)
    (2, 10, 25, [], [9, 8, 8], 0),
])
def test_form_teams_shapes(club, lo, hi, solos, open_teams, want_new, want_left):
    c, con = club
    eid = _event(c, teamMin=lo, teamMax=hi)
    people = _people(c, solos + sum(open_teams))
    k = 0
    for n, size in enumerate(open_teams):  # open teams of these sizes, made before the solos sign up
        cap = people[k]
        _go(c, eid, cap, {"create": f"Open {n}"})
        tok = _mine(c, eid, cap)["token"]
        for p in people[k + 1:k + size]:
            _go(c, eid, p, {"join": tok})
        c.patch(f"/api/events/{eid}/team", headers=tma(cap), json={"open": True})
        k += size
    closed = None
    if open_teams:  # a closed team of one is never filled
        _people(c, 1, first=99)
        _go(c, eid, 99, {"create": "Closed"})
        closed = _mine(c, eid, 99)["id"]
    for p in people[k:]:
        _go(c, eid, p)
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    old = {f"Open {n}" for n in range(len(open_teams))} | {"Closed"}
    new = [t for t in r["teams"] if t["name"] not in old]
    assert [len(t["members"]) for t in new] == want_new and r["left"] == want_left == len(r["solo"])
    assert [t["name"] for t in new] == [f"Team {i + 1}" for i in range(len(new))]  # the organizer's language (en by default here)
    solo_order = _ids(con, people[k:])
    flat = [p["id"] for t in new for p in t["members"]]
    assert flat == solo_order[len(solo_order) - len(flat) - want_left:len(solo_order) - want_left]  # in sign-up order
    assert all(t["captain"] == t["members"][0]["id"] for t in new)
    if open_teams:
        assert len(next(t for t in r["teams"] if t["id"] == closed)["members"]) == 1
        assert sorted(len(t["members"]) for t in r["teams"] if t["name"].startswith("Open")) == ([3, 3] if solos == 2 else [hi, hi])
    assert r["placed"] == solos - want_left
    # placed people hear it, once; run again: nothing moves
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'team_placed'").fetchone()[0] == r["placed"]
    again = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert again["placed"] == 0 and again["teams"] == r["teams"] and again["solo"] == r["solo"]


def test_form_rules(club, monkeypatch):
    c, con = club
    people = _people(c, 5)
    eid = _event(c, **TEAMS)
    _go(c, eid, people[0], {"create": "Team 1"})  # a name the template would take: skipped
    for p in people[1:]:
        _go(c, eid, p)
    assert c.post(f"/api/events/{eid}/teams/form", headers=tma(people[1])).status_code == 403
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert [t["name"] for t in r["teams"]] == ["Team 1", "Team 2"] and len(r["teams"][0]["members"]) == 1  # not open: untouched
    m = con.execute("SELECT *, 'ru' AS lang FROM bot_outbox WHERE kind = 'team_placed' AND user_id = ?", (_uid(con, people[1]),)).fetchone()
    text, _, start = bot._render(con, m)
    assert start == f"ev_{eid}" and "Team 2" not in text
    con.execute("UPDATE users SET lang = 'ru' WHERE id = ?", (_uid(con, 20),))
    _people(c, 2, first=97), _go(c, eid, 98), _go(c, eid, 97)
    names = [t["name"] for t in c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()["teams"]]
    assert names[-1] == "\u041a\u043e\u043c\u0430\u043d\u0434\u0430 1"


def test_moves_by_hand(club):
    c, con = club
    a, b, x = _people(c, 3)
    eid = _event(c, teamMin=2, teamMax=2)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b, {"create": "Hawks"})
    _go(c, eid, x)
    owls, hawks = (t["id"] for t in _list(c, eid)["teams"])
    put = lambda tg, team, by=20: c.put(f"/api/events/{eid}/teams/people/{_uid(con, tg)}", headers=tma(by), json={"team": team})  # noqa: E731
    assert put(x, owls, by=a).status_code == 403
    assert put(x, 999999, ).status_code == 404
    r = put(x, owls).json()
    assert [len(t["members"]) for t in r["teams"]] == [2, 1] and r["solo"] == []
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'team_placed' AND user_id = ?", (_uid(con, x),)).fetchone()[0] == 1
    assert put(b, owls).json()["message"] == "team_full"
    assert len(_list(c, eid)["teams"]) == 2  # the refused move left Hawks as it was
    r = put(x, hawks).json()
    assert [len(t["members"]) for t in r["teams"]] == [1, 2]
    r = put(b, None).json()  # Hawks' captain to no team: x leads Hawks now
    assert [p["id"] for p in r["solo"]] == _ids(con, [b]) and r["teams"][1]["captain"] == _uid(con, x)
    login(c, 50, "out")
    assert put(50, owls).json()["message"] == "not_going"


def test_lock_at_start(club, monkeypatch):
    c, con = club
    a, b, x = _people(c, 3)
    start = int(time.time()) + 3600
    eid = _event(c, start=start, **TEAMS)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b)
    tok = _mine(c, eid, a)["token"]
    set_clock(monkeypatch, lambda: start + 60)
    assert _sheet(c, eid, a)["teams"]["locked"]
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(b), json={"token": tok}).json()["message"] == "locked"
    assert c.post(f"/api/events/{eid}/team", headers=tma(b), json={"name": "Late"}).json()["message"] == "locked"
    assert c.patch(f"/api/events/{eid}/team", headers=tma(a), json={"name": "New"}).json()["message"] == "locked"
    assert c.delete(f"/api/events/{eid}/team", headers=tma(a)).json()["message"] == "locked"
    assert c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()["message"] == "locked"
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, b)}", headers=tma(20), json={"team": None}).json()["message"] == "locked"
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(a)).status_code == 409  # no stepping out after the start either
    base = {"title": "Case Cup", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, "teamMin": 3, "teamMax": 4}).json()["message"] == "locked"
    assert _mine(c, eid, a)["name"] == "Owls" and x


def test_cancel_delete_and_account(club):
    c, con = club
    a, b, x = _people(c, 3)
    eid = _event(c, **TEAMS)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b, {"join": _mine(c, eid, a)["token"]})
    _go(c, eid, x, {"join": _mine(c, eid, a)["token"]})
    # a deleted account: out of the team, the captaincy passes on
    logic.delete_me(con, logic.Viewer(_uid(con, a), "user", True))
    t = _mine(c, eid, b)
    assert t["captain"] == _uid(con, b) and [p["id"] for p in t["members"]] == _ids(con, [b, x])
    assert con.execute("SELECT COUNT(*) FROM event_team_members WHERE user_id = ?", (_uid(con, a),)).fetchone()[0] == 0
    assert ("event_team_members", "user_id") in logic._DEL_GONE
    # cancelled: the teams go, sign-ups stay as for any cancelled event
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM event_teams WHERE event_id = ?", (eid,)).fetchone()[0] == 0
    assert c.post(f"/api/events/{eid}/team", headers=tma(b), json={"name": "Back"}).status_code == 409
    # deleted: the rows go with it
    e2 = _event(c, **TEAMS)
    _go(c, e2, x, {"create": "Owls"})
    logic.organizing._delete_event(con, e2)
    assert con.execute("SELECT COUNT(*) FROM event_teams").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM event_team_members").fetchone()[0] == 0


def test_lists_read_once(club):
    """The organizer's list and the sheet's team: a fixed number of queries, however many teams and people."""
    c, con = club

    def count(eid, n_people):
        people = _people(c, n_people, first=200 + n_people * 10)
        _go(c, eid, people[0], {"create": f"Cap {n_people}"})
        for p in people[1:]:
            _go(c, eid, p)
        c.post(f"/api/events/{eid}/teams/form", headers=tma(20))
        v = logic.Viewer(_uid(con, 20), "user", True)
        me = logic.Viewer(_uid(con, people[0]), "user", True)
        seen: list = []
        con.set_trace_callback(seen.append)
        logic.evteams.teams_list(con, v, eid)
        listed = len(seen)
        seen.clear()
        logic.evteams.view(con, me, con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone(), False)
        con.set_trace_callback(None)
        return listed, len(seen)

    small = count(_event(c, teamMin=2, teamMax=3), 4)
    big = count(_event(c, teamMin=2, teamMax=3), 15)
    assert small == big, (small, big)


def test_migration_triggers(club):
    """161's triggers: any way out of the event takes the person out of the team, whatever code did it."""
    c, con = club
    a, b = _people(c, 2)
    eid = _event(c, **TEAMS)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b, {"join": _mine(c, eid, a)["token"]})
    con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'removed' WHERE event_id = ? AND user_id = ?", (eid, _uid(con, b)))
    assert [p["id"] for p in _mine(c, eid, a)["members"]] == _ids(con, [a])
    con.execute("DELETE FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, a)))
    assert con.execute("SELECT COUNT(*) FROM event_teams").fetchone()[0] == 0
    assert [n for n, _ in db.MIGRATIONS][-1] == 161


def test_names_unique_by_key(club):
    """Within an event a name is taken in any case and any width (NFKC, casefolded), Cyrillic too; Form teams' "Team N"
    skips a name taken so."""
    c, con = club
    a, b, x, y, z = _people(c, 5)
    eid = _event(c, **TEAMS)
    owls = "\u0421\u043e\u0432\u044b \u0451\u0436"  # Cyrillic, lower case with yo
    assert _go(c, eid, a, {"create": owls}).status_code == 200
    for same in ("\u0421\u041e\u0412\u042b \u0401\u0416", "\u0441\u043e\u0432\u044b \u0451\u0436"):
        assert _go(c, eid, b, {"create": same}).json()["message"] == "name_taken", same
    assert _go(c, eid, b, {"create": "\uff34\uff45\uff41\uff4d 1"}).status_code == 200  # fullwidth "Team 1"
    assert c.patch(f"/api/events/{eid}/team", headers=tma(b), json={"name": "\u0421\u043e\u0432\u042b \u0401\u0436"}).json()["message"] == "name_taken"
    assert c.patch(f"/api/events/{eid}/team", headers=tma(b), json={"name": "TEAM 1"}).status_code == 200  # its own name, another case
    for p in (x, y, z):
        _go(c, eid, p)
    names = [t["name"] for t in c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()["teams"]]
    assert names[-1] == "Team 2"
    assert _go(c, _event(c, **TEAMS), x, {"create": owls}).status_code == 200  # another event: free


def test_new_link(club):
    """The captain's "New link": the old one stops working, the team stays; only the captain."""
    c, con = club
    cap, mate, late = _people(c, 3)
    eid = _event(c, **TEAMS)
    _go(c, eid, cap, {"create": "Owls"})
    old = _mine(c, eid, cap)["token"]
    _go(c, eid, mate, {"join": old})
    assert c.post(f"/api/events/{eid}/team/link", headers=tma(mate)).json()["message"] == "captain"
    new = c.post(f"/api/events/{eid}/team/link", headers=tma(cap)).json()["teams"]["team"]
    assert new["token"] != old and len(new["token"]) == 24 and len(new["members"]) == 2
    assert c.get(f"/api/team-invites/{old}", headers=tma(late)).status_code == 404
    assert _go(c, eid, late, {"join": old}).json()["message"] == "team_link" and _sheet(c, eid, late)["my"] is None
    assert _go(c, eid, late, {"join": new["token"]}).status_code == 200


def test_banned_never_placed(club):
    c, con = club
    a, b, x, y = _people(c, 4)
    eid = _event(c, teamMin=2, teamMax=3)
    _go(c, eid, a, {"create": "Owls"})
    for p in (b, x, y):
        _go(c, eid, p)
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (_uid(con, b),))
    owls = _list(c, eid)["teams"][0]["id"]
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, b)}", headers=tma(20), json={"team": owls}).status_code == 404
    c.patch(f"/api/events/{eid}/team", headers=tma(a), json={"open": True})
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    placed = {p["id"] for t in r["teams"] for p in t["members"]}
    assert _uid(con, b) not in placed and placed == set(_ids(con, [a, x, y])) and r["placed"] == 2
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'team_placed' AND user_id = ?", (_uid(con, b),)).fetchone()



def test_consent(club):
    """Teams' own consent: /me says it; without it no team of my own, no join, no sign-up with a team (nothing left
    behind); "I have no team" still signs up, and the organizer can't place me until I agree."""
    c, con = club
    (cap,), (x,) = _people(c, 1), _people(c, 1, first=200, consent=False)
    eid = _event(c, **TEAMS)
    _go(c, eid, cap, {"create": "Owls"})
    tok = _mine(c, eid, cap)["token"]
    assert c.get("/api/me", headers=tma(x)).json()["teams"] == {"consent": False}
    assert c.get("/api/me", headers=tma(cap)).json()["teams"] == {"consent": True}
    for pick in ({"create": "Hawks"}, {"join": tok}):
        assert _go(c, eid, x, pick).json()["message"] == "team_consent" and _sheet(c, eid, x)["my"] is None
    assert c.post("/api/teams/consent", headers=tma(x), json={"consent": "old"}).status_code == 400
    assert _go(c, eid, x).json()["my"]["status"] == "going"  # "no team": signed up, alone
    assert c.post(f"/api/events/{eid}/team", headers=tma(x), json={"name": "Hawks"}).json()["message"] == "team_consent"
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(x), json={"token": tok}).json()["message"] == "team_consent"
    owls = _list(c, eid)["teams"][0]["id"]
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, x)}", headers=tma(20), json={"team": owls}).json()["message"] == "team_consent"
    assert _list(c, eid)["solo"][0]["consent"] is False
    c.post("/api/teams/consent", headers=tma(x), json={"consent": logic.evteams.CONSENT})
    assert _list(c, eid)["solo"][0]["consent"] is True
    assert c.post(f"/api/events/{eid}/team/join", headers=tma(x), json={"token": tok}).status_code == 200
    at = con.execute("SELECT version, at FROM team_consents WHERE user_id = ?", (_uid(con, x),)).fetchone()
    assert at[0] == "tm1" and at[1] > 0  # recorded: which text, when


def test_converted_event_waits_for_consent(club):
    """An event made a team event after people signed up: they wait with no team; Form teams skips them and says how
    many; once one agrees, the next Form places them."""
    c, con = club
    a, b = _people(c, 2, consent=False)
    x, y = _people(c, 2, first=300)
    eid = _event(c)
    for p in (a, b, x, y):
        _go(c, eid, p)
    base = {"title": "Case Cup", "place": "Hall", "startsAt": int(time.time()) + 5 * 3600, "emoji": "laptop_3d", "color": "#3B6BFF"}
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, **TEAMS}).status_code == 200
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert (r["placed"], r["left"], r["noConsent"]) == (2, 0, 2)
    assert {p["id"] for p in r["teams"][0]["members"]} == set(_ids(con, [x, y]))
    assert [(p["id"], p["consent"]) for p in r["solo"]] == [(i, False) for i in _ids(con, [a, b])]
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'team_placed' AND user_id IN (?, ?)", _ids(con, [a, b])).fetchone()
    for p in (a, b):
        c.post("/api/teams/consent", headers=tma(p), json={"consent": logic.evteams.CONSENT})
    r = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert (r["placed"], r["noConsent"], r["solo"]) == (2, 0, [])


def test_withdraw(club, monkeypatch):
    """Taking it back: out of every team of mine, a started event's too (captaincy passes on), still signed up, never
    placed again until a new yes."""
    c, con = club
    cap, mate, other = _people(c, 3)
    soon, later = int(time.time()) + 3600, int(time.time()) + 5 * 3600
    e1, e2 = _event(c, start=soon, **TEAMS), _event(c, start=later, **TEAMS)
    for e in (e1, e2):
        _go(c, e, cap, {"create": "Owls"})
        _go(c, e, mate, {"join": _mine(c, e, cap)["token"]})
        _go(c, e, other)
    set_clock(monkeypatch, lambda: soon + 60)  # e1 has started
    assert c.delete("/api/teams/consent", headers=tma(cap)).json() == {"consent": False}
    assert c.get("/api/me", headers=tma(cap)).json()["teams"] == {"consent": False}
    assert _mine(c, e2, cap) is None and _sheet(c, e2, cap)["my"]["status"] == "going"
    assert _mine(c, e2, mate)["captain"] == _uid(con, mate)
    assert not con.execute("SELECT 1 FROM event_team_members WHERE user_id = ?", (_uid(con, cap),)).fetchone()  # the started one too
    assert [p["id"] for p in _mine(c, e1, mate)["members"]] == _ids(con, [mate]) and _mine(c, e1, mate)["captain"] == _uid(con, mate)
    tm = _list(c, e2)["teams"][0]["id"]
    assert c.put(f"/api/events/{e2}/teams/people/{_uid(con, cap)}", headers=tma(20), json={"team": tm}).json()["message"] == "team_consent"
    c.patch(f"/api/events/{e2}/team", headers=tma(mate), json={"open": True})
    r = c.post(f"/api/events/{e2}/teams/form", headers=tma(20)).json()
    assert _uid(con, cap) not in {p["id"] for t in r["teams"] for p in t["members"]} and r["noConsent"] == 1


def test_consent_goes_with_the_account(club):
    c, con = club
    (a,) = _people(c, 1)
    uid = _uid(con, a)
    assert con.execute("SELECT 1 FROM team_consents WHERE user_id = ?", (uid,)).fetchone()
    logic.delete_me(con, logic.Viewer(uid, "user", True))
    assert not con.execute("SELECT 1 FROM team_consents WHERE user_id = ?", (uid,)).fetchone()


def test_organizer_removal_is_told(club):
    """The organizer taking someone out of a team (to no team): the bot's template, as the captain's remove."""
    c, con = club
    a, b = _people(c, 2)
    eid = _event(c, **TEAMS)
    _go(c, eid, a, {"create": "Owls"})
    _go(c, eid, b, {"join": _mine(c, eid, a)["token"]})
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, b)}", headers=tma(20), json={"team": None}).status_code == 200
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_removed' AND user_id = ?", (_uid(con, b),)).fetchone()
    assert m, "no removal message"
    text, _, start = bot._render(con, m)
    assert start == f"ev_{eid}" and "Owls" not in text
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, b)}", headers=tma(20), json={"team": None}).status_code == 200  # already alone: nothing
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'team_removed' AND user_id = ?", (_uid(con, b),)).fetchone()[0] == 1
