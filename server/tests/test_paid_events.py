"""Paid events: Kaspi receipts, deadlines and the free-first seat."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import bot, config, db, logic, receipt, app as server, texts
from test_core import INTAKE, delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def test_paid_events(env):
    """§4.3: an official club's Vice+ sets the price and the Kaspi details; "Going" holds a seat for 30 min; the receipt
    turns it into a ticket at once; the same file twice is flagged and comes first for the organizer (and at the door);
    a rejected receipt ends the ticket and the seat goes on; the image is private; the details lock once someone paid;
    deleting my data deletes my receipts' images."""
    import io
    from pathlib import Path
    from PIL import Image
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'head', 0 FROM users WHERE tg_id = 21")
    start = int(time.time()) + 3600
    body = {"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 1}
    paid = {**body, "price": 2000, "payToName": " Alikhan  S. ", "payPhone": "8 (707) 123-45-67"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=paid).json()["message"] == "price"      # a student initiative
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    assert c.post("/api/orgs/1/events", headers=tma(21), json=paid).json()["message"] == "price"      # a Head sets no prices
    assert c.post("/api/orgs/1/events", headers=tma(21), json={**body, "price": None}).status_code == 200  # free stays anyone's
    for bad in ({"price": 0}, {"price": "2000"}, {"price": True}, {"payToName": "A"}, {"payPhone": "12345"}):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**paid, **bad}).status_code == 400
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=paid).json()
    assert (ev["price"], ev["payToName"], ev["payPhone"]) == (2000, "Alikhan S.", "+77071234567")
    eid = ev["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))

    held = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()
    assert held["my"]["status"] == "hold" and held["my"]["ticketCode"] is None and held["taken"] == 1
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    shot = io.BytesIO()
    Image.new("RGB", (600, 1200), (240, 240, 240)).save(shot, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["error"] == "closed"  # no seat held
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=b"%PDF-1.4").json()["message"] == "not_an_image"
    got = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=shot.getvalue()).json()
    assert got["my"]["status"] == "going" and got["my"]["ticketCode"] and got["my"]["receipt"] == "accepted"
    home = Path(cfg.db_path).parent
    assert list((home / "receipts").rglob("*.webp")) and not (home / "media").exists()                # private, never under /media

    att = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    rid = att[0]["receipt"]["id"]
    assert att[0]["receipt"]["flags"] == ["ocr_unavailable"] and att[1]["receipt"] is None
    img = c.get(f"/api/receipts/{rid}/image", headers=tma(21))
    assert img.headers["content-type"] == "image/webp" and "no-store" in img.headers["cache-control"]
    assert c.get(f"/api/receipts/{rid}/image", headers=tma(10)).status_code == 200                     # the sender
    assert c.get(f"/api/receipts/{rid}/image", headers=tma(11)).status_code == 404                     # nobody else
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**paid, "price": 3000}).json()["message"] == "paid"
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "title": "Gala night"}).status_code == 200  # absent keeps

    assert c.post(f"/api/receipts/{rid}/review", headers=tma(10), json={"reject": True}).status_code == 403
    assert c.post(f"/api/receipts/{rid}/review", headers=tma(21), json={"reject": True}).status_code == 204
    mine = c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]
    assert (mine["status"], mine["cancelReason"], mine["ticketCode"]) == ("cancelled", "receipt_rejected", None)
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "hold"               # the waitlist moves
    assert {"receipt_rejected", "seat_hold"} <= {k for (k,) in con.execute("SELECT kind FROM bot_outbox")}

    ticket = c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["my"]["ticketCode"]
    att = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    assert att[0]["receipt"]["flags"] == ["duplicate", "ocr_unavailable"] and not att[0]["receipt"]["reviewed"]
    assert c.post(f"/api/events/{eid}/door-open", headers=tma(20)).status_code == 200
    held = c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": ticket}).json()      # warned before admission
    assert held["result"] == "flagged" and held["came"] == 0
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": ticket, "admit": True}).json()["flagged"] is True
    c.post(f"/api/receipts/{att[0]['receipt']['id']}/review", headers=tma(20), json={"reject": False})
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]["receipt"]["reviewed"] is True

    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (int(time.time()) - 5 * 3600, eid))  # a paid ticket ahead makes it wait (H2)
    for uid, name in ((11, "bob"), (10, "ali")):  # the same image: it goes when the last receipt using it does
        assert list((home / "receipts").rglob("*.webp"))
        assert delete_now(c, cfg, tma(uid)) is None
    assert not list((home / "receipts").rglob("*.*"))


