"""A club's report after its own event (logic/evreports.py, REPORTS=1): who reads and writes it (the "reports" right:
President, Vice, a role given it such as HR; never a plain member, an outsider, another club's President, the app's
admin), marks only for the club's team, only for the host club's started event, off means 404, and deleting an
account takes its marks and the link to who filled a report."""
from __future__ import annotations

import dataclasses
import time

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)
from test_team_guests import _uid


def _setup(env):
    """IT Club (1): tg 20 President, 11 Vice, 12 Head, 10 member, 13 an "HR" role with the reports right alone; tg 30
    President of Art (2); tg 40 nobody's. Events of IT: one started an hour ago, one tomorrow; Art's started."""
    c0, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, reports=True)))
    for tg, name in ((20, "pres"), (10, "ali"), (11, "bob"), (12, "cat"), (13, "dan"), (30, "eve"), (40, "fox")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'art', 'club', 'Art', 'Art', 'art_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 2, id, 'president', 0 FROM users WHERE tg_id = 30")
    for tg, role in ((10, "member"), (11, "vice"), (12, "head"), (13, "member")):
        logic.set_role(con, None, _uid(con, tg), 1, role, "test")
    # the Vice makes the HR role: a member-level role with the reports right (never ranks it above a member)
    r = c.post("/api/orgs/1/roles", headers=tma(11), json={"name": "HR", "color": "#3B6BFF", "rights": ["reports"]})
    assert r.status_code == 200, r.text
    hr = next(x for x in r.json()["roles"] if x["name"] == "HR")
    assert hr["level"] == "member"
    assert c.put(f"/api/orgs/1/roles/{hr['id']}/people", headers=tma(11), json={"users": [_uid(con, 13)]}).status_code == 200
    assert con.execute("SELECT role FROM org_members WHERE user_id = ?", (_uid(con, 13),)).fetchone()[0] == "member"
    t = int(time.time())

    def ev(org, start):
        return con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, created_at, updated_at)
            VALUES (?, 'published', 'Case', 'Hall', ?, ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (org, start, start + 7200)).lastrowid
    return c, c0, cfg, con, ev(1, t - 3600), ev(1, t + 86400), ev(2, t - 3600)


def _get(c, eid, tg):
    return c.get(f"/api/events/{eid}/report", headers=tma(tg))


def _mark(c, eid, tg, uid, status):
    return c.put(f"/api/events/{eid}/report/marks/{uid}", headers=tma(tg), json={"status": status})


def test_rights(env):
    c, _, _, con, eid, _, art = _setup(env)
    for tg, code in ((20, 200), (11, 200), (13, 200), (10, 403), (12, 403), (30, 403), (40, 403)):
        assert _get(c, eid, tg).status_code == code, tg
        assert c.patch(f"/api/events/{eid}/report", headers=tma(tg), json={"note": "ok"}).status_code == code, tg
    assert _get(c, art, 30).status_code == 200  # Art's own event
    assert _get(c, art, 20).status_code == 403  # another club's event: refused
    assert _get(c, 9999, 20).status_code == 404
    me = c.get("/api/me", headers=tma(13)).json()
    assert me["reports"] is True and "reports" in me["memberships"][0]["rights"]
    assert "reports" not in c.get("/api/me", headers=tma(12)).json()["memberships"][0]["rights"]  # a Head by level has none


def test_admin_never(env):
    c0, cfg = env
    c, _, _, con, eid, _, _ = _setup(env)
    a = TestClient(server.create(dataclasses.replace(cfg, reports=True, admins=frozenset({40}))))
    assert a.get(f"/api/events/{eid}/report", headers={**tma(40), "X-Staff-Event": str(eid)}).status_code == 403


def test_switch_off(env):
    c, c0, _, con, eid, _, _ = _setup(env)
    assert c0.get(f"/api/events/{eid}/report", headers=tma(20)).status_code == 404
    assert c0.patch(f"/api/events/{eid}/report", headers=tma(20), json={"note": "x"}).status_code == 404
    assert _mark(c0, eid, 20, _uid(con, 10), "present").status_code == 404
    assert "reports" not in c0.get("/api/me", headers=tma(20)).json()


def test_not_started(env):
    c, _, _, con, _, later, _ = _setup(env)
    r = _get(c, later, 20)
    assert r.status_code == 409 and r.json()["message"] == "not_started"
    con.execute("UPDATE events SET status = 'cancelled', starts_at = ? WHERE id = ?", (int(time.time()) - 60, later))
    assert _get(c, later, 20).status_code == 409


