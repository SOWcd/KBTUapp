"""Focused regressions for the check-in audit (H/M/L identifiers from REVIEW-checkin.md)."""
import csv
import io
import json
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kbtu import app, bot, checkin, db, logic, roster
from kbtu.logic import guests, organizing
from test_core import _csv, _paired, delete_now, env, login, set_clock, tma  # noqa: F401
from test_one_qr import _crew, _setup
from test_checkin_door import _qr, _reg
from test_review_checkin import _scan


@pytest.fixture
def door(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    host = con.execute("SELECT id FROM users WHERE tg_id = 9").fetchone()[0]
    yield c, cfg, con, oid, ann, eid, logic.Viewer(host, "user", True)
    con.close()


def _pending(con, oid, key="test", **fields):
    values = {"key": key, "org_id": oid, "sheet": "S", "role": "member", "full_name": "Testov Zed", "created_at": 0, **fields}
    rid = con.execute(f"INSERT INTO roster_pending ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})", tuple(values.values())).lastrowid
    return con.execute("SELECT * FROM roster_pending WHERE id = ?", (rid,)).fetchone()


def _mark(c, eid, key, on=True):
    return c.post(f"/api/events/{eid}/door-team", headers=tma(9), json={"key": key, "on": on})


def _csv_rows(c, sid):
    return list(csv.DictReader(io.StringIO(_csv(c, 9, sid).lstrip("\ufeff"))))


def test_h1_only_directory_identity_can_take_an_officer_row(door):
    c, _, con, oid, ann, _, _ = door
    zed = login(c, 3, "zed")
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    con.execute("UPDATE users SET tg_username = 'reused' WHERE id = ?", (zed["id"],))
    con.execute("UPDATE students SET email = 'ann@kbtu.kz', ms_oid = 'ann', ms_profile = ?, first_name = 'Edited' WHERE user_id = ?",
                (json.dumps({"givenName": "Ann", "surname": "Testov"}), ann["id"]))
    r = _pending(con, oid, email="ann@kbtu.kz", tg="reused", full_name="Testov Ann", role="vice", phone="+77012345678")
    assert roster.match(con, zed["id"]) == [] and roster.asks(con, zed["id"])
    assert not con.execute("SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", (oid, zed["id"])).fetchone()
    assert roster.match(con, ann["id"]) == [(oid, False)]
    assert con.execute("SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"])).fetchone()[0] == "vice"
    assert not con.execute("SELECT 1 FROM roster_pending WHERE id = ?", (r["id"],)).fetchone()


def test_h3_helper_list_uses_short_names_and_opaque_keys(door):
    c, _, con, oid, ann, eid, host = door
    con.execute("UPDATE events SET guest_list = 1 WHERE id = ?", (eid,))
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    con.execute("INSERT INTO event_guests (event_id, student_id, name) VALUES (?, '24B030001', 'Testov Zed Middle')", (eid,))
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at) VALUES (?, ?, ?, 'door', ?, 0)",
                (eid, ann["id"], oid, host.id))
    response = c.get(f"/api/events/{eid}/door-pending", headers=tma(1))
    row = response.json()["list"][0]
    assert row["name"] == "Zed T" and len(row["key"]) == 32
    assert "24B030001" not in response.text and "Middle" not in response.text
    assert c.post(f"/api/events/{eid}/door-pending/tick", headers=tma(1), json={"key": row["key"]}).json()["pendingCame"] == 1


