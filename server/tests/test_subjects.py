"""The subjects' cards (logic/subjects.py): the tool folds a scrape into one card per name; no file, no feature; listing
myself takes a Microsoft-confirmed student on the policy in force; others see who listed themselves (never the held, the
blocked, the expired); leaving is at once; the term's end is a date set when listed; contact is the find-people offer
(the bot's own card for a subject); a held note waits in Admin's queue with the forum off; deleting an account takes it."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from kbtu import ai, app as server, bot_dm, db, logic, outbox, texts
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import subjects as tool  # noqa: E402

CALC = "\u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435 2"  # "Calculus 2"


SCHOOL = "\u0428\u0418\u0422\u0438\u0418"  # a school, as the portal writes it


def row(code: str, ru: str, en: str, credits: str = "3") -> dict:
    return {"cells": [code, ru, ru + " kk", en, SCHOOL, credits, "2/0/1", "2026-2027", "x"], "items": [{"t": "Teacher T. 305 (12/30)"}]}


def scrape() -> dict:
    return {"done": {
        "MAT1246|y|t": row("MAT1246", CALC, "Calculus 2"),
        "MATH2206|y|t": row("MATH2206.", "\u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435 II", "Calculus II"),  # Roman: the same
        "PET1270|y|t": row("\u0420\u0415\u04221270", "\u0413\u0430\u0437", "Gas", "4"),  # Cyrillic look-alikes in the code
    }}


def test_tool_one_card_per_subject():
    out = tool.cards(scrape())
    gas, calc = out
    assert calc["names"] == {"ru": CALC, "kk": CALC + " kk", "en": "Calculus 2"} and calc["codes"] == ["MAT1246", "MATH2206"]
    assert "Calculus II" in calc["alt"] and (calc["credits"], calc["school"]) == (3, SCHOOL)
    assert gas["codes"] == ["PET1270"] and gas["credits"] == 4
    assert "Teacher" not in json.dumps(out) and "305" not in json.dumps(out)              # no teachers, rooms or counts
    assert calc["id"] == tool.cards({"done": {"z": row("Z9", CALC + " ", "x")}})[0]["id"]  # stable across scrapes


@pytest.fixture
def subj(env, tmp_path, monkeypatch):  # noqa: F811
    _, cfg = env
    path = tmp_path / "subjects.json"
    path.write_text(json.dumps({"updated": "x", "subjects": tool.cards(scrape())}, ensure_ascii=False))
    c = TestClient(server.create(dataclasses.replace(cfg, subjects_file=str(path))))
    con = db.connect(cfg.db_path)
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=True))
    people = {}
    for uid, n in ((1, "ann"), (2, "bob"), (3, "cat")):
        people[n] = login(c, uid, n)["id"]
    con.execute("UPDATE students SET consent_version = ?", (logic.CONSENT,))
    sid = tool.cards(scrape())[1]["id"]
    yield c, con, people, sid, path
    con.close()


def test_off_without_the_file(env):  # noqa: F811
    c, cfg = env
    login(c, 1, "ann")
    assert c.get("/api/subjects", headers=tma(1)).status_code == 404
    assert "subjects" not in c.get("/api/me", headers=tma(1)).json()
    assert c.put("/api/subjects/abc/me", headers=tma(1), json={}).status_code in (403, 404)


def test_listing_seen_left_and_counted(subj):
    c, con, p, sid, _ = subj
    assert c.get("/api/me", headers=tma(1)).json()["subjects"] is True
    assert c.get("/api/subjects", headers=tma(9, "Guest")).status_code == 401          # a guest: no list
    mine = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "  evenings   in the library "}).json()
    assert mine["mine"]["note"] == "evenings in the library" and mine["mine"]["status"] == "live" and mine["people"] == []
    card = c.get(f"/api/subjects/{sid}", headers=tma(2)).json()
    assert [(x["person"]["id"], x["note"], x["course"], x["school"]) for x in card["people"]] == [(p["ann"], "evenings in the library", 2, "SITE")]
    assert "telegram" not in json.dumps(card) and card["mine"] is None
    assert c.get("/api/subjects", headers=tma(2)).json()["counts"] == {sid: 1}
    assert c.get("/api/subjects", headers=tma(1)).json()["counts"] == {} and c.get("/api/subjects", headers=tma(1)).json()["mine"] == [sid]
    # a forum's list never shows it (FORUM's own)
    assert all(a.get("subject") is None for a in logic.asks(con, logic.Viewer(p["bob"], "user", True)))
    # blocked: out of each other's sight
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (p["cat"], p["ann"]))
    assert c.get(f"/api/subjects/{sid}", headers=tma(3)).json()["people"] == []
    # links and handles: refused; too long: refused
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(2), json={"note": "write me @bob"}).json()["message"] == "link"
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(2), json={"note": "x" * 141}).status_code == 400
    # leaving: gone at once
    assert c.delete(f"/api/subjects/{sid}/me", headers=tma(1)).status_code == 204
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"] == []
    assert c.get("/api/subjects/nope", headers=tma(2)).status_code == 404


def test_gate_policy_and_confirmed(subj):
    c, con, p, sid, _ = subj
    con.execute("UPDATE students SET consent_version = '1' WHERE user_id = ?", (p["ann"],))
    r = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    assert r.status_code == 403 and r.json()["message"] == "consent"                 # the in-place gate, never on opening
    for url in ("/api/subjects", f"/api/subjects/{sid}"):                               # nor reading who is listed
        assert c.get(url, headers=tma(1)).json()["message"] == "consent"
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (p["bob"],))
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(2), json={}).json()["error"] == "need_student"


def test_held_note_waits_for_admin_with_forum_off(subj, monkeypatch):
    c, con, p, sid, _ = subj
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=None))  # no AI answer
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "together"}).json()["mine"]["status"] == "held"
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"] == []        # not seen while held
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(2), json={}).json()["mine"]["status"] == "live"  # no note: no AI, live
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    q = c.get("/api/forum/mod", headers=tma(3)).json()
    assert [a["title"] for a in q["held"]] == [CALC] and q["skills"] is None
    assert c.get("/api/forum/mod", headers=tma(2)).status_code == 404                  # a student: as with the forum off
    aid = q["held"][0]["id"]
    assert c.post(f"/api/forum/asks/{aid}/release", headers=tma(3)).status_code == 200
    assert [x["person"]["id"] for x in c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"]] == [p["ann"]]
    assert c.post(f"/api/forum/asks/{aid}/hide", headers=tma(3)).status_code == 204
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'ask_hidden'").fetchone()
    assert outbox._render(con, dict(m) | {"lang": "en"})[2] == f"sj_{sid}"                                    # the author's link: the card


def test_term_end_and_expiry(subj, monkeypatch):
    c, con, p, sid, _ = subj
    at = lambda *d: int(datetime(*d, tzinfo=logic.subjects.ALMATY).timestamp())  # noqa: E731
    assert logic.subjects.term_end(at(2026, 11, 16)) == at(2027, 1, 9)
    assert logic.subjects.term_end(at(2027, 1, 20)) == at(2027, 6, 5)
    assert logic.subjects.term_end(at(2027, 6, 10)) == at(2027, 7, 23)
    assert logic.subjects.term_end(at(2027, 8, 1)) == at(2028, 1, 9)
    mine = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["mine"]
    assert mine["until"] == logic.subjects.term_end(logic.now())
    set_clock(monkeypatch, lambda: mine["until"] + 1)                                   # the term is over: read, not swept
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"] == []
    assert c.get("/api/subjects", headers=tma(2)).json()["counts"] == {}


def test_contact_is_the_find_people_offer(subj):
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET tg_username = 'bob_tg' WHERE id = ?", (p["bob"],))
    aid = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["mine"] and \
        con.execute("SELECT id FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()[0]
    sent = c.post("/api/subjects/offer", headers=tma(2), json={"ask": aid}).json()
    person = c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"][0]
    assert sent == {"id": person["offerId"], "status": "pending"} and person["offered"] == "pending"
    m = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()) | {"lang": "ru"}
    assert m["user_id"] == p["ann"] and CALC in outbox._render(con, m)[0] and "bob_tg" not in outbox._render(con, m)[0]
    cid, tok = con.execute("SELECT id, token FROM contacts").fetchone()
    assert logic.decide_contact(con, p["ann"], cid, True, tok) == "accepted"
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"][0]["telegram"] == logic.telegram_of(con, p["ann"])
    # a forum request (not a subject's) isn't reachable here
    other = logic.create_ask(con, logic.Viewer(p["cat"], "user", True), {"kind": "help", "title": "Charger?"}, True)
    assert c.post("/api/subjects/offer", headers=tma(2), json={"ask": other["id"]}).status_code == 404


def test_account_deletion_takes_listings(subj, env):  # noqa: F811
    c, con, p, sid, _ = subj
    _, cfg = env
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "mornings"})
    c.post("/api/subjects/offer", headers=tma(2), json={"ask": con.execute("SELECT id FROM asks").fetchone()[0]})
    delete_now(c, cfg, tma(1))
    assert not con.execute("SELECT 1 FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()
    assert not con.execute("SELECT 1 FROM contacts").fetchone()


def _ann_offer(c, con, sid: str, by: int) -> tuple[int, str]:
    """Ann lists herself; `by` (a tma id) offers: the offer's id and token."""
    aid = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json() and con.execute("SELECT id FROM asks WHERE user_id = 1").fetchone()[0]
    assert c.post("/api/subjects/offer", headers=tma(by), json={"ask": aid}).status_code == 200
    return tuple(con.execute("SELECT id, token FROM contacts ORDER BY id DESC").fetchone())


