"""Admin → an event: the app's admin finds any event and runs it as its organizers do (X-Staff-Event), only there,
never its money or door, every write in the owner's log; "Close registration" and its reopening."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_review_moderation import _club_event


def _setup(env):
    """An admin (60), a moderator (61), club 1's President (62) with event 1, a student (63), club 2's President (64)."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    ids = {k: login(c, uid, k)["id"] for uid, k in ((60, "boss"), (61, "mod"), (62, "pres"), (63, "ali"), (64, "other"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 61")
    _club_event(con, ids["pres"])
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'b', 'club', 'B Club', 'B', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'president', 0)", (ids["other"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (2, 2, 'published', 'B night', '305', strftime('%s') + 86400, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (ids["other"],))
    return c, con, ids


def _as(uid: int, eid: object = 1) -> dict:
    return {**tma(uid), "X-Staff-Event": str(eid)}


def _staff_lines(con) -> list:
    return con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'staff_event' ORDER BY id").fetchall()


def test_staff_path_refused_to_everyone_else(env):
    c, con, ids = _setup(env)
    close = {"until": "now"}
    for uid in (61, 63, 64):  # a moderator, a student, another club's President: the flag lends nothing
        assert c.put("/api/events/1/reg-until", headers=_as(uid), json=close).status_code == 403
    assert c.put("/api/events/1/reg-until", headers=tma(64), json=close).status_code == 403   # club B on club A's event
    assert c.put("/api/events/1/reg-until", headers=tma(60), json=close).status_code == 403   # the admin without the flag
    assert c.put("/api/events/1/reg-until", headers=_as(60, 2), json=close).status_code == 403  # the flag for another event
    assert c.put("/api/events/1/reg-until", headers=_as(60, "1 "), json=close).status_code == 403
    assert c.post("/api/orgs/1/events", headers=_as(60), json={}).status_code == 403  # not an event's own route
    assert c.get("/api/events/1/door", headers=_as(60)).status_code == 403            # never the door
    assert c.get("/api/admin/events?q=hack", headers=tma(63)).status_code == 403
    assert c.get("/api/admin/events?q=hack", headers=tma(61)).status_code == 403
    assert con.execute("SELECT reg_until FROM events WHERE id = 1").fetchone()[0] is None
    assert not _staff_lines(con)


def test_admin_finds_and_runs_an_event_audited(env):
    c, con, ids = _setup(env)
    found = c.get("/api/admin/events?q=HAC", headers=tma(60)).json()
    assert [e["id"] for e in found] == [1]
    assert c.get("/api/admin/events?q=night", headers=tma(60)).json()[0]["id"] == 2
    # reading the event isn't logged; the attendee list (personal data) and every write are
    assert c.get("/api/events/1", headers=_as(60)).status_code == 200
    assert c.get("/api/events/1/attendees", headers=_as(60)).status_code == 200
    r = c.put("/api/events/1/reg-until", headers=_as(60), json={"until": "now"})
    assert r.status_code == 200 and r.json()["regUntil"]
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 409   # closed
    assert c.put("/api/events/1/reg-until", headers=_as(60), json={"until": None}).json()["regUntil"] is None
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 200   # open again
    lines = _staff_lines(con)
    assert [(a, t) for a, t, _ in lines] == [(ids["boss"], "event:1")] * 3
    assert [x for _, _, x in lines] == ['{"do": "GET /api/events/{eid}/attendees"}'] + ['{"do": "PUT /api/events/{eid}/reg-until"}'] * 2
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    assert c.get("/api/admin/audit", headers=tma(60)).json()[0]["targetName"] == "Hack"  # the owner's log names the event
    # a refused write leaves no line
    assert c.put("/api/events/1/reg-until", headers=_as(60), json={"until": 1 << 40}).status_code == 400
    assert len(_staff_lines(con)) == 3


def test_organizers_own_event_not_logged_and_bounds(env):
    c, con, ids = _setup(env)
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": "now"}).status_code == 200
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": True}).status_code == 400
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": None}).status_code == 200
    assert not _staff_lines(con)
