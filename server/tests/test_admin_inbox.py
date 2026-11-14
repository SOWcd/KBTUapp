"""Admin → Inbox (review Nov 3): one typed queue by role, its count on the shield, a second decision is a conflict that
names who came first, and the Undo for an event's delete, a club application's refusal, a chat declined or removed."""
from __future__ import annotations

import dataclasses
import json

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_review_moderation import _club_event

GOOD = {"name": "Chess Club", "short": "CH", "description": "We play chess every Friday.", "emoji": "laptop_3d", "cover": 0,
        "links": ["https://tiktok.com/@chess"]}


def _setup(env):
    """An admin (60, from the env list), a moderator (61), a club President (62) with an event, a student (63)."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    ids = {k: login(c, uid, k)["id"] for uid, k in ((60, "boss"), (61, "mod"), (62, "pres"), (63, "ali"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 61")
    _club_event(con, ids["pres"])
    return c, con, ids


def _report(c, con):
    cid = c.post("/api/events/1/comments", headers=tma(63), json={"body": "rude words"}).json()["items"][0]["id"]
    assert c.post("/api/reports", headers=tma(62), json={"target": "comment", "id": cid, "reason": "insult"}).status_code == 204
    return cid


def _chat(con, status="pending", title="Calc chat", url="https://t.me/calc"):
    return con.execute("INSERT INTO chats (title, kind, url, created_at, status) VALUES (?, 'group', ?, 0, ?)", (title, url, status)).lastrowid


def test_inbox_by_role_and_count(env):
    c, con, ids = _setup(env)
    cid = _report(c, con)
    chat = _chat(con)
    app = c.post("/api/club-applications", headers=tma(63), json=GOOD).json()
    con.execute("INSERT INTO map_flaws (user_id, ver, floor, u, v, body, created_at) VALUES (?, 'main', 1, 0.5, 0.5, 'wrong door', 5)", (ids["mod"],))
    adm = c.get("/api/admin/inbox", headers=tma(60)).json()
    mod = c.get("/api/admin/inbox", headers=tma(61)).json()
    assert {x["key"] for x in adm["items"]} == {f"report:comment:{cid}", f"chat:{chat}", f"capp:{app['id']}"}
    assert adm["flaws"] == 1 and mod["flaws"] == 0  # the map's flaws: a quiet count, not a card nor the badge
    assert {x["key"] for x in mod["items"]} == {f"report:comment:{cid}", f"chat:{chat}"}   # clubs and the map are the admin's
    assert c.get("/api/me", headers=tma(60)).json()["counters"]["inbox"] == 3
    assert c.get("/api/me", headers=tma(61)).json()["counters"]["inbox"] == 2
    assert c.get("/api/me", headers=tma(63)).json()["counters"]["inbox"] == 0
    assert c.get("/api/admin/inbox", headers=tma(63)).status_code == 403
    assert [x["key"] for x in adm["items"]][0] == f"chat:{chat}"  # the oldest first


def test_second_decision_names_the_first(env):
    c, con, ids = _setup(env)
    cid = _report(c, con)
    assert c.post(f"/api/admin/reports/comment/{cid}", headers=tma(61), json={"remove": True}).status_code == 204
    r = c.post(f"/api/admin/reports/comment/{cid}", headers=tma(60), json={"remove": False})
    assert r.status_code == 409 and r.json()["message"] == "decided" and r.json()["by"] == "Mod T" and r.json()["action"] == "report_remove"
    assert con.execute("SELECT deleted_at FROM comments WHERE id = ?", (cid,)).fetchone()[0] is not None   # still down
    app = c.post("/api/club-applications", headers=tma(63), json=GOOD).json()
    assert c.post(f"/api/admin/club-applications/{app['id']}", headers=tma(60), json={"approve": False, "reason": "Not now"}).status_code == 200
    r = c.post(f"/api/admin/club-applications/{app['id']}", headers=tma(60), json={"approve": True})
    assert r.status_code == 409 and r.json()["by"] == "Boss T"
    chat = _chat(con)
    assert c.post(f"/api/admin/chats/{chat}/approve", headers=tma(61)).status_code == 200
    assert c.post(f"/api/admin/chats/{chat}/approve", headers=tma(60)).json()["by"] == "Mod T"


def test_undo_refused_application(env):
    c, con, ids = _setup(env)
    app = c.post("/api/club-applications", headers=tma(63), json=GOOD).json()
    assert c.post(f"/api/admin/club-applications/{app['id']}", headers=tma(60), json={"approve": False, "reason": "Not now"}).status_code == 200
    told = con.execute("SELECT send_after FROM bot_outbox WHERE kind = 'club_application_decided'").fetchone()
    assert told[0] > logic.now() + 30  # the refusal waits the Undo's minute
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["done"] if x["action"] == "capp_no")
    assert row["undo"] and row["by"] == "Boss T" and row["text"] == "Chess Club"
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(61)).status_code == 403   # a moderator: not his
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(60)).status_code == 204
    assert c.get("/api/club-applications/mine", headers=tma(63)).json()["application"]["status"] == "pending"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'club_application_decided'").fetchone()   # never told
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(60)).status_code == 409   # undone already
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["done"] if x["action"] == "capp_no")
    assert row["undone"] and not row["undo"]


def test_undo_chat_decline_and_remove(env):
    c, con, ids = _setup(env)
    chat = _chat(con)
    live = _chat(con, "live", "News", "https://t.me/news")
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(61)).status_code == 204
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(60)).status_code == 409   # declined already
    assert c.delete(f"/api/admin/chats/{live}", headers=tma(61)).status_code == 204
    assert not con.execute("SELECT 1 FROM chats WHERE id IN (?, ?)", (chat, live)).fetchone()
    done = {x["action"]: x for x in c.get("/api/admin/inbox", headers=tma(61)).json()["done"]}
    assert done["chat_decline"]["text"] == "Calc chat" and done["chat_remove"]["text"] == "News"
    for a in ("chat_decline", "chat_remove"):
        assert c.post(f"/api/admin/done/{done[a]['id']}/undo", headers=tma(61)).status_code == 204
    assert {r[0]: r[1] for r in con.execute("SELECT id, status FROM chats")} == {chat: "pending", live: "live"}
    # gone for good a week later: nothing left to undo
    assert c.delete(f"/api/admin/chats/{live}", headers=tma(61)).status_code == 204
    k = con.execute("SELECT value FROM meta WHERE key = ?", (f"chatdel:{live}",)).fetchone()[0]
    con.execute("UPDATE meta SET value = ? WHERE key = ?", (json.dumps({**json.loads(k), "at": 0}), f"chatdel:{live}"))
    logic.chats_gone(con)
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(61)).json()["done"] if x["action"] == "chat_remove" and x["undo"])
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(61)).status_code == 404


def test_undo_event_delete(env):
    c, con, ids = _setup(env)
    assert c.delete("/api/admin/events/1", headers=tma(61)).status_code == 403
    assert c.delete("/api/admin/events/1", headers=tma(60)).status_code == 204
    assert c.get("/api/events/1", headers=tma(63)).status_code == 404          # hidden from everyone at once
    assert c.get("/api/admin/orgs/1/events", headers=tma(60)).json() == []
    assert c.delete("/api/admin/events/1", headers=tma(60)).status_code == 409
    assert _undo_event(c, con).status_code == 204                                       # the inbox's undo
    assert c.get("/api/events/1", headers=tma(63)).status_code == 200
    # past its day the bot's round deletes it for good
    assert c.delete("/api/admin/events/1", headers=tma(60)).status_code == 204
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = 'evdel:1'")
    logic.events_gone(con)
    assert not con.execute("SELECT 1 FROM events WHERE id = 1").fetchone() and not con.execute("SELECT 1 FROM meta WHERE key = 'evdel:1'").fetchone()
    assert _undo_event(c, con).status_code == 404


def test_done_undo_takedown_and_people(env):
    c, con, ids = _setup(env)
    cid = _report(c, con)
    assert c.post(f"/api/admin/reports/comment/{cid}", headers=tma(61), json={"remove": True}).status_code == 204
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["done"] if x["action"] == "report_remove")
    assert (row["text"], row["by"], row["mine"], row["undo"]) == ("rude words", "Mod T", False, True)
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(60)).status_code == 204
    assert con.execute("SELECT deleted_at FROM comments WHERE id = ?", (cid,)).fetchone()[0] is None
    # People: one search by name, @username or id
    con.execute("UPDATE users SET tg_username = 'ali_k' WHERE id = ?", (ids["ali"],))
    find = lambda q, h=tma(60): c.get("/api/admin/people", params={"q": q}, headers=h)  # noqa: E731
    assert [p["person"]["id"] for p in find("Ali").json()] == [ids["ali"]]
    assert [p["person"]["id"] for p in find("@ALI_K").json()] == [ids["ali"]]
    assert [p["person"]["id"] for p in find(str(ids["pres"])).json()] == [ids["pres"]]
    assert find("Ali", tma(61)).status_code == 403 and find("a").status_code == 400


# ---- the adversarial review's fixes (Nov 3), one test each

def _undo_event(c, con):
    aid = con.execute("SELECT MAX(id) FROM audit_log WHERE action = 'event_delete'").fetchone()[0]
    return c.post(f"/api/admin/done/{aid}/undo", headers=tma(60))


def _audit(con, actor, action, target, at=None):
    return con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, ?, ?, '{}', ?)",
                       (actor, action, target, at or logic.now())).lastrowid


def _fpost(con, uid, reporter):
    pid = con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at) VALUES (?, 'hello all', 1, 'live', 7, ?)",
                      (uid, logic.now())).lastrowid
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'fpost', ?, 'spam', ?)", (reporter, pid, logic.now()))
    return pid


def test_undo_newest_only_fpost_one_thing_and_window(env):
    """1: a forum post's report take-down is one thing with its fchan line; only the newest decision is undone; old ids refused."""
    c, con, ids = _setup(env)
    pid = _fpost(con, ids["ali"], ids["pres"])
    assert c.post(f"/api/admin/reports/fpost/{pid}", headers=tma(61), json={"remove": True}).status_code == 204
    assert c.post(f"/api/admin/reports/fpost/{pid}", headers=tma(60), json={"remove": True}).status_code == 409   # 5: decided, rolled back
    lines = con.execute("SELECT action, target FROM audit_log WHERE target IN (?, ?)", (f"fpost:{pid}", f"fchan:{pid}")).fetchall()
    assert [tuple(x) for x in lines] == [("fchan_hide", f"fchan:{pid}")]                                       # one decision, one line
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(61)).json()["done"] if x["action"] == "fchan_hide")
    assert row["undo"]
    newer = _audit(con, ids["boss"], "fchan_release", f"fchan:{pid}")
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(61)).status_code == 409                    # decided again since
    con.execute("DELETE FROM audit_log WHERE id = ?", (newer,))
    old = _audit(con, ids["mod"], "chat_remove", "chat:999", logic.now() - 40 * 86400)
    assert c.post(f"/api/admin/done/{old}/undo", headers=tma(61)).status_code == 404                         # past the window
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(61)).status_code == 204