def test_only_the_sender_can_withdraw_a_pending_subject_offer(subj):
    c, con, p, sid, _ = subj
    cid, tok = _ann_offer(c, con, sid, 2)
    url = f"/api/subjects/offer/{cid}"
    ann = logic.Viewer(p["ann"], "user", True)
    assert [o["id"] for o in logic.contacts(con, ann)] == [cid]
    for who in (1, 3):
        assert c.delete(url, headers=tma(who)).status_code == 404
    m = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()) | {"lang": "en"}
    assert c.delete(url, headers=tma(2)).status_code == 204
    assert outbox._render(con, m) is None and logic.contacts(con, ann) == []
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"][0]["offered"] is None
    assert logic.decide_contact(con, p["ann"], cid, True, tok) is None
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'contact_ok'").fetchone()

    accepted, token = _ann_offer(c, con, sid, 2)
    assert accepted != cid and c.delete(url, headers=tma(2)).status_code == 404
    assert logic.decide_contact(con, p["ann"], accepted, True, token) == "accepted"
    assert c.delete(f"/api/subjects/offer/{accepted}", headers=tma(2)).status_code == 404
    assert [o["status"] for o in logic.contacts(con, ann)] == ["accepted"]
    declined, token = _ann_offer(c, con, sid, 3)
    assert logic.decide_contact(con, p["ann"], declined, False, token) == "declined"
    assert c.delete(f"/api/subjects/offer/{declined}", headers=tma(3)).status_code == 404

    ask = logic.create_ask(con, ann, {"kind": "help", "title": "Charger?"}, True)
    logic.contact(con, logic.Viewer(p["bob"], "user", True), aid=ask["id"])
    ordinary = con.execute("SELECT id FROM contacts WHERE ask_id = ?", (ask["id"],)).fetchone()[0]
    assert c.delete(f"/api/subjects/offer/{ordinary}", headers=tma(2)).status_code == 404


