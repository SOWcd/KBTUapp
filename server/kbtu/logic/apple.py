"""The iPhone app (ios/): Sign in with Apple, linked sign-ins and its push tokens. One account, many sign-ins.

Telegram stays users.tg_id (the whole app keys people by it); every other sign-in is a row in identities. An account
Apple makes first gets a synthetic tg_id of SYNTH + 1 or more: Telegram documents its user IDs as 52 bits at most, so no
Telegram account is behind it, can_dm stays 0 and the bot never writes (2**52 itself is the Play demo's). Linking
Telegram later puts the real ID in its place. A Telegram ID that already has its own account is never merged into
another one: the person is told to use that account (merging two people's histories is a support case, not a tap).

Apple's identity token is checked here: RS256 against Apple's published keys, our bundle ID as the audience, fresh, and
its nonce the SHA-256 of one the app made for this tap, spent once (web_login_used): a token copied out of a log or
another app's flow signs nobody in. Only Apple's "sub" is kept; the app asks Apple for no name and no email."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from . import core
from .core import ApiError, one, rows
from .daily import visit

log = logging.getLogger("kbtu.apple")

ISSUER = "https://appleid.apple.com"
JWKS = "https://appleid.apple.com/auth/keys"
CONSENT = "ios1"     # the policy's "iPhone app and Sign in with Apple" (section 2): at the Apple button, at notifications on
SYNTH = 2**52        # tg_id at or above: no Telegram behind the account
FRESH = 600          # an identity token older than this (by its iat) is refused
NONCE = re.compile(r"[A-Za-z0-9_-]{32,128}")
SUBJECT = re.compile(r"[A-Za-z0-9._-]{1,255}")
DEVICE = re.compile(r"[0-9a-f]{64,200}")  # an APNs token in hex (32 bytes today, Apple says it may grow)

_keys: dict[str, rsa.RSAPublicKey] = {}
_keys_at = 0.0
_keys_lock = threading.Lock()


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _load_keys(kid: str) -> rsa.RSAPublicKey | None:
    """Apple's key by id: cached for a day, fetched again for an unknown id (Apple rotates them) at most once a minute."""
    global _keys_at
    with _keys_lock:
        if (kid not in _keys and time.time() - _keys_at > 60) or time.time() - _keys_at > 86400:
            try:
                r = httpx.get(JWKS, timeout=10)
                r.raise_for_status()
                fresh = {k["kid"]: rsa.RSAPublicNumbers(int.from_bytes(_b64(k["e"]), "big"), int.from_bytes(_b64(k["n"]), "big")).public_key()
                         for k in r.json()["keys"] if k.get("kty") == "RSA" and k.get("alg", "RS256") == "RS256"}
                _keys.clear()
                _keys.update(fresh)
            except Exception as exc:  # Apple unreachable: the keys we had stay; a sign-in now fails, never a 500
                log.warning("apple keys: %s", type(exc).__name__)
            _keys_at = time.time()
        return _keys.get(kid)


def subject(token: object, nonce: object, audience: str, now: int) -> str | None:
    """Apple's "sub" for a valid identity token minted for this tap (its nonce), else None."""
    if not audience or not isinstance(token, str) or not isinstance(nonce, str) or not NONCE.fullmatch(nonce) or len(token) > 8000:
        return None
    try:
        head, body, sig = token.split(".")
        h, c = json.loads(_b64(head)), json.loads(_b64(body))
        if not isinstance(h, dict) or not isinstance(c, dict) or h.get("alg") != "RS256" or not isinstance(h.get("kid"), str):
            return None
        key = _load_keys(h["kid"])
        if key is None:
            return None
        key.verify(_b64(sig), f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, TypeError, InvalidSignature):  # malformed base64, JSON or parts; a wrong signature
        return None
    aud = c.get("aud")
    sub, iat, exp = c.get("sub"), c.get("iat"), c.get("exp")
    if c.get("iss") != ISSUER or (aud != audience and not (isinstance(aud, list) and audience in aud)):
        return None
    if not all(type(x) is int for x in (iat, exp)) or not now - FRESH <= iat <= now + 60 or exp <= now:
        return None
    if c.get("nonce") != hashlib.sha256(nonce.encode()).hexdigest():
        return None
    return sub if isinstance(sub, str) and SUBJECT.fullmatch(sub) else None


def _spend(con, nonce: str, now: int) -> None:
    """One tap, one sign-in: the nonce is spent with the transaction that uses it."""
    digest = hashlib.sha256(b"apple " + nonce.encode()).digest()
    if not con.execute("INSERT OR IGNORE INTO web_login_used VALUES (?, ?)", (digest, now + FRESH + 60)).rowcount:
        raise ApiError("forbidden", "web_login")


def _consent(body: dict) -> None:
    if body.get("consent") != CONSENT:
        raise ApiError("forbidden", "apple_consent")  # not "consent": the web's main policy gate answers that one


def owner(con, sub: str) -> int | None:
    r = one(con, "SELECT user_id FROM identities WHERE provider = 'apple' AND subject = ?", sub)
    return r[0] if r else None


