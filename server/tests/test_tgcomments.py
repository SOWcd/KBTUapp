"""The forum channel's comments in Telegram (TG_COMMENTS_CHAT; logic/tgcomments.py, tgc.py): strangers deleted, warned
once and banned the second time; the stranger's text shown in the app to that Telegram account alone; /report with
the AI gate and the moderators' last word; edits judged again; abusers' /report closed; account deletion. Telegram and
the AI are mocked; each test drives the bot's ears (bot.hear) and round (tgc.tick) as production does."""
from __future__ import annotations

import asyncio
import dataclasses
import json

import httpx
from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, logic, tgc
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)

G = -100777           # the discussion group
ROOT = 10             # the channel post's copy in the group: the thread's root


class Telegram:
    """A mock Bot API: getUpdates hands out `batch`; every other call is recorded as (method, body) and succeeds."""

    def __init__(self) -> None:
        self.batch: list[dict] = []
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": self.batch})
        body = json.loads(request.content)
        self.calls.append((method, body))  # an edit answers with the same message, as Telegram does
        return httpx.Response(200, json={"ok": True, "result": {"message_id": body.get("message_id") or 900 + len(self.calls)}})

    def of(self, method: str) -> list[dict]:
        return [b for m, b in self.calls if m == method]


def hear(cfg, tg: Telegram, *updates: dict) -> None:
    tg.batch = [{"update_id": i + 1, **u} for i, u in enumerate(updates)]

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.hear(cfg, http, 0)
            await tgc.settle()  # the AI's looks run beside the ears
    asyncio.run(go())


def banned(tg: Telegram) -> list[int]:
    return [b["user_id"] for b in tg.of("banChatMember")]


def tick(cfg, tg: Telegram, con) -> None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await tgc.tick(cfg, http, con)
    asyncio.run(go())


def msg(mid: int, tg: int, text: str = "hello", **kw) -> dict:
    return {"message_id": mid, "chat": {"id": G, "type": "supergroup"}, "from": {"id": tg, "language_code": "en"}, "date": 0,
            "text": text, "message_thread_id": ROOT, "reply_to_message": {"message_id": ROOT, "is_automatic_forward": True}, **kw}


def report(mid: int, tg: int, target: dict) -> dict:
    return {"message": msg(mid, tg, "/report", reply_to_message=target)}


COPY = {"message": {"message_id": ROOT, "chat": {"id": G, "type": "supergroup"}, "is_automatic_forward": True, "date": 0,
                    "sender_chat": {"id": -100555, "type": "channel", "username": "KBTUforum"},
                    "forward_origin": {"type": "channel", "message_id": 42}, "text": "a post"}}


def setup(env, monkeypatch, verdicts: dict | None = None):
    """The app with the feature on, and the AI's answers by text (unlisted: no answer)."""
    _, cfg0 = env
    cfg = dataclasses.replace(cfg0, tgc_chat=G)
    c = TestClient(server.create(cfg))
    looked: list[str] = []

    async def screen(cfg_, http, text, con=None):
        looked.append(text)
        v = (verdicts or {}).get(text)
        return v, "insult" if v is False else None
    monkeypatch.setattr(tgc.ai, "screen_comment", screen)
    return c, cfg, db.connect(cfg.db_path), looked


def student(c, con, tg: int, name: str, old: bool = True) -> int:
    uid = login(c, tg, name)["id"]
    if old:  # verified by Microsoft over two weeks ago: a report that counts toward a deletion
        con.execute("UPDATE students SET verified_at = 0 WHERE user_id = ?", (uid,))
    return uid


def outbox(con, kind: str) -> list[tuple[int, str]]:
    return [tuple(r) for r in con.execute("SELECT user_id, ref FROM bot_outbox WHERE kind = ? ORDER BY id", (kind,))]


