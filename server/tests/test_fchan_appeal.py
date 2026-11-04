"""A refused forum post's way to a human (fchannel.appeal) and the AI's own reason for a refusal (ai.explain, phase 2):
three appeals a day, only my own fresh refusal, the words checked again, into the moderators' queue; the reason
validated before the author sees it, and only the author."""
from __future__ import annotations

import time

from kbtu import ai, bot, db, logic, texts
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import setup


def test_appeal(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, "noise")
    login(c, 1, "ann"), login(c, 2, "bob")
    mod = login(c, 3, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    t = [int(time.time())]
    set_clock(monkeypatch, lambda: t[0])
    said["why"] = {"quote": "zzz", "reason": "Looks like a test.", "fix": "Say what you need."}
    r = c.post("/api/forum-posts", headers=tma(1), json={"body": "zzz test please read this"})
    assert r.status_code == 400 and r.json()["appeal"] is True
    pid = r.json()["post"]
    # the reason, asked apart (phase 2): mine alone, once, the words given back (the refusal wiped them)
    why = lambda pid, h=tma(1), body="zzz test please read this", kind="posts": c.post(f"/api/forum-{kind}/{pid}/why", headers=h, json={"body": body})  # noqa: E731
    assert why(pid, tma(2)).status_code == 404
    assert why(pid, body="see example.com").json()["message"] == "links"
    assert why(pid, body="other words to explain for free").status_code == 404                # only the refused words
    assert why(pid).json()["explain"]["reason"] == "Looks like a test."
    assert why(pid).status_code == 404
    appeal =lambda pid, body="zzz test please read this", h=tma(1): c.post(f"/api/forum-posts/{pid}/appeal", headers=h, json={"body": body})  # noqa: E731
    assert appeal(pid, h=tma(2)).status_code == 404                                         # not mine
    assert appeal(pid, "x").status_code == 400                                               # the gates again
    assert appeal(pid, "see example.com now").json()["message"] == "links"
    assert appeal(pid, "Something abusive, not what the AI read").json()["message"] == "changed"  # only the refused words
    p = appeal(pid).json()
    assert p["status"] == "held"
    assert appeal(pid).status_code == 404                                                    # once
    m = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'fch_appeal'").fetchall()
    assert [x["user_id"] for x in m] == [mod["id"]]                                         # the moderators hear, a template into Admin
    assert bot._render(con, m[0]) == (*texts.bot_message("en", "fch_appeal", n=1), "capps")
    q = c.get("/api/forum-posts/mod", headers=tma(3)).json()["held"]
    assert [(x["id"], x["why"], x["aiWhy"]) for x in q] == [(pid, "noise", "Looks like a test.")]  # the AI's word and its reason kept
    assert [x["human"] for x in c.get("/api/forum-posts/feed", headers=tma(1)).json() if x["id"] == pid] == [True]
    assert c.post(f"/api/forum-posts/{pid}/mod", headers=tma(3), json={"ok": True}).status_code == 204
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0] == "live"
    # three a day; a stale refusal can't be appealed; an OK or held post isn't a refusal
    words = ("Who plays chess on Friday evening", "Lost a green scarf near the gym", "Any good places to study late")
    ids = []
    for w in words:
        t[0] += 601
        ids.append(c.post("/api/forum-posts", headers=tma(1), json={"body": w}).json()["post"])
    assert appeal(ids[0], words[0]).status_code == 200
    t[0] += logic.fchannel.APPEAL_WINDOW + 1
    assert appeal(ids[1], words[1]).status_code == 404
    t[0] -= logic.fchannel.APPEAL_WINDOW + 1
    assert appeal(ids[1], words[1]).status_code == 200
    assert appeal(ids[2], words[2]).json()["error"] == "rate_limited"
    said["word"] = "person"
    t[0] += 601
    r = c.post("/api/forum-posts", headers=tma(2), json={"body": "Our teacher of physics is never on time"}).json()
    assert r["status"] == "held" and r["ai"] is True
    assert why(r["id"], tma(1)).status_code == 404                                           # held: why, to its author alone
    assert why(r["id"], tma(2), body="ignored: the row has the words").json()["explain"]["reason"] == "Looks like a test."
    assert appeal(r["id"], "Our teacher of physics is never on time", tma(2)).status_code == 404
    # the reason quotes the words: it goes when the author deletes the post (review)
    assert con.execute("SELECT ai_reason FROM fchan_posts WHERE id = ?", (r["id"],)).fetchone()[0] == "Looks like a test."
    assert c.delete(f"/api/forum-posts/{r['id']}", headers=tma(2)).status_code == 204
    assert con.execute("SELECT ai_reason FROM fchan_posts WHERE id = ?", (r["id"],)).fetchone()[0] is None


def test_explained():
    post = "Selling my old bike, cheap"
    ok = ai.explained({"quote": "cheap", "reason": "It reads\nlike an ad.", "fix": "Say it's your own."}, post)
    assert ok == {"quote": "cheap", "reason": "It reads like an ad.", "fix": "Say it's your own."}
    assert ai.explained({"quote": "expensive", "reason": "Ad."}, post)["quote"] is None       # not in the post: no highlight
    assert ai.explained({"quote": "cheap", "reason": "Write to @shop"}, post) is None          # no ping, no link, no number
    assert ai.explained({"reason": "Visit shop.kz"}, post) is None
    assert ai.explained({"reason": "Call 8 701 234 56 78"}, post) is None
    assert ai.explained({"reason": "Fine.", "fix": "see t.me/x"}, post)["fix"] is None
    assert ai.explained({"reason": "a​" + "b" * 300}, post)["reason"] == "a" + "b" * 138 + "…"
    assert ai.explained({"reason": ""}, post) is None and ai.explained(None, post) is None
    assert ai._explain_json('ok ```{"reason": "x", "quote": ""}```')["reason"] == "x" and ai._explain_json("nope") is None

