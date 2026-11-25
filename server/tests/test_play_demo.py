"""Google Play's reviewer: the PLAY_DEMO link, its read-only demo account, and the Android app's assetlinks.json."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kbtu import admin, app as server, config, db
from kbtu.logic import web_auth
from test_core import env, login, tma  # noqa: F401

ORIGIN = "https://kbtu.sow.kz"
WEB = {"X-KBTU": "1"}
KEY = "k" * 40
CERT = ":".join(["AB"] * 32)


@pytest.fixture
def demo(env):
    _, cfg = env
    cfg = replace(cfg, play_demo=KEY, android_certs=(CERT,))
    return TestClient(server.create(cfg), base_url=ORIGIN), cfg


def enter(c, key=KEY):
    return c.get("/play-demo", params={"k": key}, follow_redirects=False)


def test_off_by_default(env):
    c, _ = env
    assert enter(c).status_code == 404
    assert c.get("/.well-known/assetlinks.json").status_code == 404


def test_assetlinks(demo):
    c, _ = demo
    r = c.get("/.well-known/assetlinks.json")
    assert r.json() == [{"relation": ["delegate_permission/common.handle_all_urls"],
                         "target": {"namespace": "android_app", "package_name": "kz.kbtuapp", "sha256_cert_fingerprints": [CERT]}}]


def test_cert_env_checked():
    assert config._certs(f" {CERT.lower()} , nope,") == (CERT,)
    assert config._play_demo("short") == "" and config._play_demo(KEY) == KEY


def test_demo_reads_are_real_get_routes(demo):
    c, _ = demo
    gets = {r.path for r in c.app.routes if "GET" in (getattr(r, "methods", None) or ())}
    assert web_auth.DEMO_READS <= gets


def test_wrong_key_is_404(demo):
    c, _ = demo
    for key in ("", "k" * 39, "k" * 41, KEY.upper()):
        assert enter(c, key).status_code == 404
    assert web_auth.COOKIE not in c.cookies


def test_demo_reads_the_catalogue_alone(demo):
    c, cfg = demo
    student = login(c, 50, "real")
    r = enter(c)
    assert r.status_code == 303 and r.headers["location"] == "/" and "HttpOnly" in r.headers["set-cookie"]
    me = c.get("/api/me", headers=WEB).json()
    assert me["student"] is None and me["id"] != student["id"]
    assert c.get("/api/events", headers=WEB).status_code == 200
    # a person, a write, a staff header: refused before any route runs
    assert c.get(f"/api/users/{student['id']}", headers=WEB).json()["message"] == "demo"
    assert c.post("/api/web/logout-all", headers={**WEB, "Origin": ORIGIN}).json()["message"] == "demo"
    assert c.get("/api/events", headers={**WEB, "X-Staff-Org": "1"}).status_code == 403
    with db.connect(cfg.db_path) as con:
        row = con.execute("SELECT tg_id, role, can_dm FROM users WHERE id = ?", (me["id"],)).fetchone()
        assert tuple(row) == (web_auth.DEMO_TG_ID, "user", 0)
        con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (me["id"],))
    # promoted by mistake: still nobody in particular, and no new sign-in
    assert c.get("/api/admin/staff", headers=WEB).status_code == 403
    assert c.get("/api/me", headers=WEB).status_code == 200
    assert enter(TestClient(c.app, base_url=ORIGIN)).status_code == 403


def test_off_ends_the_sessions(demo):
    c, cfg = demo
    enter(c)
    off = TestClient(server.create(replace(cfg, play_demo="")), base_url=ORIGIN, cookies=dict(c.cookies))
    assert off.get("/api/me", headers=WEB).status_code == 401


def test_admin_prints_and_revokes(demo, monkeypatch, capsys):
    c, cfg = demo
    monkeypatch.setattr(config, "load", lambda: cfg)
    admin.main(["play-demo"])
    assert capsys.readouterr().out.strip() == f"https://{cfg.domain}/play-demo?k={KEY}"
    enter(c)
    assert c.get("/api/me", headers=WEB).status_code == 200
    admin.main(["play-demo", "revoke"])
    assert c.get("/api/me", headers=WEB).status_code == 401
    monkeypatch.setattr(config, "load", lambda: replace(cfg, play_demo=""))
    with pytest.raises(SystemExit):
        admin.main(["play-demo"])
