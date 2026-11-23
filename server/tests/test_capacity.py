"""Capacity is chosen, never a default (issue #171, task 3): an event saved without `seats` is refused; null is the
explicit "no limit". Closing sign-up in Studio keeps the tickets already given, and reopens."""
from __future__ import annotations

import time

from kbtu import db
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)


def _club(c, cfg):
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    start = int(time.time()) + 86400
    return con, {"title": "Talk", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}


def test_save_needs_an_explicit_capacity(env):
    c, cfg = env
    con, body = _club(c, cfg)
    r = c.post("/api/orgs/1/events", headers=tma(20), json=body)
    assert r.status_code == 400 and r.json()["error"] == "bad_input"
    assert not con.execute("SELECT 1 FROM events").fetchone()
    open_ = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": None}).json()
    assert open_["seats"] is None                                                     # no limit, chosen
    capped = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": 30}).json()
    assert capped["seats"] == 30
    # an edit is a save too: left out is refused, the saved capacity stays
    assert c.patch(f"/api/events/{capped['id']}", headers=tma(20), json=body).status_code == 400
    assert con.execute("SELECT seats FROM events WHERE id = ?", (capped["id"],)).fetchone()[0] == 30
    assert c.patch(f"/api/events/{capped['id']}", headers=tma(20), json={**body, "seats": None}).json()["seats"] is None
    for bad in (0, -1, 5001, "many", "30", True, 1.9):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": bad}).status_code == 400


def test_close_signup_keeps_tickets_and_reopens(env):
    c, cfg = env
    con, body = _club(c, cfg)
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": 10}).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "going"
    shut = c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": "now"}).json()
    assert shut["regUntil"] and shut["status"] == "published"                         # closed, not cancelled
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).status_code == 409
    mine = c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]
    assert mine["status"] == "going" and mine["ticketCode"]                           # Ali's ticket stays
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": None}).json()["regUntil"] is None
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "going"
    # a student of the club's audience can't close it
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(11), json={"until": "now"}).status_code == 403


def test_close_a_late_signup_event_while_it_runs(env, monkeypatch):
    c, cfg = env
    con, body = _club(c, cfg)
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "seats": None, "endsAt": body["startsAt"] + 7200, "lateSignup": True}).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    set_clock(monkeypatch, lambda: body["startsAt"] + 60)                            # under way: sign-up still open
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": "now"}).status_code == 200
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).status_code == 409
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": body["startsAt"] + 600}).status_code == 400  # a set time: still the start at most
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": None}).status_code == 200
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "going"