def test_h4_age_check_blocks_every_self_service_completion(door, monkeypatch):
    c, cfg, con, _, ann, eid, _ = door
    _reg(con, eid, ann["id"], "AGE")
    sid, q = _qr(c, 9, eid)
    con.execute("UPDATE events SET age_check = 1, guest_list = 1 WHERE id = ?", (eid,))
    monkeypatch.setattr(checkin, "_guests", lambda *args: False)  # volunteer-ledger sessions use this branch
    scan = _scan(c, 1, q["param"])
    assert scan.status_code == 403 and scan.json()["message"] == "age"
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, ?)", (sid, ann["id"], int(time.time())))
    checkin.became_student(con, ann["id"])
    assert con.execute("SELECT checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, ann["id"])).fetchone()[0] is None
    headers = _paired(c, 9, sid)
    assert c.get("/api/screen", headers=headers).json()["param"] == f"tk_{eid}"


@pytest.mark.parametrize("path", ["room", "badge", "name"])
def test_h5_walk_ins_never_skip_capacity_or_the_queue(door, path):
    c, _, con, oid, ann, eid, host = door
    bob, cat = login(c, 2, "bob"), login(c, 3, "cat")
    con.execute("UPDATE events SET seats = 1, visibility = 'members' WHERE id = ?", (eid,))
    for u in (bob, cat):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, u["id"]))
    _reg(con, eid, ann["id"], "FULL")
    for n, u in enumerate((bob, cat)):
        rid = _reg(con, eid, u["id"], f"WAIT{n}")
        con.execute("UPDATE registrations SET status = 'waitlist', waitlisted_at = ? WHERE id = ?", (n, rid))

    def assert_refused():
        if path == "room":
            with db.tx(con):
                assert not organizing.screen_came(con, eid, cat["id"], logic.now())["done"]
        elif path == "badge":
            assert organizing.checkin(con, host, eid, "u_" + cat["qr"])["result"] == "closed"
        else:
            assert organizing.checkin_by_name(con, host, eid, cat["id"])["result"] == "closed"

    assert_refused()
    assert logic.taken(con, eid) == 1
    assert con.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = 'waitlist'", (eid,)).fetchone()[0] == 2
    con.execute("UPDATE events SET seats = 2 WHERE id = ?", (eid,))
    assert_refused()
    status = dict(con.execute("SELECT user_id, status FROM registrations WHERE event_id = ?", (eid,)))
    assert status[bob["id"]] == "going" and status[cat["id"]] == "waitlist"


def test_h6_member_cannot_queue_minor_notifications(door):
    _, _, con, _, ann, eid, _ = door
    con.execute("UPDATE events SET age_check = 1 WHERE id = ?", (eid,))
    with pytest.raises(logic.ApiError) as error:
        organizing.notify_minors(con, logic.Viewer(ann["id"], "user", True), eid)
    assert error.value.code == "forbidden"
    assert not con.execute("SELECT 1 FROM meta WHERE key = ?", (f"u18:{eid}",)).fetchone()


def test_h7_roster_snapshot_and_permissions_are_inside_creation_lock(door, monkeypatch):
    _, cfg, con, oid, _, _, host = door
    calls, original = [], checkin._people
    def people(conn, *args):
        calls.append(conn.in_transaction)
        return original(conn, *args)
    monkeypatch.setattr(checkin, "_people", people)
    checkin.club_new(con, cfg.token_key, host, oid, "Meeting")
    assert calls == [True]


@pytest.mark.parametrize("action", ["cancel", "delete"])
def test_m1_cancel_and_delete_terminally_close_both_sessions(door, action):
    c, _, con, _, ann, eid, host = door
    sid, q = _qr(c, 9, eid)
    crew = _crew(con, eid)["id"]
    con.execute("UPDATE qr_sessions SET started_at = NULL WHERE id = ?", (crew,))
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, 1)", (sid, ann["id"]))
    if action == "cancel":
        organizing.cancel_event(con, host, eid)
    else:
        organizing.delete_event(con, logic.Viewer(host.id, "admin", True), eid)
    for session in (sid, crew):
        assert con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (session,)).fetchone()[0]
        assert c.post(f"/api/screens/{session}/start", headers=tma(9)).status_code == 409
    checkin.became_student(con, ann["id"])
    assert not con.execute("SELECT 1 FROM qr_marks WHERE user_id = ?", (ann["id"],)).fetchone()
    assert _scan(c, 1, q["param"]).status_code == 409


