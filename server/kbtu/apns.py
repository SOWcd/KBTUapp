"""The iPhone app's push provider (push.py picks the channel): Apple's APNs. Its words are the same server template
the bot sends (texts.py), never a user's.

HTTP/2 with a provider token: an ES256 JWT over the .p8 key (APNS_KEY), made again every 50 minutes (Apple refuses one
older than an hour and throttles one remade too often). TestFlight and App Store builds both use production APNs."""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .config import Config

log = logging.getLogger("kbtu.apns")

HOST = "https://api.push.apple.com"
GONE = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}
_jwt: tuple[str, float] = ("", 0.0)
_http: httpx.AsyncClient | None = None


def on(cfg: Config) -> bool:
    return bool(cfg.ios_bundle and cfg.apns_key_id and cfg.apns_team_id and cfg.apns_key)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _bearer(cfg: Config) -> str:
    global _jwt
    if time.time() - _jwt[1] < 3000:
        return _jwt[0]
    head = _b64(json.dumps({"alg": "ES256", "kid": cfg.apns_key_id}).encode())
    claims = _b64(json.dumps({"iss": cfg.apns_team_id, "iat": int(time.time())}).encode())
    key = serialization.load_pem_private_key(cfg.apns_key.encode(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    r, s = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    _jwt = (f"{head}.{claims}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}", time.time())
    return _jwt[0]


def plain(text: str) -> str:
    """The bot's HTML as a notification's words: its tags off, its entities back."""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()[:1500]


async def send(cfg: Config, token: str, text: str, start: str) -> str:
    """'ok'; 'gone' (Apple says the token is dead); 'down' (any other failure: keep the token)."""
    global _http
    if _http is None:
        _http = httpx.AsyncClient(http2=True, timeout=15)
    body = {"aps": {"alert": {"body": plain(text)}, "sound": "default"}, **({"start": start} if start else {})}
    try:
        r = await _http.post(f"{HOST}/3/device/{token}", json=body, headers={
            "authorization": f"bearer {_bearer(cfg)}", "apns-topic": cfg.ios_bundle, "apns-push-type": "alert"})
    except (httpx.HTTPError, ValueError) as exc:  # ValueError: a key that doesn't load
        log.warning("apns: %s", type(exc).__name__)
        return "down"
    if r.status_code == 200:
        return "ok"
    if r.status_code == 410:
        return "gone"
    try:
        body = r.json()
    except ValueError:
        body = None
    reason = str(body.get("reason", "")) if isinstance(body, dict) else ""
    if reason in GONE:
        return "gone"
    log.warning("apns: %s %s", r.status_code, reason[:60])  # never the token
    return "down"  # topic, payload, throttle, credentials or service: none says the device token is dead

