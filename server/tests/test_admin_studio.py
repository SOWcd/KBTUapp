"""The creator opens any club's whole Studio from Admin (owner, Nov 15; X-Staff-Org, app.viewer): its President's every
route of the club and of its events, each in the owner's log; the Kaspi payee his to set; never its reports, its end or
hand-over; every other admin keeps the draft's routes alone, a moderator nothing."""
from __future__ import annotations

import json

from kbtu import db
from test_admin_create_event import _body, _org
from test_admin_full import _full_setup
from test_core import tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)


def _studio(con) -> list:
    return [(a, t, json.loads(d)) for a, t, d in con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'staff_studio' ORDER BY id")]


def test_creator_runs_a_clubs_studio(env):
    c, con, ids = _full_setup(env)
    # his Studio: the President's membership, each level's rights for "view as", never reports
    lent = c.get("/api/orgs/1/lent", headers=_org(60)).json()
    assert lent["membership"]["role"] == "president" and "team" in lent["membership"]["rights"] and "reports" not in lent["membership"]["rights"]
    roles = {r["key"]: r for r in lent["roles"]}
    assert list(roles)[:4] == ["president", "vice", "head", "member"] and "team" not in roles["head"]["rights"] and "events" in roles["head"]["rights"]
    # a write on a club he isn't in: its profile, a role, the team link; a list of people: each logged
    assert c.patch("/api/orgs/1", headers=_org(60), json={"recruiting": False}).status_code == 200
    assert con.execute("SELECT recruiting FROM orgs WHERE id = 1").fetchone()[0] == 0
    assert c.patch("/api/orgs/1", headers=_org(60), json={"slug": "bossclub"}).status_code == 200  # the President's own
    assert c.get("/api/orgs/1/members", headers=_org(60)).status_code == 200
    link = c.post("/api/orgs/1/team-link", headers=_org(60))
    assert link.status_code == 200, link.text
    # one of the club's events through the same header: as its President
    assert c.get("/api/events/1/attendees", headers=_org(60)).status_code == 200
    assert c.post("/api/events/1/chat", headers=_org(60)).status_code == 200
    done = {d["do"] for _, _, d in _studio(con)}
    assert done >= {"PATCH /api/orgs/{oid}", "GET /api/orgs/{oid}/members", "POST /api/orgs/{oid}/team-link", "GET /api/events/{eid}/attendees"}
    assert all(a == ids["boss"] and t == "org:1" for a, t, _ in _studio(con))
    assert ("GET /api/orgs/{oid}/lent" not in done) and not con.execute("SELECT 1 FROM org_members WHERE user_id = ?", (ids["boss"],)).fetchone()
    # never another club's event, the club's end or hand-over, his own ticket, nor its reports
    assert c.get("/api/events/2/attendees", headers=_org(60)).status_code == 403
    assert c.delete("/api/orgs/1", headers=_org(60)).status_code == 403
    assert c.post("/api/orgs/1/transfer", headers=_org(60), json={"userId": ids["ali"]}).status_code == 403
    assert c.post("/api/events/1/registration", headers=_org(60), json={}).status_code == 403
    assert c.get("/api/events/1/report", headers=_org(60)).status_code in (403, 404)


def test_others_get_nothing_new(env):
    c, con, ids = _full_setup(env)
    for uid in (65, 61, 63, 64):  # another admin, a moderator, a student, another club's President
        assert c.patch("/api/orgs/1", headers=_org(uid), json={"recruiting": False}).status_code == 403
        assert c.get("/api/orgs/1/members", headers=_org(uid)).status_code == 403
        assert c.get("/api/orgs/1/lent", headers=_org(uid)).status_code == 403
        assert c.get("/api/events/1/attendees", headers=_org(uid)).status_code == 403
    assert c.get("/api/orgs/1/lent", headers=tma(60)).status_code == 403  # no header: nothing lent
    assert con.execute("SELECT recruiting FROM orgs WHERE id = 1").fetchone()[0] == 1 and not _studio(con)


def test_creator_sets_the_kaspi_payee(env):
    c, con, ids = _full_setup(env)
    pay = {"price": 500, "payToName": "Dana S", "payPhone": "87011234567"}
    # no details yet: he types them; then changes them as a President may
    e = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**pay)).json()
    assert (e["payToName"], e["payPhone"]) == ("Dana S", "+77011234567")
    r = c.patch(f"/api/events/{e['id']}", headers=_org(60), json=_body(**pay | {"payToName": "Aru K"}))
    assert r.status_code == 200 and r.json()["payToName"] == "Aru K"
    lines = [(t, json.loads(d)) for t, d in con.execute("SELECT target, data FROM audit_log WHERE action = 'staff_kaspi' ORDER BY id")]
    assert lines == [("org:1", {"event": None, "changed": ["name", "phone"]}),
                     ("org:1", {"event": e["id"], "changed": ["name"]})]
    old = {"event": e["id"], "was": {"name": "Dana S", "phone": "+77011234567"}, "now": {"name": "Aru K", "phone": "+77011234567"}}
    log_id = con.execute("INSERT INTO audit_log (action, target, data, at) VALUES ('staff_kaspi', 'org:1', ?, 0)", (json.dumps(old),)).lastrowid
    con.executescript(dict(db.MIGRATIONS)[231])
    assert json.loads(con.execute("SELECT data FROM audit_log WHERE id = ?", (log_id,)).fetchone()[0]) == {"event": e["id"]}
    # once someone paid, fixed for him as for anyone
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', 'TCK9', 0, 0)", (e["id"], ids["ali"]))
    con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, created_at) VALUES (900, 'x', 'receipt', 'image/webp', 1, 'r/x', 0)")
    con.execute("""INSERT INTO receipts (registration_id, file_id, via, amount, receipt_no, recipient_name, created_at)
        VALUES ((SELECT id FROM registrations WHERE event_id = ?), 900, 'app', 500, 'R-1', 'Aru K', 0)""", (e["id"],))
    assert c.patch(f"/api/events/{e['id']}", headers=_org(60), json=_body(**pay)).status_code == 409
    # another admin: never the money
    r = c.post("/api/orgs/1/events", headers=_org(65), json=_body(**pay))
    assert (r.status_code, r.json()["message"]) == (403, "price")