@pytest.mark.parametrize("state", ["cancelled", "hidden"])
@pytest.mark.parametrize("path", ["tick", "surname"])
def test_m2_pending_admission_rejects_closed_events(door, state, path):
    _, _, con, _, _, eid, host = door
    con.execute("UPDATE events SET guest_list = 1 WHERE id = ?", (eid,))
    con.execute("INSERT INTO event_guests (event_id, student_id, name, surname_hash) VALUES (?, '24B030001', 'Testov Zed', ?)",
                (eid, guests._surname_hash(eid, "24B030001", "testov")))
    if state == "cancelled":
        con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (eid,))
    else:
        con.execute("UPDATE events SET hidden_at = 1 WHERE id = ?", (eid,))
    with pytest.raises(logic.ApiError):
        if path == "tick":
            organizing.tick_pending(con, host, eid, guests.door_list(con, eid)[0]["key"])
        else:
            organizing.let_in_pending(con, host, eid, "24B030001", "Testov")
    assert con.execute("SELECT came_at FROM event_guests WHERE event_id = ?", (eid,)).fetchone()[0] is None


@pytest.mark.parametrize("midnight", [False, True])
def test_m3_team_only_never_falls_through_to_guest_admission(door, monkeypatch, midnight):
    c, _, con, _, ann, eid, _ = door
    con.execute("UPDATE events SET door_audience = 'team' WHERE id = ?", (eid,))
    if midnight:
        start = ((int(time.time()) + 5 * 3600) // 86400 + 1) * 86400 - 5 * 3600 + 15 * 60
        now = start - 25 * 60
        con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (start, start + 3600, eid))
        set_clock(monkeypatch, lambda: now)
        monkeypatch.setattr(checkin, "now", lambda: now)
        monkeypatch.setattr(checkin.time, "time", lambda: now)
    sid, q = _qr(c, 9 if midnight else 1, eid)
    response = _scan(c, 1 if midnight else 9, q["param"])
    if midnight:
        assert response.json()["team"] and _crew(con, eid)
    else:
        assert response.status_code == 409
    assert not con.execute("SELECT 1 FROM registrations WHERE event_id = ?", (eid,)).fetchone()


def test_m4_by_name_does_not_revive_an_organizer_removal(door):
    _, _, con, _, ann, eid, host = door
    con.execute("UPDATE events SET visibility = 'members' WHERE id = ?", (eid,))
    rid = _reg(con, eid, ann["id"], "REMOVED")
    con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'removed' WHERE id = ?", (rid,))
    assert organizing.checkin_by_name(con, host, eid, ann["id"])["result"] == "cancelled"
    assert con.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (rid,)).fetchone()[0] is None


