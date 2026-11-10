"""A member's QR at an event's door (checkin._door): the review's attacks (.claude/reports/checkin-review.md) now fail."""
from __future__ import annotations

import time

from kbtu import db, logic
from test_core import _club_runs, env, login, tma  # noqa: F401
from test_review_checkin import _scan
from test_vol import zz, _member, _agree, P  # noqa: F401


def _ev(con, org, t0, price=None, vis="public", ends=3600):
    return con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, price, pay_to_name, pay_phone, visibility,
        created_by, created_at, updated_at) VALUES (?, 'published', 'Party', 'Hall', ?, ?, 'trophy_3d', '#3B6BFF', ?, ?, ?, ?, 1, 0, 0)""",
        (org, t0, t0 + ends, price, price and "Dana S.", price and "+77071234567", vis)).lastrowid


def _mem(c, con, org, tg, name):
    u = login(c, tg, name)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, u["id"]))
    return u


def _qr(c, tg, eid):
    sid = c.post(f"/api/events/{eid}/screen", headers=tma(tg)).json()["session"]
    assert c.post(f"/api/screens/{sid}/start", headers=tma(tg)).status_code == 200
    return sid, c.post(f"/api/screens/{sid}/show", headers=tma(tg)).json()


def _reg(con, eid, uid, code):
    return con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, 0, 0)",
                       (eid, uid, f"{eid}-{code}")).lastrowid


def test_member_cant_check_themselves_in(env):
    """The member showing the QR can't scan it for themselves (as the scanner); a guest still can, and the door sees who."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60)
    mia = _mem(c, con, org, 7, "mia")
    _reg(con, eid, mia["id"], "AAAA")
    _, q = _qr(c, 7, eid)
    r = _scan(c, 7, q["param"])
    assert r.status_code == 403 and r.json()["message"] == "own"
    assert not con.execute("SELECT checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, mia["id"])).fetchone()[0]
    login(c, 30, "zed")
    assert _scan(c, 30, q["param"]).json()["done"]                                          # an honest guest: as before
    sid = q["session"]
    assert c.post(f"/api/screens/{sid}/show", headers=tma(7)).json()["last"]["name"]        # the phone shows who just came in
    assert _scan(c, 9, q["param"]).status_code == 200                                       # whoever runs the event: may, as at the scanner
    con.close()


def test_member_gets_no_code_outside_the_door(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60)
    _mem(c, con, org, 7, "mia")
    _qr(c, 9, eid)
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) + 86400, int(time.time()) + 90000, eid))
    r = c.post(f"/api/events/{eid}/screen", headers=tma(7))
    assert r.status_code == 409 and r.json()["message"] == "not_open" and r.json()["at"] == int(time.time()) + 86400 - logic.DOOR_AUTO
    assert c.post(f"/api/events/{eid}/screen", headers=tma(9)).json()["param"]              # its organizer: as before
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 9000, int(time.time()) - 60, eid))
    assert c.post(f"/api/events/{eid}/screen", headers=tma(7)).json()["message"] == "closed"
    con.close()


def test_member_starts_from_t30_only(env):
    """A President's early opening: the member shows a running QR, but Start (the tier line) waits for T-30."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    t = int(time.time())
    eid = _ev(con, org, t + 3 * 3600)
    con.execute("UPDATE events SET door_open_at = ? WHERE id = ?", (t - 60, eid))
    _mem(c, con, org, 7, "mia")
    sid = c.post(f"/api/events/{eid}/screen", headers=tma(7)).json()["session"]
    r = c.post(f"/api/screens/{sid}/start", headers=tma(7))
    assert r.status_code == 409 and r.json()["at"] == t + 3 * 3600 - logic.DOOR_AUTO
    assert con.execute("SELECT started_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0] is None
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).status_code == 200            # the organizer may
    assert c.post(f"/api/screens/{sid}/show", headers=tma(7)).json()["param"]               # ... and then the member shows it
    con.close()


def test_members_only_and_cancelled_stay_the_organizers(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60, vis="members")
    _mem(c, con, org, 7, "mia")
    assert c.post(f"/api/events/{eid}/screen", headers=tma(7)).json()["message"] == "door_staff"
    sid, _ = _qr(c, 9, eid)
    assert c.post(f"/api/screens/{sid}/show", headers=tma(7)).status_code == 403
    e2 = _ev(con, org, int(time.time()) - 60)
    s2 = c.post(f"/api/events/{e2}/screen", headers=tma(9)).json()["session"]
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (e2,))
    assert c.post(f"/api/screens/{s2}/start", headers=tma(7)).status_code == 409
    con.close()


def test_paid_ticket_used_twice(env):
    """A screenshot went in by the scanner: the holder's QR scan says "already" (with the time), not "you're in"."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60, price=2000)
    _mem(c, con, org, 7, "mia")
    bob = login(c, 2, "bob")
    _reg(con, eid, bob["id"], "BBBB")
    with con:
        assert logic.checkin(con, logic.Viewer(c.get("/api/me", headers=tma(7)).json()["id"], "user", True), eid, "KBTUBBBB")["result"] == "ok"
    _, q = _qr(c, 7, eid)
    r = _scan(c, 2, q["param"]).json()
    assert not r["done"] and r["already"]
    con.close()


def test_flagged_receipt_goes_to_the_scanner(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60, price=2000)
    _mem(c, con, org, 7, "mia")
    bob = login(c, 2, "bob")
    rid = _reg(con, eid, bob["id"], "BBBB")
    fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at) VALUES ('x', 'receipt', 'image/webp', 1, 1, 1, 'p', ?, 0)", (bob["id"],)).lastrowid
    con.execute("INSERT INTO receipts (registration_id, file_id, via, flags, created_at) VALUES (?, ?, 'app', 'duplicate,amount_short', 0)", (rid, fid))
    _, q = _qr(c, 7, eid)
    r = _scan(c, 2, q["param"]).json()
    assert not r["done"] and r["flagged"]
    assert not con.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (rid,)).fetchone()[0]
    con.close()


def test_leaving_after_the_door_closed(env):
    """Leaving an event's session: within its door window (+ GRACE for the crowd leaving at the end)."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    eid = _ev(con, org, int(time.time()) - 60)
    login(c, 2, "bob")
    sid, q = _qr(c, 9, eid)
    assert _scan(c, 2, q["param"]).json()["done"]
    c.post(f"/api/screens/{sid}/out", headers=tma(9))
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 9000, int(time.time()) - 600, eid))
    p = c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["param"]
    assert _scan(c, 2, p).json()["left"]                                                    # 10 min after the end: fine
    con.execute("UPDATE events SET ends_at = ? WHERE id = ?", (int(time.time()) - 3 * 3600, eid))
    assert _scan(c, 2, p).status_code == 409
    con.close()


def test_volunteer_sessions_stay_the_organizers(zz):
    """ZhZh: a plain member gets no code (hours, misses); the volunteers still check in and out by the organizer's QR."""
    c, _, con, org = zz
    _member(c, con, org, 3, "vika")
    t = int(time.time())
    eid = _ev(con, org, t - 60, ends=4 * 3600)
    assert c.post(f"/api/events/{eid}/screen", headers=tma(3)).json()["message"] == "door_staff"
    sid, q = _qr(c, P, eid)
    assert c.post(f"/api/screens/{sid}/show", headers=tma(3)).status_code == 403
    assert _scan(c, 3, q["param"]).json()["done"]                                           # a volunteer scanning the organizer's QR: counted
    c.post(f"/api/screens/{sid}/out", headers=tma(P))
    assert _scan(c, 3, c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]).json()["left"]
    _agree(c, 3)
