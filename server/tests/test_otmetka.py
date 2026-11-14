"""the Mark screen (Nov 14): whom an event's door records (events.door_audience), the team's live list by department with
roster rows that have no account, hand marks and their undo, who sees the names, and deleting a marker's account."""
from __future__ import annotations

import time

from kbtu import checkin, db, roster
from test_checkin_door import _qr, _reg
from test_core import delete_now, login, tma, env  # noqa: F401
from test_one_qr import _crew, _marks, _setup
from test_review_checkin import _scan


def _aud(c, tg, eid, a):
    return c.put(f"/api/events/{eid}/audience", headers=tma(tg), json={"audience": a})


def _row(c, tg, eid, key):
    return next(r for r in c.get(f"/api/events/{eid}/door-team", headers=tma(tg)).json()["rows"] if r["key"] == key)


def test_audience_routes_the_scan(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    assert c.get(f"/api/events/{eid}", headers=tma(9)).json()["audience"] == "both"        # default: as before
    assert _aud(c, 1, eid, "team").status_code == 403                                      # a plain member can't
    assert _aud(c, 9, eid, "nobody").status_code == 400
    assert _aud(c, 9, eid, "guests").json() == {"audience": "guests"}
    g, q = _qr(c, 9, eid)
    assert _crew(con, eid) is None                                                         # guests only: no team session
    r = _scan(c, 1, q["param"]).json()
    assert r["done"] and "team" not in r and _marks(con, g) == 1                           # a member comes as a guest

    e2 = con.execute("INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, visibility, created_by, created_at, updated_at) "
                     "SELECT org_id, status, title, place, starts_at, ends_at, emoji, color, visibility, created_by, 0, 0 FROM events WHERE id = ?", (eid,)).lastrowid
    _aud(c, 9, e2, "team")
    g2, q2 = _qr(c, 9, e2)
    login(c, 3, "cat")                                                                     # not the club's: still the team's list
    r = _scan(c, 3, q2["param"]).json()
    assert r["done"] and "team" not in r and _marks(con, g2, False) == 0                   # counted, but no team cue (reports' consent)
    assert _scan(c, 1, q2["param"]).json()["team"]                                         # the club's own: the team's cue
    c.get("/api/me", headers=tma(5))                                                       # no account yet: waits on the team's list
    r = _scan(c, 5, q2["param"]).json()
    assert not r["done"] and _marks(con, _crew(con, e2)["id"], False) == 3 and _marks(con, g2, False) == 0
    bad = login(c, 6, "bad")
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (oid, bad["id"]))
    r = _scan(c, 6, q2["param"])
    assert r.status_code == 403 and _marks(con, _crew(con, e2)["id"], False) == 3           # the club banned them: never on its list
    con.close()


def test_team_list_by_department_and_hand_marks(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    tag = con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, 'Media', '#000', 1, 0)", (oid,)).lastrowid
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (tag, ann["id"]))
    rid = con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, dept, full_name, tg, created_at) VALUES ('k1', ?, 's', 'member', 'Media', 'Petrov Zhan', 'zhan', 0)",
                      (oid,)).lastrowid
    lst = c.get(f"/api/events/{eid}/door-team", headers=tma(9)).json()
    assert lst["session"] is None and len(lst["rows"]) == 3                                # dana, ann, the roster row
    zhan = _row(c, 9, eid, f"r{rid}")
    assert zhan == {"key": f"r{rid}", "name": "Petrov Zhan", "group": "Media", "at": None, "manual": False, "app": False}
    assert _row(c, 9, eid, f"u{ann['id']}")["group"] == "Media"

    m = c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"r{rid}"}).json()  # before the QR: its organizer opens the team session
    assert m["session"] == _crew(con, eid)["id"]
    zhan = next(r for r in m["rows"] if r["key"] == f"r{rid}")
    assert zhan["at"] and zhan["manual"]
    c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}"})
    assert _row(c, 9, eid, f"u{ann['id']}")["manual"]
    c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False})  # undo
    assert _row(c, 9, eid, f"u{ann['id']}")["at"] is None and _marks(con, _crew(con, eid)["id"]) == 0
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": "r999999"}).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_hand'").fetchone()[0] == 2

    # a scan stays (it proves they came): undo takes back hand marks only
    _, q = _qr(c, 9, eid)
    assert _scan(c, 1, q["param"]).json()["team"]
    c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False})
    assert _row(c, 9, eid, f"u{ann['id']}")["at"] and not _row(c, 9, eid, f"u{ann['id']}")["manual"]

    # the roster row's student signs up and is matched: the hand mark is theirs now
    zh = login(c, 6, "zhan")
    con.execute("UPDATE students SET first_name = 'Zhan', last_name = 'Petrov' WHERE user_id = ?", (zh["id"],))
    roster.join(con, zh["id"], con.execute("SELECT * FROM roster_pending WHERE id = ?", (rid,)).fetchone())
    row = _row(c, 9, eid, f"u{zh['id']}")
    assert row["at"] and row["manual"] and row["group"] == "Media"
    assert not con.execute("SELECT 1 FROM qr_hand_marks").fetchone()
    con.close()


