"""Who is calling.

Every API request carries `Authorization: tma <initData>` (SPEC §6): Telegram signs it with a key derived
from the bot token, so a valid hash proves the Telegram user."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse

MAX_AGE = 24 * 3600


def check_init_data(init_data: str, bot_token: str, now: float | None = None) -> dict | None:
    """The Telegram user from signed initData, or None when the signature or its age is wrong."""
    pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(want, got):
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
