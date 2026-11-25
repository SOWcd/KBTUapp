"""Telegram Stars support: Telegram confirms the charge; its replay guard and private ledger commit together."""
from __future__ import annotations

import hmac
import logging
import time

import httpx

from .. import texts
from ..config import Config
from ..db import tx
from . import donations, profiles
from .core import ApiError, now, one

log = logging.getLogger(__name__)
LEAST, MOST = 1, 10000
ASKS_A_MINUTE = 10
CONSENT = "ds1"  # The invoice explains the linked private total before Telegram asks for payment.
_asks: dict[int, list[float]] = {}  # ponytail: per worker and lost on restart (a row per user would be a payer trail); it only spares Telegram's rate limit


def _ok(amount: object) -> bool:
    return isinstance(amount, int) and not isinstance(amount, bool) and LEAST <= amount <= MOST


def _throttle(uid: int) -> None:
    t = time.monotonic()
    if len(_asks) > 5000:
        for k in [k for k, x in _asks.items() if x[-1] <= t - 60]:
            del _asks[k]
    recent = [x for x in _asks.get(uid, ()) if x > t - 60]
    if len(recent) >= ASKS_A_MINUTE:
        raise ApiError("rate_limited")
    _asks[uid] = [*recent, t]


def _payload(token: str, payer: int, amount: int) -> str:
    # A forwarded link cannot charge a different account; the payload need not carry the Telegram ID.
    prefix = f"don:{CONSENT}:{amount}"
    proof = hmac.digest(token.encode(), f"{prefix}:{payer}".encode(), "sha256").hex()[:32]
    return f"{prefix}:{proof}"


async def invoice(cfg: Config, http: httpx.AsyncClient, payer: int, lang: str, amount: object) -> str:
    """A Telegram invoice for the person who requested it."""
    if not _ok(amount):
        raise ApiError("bad_input")
    _throttle(payer)
    title, text = texts.pick(texts.STARS_INVOICE, lang)
    try:
        r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/createInvoiceLink", timeout=10, json={
            "title": title, "description": text, "payload": _payload(cfg.bot_token, payer, amount), "provider_token": "", "currency": "XTR",
            "prices": [{"label": title, "amount": amount}]})).json()
    except (httpx.HTTPError, ValueError) as exc:  # the type only: the URL holds the token
        log.warning("stars invoice: %s", type(exc).__name__)
        raise ApiError("unavailable", "telegram") from None
    if not r.get("ok"):
        log.warning("stars invoice: %s", str(r.get("description"))[:200])
        raise ApiError("unavailable", "telegram")
    return r["result"]


def checkout_ok(token: str, q: dict, payer: object) -> bool:
    """Check the payer and amount against the invoice without a database round trip."""
    payload = str(q.get("invoice_payload"))
    amount = q.get("total_amount")
    return (type(payer) is int and q.get("currency") == "XTR" and _ok(amount)
            and payload.isascii() and hmac.compare_digest(payload, _payload(token, payer, amount)))


def paid(con, payment: dict, payer: object, token: str) -> None:
    """Only called for Telegram's successful_payment. Never trust the client invoice callback.
    The anonymous charge guard survives account deletion; old unlinked gifts are not backfilled."""
    charge, amount = payment.get("telegram_payment_charge_id"), payment.get("total_amount")
    if not (payment.get("currency") == "XTR" and isinstance(charge, str) and charge and type(amount) is int and amount > 0):
        return
    with tx(con):
        day = (now() + 5 * 3600) // 86400 * 86400 - 5 * 3600  # Almaty's
        new = con.execute("INSERT OR IGNORE INTO star_gifts (charge_id, amount, created_at) VALUES (?, ?, ?)", (charge, amount, day)).rowcount
        u = one(con, "SELECT id FROM users WHERE tg_id = ?", payer) if new and type(payer) is int else None
        if u and checkout_ok(token, payment, payer):
            con.execute("""INSERT INTO donations (user_id, source, status, amount, stars, star_rate, charge_id, consent, created_at, reviewed_at)
                VALUES (?, 'stars', 'confirmed', ?, ?, ?, ?, ?, ?, ?)""",
                        (u[0], amount * donations.STAR_KZT, amount, donations.STAR_KZT, charge, CONSENT, now(), now()))
            donations.sync_medal(con, u[0])
        if u and one(con, "SELECT 1 FROM students WHERE user_id = ?", u[0]) and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'supporter'", u[0]):
            profiles._grant(con, None, u[0], "supporter", log=False)  # no audit row either: it would say who gave
