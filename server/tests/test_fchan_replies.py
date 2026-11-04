"""The anonymous author's replies in the forum channel's comments (logic/fchannel.py reply_*, tgc._replies;
.claude/reports/anon-reply/review.md): the author of an anonymous post answers the thread or a linked comment through
the bot. Its own AI look, caps, a random wait, sent once, deleted by the author, taken down from the Admin sheet with
Undo, reportable, gone with the post and with the account; nothing ties a reply to anyone but through the post."""
from __future__ import annotations

import asyncio
import json
import time
import types

import httpx
import pytest

from kbtu import ai, db, logic, texts, tgc
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import CH, G, setup, tick
from test_tgcomments import Telegram

COPY = 55  # the post's copy in the group: the thread's root


class Tg(Telegram):
    """Telegram, with answers to set per method: (code, description) for a refusal, or None for no answer."""

    def __init__(self) -> None:
        super().__init__()
        self.say: dict[str, tuple[int, str] | None] = {}

    def __call__(self, request):
        method = request.url.path.rsplit("/", 1)[1]
        if method in self.say:
            body = json.loads(request.content)
            self.calls.append((method, body))
            if self.say[method] is None:
                raise httpx.ReadTimeout("no answer")
            code, why = self.say[method]
            return httpx.Response(code, json={"ok": False, "error_code": code, "description": why})
        return super().__call__(request)


def gate(cfg, tg, con, *upds: dict) -> None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await tgc.gate(cfg, http, con, list(upds))
            await tgc.settle()
    asyncio.run(go())


def note(mid: int, tg_id: int, to: int = COPY, bot: bool = False, text: str = "me too", **frm) -> dict:
    reply = {"message_id": to, "from": {"id": 777, "is_bot": True}} if bot else {"message_id": to, "is_automatic_forward": True}
    return {"message": {"message_id": mid, "from": {"id": tg_id, **frm}, "chat": {"id": G, "type": "supergroup"}, "date": 0, "text": text,
                        "message_thread_id": COPY, "reply_to_message": reply}}


def world(env, monkeypatch, word: str | None = "ok"):
    """Ann's anonymous post live in the channel, its copy in the group, a comment of Bob's (60) under it."""
    c, cfg, said, _ = setup(env, monkeypatch)
    rsaid = {"word": word}

    async def look(_cfg, _http, text, con=None):
        return rsaid["word"]
    monkeypatch.setattr(ai, "screen_reply", look)
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    tg = Tg()
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Who else thinks the cafeteria got worse?", "anon": True}).json()
    tick(cfg, tg, con)
    mid = con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0]
    gate(cfg, tg, con, {"message": {"message_id": COPY, "chat": {"id": G, "type": "supergroup"}, "is_automatic_forward": True, "date": 0, "text": "x",
                                    "sender_chat": {"id": CH, "type": "channel", "username": "KBTUappForum"}, "forward_origin": {"type": "channel", "message_id": mid}}})
    gate(cfg, tg, con, note(60, 2))
    return types.SimpleNamespace(c=c, cfg=cfg, con=con, tg=tg, pid=p["id"], mid=mid, rsaid=rsaid, ann=ann, bob=bob,
                                 link=f"https://t.me/KBTUappForum/{mid}?comment=60")


def clock(monkeypatch) -> list[int]:
    t = [int(time.time())]
    set_clock(monkeypatch, lambda: t[0])
    return t


def group_sends(tg) -> list[dict]:
    return [b for b in tg.of("sendMessage") if b["chat_id"] == G and "reply_markup" not in b]  # not the rules' first comment


