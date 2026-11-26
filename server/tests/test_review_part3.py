"""Inkar's review #404: failed channel joins and deliveries must not hold up unrelated work."""
import asyncio
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace as NS

import httpx
import pytest
from telethon.errors import ChannelPrivateError, FloodWaitError, InviteRequestSentError, UsernameInvalidError
from telethon.tl.types import Channel

from kbtu import apns, bot_groups, db, logic, mirror, outbox, userbot
from kbtu.logic import apple
from helpers import env  # noqa: F401
from test_apple import DEVICE, _dead, _queue, _sent, both, phone  # noqa: F401
from test_postman import Telegram, _round, _state, queue  # noqa: F401
from test_web_auth import WEB, WRITE, widget

APNS_SEND = apns.send


@pytest.mark.parametrize("where,error", [("resolve", UsernameInvalidError), ("resolve", ChannelPrivateError),
                                         ("join", ChannelPrivateError), ("join", InviteRequestSentError)])
def test_join_rpc_error_skips_the_channel_for_a_day(env, monkeypatch, where, error):
    _, cfg = env
    clock, sleeps, resolved, joined = [100000], [], [], []
    monkeypatch.setattr(userbot.time, "time", lambda: clock[0])
    monkeypatch.setattr(mirror, "to_leave", lambda _: [])
    monkeypatch.setattr(mirror, "to_join", lambda _: [n for n in ("blocked", "good") if n not in joined])
    monkeypatch.setattr(mirror, "joined", lambda con, cid, name: joined.append(name))

    class Client:
        async def iter_dialogs(self):
            for d in ():
                yield d

        async def get_entity(self, name):
            resolved.append(name)
            if name == "blocked" and where == "resolve":
                raise error(None)
            return Channel(id=1, title=name, photo=None, date=None, broadcast=True)

        async def __call__(self, request):
            if request.channel.title == "blocked":
                raise error(None)

    async def nothing(*_):
        pass

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            clock[0] += 86401
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    work = userbot.Mirror(cfg, Client(), None)
    monkeypatch.setattr(work, "mute", nothing)
    monkeypatch.setattr(work, "first", nothing)
    monkeypatch.setattr(userbot.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(work.joins())
    assert joined == ["good"] and resolved == ["blocked", "good", "blocked"]
    assert sleeps == [userbot.JOIN_GAP] * 3


def test_join_flood_wait_keeps_telegram_backoff(env, monkeypatch):
    _, cfg = env
    sleeps, resolved = [], []
    monkeypatch.setattr(mirror, "to_leave", lambda _: [])
    monkeypatch.setattr(mirror, "to_join", lambda _: ["flooded", "later"])

    class Client:
        async def iter_dialogs(self):
            for d in ():
                yield d

        async def get_entity(self, name):
            resolved.append(name)
            raise FloodWaitError(None, capture=12)

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(userbot.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(userbot.Mirror(cfg, Client(), None).joins())
    assert sleeps == [17, userbot.JOIN_GAP, 17] and resolved == ["flooded", "flooded"]


def test_slow_pushes_leave_other_pushes_and_telegram_free(both, monkeypatch):
    c, cfg, uid, _, _ = both
    other = "cd" * 32
    c2 = type(c)(c.app, base_url=str(c.base_url))
    assert c2.post("/api/web/login", headers=WRITE, json=widget(716)).status_code == 204
    uid2 = c2.get("/api/me", headers=WEB).json()["id"]
    assert c2.post("/api/me/devices", headers=WRITE, json={"token": other, "consent": apple.CONSENT}).status_code == 204
    with closing(db.connect(cfg.db_path)) as con:
        con.execute("UPDATE users SET can_dm = 1 WHERE id = ?", (uid2,))
        uid3 = con.execute("INSERT INTO users (tg_id, lang, can_dm, created_at, seen_at) VALUES (717, 'en', 1, 0, 0)").lastrowid
    for user, ref in ((uid, "first"), (uid, "next"), (uid2, "other"), (uid3, "telegram")):
        _queue(cfg, user, ref)
    async def go():
        release, telegram_done = asyncio.Event(), asyncio.Event()
        started = {token: asyncio.Event() for token in (DEVICE, other)}
        active, pushed, sent = set(), [], []

        async def send(cfg, token, text, start):
            assert token not in active, "one person's messages must stay in order"
            active.add(token)
            pushed.append(token)
            started[token].set()
            try:
                await release.wait()
                if token == other:
                    return "gone"
                return "down" if pushed.count(token) == 1 else "ok"
            finally:
                active.remove(token)

        async def telegram(request):
            chat = json.loads(request.content)["chat_id"]
            sent.append((chat, time.monotonic()))
            if chat == 717:
                telegram_done.set()
            return httpx.Response(200, json={"ok": True, "result": {}})

        monkeypatch.setattr(apns, "send", send)
        with closing(db.connect(cfg.db_path)) as con:
            async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
                task = asyncio.create_task(outbox._batch(cfg, http, con, outbox._due(con)))
                try:
                    await asyncio.wait_for(asyncio.gather(*(e.wait() for e in started.values()), telegram_done.wait()), 2)
                    assert pushed == [DEVICE, other]
                finally:
                    release.set()
                    await task
        assert pushed == [DEVICE, other, DEVICE]
        assert sent[0][0] == 717 and sorted(chat for chat, _ in sent[1:]) == [715, 716]
        assert sent[2][1] - sent[1][1] >= outbox.GAP - 0.005  # simultaneous APNs failures still use Telegram's pace

    asyncio.run(go())
    assert all(_sent(cfg, ref) == (1, None) for ref in ("first", "next", "other", "telegram"))
    assert _dead(cfg) == [False]  # only the rejected token was removed


def test_render_error_retires_only_its_row(queue, monkeypatch, caplog):
    con, cfg = queue
    bad = con.execute("SELECT id FROM bot_outbox WHERE user_id = (SELECT id FROM users WHERE tg_id = 2)").fetchone()[0]
    render = outbox._render

    def broken(con, m):
        if m["id"] == bad:
            raise ValueError("private payload must not enter logs")
        return render(con, m)

    monkeypatch.setattr(outbox, "_render", broken)
    tg = Telegram()
    _round(cfg, tg)
    assert _state(con) == {"error": 1, "sent": 41}
    assert con.execute("SELECT error FROM bot_outbox WHERE id = ?", (bad,)).fetchone()[0] == "render: ValueError"
    assert len(tg.starts) == 41 and all(chat != 2 for _, chat, _ in tg.starts)
    con.execute("UPDATE bot_outbox SET send_after = 0")
    _round(cfg, tg)
    assert len(tg.starts) == 41  # neither the bad row nor a cancelled in-flight send returns after its lease
    assert "private payload" not in caplog.text


@pytest.mark.parametrize("grouped", [None, 99])
def test_closed_stories_advance_without_downloading(env, grouped):
    _, cfg = env
    downloads = []

    class Client:
        async def download_media(self, m, kind):
            downloads.append(m.id)

    with closing(db.connect(cfg.db_path)) as con:
        con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Mic', 'M', 'laptop_3d', 0, 0)")
        con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Mic', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
        mirror.joined(con, 500, "mic_news")
        work = userbot.Mirror(cfg, Client(), con)
        msg = NS(peer_id=NS(channel_id=500), action=None, message="", grouped_id=grouped, date=datetime.now(UTC),
                 photo=True, video=None, gif=None, video_note=None, media=True, views=1, reactions=None)
        for mid in (8, 3, 8):
            msg.id = mid
            asyncio.run(work.post(msg))
        assert mirror.last(con, 500) == 8 and downloads == []
        assert not con.execute("SELECT 1 FROM posts").fetchone()
        assert not con.execute("SELECT 1 FROM tg_post_msgs").fetchone()
        con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
        msg.id = 9
        asyncio.run(work.post(msg))
        assert mirror.last(con, 500) == 9 and downloads == [9]
        assert con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1


@pytest.mark.parametrize("status,reason,gone", [(400, "BadTopic", False), (400, "TopicDisallowed", False),
    (400, "MissingTopic", False), (413, "PayloadTooLarge", False), (429, "TooManyRequests", False),
    (403, "InvalidProviderToken", False), (503, "ServiceUnavailable", False), (502, None, False),
    (400, "BadDeviceToken", True), (400, "DeviceTokenNotForTopic", True), (410, "Unregistered", True), (410, "", True)])
def test_apns_only_token_errors_retire_devices(both, monkeypatch, status, reason, gone):
    _, cfg, uid, _, _ = both
    _queue(cfg, uid, "apns-error")
    monkeypatch.setattr(apns, "send", APNS_SEND)
    monkeypatch.setattr(apns, "_bearer", lambda _: "test")
    telegram = []

    async def go():
        response = httpx.Response(status, json={"reason": reason} if reason is not None else [])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as apple_http:
            monkeypatch.setattr(apns, "_http", apple_http)

            def tg(request):
                telegram.append(json.loads(request.content)["chat_id"])
                return httpx.Response(200, json={"ok": True, "result": {}})

            with closing(db.connect(cfg.db_path)) as con:
                async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
                    await outbox._batch(cfg, http, con, outbox._due(con))

    asyncio.run(go())
    assert telegram == [715] and _sent(cfg, "apns-error") == (1, None)
    assert _dead(cfg) == ([] if gone else [False])


@pytest.mark.parametrize("failure", ["dialogs", "running"])
def test_userbot_reconnect_closes_resources_after_tasks(env, monkeypatch, failure):
    import telethon
    from telethon import sessions
    _, cfg = env
    connections, clients, drained, closed = [], [], [], []
    connect = db.connect

    def open_db(path):
        con = connect(path)
        connections.append(con)
        return con

    class Client:
        def __init__(self, *args, **kwargs):
            clients.append(self)
            self.work = None

        async def connect(self):
            pass

        async def is_user_authorized(self):
            return len(clients) <= 2

        async def get_me(self):
            return NS(id=123)

        async def get_dialogs(self):
            if failure == "dialogs":
                raise RuntimeError("reconnect before Mirror exists")

        async def run_until_disconnected(self):
            await asyncio.sleep(0)
            raise RuntimeError("reconnect with work in flight")

        async def disconnect(self):
            if self.work:
                # A handler can start one final detached task before disconnect settles it.
                self.work.looks.add(asyncio.create_task(self.work.wait()))
                await asyncio.sleep(0)

    class Work:
        def __init__(self, cfg, client, con, me):
            client.work = self
            self.con, self.looks, self.http = con, set(), self

        def listen(self):
            pass

        async def wait(self):
            try:
                await asyncio.Event().wait()
            finally:
                self.con.execute("SELECT 1")  # work must settle while its shared connection is open
                drained.append(self)

        joins = sweeps = catch_up = wait

        async def aclose(self):
            assert all(t.done() for t in self.looks)
            assert drained.count(self) == 4
            closed.append(self)

    monkeypatch.setattr(telethon, "TelegramClient", Client)
    monkeypatch.setattr(sessions, "StringSession", lambda _: None)
    monkeypatch.setattr(userbot, "Mirror", Work)
    monkeypatch.setattr(userbot, "RETRY", 0)
    monkeypatch.setattr(db, "connect", open_db)
    asyncio.run(userbot.run(replace(cfg, tg_api_id="1", tg_api_hash="test", tg_session="test")))
    assert len(clients) == 3 and len(connections) == 2
    assert len(closed) == (2 if failure == "running" else 0)
    for con in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")


def test_group_migration_rolls_back_on_a_write_failure(env, monkeypatch):
    _, cfg = env
    monkeypatch.setattr(bot_groups, "_moved", {})
    with closing(db.connect(cfg.db_path)) as con:
        oid = logic.create_org(con, None, "Test", "T", "laptop_3d", True)
        con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, tg_chat_id) VALUES ('Test', 'group', 'https://t.me/test_group', 0, 'org', ?, -100)", (oid,))
        con.execute("INSERT INTO chat_seen (chat_id, tg_id, org_id, seen_at) VALUES (-100, 800, ?, 1)", (oid,))
        con.execute("CREATE TEMP TRIGGER move_fail BEFORE UPDATE OF tg_chat_id ON chats BEGIN SELECT RAISE(ABORT, 'move failed'); END")
        with pytest.raises(sqlite3.IntegrityError):
            asyncio.run(bot_groups._group(cfg, None, con, {"chat": {"id": -100}, "migrate_to_chat_id": -1009}))
        assert [tuple(r) for r in con.execute("SELECT chat_id, tg_id FROM chat_seen")] == [(-100, 800)]
        assert not bot_groups._moved


@pytest.mark.parametrize("balance", ["inf", "Infinity", "-inf", "NaN", "1e999", "1e307"])
def test_nonfinite_import_balance_is_reported(balance):
    from kbtu.logic import vol
    from test_vol import FIO, HRS, _xlsx
    plan = vol.plan(_xlsx({HRS: [[FIO, "Total"], ["Test Person", balance]]}), balance="Total")
    assert plan["people"][0]["balance"] == 0
    assert any("isn't a number of hours" in problem for problem in plan["problems"])
