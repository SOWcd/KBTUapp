"""Google Play's reviewer: the PLAY_DEMO link, its read-only demo account, and the Android app's assetlinks.json."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kbtu import admin, app as server, config, db, logic
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


def test_off_then_on_again_keeps_them_ended(demo):
    """REVIEW-322 #3: PLAY_DEMO off, then a new key: a cookie kept from before is still dead; real sessions stay"""
    c, cfg = demo
    enter(c)
    kept = dict(c.cookies)
    real = login(c, 51, "real")["id"]
    with db.connect(cfg.db_path) as con:
        with db.tx(con):
            real_token = web_auth.issue(con, real, "", logic.now())
    server.create(replace(cfg, play_demo=""))  # a deploy without it
    on = TestClient(server.create(replace(cfg, play_demo="b" * 40)), base_url=ORIGIN, cookies=kept)
    assert on.get("/api/me", headers=WEB).status_code == 401
    other = TestClient(on.app, base_url=ORIGIN, cookies={web_auth.COOKIE: real_token})
    assert other.get("/api/me", headers=WEB).json()["id"] == real


def test_demo_sees_no_people(demo):
    """REVIEW-322 #1: a club's leaders, the support contacts and the donation number aren't the reviewer's to see"""
    c, cfg = demo
    c = TestClient(server.create(replace(cfg, donate_phone="+77001234567")), base_url=ORIGIN)
    pres, sup = login(c, 52, "pres"), login(c, 53, "sup")
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET tg_username = 'Sowers' WHERE id = ?", (sup["id"],))
        for oid, hidden in ((1, 1), (2, 0)):
            con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, members_hidden, created_at) "
                        "VALUES (?, ?, 'club', 'Club', 'C', 'laptop_3d', ?, 0)", (oid, f"c{oid}", hidden))
            con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", (oid, pres["id"]))
    # an ordinary person still sees them all (not 53 itself: its Telegram sign-in would rewrite the username)
    me = c.get("/api/me", headers=tma(52)).json()
    assert me["support"][0]["id"] == sup["id"] and me["donate"]
    for oid in (1, 2):
        assert c.get(f"/api/orgs/{oid}", headers=tma(52)).json()["leaders"][0]["person"]["id"] == pres["id"]
    enter(c)
    r = c.get("/api/me", headers=WEB)
    assert r.json()["support"] == [] and "donate" not in r.json() and "Sowers" not in r.text and "7001234567" not in r.text
    for oid in (1, 2):
        r = c.get(f"/api/orgs/{oid}", headers=WEB)
        assert r.status_code == 200 and r.json()["leaders"] == [] and "Testov" not in r.text


