import io
import time

import pytest

from kbtu import admin, bot, db, logic
from kbtu.logic import guests
from test_core import _club_runs, env, login, set_clock, tma  # noqa: F401


@pytest.fixture
def door_event(env):
    c, cfg = env
    with db.connect(cfg.db_path) as con:
        org = _club_runs(c, con, 9, "door")
        con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 9")
        start = logic.now() + 300
        con.execute("""INSERT INTO events (id, org_id, status, title, starts_at, ends_at, price, pay_to_name, pay_phone, created_at, updated_at)
            VALUES (1, ?, 'published', 'Paper tickets', ?, ?, 2000, 'Test Club', '+77000000000', 0, 0)""", (org, start, start + 7200))
        yield c, cfg, con
    con.close()


def _student(c, con, tg, sid, manual=0):
    me = login(c, tg, f"guest{tg}")
    con.execute("UPDATE students SET student_id = ?, manual = ? WHERE user_id = ?", (sid, manual, me["id"]))
    return me["id"]


def _sign_in(c, con, tg, sid, surname="Student"):
    uid = c.get("/api/me", headers=tma(tg)).json()["id"]
    logic.ms_remember(con, uid, {"oid": f"test-{tg}", "email": f"student{tg}@kbtu.kz", "first": "Test", "last": surname,
                                "employeeId": sid})
    signed = c.post("/api/kbtu/manual", headers=tma(tg), json={"studentId": sid, "consentVersion": logic.CONSENT})
    assert signed.status_code == 200, signed.text
    return uid


