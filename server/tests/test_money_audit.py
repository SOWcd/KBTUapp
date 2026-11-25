"""Regression cases for the six money audit findings; synthetic receipts only."""
import hashlib
import time
from pathlib import Path

import pytest

from kbtu import db, logic, media, receipt
from kbtu.logic import account, organizing, seats
from test_core import env, set_clock, tma  # noqa: F401
from test_review_seats import _paid, _shot, _status


@pytest.mark.parametrize("change", [
    {"recipient": None, "paid_at": None}, {"signed": True}, {"recipient": "Arlan A."}, {"paid_at": "future"},
])
def test_incomplete_payment_blocks_both_doors_until_review(env, monkeypatch, change):
    c, cfg = env
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    con, eid = _paid(c, cfg, start_in=60)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    fields = {"amount": 2000, "no": "123456789012345678", "recipient": "Arman A.", "paid_at": now, **change}
    if fields["paid_at"] == "future":
        fields["paid_at"] = now + 60
    monkeypatch.setattr(receipt, "read", lambda im: fields)
    ticket = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).json()["my"]["ticketCode"]
    row = con.execute("SELECT * FROM receipts").fetchone()
    uid = con.execute("SELECT user_id FROM registrations WHERE id = ?", (row["registration_id"],)).fetchone()[0]
    assert row["flags"] == "partial" and row["reviewed_at"] is None
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": f"KBTU{ticket}"}).json()["result"] == "flagged"
    assert organizing.screen_came(con, eid, uid, now) == {"done": False, "flagged": True}
    assert con.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (row["registration_id"],)).fetchone()[0] is None
    assert c.post(f"/api/receipts/{row['id']}/review", headers=tma(20), json={"reject": False}).status_code == 204
    assert organizing.screen_came(con, eid, uid, now)["done"] is True
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": f"KBTU{ticket}"}).json()["result"] == "already"


@pytest.mark.parametrize("reject", [False, True])
def test_stale_receipt_review_cannot_touch_replacement(env, reject):
    c, cfg = env
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).status_code == 200
    old = con.execute("SELECT id FROM receipts").fetchone()[0]
    assert c.get(f"/api/receipts/{old}/image", headers=tma(20)).status_code == 200
    # Seed existing uploads on upgrade, then ensure both replacement and later deletion preserve the high-water mark.
    con.execute("DELETE FROM meta WHERE key = 'seq:receipts'")
    con.executescript(dict(db.MIGRATIONS)[230])
    assert int(con.execute("SELECT value FROM meta WHERE key = 'seq:receipts'").fetchone()[0]) == old
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot(241)).status_code == 200
    new = con.execute("SELECT * FROM receipts").fetchone()
    assert new["id"] > old
    assert c.post(f"/api/receipts/{old}/review", headers=tma(20), json={"reject": reject}).status_code == 404
    assert dict(con.execute("SELECT * FROM receipts").fetchone()) == dict(new)
    assert _status(c, eid, 10) == "going" and _status(c, eid, 11) == "waitlist"
    con.execute("DELETE FROM receipts")
    with db.tx(con):
        assert logic.core.next_id(con, "receipts") > new["id"]


