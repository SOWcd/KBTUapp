"""`kbtu.admin seat`: the creator seats a student on a paid event with no receipt (logic/seats.seat_by_hand)."""
from __future__ import annotations

import time

from kbtu import admin, db
from test_core import env, login, tma  # noqa: F401  (env is a fixture)


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
