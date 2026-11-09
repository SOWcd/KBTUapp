"""Telegram Stars for "Support the app" (owner, Nov 9): one more way beside the banks, a gift and never a purchase. The
app asks for an invoice, Telegram's own window takes the Stars, the bot records the charge. Nothing about the payer is
kept, so this is no new personal data: no policy section, no consent version, nothing for an account's deletion to reach."""
from __future__ import annotations

import logging
import re
import time

import httpx

from .. import texts
from ..config import Config
from .core import ApiError, now

log = logging.getLogger(__name__)
LEAST, MOST = 1, 10000
ASKS_A_MINUTE = 10
_PAYLOAD = re.compile(r"don:([0-9]{1,5})")
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


async def invoice(cfg: Config, http: httpx.AsyncClient, uid: int, lang: str, amount: object) -> str:
    """A link for Telegram.WebApp.openInvoice: this many Stars, no user id in the payload."""
    if not _ok(amount):
        raise ApiError("bad_input")
    _throttle(uid)
    title, text = texts.pick(texts.STARS_INVOICE, lang)
    try:
        r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/createInvoiceLink", timeout=10, json={
            "title": title, "description": text, "payload": f"don:{amount}", "provider_token": "", "currency": "XTR",
            "prices": [{"label": title, "amount": amount}]})).json()
    except (httpx.HTTPError, ValueError) as exc:  # the type only: the URL holds the token
        log.warning("stars invoice: %s", type(exc).__name__)
        raise ApiError("unavailable", "telegram") from None
    if not r.get("ok"):
        log.warning("stars invoice: %s", str(r.get("description"))[:200])
        raise ApiError("unavailable", "telegram")
    return r["result"]


def checkout_ok(q: dict) -> bool:
    """A pre-checkout query: our payload, in Stars, for the amount the payload says."""
    m = _PAYLOAD.fullmatch(str(q.get("invoice_payload")))
    return bool(m) and q.get("currency") == "XTR" and q.get("total_amount") == int(m[1]) and _ok(int(m[1]))


def paid(con, payment: dict) -> None:
    """A successful_payment message: a replayed update counts once (the charge id is the key). The Stars have already
    arrived, so a payload we don't recognise is recorded too.
    ponytail: no payer on the row, so a refund (refundStarPayment wants the user id and the charge id) needs the payer's
    Telegram id from them; upgrade: a user column here, with its privacy section and a _DEL_GONE entry."""
    charge, amount = payment.get("telegram_payment_charge_id"), payment.get("total_amount")
    if payment.get("currency") == "XTR" and isinstance(charge, str) and charge and isinstance(amount, int) and amount > 0:
        con.execute("INSERT OR IGNORE INTO star_gifts (charge_id, amount, created_at) VALUES (?, ?, ?)", (charge, amount, now()))