def test_strangers_deleted_warned_banned(env, monkeypatch):
    """A stranger's comment goes at once and the bot answers once in its thread (a button into the app, no secret in
    it; the answer goes after a minute, even across a restart); the second goes with a ban. Posting as another channel:
    deleted, that channel banned; the forum channel itself may. A student stays; an app-banned student is banned here.
    Many strangers in a minute: a raid, silent bans, the owner hears. A banned stranger who signs in is unbanned."""
    c, cfg, con, _ = setup(env, monkeypatch)
    owner = login(c, 1, "owner")["id"]
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE id = ?", (owner,))
    student(c, con, 20, "ali")
    tg = Telegram()
    hear(cfg, tg, COPY, {"message": msg(11, 20, "a student's comment")}, {"message": msg(12, 77, "a stranger's comment")},
         {"message": {k: x for k, x in msg(13, 77).items() if k != "text"} | {"new_chat_members": [{"id": 77}]}})  # a join line: it stays
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [12]}]
    w = tg.of("sendMessage")
    assert len(w) == 1 and w[0]["reply_parameters"] == {"message_id": ROOT, "allow_sending_without_reply": True}
    assert w[0]["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://t.me/KBTUappBot?startapp=cm"
    assert "1 hour" in w[0]["text"] and not tg.of("banChatMember")
    assert con.execute("SELECT body, link FROM tgc_saved WHERE tg_id = 77").fetchone()[:] == ("a stranger's comment", "https://t.me/KBTUforum/42?comment=12")

    tg.calls.clear()  # the second comment: deleted and banned, no second warning
    hear(cfg, tg, {"message": msg(14, 77, "again")})
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [14]}] and banned(tg) == [77]
    assert tg.of("banChatMember")[0]["until_date"] > logic.core.now() + 89 * 86400  # as long as the record: Telegram lifts it
    assert not tg.of("sendMessage")

    tg.calls.clear()  # as another channel: deleted, that channel banned; as the forum channel (its admins): stays
    hear(cfg, tg, {"message": msg(15, 136817688, sender_chat={"id": -100999, "type": "channel"})},
         {"message": msg(16, 136817688, sender_chat={"id": -100555, "type": "channel"})})
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [15]}]
    assert tg.of("banChatSenderChat") == [{"chat_id": G, "sender_chat_id": -100999}]

    tg.calls.clear()  # banned in the app: banned here too, no warning
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 20")
    hear(cfg, tg, {"message": msg(17, 20)})
    assert banned(tg) == [20] and not tg.of("sendMessage")
    con.execute("UPDATE users SET banned_at = NULL WHERE tg_id = 20")

    tg.calls.clear()  # a raid: 6 strangers within a minute; the sixth and on are banned silently, the owner hears once
    hear(cfg, tg, *[{"message": msg(30 + i, 300 + i)} for i in range(8)])
    assert len(tg.of("sendMessage")) == 4 and {b["user_id"] for b in tg.of("banChatMember")} == {304, 305, 306, 307}
    assert len(outbox(con, "tgc_raid")) == 1

    # the warnings go after their minute, in the bot's round (kept in the database: a restart doesn't leave them up)
    tg.calls.clear()
    tick(cfg, tg, con)
    assert not tg.of("deleteMessages")
    set_clock(monkeypatch, lambda: int(__import__("time").time()) + 61)
    tick(cfg, tg, con)
    assert len(tg.of("deleteMessages")[0]["message_ids"]) == 5  # the first warning and the raid's four before it began

    tg.calls.clear()  # the banned stranger signs in with Microsoft: unbanned in the group
    login(c, 77, "newbie")
    tick(cfg, tg, con)
    assert tg.of("unbanChatMember") == [{"chat_id": G, "user_id": 77, "only_if_banned": True}]


