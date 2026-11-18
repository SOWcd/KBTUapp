"""Only complete, matching OCR results count as checked payments; doubtful receipts still need the club."""
from __future__ import annotations

import time

import pytest

from kbtu import db, logic, receipt
from kbtu.logic import seats
from test_core import env, login, set_clock, tma  # noqa: F401 (env is a fixture)
from test_event_teams import _event, _go, _list, _people
from test_paid_teams import _rid
from test_review_seats import _shot
from test_team_guests import PAID, _club, _uid


@pytest.fixture
def paid(env, monkeypatch):
    c, cfg = env
    con = _club(c, cfg)
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    eid = _event(c, **PAID, teamMin=2, teamMax=2)
    people = _people(c, 3)
    return c, con, eid, people, now


def _fields(now, number="123456789012345678"):
    return {"amount": 2000, "recipient": "Arman A.", "no": number, "paid_at": now}


def _send(paid, monkeypatch, tg, fields, shade=240):
    c, con, eid, _, _ = paid
    monkeypatch.setattr(receipt, "read", lambda im: fields)
    response = c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=_shot(shade))
    assert response.status_code == 200, response.text
    assert response.json()["my"]["status"] == "going"
    return con.execute("SELECT * FROM receipts WHERE id = ?", (_rid(con, eid, tg),)).fetchone()


def _attendee(paid, tg):
    c, con, eid, _, _ = paid
    return next(a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
                if a["person"]["id"] == _uid(con, tg))


def _unchecked(paid, tg, row):
    c, con, eid, _, _ = paid
    assert row["status"] == "accepted"
    assert row["reviewed_at"] is None and row["reviewed_by"] is None
    assert _attendee(paid, tg)["reviewed"] is False
    assert _attendee(paid, tg)["auto"] is False
    assert _uid(con, tg) in _list(c, eid)["unchecked"]


def test_clean_receipt_is_checked_and_formable(paid, monkeypatch):
    c, con, eid, (a, b, _), now = paid
    for i, tg in enumerate((a, b)):
        assert _go(c, eid, tg).json()["my"]["status"] == "hold"
        row = _send(paid, monkeypatch, tg, _fields(now, str(123456789012345678 + i)), 240 + i)
        assert row["flags"] == "" and row["status"] == "accepted"
        assert row["reviewed_at"] == now and row["reviewed_by"] is None
        assert _attendee(paid, tg)["reviewed"] is True and _attendee(paid, tg)["auto"] is True
    assert _list(c, eid)["unchecked"] == []
    formed = c.post(f"/api/events/{eid}/teams/form", headers=tma(20)).json()
    assert formed["placed"] == 2
    assert {p["id"] for t in formed["teams"] for p in t["members"]} == {_uid(con, a), _uid(con, b)}


@pytest.mark.parametrize("change,flag", [
    ({"amount": 1500}, "amount_short"),
    ({"amount": 2001}, "amount_over"),
    ({"recipient": "Aisha N."}, "recipient_mismatch"),
    ({"paid_at": -1}, "too_early"),
    ({"no": None}, "unreadable"),
])
def test_each_flag_keeps_receipt_unchecked(paid, monkeypatch, change, flag):
    c, _, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, {**_fields(now), **change})
    assert row["flags"] == flag
    _unchecked(paid, tg, row)


@pytest.mark.parametrize("field,value", [(field, value) for field in ("amount", "recipient", "no", "paid_at")
                                       for value in ("missing", None)] + [("recipient", ""), ("no", "")])
def test_unread_essential_field_keeps_receipt_unchecked(paid, monkeypatch, field, value):
    c, _, eid, (tg, _, _), now = paid
    fields = _fields(now)
    if value == "missing":
        del fields[field]
    else:
        fields[field] = value
    _go(c, eid, tg)
    _unchecked(paid, tg, _send(paid, monkeypatch, tg, fields))


@pytest.mark.parametrize("change", [{"amount": 4000}, {"paid_at": "future"}])
def test_flagless_mismatch_is_not_clean(paid, monkeypatch, change):
    c, _, eid, (tg, _, _), now = paid
    if change.get("paid_at") == "future":
        change = {"paid_at": now + 1}
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, {**_fields(now), **change})
    assert row["flags"] == ""
    _unchecked(paid, tg, row)
    # A flagless doubtful receipt can still be approved by a human.
    assert c.post(f"/api/receipts/{row['id']}/review", headers=tma(20), json={"reject": False}).status_code == 204
    assert _attendee(paid, tg)["reviewed"] is True and _attendee(paid, tg)["auto"] is False


def test_ocr_absent_is_not_clean(paid, monkeypatch):
    c, _, eid, (tg, _, _), _ = paid
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, None)
    assert row["flags"] == ""
    _unchecked(paid, tg, row)


def test_empty_ocr_result_is_not_clean(paid, monkeypatch):
    c, con, eid, (tg, _, _), _ = paid
    _go(c, eid, tg)
    monkeypatch.setattr(receipt, "read", lambda im: {})
    response = c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=_shot())
    assert response.json()["error"] == "bad_input"
    assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    assert seats._receipt_clean(con, e, "unused", {}, "") is False


