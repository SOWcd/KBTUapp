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
    return next(r for r in c.get(f"/api/events/{eid}/team", headers=tma(tg)).json()["rows"] if r["key"] == key)


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
    assert r["done"] and r["team"] and _marks(con, g2, False) == 0
    c.get("/api/me", headers=tma(5))                                                       # no account yet: waits on the team's list
    r = _scan(c, 5, q2["param"]).json()
    assert not r["done"] and r["team"] and _marks(con, _crew(con, e2)["id"], False) == 2 and _marks(con, g2, False) == 0
    con.close()


def test_team_list_by_department_and_hand_marks(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    tag = con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, 'Media', '#000', 1, 0)", (oid,)).lastrowid
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (tag, ann["id"]))
    rid = con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, dept, full_name, tg, created_at) VALUES ('k1', ?, 's', 'member', 'Media', 'Petrov Zhan', 'zhan', 0)",
                      (oid,)).lastrowid
    lst = c.get(f"/api/events/{eid}/team", headers=tma(9)).json()
    assert lst["session"] is None and len(lst["rows"]) == 3                                # dana, ann, the roster row
    zhan = _row(c, 9, eid, f"r{rid}")
    assert zhan == {"key": f"r{rid}", "name": "Petrov Zhan", "group": "Media", "at": None, "manual": False, "app": False}
    assert _row(c, 9, eid, f"u{ann['id']}")["group"] == "Media"

    m = c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"r{rid}"}).json()  # before the QR: its organizer opens the team session
    assert m["session"] == _crew(con, eid)["id"]
    zhan = next(r for r in m["rows"] if r["key"] == f"r{rid}")
    assert zhan["at"] and zhan["manual"]
    c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"u{ann['id']}"})
    assert _row(c, 9, eid, f"u{ann['id']}")["manual"]
    c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False})  # undo
    assert _row(c, 9, eid, f"u{ann['id']}")["at"] is None and _marks(con, _crew(con, eid)["id"]) == 0
    assert c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": "r999999"}).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_hand'").fetchone()[0] == 2

    # a scan stays (it proves they came): undo takes back hand marks only
    _, q = _qr(c, 9, eid)
    assert _scan(c, 1, q["param"]).json()["team"]
    c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False})
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
    assert c.get(f"/api/events/{eid}/team", headers=tma(1)).status_code == 403            # a plain member: no list
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'scan', 1, 0)", (eid, h["id"], oid))
    assert c.get(f"/api/events/{eid}/team", headers=tma(4)).status_code == 403            # scanner only: no list
    con.execute("UPDATE event_crew SET kind = 'door' WHERE user_id = ?", (h["id"],))
    names = {r["name"] for r in c.get(f"/api/events/{eid}/team", headers=tma(4)).json()["rows"]}
    assert "Zhan P" in names and not any("Olegovich" in n for n in names)                   # the President gave the list: short names
    con.close()


def test_hand_marks_close_at_midnight_after_the_end(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _qr(c, 9, eid)
    c.post(f"/api/screens/{_qr(c, 9, eid)[0]}/finish", headers=tma(9))                     # the door closed: lists still fixed
    assert c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"u{ann['id']}"}).status_code == 200
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    monkeypatch.setattr(checkin, "now", lambda: checkin._until(e) + 1)
    assert c.post(f"/api/events/{eid}/team", headers=tma(9), json={"key": f"u{ann['id']}", "on": False}).status_code == 409
    con.close()


def test_a_markers_account_deleted_keeps_the_mark(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    rid = con.execute("INSERT INTO roster_pending (key, org_id, sheet, role, full_name, created_at) VALUES ('k3', ?, 's', 'member', 'Petrov Zhan', 0)", (oid,)).lastrowid
    h = login(c, 4, "hel")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', 1, 0)", (eid, h["id"], oid))
    _qr(c, 9, eid)
    assert c.post(f"/api/events/{eid}/team", headers=tma(4), json={"key": f"r{rid}"}).status_code == 200
    assert c.post(f"/api/events/{eid}/team", headers=tma(4), json={"key": f"u{ann['id']}"}).status_code == 200
    delete_now(c, cfg, tma(4))
    assert con.execute("SELECT marked_by FROM qr_hand_marks").fetchone()[0] is None        # the mark stays, its marker gone
    assert _row(c, 9, eid, f"r{rid}")["manual"] and _row(c, 9, eid, f"u{ann['id']}")["at"]
    con.close()