def test_receipt_reading(env, monkeypatch):
    """§4.3, Oct 11: Kaspi's PDF is taken like a screenshot (in the app and by the bot); what OCR reads off a receipt
    becomes the organizer's flags, never a rejection: a smaller sum, another recipient (Tesseract reads a Latin name
    with Russian shapes), a receipt older than the event, the same receipt number again, nothing readable."""
    import io
    import pypdfium2 as pdfium
    look = lambda name: name.translate(receipt._LOOK)  # noqa: E731  (a Latin name as Tesseract's Russian model reads it)
    arman, aigerim = "\u0410\u0440\u043c\u0430\u043d \u0410.", "\u0410\u0439\u0433\u0435\u0440\u0456\u043c \u0421."  # in Cyrillic
    ru = f"(a)\nTransfer completed\n2 000T\n{look('Arman A.')}\nType Transfer...\nNo 12345678901234\n5678\nDate and time 05.10.2026 14:56\n" \
         "in Astana\nFee 0T\nSender Ivanov I.I.\nFrom Kaspi Gold"   # the fields by shape: labels may be Russian or Kazakh
    assert receipt.parse(ru) == {"amount": 2000, "recipient": look("Arman A."), "no": "123456789012345678",
                                 "paid_at": 1791194160, "sender": "Ivanov I.I."}       # 2026-10-05 14:56 in Astana
    kk = f"Transfer done\n1 500 \u20b8\n{aigerim}\nReceipt No 987654321098765432\nDate 01.10.2026 9:05\nSender Serikova A.\nFrom Kaspi Gold"
    assert receipt.parse(kk) == {"amount": 1500, "recipient": aigerim, "no": "987654321098765432", "paid_at": 1790827500, "sender": "Serikova A."}
    assert receipt.parse("a photo of a cat") == {}
    for printed, typed, same in ((look("Arman A."), "Arman A.", True), (look("Arman A."), arman, True), (arman, "Arman A.", True),
                                 (aigerim, "Aigerim S.", True), (look("Arman A."), "Arman B.", False), (look("Aisha N."), "Arman A.", False)):
        assert receipt.same_person(printed, typed) is same, (printed, typed)
    sukhrab = "\u0421\u0443\u0445\u0440\u0430\u0431"  # typed without the initial (the owner's own event): the first names
    for printed, typed, same in ((sukhrab + " \u041d.", sukhrab, True), (sukhrab + " \u041d.", "Sukhrab", True), (look("Arman A."), "Arman", True),
                                 (look("Aisha N."), "Arman", False)):
        assert receipt.same_person(printed, typed) is same, (printed, typed)

    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    ev = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Gala", "place": "Hall", "startsAt": int(time.time()) + 3600, "emoji": "laptop_3d",
                                                             "color": "#3B6BFF", "seats": 5, "price": 2000, "payToName": "Arman A.", "payPhone": "87071234567"}).json()
    eid = ev["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    made = con.execute("SELECT created_at FROM events WHERE id = ?", (eid,)).fetchone()[0]

    def pdf(w: int) -> bytes:  # a real PDF (a blank page): what Kaspi's "Share" hands over
        d, out = pdfium.PdfDocument.new(), io.BytesIO()
        d.new_page(w, 700)
        d.save(out)
        return out.getvalue()

    seen = []
    def fake(fields):
        def read(im):
            seen.append(im.size)
            return fields
        monkeypatch.setattr(receipt, "read", read)

    fake({"amount": 1500, "no": "123456789012345678", "recipient": look("Aisha N."), "paid_at": made - 86400, "sender": "Ivanov I.I."})
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    pay = lambda uid: (lambda d: (d["payToName"], d["payPhone"]))(c.get(f"/api/events/{eid}", headers=tma(uid)).json())  # noqa: E731
    assert pay(11) == (None, None)                                         # no seat: the treasurer's Kaspi phone stays hidden
    assert pay(10) == pay(20) == ("Arman A.", "+77071234567")              # the one paying and the club see it
    mine = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(500)).json()["my"]
    assert mine["status"] == "going" and mine["receiptFlags"] == ["amount_short", "recipient_mismatch", "too_early"]  # the student sees it too
    assert pay(10) == ("Arman A.", "+77071234567") and pay(11) == (None, None)   # still his after the seat is taken
    assert abs(seen[-1][0] - 500 * 300 / 72) < 2 and abs(seen[-1][1] - 700 * 300 / 72) < 2  # the page, read at ~300 dpi
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}["Testov Ali"]
    assert got["flags"] == ["amount_short", "recipient_mismatch", "too_early"]
    assert (got["amount"], got["sender"], got["no"], got["paidAt"]) == (1500, "Ivanov I.I.", "123456789012345678", made - 86400)
    assert {x["id"]: x["toCheck"] for x in c.get("/api/orgs/1/events", headers=tma(20)).json()}[eid] == 1  # Studio's "receipts to check"

    # the bot: a PDF sent to it goes to bob's only seat on hold; the number came before, the rest is fine
    class Http:
        def __init__(self):
            self.posts = []
        async def get(self, url, params=None, **kw):
            r = type("R", (), {})()
            r.json = lambda: {"ok": True, "result": {"file_path": "documents/r.pdf"}}
            r.content = pdf(501)
            return r
        async def post(self, url, json=None, **kw):
            self.posts.append((url.rsplit("/", 1)[1], json))
    http = Http()
    doc = lambda uid, mid: {"message_id": mid, "chat": {"id": uid, "type": "private"}, "from": {"id": uid}, "date": int(time.time()),  # noqa: E731
                            "document": {"file_id": f"f{mid}", "mime_type": "application/pdf", "file_size": 900}}
    fake({"amount": 2000, "no": "123456789012345678", "recipient": look("Arman A."), "paid_at": made + 60})
    assert texts.bot_message("ru", "receipt_none")[0] in asyncio.run(bot._receipt(cfg, http, con, doc(11, 1)))["text"]  # no seat held yet
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    answer = asyncio.run(bot._receipt(cfg, http, con, doc(11, 2)))
    assert "Gala" in answer["text"] and answer["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(f"startapp=tk_{eid}")
    assert texts.receipt_why("ru", ["duplicate"]) in answer["text"]  # looks wrong: said at once, the ticket stays
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "going"
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert got["Testov Bob"]["flags"] == ["duplicate"]
    assert con.execute("SELECT via FROM receipts ORDER BY id DESC").fetchone()[0] == "bot"

    # two seats on hold: the bot asks which, and the tap finds the file in the message its buttons answer
    ev2 = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, "title": "Quiz", "place": "305", "startsAt": int(time.time()) + 7200, "emoji": "laptop_3d",
                                                              "color": "#3B6BFF", "price": 500, "payToName": "Arman A.", "payPhone": "87071234567"}).json()
    c.post(f"/api/events/{ev2['id']}/publish", headers=tma(20))
    for e in (eid, ev2["id"]):
        c.post(f"/api/events/{e}/registration", headers=tma(12), json={})
    ask = asyncio.run(bot._receipt(cfg, http, con, doc(12, 3)))
    assert ask["reply_parameters"] == {"message_id": 3} and len(ask["reply_markup"]["inline_keyboard"]) == 2
    fake({})                                                                           # read, but nothing there: not a receipt (a selfie)
    tap = {"id": "q", "from": {"id": 12}, "data": f"rc:{ev2['id']}", "message": {"message_id": 4, "chat": {"id": 12}, "reply_to_message": doc(12, 3)}}
    asyncio.run(bot._tapped(cfg, http, con, tap))
    assert texts.bot_message("ru", "receipt_not")[0] in http.posts[1][1]["text"]
    assert c.get(f"/api/events/{ev2['id']}", headers=tma(12)).json()["my"]["status"] == "hold"  # refused, nothing kept
    assert c.post(f"/api/events/{ev2['id']}/receipt", headers=tma(12), content=pdf(505)).json()["message"] == "not_receipt"
    fake({"amount": 500, "no": "777000111222333444", "recipient": look("Arman A."), "paid_at": made + 60})
    http.posts.clear()
    asyncio.run(bot._tapped(cfg, http, con, tap))
    assert [m for m, _ in http.posts] == ["answerCallbackQuery", "editMessageText"] and "Quiz" in http.posts[1][1]["text"]
    assert c.get(f"/api/events/{ev2['id']}", headers=tma(12)).json()["my"]["status"] == "going"
    assert c.get(f"/api/events/{eid}", headers=tma(12)).json()["my"]["status"] == "hold"  # the other one still waits

    # another file replaces a receipt nobody looked at: twice the price pays for two (no flag), 1.5 times doesn't
    rows_of = lambda: con.execute("SELECT COUNT(*) FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.user_id = (SELECT id FROM users WHERE tg_id = 10)").fetchone()[0]  # noqa: E731
    fake({"amount": 4000, "no": "555000111222333444", "recipient": look("Arman A."), "paid_at": made + 60})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(502)).json()["my"]["receiptFlags"] == [] and rows_of() == 1
    fake({"amount": 3000, "no": "555000111222333445", "recipient": look("Arman A."), "paid_at": made + 60})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(503)).json()["my"]["receiptFlags"] == ["amount_over"]
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}["Testov Ali"]
    assert got["flags"] == ["amount_over"] and got["amount"] == 3000 and rows_of() == 1
    assert c.post(f"/api/receipts/{got['id']}/review", headers=tma(20), json={"reject": False}).status_code < 300
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["receiptFlags"] == []           # looked at: settled
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(504)).status_code >= 400  # and no longer replaceable


