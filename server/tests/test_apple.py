"""The iPhone app: Sign in with Apple, linked sign-ins, push tokens, and one channel per person: push or the bot
(logic/apple.py, apns.py, push.py)."""
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

from kbtu import apns, app as server, bot, db, logic, push
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
    state = secrets.token_hex(16)
    url = c.get(f"/api/me/logins/telegram?state={state}", headers=WEB).json()["url"]
    assert "oauth.telegram.org/auth" in url and f"state%3D{state}" in url  # back to the tab that started it, marked
    for bad in ("", "short", "x" * 40 + "&evil=1"):  # the mark is the tab's own nonce, nothing else rides on the URL
        assert c.get("/api/me/logins/telegram", params={"state": bad}, headers=WEB).status_code == 400
    c.get("/api/me", headers=tma(816))  # 816 has its own account already: never merged
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(816)).json()["message"] == "telegram_taken"
    old = c.cookies[web_auth.COOKIE]
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(815)).status_code == 204
    assert c.cookies[web_auth.COOKIE] != old  # a new session: the tg_id change ended the old one
    me = c.get("/api/me", headers=WEB).json()
    assert me["id"] == uid and me["logins"] == {"telegram": True, "apple": True}
    assert c.get("/api/me", headers=tma(815)).json()["id"] == uid  # the Mini App now opens the same account
    with db.connect(cfg.db_path) as con:
        assert push.live(con, uid, logic.now()) == [(DEVICE, "apns")]  # the iPhone's push carried to the new session
    assert c.post("/api/me/logins/telegram", headers=WRITE, json=widget(817)).json()["message"] == "telegram_linked"


def test_link_and_unlink_apple_on_a_telegram_account(phone):
    c, cfg = phone
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
    assert fresh.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    assert c.delete("/api/me/logins/apple", headers=WRITE).status_code == 204
    assert c.get("/api/me", headers=WEB).json()["logins"] == {"telegram": True, "apple": False}
    # the session Apple opened ends with the unlink (it may be a thief's), its push token with it; mine stays
    assert fresh.get("/api/me", headers=WEB).status_code == 401
    with db.connect(cfg.db_path) as con:
        assert not con.execute("SELECT 1 FROM push_devices").fetchone()
    assert stranger.get("/api/me", headers=WEB).status_code == 200  # another account's sessions untouched


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
    # an Apple account sees its week to change its mind, and can keep itself
    at = c.post("/api/me/delete", headers=WRITE, json={}).json()["deleteAt"]
    assert at and c.get("/api/me", headers=WEB).json()["deleteAt"] == at
    assert c.post("/api/me/keep", headers=WRITE).json()["deleteAt"] is None
    delete_now(c, cfg, WRITE)
    with db.connect(cfg.db_path) as con:
        assert not con.execute("SELECT 1 FROM identities").fetchone() and not con.execute("SELECT 1 FROM push_devices").fetchone()


def _tokens(cfg) -> list:
    with db.connect(cfg.db_path) as con:
        return sorted(r[0] for r in con.execute("SELECT token FROM push_devices"))


def test_push_tokens_bounded_and_withdrawn(phone):
    c, cfg = phone
    assert apple_in(c, proof("sub.many")).status_code == 204
    reg = lambda cl, tok: cl.post("/api/me/devices", headers=WRITE, json={"token": tok, "consent": apple.CONSENT})  # noqa: E731
    for i in range(20):  # one session is one phone: its last token only
        assert reg(c, f"{i:02x}" * 32).status_code == 204
    assert _tokens(cfg) == ["13" * 32]
    phones = [TestClient(c.app, base_url=ORIGIN) for _ in range(apple.DEVICES + 2)]
    for i, p in enumerate(phones):
        assert apple_in(p, proof("sub.many")).status_code == 204 and reg(p, f"{0x40 + i:02x}" * 32).status_code == 204
    assert len(_tokens(cfg)) == apple.DEVICES  # an account's phones: the longest unseen pushed out
    # notifications turned off in iOS Settings: this phone's token goes, the others stay
    last = f"{0x40 + len(phones) - 1:02x}" * 32
    assert last in _tokens(cfg)  # the newest phone is never the one pushed out
    assert phones[-1].delete("/api/me/devices", headers=WRITE).status_code == 204
    assert last not in _tokens(cfg) and len(_tokens(cfg)) == apple.DEVICES - 1


