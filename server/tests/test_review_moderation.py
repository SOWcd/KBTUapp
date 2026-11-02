"""Review 2: moderation's undo, a hidden club or event's messages, an owner's ban, the channel group's strangers and
restores. Each test failed before its fix."""
from __future__ import annotations

import time

from kbtu import bot, db
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_tgcomments import COPY, Telegram, banned, hear, msg, report, setup, student, tick

def _club_event(con, pres_id, status="published", start=None):
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres_id,))
    start = start or int(time.time()) + 86400
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, ?, 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (status, start, pres_id))

def test_moderator_restores_own_takedown(env):
    """A moderator can't judge a report about his own comment (resolve_report 403), but can undo another moderator's
    take-down of it himself."""
    c, cfg = env
    pres, m1, m2, ali = login(c, 90, "pres"), login(c, 91, "mone"), login(c, 92, "mtwo"), login(c, 93, "ali")
    con = db.connect(cfg.db_path)
    _club_event(con, pres["id"])
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id IN (91, 92)")
    M1, M2, A = tma(91), tma(92), tma(93)
    cid = c.post("/api/events/1/comments", headers=M1, json={"body": "rude words"}).json()["items"][0]["id"]
    assert c.post("/api/reports", headers=A, json={"target": "comment", "id": cid, "reason": "insult"}).status_code == 204
    assert c.post(f"/api/admin/reports/comment/{cid}", headers=M1, json={"remove": False}).status_code == 403   # control: not his call
    assert c.post(f"/api/admin/reports/comment/{cid}", headers=M2, json={"remove": True}).status_code == 204
    r = c.post(f"/api/admin/taken-down/comment/{cid}/restore", headers=M1)
    assert r.status_code == 403, r.text  # not his own verdict to undo
    assert con.execute("SELECT deleted_at FROM comments WHERE id = ?", (cid,)).fetchone()[0] is not None
    assert c.post(f"/api/admin/taken-down/comment/{cid}/restore", headers=M2).status_code == 204  # another moderator may

def test_moderator_restores_comment_its_author_deleted(env):
    """restore() brings back any deleted comment, not only a moderation take-down: the author's own delete is undone."""
    c, cfg = env
    pres, mod, ali = login(c, 90, "pres"), login(c, 91, "mone"), login(c, 93, "ali")
    con = db.connect(cfg.db_path)
    _club_event(con, pres["id"])
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 91")
    A, M = tma(93), tma(91)
    cid = c.post("/api/events/1/comments", headers=A, json={"body": "my phone is 8701..."}).json()["items"][0]["id"]
    assert c.delete(f"/api/comments/{cid}", headers=A).status_code == 204
    assert c.get("/api/admin/taken-down", headers=M).json() == []                      # not listed: not a take-down
    assert c.post(f"/api/admin/taken-down/comment/{cid}/restore", headers=M).status_code == 404  # the author's delete stays
    assert c.get("/api/events/1/comments", headers=A).json()["items"] == []

def test_restore_after_undo_window(env):
    """The undo list stops at 30 days, restore() doesn't."""
    c, cfg = env
    pres, mod, ali, bob = login(c, 90, "pres"), login(c, 91, "mone"), login(c, 93, "ali"), login(c, 94, "bob")
    con = db.connect(cfg.db_path)
    _club_event(con, pres["id"])
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 91")
    cid = c.post("/api/events/1/comments", headers=tma(93), json={"body": "spam spam"}).json()["items"][0]["id"]
    c.post("/api/reports", headers=tma(94), json={"target": "comment", "id": cid, "reason": "spam"})
    assert c.post(f"/api/admin/reports/comment/{cid}", headers=tma(91), json={"remove": True}).status_code == 204
    con.execute("UPDATE audit_log SET at = at - 40 * 86400"); con.execute("UPDATE comments SET deleted_at = deleted_at - 40 * 86400")
    assert c.get("/api/admin/taken-down", headers=tma(91)).json() == []
    assert c.post(f"/api/admin/taken-down/comment/{cid}/restore", headers=tma(91)).status_code == 404  # past the window