def sign_in(con, body: dict, sub: str, lang: str, now: int) -> int:
    """The account this Apple ID signs into, made now when it has none (inside the caller's transaction)."""
    _consent(body)
    _spend(con, body["nonce"], now)
    if (uid := owner(con, sub)) is not None:
        return uid
    while True:
        tg = SYNTH + 1 + secrets.randbelow(SYNTH - 1)  # below 2**53: still exact in the web's numbers
        if not one(con, "SELECT 1 FROM users WHERE tg_id = ?", tg):
            break
    uid = con.execute("""INSERT INTO users (tg_id, lang, can_dm, created_at, seen_at) VALUES (?, ?, 0, ?, ?)""",
                      (tg, lang if lang in ("ru", "kk", "en") else "ru", now, now)).lastrowid
    con.execute("INSERT INTO identities (provider, subject, user_id, consent, created_at) VALUES ('apple', ?, ?, ?, ?)",
                (sub, uid, CONSENT, now))
    visit(con, uid, now)
    return uid


def link_apple(con, uid: int, body: dict, sub: str, now: int) -> None:
    """Apple added to my account; an Apple ID already behind another account is refused (never moved)."""
    _consent(body)
    _spend(con, body["nonce"], now)
    held = owner(con, sub)
    if held == uid:
        return
    if held is not None:
        raise ApiError("conflict", "apple_taken")
    if one(con, "SELECT 1 FROM identities WHERE provider = 'apple' AND user_id = ?", uid):
        raise ApiError("conflict", "apple_linked")  # another Apple ID already: unlink it first
    con.execute("INSERT INTO identities (provider, subject, user_id, consent, created_at) VALUES ('apple', ?, ?, ?, ?)",
                (sub, uid, CONSENT, now))
    core.log_action(con, uid, "login_link", f"user:{uid}", '{"provider": "apple"}')


def unlink_apple(con, uid: int) -> None:
    """Apple taken off my account: only while Telegram still signs me in (never the last way in)."""
    if not telegram_linked(con, uid):
        raise ApiError("forbidden", "last_login")
    con.execute("DELETE FROM identities WHERE provider = 'apple' AND user_id = ?", (uid,))
    core.log_action(con, uid, "login_unlink", f"user:{uid}", '{"provider": "apple"}')


def telegram_linked(con, uid: int) -> bool:
    return bool(one(con, "SELECT 1 FROM users WHERE id = ? AND tg_id > 0 AND tg_id < ?", uid, SYNTH))


def logins(con, uid: int) -> dict:
    """/api/me's part: which sign-ins reach this account."""
    return {"telegram": telegram_linked(con, uid),
            "apple": one(con, "SELECT 1 FROM identities WHERE provider = 'apple' AND user_id = ?", uid) is not None}


def link_telegram(con, uid: int, tg: dict, now: int) -> None:
    """A Telegram Login proof (auth.check_widget, already spent) put on my Apple-made account. The caller issues a new
    session after it: changing tg_id signs every session of the account out (migration 216's trigger)."""
    if tg["id"] >= SYNTH:
        raise ApiError("forbidden", "web_login")
    if telegram_linked(con, uid):
        raise ApiError("conflict", "telegram_linked")
    if one(con, "SELECT 1 FROM users WHERE tg_id = ?", tg["id"]):
        raise ApiError("conflict", "telegram_taken")  # that Telegram has its own account: sign in with it instead
    con.execute("""UPDATE users SET tg_id = ?, tg_username = ?, tg_first_name = ?, tg_last_name = ? WHERE id = ?""",
                (tg["id"], tg.get("username"), tg.get("first_name") or "", tg.get("last_name") or "", uid))
    core.log_action(con, uid, "login_link", f"user:{uid}", '{"provider": "telegram"}')


def telegram_start(bot_token: str, domain: str) -> str:
    """Telegram's own sign-in page, back to us with #tgAuthResult (the widget's redirect mode, no popup)."""
    return "https://oauth.telegram.org/auth?" + str(httpx.QueryParams({
        "bot_id": bot_token.split(":")[0], "origin": f"https://{domain}", "request_access": "write",
        "return_to": f"https://{domain}/?link=telegram"}))  # the page reads #tgAuthResult (WebEntrance.telegramBack)


def add_device(con, uid: int, session: bytes, body: dict, now: int) -> None:
    """This iPhone's push token, for this signed-in session only (it goes with the session)."""
    _consent(body)
    token = body.get("token")
    if not isinstance(token, str) or not DEVICE.fullmatch(token):
        raise ApiError("bad_input")
    con.execute("""INSERT INTO push_devices (token, session, user_id, consent, created_at) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (token) DO UPDATE SET session = excluded.session, user_id = excluded.user_id,
        consent = excluded.consent, created_at = excluded.created_at""", (token, session, uid, CONSENT, now))


def devices(con, uid: int) -> list[str]:
    return [r[0] for r in rows(con, "SELECT token FROM push_devices WHERE user_id = ?", uid)]


def drop_device(con, token: str) -> None:
    """APNs said this token is dead (the app deleted, notifications off for good)."""
    con.execute("DELETE FROM push_devices WHERE token = ?", (token,))


def keep_devices(con, uid: int, old: list[str], session: bytes, now: int) -> None:
    """The session's push tokens carried to its replacement (a Telegram link re-issues the session)."""
    for token in old:
        con.execute("INSERT OR IGNORE INTO push_devices (token, session, user_id, consent, created_at) VALUES (?, ?, ?, ?, ?)",
                    (token, session, uid, CONSENT, now))