@pytest.mark.parametrize("sent_first", [True, False])
def test_withdrawal_edits_the_bot_card_even_if_delivery_is_in_flight(subj, sent_first):
    c, con, p, sid, _ = subj
    cid, tok = _ann_offer(c, con, sid, 2)
    con.execute("UPDATE users SET can_dm = 1 WHERE id = ?", (p["ann"],))
    m, = [m for m in outbox._due(con) if m["kind"] == "contact_ask"]
    assert outbox._take(con, m, False)
    if sent_first:
        outbox._answered(con, m, 200, {"ok": True, "result": {"message_id": 42}})
    assert c.delete(f"/api/subjects/offer/{cid}", headers=tma(2)).status_code == 204
    if not sent_first:
        outbox._answered(con, m, 200, {"ok": True, "result": {"message_id": 42}})
    calls = []

    class Http:
        async def post(self, url, *, json):
            calls.append((url.rsplit("/", 1)[-1], json))
            return httpx.Response(400, json={"ok": False, "description": "message can't be edited"})

    cfg = c.app.state.cfg
    asyncio.run(outbox._withdrawn_offers(cfg, Http(), con))
    how, body = calls.pop()
    assert how == "editMessageText" and (body["chat_id"], body["message_id"]) == (1, 42)
    assert body["reply_markup"] == {"inline_keyboard": []}
    assert con.execute("SELECT offer_message FROM contacts WHERE id = ?", (cid,)).fetchone()[0] is None
    # If Telegram left the card in place, its original buttons only explain what happened.
    asyncio.run(bot_dm._tapped(cfg, Http(), con, {"id": "tap", "from": {"id": 1}, "data": f"ct:{cid}:{tok}:y",
                                              "message": {"message_id": 42, "chat": {"id": 1}}}))
    assert calls == [("answerCallbackQuery", {"callback_query_id": "tap", "text": texts.bot_message(m["lang"], "contact_withdrawn")[0]})]


def test_withdrawing_does_not_refund_the_daily_offer_limit(subj, monkeypatch):
    c, con, _, sid, _ = subj
    monkeypatch.setattr(logic.forum, "CONTACTS_A_DAY", 1)
    cid, _ = _ann_offer(c, con, sid, 2)
    assert c.delete(f"/api/subjects/offer/{cid}", headers=tma(2)).status_code == 204
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    assert c.post("/api/subjects/offer", headers=tma(2), json={"ask": aid}).status_code == 429


def test_old_accept_never_answers_a_reused_offer(subj):
    """Review P1: Bob offers, Ann leaves (the offer goes with her row) and lists again, Doug offers. Doug's offer never
    gets Bob's freed id, and Ann's old Accept naming Bob does nothing; the old message renders nothing."""
    c, con, p, sid, _ = subj
    login(c, 4, "doug")
    con.execute("UPDATE students SET consent_version = ?", (logic.CONSENT,))
    bob_id, bob_tok = _ann_offer(c, con, sid, 2)
    old = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()) | {"lang": "en"}
    assert c.delete(f"/api/subjects/{sid}/me", headers=tma(1)).status_code == 204
    doug_id, doug_tok = _ann_offer(c, con, sid, 4)
    assert doug_id != bob_id and doug_tok != bob_tok                                     # never Bob's old id (core.next_id)
    assert outbox._render(con, old) is None                                                  # Bob's card: gone, not Doug's
    assert logic.decide_contact(con, p["ann"], bob_id, True, bob_tok) is None            # Bob's Accept: nothing
    assert logic.decide_contact(con, p["ann"], bob_id, True) is None                     # nor a button without a token
    bot_tap = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'contact_ask' ORDER BY id DESC").fetchone()) | {"lang": "en"}
    assert outbox._render(con, bot_tap | {"user_id": p["bob"]}) is None                    # Doug's card renders for Ann alone
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "pending"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'contact_ok'").fetchone()
    assert logic.decide_contact(con, p["ann"], doug_id, True, doug_tok) == "accepted"    # Doug's own card works


