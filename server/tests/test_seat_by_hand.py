"""`kbtu.admin seat`: the creator seats a student on a paid event with no receipt (logic/seats.seat_by_hand)."""
from __future__ import annotations

import time

from kbtu import admin, db, receipt
from kbtu.logic import seats
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)
from test_review_seats import _paid, _shot


def test_seat_by_hand(env, capsys, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Cup", "place": "Hall", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d",
                                                               "color": "#3B6BFF", "seats": 1, "price": 2000, "payToName": "Ali S.", "payPhone": "87071234567"}).json()["id"]
    admin.main(["seat", "10", str(eid)])
    assert "no such published event" in capsys.readouterr().out  # a draft seats nobody
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "hold"
    admin.main(["seat", "10", str(eid)])
    assert "seated (was: hold)" in capsys.readouterr().out
    my = c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]
    assert my["status"] == "going" and my.get("ticketCode")  # a ticket, no receipt
    assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'seat_by_hand' AND actor_id IS NULL").fetchone()[0] == 1
    admin.main(["seat", "10", str(eid)])
    assert "already going" in capsys.readouterr().out
    admin.main(["seat", "11", str(eid)])  # no seat of their own, and the event is full: seated past the cap
    assert "seated (was: no seat)" in capsys.readouterr().out
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "going"


def test_old_receipt_rejection_keeps_hand_given_seat(env, capsys, monkeypatch):
    c, cfg = env
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    monkeypatch.setattr(seats, "_audit", lambda: True)
    monkeypatch.setattr(receipt, "read", lambda im: {"amount": 2000, "recipient": "Arman A.", "no": "123456789012345678", "paid_at": clock[0]})
    con, eid = _paid(c, cfg, start_in=86400)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "hold"
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).json()["my"]["status"] == "going"
    old = con.execute("SELECT id, flags, reviewed_at FROM receipts").fetchone()
    assert old["flags"] == "spot" and old["reviewed_at"] is None
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).json()["my"]["status"] == "cancelled"
    clock[0] += 1
    admin.main(["seat", "10", str(eid)])
    assert "seated (was: cancelled)" in capsys.readouterr().out
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]["receipt"] is None
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    assert c.post(f"/api/receipts/{old['id']}/review", headers=tma(20), json={"reject": True, "why": "used"}).status_code == 204
    assert con.execute("SELECT status FROM receipts WHERE id = ?", (old["id"],)).fetchone()[0] == "rejected"
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["status"] == "going"
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "waitlist"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'receipt_rejected'").fetchone()