def test_demo_reads_write_no_tickets(demo):
    """REVIEW-322 #2: an expired hold and its waitlist stay as they are for the reviewer's GETs; anyone else's sweeps"""
    c, cfg = demo
    org, a, b = login(c, 54, "org"), login(c, 55, "a"), login(c, 56, "b")
    enter(c)
    t = logic.now()
    with db.connect(cfg.db_path) as con:
        con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT', 'IT', 'laptop_3d', 0)")
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (org["id"],))
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, created_by, created_at, updated_at)
            VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 1, ?, 0, 0)""", (t + 86400, org["id"]))
        con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, created_at, updated_at)
            VALUES (1, ?, 'hold', 'TA', ?, 0, 0)""", (a["id"], t - 60))
        con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, waitlisted_at, created_at, updated_at)
            VALUES (1, ?, 'waitlist', 'TB', 1, 1, 1)""", (b["id"],))

        def state():  # the two people's seats and their bot messages
            return ([tuple(r) for r in con.execute("SELECT user_id, status, cancel_reason, hold_until, updated_at FROM registrations ORDER BY id")],
                    [tuple(r) for r in con.execute("SELECT user_id, kind, ref FROM bot_outbox WHERE user_id IN (?, ?) ORDER BY rowid",
                                                   (a["id"], b["id"]))])

        before = state()
        for path in ("/api/events", "/api/events/1", "/api/events/999999"):
            assert c.get(path, headers=WEB).status_code < 500, path
        assert state() == before
        c.get("/api/events", headers=tma(54))  # an ordinary read still gives the seat back and moves the waitlist
        assert state() != before
        assert tuple(con.execute("SELECT status, cancel_reason FROM registrations WHERE user_id = ?", (a["id"],)).fetchone()) \
            == ("cancelled", "hold_expired")


@pytest.mark.parametrize("odd", ["role = 'admin'", "is_founder = 1", "banned_at = 1", "student"])
def test_revoke_whatever_the_row(demo, monkeypatch, capsys, odd):
    """REVIEW-322 #4: revoke never refuses: an odd demo row (a role, a founder, a ban, a student row) is when it's needed"""
    c, cfg = demo
    monkeypatch.setattr(config, "load", lambda: cfg)
    real = login(c, 57, "real")
    enter(c)
    kept = dict(c.cookies)
    with db.connect(cfg.db_path) as con:
        uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (web_auth.DEMO_TG_ID,)).fetchone()[0]
        with db.tx(con):
            real_token = web_auth.issue(con, real["id"], "", logic.now())
            if odd == "student":
                con.execute("UPDATE students SET user_id = ? WHERE user_id = ?", (uid, real["id"]))
            else:
                con.execute(f"UPDATE users SET {odd} WHERE id = ?", (uid,))
    admin.main(["play-demo", "revoke"])
    admin.main(["play-demo", "revoke"])  # again: nothing left, no error
    assert capsys.readouterr().out.count("demo sessions signed out") == 2
    with db.connect(cfg.db_path) as con:
        con.execute("UPDATE users SET role = 'user', is_founder = 0, banned_at = NULL WHERE id = ?", (uid,))
        con.execute("UPDATE students SET user_id = ? WHERE user_id = ?", (real["id"], uid))
        assert con.execute("SELECT COUNT(*) FROM web_sessions WHERE user_id = ?", (uid,)).fetchone()[0] == 0
    assert TestClient(c.app, base_url=ORIGIN, cookies=kept).get("/api/me", headers=WEB).status_code == 401
    assert TestClient(c.app, base_url=ORIGIN, cookies={web_auth.COOKIE: real_token}).get("/api/me", headers=WEB).status_code == 200


def test_revoke_without_a_demo_account(demo, monkeypatch, capsys):
    _, cfg = demo
    monkeypatch.setattr(config, "load", lambda: cfg)
    admin.main(["play-demo", "revoke"])
    assert capsys.readouterr().out.strip() == "demo sessions signed out"
    with db.connect(cfg.db_path) as con:
        assert con.execute("SELECT 1 FROM users WHERE tg_id = ?", (web_auth.DEMO_TG_ID,)).fetchone() is None


def test_link_keeps_a_real_session(demo):
    """REVIEW-322 #5: a leaked link opened where a real person is signed in changes nothing; no, an old or a demo cookie: in"""
    c, cfg = demo
    real = login(c, 58, "real")
    with db.connect(cfg.db_path) as con:
        with db.tx(con):
            token = web_auth.issue(con, real["id"], "", logic.now())
    host = ORIGIN.removeprefix("https://")  # the jar's own key: a demo cookie later replaces it, never sits beside it
    c.cookies.set(web_auth.COOKIE, token, domain=host)
    r = enter(c)
    assert r.status_code == 303 and r.headers["location"] == "/" and "set-cookie" not in r.headers
    assert c.get("/api/me", headers=WEB).json()["id"] == real["id"]
    for cookie in ("", "0" * 64):  # none, or one that's gone: the demo
        fresh = TestClient(c.app, base_url=ORIGIN)
        if cookie:
            fresh.cookies.set(web_auth.COOKIE, cookie, domain=host)
        assert enter(fresh).status_code == 303
        demo_token = fresh.cookies[web_auth.COOKIE]
        assert fresh.get("/api/me", headers=WEB).json()["id"] != real["id"]
        assert enter(fresh).status_code == 303 and fresh.cookies[web_auth.COOKIE] != demo_token  # the demo again: a new one


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
