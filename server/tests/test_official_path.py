"""The path to the official ✓ (logic/clubs.py, official_path): each step checks itself (members settled, logo and
description, a round that took someone, an event with people outside the team scanned in, a collab with an official
club); only the President or a Vice asks, once, again 30 days after a no; only the admin decides; Undo takes it back."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

ADMIN, PRES, VICE, HEAD, A, B, C, D = 60, 61, 62, 63, 64, 65, 66, 67
DAY = 86400


def _setup(env):
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}))))
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, PRES, VICE, HEAD, A, B, C, D)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", False)
    for tg, role in ((PRES, "president"), (VICE, "vice"), (HEAD, "head")):
        logic.set_role(con, None, ids[tg], oid, role, "test")
    return c, con, ids, oid


def _steps(c, oid, who=PRES):
    return c.get(f"/api/orgs/{oid}/official-path", headers=tma(who)).json()["path"]["steps"]


def _event(con, oid, ago=DAY):
    t = logic.now()
    return con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, created_at, updated_at)
        VALUES (?, 'published', 'Blitz', '305', ?, ?, 'crown_3d', '#3B6BFF', 0, 0)""", (oid, t - ago, t - ago + 3600)).lastrowid


def _came(con, eid, uid, manual=0):
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at, checkin_manual)
        VALUES (?, ?, 'going', ?, 0, 0, ?, ?)""", (eid, uid, f"t{eid}-{uid}", logic.now(), manual))


def _all_done(con, ids, oid):
    """Every step, the quick way (each one's own test is below)."""
    con.execute("UPDATE org_members SET joined_at = 0 WHERE org_id = ?", (oid,))
    fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, created_at) VALUES ('l', 'org_logo', 'image/webp', 1, 'ab/l', 0)").lastrowid
    con.execute("UPDATE orgs SET logo_file_id = ?, description = 'We play chess every Friday.' WHERE id = ?", (fid, oid))
    rid = con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_at) VALUES (?, 'Fall', 0, 'done', 0)", (oid,)).lastrowid
    con.execute("INSERT INTO round_apps (round_id, user_id, departments, answers, stage, created_at, updated_at) VALUES (?, ?, '[]', '{}', 'yes', 0, 0)",
                (rid, ids[A]))
    eid = _event(con, oid)
    for tg in (A, B, C):
        _came(con, eid, ids[tg])
    off = logic.create_org(con, None, "Debate", "DB", "crown_3d", True)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (eid, off))


def test_each_step(env):
    c, con, ids, oid = _setup(env)
    assert _steps(c, oid) == {**dict.fromkeys(logic.PATH_STEPS, False), "members": True}  # 3 KBTU students, at once (owner, Nov 5)
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(A)).status_code == 403  # not in the club
    con.execute("UPDATE org_members SET joined_at = ? WHERE org_id = ?", (logic.now() - 4 * DAY, oid))  # in the club before its events below
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids[HEAD],))
    assert not _steps(c, oid)["members"]  # a banned one doesn't
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ids[HEAD],))
    # the logo and a description
    fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, created_at) VALUES ('l', 'org_logo', 'image/webp', 1, 'ab/l', 0)").lastrowid
    con.execute("UPDATE orgs SET logo_file_id = ?, description = 'hi' WHERE id = ?", (fid, oid))
    assert not _steps(c, oid)["profile"]
    con.execute("UPDATE orgs SET description = 'We play chess every Friday.' WHERE id = ?", (oid,))
    assert _steps(c, oid)["profile"]
    # a round with results out that took someone
    rid = con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_at) VALUES (?, 'Fall', 0, 'closed', 0)", (oid,)).lastrowid
    con.execute("INSERT INTO round_apps (round_id, user_id, departments, answers, stage, created_at, updated_at) VALUES (?, ?, '[]', '{}', 'no', 0, 0)", (rid, ids[A]))
    con.execute("UPDATE rounds SET status = 'done' WHERE id = ?", (rid,))
    assert not _steps(c, oid)["round"]  # nobody accepted
    con.execute("UPDATE round_apps SET stage = 'yes'")
    assert _steps(c, oid)["round"]
    # an event over with 3 outsiders scanned: the team, a check-in by hand and one still to come don't count
    eid = _event(con, oid)
    for tg in (PRES, VICE, HEAD, A, B):
        _came(con, eid, ids[tg])
    _came(con, eid, ids[C], manual=1)
    assert not _steps(c, oid)["event"]  # 2 outsiders scanned
    later = _event(con, oid, ago=-DAY)
    for tg in (A, B, C):
        _came(con, later, ids[tg])
    assert not _steps(c, oid)["event"]  # not over yet
    _came(con, eid, ids[D])
    assert _steps(c, oid)["event"]
    # an outsider who joined after the event still counts; one in the team before it doesn't
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (oid, ids[D], logic.now()))
    assert _steps(c, oid)["event"]
    con.execute("UPDATE org_members SET joined_at = 0 WHERE user_id = ?", (ids[D],))
    assert not _steps(c, oid)["event"]
    # a collab: an accepted official co-host (pending or unofficial doesn't do)
    other = logic.create_org(con, None, "Debate", "DB", "crown_3d", False)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'pending', 0)", (later, other))
    assert not _steps(c, oid)["collab"]
    con.execute("UPDATE event_cohosts SET status = 'accepted'")
    assert not _steps(c, oid)["collab"]
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (other,))
    assert _steps(c, oid)["collab"]
    # the other way round: we co-host an official club's event
    con.execute("DELETE FROM event_cohosts")
    theirs = _event(con, other)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (theirs, oid))
    assert _steps(c, oid)["collab"]
    # an official club sees no path
    assert c.get(f"/api/orgs/{other}/official-path", headers=tma(PRES)).status_code == 403
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(PRES)).json()["path"] is None


