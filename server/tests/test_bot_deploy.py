"""A deploy restarts the bot (SIGTERM to the old process, then a new one): Telegram updates are neither lost nor handled
twice, a stop drains what is under way, a crash leaves at most the one update it was in (bot.stop, bot._save, bot._resume)."""
from __future__ import annotations

import asyncio
import dataclasses
import fcntl
import json
import threading
import time

import httpx
import pytest

from kbtu import app as server
from kbtu import bot, db, outbox, receipt, texts, tgc
from fastapi.testclient import TestClient
from test_core import env, tma  # noqa: F401  (env: the fixture)
from test_review_seats import _paid, _shot, _status


@pytest.fixture(autouse=True)
def _memory(monkeypatch):
    """Whatever a process keeps in memory, restored after each test (each 'process' below starts it empty)."""
    for name, value in (("_stop", None), ("_stop_by", float("inf")), ("_replay", None), ("_video_seen", set())):
        monkeypatch.setattr(bot, name, value)


def _hi(uid: int, chat: int) -> dict:
    return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": chat, "type": "private"},
                                          "from": {"id": chat, "language_code": "en"}, "date": int(time.time()), "text": "hi"}}


class Telegram:
    """The Bot API as the bot sees it: getUpdates hands out what is at or past the offset and forgets (confirms) what is
    before it; with nothing left a long poll is where SIGTERM finds an idle bot. `hook(method, body)` runs before a
    call is answered: it may stop the process (bot.stop) or kill it (cancel its task)."""

    def __init__(self, updates: list[dict], hook=None):
        self.updates, self.hook, self.polls, self.calls, self.task = updates, hook, [], [], None

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        if method == "getUpdates":
            off = int(request.url.params["offset"])
            self.updates = [u for u in self.updates if u["update_id"] >= off]
            if request.url.params.get("timeout") != "0":
                self.polls.append(off)
                if not self.updates:
                    bot.stop()
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        if method == "getFile":
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "R"}})
        if "/file/" in request.url.path:
            return httpx.Response(200, content=_shot())
        body = json.loads(request.content)
        if self.hook:
            await self.hook(self, method, body)
        self.calls.append((method, body))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 900}})

    def said(self, method: str = "sendMessage") -> list:
        return [b.get("chat_id") for m, b in self.calls if m == method]

    def kill(self) -> None:
        """The process dies here (SIGKILL, OOM, the deadline): its task cancelled at this very await."""
        self.task.cancel()


async def _ears(cfg, tg: Telegram) -> None:
    """One process's ears: from what it finds stored to its stop or its death. Its memory starts empty."""
    bot._stop, bot._stop_by, bot._replay, bot._video_seen = asyncio.Event(), float("inf"), None, set()
    async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
        tg.task = asyncio.create_task(bot._ears(cfg, http))
        try:
            await asyncio.wait_for(tg.task, 10)
        except asyncio.CancelledError:
            pass
        await tgc.settle()  # what it spawned (run() drains them the same way)


def _state(cfg) -> dict:
    con = db.connect(cfg.db_path)
    try:
        return json.loads(con.execute("SELECT value FROM meta WHERE key = 'bot_offset'").fetchone()[0])
    finally:
        con.close()


def test_stop_mid_batch_then_restart(env):
    """SIGTERM while the second of five messages is answered: that one finishes, the old process stops at the next
    update, and the new one starts there. Each person is answered exactly once."""
    _, cfg = env

    async def sigterm(tg, method, body):
        if body.get("chat_id") == 11:
            bot.stop()
    tg = Telegram([_hi(100 + i, 10 + i) for i in range(5)], sigterm)
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10, 11]
    assert _state(cfg)["next"] == 102 and "busy" not in _state(cfg)
    tg.hook = None
    asyncio.run(_ears(cfg, tg))                       # the next process
    assert tg.polls[-2] == 102                       # resumed where the last one stopped
    assert tg.said() == [10, 11, 12, 13, 14]         # nobody lost, nobody twice