def test_saved_text_for_its_author_only(env, monkeypatch):
    """The stranger's deleted text, by his Telegram account alone: someone else tapping the same public button sees
    nothing (the same answer as for no text). As a guest he sees it without the way back to the thread; signed in as a
    student, once, with it. Kept an hour: every read checks it, the bot's round wipes it."""
    c, cfg, con, _ = setup(env, monkeypatch)
    tg = Telegram()
    hear(cfg, tg, COPY, {"message": msg(12, 77, "my words")})
    assert c.get("/api/me", headers=tma(77)).json().get("tgComment") is True
    assert "tgComment" not in c.get("/api/me", headers=tma(78)).json()
    assert c.post("/api/me/tg-comment", headers=tma(78)).json() is None          # another account: nothing
    guest = c.post("/api/me/tg-comment", headers=tma(77)).json()
    assert guest == {"body": "my words", "link": None, "student": False}         # not a student: no way back (a ban)
    login(c, 77, "newbie")
    me = c.post("/api/me/tg-comment", headers=tma(77)).json()
    assert me == {"body": "my words", "link": "https://t.me/KBTUforum/42?comment=12", "student": True}
    assert c.post("/api/me/tg-comment", headers=tma(77)).json() is None          # once

    hear(cfg, tg, {"message": msg(13, 79, "later words")})
    real = logic.core.now
    set_clock(monkeypatch, lambda: real() + 3601)
    assert c.post("/api/me/tg-comment", headers=tma(79)).json() is None          # past the hour, even before the wipe
    assert con.execute("SELECT COUNT(*) FROM tgc_saved").fetchone()[0] == 1
    tick(cfg, tg, con)
    assert con.execute("SELECT COUNT(*) FROM tgc_saved").fetchone()[0] == 0


def test_reports_ai_gate_and_moderators(env, monkeypatch):
    """/report: the command goes at once, the reporter hears in DM. Two distinct verified reporters (over two weeks) and
    the AI's violation: deleted, its author gets his words, and it waits as "removed" for a moderator (first in the
    queue), who restores it: the author hears, the reporters were wrong, the same text posted again is never deleted
    automatically. The AI's clean: never deleted, queued, the moderators' digest. A fresh account doesn't count."""
    c, cfg, con, looked = setup(env, monkeypatch, {"bad words": False, "fine words": True})
    author = student(c, con, 20, "ali")
    r1, r2 = student(c, con, 21, "bek"), student(c, con, 22, "dan")
    fresh = student(c, con, 23, "erk", old=False)
    mod = student(c, con, 24, "mod")
    con.execute("UPDATE users SET role = 'moderator', can_dm = 1 WHERE id = ?", (mod,))
    con.execute("UPDATE users SET can_dm = 1")
    tg = Telegram()
    bad, fine = msg(50, 20, "bad words"), msg(51, 20, "fine words")
    hear(cfg, tg, COPY, report(60, 21, bad), report(61, 21, bad))                # the same reporter twice: one report
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [60, 61]}]
    assert [x[0] for x in outbox(con, "tgc_report_ok")] == [r1] and looked == ["bad words"]
    assert con.execute("SELECT status FROM tgc_comments").fetchone()[0] == "queued"  # a violation, one reporter: a moderator
    hear(cfg, tg, report(62, 23, bad))                                           # a fresh account: counted, no deletion
    assert con.execute("SELECT status FROM tgc_comments").fetchone()[0] == "queued"
    hear(cfg, tg, report(63, 22, bad), report(64, 20, bad))                      # his own comment: ignored
    cid, status, review = con.execute("SELECT id, status, review FROM tgc_comments").fetchone()
    assert (status, review) == ("deleting", 1) and outbox(con, "tgc_removed") == [(author, f"tr:{cid}")]
    assert con.execute("SELECT COUNT(*) FROM tgc_reports WHERE outcome IS NOT NULL").fetchone()[0] == 0  # only a person decides
    tg.calls.clear()
    tick(cfg, tg, con)
    assert tg.of("deleteMessage") == [{"chat_id": G, "message_id": 50}]
    assert con.execute("SELECT status FROM tgc_comments").fetchone()[0] == "deleted"
    m = bot._render(con, {"kind": "tgc_removed", "ref": f"tr:{cid}", "lang": "en", "user_id": author})
    assert m[0].endswith("\n\nbad words")                                        # his own words, to him alone

    hear(cfg, tg, report(65, 21, fine), report(66, 22, fine), report(67, 23, fine))  # the AI: clean; three reports
    fid = con.execute("SELECT id FROM tgc_comments WHERE msg_id = 51").fetchone()[0]
    assert con.execute("SELECT status FROM tgc_comments WHERE id = ?", (fid,)).fetchone()[0] == "queued"
    assert (mod, f"ta:{fid}") in outbox(con, "tgc_queue")                     # three at once: the moderators now
    tick(cfg, tg, con)
    assert any(ref.startswith("tq:") for _, ref in outbox(con, "tgc_queue"))   # and the hourly digest

    q = [x for x in c.get("/api/admin/reports", headers=tma(24)).json() if x["target"] == "tgc"]
    assert [(x["id"], x["removed"]) for x in q] == [(cid, True), (fid, False)]  # the removed one first
    assert q[0]["reporters"] and all("name" not in r for r in q[0]["reporters"])  # accuracy and age, never who
    assert c.post(f"/api/admin/reports/tgc/{cid}", headers=tma(21), json={"remove": False}).status_code == 403  # a reporter: no
    assert c.post(f"/api/admin/reports/tgc/{cid}", headers=tma(24), json={"remove": False}).status_code == 204  # restored
    assert con.execute("SELECT status FROM tgc_comments WHERE id = ?", (cid,)).fetchone()[0] == "restored"
    assert outbox(con, "tgc_back") == [(author, f"tb:{cid}")]
    assert {r[0] for r in con.execute("SELECT outcome FROM tgc_reports WHERE comment_id = ?", (cid,))} == {"overturned"}
    assert not tg.of("sendMessage")                                              # nothing in the thread

    hear(cfg, tg, report(70, 21, msg(52, 20, "bad words")), report(71, 22, msg(52, 20, "bad words")))  # posted again
    assert con.execute("SELECT status FROM tgc_comments WHERE msg_id = 52").fetchone()[0] == "queued"  # cleared: never auto
    assert c.post(f"/api/admin/reports/tgc/{fid}", headers=tma(24), json={"remove": True}).status_code == 204
    assert con.execute("SELECT status FROM tgc_comments WHERE id = ?", (fid,)).fetchone()[0] == "deleting"
    assert {a for (a,) in con.execute("SELECT action FROM audit_log WHERE target LIKE 'tgc:%'")} >= {"tg_auto_remove", "tg_restore", "tg_confirm"}
    assert fresh


