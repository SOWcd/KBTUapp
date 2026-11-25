"""The iPhone app: Sign in with Apple, linked sign-ins, push tokens and push beside the bot (logic/apple.py, apns.py)."""
import asyncio
import base64
import hashlib
import json
import secrets
from dataclasses import replace

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from kbtu import apns, app as server, bot, db, logic
from kbtu.logic import apple, web_auth
from test_core import delete_now, env, set_clock, tma  # noqa: F401
from test_web_auth import ORIGIN, WEB, WRITE, widget

BUNDLE = "kz.kbtuapp.ios"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
DEVICE = "ab" * 32


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def id_token(nonce: str, sub: str = "001234.abc.0001", key=KEY, **over) -> str:
    now = logic.now()
    claims = {"iss": apple.ISSUER, "aud": BUNDLE, "sub": sub, "iat": now, "exp": now + 600,
              "nonce": hashlib.sha256(nonce.encode()).hexdigest(), "nonce_supported": True, **over}
    head = b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    body = b64(json.dumps(claims).encode())
    sig = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{b64(sig)}"


def proof(sub: str = "001234.abc.0001", **over) -> dict:
    nonce = secrets.token_hex(16)
    return {"token": id_token(nonce, sub, **over), "nonce": nonce, "consent": apple.CONSENT}


@pytest.fixture
def phone(env, monkeypatch):
    """The iPhone app's web view: the browser session, with IOS_BUNDLE_ID set and Apple's key known."""
    _, cfg = env
    cfg = replace(cfg, ios_bundle=BUNDLE)
    monkeypatch.setattr(apple, "_load_keys", lambda kid: KEY.public_key() if kid == "k1" else None)
    return TestClient(server.create(cfg), base_url=ORIGIN), cfg


def apple_in(c, body=None):
    return c.post("/api/web/apple", headers=WRITE, json=body or proof())


def test_apple_makes_an_account_once(phone):
    c, cfg = phone
    assert apple_in(c).status_code == 204
    me = c.get("/api/me", headers=WEB).json()
    assert me["logins"] == {"telegram": False, "apple": True}
    with db.connect(cfg.db_path) as con:
        tg, dm = con.execute("SELECT tg_id, can_dm FROM users WHERE id = ?", (me["id"],)).fetchone()
        assert apple.SYNTH < tg < 2**53 and dm == 0  # no Telegram behind it: the bot never writes
    other = TestClient(c.app, base_url=ORIGIN)
    assert apple_in(other).status_code == 204
    assert other.get("/api/me", headers=WEB).json()["id"] == me["id"]  # the same Apple ID: the same account


def test_apple_token_refused(phone, env):
    c, cfg = phone
    spent = proof()
    assert apple_in(c, spent).status_code == 204
    assert apple_in(TestClient(c.app, base_url=ORIGIN), spent).json()["message"] == "web_login"  # one tap, one sign-in
    now = logic.now()
    for bad in (proof(aud="kz.other"), proof(iss="https://evil"), proof(exp=now - 1), proof(iat=now - apple.FRESH - 5),
                proof(key=OTHER), {**proof(), "nonce": secrets.token_hex(16)}, {**proof(), "consent": "no"},
                {**proof(), "token": "a.b"}, {**proof(), "nonce": "short"}):
        r = TestClient(c.app, base_url=ORIGIN).post("/api/web/apple", headers=WRITE, json=bad)
        assert r.status_code == 403, bad
    assert c.post("/api/web/apple", headers=WEB, json=proof()).json()["message"] == "csrf"  # no Origin: refused
    off, _ = env
    assert TestClient(off.app, base_url=ORIGIN).post("/api/web/apple", headers=WRITE, json=proof()).status_code == 404


def test_telegram_ids_never_in_the_apple_range(phone):
    c, _ = phone
    assert c.get("/api/me", headers=tma(apple.SYNTH + 5)).status_code == 403


