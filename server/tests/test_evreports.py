"""A club's report after its own event (logic/evreports.py, REPORTS=1): who reads and writes it (the "reports" right:
President, Vice, a role given it such as HR; never a plain member, an outsider, another club's President, the app's
admin), marks only for the club's team, only for the host club's started event, off means 404, and deleting an
account takes its marks and the link to who filled a report. The feature's own consent: without it no report and no
mark of me; withdrawing it takes my marks and author links, never the note."""
from __future__ import annotations

import dataclasses
import time

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)
from test_team_guests import _uid


def _agree(c, tg):
    return c.post("/api/reports/consent", headers=tma(tg), json={"consent": logic.evreports.CONSENT})


def _setup(env, agreed=(20, 10, 11, 12, 13, 30, 40)):
    """IT Club (1): tg 20 President, 11 Vice, 12 Head, 10 member, 13 an "HR" role with the reports right alone; tg 30
    President of Art (2); tg 40 nobody's. Events of IT: one started an hour ago, one tomorrow; Art's started.
    `agreed`: who has given the feature's consent (everyone by default)."""
    c0, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, reports=True)))
    for tg, name in ((20, "pres"), (10, "ali"), (11, "bob"), (12, "cat"), (13, "dan"), (30, "eve"), (40, "fox")):
        login(c, tg, name)
    for tg in agreed:
        assert _agree(c, tg).status_code == 200
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
    assert me["reports"] == {"consent": True} and "reports" in me["memberships"][0]["rights"]
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
    assert _agree(c0, 20).status_code == 404 and c0.delete("/api/reports/consent", headers=tma(20)).status_code == 404
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
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (gone,)).fetchone()  # my marks go
    row = con.execute("SELECT filled_by, edited_by FROM club_reports WHERE event_id = ?", (eid,)).fetchone()
    assert tuple(row) == (None, None)  # the club's report stays, without me
    assert con.execute("SELECT status FROM club_report_marks WHERE user_id = ?", (_uid(con, 10),)).fetchone()[0] == "absent"
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


def test_consent(env):
    """No consent of mine: every report route says so (the app asks then), the rest of the app works; given: works.
    A member without it is listed but can't be marked until they agree themselves."""
    c, _, _, con, eid, _, _ = _setup(env, agreed=(11,))
    for r in (_get(c, eid, 20), c.patch(f"/api/events/{eid}/report", headers=tma(20), json={"note": "x"}),
              _mark(c, eid, 20, _uid(con, 11), "present")):
        assert r.status_code == 403 and r.json()["message"] == "consent"
    me = c.get("/api/me", headers=tma(20))
    assert me.status_code == 200 and me.json()["reports"] == {"consent": False}
    assert c.get("/api/orgs/1/team", headers=tma(20)).status_code == 200  # Studio's team still opens
    assert c.post("/api/reports/consent", headers=tma(20), json={"consent": "old"}).status_code == 400
    assert _agree(c, 20).json() == {"consent": True}
    row = con.execute("SELECT version, at FROM report_consents WHERE user_id = ?", (_uid(con, 20),)).fetchone()
    assert row[0] == logic.evreports.CONSENT and row[1] > 0
    people = {p["person"]["id"]: p["consent"] for p in _get(c, eid, 20).json()["people"]}
    assert people[_uid(con, 10)] is False and people[_uid(con, 11)] is True
    r = _mark(c, eid, 20, _uid(con, 10), "present")
    assert r.status_code == 409 and r.json()["message"] == "no_consent"
    assert _mark(c, eid, 20, _uid(con, 11), "present").status_code == 200
    assert _agree(c, 10).status_code == 200  # a plain member gives their own (no reports right needed)
    assert _mark(c, eid, 20, _uid(con, 10), "late").status_code == 200


def test_withdraw(env):
    """Taking it back: my marks go from every report, my name off what I filled or edited, the note stays; marked
    again only after a new yes; the account stays."""
    c, _, _, con, eid, _, art = _setup(env)
    hr = _uid(con, 13)
    assert c.patch(f"/api/events/{eid}/report", headers=tma(13), json={"note": "went well"}).status_code == 200
    assert _mark(c, eid, 20, hr, "present").status_code == 200
    assert _mark(c, eid, 20, _uid(con, 10), "absent").status_code == 200
    assert _mark(c, eid, 13, _uid(con, 11), "late").status_code == 200  # HR is the last editor now
    assert c.delete("/api/reports/consent", headers=tma(13)).json() == {"consent": False}
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (hr,)).fetchone()
    assert not con.execute("SELECT 1 FROM report_consents WHERE user_id = ?", (hr,)).fetchone()
    row = con.execute("SELECT filled_by, edited_by, note FROM club_reports WHERE event_id = ?", (eid,)).fetchone()
    assert tuple(row) == (None, None, "went well")
    assert con.execute("SELECT COUNT(*) FROM club_report_marks WHERE event_id = ?", (eid,)).fetchone()[0] == 2  # the others' stay
    assert _mark(c, eid, 20, hr, "present").json()["message"] == "no_consent"
    assert _get(c, eid, 13).json()["message"] == "consent"
    assert c.get("/api/me", headers=tma(13)).status_code == 200  # no account deleted
    assert _agree(c, 13).status_code == 200 and _mark(c, eid, 20, hr, "present").status_code == 200