def test_reply_flow_wait_and_once(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Agreed, the soup is cold", "link": w.link}).json()
    assert r["state"] == "soon" and r["comment"] == 60
    wait = w.con.execute("SELECT send_at - created_at FROM fchan_replies WHERE id = ?", (r["id"],)).fetchone()[0]
    assert logic.fchannel.REPLY_WAIT[0] <= wait <= logic.fchannel.REPLY_WAIT[1]              # from the tap, at random
    tick(w.cfg, w.tg, w.con)
    assert not group_sends(w.tg)                                                             # not before the wait
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    tick(w.cfg, w.tg, w.con)
    s = group_sends(w.tg)
    assert len(s) == 1 and s[0]["reply_parameters"] == {"message_id": 60} and s[0]["parse_mode"] == "HTML"
    nick = texts.nick(*w.con.execute("SELECT nick_a, nick_n FROM fchan_posts WHERE id = ?", (w.pid,)).fetchone())
    assert s[0]["text"] == f"Agreed, the soup is cold\n\n<i>— {texts.FCH_REPLY_NICK.format(nick=nick)}</i>"      # the post's nick
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).json()[0]["state"] == "sent"
    # without a link: to the thread (the post's copy)
    t[0] += 61
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Thanks everyone"})
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert group_sends(w.tg)[-1]["reply_parameters"] == {"message_id": COPY}
    # plain text only
    t[0] += 61
    for bad in ("see kbtu.kz", "ask @someone", "x"):
        assert w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": bad}).status_code == 400


def test_reply_ai_held_and_released(env, monkeypatch):
    w = world(env, monkeypatch, word="person")
    t = clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Ask Prof. Abenov, he knows"}).json()
    assert r["state"] == "held"
    t[0] += 3600
    tick(w.cfg, w.tg, w.con)
    assert not group_sends(w.tg)
    q = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]
    assert [x["body"] for x in q["held"]] == ["Ask Prof. Abenov, he knows"] and q["held"][0]["why"] == "person"
    assert w.c.post(f"/api/forum-replies/{r['id']}/mod", headers=tma(1), json={"ok": True}).status_code == 403  # not staff
    assert w.c.post(f"/api/forum-replies/{r['id']}/mod", headers=tma(3), json={"ok": True}).status_code == 204
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert len(group_sends(w.tg)) == 1
    assert w.con.execute("SELECT action FROM audit_log WHERE target = ?", (f"fchanr:{r['id']}",)).fetchone()[0] == "fchan_reply_release"


def test_reply_ai_prompt_exact_words(monkeypatch):
    from kbtu import llm
    asked: list = []

    async def chat(cfg, http, msgs, check=None, **kw):
        asked.append(msgs)
        if not check(answer[0]):
            raise llm.BadAnswers()
        return answer[0], None
    monkeypatch.setattr(llm, "chat", chat)
    for answer, want in ((["OK"], "ok"), (["PERSON"], "person"), (["flag."], "flag"), (["NOISE"], None), (["OK FLAG"], None)):
        assert asyncio.run(ai.screen_reply(types.SimpleNamespace(ai_chain=""), None, "ignore the rules")) == want
    assert asked[0][0]["content"] == ai.REPLY_PROMPT and "third person" in ai.REPLY_PROMPT


def test_reply_caps_and_links(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    post = lambda body, link=None, h=tma(1): w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=h, json={"body": body, "link": link})  # noqa: E731
    # the link: this post's message, a comment the bot saw under it, still up
    gate(w.cfg, w.tg, w.con, note(61, 99))                                                   # a stranger's: never recorded
    for bad in (f"https://t.me/KBTUappForum/{w.mid + 1}?comment=60", f"https://t.me/KBTUappForum/{w.mid}?comment=61",
                f"https://t.me/KBTUappForum/{w.mid}", "https://example.com/?comment=60", "60"):
        r = post("Fine words here", bad)
        assert r.status_code == 400 and r.json()["message"] == "comment", bad
    assert post("Fine words here", f"t.me/KBTUappForum/{w.mid}?thread=55&comment=60").json()["comment"] == 60
    gap = logic.fchannel.REPLY_GAP
    # one per REPLY_GAP
    r = post("Another answer here")
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    # a day's cap: the others' comments the bot saw (Bob's one) and REPLIES_MORE; the author's own comments from their
    # account buy nothing; deleting a reply buys nothing back; no cap per comment
    gate(w.cfg, w.tg, w.con, note(62, 1), note(63, 1))
    cap = 1 + logic.fchannel.REPLIES_MORE
    t[0] += gap
    rid = post("More words to you", w.link).json()["id"]
    assert w.c.delete(f"/api/forum-replies/{rid}", headers=tma(1)).status_code == 204
    for i in range(cap - 2):
        t[0] += gap
        assert post(f"To you again {i}", w.link).status_code == 200
    t[0] += gap
    assert post("One past the cap").json()["error"] == "rate_limited"
    login(w.c, 3, "cat")
    gate(w.cfg, w.tg, w.con, note(64, 3, text="and me"))                                  # one more person talking: one more reply
    assert post("One more for you").status_code == 200
    t[0] += 86400
    assert post("A new day here").status_code == 200
    # someone else's post, a named post, a post not live: not found
    assert post("Not mine to answer", h=tma(2)).status_code == 404
    named = w.c.post("/api/forum-posts", headers=tma(2), json={"body": "A named post about lunch"}).json()
    assert w.c.post(f"/api/forum-posts/{named['id']}/replies", headers=tma(2), json={"body": "Hello there"}).status_code == 404