def test_who_sees_the_names(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, full_name, created_at) VALUES ('k2', ?, 's', 'member', 'Petrov Zhan Olegovich', 0)", (oid,))
    assert c.get(f"/api/events/{eid}/door-team", headers=tma(1)).status_code == 403            # a plain member: no list
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'scan', 1, 0)", (eid, h["id"], oid))
    assert c.get(f"/api/events/{eid}/door-team", headers=tma(4)).status_code == 403            # scanner only: no list
    con.execute("UPDATE event_crew SET kind = 'door' WHERE user_id = ?", (h["id"],))
    names = {r["name"] for r in c.get(f"/api/events/{eid}/door-team", headers=tma(4)).json()["rows"]}
    assert "Zhan P" in names and not any("Olegovich" in n for n in names)                   # the President gave the list: short names
    con.close()


def test_hand_marks_close_at_midnight_after_the_end(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _qr(c, 9, eid)
    c.post(f"/api/screens/{_qr(c, 9, eid)[0]}/finish", headers=tma(9))                     # the door closed: lists still fixed
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}"}).status_code == 200
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    monkeypatch.setattr(checkin, "now", lambda: checkin._until(e) + 1)
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False}).status_code == 409
    con.close()


def test_a_markers_account_deleted_keeps_the_mark(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    rid = con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, full_name, created_at) VALUES ('k3', ?, 's', 'member', 'Petrov Zhan', 0)", (oid,)).lastrowid
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', 1, 0)", (eid, h["id"], oid))
    _qr(c, 9, eid)
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(4), json={"key": f"r{rid}"}).status_code == 200
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(4), json={"key": f"u{ann['id']}"}).status_code == 200
    delete_now(c, cfg, tma(4))
    assert con.execute("SELECT marked_by FROM qr_hand_marks").fetchone()[0] is None        # the mark stays, its marker gone
    assert _row(c, 9, eid, f"r{rid}")["manual"] and _row(c, 9, eid, f"u{ann['id']}")["manual"]  # still a hand mark, not a "scan"
    c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False})
    assert _row(c, 9, eid, f"u{ann['id']}")["at"] is None                                  # and still undone by an organizer
    con.close()


