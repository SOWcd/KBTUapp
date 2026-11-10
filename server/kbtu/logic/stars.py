"""Telegram Stars for "Support the app" (owner, Nov 9): one more way beside the banks, a gift and never a purchase. The
app asks for an invoice, Telegram's own window takes the Stars, the bot records the charge. Nothing about the payer is
kept on the gift. A new gift gives its payer the award Fuel (Nov 10, reviews: for Stars only, never a bank transfer;
no amount, no level): that one fact sits on their account (achievement_grants, gone with it) and needs the privacy
policy's line (TODO(legal) there)."""
from __future__ import annotations

import logging
import re
import time

import httpx

from .. import texts
from ..config import Config
from ..db import tx
from . import profiles
from .core import ApiError, now, one

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


def paid(con, payment: dict, payer: object = None) -> None:
    """A successful_payment message: a replayed update counts once (the charge id is the key). The Stars have already
    arrived, so a payload we don't recognise is recorded too. A new gift gives its payer (`payer`: the message's from.id)
    the award Fuel, if they are a student and haven't it yet; the payer is never written next to the gift.
    ponytail: no payer on the row, so a refund (refundStarPayment wants the user id and the charge id) needs the payer's
    Telegram id from them, and Fuel isn't taken back by itself: the creator takes it back by hand (Admin, take_back).
    Upgrade: a user column here, with its privacy section and a _DEL_GONE entry.
    ponytail: the gift's time is kept to the day, so it doesn't line up with Fuel's grant to the second; a day with one
    gift still says who gave how much to someone reading the database. Drop the amounts if that ever matters.
    ponytail: a payer who signs in with KBTU only later gets no Fuel (the creator can give it by hand)."""
    charge, amount = payment.get("telegram_payment_charge_id"), payment.get("total_amount")
    if not (payment.get("currency") == "XTR" and isinstance(charge, str) and charge and isinstance(amount, int) and amount > 0):
        return
    with tx(con):
        day = (now() + 5 * 3600) // 86400 * 86400 - 5 * 3600  # Almaty's
        new = con.execute("INSERT OR IGNORE INTO star_gifts (charge_id, amount, created_at) VALUES (?, ?, ?)", (charge, amount, day)).rowcount
        u = one(con, "SELECT s.user_id FROM users u JOIN students s ON s.user_id = u.id WHERE u.tg_id = ?", payer) if new and type(payer) is int else None
        if u and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'supporter'", u[0]):
            profiles._grant(con, None, u[0], "supporter", log=False)  # no audit row either: it would say who gave
