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

import pytest
from fastapi.testclient import TestClient

from kbtu import ai, app as server, bot, db, logic
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import subjects as tool  # noqa: E402

CALC = "\u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435 2"  # "Calculus 2"


def scrape() -> dict:
    return {"done": {
        "MAT1246": {"name": CALC, "events": []},
        "MATH2206.": {"name": " \u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435  2", "events": []},  # the same name, spaced
        "\u0420\u0415\u04221270": {"name": "Gas", "events": []},                                                     # Cyrillic look-alikes in the code
        "X1": {"name": "\u0412\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0437\u0430\u043d\u044f\u0442\u0438\u044f", "events": []},  # a placeholder
    }}


def test_tool_one_card_per_name():
    out = tool.cards(scrape())
    assert [(x["name"], x["codes"]) for x in out] == [("Gas", ["PET1270"]), (CALC, ["MAT1246", "MATH2206"])]
    assert out[1]["id"] == tool.cards({"done": {"Z9": {"name": CALC + " "}}})[0]["id"]  # stable across scrapes


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
    assert c.get(f"/api/subjects/{sid}", headers=tma(1)).status_code == 200            # reading is fine
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
    assert bot._render(con, dict(m) | {"lang": "en"})[2] == f"sj_{sid}"                                    # the author's link: the card


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
    assert c.post("/api/subjects/offer", headers=tma(2), json={"ask": aid}).json() == {"status": "pending"}
    assert c.get(f"/api/subjects/{sid}", headers=tma(2)).json()["people"][0]["offered"] == "pending"
    m = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'contact_ask'").fetchone()) | {"lang": "ru"}
    assert m["user_id"] == p["ann"] and CALC in bot._render(con, m)[0] and "bob_tg" not in bot._render(con, m)[0]
    cid = con.execute("SELECT id FROM contacts").fetchone()[0]
    assert logic.decide_contact(con, p["ann"], cid, True) == "accepted"
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
