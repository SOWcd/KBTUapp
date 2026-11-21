"""A club's report after its own event (logic/evreports.py, REPORTS=1): who reads and writes it (the "reports" right:
President, Vice, a role given it such as HR; never a plain member, an outsider, another club's President, the app's
admin), marks only for the club's team, only for the host club's started event, off means 404, and deleting an
account takes its marks and the link to who filled a report. The feature's own consent: without it no report and no
mark of me; withdrawing it takes my marks and author links, never the note."""
from __future__ import annotations

import codecs
import csv
import dataclasses
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
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


def _mark(c, eid, tg, uid, status, **fields):
    return c.put(f"/api/events/{eid}/report/marks/{uid}", headers=tma(tg), json={"status": status, **fields})


def _comment(c, eid, tg, uid, comment):
    return c.put(f"/api/events/{eid}/report/marks/{uid}", headers=tma(tg), json={"comment": comment})


def _export(c, oid, tg, **headers):
    return c.post(f"/api/orgs/{oid}/reports/export", headers={**tma(tg), **headers})


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
    a = TestClient(server.create(dataclasses.replace(cfg, reports=True, admins=frozenset({13, 40}))))
    assert _mark(c, eid, 13, _uid(con, 10), "present", comment="Checked guests in").status_code == 200
    assert a.get(f"/api/events/{eid}/report", headers={**tma(40), "X-Staff-Event": str(eid)}).status_code == 403
    assert a.get(f"/api/events/{eid}/report", headers={**tma(13), "X-Staff-Event": str(eid)}).status_code == 403
    assert _get(a, eid, 13).status_code == 200  # their own club role still applies


def test_switch_off(env):
    c, c0, _, con, eid, _, _ = _setup(env)
    assert c0.get(f"/api/events/{eid}/report", headers=tma(20)).status_code == 404
    assert c0.patch(f"/api/events/{eid}/report", headers=tma(20), json={"note": "x"}).status_code == 404
    assert _mark(c0, eid, 20, _uid(con, 10), "present").status_code == 404
    assert _agree(c0, 20).status_code == 404 and c0.delete("/api/reports/consent", headers=tma(20)).status_code == 404
    assert _export(c0, 1, 20).status_code == 404
    assert {"reports", "reportLog"}.isdisjoint(c0.get("/api/me", headers=tma(20)).json())


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


def test_comments_follow_the_mark(env, monkeypatch):
    c, _, _, con, eid, _, _ = _setup(env)
    uid = _uid(con, 10)
    now = int(time.time())
    monkeypatch.setattr(logic.core, "now", lambda: now)
    comment = "<b>Checked guests in</b>"
    r = _mark(c, eid, 13, uid, "present", comment=f"  {comment}  ")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "private, no-store"
    assert next(p["comment"] for p in r.json()["people"] if p["person"]["id"] == uid) == comment
    assert _mark(c, eid, 20, uid, "late").status_code == 200
    assert _comment(c, eid, 10, uid, "Self edit").status_code == 403
    assert _comment(c, eid, 30, uid, "Other club").status_code == 403
    for invalid in (None, False, ["x"], "x" * 301, " " * 301, "text\0more"):
        assert _comment(c, eid, 20, uid, invalid).status_code == 400
    new = "\U0001f44b" * 300
    now += 60
    assert _comment(c, eid, 20, uid, new).status_code == 200
    row = con.execute("""SELECT status, comment, comment_by, comment_at, comment_edited_by, comment_edited_at
        FROM club_report_marks WHERE user_id = ?""", (uid,)).fetchone()
    assert tuple(row) == ("late", new, _uid(con, 13), now - 60, _uid(con, 20), now)
    assert _comment(c, eid, 20, uid, "").status_code == 200
    row = con.execute("SELECT comment, comment_by, comment_at FROM club_report_marks WHERE user_id = ?", (uid,)).fetchone()
    assert tuple(row) == ("", None, None)
    assert _mark(c, eid, 20, uid, "absent", comment="Setup duty").status_code == 200
    logic.set_role(con, None, uid, 1, "none", "test")
    assert _comment(c, eid, 20, uid, "New note after leaving").status_code == 404
    r = _comment(c, eid, 20, uid, "")
    assert r.status_code == 200
    p = next(p for p in r.json()["people"] if p["person"]["id"] == uid)
    assert (p["team"], p["status"], p["comment"]) == (False, "absent", "")
    assert _comment(c, eid, 20, uid, "Add a note after leaving").status_code == 404
    assert _mark(c, eid, 20, uid, None).status_code == 200
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (uid,)).fetchone()


