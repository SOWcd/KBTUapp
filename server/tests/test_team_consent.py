"""Signing up to a team event is the teams consent (evteams.signup's consent marker, the owner, Nov 18), and those
signed up before it are asked by the bot: the organizer's reminder."""
from __future__ import annotations

import time

from kbtu import logic, outbox
from test_core import env, set_clock, tma  # noqa: F401  (env is a fixture)
from test_event_teams import TEAMS, _event, _go, _list, _people, _sheet, club  # noqa: F401  (club is a fixture)
from test_team_guests import PAID, _uid

V = logic.evteams.CONSENT


def _consent(c, tg):
    return c.get("/api/me", headers=tma(tg)).json()["teams"]["consent"]


def _asks(con, tg=None):
    q = "SELECT u.tg_id, b.ref FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'team_consent'"
    return sorted(tuple(r) for r in con.execute(q).fetchall() if tg is None or r[0] == tg)


def test_signup_with_the_marker_is_the_consent(club):
    """The marker writes the row with the sign-up (any way in: no team, a team of my own, a paid hold); without it (an
    old app) nothing is written; a bad version or a failed sign-up leaves nothing; a plain event ignores it."""
    c, con = club
    a, b, x, y, z = _people(c, 5, consent=False)
    eid = _event(c, **TEAMS)
    assert _go(c, eid, a).json()["my"]["status"] == "going" and not _consent(c, a)  # old client: as today
    r = c.post(f"/api/events/{eid}/registration", headers=tma(b), json={"teamConsent": V})
    assert r.json()["my"]["status"] == "going" and _consent(c, b)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(a), json={"teamConsent": V}).status_code == 200
    assert not _consent(c, a)  # already signed up: that tap made no sign-up, so no consent
    assert c.post(f"/api/events/{eid}/registration", headers=tma(x), json={"teamConsent": "old"}).status_code == 400
    assert not _consent(c, x) and _sheet(c, eid, x)["my"] is None
    r = c.post(f"/api/events/{eid}/registration", headers=tma(x), json={"teamConsent": V, "team": {"create": "Owls"}})
    assert r.status_code == 200 and _consent(c, x)  # the consent comes first: the team is made in the same tap
    board = _list(c, eid)
    assert [p["consent"] for p in board["solo"]] == [False, True]  # a (old client), b
    tm = board["teams"][0]["id"]
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, b)}", headers=tma(20), json={"team": tm}).status_code == 200  # placeable
    assert c.put(f"/api/events/{eid}/teams/people/{_uid(con, a)}", headers=tma(20), json={"team": tm}).json()["message"] == "team_consent"
    shut = _event(c, **TEAMS, regUntil=int(time.time()) - 60)
    assert c.post(f"/api/events/{shut}/registration", headers=tma(y), json={"teamConsent": V}).status_code != 200
    assert not _consent(c, y)  # the sign-up failed: the transaction took the consent with it
    plain = _event(c)
    assert c.post(f"/api/events/{plain}/registration", headers=tma(y), json={"teamConsent": V}).json()["my"]["status"] == "going"
    assert not _consent(c, y)
    paid = _event(c, **PAID, **TEAMS)
    assert c.post(f"/api/events/{paid}/registration", headers=tma(z), json={"teamConsent": V}).json()["my"]["status"] == "hold"
    assert _consent(c, z)  # a paid one: at the hold, not the receipt
    full = _event(c, seats=1, **TEAMS)
    _go(c, full, a)
    r = c.post(f"/api/events/{full}/registration", headers=tma(y), json={"teamConsent": V})
    assert r.json()["my"]["status"] == "waitlist" and r.json()["teamsConsent"] is False  # the waitlist: not yet


