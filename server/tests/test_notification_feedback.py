"""The bot and Settings share notification switches, and Admin gets only aggregate counts."""
from __future__ import annotations

import asyncio
import json

import httpx

from kbtu import bot_dm, db, logic, outbox, texts
from kbtu.logic import notifications
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_feedback_from_delivery_to_admin(env, monkeypatch):
    c, cfg = env
    uid = login(c, 10, "ann")["id"]
    admin = login(c, 11, "ben")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET can_dm = 1, lang = 'kk' WHERE id = ?", (uid,))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin,))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    sent_at = logic.now()
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (5, 1, 'published', 'Demo', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (sent_at + 86400,))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (5, ?, 'going', 'T-DEMO', 0, 0)", (uid,))
    monkeypatch.setattr(outbox, "_chores", lambda *_: None)

    messages, edits = [], []
    def telegram(request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        if method == "sendMessage":
            msg = {**body, "chat": {"type": "private", "id": 10}, "message_id": len(messages) + 1, "date": sent_at}
            messages.append(msg)
            return httpx.Response(200, json={"ok": True, "result": msg})
        if method.startswith("editMessage"):
            edits.append((method, body))
        return httpx.Response(200, json={"ok": True})

    async def send():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await outbox.send_due(cfg, http)

    def tap(message, data, who=10):
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
                await bot_dm._tapped(cfg, http, con, {"id": "tap", "from": {"id": who}, "message": message, "data": data})
        asyncio.run(go())

    key = "nBroadcasts"
    settings = lambda: c.get("/api/me", headers=tma(10)).json()["settings"]  # noqa: E731
    con.execute("INSERT INTO posts (id, org_id, title, created_at) VALUES (1, 1, 'News', ?)", (sent_at,))
    logic.notify(con, uid, "broadcast", "post:1")
    asyncio.run(send())
    card, = messages
    app, feedback = card["reply_markup"]["inline_keyboard"]
    assert app[0]["url"].endswith("startapp=news")
    off, = feedback  # an announcement: only "Don't send these", no "Useful" (Nov 23)
    assert off["text"] == texts.bot_message("kk", "feedback_off")[0]
    off = off["callback_data"]
    assert len(off) <= 64

    tap(card, off, who=11)
    assert not edits and settings()[key]
    tap(card, off)
    tap(card, off)
    assert len(edits) == 1 and not settings()[key] and settings()["nRemind"]
    _, muted = edits[-1]
    status, undo_label = texts.bot_message("kk", "feedback_disabled")
    assert muted["text"].endswith(status)
    assert muted["reply_markup"]["inline_keyboard"][0] == app
    undo, = muted["reply_markup"]["inline_keyboard"][1]
    assert undo["text"] == undo_label

    # A ticket's reminder, a rating ask, door and seat alerts: the whole keyboard is their own action.
    logic.notify(con, uid, "remind_2h", f"event:5:{sent_at + 86400}")
    logic.notify(con, uid, "rate", "rate:5")
    logic.notify(con, uid, "door_open", "event:5")
    logic.notify(con, uid, "seat_free", "event:5")
    asyncio.run(send())
    assert len(messages) == 5
    assert all(len(m["reply_markup"]["inline_keyboard"]) == 1 for m in messages[1:])

    tap({**card, **muted}, undo["callback_data"])
    assert settings()[key]
    assert edits[-1][1]["text"].endswith(texts.bot_message("kk", "feedback_enabled")[0])
    # A restart can replay older callbacks with their original keyboards; an old card's "Useful" does nothing.
    bot_dm._feedback_edits.clear()
    count = len(edits)
    tap(card, off.replace("nf:off:", "nf:useful:"))
    assert len(edits) == count
    tap(card, off)
    assert settings()[key]
    assert tuple(logic.one(con, "SELECT sent, turned_off FROM notification_days WHERE category = ?", key)) == (1, 1)
    assert c.get("/api/admin/stats", headers=tma(10)).status_code == 403
    result = c.get("/api/admin/stats", headers=tma(11)).json()["notificationCounts"]
    assert next(r for r in result if r["category"] == key) == {"category": key, "sent": 1, "turnedOff": 1}

    assert c.patch("/api/me", headers=tma(10), json={key: False}).status_code == 200
    con.execute("INSERT INTO posts (id, org_id, title, created_at) VALUES (2, 1, 'More', ?)", (sent_at,))
    logic.notify(con, uid, "broadcast", "post:2")
    asyncio.run(send())
    assert len(messages) == 5
    assert logic.one(con, "SELECT error FROM bot_outbox WHERE kind = 'broadcast' ORDER BY id DESC")[0] == "gone"
    con.close()


def test_preference_undo_respects_subsequent_settings_changes(env):
    c, cfg = env
    login(c, 10, "ann")
    key, now = "nBroadcasts", logic.now()
    con = db.connect(cfg.db_path)
    # A callback can precede the database acknowledgement of the Telegram send.
    assert notifications.switch_from_chat(con, 10, key, False, "first", now) == ("ru", False, True)
    notifications.delivered(con, key, now)
    for on in (True, False):
        assert c.patch("/api/me", headers=tma(10), json={key: on}).json()["settings"][key] == on
    assert notifications.switch_from_chat(con, 10, key, True, "first", now) == ("ru", False, False)
    assert not c.get("/api/me", headers=tma(10)).json()["settings"][key]
    assert tuple(logic.one(con, "SELECT sent, turned_off FROM notification_days")) == (1, 1)
    assert not any(r["sent"] for r in notifications.summary(con, now + 30 * 86400))
    assert not list(con.execute("PRAGMA foreign_key_list(notification_days)"))
    con.close()