def test_m5_leaders_badge_still_requires_a_reservation(door):
    _, _, con, oid, ann, eid, host = door
    con.execute("UPDATE events SET visibility = 'leaders' WHERE id = ?", (eid,))
    con.execute("UPDATE org_members SET role = 'vice' WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    assert organizing.checkin(con, host, eid, "u_" + ann["qr"])["result"] == "not_found"
    assert not con.execute("SELECT 1 FROM registrations WHERE event_id = ?", (eid,)).fetchone()


def test_m6_telegram_only_ticket_is_on_lists_and_export(door):
    c, _, con, _, _, eid, host = door
    guest = c.get("/api/me", headers=tma(44, "Visitor")).json()
    con.execute("UPDATE events SET guest_list = 1 WHERE id = ?", (eid,))
    _reg(con, eid, guest["id"], "VISIT")
    assert any(r["person"]["id"] == guest["id"] for r in organizing.door(con, host, eid))
    attendee = next(r for r in organizing.attendees(con, host, eid) if r["person"]["id"] == guest["id"])
    assert "Visitor" in attendee["fullName"] and "None" not in attendee["fullName"]
    row = organizing.attendees_export(con, host, eid)[1][0]
    assert row["first_name"] == "Visitor" and row["student_id"] is None


def test_m7_age_recording_uses_the_six_hour_door_window(door, monkeypatch):
    _, _, con, oid, ann, eid, host = door
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    monkeypatch.setattr(bot, "now", lambda: now)
    con.execute("UPDATE org_members SET role = 'vice' WHERE org_id = ? AND user_id = ?", (oid, host.id))
    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL, age_check = 1 WHERE id = ?", (now - 4 * 3600, eid))
    rid = _reg(con, eid, ann["id"], "AGE")
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE id = ?", (now, rid))
    assert organizing.mark_age(con, host, eid, ann["id"], False) == {"adult": False}
    assert organizing.notify_minors(con, host, eid) == {"count": 1}
    message = con.execute("SELECT * FROM bot_outbox WHERE kind = 'u18_leave'").fetchone()
    assert bot._render(con, dict(message, lang="en"))[-1] == f"ev_{eid}"


def test_m8_repeat_scan_does_not_disclose_receipt_flags_to_members(door, monkeypatch):
    _, _, con, _, ann, eid, host = door
    rid = _reg(con, eid, host.id, "FLAG")
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE id = ?", (logic.now(), rid))
    monkeypatch.setattr(organizing, "flagged", lambda *args: True)
    result = organizing.checkin(con, logic.Viewer(ann["id"], "user", True), eid, "FLAG")
    assert result["result"] == "already" and not result["flagged"]


@pytest.mark.parametrize("path", ["room", "ticket", "name"])
def test_m9_existing_seat_does_not_bypass_current_membership(door, path):
    _, _, con, oid, ann, eid, host = door
    con.execute("UPDATE events SET visibility = 'members' WHERE id = ?", (eid,))
    rid = _reg(con, eid, ann["id"], "LEFT")
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    if path == "room":
        assert not organizing.screen_came(con, eid, ann["id"], logic.now())["done"]
    elif path == "ticket":
        assert organizing.checkin(con, host, eid, "LEFT")["result"] == "not_found"
    else:
        assert organizing.checkin_by_name(con, host, eid, ann["id"])["result"] == "not_found"
    assert con.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (rid,)).fetchone()[0] is None


def test_m12_manual_only_people_are_present_in_totals_lists_and_csv(door):
    c, _, con, oid, ann, eid, _ = door
    _qr(c, 9, eid)
    sid = _crew(con, eid)["id"]
    r = _pending(con, oid)
    con.execute("INSERT INTO qr_expected (session_id, email, full_name) VALUES (?, 'zed@kbtu.kz', 'Expected Zed')", (sid,))
    key = con.execute("SELECT door_key FROM qr_expected WHERE email = 'zed@kbtu.kz'").fetchone()[0]
    assert _mark(c, eid, 'r' + r["door_key"]).status_code == 200
    assert _mark(c, eid, 'x' + key).status_code == 200
    state = c.post(f"/api/screens/{sid}/show", headers=tma(9)).json()
    assert state["done"] == 2 and state["came"] == 1
    people = c.get(f"/api/screens/{sid}/people", headers=tma(9)).json()
    assert "Expected Zed" in people["came"] and "Testov Zed" in people["other"]
    present = {r["name"]: r for r in _csv_rows(c, sid) if r["status"] == "came"}
    assert present["Expected Zed"]["by_hand"] and present["Testov Zed"]["by_hand"]
    assert present["Testov Zed"]["email"] == ""