def test_old_accept_on_the_forum_path_too(subj):
    """The same hole on the find-people forum's requests: a request deleted (forum_sweep, an account) frees its offers' ids."""
    c, con, p, sid, _ = subj
    ann, cat = logic.Viewer(p["ann"], "user", True), logic.Viewer(p["cat"], "user", True)
    a1 = logic.create_ask(con, ann, {"kind": "help", "title": "Charger?"}, True)
    logic.contact(con, logic.Viewer(p["bob"], "user", True), aid=a1["id"])
    cid, tok = con.execute("SELECT id, token FROM contacts").fetchone()
    con.execute("DELETE FROM asks WHERE id = ?", (a1["id"],))
    a2 = logic.create_ask(con, ann, {"kind": "help", "title": "Umbrella?"}, True)
    logic.contact(con, cat, aid=a2["id"])
    assert con.execute("SELECT id FROM contacts").fetchone()[0] != cid                    # a new id, never the freed one
    assert logic.decide_contact(con, p["ann"], cid, True, tok) is None


def test_moderators_without_forum_see_subjects_only(subj, monkeypatch):
    """Review P2: with FORUM off, the subjects' moderation never reads, lets out or hides the forum's own requests."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    ordinary = logic.create_ask(con, logic.Viewer(p["bob"], "user", True), {"kind": "help", "title": "Charger?"}, None)
    live = logic.create_ask(con, logic.Viewer(p["bob"], "user", True), {"kind": "help", "title": "Umbrella?"}, True)
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=None))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "together"})
    assert [a["title"] for a in c.get("/api/forum/mod", headers=tma(3)).json()["held"]] == [CALC]
    assert c.post(f"/api/forum/asks/{ordinary['id']}/release", headers=tma(3)).status_code == 404
    assert c.post(f"/api/forum/asks/{live['id']}/hide", headers=tma(3)).status_code == 404
    assert [r[0] for r in con.execute("SELECT status FROM asks WHERE subject IS NULL ORDER BY id")] == ["held", "live"]


def test_take_down_is_its_own_record(subj):
    """Review 2, P2: leaving is always real (gone from mine, no slot, its offers with it); a moderator's take-down is a
    record of its own: listing again on that subject is refused while it stands, Admin lists it and lifts it (an
    accidental hide undone, the listing back if its author kept it), the lift can be put back, and it ends with the term."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "together"})
    aid = con.execute("SELECT id FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()[0]
    assert c.post(f"/api/forum/asks/{aid}/hide", headers=tma(3)).status_code == 204
    r = c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "together"})
    assert r.status_code == 409 and r.json()["message"] == "restricted"                  # the same note again: refused
    assert c.delete(f"/api/subjects/{sid}/me", headers=tma(1)).status_code == 204
    card = c.get(f"/api/subjects/{sid}", headers=tma(1)).json()
    assert card["mine"] is None and card["restricted"] and not con.execute("SELECT 1 FROM asks").fetchone()  # gone for real
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["message"] == "restricted"  # leaving and again: refused
    hold = c.get("/api/forum/mod", headers=tma(3)).json()["holds"]
    assert [h["title"] for h in hold] == [CALC]
    assert c.post(f"/api/forum/holds/{hold[0]['id']}", headers=tma(2)).status_code == 404  # a student: no
    assert c.post(f"/api/forum/holds/{hold[0]['id']}", headers=tma(3)).status_code == 204  # lifted: the record goes
    assert not con.execute("SELECT 1 FROM subject_holds").fetchone()
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["mine"]["status"] == "live"
    assert [x["person"]["id"] for x in c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"]] == [p["ann"]]
    done = [d for d in c.get("/api/admin/inbox", headers=tma(3)).json()["done"] if d["action"] == "subject_lift"]
    assert done[0]["undo"] and done[0]["text"] == CALC
    assert c.post(f"/api/admin/done/{done[0]['id']}/undo", headers=tma(3)).status_code == 204  # Done's Undo: the hold again
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"] == []            # out of sight in the read itself
    assert c.get(f"/api/subjects/{sid}", headers=tma(1)).json()["mine"]["status"] == "hidden"
    end = con.execute("SELECT until FROM subject_holds").fetchone()[0]
    assert end == con.execute("SELECT expires_at FROM asks").fetchone()[0]                 # the listing's own end


def test_hide_lift_hide_keeps_one_hold(subj):
    """Review 3: hide, lift, hide again: one take-down at a time, and the listing out of sight while it stands."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    assert c.post(f"/api/forum/asks/{aid}/hide", headers=tma(3)).status_code == 204
    h1 = c.get("/api/forum/mod", headers=tma(3)).json()["holds"][0]["id"]
    assert c.post(f"/api/forum/holds/{h1}", headers=tma(3)).status_code == 204
    assert c.post(f"/api/forum/asks/{aid}/hide", headers=tma(3)).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM subject_holds").fetchone()[0] == 1
    lift_line = con.execute("SELECT id FROM audit_log WHERE action = 'subject_lift'").fetchone()[0]
    assert c.post(f"/api/admin/done/{lift_line}/undo", headers=tma(3)).status_code in (404, 409)  # decided again since: no
    assert c.post(f"/api/forum/holds/{h1}", headers=tma(3)).status_code == 404                     # the old one is gone
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"] == []


def test_expired_listing_report_makes_no_hold(subj, monkeypatch):
    """Review 3: a listing over on Jan 9, its report decided on Jan 10: the report closes, no take-down for spring."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    at = lambda *d: int(datetime(*d, tzinfo=logic.subjects.ALMATY).timestamp())  # noqa: E731
    set_clock(monkeypatch, lambda: at(2026, 12, 1))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    assert c.post("/api/reports", headers=tma(2), json={"target": "ask", "id": aid, "reason": "spam"}).status_code == 204
    set_clock(monkeypatch, lambda: at(2027, 1, 10))
    logic.resolve_report(con, logic.Viewer(p["cat"], "moderator", True), "ask", aid, True)
    assert con.execute("SELECT status FROM reports").fetchone()[0] == "actioned"
    assert not con.execute("SELECT 1 FROM subject_holds").fetchone()
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["mine"]["status"] == "live"


def test_ids_never_come_back(subj):
    """Review 3, the root: the newest request or offer deleted, the next one gets a new id (core.next_id)."""
    c, con, p, sid, _ = subj
    ann, bob = logic.Viewer(p["ann"], "user", True), logic.Viewer(p["bob"], "user", True)
    a1 = logic.create_ask(con, ann, {"kind": "help", "title": "Charger?"}, True)
    logic.contact(con, bob, aid=a1["id"])
    c1 = con.execute("SELECT id FROM contacts").fetchone()[0]
    con.execute("DELETE FROM asks WHERE id = ?", (a1["id"],))                              # its offer goes with it
    a2 = logic.create_ask(con, ann, {"kind": "help", "title": "Umbrella?"}, True)
    logic.contact(con, bob, aid=a2["id"])
    assert a2["id"] > a1["id"] and con.execute("SELECT id FROM contacts").fetchone()[0] > c1
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    s1 = con.execute("SELECT id FROM asks WHERE subject IS NOT NULL").fetchone()[0]
    c.delete(f"/api/subjects/{sid}/me", headers=tma(1))
    c.put(f"/api/subjects/{sid}/me", headers=tma(2), json={})
    assert con.execute("SELECT id FROM asks WHERE subject IS NOT NULL").fetchone()[0] > s1


def test_telegram_only_from_the_listings_own_author(subj):
    """Review 3, P1: an accepted offer shows a Telegram only where it was made to that listing's author."""
    c, con, p, sid, _ = subj
    login(c, 4, "doug")
    con.execute("UPDATE students SET consent_version = ?", (logic.CONSENT,))
    cid, tok = _ann_offer(c, con, sid, 2)
    con.execute("UPDATE asks SET user_id = ? WHERE user_id = ?", (4, p["ann"]))           # the row now Doug's, by any path
    assert logic.decide_contact(con, p["ann"], cid, True, tok) == "accepted"
    assert "telegram" not in json.dumps(c.get(f"/api/subjects/{sid}", headers=tma(2)).json())


def test_late_ai_verdict_only_on_its_own_row(subj, monkeypatch):
    """Review 3: the AI's word on reports, come late, hides only the row it read (same author, same making)."""
    c, con, p, sid, _ = subj
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    aid = con.execute("SELECT id, created_at FROM asks").fetchone()
    logic.hide_ask(con, aid[0], "reports", made=(p["bob"], aid[1]))                          # read on someone else's
    assert con.execute("SELECT status FROM asks").fetchone()[0] == "live"
    logic.hide_ask(con, aid[0], "reports", made=(p["ann"], aid[1]))
    assert con.execute("SELECT status FROM asks").fetchone()[0] == "hidden"


def test_cap_holds_under_two_at_once(subj, monkeypatch):
    """Review 2, P2: two lists at once at the cap minus one: both pass reserve() (the AI is slow), one listing ends up."""
    c, con, p, sid, path = subj
    monkeypatch.setattr(logic.subjects, "LISTED_MAX", 1)
    ann = logic.Viewer(p["ann"], "user", True)
    gas, calc = tool.cards(scrape())
    a, b = (logic.subjects.reserve(con, ann, str(path), x["id"]) for x in (gas, calc))
    logic.subjects.join(con, ann, str(path), a, "", True)
    with pytest.raises(logic.ApiError):
        logic.subjects.join(con, ann, str(path), b, "", True)
    assert con.execute("SELECT COUNT(*) FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()[0] == 1


def test_report_then_remove_from_admin(subj):
    """Review 2, P2: a reported listing removed from Admin's reports: hidden, its report closed, one decision."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "together"})
    aid = con.execute("SELECT id FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()[0]
    assert c.post("/api/reports", headers=tma(2), json={"target": "ask", "id": aid, "reason": "spam"}).status_code == 204
    assert [r["id"] for r in c.get("/api/admin/reports", headers=tma(3)).json() if r["target"] == "ask"] == [aid]
    assert c.post(f"/api/admin/reports/ask/{aid}", headers=tma(3), json={"remove": True}).status_code == 204
    assert con.execute("SELECT status FROM asks WHERE id = ?", (aid,)).fetchone()[0] == "hidden"
    assert con.execute("SELECT status FROM reports").fetchone()[0] == "actioned"
    assert con.execute("SELECT COUNT(*) FROM subject_holds").fetchone()[0] == 1


def test_reports_scope_without_forum(subj):
    """Review 2, P2: with FORUM off, the forum's own requests never surface through reports: not reported, not in the
    queue, not decided, not in Admin's count or Done."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id IN (?, ?)", (p["cat"], p["bob"]))
    other = logic.create_ask(con, logic.Viewer(p["ann"], "user", True), {"kind": "help", "title": "Secret words"}, True)
    assert c.post("/api/reports", headers=tma(3), json={"target": "ask", "id": other["id"], "reason": "spam"}).status_code == 404
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'ask', ?, 'spam', 0)", (p["bob"], other["id"]))
    assert "Secret" not in json.dumps(c.get("/api/admin/reports", headers=tma(3)).json())
    assert c.get("/api/me", headers=tma(3)).json()["counters"]["inbox"] == 0
    assert c.post(f"/api/admin/reports/ask/{other['id']}", headers=tma(3), json={"remove": True}).status_code == 404
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'report_remove', ?, '{}', ?)", (p["bob"], f"ask:{other['id']}", logic.now()))
    assert "Secret" not in json.dumps(c.get("/api/admin/inbox", headers=tma(3)).json())