def test_account_deletion_takes_consent(env):
    c, _, cfg, con, _, _, _ = _setup(env)
    gone = _uid(con, 10)
    assert ("report_consents", "user_id") in logic._DEL_GONE
    delete_now(c, cfg, tma(10))
    assert not con.execute("SELECT 1 FROM report_consents WHERE user_id = ?", (gone,)).fetchone()


def _cohost(c, con, eid, status="accepted"):
    """Art (2) co-hosts IT's started event; Art's HR is tg 41 (a member-level role with the reports right), and tg 10
    is in both clubs (IT's member, Art's member)."""
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, 2, ?, 0)", (eid, status))
    login(c, 41, "gus")
    assert _agree(c, 41).status_code == 200
    for tg in (41, 10):
        logic.set_role(con, None, _uid(con, tg), 2, "member", "test")
    r = c.post("/api/orgs/2/roles", headers=tma(30), json={"name": "HR", "color": "#3B6BFF", "rights": ["reports"]}).json()
    hr = next(x for x in r["roles"] if x["name"] == "HR")
    assert c.put(f"/api/orgs/2/roles/{hr['id']}/people", headers=tma(30), json={"users": [_uid(con, 41)]}).status_code == 200


def _co(c, eid, tg, method="get", **kw):
    return getattr(c, method)(f"/api/events/{eid}/report", headers=tma(tg), params={"org": 2}, **kw)


def test_cohost_writes_its_own(env):
    """The co-host's HR reads and writes Art's own report: its department, its team, its count and note; the host's
    report is another one, and neither club's reporters reach the other's."""
    c, _, _, con, eid, _, _ = _setup(env)
    _cohost(c, con, eid)
    art = c.post("/api/orgs/2/tags", headers=tma(30), json={"name": "Senate", "color": "#3B6BFF", "department": True}).json()["tags"][0]["id"]
    it = c.post("/api/orgs/1/tags", headers=tma(11), json={"name": "PR", "color": "#3B6BFF", "department": True}).json()["tags"][0]["id"]
    empty = _co(c, eid, 41).json()
    assert [d["id"] for d in empty["depts"]] == [art] and empty["filledBy"] is None
    assert {p["person"]["id"] for p in empty["people"]} == {_uid(con, tg) for tg in (30, 41, 10)}  # Art's team only
    r = _co(c, eid, 41, "patch", json={"dept": art, "guests": 7, "note": "senate ran it"}).json()
    assert (r["dept"], r["guests"], r["note"], r["filledBy"]["id"]) == (art, 7, "senate ran it", _uid(con, 41))
    assert _co(c, eid, 41, "patch", json={"dept": it}).status_code == 400  # the host's department isn't ours
    assert c.patch(f"/api/events/{eid}/report", headers=tma(13), json={"note": "it ran it"}).status_code == 200
    host = _get(c, eid, 20).json()
    assert host["note"] == "it ran it" and host["guests"] is None and host["filledBy"]["id"] == _uid(con, 13)
    assert _co(c, eid, 30).json()["note"] == "senate ran it"
    # never the other club's: the host's reporters can't open Art's, Art's can't open the host's; a plain member neither
    for tg in (20, 11, 13):
        assert _co(c, eid, tg).status_code == 403, tg
        assert _co(c, eid, tg, "patch", json={"note": "x"}).status_code == 403, tg
    for tg in (30, 41):
        assert _get(c, eid, tg).status_code == 403, tg
        assert _mark(c, eid, tg, _uid(con, 10), "present").status_code == 403, tg
    assert _co(c, eid, 10).status_code == 403
    assert c.get(f"/api/events/{eid}/report", headers=tma(30), params={"org": 9999}).status_code == 403
    # marks: Art's team only; someone in both clubs is marked in each report on their own
    url = f"/api/events/{eid}/report/marks/"
    assert c.put(url + str(_uid(con, 12)), headers=tma(41), params={"org": 2}, json={"status": "present"}).status_code == 404  # IT's Head
    assert c.put(url + str(_uid(con, 10)), headers=tma(41), params={"org": 2}, json={"status": "absent"}).status_code == 200
    assert _mark(c, eid, 13, _uid(con, 10), "present").status_code == 200
    st = lambda r: {p["person"]["id"]: p["status"] for p in r["people"]}  # noqa: E731
    assert st(_co(c, eid, 41).json())[_uid(con, 10)] == "absent"
    assert st(_get(c, eid, 13).json())[_uid(con, 10)] == "present"
    assert c.put(url + str(_uid(con, 10)), headers=tma(41), params={"org": 2}, json={"status": None}).status_code == 200
    assert st(_get(c, eid, 13).json())[_uid(con, 10)] == "present"  # clearing Art's mark leaves IT's
    assert _uid(con, 10) in st(_co(c, eid, 41).json())  # still on Art's team, unmarked
    # leaving a club takes nobody's mark from the other's report; a person's withdrawal takes both
    assert c.put(url + str(_uid(con, 10)), headers=tma(41), params={"org": 2}, json={"status": "late"}).status_code == 200
    assert c.delete("/api/reports/consent", headers=tma(10)).status_code == 200
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (_uid(con, 10),)).fetchone()


