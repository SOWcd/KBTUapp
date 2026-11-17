"""Signing up to a team event is the teams consent (evteams.signup's consent marker, the owner, Nov 18), and those
signed up before it are asked by the bot: the admin's one-time team-consent-ask and the organizer's reminder."""
from __future__ import annotations

import time

from kbtu import admin, bot, logic
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


def test_withdraw_still_works(club):
    c, con = club
    (a,) = _people(c, 1, consent=False)
    eid = _event(c, **TEAMS)
    c.post(f"/api/events/{eid}/registration", headers=tma(a), json={"teamConsent": V, "team": {"create": "Owls"}})
    assert _consent(c, a)
    assert c.delete("/api/teams/consent", headers=tma(a)).json() == {"consent": False}
    assert _sheet(c, eid, a)["teams"]["team"] is None and _sheet(c, eid, a)["my"]["status"] == "going"


def test_admin_command_asks_once(club, monkeypatch):
    """team-consent-ask: those signed up to a coming team event without the consent, once per event; --dry queues
    nothing; a consented one, a plain event, a started one, someone who left: never."""
    c, con = club
    a, b, x = _people(c, 3, consent=False)
    (ok,) = _people(c, 1, first=300)
    soon = int(time.time()) + 3600
    e1, e2, started, plain = _event(c, **TEAMS), _event(c, **TEAMS), _event(c, start=soon, **TEAMS), _event(c)
    for p in (a, b, ok):
        _go(c, e1, p)
    _go(c, e2, a)
    _go(c, plain, x)
    _go(c, started, x)
    _go(c, e2, b)
    c.delete(f"/api/events/{e2}/registration", headers=tma(b))  # left
    set_clock(monkeypatch, lambda: soon + 60)  # `started` has started
    n = logic.evteams.consent_ask(con, dry=True)
    assert n == 3 and _asks(con) == []
    assert logic.evteams.consent_ask(con) == 3
    assert _asks(con) == sorted([(a, f"tc:{e1}"), (b, f"tc:{e1}"), (a, f"tc:{e2}")])
    assert logic.evteams.consent_ask(con) == 0  # idempotent
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent' AND user_id = ? AND ref = ?", (_uid(con, a), f"tc:{e1}")).fetchone()
    text, button, start = bot._render(con, m)
    assert start == f"tc_{e1}" and "Case Cup" in text and button
    c.post("/api/teams/consent", headers=tma(a), json={"consent": V})
    assert bot._render(con, m) is None  # agreed meanwhile: quiet
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent' AND user_id = ?", (_uid(con, b),)).fetchone()
    c.delete(f"/api/events/{e1}/registration", headers=tma(b))
    assert bot._render(con, m) is None  # left: quiet


def test_admin_cli(club, env, capsys, monkeypatch):
    c, con = club
    (a,) = _people(c, 1, consent=False)
    _go(c, _event(c, **TEAMS), a)
    monkeypatch.setattr(admin.config, "load", lambda: env[1])
    admin.main(["team-consent-ask", "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 1" and _asks(con) == []
    admin.main(["team-consent-ask"])
    assert capsys.readouterr().out.strip() == "queued 1"
    admin.main(["team-consent-ask"])
    assert capsys.readouterr().out.strip() == "queued 0" and len(_asks(con)) == 1


def test_organizer_reminder(club, monkeypatch):
    """The board's "Remind about consent": only who may manage the event's teams, once a day per person and event
    (the admin's run counts), nothing for someone who agreed or left; renders to the consent sheet."""
    c, con = club
    a, b = _people(c, 2, consent=False)
    eid = _event(c, start=int(time.time()) + 3 * 86400, **TEAMS)  # still ahead a day later
    _go(c, eid, a)
    _go(c, eid, b)
    url = lambda tg: f"/api/events/{eid}/teams/people/{_uid(con, tg)}/remind"  # noqa: E731
    assert c.post(url(a), headers=tma(b)).status_code == 403  # a student: not theirs
    assert c.post(url(a), headers=tma(20)).json() == {"queued": True, "consent": False}
    assert c.post(url(a), headers=tma(20)).json() == {"queued": False, "consent": False}  # today already
    assert len(_asks(con, a)) == 1
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'team_consent'").fetchone()
    assert bot._render(con, m)[2] == f"tc_{eid}"
    now = int(time.time())
    set_clock(monkeypatch, lambda: now + 86400 + 60)
    assert c.post(url(a), headers=tma(20)).json()["queued"] is True and len(_asks(con, a)) == 2  # a day later
    logic.evteams.consent_ask(con)  # b: the admin's run asked today
    assert c.post(url(b), headers=tma(20)).json()["queued"] is False
    c.post("/api/teams/consent", headers=tma(a), json={"consent": V})
    assert c.post(url(a), headers=tma(20)).json() == {"queued": False, "consent": True}
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))
    assert c.post(url(b), headers=tma(20)).status_code == 404  # left
    plain = _event(c, start=now + 3 * 86400)
    _go(c, plain, a)
    assert c.post(f"/api/events/{plain}/teams/people/{_uid(con, a)}/remind", headers=tma(20)).status_code == 404