def test_ai_only_after_the_subject_and_the_quota(subj, monkeypatch):
    """Review P2: a made-up subject or a spent hour never reaches the AI."""
    c, con, p, sid, _ = subj
    calls = []
    monkeypatch.setattr(ai, "screen", lambda *a, **k: calls.append(1) or asyncio.sleep(0, result=True))
    assert c.put("/api/subjects/nope/me", headers=tma(1), json={"note": "hello"}).status_code == 404
    assert calls == []
    monkeypatch.setattr(logic.subjects, "WRITES_AN_HOUR", 2)
    for _ in range(2):
        assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "hello"}).status_code == 200
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "hello"}).status_code == 429
    assert len(calls) == 2


def test_hourly_counters_go(subj, monkeypatch):
    """Review P2: the hourly write counter: an older hour's goes with the next write and in the nightly forum_sweep."""
    c, con, p, sid, _ = subj
    con.execute("INSERT INTO meta (key, value) VALUES ('subj:1:5', '3'), ('subj:2:5', '1'), ('fsearch:2:5', '1')")
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    assert [r[0] for r in con.execute("SELECT key FROM meta WHERE key LIKE 'subj:1:%'")] == [f"subj:1:{logic.now() // 3600}"]
    logic.forum.forum_sweep(con)
    assert [r[0] for r in con.execute("SELECT key FROM meta WHERE key LIKE 'subj:%' OR key LIKE 'fsearch:%'")] == [f"subj:1:{logic.now() // 3600}"]


