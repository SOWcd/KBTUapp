"""The Telegram Login Widget entrance through the real API."""
import hashlib
import hmac
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kbtu import db, logic
from kbtu.logic import web_auth
from test_core import BOT, delete_now, env, login, set_clock, tma  # noqa: F401


ORIGIN = "https://kbtu.sow.kz"
WEB = {"X-KBTU": "1"}
WRITE = {**WEB, "Origin": ORIGIN}


@pytest.fixture
def browser(env):
    client, cfg = env
    return TestClient(client.app, base_url=ORIGIN), cfg


def widget(uid=715, date=None, **profile):
    payload = {"id": uid, "first_name": "Test", "auth_date": logic.now() if date is None else date, **profile}
    check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    key = hashlib.sha256(BOT.encode()).digest()
    return {**payload, "hash": hmac.new(key, check.encode(), hashlib.sha256).hexdigest()}


def sign_in(client, payload=None):
    return client.post("/api/web/login", headers=WRITE, json=payload if payload is not None else widget())


def test_widget_signature(browser):
    c, _ = browser
    bad = {**widget(), "first_name": "Changed"}
    assert sign_in(c, bad).json()["message"] == "web_login"
    assert c.get("/api/me", headers=WEB).status_code == 401


@pytest.mark.parametrize(("age", "status"), [(-31, 403), (-30, 204), (599, 204), (600, 403)])
def test_widget_age_and_clock_skew(browser, monkeypatch, age, status):
    c, _ = browser
    now = logic.now()
    set_clock(monkeypatch, lambda: now)
    assert sign_in(c, widget(date=now - age)).status_code == status


def test_cookie_matches_mini_app_user_and_slides(browser, monkeypatch):
    c, cfg = browser
    start = logic.now()
    current = start
    set_clock(monkeypatch, lambda: current)
    classic = c.get("/api/me", headers=tma(715)).json()
    signed = sign_in(c, widget(username="qa_user"))
    assert signed.status_code == 204
    cookie = signed.headers["set-cookie"]
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=5184000"):
        assert attribute in cookie
    token = c.cookies[web_auth.COOKIE]
    assert len(bytes.fromhex(token)) == 32
    assert "Domain=" not in cookie
    with db.connect(cfg.db_path) as con:
        row = con.execute("SELECT * FROM web_sessions").fetchone()
        assert tuple(row) == (hashlib.sha256(bytes.fromhex(token)).digest(), classic["id"], start, start)
    current += web_auth.IDLE - 5
    me = c.get("/api/me", headers=WEB)
    assert me.json()["id"] == classic["id"]
    assert me.headers["cache-control"] == "private, no-store"
    assert "Max-Age=5184000" in me.headers["set-cookie"]
    current += 10
    assert c.get("/api/me", headers=WEB).status_code == 200
    current += web_auth.IDLE
    assert c.get("/api/me", headers=WEB).status_code == 401


@pytest.mark.parametrize(("role", "days"), [("user", 90), ("moderator", 14), ("admin", 14), ("staff", 14)])
def test_active_session_expires_at_absolute_limit(browser, monkeypatch, role, days):
    c, cfg = browser
    second = TestClient(c.app, base_url=ORIGIN)
    start = current = logic.now()
    set_clock(monkeypatch, lambda: current)
    if role == "staff":
        uid = login(c, 715, "Test")["id"]
        with db.connect(cfg.db_path) as con:
            con.execute("UPDATE students SET consent_version = 'staff' WHERE user_id = ?", (uid,))
    assert sign_in(c).status_code == 204
    assert sign_in(second, widget(first_name="Second")).status_code == 204
    # A change of platform role applies even when the browser session was issued earlier.
    if role in ("moderator", "admin"):
        with db.connect(cfg.db_path) as con:
            con.execute("UPDATE users SET role = ? WHERE tg_id = 715", (role,))
    current = start + days * 86400 // 2
    assert c.get("/api/me", headers=WEB).status_code == 200
    assert second.get("/api/me", headers=WEB).status_code == 200
    current = start + days * 86400 - 1
    with db.connect(cfg.db_path) as con:
        web_auth.forget(con, current)
    assert c.get("/api/me", headers=WEB).status_code == 200
    current += 1
    expired = c.get("/api/me", headers=WEB)
    assert expired.status_code == 401 and expired.json()["message"] == "web_session"
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 1
        web_auth.forget(con, current)
        assert con.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0


def test_new_environment_admin_cannot_resume_old_browser_session(browser, monkeypatch):
    c, cfg = browser
    start = current = logic.now()
    set_clock(monkeypatch, lambda: current)
    assert sign_in(c).status_code == 204
    current = start + 14 * 86400
    c.app.state.cfg = replace(cfg, admins=frozenset({715}))
    assert c.get("/api/me", headers=WEB).status_code == 401
    c.app.state.cfg = cfg
    assert c.get("/api/me", headers=WEB).status_code == 401


def test_logout_revokes_cookie_and_does_not_release_proof(browser):
    c, cfg = browser
    proof = widget()
    assert sign_in(c, proof).status_code == 204
    old = c.cookies[web_auth.COOKIE]
    assert sign_in(c, proof).status_code == 403
    done = c.post("/api/web/logout", headers=WRITE)
    assert done.status_code == 204
    assert "Max-Age=0" in done.headers["set-cookie"]
    assert web_auth.COOKIE not in c.cookies
    assert c.get("/api/me", headers={**WEB, "Cookie": f"{web_auth.COOKIE}={old}"}).status_code == 401
    assert sign_in(c, proof).status_code == 403
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0


