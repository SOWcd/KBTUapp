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


def test_title_default_and_log(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    s = _new(c, 9, oid).json()
    assert s["title"].startswith("Meeting \u00b7 ") and s["started"] is None and s["event"] is None
    assert _new(c, 9, oid, "  \u0412\u0441\u0442\u0440\u0435\u0447\u0430\n\n  " + "x" * 200).json()["title"] == ("\u0412\u0441\u0442\u0440\u0435\u0447\u0430 " + "x" * 200)[:80]
    assert _new(c, 9, oid, "   ").json()["title"].startswith("Meeting")
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_new'").fetchone()[0] == 3
    assert s["session"] in [x["session"] for x in c.get("/api/screens", headers=tma(9)).json()]   # the organizer's list has it
    con.close()


def test_caps(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    ids = [_new(c, 9, oid).json()["session"] for _ in range(checkin.CLUB_OPEN)]
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


def _mail(con, tg, mail):
    con.execute("UPDATE students SET email = ? WHERE user_id = (SELECT id FROM users WHERE tg_id = ?)", (mail, tg))


def test_who_is_expected_and_who_is_absent(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    _mail(con, 9, "dana@kbtu.kz")
    for tg, name in ((1, "ann"), (2, "bob")):
        _join(c, con, oid, tg, name, "member")
        _mail(con, tg, f"{name}@kbtu.kz")
    login(c, 3, "cat")                                                  # not in the club
    tag = con.execute("INSERT INTO org_tags (org_id, name, color, created_at) VALUES (?, 'Media', 'blue', 0)", (oid,)).lastrowid
    con.execute("INSERT INTO member_tags (tag_id, user_id) SELECT ?, id FROM users WHERE tg_id = 2", (tag,))
    other = _club_runs(c, con, 8, "eve", "go")
    foreign = con.execute("INSERT INTO org_tags (org_id, name, color, created_at) VALUES (?, 'X', 'red', 0)", (other,)).lastrowid
    assert c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={"who": foreign}).status_code == 400   # another club's tag
    assert c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={"who": "x"}).status_code == 400
    assert c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={"who": tag}).json()["expected"] == 1
    assert c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={"who": "all"}).json()["expected"] == 0
    sid = c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={}).json()["session"]          # the whole club, by default
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    for tg in (1, 3):
        assert c.post("/api/checkin", headers=tma(tg), json={"p": p}).json()["done"]
    row = [x for x in c.get("/api/screens", headers=tma(9)).json() if x["session"] == sid][0]
    assert (row["expected"], row["came"], row["done"]) == (3, 1, 2)    # came 1 of 3, and one more not on the list
    assert c.get(f"/api/screens/{sid}/people", headers=tma(9)).json()["absent"] == ["Testov Bob", "Testov Dana"]
    assert c.get(f"/api/screens/{sid}/people", headers=tma(1)).status_code == 403
    csv = c.get(c.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]).text
    assert "came (not on the list)" in csv and "absent,Testov Bob" in csv and "bob@kbtu.kz" not in csv   # the team never sees mails
    con.close()