def test_m13_unstarted_manual_meeting_has_no_csv_tier(door):
    c, _, con, _, ann, eid, _ = door
    con.execute("UPDATE events SET visibility = 'members' WHERE id = ?", (eid,))
    sid = _mark(c, eid, f"u{ann['id']}").json()["session"]
    assert con.execute("SELECT started_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0] is None
    assert next(r for r in _csv_rows(c, sid) if r["student_id"] == "24Bann")["tier"] == ""


@pytest.mark.parametrize("path", ["room", "ticket"])
def test_m14_real_scan_survives_undo_of_an_earlier_manual_mark(door, path):
    c, _, con, _, ann, eid, host = door
    if path == "room":
        _, q = _qr(c, 9, eid)
        sid = _crew(con, eid)["id"]
        _mark(c, eid, f"u{ann['id']}")
        before = con.execute("SELECT done_at FROM qr_marks WHERE session_id = ? AND user_id = ?", (sid, ann["id"])).fetchone()[0]
        assert _scan(c, 1, q["param"]).json()["done"]
        _mark(c, eid, f"u{ann['id']}", False)
        assert tuple(con.execute("SELECT done_at, hand FROM qr_marks WHERE session_id = ? AND user_id = ?", (sid, ann["id"])).fetchone()) == (before, 0)
    else:
        _reg(con, eid, ann["id"], "REAL")
        organizing.checkin_by_name(con, host, eid, ann["id"])
        organizing.checkin(con, host, eid, "REAL")
        with pytest.raises(logic.ApiError):
            organizing.undo_checkin(con, host, eid, ann["id"])


def test_m15_roster_transfer_completes_pending_scan_without_losing_it(door):
    c, _, con, oid, ann, eid, host = door
    _qr(c, 9, eid)
    sid = _crew(con, eid)["id"]
    r = _pending(con, oid)
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, 10)", (sid, ann["id"]))
    con.execute("INSERT INTO qr_hand_marks (session_id, who, marked_by, at) VALUES (?, ?, ?, 20)", (sid, 'r' + r["door_key"], host.id))
    con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ?", (logic.now() - checkin.GRACE - 1, sid))
    roster.join(con, ann["id"], r)
    assert tuple(con.execute("SELECT scanned_at, done_at, marked_by, hand FROM qr_marks WHERE session_id = ? AND user_id = ?", (sid, ann["id"])).fetchone()) == (10, 20, host.id, 2)


def test_m16_scan_rereads_verification_after_the_write_lock(door):
    c, cfg, con, _, ann, eid, _ = door
    sid, q = _qr(c, 9, eid)
    assert checkin.mark(con, cfg.token_key, logic.Viewer(ann["id"], "user", False), q["param"])["done"]
    assert con.execute("SELECT done_at FROM qr_marks WHERE user_id = ?", (ann["id"],)).fetchone()[0]


def test_m17_csv_uses_physical_arrival_but_manual_completion_time(door):
    c, _, con, oid, ann, _, host = door
    sid = checkin.new(con, "Times", [], oid)
    con.execute("UPDATE qr_sessions SET started_at = 1 WHERE id = ?", (sid,))
    con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at, done_at, left_at) VALUES (?, ?, 3600, 4800, 7200)", (sid, ann["id"]))
    assert _csv_rows(c, sid)[0]["hours"] == "1.0"
    con.execute("UPDATE qr_marks SET hand = 2 WHERE session_id = ?", (sid,))
    assert _csv_rows(c, sid)[0]["hours"] == "0.7"


def test_m18_first_next_day_mark_creates_a_closed_crew_record(door, monkeypatch):
    c, _, con, _, ann, eid, _ = door
    end = con.execute("SELECT ends_at FROM events WHERE id = ?", (eid,)).fetchone()[0]
    now = ((end + 5 * 3600) // 86400 + 1) * 86400 - 5 * 3600 + 3600
    monkeypatch.setattr(checkin, "now", lambda: now)
    set_clock(monkeypatch, lambda: now)
    sid = _mark(c, eid, f"u{ann['id']}").json()["session"]
    assert con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).status_code == 409


