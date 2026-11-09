"""An offline casting is a marked post: a time, a place, no sign-up (logic/newsfeed.py). Its state is computed from the
clock; ended, cancelled and deleted ones are never current."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)

ADMIN, PRES, STUDENT, MEMBER = 70, 71, 72, 73
HOUR = 3600
T0 = 2_000_000_000


def _club(con, ids, name):
    oid = logic.create_org(con, None, name, name[:2].upper(), "crown_3d", True)
    logic.set_role(con, None, ids[PRES], oid, "president", "test")
    return oid


def _setup(env, monkeypatch):
    _, cfg = env
    clock = [T0]
    set_clock(monkeypatch, lambda: clock[0])
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}))))
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, PRES, STUDENT, MEMBER)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, ids[PRES], oid, "president", "test")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, ids[MEMBER]))
    c.ids = ids
    return c, con, clock, oid


def _new(c, oid, who=PRES, start=T0 + HOUR, end=T0 + 3 * HOUR, place="Room 305"):
    return c.post(f"/api/orgs/{oid}/posts", headers=tma(who), json={"title": "Dance casting", "body": "", "tag": None,
                                                                     "casting": {"from": start, "to": end, "place": place}})


def _strip(c, who=STUDENT):
    return [p["id"] for p in c.get("/api/castings", headers=tma(who)).json()]


def _state(con, pid):
    return logic.casting_state(con.execute("SELECT * FROM posts WHERE id = ?", (pid,)).fetchone(), logic.core.now())


def _club_page(c, oid, who=STUDENT):
    return {p["id"]: p for p in c.get("/api/posts", params={"scope": f"org:{oid}"}, headers=tma(who)).json()}


def test_states_by_time_and_ended_never_current(env, monkeypatch):
    c, con, clock, oid = _setup(env, monkeypatch)
    pid = _new(c, oid).json()["id"]
    assert _state(con, pid) == "scheduled" and _strip(c) == [pid]
    clock[0] = T0 + HOUR
    assert _state(con, pid) == "open" and _strip(c) == [pid]
    clock[0] = T0 + 3 * HOUR
    assert _state(con, pid) == "ended" and _strip(c) == []
    assert _club_page(c, oid)[pid]["casting"]["cancelled"] is False  # it stays in the club's posts, the state says "over"
    assert c.post(f"/api/posts/{pid}/casting/cancel", headers=tma(PRES)).status_code == 400  # an ended one isn't called off
    assert c.patch(f"/api/posts/{pid}", headers=tma(PRES), json={"casting": {"from": T0 + 9 * HOUR, "to": T0 + 10 * HOUR, "place": "Hall"}}).status_code == 400


def test_soonest_first_and_input_checked(env, monkeypatch):
    c, con, _, oid = _setup(env, monkeypatch)
    later, soon = _new(c, oid, start=T0 + 5 * HOUR, end=T0 + 6 * HOUR).json()["id"], _new(c, _club(con, c.ids, "Debate")).json()["id"]
    assert _strip(c) == [soon, later]
    oid = _club(con, c.ids, "Fresh")
    for bad in ({"start": T0 + 2 * HOUR, "end": T0 + HOUR}, {"start": T0 - 2 * HOUR, "end": T0 - HOUR}, {"place": " "}, {"end": T0 + 15 * 86400}):
        assert _new(c, oid, **bad).status_code == 400


def test_cancel(env, monkeypatch):
    c, con, _, oid = _setup(env, monkeypatch)
    pid = _new(c, oid).json()["id"]
    assert c.post(f"/api/posts/{pid}/casting/cancel", headers=tma(STUDENT)).status_code == 403
    assert c.post(f"/api/posts/{pid}/casting/cancel", headers=tma(PRES)).json()["casting"]["cancelled"] is True
    assert _state(con, pid) == "cancelled" and _strip(c) == []
    assert _club_page(c, oid)[pid]["title"] == "Dance casting"  # the post stays, marked


def test_deleted_post_is_cancelled_on_the_club_page_until_its_end(env, monkeypatch):
    c, _, clock, oid = _setup(env, monkeypatch)
    pid = _new(c, oid).json()["id"]
    assert c.delete(f"/api/posts/{pid}", headers=tma(PRES)).status_code == 204
    assert _strip(c) == []
    feed = c.get("/api/posts", params={"scope": "all"}, headers=tma(STUDENT)).json()
    assert pid not in [p["id"] for p in feed]
    p = _club_page(c, oid)[pid]
    assert p["casting"] == {"from": T0 + HOUR, "to": T0 + 3 * HOUR, "place": "Room 305", "cancelled": True} and p["title"] == ""
    assert not p["canEdit"] and not _club_page(c, oid, PRES)[pid]["canDelete"]
    clock[0] = T0 + 3 * HOUR
    assert pid not in _club_page(c, oid)  # after its end it just goes


def test_moderators_takedown_just_goes(env, monkeypatch):
    c, _, _, oid = _setup(env, monkeypatch)
    pid = _new(c, oid).json()["id"]
    assert c.delete(f"/api/posts/{pid}", headers=tma(ADMIN)).status_code == 204
    assert pid not in _club_page(c, oid) and _strip(c) == []


def test_only_the_clubs_posters_create_it(env, monkeypatch):
    c, _, _, oid = _setup(env, monkeypatch)
    assert _new(c, oid, who=STUDENT).status_code == 403
    assert _new(c, oid, who=MEMBER).status_code == 403
    assert _new(c, oid, who=ADMIN).status_code == 403  # one interface: the app's staff are no club's posters


def test_small_club_is_off_the_strip_for_everyone(env, monkeypatch):
    c, _, _, oid = _setup(env, monkeypatch)
    pid = _new(c, oid).json()["id"]
    monkeypatch.setattr(logic.clubs, "CLUB_MIN", 5)
    assert _strip(c) == [] and _strip(c, PRES) == [] and _strip(c, ADMIN) == []
    assert pid in _club_page(c, oid)  # its own page still has it, as any post


def test_one_live_casting_per_club(env, monkeypatch):
    c, _, clock, oid = _setup(env, monkeypatch)
    first = _new(c, oid).json()["id"]
    assert _new(c, oid).status_code == 409
    c.post(f"/api/posts/{first}/casting/cancel", headers=tma(PRES))
    second = _new(c, oid).json()["id"]  # a cancelled one frees the place, and so does an ended one
    clock[0] = T0 + 3 * HOUR
    assert _new(c, oid, start=T0 + 4 * HOUR, end=T0 + 5 * HOUR).status_code == 200 and second != first


def test_a_club_before_the_collab_step_can_still_run_one(env, monkeypatch):
    c, con, _, _ = _setup(env, monkeypatch)
    oid = logic.create_org(con, None, "New initiative", "NI", "crown_3d", False)
    logic.set_role(con, None, c.ids[PRES], oid, "president", "test")
    plain = c.post(f"/api/orgs/{oid}/posts", headers=tma(PRES), json={"title": "Hello there", "body": "", "tag": None})
    assert plain.status_code == 403 and _new(c, oid).status_code == 200


def test_live_casting_is_cancelled_not_deleted(env, monkeypatch):
    c, _, _, oid = _setup(env, monkeypatch)
    p = _new(c, oid).json()
    assert p["canDelete"] is False and p["canEdit"] is True
    assert c.post(f"/api/posts/{p['id']}/casting/cancel", headers=tma(PRES)).json()["canDelete"] is True


def test_followers_outside_the_club_hear_it_once(env, monkeypatch):
    c, con, _, oid = _setup(env, monkeypatch)
    for tg in (STUDENT, MEMBER):
        con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, ?, 0)", (c.ids[tg], oid))
    pid = _new(c, oid).json()["id"]
    c.patch(f"/api/posts/{pid}", headers=tma(PRES), json={"casting": {"from": T0 + 2 * HOUR, "to": T0 + 4 * HOUR, "place": "Hall"}})
    sent = [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'casting_open'")]
    assert sent == [c.ids[STUDENT]]