@pytest.mark.parametrize("audit", [False, True])
@pytest.mark.parametrize("promoted", [False, True])
def test_erased_receipt_cannot_pay_for_a_later_hold(env, monkeypatch, audit, promoted):
    c, cfg = env
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    con, first = _paid(c, cfg, start_in=60, length=60)
    body = {"title": "Later gala", "place": "Hall", "startsAt": clock[0] + 14 * 86400, "seats": 1, "emoji": "laptop_3d", "color": "#3B6BFF",
            "price": 2000, "payToName": "Arman A.", "payPhone": "87071234567"}
    second = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    assert c.post(f"/api/events/{second}/publish", headers=tma(20)).status_code == 200
    clock[0] += 59
    c.post(f"/api/events/{first}/registration", headers=tma(10), json={})
    # Same minute as the hold: Kaspi's rounded-down timestamp must still pass.
    fields = {"amount": 2000, "no": "123456789012345678", "recipient": "Arman A.", "paid_at": clock[0] // 60 * 60}
    monkeypatch.setattr(receipt, "read", lambda im: fields)
    assert c.post(f"/api/events/{first}/receipt", headers=tma(10), content=_shot()).status_code == 200
    assert con.execute("SELECT reviewed_at FROM receipts").fetchone()[0] is not None
    uid = con.execute("SELECT id FROM users WHERE tg_id = 10").fetchone()[0]
    assert organizing.screen_came(con, first, uid, clock[0])["done"] is True
    if promoted:
        assert c.post(f"/api/events/{second}/registration", headers=tma(20), json={}).json()["my"]["status"] == "hold"
        assert c.post(f"/api/events/{second}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    clock[0] += 120
    assert c.post("/api/me/delete", headers=tma(10), json={}).status_code == 200
    clock[0] += account.DELETE_WAIT + 1
    account.delete_due(con)
    assert not con.execute("SELECT 1 FROM receipts").fetchone()
    assert not con.execute("SELECT 1 FROM receipt_replaced").fetchone()
    assert not con.execute("SELECT 1 FROM files WHERE kind = 'receipt'").fetchone()
    if promoted:
        assert c.post(f"/api/events/{second}/seats", headers=tma(20), json={"add": 1}).status_code == 200
    else:
        assert c.post(f"/api/events/{second}/registration", headers=tma(11), json={}).json()["my"]["status"] == "hold"
    monkeypatch.setattr(seats, "_audit", lambda: audit)
    assert c.post(f"/api/events/{second}/receipt", headers=tma(11), content=_shot()).status_code == 200
    row = con.execute("SELECT * FROM receipts").fetchone()
    assert row["flags"] == "partial" and row["reviewed_at"] is None
    assert organizing.flagged(con, row["registration_id"])
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (clock[0], second))
    uid = con.execute("SELECT id FROM users WHERE tg_id = 11").fetchone()[0]
    assert organizing.screen_came(con, second, uid, clock[0]) == {"done": False, "flagged": True}


@pytest.mark.parametrize("failed", [False, True])
def test_delayed_receipt_cleanup_cannot_erase_another_upload(env, monkeypatch, failed):
    c, cfg = env
    con, eid = _paid(c, cfg, seats=2)
    for tg in (10, 11):
        c.post(f"/api/events/{eid}/registration", headers=tma(tg), json={})
    original = _shot()
    if not failed:
        assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=original).status_code == 200
    add, drop, pending = logic.add_receipt, media.drop, []
    if failed:
        def refuse(*args, **kwargs):
            raise logic.ApiError("closed")
        monkeypatch.setattr(logic, "add_receipt", refuse)
    # Defer A's unlink until B's separate request/connection has committed the same original bytes.
    monkeypatch.setattr(media, "drop", lambda root, paths: pending.append((root, list(paths))))
    response = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=original if failed else _shot(241))
    assert response.status_code == (409 if failed else 200)
    assert any(paths for _, paths in pending)
    monkeypatch.setattr(logic, "add_receipt", add)
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=original).status_code == 200
    for root, paths in pending:
        drop(root, paths)
    for rid, path in con.execute("SELECT c.id, f.path FROM receipts c JOIN files f ON f.id = c.file_id"):
        assert (Path(cfg.db_path).parent / "receipts" / f"{path}.webp").is_file()
        assert c.get(f"/api/receipts/{rid}/image", headers=tma(20)).status_code == 200
    kept = con.execute("SELECT sha256 FROM files f JOIN registrations r ON r.user_id = f.owner_id JOIN users u ON u.id = r.user_id WHERE u.tg_id = 11").fetchone()
    assert kept[0] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("cancel_event", [False, True])
def test_cancelled_payment_remains_accessible_for_refund(env, monkeypatch, cancel_event):
    c, cfg = env
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).status_code == 200
    rid = con.execute("SELECT id FROM receipts").fetchone()[0]
    if cancel_event:
        assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).status_code == 200
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).status_code == 200
    attendee = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]
    assert attendee["status"] == "cancelled" and attendee["receipt"]["id"] == rid
    assert c.get(f"/api/events/{eid}", headers=tma(20)).json()["taken"] == 0
    if not cancel_event:
        clock[0] += 1
        assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "hold"
        attendee = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]
        assert attendee["receipt"] is None and [r["id"] for r in attendee["previousReceipts"]] == [rid]
        assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot(241)).status_code == 200
        attendee = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]
        assert attendee["receipt"]["id"] != rid and [r["id"] for r in attendee["previousReceipts"]] == [rid]
        assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).status_code == 200
        attendee = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]
        assert attendee["status"] == "cancelled" and attendee["previousReceipts"][0]["id"] == rid
    assert c.get(f"/api/receipts/{rid}/image", headers=tma(20)).status_code == 200


@pytest.mark.parametrize("during_ocr", [False, True])
def test_short_event_caps_holds_and_refuses_receipts_at_end(env, monkeypatch, during_ocr):
    c, cfg = env
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    con, eid = _paid(c, cfg, start_in=300, length=600)
    end = clock[0] + 900
    first = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]
    assert first["holdUntil"] == end
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    clock[0] += 60
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).status_code == 200
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["holdUntil"] == end
    # An existing hold created before the fix may still advertise the old deadline.
    con.execute("UPDATE registrations SET hold_until = ? WHERE status = 'hold'", (end + 900,))
    take = receipt.take
    def cross_end(data, root):
        clock[0] = end
        return take(data, root)
    if during_ocr:
        monkeypatch.setattr(receipt, "take", cross_end)
        clock[0] = end - 1
    else:
        clock[0] = end
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=_shot()).json()["error"] == "closed"
    assert not con.execute("SELECT 1 FROM receipts").fetchone()
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.webp"))