def test_m19_undated_draft_has_a_closed_team_list(door):
    c, _, con, _, ann, eid, _ = door
    con.execute("UPDATE events SET status = 'draft', starts_at = NULL, ends_at = NULL WHERE id = ?", (eid,))
    assert not c.get(f"/api/events/{eid}/door-team", headers=tma(9)).json()["open"]
    assert c.get(f"/api/events/{eid}/door-team", headers=tma(1)).status_code == 403
    assert _mark(c, eid, f"u{ann['id']}").status_code == 409


def test_m20_displayed_phase_is_bound_to_the_qr(door):
    c, _, con, oid, ann, _, _ = door
    sid = checkin.new(con, "Phase", [], oid)
    arrival = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert _scan(c, 1, arrival).json()["done"]
    departure = c.post(f"/api/screens/{sid}/out", headers=tma(9)).json()["param"]
    assert departure != arrival and _scan(c, 1, arrival).status_code == 400
    assert con.execute("SELECT left_at FROM qr_marks WHERE session_id = ?", (sid,)).fetchone()[0] is None
    assert _scan(c, 1, departure).json()["left"]


def test_m21_hand_mark_validates_the_live_row_under_the_write_lock(door, monkeypatch):
    c, _, con, _, ann, eid, host = door
    _qr(c, 9, eid)
    original, locks = checkin.team, []
    def team(conn, *args):
        locks.append(conn.in_transaction)
        return original(conn, *args)
    monkeypatch.setattr(checkin, "team", team)
    checkin.team_mark(con, host, eid, f"u{ann['id']}")
    assert locks[0] is True


def test_m22_stale_roster_key_cannot_mark_a_reused_row_id(door):
    c, _, con, oid, _, eid, _ = door
    _qr(c, 9, eid)
    old = _pending(con, oid, "old")
    con.execute("DELETE FROM roster_pending WHERE id = ?", (old["id"],))
    new = _pending(con, oid, "new")
    assert old["id"] == new["id"] and old["door_key"] != new["door_key"]
    assert _mark(c, eid, 'r' + old["door_key"]).status_code == 404
    assert not con.execute("SELECT 1 FROM qr_hand_marks").fetchone()


def test_m23_pairing_counts_and_insert_share_one_write_lock(door, monkeypatch):
    _, cfg, con, _, _, _, _ = door
    original, locks = checkin.one, []
    def one(conn, sql, *args):
        if "COUNT(*) FROM qr_screens" in sql:
            locks.append(conn.in_transaction)
        return original(conn, sql, *args)
    monkeypatch.setattr(checkin, "one", one)
    checkin.pair(con, cfg.token_key, "192.0.2.1")
    assert locks == [True, True]


def test_m24_retention_erases_only_expired_unlinked_walk_ins(door, monkeypatch):
    _, _, con, _, ann, eid, host = door
    now = (int(time.time()) // 86400) * 86400 - 5 * 3600 + 60
    set_clock(monkeypatch, lambda: now)
    for name, at, uid in (("old", now - organizing.GUEST_DAYS, None), ("recent", now, None), ("linked", 0, ann["id"])):
        con.execute("INSERT INTO door_guests (event_id, name, norm, added_by, created_at, user_id) VALUES (?, ?, ?, ?, ?, ?)", (eid, name, name, host.id, at, uid))
    logic.daily.stats_day(con)
    assert {r[0] for r in con.execute("SELECT name FROM door_guests")} == {"recent", "linked"}


def test_m25_deletion_scrubs_the_manual_attendance_subject(door):
    c, cfg, con, _, ann, eid, _ = door
    _mark(c, eid, f"u{ann['id']}")
    delete_now(c, cfg, tma(1))
    assert all("who" not in json.loads(r[0]) for r in con.execute("SELECT data FROM audit_log WHERE action IN ('checkin_hand', 'checkin_unhand')"))


def test_m26_deletion_erases_verified_unclaimed_roster_and_hand_marks(door):
    c, cfg, con, oid, ann, eid, _ = door
    _qr(c, 9, eid)
    r = _pending(con, oid, email="ann@kbtu.kz", full_name="Testov Ann")
    other = _pending(con, oid, "other", email="ann@kbtu.kz", full_name="Someone Else")
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (oid, ann["id"]))
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    con.execute("INSERT INTO qr_hand_marks (session_id, who, at) VALUES (?, ?, 1)", (_crew(con, eid)["id"], 'r' + r["door_key"]))
    delete_now(c, cfg, tma(1))
    assert not con.execute("SELECT 1 FROM roster_pending WHERE id = ?", (r["id"],)).fetchone()
    assert con.execute("SELECT 1 FROM roster_pending WHERE id = ?", (other["id"],)).fetchone()
    assert con.execute("SELECT 1 FROM meta WHERE key = ?", (f"roster_done:{r['key']}",)).fetchone()
    assert not con.execute("SELECT 1 FROM qr_hand_marks").fetchone()


