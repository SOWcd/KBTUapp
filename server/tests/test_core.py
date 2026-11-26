"""The core loop through the HTTP layer: a KBTU student (written into the database), a president creates and publishes an
event, students register, the waitlist moves, the door scans tickets. Run from server/: .venv/bin/pytest -q"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

import pytest

from kbtu import bot, bot_dm, config, db, logic, app as server, texts

# the shared helpers live in helpers.py; re-exported here, where every test file has always imported them from
from helpers import BOT, DB, INTAKE, _board_on, _club_runs, _csv, _paired, delete_now, env, login, set_clock, tma  # noqa: F401


def test_core_loop(env):
    c, cfg = env
    assert c.get("/api/me").status_code == 403                       # no initData
    guest = c.get("/api/me", headers=tma(10, "Ali")).json()
    assert guest["student"] is None and guest["tg"]["firstName"] == "Ali"

    me = login(c, 10, "ali")
    assert me["student"]["studentId"] == "24Bali" and me["name"] == "Ali T"
    assert c.get("/api/me/schedule", headers=tma(10)).json()[0]["subject"] == "Calculus"
    con = db.connect(cfg.db_path)

    # a president (set by hand for the pilot) creates and publishes an event with one seat
    pres = login(c, 20, "pres")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    body = {"title": "Hack night", "place": "305", "startsAt": start, "endsAt": start + 7200, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 1}
    assert c.post("/api/orgs/1/events", headers=tma(10), json=body).json()["error"] == "forbidden"   # not in the club
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert ev["status"] == "draft"
    assert c.get(f"/api/events/{ev['id']}", headers=tma(10)).status_code == 404   # drafts are the team's
    assert c.post(f"/api/events/{ev['id']}/publish", headers=tma(20)).json()["status"] == "published"
    eid = ev["id"]

    # guests can look but not act; students register; the second one waits
    r = c.post(f"/api/events/{eid}/registration", headers=tma(30, "Zhan"))
    assert r.status_code == 401 and r.json()["error"] == "need_student"
    zhan = login(c, 30, "zhan")
    ali_card = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()
    assert ali_card["my"]["status"] == "going" and ali_card["taken"] == 1
    assert c.post(f"/api/events/{eid}/registration", headers=tma(30), json={}).json()["my"]["status"] == "waitlist"

    # Ali drops out: Zhan gets the seat and a bot message is queued
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).json()["my"]["status"] == "cancelled"
    ticket = c.get(f"/api/events/{eid}", headers=tma(30)).json()["my"]
    assert ticket["status"] == "going"
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'seat_free'", (zhan["id"],)).fetchone()

    # the door: shut an hour before, opened early by the President; then ok, then already, then a code that isn't ours
    scan = lambda code: c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": code}).json()
    assert scan("KBTU" + ticket["ticketCode"])["result"] == "not_open"
    assert c.post(f"/api/events/{eid}/door-open", headers=tma(20)).status_code == 200
    code = ticket["ticketCode"]
    assert re.fullmatch(r"[2-9A-HJKMNP-Z]{4}", code)  # short, nothing to mix up (no 0/O, 1/I/L)
    first = scan("KBTU" + code)  # what the ticket QR holds
    assert first["result"] == "ok" and first["came"] == 1 and first["person"]["name"] == "Zhan T"
    assert scan(f" {code[:2].lower()} - {code[2:]}")["result"] == "already"  # typed by hand
    assert scan("KBTU-" + code)["result"] == "already"  # the QR before Oct 5
    assert scan("KBTU-NOPE")["result"] == "not_found"
    assert [a["fullName"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()] == ["Testov Zhan"]
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(30)).json()["error"] == "forbidden"


def test_multi_day_event(env, monkeypatch):
    """A casting of ten days: no 24 h cap; listed and live all along, the door open all along, one reminder before the start."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    pres, ali = login(c, 20, "pres"), login(c, 10, "ali")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3 * 3600
    end = start + 10 * 86400
    body = {"seats": None, "title": "Casting", "place": "305", "startsAt": start, "endsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["error"] == "bad_input"   # ends when it starts
    assert c.post("/api/orgs/1/events", headers=tma(20), json={**body, "endsAt": start + 40 * 86400}).json()["error"] == "bad_input"  # days, not years
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "endsAt": end}).json()["id"]
    assert c.post(f"/api/events/{eid}/publish", headers=tma(20)).json()["endsAt"] == end
    code = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["ticketCode"]
    assert [r[0] for r in con.execute("SELECT send_after FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h'", (ali["id"],))] == [start - 7200]
    set_clock(monkeypatch, lambda: start + 5 * 86400)   # day six
    assert eid in [e["id"] for e in c.get("/api/events", headers=tma(10)).json()]
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": code}).json()["result"] == "ok"
    set_clock(monkeypatch, lambda: end + 60)
    assert eid not in [e["id"] for e in c.get("/api/events", headers=tma(10)).json()]
    con.close()


