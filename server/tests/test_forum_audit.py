"""Forum audit regressions: privacy, erasure, stale decisions and atomic limits. CI only."""
from __future__ import annotations

import asyncio
import dataclasses
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

import httpx
import pytest
from fastapi.testclient import TestClient

from kbtu import ai, app as server, bot, db, logic, tgc
from test_core import env, login, set_clock, tma  # noqa: F401
from test_fchan_replies import Tg, gate, note, sent_reply, world
from test_fchannel import G
from test_review_moderation import _club_event
from test_tgcomments import setup, student, tick

F, T = logic.fchannel, logic.tgcomments


def test_named_visits_are_owner_only(env):
    c, cfg = env
    owner, admin, author = [login(c, i, name)["id"] for i, name in ((1, "owner"), (2, "admin"), (3, "author"))]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE id IN (?, ?)", (owner, admin))
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (owner,))
    day = logic.day_of(logic.now())
    public = c.get(f"/api/admin/stats/{day}", headers=tma(2)).json()
    private = c.get(f"/api/admin/stats/{day}", headers=tma(1)).json()
    assert public["people"] is None and public["active"] == private["active"]
    assert author in {p["id"] for p in private["people"]}
    con.close()


@pytest.mark.parametrize("purge", ["sweep", "hidden", "account", "inflight"])
def test_reply_cleanup_survives_parent_erasure(env, monkeypatch, purge):
    w = world(env, monkeypatch)
    now = logic.now()
    set_clock(monkeypatch, lambda: now)
    if purge == "inflight":
        rid, _ = F.reply_reserve(w.con, logic.Viewer(w.ann["id"], "user", True), w.pid, {"body": "An answer on its way"})
        F.reply_settle(w.con, logic.Viewer(w.ann["id"], "user", True), w.pid, rid, "ok")
        assert F.reply_sending(w.con, rid)
        mid = 999
    else:
        rid, mid = sent_reply(w, None)
    w.con.execute("UPDATE fchan_posts SET created_at = ? WHERE id = ?", (now - 31 * 86400, w.pid))
    if purge in ("hidden", "account"):
        F.mod_decide(w.con, logic.Viewer(w.bob["id"], "moderator", True), w.pid, False)
    else:
        F.delete(w.con, logic.Viewer(w.ann["id"], "user", True), w.pid)
    if purge == "account":
        logic.delete_me(w.con, logic.Viewer(w.ann["id"], "user", True))
    else:
        F.sweep(w.con)
    assert not w.con.execute("SELECT 1 FROM fchan_replies WHERE id = ?", (rid,)).fetchone()
    if purge == "inflight":
        F.reply_sent(w.con, rid, mid)
    w.tg.calls.clear()
    w.tg.say["deleteMessage"] = (400, "Bad Request: message can't be deleted")
    w.tg.say["editMessageText"] = (500, "try later")

    async def cleanup():
        async with httpx.AsyncClient(transport=httpx.MockTransport(w.tg)) as http:
            await tgc._replies(w.cfg, http, w.con)

    asyncio.run(cleanup())
    assert {"chat_id": G, "message_id": mid} in w.tg.of("deleteMessage")
    assert w.tg.of("editMessageText")[-1]["message_id"] == mid
    set_clock(monkeypatch, lambda: now + 601)
    assert any(r[1] == mid for r in F.reply_drops(w.con))  # a failed edit remains retryable
    del w.tg.say["editMessageText"]
    asyncio.run(cleanup())
    assert not F.reply_drops(w.con)
    w.con.close()


