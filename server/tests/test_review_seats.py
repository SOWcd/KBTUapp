"""Review of money and tickets (seats.py, receipts): each test fails while its bug is there."""
from __future__ import annotations

import io
import time

from PIL import Image

from kbtu import db, logic, receipt
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)


def _paid(c, cfg, seats=1, start_in=3600, length=None):
    """An official club (tg 20 its president), a published paid event; students tg 10, 11 signed in."""
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    start = logic.core.now() + start_in
    body = {"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": seats,
            "price": 2000, "payToName": "Arman A.", "payPhone": "87071234567", **({"endsAt": start + length} if length else {})}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert c.post(f"/api/events/{ev['id']}/publish", headers=tma(20)).json()["status"] == "published"
    return con, ev["id"]


def _shot(shade=240) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (600, 1200), (shade, shade, shade)).save(b, "PNG")
    return b.getvalue()


def _status(c, eid, uid):
    return c.get(f"/api/events/{eid}", headers=tma(uid)).json()["my"]["status"]


def test_cancelled_event_promotes_waitlist_into_hold(env):
    """A cancelled event: someone leaving must not hand the waitlist a "pay within 30 min" seat (promote() ignores status)."""
    c, cfg = env
    con, eid = _paid(c, cfg)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "hold"
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).json()["status"] == "cancelled"
    c.delete(f"/api/events/{eid}/registration", headers=tma(10))
    assert _status(c, eid, 11) == "waitlist"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind IN ('seat_hold', 'seat_free')").fetchone()


def test_cancelled_event_takes_no_receipt(env):
    """A hold on an event cancelled since: the receipt must not turn it into a ticket (_receipt_slot ignores status)."""
    c, cfg = env
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    c.post(f"/api/events/{eid}/cancel", headers=tma(20))
    r = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).json()
    assert r.get("error") == "closed", r.get("my")


def test_hold_after_event_is_over(env, monkeypatch):
    """An expired hold swept after the event ended: the waitlist must not get a seat to pay for, nor a ticket for it."""
    c, cfg = env
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    con, eid = _paid(c, cfg, start_in=600, length=3600)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})   # hold until t0 + 30 min
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})   # waitlist
    clock[0] = t0 + 600 + 3600 + 60                                         # the event is over; nobody looked meanwhile
    assert _status(c, eid, 11) != "hold"
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=_shot()).json().get("error") == "closed"


def test_hold_expired_while_receipt_was_read(env, monkeypatch):
    """The hold runs out while the receipt is read (OCR waits its turn): add_receipt must refuse it (the app says so and
    drops the file), not give a ticket to the expired hold while the waitlisted person keeps waiting."""
    c, cfg = env
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    take = receipt.take

    def slow(data, root):
        clock[0] = t0 + logic.core.HOLD + 60
        return take(data, root)
    monkeypatch.setattr(receipt, "take", slow)
    r = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).json()
    assert r.get("error") == "closed", r.get("my")


def test_receipt_without_number_is_flagged(env, monkeypatch):
    """OCR read a sum but no receipt number (a cropped or re-saved screenshot): the duplicate check can't run, so the
    organizer must see it ('unreadable' exists in the schema, the bot's texts and the app's strings, but is never set).
    As it is, one receipt shown twice, re-saved, passes clean for a second ticket."""
    c, cfg = env
    con, eid = _paid(c, cfg, seats=5)
    monkeypatch.setattr(receipt, "read", lambda im: {"amount": 2000})
    for uid, shade in ((10, 240), (11, 241)):  # the same receipt, re-saved: other bytes
        c.post(f"/api/events/{eid}/registration", headers=tma(uid), json={})
        mine = c.post(f"/api/events/{eid}/receipt", headers=tma(uid), content=_shot(shade)).json()["my"]
        assert mine["status"] == "going"
    assert mine["receiptFlags"] != [], "a second ticket from the same receipt, with nothing for the organizer to see"


def test_bot_receipt_waits_out_a_locked_database(env, monkeypatch):
    """A receipt sent to the bot while a burst of sign-ups holds the write lock: was, "database is locked" fell to the
    catch-all, the update was consumed with no answer and the hold ran out (paid, no seat). Now the same update comes
    again next round, and the receipt is taken then."""
    import asyncio
    import json
    import sqlite3

    import httpx

    from kbtu import bot
    c, cfg = env
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    monkeypatch.setattr(receipt, "read", lambda im: {"amount": 2000})
    nap = asyncio.sleep
    monkeypatch.setattr(bot.asyncio, "sleep", lambda s: nap(0))
    batch = [{"update_id": 5, "message": {"message_id": 1, "chat": {"id": 10, "type": "private"}, "from": {"id": 10}, "date": int(time.time()),
                                          "document": {"file_id": "R", "mime_type": "image/png", "file_size": 900}}}]
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [u for u in batch if u["update_id"] >= int(request.url.params["offset"])]})
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "R"}})
        if "/file/" in request.url.path:
            return httpx.Response(200, content=_shot())
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def hear(offset):
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot.hear(cfg, http, offset)
    add = logic.add_receipt

    def locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(logic, "add_receipt", locked)
    assert asyncio.run(hear(5)) == 5 and sent == []                  # not consumed: asked again next round
    assert _status(c, eid, 10) == "hold"
    monkeypatch.setattr(logic, "add_receipt", add)
    assert asyncio.run(hear(5)) == 6                                  # the lock is gone: taken, answered once
    assert _status(c, eid, 10) == "going" and [m["chat_id"] for m in sent] == [10]
    assert con.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