def test_crash_mid_update_skips_only_what_may_not_run_twice(env):
    """The process dies inside a button tap (it may have decided an offer, taken a receipt): the next one doesn't run
    that tap again (the button, if untouched, is tapped again), and nothing before it either; what follows is handled."""
    _, cfg = env

    async def die(tg, method, body):
        if method == "answerCallbackQuery":
            tg.kill()
            await asyncio.sleep(0)
    tap = {"update_id": 101, "callback_query": {"id": "q", "from": {"id": 11}, "data": "an:y",
                                                "message": {"message_id": 5, "chat": {"id": 11, "type": "private"}}}}
    tg = Telegram([_hi(100, 10), tap, _hi(102, 12)], die)
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10] and _state(cfg)["next"] == 101 and _state(cfg)["busy"]
    tg.hook = None
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10, 12] and tg.said("answerCallbackQuery") == []


def test_crash_while_answering_sends_the_answer_once(env):
    """Dead while the answer was on its way (the work behind it done): the next process sends that answer, once, and
    doesn't do the work again."""
    _, cfg = env

    async def die(tg, method, body):
        if body.get("chat_id") == 10:
            tg.kill()
            await asyncio.sleep(0)
    tg = Telegram([_hi(100, 10), _hi(101, 11)], die)
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == []
    tg.hook = None
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10, 11] and tg.polls[-2] == 101
    asyncio.run(_ears(cfg, Telegram([])))             # and never a third time
    assert "reply" not in _state(cfg)


def test_sigterm_during_a_receipt(env, monkeypatch):
    """SIGTERM while a receipt's OCR runs: the receipt is taken and answered before the old process lets go; the new one
    neither takes it again nor loses the message behind it."""
    c, cfg = env
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    loop = []

    def read(im):  # OCR runs in a thread; the signal reaches the event loop
        loop[0].call_soon_threadsafe(bot.stop)
        time.sleep(0.1)
        return {"amount": 2000}
    monkeypatch.setattr(receipt, "read", read)
    doc = {"update_id": 100, "message": {"message_id": 1, "chat": {"id": 10, "type": "private"}, "from": {"id": 10}, "date": int(time.time()),
                                         "document": {"file_id": "R", "mime_type": "image/png", "file_size": 900}}}
    tg = Telegram([doc, _hi(101, 11)])

    async def first():
        loop.append(asyncio.get_running_loop())
        await _ears(cfg, tg)
    asyncio.run(first())
    assert _status(c, eid, 10) == "going" and tg.said() == [10] and _state(cfg)["next"] == 101
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10, 11] and con.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1


@pytest.mark.parametrize("where", ["ocr", "answer", "tap", "edit"])
def test_crash_during_a_receipt(env, monkeypatch, where):
    """Dead in the middle of a receipt: during its OCR (nothing written: taken by the next process), while its answer
    was on its way (taken already: the next process sends the answer, never "no seat on hold"), or during the OCR of a
    receipt picked by its button (the one tap that runs again: losing it would cost the seat), or while that pick's answer
    was on its way (run again, it finds the ticket taken and says so). One receipt, one ticket, one answer, and it says
    the ticket is there."""
    c, cfg = env
    con, eid = _paid(c, cfg)
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    doc = {"message_id": 1, "chat": {"id": 10, "type": "private"}, "from": {"id": 10}, "date": int(time.time()),
           "document": {"file_id": "R", "mime_type": "image/png", "file_size": 900}}
    tap = where in ("tap", "edit")
    tg = Telegram([{"update_id": 100, "callback_query": {"id": "q", "from": {"id": 10}, "data": f"rc:{eid}", "message": {
        "message_id": 2, "chat": {"id": 10, "type": "private"}, "reply_to_message": doc}}} if tap else {"update_id": 100, "message": doc}])
    loop = []

    def read(im):
        if where in ("ocr", "tap") and loop:
            loop[0].call_soon_threadsafe(tg.kill)
            time.sleep(0.2)  # the cancel lands at the await while the thread is still reading
        return {"amount": 2000}
    monkeypatch.setattr(receipt, "read", read)

    async def die(tg, method, body):
        if where == "answer" and method == "sendMessage" or where == "edit" and method == "editMessageText":
            tg.kill()
            await asyncio.sleep(0)

    async def first():
        loop.append(asyncio.get_running_loop())
        await _ears(cfg, tg)
    tg.hook = die
    asyncio.run(first())
    assert tg.said() == [] and _status(c, eid, 10) == ("hold" if where in ("ocr", "tap") else "going")
    loop.clear()
    tg.hook = None
    asyncio.run(_ears(cfg, tg))
    assert _status(c, eid, 10) == "going" and con.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
    said = [b["text"] for m, b in tg.calls if m == ("editMessageText" if tap else "sendMessage")]
    assert len(said) == 1 and "<b>Gala</b>" in said[0] and said[0] != texts.bot_message("ru", "receipt_none")[0]  # the ticket's answer