def test_left_running_finishes_itself(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    sid = _new(c, 9, oid).json()["session"]
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    login(c, 1, "ann")
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    late = _new(c, 9, oid).json()["session"]                            # never started: stays
    con.execute("UPDATE qr_sessions SET started_at = started_at - ? WHERE id = ?", (checkin.STALE - 60, sid))
    assert [x["ended"] for x in c.get("/api/screens", headers=tma(9)).json() if x["session"] == sid] == [None]
    con.execute("UPDATE qr_sessions SET started_at = started_at - 120 WHERE id = ?", (sid,))
    l = c.get("/api/screens", headers=tma(9)).json()
    assert [x["session"] for x in l] == [late, sid] and l[1]["ended"] and l[1]["done"] == 1   # open first; the mark kept
    con.close()


def _badge(c, tg, sid, qr):
    return c.post(f"/api/screens/{sid}/badge", headers=tma(tg), json={"qr": qr})


def test_mark_by_hand(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    _join(c, con, oid, 1, "ann", "member")
    login(c, 2, "bob")
    qr = c.get("/api/me", headers=tma(2)).json()["qr"]
    url = f"https://t.me/KBTUappBot?startapp=u_{qr}"
    sid = _new(c, 9, oid).json()["session"]
    assert _badge(c, 9, sid, url).json()["error"] == "closed"           # not started
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    assert _badge(c, 1, sid, url).status_code == 403                    # a plain member
    assert _badge(c, 8, sid, url).status_code in (401, 403)             # nobody's organizer
    assert _badge(c, 9, sid, url[:-1] + ("A" if url[-1] != "A" else "B")).status_code == 404   # wrong code
    assert _badge(c, 9, sid, "garbage").status_code == 404
    assert _badge(c, 9, sid, f"u_{c.get('/api/me', headers=tma(9)).json()['qr']}").status_code == 404  # my own
    login(c, 3, "cat")
    old = c.get("/api/me", headers=tma(3)).json()["qr"]
    con.execute("UPDATE users SET qr_code = 'ZZZZZZZZZZ' WHERE tg_id = 3")
    assert _badge(c, 9, sid, f"u_{old}").status_code == 404             # stale (its code changed)
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 3")
    assert _badge(c, 9, sid, "u_" + old.split("_")[0] + "_ZZZZZZZZZZ").status_code == 404   # banned
    got = _badge(c, 9, sid, url).json()
    assert got["done"] and got["person"]
    assert _badge(c, 9, sid, url).status_code == 409                    # once per person
    row = con.execute("SELECT done_at, marked_by FROM qr_marks WHERE session_id = ?", (sid,)).fetchone()
    assert row[0] and row[1] == c.get("/api/me", headers=tma(9)).json()["id"]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_badge'").fetchone()[0] == 1
    csv = c.get(c.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]).text.splitlines()
    assert csv[0].endswith(",by_hand") and csv[1].rsplit(",", 1)[1].startswith("Dana")   # who marked it
    c.post(f"/api/screens/{sid}/finish", headers=tma(9))
    assert _badge(c, 9, sid, url).json()["error"] == "closed"           # finished
    con.close()


def test_mark_by_hand_attacks(env):
    """Another club's head, the leaving phase, an archived club, a flagged receipt at an event's own session."""
    import time
    from test_checkin_door import _ev, _qr, _reg
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    _club_runs(c, con, 8, "eve", "go")
    login(c, 2, "bob")
    bob = f"u_{c.get('/api/me', headers=tma(2)).json()['qr']}"
    sid = _new(c, 9, oid).json()["session"]
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    assert _badge(c, 8, sid, bob).status_code == 403                    # another club's head, my session
    assert c.get(f"/api/screens/{sid}/people", headers=tma(8)).status_code == 403
    assert c.post(f"/api/screens/{sid}/csv", headers=tma(8)).status_code == 403
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(8)).status_code == 403
    c.post(f"/api/screens/{sid}/out", headers=tma(9))
    assert _badge(c, 9, sid, bob).json()["message"] == "qr_out"         # leaving now: no arrival by hand
    c.post(f"/api/screens/{sid}/in", headers=tma(9))
    late = _new(c, 9, oid).json()["session"]                            # made, never started
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = ?", (oid,))
    assert _badge(c, 9, sid, bob).json()["error"] == "closed"           # the club is gone
    assert c.post(f"/api/screens/{late}/start", headers=tma(9)).json()["error"] == "closed"
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(9)).status_code == 200   # finishing still works
    # an event's own session: a ticket whose receipt nobody reviewed goes to the door scanner, as a scan does
    eid = _ev(con, _club_runs(c, con, 7, "mia", "poker"), int(time.time()) - 60, price=2000)
    rid = _reg(con, eid, c.get("/api/me", headers=tma(2)).json()["id"], "BBBB")
    fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at) VALUES ('x', 'receipt', 'image/webp', 1, 1, 1, 'p', 1, 0)").lastrowid
    con.execute("INSERT INTO receipts (registration_id, file_id, via, flags, created_at) VALUES (?, ?, 'app', 'duplicate', 0)", (rid, fid))
    esid, _ = _qr(c, 7, eid)
    assert _badge(c, 7, esid, bob).json()["message"] == "flagged"
    assert not con.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (rid,)).fetchone()[0]
    con.close()


def test_deleting_the_marker_drops_the_link(env):
    """Who marked by hand loses the link on deleting their account (marked_by: nullable, emptied with the rest)."""
    from kbtu.logic import Viewer, account
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    me = c.get("/api/me", headers=tma(9)).json()["id"]
    login(c, 2, "bob")
    sid = _new(c, 9, oid).json()["session"]
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    assert _badge(c, 9, sid, f"u_{c.get('/api/me', headers=tma(2)).json()['qr']}").json()["done"]
    account.delete_me(con, Viewer(me, "user", True))
    assert con.execute("SELECT marked_by FROM qr_marks WHERE session_id = ?", (sid,)).fetchone()[0] is None
    con.close()
