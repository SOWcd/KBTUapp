"""A club starts its own attendance in Studio, no event, no admin (checkin.club_new): who may, the caps, the title, and
that such a session runs the usual start, scan, finish."""
from __future__ import annotations

from kbtu import checkin, db
from test_core import _club_runs, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)


def _new(c, tg, oid, title=None):
    return c.post(f"/api/orgs/{oid}/screens", headers=tma(tg), json={} if title is None else {"title": title})


def _join(c, con, oid, tg, name, role):
    uid = login(c, tg, name)["id"]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", (oid, uid, role))
    return uid


def test_who_may_start_one(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    other = _club_runs(c, con, 8, "eve", "go")
    _join(c, con, oid, 1, "ann", "member")
    assert _new(c, 1, oid).status_code == 403                           # a plain member runs no sessions
    assert _new(c, 8, oid).status_code == 403                           # another club's head
    assert _new(c, 9, other).status_code == 403                         # ... nor mine in theirs
    login(c, 2, "bob")
    assert _new(c, 2, oid).status_code == 403                           # a student outside the club
    assert _new(c, 9, 99999).status_code == 403                         # no such club
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = ?", (oid,))
    assert _new(c, 9, oid).status_code == 403                           # a club gone
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (oid,))
    assert _new(c, 9, oid).status_code == 200
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 9")
    assert _new(c, 9, oid).status_code == 403                           # banned
    assert con.execute("SELECT COUNT(*) FROM qr_sessions").fetchone()[0] == 1
    con.close()


def _started(con, sid):
    con.execute("UPDATE qr_sessions SET started_at = 1 WHERE id = ?", (sid,))
    return sid


def test_title_default_reuse_and_log(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    s = _new(c, 9, oid).json()
    assert s["title"].startswith("Meeting · ") and s["started"] is None and s["expected"] == 0 and s["event"] is None
    assert _new(c, 9, oid, "Other").json()["session"] == s["session"]   # not started yet: the same one again, no junk
    _started(con, s["session"])
    assert _new(c, 9, oid, "  \u0412\u0441\u0442\u0440\u0435\u0447\u0430\n\n  " + "x" * 200).json()["title"] == ("\u0412\u0441\u0442\u0440\u0435\u0447\u0430 " + "x" * 200)[:80]
    con.execute("UPDATE qr_sessions SET started_at = 1")
    assert _new(c, 9, oid, "   ").json()["title"].startswith("Meeting")
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_new'").fetchone()[0] == 3
    assert s["session"] in [x["session"] for x in c.get("/api/screens", headers=tma(9)).json()]   # the organizer's list has it
    con.close()


def test_caps(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    ids = [_started(con, _new(c, 9, oid).json()["session"]) for _ in range(checkin.CLUB_OPEN)]
    assert _new(c, 9, oid).status_code == 429                           # five open at once
    con.execute(f"UPDATE qr_sessions SET ended_at = 2 WHERE id IN ({','.join(map(str, ids))})")
    for _ in range(checkin.CLUB_DAY - checkin.CLUB_OPEN):
        con.execute("UPDATE qr_sessions SET started_at = 1, ended_at = 2 WHERE id = ?", (_new(c, 9, oid).json()["session"],))
    assert _new(c, 9, oid).status_code == 429                           # twenty a day, finished or not
    con.execute("UPDATE qr_sessions SET created_at = created_at - 86401")
    assert _new(c, 9, oid).status_code == 200                           # a day on
    con.close()


def test_runs_start_scan_finish(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    sid = _new(c, 9, oid).json()["session"]
    login(c, 1, "ann")
    assert c.post(f"/api/screens/{sid}/start", headers=tma(1)).status_code == 403   # not theirs to start
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["started"]
    p = c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["param"]          # the organizer's own phone shows it
    assert p.startswith(f"ci_{sid}_")
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p[:-1] + ("0" if p[-1] != "0" else "1")}).status_code == 400  # forged
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(9)).json()["done"] == 1
    con.close()