def test_m27_finish_removes_helpers_from_linked_crew(door):
    c, _, con, _, ann, eid, host = door
    sid, _ = _qr(c, 9, eid)
    crew = _crew(con, eid)["id"]
    con.execute("INSERT INTO qr_helpers (session_id, user_id, added_by, created_at) VALUES (?, ?, ?, 0)", (crew, ann["id"], host.id))
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(9)).status_code == 200
    assert not con.execute("SELECT 1 FROM qr_helpers").fetchone()


def test_m28_pending_correction_preserves_claim_key_and_attendance(door):
    c, _, con, oid, ann, eid, host = door
    _qr(c, 9, eid)
    item = dict(sheet="S", full_name="Testov Zed", role="member", dept="Old", phone="+77012345678")
    roster.load(con, [item], {"S": "chess"})
    r = con.execute("SELECT * FROM roster_pending").fetchone()
    con.execute("UPDATE roster_pending SET claimed_by = ?", (ann["id"],))
    con.execute("INSERT INTO qr_hand_marks (session_id, who, at) VALUES (?, ?, 1)", (_crew(con, eid)["id"], 'r' + r["door_key"]))
    assert roster.load(con, [{**item, "dept": "New", "phone": "+77019876543"}], {"S": "chess"})["added"] == 0
    new = con.execute("SELECT * FROM roster_pending").fetchone()
    assert (new["id"], new["door_key"], new["claimed_by"]) == (r["id"], r["door_key"], ann["id"])
    assert (new["dept"], new["phone"]) == ("New", "+77019876543")
    assert con.execute("SELECT 1 FROM qr_hand_marks").fetchone()


def test_m29_imported_course_is_stamped_with_its_academic_year(door):
    _, _, con, oid, ann, _, _ = door
    con.execute("UPDATE students SET course = NULL, course_year = 2025, synced_at = 1 WHERE user_id = ?", (ann["id"],))
    roster.join(con, ann["id"], _pending(con, oid, course=2))
    assert tuple(con.execute("SELECT course, course_year FROM students WHERE user_id = ?", (ann["id"],)).fetchone()) == (2, logic.academic_year())


def test_m30_demoted_issuer_cannot_delegate_with_an_old_invite(door):
    c, _, con, oid, ann, eid, host = door
    con.execute("UPDATE org_members SET role = 'vice' WHERE org_id = ? AND user_id = ?", (oid, host.id))
    sid, _ = _qr(c, 9, eid)
    param = c.post(f"/api/screens/{sid}/helpers", headers=tma(9)).json()["param"]
    con.execute("UPDATE org_members SET role = 'member' WHERE org_id = ? AND user_id = ?", (oid, host.id))
    response = c.post("/api/screens/helper", headers=tma(1), json={"p": param, "join": True})
    assert response.status_code == 403 and not con.execute("SELECT 1 FROM qr_helpers").fetchone()