def test_edit_is_judged_again(env, monkeypatch):
    """A comment edited after a report is judged again on its new text: clean when reported, abuse after the edit,
    with one reporter: queued for a moderator (never deleted on one report); one a moderator kept goes back too."""
    c, cfg, con, looked = setup(env, monkeypatch, {"nice": True, "nasty": False})
    student(c, con, 20, "ali")
    student(c, con, 21, "bek")
    tg = Telegram()
    hear(cfg, tg, COPY, report(60, 21, msg(50, 20, "nice")))
    assert con.execute("SELECT status FROM tgc_comments").fetchone()[0] == "open"
    hear(cfg, tg, {"edited_message": msg(50, 20, "nasty")})
    assert looked == ["nice", "nasty"]
    assert con.execute("SELECT status, body FROM tgc_comments").fetchone()[:] == ("queued", "nasty")
    con.execute("UPDATE tgc_comments SET status = 'kept'")
    hear(cfg, tg, {"edited_message": msg(50, 20, "nice")})
    assert con.execute("SELECT status, ai FROM tgc_comments").fetchone()[:] == ("open", "ok")
    hear(cfg, tg, {"edited_message": msg(99, 20, "nasty")})                     # not a reported one: nothing to judge
    assert looked == ["nice", "nasty", "nice"]