def test_sign_in_rules(env, monkeypatch, capsys):
    c, cfg = env
    login(c, 10, "ali")
    # a changed student ID: the admin unlinks it by hand, then the next sign-in links afresh
    from kbtu import admin
    monkeypatch.setattr(config, "load", lambda: cfg)
    admin.main(["unlink", "10"])
    assert c.get("/api/me", headers=tma(10)).json()["student"] is None
    assert login(c, 10, "bek")["student"]["studentId"] == "24Bbek"
    # staff (DMP, KBTU's IT testing the app) aren't students: verified by hand, they act, take no card number, aren't counted
    assert c.get("/api/friends", headers=tma(13)).status_code == 401
    admin.main(["staff", "13", "Test", "Tester", "IT"])
    me = c.get("/api/me", headers=tma(13)).json()
    assert me["student"]["school"] == "IT" and me["no"] is None and c.get("/api/friends", headers=tma(13)).status_code == 200
    admin.main(["mark", "13", "idea"])  # the idea author's blue seal: one person, by name everywhere
    mine = c.get("/api/me", headers=tma(13)).json()
    assert mine["mark"] == "idea" and c.get(f"/api/users/{mine['id']}", headers=tma(10)).json()["mark"] == "idea"
    capsys.readouterr()
    admin.main(["stats"])  # counts only
    stats = {name: n for n, name in (line.split(None, 1) for line in capsys.readouterr().out.splitlines())}
    assert stats["signed in with KBTU"] == "1" and stats["staff"] == "1"
    admin.main(["achstats"])  # counts only, the staff left out, the hand-given ones skipped
    out = capsys.readouterr().out
    assert out.startswith("1 students, 0 came") and "regular" in out and "first50" not in out
    # a tester who signed in as a student turns staff: the number is retired (a gap: moving the later ones down would
    # reuse a deleted account's burnt number), and signing in again brings no number back
    login(c, 14, "it"), login(c, 15, "zhan")
    nos = lambda: [c.get("/api/me", headers=tma(u)).json()["no"] for u in (10, 14, 15)]
    assert nos() == [1, 2, 3]
    admin.main(["staff", "14"])
    assert nos() == [1, None, 3]
    login(c, 14, "it")
    assert nos() == [1, None, 3]
    # signed in from a wrong Telegram (10): the whole account moves to the real one (12), which only opened the app
    c.get("/api/me", headers=tma(12))
    before = c.get("/api/me", headers=tma(10)).json()
    login(c, 16, "dan")
    with pytest.raises(SystemExit):
        admin.main(["move", "10", "16"])  # the target holds its own KBTU account: refused
    admin.main(["move", "10", "12"])
    moved = c.get("/api/me", headers=tma(12)).json()
    assert moved["id"] == before["id"] and moved["no"] == before["no"] and moved["student"]["studentId"] == "24Bbek"
    assert c.get("/api/me", headers=tma(10)).json()["student"] is None
    admin.main(["move", "12", "10"])  # and back
    assert c.get("/api/me", headers=tma(10)).json()["id"] == before["id"]


def test_frontend(env):
    c, _ = env
    assert "<title>app</title>" in c.get("/clubs/it").text   # SPA fallback
    r = c.get("/demo/", follow_redirects=False)              # the in-browser demo went: its old links open the app
    assert r.status_code == 302 and r.headers["location"].startswith("https://t.me/")
    r = c.get("/assets/a.js")
    assert "immutable" in r.headers["cache-control"]
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert "immutable" in c.get("/map/u1/o.webp").headers["cache-control"]
    assert c.get("/api/nope", headers=tma(1)).status_code == 404
    r = c.get("/../../etc/passwd")
    assert "<title>app</title>" in r.text and "root:" not in r.text     # never leaves dist