def test_review_attacks(env):
    """The adversarial review's probes (otmetka/review.md), each failing now."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _, q = _qr(c, 9, eid)
    sid = _crew(con, eid)["id"]
    post = lambda tg, key, on=True: c.post(f"/api/events/{eid}/door-team", headers=tma(tg), json={"key": key, "on": on})  # noqa: E731
    rid = con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, full_name, tg, created_at) VALUES ('k9', ?, 's', 'member', 'Petrov Zhan', 'zhan', 0)", (oid,)).lastrowid
    for k in ("u\u00b2", f"r0{rid}", f"r\u0661", "r", "q1", "", 5, None, f"u{ann['id']} "):        # strict keys: 400, never a 500 or a twin row
        assert post(9, k).status_code == 400, k
    assert post(9, f"r{rid}").status_code == 200 and con.execute("SELECT COUNT(*) FROM qr_hand_marks").fetchone()[0] == 1

    # a hidden expected row (the club's own frozen one) can't be marked
    con.execute("""INSERT INTO qr_expected (session_id, email, full_name, extra) VALUES (?, 'hid@kbtu.kz', 'Hidden One', '{"club": 1}')""", (sid,))
    assert post(9, "xhid@kbtu.kz").status_code == 404

    # undo takes back hand marks only: a badge mark and a scan completed by hand stay
    bob = login(c, 2, "bob")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, bob["id"]))
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at, done_at, marked_by) VALUES (?, ?, 1, 1, ?)", (sid, bob["id"], ann["id"]))  # a badge
    post(9, f"u{bob['id']}", False)
    assert _row(c, 9, eid, f"u{bob['id']}")["at"] == 1
    cat = login(c, 3, "cat")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, cat["id"]))
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, 5)", (sid, cat["id"]))  # scanned before signing up
    post(9, f"u{cat['id']}")
    post(9, f"u{cat['id']}", False)
    assert tuple(con.execute("SELECT scanned_at, done_at FROM qr_marks WHERE session_id = ? AND user_id = ?", (sid, cat["id"])).fetchone()) == (5, None)

    # a door helper undoes only their own hand marks
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', 1, 0)", (eid, h["id"], oid))
    post(4, f"r{rid}", False)
    assert _row(c, 9, eid, f"r{rid}")["at"]

    # a roster row whose person is a member already is listed once; a roster row gone takes its hand marks
    con.execute("UPDATE users SET tg_username = 'zhan' WHERE id = ?", (bob["id"],))
    assert not [r for r in c.get(f"/api/events/{eid}/door-team", headers=tma(9)).json()["rows"] if r["key"] == f"r{rid}"]
    con.execute("DELETE FROM roster_pending WHERE id = ?", (rid,))
    assert not con.execute("SELECT 1 FROM qr_hand_marks WHERE who = ?", (f"r{rid}",)).fetchone()
    con.close()


def test_an_expected_mail_goes_with_the_account(env):
    """An admin's expected row marked by hand (x<mail>): deleting that student's account takes the mark's mail too."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _qr(c, 9, eid)
    sid = _crew(con, eid)["id"]
    zed = login(c, 7, "zed")
    con.execute("UPDATE students SET email = 'zed@kbtu.kz' WHERE user_id = ?", (zed["id"],))
    con.execute("INSERT INTO qr_expected (session_id, email, full_name) VALUES (?, 'zed@kbtu.kz', 'Zed Z')", (sid,))
    assert c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": "xzed@kbtu.kz"}).status_code == 200
    delete_now(c, cfg, tma(7))
    assert not con.execute("SELECT 1 FROM qr_hand_marks WHERE who LIKE '%zed%'").fetchone()
    con.close()


def test_door_helper_runs_the_same_mark_screen(env):
    """A helper a President named (crew "door") opens the event's QR and its lists, as the club's own do."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _qr(c, 9, eid)
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', 1, 0)", (eid, h["id"], oid))
    s = c.post(f"/api/events/{eid}/screen", headers=tma(4)).json()
    assert c.post(f"/api/screens/{s['session']}/show", headers=tma(4)).json()["param"]
    assert c.get(f"/api/events/{eid}/door-team", headers=tma(4)).status_code == 200
    con.close()


def test_one_list_of_helpers(env):
    """The Mark screen's «Helper» (CrewSheet): whom the helper's QR let in is listed with the named ones, and taken out there."""
    from test_qr_helpers import _in
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)                                                              # bob (tg 2) let in by the QR
    bob = c.get("/api/me", headers=tma(2)).json()["id"]
    crew = c.get(f"/api/events/{eid}", headers=tma(9)).json()["crew"]
    assert [(x["person"]["id"], x["kind"]) for x in crew] == [(bob, "qr")]
    assert c.get(f"/api/events/{eid}", headers=tma(2)).json()["myCrew"] == "scan"           # the screen says scanner only
    assert c.delete(f"/api/events/{eid}/crew/{bob}", headers=tma(2)).status_code in (403, 404) and con.execute("SELECT 1 FROM qr_helpers").fetchone()  # not theirs to take
    assert c.delete(f"/api/events/{eid}/crew/{bob}", headers=tma(9)).json() == []
    assert not con.execute("SELECT 1 FROM qr_helpers").fetchone()
    con.close()


def test_named_helper_shows_the_qr_before_the_door(env):
    """Before the door time the organizer shows the QR (the team comes early); a named helper sees the same, no 409."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    t0 = int(time.time()) + 2 * 3600
    oid, ann, eid = _setup(c, con, t0)
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', 1, 0)", (eid, h["id"], oid))
    s = c.post(f"/api/events/{eid}/screen", headers=tma(4)).json()
    assert c.post(f"/api/screens/{s['session']}/start", headers=tma(4)).status_code == 200
    assert c.post(f"/api/screens/{s['session']}/show", headers=tma(4)).json()["param"]
    assert c.post(f"/api/screens/{s['session']}/show", headers=tma(1)).status_code == 409   # a plain member: at the door time, as before
    con.close()