def test_abusers_report_closed_by_a_moderator(env, monkeypatch):
    """Only a moderator closes /report, and only for someone already wrong twice: then /report answers with the closed
    template and counts nothing; an admin reopens it."""
    c, cfg, con, _ = setup(env, monkeypatch, {})
    student(c, con, 20, "ali")
    r = student(c, con, 21, "bek")
    mod = student(c, con, 24, "mod")
    adm = student(c, con, 25, "adm")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod,))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (adm,))
    tg = Telegram()
    hear(cfg, tg, COPY, report(60, 21, msg(50, 20, "one")), report(61, 21, msg(51, 20, "two")))
    a, b = [x for (x,) in con.execute("SELECT id FROM tgc_comments ORDER BY id")]
    assert c.post(f"/api/admin/reports/tgc/{a}", headers=tma(24), json={"abuse": True}).status_code == 204
    assert not con.execute("SELECT 1 FROM tgc_closed").fetchone()                # wrong once: not yet
    assert c.post(f"/api/admin/reports/tgc/{b}", headers=tma(24), json={"abuse": True}).status_code == 204
    assert con.execute("SELECT user_id FROM tgc_closed").fetchone()[0] == r
    hear(cfg, tg, report(62, 21, msg(52, 20, "three")))
    assert not con.execute("SELECT 1 FROM tgc_comments WHERE msg_id = 52").fetchone()
    assert len(outbox(con, "tgc_closed")) == 1 and tg.of("deleteMessages")[-1]["message_ids"] == [62]
    assert [x["person"]["id"] for x in c.get("/api/admin/tgc-closed", headers=tma(25)).json()] == [r]
    assert c.get("/api/admin/tgc-closed", headers=tma(24)).status_code == 403     # the admin's switch, not a moderator's
    assert c.delete(f"/api/admin/tgc-closed/{r}", headers=tma(25)).status_code == 204
    hear(cfg, tg, report(63, 21, msg(52, 20, "three")))
    assert con.execute("SELECT 1 FROM tgc_comments WHERE msg_id = 52").fetchone()


def test_account_deletion_takes_it_all(env, monkeypatch):
    """Deleting an account takes its comments' copies, its reports, a closed /report, and what its Telegram id left
    before it signed in (a saved text, a warning)."""
    c, cfg, con, _ = setup(env, monkeypatch, {})
    student(c, con, 20, "ali")
    student(c, con, 21, "bek")
    tg = Telegram()
    hear(cfg, tg, COPY, {"message": msg(40, 22, "before I signed in")}, report(60, 21, msg(50, 20, "x")), report(61, 20, msg(51, 21, "y")))
    login(c, 22, "cem")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 21").fetchone()[0]
    con.execute("INSERT INTO tgc_closed (user_id, at) VALUES (?, 0)", (uid,))
    for who in (21, 22):
        delete_now(c, cfg, tma(who))
    assert con.execute("SELECT COUNT(*) FROM tgc_comments WHERE author_tg = 21").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM tgc_reports WHERE reporter_id = ?", (uid,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM tgc_closed").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM tgc_saved WHERE tg_id = 22").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM tgc_strangers WHERE tg_id = 22").fetchone()[0] == 0


def test_policy_section_and_consent_only_with_the_switch(env, monkeypatch):
    """With the group set: a new consent version and the policy's section, numbered after the forums'; without: neither."""
    c0, cfg0 = env
    off = c0.get("/api/me", headers=tma(20)).json()["consentNow"]
    assert "+tgc" not in off and "{{tgcn}}" not in c0.get("/privacy").text and "/report" not in c0.get("/privacy?lang=en").text
    c, *_ = setup(env, monkeypatch)
    assert c.get("/api/me", headers=tma(20)).json()["consentNow"] == off + logic.CONSENT_TGC
    page = c.get("/privacy?lang=en").text
    assert "11. Comments in the forum's Telegram channel" in page and "{{tgcn}}" not in page