def test_reply_anonymity(env, monkeypatch):
    """Nothing but the post owner's own view ties a reply to a person: no user id on the row, no author in the
    moderators' queue, someone else asking for the list gets nothing, the feed carries none."""
    w = world(env, monkeypatch, word="flag")
    clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (mod["id"],))
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Secret words of mine"}).json()
    cols = [x[1] for x in w.con.execute("PRAGMA table_info(fchan_replies)")]
    assert not any("user" in x or "tg" == x for x in cols) and "tg_msg" in cols
    assert [fk[2] for fk in w.con.execute("PRAGMA foreign_key_list(fchan_replies)")] == ["fchan_posts"]
    for h in (tma(2), tma(3), tma(9)):
        assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=h).status_code in (401, 404)
        assert w.c.delete(f"/api/forum-replies/{r['id']}", headers=h).status_code in (401, 404)
        assert w.c.post(f"/api/forum-replies/{r['id']}/why", headers=h).status_code in (401, 403, 404)  # the AI's reason: its author's alone
    assert r["ai"] is True and w.c.post(f"/api/forum-replies/{r['id']}/why", headers=tma(1)).json() == {"explain": None}
    assert w.c.post(f"/api/forum-replies/{r['id']}/why", headers=tma(1)).status_code == 404  # once
    q = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()
    held = q["replies"]["held"][0]
    assert set(held) == {"id", "body", "post", "postBody", "why", "reports", "at", "undo", "anon", "nick"}
    blob = json.dumps(q["replies"]) + json.dumps(w.c.get("/api/forum-posts/feed", headers=tma(3)).json())
    assert "Ann" not in blob and '"person"' not in json.dumps(q["replies"])
    assert "Secret words" not in json.dumps(w.c.get("/api/forum-posts/feed", headers=tma(2)).json())