def test_decided_reads_only_decisions_and_roster_rights_first(env):
    """2, 6: a lookup's line never names anyone; a claim's audit keeps the club, not the sheet's name; the rights come first."""
    c, con, ids = _setup(env)
    chat = _chat(con, "live")
    _audit(con, ids["boss"], "pd_lookup", f"chat:{chat}")
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(61)).status_code == 204
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(61)).json()["action"] == "chat_remove"
    con.execute("UPDATE audit_log SET action = 'pd_lookup' WHERE action = 'chat_remove'")
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(61)).json()["by"] is None                         # no decision line: nobody named
    rid = con.execute("""INSERT INTO roster_pending (key, org_id, sheet, role, full_name, claimed_by, created_at)
        VALUES ('k1', 1, 's', 'member', 'Secret Sheetname', ?, 0)""", (ids["ali"],)).lastrowid
    assert c.post(f"/api/roster/requests/{rid}", headers=tma(60), json={"ok": False}).status_code == 403      # the club has a President
    assert c.post(f"/api/roster/requests/{rid}", headers=tma(62), json={"ok": False}).status_code == 204
    assert c.post(f"/api/roster/requests/{rid}", headers=tma(60), json={"ok": True}).status_code == 403       # still not his, decided or not
    assert c.post(f"/api/roster/requests/{rid}", headers=tma(62), json={"ok": True}).status_code == 409
    data = con.execute("SELECT data FROM audit_log WHERE target = ?", (f"roster:{rid}",)).fetchone()[0]
    assert "Secret" not in data and json.loads(data) == {"org": 1}