def test_parent_deletion_erases_hidden_reply_text(env, monkeypatch):
    w = world(env, monkeypatch)
    rid, mid = sent_reply(w, None)
    mod = logic.Viewer(w.bob["id"], "moderator", True)
    F.reply_mod_decide(w.con, mod, rid, False)
    w.con.execute("UPDATE fchan_replies SET ai_reason = 'Old private explanation' WHERE id = ?", (rid,))
    F.delete(w.con, logic.Viewer(w.ann["id"], "user", True), w.pid)
    assert tuple(w.con.execute("SELECT body, ai_reason, status FROM fchan_replies WHERE id = ?", (rid,)).fetchone()) == ("", None, "gone")
    assert w.c.get(f"/api/forum-posts/{w.pid}/replies", headers=tma(1)).status_code == 404
    assert not any(F.mod_queue(w.con, mod)["replies"].values())
    assert any(r[1] == mid for r in F.reply_drops(w.con))
    w.con.close()


def test_closed_reporter_cannot_report_anonymous_reply(env, monkeypatch):
    w = world(env, monkeypatch)
    rid, mid = sent_reply(w, None)
    w.con.execute("INSERT INTO tgc_closed (user_id, at) VALUES (?, ?)", (w.bob["id"], logic.now()))
    gate(w.cfg, w.tg, w.con, note(80, 2, to=mid, bot=True, text="/report"))
    assert not w.con.execute("SELECT 1 FROM fchan_reply_reports WHERE reply_id = ?", (rid,)).fetchone()
    assert w.con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'tgc_closed'", (w.bob["id"],)).fetchone()
    w.con.close()


@pytest.mark.parametrize("kind", ["report", "comment"])
def test_concurrent_writes_share_last_quota_slot(env, monkeypatch, kind):
    c, cfg = env
    uid, a, b = [login(c, i, name)["id"] for i, name in ((1, "reporter"), (2, "ann"), (3, "bob"))]
    con = db.connect(cfg.db_path)
    v = logic.Viewer(uid, "user", True)
    if kind == "report":
        limit, table = logic.moderation.REPORTS_A_DAY, "reports"
        con.executemany("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'user', ?, 'spam', ?)",
                        [(uid, i + 1000, logic.now()) for i in range(limit - 1)])
    else:
        limit, table = logic.moderation.COMMENTS_A_MINUTE, "comments"
        _club_event(con, a)
        con.executemany("INSERT INTO comments (event_id, user_id, body, created_at) VALUES (1, ?, 'Earlier comment', ?)",
                        [(uid, logic.now()) for _ in range(limit - 1)])
    barrier = Barrier(2)
    one = logic.moderation.one

    def counted(conn, sql, *args):
        row = one(conn, sql, *args)
        if sql.startswith(f"SELECT COUNT(*) FROM {table} WHERE"):
            try:
                barrier.wait(timeout=2)  # unprotected readers both see the last free slot
            except BrokenBarrierError:  # a transaction keeps the other reader outside until commit
                pass
        return row

    monkeypatch.setattr(logic.moderation, "one", counted)

    def write(target):
        other = db.connect(cfg.db_path)
        try:
            if kind == "report":
                logic.moderation.report(other, v, "user", target, "spam")
            else:
                logic.moderation.add_comment(other, v, "event", 1, "Another comment", False)
            return "ok"
        except logic.ApiError as exc:
            return exc.code
        finally:
            other.close()

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(write, (a, b))) == ["ok", "rate_limited"]
    assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == limit
    con.close()


def test_forum_screening_is_reserved_before_ai(env, monkeypatch):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    uid = login(c, 1, "mod")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (uid,))
    now = logic.now()
    set_clock(monkeypatch, lambda: now)
    calls = []

    async def screen(*args, **kw):
        calls.append(args[2])
        return False

    monkeypatch.setattr(ai, "screen", screen)
    ask = {"kind": "help", "title": "Study help", "body": "Help with calculus", "days": 1}
    assert c.post("/api/forum/asks", headers=tma(1), json={**ask, "title": "x"}).status_code == 400
    assert not calls
    for _ in range(logic.forum.OPEN_ASKS):
        assert c.post("/api/forum/asks", headers=tma(1), json=ask).status_code == 200
    assert c.post("/api/forum/asks", headers=tma(1), json=ask).status_code == 429
    assert len(calls) == logic.forum.OPEN_ASKS
    # Rejected skill names consume the remaining screening budget without creating catalog rows.
    for _ in range(logic.forum.SCREENS_AN_HOUR - len(calls)):
        assert c.post("/api/forum/skills", headers=tma(1), json={"name": "campus photo walks", "force": True}).status_code == 400
    assert c.post("/api/forum/skills", headers=tma(1), json={"name": "campus photo walks", "force": True}).status_code == 429
    assert len(calls) == logic.forum.SCREENS_AN_HOUR
    con.close()