def test_push_stops_when_the_session_expires(phone):
    c, cfg = phone
    assert apple_in(c).status_code == 204
    uid = c.get("/api/me", headers=WEB).json()["id"]
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    with db.connect(cfg.db_path) as con:
        assert push.live(con, uid, logic.now()) == [(DEVICE, "apns")]
        # the session's 90 days are up, the token was seen a minute ago, and the night's sweep hasn't run
        con.execute("UPDATE web_sessions SET created_at = ?", (logic.now() - web_auth.MAX_AGE - 60,))
        assert push.live(con, uid, logic.now()) == []
        assert not con.execute(f"SELECT {push.LIVE.format('?')}", (uid, *push.bounds(logic.now()))).fetchone()[0]
        con.execute("UPDATE web_sessions SET created_at = ?, last_used_at = ?", (logic.now(), logic.now() - web_auth.IDLE - 1))
        assert push.live(con, uid, logic.now()) == []  # idle too long: the same


def _postman(cfg, telegram: list):
    def tg(request):
        if request.url.path.endswith("/sendMessage"):
            telegram.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())


def _queue(cfg, uid: int, ref: str, kind: str = "backup_ok") -> None:
    with db.connect(cfg.db_path) as con:
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, ?, ?, 0)", (uid, kind, ref))


def _sent(cfg, ref: str) -> tuple:
    with db.connect(cfg.db_path) as con:
        return tuple(con.execute("SELECT sent_at IS NOT NULL, error FROM bot_outbox WHERE ref = ?", (ref,)).fetchone())


def _dead(cfg) -> list:
    with db.connect(cfg.db_path) as con:
        return [r[0] is not None for r in con.execute("SELECT dead_at FROM push_devices")]


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
    monkeypatch.setattr(apns, "send", fake_send)
    _queue(cfg, uid, "bo:1")
    _queue(cfg, uid, "bo:2")
    _postman(cfg, telegram)
    assert pushed == [(DEVICE, ""), (DEVICE, "")] and not telegram  # one notice per message, on the phone
    assert _sent(cfg, "bo:1") == (1, None) and _sent(cfg, "bo:2") == (1, None)
    # without a phone and without Telegram: nowhere to go, said why
    with db.connect(cfg.db_path) as con:
        con.execute("DELETE FROM push_devices")
    _queue(cfg, uid, "bo:3")
    _postman(cfg, telegram)
    assert _sent(cfg, "bo:3") == (0, "no_dm")
    assert apns.plain("<b>Hi</b> &amp; bye") == "Hi & bye"


@pytest.fixture
def both(phone, monkeypatch):
    """A Telegram account the bot may write to, with the iPhone app's live token and APNs on; got: what APNs answers."""
    c, cfg = phone
    cfg = replace(cfg, apns_key_id="K", apns_team_id="T", apns_key="pem")
    assert c.post("/api/web/login", headers=WRITE, json=widget(715)).status_code == 204
    uid = c.get("/api/me", headers=WEB).json()["id"]
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET can_dm = 1 WHERE id = ?", (uid,))
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    pushed, got = [], ["ok"]

    async def fake_send(cfg_, token, text, start):
        pushed.append(token)
        return got[0]
    monkeypatch.setattr(apns, "send", fake_send)
    return c, cfg, uid, pushed, got


def test_one_channel_push_while_the_token_is_live(both):
    c, cfg, uid, pushed, _ = both
    assert c.get("/api/me", headers=WEB).json()["notify"] == {"via": "app", "app": True}
    telegram: list = []
    _queue(cfg, uid, "bo:1")
    _postman(cfg, telegram)
    assert pushed == [DEVICE] and not telegram and _sent(cfg, "bo:1") == (1, None)  # the app by default, never both