def test_withdraw_is_remembered(club):
    """Taking it back still takes me out of my teams; the no is kept (OFF): the board says so with no Remind, the
    organizer skips me, a message queued before stays quiet; a new yes (a marked sign-up) overwrites."""
    c, con = club
    a, b = _people(c, 2, consent=False)
    eid, other = _event(c, **TEAMS), _event(c, **TEAMS)
    r = c.post(f"/api/events/{eid}/registration", headers=tma(a), json={"teamConsent": V, "team": {"create": "Owls"}})
    assert r.json()["teamsConsent"] is True and _consent(c, a)  # the server's word comes back with the card
    _go(c, eid, b)
    assert c.delete("/api/teams/consent", headers=tma(a)).json() == {"consent": False}
    assert _sheet(c, eid, a)["teams"]["team"] is None and _sheet(c, eid, a)["my"]["status"] == "going"
    assert con.execute("SELECT version FROM team_consents WHERE user_id = ?", (_uid(con, a),)).fetchone()[0] == "off"
    solo = {p["id"]: p for p in _list(c, eid)["solo"]}
    assert (solo[_uid(con, a)]["consent"], solo[_uid(con, a)]["off"]) == (False, True)
    assert (solo[_uid(con, b)]["consent"], solo[_uid(con, b)]["off"]) == (False, False)
    url = f"/api/events/{eid}/teams/people/{_uid(con, a)}/remind"
    assert c.post(url, headers=tma(20)).json() == {"queued": False, "consent": False, "off": True}
    assert _asks(con, a) == []
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'team_consent', ?, 0)", (_uid(con, a), f"tc:{eid}"))
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent' AND user_id = ?", (_uid(con, a),)).fetchone()
    assert outbox._render(con, m) is None  # queued before the no: quiet
    r = c.post(f"/api/events/{other}/registration", headers=tma(a), json={"teamConsent": V})
    assert r.json()["teamsConsent"] is True and _consent(c, a)  # a new yes


def test_organizer_reminder(club, monkeypatch):
    """The board's "Remind about consent": only who may manage the event's teams, a ticket only, once a day per person
    (any event's), nothing for someone who agreed or left; renders to the consent sheet."""
    c, con = club
    a, b = _people(c, 2, consent=False)
    later = int(time.time()) + 3 * 86400  # still ahead a day later
    eid, other = _event(c, start=later, **TEAMS), _event(c, start=later, **TEAMS)
    _go(c, eid, a)
    _go(c, eid, b)
    _go(c, other, a)
    url = lambda tg, e=eid: f"/api/events/{e}/teams/people/{_uid(con, tg)}/remind"  # noqa: E731
    assert c.post(url(a), headers=tma(b)).status_code == 403  # a student: not theirs
    assert c.post(url(a), headers=tma(20)).json() == {"queued": True, "consent": False, "off": False}
    assert c.post(url(a), headers=tma(20)).json()["queued"] is False  # today already
    assert c.post(url(a, other), headers=tma(20)).json()["queued"] is False  # per person, not per event
    assert len(_asks(con, a)) == 1
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent'").fetchone()
    assert outbox._render(con, m)[2] == f"tc_{eid}"
    now = int(time.time())
    set_clock(monkeypatch, lambda: now + 86400 + 60)
    assert c.post(url(a), headers=tma(20)).json()["queued"] is True and len(_asks(con, a)) == 2  # a day later
    assert c.post(url(b), headers=tma(20)).json()["queued"] is True
    mb = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent' AND user_id = ?", (_uid(con, b),)).fetchone()
    c.post("/api/teams/consent", headers=tma(a), json={"consent": V})
    assert c.post(url(a), headers=tma(20)).json() == {"queued": False, "consent": True, "off": False}
    assert outbox._render(con, m) is None  # agreed meanwhile: quiet
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))
    assert c.post(url(b), headers=tma(20)).status_code == 404  # left
    assert outbox._render(con, mb) is None  # left: quiet
    full = _event(c, start=now + 3 * 86400, seats=1, **TEAMS)
    _go(c, full, a)
    _go(c, full, b)  # the waitlist: no ticket, not on the board
    assert c.post(url(b, full), headers=tma(20)).status_code == 404
    plain = _event(c, start=now + 3 * 86400)
    _go(c, plain, a)
    assert c.post(url(a, plain), headers=tma(20)).status_code == 404


def test_expired_hold_then_marked_tap(club, monkeypatch):
    """An expired hold isn't a sign-up: the new tap with the line is one, so it is the consent (had after the sweep)."""
    c, con = club
    (w,) = _people(c, 1, consent=False)
    paid = _event(c, **PAID, **TEAMS)
    assert _go(c, paid, w).json()["my"]["status"] == "hold" and not _consent(c, w)  # old client
    now = int(time.time())
    set_clock(monkeypatch, lambda: now + 31 * 60)
    r = c.post(f"/api/events/{paid}/registration", headers=tma(w), json={"teamConsent": V})
    assert r.json()["my"]["status"] == "hold" and r.json()["teamsConsent"] is True and _consent(c, w)