def test_duplicate_ask_report_does_not_repeat_ai(env, monkeypatch):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    people = [login(c, i, f"person{i}")["id"] for i in range(1, 6)]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator', created_at = 0")
    ask = logic.create_ask(con, logic.Viewer(people[0], "moderator", True), {"kind": "help", "title": "Study together"}, True)
    calls = []

    async def screen(*args, **kw):
        calls.append(args[2])
        return True

    monkeypatch.setattr(ai, "screen", screen)
    for tg in (2, 3, 4, 4, 5):
        assert c.post("/api/reports", headers=tma(tg), json={"target": "ask", "id": ask["id"], "reason": "spam"}).status_code == 204
    assert len(calls) == 1
    con.close()


def test_comment_ids_and_author_notices_survive_retention(env, monkeypatch):
    c, cfg, con, _ = setup(env, monkeypatch)
    ann, bob, reporter = [student(c, con, i, name) for i, name in ((1, "ann"), (2, "bob"), (3, "reporter"))]
    con.execute("INSERT INTO tgc_comments (id, chat_id, msg_id, author_tg, body, created_at) VALUES (10, ?, 49, 1, 'Legacy row', 0)", (G,))
    T.sweep(con)
    _, old = T.report(con, 3, G, 50, 1, "Ann's words", None)
    assert old > 10
    logic.notify(con, ann, "tgc_back", f"tb:{old}")
    logic.notify(con, reporter, "tgc_report_ok", "rr:999")
    con.execute("UPDATE tgc_comments SET created_at = 0")
    now = logic.now()
    set_clock(monkeypatch, lambda: now + 300)
    T.sweep(con)
    _, new = T.report(con, 3, G, 51, 2, "Bob's words", None)
    assert new > old
    with pytest.raises(logic.ApiError, match="not_found"):
        T.resolve(con, logic.Viewer(reporter, "moderator", True), old, "remove")
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE ref = ?", (f"tb:{old}",)).fetchone()
    assert con.execute("SELECT 1 FROM bot_outbox WHERE ref = 'rr:999'").fetchone()
    con.execute("UPDATE tgc_comments SET status = 'restored', dm_id = 77 WHERE id = ?", (new,))
    wrong = {"kind": "tgc_back", "ref": f"tb:{new}", "user_id": ann}
    assert tgc.render(con, wrong, "en") is None
    assert asyncio.run(tgc.edit_first(cfg, None, con, wrong, {})) is None
    tgc.sent(con, wrong, {"result": {"message_id": 88}})
    assert con.execute("SELECT dm_id FROM tgc_comments WHERE id = ?", (new,)).fetchone()[0] == 77
    assert "Bob&#x27;s words" in tgc.render(con, {**wrong, "user_id": bob}, "en")[0]
    con.close()


def test_stale_ai_verdict_cannot_remove_edited_comment(env, monkeypatch):
    c, cfg, con, _ = setup(env, monkeypatch)
    for i, name in ((1, "author"), (2, "ann"), (3, "bob")):
        student(c, con, i, name)
    for tg in (2, 3):
        _, cid = T.report(con, tg, G, 50, 1, "Old text", None)

    async def screen(*args, **kw):
        T.edited(con, G, 50, "Corrected text")
        return False, "abuse"

    monkeypatch.setattr(ai, "screen_comment", screen)
    asyncio.run(tgc._judge(cfg, None, cid))
    assert tuple(con.execute("SELECT status, body, ai_hash FROM tgc_comments WHERE id = ?", (cid,)).fetchone()) == ("open", "Corrected text", None)
    assert T.judge(con, cid, True, body="Corrected text") == "queue"
    assert T.looked(con, cid) == (True, None)
    assert not T.to_delete(con)
    con.close()