def test_l1_session_summary_reads_do_not_grow_per_session(door):
    _, cfg, con, oid, _, _, host = door
    def reads():
        queries = []
        con.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
        result = checkin.sessions(con, cfg.token_key, host)
        con.set_trace_callback(None)
        return len(queries), len(result)
    checkin.new(con, "One", [], oid)
    first, _ = reads()
    for n in range(20):
        checkin.new(con, f"Meeting {n}", [], oid)
    more, size = reads()
    assert size == 21 and more <= first + 1


def test_l2_csv_reads_each_marker_once(door, monkeypatch):
    c, _, con, oid, ann, _, host = door
    sid = checkin.new(con, "Markers", [], oid)
    for n in range(3):
        u = login(c, 30 + n, f"person{n}")
        con.execute("INSERT INTO qr_marks (session_id, user_id, scanned_at, done_at, marked_by) VALUES (?, ?, 1, 1, ?)", (sid, u["id"], host.id))
    calls, original = [], checkin.rows
    def rows(conn, sql, *args):
        if sql.startswith(logic.PERSON):
            calls.append(sql)
        return original(conn, sql, *args)
    monkeypatch.setattr(checkin, "rows", rows)
    assert all(r["by_hand"] for r in _csv_rows(c, sid))
    assert len(calls) == 1


def test_l3_claim_inbox_authorizes_each_club_once(door, monkeypatch):
    _, _, con, oid, ann, _, host = door
    for n in range(3):
        _pending(con, oid, f"claim{n}", claimed_by=ann["id"])
    calls = []
    monkeypatch.setattr(roster, "_approves", lambda *args: calls.append(args[2]) or True)
    assert len(roster.requests(con, host)) == 3 and calls == [oid]


def test_l4_team_door_excludes_registered_people_in_linear_work(door, monkeypatch):
    _, _, con, _, ann, eid, host = door
    con.execute("UPDATE events SET visibility = 'members' WHERE id = ?", (eid,))
    _reg(con, eid, ann["id"], "ONCE")
    reads = []
    class Person(dict):
        def __getitem__(self, key):
            if key == "id":
                reads.append(key)
            return super().__getitem__(key)
    original = organizing.rows
    def rows(conn, sql, *args):
        result = original(conn, sql, *args)
        return [Person(r) for r in result] if "r.door_team" in sql else result
    monkeypatch.setattr(organizing, "rows", rows)
    monkeypatch.setattr(organizing, "_expected", lambda *args: [ann["id"]] * 200)
    assert len(organizing.door(con, host, eid)) == 1 and len(reads) < 10


def test_l5_empty_legacy_guests_never_scan_all_student_names(door, monkeypatch):
    _, _, con, _, ann, _, _ = door
    original = organizing.rows
    def rows(conn, sql, *args):
        assert "SELECT first_name, last_name FROM students" not in sql
        return original(conn, sql, *args)
    monkeypatch.setattr(organizing, "rows", rows)
    organizing.link_door_guests(con, ann["id"])


def test_l7_screen_uses_the_configured_bot(door):
    _, cfg, _, _, _, _, _ = door
    c = TestClient(app.create(replace(cfg, bot_username="TestCheckinBot")))
    response = c.post("/api/screen/pair").json()
    assert response["bot"] == "https://t.me/TestCheckinBot?startapp="
    assert c.get("/api/screen", headers={"X-Screen": response["secret"]}).json()["bot"] == response["bot"]


def test_l8_banned_roster_match_is_not_reported_as_a_join(door):
    _, _, con, oid, ann, _, _ = door
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (oid, ann["id"]))
    item = dict(sheet="S", role="member", full_name="Testov Ann", email="ann@kbtu.kz")
    for _ in range(2):
        assert roster.load(con, [item], {"S": "chess"})["joined"] == 0
    assert con.execute("SELECT 1 FROM roster_pending").fetchone()
