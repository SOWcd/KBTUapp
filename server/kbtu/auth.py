"""Who is calling.

Telegram signs Mini App initData and Login Widget payloads with different keys derived from the bot token."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.parse

BOT_TOKEN = re.compile(r"[1-9][0-9]*:[A-Za-z0-9_-]{32,}")

MAX_AGE = 24 * 3600
WIDGET_MAX_AGE = 600
WIDGET_FIELDS = {"auth_date", "id", "first_name", "last_name", "username", "photo_url", "hash"}


def check_init_data(init_data: str, bot_token: str, now: float | None = None) -> dict | None:
    """The Telegram user from signed initData, or None when the signature or its age is wrong."""
    if not BOT_TOKEN.fullmatch(bot_token):
        return None
    pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(want.encode(), got.encode()):  # bytes: a non-ASCII str raises (a 500)
        return None
    try:
        if (now or time.time()) - int(pairs.get("auth_date", "0")) > MAX_AGE:
            return None
        user = json.loads(pairs.get("user") or "null")
    except ValueError:
        return None
    return user if isinstance(user, dict) and isinstance(user.get("id"), int) else None


def sign_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """The inverse of check_init_data, for tests and local runs without Telegram."""
    pairs = {"auth_date": str(auth_date or int(time.time())), "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)


def check_widget(data: dict, bot_token: str, now: int) -> dict | None:
    """Verify a legacy Telegram Login Widget callback, without changing the signed values."""
    if not BOT_TOKEN.fullmatch(bot_token) or data.keys() - WIDGET_FIELDS:
        return None
    if not all(type(v) is int and k in ("auth_date", "id")
               or isinstance(v, str) and "\n" not in v and "\r" not in v for k, v in data.items()):
        return None
    got = data.get("hash")
    if not isinstance(got, str) or not re.fullmatch(r"[0-9a-f]{64}", got):
        return None
    date, uid = str(data.get("auth_date", "")), str(data.get("id", ""))
    if not re.fullmatch(r"[0-9]{1,12}", date) or not re.fullmatch(r"[1-9][0-9]{0,15}", uid):
        return None
    if not -30 <= now - int(date) < WIDGET_MAX_AGE:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if k != "hash")
    try:
        want = hmac.digest(hashlib.sha256(bot_token.encode()).digest(), check.encode(), "sha256")
    except UnicodeEncodeError:
        return None
    if not hmac.compare_digest(want, bytes.fromhex(got)):
        return None
    return {**data, "id": int(uid), "auth_date": int(date)}
