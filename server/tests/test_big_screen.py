"""The running check-in in the capsule (/api/me: checkin), Profile's "Big screen" (bigScreen), who can pair, and a pairing
that outlives a quiet network but not its tab."""
from __future__ import annotations

from kbtu import checkin, db
from test_core import _paired, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)
from test_qr_helpers import H, _in, _phone_event, _show


def _me(c, tg):
    return c.get("/api/me", headers=tma(tg)).json()


def test_organizer_sees_it_and_it_goes_with_finish(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _phone_event(c, con, "vol")
    me = _me(c, H)
    assert me["bigScreen"] == "pair"
    assert me["checkin"]["session"] == sid and me["checkin"]["event"] == eid and me["checkin"]["helper"] is False
    assert me["checkin"]["param"] is None                                # the rotating code never rides in /me (nor the phone's copy)
    c.post(f"/api/screens/{sid}/finish", headers=tma(H))
    assert _me(c, H)["checkin"] is None and _me(c, H)["bigScreen"] == "pair"
    con.close()


def test_helper_sees_its_own_qr_way_back_until_finish(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)
    me = _me(c, 2)
    assert me["bigScreen"] == "qr" and me["checkin"] == {"session": sid, "event": eid, "title": "Meet", "helper": True, "scanner": True, "until": me["checkin"]["until"]}
    assert _show(c, sid).status_code == 200                              # no second scan
    c.post(f"/api/screens/{sid}/finish", headers=tma(H))
    me = _me(c, 2)
    assert me["checkin"] is None and me["bigScreen"] is None
    con.close()


def test_an_over_event_lets_go_of_a_forgotten_session(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, _, _ = _in(c, con)
    assert _me(c, H)["checkin"]["until"] == con.execute("SELECT ends_at FROM events WHERE id = ?", (eid,)).fetchone()[0]
    con.execute("UPDATE events SET ends_at = strftime('%s','now') - 1, starts_at = strftime('%s','now') - 7200 WHERE id = ?", (eid,))
    assert _me(c, H)["checkin"] is None
    me = _me(c, 2)
    assert me["checkin"] is None and me["bigScreen"] is None
    con.close()


def test_unstarted_and_ordinary_students_see_nothing(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _phone_event(c, con, "vol")
    login(c, 3, "cat")
    assert _me(c, 3)["checkin"] is None and _me(c, 3)["bigScreen"] is None  # an ordinary student: no row
    uid = _me(c, 3)["id"]
    org = con.execute("SELECT org_id FROM events WHERE id = ?", (eid,)).fetchone()[0]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, uid))
    assert _me(c, 3)["bigScreen"] is None                                # a club's Member runs no events
    con.execute("UPDATE qr_sessions SET started_at = NULL WHERE id = ?", (sid,))
    assert _me(c, H)["checkin"] is None                                  # opened, not started: nothing running
    con.close()


def test_the_admin_gets_no_capsule_for_every_club(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _phone_event(c, con, "vol")
    login(c, 4, "root")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 4")
    me = _me(c, 4)
    assert me["checkin"] is None and me["bigScreen"] is None
    con.close()


def test_who_can_pair(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _in(c, con)
    code = c.post("/api/screen/pair").json()["code"]
    r = c.post("/api/screens/bind", headers=tma(2), json={"code": code})  # a helper only shows the QR: checkin.bind stays the organizers'
    assert r.status_code == 403
    assert c.post("/api/screens/bind", headers=tma(2), json={"code": code, "session": sid}).status_code == 403
    assert c.post("/api/screens/bind", headers=tma(H), json={"code": code}).json()["session"] == sid
    con.close()


def test_an_organizer_with_nothing_open_binds_nothing(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _phone_event(c, con, "vol")
    con.execute("DELETE FROM qr_sessions WHERE id = ?", (sid,))
    code = c.post("/api/screen/pair").json()["code"]
    r = c.post("/api/screens/bind", headers=tma(H), json={"code": code})
    assert r.status_code == 403                                          # the rule stands: the app words it (ScreenSheet)
    assert _me(c, H)["bigScreen"] == "pair" and c.get("/api/screens", headers=tma(H)).json() == []  # what it words it from
    con.close()


def test_pairing_survives_quiet_and_goes_when_the_tab_is_long_gone(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _phone_event(c, con, "vol")
    me = _paired(c, H, sid)
    count = lambda: c.get("/api/screens", headers=tma(H)).json()[0]["screens"]  # noqa: E731
    assert count() == 1
    t = checkin.now()
    # the tab went quiet: not counted as connected, but its pairing holds, as it must through a dead network
    monkeypatch.setattr(checkin, "now", lambda: t + checkin.SCREEN_SEEN + 11)
    assert count() == 0
    c.post("/api/screen/pair")                                           # (the sweep runs here)
    assert c.get("/api/screen", headers=me).json()["session"] == sid
    assert count() == 1                                                  # back as soon as it polls
    # a day of silence: nothing can still hold it
    monkeypatch.setattr(checkin, "now", lambda: t + checkin.SCREEN_SEEN + 11 + 86401)
    c.post("/api/screen/pair")
    assert c.get("/api/screen", headers=me).status_code == 403
    con.close()
