"""Telegram Stars on "Support the app" (logic/stars.py): the invoice, the pre-checkout, the record that says nothing of who gave."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from kbtu import bot, db, logic, texts
from test_core import env, tma  # noqa: F401  (env: the fixture)


class Telegram:
    """Bot API by hand: `batches` are the rounds getUpdates hands out, the last one over and over."""
    def __init__(self, *batches):
        self.batches, self.calls = list(batches), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        if method == "getUpdates":
            self.calls.append((method, dict(request.url.params)))
            return httpx.Response(200, json={"ok": True, "result": self.batches.pop(0) if len(self.batches) > 1 else self.batches[0]})
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        return httpx.Response(200, json={"ok": True, "result": "https://t.me/$invoice"})

    def sent(self, method):
        return [b for m, b in self.calls if m == method]


def hear(cfg, tg):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.hear(cfg, http, 0)
    asyncio.run(go())


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