def test_review_fixes(env, monkeypatch):
    """The code review's cases: no channel ban before the forum channel is known; a stranger's edit isn't his second
    comment; one message that breaks doesn't stop the batch's deletions; an app-banned student's group ban lifts with
    the app's unban; the AI looks once per text, and a reporter's day of fresh looks is capped (the reports aren't)."""
    c, cfg, con, looked = setup(env, monkeypatch, {"rude": False, "rude again": False})
    tg = Telegram()
    hear(cfg, tg, {"message": msg(5, 136817688, sender_chat={"id": -100555, "type": "channel"})})  # before any post's copy
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [5]}] and not tg.of("banChatSenderChat")

    tg.calls.clear()  # a stranger's comment and its edit in one batch: one warning, no ban
    hear(cfg, tg, COPY, {"message": msg(12, 77, "hi")}, {"edited_message": msg(12, 77, "hi!")})
    assert len(tg.of("sendMessage")) == 1 and not tg.of("banChatMember")
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [12, 12]}]

    tg.calls.clear()  # one message breaks (a locked database): the others' deletions and warnings still go
    real = tgc.rules.stranger

    def flaky(con_, tg_id, body, link):
        if tg_id == 88:
            raise logic.ApiError("busy")
        return real(con_, tg_id, body, link)
    monkeypatch.setattr(tgc.rules, "stranger", flaky)
    hear(cfg, tg, {"message": msg(20, 88)}, {"message": msg(21, 89)})
    assert tg.of("deleteMessages") == [{"chat_id": G, "message_ids": [20, 21]}] and len(tg.of("sendMessage")) == 1
    monkeypatch.setattr(tgc.rules, "stranger", real)

    student(c, con, 30, "ali")  # banned in the app: banned in the group, on record; the app's unban lifts both
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 30")
    tg.calls.clear()
    hear(cfg, tg, {"message": msg(31, 30)})
    assert banned(tg) == [30]
    con.execute("UPDATE users SET banned_at = NULL WHERE tg_id = 30")
    tick(cfg, tg, con)
    assert [b["user_id"] for b in tg.of("unbanChatMember")] == [30]

    student(c, con, 40, "bek")  # the AI looks once per text: three reports, one look; the same words edited in: none
    for tg_id, name in ((41, "cem"), (42, "dan"), (43, "erk")):
        student(c, con, tg_id, name)
    hear(cfg, tg, report(50, 41, msg(45, 40, "rude")), report(51, 42, msg(45, 40, "rude")), report(52, 43, msg(45, 40, "rude")))
    assert looked == ["rude"]
    hear(cfg, tg, {"edited_message": msg(45, 40, "rude")})
    assert looked == ["rude"]
    monkeypatch.setattr(tgc.rules, "AI_LOOKS", 0)  # the day's looks used up: the report counts, no new look, a moderator
    hear(cfg, tg, report(53, 41, msg(46, 40, "rude again")))
    assert looked == ["rude"]
    assert con.execute("SELECT COUNT(*) FROM tgc_reports r JOIN tgc_comments x ON x.id = r.comment_id WHERE x.msg_id = 46").fetchone()[0] == 1


def test_switched_off_changes_nothing(env):
    """Without TG_COMMENTS_CHAT: no edits asked of Telegram, the round does nothing of this feature."""
    _, cfg = env
    asked = []

    def telegram(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params.get("allowed_updates"))
        return httpx.Response(200, json={"ok": True, "result": []})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.hear(cfg, http, 0)
    asyncio.run(go())
    assert "edited_message" not in asked[0] and "message" in asked[0]
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO tgc_saved (tg_id, body, at) VALUES (1, 'x', 0)")
    tick(cfg, Telegram(), con)
    assert con.execute("SELECT COUNT(*) FROM tgc_saved").fetchone()[0] == 1


def postman(cfg, handler) -> None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())