def test_tokenless_offers_never_answer(subj):
    """Review 2, P1: an offer from before tokens whose id another took: the migration gives every row a token, and a
    button or message without one answers or shows nothing (bot and app alike); an accepted message renders for its
    own recipient only."""
    c, con, p, sid, _ = subj
    cid, tok = _ann_offer(c, con, sid, 2)
    assert logic.decide_contact(con, p["ann"], cid, True, None) is None
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (p["ann"],))
    forum = TestClient(server.create(dataclasses.replace(c.app.state.cfg, forum=True)))
    assert forum.post(f"/api/forum/contacts/{cid}", headers=tma(1), json={"yes": True}).status_code == 404  # the app, no token
    assert outbox._render(con, {"kind": "contact_ask", "ref": f"ct:{cid}", "lang": "en", "user_id": p["ann"]}) is None
    assert logic.decide_contact(con, p["ann"], cid, True, tok) == "accepted"
    ok = {"kind": "contact_ok", "ref": f"co:{cid}:to:{tok}", "lang": "en"}
    assert outbox._render(con, ok | {"user_id": p["bob"]}) and outbox._render(con, ok | {"user_id": p["cat"]}) is None
    assert outbox._render(con, {"kind": "contact_ok", "ref": f"co:{cid}:to", "lang": "en", "user_id": p["bob"]}) is None


def test_migration_gives_old_offers_tokens(env, before_door_migration):  # noqa: F811
    c, cfg = env
    a, b = login(c, 1, "ann")["id"], login(c, 2, "bob")["id"]
    con = db.connect(cfg.db_path)
    before_door_migration(con)
    con.execute("DROP INDEX asks_subject")
    con.execute("ALTER TABLE asks DROP COLUMN subject")
    con.execute("ALTER TABLE contacts DROP COLUMN token")
    con.execute("DROP TABLE subject_holds")
    con.execute("INSERT INTO contacts (from_id, to_id, created_at) VALUES (?, ?, 0)", (b, a))
    con.execute("ALTER TABLE events DROP COLUMN online")  # 188's, added again on the way up
    con.execute("ALTER TABLE credits DROP COLUMN gh")  # 191's
    con.execute("ALTER TABLE users DROP COLUMN tg_photo_at")  # 194's
    con.executescript("""DROP TABLE reg_age; DROP TABLE event_guests;
        ALTER TABLE events DROP COLUMN age_check; ALTER TABLE events DROP COLUMN guest_list;""")
    con.execute("ALTER TABLE events DROP COLUMN silent_publish")  # 198's
    con.execute("ALTER TABLE org_invites DROP COLUMN consumed")  # 200's
    if con.execute("SELECT 1 FROM sqlite_master WHERE name = 'event_guests'").fetchone():
        con.execute("ALTER TABLE event_guests DROP COLUMN team")  # 212's
        con.execute("ALTER TABLE event_guests DROP COLUMN username")  # 211's
        con.execute("ALTER TABLE event_guests DROP COLUMN name")  # 210's
        con.execute("ALTER TABLE event_guests DROP COLUMN came_at")  # 209's
    con.execute("ALTER TABLE registrations DROP COLUMN door_team")  # 212's
    con.execute("ALTER TABLE events DROP COLUMN door_extra")  # 208's
    con.execute("ALTER TABLE users DROP COLUMN n_forum_comments")  # 206's
    con.executescript("DROP TABLE fchan_hearts; ALTER TABLE users DROP COLUMN forum_seen_msg;")  # 205
    con.execute("PRAGMA user_version = 176")
    con.close()
    db.init(cfg.db_path)
    con = db.connect(cfg.db_path)
    assert len(con.execute("SELECT token FROM contacts").fetchone()[0]) == 32
    con.close()


