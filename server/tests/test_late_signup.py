"""Late sign-up (Nov 3): a free uncapped public event keeps "Going" open from its start until its end."""
from __future__ import annotations

import time

from kbtu import db
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)


def _event(c, cfg, **extra):
    """An official club (tg 20 its president), a published free event an hour from now, 2 h long; tg 10, 11 students."""
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    start = int(time.time()) + 3600
    body = {"title": "Talk", "place": "Hall", "startsAt": start, "endsAt": start + 7200, "emoji": "laptop_3d", "color": "#3B6BFF", **extra}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    if "id" in ev:
        c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
    return con, ev, body, start


def _go(c, eid, uid=10):
    return c.post(f"/api/events/{eid}/registration", headers=tma(uid), json={}).json()


def test_late_signup_open_until_the_end(env, monkeypatch):
    c, cfg = env
    con, ev, _, start = _event(c, cfg, lateSignup=True)
    eid = ev["id"]
    assert ev["lateSignup"] is True
    set_clock(monkeypatch, lambda: start + 60)
    r = _go(c, eid)
    assert r["my"]["status"] == "going", r
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'remind_2h'").fetchone()  # no "starts soon" after the start
    # the door scans a minute-old ticket
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": r["my"]["ticketCode"]}).json()["result"] == "ok"
    # one may step out while it's open
    assert _go(c, eid, 11)["my"]["status"] == "going"
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(11)).json()["my"]["status"] == "cancelled"
    # it stays in the afisha while it runs
    assert eid in [e["id"] for e in c.get("/api/events", headers=tma(11)).json()]
    set_clock(monkeypatch, lambda: start + 7200 + 1)
    assert _go(c, eid, 11).get("error") == "closed"


def test_without_it_closed_at_the_start(env, monkeypatch):
    c, cfg = env
    _, ev, _, start = _event(c, cfg)
    set_clock(monkeypatch, lambda: start + 60)
    assert _go(c, ev["id"]).get("error") == "closed"


def test_turned_on_after_the_start_and_off_again(env, monkeypatch):
    c, cfg = env
    _, ev, body, start = _event(c, cfg)
    eid = ev["id"]
    set_clock(monkeypatch, lambda: start + 60)
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "lateSignup": True}).json()["lateSignup"] is True
    assert _go(c, eid)["my"]["status"] == "going"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "lateSignup": False}).json()["lateSignup"] is False
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["status"] == "going"  # who signed up keeps the seat
    assert _go(c, eid, 11).get("error") == "closed"


def test_only_free_uncapped_public(env):
    c, cfg = env
    _, ev, body, _ = _event(c, cfg, lateSignup=True, regUntil=int(time.time()) + 1800)
    assert ev["regUntil"] is None  # no deadline with it
    for bad in ({"seats": 50}, {"price": 2000, "payToName": "Arman A.", "payPhone": "87071234567"}, {"visibility": "members"},
                {"visibility": "members", "meeting": True}):
        r = c.post("/api/orgs/1/events", headers=tma(20), json={**body, **bad})
        assert r.json().get("error") == "bad_input", bad
        r = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "lateSignup": True, **bad})
        assert r.json().get("error") == "bad_input", bad