def test_cohost_not_accepted_gets_nothing(env):
    """A pending or declined co-host has no report; one removed later loses its report (no data without a reader)."""
    c, _, _, con, eid, _, _ = _setup(env)
    _cohost(c, con, eid, "pending")
    for status in ("pending", "declined"):
        con.execute("UPDATE event_cohosts SET status = ? WHERE event_id = ?", (status, eid))
        for tg in (30, 41):
            assert _co(c, eid, tg).status_code == 403, (status, tg)
            assert _co(c, eid, tg, "patch", json={"note": "x"}).status_code == 403, (status, tg)
    con.execute("UPDATE event_cohosts SET status = 'accepted' WHERE event_id = ?", (eid,))
    assert _co(c, eid, 41, "patch", json={"note": "ours"}).status_code == 200
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 2")  # a co-host club no longer shown: none either
    assert _co(c, eid, 41).status_code == 403
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 2")
    # the co-hosting ends (cohosts.end): the club's report goes with it, marks too; the host's own stays
    assert c.put(f"/api/events/{eid}/report/marks/{_uid(con, 20)}", headers=tma(20), json={"status": "present"}).status_code == 200
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(20)).status_code == 204
    assert _co(c, eid, 41).status_code == 403
    assert not con.execute("SELECT 1 FROM club_reports WHERE event_id = ? AND org_id = 2", (eid,)).fetchone()
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE event_id = ? AND org_id = 2", (eid,)).fetchone()
    assert con.execute("SELECT 1 FROM club_report_marks WHERE event_id = ? AND org_id = 1", (eid,)).fetchone()


def test_cohost_switch_off_and_deletion(env):
    c, c0, cfg, con, eid, _, _ = _setup(env)
    _cohost(c, con, eid)
    assert _co(c0, eid, 41).status_code == 404
    assert _co(c0, eid, 41, "patch", json={"note": "x"}).status_code == 404
    url = f"/api/events/{eid}/report/marks/{_uid(con, 10)}"
    assert c0.put(url, headers=tma(41), params={"org": 2}, json={"status": "present"}).status_code == 404
    assert c.put(url, headers=tma(41), params={"org": 2}, json={"status": "present"}).status_code == 200
    assert _mark(c, eid, 20, _uid(con, 10), "late").status_code == 200
    gone = _uid(con, 10)
    delete_now(c, cfg, tma(10))  # someone in both clubs: their marks go from both reports
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (gone,)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM club_reports WHERE event_id = ?", (eid,)).fetchone()[0] == 2  # the reports stay
    hr = _uid(con, 41)
    delete_now(c, cfg, tma(41))
    assert tuple(con.execute("SELECT filled_by, edited_by FROM club_reports WHERE org_id = 2").fetchone()) == (None, None)
    assert hr not in {p["person"]["id"] for p in _co(c, eid, 30).json()["people"]}


def test_migration_keeps_reports_as_the_hosts(env):
    """160: 158's reports and marks move over as the host's; 158's tables go."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO users (id, tg_id, created_at, seen_at) VALUES (500, 500, 0, 0), (501, 501, 0, 0)")
    eid = con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (1, 'published', 'Case', 'Hall', 0, 'laptop_3d', '#3B6BFF', 0, 0)""").lastrowid
    con.execute("DROP TABLE club_report_marks")
    con.execute("DROP TABLE club_reports")
    con.executescript("BEGIN;" + dict(db.MIGRATIONS)[158].split("UPDATE org_roles", 1)[0] + "COMMIT;")
    con.execute("INSERT INTO event_reports (event_id, guests, note, filled_by, filled_at, edited_by, edited_at) VALUES (?, 5, 'kept', 500, 1, 501, 2)", (eid,))
    con.execute("INSERT INTO report_marks (event_id, user_id, status) VALUES (?, 500, 'late'), (?, 501, 'present')", (eid, eid))
    con.executescript("BEGIN;" + dict(db.MIGRATIONS)[160] + "COMMIT;")
    assert [tuple(r) for r in con.execute("SELECT event_id, org_id, guests, note, filled_by, filled_at, edited_by, edited_at FROM club_reports")] \
        == [(eid, 1, 5, "kept", 500, 1, 501, 2)]
    assert sorted(tuple(r) for r in con.execute("SELECT event_id, org_id, user_id, status FROM club_report_marks")) \
        == [(eid, 1, 500, "late"), (eid, 1, 501, "present")]
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name IN ('event_reports', 'report_marks')").fetchone()
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