def test_ears(env):
    """Whatever someone writes to the bot is answered with a button into the app, in their language (the app's first);
    /start's parameter goes on to the app; group chats and what piled up before anyone listened are left alone."""
    import asyncio
    import json
    import httpx
    from kbtu import bot, texts
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET lang = 'kk', can_dm = 0 WHERE tg_id = 10")
    t = bot.now()
    msgs = [{"chat": {"id": 10, "type": "private"}, "from": {"id": 10, "language_code": "ru"}, "date": t, "text": "/start ev_5"},
            {"chat": {"id": 11, "type": "private"}, "from": {"id": 11, "language_code": "en"}, "date": t, "text": "hi"},
            {"chat": {"id": -5, "type": "group"}, "from": {"id": 12}, "date": t, "text": "/start"},
            {"chat": {"id": 13, "type": "private"}, "from": {"id": 13}, "date": t - 3600, "text": "/start"}]
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7 + i, "message": m} for i, m in enumerate(msgs)]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot.hear(cfg, http, 0)
    assert asyncio.run(go()) == 11 and [m["chat_id"] for m in sent] == [10, 11]
    url = lambda m: m["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert sent[0]["text"] == texts.bot_message("kk", "welcome")[0] and url(sent[0]).endswith("?startapp=ev_5")
    assert sent[1]["text"] == texts.bot_message("en", "welcome")[0] and url(sent[1]).endswith("?startapp")
    assert con.execute("SELECT can_dm FROM users WHERE tg_id = 10").fetchone()[0] == 1

    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 10")   # banned: the bot doesn't answer him at all
    sent.clear()
    assert asyncio.run(go()) == 11 and [m["chat_id"] for m in sent] == [11]


def test_postman(env, monkeypatch):
    """Queued messages go out once, in the user's language, with a button into the app; a block stops them; two postmen
    reading one queue (a deploy's old and new container, side by side for a few seconds) still send a message once."""
    import asyncio
    import json
    import httpx
    from kbtu import bot, outbox
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET can_dm = 1, lang = 'kk'")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (20003, 1, 'published', 'Hack <night>', '305', 1791090000, 'laptop_3d', '#3B6BFF', 0, 0)""")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 10").fetchone()[0]
    for kind, ref in (("usage_week", "uw:20003"), ("seat_free", "event:20003"), ("new_event", "event:20003"), ("event_changed", "event:404:1")):
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, ?, ?, 0)", (uid, kind, ref))
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}}) if len(sent) == 1 else httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await outbox.send_due(cfg, http)
            await outbox.send_due(cfg, http)  # nothing left to send twice
    asyncio.run(go())
    first = sent[0]
    from kbtu import texts
    kk = texts.bot_message("kk", "seat_free", title="Hack <night>", when=texts.when(1791090000, "kk"), place="305")[0]
    assert first["chat_id"] == 10 and first["text"] == kk and "Hack &lt;night&gt;" in kk   # Kazakh, escaped
    assert first["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=tk_20003")
    state = dict(con.execute("SELECT kind, COALESCE(error, 'sent') FROM bot_outbox").fetchall())
    assert state == {"usage_week": "gone", "seat_free": "sent", "new_event": "blocked", "event_changed": "gone"} and len(sent) == 2
    assert con.execute("SELECT can_dm FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0

    con.execute("DELETE FROM bot_outbox")
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'seat_free', 'event:20003', 0)", (uid,))
    stale = bot.rows(con, "SELECT b.*, u.tg_id, u.lang, u.can_dm FROM bot_outbox b JOIN users u ON u.id = b.user_id")
    sent.clear()

    async def postman():
        ok = lambda r: (sent.append(r), httpx.Response(200, json={"ok": True, "result": {}}))[1]
        async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
            await outbox.send_due(cfg, http)
    asyncio.run(postman())                               # the new container's postman sends it
    real_rows = outbox.rows
    monkeypatch.setattr(outbox, "rows", lambda con, q, *a: stale if "FROM bot_outbox" in q else real_rows(con, q, *a))  # the old one read the queue a moment earlier
    asyncio.run(postman())
    assert len(sent) == 1