def test_fill_and_marks(env):
    c, _, _, con, eid, _, _ = _setup(env)
    empty = _get(c, eid, 20).json()
    assert empty["filledBy"] is None and empty["note"] == "" and empty["guests"] is None
    assert {p["person"]["id"] for p in empty["people"]} == {_uid(con, tg) for tg in (20, 10, 11, 12, 13)}
    # a department: HR's own; Ali and Bob in it
    tags = c.post("/api/orgs/1/tags", headers=tma(11), json={"name": "PR", "color": "#3B6BFF", "department": True}).json()["tags"]
    pr = tags[0]["id"]
    for tg in (10, 11):
        assert c.patch(f"/api/orgs/1/members/{_uid(con, tg)}", headers=tma(20), json={"addDept": pr}).status_code == 200
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at) SELECT ?, id, 'going', 't40', 0, 0, 1 FROM users WHERE tg_id = 40", (eid,))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) SELECT ?, id, 'going', 't30', 0, 0 FROM users WHERE tg_id = 30", (eid,))
    r = c.patch(f"/api/events/{eid}/report", headers=tma(13), json={"dept": pr, "guests": 42, "note": "  went well  "}).json()
    assert (r["dept"], r["guests"], r["note"], r["signed"], r["came"]) == (pr, 42, "went well", 2, 1)
    assert r["filledBy"]["id"] == _uid(con, 13) and r["editedBy"]["id"] == _uid(con, 13)
    assert [d["id"] for d in r["depts"]] == [pr]
    assert {p["person"]["id"] for p in r["people"] if pr in p["depts"]} == {_uid(con, 10), _uid(con, 11)}
    # marks: the team only; another club's person, a stranger, a bad status: no
    assert _mark(c, eid, 20, _uid(con, 10), "late").status_code == 200
    assert _mark(c, eid, 20, _uid(con, 12), "present").status_code == 200  # someone from the rest of the team, by hand
    assert _mark(c, eid, 20, _uid(con, 30), "present").status_code == 404
    assert _mark(c, eid, 20, _uid(con, 40), "present").status_code == 404
    assert _mark(c, eid, 20, _uid(con, 10), "asleep").status_code == 400
    r = _get(c, eid, 13).json()
    st = {p["person"]["id"]: p["status"] for p in r["people"]}
    assert st[_uid(con, 10)] == "late" and st[_uid(con, 12)] == "present" and st[_uid(con, 11)] is None
    assert r["filledBy"]["id"] == _uid(con, 13) and r["editedBy"]["id"] == _uid(con, 20)  # the last editor kept
    # bad input
    for body in ({"dept": 999}, {"guests": -1}, {"guests": "5"}, {"note": "x" * 1001}, {"dept": True}):
        assert c.patch(f"/api/events/{eid}/report", headers=tma(20), json=body).status_code == 400, body
    # one who left the team keeps their mark, can be cleared, can't be marked again
    logic.set_role(con, None, _uid(con, 12), 1, "none", "test")
    p = next(x for x in _get(c, eid, 20).json()["people"] if x["person"]["id"] == _uid(con, 12))
    assert p["team"] is False and p["status"] == "present"
    assert _mark(c, eid, 20, _uid(con, 12), "late").status_code == 404
    assert _mark(c, eid, 20, _uid(con, 12), None).status_code == 200
    assert _uid(con, 12) not in {x["person"]["id"] for x in _get(c, eid, 20).json()["people"]}


def test_account_deletion(env):
    c, _, cfg, con, eid, _, _ = _setup(env)
    assert _mark(c, eid, 13, _uid(con, 10), "absent").status_code == 200
    assert _mark(c, eid, 13, _uid(con, 13), "present").status_code == 200
    gone = _uid(con, 13)
    delete_now(c, cfg, tma(13))
    assert not con.execute("SELECT 1 FROM report_marks WHERE user_id = ?", (gone,)).fetchone()  # my marks go
    row = con.execute("SELECT filled_by, edited_by FROM event_reports WHERE event_id = ?", (eid,)).fetchone()
    assert tuple(row) == (None, None)  # the club's report stays, without me
    assert con.execute("SELECT status FROM report_marks WHERE user_id = ?", (_uid(con, 10),)).fetchone()[0] == "absent"
    r = _get(c, eid, 20).json()
    assert r["filledBy"] is None and r["editedBy"] is None


def test_vice_role_migration(env):
    """158: a Vice's role with its own toggles gets the reports right once, on a replay too."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, fixed, created_at) VALUES (1, 'Vice', '#7C4DFF', 'vice', 'team,money', 1, 0)")
    con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, created_at) VALUES (1, 'X', '#3B6BFF', 'head', 'events', 0)")
    sql = dict(db.MIGRATIONS)[158].split("UPDATE org_roles", 1)[1]
    for _ in range(2):
        con.execute("UPDATE org_roles" + sql)
    got = dict(con.execute("SELECT level, rights FROM org_roles WHERE org_id = 1 AND rights IS NOT NULL").fetchall())
    assert got == {"vice": "team,money,reports", "head": "events"}