def test_link_telegram_to_an_apple_account(phone):
    c, cfg = phone
    assert apple_in(c).status_code == 204
    uid = c.get("/api/me", headers=WEB).json()["id"]
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    assert "oauth.telegram.org/auth" in c.get("/api/me/logins/telegram", headers=WEB).json()["url"]
    c.get("/api/me", headers=tma(816))  # 816 has its own account already: never merged
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(816)).json()["message"] == "telegram_taken"
    old = c.cookies[web_auth.COOKIE]
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(815)).status_code == 204
    assert c.cookies[web_auth.COOKIE] != old  # a new session: the tg_id change ended the old one
    me = c.get("/api/me", headers=WEB).json()
    assert me["id"] == uid and me["logins"] == {"telegram": True, "apple": True}
    assert c.get("/api/me", headers=tma(815)).json()["id"] == uid  # the Mini App now opens the same account
    with db.connect(cfg.db_path) as con:
        assert apple.devices(con, uid) == [DEVICE]  # the iPhone's push carried to the new session
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(817)).json()["message"] == "telegram_linked"


def test_link_and_unlink_apple_on_a_telegram_account(phone):
    c, _ = phone
    assert c.post("/api/web/login", headers=WRITE, json=widget(715)).status_code == 204
    uid = c.get("/api/me", headers=WEB).json()["id"]
    assert c.post("/api/me/logins/apple", headers=WRITE, json=proof("sub.715")).status_code == 204
    fresh = TestClient(c.app, base_url=ORIGIN)
    assert apple_in(fresh, proof("sub.715")).status_code == 204
    assert fresh.get("/api/me", headers=WEB).json()["id"] == uid
    stranger = TestClient(c.app, base_url=ORIGIN)
    assert apple_in(stranger, proof("sub.other")).status_code == 204  # an Apple-made account
    assert stranger.delete("/api/me/logins/apple", headers=WRITE).json()["message"] == "last_login"  # its only way in
    assert c.post("/api/me/logins/apple", headers=WRITE, json=proof("sub.other")).json()["message"] == "apple_taken"
    assert c.delete("/api/me/logins/apple", headers=WRITE).status_code == 204
    assert c.get("/api/me", headers=WEB).json()["logins"] == {"telegram": True, "apple": False}


def test_sign_out_and_deletion_take_the_apple_data(phone):
    c, cfg = phone
    assert apple_in(c).status_code == 204
    assert c.post("/api/me/devices", headers=WRITE, json={"token": "XYZ", "consent": apple.CONSENT}).status_code == 400
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE}).status_code == 403  # no consent
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    assert c.post("/api/web/logout", headers=WRITE).status_code == 204
    with db.connect(cfg.db_path) as con:
        assert not con.execute("SELECT 1 FROM push_devices").fetchone()  # signed out: no more pushes to that phone
    assert apple_in(c).status_code == 204
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    delete_now(c, cfg, WRITE)
    with db.connect(cfg.db_path) as con:
        assert not con.execute("SELECT 1 FROM identities").fetchone() and not con.execute("SELECT 1 FROM push_devices").fetchone()


def test_push_instead_of_a_second_telegram_message(phone, monkeypatch):
    c, cfg = phone
    cfg = replace(cfg, apns_key_id="K", apns_team_id="T", apns_key="pem")
    assert apple_in(c).status_code == 204
    uid = c.get("/api/me", headers=WEB).json()["id"]
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    pushed, telegram = [], []

    async def fake_send(cfg_, token, text, start):
        pushed.append((token, start))
        return "ok"
    monkeypatch.setattr(apns, "_send", fake_send)
    with db.connect(cfg.db_path) as con:
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'backup_ok', 'bo:1', 0)", (uid,))
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'backup_ok', 'bo:2', 0)", (uid,))

    def tg(request):
        if request.url.path.endswith("/sendMessage"):
            telegram.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())
    assert pushed == [(DEVICE, ""), (DEVICE, "")] and not telegram  # one notice per message, on the phone
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE sent_at IS NOT NULL").fetchone()[0] == 2
        # without a phone and without Telegram: nowhere to go, said why
        con.execute("DELETE FROM push_devices")
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'backup_ok', 'bo:3', 0)", (uid,))
    asyncio.run(go())
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT error FROM bot_outbox WHERE ref = 'bo:3'").fetchone()[0] == "no_dm"
    assert apns.plain("<b>Hi</b> &amp; bye") == "Hi & bye"