def test_guest_import_and_claim_on_sign_in(door_event, monkeypatch, capsys):
    c, cfg, con = door_event
    verified = _student(c, con, 1, "24B030001")
    manual = _student(c, con, 2, "24B030002", manual=1)
    con.executemany("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, created_at, updated_at)
        VALUES (1, ?, 'hold', ?, ?, 0, 0)""", ((verified, "1-TEST", logic.now() + 60), (manual, "1-OLD", logic.now() + 60)))
    source = ('\ufeffstudent_id,adult,username,full_name\n"24b030001",1,,Ivan \u0422\u0401\u0421\u0422\u041e\u0412\n'
              '24B030002,0,,sTUDENT Jane\n24B030003,,,Jane Student\n24B030004,1,,Jane Buyer\n'
              '"broken\n24B030005,yes,,Jane Student\n')
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    for _ in range(2):
        monkeypatch.setattr(admin.sys, "stdin", io.StringIO(source))
        admin.main(["guests", "1"])
        assert capsys.readouterr().out == "registered 1, pending 3, offline 0, bad rows 2\n"
    assert [tuple(r) for r in con.execute("""SELECT user_id, status, ticket_code, hold_until FROM registrations
        WHERE event_id = 1 ORDER BY user_id""")] == [(verified, "going", "1-TEST", None), (manual, "cancelled", "1-OLD", None)]
    assert [tuple(r) for r in con.execute("SELECT student_id, adult FROM event_guests ORDER BY student_id")] == [
        ("24B030002", 0), ("24B030003", None), ("24B030004", 1)]
    codes = dict(con.execute("SELECT student_id, surname_hash FROM event_guests"))
    assert all(isinstance(code, bytes) and b"jane" not in code.lower() for code in codes.values())
    assert codes["24B030002"] != codes["24B030003"]  # the same name under a different number has a different code
    card = c.get("/api/events/1", headers=tma(1)).json()
    assert card["guestList"] is True and card["ageCheck"] is True

    # Signing in with Microsoft supersedes a previous unverified claim to the same student ID.
    uid = _sign_in(c, con, 3, "24B030002")
    assert uid != manual
    claimed = con.execute("""SELECT r.status, r.ticket_code, a.adult FROM registrations r
        JOIN reg_age a ON a.registration_id = r.id WHERE r.event_id = 1 AND r.user_id = ?""", (uid,)).fetchone()
    assert claimed["status"] == "going" and claimed["ticket_code"].startswith("1-") and claimed["adult"] == 0
    assert not con.execute("SELECT 1 FROM event_guests WHERE student_id = '24B030002'").fetchone()
    other = _sign_in(c, con, 12, "24B030004", surname="Buyers")
    assert not con.execute("SELECT 1 FROM registrations WHERE user_id = ?", (other,)).fetchone()
    assert con.execute("SELECT adult FROM event_guests WHERE student_id = '24B030004'").fetchone()[0] == 1
    end = logic.now() - 1
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = 1", (end - 3600, end))
    later = _sign_in(c, con, 4, "24B030003")
    assert not con.execute("SELECT 1 FROM registrations WHERE user_id = ?", (later,)).fetchone()
    assert con.execute("SELECT 1 FROM event_guests WHERE student_id = '24B030003'").fetchone()


def test_guest_import_username_fallback(door_event, monkeypatch, capsys):
    c, cfg, con = door_event
    by_id = _student(c, con, 1, "24B030001")
    by_handle = _student(c, con, 2, "24B030002")
    no_id = _student(c, con, 3, "24B030003")
    invalid_id = _student(c, con, 4, "24B030004")
    manual = _student(c, con, 5, "24B030005", manual=1)
    duplicate = _student(c, con, 6, "24B030006")
    duplicate_other = _student(c, con, 7, "24B030007")
    staff = _student(c, con, 8, "24B030008")
    previous_owner = _student(c, con, 10, "24B030010")
    current_owner = c.get("/api/me", headers=tma(11)).json()["id"]
    wrong_name = _student(c, con, 12, "24B030012")
    con.execute("UPDATE students SET consent_version = 'staff' WHERE user_id = ?", (staff,))
    con.execute("UPDATE students SET last_lat = 'Akhmetov' WHERE user_id = ?", (invalid_id,))
    con.execute("UPDATE students SET last_name = 'Other' WHERE user_id = ?", (wrong_name,))
    con.executemany("UPDATE users SET tg_username = ? WHERE id = ?", [
        ("ByHandle", by_handle), ("NoId", no_id), ("InvalidId", invalid_id), ("Manual", manual),
        ("Duplicate", duplicate), ("duplicate", duplicate_other), ("StaffHandle", staff),
        ("ReusedHandle", previous_owner), ("reusedhandle", current_owner), ("WrongName", wrong_name)])
    assert guests.import_csv(con, 1, ["24B030011,0,,Jane Testov"]) == (0, 1, 0, 0)

    source = (
        "\ufeffstudent_id,adult,tg_username,full_name\n"
        "24B030001,1,NoId,Testov Jane Middle\n"
        "24B030011,, @BYHANDLE ,Jane Testov\n"
        "24B030012,1,@BYHANDLE,Jane Testov\n"
        ",0,noid,Jane Testov\n"
        "unknown,1,@invalidid,Ahmetov Jane\n"
        "24B030005,,manual,Jane Testov\n"
        "24B030013,1,@DUPLICATE,Jane Testov\n"
        ",,manual,Jane Testov\n,,staffhandle,Jane Testov\n,,missing,Jane Testov\n"
        ",,reusedhandle,Jane Testov\n,,duplicate,Jane Testov\n,,wrongname,Jane Testov\n"
        ",yes,byhandle,Jane Testov\n"
    )
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    monkeypatch.setattr(admin.sys, "stdin", io.StringIO(source))
    admin.main(["guests", "1"])
    assert capsys.readouterr().out == "registered 3, pending 4, offline 6, bad rows 1\n"
    assert {tuple(r) for r in con.execute("""SELECT r.user_id, a.adult FROM registrations r
        JOIN reg_age a ON a.registration_id = r.id WHERE r.event_id = 1 AND r.status = 'going'""")} == {
        (by_id, 1), (no_id, 0), (invalid_id, 1)}
    assert not con.execute("SELECT 1 FROM registrations WHERE user_id IN (?, ?)", (by_handle, wrong_name)).fetchone()
    assert [tuple(r) for r in con.execute("SELECT student_id, adult FROM event_guests ORDER BY student_id")] == [
        ("24B030005", None), ("24B030011", 0), ("24B030012", 1), ("24B030013", 1)]


@pytest.mark.parametrize("source", [
    "", "student_id,adult,username,full_name\n",
    "24B030001,1\n24B030001,yes,,Jane Testov\n24B030001,0,,\ninvalid,0,,Jane Testov\n",
])
def test_guest_import_refuses_zero_valid_rows(door_event, monkeypatch, source):
    c, cfg, con = door_event
    uid = _student(c, con, 1, "24B030001")
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at)
        VALUES (1, ?, 'going', '1-OLD', 0, 0)""", (uid,))
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    monkeypatch.setattr(admin.sys, "stdin", io.StringIO(source))
    with pytest.raises(SystemExit, match="guest CSV has no valid rows"):
        admin.main(["guests", "1"])
    assert tuple(con.execute("SELECT guest_list, age_check FROM events WHERE id = 1").fetchone()) == (0, 0)
    assert tuple(con.execute("SELECT status, ticket_code FROM registrations WHERE event_id = 1").fetchone()) == ("going", "1-OLD")
    assert not con.execute("SELECT 1 FROM event_guests").fetchone()
    assert not con.execute("SELECT 1 FROM reg_age").fetchone()