@pytest.mark.parametrize("reverify", [False, True])
def test_erasure_rejects_stale_post_and_processed_upload(env, monkeypatch, reverify):
    c, cfg = env
    uid = login(c, 1, "ann")["id"]
    con = db.connect(cfg.db_path)
    v = server._viewer_user(con, con.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    logic.delete_me(con, v)
    if reverify:
        set_clock(monkeypatch, lambda: v.student_since + 1)
        login(c, 1, "ann")
    with pytest.raises(logic.ApiError, match="need_student"):
        F.reserve(con, v, {"body": "Words from before erasure", "anon": True})
    with pytest.raises(logic.ApiError, match="need_student"):
        F.photo_room(con, v)
    with pytest.raises(logic.ApiError, match="need_student"):
        F.add_photo(con, v, {"path": "processed-before-erasure", "width": 100, "height": 100, "color": ""})
    assert not con.execute("SELECT 1 FROM fchan_posts WHERE user_id = ?", (uid,)).fetchone()
    assert not con.execute("SELECT 1 FROM fchan_photos WHERE user_id = ?", (uid,)).fetchone()
    con.close()


@pytest.mark.parametrize("error", ["message can't be deleted", "chat not found"])
def test_refused_comment_deletion_is_not_announced_as_removed(env, monkeypatch, error):
    c, cfg, con, _ = setup(env, monkeypatch)
    author, reporter, mod = [student(c, con, i, name) for i, name in ((1, "author"), (2, "reporter"), (3, "mod"))]
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod,))
    _, cid = T.report(con, 2, G, 50, 1, "Comment still in Telegram", None)
    T.resolve(con, logic.Viewer(mod, "moderator", True), cid, "remove", "pdata")
    notice = {"kind": "tgc_confirmed", "ref": f"tc:{cid}", "user_id": author}
    assert tgc.render(con, notice, "en") is None  # no success before the API answer
    tg = Tg()
    tg.say["deleteMessage"] = (400, f"Bad Request: {error}")
    tick(cfg, tg, con)
    assert con.execute("SELECT status FROM tgc_comments WHERE id = ?", (cid,)).fetchone()[0] == "queued"
    assert tgc.render(con, notice, "en") is None
    assert T.take_saved(con, logic.Viewer(author, "user", True)) is None
    queue = T.queue_items(con, logic.Viewer(mod, "moderator", True))
    assert any(r["id"] == cid and not r["removed"] for r in queue)
    alert = con.execute("SELECT * FROM bot_outbox WHERE kind = 'tgc_delete_failed' AND user_id = ?", (mod,)).fetchone()
    assert alert and "manually in Telegram" in tgc.render(con, alert, "en")[0]
    con.close()


def test_forum_notifications_do_not_forward_custom_skills(env):
    c, cfg = env
    a, b = [logic.Viewer(login(c, i, name)["id"], "user", True) for i, name in ((1, "ann"), (2, "bob"))]
    con = db.connect(cfg.db_path)
    skill = logic.add_skill(con, a, "campus photo walks")
    for v in (a, b):
        logic.set_my_forum(con, v, {"skills": [skill["id"]], "open": True, "pings": True})
    logic.create_ask(con, a, {"kind": "project", "title": "Photo project", "skills": [skill["id"]]}, True)
    logic.contact(con, a, to=b.id)
    for kind in ("ask_match", "contact_ask"):
        m = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = ?", (kind,)).fetchone())
        for lang in ("ru", "kk", "en"):
            rendered = bot._render(con, {**m, "lang": lang})
            assert rendered and "campus photo walks" not in rendered[0]
    con.close()