def test_own_log_is_private_and_keeps_former_members(env):
    c, _, _, con, eid, later, _ = _setup(env)
    ali, bob = _uid(con, 10), _uid(con, 11)
    start = con.execute("SELECT starts_at FROM events WHERE id = ?", (eid,)).fetchone()[0]
    con.execute("UPDATE events SET starts_at = ?, title = 'The next event' WHERE id = ?", (start + 60, later))
    assert _mark(c, eid, 13, ali, "present", comment="Watched the floor").status_code == 200
    assert _mark(c, later, 13, ali, "late", comment="Closed the hall").status_code == 200
    assert _mark(c, eid, 13, bob, "excused", comment="Other member").status_code == 200
    logic.set_role(con, None, ali, 1, "none", "test")
    r = c.get("/api/me", headers=tma(10), params={"user": bob})
    assert r.headers["Cache-Control"] == "private, no-store"
    assert r.json()["reportLog"] == [
        {"event": later, "org": 1, "club": "IT Club", "title": "The next event", "date": start + 60, "status": "late", "comment": "Closed the hall"},
        {"event": eid, "org": 1, "club": "IT Club", "title": "Case", "date": start, "status": "present", "comment": "Watched the floor"},
    ]
    assert [entry["comment"] for entry in c.get("/api/me", headers=tma(11), params={"user": ali}).json()["reportLog"]] == ["Other member"]
    r = c.get("/api/me", headers=tma(10), params={"reportLog": False})
    assert "reportLog" not in r.json() and r.json()["reports"] == {"consent": True}
    for tg in (12, 13, 20, 30, 40):
        assert c.get("/api/me", headers=tma(tg), params={"user": ali}).json()["reportLog"] == []
    assert c.get("/api/me", params={"user": ali}).status_code == 403
    assert _get(c, eid, 10).status_code == 403


def test_account_deletion(env):
    c, _, cfg, con, eid, _, _ = _setup(env)
    assert _mark(c, eid, 13, _uid(con, 10), "absent", comment="Ali's entry").status_code == 200
    assert _mark(c, eid, 13, _uid(con, 13), "present", comment="HR's entry").status_code == 200
    gone = _uid(con, 13)
    restored = Path(cfg.db_path).with_name("before-report-erasure.db")
    con.execute("VACUUM INTO ?", (str(restored),))
    delete_now(c, cfg, tma(13))
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (gone,)).fetchone()  # my marks go
    row = con.execute("SELECT filled_by, edited_by FROM club_reports WHERE event_id = ?", (eid,)).fetchone()
    assert tuple(row) == (None, None)  # the club's report stays, without me
    server.create(dataclasses.replace(cfg, db_path=str(restored)))
    replayed = db.connect(str(restored))
    for copy in (con, replayed):
        marks = copy.execute("SELECT status, comment, comment_by, comment_edited_by FROM club_report_marks").fetchall()
        assert [tuple(m) for m in marks] == [("absent", "Ali's entry", None, None)]
    replayed.close()
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
    """The old marks-only consent leaves marks stored, hidden until each person accepts the new version."""
    c, _, _, con, eid, _, _ = _setup(env, agreed=(10, 11, 20))
    ali, pres = _uid(con, 10), _uid(con, 20)
    assert _mark(c, eid, 20, ali, "present").status_code == 200
    con.execute("UPDATE report_consents SET version = 'evr1' WHERE user_id IN (?, ?)", (ali, pres))
    for r in (_get(c, eid, 20), c.patch(f"/api/events/{eid}/report", headers=tma(20), json={"note": "x"}),
              _mark(c, eid, 20, _uid(con, 11), "present"), _export(c, 1, 20)):
        assert r.status_code == 403 and r.json()["message"] == "report_consent"
    me = c.get("/api/me", headers=tma(20))
    assert me.status_code == 200 and me.json()["reports"] == {"consent": False, "legacy": True}
    assert c.get("/api/me", headers=tma(10)).json()["reportLog"] == []
    assert c.get("/api/orgs/1/team", headers=tma(20)).status_code == 200  # Studio's team still opens
    assert c.post("/api/reports/consent", headers=tma(20), json={"consent": "evr1"}).status_code == 400
    assert _agree(c, 20).json() == {"consent": True, "reportLog": []}
    row = con.execute("SELECT version, at FROM report_consents WHERE user_id = ?", (pres,)).fetchone()
    assert row[0] == "evr2" and row[1] > 0
    report = _get(c, eid, 20).json()
    people = {p["person"]["id"]: p for p in report["people"]}
    assert people[ali]["consent"] is False and people[ali]["status"] is None
    assert people[_uid(con, 11)]["consent"] is True
    r = _mark(c, eid, 20, ali, "present")
    assert r.status_code == 409 and r.json()["message"] == "no_consent"
    assert _mark(c, eid, 20, _uid(con, 11), "present").status_code == 200
    r = _agree(c, 10)  # a plain member gives their own (no reports right needed)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "private, no-store"
    assert r.json()["reportLog"][0]["status"] == "present"
    assert _mark(c, eid, 11, ali, "late").status_code == 200
    bob = _uid(con, 11)
    con.execute("UPDATE report_consents SET version = 'evr1' WHERE user_id = ?", (bob,))
    assert _get(c, eid, 20).json()["editedBy"] is None
    assert c.delete("/api/reports/consent", headers=tma(11)).json() == {"consent": False}
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (bob,)).fetchone()