def test_group_video_not_sent_twice(env, monkeypatch):
    """A group video started just before the stop: the batch comes again to the next process, the video doesn't."""
    _, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    videos = []

    async def video(cfg_, http, msg, url, started):
        videos.append(msg["message_id"])
    monkeypatch.setattr(bot, "_group_video", video)

    def link(msg):
        bot.stop()  # SIGTERM right as the batch came in
        return "https://www.tiktok.com/@a/video/1" if "vid" in str(msg.get("text")) else None
    monkeypatch.setattr(bot.tiktok, "link", link)
    grp = {"update_id": 100, "message": {"message_id": 7, "chat": {"id": -100, "type": "supergroup"}, "from": {"id": 10},
                                         "date": int(time.time()), "text": "vid"}}
    tg = Telegram([grp, _hi(101, 11)])
    asyncio.run(_ears(cfg, tg))
    assert videos == [7] and tg.said() == [] and _state(cfg)["next"] == 100
    monkeypatch.setattr(bot.tiktok, "link", lambda msg: "https://www.tiktok.com/@a/video/1" if "vid" in str(msg.get("text")) else None)
    asyncio.run(_ears(cfg, tg))
    assert videos == [7] and tg.said() == [11]


def test_a_busy_database_at_the_stop_sends_no_answer_twice(env):
    """The batch's last write skipped (another writer held the database over a second, e.g. the nightly chores): the
    stop writes once more, waiting longer, so the next process doesn't send the last answer again."""
    _, cfg = env
    other = db.connect(cfg.db_path)

    async def hook(tg, method, body):
        if body.get("chat_id") == 10:
            other.execute("BEGIN IMMEDIATE")
            threading.Timer(1.5, other.execute, ("ROLLBACK",)).start()
            bot.stop()
    tg = Telegram([_hi(100, 10)], hook)
    asyncio.run(_ears(cfg, tg))
    assert "reply" not in _state(cfg)
    tg.hook = None
    asyncio.run(_ears(cfg, tg))
    assert tg.said() == [10]


def test_no_new_group_video_while_stopping(env, monkeypatch):
    """A video link that arrives while the old process finishes its last update (the checkout watcher's peeks): not
    started there, where the drain would cut it and the next process would skip it as started; the next process sends it."""
    _, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    monkeypatch.setattr(bot, "PEEK", 0.05)
    sent = []

    async def video(cfg_, http, msg, url, started):
        sent.append(msg["message_id"])
    monkeypatch.setattr(bot, "_group_video", video)
    monkeypatch.setattr(bot.tiktok, "link", lambda m: "https://www.tiktok.com/@a/video/1" if "vid" in str(m.get("text")) else None)
    grp = {"update_id": 101, "message": {"message_id": 7, "chat": {"id": -100, "type": "supergroup"}, "from": {"id": 10},
                                         "date": int(time.time()), "text": "vid"}}

    async def slow(tg, method, body):
        if body.get("chat_id") == 10 and grp not in tg.updates:
            bot.stop()
            tg.updates.append(grp)  # posted while the old process drains
            await asyncio.sleep(0.3)  # the update under way takes a moment: the watcher peeks
    tg = Telegram([_hi(100, 10)], slow)
    asyncio.run(_ears(cfg, tg))
    assert sent == [] and _state(cfg)["next"] == 101
    tg.hook = None
    asyncio.run(_ears(cfg, tg))
    assert sent == [7]


def test_stop_ends_the_long_poll_at_once(env):
    """SIGTERM while Telegram holds the long poll (an idle bot): the poll ends now, not in 25 s, and the offset stays."""
    _, cfg = env

    async def hold(request):
        await asyncio.sleep(30)

    async def go():
        bot._stop = asyncio.Event()
        asyncio.get_running_loop().call_later(0.1, bot.stop)
        async with httpx.AsyncClient(transport=httpx.MockTransport(hold)) as http:
            return await bot.hear(cfg, http, 7)
    t = time.monotonic()
    assert asyncio.run(go()) == 7 and time.monotonic() - t < 2