@pytest.mark.parametrize("mini_app", [False, True])
def test_logout_all_revokes_only_viewers_browsers(browser, monkeypatch, mini_app):
    c, cfg = browser
    second = TestClient(c.app, base_url=ORIGIN)
    other = TestClient(c.app, base_url=ORIGIN)
    assert sign_in(c).status_code == 204
    assert sign_in(second, widget(first_name="Second")).status_code == 204
    assert sign_in(other, widget(uid=716)).status_code == 204
    token = c.cookies[web_auth.COOKIE]
    url = "/api/web/logout-all"
    caller = other if mini_app else c
    auth = tma(715) if mini_app else {}
    for invalid in (WEB, {"Origin": ORIGIN}, {**WEB, "Origin": "https://other.example"}):
        assert caller.post(url, headers={**auth, **invalid}).json()["message"] == "csrf"
    assert TestClient(c.app, base_url=ORIGIN).post(url, headers=WRITE).status_code == 401
    assert c.get("/api/me", headers=WEB).status_code == 200
    assert second.get("/api/me", headers=WEB).status_code == 200

    # A successful cookie-authenticated request would usually renew its cookie on this tick.
    later = logic.now() + 1
    set_clock(monkeypatch, lambda: later)
    done = caller.post(url, headers={**auth, **WRITE})
    assert done.status_code == 204 and "no-store" in done.headers["cache-control"]
    if mini_app:
        assert "set-cookie" not in done.headers
    else:
        assert len(done.headers.get_list("set-cookie")) == 1
        assert "Max-Age=0" in done.headers["set-cookie"]
        assert web_auth.COOKIE not in c.cookies
    assert c.get("/api/me", headers={**WEB, "Cookie": f"{web_auth.COOKIE}={token}"}).status_code == 401
    assert second.get("/api/me", headers=WEB).status_code == 401
    assert other.get("/api/me", headers=WEB).json()["tg"]["id"] == 716
    assert c.get("/api/me", headers=tma(715)).status_code == 200
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 1


def test_account_erasure_revokes_sessions(browser):
    c, cfg = browser
    login(c, 715, "Test")
    proof = widget()
    assert sign_in(c, proof).status_code == 204
    delete_now(c, cfg, tma(715))
    assert c.get("/api/me", headers=WEB).status_code == 401
    assert sign_in(c, proof).status_code == 403
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0] == 0


def test_platform_ban_revokes_every_session(browser):
    c, cfg = browser
    assert sign_in(c).status_code == 204
    second = TestClient(c.app, base_url=ORIGIN)
    assert sign_in(second, widget(username="qa_user")).status_code == 204
    admin = c.get("/api/me", headers=tma(918)).json()
    target = c.get("/api/me", headers=WEB).json()
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (admin["id"],))
    assert c.post("/api/admin/ban", headers=tma(918), json={"userId": target["id"], "on": True, "reason": "Test ban"}).status_code == 200
    assert sign_in(c, widget(first_name="Banned")).json()["message"] == "banned"
    assert c.post("/api/admin/ban", headers=tma(918), json={"userId": target["id"], "on": False}).status_code == 200
    assert c.get("/api/me", headers=WEB).status_code == 401
    assert second.get("/api/me", headers=WEB).status_code == 401


def test_cookie_csrf_and_credential_precedence(browser):
    c, _ = browser
    proof = widget()
    assert c.post("/api/web/login", json=proof, headers=WEB).status_code == 403
    assert sign_in(c, proof).status_code == 204
    assert c.get("/api/me").status_code == 403
    assert c.get("/api/me", headers={**WEB, "Authorization": "tma invalid"}).json()["message"] == "init_data"
    body = {"lang": "kk"}
    for missing in (WEB, {"Origin": ORIGIN}, {**WEB, "Origin": "https://other.example"}):
        assert c.patch("/api/me", headers=missing, json=body).json()["message"] == "csrf"
        assert c.post("/api/web/logout", headers=missing).status_code == 403
    assert c.patch("/api/me", headers=WRITE, json=body).status_code == 200
    assert c.patch("/api/me", headers=tma(715), json={"lang": "en"}).status_code == 200
    assert c.post("/api/ms/start", headers=WRITE).json()["message"] == "telegram"
    assert c.post("/api/ms/start", headers=tma(715)).status_code == 200


def test_award_shared_from_a_browser_is_the_cards_words(browser, monkeypatch):
    """Outside Telegram there is no card: the share sheet gets the card's own words, plain, and its button's link (the
    award's minted gl_ link, never the bare bot link). Only with the app's header, as every browser write."""
    import httpx
    from kbtu import app as server, texts
    sent = []
    real = httpx.AsyncClient

    def telegram(r):
        sent.append(json.loads(r.content)["result"])
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))
    c, cfg = browser
    assert sign_in(c).status_code == 204
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 715")
    card = {"kind": "gl", "code": "init26", "uses": 1, "days": 7}
    assert c.post("/api/share", headers={"Origin": ORIGIN}, json={**card, "link": True}).status_code == 403
    web = c.post("/api/share", headers=WRITE, json={**card, "link": True}).json()
    assert web["link"].startswith(f"https://t.me/{cfg.bot_username}?startapp=gl_") and "id" not in web
    # the Mini App's card, word for word: the same lines without the bold, the button's link below them
    assert c.post("/api/share", headers=tma(715), json=card).json() == {"id": "prep1"}
    html = sent[0]["input_message_content"]["message_text"]
    assert "<b>" in html and web["text"] == html.replace("<b>", "").replace("</b>", "") and "<" not in web["text"]
    assert texts.plain("<b>A &amp; B</b> &lt;3") == "A & B <3"
