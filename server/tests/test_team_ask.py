"""A host club's member comes to its public event as a guest by its President's or a Vice's yes (owner, Nov 7;
seats.team_ask): ask, withdraw, yes lets them sign up (and keeps the seat from joined()), no says so; nobody else decides."""
from __future__ import annotations

from kbtu import bot, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)
from test_team_guests import PAID, _club, _event, _go, _reg, _uid


def _member(con, tg, role="member"):
    logic.set_role(con, None, _uid(con, tg), 1, role, "test")


def _ask(c, eid, tg):
    return c.post(f"/api/events/{eid}/team-ask", headers=tma(tg))


def _decide(c, eid, uid, tg, yes):
    return c.put(f"/api/events/{eid}/team-asks/{uid}", headers=tma(tg), json={"yes": yes})


def _rendered(con, kind, tg):
    """What the bot would send now: its startapp, or None when quiet."""
    m = con.execute("SELECT *, 'ru' AS lang FROM bot_outbox WHERE kind = ? AND user_id = ?", (kind, _uid(con, tg))).fetchone()
    r = bot._render(con, m)
    return r and r[2]


def _pings(con, kind, tg):
    return con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = ? AND user_id = ?", (kind, _uid(con, tg))).fetchone()[0]


def test_ask_yes_then_sign_up(env):
    c, cfg = env
    con = _club(c, cfg)
    _member(con, 10)
    _member(con, 11, "vice")
    eid, paid = _event(c), _event(c, **PAID)
    assert _ask(c, eid, 10).json()["teamAsk"] == "pending"
    assert _ask(c, eid, 10).json()["teamAsk"] == "pending"  # again: nothing new
    assert _pings(con, "team_ask", 20) == 1 and _pings(con, "team_ask", 11) == 1  # the President and the Vice, once
    assert _ask(c, eid, 12).status_code == 409  # not of the club: signs up as anyone does
    assert _ask(c, eid, 11).status_code == 409  # a Vice needs nobody's yes
    assert _rendered(con, "team_ask", 20) == f"mg_{eid}"
    asks = c.get(f"/api/events/{eid}/team-asks", headers=tma(11)).json()
    assert [a["person"]["id"] for a in asks] == [_uid(con, 10)]
    assert _decide(c, eid, _uid(con, 10), 11, True).status_code == 204
    assert _decide(c, eid, _uid(con, 10), 20, False).status_code == 409  # answered already
    assert _pings(con, "team_ask_yes", 10) == 1 and _rendered(con, "team_ask_yes", 10) == f"ev_{eid}"
    assert _rendered(con, "team_ask", 20) is None  # answered: the other leader's card stays quiet
    assert _go(c, eid, 10)["my"]["status"] == "going"
    assert _go(c, paid, 10).get("message") == "team"  # per event
    assert c.get(f"/api/events/{eid}/team-asks", headers=tma(20)).json() == []


def test_no_and_withdraw(env):
    c, cfg = env
    con = _club(c, cfg)
    _member(con, 10)
    eid = _event(c)
    _ask(c, eid, 10)
    assert _decide(c, eid, _uid(con, 10), 20, False).status_code == 204
    assert _pings(con, "team_ask_no", 10) == 1 and _rendered(con, "team_ask_no", 10) == f"ev_{eid}"
    assert _go(c, eid, 10).get("message") == "team"
    assert _ask(c, eid, 10).json()["teamAsk"] == "pending"  # may ask again; the same day pings nobody twice
    assert _pings(con, "team_ask", 20) == 1
    assert _rendered(con, "team_ask_no", 10) is None  # asked again: the no is old news
    assert "teamAsk" not in c.delete(f"/api/events/{eid}/team-ask", headers=tma(10)).json()
    assert _decide(c, eid, _uid(con, 10), 20, True).status_code == 409


def test_only_its_leaders_decide(env):
    c, cfg = env
    con = _club(c, cfg)
    login(c, 30, "other")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'art', 'club', 'Art', 'Art', 'art_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 2, id, 'president', 0 FROM users WHERE tg_id = 30")
    _member(con, 10)
    _member(con, 11, "head")
    eid = _event(c)
    _ask(c, eid, 10)
    for tg in (11, 30, 12, 10):  # a Head, another club's President, a stranger, the asker
        assert _decide(c, eid, _uid(con, 10), tg, True).status_code == 403, tg
        assert c.get(f"/api/events/{eid}/team-asks", headers=tma(tg)).status_code == 403
    assert con.execute("SELECT status FROM team_asks").fetchone()[0] == "pending"


def test_joined_and_refill_keep_a_permitted_seat(env):
    c, cfg = env
    con = _club(c, cfg)
    _member(con, 10)
    eid = _event(c, seats=1)
    _ask(c, eid, 10)
    _decide(c, eid, _uid(con, 10), 20, True)
    assert _go(c, eid, 10)["my"]["status"] == "going"
    assert _go(c, eid, 12)["my"]["status"] == "waitlist"
    logic.joined(con, 1, _uid(con, 10))  # joining again by any path
    _member(con, 10, "head")
    logic.refill(con)
    assert _reg(con, eid, 10)["status"] == "going" and _reg(con, eid, 12)["status"] == "waitlist"

