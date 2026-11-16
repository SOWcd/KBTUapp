"""Sharing a forum post: the card (POST /api/share kind "fp") only for a post live in the channel, its opening words and
a button with the post's id, never a signature; inline mode offers my own live signed posts, never an anonymous one."""
from __future__ import annotations

import json

import httpx

from kbtu import app as server, bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def _post(con, uid, body, anon=0, status="live", msg=7):
    return con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at, sign) VALUES (?, ?, ?, ?, ?, ?, 'Ali K.')",
                       (uid, body, anon, status, msg, logic.now())).lastrowid


def test_share_post_card_and_inline(env, monkeypatch):
    c, cfg = env
    ali, _ = login(c, 61, "ali"), login(c, 62, "bob")
    con = db.connect(cfg.db_path)
    signed = _post(con, ali["id"], "Who is up for chess <b>tonight</b>?\nRoom 404")
    anon = _post(con, ali["id"], "A secret thought", anon=1)
    held = _post(con, ali["id"], "Not yet", status="held", msg=None)
    long = _post(con, ali["id"], "word " * 100)
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))

    # anyone may pass a live post on, an anonymous one too: the card has its words, escaped, and no signature
    for pid in (signed, anon):
        assert c.post("/api/share", headers=tma(62), json={"kind": "fp", "id": pid}).json() == {"id": "prep1"}
    card = sent[-1]["result"]
    text = card["input_message_content"]["message_text"]
    assert "A secret thought" in text and "Ali" not in json.dumps(card)
    assert card["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(f"startapp=fp_{anon}")
    c.post("/api/share", headers=tma(62), json={"kind": "fp", "id": signed})
    assert "&lt;b&gt;tonight&lt;/b&gt;" in sent[-1]["result"]["input_message_content"]["message_text"]
    c.post("/api/share", headers=tma(62), json={"kind": "fp", "id": long})
    assert len(sent[-1]["result"]["description"]) <= 161 and sent[-1]["result"]["description"].endswith("…")
    # not in the channel (held, gone, unknown): no card
    con.execute("UPDATE fchan_posts SET status = 'hidden' WHERE id = ?", (long,))
    for pid in (held, long, 999):
        assert c.post("/api/share", headers=tma(62), json={"kind": "fp", "id": pid}).status_code != 200

    # inline: my own live signed posts only, never the anonymous one (the sender shows in the chat), nor others'
    def ask(tg):
        return [r["id"] for r in bot.inline_answer(cfg, con, {"id": "q", "from": {"id": tg, "language_code": "en"}, "query": ""})["results"]]
    assert [i for i in ask(61) if i.startswith("fp-")] == [f"fp-{signed}"]
    assert not any(i.startswith("fp-") for i in ask(62))
