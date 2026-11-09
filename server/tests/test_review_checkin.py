"""Review of QR check-in and award links: each test here fails on the code as found."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from kbtu import app as server, checkin, db, logic
from test_core import _club_runs, _csv, _paired, env, login, tma  # noqa: F401  (env: the fixture)


def test_csv_survives_an_unlinked_student(env):
    """`admin unlink` deletes the students row; that person's counted mark stays (done_at set). The CSV's tier column
    then compares None <= int: the whole list for the session is a 500."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    sid = checkin.new(con, "Meeting", [], _club_runs(c, con, 9, "dana"))
    ann = login(c, 1, "ann")
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    con.execute("DELETE FROM students WHERE user_id = ?", (ann["id"],))   # what admin.py `unlink` does
    x = TestClient(server.create(cfg), raise_server_exceptions=False)
    url = x.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]
    assert x.get(url).status_code == 200
    con.close()


def test_demoted_admins_link_stops_granting(env):
    """An admin's one-time award link outlives the admin: after the owner takes the role away, the link still hands
    out the award in that person's name (granted_by is someone who can no longer grant)."""
    c, cfg = env
    boss, adm = login(c, 60, "boss"), login(c, 61, "adm")
    login(c, 62, "bob")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (adm["id"],))
    token = logic.grant_link(con, logic.Viewer(adm["id"], "admin", True), "init26")
    assert c.post("/api/admin/staff", headers=tma(60), json={"userId": adm["id"], "role": "user"}).status_code == 200
    assert c.post(f"/api/grant-links/{token}", headers=tma(62)).json().get("error") == "closed"
    con.close()


def test_share_badge_link_bad_code_is_400(env):
    """The owner's "Link for everyone" with a non-string code: `code in BADGE_OF` on a list is a TypeError, a 500."""
    c, cfg = env
    boss = login(c, 60, "boss")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    x = TestClient(server.create(cfg), raise_server_exceptions=False)
    assert x.post("/api/share", headers=tma(60), json={"kind": "gl", "code": ["init26"], "many": True}).status_code == 400
    con.close()


# ---- an event's check-in QR on the organizer's own phone (checkin.py "show", EventQr.svelte)

def _phone_event(c, con, slug, vis="public", frm=None):
    """A free public event running now, of a club whose Head is tg 9: (event, session, its QR)."""
    oid = _club_runs(c, con, 9, "dana", slug)
    t = int(time.time())
    eid = con.execute("""INSERT INTO events (org_id, title, description, starts_at, ends_at, status, visibility, leaders_from, created_by, created_at, updated_at)
        VALUES (?, 'Meet', '', ?, ?, 'published', ?, ?, (SELECT user_id FROM org_members WHERE org_id = ?), 0, 0)""", (oid, t - 60, t + 3600, vis, frm, oid)).lastrowid
    sid = c.post(f"/api/events/{eid}/screen", headers=tma(9)).json()["session"]
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    return eid, sid, c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["param"]


def _scan(c, tg, p):
    return c.post("/api/checkin", headers=tma(tg), json={"p": p})


def _signed(cfg, sid, slot):
    return f"ci_{sid}_{slot}_{checkin._sig(cfg.token_key, f'ci.{sid}.{slot}')}"


def _grants(con, uid):
    return con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'dmp'", (uid,)).fetchone()[0]


def test_phone_qr_only_for_who_runs_the_event(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _phone_event(c, con, "vol")
    login(c, 1, "ann")
    assert c.post(f"/api/events/{eid}/screen", headers=tma(1)).status_code == 403
    assert c.post(f"/api/screens/{sid}/show", headers=tma(1)).status_code == 403
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(1)).status_code == 403
    con.close()


def test_phone_qr_refuses_forged_stale_and_unshown(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, p = _phone_event(c, con, "vol")
    ann = login(c, 1, "ann")
    slot = int(time.time()) // checkin.SLOT
    assert _scan(c, 1, f"ci_{sid}_{slot}_{'0' * 16}").status_code == 400                   # forged
    assert _scan(c, 1, p[:-1] + ("0" if p[-1] != "0" else "1")).status_code == 400
    old = slot - (checkin.SCAN_OK + checkin.SLOT) // checkin.SLOT - 1
    assert _scan(c, 1, _signed(cfg, sid, old)).status_code == 400                          # stale
    assert _scan(c, 1, _signed(cfg, sid, slot + 99)).status_code == 400                    # not yet
    # the phone closed: the session still runs, its code stops with the lease, and a poll brings it back
    con.execute("UPDATE qr_sessions SET lease_until = ? WHERE id = ?", (int(time.time()) - 1, sid))
    assert _scan(c, 1, p).status_code == 400
    assert con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0] is None
    assert not con.execute("SELECT 1 FROM qr_marks WHERE user_id = ?", (ann["id"],)).fetchone()
    assert _scan(c, 1, c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["param"]).json()["done"]
    con.close()