def test_request_lifecycle(env, monkeypatch):
    c, con, ids, oid = _setup(env)
    ask = lambda who=PRES: c.post(f"/api/orgs/{oid}/official-path", headers=tma(who))  # noqa: E731
    assert ask().status_code == 400  # steps not done
    _all_done(con, ids, oid)
    assert ask(HEAD).status_code == 403 and ask(A).status_code == 403  # the President or a Vice only
    r = ask(VICE)
    assert r.status_code == 200 and r.json()["path"]["request"]["status"] == "pending"
    assert ask().status_code == 409  # one at a time
    rid = r.json()["path"]["request"]["id"]
    told = con.execute("SELECT u.tg_id, b.ref FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'club_path'").fetchall()
    assert [tuple(t) for t in told] == [(ADMIN, f"opath:{rid}")]
    row = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'club_path'").fetchone()) | {"lang": "en"}
    text, _, start = bot._render(con, row)
    assert "Chess" in text and start == "capps"
    # only the admin decides; it's in his Inbox
    decide = lambda who=ADMIN, **b: c.post(f"/api/admin/official-requests/{rid}", headers=tma(who), json=b)  # noqa: E731
    assert decide(PRES, approve=True).status_code == 403
    inbox = c.get("/api/admin/inbox", headers=tma(ADMIN)).json()
    assert [x["key"] for x in inbox["items"] if x["kind"] == "opath"] == [f"opath:{rid}"]
    assert decide(approve=False, reason="x").status_code == 400  # a no needs its reason
    assert decide(approve=False, reason="Not yet, come in spring").status_code == 200
    p = c.get(f"/api/orgs/{oid}/official-path", headers=tma(HEAD)).json()["path"]
    assert p["request"]["status"] == "rejected" and p["request"]["reason"] == "Not yet, come in spring"
    assert decide(approve=True).status_code == 409  # decided already
    assert ask().status_code == 429  # 30 days after a no
    # Undo the no: waiting again; then a yes makes it official, its President told after the Undo's minute
    done = c.get("/api/admin/inbox", headers=tma(ADMIN)).json()["done"]
    no = next(d for d in done if d["action"] == "opath_no")
    assert no["undo"] and no["text"].startswith("Chess")
    assert c.post(f"/api/admin/done/{no['id']}/undo", headers=tma(ADMIN)).status_code in (200, 204)
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(PRES)).json()["path"]["request"]["status"] == "pending"
    assert decide(approve=True).status_code == 200
    assert con.execute("SELECT official FROM orgs WHERE id = ?", (oid,)).fetchone()[0] == 1
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(PRES)).json()["path"] is None
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_official' AND sent_at IS NULL").fetchone()[0] == 1
    # Undo the yes: the ✓ back off, the message unsent, the request waits
    yes = next(d for d in c.get("/api/admin/inbox", headers=tma(ADMIN)).json()["done"] if d["action"] == "opath_yes")
    assert c.post(f"/api/admin/done/{yes['id']}/undo", headers=tma(ADMIN)).status_code in (200, 204)
    assert con.execute("SELECT official FROM orgs WHERE id = ?", (oid,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_official'").fetchone()[0] == 0
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(PRES)).json()["path"]["request"]["status"] == "pending"
    # a no again, then 31 days later the club may ask again
    assert decide(approve=False, reason="Not yet, come in spring").status_code == 200
    t = logic.now() + 31 * DAY
    monkeypatch.setattr(logic.core, "now", lambda: t)
    assert ask().status_code == 200