def test_guest_signup_and_walk_in_blocked_but_tickets_check_in(door_event):
    c, _, con = door_event
    scanned = _student(c, con, 1, "24B030001")
    named = _student(c, con, 2, "24B030002")
    shown = _student(c, con, 3, "24B030003")
    outsider = _student(c, con, 4, "24B030004")
    guests.import_csv(con, 1, ["24B030001,1,,Jane Testov", "24B030002,0,,Jane Testov", "24B030003,,,Jane Testov"])
    base, door = "/api/events/1", tma(9)
    assert c.post(f"{base}/registration", headers=tma(4), json={}).json()["error"] == "guest_list"
    assert c.post(f"{base}/receipt", headers=tma(4), content=b"receipt").json()["error"] == "guest_list"
    # Turning a guest-list event free or capping its seats still permits no walk-in or waitlist.
    con.execute("UPDATE events SET price = NULL, seats = 1 WHERE id = 1")
    assert c.post(f"{base}/registration", headers=tma(4), json={}).json()["error"] == "guest_list"
    badge = f"u_{outsider}_" + con.execute("SELECT qr_code FROM users WHERE id = ?", (outsider,)).fetchone()[0]
    assert c.post(f"{base}/checkin", headers=door, json={"code": badge}).json()["error"] == "guest_list"
    assert c.post(f"{base}/checkin", headers=door, json={"userId": outsider}).json()["error"] == "guest_list"

    code = con.execute("SELECT ticket_code FROM registrations WHERE event_id = 1 AND user_id = ?", (scanned,)).fetchone()[0]
    result = c.post(f"{base}/checkin", headers=door, json={"code": code.split("-")[1]}).json()
    assert result["result"] == "ok" and result["adult"] is True
    result = c.post(f"{base}/checkin", headers=door, json={"userId": named}).json()
    assert result["result"] == "ok" and result["adult"] is False
    session = c.post(f"{base}/screen", headers=door).json()["session"]
    param = c.post(f"/api/screens/{session}/start", headers=door).json()["param"]
    assert c.post("/api/checkin", headers=tma(3), json={"p": param}).json()["error"] == "forbidden"  # 18+: the scanner, never the room's QR
    assert c.post("/api/checkin", headers=tma(4), json={"p": param}).json()["error"] == "forbidden"
    assert c.post(f"/api/screens/{session}/badge", headers=door, json={"qr": badge}).json()["error"] == "guest_list"
    assert {tuple(r) for r in con.execute("SELECT user_id, walk_in FROM registrations WHERE checked_in_at IS NOT NULL")} == {
        (scanned, 0), (named, 0)}
    assert not con.execute("SELECT 1 FROM qr_marks WHERE user_id = ?", (outsider,)).fetchone()