def test_deadline_and_free_first(env):
    """A registration deadline closes "Going" (NULL: open until the start); a paid event's first N 1st-year students
    come free: going at once, no hold, no receipt; the waitlist hands a freed free seat to the next 1st-year; the
    number can change after receipts are in, the payment details can't."""
    import io
    from PIL import Image
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'head', 0 FROM users WHERE tg_id = 21")
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dB%07d', ?, user_id) WHERE user_id IN (SELECT id FROM users WHERE tg_id IN (10, 11, 13))",
                (INTAKE % 100,))  # ann, bob, dan: this year's intake (the ID says the year, audit M3)
    con.execute("UPDATE students SET ms_oid = 'oid' || user_id, ms_profile = json_object('employeeId', student_id)")
    # migration 58 (M3): a year typed in since the portal closed becomes the ID's; the portal's own stays (a repeater)
    con.execute("UPDATE students SET course = 1, consent_at = 1792350000 WHERE user_id = (SELECT id FROM users WHERE tg_id = 12)")
    con.execute("UPDATE students SET course = 1, consent_at = 1792000000 WHERE user_id = (SELECT id FROM users WHERE tg_id = 13)")
    con.executescript(dict(db.MIGRATIONS)[58])
    assert [r[0] for r in con.execute("SELECT course FROM students s JOIN users u ON u.id = s.user_id WHERE u.tg_id IN (12, 13) ORDER BY u.tg_id")] \
        == [logic.course_of("24B0000001"), 1] != [1, 1]
    con.execute("UPDATE students SET course = 2 WHERE user_id = (SELECT id FROM users WHERE tg_id = 12)")
    start = int(time.time()) + 7200
    body = {"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 3,
            "price": 2000, "payToName": "Alikhan S.", "payPhone": "87071234567", "freeFirst": 1, "regUntil": start - 600}
    for bad in ({"regUntil": start + 1}, {"regUntil": "soon"}, {"freeFirst": "5"}, {"freeFirst": True}, {"freeFirst": 5001}):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**body, **bad}).status_code == 400
    assert c.post("/api/orgs/1/events", headers=tma(21), json=body).json()["message"] == "price"           # Vice+ only
    free = c.post("/api/orgs/1/events", headers=tma(21), json={**body, "price": None, "freeFirst": 5}).json()
    assert free["freeFirst"] is None and free["regUntil"] == start - 600                                   # no price, no quota
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    eid = ev["id"]
    assert (ev["freeFirst"], ev["freeLeft"], ev["regUntil"]) == (1, 1, start - 600)
    c.post(f"/api/events/{eid}/publish", headers=tma(20))

    ann = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()                      # 1st year: free
    assert (ann["my"]["status"], ann["my"]["free"], bool(ann["my"]["ticketCode"]), ann["freeLeft"]) == ("going", True, True, 0)
    bob = c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()                      # 1st year, none left
    assert (bob["my"]["status"], bob["my"]["free"]) == ("hold", False)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(12), json={}).json()["my"]["status"] == "hold"  # 2nd year pays
    assert c.post(f"/api/events/{eid}/registration", headers=tma(13), json={}).json()["my"]["status"] == "waitlist"
    att = {a["fullName"]: a for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert att["Testov Ann"]["free"] and not att["Testov Bob"]["free"]

    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).status_code == 200                 # ann gives it back
    dan = c.get(f"/api/events/{eid}", headers=tma(13)).json()
    assert (dan["my"]["status"], dan["my"]["free"], dan["freeLeft"]) == ("going", True, 0)                 # the next 1st-year
    assert any(k == "seat_free" and r.startswith(f"event:{eid}:") for k, r in con.execute("SELECT kind, ref FROM bot_outbox"))  # one per promotion

    shot = io.BytesIO()
    Image.new("RGB", (600, 1200), (240, 240, 240)).save(shot, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["my"]["status"] == "going"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "freeFirst": 2}).json()["freeLeft"] == 1  # still changes
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "freeFirst": 2, "price": 2500}).json()["message"] == "paid"
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "freeFirst": 2, "title": "Gala night"}).status_code == 200

    login(c, 15, "fay")                                                                                    # a 1st-year master pays
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dM%07d', ?, user_id) WHERE user_id = (SELECT id FROM users WHERE tg_id = 15)",
                (INTAKE % 100,))
    con.execute("UPDATE events SET seats = 10 WHERE id = ?", (eid,))
    fay = c.post(f"/api/events/{eid}/registration", headers=tma(15), json={}).json()
    assert (fay["my"]["status"], fay["my"]["free"], fay["freeLeft"]) == ("hold", False, 1)

    con.execute("UPDATE events SET reg_until = ? WHERE id = ?", (int(time.time()) - 1, eid))
    late = c.post(f"/api/events/{eid}/registration", headers=tma(14), json={}).json()
    assert (late["error"], late["message"]) == ("closed", "deadline")