def test_a_big_screen_poll_renews_the_lease_too(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _phone_event(c, con, "vol")
    k = _paired(c, 9, sid)
    con.execute("UPDATE qr_sessions SET lease_until = 1 WHERE id = ?", (sid,))
    p = c.get("/api/screen", headers=k).json()["param"]
    login(c, 1, "ann")
    assert _scan(c, 1, p).json()["done"]
    con.close()


def test_phone_qr_counts_a_walk_in_once(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, p = _phone_event(c, con, "vol")
    ann = login(c, 1, "ann")
    for _ in range(3):
        assert _scan(c, 1, p).json()["done"]
    assert c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["done"] == 1
    r = con.execute("SELECT status, walk_in, checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, ann["id"])).fetchone()
    assert r["status"] == "going" and r["walk_in"] == 1 and r["checked_in_at"]
    con.close()


def test_dmp_event_gives_attendance_once(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, p = _phone_event(c, con, "dmp")
    ann = login(c, 1, "ann")
    outsider = c.get("/api/me", headers=tma(7, "Out")).json()["id"]
    assert _scan(c, 1, p).json()["done"] and _scan(c, 1, p).json()["done"]
    assert not _scan(c, 7, p).json()["done"]                                                # not a student: waits, no award
    assert _grants(con, ann["id"]) == 1 and _grants(con, outsider) == 0
    day = (int(time.time()) + 5 * 3600) // 86400
    assert con.execute("SELECT batch FROM achievement_grants WHERE user_id = ?", (ann["id"],)).fetchone()[0] == f"q{sid}_{day}"
    # the next day, the session left open: the same old link counts as before but is no second award
    con.execute("UPDATE achievement_grants SET created_at = created_at - 86400 WHERE user_id = ?", (ann["id"],))
    old = int(time.time()) // checkin.SLOT - 40
    assert _scan(c, 1, _signed(cfg, sid, old)).json()["done"] and _grants(con, ann["id"]) == 1
    # the leaving phase never gives one
    c.post(f"/api/screens/{sid}/out", headers=tma(9))
    assert _scan(c, 1, c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["param"]).json()["left"]
    assert _grants(con, ann["id"]) == 1
    con.close()


def test_dmp_award_waits_for_the_sign_up(env):
    """A guest's scan, the sign-in done long after the QR's window: the saved scan earns it, under the scan's own day."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, p = _phone_event(c, con, "dmp")
    uid = c.get("/api/me", headers=tma(7, "Gul")).json()["id"]
    assert not _scan(c, 7, p).json()["done"]
    scanned = int(time.time()) - 86400
    con.execute("UPDATE qr_marks SET scanned_at = ? WHERE user_id = ?", (scanned, uid))
    login(c, 7, "gul")
    checkin.became_student(con, uid)
    checkin.became_student(con, uid)  # again: nothing waits any more
    assert _grants(con, uid) == 1
    assert con.execute("SELECT batch FROM achievement_grants WHERE user_id = ?", (uid,)).fetchone()[0] == f"q{sid}_{(scanned + 5 * 3600) // 86400}"
    con.close()


def test_another_clubs_event_gives_no_attendance(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, _, p = _phone_event(c, con, "vol")
    ann = login(c, 1, "ann")
    assert _scan(c, 1, p).json()["done"]
    assert _grants(con, ann["id"]) == 0
    con.close()


def _reg(con, eid, uid):
    return con.execute("SELECT status, walk_in FROM registrations WHERE event_id = ? AND user_id = ?", (eid, uid)).fetchone()


def test_dmp_leaders_meeting_counts_the_hall_and_hides_itself(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, p = _phone_event(c, con, "dmp", "leaders", "head")
    _club_runs(c, con, 11, "lee", "art")                                                    # another club's Head: invited
    lee = c.get("/api/me", headers=tma(11)).json()["id"]
    r = _scan(c, 11, p).json()
    assert r["done"] and r["title"] == "Meet" and _grants(con, lee) == 1
    assert _reg(con, eid, lee)["status"] == "going" and _reg(con, eid, lee)["walk_in"] == 1
    ann = login(c, 1, "ann")                                                                # no club: not invited
    r = _scan(c, 1, p).json()
    assert r["done"] and r["title"] != "Meet" and _grants(con, ann["id"]) == 1
    assert _scan(c, 1, p).json()["done"] and _grants(con, ann["id"]) == 1
    assert _reg(con, eid, ann["id"]) is None
    assert c.get(f"/api/events/{eid}", headers=tma(1)).status_code in (403, 404)
    assert c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()["done"] == 2
    con.close()


def test_other_leaders_meetings_still_count_their_list_only(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, _, p = _phone_event(c, con, "vol", "leaders", "head")
    _club_runs(c, con, 11, "lee", "art")
    lee = c.get("/api/me", headers=tma(11)).json()["id"]
    assert not _scan(c, 11, p).json()["done"] and _grants(con, lee) == 0 and _reg(con, eid, lee) is None
    con.close()


def test_a_started_session_nothing_shows_stops(env):
    """Start alone leases it too: a code only ever read from the session list dies with the lease"""
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    sid = checkin.new(con, "Meeting", [], oid)
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    con.execute("UPDATE qr_sessions SET lease_until = ? WHERE id = ?", (int(time.time()) - 1, sid))
    login(c, 1, "ann")
    assert _scan(c, 1, p).status_code == 400
    con.close()
