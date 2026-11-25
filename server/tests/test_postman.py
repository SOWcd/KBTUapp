"""The postman sends side by side under Telegram's cap: a fake Telegram that answers slowly counts what overlaps."""
import asyncio
import json
import time

import httpx
import pytest

from kbtu import bot, db, texts
from test_core import env  # noqa: F401  (env: the fixture)

URL = "https://t.me/example_channel/42"
LATENCY = 0.15  # each fake answer takes this long: one at a time would be ~7 a second


@pytest.fixture
def queue(env, monkeypatch):
    """40 people with one broadcast each, and person 1 with three (queued in this order)."""
    _, cfg = env
    monkeypatch.setattr(bot, "_chores", lambda *_: None)
    con = db.connect(cfg.db_path)
    try:
        for tg in range(1, 41):
            con.execute("INSERT INTO users (tg_id, lang, can_dm, role, created_at, seen_at) VALUES (?, 'en', 1, 'user', 0, 0)", (tg,))
        uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
        put = "INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, 'app_broadcast', ?, ?, 0)"
        for ref in ("app_home", "acoustic", "research_launch"):
            con.execute(put, (uid(1), ref, json.dumps({"url": URL})))
        for tg in range(2, 41):
            con.execute(put, (uid(tg), "app_home", json.dumps({"url": URL})))
        yield con, cfg
    finally:
        con.close()


class Telegram:
    """sendMessage answered after LATENCY; what started when, and how many were in flight at most."""

    def __init__(self, answer=None):
        self.starts: list[tuple[float, int, str]] = []
        self.busy: dict[int, int] = {}
        self.flying = self.most = 0
        self.answer = answer or (lambda n, body: httpx.Response(200, json={"ok": True, "result": {"message_id": n}}))

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sendMessage")
        body = json.loads(request.content)
        chat = body["chat_id"]
        self.starts.append((time.monotonic(), chat, body["text"]))
        n = len(self.starts)
        assert not self.busy.get(chat), "two messages to one chat at once"
        self.busy[chat] = 1
        self.flying += 1
        self.most = max(self.most, self.flying)
        try:
            await asyncio.sleep(LATENCY)
            return self.answer(n, body)
        finally:
            self.flying -= 1
            self.busy[chat] = 0


def _round(cfg, tg: Telegram) -> None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())


def _state(con) -> dict[str, int]:
    return dict(con.execute("""SELECT CASE WHEN sent_at IS NOT NULL THEN 'sent' WHEN error IS NOT NULL THEN 'error'
        WHEN send_after > 0 THEN 'taken' ELSE 'queued' END, COUNT(*) FROM bot_outbox GROUP BY 1""").fetchall())


def test_side_by_side_under_the_cap(queue):
    con, cfg = queue
    tg = Telegram()
    began = time.monotonic()
    _round(cfg, tg)
    took = time.monotonic() - began
    assert _state(con) == {"sent": 42}
    assert sorted(c for _, c, _ in tg.starts) == sorted([1, 1, 1, *range(2, 41)])  # each once
    assert 1 < tg.most <= bot.SENDERS  # side by side, not one at a time
    starts = [t for t, _, _ in tg.starts]
    assert all(b - a >= 1 for a, b in zip(starts, starts[30:]))  # never Telegram's 30 in a second (25 planned: room for the database's turns)
    assert took < 42 * LATENCY / 2  # far faster than one at a time
    first = [text for _, c, text in tg.starts if c == 1]  # person 1's three: in the queue's order, never together (Telegram asserts)
    assert first == [texts.bot_message("en", ref)[0] for ref in ("app_home", "acoustic", "research_launch")]


def test_429_stops_everyone_and_nothing_goes_twice(queue, monkeypatch):
    con, cfg = queue
    told = []

    def answer(n, body):
        if n == 5:
            told.append(time.monotonic())
            return httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 1}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": n}})
    tg = Telegram(answer)
    began = time.monotonic()
    _round(cfg, tg)
    assert time.monotonic() - began >= 1 and len(tg.starts) < 42  # waited as told, and the round ended there
    st = _state(con)
    assert st["sent"] == len(tg.starts) - 1 and st["taken"] == 1 and "error" not in st  # the refused one waits its LEASE
    assert st["queued"] == 42 - len(tg.starts)  # the rest untouched

    refused = con.execute("SELECT id FROM bot_outbox WHERE sent_at IS NULL AND send_after > 0").fetchone()[0]
    con.execute("UPDATE bot_outbox SET send_after = 0 WHERE id = ?", (refused,))  # its LEASE is over
    again = Telegram()
    _round(cfg, again)
    assert _state(con) == {"sent": 42}
    delivered = [c for _, c, _ in tg.starts[:4] + tg.starts[5:]] + [c for _, c, _ in again.starts]
    assert sorted(delivered) == sorted([1, 1, 1, *range(2, 41)])  # every row sent exactly once in all


def test_network_down_leaves_the_rest_queued(queue):
    con, cfg = queue

    def answer(n, body):
        if n == 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": n}})
    tg = Telegram(answer)
    _round(cfg, tg)
    st = _state(con)
    assert st["sent"] == len(tg.starts) - 1 and st["taken"] == 1 and st["queued"] == 42 - len(tg.starts)
    assert len(tg.starts) < 42