def test_blank_payee_is_not_clean(paid, monkeypatch):
    # '' passes the schema's CHECK (only NULL is refused on a priced published event), though the API wants 2+ chars
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    con.execute("UPDATE events SET pay_to_name = '' WHERE id = ?", (eid,))
    row = _send(paid, monkeypatch, tg, _fields(now))
    assert row["flags"] == ""
    assert row["reviewed_at"] is None and row["reviewed_by"] is None


def test_first_name_payee_is_not_clean(paid, monkeypatch):
    # "Arman" alone: same_person compares first names only, any Arman X. passes the flag check
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    con.execute("UPDATE events SET pay_to_name = 'Arman' WHERE id = ?", (eid,))
    row = _send(paid, monkeypatch, tg, {**_fields(now), "recipient": "Arman B."})
    assert row["flags"] == ""
    _unchecked(paid, tg, row)


@pytest.mark.parametrize("column,value", [("pay_to_name", None), ("price", None), ("price", 0)])
def test_missing_event_payment_details_are_not_clean(paid, column, value):
    # the schema refuses these on a published priced event (CHECK price > 0, payee NOT NULL), and the price is
    # fixed once a receipt is in: no seat can send a receipt then. The guard is still tested on a row as it reads.
    _, con, eid, _, now = paid
    e = {**dict(con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()), column: value}
    assert seats._receipt_clean(con, e, "unused", _fields(now), "") is False
    assert seats._receipt_clean(con, {**e, column: dict(con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone())[column]},
                                "unused", _fields(now), "") is True  # the same row with the real value is clean


def test_replacement_rechecks_all_fields(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    _unchecked(paid, tg, _send(paid, monkeypatch, tg, {**_fields(now), "amount": 1500}))
    partial = _fields(now, "223456789012345678")
    del partial["recipient"]
    _unchecked(paid, tg, _send(paid, monkeypatch, tg, partial, 241))
    clean = _send(paid, monkeypatch, tg, _fields(now, "323456789012345678"), 242)
    assert clean["reviewed_at"] == now and clean["reviewed_by"] is None
    assert _attendee(paid, tg)["auto"] is True
    assert con.execute("SELECT COUNT(*) FROM receipt_replaced").fetchone()[0] == 2
    assert _list(c, eid)["unchecked"] == []
    # Checked receipts retain the existing rule: the student cannot replace them again.
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=_shot(243)).json()["error"] == "closed"


@pytest.mark.parametrize("same_file", [False, True])
def test_duplicate_never_clean(paid, monkeypatch, same_file):
    c, _, eid, (a, b, _), now = paid
    for tg in (a, b):
        _go(c, eid, tg)
    _send(paid, monkeypatch, a, _fields(now))
    fields = _fields(now, "223456789012345678") if same_file else _fields(now)
    row = _send(paid, monkeypatch, b, fields, 240 if same_file else 241)
    assert row["flags"] == "duplicate"
    _unchecked(paid, b, row)


def test_replaced_number_never_clean_even_for_same_seat(paid, monkeypatch):
    c, _, eid, (a, b, _), now = paid
    _go(c, eid, a)
    _send(paid, monkeypatch, a, {**_fields(now), "amount": 1500})
    row = _send(paid, monkeypatch, a, _fields(now), 241)
    assert row["flags"] == ""  # existing flags exempt this seat's replaced receipts
    _unchecked(paid, a, row)
    _send(paid, monkeypatch, a, {**_fields(now, "223456789012345678"), "amount": 1500}, 242)
    _go(c, eid, b)
    row = _send(paid, monkeypatch, b, _fields(now), 243)
    assert row["flags"] == "duplicate"  # the deleted row's number is still remembered
    _unchecked(paid, b, row)


def test_organizer_can_open_and_reject_auto_checked_receipt(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, _fields(now))
    assert c.get(f"/api/receipts/{row['id']}/image", headers=tma(20)).status_code == 200
    assert c.post(f"/api/events/{eid}/team", headers=tma(tg), json={"name": "Vision"}).status_code == 200
    assert c.post(f"/api/receipts/{row['id']}/review", headers=tma(20), json={"reject": True}).status_code == 204
    rejected = con.execute("SELECT * FROM receipts WHERE id = ?", (row["id"],)).fetchone()
    assert rejected["status"] == "rejected" and rejected["reviewed_by"] == _uid(con, 20)
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 0
    reg = con.execute("SELECT status, cancel_reason FROM registrations WHERE id = ?", (row["registration_id"],)).fetchone()
    assert tuple(reg) == ("cancelled", "receipt_rejected")
    assert con.execute("SELECT COUNT(*) FROM event_team_members WHERE user_id = ?", (_uid(con, tg),)).fetchone()[0] == 0
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'receipt_rejected'", (_uid(con, tg),)).fetchone()