def test_guest_door_age_notify_and_retention(door_event, monkeypatch):
    c, cfg, con = door_event
    minor = _student(c, con, 1, "24B030001")
    adult = _student(c, con, 2, "24B030002")
    absent = _student(c, con, 3, "24B030003")
    unknown = _student(c, con, 4, "24B030004")
    helper = _student(c, con, 5, "24B030006")
    con.execute("""INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at)
        SELECT id, ?, org_id, 'scan', (SELECT id FROM users WHERE tg_id = 9), 0 FROM events WHERE id = 1""", (helper,))
    guests.import_csv(con, 1, ["24B030001,1,,Jane Testov", "24B030002,1,,Jane Testov", "24B030003,0,,Jane Testov",
                               "24B030004,,,Jane Testov", "24B030005,0,,Jane Testov"])
    base, door, scanner = "/api/events/1", tma(9), tma(5)
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    monkeypatch.setattr(bot, "now", lambda: now)
    assert c.post(f"{base}/age", headers=tma(1), json={"user_id": minor, "adult": False}).status_code == 403
    assert c.post(f"{base}/age/notify", headers=tma(1)).status_code == 403
    assert c.post(f"{base}/age", headers=door, json={"user_id": 9999, "adult": True}).status_code == 404
    assert c.post(f"{base}/age", headers=door, json={"user_id": minor, "adult": 0}).status_code == 400
    assert c.post(f"{base}/age", headers=scanner, json={"user_id": minor, "adult": False}).status_code == 404
    for uid, expected in ((minor, True), (adult, True), (unknown, None)):
        assert c.post(f"{base}/checkin", headers=door, json={"userId": uid}).json()["adult"] is expected
    assert c.post(f"{base}/age", headers=scanner, json={"user_id": minor, "adult": False}).json() == {"adult": False}
    assert c.post(f"{base}/age", headers=scanner, json={"user_id": helper, "adult": False}).status_code == 403
    assert c.post(f"{base}/age/notify", headers=scanner).status_code == 403
    guests.import_csv(con, 1, ["24B030001,1,,Jane Testov", "24B030003,1,,Jane Testov"])
    assert tuple(con.execute("""SELECT a.adult, a.set_by, a.set_at FROM reg_age a JOIN registrations r ON r.id = a.registration_id
        WHERE r.event_id = 1 AND r.user_id = ?""", (minor,)).fetchone()) == (0, helper, now)
    assert {p["person"]["id"]: p["adult"] for p in c.get(f"{base}/door", headers=door).json()} == {
        minor: False, adult: True, absent: True, unknown: None}
    assert "adult" not in c.get(base, headers=tma(1)).json()["my"]
    assert c.post(f"{base}/age/notify", headers=door).json() == {"count": 1}
    msg = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'u18_leave'").fetchone(), lang="en")
    assert msg["user_id"] == minor and bot._render(con, msg)[1:] == ("Open the event", "ev_1")
    con.execute("UPDATE events SET starts_at = starts_at + 86400, ends_at = ends_at + 86400 WHERE id = 1")
    assert bot._render(con, msg) is None
    assert c.post(f"{base}/age/notify", headers=door).json()["error"] == "closed"
    con.execute("UPDATE events SET starts_at = starts_at - 86400, ends_at = ends_at - 86400 WHERE id = 1")
    c.post(f"{base}/age", headers=door, json={"user_id": minor, "adult": True})
    assert bot._render(con, msg) is None
    c.post(f"{base}/age", headers=door, json={"user_id": minor, "adult": False})
    now += 599
    assert c.post(f"{base}/age/notify", headers=door).status_code == 429
    now += 1
    assert c.post(f"{base}/age/notify", headers=door).json() == {"count": 1}

    con.execute("""INSERT INTO events (id, org_id, title, created_at, updated_at)
        SELECT 2, org_id, 'Undated draft', ?, ? FROM events WHERE id = 1""", (now, now))
    assert guests.import_csv(con, 2, ["24B030001,0,,Jane Testov", "24B030005,0,,Jane Testov"]) == (1, 1, 0, 0)
    end = con.execute("SELECT ends_at FROM events WHERE id = 1").fetchone()[0]
    monkeypatch.setattr(logic, "stats_day", lambda con: None)
    monkeypatch.setattr(bot, "backup_day", lambda cfg, con: None)
    now = end + 86399
    bot._chores(cfg, con)
    assert con.execute("SELECT COUNT(*) FROM reg_age").fetchone()[0] == 3
    assert [r[0] for r in con.execute("SELECT event_id FROM event_guests")] == [1]
    now += 1
    bot._chores(cfg, con)
    for table in ("reg_age", "event_guests"):
        assert not con.execute(f"SELECT 1 FROM {table}").fetchone()
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'u18_leave'").fetchone()
    assert not con.execute("SELECT 1 FROM meta WHERE key = 'u18:1'").fetchone()
    assert con.execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 5