def test_workers_share_state(env):
    """Several worker processes are several apps over one database file: the "To calendar" link's key comes from the
    env, so a link signed by one opens on another."""
    _, cfg = env
    key = logic.seats.ICS_KEY
    server.create(cfg)
    assert logic.seats.ICS_KEY == key
    server.create(config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=cfg.db_path, web_dist=cfg.web_dist, background=False, seed=False))
    assert logic.seats.ICS_KEY != key


def test_bad_numbers_are_bad_input(env):
    """Hand-made requests get a 400, never a crash: an id past SQLite's 64-bit integers anywhere, a level that isn't one."""
    c, cfg = env
    login(c, 61, "ali")
    A = tma(61, "Ali")
    huge = 2 ** 70
    assert c.get(f"/api/events/{huge}", headers=A).status_code == 400
    assert c.post("/api/posts/read", headers=A, json={"ids": [huge]}).status_code == 400
    assert c.post("/api/reports", headers=A, json={"target": "post", "id": huge, "reason": "spam"}).status_code == 400
    assert c.post("/api/me/unlocked", headers=A, json={"code": "first50", "level": "abc"}).status_code == 400
    assert c.post("/api/me/unlocked", headers=A, json={"code": "first50", "level": 1}).status_code == 200


def test_every_api_route_needs_telegram(env):
    """No /api route answers with data to a request without Telegram's initData — a new route that forgot its viewer
    fails here. The calendar file carries its own signature (§4.2); /show's pairing code is the laptop's, no Telegram
    there (it opens nothing until an organizer binds it: test_screen_pairing); android.html's step counts answer nothing
    and hold no person (test_android_page_counts_signed_out)."""
    import re as _re
    c, cfg = env
    open_ok = {("GET", "/api/events/{eid}/ics"), ("POST", "/api/screen/pair"), ("POST", "/api/stats/andr")}
    for r in c.app.routes:
        path, methods = getattr(r, "path", ""), getattr(r, "methods", set()) or set()
        if not path.startswith("/api/"):
            continue
        for m in methods - {"HEAD", "OPTIONS"}:
            if (m, path) in open_ok:
                continue
            url = _re.sub(r"\{[^}]+\}", "1", path)
            res = c.request(m, url, json={})
            assert res.status_code >= 400, (m, path, res.status_code)


def test_head_for_monitors(env):
    """An uptime monitor's HEAD gets 200 like a GET (UptimeRobot showed the app down with 405)."""
    c, _ = env
    assert c.head("/").status_code == 200 and c.get("/").status_code == 200


def test_exit_link(env):
    """"Help me get out": kbtu.sow.kz/exit goes to the app's exit screen; /exit in the bot answers with
    a message and its button, to forward anywhere."""
    c, cfg = env
    r = c.get("/exit", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("?startapp=exit")
    con = db.connect(cfg.db_path)
    msg = {"chat": {"id": 5, "type": "private"}, "date": int(time.time()), "text": "/exit", "from": {"language_code": "ru"}}
    out = bot_dm._welcome(con, cfg, msg)
    assert out["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("?startapp=exit")
    msg["text"] = "/start"
    assert bot_dm._welcome(con, cfg, msg)["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("?startapp")


def test_db_must_exist(tmp_path, monkeypatch):
    """A locked vault leaves an empty folder: the image's DB_MUST_EXIST=1 stops the app instead of starting it empty"""
    monkeypatch.setenv("BOT_TOKEN", BOT)
    monkeypatch.setenv("TOKEN_KEY", "A" * 43 + "=")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "kbtu.db"))
    monkeypatch.setenv("DB_MUST_EXIST", "1")
    with pytest.raises(SystemExit, match="vault locked"):
        config.load()
    (tmp_path / "kbtu.db").touch()
    assert config.load().db_path == str(tmp_path / "kbtu.db")
    monkeypatch.setenv("DB_MUST_EXIST", "0")
    (tmp_path / "kbtu.db").unlink()
    assert config.load()


def test_config_repr_hides_secrets():
    """A logged or dumped Config never carries a secret."""
    cfg = config.Config(bot_token="BOT-SECRET", token_key=b"KEY-SECRET", db_path=":memory:", web_dist=".", cf_ai_token="CF-SECRET")
    assert "SECRET" not in repr(cfg)