def test_old_unreviewed_receipt_cannot_replace_latest_checked_receipt(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    old = _send(paid, monkeypatch, tg, None)
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(tg)).status_code == 200
    _go(c, eid, tg)
    latest = _send(paid, monkeypatch, tg, _fields(now), 241)
    assert latest["id"] > old["id"] and latest["reviewed_at"] == now
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=_shot(242)).json()["error"] == "closed"
    assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 2


def test_own_replaced_file_is_not_clean_with_a_new_ocr_number(paid, monkeypatch):
    c, _, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    _send(paid, monkeypatch, tg, {**_fields(now), "amount": 1500})
    row = _send(paid, monkeypatch, tg, _fields(now, "223456789012345678"))
    assert row["flags"] == ""  # existing flags exempt this seat's replaced files
    _unchecked(paid, tg, row)


def test_deleted_human_reviewer_does_not_become_app(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    reviewer = login(c, 21, "vice")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0)", (reviewer["id"],))
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, _fields(now))
    assert c.post(f"/api/receipts/{row['id']}/review", headers=tma(21), json={"reject": False}).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 0
    logic.delete_me(con, logic.Viewer(reviewer["id"], "user", True))
    assert con.execute("SELECT reviewed_by FROM receipts WHERE id = ?", (row["id"],)).fetchone()[0] is None
    assert _attendee(paid, tg)["reviewed"] is True and _attendee(paid, tg)["auto"] is False


def test_migration_does_not_backfill_old_receipts(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, None)
    # A legacy human review whose reviewer was deleted is indistinguishable in the old columns.
    con.execute("UPDATE receipts SET reviewed_at = ? WHERE id = ?", (now, row["id"]))
    con.execute("DROP TABLE receipt_auto_checks")
    con.execute("PRAGMA user_version = 186")
    path = con.execute("PRAGMA database_list").fetchone()[2]
    db.init(path)
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 0
    assert _attendee(paid, tg)["reviewed"] is True and _attendee(paid, tg)["auto"] is False


def test_account_deletion_cascades_app_marker(paid, monkeypatch):
    c, con, eid, (tg, _, _), now = paid
    _go(c, eid, tg)
    _send(paid, monkeypatch, tg, _fields(now))
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 1
    logic.delete_me(con, logic.Viewer(_uid(con, tg), "user", True))
    assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 0


def test_spot_check_sends_one_clean_receipt_in_five_to_the_organizer(paid, monkeypatch):
    # (b) the 1 in 5 is seats._audit: the picked one waits as any unchecked receipt does (seat held, no new state)
    c, con, eid, (a, b, _), now = paid
    draws = iter([True, False])
    monkeypatch.setattr(seats, "_audit", lambda: next(draws))
    _go(c, eid, a)
    _go(c, eid, b)
    picked = _send(paid, monkeypatch, a, _fields(now))
    assert picked["flags"] == ""
    _unchecked(paid, a, picked)
    assert con.execute("SELECT COUNT(*) FROM receipt_auto_checks").fetchone()[0] == 0
    passed = _send(paid, monkeypatch, b, _fields(now, "223456789012345678"), 241)
    assert passed["reviewed_at"] == now and _attendee(paid, b)["auto"] is True
    assert c.post(f"/api/receipts/{picked['id']}/review", headers=tma(20), json={"reject": False}).status_code == 204
    assert _attendee(paid, a)["reviewed"] is True and _attendee(paid, a)["auto"] is False


def test_audit_draws_one_in_five(monkeypatch):
    monkeypatch.undo()  # the real draw, not conftest's
    picks = [seats._audit() for _ in range(5000)]
    assert 800 < sum(picks) < 1200


def test_organizer_sees_the_apps_count_and_sum(paid, monkeypatch):
    # (a) EventManage's line sums the receipts with auto: true; a person's check or a spot-checked one isn't in it
    c, _, eid, (a, b, d), now = paid
    draws = iter([False, False, True])
    monkeypatch.setattr(seats, "_audit", lambda: next(draws))
    for i, tg in enumerate((a, b, d)):
        _go(c, eid, tg)
        _send(paid, monkeypatch, tg, _fields(now, str(123456789012345678 + i)), 240 + i)
    att = [x["receipt"] for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json() if x["receipt"]]
    auto = [x["amount"] for x in att if x["auto"]]
    assert (len(auto), sum(auto)) == (2, 4000)


@pytest.mark.parametrize("sign", ["-", "+", "−", "–"])
def test_signed_amount_is_never_clean(paid, monkeypatch, sign):
    # (c) a receipt prints its sum bare; a signed one is a history line or money coming back (a refund)
    c, _, eid, (tg, _, _), now = paid
    got = receipt.parse(f"Transfer\n{sign} 2 000 ₸\nArman A.\nNo 123456789012345678\n05.10.2026 14:56")
    assert got["amount"] == 2000 and got["signed"] is True
    assert "signed" not in receipt.parse("Transfer\n2 000 ₸\nArman A.")
    _go(c, eid, tg)
    row = _send(paid, monkeypatch, tg, {**_fields(now), "signed": True})
    assert row["flags"] == ""
    _unchecked(paid, tg, row)