def test_reply_delete_takedown_undo(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    ids = []
    for body in ("First answer here", "Second answer here"):
        ids.append(w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": body}).json()["id"])
        t[0] += 61
    tick(w.cfg, w.tg, w.con)
    msgs = [w.con.execute("SELECT tg_msg FROM fchan_replies WHERE id = ?", (i,)).fetchone()[0] for i in ids]
    assert all(m > 0 for m in msgs)
    # the author deletes: the words wiped at once, the message out of the group next round
    assert w.c.delete(f"/api/forum-replies/{ids[0]}", headers=tma(1)).status_code == 204
    assert w.con.execute("SELECT body FROM fchan_replies WHERE id = ?", (ids[0],)).fetchone()[0] == ""
    tick(w.cfg, w.tg, w.con)
    assert {"chat_id": G, "message_id": msgs[0]} in w.tg.of("deleteMessage")
    # a moderator takes one down: Undo inside the minute keeps the message
    assert w.c.post(f"/api/forum-replies/{ids[1]}/mod", headers=tma(3), json={"ok": False}).status_code == 204
    rem = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]["removed"]
    assert rem[0]["id"] == ids[1] and rem[0]["undo"] is True
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).json()[0]["state"] == "removed"
    tick(w.cfg, w.tg, w.con)
    assert {"chat_id": G, "message_id": msgs[1]} not in w.tg.of("deleteMessage")
    assert w.c.post(f"/api/forum-replies/{ids[1]}/restore", headers=tma(3)).status_code == 204
    t[0] += 120
    tick(w.cfg, w.tg, w.con)
    assert {"chat_id": G, "message_id": msgs[1]} not in w.tg.of("deleteMessage")
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).json()[0]["state"] == "sent"
    # taken down again, the minute over: out; too old to delete (Telegram's 400): edited to the template
    w.c.post(f"/api/forum-replies/{ids[1]}/mod", headers=tma(3), json={"ok": False})
    t[0] += 61
    w.tg.say["deleteMessage"] = (400, "Bad Request: message can't be deleted")
    tick(w.cfg, w.tg, w.con)
    assert w.tg.of("editMessageText")[-1] == {"chat_id": G, "message_id": msgs[1], "text": texts.bot_message("ru", "fch_reply_removed")[0]}
    assert w.con.execute("SELECT tg_msg FROM fchan_replies WHERE id = ?", (ids[1],)).fetchone()[0] is None
    acts = [a for (a,) in w.con.execute("SELECT action FROM audit_log WHERE target = ? ORDER BY id", (f"fchanr:{ids[1]}",))]
    assert acts == ["fchan_reply_hide", "fchan_reply_undo", "fchan_reply_hide"]