def test_event_delete_restore_ics_and_cancel_first(env):
    """3, 4, 12: a deleting event can't come back by a report's restore; the round re-hides it; a calendar file of a hidden
    event is gone; one with people still ahead is cancelled first; the old DELETE goes the same way for the admin."""
    c, con, ids = _setup(env)
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T1', 0, 0)", (ids["ali"],))
    r = c.delete("/api/admin/events/1", headers=tma(60))
    assert r.status_code == 409 and r.json()["message"] == "cancel_first"
    assert c.post("/api/events/1/cancel", headers=tma(60)).status_code == 200                               # the admin may cancel
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'event_cancelled'").fetchone()
    assert c.delete("/api/events/1", headers=tma(60)).status_code == 204                                   # the old route: soft, audited
    assert con.execute("SELECT 1 FROM events WHERE id = 1 AND hidden_at IS NOT NULL").fetchone()
    assert con.execute("SELECT 1 FROM audit_log WHERE action = 'event_delete'").fetchone()
    _audit(con, ids["mod"], "report_remove", "event:1")
    assert c.post("/api/admin/taken-down/event/1/restore", headers=tma(61)).status_code == 409
    assert c.get(f"/api/events/1/ics?k={logic.ics_sig(1)}").status_code == 404
    con.execute("UPDATE events SET hidden_at = NULL, status = 'published' WHERE id = 1")
    assert c.get(f"/api/events/1/ics?k={logic.ics_sig(1)}").status_code == 200
    con.execute("UPDATE events SET hidden_at = 5 WHERE id = 1")
    assert c.get(f"/api/events/1/ics?k={logic.ics_sig(1)}").status_code == 404
    con.execute("UPDATE events SET hidden_at = NULL WHERE id = 1")
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = 'evdel:1'")
    seen = []
    real = logic.organizing._delete_event
    logic.organizing._delete_event = lambda con_, eid: (seen.append(con_.execute("SELECT hidden_at FROM events WHERE id = ?", (eid,)).fetchone()[0]), real(con_, eid))[1]
    try:
        logic.events_gone(con)
    finally:
        logic.organizing._delete_event = real
    assert seen and seen[0] is not None                                                                  # hidden again first