def test_subject_moderation_needs_the_policy_too(subj):
    """Review 4: a moderator who isn't the forum's sees subject listings in the queue only as a student on the policy in force."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    con.execute("UPDATE students SET consent_version = '1' WHERE user_id = ?", (p["cat"],))
    assert c.get("/api/forum/mod", headers=tma(3)).json()["message"] == "consent"
    con.execute("UPDATE students SET consent_version = ?, manual = 1 WHERE user_id = ?", (logic.CONSENT, p["cat"]))
    assert c.get("/api/forum/mod", headers=tma(3)).status_code in (401, 403)
    con.execute("UPDATE students SET manual = 0 WHERE user_id = ?", (p["cat"],))
    assert c.get("/api/forum/mod", headers=tma(3)).status_code == 200


def _lifted(c, con, p, sid) -> int:
    """Ann listed, hidden, lifted by Cat: the lift's audit line id."""
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    aid = con.execute("SELECT id FROM asks WHERE user_id = ?", (p["ann"],)).fetchone()[0]
    assert c.post(f"/api/forum/asks/{aid}/hide", headers=tma(3)).status_code == 204
    hid = con.execute("SELECT id FROM subject_holds").fetchone()[0]
    assert c.post(f"/api/forum/holds/{hid}", headers=tma(3)).status_code == 204
    return con.execute("SELECT id FROM audit_log WHERE action = 'subject_lift' ORDER BY id DESC").fetchone()[0]


def test_deleted_author_leaves_no_lift_to_undo(subj, env):  # noqa: F811
    """Review 4: deleting the account takes the lift's audit lines (they name the author and subject), and an Undo
    for someone no longer a student makes nothing."""
    c, con, p, sid, _ = subj
    _, cfg = env
    line = _lifted(c, con, p, sid)
    data = json.loads(con.execute("SELECT data FROM audit_log WHERE id = ?", (line,)).fetchone()[0])
    con.execute("DELETE FROM students WHERE user_id = ?", (p["ann"],))
    with pytest.raises(logic.ApiError):
        logic.subjects.unlift(con, logic.Viewer(p["cat"], "moderator", True), f"subject_hold:{1}", data)
    con.execute("INSERT INTO students (user_id, student_id, first_name, last_name, course, school, consent_version, consent_at, verified_at, synced_at) "
                "VALUES (?, '24Bann', 'Ann', 'Testov', 2, 'SITE', ?, 0, 0, 0)", (p["ann"], logic.CONSENT))
    delete_now(c, cfg, tma(1))
    assert not con.execute("SELECT 1 FROM audit_log WHERE action IN ('subject_lift', 'subject_unlift')").fetchone()
    assert not con.execute("SELECT 1 FROM subject_holds").fetchone()


def test_hide_with_the_row_gone_is_quiet(subj):
    """Review 4: hide_ask is one write; a row gone (left) meanwhile: nothing, no error; a hide records its hold whole."""
    c, con, p, sid, _ = subj
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    row = con.execute("SELECT id, created_at FROM asks").fetchone()
    c.delete(f"/api/subjects/{sid}/me", headers=tma(1))
    logic.hide_ask(con, row[0], "reports", made=(p["ann"], row[1]))                       # left before the verdict: quiet
    assert not con.execute("SELECT 1 FROM subject_holds").fetchone()

    # one transaction: a failure part way (here the hold's write) leaves the listing as it was, never half hidden
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    row = con.execute("SELECT id FROM asks").fetchone()

    def broken(*a, **k):
        raise RuntimeError("mid-way")
    import kbtu.logic.subjects as subj_mod
    real, subj_mod.hold = subj_mod.hold, broken
    try:
        with pytest.raises(RuntimeError):
            logic.hide_ask(con, row[0], "moderator", p["cat"])
    finally:
        subj_mod.hold = real
    assert con.execute("SELECT status FROM asks").fetchone()[0] == "live" and not con.in_transaction