def test_reply_goes_with_post(env, monkeypatch):
    """Deleting or taking down the post takes its replies out of the group; unsent ones never go; a hidden post or a
    banned author gets no replies."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    sent = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Sent before the end"}).json()["id"]
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    t[0] += 61
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Not yet sent"})
    msg = w.con.execute("SELECT tg_msg FROM fchan_replies WHERE id = ?", (sent,)).fetchone()[0]
    w.con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 1")                          # banned meanwhile: nothing goes
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert len(group_sends(w.tg)) == 1
    w.con.execute("UPDATE users SET banned_at = NULL WHERE tg_id = 1")
    assert w.c.delete(f"/api/forum-posts/{w.pid}", headers=tma(1)).status_code == 204
    tick(w.cfg, w.tg, w.con)
    assert {"chat_id": G, "message_id": msg} in w.tg.of("deleteMessage") and len(group_sends(w.tg)) == 1
    assert {s for (s,) in w.con.execute("SELECT status FROM fchan_replies")} == {"hidden"}
    assert w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "After the end"}).status_code == 404


def test_reply_send_missing_and_lost(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "To a comment soon gone", "link": w.link}).json()
    t[0] += 21
    w.tg.say["sendMessage"] = (400, "Bad Request: message to be replied not found")
    tick(w.cfg, w.tg, w.con)
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).json()[0]["state"] == "missing"
    assert w.con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'fch_reply_gone' AND ref = ?", (w.ann["id"], f"fg:{r['id']}")).fetchone()
    tick(w.cfg, w.tg, w.con)
    assert len([b for b in w.tg.of("sendMessage") if b["chat_id"] == G and "reply_parameters" in b and b["reply_parameters"]["message_id"] == 60]) == 1
    # no answer at all: never sent twice by itself, a moderator decides
    t[0] += 61
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Into the void"}).json()
    t[0] += 21
    w.tg.say["sendMessage"] = None
    tick(w.cfg, w.tg, w.con)
    tick(w.cfg, w.tg, w.con)
    assert len([b for b in w.tg.of("sendMessage") if b["text"].startswith("Into the void")]) == 1
    assert w.con.execute("SELECT status, why FROM fchan_replies WHERE id = ?", (r["id"],)).fetchone()[:] == ("held", "lost")


def test_reply_report_answer_and_posing(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    r = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "My anonymous answer"}).json()
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    msg = w.con.execute("SELECT tg_msg FROM fchan_replies WHERE id = ?", (r["id"],)).fetchone()[0]
    # /report on the bot's reply: into the Admin sheet, the reporter told; counted once per reporter
    for _ in range(2):
        gate(w.cfg, w.tg, w.con, note(70, 2, to=msg, bot=True, text="/report"))
    live = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]["live"]
    assert live[0]["id"] == r["id"] and live[0]["reports"] == 1
    assert w.con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'tgc_report_ok' AND ref = ?", (w.bob["id"], f"rr:{r['id']}")).fetchone()
    assert w.c.post(f"/api/forum-replies/{r['id']}/mod", headers=tma(3), json={"ok": True}).status_code == 204  # kept: reports cleared
    assert w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]["live"][0]["reports"] == 0
    # an answer to the bot's reply: its author hears (a template with a button to the post), once an hour
    gate(w.cfg, w.tg, w.con, note(71, 2, to=msg, bot=True, text="who are you?"), note(72, 2, to=msg, bot=True, text="hello?"))
    rows = w.con.execute("SELECT user_id, ref FROM bot_outbox WHERE kind = 'fch_reply_answer'").fetchall()
    assert [tuple(x) for x in rows] == [(w.ann["id"], f"fa:{r['id']}:{t[0] // 3600}")]
    from kbtu import bot
    m = w.con.execute("SELECT *, 'ru' AS lang FROM bot_outbox WHERE kind = 'fch_reply_answer'").fetchone()
    assert bot._render(w.con, m) == (*texts.bot_message("ru", "fch_reply_answer"), f"fp_{w.pid}")
    # posing as the mark: the mark's words in the name (case, Latin look-alikes, invisible characters, with or without
    # the mask) or as the text's own signature line: deleted; the mask alone in a name, or the words inside a sentence, stay
    w.tg.calls.clear()
    words = texts.FCH_REPLY_SIGN[2:]
    gate(w.cfg, w.tg, w.con, note(73, 2, first_name="\U0001f3ad Author"), note(74, 2, first_name=words.upper()), note(75, 2, first_name="Bob"),
         note(76, 2, first_name="A" + words[1:3] + "\u200b" + words[3:]), note(77, 2, text=f"sure\n\n\u2014 {texts.FCH_REPLY_SIGN}"),
         note(78, 2, text=f"{words} is right"))
    assert w.tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [74, 76, 77]}]


def test_reply_account_deletion(env, monkeypatch):
    """Deleting the account: sent replies under the live post stay with it (the placeholder), unsent ones go."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Sent one here"})
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    t[0] += 61
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Waiting one here"})
    delete_now(w.c, w.cfg, tma(1))
    left = w.con.execute("SELECT r.body, u.tg_id FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id JOIN users u ON u.id = p.user_id").fetchall()
    assert [x[0] for x in left] == ["Sent one here"] and left[0][1] < 0


def sent_reply(w, t, body: str = "My anonymous answer") -> tuple[int, int]:
    rid = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": body}).json()["id"]
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    return rid, w.con.execute("SELECT tg_msg FROM fchan_replies WHERE id = ?", (rid,)).fetchone()[0]