def test_withdraw(env):
    """Taking it back: my marks go from every report, my name off what I filled or edited, the note stays; marked
    again only after a new yes; the account stays."""
    c, _, cfg, con, eid, _, _ = _setup(env)
    hr = _uid(con, 13)
    assert c.patch(f"/api/events/{eid}/report", headers=tma(13), json={"note": "went well"}).status_code == 200
    assert _mark(c, eid, 20, hr, "present", comment="Own entry").status_code == 200
    assert _mark(c, eid, 20, _uid(con, 10), "absent").status_code == 200
    assert _mark(c, eid, 13, _uid(con, 11), "late", comment="Someone else's entry").status_code == 200
    assert c.get("/api/me", headers=tma(13)).json()["reportLog"][0]["comment"] == "Own entry"
    restored = Path(cfg.db_path).with_name("before-report-withdrawal.db")
    con.execute("VACUUM INTO ?", (str(restored),))
    assert c.delete("/api/reports/consent", headers=tma(13)).json() == {"consent": False}
    assert not con.execute("SELECT 1 FROM club_report_marks WHERE user_id = ?", (hr,)).fetchone()
    assert not con.execute("SELECT 1 FROM report_consents WHERE user_id = ?", (hr,)).fetchone()
    row = con.execute("SELECT filled_by, edited_by, note FROM club_reports WHERE event_id = ?", (eid,)).fetchone()
    assert tuple(row) == (None, None, "went well")
    assert con.execute("SELECT COUNT(*) FROM club_report_marks WHERE event_id = ?", (eid,)).fetchone()[0] == 2  # the others' stay
    assert _mark(c, eid, 20, hr, "present").json()["message"] == "no_consent"
    assert _get(c, eid, 13).json()["message"] == "report_consent"
    assert c.get("/api/me", headers=tma(13)).json()["reportLog"] == []
    row = con.execute("SELECT comment, comment_by, comment_edited_by FROM club_report_marks WHERE user_id = ?", (_uid(con, 11),)).fetchone()
    assert tuple(row) == ("Someone else's entry", None, None)
    assert _agree(c, 13).status_code == 200
    assert c.get("/api/me", headers=tma(13)).json()["reportLog"] == []
    assert _mark(c, eid, 20, hr, "present").status_code == 200
    # Reopening an older snapshot replays only the withdrawal, and leaves the person's account intact.
    rewound = TestClient(server.create(dataclasses.replace(cfg, db_path=str(restored), reports=True)))
    me = rewound.get("/api/me", headers=tma(13)).json()
    assert me["student"] and me["reports"] == {"consent": False} and me["reportLog"] == []
    with db.connect(str(restored)) as rcon:
        restored_mark = rcon.execute("SELECT comment, comment_by, comment_edited_by FROM club_report_marks WHERE user_id = ?", (_uid(con, 11),)).fetchone()
        assert tuple(restored_mark) == ("Someone else's entry", None, None)
    current = TestClient(server.create(dataclasses.replace(cfg, reports=True)))
    assert current.get("/api/me", headers=tma(13)).json()["reportLog"][0]["status"] == "present"


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