def test_a_failed_push_goes_to_the_bot_at_once_and_kills_the_token(both):
    c, cfg, uid, pushed, got = both
    got[0] = "failed"
    telegram: list = []
    _queue(cfg, uid, "bo:1")
    _postman(cfg, telegram)
    assert pushed == [DEVICE] and len(telegram) == 1 and _sent(cfg, "bo:1") == (1, None)  # the same round, by the bot
    assert _dead(cfg) == [True]
    assert c.get("/api/me", headers=WEB).json()["notify"]["app"] is False
    _queue(cfg, uid, "bo:2")
    _postman(cfg, telegram)
    assert pushed == [DEVICE] and len(telegram) == 2  # a dead token is not tried again: the bot alone
    # the app's next launch registers the token again: live, the app again
    assert c.post("/api/me/devices", headers=WRITE, json={"token": DEVICE, "consent": apple.CONSENT}).status_code == 204
    assert _dead(cfg) == [False]
    got[0] = "ok"
    _queue(cfg, uid, "bo:3")
    _postman(cfg, telegram)
    assert pushed == [DEVICE, DEVICE] and len(telegram) == 2


def test_a_gone_token_is_dropped_and_apple_down_keeps_it(both):
    c, cfg, uid, pushed, got = both
    telegram: list = []
    got[0] = "down"  # no word about the token (Apple unreachable, our key): the bot this time, the token kept
    _queue(cfg, uid, "bo:1")
    _postman(cfg, telegram)
    assert len(telegram) == 1 and _dead(cfg) == [False]
    got[0] = "gone"
    _queue(cfg, uid, "bo:2")
    _postman(cfg, telegram)
    assert len(telegram) == 2 and _dead(cfg) == []


def test_a_stale_token_counts_for_nothing(both):
    c, cfg, uid, pushed, _ = both
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE push_devices SET created_at = ?", (logic.now() - push.STALE - 1,))
    assert c.get("/api/me", headers=WEB).json()["notify"]["app"] is False
    telegram: list = []
    _queue(cfg, uid, "bo:1")
    _postman(cfg, telegram)
    assert not pushed and len(telegram) == 1


def test_telegram_picked_in_settings(both):
    c, cfg, uid, pushed, _ = both
    assert c.patch("/api/me", headers=WRITE, json={"notifyVia": "sms"}).status_code == 400
    assert c.patch("/api/me", headers=WRITE, json={"notifyVia": "telegram"}).status_code == 200
    assert c.get("/api/me", headers=WEB).json()["notify"] == {"via": "telegram", "app": True}
    telegram: list = []
    _queue(cfg, uid, "bo:1")
    _postman(cfg, telegram)
    assert not pushed and len(telegram) == 1  # Telegram alone, the live token unused
    # the bot can't write any more (blocked): the app is the one channel left
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (uid,))
    _queue(cfg, uid, "bo:2")
    _postman(cfg, telegram)
    assert pushed == [DEVICE] and len(telegram) == 1 and _sent(cfg, "bo:2") == (1, None)
    assert c.patch("/api/me", headers=WRITE, json={"notifyVia": "app"}).status_code == 200


def test_group_things_and_forum_comments_stay_telegram(both):
    _, cfg, _, _, _ = both
    m = {"pushable": 1, "kind": "fch_comments"}
    assert not bot._pushes(cfg, m, "") and not bot._pushes(cfg, {**m, "kind": "tgc_reply"}, "")
    assert not bot._pushes(cfg, {**m, "kind": "credit_ask"}, "") and bot._pushes(cfg, {**m, "kind": "backup_ok"}, "")
    assert not bot._pushes(cfg, {"pushable": 1, "kind": "backup_ok"}, [[{"text": "x", "start": "y"}]])  # a keyboard
    assert push.on(cfg) and not push.on(replace(cfg, apns_key=""))