def test_undo_rules_chat_snapshot_tgreport_and_old_lines(env):
    """7, 8, 9, 10: the snapshot keeps nobody; a moderator undoes only his own; /report's lines are tgreport:<id>; an
    old line's shape is a 404, never a 500."""
    c, con, ids = _setup(env)
    chat = _chat(con)
    con.execute("UPDATE chats SET added_by = ? WHERE id = ?", (ids["ali"], chat))
    assert c.delete(f"/api/admin/chats/{chat}", headers=tma(60)).status_code == 204
    k = json.loads(con.execute("SELECT value FROM meta WHERE key = ?", (f"chatdel:{chat}",)).fetchone()[0])
    assert k["row"]["added_by"] is None
    row = next(x for x in c.get("/api/admin/inbox", headers=tma(61)).json()["done"] if x["action"] == "chat_decline")
    assert not row["undo"]                                                                               # the admin's, not his
    assert c.post(f"/api/admin/done/{row['id']}/undo", headers=tma(61)).status_code == 403
    old = _audit(con, ids["boss"], "tg_report_close", "user:5")
    assert c.post(f"/api/admin/done/{old}/undo", headers=tma(60)).status_code == 404
    gone = _audit(con, ids["boss"], "tg_report_close", "user")                                           # an account deleted since
    assert c.post(f"/api/admin/done/{gone}/undo", headers=tma(60)).status_code == 404
    con.execute("INSERT INTO tgc_closed (user_id, at, by_id) VALUES (?, 0, ?)", (ids["ali"], ids["boss"]))
    close = _audit(con, ids["boss"], "tg_report_close", f"tgreport:{ids['ali']}")
    assert c.post(f"/api/admin/done/{close}/undo", headers=tma(60)).status_code == 204
    assert con.execute("SELECT target FROM audit_log WHERE action = 'tg_report_open'").fetchone()[0] == f"tgreport:{ids['ali']}"


def test_refusal_message_follows_status_and_inbox_get_writes_nothing(env):
    """11, 13: an undone refusal's message renders nothing; GET inbox leaves the reports as they were; the indexes exist."""
    from kbtu import bot
    c, con, ids = _setup(env)
    app = c.post("/api/club-applications", headers=tma(63), json=GOOD).json()
    c.post(f"/api/admin/club-applications/{app['id']}", headers=tma(60), json={"approve": False, "reason": "Not now"})
    m = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'club_application_decided'").fetchone())
    assert bot._render(con, {**m, "lang": "en"}) is not None
    con.execute("UPDATE club_applications SET status = 'pending' WHERE id = ?", (app["id"],))
    assert bot._render(con, {**m, "lang": "en"}) is None
    cid = _report(c, con)
    con.execute("UPDATE comments SET deleted_at = 1 WHERE id = ?", (cid,))
    c.get("/api/admin/inbox", headers=tma(60))
    assert con.execute("SELECT status FROM reports WHERE target_id = ?", (cid,)).fetchone()[0] == "open"
    logic.close_gone(con)
    assert con.execute("SELECT status FROM reports WHERE target_id = ?", (cid,)).fetchone()[0] == "actioned"
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"audit_by_target", "audit_by_at"} <= names