def test_team_log_export(env, monkeypatch):
    c, _, cfg, con, eid, later, art = _setup(env)
    _cohost(c, con, eid)
    ali, bob, hr = (_uid(con, tg) for tg in (10, 11, 13))
    start = int(datetime(2025, 1, 1, 20, tzinfo=UTC).timestamp())
    con.execute("UPDATE events SET title = '=Case', starts_at = ? WHERE id = ?", (start, eid))
    con.execute("UPDATE events SET title = 'Next', starts_at = ? WHERE id = ?", (start + 86400, later))
    con.execute("UPDATE users SET lang = 'en' WHERE id = ?", (hr,))
    assert _mark(c, eid, 13, ali, "present", comment="Set up; closed\nthe hall").status_code == 200
    assert _mark(c, later, 13, ali, "late", comment="=Note").status_code == 200
    assert _mark(c, later, 13, bob, "excused", comment="Old consent").status_code == 200
    assert _mark(c, art, 30, _uid(con, 30), "absent").status_code == 200
    assert c.put(f"/api/events/{eid}/report/marks/{ali}", headers=tma(41), params={"org": 2},
                 json={"status": "absent", "comment": "Art only"}).status_code == 200
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (eid,))
    con.execute("UPDATE report_consents SET version = 'evr1' WHERE user_id = ?", (bob,))
    logic.set_role(con, None, ali, 1, "none", "test")
    messages = []

    async def send(_, url, *, data, files):
        assert url.endswith("/sendDocument")
        messages.append((data, files["document"]))
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", send)
    admin = TestClient(server.create(dataclasses.replace(cfg, reports=True, admins=frozenset({13, 40}))))
    for tg in (10, 12, 30, 40, 41):
        assert _export(admin, 1, tg).status_code == 403
    assert _export(admin, 1, 13, **{"X-Staff-Event": str(eid)}).status_code == 403
    assert _export(admin, 1, 13, **{"X-Staff-Org": "1"}).status_code == 403
    assert _export(admin, 2, 13).status_code == 403
    assert messages == []

    r = _export(c, 1, 13)
    assert r.status_code == 204 and not r.content
    data, (name, contents, mime) = messages.pop()
    assert data == {"chat_id": "13", "caption": "Team log: IT Club"}
    assert name == "team-log.csv" and mime == "text/csv" and contents.startswith(codecs.BOM_UTF8)
    assert list(csv.reader(io.StringIO(contents.decode("utf-8-sig")), delimiter=";")) == [
        ["Full name", "Event", "Date", "Mark", "Comment"],
        ["Testov Ali", "Next", "2025-01-03", "Late", "'=Note"],
        ["Testov Ali", "'=Case", "2025-01-02", "Present", "Set up; closed\nthe hall"],
    ]
    audit = con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'team_log_export'").fetchall()
    assert [(a["actor_id"], a["target"], json.loads(a["data"])) for a in audit] == [(hr, "org:1", {"rows": 2})]

    assert _export(c, 2, 41).status_code == 204
    assert b"Art only" in messages.pop()[1][1]
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 2")
    assert _export(c, 2, 41).status_code == 204
    assert b"Art only" not in messages.pop()[1][1]

    upsert = server._upsert

    def moved(conn, *args):
        viewer = upsert(conn, *args)
        conn.execute("UPDATE users SET tg_id = 99 WHERE id = ?", (viewer.id,))
        return viewer

    monkeypatch.setattr(server, "_upsert", moved)
    assert _export(c, 1, 13).status_code == 403
    assert messages == []


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