def test_resume_trusts_only_a_fresh_offset_of_this_bot(env, monkeypatch):
    """A stored offset older than a day (Telegram may pick random ids after a week of silence), from the future (the
    clock jumped back), another bot's, or unreadable: not trusted, Telegram's own confirmation decides (offset 0)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    me = cfg.bot_token.split(":")[0]

    def put(**s):
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('bot_offset', ?)", (json.dumps(s),))
        return bot._resume(cfg, con)
    t = int(time.time())
    assert put(bot=me, next=50, at=t - 60) == (50, None) and bot._replay is None
    assert put(bot=me, next=50, at=t - 60, busy=1) == (50, None) and bot._replay == 50
    assert put(bot=me, next=50, at=t - 2 * 86400)[0] == 0
    assert put(bot=me, next=50, at=t + 3600)[0] == 0
    assert put(bot="999", next=50, at=t - 60)[0] == 0
    assert put(bot=me, next="50", at=t - 60)[0] == 0
    con.execute("UPDATE meta SET value = '{' WHERE key = 'bot_offset'")
    assert bot._resume(cfg, con) == (0, None)
    reply = {"chat_id": 10, "text": "x"}
    assert put(bot=me, next=50, at=t - 10, reply=reply) == (50, reply)
    assert bot._resume(cfg, con) == (50, None)                         # handed out once
    assert put(bot=me, next=50, at=t - bot.FRESH - 10, reply=reply) == (50, None)  # stale: not sent at all


def test_run_drains_then_lets_go(env, monkeypatch):
    """stop(): the ears and the postman end by themselves, the loops that start over anyway are cancelled, spawned jobs
    finish until the deadline (a swear warning due in a minute is deleted now, as no process would be left to), a job
    past it is cancelled; only then is the lock let go, well inside Docker's grace."""
    _, cfg = env
    cfg = dataclasses.replace(cfg, chat_sync=False)
    monkeypatch.setattr(bot, "DRAIN", 0.5)
    calls, seen = [], {}

    def telegram(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json={"ok": True, "result": []})
    real = httpx.AsyncClient
    monkeypatch.setattr(bot.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))

    async def nothing(*_a):
        return None

    async def quick():
        await asyncio.sleep(0.05)
        seen["quick"] = "done"

    async def slow():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            seen["slow"] = "cut"
            raise

    async def ears(cfg_, http):
        tgc.spawn(quick(), None)
        tgc.spawn(slow(), None)
        tgc.spawn(bot._unsay(cfg_, http, -100, 5), None)
        seen["ears"] = "up"
        while not bot._stopping():
            await bot._nap(30)
        seen["ears"] = "ended"

    def forever(name):
        async def child(*_a):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                seen[name] = "cancelled"
                raise
        return child
    monkeypatch.setattr(bot, "load_pack", nothing)
    monkeypatch.setattr(bot, "_commands", nothing)
    monkeypatch.setattr(bot.receipt, "ready", lambda: True)
    monkeypatch.setattr(outbox, "send_due", nothing)
    monkeypatch.setattr(bot, "_ears", ears)
    for name in ("_videos", "_translator", "_userbot"):
        monkeypatch.setattr(bot, name, forever(name))

    async def main():
        task = asyncio.create_task(bot.run(cfg))
        while seen.get("ears") != "up":
            await asyncio.sleep(0.01)
        t = time.monotonic()
        bot.stop()
        await asyncio.wait_for(task, 5)
        return time.monotonic() - t
    took = asyncio.run(main())
    assert took < 2 and bot._stop is None
    assert seen == {"ears": "ended", "quick": "done", "slow": "cut", "_videos": "cancelled", "_translator": "cancelled", "_userbot": "cancelled"}
    assert calls == ["deleteMessage"]
    with open(f"{cfg.db_path}.bot.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)  # let go


def test_shutdown_stops_the_bot_instead_of_cancelling_it(env, monkeypatch):
    """The lifespan's shutdown asks the bot to stop and waits for it; a cancel is only the fallback."""
    _, cfg = env
    seen = []

    async def run(cfg_):
        bot._stop = asyncio.Event()
        try:
            await bot._stop.wait()
            seen.append("stopped")
        except asyncio.CancelledError:
            seen.append("cancelled")
            raise
    monkeypatch.setattr(bot, "run", run)
    with TestClient(server.create(dataclasses.replace(cfg, background=True))) as c:
        assert c.get("/healthz").status_code == 200
    assert seen == ["stopped"]