class NoEdits(Telegram):
    """Telegram refusing every edit (the message too old, or deleted by its reader)."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/editMessageText"):
            self.calls.append(("editMessageText", json.loads(request.content)))
            return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "message to edit not found"})
        return super().__call__(request)


def test_verdict_edits_the_first_message(env, monkeypatch):
    """Removed after reports: its author gets "under review" with his words; the moderator's verdict edits that same
    message (the rule picked from the report reasons, the AI's guess by default), the undo list's restore edits it
    again. Telegram refusing the edit: a new message. The bot blocked: the app's card says it instead."""
    c, cfg, con, _ = setup(env, monkeypatch, {"bad words": False, "more bad": False, "bad words!": False})
    student(c, con, 20, "ali")
    student(c, con, 21, "bek")
    student(c, con, 22, "dan")
    mod = student(c, con, 24, "mod")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod,))
    con.execute("UPDATE users SET can_dm = 1, lang = 'en'")
    tg = Telegram()
    hear(cfg, tg, COPY, report(60, 21, msg(50, 20, "bad words")), report(61, 22, msg(50, 20, "bad words")))
    cid, rule = con.execute("SELECT id, rule FROM tgc_comments").fetchone()
    assert rule == "insult"                                                      # the AI's guess, the moderator's default
    tg.calls.clear()
    postman(cfg, tg)
    first = [b for b in tg.of("sendMessage") if b["chat_id"] == 20]
    assert len(first) == 1 and "under a moderator's review" in first[0]["text"] and first[0]["text"].endswith("bad words")
    dm = con.execute("SELECT dm_id FROM tgc_comments WHERE id = ?", (cid,)).fetchone()[0]
    assert dm

    q = c.get("/api/admin/reports", headers=tma(24)).json()
    assert [x["rule"] for x in q if x["target"] == "tgc"] == ["insult"]
    assert c.post(f"/api/admin/reports/tgc/{cid}", headers=tma(24), json={"remove": True, "rule": "nope"}).status_code == 400
    assert c.post(f"/api/admin/reports/tgc/{cid}", headers=tma(24), json={"remove": True, "rule": "spam"}).status_code == 204
    tg.calls.clear()
    postman(cfg, tg)
    ed = tg.of("editMessageText")
    assert len(ed) == 1 and ed[0]["chat_id"] == 20 and ed[0]["message_id"] == dm
    assert "no spam or ads" in ed[0]["text"] and ed[0]["text"].endswith("bad words")
    assert not [b for b in tg.of("sendMessage") if b["chat_id"] == 20]          # edited, not a second message

    assert c.post(f"/api/admin/taken-down/tgc/{cid}/restore", headers=tma(24)).status_code == 204  # the undo list
    tg.calls.clear()
    postman(cfg, tg)
    ed = tg.of("editMessageText")
    assert len(ed) == 1 and ed[0]["message_id"] == dm and "by mistake" in ed[0]["text"]

    # Telegram refuses the edit (too old, deleted by him): the verdict goes as a new message
    hear(cfg, tg, report(62, 21, msg(51, 20, "more bad")), report(63, 22, msg(51, 20, "more bad")))
    postman(cfg, tg)
    c2 = con.execute("SELECT id FROM tgc_comments WHERE msg_id = 51").fetchone()[0]
    assert con.execute("SELECT dm_id FROM tgc_comments WHERE id = ?", (c2,)).fetchone()[0]
    assert c.post(f"/api/admin/reports/tgc/{c2}", headers=tma(24), json={"remove": True}).status_code == 204
    refuse = NoEdits()
    postman(cfg, refuse)
    assert len(refuse.of("editMessageText")) == 1
    new = [b for b in refuse.of("sendMessage") if b["chat_id"] == 20]
    assert len(new) == 1 and "no insults" in new[0]["text"] and new[0]["text"].endswith("more bad")

    # the bot blocked: no message gets through; the app's card says what became of it
    hear(cfg, tg, report(64, 21, msg(52, 20, "bad words!")), report(65, 22, msg(52, 20, "bad words!")))
    c3 = con.execute("SELECT id FROM tgc_comments WHERE msg_id = 52").fetchone()[0]
    con.execute("UPDATE users SET can_dm = 0 WHERE tg_id = 20")
    assert c.get("/api/me", headers=tma(20)).json().get("tgComment") is True
    assert c.post("/api/me/tg-comment", headers=tma(20)).json()["verdict"] == "pending"
    assert c.post(f"/api/admin/reports/tgc/{c3}", headers=tma(24), json={"remove": True, "rule": "danger"}).status_code == 204
    card = c.post("/api/me/tg-comment", headers=tma(20)).json()
    assert card == {"body": "bad words!", "link": None, "student": True, "removed": True, "verdict": "confirmed", "rule": "danger"}
    assert c.post("/api/me/tg-comment", headers=tma(20)).json() is None         # once per news
