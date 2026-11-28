"""Bot/outbox review: stale chats, ambiguous sends, and comment verdicts bound to their original DM chat."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from kbtu import db, outbox
from helpers import env  # noqa: F401
from test_tgcomments import Telegram


@pytest.fixture
def notice(env, request):
    _, cfg = env
    con = db.connect(cfg.db_path)
    kind = request.param
    try:
        con.executemany("""INSERT INTO users (id, tg_id, lang, can_dm, created_at, seen_at)
            VALUES (?, ?, 'en', 1, 0, 0)""", [(1, 10), (2, 20)])
        con.execute("""INSERT INTO contacts (id, from_id, to_id, status, token, created_at)
            VALUES (1, 1, 2, ?, 'token', 0)""", ("accepted" if kind == "contact_ok" else "pending",))
        con.execute("""INSERT INTO tgc_comments (id, chat_id, msg_id, author_id, author_tg, body, status, review, created_at)
            VALUES (1, -100, 50, 1, 10, 'My own words', ?, ?, 0)""",
                    ("restored" if kind == "tgc_back" else "deleted", int(kind == "tgc_removed")))
        ref = {"contact_ask": "ct:1:token", "contact_ok": "co:1:to:token", "app_broadcast": "app_home"}.get(kind, "tr:1")
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, ?, ?, ?, 0)",
                    (2 if kind == "contact_ask" else 1, kind, ref, json.dumps({"url": "https://t.me/example_channel/42"})))
        yield con, cfg
    finally:
        con.close()


def batch(con, cfg, telegram, due=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await outbox._batch(cfg, http, con, outbox._due(con) if due is None else due)
    return asyncio.run(go())


def state(con):
    return tuple(con.execute("SELECT sent_at IS NOT NULL, error FROM bot_outbox").fetchone())


@pytest.mark.parametrize("notice", ["contact_ask", "contact_ok", "tgc_back", "tgc_report_ok", "app_broadcast"], indirect=True)
@pytest.mark.parametrize("when", ["snapshot", "render"])
def test_relinked_recipient_waits_for_a_fresh_snapshot(notice, monkeypatch, when):
    con, cfg = notice
    due = outbox._due(con)
    m, = due
    rendered = outbox._render(con, m)
    assert rendered is not None
    if m["kind"] == "contact_ok":
        assert rendered[2][0][0]["url"] == "tg://user?id=20"  # another person's contact must never go to the old chat

    def move():
        con.execute("UPDATE users SET tg_id = 99 WHERE id = ?", (m["user_id"],))
        con.execute("INSERT INTO users (tg_id, created_at, seen_at) VALUES (?, 0, 0)", (m["tg_id"],))

    render = outbox._render
    if when == "snapshot":
        move()
    else:
        def moved(con, message):
            result = render(con, message)
            move()
            return result
        monkeypatch.setattr(outbox, "_render", moved)
    tg = Telegram()
    assert batch(con, cfg, tg, due)
    assert not tg.calls and state(con) == (0, None)
    monkeypatch.setattr(outbox, "_render", render)
    con.execute("UPDATE bot_outbox SET send_after = 0")  # the lease ends; now read the new chat
    assert batch(con, cfg, tg)
    assert [b["chat_id"] for b in tg.of("sendMessage")] == [99]
    assert state(con) == (1, None)


@pytest.mark.parametrize("notice", ["contact_ok", "tgc_back"], indirect=True)
def test_relink_while_waiting_for_telegram_slot(notice, monkeypatch):
    con, cfg = notice
    con.execute("""INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after)
        VALUES (2, 'app_broadcast', 'app_home', ?, 0)""", (json.dumps({"url": "https://t.me/example_channel/42"}),))
    due = list(reversed(outbox._due(con)))  # another chat uses the first send slot
    monkeypatch.setattr(outbox, "time", SimpleNamespace(monotonic=lambda: 0))
    sleep, waits = asyncio.sleep, []

    async def relink_in_wait(delay):
        if delay > 0:
            waits.append(delay)
            if len(waits) == 2:  # first the batch turn, then Telegram's send gate
                con.execute("UPDATE users SET tg_id = 99 WHERE id = 1")
                con.execute("INSERT INTO users (tg_id, created_at, seen_at) VALUES (10, 0, 0)")
        await sleep(0)

    monkeypatch.setattr(asyncio, "sleep", relink_in_wait)
    tg = Telegram()
    assert batch(con, cfg, tg, due)
    assert waits == [outbox.GAP, outbox.GAP]
    assert [b["chat_id"] for b in tg.of("sendMessage")] == [20]
    assert tuple(con.execute("SELECT sent_at, error FROM bot_outbox WHERE user_id = 1").fetchone()) == (None, None)
    con.execute("UPDATE bot_outbox SET send_after = 0")
    assert batch(con, cfg, tg)
    assert [b["chat_id"] for b in tg.of("sendMessage")] == [20, 99]


@pytest.mark.parametrize("notice", ["contact_ask", "tgc_removed", "tgc_confirmed", "tgc_back", "tgc_report_ok", "app_broadcast"], indirect=True)
@pytest.mark.parametrize("failure", ["timeout", "disconnect", "invalid_json"])
def test_ambiguous_delivery_retries_only_ordinary_notices(notice, failure):
    con, cfg = notice
    attempts = []

    def no_answer(request):
        attempts.append(json.loads(request.content))  # Telegram may have accepted before its answer was lost
        if failure == "invalid_json":
            return httpx.Response(200, text="truncated")
        raise (httpx.ReadTimeout if failure == "timeout" else httpx.ReadError)("answer lost")

    assert not batch(con, cfg, no_answer)
    assert len(attempts) == 1
    ordinary = con.execute("SELECT kind FROM bot_outbox").fetchone()[0] == "app_broadcast"
    assert state(con) == (0, None if ordinary else "lost")
    con.execute("UPDATE bot_outbox SET send_after = 0")
    tg = Telegram()
    assert batch(con, cfg, tg)
    assert len(tg.of("sendMessage")) == int(ordinary)
    assert state(con) == ((1, None) if ordinary else (0, "lost"))


@pytest.mark.parametrize("notice", ["contact_ask", "tgc_back"], indirect=True)
@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout])
def test_unsent_connection_failure_retries_sensitive_notices(notice, failure):
    con, cfg = notice

    def refused(request):
        raise failure("never reached Telegram")

    assert not batch(con, cfg, refused)
    assert state(con) == (0, None)
    con.execute("UPDATE bot_outbox SET send_after = 0")
    tg = Telegram()
    assert batch(con, cfg, tg)
    assert len(tg.of("sendMessage")) == 1 and state(con) == (1, None)


@pytest.mark.parametrize("notice", ["contact_ask", "tgc_back", "tgc_report_ok"], indirect=True)
def test_explicit_flood_wait_still_retries_sensitive_notices(notice):
    con, cfg = notice
    assert not batch(con, cfg, lambda _: httpx.Response(429, json={
        "ok": False, "error_code": 429, "parameters": {"retry_after": 0}}))
    assert state(con) == (0, None)
    con.execute("UPDATE bot_outbox SET send_after = 0")
    tg = Telegram()
    assert batch(con, cfg, tg)
    assert len(tg.of("sendMessage")) == 1 and state(con) == (1, None)


@pytest.mark.parametrize("notice", ["tgc_confirmed", "tgc_back"], indirect=True)
@pytest.mark.parametrize("saved_chat", [10, 99, None])
def test_verdict_edits_only_a_message_in_its_saved_chat(notice, saved_chat):
    con, cfg = notice
    con.execute("UPDATE tgc_comments SET dm_id = 77, dm_chat_id = ?", (saved_chat,))
    tg = Telegram()
    assert batch(con, cfg, tg)
    method = "editMessageText" if saved_chat == 10 else "sendMessage"
    assert [m for m, _ in tg.calls] == [method]
    body = tg.calls[0][1]
    assert body["chat_id"] == 10 and body["parse_mode"] == "HTML"
    assert body.get("message_id") == (77 if saved_chat == 10 else None)
    assert tuple(con.execute("SELECT dm_id, dm_chat_id, shown FROM tgc_comments").fetchone()) == (
        77 if saved_chat == 10 else 901, 10, 1)


@pytest.mark.parametrize("notice", ["tgc_removed"], indirect=True)
def test_relink_during_response_keeps_the_original_dm_chat(notice):
    con, cfg = notice
    tg = Telegram()

    def move_while_sending(request):
        con.execute("UPDATE users SET tg_id = 99 WHERE id = 1")
        return tg(request)

    assert batch(con, cfg, move_while_sending)
    assert tuple(con.execute("SELECT dm_id, dm_chat_id FROM tgc_comments").fetchone()) == (901, 10)
    con.execute("UPDATE tgc_comments SET review = 0")
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (1, 'tgc_confirmed', 'tc:1', 0)")
    tg.calls.clear()
    assert batch(con, cfg, tg)
    assert [m for m, _ in tg.calls] == ["sendMessage"]
    assert tg.of("sendMessage")[0]["chat_id"] == 99
    assert con.execute("SELECT dm_chat_id FROM tgc_comments").fetchone()[0] == 99


@pytest.mark.parametrize("notice", ["tgc_confirmed", "tgc_back"], indirect=True)
def test_edit_timeout_is_lost_without_a_new_message(notice):
    con, cfg = notice
    con.execute("UPDATE tgc_comments SET dm_id = 77, dm_chat_id = 10")
    calls = []

    def no_answer(request):
        calls.append(request.url.path.rsplit("/", 1)[1])
        raise httpx.ReadTimeout("edit accepted, answer lost")

    assert not batch(con, cfg, no_answer)
    assert calls == ["editMessageText"] and state(con) == (0, "lost")
    con.execute("UPDATE bot_outbox SET send_after = 0")
    assert batch(con, cfg, no_answer)
    assert calls == ["editMessageText"]