@pytest.mark.parametrize("how", ["delete", "hide"])
def test_reply_mid_send_post_off(env, monkeypatch, how):
    """Adversarial 1: the post deleted (or taken down) while its reply is on the wire: the reply still leaves the group."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    rid = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "On the wire now"}).json()["id"]
    assert logic.fchannel.reply_sending(w.con, rid)
    if how == "delete":
        assert w.c.delete(f"/api/forum-posts/{w.pid}", headers=tma(1)).status_code == 204
    else:
        assert w.c.post(f"/api/forum-posts/{w.pid}/mod", headers=tma(3), json={"ok": False}).status_code == 204
    logic.fchannel.reply_sent(w.con, rid, 999)
    t[0] += 61
    tick(w.cfg, w.tg, w.con)
    assert {"chat_id": G, "message_id": 999} in w.tg.of("deleteMessage"), how
    w.con.close()


def test_reply_reports_reach_moderators(env, monkeypatch):
    """Adversarial 2, 3: a report on an old reply still shows in Admin and pings the moderators; three long-verified
    reporters take it down at once (Undo/Bring back as a moderator's); who reported is a row that goes with the account."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    for i, n in ((3, "mod"), (4, "cat"), (5, "dan")):
        login(w.c, i, n)
    w.con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 3")
    rid, msg = sent_reply(w, t)
    t[0] += 8 * 86400                                                                           # past the week's list
    gate(w.cfg, w.tg, w.con, note(70, 2, to=msg, bot=True, text="/report"))
    q = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]
    assert [(x["id"], x["reports"]) for x in q["live"]] == [(rid, 1)]
    mods = w.con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'fch_reply_queue'").fetchall()
    assert [m[0] for m in mods] == [w.con.execute("SELECT id FROM users WHERE tg_id = 3").fetchone()[0]]
    from kbtu import bot
    m = w.con.execute("SELECT *, 'ru' AS lang FROM bot_outbox WHERE kind = 'fch_reply_queue'").fetchone()
    assert bot._render(w.con, m) == (*texts.bot_message("ru", "fch_reply_queue", n=1), "capps")
    assert w.con.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'fchrrep:%'").fetchone()[0] == 0
    # the reporter deletes the account: their report goes with it
    delete_now(w.c, w.cfg, tma(2))
    assert w.con.execute("SELECT COUNT(*) FROM fchan_reply_reports").fetchone()[0] == 0
    # three reporters verified long ago: down at once
    w.con.execute("UPDATE students SET verified_at = 0")
    for i, mid in ((3, 71), (4, 72)):
        gate(w.cfg, w.tg, w.con, note(mid, i, to=msg, bot=True, text="/report"))
    assert w.con.execute("SELECT status FROM fchan_replies WHERE id = ?", (rid,)).fetchone()[0] == "live"
    gate(w.cfg, w.tg, w.con, note(73, 5, to=msg, bot=True, text="/report"))
    assert w.con.execute("SELECT status, why FROM fchan_replies WHERE id = ?", (rid,)).fetchone()[:] == ("hidden", "reports")
    rem = w.c.get("/api/forum-posts/mod", headers=tma(3)).json()["replies"]["removed"]
    assert rem[0]["id"] == rid and rem[0]["undo"] is True and rem[0]["anon"] is True
    assert w.c.post(f"/api/forum-replies/{rid}/restore", headers=tma(3)).status_code == 204
    assert w.con.execute("SELECT COUNT(*) FROM fchan_reply_reports").fetchone()[0] == 0
    # the reply's post is anonymous: the owner's reveal goes through it, audited as for the post
    w.con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 3")
    assert w.c.post(f"/api/forum-posts/{w.pid}/reveal", headers=tma(3)).json()["id"] == w.ann["id"]


def test_reply_lost_needs_explicit_again(env, monkeypatch):
    """Adversarial 5: a lost send may be in the group: never released by a plain yes, only by again=True."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    mod = login(w.c, 3, "mod")
    w.con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    rid = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Lost on the way"}).json()["id"]
    assert logic.fchannel.reply_sending(w.con, rid)
    tick(w.cfg, w.tg, w.con)                                                                    # no answer came: lost
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).json()[0]["state"] == "maybe"
    r = w.c.post(f"/api/forum-replies/{rid}/mod", headers=tma(3), json={"ok": True})
    assert r.status_code == 409
    assert w.c.post(f"/api/forum-replies/{rid}/mod", headers=tma(3), json={"ok": True, "again": True}).status_code == 204
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert len([b for b in group_sends(w.tg) if b["text"].startswith("Lost on the way")]) == 1


def test_reply_other_not_found_keeps_reply(env, monkeypatch):
    """Nit: only "message to be replied not found" means the comment is gone; "chat not found" retries."""
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    rid = w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Patience please"}).json()["id"]
    t[0] += 21
    w.tg.say["sendMessage"] = (400, "Bad Request: chat not found")
    tick(w.cfg, w.tg, w.con)
    assert w.con.execute("SELECT status, tg_msg FROM fchan_replies WHERE id = ?", (rid,)).fetchone()[:] == ("live", None)