def test_view_as_is_enforced(env):
    """His "view as" (X-Staff-Role): what that role may do works, nothing more; a club's own role by its toggles; logged."""
    c, con, ids = _full_setup(env)
    rid = con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, created_at) VALUES (1, 'Vice-head', '#000000', 'head', 'events', 0)").lastrowid
    assert any(r["key"] == f"r{rid}" and r["level"] == "head" and r["rights"] == ["door", "events"] for r in c.get("/api/orgs/1/lent", headers=_org(60)).json()["roles"])
    as_ = lambda role: {**_org(60), "X-Staff-Role": role}  # noqa: E731
    assert c.patch("/api/orgs/1", headers=as_("vice"), json={"recruiting": False}).status_code == 200
    assert c.patch("/api/orgs/1", headers=as_("vice"), json={"slug": "bossclub"}).status_code == 403  # the President's own
    for role in ("head", "member", f"r{rid}"):
        assert c.patch("/api/orgs/1", headers=as_(role), json={"recruiting": True}).status_code == 403, role
    assert c.get("/api/events/1/attendees", headers=as_(f"r{rid}")).status_code == 200
    assert c.get("/api/events/1/attendees", headers=as_("member")).status_code == 403
    assert c.patch("/api/events/1", headers=as_("member"), json=_body()).status_code == 403
    assert c.patch("/api/orgs/1", headers=as_("r99999"), json={"recruiting": True}).status_code == 403  # not this club's role
    assert {"as": "vice"}.items() <= _studio(con)[0][2].items()


def test_his_own_actions_stay_his(env):
    """Saving, volunteering, a team, a rating, a seat on the club's event: his as any student's, never lent; the header refused there."""
    c, con, ids = _full_setup(env)
    for method, path in (("PUT", "/api/events/1/saved"), ("POST", "/api/events/1/volunteer"), ("POST", "/api/events/1/team"),
                         ("POST", "/api/events/1/team/join"), ("POST", "/api/events/1/team-ask"), ("POST", "/api/events/1/decline"),
                         ("PUT", "/api/events/1/rating"), ("POST", "/api/events/1/seats"), ("POST", "/api/events/1/invites")):
        assert c.request(method, path, headers=_org(60), json={}).status_code == 403, path
    assert c.put("/api/events/1/saved", headers=tma(60)).status_code == 204  # as himself
    assert not _studio(con)


def test_creator_on_the_event_path_is_always_logged(env):
    """X-Staff-Event from Admin: every request of his but the card in the log, even one decided by role_in alone (the door helpers)."""
    from test_admin_events import _as
    c, con, ids = _full_setup(env)
    assert c.put("/api/events/1/crew", headers=_as(60), json={"userId": ids["mod"], "kind": "scan"}).status_code == 200
    assert c.get("/api/events/1", headers=_as(60)).status_code == 200
    done = [json.loads(d)["do"] for (d,) in con.execute("SELECT data FROM audit_log WHERE action = 'staff_event'")]
    assert done == ["PUT /api/events/{eid}/crew"]


def test_creator_gives_roles(env):
    """Roles from the lent Studio (Codex's review, Nov 16: every one was refused, his own absent membership was read):
    the creator gives any level below President; viewed as a Head he gives none."""
    c, con, ids = _full_setup(env)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (ids["ali"],))
    url = f"/api/orgs/1/members/{ids['ali']}"
    assert c.patch(url, headers={**_org(60), "X-Staff-Role": "head"}, json={"role": "head", "roleId": None}).status_code == 403
    for role in ("head", "vice", "member"):
        assert c.patch(url, headers=_org(60), json={"role": role, "roleId": None}).status_code == 200, role
        assert con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (ids["ali"],)).fetchone()[0] == role
    assert c.patch(url, headers=_org(60), json={"role": "president", "roleId": None}).status_code == 403
    assert c.patch(url, headers=tma(60), json={"role": "head", "roleId": None}).status_code == 403  # no header: nothing lent


def test_creator_runs_a_clubs_recruitment(env):
    """Recruitment routes are keyed by a round, an application or a slot, not the club: lent for its own club only."""
    c, con, ids = _full_setup(env)
    con.execute("INSERT INTO rounds (id, org_id, title, closes_at, created_at) VALUES (7, 1, 'r', 9999999999, 1), (8, 2, 'r', 9999999999, 1)")
    con.execute("INSERT INTO round_slots (id, round_id, starts_at, minutes) VALUES (5, 7, 9999999000, 15), (6, 8, 9999999000, 15)")
    assert c.get("/api/rounds/7/apps", headers=_org(60)).status_code == 200
    assert c.get("/api/rounds/7/slots", headers=_org(60)).status_code == 200
    assert "GET /api/rounds/{rid}/apps" in {d["do"] for _, _, d in _studio(con)}
    # another club's round or slot, his own application: never
    assert c.get("/api/rounds/8/apps", headers=_org(60)).status_code == 403
    assert c.delete("/api/round-slots/6", headers=_org(60)).status_code == 403
    assert c.post("/api/rounds/7/apply", headers=_org(60), json={}).status_code == 403
    assert c.get("/api/rounds/7/apps", headers=_org(65)).status_code == 403  # another admin