def test_a_past_terms_hold_never_blocks_a_new_one(subj, monkeypatch):
    """Review 4: last term's hold, over, makes way: the new take-down is recorded (a new row) and stands."""
    c, con, p, sid, _ = subj
    con.execute("INSERT INTO subject_holds (user_id, subject, title, why, at, until) VALUES (?, ?, 'x', 'moderator', 0, 1)", (p["ann"], sid))
    old = con.execute("SELECT id FROM subject_holds").fetchone()[0]
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={})
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    logic.hide_ask(con, aid, "moderator", p["cat"])
    rows = con.execute("SELECT id, until FROM subject_holds").fetchall()
    assert len(rows) == 1 and rows[0][0] != old and rows[0][1] > logic.now()
    c.delete(f"/api/subjects/{sid}/me", headers=tma(1))
    assert c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={}).json()["message"] == "restricted"


def test_an_undone_lift_cant_be_replayed(subj):
    """Review 4: lift H1, undo it (the hold again: H2), lift H2: H1's Undo is decided and does nothing."""
    c, con, p, sid, _ = subj
    line1 = _lifted(c, con, p, sid)
    assert c.post(f"/api/admin/done/{line1}/undo", headers=tma(3)).status_code == 204
    h2 = con.execute("SELECT id FROM subject_holds").fetchone()[0]
    assert c.post(f"/api/forum/holds/{h2}", headers=tma(3)).status_code == 204
    assert c.post(f"/api/admin/done/{line1}/undo", headers=tma(3)).status_code in (404, 409)
    assert not con.execute("SELECT 1 FROM subject_holds").fetchone()


def test_reports_show_a_listing_only_to_a_reader(subj):
    """Review 5: with FORUM off, a reported listing's words reach a moderator through the reports and the inbox (and can
    be decided) only when they could read the listing itself: a student on the policy in force."""
    c, con, p, sid, _ = subj
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (p["cat"],))
    c.put(f"/api/subjects/{sid}/me", headers=tma(1), json={"note": "secret words"})
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    assert c.post("/api/reports", headers=tma(2), json={"target": "ask", "id": aid, "reason": "spam"}).status_code == 204
    con.execute("UPDATE students SET consent_version = '1' WHERE user_id = ?", (p["cat"],))
    assert "secret" not in json.dumps(c.get("/api/admin/reports", headers=tma(3)).json())
    assert "secret" not in json.dumps(c.get("/api/admin/inbox", headers=tma(3)).json())
    assert c.get("/api/me", headers=tma(3)).json()["counters"]["inbox"] == 0
    assert c.post(f"/api/admin/reports/ask/{aid}", headers=tma(3), json={"remove": True}).status_code == 404
    con.execute("UPDATE students SET consent_version = ? WHERE user_id = ?", (logic.CONSENT, p["cat"]))
    assert "secret" in json.dumps(c.get("/api/admin/reports", headers=tma(3)).json())


def test_join_rechecks_the_account_after_the_ai(subj):
    """Review 5: the account deleted while the AI looked at the note: the late write makes nothing."""
    c, con, p, sid, path = subj
    ann = logic.Viewer(p["ann"], "user", True)
    s = logic.subjects.reserve(con, ann, str(path), sid)
    con.execute("DELETE FROM students WHERE user_id = ?", (p["ann"],))                   # gone meanwhile
    with pytest.raises(logic.ApiError):
        logic.subjects.join(con, ann, str(path), s, "late words", True)
    assert not con.execute("SELECT 1 FROM asks").fetchone()


def test_undo_of_a_lift_holds_the_write_lock(subj, env, monkeypatch):  # noqa: F811
    """Review 5: the newest-decision check and the undo are one write: another moderator can't slip in between."""
    import sqlite3
    c, con, p, sid, _ = subj
    _, cfg = env
    line = _lifted(c, con, p, sid)
    real, seen = logic.subjects.unlift, []

    def between(*a, **k):
        other = sqlite3.connect(cfg.db_path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")                                                # a second moderator's write
            seen.append("got in")
        except sqlite3.OperationalError:
            seen.append("locked")
        finally:
            other.close()
        return real(*a, **k)
    monkeypatch.setattr(logic.subjects, "unlift", between)
    assert c.post(f"/api/admin/done/{line}/undo", headers=tma(3)).status_code == 204
    assert seen == ["locked"]


def test_an_old_workers_tokenless_offer_heals(subj):
    """Review 5: an offer written without a token (an old worker during a deploy): its card gets one when it's sent,
    offering again gives it one and a new card; a button without a token still does nothing."""
    c, con, p, sid, _ = subj
    cid, _tok = _ann_offer(c, con, sid, 2)
    con.execute("UPDATE contacts SET token = NULL")
    card = outbox._render(con, {"kind": "contact_ask", "ref": f"ct:{cid}", "lang": "en", "user_id": p["ann"]})
    tok = con.execute("SELECT token FROM contacts").fetchone()[0]
    assert tok and card[2][0][0]["callback_data"] == f"ct:{cid}:{tok}:y"
    assert logic.decide_contact(con, p["ann"], cid, True) is None
    con.execute("UPDATE contacts SET token = NULL")
    before = con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()[0]
    aid = con.execute("SELECT id FROM asks").fetchone()[0]
    assert c.post("/api/subjects/offer", headers=tma(2), json={"ask": aid}).status_code == 200  # offering again
    tok2 = con.execute("SELECT token FROM contacts").fetchone()[0]
    assert tok2 and con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()[0] == before + 1
    assert logic.decide_contact(con, p["ann"], cid, True, tok2) == "accepted"
