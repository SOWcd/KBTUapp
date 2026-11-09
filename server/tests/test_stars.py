"""Telegram Stars on "Support the app" (logic/stars.py): the invoice, the pre-checkout, the record that says nothing of who gave."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import httpx
import pytest

from kbtu import bot, db, logic, texts
from test_core import env, tma  # noqa: F401  (env: the fixture)


class Telegram:
    """Bot API by hand: `batches` are the rounds getUpdates hands out, the last one over and over."""
    def __init__(self, *batches, answers=()):
        self.batches, self.calls, self.timeouts = list(batches), [], []
        self.answers = list(answers)  # how answerPreCheckoutQuery goes, try by try: a status, or None for a timeout; then 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        if method == "getUpdates":
            self.calls.append((method, dict(request.url.params)))
            return httpx.Response(200, json={"ok": True, "result": self.batches.pop(0) if len(self.batches) > 1 else self.batches[0]})
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        if method == "answerPreCheckoutQuery":
            self.timeouts.append(request.extensions["timeout"]["read"])
            status = self.answers.pop(0) if self.answers else 200
            if status is None:
                raise httpx.ReadTimeout("hung", request=request)
            return httpx.Response(status, json={"ok": status == 200, "result": True, "description": "x"})
        return httpx.Response(200, json={"ok": True, "result": "https://t.me/$invoice"})

    def sent(self, method):
        return [b for m, b in self.calls if m == method]


def hear(cfg, tg):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            return await bot.hear(cfg, http, 0)
    return asyncio.run(go())


def checkout(qid="q1", amount=50, payload="don:50", currency="XTR"):
    return {"update_id": 1, "pre_checkout_query": {"id": qid, "from": {"id": 7, "language_code": "en"}, "currency": currency,
                                                   "total_amount": amount, "invoice_payload": payload}}


def payment(uid=1, charge="c1", amount=50):
    return {"update_id": uid, "message": {"message_id": 3, "chat": {"id": 7, "type": "private"}, "from": {"id": 7}, "date": 0, "successful_payment": {
        "currency": "XTR", "total_amount": amount, "invoice_payload": f"don:{amount}", "telegram_payment_charge_id": charge, "provider_payment_charge_id": ""}}}


@pytest.fixture(autouse=True)
def _fresh():
    logic.stars._asks.clear()
    bot._checked.clear()


def wire(c):
    tg = Telegram([])
    c.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(tg))
    return tg


def test_invoice_in_stars(env):
    c, _ = env
    tg = wire(c)
    r = c.post("/api/donate/stars", headers=tma(40, "Ann"), json={"amount": 100})
    assert r.json() == {"url": "https://t.me/$invoice"}
    b = tg.sent("createInvoiceLink")[0]
    assert (b["currency"], b["provider_token"], b["prices"][0]["amount"], b["payload"]) == ("XTR", "", 100, "don:100")
    assert "40" not in b["payload"]  # nothing of the payer


def test_invoice_refuses_a_bad_amount_and_strangers(env):
    c, _ = env
    tg = wire(c)
    for bad in (0, -5, 10001, 1.5, "50", True, None):
        assert c.post("/api/donate/stars", headers=tma(41, "Ann"), json={"amount": bad}).status_code == 400, bad
    assert c.post("/api/donate/stars", json={"amount": 50}).status_code == 403
    assert tg.sent("createInvoiceLink") == []


def test_invoice_rate_limit(env):
    c, _ = env
    wire(c)
    codes = [c.post("/api/donate/stars", headers=tma(42, "Ann"), json={"amount": 1}).status_code for _ in range(logic.stars.ASKS_A_MINUTE + 1)]
    assert codes[:-1] == [200] * logic.stars.ASKS_A_MINUTE and codes[-1] == 429


def test_texts_fit_telegram():
    assert set(texts.STARS_INVOICE) == set(texts.STARS_REFUSED) == {"ru", "kk", "en"}
    assert all(1 <= len(t) <= 32 and 1 <= len(d) <= 255 for t, d in texts.STARS_INVOICE.values())


@pytest.mark.parametrize("kw", [dict(payload="other"), dict(amount=51), dict(currency="USD"), dict(payload="don:20000", amount=20000), dict(payload="don:0", amount=0)])
def test_checkout_refused(env, kw):
    _, cfg = env
    tg = Telegram([checkout(**kw)], [])
    hear(cfg, tg)
    a = tg.sent("answerPreCheckoutQuery")
    assert len(a) == 1 and a[0]["ok"] is False and a[0]["error_message"]


def test_checkout_answered_once_and_says_nothing_else(env):
    _, cfg = env
    tg = Telegram([checkout()], [])
    hear(cfg, tg)
    assert [b["ok"] for b in tg.sent("answerPreCheckoutQuery")] == [True] and tg.sent("sendMessage") == []
    tg.batches = [[checkout()], []]  # the next round sees it again
    hear(cfg, tg)
    assert len(tg.sent("answerPreCheckoutQuery")) == 1


def test_allowed_updates_ask_for_it(env):
    _, cfg = env
    tg = Telegram([], [])
    hear(cfg, tg)
    assert "pre_checkout_query" in json.loads(tg.calls[0][1]["allowed_updates"])


def test_a_pre_checkout_doesnt_wait_behind_a_slow_batch(env, monkeypatch):
    """It came while the batch ran: answered before the batch ends, by a look that confirms nothing (the batch's own offset)."""
    _, cfg = env
    tg = Telegram([{"update_id": 1, "callback_query": {"id": "x", "from": {"id": 9}}}], [{"update_id": 2, **{k: v for k, v in checkout("late").items() if k != "update_id"}}])
    answered_in_batch = []

    async def slow(*_):
        for _ in range(100):
            await asyncio.sleep(0.01)
            if tg.sent("answerPreCheckoutQuery"):
                break
        answered_in_batch.append(bool(tg.sent("answerPreCheckoutQuery")))

    monkeypatch.setattr(bot, "_tapped", slow)
    monkeypatch.setattr(bot, "PEEK", 0.01)
    hear(cfg, tg)
    assert answered_in_batch == [True] and tg.sent("answerPreCheckoutQuery")[0]["ok"] is True
    assert all(p["offset"] == "0" for m, p in tg.calls if m == "getUpdates")


def test_payment_counts_once_and_keeps_no_payer(env):
    _, cfg = env
    con = db.connect(cfg.db_path)
    tg = Telegram([payment()], [])
    hear(cfg, tg)
    tg.batches = [[payment(2)], []]  # replayed under a new update id
    hear(cfg, tg)
    assert [tuple(r)[:2] for r in con.execute("SELECT charge_id, amount FROM star_gifts")] == [("c1", 50)]
    assert tg.sent("sendMessage") == []  # Telegram's own receipt is the only one
    assert {r[1] for r in con.execute("PRAGMA table_info(star_gifts)")} == {"charge_id", "amount", "created_at"}
    assert not list(con.execute("PRAGMA foreign_key_list(star_gifts)"))


def test_a_banned_payer_still_counts(env):
    """The Stars have arrived whoever sent them; the ban skip comes after."""
    c, cfg = env
    c.get("/api/me", headers=tma(7, "Ann"))
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 7")
    hear(cfg, Telegram([payment(charge="c2")], []))
    assert con.execute("SELECT amount FROM star_gifts WHERE charge_id = 'c2'").fetchone()[0] == 50


def tap(uid):
    return {"update_id": uid, "callback_query": {"id": str(uid), "from": {"id": 9}}}


def test_a_locked_database_keeps_the_payment_for_the_next_round(env, monkeypatch):
    """A paid transfer the write failed for: the batch stops there, the same update comes again, and the retry counts once."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    tapped, real = [], logic.stars.paid

    async def on_tap(_cfg, _http, _con, q):
        tapped.append(q["id"])

    def locked(*_):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(bot, "_tapped", on_tap)
    monkeypatch.setattr(logic.stars, "paid", locked)
    batch = [tap(5), payment(6), tap(7)]
    assert hear(cfg, Telegram(batch, [])) == 6
    assert tapped == ["5"] and con.execute("SELECT count(*) FROM star_gifts").fetchone()[0] == 0
    monkeypatch.setattr(logic.stars, "paid", real)
    assert hear(cfg, Telegram(batch[1:], [])) == 8
    assert hear(cfg, Telegram(batch[1:], [])) == 8  # delivered twice all the same
    assert tapped == ["5", "7", "7"] and [tuple(r) for r in con.execute("SELECT charge_id, amount FROM star_gifts")] == [("c1", 50)]


def test_a_failed_connect_leaves_no_watcher(env, monkeypatch):
    _, cfg = env
    tg = Telegram([tap(5)], [])

    def broken(_):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(bot.db, "connect", broken)
    monkeypatch.setattr(bot, "PEEK", 0.01)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            with pytest.raises(sqlite3.OperationalError):
                await bot.hear(cfg, http, 0)
            assert asyncio.all_tasks() == {asyncio.current_task()}
            await asyncio.sleep(0.05)
    asyncio.run(go())
    assert len([m for m, _ in tg.calls if m == "getUpdates"]) == 1


@pytest.mark.parametrize("trouble", [[500], [429], [None], [500, 429, None]])
def test_checkout_answer_retried_after_a_transient_error(env, monkeypatch, trouble):
    _, cfg = env
    monkeypatch.setattr(bot, "CHECKOUT_RETRY", 0.01)
    tg = Telegram([checkout()], [], answers=trouble)
    hear(cfg, tg)
    assert len(tg.sent("answerPreCheckoutQuery")) == len(trouble) + 1 and "q1" in bot._checked
    assert set(tg.timeouts) == {bot.CHECKOUT_HTTP}


def test_checkout_refused_for_good_is_not_retried(env, monkeypatch):
    _, cfg = env
    monkeypatch.setattr(bot, "CHECKOUT_RETRY", 0.01)
    tg = Telegram([checkout()], [], answers=[400])
    hear(cfg, tg)
    assert len(tg.sent("answerPreCheckoutQuery")) == 1 and "q1" in bot._checked


def test_checkout_retries_stop_in_time_and_stay_unanswered(env, monkeypatch):
    _, cfg = env
    monkeypatch.setattr(bot, "CHECKOUT_RETRY", 0.01)
    monkeypatch.setattr(bot, "CHECKOUT_WINDOW", 0.05)
    tg = Telegram([checkout()], [], answers=[500] * 1000)
    hear(cfg, tg)
    assert len(tg.sent("answerPreCheckoutQuery")) > 1 and "q1" not in bot._checked


def test_a_failing_checkout_lets_its_neighbour_go_first(env, monkeypatch):
    _, cfg = env
    monkeypatch.setattr(bot, "CHECKOUT_RETRY", 0.01)
    tg = Telegram([checkout("a"), checkout("b")], [], answers=[500])
    hear(cfg, tg)
    assert [b["pre_checkout_query_id"] for b in tg.sent("answerPreCheckoutQuery")] == ["a", "b", "a"]


def paysupport(text="/paysupport", kind="private", lang="en", uid=7):
    return {"update_id": 1, "message": {"message_id": 3, "chat": {"id": uid, "type": kind}, "from": {"id": uid, "language_code": lang}, "date": int(time.time()), "text": text}}


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_paysupport_is_its_own_template(env, lang):
    _, cfg = env
    tg = Telegram([paysupport(lang=lang)], [])
    hear(cfg, tg)
    [b] = tg.sent("sendMessage")
    want = texts.bot_message(lang, "paysupport", tg_id=7)[0]
    assert "@Sowers" in want and "<code>7</code>" in want
    assert b["chat_id"] == 7 and "reply_markup" not in b and "@Sowers" in b["text"]


def test_paysupport_answers_a_banned_payer_and_only_this_command(env):
    c, cfg = env
    c.get("/api/me", headers=tma(7, "Ann"))
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 7")
    tg = Telegram([paysupport("/paysupport@KBTUappBot")], [])
    hear(cfg, tg)
    assert len(tg.sent("sendMessage")) == 1
    tg = Telegram([paysupport("/paysupport2")], [])  # another word: still the ban skip
    hear(cfg, tg)
    assert tg.sent("sendMessage") == []