def test_free_first_needs_a_new_ms_account(env):
    """A typed number alone never earns a free seat. A configured intake date can corroborate the course."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "old"), (11, "new"), (12, "unk"), (13, "nodate")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dB%07d', ?, user_id) WHERE user_id IN (SELECT id FROM users WHERE tg_id IN (10, 11, 12, 13))",
                (INTAKE % 100,))
    for tg, prof in ((10, {"id": "x", "createdDateTime": f"{INTAKE}-05-31T23:59:59Z"}),   # a day before the intake's summer
                     (11, {"id": "x", "createdDateTime": f"{INTAKE}-06-01T00:00:00Z"}),   # the cutoff itself
                     (12, None), (13, {"id": "x"})):                                       # never signed in / no date
        con.execute("UPDATE students SET manual = 0, ms_oid = ?, ms_profile = ? WHERE user_id = (SELECT id FROM users WHERE tg_id = ?)",
                    (f"oid{tg}", prof and json.dumps(prof), tg))
    me = lambda: [c.get("/api/me", headers=tma(t)).json()["student"]["freeFirst"] for t in (10, 11, 12, 13)]  # noqa: E731
    assert me() == [False] * 4  # no configured intake date or corroborated directory ID
    with pytest.raises(SystemExit):
        config._month_day("6-1")
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}), ms_age_cutoff=config._month_day("06-01"))))
    st = c.get("/api/admin/stats", headers=tma(20)).json()
    assert (st["msCutoff"], st["msMonths"][f"{INTAKE}-05"], st["msMonths"][f"{INTAKE}-06"], st["msMonths"][""] >= 2) == ("06-01", 1, 1, True)
    assert me() == [False, True, False, False]
    start = int(time.time()) + 7200
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d",
                 "color": "#3B6BFF", "seats": 10, "price": 2000, "payToName": "Alikhan S.", "payPhone": "87071234567", "freeFirst": 5}).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    got = [c.post(f"/api/events/{eid}/registration", headers=tma(t), json={}).json()["my"] for t in (10, 11, 12, 13)]
    assert [(m["status"], m["free"]) for m in got] == [("hold", False), ("going", True), ("hold", False), ("hold", False)]
    logic.core.MS_AGE_CUTOFF = None  # a module global (app.py sets it): not into the next test
