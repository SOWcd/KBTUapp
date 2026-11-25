"""Fixes from Aldiyar's security report (Nov 25): the pairing cap's address, the response headers, deploy hygiene.
The Microsoft sign-in's PKCE is in test_sign_in.py."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from kbtu import app as server
from test_core import env  # noqa: F401  (env: the fixture)

ROOT = Path(__file__).resolve().parents[2]


def test_pair_address_only_through_proxy(env, monkeypatch):
    """A request straight to the origin (a public peer) is counted by its own address whatever Cloudflare header it
    sends, so it can't take every pairing code; behind our own proxy (a private peer) the header names the visitor."""
    from kbtu import checkin
    c, _ = env
    monkeypatch.setattr(checkin, "PAIR_PER_IP", 1)
    direct = TestClient(c.app, client=("93.184.216.34", 40000))
    assert direct.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.1"}).status_code == 200
    assert direct.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.2"}).status_code == 429
    proxy = TestClient(c.app, client=("172.18.0.3", 40000))
    assert proxy.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.3"}).status_code == 200
    assert proxy.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.4"}).status_code == 200
    assert proxy.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.4"}).status_code == 429


def test_security_headers(env):
    """Every answer: no sniffing, HTTPS only, framed only by Telegram Web or us; a page's own stricter CSP stays."""
    c, _ = env
    for r in (c.get("/"), c.get("/healthz")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["strict-transport-security"].startswith("max-age=")
        assert r.headers["content-security-policy"] == "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"

    async def strict(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-security-policy", b"frame-ancestors 'none'")]})
        await send({"type": "http.response.body", "body": b""})
    r = TestClient(server._Secure(strict)).get("/")
    assert r.headers.get_list("content-security-policy") == ["frame-ancestors 'none'"] and r.headers["x-content-type-options"] == "nosniff"


def test_deploy_hygiene():
    """Forwarded headers are trusted only from private peers, and every workflow names its token's permissions."""
    cmd = (ROOT / "Dockerfile").read_text()
    assert "--forwarded-allow-ips '*'" not in cmd and "--forwarded-allow-ips '127.0.0.1," in cmd
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        assert re.search(r"^permissions:", wf.read_text(), re.M), wf.name