def test_hidden_club_publish_messages_subscribers(env):
    """The admin hid a club ("its events go with it"); its team still publishes, and the bot tells its followers."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 93, "ali")
    con = db.connect(cfg.db_path)
    _club_event(con, pres["id"], status="draft")
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (ali["id"],))
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert c.post("/api/events/1/publish", headers=tma(90)).status_code == 200
    m = con.execute("""SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'new_event'""").fetchone()
    assert m and m["user_id"] == ali["id"]
    assert bot._render(con, m) is None  # no card for an event nobody can open
    assert c.get("/api/events/1", headers=tma(93)).status_code == 404  # while the event itself is gone for him

def test_hidden_event_still_messages(env):
    """A moderator took an event down (hidden_at); its team posts an update, and the bot still tells everyone going."""
    c, cfg = env
    pres, ali, bob, mod = login(c, 90, "pres"), login(c, 93, "ali"), login(c, 94, "bob"), login(c, 91, "mone")
    con = db.connect(cfg.db_path)
    _club_event(con, pres["id"])
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 91")
    assert c.post("/api/events/1/registration", headers=tma(93), json={}).status_code == 200
    c.post("/api/reports", headers=tma(94), json={"target": "event", "id": 1, "reason": "danger"})
    assert c.post("/api/admin/reports/event/1", headers=tma(91), json={"remove": True}).status_code == 204
    assert c.get("/api/events/1", headers=tma(93)).status_code == 404
    assert c.post("/api/events/1/updates", headers=tma(90), json={"body": "come anyway"}).status_code == 200
    m = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'event_update' AND b.user_id = ?",
                    (ali["id"],)).fetchone()
    assert m and bot._render(con, m) is None  # a taken-down event messages nobody
    r = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'remind_2h' AND b.user_id = ?",
                    (ali["id"],)).fetchone()
    assert r is None or bot._render(con, r) is None

def test_plain_admin_unbans_admin_the_owner_banned(env):
    """The ban sets role='user', so the 'another admin is the owner's' guard is gone: a plain admin lifts the owner's ban
    of an admin; with ADMIN_TG_IDS he is admin again on his next request."""
    import dataclasses
    from kbtu import app as server
    from fastapi.testclient import TestClient
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({95}))))
    owner, plain, x = login(c, 90, "owner"), login(c, 91, "plain"), login(c, 95, "xadmin")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 90")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 91")
    assert c.post("/api/admin/ban", headers=tma(91), json={"userId": x["id"], "on": True, "reason": "abuse"}).status_code == 403  # control
    assert c.post("/api/admin/ban", headers=tma(90), json={"userId": x["id"], "on": True, "reason": "abuse"}).status_code == 200
    assert c.post("/api/admin/ban", headers=tma(91), json={"userId": x["id"], "on": False}).status_code == 403  # the owner's to lift
    assert c.get("/api/admin/staff", headers=tma(95)).status_code == 403  # still banned
    assert c.post("/api/admin/ban", headers=tma(90), json={"userId": x["id"], "on": False}).status_code == 200


def test_restore_during_delete(env, monkeypatch):
    c, cfg, con, _ = setup(env, monkeypatch, {"bad words": False})
    author = student(c, con, 20, "ali")
    student(c, con, 21, "bek"); student(c, con, 22, "dan")
    mod = student(c, con, 24, "mod")
    con.execute("UPDATE users SET role = 'moderator', can_dm = 1 WHERE id = ?", (mod,))
    tg = Telegram()
    bad = msg(50, 20, "bad words")
    hear(cfg, tg, COPY, report(60, 21, bad), report(61, 22, bad))
    cid, status = con.execute("SELECT id, status FROM tgc_comments").fetchone()
    assert status == "deleting"

    class Racy(Telegram):
        def __call__(self, request):
            if request.url.path.endswith("/deleteMessage"):  # the moderator's "keep" lands while the call is out
                assert c.post(f"/api/admin/reports/tgc/{cid}", headers=tma(24), json={"remove": False}).status_code == 204
            return super().__call__(request)
    r = Racy()
    tick(cfg, r, con)
    assert r.of("deleteMessage") == [{"chat_id": -100777, "message_id": 50}]           # out of Telegram
    assert con.execute("SELECT status FROM tgc_comments").fetchone()[0] == "restored"  # gone, and known to be
    assert [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'tgc_back'")] == [author]  # his words back


def test_redelivered_comment_no_ban(env, monkeypatch):
    c, cfg, con, _ = setup(env, monkeypatch)
    tg = Telegram()
    hear(cfg, tg, COPY, {"message": msg(12, 77, "one comment")})
    assert banned(tg) == [] and len(tg.of("sendMessage")) == 1
    # the process restarted before the next getUpdates confirmed the offset: Telegram hands the same update again
    tg.calls.clear()
    hear(cfg, tg, {"message": msg(12, 77, "one comment")})
    assert banned(tg) == [] and tg.of("sendMessage") == []  # the same message: no ban, no second warning
    hear(cfg, tg, {"message": msg(13, 77, "and again")})
    assert banned(tg) == [77]                                # a second comment still bans

