"""Access decisions at the event door and its exports."""
import time

import pytest

from kbtu import db, logic
from test_checkin_door import _ev, _mem, _qr, _reg
from test_core import _club_runs, env, login, set_clock, tma  # noqa: F401
from test_review_checkin import _scan


def _ticket(c, eid, tg, code):
    return c.post(f"/api/events/{eid}/checkin", headers=tma(tg), json={"code": code})


@pytest.mark.parametrize("restricted", ["members", "department", "board", "leaders", "school"])
def test_walk_in_checks_the_attendees_audience(env, restricted):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    vis = "members" if restricted in ("board", "department") else "public" if restricted == "school" else restricted
    eid = _ev(con, oid, int(time.time()), vis=vis)
    if restricted in ("board", "department"):
        user = _mem(c, con, oid, 1, "ann")
        if restricted == "board":
            con.execute("UPDATE events SET for_board = 1 WHERE id = ?", (eid,))
        else:
            tag = con.execute("INSERT INTO org_tags (org_id, name, color, created_at) VALUES (?, 'Other', 'blue', 0)", (oid,)).lastrowid
            con.execute("UPDATE events SET meeting_tag = ? WHERE id = ?", (tag, eid))
    else:
        user = login(c, 1, "ann")
    if restricted == "school":
        con.execute("UPDATE events SET school = 'other' WHERE id = ?", (eid,))
    _, q = _qr(c, 9, eid)
    uid = user["id"]
    badge = f"u_{uid}_" + con.execute("SELECT qr_code FROM users WHERE id = ?", (uid,)).fetchone()[0]
    assert _ticket(c, eid, 9, badge).json()["result"] == "not_found"
    marked = _scan(c, 1, q["param"]).json()
    assert not marked["done"] and marked["event"] is None and marked["title"] != "Party"
    assert not con.execute("SELECT 1 FROM registrations WHERE user_id = ?", (uid,)).fetchone()


@pytest.mark.parametrize("change", ["status = 'cancelled'", "hidden_at = 1"])
def test_unavailable_event_refuses_code_and_name(env, change):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    eid = _ev(con, oid, int(time.time()))
    uid = login(c, 1, "ann")["id"]
    _reg(con, eid, uid, "TEST")
    con.execute(f"UPDATE events SET {change} WHERE id = ?", (eid,))
    for body in ({"code": "TEST"}, {"userId": uid}):
        assert c.post(f"/api/events/{eid}/checkin", headers=tma(9), json=body).json()["result"] == "closed"
    assert con.execute("SELECT checked_in_at FROM registrations WHERE user_id = ?", (uid,)).fetchone()[0] is None


def test_reissued_ticket_rotates_and_checks_in_once(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    eid = _ev(con, oid, int(time.time()) + 300)
    login(c, 1, "ann")
    route = f"/api/events/{eid}/registration"
    first = c.post(route, headers=tma(1)).json()["my"]["ticketCode"]
    assert c.delete(route, headers=tma(1)).json()["my"]["status"] == "cancelled"
    second = c.post(route, headers=tma(1)).json()["my"]["ticketCode"]
    assert second != first and _ticket(c, eid, 9, first).json()["result"] == "not_found"
    assert _ticket(c, eid, 9, second).json()["result"] == "ok"
    # Even if the generator draws the old ticket first, it cannot become another attendee's ticket.
    fresh = next(code for code in ("AAAA", "BBBB", "CCCC") if code not in (first, second))
    draw = iter(first + fresh)
    monkeypatch.setattr(logic.seats.secrets, "choice", lambda alphabet: next(draw))
    assert logic.seats._ticket_code(con, eid) == f"{eid}-{fresh}"


def test_ticket_misses_are_shared_and_scoped(env, monkeypatch):
    c, cfg = env
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    eid = _ev(con, oid, now)
    helper = login(c, 2, "helper")["id"]
    uid = login(c, 1, "ann")["id"]
    _reg(con, eid, uid, "PASS")
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'scan', 1, 0)", (eid, helper, oid))
    for _ in range(5):
        assert _ticket(c, eid, 2, "MISS").json()["result"] == "not_found"
    with pytest.raises(logic.ApiError, match="rate_limited"):
        logic.checkin(con, logic.Viewer(helper, "user", True), eid, "PASS")
    assert _ticket(c, eid, 9, "PASS").json()["result"] == "ok"
    now += 61
    assert _ticket(c, eid, 2, "PASS").json()["result"] == "already"


def test_temporary_qr_helper_cannot_check_themselves_in(env):
    from test_qr_helpers import _ask, _hand
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana", "chess")
    eid = _ev(con, oid, int(time.time()))
    uid = login(c, 2, "helper")["id"]
    _reg(con, eid, uid, "PASS")
    sid, _ = _qr(c, 9, eid)
    con.execute("UPDATE org_members SET role = 'vice' WHERE org_id = ? AND role = 'head'", (oid,))
    assert _ask(c, 2, _hand(c, sid)["param"], True).json()["joined"]
    qr = c.post(f"/api/screens/{sid}/show", headers=tma(2)).json()["param"]
    assert _scan(c, 2, qr).json()["message"] == "own"
    assert con.execute("SELECT checked_in_at FROM registrations WHERE user_id = ?", (uid,)).fetchone()[0] is None


def test_typed_number_cannot_match_another_expected_person(env):
    from kbtu import checkin
    from test_core import _csv
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    login(c, 1, "ann")
    sid = checkin.new(con, "Meeting", [{"name": "Other Person", "email": "other@example.test", "studentId": "24Bann",
                                        "phone": "123456"}], oid)
    qr = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert _scan(c, 1, qr).json()["done"]
    people = c.get(f"/api/screens/{sid}/people", headers=tma(9)).json()
    assert people == {"came": [], "other": ["Testov Ann"], "absent": ["Other Person"]}
    lines = _csv(c, 9, sid).splitlines()
    assert lines[1].startswith("came (not on the list),Testov Ann,") and "123456" not in lines[1]
    assert lines[2].startswith("absent,Other Person,")


def test_registration_phone_requires_this_events_signup(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = _club_runs(c, con, 9, "dana")
    eid = _ev(con, oid, int(time.time()) + 300)
    old, walk, shared = (login(c, n, s)["id"] for n, s in ((1, "old"), (2, "walk"), (3, "shared")))
    con.execute("UPDATE students SET phone = '+77000000000'")
    assert c.post(f"/api/events/{eid}/registration", headers=tma(1)).status_code == 200
    con.execute("UPDATE events SET needs_phone = 1 WHERE id = ?", (eid,))
    badge = f"u_{walk}_" + con.execute("SELECT qr_code FROM users WHERE id = ?", (walk,)).fetchone()[0]
    assert _ticket(c, eid, 9, badge).json()["result"] == "ok"
    assert c.post(f"/api/events/{eid}/registration", headers=tma(3)).status_code == 200
    viewer = logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = 9").fetchone()[0], "user", True)
    export = lambda: {r["first_name"]: r["phone"] for r in logic.attendees_export(con, viewer, eid)[1]}
    assert export() == {"Old": None, "Walk": None, "Shared": "+77000000000"}
    con.execute("UPDATE students SET phone = '+77000000001' WHERE user_id = ?", (shared,))
    assert export()["Shared"] is None