def test_guest_age_deleted_when_ended_ticket_is_anonymized(door_event):
    c, _, con = door_event
    uid = _student(c, con, 1, "24B030001")
    guests.import_csv(con, 1, ["24B030001,0,,Jane Testov"])
    end = logic.now() - 1
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = 1", (end - 3600, end))
    logic.delete_me(con, logic.Viewer(uid, "user", True))
    assert con.execute("SELECT user_id FROM registrations WHERE event_id = 1").fetchone()[0] != uid
    assert not con.execute("SELECT 1 FROM reg_age").fetchone()


def test_reg_until_closes_sign_up(door_event, monkeypatch):
    c, cfg, con = door_event
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    starts = con.execute("SELECT starts_at FROM events WHERE id = 1").fetchone()[0]
    from datetime import datetime, timezone
    at = datetime.fromtimestamp(starts - 3600, timezone.utc).isoformat()
    admin.main(["reg-until", "1", at])
    assert tuple(con.execute("SELECT reg_until, late_signup FROM events WHERE id = 1").fetchone()) == (starts - 3600, 0)
    with pytest.raises(SystemExit):
        admin.main(["reg-until", "1", datetime.fromtimestamp(starts + 60, timezone.utc).isoformat()])


def test_guests_from_a_gz_argument(door_event, monkeypatch, capsys):
    import base64
    import gzip
    c, cfg, con = door_event
    _student(c, con, 1, "24B030001")
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    monkeypatch.setattr(admin.sys, "stdin", io.StringIO(""))  # the gate passes no stdin
    data = base64.b64encode(gzip.compress("24B030001,1,,Ivan \u0422\u0401\u0421\u0422\u041e\u0412\n24B030009,0,,Jane Buyer\n".encode())).decode()
    admin.main(["guests", "1", "--gz", data])
    assert capsys.readouterr().out == "registered 1, pending 1, offline 0, bad rows 0\n"
    with pytest.raises(SystemExit):
        admin.main(["guests", "1", "--gz", "not base64!"])


def test_door_extra_counts_outsiders_anonymously(door_event):
    """Outsiders let in without the app: one bare count per event, +1/-1 by the door, never below zero, nobody named."""
    c, cfg, con = door_event
    base, door = "/api/events/1/door-extra", tma(9)
    assert c.get(base, headers=door).json() == {"extra": 0}
    assert c.post(base, headers=door, json={"step": 1}).json() == {"extra": 1}
    assert c.post(base, headers=door, json={"step": 1}).json() == {"extra": 2}
    assert c.post(base, headers=door, json={"step": -1}).json() == {"extra": 1}
    assert c.post(base, headers=door, json={"step": 5}).status_code == 400
    stranger = _student(c, con, 1, "24B030001")
    assert c.post(base, headers=tma(1), json={"step": 1}).status_code == 403 and stranger
    c.post(base, headers=door, json={"step": -1}); c.post(base, headers=door, json={"step": -1})
    assert c.get(base, headers=door).json() == {"extra": 0}


def test_door_lets_in_a_buyer_not_in_the_app(door_event):
    """The door types a list buyer's student ID and surname: only a matching surname lets them in; their ticket comes
    checked in when they sign in; the door sees the count."""
    c, cfg, con = door_event
    guests.import_csv(con, 1, ["24B030001,1,,Jane Testov", "24B030002,,,Ivan Petrov"])
    base, door = "/api/events/1/door-pending", tma(9)
    assert c.get(base, headers=door).json() == {"pending": 2, "pendingCame": 0}
    assert c.post(base, headers=door, json={"studentId": "24B030001", "surname": "Wrong"}).status_code == 404
    assert c.post(base, headers=door, json={"studentId": "24B039999", "surname": "Testov"}).status_code == 404
    r = c.post(base, headers=door, json={"studentId": "24b030001", "surname": "TESTOV"}).json()
    assert r == {"already": False, "adult": True, "pending": 2, "pendingCame": 1}
    assert c.post(base, headers=door, json={"studentId": "24B030002", "surname": "Petrov", "adult": False}).json()["adult"] is False
    assert c.post(base, headers=tma(1), json={"studentId": "24B030002", "surname": "Petrov"}).status_code == 403  # not the door
    # signing in later: the ticket, already checked in
    uid = _student(c, con, 1, "24B030001")
    guests.claim(con, uid)
    assert con.execute("SELECT checked_in_at IS NOT NULL FROM registrations WHERE event_id = 1 AND user_id = ?", (uid,)).fetchone()[0] == 1
