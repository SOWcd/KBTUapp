"""The core loop through the HTTP layer: a KBTU student (written into the database), a president creates and publishes an
event, students register, the waitlist moves, the door scans tickets. Run from server/: .venv/bin/pytest -q"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import re
import shutil
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import casting, app as server, auth, bot, config, db, logic, media, receipt, texts, video

BOT = "123:test"


def delete_now(c, cfg, h: dict) -> None:
    """"Delete my account", and the week gone by: the bot's round deletes it."""
    assert c.post("/api/me/delete", headers=h).status_code == 200
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET delete_at = 0 WHERE delete_at IS NOT NULL")
    bot.purge(cfg, con)
    con.close()


def tma(uid: int, first: str = "Test") -> dict:
    return {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": first}, BOT)}


@pytest.fixture
def env(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><head><title>app</title></head></html>")
    (dist / "assets" / "a.js").write_text("1")
    (dist / "map" / "u1").mkdir(parents=True)
    (dist / "emoji").mkdir()
    shutil.copy(Path(__file__).parents[2] / "web/public/emoji/party_popper_3d.webp", dist / "emoji")
    (dist / "map" / "u1" / "o.webp").write_bytes(b"RIFF")
    cfg = config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=str(tmp_path / "t.db"), web_dist=str(dist), background=False, seed=False)

    monkeypatch.setattr(logic.profiles, "FIRST_N", 0)  # "First 500" stays out of the other tests' outboxes (test_first_fifty turns it on)
    monkeypatch.setattr(receipt, "read", lambda im: None)  # no OCR: tests don't depend on Tesseract (test_receipt_reading fakes it)
    DB[:] = [cfg.db_path]
    client = TestClient(server.create(cfg))
    return client, cfg


DB: list[str] = []  # the env's database (login() writes students straight into it)


def set_clock(monkeypatch, fake) -> None:
    """The rules' clock (logic.core.now, which every logic module reads), and logic.now the tests read too."""
    monkeypatch.setattr(logic.core, "now", fake)
    monkeypatch.setattr(logic, "now", fake)


INTAKE = time.gmtime(time.time() + 5 * 3600).tm_year - (time.gmtime(time.time() + 5 * 3600).tm_mon < 9)  # this academic year's first-years entered then (Almaty)


def login(c, uid: int, name: str):
    """A confirmed KBTU student "<name>": student ID 24B<name>, <Name> Testov, year 2, SITE, a Monday Calculus class.
    Written into the database as the KBTU sign-in did (the portal-password one is gone since Oct 19)."""
    me = c.get("/api/me", headers=tma(uid, name.title())).json()
    con = db.connect(DB[0])
    with db.tx(con):
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, school, consent_version, consent_at,
                verified_at, synced_at) VALUES (?, ?, ?, 'Testov', 2, 'SITE', '1', ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET student_id = excluded.student_id, first_name = excluded.first_name, manual = 0""",
                    (me["id"], "24B" + name, name.title(), *[logic.now()] * 3))
        logic.save_schedule(con, me["id"], [types.SimpleNamespace(weekday=1, begins="09:00", ends="09:50", subject="Calculus",
                                                                  code="MATH101", kind="lecture", room="305", teacher=None)])
    con.close()
    r = c.get("/api/me", headers=tma(uid))
    assert r.status_code == 200, r.text
    return r.json()


def test_core_loop(env):
    c, cfg = env
    assert c.get("/api/me").status_code == 403                       # no initData
    guest = c.get("/api/me", headers=tma(10, "Ali")).json()
    assert guest["student"] is None and guest["tg"]["firstName"] == "Ali"

    me = login(c, 10, "ali")
    assert me["student"]["studentId"] == "24Bali" and me["name"] == "Ali T."
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
    ticket = c.get("/api/me/tickets", headers=tma(30)).json()[0]["my"]
    assert ticket["status"] == "going"
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'seat_free'", (zhan["id"],)).fetchone()

    # the door: ok, then already, then a code that isn't ours
    scan = lambda code: c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": code}).json()
    code = ticket["ticketCode"]
    assert re.fullmatch(r"[2-9A-HJKMNP-Z]{6}", code)  # short, nothing to mix up (no 0/O, 1/I/L)
    first = scan("KBTU" + code)  # what the ticket QR holds
    assert first["result"] == "ok" and first["came"] == 1 and first["person"]["name"] == "Zhan T."
    assert scan(f" {code[:3].lower()} - {code[3:]}")["result"] == "already"  # typed by hand
    assert scan("KBTU-" + code)["result"] == "already"  # the QR before Oct 5
    assert scan("KBTU-NOPE")["result"] == "not_found"
    assert [a["fullName"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()] == ["Testov Zhan"]
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(30)).json()["error"] == "forbidden"


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
    assert stats["signed in with KBTU"] == "1" and stats["staff (by hand)"] == "1"
    # a tester who signed in as a student turns staff: the number is retired (a gap: moving the later ones down would
    # reuse a deleted account's burnt number), and signing in again brings no number back
    login(c, 14, "it"), login(c, 15, "zhan")
    nos = lambda: [c.get("/api/me", headers=tma(u)).json()["no"] for u in (10, 14, 15)]
    assert nos() == [1, 2, 3]
    admin.main(["staff", "14"])
    assert nos() == [1, None, 3]
    login(c, 14, "it")
    assert nos() == [1, None, 3]



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
    from kbtu import bot
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET can_dm = 1, lang = 'kk'")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (5, 1, 'published', 'Hack <night>', '305', 1791090000, 'laptop_3d', '#3B6BFF', 0, 0)""")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 10").fetchone()[0]
    for kind, ref in (("seat_free", "event:5"), ("new_event", "event:5"), ("event_changed", "event:404:1")):
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, ?, ?, 0)", (uid, kind, ref))
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}}) if len(sent) == 1 else httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.send_due(cfg, http)
            await bot.send_due(cfg, http)  # nothing left to send twice
    asyncio.run(go())
    first = sent[0]
    from kbtu import texts
    kk = texts.bot_message("kk", "seat_free", title="Hack <night>", when=texts.when(1791090000, "kk"), place="305")[0]
    assert first["chat_id"] == 10 and first["text"] == kk and "Hack &lt;night&gt;" in kk   # Kazakh, escaped
    assert first["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=tk_5")
    state = dict(con.execute("SELECT kind, COALESCE(error, 'sent') FROM bot_outbox").fetchall())
    assert state == {"seat_free": "sent", "new_event": "blocked", "event_changed": "gone"} and len(sent) == 2
    assert con.execute("SELECT can_dm FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0

    con.execute("DELETE FROM bot_outbox")
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'seat_free', 'event:5', 0)", (uid,))
    stale = bot.rows(con, "SELECT b.*, u.tg_id, u.lang, u.can_dm FROM bot_outbox b JOIN users u ON u.id = b.user_id")
    sent.clear()

    async def postman():
        ok = lambda r: (sent.append(r), httpx.Response(200, json={"ok": True, "result": {}}))[1]
        async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(postman())                               # the new container's postman sends it
    monkeypatch.setattr(bot, "rows", lambda *a: stale)   # the old one read the queue a moment earlier
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




def test_photos(env):
    """An organizer's photo is re-encoded (EXIF with GPS gone), served by hash and put on an event; nobody else uploads."""
    import io
    from PIL import Image
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    exif = Image.Exif()
    exif[0x8825] = {2: (43.0, 14.0, 0.0), 4: (76.0, 55.0, 0.0)}   # GPSInfo: where the photo was taken
    raw = io.BytesIO()
    Image.new("RGB", (3000, 2000), (200, 40, 40)).save(raw, "JPEG", exif=exif)
    assert c.post("/api/photos", headers=tma(30), content=raw.getvalue()).status_code == 403          # not an organizer
    assert c.post("/api/photos", headers=tma(20), content=b"not an image").json()["message"] == "not_an_image"
    up = c.post("/api/photos", headers=tma(20), content=raw.getvalue()).json()
    assert (up["w"], up["h"]) == (1600, 1067) and up["url"].endswith(".webp")
    clear = io.BytesIO()
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(clear, "PNG")
    assert c.post("/api/photos", headers=tma(20), content=clear.getvalue()).json()["color"] == "#ffffff"  # a logo's transparency: white
    bomb = io.BytesIO()
    Image.new("1", (8000, 5000)).save(bomb, "PNG")                     # ~100 KB that would unpack into hundreds of MB
    assert c.post("/api/photos", headers=tma(20), content=bomb.getvalue()).json()["message"] == "not_an_image"
    tiff = io.BytesIO()
    Image.new("RGB", (40, 30)).save(tiff, "TIFF")                      # only the five formats are ever parsed
    assert c.post("/api/photos", headers=tma(20), content=tiff.getvalue()).json()["message"] == "not_an_image"
    for size in ((8064, 6048), (6000, 4000), (4284, 5712), (6001, 4001)):   # 48 MP, a 24 MP camera, a 24 MP iPhone portrait, a crop: read smaller, not refused
        huge = io.BytesIO()
        Image.new("RGB", size, (10, 90, 200)).save(huge, "JPEG")
        r = c.post("/api/photos", headers=tma(20), content=huge.getvalue()).json()
        assert max(r["w"], r["h"]) == 1600
    served = c.get("/" + up["url"])
    assert served.headers["content-type"] == "image/webp" and "immutable" in served.headers["cache-control"]
    assert not Image.open(io.BytesIO(served.content)).getexif()                                        # no EXIF, no GPS
    start = int(time.time()) + 86400
    body = {"title": "Poster", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "coverId": up["id"]}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert ev["cover"]["thumb"] == up["thumb"] and ev["tint"] == "#2c50bf"                            # the colour sent: the editor picks the photo's
    assert ev["cover"]["focus"] is None                                                                # the middle until marked
    framed = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverFocus": [0.25, 0.8]}).json()
    assert framed["cover"]["focus"] == [0.25, 0.8]
    for bad in ([2, 0], [0.5], "0.5,0.5", ["x", 0], [-0.1, 0.5]):
        assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverFocus": bad}).status_code == 400
    kept = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={k: v for k, v in body.items() if k != "coverId"}).json()
    assert kept["cover"] is not None and kept["cover"]["focus"] == [0.25, 0.8]                         # absent keeps both
    gone = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverId": None}).json()
    assert gone["cover"] is None
    # PLAN 33: photos after the cover, swiped sideways; a co-organizer keeps the others' when saving
    login(c, 21, "vic")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'vice', 0 FROM users WHERE tg_id = 21")
    def pic(tg, rgb):
        b = io.BytesIO(); Image.new("RGB", (40, 30), rgb).save(b, "PNG")
        return c.post("/api/photos", headers=tma(tg), content=b.getvalue()).json()["id"]
    a, b2, mine = pic(20, (1, 2, 3)), pic(20, (4, 5, 6)), pic(21, (7, 8, 9))
    plain = {k: v for k, v in body.items() if k != "coverId"}   # the editor sends coverId only when it changes
    put = lambda tg, ids: c.patch(f"/api/events/{ev['id']}", headers=tma(tg), json={**plain, "slideIds": ids})  # noqa: E731
    assert [x["id"] for x in put(20, [b2, a]).json()["slides"]] == [b2, a]                              # in the order picked
    for bad in ([a, a], [True], "1", [a] * 10, [mine]):                                                 # the last: someone else's upload
        assert put(20, bad).status_code == 400
    assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "slideIds": [up["id"]]}).status_code == 400  # not the cover again
    assert [x["id"] for x in put(21, [a, mine]).json()["slides"]] == [a, mine]                          # the Vice keeps the President's
    c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
    assert [x["id"] for x in c.get("/api/events", headers=tma(30)).json()[0]["slides"]] == [a, mine]
    assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json=body).json()["slides"] != []        # absent keeps
    assert put(20, []).json()["slides"] == []
    put(20, [a, b2])
    other = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "slideIds": [a]}).json()       # the same photo on two events
    c.post(f"/api/events/{ev['id']}/cancel", headers=tma(20), json={"reason": "x"})
    assert c.delete(f"/api/events/{ev['id']}", headers=tma(20)).status_code == 204
    assert con.execute("SELECT 1 FROM files WHERE id = ?", (a,)).fetchone() and not con.execute("SELECT 1 FROM files WHERE id = ?", (b2,)).fetchone()
    assert [x["id"] for x in c.get(f"/api/events/{other['id']}", headers=tma(20)).json()["slides"]] == [a]
    assert c.get("/media/..%2Ft.db").status_code == 404 and "SQLite" not in c.get("/media/../t.db").text   # never leaves media/


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_videos(env, tmp_path):
    """An organizer's video comes in pieces (a repeated piece isn't added twice), is compressed without its metadata, and
    plays on the event once ready; a non-video fails; nobody else uploads."""
    import subprocess
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    src = tmp_path / "in.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=60:d=2", "-f", "lavfi", "-i", "sine=d=2",
                    "-metadata", "location=+43.2+076.9/", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src)], check=True)
    raw = src.read_bytes()
    P = tma(20)
    assert c.post("/api/videos", headers=tma(30), json={"size": len(raw)}).status_code == 403          # not an organizer
    assert c.post("/api/videos", headers=P, json={"size": video.MAX_BYTES + 1}).status_code == 400
    vid = c.post("/api/videos", headers=P, json={"size": len(raw)}).json()["id"]
    half = len(raw) // 2
    assert c.post(f"/api/videos/{vid}/done", headers=P).status_code == 409                             # not all of it yet
    assert c.put(f"/api/videos/{vid}?at=0", headers=P, content=raw[:half]).json() == {"at": half}
    assert c.put(f"/api/videos/{vid}?at=0", headers=P, content=raw[:half]).json() == {"at": half}       # sent again: where it stands
    assert c.put(f"/api/videos/{vid}?at={half}", headers=tma(30), content=raw[half:]).status_code == 404  # someone else's
    assert c.put(f"/api/videos/{vid}?at={half}", headers=P, content=raw[half:]).json() == {"at": len(raw)}
    assert c.post(f"/api/videos/{vid}/done", headers=P).json()["status"] == "queued"
    start = int(time.time()) + 86400
    body = {"title": "Reel", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "videoId": vid}
    ev = c.post("/api/orgs/1/events", headers=P, json=body).json()
    assert ev["video"]["status"] == "queued"                                                           # the editor sees it coming
    c.post(f"/api/events/{ev['id']}/publish", headers=P)
    assert c.get("/api/events", headers=tma(30)).json()[0]["video"] is None                           # students: only once ready

    async def work():  # the postman's loop, one round
        x = logic.next_video(con)
        logic.video_done(con, x["id"], await video.compress(Path(cfg.db_path).parent / "uploads" / str(x["id"]), Path(cfg.db_path).parent / "media"))
    asyncio.run(work())
    shown = c.get("/api/events", headers=tma(30)).json()[0]["video"]
    assert shown["status"] == "ready" and shown["duration"] == 2.0 and shown["poster"]["w"] == 720
    played = c.get("/" + shown["url"], headers={"Range": "bytes=0-99"})
    assert played.status_code == 206 and len(played.content) == 100                                    # iOS plays only with ranges
    out = Path(cfg.db_path).parent / shown["url"]
    meta = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream=width,height,r_frame_rate", "-of", "json", str(out)],
                          capture_output=True, text=True).stdout
    assert "location" not in meta and '"width": 720' in meta and '"30/1"' in meta
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None}).json()["video"] is None

    bad = c.post("/api/videos", headers=P, json={"size": 5}).json()["id"]
    c.put(f"/api/videos/{bad}?at=0", headers=P, content=b"hello")
    c.post(f"/api/videos/{bad}/done", headers=P)
    x = logic.next_video(con)
    with pytest.raises(video.BadVideo):
        asyncio.run(video.compress(Path(cfg.db_path).parent / "uploads" / str(x["id"]), Path(cfg.db_path).parent / "media"))
    # PLAN 32: a horizontal clip behind the sheet: 720 on the short side, muted, 20 s at most; only in its own slot
    wsrc = tmp_path / "wide.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=2", "-f", "lavfi", "-i", "sine=d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(wsrc)], check=True)
    wraw = wsrc.read_bytes()
    wid = c.post("/api/videos", headers=P, json={"size": len(wraw), "wide": True}).json()["id"]
    c.put(f"/api/videos/{wid}?at=0", headers=P, content=wraw)
    c.post(f"/api/videos/{wid}/done", headers=P)
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": wid}).status_code == 400   # not the Feed's slot
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None, "wideVideoId": vid}).status_code == 400
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None, "wideVideoId": wid}).json()["wideVideo"]["status"] == "queued"
    assert c.get(f"/api/events/{ev['id']}", headers=tma(30)).json()["wideVideo"] is None                # students: only once ready
    wx = logic.next_video(con)
    assert wx["id"] == wid
    logic.video_done(con, wid, asyncio.run(video.compress(Path(cfg.db_path).parent / "uploads" / str(wid), Path(cfg.db_path).parent / "media", True)))
    wide = c.get(f"/api/events/{ev['id']}", headers=tma(30)).json()["wideVideo"]
    assert wide["poster"]["w"] == 1280 and wide["poster"]["h"] == 720
    wmeta = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(Path(cfg.db_path).parent / wide["url"])],
                           capture_output=True, text=True).stdout.split()
    assert wmeta == ["video"]                                                                            # no sound track
    con.execute("UPDATE videos SET created_at = 0")
    assert sorted(i for i, _ in logic.stale_videos(con)) == [vid] and not con.execute("SELECT 1 FROM videos WHERE id = ?", (vid,)).fetchone()


def test_join_requests(env):
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P, A = tma(20, "Pres"), tma(21, "Ali")
    pings = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'join_request'", (pres["id"],)).fetchone()[0]

    assert c.get("/api/orgs/1", headers=A).json()["recruiting"] is True          # open unless the club closes it
    assert c.post("/api/orgs/1/join-requests", headers=tma(22, "Guest")).status_code == 401
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["myRequest"] == "pending"
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["myRequest"] == "pending" and pings() == 1  # twice = once
    assert c.get("/api/orgs/1/join-requests", headers=A).status_code == 403      # the inbox is Vice+
    inbox = c.get("/api/orgs/1/join-requests", headers=P).json()
    assert [(r["fullName"], r["course"]) for r in inbox] == [("Testov Ali", 2)]
    ping = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'join_request'").fetchone()
    assert bot._render(con, ping)[2] == "jr_1"

    # withdrawn: the club's ping goes nowhere; asking again the same day doesn't ping twice
    assert c.delete("/api/orgs/1/join-requests/mine", headers=A).json()["myRequest"] is None
    assert bot._render(con, ping) is None
    c.post("/api/orgs/1/join-requests", headers=A)
    assert pings() == 1

    # declined: the bot tells, and no new application for 30 days
    first = c.get("/api/orgs/1/join-requests", headers=P).json()[0]["id"]
    assert c.post(f"/api/join-requests/{first}/reject", headers=P).status_code == 204
    assert c.post(f"/api/join-requests/{first}/accept", headers=P).status_code == 409   # already answered
    assert c.get("/api/orgs/1", headers=A).json()["myRequest"] == "rejected"
    assert c.post("/api/orgs/1/join-requests", headers=A).status_code == 429
    con.execute("UPDATE join_requests SET decided_at = decided_at - 31 * 86400")

    # closed: nobody can apply
    assert c.patch("/api/orgs/1", headers=A, json={"recruiting": False}).status_code == 403
    assert c.patch("/api/orgs/1", headers=P, json={"recruiting": False}).json()["recruiting"] is False
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["error"] == "closed"
    c.patch("/api/orgs/1", headers=P, json={"recruiting": True})

    # accepted: a member at once, the bot tells
    c.post("/api/orgs/1/join-requests", headers=A)
    second = c.get("/api/orgs/1/join-requests", headers=P).json()[0]["id"]
    assert c.post(f"/api/join-requests/{second}/accept", headers=P).status_code == 204
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=A).json()["memberships"]] == [(1, "member")]
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["error"] == "conflict"
    told = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'join_decided' ORDER BY id").fetchall()
    assert [r["ref"] for r in told] == [f"jr:{first}:no", f"jr:{second}:yes"]
    assert [bot._render(con, r)[1:] for r in told] == [(None, "cl_1"), (texts.bot_message("ru", "join_yes", org="")[1], "cl_1")]


def test_walk_in(env):
    """A badge QR at the door (§4.4): free events register and check in on the spot; made-up or paid: no."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P = tma(20, "Pres")
    start = int(time.time()) - 1800   # started half an hour ago: the door is open, a walk-in is late
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    qr = c.get("/api/me", headers=tma(21, "Ali")).json()["qr"]
    assert re.fullmatch(r"\d+_[A-Z2-7]{10}", qr) and c.get("/api/me", headers=tma(21, "Ali")).json()["qr"] == qr   # made once, stable
    scan = lambda raw: c.post("/api/events/1/checkin", headers=P, json={"code": raw}).json()
    link = lambda q: f"https://t.me/KBTUappBot?startapp=u_{q}"

    assert scan(link(f"{ali['id']}_AAAAAAAAAA"))["result"] == "not_found"          # a QR made from a user id
    r = scan(link(qr))
    assert (r["result"], r["walkIn"], r["late"] >= 29, r["person"]["id"]) == ("ok", True, True, ali["id"])
    assert scan(link(qr))["result"] == "already"
    assert [a["walkIn"] for a in c.get("/api/events/1/attendees", headers=P).json()] == [True]
    con.execute("UPDATE events SET price = 2000, pay_to_name = 'Pres', pay_phone = '+77000000000' WHERE id = 1")
    assert scan(link(c.get("/api/me", headers=tma(22, "Zhan")).json()["qr"]))["result"] == "paid"   # paid: a ticket only


def test_delete_my_data(env):
    """§4.8 / H2: a week, then the student's data goes; the Telegram account stays a guest. What is over moves to a
    nameless placeholder, so every count stays; free text, receipts, names go; a President's club passes on."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    t0 = int(time.time())
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (ali["id"], "head")])
    for eid, at in ((1, t0 + 86400), (2, t0 - 2 * 86400)):  # one ahead, one over
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, created_by, created_at, updated_at)
            VALUES (?, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 1, ?, 0, 0)""", (eid, at, ali["id"]))
    A, Z = tma(21, "Ali"), tma(22, "Zhan")
    c.post("/api/events/1/registration", headers=A)     # the only seat
    c.post("/api/events/1/registration", headers=Z)     # waitlist
    c.put("/api/events/1/saved", headers=A)
    c.put("/api/orgs/1/subscription", headers=A)
    c.patch("/api/me", headers=A, json={"bio": "hi"})
    # Ali's past: came to event 2 (paid, rated, volunteered), brought Zhan, a casting round, words as the club and his own
    with db.tx(con):
        for uid, inv in ((ali["id"], None), (zhan["id"], ali["id"])):
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, invited_by, created_at, updated_at, checked_in_at, note)
                VALUES (2, ?, 'going', ?, ?, 0, 0, ?, 'vegan')""", (uid, f"T{uid}", inv, t0 - 2 * 86400))
        fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('r', 'receipt', 'image/jpeg', 1, 'ab/rcpt', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) SELECT id, ?, 'app', 0 FROM registrations WHERE event_id = 2 AND user_id = ?",
                    (fid, ali["id"]))
        pic = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('p', 'event_photo', 'image/webp', 1, 'ab/pic', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (2, ?, 0, ?)", (pic, ali["id"]))
        con.execute("INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (2, ?, 5, 'great', 0)", (ali["id"],))
        con.execute("INSERT INTO volunteers (event_id, user_id, status, note, created_at) VALUES (2, ?, 'yes', 'call me', 0)", (ali["id"],))
        con.execute("INSERT INTO rounds (id, org_id, title, closes_at, status, created_at) VALUES (1, 1, 'Autumn', 0, 'done', 0)")
        app_id = con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, created_at, updated_at)
            VALUES (1, ?, 'dev', '{"why": "me"}', 0, 0)""", (ali["id"],)).lastrowid
        con.execute("INSERT INTO round_votes (app_id, user_id, verdict, note, at) VALUES (?, ?, 'next', 'strong', 0)", (app_id, pres["id"]))
        con.execute("INSERT INTO comments (event_id, user_id, as_org, body, created_at) VALUES (2, ?, 1, 'Thanks all', 0), (2, ?, 0, 'mine', 0)",
                    (ali["id"], ali["id"]))
        con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (1, ?, 0)", (ali["id"],))
        con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", tuple(sorted((ali["id"], zhan["id"]))))
    (Path(cfg.db_path).parent / "receipts" / "ab").mkdir(parents=True, exist_ok=True)
    (Path(cfg.db_path).parent / "receipts" / "ab" / "rcpt.jpg").write_bytes(b"x")
    came = lambda: con.execute("SELECT COUNT(*) FROM registrations WHERE event_id = 2 AND checked_in_at IS NOT NULL").fetchone()[0]  # noqa: E731
    zsoul = con.execute("SELECT COUNT(*) FROM registrations WHERE invited_by = ?", (ali["id"],)).fetchone()[0]

    reminders = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h'", (ali["id"],)).fetchone()[0]  # noqa: E731
    assert reminders() == 1
    assert c.patch("/api/me", headers=A, json={"nRemind": False}).json()["settings"]["nRemind"] is False and reminders() == 0
    c.patch("/api/me", headers=A, json={"nRemind": True})
    assert reminders() == 1                                                                   # the switch acts at once

    assert c.get("/api/me/delete", headers=A).json() == {"photos": 1, "paid": False}
    delete = lambda h, **kw: c.post("/api/me/delete", headers=h, json=kw)  # noqa: E731
    assert delete(tma(23, "Guest")).status_code == 401
    at = delete(A).json()["deleteAt"]                                                    # a week to change my mind
    assert at > time.time() + 6 * 86400 and con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'delete_soon'", (ali["id"],)).fetchone()
    bot.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is not None                    # not yet
    assert c.post("/api/me/keep", headers=A).json()["deleteAt"] is None                 # changed my mind
    no = con.execute("SELECT card_no FROM users WHERE id = ?", (ali["id"],)).fetchone()[0]
    delete_now(c, cfg, A)
    left = [(t, col) for t, col, notnull in logic._user_fks(con) if (t, col) not in logic._DEL_KEEP
            if con.execute(f"SELECT 1 FROM {t} WHERE {col} = ?", (ali["id"],)).fetchone()]
    assert left == [], left                                                                   # every table, new ones too
    me = c.get("/api/me", headers=A).json()
    assert (me["student"], me["memberships"], me["bio"], me["qr"], me["no"]) == (None, [], "", None, None)    # a guest again
    u = con.execute("SELECT tg_username, tg_first_name, card_no, delete_at FROM users WHERE id = ?", (ali["id"],)).fetchone()
    assert tuple(u) == (None, "Ali", None, None)       # Telegram's name comes back only because he opened the app again
    assert c.get("/api/events/1", headers=Z).json()["my"]["status"] == "going"               # the seat went on
    # what is over stays counted, without him and without words
    ph = con.execute("SELECT * FROM users WHERE id = (SELECT user_id FROM event_ratings WHERE event_id = 2)").fetchone()
    assert ph["tg_id"] < 0 and ph["tg_id"] != -ali["id"]                                   # random: nothing leads back
    assert ph and (ph["tg_first_name"], ph["tg_username"], ph["seen_at"], ph["can_dm"]) == ("", None, 0, 0)
    assert came() == 2 and con.execute("SELECT note FROM registrations WHERE user_id = ?", (ph["id"],)).fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM registrations WHERE invited_by = ?", (ali["id"],)).fetchone()[0] == 0 and zsoul == 1
    assert tuple(con.execute("SELECT user_id, score, comment FROM event_ratings WHERE event_id = 2").fetchone()) == (ph["id"], 5, "")
    assert tuple(con.execute("SELECT user_id, note FROM volunteers").fetchone()) == (ph["id"], "")
    assert tuple(con.execute("SELECT user_id, answers FROM round_apps").fetchone()) == (ph["id"], "{}")
    assert con.execute("SELECT note FROM round_votes").fetchone()[0] == ""                  # others' words about him go too
    assert [tuple(r) for r in con.execute("SELECT user_id, body FROM comments")] == [(ph["id"], "Thanks all")]
    assert con.execute("SELECT 1 FROM org_bans WHERE user_id = ?", (ali["id"],)).fetchone()
    assert con.execute("SELECT added_by FROM event_photos").fetchone()[0] is None            # the photo stays, nameless
    assert con.execute("SELECT owner_id FROM files WHERE id = ?", (pic,)).fetchone()[0] is None
    assert con.execute("SELECT created_by FROM events WHERE id = 2").fetchone()[0] is None
    assert not con.execute("SELECT 1 FROM receipts").fetchone() and not (Path(cfg.db_path).parent / "receipts" / "ab" / "rcpt.jpg").exists()
    # a returning Ali gets a new number, never his burnt one
    login(c, 21, "ali")
    assert c.get("/api/me", headers=A).json()["no"] not in (None, no)

    # a President leaving: the club passes to the highest rank left (Zhan; Ali, its head, left with his account); alone, to the admin
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (zhan["id"],))
    assert delete(tma(20, "Pres"), photos=True).status_code == 200
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (pres["id"],))
    bot.purge(cfg, con)
    assert con.execute("SELECT user_id FROM org_members WHERE org_id = 1 AND role = 'president'").fetchone()[0] == zhan["id"]
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'solo', 'club', 'Solo', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'president', 0)", (zhan["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (pres["id"],))     # a deleted admin can't take it: no student
    boss = login(c, 30, "boss")
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    delete_now(c, cfg, Z)
    assert con.execute("SELECT user_id FROM org_members WHERE org_id = 2 AND role = 'president'").fetchone()[0] == boss["id"]
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'club_handover' AND ref = 'ho:2'", (boss["id"],)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM users WHERE tg_id < 0").fetchone()[0] == 3


def test_delete_lists_cover_schema(env):
    """Every column pointing at a person is in delete_me's lists or nullable: a new table can't keep someone by being
    forgotten (H2)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    missing = [(t, col) for t, col, notnull in logic._user_fks(con) if notnull and (t, col) not in logic._DEL_GONE | logic._DEL_KEEP]
    assert missing == [], missing


def test_delete_with_a_ticket_out_of_sight(env):
    """A future seat at an event he can no longer see (the club hidden) doesn't block the deletion; the seat frees up.
    His unsent invites to friends go; deletions.log keeps "delete my photos too" and forgets lines after 40 days."""
    c, cfg = env
    ali, zhan = login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 1, 0, 0)""", (int(time.time()) + 86400,))
    A, Z = tma(21, "Ali"), tma(22, "Zhan")
    c.post("/api/events/1/registration", headers=A)
    c.post("/api/events/1/registration", headers=Z)                                      # waitlist
    con.execute("UPDATE orgs SET status = 'hidden'")
    logic.notify(con, zhan["id"], "friend_invite", f"fi:1:{ali['id']}")
    c.post("/api/me/delete", headers=A, json={"photos": True})
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (ali["id"],))
    bot.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is None
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (zhan["id"],)).fetchone()[0] == "going"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'friend_invite'").fetchone()
    log_ = Path(cfg.db_path).parent / "deletions.log"
    assert log_.read_text().split()[2] == "photos"
    log_.write_text(f"{int(time.time()) - 41 * 86400} {'0' * 32}\n" + log_.read_text() + "12")    # an old line, a torn one
    logic._prune_deletion_log(con)
    assert len(log_.read_text().splitlines()) == 1


def test_delete_waits_for_a_paid_ticket(env):
    """A ticket paid for an event still ahead: the deletion waits until it has passed."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, created_at, updated_at)
        VALUES (1, 1, 'published', 'Gala', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 0, 0)""", (int(time.time()) + 86400,))
    with db.tx(con):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T1', 0, 0)", (ali["id"],))
        fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('r', 'receipt', 'image/jpeg', 1, 'ab/r', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) SELECT id, ?, 'app', 0 FROM registrations", (fid,))
    A = tma(21, "Ali")
    assert c.get("/api/me/delete", headers=A).json()["paid"] is True
    delete_now(c, cfg, A)
    assert c.get("/api/me", headers=A).json()["student"] is not None                    # waits for the event
    con.execute("UPDATE events SET starts_at = ?", (int(time.time()) - 5 * 3600,))
    bot.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is None


def test_consent_again(env):
    """The privacy policy changed (H2): a student agrees again once; the version is kept, staff keep theirs."""
    c, cfg = env
    login(c, 21, "ali")
    A = tma(21, "Ali")
    assert c.get("/api/me", headers=A).json()["student"]["consent"] == "1"
    assert c.post("/api/me/consent", headers=A, json={"version": ""}).status_code == 400
    assert c.post("/api/me/consent", headers=A, json={"version": "2026-10-v3"}).json()["student"]["consent"] == "2026-10-v3"
    assert c.post("/api/me/consent", headers=tma(22, "Guest"), json={"version": "2026-10-v3"}).status_code == 401
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET consent_version = 'staff'")
    assert c.post("/api/me/consent", headers=A, json={"version": "2026-10-v3"}).json()["student"]["consent"] == "staff"


def test_legal_pages(env):
    """The privacy policy and the terms: public pages in three languages, linked to each other."""
    c, _ = env
    for doc in ("privacy", "terms"):
        for lang in ("ru", "kk", "en"):
            r = c.get(f"/{doc}?lang={lang}")
            assert r.status_code == 200 and f'lang="{lang}"' in r.text and "@Sowers" in r.text
    assert 'href="privacy?lang=en"' in c.get("/terms?lang=en").text and c.get("/privacy?lang=xx").text.count('lang="ru"') == 1




def test_admin_clubs(env):
    """The pilot's admin panel (SPEC §2): the admin creates a club and gives it a president by @username or Telegram ID;
    a new president moves the old one to vice; nobody else can do any of it."""
    import dataclasses
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}))))
    who = lambda uid, first, username: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": first, "username": username}, BOT)}
    A, P = who(20, "Owner", "owner"), who(21, "Pres", "pres_kbtu")
    c.get("/api/me", headers=A)
    login(c, 21, "pres")
    assert c.get("/api/admin/orgs", headers=P).status_code == 403
    assert c.post("/api/admin/orgs", headers=P, json={"name": "Chess", "short": "C", "emoji": "trophy_3d"}).status_code == 403
    assert c.post("/api/admin/orgs", headers=A, json={"name": "X", "short": "X", "emoji": "trophy_3d"}).status_code == 400

    club = c.post("/api/admin/orgs", headers=A, json={"name": "Chess Club", "short": "ch", "emoji": "trophy_3d", "official": True}).json()
    assert (club["short"], club["official"], club["slug"], club["team"], club["members"]) == ("CH", True, "chessclub", [], 0)
    put = lambda body: c.put(f"/api/admin/orgs/{club['id']}/role", headers=A, json=body)
    assert put({"who": "@nobody", "role": "president"}).json()["message"] == "who"   # never opened the app
    assert put({"who": "@pres_kbtu", "role": "boss"}).status_code == 400
    team = put({"who": "@PRES_kbtu", "role": "president"}).json()["team"]
    assert [(m["username"], m["role"], m["student"]) for m in team] == [("pres_kbtu", "president", True)]
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=P).json()["memberships"]] == [(club["id"], "president")]

    c.get("/api/me", headers=who(22, "Next", "next_one"))                              # a guest so far
    team = put({"who": "22", "role": "president"}).json()["team"]                      # by Telegram ID
    assert [(m["username"], m["role"], m["student"]) for m in team] == [("next_one", "president", False), ("pres_kbtu", "vice", True)]
    assert put({"who": "@pres_kbtu", "role": "none"}).json()["members"] == 1
    # every step was written down by itself (org_history's triggers): President, then Vice, then out; a role held under
    # a day doesn't show, so the test moves the clock back two days
    con = db.connect(cfg.db_path)
    pid = c.get("/api/me", headers=P).json()["id"]
    assert [tuple(r) for r in con.execute("SELECT role, until IS NULL FROM org_history WHERE user_id = ? ORDER BY id", (pid,))] == [("president", 0), ("vice", 0)]
    con.execute("UPDATE org_history SET since = since - 2 * 86400 WHERE user_id = ?", (pid,))
    past = c.get(f"/api/users/{pid}", headers=P).json()["past"]
    assert [(x["org"]["id"], x["role"]) for x in past] == [(club["id"], None), (club["id"], None)]  # the role: to the club's team only
    assert [o["id"] for o in c.get("/api/admin/orgs", headers=A).json()] == [club["id"]]
    # hide, never delete: gone for everyone but the admin's list, and back with one more tap
    hide = lambda on, h=A: c.put(f"/api/admin/orgs/{club['id']}/hidden", headers=h, json={"hidden": on})
    assert hide(True, P).status_code == 403
    assert hide(True).json()["hidden"] is True
    assert c.get(f"/api/orgs/{club['id']}", headers=P).status_code == 404 and c.get(f"/api/orgs/{club['id']}", headers=A).status_code == 200
    assert club["id"] not in [o["id"] for o in c.get("/api/orgs", headers=P).json()]
    assert hide(False).json()["hidden"] is False and c.get(f"/api/orgs/{club['id']}", headers=P).status_code == 200
    # schools come from KBTU's site (seed_schools), never made by hand; their President by the same link
    for kind in ("office", "school"):
        assert c.post("/api/admin/orgs", headers=A, json={"name": "School of IT", "short": "IT", "emoji": "laptop_3d", "kind": kind}).status_code == 400
    con = db.connect(cfg.db_path)
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    school = con.execute("SELECT id, official FROM orgs WHERE slug = 'site'").fetchone()
    boss = logic.Viewer(c.get("/api/me", headers=A).json()["id"], "admin", True)
    assert school["official"] and logic.president_link(con, boss, school["id"])["token"]


def test_attendees_csv(env):
    """The attendee file (SPEC §6): the club's Head+ only, Excel-friendly (BOM, ';'), a cell a spreadsheet would run
    as a formula defused, every export in the audit log."""
    import codecs
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, created_by, created_at, updated_at, needs_phone)
        VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0, 1)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("UPDATE students SET phone = '+77001234567' WHERE user_id = ?", (ali["id"],))  # the event asks for it
    c.post("/api/events/1/registration", headers=tma(21, "Ali"))
    con.execute("UPDATE students SET phone = '+77001234567', email = '=HYPERLINK(1)' WHERE user_id = ?", (ali["id"],))
    assert c.post("/api/events/1/attendees/export", headers=tma(21, "Ali")).status_code == 403   # not the club's team
    e, people = logic.attendees_export(con, logic.Viewer(pres["id"], "user", True), 1)
    name, data, caption = texts.attendees_csv("en", e["title"], people)
    assert data.startswith(codecs.BOM_UTF8) and caption == "Attendees: Talk"
    head, row = data.decode("utf-8-sig").splitlines()
    assert head.split(";") == list(texts.CSV_HEAD["en"])
    assert row.split(";")[:9] == ["Testov", "Ali", "", "24Bali", "2", "SITE", "'=HYPERLINK(1)", "'+77001234567", "going"]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'attendees_export'").fetchone()[0] == 1


def test_team_rank_rule(env):
    """The club's own team (SPEC §2): everyone in it sees the roster; Vice+ manage only people below them and give only
    roles below their own; the President hands the club over and becomes Vice; anyone but the President can leave."""
    c, cfg = env
    ids = {n: login(c, i, n)["id"] for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "memb"), (24, "out"))}
    H = {n: tma(i, n.title()) for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "memb"), (24, "out"))}
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(ids["pres"], "president"), (ids["vice"], "vice"), (ids["head"], "head"), (ids["memb"], "member")])
    roles = lambda: {m["fullName"].split()[-1].lower(): m["role"] for m in c.get("/api/orgs/1/members", headers=H["pres"]).json()}
    patch = lambda who, uid, role: c.patch(f"/api/orgs/1/members/{uid}", headers=H[who], json={"role": role})

    assert c.get("/api/orgs/1/members", headers=H["out"]).status_code == 403             # not in the club
    assert [m["role"] for m in c.get("/api/orgs/1/members", headers=H["memb"]).json()] == ["president", "vice", "head", "member"]
    assert patch("head", ids["memb"], "head").status_code == 403                          # a Head manages nobody
    assert patch("vice", ids["head"], "vice").status_code == 403                          # only roles below your own
    assert patch("vice", ids["pres"], "member").status_code == 403                        # only people below you
    assert patch("vice", ids["memb"], "head").status_code == 200 and roles()["memb"] == "head"
    assert patch("pres", ids["vice"], "member").status_code == 200 and roles()["vice"] == "member"
    assert c.delete(f"/api/orgs/1/members/{ids['pres']}", headers=H["pres"]).json()["message"] == "president"   # hand it over first
    assert c.delete(f"/api/orgs/1/members/{ids['vice']}", headers=H["vice"]).status_code == 204                 # leaving by yourself
    assert c.post("/api/orgs/1/transfer", headers=H["head"], json={"userId": ids["memb"]}).status_code == 403
    assert c.post("/api/orgs/1/transfer", headers=H["pres"], json={"userId": ids["out"]}).status_code == 404    # not in the club
    team = c.post("/api/orgs/1/transfer", headers=H["pres"], json={"userId": ids["head"]}).json()
    assert {m["fullName"].split()[-1].lower(): m["role"] for m in team} == {"head": "president", "pres": "vice", "memb": "head"}
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'presidency_transfer'").fetchone()[0] == 1


def test_invite_link(env):
    """A club's invite link (SPEC §4.5): Vice+ get a fresh one each time; a student who opens it is a Member at once (a
    pending application is settled); one person, once, within 48 hours; a member opening it doesn't use it up."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P, A, Z = tma(20, "Pres"), tma(21, "Ali"), tma(22, "Zhan")
    assert c.post("/api/orgs/1/invites", headers=A).status_code == 403                      # Vice+ only
    token = c.post("/api/orgs/1/invites", headers=P).json()["token"]
    assert re.fullmatch(r"[0-9a-f]{24}", token) and c.post("/api/orgs/1/invites", headers=P).json()["token"] != token   # fresh each time
    c.post("/api/orgs/1/join-requests", headers=A)                                           # applied earlier
    assert c.post(f"/api/invites/{token}", headers=tma(23, "Guest")).status_code == 401
    assert c.post(f"/api/invites/{token}", headers=P).status_code == 200                    # already in: not used up
    assert c.post(f"/api/invites/{token}", headers=A).json()["id"] == 1
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=A).json()["memberships"]] == [(1, "member")]
    assert c.get("/api/orgs/1/join-requests", headers=P).json() == []                        # the application is settled
    assert c.post(f"/api/invites/{token}", headers=Z).status_code == 404                     # once
    late = c.post("/api/orgs/1/invites", headers=P).json()["token"]
    con.execute("UPDATE org_invites SET expires_at = 1 WHERE token = ?", (late,))
    assert c.post(f"/api/invites/{late}", headers=Z).status_code == 404                      # 48 hours


def test_friends(env):
    """Friends (SPEC §4.7): a request and its answer, a mutual ask that settles itself, a quiet decline that keeps
    looking pending, a one-time link (the first one wins), where friends go (only if they allow it), unfriend."""
    c, cfg = env
    ali, zhan, dana = login(c, 31, "ali"), login(c, 32, "zhan"), login(c, 33, "dana")
    A, Z, D = tma(31, "Ali"), tma(32, "Zhan"), tma(33, "Dana")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET tg_username = 'zhan_k' WHERE tg_id = 32")
    found = c.get("/api/friends/find?username=@ZHAN_K", headers=A).json()                 # @username, any case
    assert found["person"]["id"] == zhan["id"] and found["friendship"] == "none"
    assert c.get("/api/friends/find?username=nobody_here", headers=A).status_code == 404
    assert c.post("/api/friends/requests", headers=A, json={"userId": zhan["id"]}).json()["friendship"] == "requested"
    assert c.get(f"/api/users/{ali['id']}", headers=Z).json()["friendship"] == "incoming"
    assert c.get("/api/me", headers=Z).json()["counters"]["friendRequests"] == 1
    out = c.post(f"/api/friends/requests/{ali['id']}/accept", headers=Z).json()
    assert [(x["person"]["id"], x["fullName"]) for x in out["friends"]] == [(ali["id"], "Ali Testov")]
    assert c.get(f"/api/users/{zhan['id']}", headers=A).json()["friendship"] == "friends"
    assert [r[0] for r in con.execute("SELECT kind FROM bot_outbox ORDER BY id")] == ["friend_request", "friend_new"]
    # a quiet decline: Dana keeps seeing "requested", and asking again changes nothing
    c.post("/api/friends/requests", headers=D, json={"userId": ali["id"]})
    assert c.post(f"/api/friends/requests/{dana['id']}/decline", headers=A).json()["incoming"] == []
    assert c.get(f"/api/users/{ali['id']}", headers=D).json()["friendship"] == "requested"
    assert c.post("/api/friends/requests", headers=D, json={"userId": ali["id"]}).json()["friendship"] == "requested"
    assert c.get("/api/friends", headers=A).json()["incoming"] == []
    # asking someone who already asked me is the answer
    c.post("/api/friends/requests", headers=Z, json={"userId": dana["id"]})
    assert c.post("/api/friends/requests", headers=D, json={"userId": zhan["id"]}).json()["friendship"] == "friends"
    # the one-time link: the same until used, the first one wins, the owner sees who it was, then a fresh one
    link = c.post("/api/friends/link", headers=D).json()["token"]
    assert re.fullmatch(r"[0-9a-f]{24}", link) and c.post("/api/friends/link", headers=D).json()["token"] == link
    assert c.post(f"/api/friends/link/{link}", headers=D).json()["result"] == "self"
    assert c.post(f"/api/friends/link/{link}", headers=A).json()["result"] == "friends"
    assert c.get(f"/api/friends/link/{link}", headers=D).json()["usedBy"]["id"] == ali["id"]
    login(c, 34, "eve")
    assert c.post(f"/api/friends/link/{link}", headers=tma(34, "Eve")).json()["result"] == "used"
    assert c.post("/api/friends/link", headers=D).json()["token"] != link
    # where friends go: only those who let friends see it
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (7, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (int(time.time()) + 86400,))
    assert c.post("/api/events/7/registration", headers=Z).status_code == 200
    going = c.get("/api/friends", headers=A).json()["going"]
    assert [(e["id"], [p["id"] for p in e["friends"]]) for e in going] == [(7, [zhan["id"]])]
    # a team-only event Zhan goes to (Zhan is in the club, Ali isn't) shows on neither Ali's feed nor Zhan's card for Ali
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (zhan["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, visibility, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (8, 1, 'published', 'members', 'Team retro', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (int(time.time()) + 86400,))
    assert c.post("/api/events/8/registration", headers=Z).status_code == 200
    assert [e["id"] for e in c.get("/api/friends", headers=A).json()["going"]] == [7]
    assert [e["id"] for e in c.get(f"/api/users/{zhan['id']}", headers=A).json()["going"]] == [7]
    c.patch("/api/me", headers=Z, json={"showGoing": False})
    assert c.get("/api/friends", headers=A).json()["going"] == []
    assert c.delete(f"/api/friends/{zhan['id']}", headers=A).status_code == 204                # quietly
    assert c.get(f"/api/users/{zhan['id']}", headers=A).json()["friendship"] == "none"


def test_showcase(env):
    """The showcase (SPEC §4.11): up to 6 keys — achievement codes and badges as b<event id> — kept in the order picked;
    junk is dropped; the card's shelf shows only what the person actually has."""
    c, cfg = env
    ali = login(c, 41, "ali")
    A = tma(41, "Ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, badge_name, created_at, updated_at)
        VALUES (9, 1, 'published', 'Hack', '305', 1700000000, 'laptop_3d', '#3B6BFF', 'Hacker', 0, 0)""")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (9, ?, 'going', 'ABC234', 1700000100, 0, 0)", (ali["id"],))
    con.execute("INSERT INTO achievement_grants (user_id, code, created_at) VALUES (?, 'bugs', 0)", (ali["id"],))
    me = c.patch("/api/me", headers=A, json={"showcase": ["b9", "<script>", "bugs", "regular", "b9", 5, "nope"]}).json()
    assert me["showcase"] == ["b9", "bugs", "regular"]                       # known keys, deduped, in order
    card = c.get(f"/api/users/{ali['id']}", headers=A).json()
    assert card["shelf"] == ["b9", "bugs"]                                  # "regular" isn't earned yet
    assert len(c.patch("/api/me", headers=A, json={"showcase": ["bugs"] * 3 + [f"b{i}" for i in range(10)]}).json()["showcase"]) == 6


def test_posts(env):
    """News (SPEC §4.10): Head+ write their club's posts; only a broadcast org writes to every club member, and the bot
    tells them; the unread dot counts broadcasts until they're read; a club takes its post down; a photo must be one's own."""
    c, cfg = env
    head, mem, dmp = login(c, 51, "head"), login(c, 52, "mem"), login(c, 53, "dmp")
    H, M, D = tma(51, "Head"), tma(52, "Mem"), tma(53, "Dmp")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_broadcast, created_at) VALUES (2, 'dmp', 'office', 'DMP', 'DM', 'sparkles_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'head', 0), (1, ?, 'member', 0), (2, ?, 'head', 0)", (head["id"], mem["id"], dmp["id"]))
    post = {"title": "Hackathon teams", "body": "Sign up by Friday", "tag": "recruiting", "pinned": True}
    assert c.post("/api/orgs/1/posts", headers=M, json=post).status_code == 403                  # Head+ only
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "audience": "clubs"}).status_code == 400   # not a broadcast org
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "tag": "<b>"}).status_code == 400
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "photoId": 999}).status_code == 400
    p = c.post("/api/orgs/1/posts", headers=H, json=post).json()
    assert p["pinned"] and p["canDelete"] and p["photo"] is None
    assert [x["id"] for x in c.get("/api/posts?scope=subs", headers=M).json()] == [p["id"]]       # a member sees the club's post
    b = c.post("/api/orgs/2/posts", headers=D, json={"title": "No more club reports", "audience": "clubs"}).json()
    assert [r[0] for r in con.execute("SELECT kind FROM bot_outbox WHERE user_id = ?", (mem["id"],))] == ["broadcast"]
    assert c.get("/api/me", headers=M).json()["counters"]["unreadBroadcasts"] == 1
    assert c.get("/api/me", headers=D).json()["counters"]["unreadBroadcasts"] == 0               # the author has read it
    assert c.post("/api/posts/read", headers=M, json={"ids": [b["id"], "x"]}).status_code == 204
    assert c.get("/api/me", headers=M).json()["counters"]["unreadBroadcasts"] == 0
    # edit and pin (the club's Head+): text changes read "edited", a pin alone doesn't; one pinned post per club
    assert c.patch(f"/api/posts/{p['id']}", headers=M, json={"title": "Mine now"}).status_code == 403
    for bad in ({"title": "x"}, {"tag": "<b>"}, {"photoId": 999}, {"pinned": "yes"}, {}):
        assert c.patch(f"/api/posts/{p['id']}", headers=H, json=bad).status_code == 400, bad
    e = c.patch(f"/api/posts/{p['id']}", headers=H, json={"title": "Hackathon: teams of 4", "tag": None, "photoId": None}).json()
    assert (e["title"], e["tag"], e["body"], e["pinned"], e["canEdit"]) == ("Hackathon: teams of 4", None, "Sign up by Friday", True, True) and e["editedAt"]
    q = c.post("/api/orgs/1/posts", headers=H, json={"title": "Second"}).json()
    assert c.patch(f"/api/posts/{q['id']}", headers=H, json={"pinned": True}).json()["editedAt"] is None
    assert [(x["title"], x["pinned"]) for x in c.get("/api/posts?scope=subs", headers=M).json()] == [("Second", True), ("Hackathon: teams of 4", False)]
    assert c.get("/api/posts?scope=subs", headers=M).json()[0]["canEdit"] is False
    assert c.delete(f"/api/posts/{p['id']}", headers=M).status_code == 403
    assert c.delete(f"/api/posts/{p['id']}", headers=H).status_code == 204
    assert [r[0] for r in con.execute("SELECT target FROM audit_log WHERE action = 'post_hide'")] == [f"post:{p['id']}"]
    assert c.patch(f"/api/posts/{p['id']}", headers=H, json={"title": "Back?"}).status_code == 404
    assert [x["title"] for x in c.get("/api/posts?scope=subs", headers=M).json()] == ["Second"]


def test_invite_cards(env, monkeypatch):
    """Invites go out as our bot's card: a line of text and a button — the link only behind the button,
    never in the text; a club's card is for its Vice+ only."""
    import json
    import httpx
    c, cfg = env
    ali, mem = login(c, 61, "ali"), login(c, 62, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'member', 0)", (ali["id"], mem["id"]))
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))
    A = tma(61, "Ali")
    assert c.post("/api/share", headers=A, json={"kind": "fr"}).json() == {"id": "prep1"}
    card = sent[-1]["result"]
    url = card["reply_markup"]["inline_keyboard"][0][0]["url"]
    token = c.post("/api/friends/link", headers=A).json()["token"]
    assert card["type"] == "article" and url.endswith(f"startapp=fr_{token}")          # the same live link as the QR
    assert "http" not in card["input_message_content"]["message_text"] and "Ali T." in card["input_message_content"]["message_text"]
    assert c.post("/api/share", headers=A, json={"kind": "join", "id": 1}).status_code == 200
    assert "startapp=join_1_" in sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert c.post("/api/share", headers=tma(62, "Mem"), json={"kind": "join", "id": 1}).status_code == 403
    assert c.post("/api/share", headers=A, json={"kind": "nope"}).status_code == 400
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "regular"}).status_code == 400    # not earned
    con.execute("INSERT INTO achievement_grants (user_id, code, created_at) VALUES (?, 'bugs', 0)", (ali["id"],))
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs"}).status_code == 200
    card = sent[-1]["result"]
    assert card["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=aw_bugs") and "· I" in card["input_message_content"]["message_text"]


def test_checkin_by_name(env):
    """No QR at the door (a dead phone, §4.4): a Member checks a going person in from the door list (short names only),
    marked "by hand" for the organizer and the CSV; a wrong tap is taken back within 10 minutes; not going: refused."""
    c, cfg = env
    pres, mem, ali, zhan = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali"), login(c, 73, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'TTT234', 0, 0)", (ali["id"],))
    M = tma(71, "Mem")
    assert c.get("/api/events/1/door", headers=tma(73, "Zhan")).status_code == 403             # the team only
    door = c.get("/api/events/1/door", headers=M).json()
    assert [(d["person"]["name"], d["checkedInAt"]) for d in door] == [("Ali T.", None)]       # a short name
    r = c.post("/api/events/1/checkin", headers=M, json={"userId": ali["id"]}).json()
    assert (r["result"], r["person"]["id"], r["came"]) == ("ok", ali["id"], 1)
    assert c.post("/api/events/1/checkin", headers=M, json={"userId": zhan["id"]}).json()["result"] == "not_found"
    assert [a["manual"] for a in c.get("/api/events/1/attendees", headers=tma(70, "Pres")).json()] == [True]
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 204       # a wrong tap
    assert c.get("/api/events/1/door", headers=M).json()[0]["checkedInAt"] is None
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 409       # nothing to take back
    con.execute("UPDATE registrations SET checked_in_at = ?, checkin_manual = 1", (int(time.time()) - 3600,))
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 409       # too late to undo
    e, people = __import__("kbtu.logic", fromlist=["x"]).attendees_export(con, __import__("kbtu.logic", fromlist=["x"]).Viewer(pres["id"], "user", True), 1)
    assert texts.attendees_csv("ru", e["title"], people)[1].decode("utf-8-sig").splitlines()[1].endswith(";" + texts.CSV_STATUS["ru"]["yes"])


def test_event_updates(env):
    """An organizer's update: Head+ only, pinned on the event for everyone, the bot tells the people going
    (our template, never the organizer's words), three a day at most; deleting it drops the queued message."""
    c, cfg = env
    pres, mem, ali = login(c, 80, "pres"), login(c, 81, "mem"), login(c, 82, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    c.post("/api/events/1/registration", headers=tma(82, "Ali"))
    P = tma(80, "Pres")
    assert c.post("/api/events/1/updates", headers=tma(81, "Mem"), json={"body": "Side door"}).status_code == 403   # Head+
    ups = c.post("/api/events/1/updates", headers=P, json={"body": "Entrance by the side door"}).json()
    assert [u["body"] for u in ups] == ["Entrance by the side door"]
    assert c.get("/api/events/1", headers=tma(82, "Ali")).json()["updates"][0]["canDelete"] is False
    msg = con.execute("SELECT user_id, kind, ref FROM bot_outbox WHERE kind = 'event_update'").fetchall()
    assert [(m[0], m[1]) for m in msg] == [(ali["id"], "event_update")]
    text = bot._render(con, {"kind": "event_update", "ref": msg[0][2], "lang": "en", "user_id": ali["id"]})
    assert text[2] == "ev_1" and "Side door" not in text[0] and "Hack" in text[0]          # the template, not the words
    c.post("/api/events/1/updates", headers=P, json={"body": "Bring a laptop"})
    c.post("/api/events/1/updates", headers=P, json={"body": "We start at 19:15"})
    assert c.post("/api/events/1/updates", headers=P, json={"body": "One more"}).status_code == 429   # three a day
    assert c.delete(f"/api/events/1/updates/{ups[0]['id']}", headers=P).status_code == 204
    assert bot._render(con, {"kind": "event_update", "ref": msg[0][2], "lang": "en", "user_id": ali["id"]}) is None


def test_ratings(env):
    """One tap after the event: only people checked in, from the end until 7 days later; anonymous to the club
    (average, counts, comments without names; from three ratings on); the bot asks an hour after the end unless reminders are off."""
    c, cfg = env
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    for uid in (ali["id"], zhan["id"]):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', ?, 0, 0)", (uid, f"T{uid}AB"))
    P, A, Z = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan")
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "ok"
    ask = con.execute("SELECT send_after FROM bot_outbox WHERE kind = 'rate' AND user_id = ?", (ali["id"],)).fetchone()
    assert ask and ask[0] == start + 3600 + 3600                                          # an hour after the end
    assert c.put("/api/events/1/rating", headers=A, json={"score": 5}).status_code == 403    # not over yet
    con.execute("UPDATE events SET ends_at = ? WHERE id = 1", (int(time.time()) - 60,))
    assert c.get("/api/events/1", headers=A).json()["canRate"] is True
    assert c.get("/api/events/1", headers=Z).json()["canRate"] is False                   # didn't come
    assert c.put("/api/events/1/rating", headers=Z, json={"score": 1}).status_code == 403
    assert c.put("/api/events/1/rating", headers=A, json={"score": 9}).status_code == 400
    e = c.put("/api/events/1/rating", headers=A, json={"score": 4, "comment": "Great jury"}).json()
    assert e["myRating"] == 4 and e["ratings"] is None                                    # a student never sees the summary
    s = c.get("/api/events/1", headers=P).json()["ratings"]
    assert s == {"avg": None, "count": 1, "dist": [], "comments": []}                  # under three: how many, nothing more
    for uid in (pres["id"], zhan["id"]):                                                  # two more (straight in: the rules are above)
        con.execute("INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (1, ?, 5, '', 0)", (uid,))
    s = c.get("/api/events/1", headers=P).json()["ratings"]
    assert s == {"avg": 4.7, "count": 3, "dist": [0, 0, 0, 1, 2], "comments": [{"score": 4, "body": "Great jury", "at": s["comments"][0]["at"]}]}
    assert "name" not in json.dumps(s) if (json := __import__("json")) else True        # anonymous
    m = {"kind": "rate", "ref": "rate:1", "lang": "en", "user_id": ali["id"]}
    assert bot._render(con, m) is None                                                    # rated already: no question


def test_calendar_file(env):
    """"To calendar" on the ticket: the going get a signed link the phone's browser opens with no session."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club, KBTU', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack; night', '305', ?, NULL, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, pres["id"]))
    A = tma(91, "Ali")
    assert c.get("/api/events/1", headers=A).json()["my"] is None
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', 0, 0)", (ali["id"],))
    link = c.get("/api/events/1", headers=A).json()["my"]["ics"]
    r = c.get(link)                                                                       # no Telegram headers
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Hack\\; night" in r.text and "DESCRIPTION:IT Club\\, KBTU\\nhttps://t.me/" in r.text
    assert time.strftime("DTEND:%Y%m%dT%H%M%SZ", time.gmtime(start + 3 * 3600)) in r.text  # no end: three hours
    assert c.get(link.replace("events/1/", "events/2/")).status_code == 404               # the signature is per event
    assert c.get("/api/events/1/ics").status_code == 404


def test_album(env):
    """The guests' album: who came adds up to 10 photos from the start until a week after the end, the team too;
    the one who added it or the club's Head+ take one out; guests see none; deleting my data takes mine out."""
    import io
    from PIL import Image
    c, cfg = env
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 7200
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', ?, 0, 0)", (ali["id"], start))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T92ABC', 0, 0)", (zhan["id"],))
    dana = login(c, 96, "dana")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', 'T96ABC', ?, 0, 0)", (dana["id"], start))
    P, A, Z = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan")

    def jpeg(n: int) -> bytes:
        raw = io.BytesIO()
        Image.new("RGB", (64, 48), (n * 20 % 256, 90, 160)).save(raw, "JPEG")
        return raw.getvalue()

    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is True
    assert c.get("/api/events/1", headers=Z).json()["canAddPhotos"] is False               # going, but didn't come
    assert c.post("/api/events/1/photos", headers=Z, content=jpeg(0)).status_code == 403
    e = c.post("/api/events/1/photos", headers=A, content=jpeg(0)).json()
    assert len(e["photos"]) == 1 and e["photos"][0]["canDelete"] is True
    first = e["photos"][0]["id"]
    assert c.get("/api/events/1", headers=Z).json()["photos"][0]["canDelete"] is False
    assert c.get("/api/events/1", headers=tma(93, "Guest")).json()["photos"] == []           # people's faces: students only
    for n in range(1, 10):
        e = c.post("/api/events/1/photos", headers=A, content=jpeg(n)).json()
    assert len(e["photos"]) == 10 and e["canAddPhotos"] is False                            # ten each
    report = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'photo_report'").fetchall()
    assert [r["user_id"] for r in report] == [dana["id"]] and bot._render(con, report[0])[2] == "ph_1"  # once, to who else came
    assert c.post("/api/events/1/photos", headers=A, content=jpeg(11)).status_code == 403
    assert c.get("/api/events/1", headers=P).json()["canAddPhotos"] is True                 # the team brings its own
    assert c.delete(f"/api/events/1/photos/{first}", headers=Z).status_code == 403
    assert len(c.delete(f"/api/events/1/photos/{first}", headers=P).json()["photos"]) == 9  # the club's Head+
    con.execute("UPDATE events SET ends_at = ? WHERE id = 1", (int(time.time()) - 8 * 86400,))
    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is False               # a week after the end: closed
    assert delete_now(c, cfg, A) is None
    left = c.get("/api/events/1", headers=P).json()["photos"]
    assert len(left) == 9 and {p["by"] for p in left} == {None}                              # my photos stay, without my name (H2)


def test_album_reports(env):
    """A photo can be reported: gone for the reporter at once, for everyone after two people, the admin's queue
    shows its thumb and "take down" deletes it; "Photos from participants" off = only the team adds; who added it shows."""
    import dataclasses
    import io
    from PIL import Image
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 96, "dana")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 7200
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    for u, code in ((ali, "T91ABC"), (zhan, "T92ABC"), (dana, "T96ABC")):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', ?, ?, 0, 0)",
                    (u["id"], code, start))
    P, A, Z, D, B = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(96, "Dana"), tma(94, "Boss")
    raw = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 90, 160)).save(raw, "JPEG")
    ph = c.post("/api/events/1/photos", headers=A, content=raw.getvalue()).json()["photos"][0]
    assert ph["by"] == "Ali T." and ph["mine"] is True
    assert c.get("/api/events/1", headers=Z).json()["photos"][0]["mine"] is False
    rep = lambda h: c.post("/api/reports", headers=h, json={"target": "photo", "id": ph["id"], "reason": "insult"}).status_code  # noqa: E731
    assert rep(A) == 404                                                                    # not my own
    assert rep(Z) == 204
    assert c.get("/api/events/1", headers=Z).json()["photos"] == []                         # gone for me at once
    assert len(c.get("/api/events/1", headers=P).json()["photos"]) == 1                     # not yet for the rest
    assert rep(D) == 204
    assert c.get("/api/events/1", headers=P).json()["photos"] == []                         # two people: hidden until the admin looks
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(r["target"], r["id"], r["where"]) for r in q] == [("photo", ph["id"], {"kind": "event", "id": 1})] and q[0]["text"].endswith(".t.webp")
    # a moderator never judges their own photo: not in their queue, and refused
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 91")
    assert c.get("/api/me", headers=A).json()["counters"]["reports"] == 0
    assert c.get("/api/admin/reports", headers=A).json() == [] and c.post(f"/api/admin/reports/photo/{ph['id']}", headers=A, json={"remove": False}).status_code == 403
    con.execute("UPDATE users SET role = 'user' WHERE tg_id = 91")
    # kept: back for everyone, and two new reports hide it only for those two (a moderator's call holds)
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": False}).status_code == 204
    assert rep(Z) == 204 and rep(D) == 204
    assert len(c.get("/api/events/1", headers=P).json()["photos"]) == 1 and c.get("/api/events/1", headers=Z).json()["photos"] == []
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": True}).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM event_photos").fetchone()[0] == 0 and c.get("/api/admin/reports", headers=B).json() == []
    # kept 30 days for an undo: the file stays, "taken down" lists it, Restore puts it back in the album
    path = con.execute("SELECT path FROM files WHERE id = ?", (ph["id"],)).fetchone()[0]
    on_disk = lambda: (Path(cfg.db_path).parent / "media" / f"{path}.webp").exists()  # noqa: E731
    assert on_disk() and [(x["target"], x["id"]) for x in c.get("/api/admin/taken-down", headers=B).json()] == [("photo", ph["id"])]
    assert c.post(f"/api/admin/taken-down/photo/{ph['id']}/restore", headers=B).status_code == 204
    assert [(p["id"], p["by"]) for p in c.get("/api/events/1", headers=P).json()["photos"]] == [(ph["id"], "Ali T.")]
    assert c.post("/api/reports", headers=P, json={"target": "photo", "id": ph["id"], "reason": "insult"}).status_code == 204
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": True}).status_code == 204
    con.execute("UPDATE takedowns SET at = at - 29 * 86400")
    bot.purge(cfg, con)
    assert on_disk()                                                                         # 29 days: still there
    con.execute("UPDATE takedowns SET at = at - 2 * 86400")
    bot.purge(cfg, con)                                                                      # 31: gone, from disk too
    assert not on_disk() and not con.execute("SELECT 1 FROM files WHERE id = ?", (ph["id"],)).fetchone()
    assert c.post(f"/api/admin/taken-down/photo/{ph['id']}/restore", headers=B).status_code == 404
    e = c.get("/api/events/1", headers=P).json()
    body = {k: e[k] for k in ("title", "description", "startsAt", "endsAt", "place", "placeUrl", "emoji", "color", "seats", "firstYear")}
    assert c.patch("/api/events/1", headers=P, json={**body, "albumOpen": False}).status_code == 200
    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is False                # who came: no more
    assert c.get("/api/events/1", headers=P).json()["canAddPhotos"] is True                 # the team still adds
    assert c.get("/api/events/1", headers=P).json()["albumOpen"] is False


def test_bring_a_friend(env):
    """"Bring a friend": my friends and where they stand; one bot card per friend and event; the friend's
    registration credits the first one who asked ("Life of the party"); the card goes quiet once they're in."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 93, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("INSERT INTO friendships VALUES (?, ?, 0)", (min(ali["id"], zhan["id"]), max(ali["id"], zhan["id"])))
    A, Z = tma(91, "Ali"), tma(92, "Zhan")
    assert [(x["person"]["id"], x["state"]) for x in c.get("/api/events/1/invites", headers=A).json()] == [(zhan["id"], "none")]
    assert c.post("/api/events/1/invites", headers=A, json={"userId": dana["id"]}).status_code == 403   # not a friend
    assert c.post("/api/events/1/invites", headers=A, json={"userId": zhan["id"]}).json()[0]["state"] == "invited"
    c.post("/api/events/1/invites", headers=A, json={"userId": zhan["id"]})                            # twice: one card
    cards = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'friend_invite' AND user_id = ?", (zhan["id"],)).fetchall()
    assert len(cards) == 1 and bot._render(con, cards[0])[2] == "ev_1"
    c.post("/api/events/1/registration", headers=Z)
    assert con.execute("SELECT invited_by FROM registrations WHERE user_id = ?", (zhan["id"],)).fetchone()[0] == ali["id"]
    assert bot._render(con, cards[0]) is None                                                           # in already
    assert c.get("/api/events/1/invites", headers=A).json()[0]["state"] == "going"


def test_member_link(env):
    """"My link" (a member's KPI): who signs up by a club member's link (ev_<id>_<badge code>) is that member's; the
    first link wins, never myself, never a stranger's code; the organizers see who brought whom, the Team page the
    ones who came."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 93, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (ali["id"], "member")])
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    code = {u["id"]: logic._qr_code(con, u["id"]) for u in (pres, ali, dana)}
    P, A, Z, D = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(93, "Dana")
    by = lambda u: con.execute("SELECT invited_by FROM registrations WHERE user_id = ?", (u["id"],)).fetchone()[0]  # noqa: E731
    c.post("/api/events/1/registration", headers=A, json={"ref": code[ali["id"]]})
    c.post("/api/events/1/registration", headers=D, json={"ref": code[dana["id"]]})
    assert by(ali) is None and by(dana) is None                                                         # myself; not in the club
    c.post("/api/events/1/registration", headers=Z, json={"ref": code[ali["id"]]})
    c.delete("/api/events/1/registration", headers=Z)
    c.post("/api/events/1/registration", headers=Z, json={"ref": code[pres["id"]]})
    assert by(zhan) == ali["id"]                                                                        # the first link wins
    seen = {a["person"]["id"]: a["by"] and a["by"]["id"] for a in c.get("/api/events/1/attendees", headers=P).json()}
    assert seen == {ali["id"]: None, dana["id"]: None, zhan["id"]: ali["id"]}
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE user_id = ?", (int(time.time()), zhan["id"]))
    team = {m["person"]["id"]: m.get("brought") for m in c.get("/api/orgs/1/members", headers=P).json()}
    assert team == {pres["id"]: 0, ali["id"]: 1}
    assert "brought" not in c.get("/api/orgs/1/members", headers=A).json()[0]                           # Head+ only


def test_comments(env):
    """Comments under events and posts (§4.10): students write (500 characters, 10 a minute), the club's Head+ answer
    as the club, take any down and turn the thread off; reports go to the admin's queue, once per person and thing."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    P, A, Z, B = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(94, "Boss")
    assert c.get("/api/events/1/comments", headers=tma(95, "Guest")).status_code == 401                # students only
    t = c.post("/api/events/1/comments", headers=A, json={"body": "  Where is the entrance?  "}).json()
    assert [(x["body"], x["person"]["id"], x["canDelete"]) for x in t["items"]] == [("Where is the entrance?", ali["id"], True)]
    assert c.get("/api/events/1", headers=Z).json()["comments"] == 1
    assert c.get("/api/orgs/1/events", headers=P).json()[0]["questions"] == 1                          # waits in Studio
    ping = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_question'").fetchall()
    assert [r["user_id"] for r in ping] == [pres["id"]] and bot._render(con, ping[0])[2] == "cm_1"     # the club's Head+
    assert c.get("/api/events/1/comments", headers=Z).json()["items"][0]["canDelete"] is False
    assert c.post("/api/events/1/comments", headers=Z, json={"body": "x", "asOrg": True}).status_code == 403  # not the club's Head+
    t = c.post("/api/events/1/comments", headers=P, json={"body": "Round the side", "asOrg": True}).json()
    assert t["items"][1]["person"] is None and t["items"][1]["org"]["id"] == 1 and t["canModerate"] is True
    assert c.get("/api/orgs/1/events", headers=P).json()[0]["questions"] == 0                          # answered
    assert bot._render(con, ping[0]) is None                                                            # quiet once answered
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_answer'").fetchall()
    assert [r["user_id"] for r in told] == [ali["id"]] and "answered your question" in bot._render(con, told[0])[0]
    for bad in ("", " ", "x" * 501):
        assert c.post("/api/events/1/comments", headers=Z, json={"body": bad}).status_code == 400
    for n in range(10):
        c.post("/api/events/1/comments", headers=Z, json={"body": f"spam {n}"})
    assert c.post("/api/events/1/comments", headers=Z, json={"body": "one more"}).status_code == 429     # ten a minute
    first = t["items"][0]["id"]
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "spam"}).status_code == 204
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "insult"}).status_code == 204  # quiet repeat
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "boring"}).status_code == 400
    for bad in ("x" * 501, 5, ["a"]):
        assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "other", "note": bad}).status_code == 400
    # the open report is updated, not doubled: the latest reason, the words kept
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "other", "note": "  Rude to the host "}).status_code == 204
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "spam", "note": ""}).status_code == 204
    mine = next(x["id"] for x in c.get("/api/events/1/comments", headers=Z).json()["items"] if x["mine"])
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": mine, "reason": "spam"}).status_code == 404  # my own: delete it
    assert c.get("/api/admin/reports", headers=P).status_code == 403
    assert c.get("/api/me", headers=B).json()["counters"]["reports"] == 1 and c.get("/api/me", headers=P).json()["counters"]["reports"] == 0
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(x["target"], x["id"], x["text"], x["count"], x["reasons"]) for x in q] == [("comment", first, "Where is the entrance?", 1, {"spam": 1})]
    assert [(n["reason"], n["note"]) for n in q[0]["notes"]] == [("spam", "Rude to the host")] and "reporter" not in str(q[0])
    assert c.delete(f"/api/comments/{first}", headers=Z).status_code == 403                             # not hers
    assert c.post(f"/api/admin/reports/comment/{first}", headers=B, json={"remove": True}).status_code == 204
    assert c.get("/api/admin/reports", headers=B).json() == [] and c.get("/api/me", headers=B).json()["counters"]["reports"] == 0
    assert first not in [x["id"] for x in c.get("/api/events/1/comments", headers=A).json()["items"]]
    # a wrong call undone (§2): the admin's take-downs of the last 30 days, and Restore
    assert c.get("/api/admin/taken-down", headers=P).status_code == 403
    assert [(x["target"], x["id"]) for x in c.get("/api/admin/taken-down", headers=B).json()] == [("comment", first)]
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=B).status_code == 204
    assert first in [x["id"] for x in c.get("/api/events/1/comments", headers=A).json()["items"]]
    # decided once, it may be reported again (it is back); kept this time
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "danger"}).status_code == 204
    assert [(x["id"], x["reasons"], x["notes"]) for x in c.get("/api/admin/reports", headers=B).json()] == [(first, {"danger": 1}, [])]
    assert c.post(f"/api/admin/reports/comment/{first}", headers=B, json={"remove": False}).status_code == 204
    assert c.get("/api/admin/taken-down", headers=B).json() == []
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=B).status_code == 404               # nothing to undo
    assert c.post(f"/api/admin/taken-down/user/{first}/restore", headers=B).status_code == 404   # nothing of theirs kept

    assert c.delete(f"/api/comments/{first}", headers=P).status_code == 204                                    # gone again (the club)
    assert c.get("/api/admin/taken-down", headers=B).json() == []                                              # the club's call, not the admin's
    assert c.patch("/api/events/1/comments", headers=A, json={"on": False}).status_code == 403
    assert c.patch("/api/events/1/comments", headers=P, json={"on": False}).json()["on"] is False
    assert c.post("/api/events/1/comments", headers=A, json={"body": "hello?"}).status_code == 409         # turned off
    con.execute("INSERT INTO posts (id, org_id, author_id, audience, title, body, created_at) VALUES (1, 1, ?, 'public', 'News', 'Text', 0)", (pres["id"],))
    pid = c.post("/api/posts/1/comments", headers=A, json={"body": "Nice"}).json()["items"][0]["id"]
    assert c.delete(f"/api/comments/{pid}", headers=P).status_code == 204                               # the club's Head+
    assert c.get("/api/posts", headers=A, params={"scope": "all"}).json()[0]["comments"] == 0


def test_question_badges(env):
    """Studio's "questions waiting" (they stayed after he read and answered): a Head+'s answer as themselves
    counts like the club's, their own words are never questions, and reading the thread clears it for the reader only."""
    c, cfg = env
    pres, vice, ali = login(c, 90, "pres"), login(c, 91, "vice"), login(c, 92, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice")])
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    P, V, A = tma(90, "Pres"), tma(91, "Vice"), tma(92, "Ali")
    waiting = lambda h: c.get("/api/orgs/1/events", headers=h).json()[0]["questions"]
    say = lambda h, body: c.post("/api/events/1/comments", headers=h, json={"body": body}).json()
    say(A, "Where is it?"); say(A, "And when?")
    assert waiting(P) == 2 and waiting(V) == 2
    say(P, "Room 305, at six")                                     # as himself: an answer, not a question
    assert waiting(P) == 0 and waiting(V) == 0
    assert [r["user_id"] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'comment_question'")] == [pres["id"], vice["id"]]  # not for his
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_answer'").fetchall()
    assert [r["user_id"] for r in told] == [ali["id"]] and "answered your question" in bot._render(con, told[0])[0]
    say(A, "Can I bring a friend?")
    assert waiting(P) == 1 and waiting(V) == 1
    c.get("/api/events/1/comments", headers=V)                     # the Vice has read it: gone for her, not for the President
    assert waiting(V) == 0 and waiting(P) == 1
    asks = {r["user_id"]: r for r in con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_question'")}
    assert bot._render(con, asks[vice["id"]]) is None and bot._render(con, asks[pres["id"]])[2] == "cm_1"
    c.get("/api/events/1/comments", headers=A)                     # a student reading changes nothing
    assert waiting(P) == 1



def test_nick_and_photo(env):
    """A nickname and my own photo: everyone sees the nick, organizers the real name beside it; my photo
    turns "Photo from Telegram" off, on again is Telegram's; a report takes the nick, photo and "about me" down."""
    import dataclasses
    import io
    from pathlib import Path

    from PIL import Image
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'NNN234', 0, 0)", (ali["id"],))
    P, B = tma(90, "Pres"), tma(94, "Boss")
    A = {"Authorization": "tma " + auth.sign_init_data({"id": 91, "first_name": "Ali", "photo_url": "https://t.me/i/userpic/320/ali.jpg"}, BOT)}
    real = c.get("/api/me", headers=A).json()["name"]
    for bad in ("x", "y" * 25, "@ali", "t.me/ali", "see https://x.kz"):
        assert c.patch("/api/me", headers=A, json={"nick": bad}).status_code == 400
    me = c.patch("/api/me", headers=A, json={"nick": "  Ali \u200b the   Great "}).json()
    assert (me["nick"], me["name"], me["avatar"], me["photo"]["telegram"]) == ("Ali the Great", "Ali the Great", "https://t.me/i/userpic/320/ali.jpg", True)
    c.post("/api/events/1/comments", headers=A, json={"body": "Hi"})
    assert c.get("/api/events/1/comments", headers=P).json()["items"][0]["person"]["name"] == "Ali the Great"  # everyone: the nick
    att = c.get("/api/events/1/attendees", headers=P).json()[0]
    assert att["person"]["nick"] == "Ali the Great" and "Ali" in att["fullName"] and "Great" not in att["fullName"]  # organizers: both
    assert c.get("/api/events/1/door", headers=P).json()[0]["person"]["realName"] == real
    assert c.patch("/api/me", headers=A, json={"avatarTg": False}).status_code == 400   # no photo of my own yet
    raw = io.BytesIO()
    Image.new("RGB", (300, 300), (30, 160, 90)).save(raw, "JPEG")
    me = c.post("/api/me/photo", headers=A, content=raw.getvalue()).json()
    own = me["photo"]["own"]
    assert me["avatar"] == own and own.startswith("media/") and me["photo"]["telegram"] is False
    assert (Path(cfg.db_path).parent / own).exists()                                     # served from /media/
    assert c.get(f"/api/users/{ali['id']}", headers=P).json()["avatar"] == own
    assert c.patch("/api/me", headers=A, json={"avatarTg": True}).json()["avatar"] == "https://t.me/i/userpic/320/ali.jpg"  # back
    assert c.patch("/api/me", headers=A, json={"avatarTg": False}).json()["avatar"] == own                                 # mine kept
    raw2 = io.BytesIO()
    Image.new("RGB", (300, 300), (200, 60, 60)).save(raw2, "JPEG")
    newer = c.post("/api/me/photo", headers=A, content=raw2.getvalue()).json()["photo"]["own"]
    assert newer != own and not (Path(cfg.db_path).parent / own).exists()               # the one it replaced left the disk
    gone = c.delete("/api/me/photo", headers=A).json()["photo"]                             # "Delete my photo": off the disk, Telegram's back
    assert gone["own"] is None and gone["telegram"] and not (Path(cfg.db_path).parent / newer).exists()
    newer = c.post("/api/me/photo", headers=A, content=raw2.getvalue()).json()["photo"]["own"]
    assert c.post("/api/reports", headers=A, json={"target": "user", "id": ali["id"], "reason": "spam"}).status_code == 404  # not myself
    assert c.post("/api/reports", headers=P, json={"target": "user", "id": ali["id"], "reason": "insult"}).status_code == 204
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(x["target"], x["text"], x["where"]) for x in q] == [("user", "Ali the Great", {"kind": "person", "id": ali["id"]})]
    assert c.post(f"/api/admin/reports/user/{ali['id']}", headers=B, json={"remove": True}).status_code == 204
    assert (Path(cfg.db_path).parent / newer).exists()                                     # kept 30 days for an undo
    me = c.get("/api/me", headers=A).json()
    assert (me["nick"], me["name"], me["avatar"], me["photo"]) == (None, real, "https://t.me/i/userpic/320/ali.jpg",
                                                                   {"telegram": True, "tg": "https://t.me/i/userpic/320/ali.jpg", "own": None})
    assert [(x["target"], x["id"], x["text"]) for x in c.get("/api/admin/taken-down", headers=B).json()] == [("user", ali["id"], "Ali the Great")]
    assert c.post(f"/api/admin/taken-down/user/{ali['id']}/restore", headers=B).status_code == 204   # a wrong call undone
    me = c.get("/api/me", headers=A).json()
    assert (me["nick"], me["avatar"]) == ("Ali the Great", newer) and c.get("/api/admin/taken-down", headers=B).json() == []
    assert c.post(f"/api/admin/taken-down/user/{ali['id']}/restore", headers=B).status_code == 404   # once
    c.post(f"/api/admin/reports/user/{ali['id']}", headers=B, json={"remove": True})                  # down again, kept again
    assert con.execute("SELECT COUNT(*) FROM takedowns WHERE user_id = ?", (ali["id"],)).fetchone()[0] == 1
    c.patch("/api/me", headers=A, json={"nick": "Ali again"})
    c.post("/api/me/photo", headers=A, content=raw.getvalue())
    assert delete_now(c, cfg, A) is None
    # deleting the account takes the kept copy at once: the nick and words, the photo off the disk
    assert not con.execute("SELECT 1 FROM takedowns WHERE user_id = ?", (ali["id"],)).fetchone() and not (Path(cfg.db_path).parent / newer).exists()
    u = con.execute("SELECT nick, avatar_tg, avatar_file_id FROM users WHERE id = ?", (ali["id"],)).fetchone()
    assert tuple(u) == (None, 1, None) and not con.execute("SELECT 1 FROM files WHERE kind = 'avatar' AND owner_id = ?", (ali["id"],)).fetchone()

def test_calendar_feed(env):
    """My calendar feed: one secret address per student, kept; everything I go to (a cancelled event struck
    through); the page hands webcal:// to the phone's calendar; gone with my data."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    for eid, status, title in ((1, "published", "Hack"), (2, "cancelled", "Talk"), (3, "published", "Not mine")):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
            VALUES (?, 1, ?, ?, '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (eid, status, title, start, pres["id"]))
    for eid in (1, 2):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, 0, 0)", (eid, ali["id"], f"T{eid}ABCD"))
    A = tma(91, "Ali")
    links = c.post("/api/me/calendar", headers=A).json()
    assert links == c.post("/api/me/calendar", headers=A).json()                                 # the same address, kept
    token = links["page"].rsplit("/", 1)[1]
    assert links["feed"] == f"webcal://{cfg.domain}/cal/{token}.ics"
    feed = c.get(f"/cal/{token}.ics")                                                            # no Telegram headers
    assert feed.headers["content-type"].startswith("text/calendar") and "X-WR-CALNAME:KBTU App" in feed.text
    assert "SUMMARY:Hack" in feed.text and "SUMMARY:Talk\r\nLOCATION" in feed.text and "STATUS:CANCELLED" in feed.text and "Not mine" not in feed.text
    page = c.get(f"/cal/{token}")
    assert page.status_code == 200 and f"webcal://{cfg.domain}/cal/{token}.ics" in page.text
    assert c.get("/cal/nobody.ics").status_code == 404 and c.get("/cal/nobody").status_code == 404
    assert delete_now(c, cfg, A) is None
    assert c.get(f"/cal/{token}.ics").status_code == 404                                        # gone with my data


def test_unlock_moment(env):
    """A check-in that brings a new achievement level: the date it was reached, the bot's message once, and the
    app's unlock moment until it has been celebrated."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', 0, 0)", (ali["id"],))
    P, A = tma(90, "Pres"), tma(91, "Ali")
    assert c.get("/api/me", headers=A).json()["unlocked"] == []
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "ok"
    assert c.get("/api/me", headers=A).json()["unlocked"] == [{"code": "first_in", "level": 1}]       # the first one in
    sent = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'achievement'").fetchall()
    assert [(r["user_id"], r["ref"]) for r in sent] == [(ali["id"], "ach:first_in:1")] and bot._render(con, sent[0])[2] == "aw_first_in"
    first = next(a for a in c.get(f"/api/users/{ali['id']}", headers=A).json()["awards"]["achievements"] if a["code"] == "first_in")
    assert first["level"] == 1 and first["at"]                                                     # the earned date
    assert c.post("/api/me/unlocked", headers=A, json={"code": "first_in", "level": 1}).json()["unlocked"] == []
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "already"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'achievement'").fetchone()[0] == 1  # once


def test_registry(env, monkeypatch):
    """DMP's registry (§4.13): DMP Head+ only; every club with its numbers and President; rosters with full names and
    IDs, contacts only of Presidents and Vices; search finds club members only; the CSV goes to their chat."""
    import httpx
    c, cfg = env
    dmp, pres, ali, zhan = login(c, 80, "dmp"), login(c, 81, "pres"), login(c, 82, "ali"), login(c, 83, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", [(9, dmp["id"], "head"), (1, pres["id"], "president"), (1, ali["id"], "member")])
    con.execute("UPDATE users SET tg_username = 'pres_tg' WHERE id = ?", (pres["id"],))
    con.execute("UPDATE users SET tg_username = 'ali_tg' WHERE id = ?", (ali["id"],))
    D, A = tma(80, "Dmp"), tma(82, "Ali")
    assert c.get("/api/registry/orgs", headers=A).status_code == 403
    clubs = c.get("/api/registry/orgs", headers=D).json()
    it = next(x for x in clubs if x["org"]["id"] == 1)
    assert it["members"] == 2 and it["president"]["fullName"] == "Testov Pres" and it["president"]["username"] == "pres_tg"
    assert all(x["org"]["id"] != 9 for x in clubs)                                                       # offices aren't clubs
    assert c.get("/api/registry/orgs", headers=D, params={"back": 3}).status_code == 200 and c.get("/api/registry/orgs", headers=D, params={"back": 13}).status_code == 400
    roster = c.get("/api/registry/orgs/1/members", headers=D).json()
    assert [(x["role"], x["studentId"]) for x in roster] == [("president", "24Bpres"), ("member", "24Bali")]
    assert roster[1]["username"] is None and roster[1]["quiet"] is True                                # a member: no contacts
    assert [x["person"]["id"] for x in c.get("/api/registry/search", headers=D, params={"q": "24Bal"}).json()] == [ali["id"]]
    assert c.get("/api/registry/search", headers=D, params={"q": "Zhan"}).json() == []                 # in no club
    looks = [(r[0], r[1]) for r in con.execute("SELECT actor_id, action FROM audit_log WHERE action LIKE 'registry_%' ORDER BY id")]
    assert looks == [(dmp["id"], "registry_roster"), (dmp["id"], "registry_search"), (dmp["id"], "registry_search")]  # §9
    sent = []
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(
        lambda r: (sent.append(r.content), httpx.Response(200, json={"ok": True}))[1])))
    assert c.post("/api/registry/export", headers=D).status_code == 204
    assert b"Testov" in sent[0] and b"pres_tg" in sent[0] and b"ali_tg" not in sent[0]
    assert [r[0] for r in con.execute("SELECT actor_id FROM audit_log WHERE action = 'registry_export'")] == [dmp["id"]]  # §2
    # DMP gives the ✓ (and can take it back): the President hears it once; not for offices; never for a plain member
    assert c.post("/api/registry/orgs/1/official", headers=A, json={"on": True}).status_code == 403
    assert c.post("/api/registry/orgs/9/official", headers=D, json={"on": True}).status_code == 404
    assert c.post("/api/registry/orgs/1/official", headers=D, json={"on": "yes"}).status_code == 400
    assert c.post("/api/registry/orgs/1/official", headers=D, json={"on": True}).json()["official"] is True
    c.post("/api/registry/orgs/1/official", headers=D, json={"on": False}); c.post("/api/registry/orgs/1/official", headers=D, json={"on": True})
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'club_official'").fetchall()
    assert [t["user_id"] for t in told] == [pres["id"]] and bot._render(con, told[0])[2] == "cl_1"
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'official'").fetchone()[0] == 3
    # (after the export: a request refreshes the person's Telegram fields from initData)
    team = {x["person"]["id"]: x["quiet"] for x in c.get("/api/orgs/1/members", headers=tma(81, "Pres")).json()}
    assert team[ali["id"]] is True and not any(x["quiet"] for x in c.get("/api/orgs/1/members", headers=A).json())  # Vice+ only


def test_first_fifty(env, monkeypatch):
    """Card numbers and "First 500" (§4.4, §4.11): the number is the order of first KBTU sign-in and stays the person's;
    the Creator's card shows 0 and takes no place, so the grant goes to cards 1..FIRST_N; a deleted account's number
    stays empty, never given again: a return gets a new one."""
    c, cfg = env
    monkeypatch.setattr(logic.profiles, "FIRST_N", 2)
    con = db.connect(cfg.db_path)
    c.get("/api/me", headers=tma(69, "Boss"))
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 69")
    first = [{"code": "first50", "level": 1}]
    f = login(c, 69, "ff")
    assert f["no"] == 0 and f["unlocked"] == first
    a, b = login(c, 70, "aa"), login(c, 71, "bb")
    assert (a["no"], b["no"]) == (1, 2) and a["unlocked"] == b["unlocked"] == first
    delete_now(c, cfg, tma(70, "Aa"))
    cc = login(c, 72, "cc")
    assert cc["no"] == 3 and cc["unlocked"] == []                       # past the 2; number 1 stays empty
    again = login(c, 70, "aa")
    assert again["no"] == 4 and again["unlocked"] == []                 # back after deleting: a new card, the old one burnt
    assert c.get(f"/api/users/{b['id']}", headers=tma(72, "Cc")).json()["no"] == 2
    assert c.get("/api/me", headers=tma(73, "Guest")).json()["no"] is None
    # migration 36: a card within the 500 that missed the award gets it quietly; then everyone has it = 100%
    monkeypatch.setattr(logic.profiles, "FIRST_N", 500)
    con.execute("DELETE FROM achievement_grants WHERE user_id = ?", (cc["id"],))
    con.execute("DELETE FROM achievement_levels WHERE user_id = ?", (cc["id"],))
    con.executescript(dict(db.MIGRATIONS)[36])
    ach = next(a for a in logic.achievements(con, cc["id"]) if a["code"] == "first50")
    assert ach["level"] == 1 and ach["rarity"] == 1
    # migration 59: a night sign-in left without a number gets the next one, and its "First 500" on the next open
    for k, x in enumerate((b["id"], cc["id"], again["id"])):                # signed in in this order
        con.execute("UPDATE students SET verified_at = ? WHERE user_id = ?", (1792600000 + k, x))
        con.execute("UPDATE users SET card_no = NULL WHERE id = ?", (x,))
        con.execute("DELETE FROM achievement_grants WHERE user_id = ?", (x,))
        con.execute("DELETE FROM achievement_levels WHERE user_id = ?", (x,))
    con.executescript(dict(db.MIGRATIONS)[59])
    late = c.get("/api/me", headers=tma(71, "Bb")).json()
    assert late["no"] == 5 and late["unlocked"] == first
    assert [c.get("/api/me", headers=tma(t)).json()["no"] for t in (72, 70)] == [6, 7]


def test_chats_directory(env, monkeypatch):
    """The chats directory (§4.11): the admin adds t.me links; "for you" = aimed at my school and course, then those for
    everyone; a tick once opened; a bad link is refused. The avatar, members and (if left empty) the title come from the
    chat's t.me page; a topics group is its own kind."""
    import dataclasses
    import io
    from PIL import Image
    c, cfg = env
    png = io.BytesIO(); Image.new("RGB", (64, 64), "red").save(png, "PNG")

    async def peek(http, url):
        return {"title": "KBTU &official", "image": png.getvalue(), "members": 1234} if "official" in url else {"title": None, "image": None, "members": None}
    monkeypatch.setattr(media, "chat_peek", peek)
    page = '<meta property="og:title" content="KBTU app Topics&#33;">\n<div class="tgme_page_extra">15 members, 9 online</div>'
    assert media._OG.findall(page) == [("title", "KBTU app Topics&#33;")] and media._EXTRA.search(page).group(1) == "15"
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"), login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    add = lambda **kw: c.post("/api/admin/chats", headers=B, json={"kind": "group", **kw})
    assert c.post("/api/admin/chats", headers=A, json={"title": "X", "url": "https://t.me/x", "kind": "group"}).status_code == 403
    assert add(title="Bad", url="http://evil.example/x").status_code == 400
    everyone = add(url="https://t.me/kbtu_official", kind="channel").json()                     # no title: the chat's own
    assert everyone["title"] == "KBTU &official" and everyone["photo"] and everyone["members"] == 1234
    assert add(title="Talk", url="https://t.me/talk", kind="forum").json()["kind"] == "forum"
    assert add(url="https://t.me/nameless").status_code == 400                                 # no title anywhere
    mine = add(title="SITE 2nd year", url="https://t.me/+AbCdEf123", school="SITE", course=2).json()
    add(title="SITE 4th year", url="https://t.me/+Zz9", school="SITE", course=4)
    got = c.get("/api/chats", headers=A).json()
    assert [x["id"] for x in got["forYou"]] == [mine["id"], everyone["id"], got["forYou"][2]["id"]] and len(got["all"]) == 4
    assert c.post(f"/api/chats/{mine['id']}/opened", headers=A).status_code == 204
    assert next(x for x in c.get("/api/chats", headers=A).json()["forYou"] if x["id"] == mine["id"])["opened"] is True
    assert len(c.get("/api/chats", headers=tma(62, "Guest")).json()["forYou"]) == 2  # a guest: those for everyone


def test_grants(env):
    """Manual achievements (§4.11): the admin only; "Bug hunter" adds up, a secret one is given once; each new level is
    celebrated (the bot's card, the unlock moment) and audited."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    give = lambda code, h=B: c.post("/api/admin/grants", headers=h, json={"userId": ali["id"], "code": code})
    assert give("bugs", A).status_code == 403 and give("first50").status_code == 400
    bugs = lambda p: next(a for a in p["awards"]["achievements"] if a["code"] == "bugs")
    assert bugs(give("bugs").json())["level"] == 1
    assert c.get("/api/me", headers=A).json()["unlocked"] == [{"code": "bugs", "level": 1}]
    twice = bugs(give("bugs").json())
    assert twice["count"] == 2                                                                    # adds up
    assert twice["rarity"] == 0.5 and [x["rarity"] for x in twice["levels"]] == [0.5, 0, 0, 0]   # 1 of the 2 students has level 1
    assert give("creator_laugh").status_code == 200 and give("creator_laugh").status_code == 409  # a secret one: once
    con = db.connect(cfg.db_path)
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'grant'").fetchone()[0] == 3
    # one given by mistake comes back off the profile at any time, all of it at once; never "First 500"
    back = lambda code, h=B: c.post("/api/admin/grants/take-back", headers=h, json={"userId": ali["id"], "code": code})
    assert back("bugs", A).status_code == 403 and back("first50").status_code == 400
    left = bugs(back("bugs").json())
    assert left["count"] == 0 and left["level"] == 0
    assert back("bugs").status_code == 404
    assert give("creator_laugh").status_code == 409 and back("creator_laugh").status_code == 200 and give("creator_laugh").status_code == 200


def test_grant_scanner(env):
    """The owner's batch scanner (PLAN "Creator awards"): a badge QR is one grant, a wrong code finds nobody, a
    secret one only once; undo within a minute takes the level and its unsent card back; "You gave" lists them."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    qr = "https://t.me/kbtu_bot/app?startapp=u_" + c.get("/api/me", headers=A).json()["qr"]
    scan = lambda code, raw=qr, h=B: c.post("/api/admin/grants/scan", headers=h, json={"qr": raw, "code": code})  # noqa: E731
    assert scan("bugs", h=A).status_code == 403 and scan("bugs", raw=qr[:-1] + ("Q" if qr[-1] != "Q" else "R")).status_code == 404 and scan("first50").status_code == 400
    one_ = scan("bugs").json()
    assert one_["person"]["id"] == ali["id"] and scan("bugs").status_code == 200                 # one per scan
    assert scan("creator_found").status_code == 200 and scan("creator_found").status_code == 409
    con = db.connect(cfg.db_path)
    assert c.delete(f"/api/admin/grants/{one_['id']}", headers=B).status_code == 204
    gave = c.get("/api/admin/grants", headers=B).json()
    assert [g["code"] for g in gave] == ["creator_found", "bugs"] and gave[0]["person"]["id"] == ali["id"]
    last = next(g for g in gave if g["code"] == "creator_found")
    assert c.delete(f"/api/admin/grants/{last['id']}", headers=B).status_code == 204
    assert not con.execute("SELECT 1 FROM achievement_levels WHERE user_id = ? AND code = 'creator_found'", (ali["id"],)).fetchone()
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref LIKE 'ach:creator_found:%'", (ali["id"],)).fetchone()
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'bugs'", (ali["id"],)).fetchone()[0] == 1  # one bug left
    con.execute("UPDATE achievement_grants SET created_at = created_at - 120")
    assert c.delete(f"/api/admin/grants/{gave[1]['id']}", headers=B).status_code == 404       # too late to undo


def test_course_day(env, monkeypatch):
    """The year of study moves on every September 1 (Almaty), once, whatever year it was written in: the portal's lag
    (a repeater) stays, the degree's last year is the top (bachelor 4, master 2; a portal 6 is not lowered), an August
    ID of the coming intake starts at 1, a missed year is caught up."""
    import calendar
    c, cfg = env
    ids = [login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve"))]
    con = db.connect(cfg.db_path)
    sept = calendar.timegm((2027, 9, 1, 0, 0, 0)) - 5 * 3600                                # Sept 1, 2027, 00:00 Almaty
    for uid, sid, course, synced in zip(ids, ("26B000001", "24B000002", "21B000003", "27B000004", "26M000005"), (1, 2, 6, 1, 1),
                                        (sept - 300 * 86400,) * 3 + (sept - 10 * 86400, sept - 300 * 86400)):
        con.execute("UPDATE students SET student_id = ?, course = ?, synced_at = ? WHERE user_id = ?", (sid, course, synced, uid))
    courses = lambda: [con.execute("SELECT course FROM students WHERE user_id = ?", (u,)).fetchone()[0] for u in ids]  # noqa: E731
    set_clock(monkeypatch, lambda: sept - 60)                                    # Aug 31, 23:59: not yet
    logic.course_day(con)
    assert courses() == [1, 2, 6, 1, 1]
    set_clock(monkeypatch, lambda: sept + 60)
    logic.course_day(con)
    logic.course_day(con)
    assert courses() == [2, 3, 6, 1, 2]
    set_clock(monkeypatch, lambda: sept + 731 * 86400)                           # Sept 2029, 2028 missed
    logic.course_day(con)
    assert courses() == [4, 4, 6, 3, 2] and courses()[0] == logic.course_of("26B000001")
    assert logic.course_of("19B000006") == 4 and logic.course_of("20M000007") == 2 and logic.course_of("20X000008") == 6
    # migration 62 (its UPDATEs; the column exists already): course_year from synced_at (or an August ID's own year);
    # a typed-in year (written since the portal closed) past the degree's last is capped, the portal's and staff's never
    oct20, oct10, spring26 = (calendar.timegm(d) for d in ((2026, 10, 20, 0, 0, 0), (2026, 10, 10, 0, 0, 0), (2026, 4, 1, 0, 0, 0)))
    for uid, sid, course, synced, ver in zip(ids, ("21B000001", "20B000002", "20M000003", "27B000004", "24M000005"), (6, 5, 4, 1, 3),
                                             (oct20, spring26, oct20, oct10, oct20), ("v3", "v3", "v3", "v3", "staff")):
        con.execute("UPDATE students SET student_id = ?, course = ?, course_year = NULL, synced_at = ?, manual = 0, consent_version = ? WHERE user_id = ?",
                    (sid, course, synced, ver, uid))
    con.executescript(dict(db.MIGRATIONS)[62].split(";", 1)[1])
    got = [tuple(con.execute("SELECT course, course_year FROM students WHERE user_id = ?", (u,)).fetchone()) for u in ids]
    assert got == [(4, 2026), (5, 2025), (2, 2026), (1, 2027), (3, 2026)]


def test_admin_stats(env, monkeypatch):
    """The admin's stats (PLAN): online in 10 minutes, active day/week/month, students, new today; a row a night
    just after midnight from seen_at, none later in the day; counts only."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    t = int(time.time())
    assert c.get("/api/admin/stats", headers=tma(61, "Ali")).status_code == 403
    con.execute("UPDATE users SET seen_at = ?, created_at = ? WHERE id = ?", (t - 3 * 86400, t - 40 * 86400, ali["id"]))
    st = c.get("/api/admin/stats", headers=tma(60, "Boss")).json()
    assert (st["online"], st["day"], st["week"], st["month"], st["users"], st["students"], st["newToday"]) == (1, 1, 2, 2, 2, 2, 1)
    midnight = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    set_clock(monkeypatch, lambda: midnight + 3600 * 5)                          # 05:00: too late, today's visits would count
    logic.stats_day(con)
    assert not con.execute("SELECT 1 FROM stats_days").fetchone()
    set_clock(monkeypatch, lambda: midnight + 600)                               # 00:10
    logic.stats_day(con)
    logic.stats_day(con)
    assert [tuple(r) for r in con.execute("SELECT day, active, students FROM stats_days")] == [((t + 5 * 3600) // 86400 - 1, 1, 0)]  # both signed in today


def test_feature_post(env):
    """A post for everyone on top of List (§2): moderators and the admin, public posts only, one at a time, 0 days ends it."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); pres = login(c, 61, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for pid, aud in ((1, "public"), (2, "public"), (3, "clubs")):
        con.execute("INSERT INTO posts (id, org_id, author_id, audience, title, body, created_at) VALUES (?, 1, ?, ?, 'T', 'B', 0)", (pid, pres["id"], aud))
    B, P = tma(60, "Boss"), tma(61, "Pres")
    feat = lambda pid, days, h=B: c.post("/api/admin/feature", headers=h, json={"postId": pid, "days": days})
    assert feat(1, 3, P).status_code == 403 and feat(3, 3).status_code == 400 and feat(1, 30).status_code == 400
    assert feat(1, 3).json()["featured"] is True
    feat(2, 3)
    got = {p["id"]: p["featured"] for p in c.get("/api/posts", headers=B, params={"scope": "all"}).json()}
    assert got == {1: False, 2: True}                                                           # one at a time
    assert feat(2, 0).json()["featured"] is False
    login(c, 62, "ali")
    react = lambda pid: c.put(f"/api/posts/{pid}/reactions/fire", headers=tma(62)).status_code  # noqa: E731
    assert react(1) == 200 and react(3) == 404             # a members-only broadcast doesn't leak through its reactions
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'member', 0 FROM users WHERE tg_id = 62")
    assert react(3) == 200                                 # a club member reacts to it as before
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert react(1) == 404                                 # nor a hidden club's post


def test_bot_texts_match_across_languages():
    """Every bot message and share card uses the same fields in ru, kk and en: a field only one language asks for would
    fail only for the people reading it."""
    import string
    fields = lambda tpl: {f for _, f, _, _ in string.Formatter().parse(tpl or "") if f}
    for table in (texts.BOT, texts.SHARE_FRIEND, texts.SHARE_JOIN, texts.SHARE_PRES, texts.SHARE_AWARD):
        for key in (table["ru"] if table is texts.BOT else [None]):
            ru = table["ru"][key] if key else table["ru"]
            for lang in ("kk", "en"):
                other = table[lang][key] if key else table[lang]
                assert [fields(x) for x in ru if isinstance(x, str)] == [fields(x) for x in other if isinstance(x, str)], (key, lang)


def test_club_applications(env, monkeypatch):
    """Starting a club (§4.6): one pending application per person, the admins hear about it; yes = the club exists with
    the applicant as President; no = a reason, and a new application only in 30 days."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali"); zhan = login(c, 62, "zhan")
    B, A, Z = tma(60, "Boss"), tma(61, "Ali"), tma(62, "Zhan")
    # A4: a name, a description, up to 6 social links; no "why" (the form before the refactor still sends one link)
    links = ["https://instagram.com/chess.kbtu", "https://t.me/chesskbtu"]
    good = {"name": "Chess Club", "short": "CH", "description": "We play chess every week.", "emoji": "trophy_3d", "cover": 2, "links": links}
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["javascript:alert(1)"]}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["https://t.me/x"] * 7}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": "https://t.me/x"}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["https://t.me/x"] * 2}).status_code == 400  # keyed in the app
    assert c.post("/api/club-applications", headers=A, json={k: x for k, x in good.items() if k != "links"} | {"link": "javascript:alert(1)"}).status_code == 400
    app = c.post("/api/club-applications", headers=A, json=good).json()
    assert app["links"] == links and app["why"] is None
    assert app["status"] == "pending" and c.post("/api/club-applications", headers=A, json=good).json()["message"] == "pending"
    con = db.connect(cfg.db_path)
    ping = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'club_application'").fetchall()
    assert len(ping) == 1 and bot._render(con, ping[0])[2] == "capps"                               # the admin hears
    assert c.get("/api/me", headers=B).json()["counters"]["clubApps"] == 1
    assert c.get("/api/admin/club-applications", headers=A).status_code == 403
    # all or nothing: a failure after the club is made leaves no club without its President, and the application waits
    real = logic.set_role
    monkeypatch.setattr(logic.oversight, "set_role", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        c.post(f"/api/admin/club-applications/{app['id']}", headers=B, json={"approve": True})
    monkeypatch.setattr(logic.oversight, "set_role", real)
    assert not con.execute("SELECT 1 FROM orgs WHERE name = 'Chess Club'").fetchone()
    assert c.get("/api/club-applications/mine", headers=A).json()["application"]["status"] == "pending"
    done = c.post(f"/api/admin/club-applications/{app['id']}", headers=B, json={"approve": True}).json()
    assert done["status"] == "approved" and done["applicant"]["fullName"] == "Testov Ali"
    me = c.get("/api/me", headers=A).json()
    assert [(m["org"]["name"], m["role"]) for m in me["memberships"]] == [("Chess Club", "president")]
    assert c.get(f"/api/orgs/{done['orgId']}", headers=A).json()["links"] == links           # the club got them all
    told = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'club_application_decided'").fetchone()
    assert bot._render(con, told)[2] == f"cl_{done['orgId']}"
    z = c.post("/api/club-applications", headers=Z, json={k: x for k, x in good.items() if k != "links"} | {"name": "Go Club", "link": "https://t.me/go",
                                                                                                           "why": "Old form"}).json()
    assert (z["links"], z["why"]) == (["https://t.me/go"], "Old form")                          # an old client
    assert c.post(f"/api/admin/club-applications/{z['id']}", headers=B, json={"approve": False}).status_code == 400  # a reason
    assert c.post(f"/api/admin/club-applications/{z['id']}", headers=B, json={"approve": False, "reason": "There is a Go club already"}).json()["status"] == "rejected"
    assert c.get("/api/club-applications/mine", headers=Z).json()["application"]["reason"] == "There is a Go club already"
    assert c.post("/api/club-applications", headers=Z, json={**good, "name": "Go Club 2"}).status_code == 429  # 30 days


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


def test_president_link(env, monkeypatch):
    """A new club's President by link (§2): only the admin makes one, as our bot's card; the first student to open it
    leads the club (the old President steps down to Vice); once, within 7 days; a new link ends the unused old one."""
    import dataclasses
    import json
    import httpx
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali, zhan, old = login(c, 61, "ali"), login(c, 62, "zhan"), login(c, 63, "old")
    B, A, Z = tma(60, "Boss"), tma(61, "Ali"), tma(62, "Zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'chess', 'club', 'Chess Club', 'CH', 'trophy_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (old["id"],))
    sent = []
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(
        lambda r: (sent.append(json.loads(r.content)), httpx.Response(200, json={"ok": True, "result": {"id": "prep"}}))[1])))
    assert c.post("/api/share", headers=A, json={"kind": "pres", "id": 1}).status_code == 403             # the admin only
    start = lambda: re.search(r"startapp=pres_1_([0-9a-f]{24})", sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"]).group(1)  # noqa: E731
    assert c.post("/api/share", headers=B, json={"kind": "pres", "id": 1}).status_code == 200
    first = start()
    assert "http" not in sent[-1]["result"]["input_message_content"]["message_text"]
    c.post("/api/share", headers=B, json={"kind": "pres", "id": 1})
    token = start()
    assert c.post(f"/api/invites/{first}", headers=A).status_code == 404                                  # replaced
    assert c.post(f"/api/invites/{token}", headers=A).json()["myRole"] == "president"
    roles = dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())
    assert roles == {ali["id"]: "president", old["id"]: "vice"}
    assert c.post(f"/api/invites/{token}", headers=Z).status_code == 404                                  # once
    c.post("/api/share", headers=B, json={"kind": "pres", "id": 1})
    con.execute("UPDATE org_invites SET expires_at = 1 WHERE token = ?", (start(),))
    assert c.post(f"/api/invites/{start()}", headers=Z).status_code == 404                                # 7 days


def test_club_profile(env):
    """The club's own profile (Vice+, §2): name, two letters, emoji, cover, about, links, logo — only what is sent changes;
    a member can't; a taken name, a bad link or a stray value are refused and nothing changes."""
    c, cfg = env
    vice, mem = login(c, 20, "vice"), login(c, 21, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0), "
                "(2, 'go', 'club', 'Go Club', 'GO', 'trophy_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'member', 0)", (vice["id"], mem["id"]))
    V, M = tma(20, "Vice"), tma(21, "Mem")
    patch = {"name": "IT Club KBTU", "short": "it", "emoji": "rocket_3d", "cover": 4, "description": "We build things.",
             "links": ["https://instagram.com/itclub", "https://t.me/itclub"]}
    assert c.patch("/api/orgs/1", headers=M, json=patch).status_code == 403
    o = c.patch("/api/orgs/1", headers=V, json=patch).json()
    assert (o["name"], o["short"], o["emoji"], o["cover"], o["description"], o["links"], o["recruiting"]) == \
        ("IT Club", "IT", "rocket_3d", 4, "We build things.", patch["links"], True)
    assert c.patch("/api/orgs/1", headers=V, json={"recruiting": False}).json()["name"] == "IT Club"   # one field at a time
    assert c.patch("/api/orgs/1", headers=V, json={"name": "go club"}).json()["message"] == "taken"
    for bad in ({"links": ["javascript:alert(1)"]}, {"links": ["https://a.kz"] * 7}, {"cover": 9}, {"short": "ABC"}, {"emoji": "../x"},
                {"name": "X"}, {"description": "x" * 601}, {}, {"description": "ok", "cover": True}):
        assert c.patch("/api/orgs/1", headers=V, json=bad).status_code == 400, bad
    assert c.get("/api/orgs/1", headers=M).json()["description"] == "We build things."                    # nothing half-saved
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'org_edit'").fetchone()[0] == 1

    # the logo: the editor's own upload goes on and shows wherever the club does; a stray id doesn't; null takes it off
    import io
    from PIL import Image
    raw = io.BytesIO()
    Image.new("RGB", (600, 600), (40, 90, 200)).save(raw, "PNG")
    up = c.post("/api/photos", headers=V, content=raw.getvalue()).json()
    assert c.patch("/api/orgs/1", headers=V, json={"logoId": up["id"]}).json()["logo"] == up["thumb"]
    assert c.get("/api/me", headers=M).json()["memberships"][0]["org"]["logo"] == up["thumb"]
    for bad in ({"logoId": up["id"] + 1}, {"logoId": str(up["id"])}, {"logoId": True}):
        assert c.patch("/api/orgs/1", headers=V, json=bad).status_code == 400, bad
    assert c.patch("/api/orgs/1", headers=V, json={"logoId": None}).json()["logo"] is None
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'org_edit'").fetchone()[0] == 3




def test_meetings(env):
    """Studio part 2 (§2b): a meeting the whole club (or a tag) is expected at. Everyone expected hears; "can't" needs a
    reason; Head+ see the answers and who came; the door lists everyone expected and
    lets in someone who came anyway; others don't see it."""
    c, cfg = env
    pres, head, mem, mem2, out = login(c, 80, "pres"), login(c, 81, "head"), login(c, 82, "mem"), login(c, 83, "mem2"), login(c, 84, "out")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at, probation) VALUES (1, ?, ?, 0, ?)",
                    [(pres["id"], "president", 0), (head["id"], "head", 0), (mem["id"], "member", 1), (mem2["id"], "member", 1)])
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (5, 1, 'SMM', '#FF4FA3', 0)")
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (5, ?)", (mem2["id"],))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'art', 'club', 'Art', 'A', 'art_3d', 0)")
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (6, 2, 'Other', '#FF4FA3', 0)")  # another club's tag
    H = tma(81, "Head")
    start = int(time.time()) + 3600
    body = {"title": "Weekly sync", "place": "305", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF",
            "seats": None, "visibility": "members", "meeting": True}
    for bad in ({"visibility": "public"}, {"seats": 10}, {"meetingTag": 6}, {"price": 1000, "payToName": "IT Club", "payPhone": "+77010000000"}):
        assert c.post("/api/orgs/1/events", headers=H, json={**body, **bad}).status_code in (400, 403), bad
    ev = c.post("/api/orgs/1/events", headers=H, json=body).json()
    assert ev["meeting"] is True and ev["meetingTag"] is None
    c.post(f"/api/events/{ev['id']}/publish", headers=H)
    invited = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'meeting_invite'")}
    assert invited == {pres["id"], mem["id"], mem2["id"]}                        # everyone but the one who published
    assert c.get(f"/api/events/{ev['id']}", headers=tma(84)).status_code == 404  # not their club
    M, M2 = tma(82, "Mem"), tma(83, "Mem2")
    assert c.post(f"/api/events/{ev['id']}/decline", headers=M, json={}).json()["message"] == "note"   # why, please
    assert c.post(f"/api/events/{ev['id']}/decline", headers=M, json={"note": "Exam  at 6"}).json()["my"]["note"] == "Exam at 6"
    assert c.post(f"/api/events/{ev['id']}/registration", headers=M2, json={}).json()["my"]["status"] == "going"
    assert c.get(f"/api/events/{ev['id']}/meeting", headers=M2).status_code == 403                  # Head+ only
    ans = {a["person"]["id"]: a for a in c.get(f"/api/events/{ev['id']}/meeting", headers=H).json()}
    assert (ans[mem["id"]]["answer"], ans[mem["id"]]["note"]) == ("no", "Exam at 6") and ans[mem2["id"]]["answer"] == "yes"
    assert ans[pres["id"]]["answer"] == "none"
    door = {d["person"]["id"] for d in c.get(f"/api/events/{ev['id']}/door", headers=H).json()}
    assert door == {pres["id"], head["id"], mem["id"], mem2["id"]}                                    # everyone expected
    # it happens: mem said no but came; mem2 said yes and didn't; the door lets mem in by name
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, ev["id"]))
    assert c.post(f"/api/events/{ev['id']}/checkin", headers=H, json={"userId": mem["id"]}).json()["result"] == "ok"
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, ev["id"]))
    ans = {a["person"]["id"]: a for a in c.get(f"/api/events/{ev['id']}/meeting", headers=H).json()}
    assert ans[mem["id"]]["came"] and not ans[mem2["id"]]["came"]
    # a tag's meeting expects only the tag's people
    tagged = c.post("/api/orgs/1/events", headers=H, json={**body, "meetingTag": 5, "startsAt": start + 86400, "endsAt": start + 90000}).json()
    c.post(f"/api/events/{tagged['id']}/publish", headers=H)
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'meeting_invite' AND ref = ?", (f"mi:{tagged['id']}",))} == {mem2["id"]}
    assert [a["person"]["id"] for a in c.get(f"/api/events/{tagged['id']}/meeting", headers=H).json()] == [mem2["id"]]


def test_team_only_event(env):
    """A team-only event (§4.10): the club's members see it and sign up; nobody else finds it; subscribers aren't told."""
    c, cfg = env
    pres, mem, ali = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (ali["id"],))
    P, M, A = tma(70, "Pres"), tma(71, "Mem"), tma(72, "Ali")
    body = {"title": "Team sync", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "visibility": "members"}
    assert c.post("/api/orgs/1/events", headers=P, json={**body, "visibility": "leaders"}).status_code == 400
    e = c.post("/api/orgs/1/events", headers=P, json=body).json()
    assert e["visibility"] == "members"
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert [x["id"] for x in c.get("/api/events", headers=M).json()] == [e["id"]]
    assert c.get("/api/events", headers=A).json() == [] and c.get(f"/api/events/{e['id']}", headers=A).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event'").fetchone()[0] == 0     # subscribers aren't told


def test_teambuilding_thunder(env):
    """"Teambuilding thunder" (§4.11): a club's own events count (a public one doesn't), with no top: the count goes on.
    A new achievement or level is recorded at start for whoever already reached it, without a bot message; the app's
    unlock moment shows it. The reminder before a club's own event has no ticket in it."""
    c, cfg = env
    pres, mem = login(c, 90, "pres"), login(c, 91, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    P, M = tma(90, "Pres"), tma(91, "Mem")
    start = int(time.time()) + 86400

    def came(visibility: str) -> None:
        e = c.post("/api/orgs/1/events", headers=P, json={"title": "Sync", "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                            "color": "#3B6BFF", "visibility": visibility}).json()
        c.post(f"/api/events/{e['id']}/publish", headers=P)
        assert c.post(f"/api/events/{e['id']}/registration", headers=M, json={}).json()["my"]["status"] == "going"
        if visibility == "members":
            ref = con.execute("SELECT kind, ref FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' ORDER BY id DESC", (mem["id"],)).fetchone()
            text, button, link = bot._render(con, {"user_id": mem["id"], "kind": ref[0], "ref": ref[1], "lang": "ru"})
            assert "\u0411\u0438\u043b\u0435\u0442" not in text and link == f"ev_{e['id']}"   # no "Ticket": it opens the event
        con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, e["id"]))
        assert c.post(f"/api/events/{e['id']}/checkin", headers=P, json={"userId": mem["id"]}).json()["result"] == "ok"

    team = lambda: next(a for a in logic.achievements(con, mem["id"]) if a["code"] == "team")
    came("public")
    assert team()["count"] == 0
    for _ in range(3):
        came("members")
    assert (team()["count"], team()["level"]) == (3, 1)
    # no tickets: the door has the whole team, and someone who didn't sign up is let in by name
    e = c.post("/api/orgs/1/events", headers=P, json={"title": "Pizza", "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                        "color": "#3B6BFF", "visibility": "members"}).json()
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert {d["person"]["id"] for d in c.get(f"/api/events/{e['id']}/door", headers=P).json()} == {pres["id"], mem["id"]}
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, e["id"]))
    assert c.post(f"/api/events/{e['id']}/checkin", headers=P, json={"userId": mem["id"]}).json()["result"] == "ok"
    assert team()["count"] == 4
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'achievement' AND ref = 'ach:team:1'").fetchone()[0] == 1
    # as if "team" were new today: the start records what was already reached, quietly, once
    con.execute("DELETE FROM achievement_levels WHERE code = 'team'")
    con.execute("DELETE FROM meta")
    sent = con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0]
    logic.sync_levels(con)
    assert con.execute("SELECT level, seen FROM achievement_levels WHERE user_id = ? AND code = 'team'", (mem["id"],)).fetchone()[:] == (1, 0)
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == sent
    con.execute("DELETE FROM achievement_levels WHERE code = 'team'")
    logic.sync_levels(con)                                                               # the list hasn't changed since
    assert con.execute("SELECT COUNT(*) FROM achievement_levels WHERE code = 'team'").fetchone()[0] == 0


def test_message_teammate(env):
    """"Message on Telegram": a profile carries the @username to the same club's team only."""
    c, cfg = env
    pres, mem, out = login(c, 95, "pres"), login(c, 96, "mem"), login(c, 97, "out")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    con.execute("UPDATE users SET tg_username = 'mem_handle' WHERE id = ?", (mem["id"],))
    assert c.get(f"/api/users/{mem['id']}", headers=tma(95)).json()["username"] == "mem_handle"
    assert c.get(f"/api/users/{mem['id']}", headers=tma(97)).json()["username"] is None      # not their club
    assert c.get(f"/api/users/{mem['id']}", headers=tma(96)).json()["username"] is None      # nor their own card


def test_leaders_meeting(env):
    """A leaders meeting (§4.10): only an oversight org makes one; it invites every club's leaders from the chosen role up
    (the bot at once); they answer yes or no; DMP sees the answers per club; nobody else sees the event."""
    c, cfg = env
    dmp, pres, vice, mem = login(c, 80, "dmp"), login(c, 81, "pres"), login(c, 82, "vice"), login(c, 83, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", [(9, dmp["id"], "head"), (1, pres["id"], "president"), (1, vice["id"], "vice"), (1, mem["id"], "member")])
    D, P, V, M = tma(80, "Dmp"), tma(81, "Pres"), tma(82, "Vice"), tma(83, "Mem")
    body = {"title": "Leaders meeting", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "trophy_3d", "color": "#3B6BFF",
            "visibility": "leaders", "leadersFrom": "vice"}
    assert c.post("/api/orgs/1/events", headers=P, json=body).status_code == 400              # not an oversight org
    e = c.post("/api/orgs/9/events", headers=D, json=body).json()
    c.post(f"/api/events/{e['id']}/publish", headers=D)
    asked = sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'leaders_invite'"))
    assert asked == sorted([pres["id"], vice["id"]])                                             # from Vice up
    assert [x["id"] for x in c.get("/api/events", headers=P).json()] == [e["id"]] and c.get("/api/events", headers=M).json() == []
    c.post(f"/api/events/{e['id']}/registration", headers=P)
    assert c.post(f"/api/events/{e['id']}/decline", headers=V).json()["my"]["status"] == "cancelled"
    answers = c.get(f"/api/events/{e['id']}/leaders", headers=D).json()
    assert [(a["org"]["id"], sorted(p["answer"] for p in a["people"])) for a in answers] == [(1, ["no", "yes"])]
    assert c.get(f"/api/events/{e['id']}/leaders", headers=P).status_code == 403


def test_every_api_route_needs_telegram(env):
    """No /api route answers with data to a request without Telegram's initData — a new route that forgot its viewer
    fails here. The calendar file carries its own signature (§4.2); /show's pairing code is the laptop's, no Telegram
    there (it opens nothing until an organizer binds it: test_screen_pairing)."""
    import re as _re
    c, cfg = env
    open_ok = {("GET", "/api/events/{eid}/ics"), ("POST", "/api/screen/pair")}
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


def test_add_seats(env):
    """"+N seats" (§4.2): the club's Head+ only; the waitlist moves in at once, in order."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 70, "pres"), login(c, 71, "ali"), login(c, 72, "zhan"), login(c, 73, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, seats, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', 1, ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    for uid in (71, 72, 73):
        c.post("/api/events/1/registration", headers=tma(uid, "X"))
    st = lambda uid: con.execute("SELECT status FROM registrations WHERE user_id = ?", (uid,)).fetchone()[0]
    assert [st(ali["id"]), st(zhan["id"]), st(dana["id"])] == ["going", "waitlist", "waitlist"]
    assert c.post("/api/events/1/seats", headers=tma(71, "Ali"), json={"add": 1}).status_code == 403
    assert c.post("/api/events/1/seats", headers=tma(70, "Pres"), json={"add": 0}).status_code == 400
    e = c.post("/api/events/1/seats", headers=tma(70, "Pres"), json={"add": 1}).json()
    assert e["seats"] == 2 and [st(zhan["id"]), st(dana["id"])] == ["going", "waitlist"]          # in order




def test_paid_events(env):
    """§4.3: an official club's Vice+ sets the price and the Kaspi details; "Going" holds a seat for 30 min; the receipt
    turns it into a ticket at once; the same file twice is flagged and comes first for the organizer (and at the door);
    a rejected receipt ends the ticket and the seat goes on; the image is private; the details lock once someone paid;
    deleting my data deletes my receipts' images."""
    import io
    from pathlib import Path
    from PIL import Image
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'head', 0 FROM users WHERE tg_id = 21")
    start = int(time.time()) + 3600
    body = {"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 1}
    paid = {**body, "price": 2000, "payToName": " Alikhan  S. ", "payPhone": "8 (707) 123-45-67"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=paid).json()["message"] == "price"      # a student initiative
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    assert c.post("/api/orgs/1/events", headers=tma(21), json=paid).json()["message"] == "price"      # a Head sets no prices
    assert c.post("/api/orgs/1/events", headers=tma(21), json={**body, "price": None}).status_code == 200  # free stays anyone's
    for bad in ({"price": 0}, {"price": "2000"}, {"price": True}, {"payToName": "A"}, {"payPhone": "12345"}):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**paid, **bad}).status_code == 400
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=paid).json()
    assert (ev["price"], ev["payToName"], ev["payPhone"]) == (2000, "Alikhan S.", "+77071234567")
    eid = ev["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))

    held = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()
    assert held["my"]["status"] == "hold" and held["my"]["ticketCode"] is None and held["taken"] == 1
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["my"]["status"] == "waitlist"
    shot = io.BytesIO()
    Image.new("RGB", (600, 1200), (240, 240, 240)).save(shot, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["error"] == "closed"  # no seat held
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=b"%PDF-1.4").json()["message"] == "not_an_image"
    got = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=shot.getvalue()).json()
    assert got["my"]["status"] == "going" and got["my"]["ticketCode"] and got["my"]["receipt"] == "accepted"
    home = Path(cfg.db_path).parent
    assert list((home / "receipts").rglob("*.webp")) and not (home / "media").exists()                # private, never under /media

    att = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    rid = att[0]["receipt"]["id"]
    assert att[0]["receipt"]["flags"] == [] and att[1]["receipt"] is None
    img = c.get(f"/api/receipts/{rid}/image", headers=tma(21))
    assert img.headers["content-type"] == "image/webp" and "no-store" in img.headers["cache-control"]
    assert c.get(f"/api/receipts/{rid}/image", headers=tma(10)).status_code == 200                     # the sender
    assert c.get(f"/api/receipts/{rid}/image", headers=tma(11)).status_code == 404                     # nobody else
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**paid, "price": 3000}).json()["message"] == "paid"
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "title": "Gala night"}).status_code == 200  # absent keeps

    assert c.post(f"/api/receipts/{rid}/review", headers=tma(10), json={"reject": True}).status_code == 403
    assert c.post(f"/api/receipts/{rid}/review", headers=tma(21), json={"reject": True}).status_code == 204
    mine = c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]
    assert (mine["status"], mine["cancelReason"], mine["ticketCode"]) == ("cancelled", "receipt_rejected", None)
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "hold"               # the waitlist moves
    assert {"receipt_rejected", "seat_hold"} <= {k for (k,) in con.execute("SELECT kind FROM bot_outbox")}

    ticket = c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["my"]["ticketCode"]
    att = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    assert att[0]["receipt"]["flags"] == ["duplicate"] and not att[0]["receipt"]["reviewed"]
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": ticket}).json()["flagged"] is True
    c.post(f"/api/receipts/{att[0]['receipt']['id']}/review", headers=tma(20), json={"reject": False})
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()[0]["receipt"]["reviewed"] is True

    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (int(time.time()) - 5 * 3600, eid))  # a paid ticket ahead makes it wait (H2)
    for uid, name in ((11, "bob"), (10, "ali")):  # the same image: it goes when the last receipt using it does
        assert list((home / "receipts").rglob("*.webp"))
        assert delete_now(c, cfg, tma(uid)) is None
    assert not list((home / "receipts").rglob("*.*"))



def test_receipt_reading(env, monkeypatch):
    """§4.3, Oct 11: Kaspi's PDF is taken like a screenshot (in the app and by the bot); what OCR reads off a receipt
    becomes the organizer's flags, never a rejection: a smaller sum, another recipient (Tesseract reads a Latin name
    with Russian shapes), a receipt older than the event, the same receipt number again, nothing readable."""
    import io
    import pypdfium2 as pdfium
    look = lambda name: name.translate(receipt._LOOK)  # noqa: E731  (a Latin name as Tesseract's Russian model reads it)
    arman, aigerim = "\u0410\u0440\u043c\u0430\u043d \u0410.", "\u0410\u0439\u0433\u0435\u0440\u0456\u043c \u0421."  # in Cyrillic
    ru = f"(a)\nTransfer completed\n2 000T\n{look('Arman A.')}\nType Transfer...\nNo 12345678901234\n5678\nDate and time 05.10.2026 14:56\n" \
         "in Astana\nFee 0T\nSender Ivanov I.I.\nFrom Kaspi Gold"   # the fields by shape: labels may be Russian or Kazakh
    assert receipt.parse(ru) == {"amount": 2000, "recipient": look("Arman A."), "no": "123456789012345678",
                                 "paid_at": 1791194160, "sender": "Ivanov I.I."}       # 2026-10-05 14:56 in Astana
    kk = f"Transfer done\n1 500 \u20b8\n{aigerim}\nReceipt No 987654321098765432\nDate 01.10.2026 9:05\nSender Serikova A.\nFrom Kaspi Gold"
    assert receipt.parse(kk) == {"amount": 1500, "recipient": aigerim, "no": "987654321098765432", "paid_at": 1790827500, "sender": "Serikova A."}
    assert receipt.parse("a photo of a cat") == {}
    for printed, typed, same in ((look("Arman A."), "Arman A.", True), (look("Arman A."), arman, True), (arman, "Arman A.", True),
                                 (aigerim, "Aigerim S.", True), (look("Arman A."), "Arman B.", False), (look("Aisha N."), "Arman A.", False)):
        assert receipt.same_person(printed, typed) is same, (printed, typed)
    sukhrab = "\u0421\u0443\u0445\u0440\u0430\u0431"  # typed without the initial (the owner's own event): the first names
    for printed, typed, same in ((sukhrab + " \u041d.", sukhrab, True), (sukhrab + " \u041d.", "Sukhrab", True), (look("Arman A."), "Arman", True),
                                 (look("Aisha N."), "Arman", False)):
        assert receipt.same_person(printed, typed) is same, (printed, typed)

    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    ev = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Gala", "place": "Hall", "startsAt": int(time.time()) + 3600, "emoji": "laptop_3d",
                                                             "color": "#3B6BFF", "seats": 5, "price": 2000, "payToName": "Arman A.", "payPhone": "87071234567"}).json()
    eid = ev["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    made = con.execute("SELECT created_at FROM events WHERE id = ?", (eid,)).fetchone()[0]

    def pdf(w: int) -> bytes:  # a real PDF (a blank page): what Kaspi's "Share" hands over
        d, out = pdfium.PdfDocument.new(), io.BytesIO()
        d.new_page(w, 700)
        d.save(out)
        return out.getvalue()

    seen = []
    def fake(fields):
        def read(im):
            seen.append(im.size)
            return fields
        monkeypatch.setattr(receipt, "read", read)

    fake({"amount": 1500, "no": "123456789012345678", "recipient": look("Aisha N."), "paid_at": made - 86400, "sender": "Ivanov I.I."})
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    pay = lambda uid: (lambda d: (d["payToName"], d["payPhone"]))(c.get(f"/api/events/{eid}", headers=tma(uid)).json())  # noqa: E731
    assert pay(11) == (None, None)                                         # no seat: the treasurer's Kaspi phone stays hidden
    assert pay(10) == pay(20) == ("Arman A.", "+77071234567")              # the one paying and the club see it
    mine = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(500)).json()["my"]
    assert mine["status"] == "going" and mine["receiptFlags"] == ["amount_short", "recipient_mismatch", "too_early"]  # the student sees it too
    assert pay(10) == ("Arman A.", "+77071234567") and pay(11) == (None, None)   # still his after the seat is taken
    assert abs(seen[-1][0] - 500 * 300 / 72) < 2 and abs(seen[-1][1] - 700 * 300 / 72) < 2  # the page, read at ~300 dpi
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}["Testov Ali"]
    assert got["flags"] == ["amount_short", "recipient_mismatch", "too_early"]
    assert (got["amount"], got["sender"], got["no"], got["paidAt"]) == (1500, "Ivanov I.I.", "123456789012345678", made - 86400)
    assert {x["id"]: x["toCheck"] for x in c.get("/api/orgs/1/events", headers=tma(20)).json()}[eid] == 1  # Studio's "receipts to check"

    # the bot: a PDF sent to it goes to bob's only seat on hold; the number came before, the rest is fine
    class Http:
        def __init__(self):
            self.posts = []
        async def get(self, url, params=None, **kw):
            r = type("R", (), {})()
            r.json = lambda: {"ok": True, "result": {"file_path": "documents/r.pdf"}}
            r.content = pdf(501)
            return r
        async def post(self, url, json=None, **kw):
            self.posts.append((url.rsplit("/", 1)[1], json))
    http = Http()
    doc = lambda uid, mid: {"message_id": mid, "chat": {"id": uid, "type": "private"}, "from": {"id": uid}, "date": int(time.time()),  # noqa: E731
                            "document": {"file_id": f"f{mid}", "mime_type": "application/pdf", "file_size": 900}}
    fake({"amount": 2000, "no": "123456789012345678", "recipient": look("Arman A."), "paid_at": made + 60})
    assert texts.bot_message("ru", "receipt_none")[0] in asyncio.run(bot._receipt(cfg, http, con, doc(11, 1)))["text"]  # no seat held yet
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    answer = asyncio.run(bot._receipt(cfg, http, con, doc(11, 2)))
    assert "Gala" in answer["text"] and answer["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(f"startapp=tk_{eid}")
    assert texts.receipt_why("ru", ["duplicate"]) in answer["text"]  # looks wrong: said at once, the ticket stays
    assert c.get(f"/api/events/{eid}", headers=tma(11)).json()["my"]["status"] == "going"
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert got["Testov Bob"]["flags"] == ["duplicate"]
    assert con.execute("SELECT via FROM receipts ORDER BY id DESC").fetchone()[0] == "bot"

    # two seats on hold: the bot asks which, and the tap finds the file in the message its buttons answer
    ev2 = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Quiz", "place": "305", "startsAt": int(time.time()) + 7200, "emoji": "laptop_3d",
                                                              "color": "#3B6BFF", "price": 500, "payToName": "Arman A.", "payPhone": "87071234567"}).json()
    c.post(f"/api/events/{ev2['id']}/publish", headers=tma(20))
    for e in (eid, ev2["id"]):
        c.post(f"/api/events/{e}/registration", headers=tma(12), json={})
    ask = asyncio.run(bot._receipt(cfg, http, con, doc(12, 3)))
    assert ask["reply_parameters"] == {"message_id": 3} and len(ask["reply_markup"]["inline_keyboard"]) == 2
    fake({})                                                                           # read, but nothing there: not a receipt (a selfie)
    tap = {"id": "q", "from": {"id": 12}, "data": f"rc:{ev2['id']}", "message": {"message_id": 4, "chat": {"id": 12}, "reply_to_message": doc(12, 3)}}
    asyncio.run(bot._tapped(cfg, http, con, tap))
    assert texts.bot_message("ru", "receipt_not")[0] in http.posts[1][1]["text"]
    assert c.get(f"/api/events/{ev2['id']}", headers=tma(12)).json()["my"]["status"] == "hold"  # refused, nothing kept
    assert c.post(f"/api/events/{ev2['id']}/receipt", headers=tma(12), content=pdf(505)).json()["message"] == "not_receipt"
    fake({"amount": 500, "no": "777000111222333444", "recipient": look("Arman A."), "paid_at": made + 60})
    http.posts.clear()
    asyncio.run(bot._tapped(cfg, http, con, tap))
    assert [m for m, _ in http.posts] == ["answerCallbackQuery", "editMessageText"] and "Quiz" in http.posts[1][1]["text"]
    assert c.get(f"/api/events/{ev2['id']}", headers=tma(12)).json()["my"]["status"] == "going"
    assert c.get(f"/api/events/{eid}", headers=tma(12)).json()["my"]["status"] == "hold"  # the other one still waits

    # another file replaces a receipt nobody looked at: twice the price pays for two (no flag), 1.5 times doesn't
    rows_of = lambda: con.execute("SELECT COUNT(*) FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.user_id = (SELECT id FROM users WHERE tg_id = 10)").fetchone()[0]  # noqa: E731
    fake({"amount": 4000, "no": "555000111222333444", "recipient": look("Arman A."), "paid_at": made + 60})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(502)).json()["my"]["receiptFlags"] == [] and rows_of() == 1
    fake({"amount": 3000, "no": "555000111222333445", "recipient": look("Arman A."), "paid_at": made + 60})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(503)).json()["my"]["receiptFlags"] == ["amount_over"]
    got = {a["fullName"]: a["receipt"] for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}["Testov Ali"]
    assert got["flags"] == ["amount_over"] and got["amount"] == 3000 and rows_of() == 1
    assert c.post(f"/api/receipts/{got['id']}/review", headers=tma(20), json={"reject": False}).status_code < 300
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["receiptFlags"] == []           # looked at: settled
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=pdf(504)).status_code >= 400  # and no longer replaceable

def test_deadline_and_free_first(env):
    """A registration deadline closes "Going" (NULL: open until the start); a paid event's first N 1st-year students
    come free: going at once, no hold, no receipt; the waitlist hands a freed free seat to the next 1st-year; the
    number can change after receipts are in, the payment details can't."""
    import io
    from PIL import Image
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'head', 0 FROM users WHERE tg_id = 21")
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dB%07d', ?, user_id) WHERE user_id IN (SELECT id FROM users WHERE tg_id IN (10, 11, 13))",
                (INTAKE % 100,))  # ann, bob, dan: this year's intake (the ID says the year, audit M3)
    # migration 58 (M3): a year typed in since the portal closed becomes the ID's; the portal's own stays (a repeater)
    con.execute("UPDATE students SET course = 1, consent_at = 1792350000 WHERE user_id = (SELECT id FROM users WHERE tg_id = 12)")
    con.execute("UPDATE students SET course = 1, consent_at = 1792000000 WHERE user_id = (SELECT id FROM users WHERE tg_id = 13)")
    con.executescript(dict(db.MIGRATIONS)[58])
    assert [r[0] for r in con.execute("SELECT course FROM students s JOIN users u ON u.id = s.user_id WHERE u.tg_id IN (12, 13) ORDER BY u.tg_id")] \
        == [logic.course_of("24B0000001"), 1] != [1, 1]
    con.execute("UPDATE students SET course = 2 WHERE user_id = (SELECT id FROM users WHERE tg_id = 12)")
    start = int(time.time()) + 7200
    body = {"title": "Gala", "place": "Hall", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 3,
            "price": 2000, "payToName": "Alikhan S.", "payPhone": "87071234567", "freeFirst": 1, "regUntil": start - 600}
    for bad in ({"regUntil": start + 1}, {"regUntil": "soon"}, {"freeFirst": "5"}, {"freeFirst": True}, {"freeFirst": 5001}):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**body, **bad}).status_code == 400
    assert c.post("/api/orgs/1/events", headers=tma(21), json=body).json()["message"] == "price"           # Vice+ only
    free = c.post("/api/orgs/1/events", headers=tma(21), json={**body, "price": None, "freeFirst": 5}).json()
    assert free["freeFirst"] is None and free["regUntil"] == start - 600                                   # no price, no quota
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    eid = ev["id"]
    assert (ev["freeFirst"], ev["freeLeft"], ev["regUntil"]) == (1, 1, start - 600)
    c.post(f"/api/events/{eid}/publish", headers=tma(20))

    ann = c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()                      # 1st year: free
    assert (ann["my"]["status"], ann["my"]["free"], bool(ann["my"]["ticketCode"]), ann["freeLeft"]) == ("going", True, True, 0)
    bob = c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()                      # 1st year, none left
    assert (bob["my"]["status"], bob["my"]["free"]) == ("hold", False)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(12), json={}).json()["my"]["status"] == "hold"  # 2nd year pays
    assert c.post(f"/api/events/{eid}/registration", headers=tma(13), json={}).json()["my"]["status"] == "waitlist"
    att = {a["fullName"]: a for a in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert att["Testov Ann"]["free"] and not att["Testov Bob"]["free"]

    assert c.delete(f"/api/events/{eid}/registration", headers=tma(10)).status_code == 200                 # ann gives it back
    dan = c.get(f"/api/events/{eid}", headers=tma(13)).json()
    assert (dan["my"]["status"], dan["my"]["free"], dan["freeLeft"]) == ("going", True, 0)                 # the next 1st-year
    assert ("seat_free", f"event:{eid}") in {tuple(r) for r in con.execute("SELECT kind, ref FROM bot_outbox")}

    shot = io.BytesIO()
    Image.new("RGB", (600, 1200), (240, 240, 240)).save(shot, "PNG")
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=shot.getvalue()).json()["my"]["status"] == "going"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "freeFirst": 2}).json()["freeLeft"] == 1  # still changes
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "freeFirst": 2, "price": 2500}).json()["message"] == "paid"
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "freeFirst": 2, "title": "Gala night"}).status_code == 200

    login(c, 15, "fay")                                                                                    # a 1st-year master pays
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dM%07d', ?, user_id) WHERE user_id = (SELECT id FROM users WHERE tg_id = 15)",
                (INTAKE % 100,))
    con.execute("UPDATE events SET seats = 10 WHERE id = ?", (eid,))
    fay = c.post(f"/api/events/{eid}/registration", headers=tma(15), json={}).json()
    assert (fay["my"]["status"], fay["my"]["free"], fay["freeLeft"]) == ("hold", False, 1)

    con.execute("UPDATE events SET reg_until = ? WHERE id = ?", (int(time.time()) - 1, eid))
    late = c.post(f"/api/events/{eid}/registration", headers=tma(14), json={}).json()
    assert (late["error"], late["message"]) == ("closed", "deadline")


def test_departments(env):
    """Departments (PLAN item 47): a tag marked department, one per person or none. A Vice+ puts anyone anywhere; a
    Head moves those below them into or out of their own department only, never themselves; plain tags leave the
    department alone."""
    c, cfg = env
    for tg, name in ((20, "pres"), (21, "vic"), (22, "hed"), (23, "hed2"), (10, "ann"), (11, "bob")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for tg, role in ((20, "president"), (21, "vice"), (22, "head"), (23, "head"), (10, "member"), (11, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, ?, 0 FROM users WHERE tg_id = ?", (role, tg))
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 23, 10, 11)}
    put = lambda by, tg, body: c.patch(f"/api/orgs/1/members/{uid[tg]}", headers=tma(by), json=body)  # noqa: E731
    dept = lambda tg: next(m for m in c.get("/api/orgs/1/members", headers=tma(20)).json() if m["person"]["id"] == uid[tg])["dept"]  # noqa: E731
    tags = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "SMM", "color": "#18A9DB", "department": True}).json()["tags"]
    smm = tags[0]["id"]
    assert tags[0]["department"] is True
    dev = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "Dev", "color": "#2FBF71", "department": True}).json()["tags"][1]["id"]
    star = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "Star", "color": "#FFB23D"}).json()["tags"][2]["id"]
    assert put(21, 22, {"dept": smm}).status_code == 200 and put(21, 23, {"dept": dev}).status_code == 200
    assert put(21, 10, {"dept": star}).status_code == 400                       # a plain tag isn't a department
    assert put(22, 10, {"dept": smm}).status_code == 200 and dept(10) == smm     # a Head: into their own
    assert put(22, 10, {"dept": dev}).status_code == 403                        # not into another's
    assert put(23, 10, {"dept": None}).status_code == 403                       # not out of another's
    assert put(22, 22, {"dept": None}).status_code == 403                       # not themselves
    assert put(22, 23, {"dept": smm}).status_code == 403                        # not a peer
    assert put(21, 10, {"dept": dev}).status_code == 200 and dept(10) == dev     # a Vice+: anywhere, one at a time
    assert con.execute("SELECT COUNT(*) FROM member_tags WHERE user_id = ?", (uid[10],)).fetchone()[0] == 1
    assert put(21, 10, {"tags": [star]}).status_code == 200 and dept(10) == dev  # tags leave the department alone
    meet = {"title": "SMM sync", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": None, "visibility": "members", "meeting": True}
    assert c.post("/api/orgs/1/events", headers=tma(22), json={**meet, "meetingTag": dev}).json().get("message") == "dept"  # PLAN 35
    assert c.post("/api/orgs/1/events", headers=tma(22), json=meet).json().get("message") == "dept"                # not the whole club
    assert c.post("/api/orgs/1/events", headers=tma(22), json={**meet, "meetingTag": smm}).status_code == 200
    assert c.post("/api/orgs/1/events", headers=tma(21), json=meet).status_code == 200                              # a Vice calls anyone
    assert c.get("/api/orgs/1/team", headers=tma(22)).json()["myDept"] == smm
    assert put(23, 10, {"dept": None}).status_code == 200 and dept(10) is None   # out of the Head's own
    assert put(22, 11, {"dept": smm}).status_code == 200
    assert c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(22), json={"name": "SMM", "color": "#18A9DB", "department": False}).status_code == 403  # Vice+ only
    assert c.post("/api/orgs/1/tags", headers=tma(22), json={"name": "Mine", "color": "#18A9DB", "department": True}).status_code == 403
    assert c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(22), json={"name": "SMM team", "color": "#18A9DB", "department": True}).status_code == 200  # a rename is fine
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (dev, uid[11]))  # two departments from before
    assert put(22, 11, {"dept": None}).status_code == 200                       # the Head takes out of their own only
    assert dept(11) == dev
    c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(21), json={"name": "SMM", "color": "#18A9DB", "department": False})
    put(21, 11, {"dept": None}); con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (smm, uid[11]))
    assert dept(11) is None and smm in next(m for m in c.get("/api/orgs/1/members", headers=tma(20)).json() if m["person"]["id"] == uid[11])["tags"]
    login(c, 12, "cat"); login(c, 13, "dan")                                     # a link straight into a department
    assert c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": star}).status_code == 400
    assert c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": "x"}).status_code == 400
    tok = c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": dev}).json()["token"]
    assert c.post(f"/api/invites/{tok}", headers=tma(12)).status_code == 200
    uid[12] = con.execute("SELECT id FROM users WHERE tg_id = 12").fetchone()[0]
    assert dept(12) == dev
    tok = c.post("/api/orgs/1/invites", headers=tma(21)).json()["token"]                # no department, as before
    assert c.post(f"/api/invites/{tok}", headers=tma(13)).status_code == 200
    uid[13] = con.execute("SELECT id FROM users WHERE tg_id = 13").fetchone()[0]
    assert dept(13) is None


def test_team_two(env):
    """Team 2.0 (§2b): the club's own roles are a name on a level (Vice+, strictly below their own); tags are groups
    (Head+); probation is a label (Head+ put it on, the person and Head+ see it, a Vice+ takes it off); a Head's removal is a request, a Vice+ removes at once; a ban keeps
    them out of applications and the link until lifted."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "vic"), (22, "hed"), (10, "ann"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for tg, role in ((20, "president"), (21, "vice"), (22, "head"), (10, "member"), (11, "member"), (12, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, ?, 0 FROM users WHERE tg_id = ?", (role, tg))
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 10, 11, 12)}
    member = lambda viewer, tg: next(m for m in c.get("/api/orgs/1/members", headers=tma(viewer)).json() if m["person"]["id"] == uid[tg])  # noqa: E731
    outbox = lambda kind: [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = ?", (kind,))]  # noqa: E731

    # roles: a name and colour on a level below the maker's own
    smm = {"name": "SMM lead", "color": "#FF4FA3", "level": "head"}
    assert c.post("/api/orgs/1/roles", headers=tma(22), json=smm).status_code == 403                  # a Head makes none
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={**smm, "level": "vice"}).status_code == 403
    for bad in ({"color": "pink"}, {"name": ""}, {"name": "x" * 25}, {"level": "president"}):
        assert c.post("/api/orgs/1/roles", headers=tma(21), json={**smm, **bad}).status_code == 400
    rid = c.post("/api/orgs/1/roles", headers=tma(21), json=smm).json()["roles"][0]["id"]
    assert c.post("/api/orgs/1/roles", headers=tma(20), json={**smm, "name": "smm LEAD"}).json()["message"] == "taken"
    treasurer = c.post("/api/orgs/1/roles", headers=tma(20), json={"name": "Treasurer", "color": "#2FBF71", "level": "vice"}).json()["roles"][1]["id"]
    assert c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"roleId": treasurer}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"roleId": rid})
    ann = member(11, 10)
    assert (ann["role"], ann["title"], ann["titleColor"]) == ("head", "SMM lead", "#FF4FA3")
    assert c.get("/api/me", headers=tma(10)).json()["memberships"][0]["title"] == "SMM lead"
    assert c.get("/api/orgs/1", headers=tma(10)).json()["myTitle"] == "SMM lead"
    assert c.patch(f"/api/orgs/1/roles/{treasurer}", headers=tma(21), json={"name": "Cash", "color": "#2FBF71", "level": "head"}).status_code == 403
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(20), json={**smm, "level": "member"})                # its people move with it
    assert member(20, 10)["role"] == "member"
    c.delete(f"/api/orgs/1/roles/{rid}", headers=tma(21))
    assert (member(20, 10)["role"], member(20, 10)["title"]) == ("member", None)
    assert c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"role": "head"}).json()[2]["role"] == "head"  # the old way still works
    c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"role": "member"})

    # the toggles: a role is its rights; the highest ranks it; only rights I have, below my level
    made = c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "SMM", "color": "#FF4FA3", "rights": ["posts", "posts"]}).json()["roles"]
    r_smm = next(r for r in made if r["name"] == "SMM")
    assert (r_smm["rights"], r_smm["level"]) == (["door", "posts"], "head")  # the door is everyone's
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "Cashier", "color": "#2FBF71", "rights": ["money"]}).status_code == 403
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "X", "color": "#2FBF71", "rights": ["nope"]}).status_code == 400
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"roleId": r_smm["id"]})
    assert c.get("/api/me", headers=tma(11)).json()["memberships"][0]["rights"] == ["door", "posts"]
    assert c.get("/api/orgs/1", headers=tma(11)).json()["myRights"] == ["door", "posts"]
    post = {"title": "Hello", "body": "We meet on Friday", "audience": "public"}
    assert c.post("/api/orgs/1/posts", headers=tma(11), json=post).status_code == 200            # their toggle
    assert c.post("/api/orgs/1/tags", headers=tma(11), json={"name": "Nope", "color": "#18A9DB"}).status_code == 403  # not theirs
    assert c.get("/api/orgs/1/join-requests", headers=tma(11)).status_code == 403
    assert c.get("/api/me", headers=tma(22)).json()["memberships"][0]["rights"] == ["door", "events", "posts", "people", "casting"]  # a level: its rights
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"role": "member"})
    c.delete(f"/api/orgs/1/roles/{r_smm['id']}", headers=tma(21))

    # tags: groups of people, Head+, on themselves or anyone below them
    assert c.post("/api/orgs/1/tags", headers=tma(10), json={"name": "SMM", "color": "#18A9DB"}).status_code == 403
    tag = c.post("/api/orgs/1/tags", headers=tma(22), json={"name": "SMM", "color": "#18A9DB"}).json()["tags"][0]["id"]
    assert c.patch(f"/api/orgs/1/members/{uid[22]}", headers=tma(22), json={"tags": [tag]}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(22), json={"tags": [tag]}).status_code == 403
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"tags": [tag + 99]}).status_code == 400
    # the Vice and the President tag each other and themselves; a Vice takes a role of their own level
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(21), json={"tags": [tag]}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(20), json={"tags": []}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(21), json={"roleId": treasurer}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(21), json={"role": "head"}).status_code == 403
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(21), json={"roleId": treasurer}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(20), json={"role": "vice"})
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"tags": [tag]})
    assert member(12, 11)["tags"] == [tag] and c.get("/api/orgs/1/team", headers=tma(12)).json()["tags"][0]["count"] == 2
    assert "removals" not in c.get("/api/orgs/1/team", headers=tma(22)).json()                         # Vice+ only

    # probation: a label Head+ put on, only the President or a Vice take off (passed: the bot congratulates)
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(10), json={"probation": True}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"probation": True})
    assert member(22, 11)["probation"] and member(11, 11)["probation"] and "probation" not in member(12, 11)  # theirs and the leaders' only
    assert "probation" not in member(22, 21) and "probation" in member(21, 22)                    # a Head can't see the Vice's (L10)
    assert texts._cell("\t=1+1") == "'\t=1+1" and texts._cell("\r@x")[0] == "'"                  # CSV: no formula behind a tab (L4)
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"probation": False}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"probation": False})               # passed
    assert not member(22, 11)["probation"] and outbox("probation_passed") == [uid[11]]

    # removal: a Head asks, the President or a Vice decides; a ban keeps them out until lifted
    assert c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(10), json={}).status_code == 403
    assert c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(22), json={"ban": True, "note": "spam"}).json() == {"done": False}
    q = c.get("/api/orgs/1/team", headers=tma(20)).json()["removals"][0]
    assert (q["by"]["id"], q["ban"], q["note"]) == (uid[22], True, "spam")
    ask = con.execute("SELECT ref, user_id FROM bot_outbox WHERE kind = 'removal_ask' AND ref = ?", (f"rm:{q['id']}",)).fetchone()
    assert "and ban them" in bot._render(con, {"kind": "removal_ask", "ref": ask[0], "lang": "en", "user_id": ask[1]})[0]
    assert c.post(f"/api/removals/{q['id']}", headers=tma(22), json={"approve": True}).status_code == 403
    c.post(f"/api/removals/{q['id']}", headers=tma(20), json={"approve": False})
    assert member(20, 12)["role"] == "member"                                                         # kept
    q = c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(22), json={"ban": True}).json()
    rid2 = c.get("/api/orgs/1/team", headers=tma(21)).json()["removals"][0]["id"]
    assert c.post(f"/api/removals/{rid2}", headers=tma(21), json={"approve": True}).status_code == 204
    assert c.post(f"/api/removals/{rid2}", headers=tma(20), json={"approve": True}).status_code == 409  # answered already
    assert all(m["person"]["id"] != uid[12] for m in c.get("/api/orgs/1/members", headers=tma(20)).json())
    assert c.post("/api/orgs/1/join-requests", headers=tma(12)).json()["message"] == "banned"
    token = c.post("/api/orgs/1/invites", headers=tma(21)).json()["token"]
    assert c.post(f"/api/invites/{token}", headers=tma(12)).json()["message"] == "banned"
    assert [b["person"]["id"] for b in c.get("/api/orgs/1/team", headers=tma(21)).json()["bans"]] == [uid[12]]
    assert c.delete(f"/api/orgs/1/bans/{uid[12]}", headers=tma(22)).status_code == 403
    assert c.delete(f"/api/orgs/1/bans/{uid[12]}", headers=tma(21)).status_code == 204
    assert c.post(f"/api/invites/{token}", headers=tma(12)).status_code == 200                           # back by the link
    assert c.post(f"/api/orgs/1/members/{uid[11]}/remove", headers=tma(21), json={}).json() == {"done": True}  # a Vice at once


def test_streak_pauses():
    # weeks with a check-in, weeks that had public events, this week
    assert logic._streak({1, 2, 4}, {1, 2, 4}, 6) == (3, 3)     # 3 and 5 had no events: no break; 6 is still on
    assert logic._streak({1, 2, 4}, {1, 2, 3, 4}, 6) == (2, 1)  # 3 had events and I missed them
    assert logic._streak({1, 2}, {1, 2, 5}, 6) == (2, 0)        # 5 went by without me
    assert logic._streak(set(), {1}, 6) == (0, 0)


def test_memo(env, monkeypatch):
    """PLAN "Memo in one tap": next week's events that ask DMP for something become DMP's complex memos in one
    email, signed by whoever opens it; Wednesday morning the President and Vices hear it's ready. A place may be left
    to be confirmed: the memo then asks for any room, the organizer hears 7/3/1/0 days before, and typing the room in
    later sends nobody a message (the 2-hour reminder says it)."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ali")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("UPDATE students SET middle_name = 'Erlanovich', phone = '87012345678' WHERE user_id = (SELECT id FROM users WHERE tg_id = 20)")
    monday = logic._next_week()
    base = {"emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    asks = {"room": {"any": True, "projector": True}, "guests": {"side": "tole", "list": "Ivanov Ivan, Satbayev University\n"}}
    a = c.post("/api/orgs/1/events", headers=tma(20), json={**base, "title": "Hackday", "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "memo": asks}).json()
    assert a["memo"] == asks                                                                  # the editor gets it back (Head+)
    b = c.post("/api/orgs/1/events", headers=tma(20), json={**base, "title": "Quiz", "place": "", "startsAt": monday + 3 * 86400 + 13 * 3600, "memo": {"room": {}}}).json()
    c.post("/api/orgs/1/events", headers=tma(20), json={**base, "title": "Talk", "place": "Atrium", "startsAt": monday + 2 * 86400})
    assert c.post("/api/orgs/1/events", headers=tma(20), json={**base, "title": "X", "place": "", "startsAt": monday, "memo": {"cake": {}}}).status_code == 400
    for e in (a, b):
        c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    assert c.get(f"/api/events/{a['id']}", headers=tma(10)).json()["memo"] is None             # students never see it

    m = c.get("/api/orgs/1/memo", headers=tma(20)).json()
    assert m["to"] == "youth_policy@kbtu.kz" and "IT Club" in m["subject"] and [x["title"] for x in m["events"]] == ["Hackday", "Quiz"]
    assert [x["title"] for x in m["without"]] == ["Talk"]
    text = m["text"]
    assert text.startswith(f"{texts.MEMO2_TO}\n{texts.MEMO2_TITLE[1]}\n")                   # one memo for the week
    assert "«Hackday»" in text.split("\n")[3] and "«Quiz»" in text.split("\n")[3]
    assert "№305" in text and "Ivanov Ivan, Satbayev University" in text and texts.memo_day(a["startsAt"]) in text
    numbered = [x for x in text.split("\n") if x[:3] in ("1) ", "2) ", "3) ")]
    assert len(numbered) == 3 and "305" in numbered[0] and "50" in numbered[2]               # numbered through the memo
    assert text.count("Pres Testov") == 3 and "Pres Testov\n+7 (701) 234 56 78\n-------" in text       # kk and ru, then the Latin one
    pos = texts.MEMO2_POS["president"]
    assert "\n".join((texts.MEMO2_SIGN["kk"][0], texts.MEMO2_SIGN["kk"][1].format(org="IT Club", pos=pos["kk"]))) in text
    assert "Regards and best wishes,\nPresident of Student Organization «IT Club»\nPres Testov" in text
    assert c.get("/api/orgs/1/memo", headers=tma(10)).status_code == 403

    # Wednesday 10:00 in Almaty: the President hears it once
    wed = monday - 5 * 86400 + 10 * 3600
    set_clock(monkeypatch, lambda: wed)
    logic.memo_week(con)
    logic.memo_week(con)
    sent = con.execute("SELECT kind, ref FROM bot_outbox WHERE kind = 'memo_ready'").fetchall()
    assert [tuple(r) for r in sent] == [("memo_ready", f"memo:1:{monday}")]
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'memo_ready'").fetchone()
    text, button, start = bot._render(con, row)
    assert "IT Club" in text and start == "memo_1"

    # the place still to be confirmed: the organizer hears it 3 days before (Friday 10:00 for the Monday after)
    set_clock(monkeypatch, lambda: b["startsAt"] - 3 * 86400 - 3 * 3600)
    logic.tba_day(con)
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'place_tba'").fetchone()
    assert row and "Quiz" in bot._render(con, row)[0]
    # DMP gave a room: typed in, nobody is told now
    c.post(f"/api/events/{b['id']}/registration", headers=tma(10), json={})
    before = con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'event_changed'").fetchone()[0]
    upd = c.patch(f"/api/events/{b['id']}", headers=tma(20), json={**base, "title": "Quiz", "place": "Aud. 412", "startsAt": b["startsAt"]})
    assert upd.status_code == 200 and con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'event_changed'").fetchone()[0] == before


def test_memo_v2(env, monkeypatch):
    """Memo v2 (PLAN stage 2): one memo for the week with every request, a meeting's own line, the signature in
    kk, ru, en with the Latin name (fixed once); the secretary's "memo" right; sent events leave it until an edit;
    later events behind a switch; Wednesday's message to everyone with the right."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "sec"), (22, "head"), (10, "ali")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'stx', 'club', 'StudEx', 'SX', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_roles (id, org_id, name, color, level, created_at, rights) VALUES (1, 1, ?, '#888888', 'vice', 0, 'door,events,memo')",
                ("\u0421\u0435\u043a\u0440\u0435\u0442\u0430\u0440\u044c",))  # the role typed in Russian: "Secretary"

    con.execute("INSERT INTO org_members (org_id, user_id, role, role_id, joined_at) VALUES (1, ?, 'president', NULL, 0), (1, ?, 'vice', 1, 0), (1, ?, 'head', NULL, 0)",
                (uid[20], uid[21], uid[22]))
    cyr = ("\u0410\u0439\u0433\u0435\u0440\u0438\u043c", "\u0421\u0430\u043f\u0430\u0440\u043e\u0432\u0430")  # her portal name in Cyrillic
    con.execute("UPDATE students SET first_name = ?, last_name = ?, phone = '87001112233' WHERE user_id = ?", (*cyr, uid[21]))
    monday = logic._next_week()
    every = {"room": {"any": False, "projector": True, "board": True, "capacity": 40, "slots": [{"date": time.strftime("%Y-%m-%d", time.gmtime(monday + 4 * 86400 + 5 * 3600)), "from": "15:00", "to": "17:00"}]},
             "guests": {"side": "turgut", "list": "Ivanov Ivan, Satbayev University"},
             "provide": {"jbl": True, "tables": 2, "chairs": 10, "mixer": True, "cooler": 30, "other": "extension cord"},
             "promo": {"place": "Floor 1", "dates": ["2026-10-13", "2026-10-14", "2026-11-03"], "from": "12:00", "to": "18:00"},
             "gear": {"items": "Speaker", "outDate": "2026-10-20", "outTime": "17:00", "side": "kazybek"},
             "print": {"items": [{"name": "Poster", "count": 5, "format": "A3", "bw": False, "density": 2}]},
             "film": {"date": "2026-10-21", "from": "10:00", "to": "12:00", "note": "interview"}}
    base = {"emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    a = c.post("/api/orgs/1/events", headers=tma(21), json={**base, "title": "Hackday", "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "memo": every})
    assert a.status_code == 200
    a = a.json()
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, visibility, meeting, memo, created_by, created_at, updated_at)
        VALUES (90, 1, 'draft', 'General meeting', '', ?, 'laptop_3d', '#3B6BFF', 'members', 1, '{"room": {"capacity": 80}}', ?, 0, 0)""",
                (monday + 2 * 86400 + 14 * 3600, uid[20]))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, memo, created_by, created_at, updated_at)
        VALUES (91, 1, 'draft', 'Big fair', '', ?, 'laptop_3d', '#3B6BFF', '{"room": {"dorm": true, "dormPlace": "gym"}}', ?, 0, 0)""",
                (monday + 15 * 86400, uid[20]))
    assert c.get("/api/orgs/1/memo", headers=tma(22)).status_code == 403                    # a Head without "memo"
    m = c.get("/api/orgs/1/memo", headers=tma(21)).json()                                   # the secretary has it
    assert [x["title"] for x in m["events"]] == ["Hackday", "General meeting"] and [x["title"] for x in m["later"]] == ["Big fair"]
    t = m["text"]
    assert texts.MEMO2_FOR["meeting"].split("{")[0] + "General meeting»" in t
    assert texts.MEMO2_FOR["event"].split("{")[0] + "Hackday»" in t
    provide = [texts.MEMO2_PROVIDE[k].format(n=n) for k, n in (("jbl", 1), ("tables", 2), ("chairs", 10), ("mixer", 1), ("cooler", 30))]
    sec = texts.MEMO2_POS["secretary"]
    for bit in ("305 ", texts.MEMO2_ROOM_EXTRA["projector"], texts.MEMO2_ROOM_EXTRA["board"], " 40 ", f"{texts.memo_day(monday + 4 * 86400 + 43200)}\n",
                "15:00-17:00", texts.MEMO2_GUESTS_DORM.format(side=texts.MEMO2_DORM_SIDES["turgut"]),
                texts.MEMO2_PROVIDE_HEAD.format(items="; ".join([*provide, "extension cord"])), texts.MEMO2_QUIET,
                texts.MEMO2_DATES.format(dates=texts._dates(every["promo"]["dates"])),
                f"{texts.MEMO2_FILM}\n", "10:00-12:00", "interview", texts.MEMO2_SIGN["ru"][1].format(org="StudEx", pos=sec["ru"]) + f"\n{' '.join(cyr)}\n+7 (700) 111 22 33",
                texts.MEMO2_SIGN["kk"][1].format(org="StudEx", pos=sec["kk"]), "Secretary of Student Organization «StudEx»\nAigerim Saparova"):
        assert bit in t, bit
    assert texts._dates(["2026-10-14", "2026-10-13", "2026-11-03"]) == f"13, 14 {texts.MONTHS['ru'][9]} \u0438 3 {texts.MONTHS['ru'][10]} 2026"
    seventh = next(x for x in t.split("\n") if x.startswith("7) "))
    assert "80" in seventh and "Poster" not in t                                            # the meeting's room: numbered on
    # printing goes in its own letter to the Publishing Center, signed in Russian
    pr = m["print"]
    assert pr["to"] == "ic@kbtu.kz" and "Hackday" in pr["subject"] and "General meeting" not in pr["subject"]
    for bit in ("1) ", "Poster", "A3", f"{texts.MEMO2_DENSITY[2]} ", texts.MEMO2_SIGN["ru"][1].format(org="StudEx", pos=sec["ru"]), "+7 (700) 111 22 33"):
        assert bit in pr["text"], bit
    assert m["guests"] and m["sign"]["nameEn"] == "Aigerim Saparova" and not m["sign"]["fixed"]
    assert "Big fair" in c.get("/api/orgs/1/memo?later=true", headers=tma(21)).json()["text"]   # the switch
    m = c.put("/api/orgs/1/memo/sign", headers=tma(21), json={"nameEn": "Aigerim Saparova-Lee", "kk": "", "ru": "", "en": ""}).json()
    assert "Aigerim Saparova-Lee" in m["text"] and m["sign"]["fixed"] and m["sign"]["ru"] == texts.MEMO2_POS["secretary"]["ru"]

    # opened, then "Sent it?" -> yes: they leave the memo; an edit of the requests brings Hackday back
    assert c.post("/api/orgs/1/memo/opened", headers=tma(21)).status_code == 204
    assert c.get("/api/orgs/1/memo", headers=tma(20)).json()["opened"]["by"]
    assert c.post("/api/orgs/1/memo/sent", headers=tma(21), json={"ids": [a["id"], 90]}).status_code == 204
    m = c.get("/api/orgs/1/memo", headers=tma(20)).json()
    assert m["events"] == [] and texts.MEMO2_BLANK.format(org="StudEx") in m["text"] and {x["id"] for x in m["sent"]} == {a["id"], 90} and m["sent"][0]["sentBy"]
    # DMP sees it in the app: the club, its events, who said "sent"; others may not look
    assert c.get("/api/registry/memos", headers=tma(20)).status_code == 403
    login(c, 29, "dmp")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 9, id, 'head', 0 FROM users WHERE tg_id = 29")
    con.commit()
    sent = c.get("/api/registry/memos", headers=tma(29)).json()
    assert len(sent) == 1 and sent[0]["org"]["id"] == 1 and sent[0]["by"] and {x["id"] for x in sent[0]["events"]} == {a["id"], 90}
    c.patch(f"/api/events/{a['id']}", headers=tma(20), json={**base, "title": "Hackday", "place": "Aud. 305", "startsAt": a["startsAt"], "memo": {"room": {}}})
    assert [x["title"] for x in c.get("/api/orgs/1/memo", headers=tma(20)).json()["events"]] == ["Hackday"]
    one_ = c.get("/api/orgs/1/memo", headers=tma(20)).json()["text"]
    assert one_.split("\n")[1] == texts.MEMO2_TITLE[0] and texts.MEMO2_FOR["event"].split("{")[0] not in one_  # one event: no per-event line
    assert c.post("/api/orgs/1/memo/again/90", headers=tma(20)).status_code == 204
    assert len(c.get("/api/orgs/1/memo", headers=tma(20)).json()["events"]) == 2

    # Wednesday 10:00: the President and the secretary hear it, the Head doesn't
    set_clock(monkeypatch, lambda: monday - 5 * 86400 + 10 * 3600)
    logic.memo_week(con)
    told = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'memo_ready'")}
    assert told == {uid[20], uid[21]}

    # with nothing asked, the blank with the signature and the templates
    con.execute("UPDATE events SET memo = NULL WHERE org_id = 1")
    m = c.get("/api/orgs/1/memo", headers=tma(21)).json()
    assert m["text"].startswith(texts.MEMO2_TO) and texts.MEMO2_BLANK.format(org="StudEx") in m["text"] and m["signFrom"] in m["text"]
    item = {"kind": "room", "fields": {"any": True, "projector": True}, "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "endsAt": monday + 86400 + 15 * 3600}
    r = c.post("/api/orgs/1/memo/item", headers=tma(21), json=item)
    assert r.status_code == 200 and "305" in r.json()["text"] and "13:00-15:00" in r.json()["text"]
    assert c.post("/api/orgs/1/memo/item", headers=tma(22), json=item).status_code == 403   # a Head without "memo"
    assert c.post("/api/orgs/1/memo/item", headers=tma(21), json={**item, "kind": "print"}).status_code == 400


def test_place_changes(env, monkeypatch):
    """PLAN "Place and time": one KBTU room for another tells only those with reminders off (the 2-hour reminder
    shows it); another venue tells everyone, edits within 10 minutes in one message; within 2 hours of the start, at
    once and only to who isn't checked in; Studio's "Change room" during the event; each new place a line in Updates."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ali"), (11, "zhan"), (12, "bota")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 10, 11, 12)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (uid[20],))
    con.execute("UPDATE users SET n_remind = 0 WHERE id = ?", (uid[11],))                     # Zhan turned reminders off
    start = int(time.time()) + 2 * 86400
    body = {"title": "Hack", "place": "Aud. 305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    for tg in (10, 11, 12):
        c.post(f"/api/events/{e['id']}/registration", headers=tma(tg), json={})
    told = lambda: {r[0]: r[1] for r in con.execute("SELECT user_id, send_after FROM bot_outbox WHERE kind = 'event_changed' AND sent_at IS NULL")}  # noqa: E731

    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 412"}).status_code == 200  # room -> room
    assert set(told()) == {uid[11]}                                                         # only reminders-off hears it now
    assert c.get(f"/api/events/{e['id']}", headers=tma(10)).json()["updates"][0]["body"] == "📍 → Aud. 412"
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(10), json={"place": "Aud. 1"}).status_code == 403   # not the team
    con.execute("DELETE FROM bot_outbox")
    venue = {**body, "place": "Abu Dhabi Plaza", "placeUrl": "https://2gis.kz/almaty/firm/1"}
    assert c.patch(f"/api/events/{e['id']}", headers=tma(20), json=venue).status_code == 200  # another venue: everyone
    first = told()
    assert set(first) == {uid[10], uid[11], uid[12]} and all(t >= int(time.time()) + 500 for t in first.values())  # in 10 minutes
    c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**venue, "place": "Abu Dhabi Plaza, floor 2"})
    assert told() == first                                                                  # merged: the bot reads the event when it sends

    # within 2 hours of the start: at once, only to who isn't in yet
    con.execute("DELETE FROM bot_outbox")
    con.execute("UPDATE events SET starts_at = ?, place = 'Aud. 305', place_url = NULL WHERE id = ?", (int(time.time()) - 600, e["id"]))
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ? AND user_id = ?", (int(time.time()), e["id"], uid[10]))
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 202"}).status_code == 200
    soon = told()
    assert set(soon) == {uid[11], uid[12]} and all(t <= int(time.time()) for t in soon.values())
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, e["id"]))
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 1"}).status_code == 409   # over


def test_comment_replies(env):
    """Comment replies (PLAN): a reply quotes the comment it answers (only one still up in the same thread), and
    its author hears it once an hour per thread; not for answering oneself, not twice for an asker the club answers."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ali"), (11, "zhan")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 10, 11)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (uid[20],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, uid[20]))
    first = c.post("/api/events/1/comments", headers=tma(10), json={"body": "Is there pizza?"}).json()["items"][0]
    t = c.post("/api/events/1/comments", headers=tma(11), json={"body": "I hope so", "replyTo": first["id"]}).json()
    assert t["items"][1]["replyTo"] == {"id": first["id"], "name": first["person"]["name"], "body": "Is there pizza?"} and t["items"][0]["replyTo"] is None
    c.post("/api/events/1/comments", headers=tma(11), json={"body": "Me too", "replyTo": first["id"]})
    told = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'comment_reply'").fetchall()
    assert [r["user_id"] for r in told] == [uid[10]]                                         # two replies, one message this hour
    text, _, start = bot._render(con, told[0])
    assert "Hack" in text and start == "cm_1"
    assert c.post("/api/events/1/comments", headers=tma(11), json={"body": "x", "replyTo": 999}).status_code == 400
    c.post("/api/events/1/comments", headers=tma(10), json={"body": "Self", "replyTo": first["id"]})
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_reply'").fetchone()[0] == 1   # not to myself
    c.post("/api/events/1/comments", headers=tma(20), json={"body": "Yes, pizza", "asOrg": True, "replyTo": first["id"]})
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_answer' AND user_id = ?", (uid[10],)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_reply'").fetchone()[0] == 1   # the answer's card covers it
    c.delete(f"/api/comments/{first['id']}", headers=tma(10))
    assert all(x["replyTo"] is None for x in c.get("/api/events/1/comments", headers=tma(11)).json()["items"])  # gone: no quote


def test_casting(env):
    """Casting (PLAN "Casting"): a club opens a round with its tags as departments and a few questions; its
    followers hear it; students apply (a department's own question only if they picked it); the casting team (Head+ by
    default) sees the applications with what only the app knows, votes, takes one into a department; the results in one
    tap make the accepted members with the department's tag and tell everyone."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ann"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 10, 11, 12)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'head', 0)", (uid[20], uid[21]))
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (1, 1, 'SMM', '#FF4FA3', 0), (2, 1, 'HR', '#2FBF71', 0)")
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (uid[12],))
    body = {"title": "Recruitment 2026", "picks": 2, "closesAt": int(time.time()) + 7 * 86400,
            "departments": [{"tagId": 1, "about": "Posts and reels", "places": 3}, {"tagId": 2, "about": "People"}],
            "questions": [{"kind": "one", "text": "Hours a week", "options": ["1-4", "5-8"]}, {"kind": "long", "text": "Why us?"},
                          {"kind": "link", "text": "Portfolio", "tagId": 1}]}
    assert c.post("/api/orgs/1/round", headers=tma(10), json=body).status_code == 403                # not the team
    r = c.post("/api/orgs/1/round", headers=tma(21), json=body).json()                               # a Head may (casting right)
    assert r["team"] and [d["name"] for d in r["departments"]] == ["SMM", "HR"] and len(r["questions"]) == 3
    assert c.post("/api/orgs/1/round", headers=tma(20), json=body).status_code == 409                # one round at a time
    assert [tuple(x) for x in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'round_open'")] == [(uid[12],)]  # the follower hears it
    rid, q = r["id"], {x["text"]: str(x["id"]) for x in r["questions"]}

    seen = c.get("/api/orgs/1/round", headers=tma(10)).json()
    assert "counts" not in seen and seen["open"] and seen["mine"] is None
    apply = lambda tg, deps, answers: c.post(f"/api/rounds/{rid}/apply", headers=tma(tg), json={"departments": deps, "answers": answers})  # noqa: E731
    assert apply(10, [1, 2], {q["Hours a week"]: "5-8", q["Why us?"]: "I post daily"}).status_code == 400  # SMM wants the portfolio
    assert apply(10, [1, 2], {q["Hours a week"]: "9-12", q["Why us?"]: "x", q["Portfolio"]: "behance.net/ann"}).status_code == 400  # not an option
    mine = apply(10, [1, 2], {q["Hours a week"]: "5-8", q["Why us?"]: "I post daily", q["Portfolio"]: "behance.net/ann"}).json()["mine"]
    assert mine["departments"] == [1, 2] and mine["stage"] == "sent"
    assert apply(11, [2], {q["Hours a week"]: "1-4", q["Why us?"]: "I like people"}).status_code == 200  # HR only: no portfolio asked
    assert apply(21, [2], {q["Why us?"]: "x"}).status_code == 409                                    # already in the club
    assert c.get("/api/orgs/1", headers=tma(10)).json()["round"] == {"id": rid, "closesAt": body["closesAt"], "applied": True}

    assert c.get(f"/api/rounds/{rid}/apps", headers=tma(10)).status_code == 403
    apps = {a["fullName"]: a for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(21)).json()}
    ann, bob = apps["Testov Ann"], apps["Testov Bob"]
    assert ann["answers"][q["Portfolio"]] == "behance.net/ann" and ann["came"] == 0 and not ann["before"]
    assert c.post(f"/api/round-apps/{ann['id']}/vote", headers=tma(21), json={"verdict": "next", "stars": 4, "note": "Strong reels"}).json()["stage"] == "next"
    c.post(f"/api/round-apps/{bob['id']}/vote", headers=tma(20), json={"verdict": "no"})
    votes = {a["fullName"]: a for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(20)).json()}["Testov Ann"]["votes"]
    assert votes == [{"by": "Head T.", "mine": False, "verdict": "next", "stars": 4, "note": "Strong reels"}]
    # interviews: slots, the shortlisted invited, a time booked (reminders queued), who came
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 2 * 86400 + 5 * 3600))
    assert c.post(f"/api/rounds/{rid}/invite", headers=tma(21)).status_code == 409                          # no slots yet
    got = c.post(f"/api/rounds/{rid}/slots", headers=tma(21), json={"date": day, "from": "15:00", "to": "16:00", "minutes": 20, "place": "Room 305"}).json()
    assert len(got) == 3 and got[0]["left"] == 1
    assert c.get(f"/api/rounds/{rid}/slots", headers=tma(10)).status_code == 403                              # not invited yet
    assert c.post(f"/api/rounds/{rid}/invite", headers=tma(21)).json() == {"invited": 1}                      # Ann only: next
    assert c.get("/api/orgs/1/round", headers=tma(10)).json()["mine"]["invited"]
    mine = c.post(f"/api/rounds/{rid}/book", headers=tma(10), json={"slotId": got[1]["id"]}).json()
    assert [x["id"] for x in mine if x.get("mine")] == [got[1]["id"]]
    refs = [x[0] for x in con.execute("SELECT ref FROM bot_outbox WHERE kind = 'round_iv_remind' AND sent_at IS NULL")]
    assert sorted(x.split(":")[-1] for x in refs) == ["eve", "hour"]                                           # the evening before, an hour before
    assert c.post(f"/api/rounds/{rid}/book", headers=tma(11), json={"slotId": got[1]["id"]}).status_code == 403  # Bob wasn't invited
    assert c.delete(f"/api/round-slots/{got[1]['id']}", headers=tma(21)).status_code == 409                   # booked: it stays
    assert len(c.delete(f"/api/round-slots/{got[2]['id']}", headers=tma(21)).json()) == 2
    assert c.get(f"/api/rounds/{rid}/slots", headers=tma(21)).json()[1]["people"][0]["fullName"] == "Testov Ann"
    assert c.post(f"/api/round-apps/{ann['id']}/came", headers=tma(21), json={"came": True}).json() == {"showed": True}
    nudge = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_iv_nudge'").fetchone()
    assert bot._render(con, nudge) is None                                                                      # she picked a time
    remind = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_iv_remind'").fetchone()
    assert "Room 305" in bot._render(con, remind)[0]

    assert c.post(f"/api/round-apps/{ann['id']}/decide", headers=tma(20), json={"stage": "yes", "tagId": 1}).json()["takenTag"] == 1
    assert c.get("/api/orgs/1/round", headers=tma(20)).json()["counts"] == {"yes": 1, "no": 1}

    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20)).json() == {"accepted": 1, "declined": 1}
    assert con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (uid[10],)).fetchone()[0] == "member"
    assert [tuple(x) for x in con.execute("SELECT tag_id FROM member_tags WHERE user_id = ?", (uid[10],))] == [(1,)]
    assert con.execute("SELECT 1 FROM org_members WHERE org_id = 1 AND user_id = ?", (uid[11],)).fetchone() is None
    sent = {x[0]: x[1] for x in con.execute("SELECT kind, user_id FROM bot_outbox WHERE kind IN ('round_yes', 'round_no')")}
    assert sent == {"round_yes": uid[10], "round_no": uid[11]}
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_yes'").fetchone()
    assert "SMM" in bot._render(con, row)[0]
    assert c.get("/api/orgs/1/round", headers=tma(11)).json() is None and c.post(f"/api/rounds/{rid}/send", headers=tma(20)).status_code == 409
    # sixty days after the results the answers and notes go; who applied and how it ended stay
    con.execute("UPDATE rounds SET sent_at = ? WHERE id = ?", (int(time.time()) - 61 * 86400, rid))
    casting.forget(con)
    assert [x[0] for x in con.execute("SELECT answers FROM round_apps WHERE round_id = ?", (rid,))] == ["{}", "{}"]
    assert con.execute("SELECT COUNT(*) FROM round_votes").fetchone()[0] == 0
    assert sorted(x[0] for x in con.execute("SELECT stage FROM round_apps WHERE round_id = ?", (rid,))) == ["no", "yes"]


def test_saved_tomorrow(env, monkeypatch):
    """"Save" with a purpose (instead of a like): the day before, at noon, whoever saved an event and isn't going
    hears it once (with the reminders' switch); signing up meanwhile quiets it; the organizer sees how many saved it."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ann"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    day = (int(time.time()) + 5 * 3600) // 86400
    start = (day + 1) * 86400 - 5 * 3600 + 18 * 3600                       # tomorrow 18:00 in Almaty
    e = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Quiz", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    for tg in (10, 11):
        c.put(f"/api/events/{e['id']}/saved", headers=tma(tg))
    con.execute("UPDATE users SET n_remind = 0 WHERE tg_id = 11")                # Bob turned reminders off
    assert {x["id"]: x["savedBy"] for x in c.get("/api/orgs/1/events", headers=tma(20)).json()}[e["id"]] == 2
    set_clock(monkeypatch, lambda: day * 86400 - 5 * 3600 + 12 * 3600 + 60)  # today 12:01
    logic.saved_day(con)
    logic.saved_day(con)
    rows_ = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'saved_tomorrow'").fetchall()
    assert len(rows_) == 1 and "Quiz" in bot._render(con, rows_[0])[0]           # Ann only, once
    monkeypatch.undo()
    c.post(f"/api/events/{e['id']}/registration", headers=tma(10), json={})
    assert bot._render(con, rows_[0]) is None                                     # she signed up meanwhile


def test_badge_skin(env):
    """Badge skins: I show the badge of an official club I'm in, or the KBTU one; never picked, a club
    with a badge shows by itself; my pick holds, and others see it. Since Oct 20 anyone may try on any club's; the
    creator's own is his alone."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'sx', 'club', 'StudEx', 'SX', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'x', 'club', 'Side', 'X', 'laptop_3d', 0)")
    for o in (1, 2):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (o, pres["id"]))
    con.commit()
    P, A = tma(90, "Pres"), tma(91, "Ali")
    assert c.get("/api/me", headers=P).json()["skin"] == 1                        # never picked: StudEx's by itself
    assert c.patch("/api/me", headers=P, json={"skin": None}).json()["skin"] is None  # picked KBTU: it holds
    for bad in (2, 3, "1", True, "sower"):  # not official, not a club, not an id, not the creator
        assert c.patch("/api/me", headers=P, json={"skin": bad}).status_code == 400
    assert c.patch("/api/me", headers=A, json={"skin": 1}).json()["skin"] == 1  # not in it: tried on all the same
    con.execute("UPDATE users SET skin_pick = NULL, skin_org = NULL WHERE id = ?", (ali["id"],))
    con.commit()
    assert c.patch("/api/me", headers=P, json={"skin": 1}).json()["skin"] == 1
    assert c.get(f"/api/users/{pres['id']}", headers=A).json()["skin"] == 1
    con.execute("DELETE FROM org_members WHERE org_id = 1")
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] == 1  # a pick holds after leaving: anyone may wear it
    con.execute("UPDATE users SET skin_pick = NULL WHERE id = ?", (pres["id"],))
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] is None  # never picked: only a club I'm in comes by itself
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (3, 'kn', 'club', 'KBTU Knights', 'KN', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (3, ?, 'member', 0)", (pres["id"],))
    con.commit()
    assert c.patch("/api/me", headers=P, json={"skin": 3}).json()["skin"] == 3  # Knights have one too
    con.execute("UPDATE users SET skin_pick = NULL WHERE id = ?", (pres["id"],))
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] == 3                        # and it comes by itself
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ali["id"],))
    con.commit()
    assert c.get("/api/me", headers=A).json()["skin"] == "sower"
    assert c.patch("/api/me", headers=A, json={"skin": None}).json()["skin"] is None
    assert c.patch("/api/me", headers=A, json={"skin": "sower"}).json()["skin"] == "sower"


def test_important_post(env):
    """An "Important" post: Vice+ write it; the club's members (not the author) hear it from the bot, one
    such message a day per club at most; other labels message nobody."""
    from kbtu import bot
    c, cfg = env
    vice, head, mem = login(c, 61, "vice"), login(c, 62, "head"), login(c, 63, "mem")
    V, H = tma(61, "Vice"), tma(62, "Head")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'head', 0), (1, ?, 'member', 0)",
                (vice["id"], head["id"], mem["id"]))
    con.commit()
    sent = lambda: sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'important'"))  # noqa: E731
    post = {"title": "Meeting moved to 305", "body": "", "tag": "important"}
    assert c.post("/api/orgs/1/posts", headers=H, json=post).status_code == 403            # Head can't
    pid = c.post("/api/orgs/1/posts", headers=H, json={**post, "tag": "news"}).json()["id"]
    assert sent() == []                                                                    # a plain post is silent
    assert c.patch(f"/api/posts/{pid}", headers=H, json={"tag": "important"}).status_code == 403
    c.post("/api/orgs/1/posts", headers=V, json=post)
    assert sent() == sorted([head["id"], mem["id"]])
    c.post("/api/orgs/1/posts", headers=V, json={**post, "title": "And again"})
    assert len(sent()) == 2                                                                # once a day per club
    m = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'important' AND b.user_id = ?", (mem["id"],)).fetchone()
    text, button, start = bot._render(con, m)
    assert "IT Club" in text and "Meeting moved to 305" in text and start == "news"


def test_head_for_monitors(env):
    """An uptime monitor's HEAD gets 200 like a GET (UptimeRobot showed the app down with 405)."""
    c, _ = env
    assert c.head("/").status_code == 200 and c.get("/").status_code == 200


def test_share_poster(env):
    """A coverless event's share card gets its own poster, not the app picture; no place, no dangling dot."""
    c, _ = env
    r = c.get("/og/poster.jpg?c=3B6BFF&e=party_popper_3d")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert c.get("/og/poster.jpg?c=zz&e=party_popper_3d").status_code == 404
    assert c.get("/og/poster.jpg?c=3B6BFF&e=../index").status_code == 404
    assert "·" not in texts.share_event("ru", "T", 0, "")[0] and "· Hall" in texts.share_event("en", "T", 0, "Hall")[0]


def test_delete_cancelled_event(env):
    """A cancelled event can be deleted unless it has payments; a live one can't."""
    c, cfg = env
    pres = login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    body = {"title": "Oops", "place": "", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 5}
    eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    assert c.delete(f"/api/events/{eid}", headers=tma(20)).status_code == 409         # live: cancel first
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).json()["status"] == "cancelled"
    assert c.delete(f"/api/events/{eid}", headers=tma(20)).status_code == 204
    assert not con.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone()
    # the admin deletes a live one too, from Admin's list of the club's events; nobody else sees that list
    eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    admin = logic.Viewer(pres["id"], "admin", True)
    with pytest.raises(logic.ApiError):
        logic.admin_org_events(con, logic.Viewer(pres["id"], "user", True), 1)
    assert [x["id"] for x in logic.admin_org_events(con, admin, 1)] == [eid]
    # a paid one: the receipt (personal) leaves the disk with it
    con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, owner_id, created_at) VALUES (90, 'h', 'receipt', 'image/webp', 1, 'r/x', ?, 0)", (pres["id"],))
    con.execute("INSERT INTO registrations (id, event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (90, ?, ?, 'going', 'tk90', 0, 0)", (eid, pres["id"]))
    con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) VALUES (90, 90, 'app', 0)")
    assert logic.delete_event(con, admin, eid) == (["r/x"], [])
    assert not con.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone()
    assert not con.execute("SELECT 1 FROM files WHERE id = 90").fetchone()


def test_grant_link(env):
    """The admin's one-time award link: one student, once, celebrated (Bug hunter comes from a chat)."""
    c, cfg = env
    boss, ali = login(c, 60, "boss"), login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    with pytest.raises(logic.ApiError):
        logic.grant_link(con, logic.Viewer(ali["id"], "user", True), "bugs")      # not the admin
    token = logic.grant_link(con, logic.Viewer(boss["id"], "admin", True), "bugs")
    assert c.post(f"/api/grant-links/{token}", headers=tma(61)).json() == {"code": "bugs"}
    assert c.post(f"/api/grant-links/{token}", headers=tma(61)).json()["error"] == "closed"   # once
    assert con.execute("SELECT granted_by FROM achievement_grants WHERE user_id = ? AND code = 'bugs'", (ali["id"],)).fetchone()[0] == boss["id"]


def test_premium_emoji(monkeypatch):
    """The pack's emoji: the plain ones our texts use become <tg-emoji>, with or without U+FE0F; the rest stay."""
    import re as _re
    from kbtu import bot
    monkeypatch.setattr(bot, "_custom", {"🎉": "1", "⚠": "2"})
    monkeypatch.setattr(bot, "_custom_re", _re.compile("🎉️?|⚠️?"))
    assert bot.premium("🎉 <b>IDC</b> ⚠️ 😔") == '<tg-emoji emoji-id="1">🎉</tg-emoji> <b>IDC</b> <tg-emoji emoji-id="2">⚠️</tg-emoji> 😔'
    monkeypatch.setattr(bot, "_custom_re", None)
    assert bot.premium("🎉") == "🎉"


def test_schools_seeded(env):
    """KBTU's schools come from its site once: crests, three languages; a school made by hand before is
    filled in, not doubled; an edit by hand drops that field's translations."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    got = con.execute("SELECT slug, name, i18n, logo_file_id, official FROM orgs WHERE kind = 'school' ORDER BY id").fetchall()
    assert len(got) == len(logic.SCHOOLS) == 11 and all(r["logo_file_id"] and r["official"] for r in got)
    site = next(r for r in got if r["slug"] == "site")
    assert json.loads(site["i18n"])["en"]["name"] == "School of Information Technology and Engineering"
    # run again: nothing doubles; a hand-made one before the seed is matched by name
    con.execute("DELETE FROM meta WHERE key = 'schools'")
    con.execute("UPDATE orgs SET name = 'School of Law', slug = 'handmade', logo_file_id = NULL, i18n = NULL WHERE slug = 'law'")
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    law = con.execute("SELECT * FROM orgs WHERE slug = 'handmade'").fetchone()
    assert con.execute("SELECT COUNT(*) FROM orgs WHERE kind = 'school'").fetchone()[0] == 11 and law["logo_file_id"] and law["i18n"]
    shown = logic.org_ref(con, law)
    assert shown["i18n"]["kk"]["name"] and shown["logo"] and shown["i18n"]["ru"]["abbr"] == "\u0428\u041f"
    # version 1 seeded before: the next brings the short names, the name the school typed stays
    con.execute("UPDATE meta SET value = '1' WHERE key = 'schools'")
    con.execute("UPDATE orgs SET name = 'Our Law', slug = 'law', i18n = NULL WHERE slug = 'handmade'")
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    law = con.execute("SELECT * FROM orgs WHERE slug = 'law'").fetchone()
    assert law["name"] == "Our Law" and json.loads(law["i18n"])["en"]["abbr"] == "SL"


def test_official_roles(env):
    """Every club has the three official roles: the President (the level) and the fixed Vice
    and Head, which can't be renamed, deleted or raised (their rights below the level may be tuned); a Vice or Head
    without a role name holds them, the old President too after handing the club over."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "vic"), (22, "hed")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    for tg, role in ((20, "president"), (21, "vice"), (22, "head")):
        logic.set_role(con, None, ids[tg], oid, role, "test")
    roles = c.get(f"/api/orgs/{oid}/team", headers=tma(20)).json()["roles"]
    assert [(r["name"], r["level"], r["fixed"], r["count"]) for r in roles] == [("Vice", "vice", True, 1), ("Head", "head", True, 1)]
    vp, head = roles[0]["id"], roles[1]["id"]
    assert c.delete(f"/api/orgs/{oid}/roles/{head}", headers=tma(20)).status_code == 403
    assert c.patch(f"/api/orgs/{oid}/roles/{head}", headers=tma(20), json={"name": "Boss", "color": "#2FBF71", "rights": ["money"]}).status_code == 403
    out = c.patch(f"/api/orgs/{oid}/roles/{head}", headers=tma(21), json={"name": "Boss", "color": "#2FBF71", "rights": ["door", "events"]}).json()["roles"]
    assert next((r["name"], r["level"], r["rights"]) for r in out if r["id"] == head) == ("Head", "head", ["door", "events"])
    c.post(f"/api/orgs/{oid}/transfer", headers=tma(20), json={"userId": ids[21]})
    assert con.execute("SELECT role, role_id FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ids[20])).fetchone()[:] == ("vice", vp)
    # a clubmate sees the role; outside the club, the card shows no clubs at all since audit M2 (it showed the club, not the role)
    login(c, 30, "out")
    clubs = lambda viewer: c.get(f"/api/users/{ids[21]}", headers=tma(viewer)).json()["clubs"]  # noqa: E731
    assert clubs(30) == [] and next(m for m in clubs(22) if m["org"]["id"] == oid)["role"] == "president"


def test_volunteers(env):
    """Volunteers: an event asks for N, maybe not year 1; a student applies with a "why", the organizer
    says yes or no and the bot tells them; no more yeses than places."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ali"), (22, "bota"), (23, "dan")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 23)}
    logic.set_role(con, None, ids[20], oid, "president", "test")
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dB%07d', ?, user_id) WHERE user_id = ?", (INTAKE % 100, ids[23]))
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF",
          "seats": 50, "volunteers": 1, "volunteersSenior": True}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    assert c.post(f"/api/events/{e['id']}/publish", headers=tma(20)).status_code == 200
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=tma(23), json={}).status_code == 403          # year 1
    r = c.post(f"/api/events/{e['id']}/volunteer", headers=tma(21), json={"note": "I helped last year"}).json()
    assert r["volunteers"]["mine"] == "asked" and "asked" not in r["volunteers"]                              # a student sees no counts of others waiting
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=tma(22), json={}).status_code == 200
    assert c.get(f"/api/events/{e['id']}/volunteers", headers=tma(21)).status_code == 403
    lst = c.get(f"/api/events/{e['id']}/volunteers", headers=tma(20)).json()
    assert [x["note"] for x in lst] == ["I helped last year", ""] and lst[0]["fullName"]
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[21]}", headers=tma(20), json={"yes": True}).status_code == 200
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[22]}", headers=tma(20), json={"yes": True}).status_code == 409   # one place
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[22]}", headers=tma(20), json={"yes": False}).status_code == 200
    assert {r[0] for r in con.execute("SELECT kind FROM bot_outbox WHERE kind LIKE 'volunteer_%'")} == {"volunteer_yes", "volunteer_no"}
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["volunteers"] == {"need": 1, "senior": True, "taken": 1, "mine": None, "asked": 0}


def test_event_chat(env):
    """An event's group without a userbot: "Create chat" gives a startgroup link with a one-time token;
    the bot's /start in the group from an organizer links it; join requests: those going and the team in, others not."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ali"), (22, "bota")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    logic.set_role(con, None, ids[20], oid, "president", "test")
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    assert c.post(f"/api/events/{e['id']}/chat", headers=tma(21)).status_code == 403
    url = c.post(f"/api/events/{e['id']}/chat", headers=tma(20)).json()["url"]
    token = url.split("startgroup=ec_")[1].split("&")[0]
    assert logic.chat_claim(con, token, 21, -100) is None                     # not an organizer
    assert logic.chat_claim(con, token, 20, -100)["id"] == e["id"]
    assert logic.chat_claim(con, token, 20, -100) is None                     # spent
    assert c.post(f"/api/events/{e['id']}/registration", headers=tma(21)).status_code == 200
    assert logic.chat_join(con, -100, 21) is True and logic.chat_join(con, -100, 22) is False and logic.chat_join(con, -100, 20) is True
    assert logic.chat_join(con, -999, 21) is None
    con.execute("UPDATE events SET chat_link = 'https://t.me/+x' WHERE id = ?", (e["id"],))
    assert c.get(f"/api/events/{e['id']}", headers=tma(21)).json()["chat"] == "https://t.me/+x"
    assert c.get(f"/api/events/{e['id']}", headers=tma(22)).json()["chat"] is None


def test_events_channel(env, monkeypatch):
    """The events channel: a published public event is due once; an edit makes it due again; a cancel
    marks its post; a team-only one never goes."""
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], oid, "president", "test")
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    t = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json={**ev, "title": "Team", "visibility": "members"}).json()
    assert logic.channel_due(con) == []                                                         # drafts don't go
    for x in (e, t):
        c.post(f"/api/events/{x['id']}/publish", headers=tma(20))
    (row, text, cover, sig), = logic.channel_due(con)
    assert row["id"] == e["id"] and "Open day" in text and "Atrium" in text
    con.execute("UPDATE events SET channel_msg = 7, channel_sig = ? WHERE id = ?", (sig, e["id"]))
    assert logic.channel_due(con) == []
    c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**ev, "place": "Hall"})
    assert "Hall" in logic.channel_due(con)[0][1]
    assert 'startapp=ev_%d">' % e["id"] in logic.channel_due(con, "KBTUappBot")[0][1]           # sign up: a link, not a button
    con.execute("UPDATE events SET channel_msg = NULL WHERE id = ?", (e["id"],))
    # Telegram's copy of post 7 in the discussion group: the bot comments the rules under it, the app links that comment.
    # The copy comes before post_channel has stored the post's id: the bot waits for it
    real_sleep = asyncio.sleep

    async def sleep(s):
        con.execute("UPDATE events SET channel_msg = 7 WHERE id = ?", (e["id"],))
        await real_sleep(0)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    import httpx
    cfg2 = dataclasses.replace(cfg, events_channel="@KBTUevents")
    copy = {"message_id": 70, "chat": {"id": -100, "type": "supergroup"}, "is_automatic_forward": True,
            "sender_chat": {"id": -200, "type": "channel", "username": "KBTUevents"}, "forward_origin": {"type": "channel", "message_id": 7}}
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1, "message": copy}, {"update_id": 2, "message": copy}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 71}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot.hear(cfg2, http, 0)
    asyncio.run(go())
    assert len(sent) == 1 and sent[0]["chat_id"] == -100 and sent[0]["reply_parameters"] == {"message_id": 70}  # once
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["discuss"] == "https://t.me/kbtuevents/7?comment=71"
    con.execute("UPDATE events SET comments_on = 0 WHERE id = ?", (e["id"],))
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["discuss"] is None              # comments off: no talk
    con.execute("UPDATE events SET comments_on = 1 WHERE id = ?", (e["id"],))
    c.post(f"/api/events/{e['id']}/cancel", headers=tma(20))
    assert logic.channel_due(con)[0][1].startswith("❌")
    # deleting the cancelled event deletes its post and the post's copy in the group (it stayed)
    assert c.delete(f"/api/events/{e['id']}", headers=tma(20)).status_code == 204
    assert logic.channel_gone(con) == [(7, "-100 70")]
    sent.clear()

    async def drop():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.post_channel(cfg2, http, con)
    asyncio.run(drop())
    gone = [(x["chat_id"], x["message_id"]) for x in sent if "text" not in x and "caption" not in x]
    assert gone == [("@KBTUevents", 7), ("-100", 70)] and logic.channel_gone(con) == []


def test_map_graph(env):
    """Indoor routes' graph (PLAN item 22): anyone reads Claude's draft; nobody saves it (the editor is off)."""
    c, _ = env
    login(c, 20, "ali")
    g = c.get("/api/map/graph", headers=tma(20)).json()
    assert g["n"] and g["e"] and g["ver"] == 0
    assert c.put("/api/map/graph", headers=tma(20), json=g).status_code == 405


def test_exit_link(env):
    """"Help me get out": kbtu.sow.kz/exit goes to the app's exit screen; /exit in the bot answers with
    a message and its button, to forward anywhere."""
    c, cfg = env
    r = c.get("/exit", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("?startapp=exit")
    con = db.connect(cfg.db_path)
    msg = {"chat": {"id": 5, "type": "private"}, "date": int(time.time()), "text": "/exit", "from": {"language_code": "ru"}}
    out = bot._welcome(con, cfg, msg)
    assert out["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("?startapp=exit")
    msg["text"] = "/start"
    assert bot._welcome(con, cfg, msg)["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("?startapp")


def test_premium_emoji_everywhere(env, monkeypatch):
    """The pack's emoji in every HTML text the bot sends, channel and groups too; refused: once more plain."""
    import httpx
    _, cfg = env
    monkeypatch.setattr(bot, "_custom", {"💬": "42"})
    monkeypatch.setattr(bot, "_custom_re", re.compile("💬️?"))
    got = []

    def telegram(request: httpx.Request) -> httpx.Response:
        b = json.loads(request.content)
        got.append(b["text"])
        return httpx.Response(400 if "tg-emoji" in b["text"] and len(got) > 2 else 200, json={"ok": False, "description": "custom emoji not allowed"})

    async def go(body):
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot._tg(cfg, http, "sendMessage", body)
    asyncio.run(go({"chat_id": 1, "text": "💬 hi", "parse_mode": "HTML"}))
    asyncio.run(go({"chat_id": 1, "text": "💬 plain"}))                         # no HTML: left as it is
    assert got == ['<tg-emoji emoji-id="42">💬</tg-emoji> hi', "💬 plain"]
    asyncio.run(go({"chat_id": 1, "text": "💬 again", "parse_mode": "HTML"}))    # refused: plain, and the pack goes off
    assert got[2:] == ['<tg-emoji emoji-id="42">💬</tg-emoji> again', "💬 again"] and bot._custom_re is None


def test_card_number_never_given_twice(env):
    """Card numbers: the last card's account purged, the next student still gets a new number."""
    c, cfg = env
    for tg in (31, 32):
        login(c, tg, f"s{tg}")
    con = db.connect(cfg.db_path)
    no = dict(con.execute("SELECT tg_id, card_no FROM users WHERE tg_id IN (31, 32)").fetchall())
    assert no[32] == no[31] + 1
    con.execute("DELETE FROM users WHERE tg_id = 32")
    login(c, 33, "s33")
    assert con.execute("SELECT card_no FROM users WHERE tg_id = 33").fetchone()[0] == no[32] + 1


def test_nightly_backup(env, monkeypatch):
    """A copy of the database each night after 04:00 Almaty, once, the last 14 kept (there were none)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    day0 = 20000 * 86400 - 5 * 3600                                    # 00:00 Almaty
    for d in range(16):
        for hour in (3, 5, 6):                                         # before 04:00 nothing; after, once
            monkeypatch.setattr(bot.time, "time", lambda: day0 + d * 86400 + hour * 3600)
            bot.backup_day(cfg, con)
    kept = sorted((Path(cfg.db_path).resolve().parent / "backups").glob("kbtu-*.db"))
    assert len(kept) == 14 and kept[-1].name == "kbtu-2024-10-19.db"
    copy = db.connect(str(kept[-1]))
    assert copy.execute("SELECT COUNT(*) FROM users").fetchone()[0] == con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_channel_refused_post_skipped(env):
    """A post Telegram refuses for itself (a caption too long) is skipped, so the ones after it still go;
    no rights stops the round instead, every post waits."""
    import httpx
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], oid, "president", "test")
    ev = {"place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    ids = [c.post(f"/api/orgs/{oid}/events", headers=tma(20), json={**ev, "title": t}).json()["id"] for t in ("Long", "Fine")]
    for i in ids:
        c.post(f"/api/events/{i}/publish", headers=tma(20))
    con.execute("UPDATE events SET published_at = published_at - 60 WHERE id = ?", (ids[0],))  # Long goes first
    cfg2 = dataclasses.replace(cfg, events_channel="@KBTUevents")
    why = {"Long": "Bad Request: message is too long"}

    def telegram(request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content)["text"]
        for k, d in why.items():
            if k in text:
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": d})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.post_channel(cfg2, http, con)
    why["Fine"] = "Bad Request: not enough rights to send text messages to the chat"
    asyncio.run(go())
    assert len(logic.channel_due(con, cfg.bot_username)) == 1           # no rights: Fine waits, Long was skipped
    del why["Fine"]
    asyncio.run(go())
    assert logic.channel_due(con, cfg.bot_username) == [] and con.execute("SELECT channel_msg FROM events WHERE id = ?", (ids[1],)).fetchone()[0] == 9




def test_manual_sign_in(env, monkeypatch):
    """Microsoft only: the ID and year are typed only after a Microsoft sign-in; a row typed in before
    acts as nobody until Microsoft confirms it; an ID held by such a row goes to the Microsoft one, held by a confirmed
    one it's refused; the admins hear of both with both contacts. The admin adds someone with no Microsoft by hand."""
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    login(c, 20, "ali")  # confirmed: "24Bali"
    body = {"firstName": "\u041c\u0430\u0433\u0430", "lastName": "\u0422\u0435\u043c\u0438\u0440", "studentId": "24b031234", "course": 2, "consentVersion": logic.CONSENT}
    manual = lambda uid, b=body: c.post("/api/kbtu/manual", headers=tma(uid), json=b)  # noqa: E731
    for bad in ({"firstName": "M4ga"}, {"studentId": "hello"}, {"studentId": "99B031234"}, {"consentVersion": ""}, {"consentVersion": "v1"}):  # the year: from the ID (M3), never ahead
        assert manual(21, {**body, **bad}).status_code == 400
    assert manual(21).json()["message"] == "ms_first"                                     # no Microsoft, no account
    assert manual(20).json()["message"] == "ms_first"                                     # confirmed already: nothing to type either
    ids = {tg: c.get("/api/me", headers=tma(tg)).json()["id"] for tg in (21, 22, 23, 24, 25)}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', tg_username = 'squat' WHERE id = ?", (ids[25],))
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B031234', 'Squat', 'Ter', 2, '1', 0, 0, 0, 1)""", (ids[23],))  # typed in before Oct 20
    me = c.get("/api/me", headers=tma(23)).json()
    assert me["student"] is None and me["relink"] and me["msPending"] is None              # signed out until Microsoft
    assert c.post("/api/friends/link", headers=tma(23)).json()["error"] == "need_student"
    who = lambda n: {"oid": f"oid-{n}", "email": f"s_{n}@kbtu.kz", "first": "Maga", "last": f"N{n}", "employeeId": "", "profile": {}}  # noqa: E731
    for tg in (21, 22, 24):
        logic.ms_remember(con, ids[tg], who(tg))
    me = manual(21).json()                                                                 # the ID held by a typed-in row: it gives way
    assert me["student"]["studentId"] == "24B031234" and me["student"]["ms"] and me["no"] is not None
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (ids[23],)).fetchone()
    r = manual(22)                                                                         # held by a Microsoft one: refused
    assert r.status_code == 409 and r.json()["message"] == "sid_taken"
    assert c.get("/api/me", headers=tma(22)).json()["msPending"]                           # can type another
    out = con.execute("SELECT * FROM bot_outbox WHERE kind = 'id_clash' ORDER BY id").fetchall()
    assert [m["ref"] for m in out] == [f"ic:24B031234:{ids[21]}:{ids[23]}", f"ic:24B031234:{ids[22]}:{ids[21]}"]
    text = bot._render(con, {**dict(out[0]), "lang": "ru"})[0]                             # the holder, though their row is gone
    assert "Squat Ter" in text
    text = bot._render(con, {**dict(out[1]), "lang": "ru"})[0]
    assert "s_21@kbtu.kz" in text and f"tg://user?id=22" in text and "Maga N21" in text    # both, to write to
    for i in range(5):                                                                     # 3 clash messages a day per person
        logic.id_clash(con, f"24B00000{i}", ids[24], ids[21])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'id_clash' AND ref LIKE ?", (f"ic:%:{ids[24]}:%",)).fetchone()[0] == 3
    assert manual(22, {**body, "studentId": "24B031235", "firstName": "x1"}).json()["student"]["firstName"] == "Maga"  # Microsoft's names win
    logic.delete_me(con, logic.Viewer(ids[24], "user", True))                            # an unfinished sign-in leaves with the account
    assert not con.execute("SELECT 1 FROM meta WHERE key = ?", (f"ms:{ids[24]}",)).fetchone()
    con.execute("INSERT INTO meta (key, value) VALUES ('ms:999', ?), ('ms_used:abc', '1')", (json.dumps({"at": 1}),))
    logic.ms_sweep(con)
    assert not con.execute("SELECT 1 FROM meta WHERE key IN ('ms:999', 'ms_used:abc')").fetchone()
    from kbtu import admin                                                                # no Microsoft account: by hand
    admin.main(["student", "23", "24B031299", "Squat", "Ter", "3"])
    me = c.get("/api/me", headers=tma(23)).json()
    assert me["student"]["studentId"] == "24B031299" and me["no"] is not None and not me["relink"]
    for gone in ("/api/kbtu/login", "/api/kbtu/status"):                                  # the password sign-in is gone
        assert c.post(gone, headers=tma(21), json={"login": "a", "password": "b"}).status_code in (404, 405)


def test_offsite_backup(env, monkeypatch):
    """The off-site copy (PLAN item 22): SigV4 as AWS's own example signs it; after the night's copy, it and the receipts
    go up once (Sundays the media too), a failure is tried again an hour later, never while one is running."""
    from kbtu import offsite
    auth = offsite.sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt",
                        {"range": "bytes=0-9", "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                         "x-amz-date": "20130524T000000Z"}, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "20130524T000000Z")
    assert auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    _, cfg = env
    con = db.connect(cfg.db_path)
    sent, fail = [], [True]
    def up(paths, name, work):
        if fail[0]:
            raise RuntimeError("R2 503")
        sent.append((name, [p.name for p in paths]))
        return 1024
    monkeypatch.setattr(offsite, "ready", lambda: True)
    monkeypatch.setattr(offsite, "upload", up)
    sunday = 20002 * 86400                                              # 05:00 Almaty, Sunday 2024-10-06
    clock = [sunday]
    monkeypatch.setattr(bot.time, "time", lambda: clock[0])
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(bot, "now", lambda: clock[0])
    jobs = []
    class Loop:
        def create_task(self, coro):
            coro.close()
            return None
    monkeypatch.setattr(bot.asyncio, "get_running_loop", lambda: Loop())
    monkeypatch.setattr(bot.asyncio, "to_thread", lambda fn, *a: (jobs.append(a), fn(*a), _noop())[2])
    bot.backup_day(cfg, con)
    bot.offsite_round(cfg, con)                                         # the first try fails
    assert sent == [] and len(jobs) == 1
    fail[0] = False
    bot.offsite_round(cfg, con)                                         # within the hour: not again
    assert len(jobs) == 1
    clock[0] += 3600
    bot.offsite_round(cfg, con)
    assert [n.split("/")[0] for n, _ in sent] == ["db", "media"] and sent[0][1] == ["kbtu-2024-10-06.db", "receipts", "deletions.log", "deletions.salt"]
    clock[0] += 3600
    bot.offsite_round(cfg, con)                                         # done for the day
    assert len(sent) == 2
    con.execute("INSERT INTO users (tg_id, role, created_at, seen_at) VALUES (9001, 'admin', 0, 0)")
    alerts = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'backup_failed'").fetchone()[0]  # noqa: E731
    fail[0] = True
    clock[0] = sunday + 86400 + 6 * 3600                                # Monday 11:00, failing: Sunday's copy is there
    bot.offsite_round(cfg, con)
    assert alerts() == 0
    clock[0] += 86400                                                   # Tuesday 11:00: two nights without one
    bot.offsite_round(cfg, con)
    clock[0] += 3600
    bot.offsite_round(cfg, con)                                         # once per outage, not once a day
    clock[0] += 86400
    bot.offsite_round(cfg, con)                                         # Wednesday, still failing: no second alert
    assert alerts() == 1
    oks = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'backup_ok'").fetchone()[0]  # noqa: E731
    fail[0] = False
    clock[0] += 3600
    bot.backup_day(cfg, con)                                            # the night's local copy, as the bot makes it
    bot.offsite_round(cfg, con)                                         # tonight's copy gets through
    assert oks() == 0                                                   # (counted once R2 said 200)
    clock[0] += 60
    bot.offsite_round(cfg, con)
    clock[0] += 3600
    bot.offsite_round(cfg, con)
    assert oks() == 1 and not con.execute("SELECT 1 FROM meta WHERE key = 'offsite_alert'").fetchone()
    fail[0] = True                                                      # a new outage: alerted again, once
    clock[0] += 2 * 86400
    bot.offsite_round(cfg, con)
    clock[0] += 3600
    bot.offsite_round(cfg, con)
    assert alerts() == 2
    payload = con.execute("SELECT payload, ref FROM bot_outbox WHERE kind IN ('backup_failed', 'backup_ok')").fetchall()
    assert all("key" not in (p or "").lower() and "secret" not in (p or "").lower() for p, _ in payload)  # nothing of the R2 credentials


async def _noop():
    return None


def test_ms_sign_in(env, monkeypatch):
    """The KBTU Microsoft sign-in (PLAN item 44): a link whose state only this server signs; the verifier for it; a
    token Graph accepts but issued elsewhere is refused; a typed-in student is confirmed; someone new types only the
    ID and year after; one Microsoft account never links to two Telegram users."""
    import base64
    import httpx
    from kbtu import msauth
    c, cfg = env
    login(c, 20, "ali")
    con = db.connect(cfg.db_path)  # typed in before Oct 20 (Microsoft only since): confirmed by Microsoft below
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B099001', 'Bek', 'Typed', 2, 'v2', 0, 0, 0, 1)""", (c.get("/api/me", headers=tma(21)).json()["id"],))
    url = c.post("/api/ms/start", headers=tma(21)).json()["url"]
    state = re.search(r"state=([^&]+)", url).group(1).replace("%2E", ".").replace("%3D", "=")
    assert msauth.KBTU in url and "code_challenge=" in url
    v = c.get("/api/ms/verifier", params={"state": state}).json()
    assert v == {"verifier": msauth.verifier(cfg.token_key, state)}           # nobody's name
    assert c.get("/api/ms/verifier", params={"state": "1.2.\u00e9"}).status_code == 404      # not a 500
    assert c.get("/api/ms/verifier", params={"state": state[:-2] + "xx"}).status_code == 404

    def token(tid=msauth.KBTU, app=msauth.CLIENT):
        part = base64.urlsafe_b64encode(json.dumps({"tid": tid, "appid": app}).encode()).decode().rstrip("=")
        return f"h.{part}.s"
    graph = {"id": "oid-1", "givenName": "Bek", "surname": "Real", "mail": "bek@gmail.com", "userPrincipalName": "B_REAL@kbtu.kz"}
    async def get(self, url, **kw):
        return httpx.Response(200, json=graph)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    uid = lambda tg: c.get("/api/me", headers=tma(tg)).json()["id"]  # noqa: E731 (states carry our user id, not Telegram's)
    finish = lambda tg, tok, st=None: c.post("/api/ms/finish", json={"state": st or msauth.state_for(cfg.token_key, uid(tg)), "token": tok})  # noqa: E731
    assert finish(21, token(tid="other-tenant")).status_code == 403           # someone else's directory
    assert finish(21, token(app="other-app")).status_code == 403              # a token made for another app
    assert finish(21, token(), st="21.1.x.bad").status_code == 403              # a state we never signed
    graph["userPrincipalName"] = "bek@gmail.com"
    assert finish(21, token()).status_code == 403                             # not a kbtu.kz sign-in name
    graph["userPrincipalName"] = "B_REAL@kbtu.kz"                             # "mail" may be a gmail: the sign-in name counts
    st = msauth.state_for(cfg.token_key, uid(21))
    assert finish(21, token(), st=st).json() == {"ok": True}                  # linked at once (no return code)
    assert finish(21, token(), st=st).status_code == 403                      # each link once
    me = c.get("/api/me", headers=tma(21)).json()
    assert "msCode" not in me
    assert me["student"]["ms"] and me["student"]["email"] == "b_real@kbtu.kz"
    assert me["student"]["lastName"] == "Real"                                # the account's names over typed ones
    graph["id"] = "oid-9"
    assert finish(21, token()).json()["message"] == "other_ms"                # no silent swap to another account
    graph["id"] = "oid-1"
    assert finish(22, token()).json()["message"] == "linked"                  # the same account, another Telegram
    graph = {"id": "oid-2", "givenName": "Dana", "surname": "New", "userPrincipalName": "d_new@kbtu.kz"}
    assert finish(22, token()).json() == {"ok": True}                         # new: remembered for the form
    assert c.get("/api/me", headers=tma(22)).json()["msPending"] == {"first": "Dana", "last": "New", "email": "d_new@kbtu.kz", "prefill": None}
    c.post("/api/kbtu/manual", headers=tma(22), json={"consentVersion": logic.CONSENT, "firstName": "Dana", "lastName": "New", "studentId": "24B099002", "course": 1})
    me = c.get("/api/me", headers=tma(22)).json()
    assert me["student"]["ms"] and me["msPending"] is None and me["no"]
    assert me["student"]["course"] == logic.course_of("24B099002") != 1                 # the ID's year, not the typed 1 (M3)

def test_suggest_chat(env, monkeypatch):
    """Any student suggests a chat through the bot (PLAN item 45): picked in Telegram's picker or sent as @name; public
    only, a person or a bot refused, nothing twice, 3 a day; waiting it shows nowhere but the admin's list; approved,
    it joins the catalog and its suggester hears so."""
    from kbtu import media
    c, cfg = env
    ali = login(c, 30, "ali")
    adm = c.get("/api/me", headers=tma(31)).json()
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (adm["id"],))  # an admin's role comes from the config
    assert [logic.chat_handle(x) for x in ("@KBTU_news", "https://t.me/kbtu_news/", "t.me/s/Kbtu_news", "https://t.me/+AbCdEf", "hi")] \
        == ["kbtu_news", "kbtu_news", "kbtu_news", None, None]
    pages = {"https://t.me/kbtu_news": {"title": "KBTU News", "image": None, "members": 4900, "channel": True},
             "https://t.me/some_person": {"title": "Some Person", "image": None, "members": None}}
    async def peek(http, url):
        return {"ok": True, **(pages.get(url) or {"title": "Chat", "image": None, "members": 10, "channel": False})}
    monkeypatch.setattr(media, "chat_peek", peek)
    def say(tg, **m):  # each a while after the last (one t.me look per 10 s per student)
        con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
        return asyncio.run(bot._suggest(cfg, None, con, {"chat": {"id": tg, "type": "private"}, "date": logic.now(), **m}))["text"]
    picked = {"chat_shared": {"request_id": 1, "chat_id": -100777, "username": "KBTU_news", "title": "KBTU News"}}
    assert say(99, **picked) == texts.bot_message("ru", "chat_signin")[0]          # not a student
    assert say(30, **picked) == texts.bot_message("ru", "chat_sent", title="KBTU News")[0]
    assert say(30, text="@kbtu_news") == texts.bot_message("ru", "chat_waiting")[0]  # same chat, typed: already waiting
    assert say(30, text="@some_person") == texts.bot_message("ru", "chat_notchat")[0]
    assert say(30, text="hello") == texts.bot_message("ru", "chat_private")[0]
    assert say(30, **{"chat_shared": {"request_id": 2, "chat_id": -100555, "title": "Closed"}}) == texts.bot_message("ru", "chat_invite")[0]
    assert [logic.chat_link(x) for x in ("@A_chat", "t.me/+AbCdEf12", "https://t.me/joinchat/AbCdEf12", "t.me/+x")] \
        == ["https://t.me/a_chat", "https://t.me/+AbCdEf12", "https://t.me/+AbCdEf12", None]
    assert say(30, text="https://t.me/+AbCdEf12").startswith("✅")                  # a closed chat by its invite link
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "t.me/joinchat/AbCdEf12"}).json()["status"] == "waiting"  # the app's sheet
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "nope"}).json()["status"] == "bad"
    assert c.post("/api/chats/suggest", headers=tma(99), json={"link": "@x_chat"}).status_code == 403
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "@typed_once"}).json()["status"] == "sent"
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "@typed_fast"}).json()["status"] == "slow"  # within 10 s of the last
    con.execute("DELETE FROM chats WHERE url = 'https://t.me/typed_once'")
    assert say(30, text="@second_chat").startswith("✅") and say(30, text="@third_chat").startswith("✅")
    assert asyncio.run(bot._suggest(cfg, None, con, {"chat": {"id": 30, "type": "private"}, "date": logic.now(), "text": "@quick_one"}))["text"] \
        == texts.bot_message("ru", "chat_later")[0]                                    # within 10 s of the last
    for i in range(6):
        assert say(30, text=f"@more_chat_{i}").startswith("✅")
    assert say(30, text="@eleventh_chat") == texts.bot_message("ru", "chat_limit")[0]  # 10 a day
    assert c.get("/api/chats", headers=tma(30)).json()["all"] == []                  # waiting: nowhere to see
    assert "pending" not in c.get("/api/chats", headers=tma(30)).json()
    waiting = c.get("/api/chats", headers=tma(31)).json()["pending"]
    assert [x["kind"] for x in waiting][-3:] == ["group", "group", "channel"] and len(waiting) == 10  # newest first
    ping = con.execute("SELECT * FROM bot_outbox WHERE kind = 'chat_suggested'").fetchall()
    assert len(ping) == 1 and bot._render(con, {**dict(ping[0]), "lang": "ru"})[2] == "achats"   # one a day
    news = waiting[-1]["id"]
    assert c.post(f"/api/chats/{news}/opened", headers=tma(30)).status_code == 404
    assert c.post(f"/api/admin/chats/{news}/approve", headers=tma(30)).status_code == 403
    assert c.post(f"/api/admin/chats/{news}/approve", headers=tma(31)).json()["title"] == "KBTU News"
    assert [x["title"] for x in c.get("/api/chats", headers=tma(30)).json()["all"]] == ["KBTU News"]
    told = con.execute("SELECT * FROM bot_outbox WHERE kind = 'chat_approved' AND user_id = ?", (ali["id"],)).fetchone()
    assert bot._render(con, {**dict(told), "lang": "ru"})[2] == "clubs"
    assert c.delete(f"/api/admin/chats/{waiting[0]['id']}", headers=tma(31)).status_code == 204   # declined
    assert len(c.get("/api/chats", headers=tma(31)).json()["pending"]) == 8
    assert say(30, text="@kbtu_news") == texts.bot_message("ru", "chat_exists")[0]   # live now
    inv = next(x for x in c.get("/api/chats", headers=tma(31)).json()["pending"] if "/+" in x["url"])
    c.post(f"/api/admin/chats/{inv['id']}/approve", headers=tma(31))
    assert inv["url"] in [x["url"] for x in c.get("/api/chats", headers=tma(30)).json()["all"]]       # a student sees the invite
    assert inv["url"] not in [x["url"] for x in c.get("/api/chats", headers=tma(99)).json()["all"]]   # a guest doesn't
    keys = bot._welcome(con, cfg, {"chat": {"id": 30, "type": "private"}, "date": logic.now(), "text": "/start chat"})["reply_markup"]["keyboard"]
    assert [k[0]["request_chat"]["chat_is_channel"] for k in keys] == [True, False] and "chat_has_username" not in keys[0][0]["request_chat"]  # any chat


def test_translations(env):
    """PLAN 9 (ai.py): the source language from the letters; the model's answer parsed or refused; only public published
    events and active clubs are sent; an edit of the text (not of the time) translates again; a translation never
    overwrites an edit made meanwhile; 3 failures leave it; cards carry titles, the club's description only its page."""
    import httpx
    from kbtu import ai
    assert (ai.lang_of("\u049a\u043e\u0448 \u043a\u0435\u043b\u0434\u0456\u04a3"), ai.lang_of("\u041f\u0440\u0438\u0432\u0435\u0442, \u043c\u0438\u0440"), ai.lang_of("KBTU Open 2026")) == ("kk", "ru", "en")
    L = {"title": 80, "description": 2000}
    good = 'Sure!\n```json\n{"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}\n```'
    assert ai.parse(good, {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430"}, "ru", L) == {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}
    for bad in (None, "", "no json here", '{"kk": {"title": "x"}}', '{"kk": {"title": "x"}, "en": {"title": 5}}', '{"kk": {}, "en": {}}'):
        with pytest.raises(ai.Failed):
            ai.parse(bad, {"title": "\u041d\u043e\u0447\u044c"}, "ru", L)
    assert ai.parse('{"kk": {"title": "' + "\u0430" * 300 + '"}, "en": {"title": "b"}}', {"title": "\u041d\u043e\u0447\u044c"}, "ru", L)["kk"]["title"] == "\u0430" * 80

    # the AI chain (llm.py): the next link when one is limited, busy or unusable; a limited one rests, an unusable one doesn't
    import dataclasses
    from kbtu import llm
    chained = dataclasses.replace(env[1], cf_account_id="acc", cf_ai_token="cf", munito_keys=("m1", "m2"), groq_key="gq",
                                  ai_chain="cf:model-a,munito:model-b,groq:model-c")
    assert [x.name for x in llm.links(chained)] == ["cf:model-a", "munito:model-b", "munito2:model-b", "groq:model-c"]
    assert not llm.available(env[1])                                                   # no keys: no chain, the translator stays off
    good_answer = {"choices": [{"finish_reason": "stop", "message": {"content": '{"kk": {"title": "\u0422"}, "en": {"title": "N"}}'}}]}
    def call(answers: dict):
        seen = []
        def handler(r):
            key = r.headers["authorization"].split()[1]
            seen.append(key)
            return answers.get(key) or httpx.Response(200, json=good_answer)
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                return await ai.translate(chained, http, {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": ""}, L)
        return asyncio.run(go()), seen
    llm._rest.clear()
    assert call({}) == (("ru", {"kk": {"title": "\u0422"}, "en": {"title": "N"}}), ["cf"])     # the empty description isn't sent
    assert call({"cf": httpx.Response(429, headers={"retry-after": "120"})})[1] == ["cf", "m1"]
    assert call({})[1] == ["m1"]                                                         # cf rests its two minutes
    assert call({"m1": httpx.Response(503)})[1] == ["m1", "m2"]                          # Munito's second key
    llm._rest.clear()
    assert call({"cf": httpx.Response(200, json={"choices": [{"message": {"content": "no json here"}}]})})[1] == ["cf", "m1"]
    assert call({})[1] == ["cf"]                                                         # a bad answer doesn't rest the link
    assert call({"cf": httpx.Response(400, json={"errors": [{"code": 4006}]})})[1] == ["cf", "m1"]  # Cloudflare's day spent
    assert call({})[1] == ["m1"]                                                         # it rests for hours
    llm._rest.clear()
    busy = {k: httpx.Response(503) for k in ("cf", "m1", "m2", "gq")}
    with pytest.raises(ai.Busy):
        call(busy)
    llm._rest.clear()
    junk = {k: httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": None}}]}) for k in ("cf", "m1", "m2", "gq")}
    with pytest.raises(ai.Failed):
        call(junk)
    llm._rest.clear()

    c, cfg = env
    pres = login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, description) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0, '')")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    body = {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": "\u041a\u043e\u0434\u0438\u043c \u0434\u043e \u0443\u0442\u0440\u0430", "place": "305", "startsAt": start, "endsAt": start + 7200,
            "emoji": "laptop_3d", "color": "#3B6BFF"}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert logic.ai_next(con) is None                                     # a draft stays home; a club with no description too
    c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
    kind, rid, was = logic.ai_next(con)
    assert (kind, rid, was) == ("event", ev["id"], {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": "\u041a\u043e\u0434\u0438\u043c \u0434\u043e \u0443\u0442\u0440\u0430"})
    tr = {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456", "description": "\u0422\u0430\u04a3\u0493\u0430 \u0434\u0435\u0439\u0456\u043d"}, "en": {"title": "Hack night", "description": "Code till dawn"}}
    logic.ai_save(con, kind, rid, was, "ru", tr)
    assert logic.ai_next(con) is None
    full = c.get(f"/api/events/{rid}", headers=tma(20)).json()
    assert full["i18n"]["en"] == {"title": "Hack night", "description": "Code till dawn"}
    assert logic.cards(con, logic.Viewer(pres["id"], "student", True), [logic.one(con, "SELECT * FROM events WHERE id = ?", rid)])[0]["i18n"] == \
        {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}
    post = logic.channel_due(con, "bot")[0][1]
    assert "<i>\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456</i>" in post and "<i>Hack night</i>" in post

    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "place": "306"})   # not the text: the translation stays
    assert logic.ai_next(con) is None
    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430"})
    kind, rid, was = logic.ai_next(con)
    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430 2"})  # edited while the model thought
    logic.ai_save(con, kind, rid, was, "ru", {"kk": {"title": "x", "description": "x"}, "en": {"title": "x", "description": "x"}})
    assert one_val(con, "SELECT i18n FROM events WHERE id = ?", rid) is None and logic.ai_next(con)[2]["title"] == "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430 2"
    for _ in range(3):
        logic.ai_failed(con, "event", rid, "bad")
    assert logic.ai_next(con) is None and logic.ai_state(con)["error"].endswith("event %d: bad" % rid)

    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u0421\u0431\u043e\u0440 \u043a\u043e\u043c\u0430\u043d\u0434\u044b", "visibility": "members"})
    assert logic.ai_next(con) is None                                     # a team-only event never goes out

    # the club: its description, kept apart from the name; cards don't carry it
    c.patch("/api/orgs/1", headers=tma(20), json={"description": "\u041c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u0432\u0435\u0449\u0438."})
    con.execute("UPDATE orgs SET i18n = ? WHERE id = 1", (json.dumps({"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b"}}),))
    kind, oid, was = logic.ai_next(con)
    assert (kind, oid, was) == ("org", 1, {"description": "\u041c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u0432\u0435\u0449\u0438."})
    logic.ai_save(con, kind, oid, was, "ru", {"kk": {"description": "\u0411\u0456\u0437 \u0436\u0430\u0441\u0430\u0439\u043c\u044b\u0437."}, "en": {"description": "We build things."}})
    assert json.loads(one_val(con, "SELECT i18n FROM orgs WHERE id = 1")) == {"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b", "description": "\u0411\u0456\u0437 \u0436\u0430\u0441\u0430\u0439\u043c\u044b\u0437."},
                                                                             "en": {"description": "We build things."}}
    assert "description" not in logic.org_ref(con, logic.one(con, "SELECT * FROM orgs WHERE id = 1"))["i18n"]["kk"]
    assert logic.ai_state(con)["today"] == 2
    c.patch("/api/orgs/1", headers=tma(20), json={"description": "\u041d\u043e\u0432\u043e\u0435."})
    assert json.loads(one_val(con, "SELECT i18n FROM orgs WHERE id = 1")) == {"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b"}} and logic.ai_next(con)[0] == "org"
    con.close()


def one_val(con, sql: str, *args):
    return logic.one(con, sql, *args)[0]


def test_admin_day_and_ai(env):
    """The admin's chart opens a day: who came in, newcomers marked. The AI page counts
    what was translated, what waits and what failed, and gives the failed three more tries."""
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({1}))))
    adm = c.get("/api/me", headers=tma(1)).json()
    ali = login(c, 30, "ali")
    con = db.connect(cfg.db_path)
    today = logic.day_of(logic.now())
    assert c.get(f"/api/admin/stats/{today}", headers=tma(30)).status_code == 403
    day = c.get(f"/api/admin/stats/{today}", headers=tma(1)).json()
    assert {p["id"] for p in day["people"]} >= {adm["id"], ali["id"]} and day["active"] == len(day["people"])
    assert c.get("/api/admin/stats", headers=tma(1)).json()["today"] == day["active"]
    assert c.get(f"/api/admin/stats/{today - 400}", headers=tma(1)).json()["people"] is None   # before the log
    # only opened the app: no profile to open (it was "Something went wrong"), the row goes to Telegram instead
    guest = c.get("/api/me", headers=tma(31)).json()
    prof = {p["id"]: p["profile"] for p in c.get(f"/api/admin/stats/{today}", headers=tma(1)).json()["people"]}
    assert prof[ali["id"]] and not prof[guest["id"]]
    assert c.get(f"/api/users/{guest['id']}", headers=tma(30)).status_code == 404
    ai = c.get("/api/admin/ai", headers=tma(1)).json()
    assert set(ai) >= {"on", "today", "chain", "usage", "events", "clubs", "failed"}
    assert c.post("/api/admin/ai/retry", headers=tma(30)).status_code == 403
    assert c.post("/api/admin/ai/retry", headers=tma(1)).status_code == 204


def test_deleted_stay_deleted_after_restore(env, monkeypatch, capsys):
    """H2: a copy restored after a deletion brings the person back; deletions.log (outside the database, the Telegram
    ID salted) lets `kbtu.admin redelete` delete them again, never someone who signed in again since."""
    c, cfg = env
    ali, zhan = login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    home = Path(cfg.db_path).parent
    restored = home / "restored.db"
    con.execute("VACUUM INTO ?", (str(restored),))                # last night's copy: both still there
    delete_now(c, cfg, tma(21, "Ali"))
    delete_now(c, cfg, tma(22, "Zhan"))
    line = (home / "deletions.log").read_text().splitlines()[0]
    assert len(line.split()) == 2 and re.fullmatch(r"[0-9a-f]{32}", line.split()[1]) and (home / "deletions.salt").exists()
    login(c, 22, "zhan")                                           # Zhan came back: a new sign-in after the deletion
    later = con.execute("SELECT verified_at FROM students WHERE user_id = ?", (zhan["id"],)).fetchone()[0]
    rcon = db.connect(str(restored))
    rcon.execute("UPDATE students SET verified_at = ? WHERE user_id = ?", (later + 10, zhan["id"]))  # as if restored after his return
    rcon.execute("UPDATE students SET verified_at = 0 WHERE user_id = ?", (ali["id"],))                # signed in long before
    rcon.close()
    for k, v in (("BOT_TOKEN", "1:x"), ("TOKEN_KEY", "A" * 43 + "="), ("DB_PATH", str(restored))):
        monkeypatch.setenv(k, v)
    from kbtu import admin
    admin.main(["redelete"])
    assert capsys.readouterr().out.strip() == "1 deleted again (2 in deletions.log)"
    rcon = db.connect(str(restored))
    assert [r[0] for r in rcon.execute("SELECT user_id FROM students")] == [zhan["id"]]


def test_forgetting(env, monkeypatch):
    """H2 minimisation: the bot's copies of messages lose their words after 30 days (the row keeps its key, so it
    never goes twice); DMP's registry searches lose the typed text; a migration's .bak goes after 14 days."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    t = int(time.time())
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after, sent_at) VALUES (?, 'x', 'old', '{\"t\": 1}', ?, ?), (?, 'x', 'new', '{\"t\": 1}', ?, ?)",
                (ali["id"], t - 31 * 86400, t - 31 * 86400, ali["id"], t, t))
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'registry_search', 'registry', '{\"q\": \"Ali\"}', ?)", (ali["id"], t - 31 * 86400))
    midnight = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    set_clock(monkeypatch, lambda: midnight + 600)
    logic.stats_day(con)
    assert [tuple(r) for r in con.execute("SELECT ref, payload FROM bot_outbox WHERE kind = 'x' ORDER BY ref")] == [("new", '{"t": 1}'), ("old", "{}")]
    assert con.execute("SELECT data FROM audit_log WHERE action = 'registry_search'").fetchone()[0] == "{}"
    db_path = Path(cfg.db_path).resolve()
    old, new = db_path.with_name(db_path.name + ".v1-1.bak"), db_path.with_name(db_path.name + ".v2-2.bak")
    for f, age in ((old, 15), (new, 1)):
        f.write_bytes(b"x")
        os.utime(f, (t - age * 86400, t - age * 86400))
    bot.backup_day(cfg, con)
    assert not old.exists() and new.exists()


def test_db_must_exist(tmp_path, monkeypatch):
    """A locked vault leaves an empty folder: the image's DB_MUST_EXIST=1 stops the app instead of starting it empty"""
    monkeypatch.setenv("BOT_TOKEN", "1:x")
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


def test_app_team(env):
    """The app's team: the owner alone gives or takes the admin role; an admin gives the moderator role
    and bans, never touching the owner, himself or another admin; a moderator only filters content; a ban needs a
    reason, drops the role, shows him why, and the bot stops writing; the owner reads the audit log."""
    import httpx
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({30}))))
    who = lambda uid, username: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": username.title(), "username": username}, BOT)}
    O, A, M, U, X = who(30, "owner_x"), who(31, "admin_x"), who(32, "mod_x"), who(33, "user_x"), who(34, "other_x")
    ids = {k: c.get("/api/me", headers=h).json()["id"] for k, h in dict(O=O, A=A, M=M, U=U, X=X).items()}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["O"],))
    find = lambda h, name: c.get("/api/admin/staff/find", headers=h, params={"username": name})
    role = lambda h, k, r: c.post("/api/admin/staff", headers=h, json={"userId": ids[k], "role": r})
    ban = lambda h, k, on, reason=None: c.post("/api/admin/ban", headers=h, json={"userId": ids[k], "on": on, "reason": reason})

    assert c.get("/api/admin/staff", headers=U).status_code == 403
    assert find(O, "@ADMIN_x").json()["person"]["id"] == ids["A"] and find(O, "nobody_here").status_code == 404 and find(O, "a b").status_code == 400
    assert role(O, "A", "admin").status_code == 200                       # the owner makes an admin; it survives the next sign-in
    assert c.get("/api/me", headers=A).json()["role"] == "admin"
    assert role(A, "X", "admin").status_code == 403                       # an admin can't make admins
    assert role(A, "M", "moderator").json()["team"][-1]["person"]["id"] == ids["M"]
    assert role(A, "O", "user").status_code == 403 and ban(A, "O", True, "nope").status_code == 403   # nobody touches the owner
    assert role(A, "A", "user").status_code == 403                        # nor himself
    assert role(M, "U", "moderator").status_code == 403 and c.get("/api/admin/staff", headers=M).status_code == 403
    assert c.get("/api/admin/reports", headers=M).status_code == 200     # the moderator's own work
    assert c.get("/api/admin/stats", headers=M).status_code == 403
    assert find(M, "user_x").status_code == 403 and c.get("/api/admin/club-applications", headers=M).status_code == 403   # clubs are the admin's
    assert c.post("/api/admin/feature", headers=M, json={"postId": 1, "days": 1}).status_code == 403
    assert c.get("/api/me", headers=M).json()["counters"]["clubApps"] == 0
    assert ban(A, "X", True, "testing an admin ban").status_code == 200 and ban(A, "X", False).status_code == 200   # an admin bans users
    assert c.post("/api/admin/ban", headers=O, json={"userId": ids["X"], "on": 1, "reason": "nope"}).status_code == 400   # a real bool
    assert ban(O, "X", True, "x" * 301).status_code == 400
    assert logic.one(con, "SELECT ban_reason FROM users WHERE id = ?", ids["X"])["ban_reason"] is None   # unban cleared it
    assert role(O, "A", "moderator").status_code == 200 and role(O, "A", "admin").status_code == 200
    assert ban(A, "X", True, "nope") .status_code == 200 and role(O, "X", "user").status_code == 200 and ban(O, "X", False).status_code == 200
    assert role(O, "X", "admin").status_code == 200 and ban(A, "X", True, "nope").status_code == 403   # an admin can't ban an admin
    assert role(O, "X", "user").status_code == 200
    assert role(O, "A", "moderator").status_code == 200 and ban(O, "A", True, "spam links").status_code == 200   # the owner may
    assert role(O, "A", "admin").status_code == 409                       # banned: no role back until unbanned

    assert ban(O, "U", True).status_code == 400                           # a reason is required
    assert ban(O, "M", True, "  insults   in chats ").json()["banned"][0]["banReason"] == "insults in chats"
    r = c.get("/api/me", headers=M)
    assert r.status_code == 403 and r.json()["message"] == "banned" and r.json()["reason"] == "insults in chats" and r.json()["contact"] == "owner_x"
    assert logic.one(con, "SELECT role FROM users WHERE id = ?", ids["M"])["role"] == "user"
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'new_event', 'event:1', 0)", (ids["M"],))
    sent = []

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda q: sent.append(q) or httpx.Response(200, json={"ok": True, "result": {}}))) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())
    assert not sent and logic.one(con, "SELECT error FROM bot_outbox WHERE user_id = ?", ids["M"])["error"] == "banned"   # the bot keeps quiet
    assert ban(O, "M", False).status_code == 200 and c.get("/api/me", headers=M).status_code == 200

    log = c.get("/api/admin/audit", headers=O).json()
    assert [a["action"] for a in log][:3] == ["unban", "ban", "ban"] and log[1]["data"] == {"reason": "insults in chats"}
    assert c.get("/api/admin/audit", headers=A).status_code == 403      # the owner's only (A is banned anyway)
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ids["A"],))
    assert role(O, "A", "admin").status_code == 200 and c.get("/api/admin/audit", headers=A).status_code == 403

    # an ADMIN_TG_IDS admin banned by the owner stays a plain user while banned (the ban outranks the env)
    con.execute("UPDATE users SET is_founder = 0 WHERE id = ?", (ids["O"],))
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["A"],))
    assert ban(A, "O", True, "env admin test").status_code == 200
    assert c.get("/api/me", headers=O).status_code == 403 and logic.one(con, "SELECT role FROM users WHERE id = ?", ids["O"])["role"] == "user"
    assert ban(A, "O", False).status_code == 200 and c.get("/api/me", headers=O).json()["role"] == "admin"   # back at the next sign-in
    # migration 61 keeps the owner's admin role, takes the rest
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ids["X"],))
    con.executescript(dict(db.MIGRATIONS)[61])
    assert [r["role"] for r in con.execute("SELECT role FROM users WHERE id IN (?, ?, ?) ORDER BY id", (ids["O"], ids["A"], ids["X"]))] == ["user", "admin", "user"]


def test_profile_privacy(env, monkeypatch):
    """Audit M2: a stranger sees the card, bio and achievements but not clubs, past roles, event badges or a club's
    badge that came by itself, and at most PROFILES_A_DAY profiles a day (the same one again is free); friends,
    clubmates and moderators see it all and are never counted."""
    c, cfg = env
    ann, bob, cat, dan, eve = (login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve")))
    con = db.connect(cfg.db_path)
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0),
        (2, 'studex', 'club', 'StudEx', 'SE', 'star_3d', 1, 0), (3, 'chess', 'club', 'Chess', 'CH', 'crown_3d', 1, 0)""")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0), (1, ?, 'member', 0), (2, ?, 'member', 0)", (ann, cat, ann))
    con.execute("INSERT INTO org_history (user_id, org_id, role, since, until) VALUES (?, 3, 'head', 0, 5 * 86400)", (ann,))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, badge_name, created_at, updated_at)
        VALUES (9, 1, 'published', 'Hack', '305', 1000, 'laptop_3d', '#3B6BFF', 'Hacker', 0, 0)""")
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
        VALUES (9, ?, 'going', 'T9', 0, 0, 1000)""", (ann,))
    con.execute("UPDATE users SET showcase = 'b9', tg_username = 'ann_tg' WHERE id = ?", (ann,))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ann, bob), max(ann, bob)))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (eve,))
    full = lambda tg: c.get(f"/api/users/{ann}", headers=tma(tg)).json()  # noqa: E731
    for tg in (10, 11, 12, 14):  # herself, a friend, a clubmate, a moderator
        p = full(tg)
        assert {m["org"]["id"] for m in p["clubs"]} == {1, 2} and [h["org"]["id"] for h in p["past"]] == [3] and "limited" not in p
        assert [b["eventId"] for b in p["awards"]["badges"]] == [9] and p["shelf"] == ["b9"] and p["skin"] == 2
    p = full(13)
    assert p["clubs"] == [] and p["past"] == [] and p["awards"]["badges"] == [] and p["shelf"] == [] and p["limited"] is True
    assert p["skin"] is None and p["username"] is None and p["name"] and p["course"] == 2               # StudEx's badge came by itself
    con.execute("UPDATE users SET skin_pick = 'org', skin_org = 2 WHERE id = ?", (ann,))
    assert full(13)["skin"] == 2                                                                       # picked to be shown: shows
    con.execute("INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'first_in', 1, 1000)", (ann,))
    assert all(a["at"] is None for a in full(13)["awards"]["achievements"])                            # a level's date names a check-in
    assert any(a["at"] for a in full(11)["awards"]["achievements"])
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (eve,))
    assert "limited" not in full(14)                                                                   # an admin sees it all, uncounted
    assert c.get("/api/users/999999", headers=tma(13)).status_code == 404                             # nobody there: not counted
    assert [tuple(r) for r in con.execute("SELECT viewer_id, user_id FROM profile_views")] == [(dan, ann)]  # only the stranger counts
    monkeypatch.setattr(logic.profiles, "PROFILES_A_DAY", 2)
    assert c.get(f"/api/users/{ann}", headers=tma(13)).status_code == 200                              # the same one again: free
    assert c.get(f"/api/users/{bob}", headers=tma(13)).status_code == 200
    assert c.get(f"/api/users/{cat}", headers=tma(13)).json()["error"] == "rate_limited"
    assert c.get(f"/api/users/{ann}", headers=tma(12)).status_code == 200                              # a clubmate is never counted
    later = int(time.time()) + 2 * 86400
    set_clock(monkeypatch, lambda: later)                                                   # two days on
    assert c.get(f"/api/users/{cat}", headers=tma(13)).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM profile_views WHERE day < ?", ((later + 5 * 3600) // 86400 - 1,)).fetchone()[0] == 0
    c.get(f"/api/users/{dan}", headers=tma(10))                                                        # dan is someone's stranger too
    logic.delete_me(con, logic.Viewer(dan, "user", True))
    assert con.execute("SELECT COUNT(*) FROM profile_views WHERE ? IN (viewer_id, user_id)", (dan,)).fetchone()[0] == 0


def test_report_limit(env, monkeypatch):
    """The day's limit counts new reports only: updating one still waiting is free (the one report sheet)."""
    c, cfg = env
    ann, bob, cat = (login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat")))
    monkeypatch.setattr(logic.moderation, "REPORTS_A_DAY", 1)
    rep = lambda uid, note=None: c.post("/api/reports", headers=tma(10), json={"target": "user", "id": uid, "reason": "spam", "note": note})  # noqa: E731
    assert rep(bob).status_code == 204 and rep(cat).json()["error"] == "rate_limited"
    assert rep(bob, "Fake name").status_code == 204                                                    # the open one, updated: free
    con = db.connect(cfg.db_path)
    assert [tuple(r) for r in con.execute("SELECT target_id, note FROM reports")] == [(bob, "Fake name")]
    logic.delete_me(con, logic.Viewer(ann, "user", True))                                              # her words go with her data
    assert [tuple(r) for r in con.execute("SELECT reporter_id, target_id, note FROM reports")] == [(None, bob, None)]


def test_club_short_links(env):
    """A5: a club's slug comes from its name (Cyrillic in Latin letters, unique, never the app's own paths); only the
    President changes it; kbtu.sow.kz/<slug> opens the club in the bot; the clubs made before take their names' slugs."""
    c, cfg = env
    pres, vice = login(c, 90, "pres"), login(c, 91, "vice")
    con = db.connect(cfg.db_path)
    with db.tx(con):
        a = logic.create_org(con, None, "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u0443\u0431", "SK", "trophy_3d", False)
        b = logic.create_org(con, None, "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439  \u041a\u043b\u0443\u0431!", "SK", "trophy_3d", False)
        x = logic.create_org(con, None, "API", "A", "trophy_3d", False)
        old = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('club7', 'club', 'Open Mic', 'OM', 'trophy_3d', 0)").lastrowid
    slug = lambda oid: con.execute("SELECT slug FROM orgs WHERE id = ?", (oid,)).fetchone()[0]  # noqa: E731
    assert (slug(a), slug(b), slug(x)) == ("shahmatnyiklub", "shahmatnyiklub2", "api2")
    con.execute("DELETE FROM meta WHERE key = 'slugs_named'")  # the app's start ran it already
    logic.name_slugs(con)
    assert slug(old) == "openmic"
    con.execute("UPDATE orgs SET slug = 'club7' WHERE id = ?", (old,))
    logic.name_slugs(con)
    assert slug(old) == "club7"                                                        # once: a chosen club7 stays
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0), (?, ?, 'vice', 0)", (a, pres["id"], a, vice["id"]))
    P = tma(90, "Pres")
    assert c.patch(f"/api/orgs/{a}", headers=tma(91, "Vice"), json={"slug": "chess"}).status_code == 403   # the President's
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "exit"}).status_code == 400                  # the app's own
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "Ch-ess"}).status_code == 400
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "club7"}).status_code == 409
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "Chess"}).json()["slug"] == "chess"
    r = c.get("/Chess", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith(f"?startapp=cl_{a}")
    assert c.get("/shahmatnyiklub", follow_redirects=False).headers["location"].endswith(f"cl_{a}")  # the old bio still works
    assert logic.slug_for(con, "Shahmatnyi klub") == "shahmatnyiklub3"                 # and nobody else takes it
    assert c.get("/nosuchclub", follow_redirects=False).status_code == 200                              # the app itself
    assert c.get("/exit", follow_redirects=False).headers["location"].endswith("startapp=exit")


def test_custom_short_links(env):
    """A club's Vice+ makes kbtu.sow.kz/<slug> for the club, one of its published events or its round, never outside the
    app; names are first come, first served across club slugs and links, never the app's own; DMP's admin revokes any."""
    c, cfg = env
    ids = {n: login(c, i, n)["id"] for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "other"), (24, "boss"))}
    H = {n: tma(i, n.title()) for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "other"), (24, "boss"))}
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'trophy_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, ids["pres"], "president"), (1, ids["vice"], "vice"), (1, ids["head"], "head"), (2, ids["other"], "president")])
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ids["boss"],))
    start = int(time.time()) + 3600
    ev = c.post("/api/orgs/1/events", headers=H["pres"], json={"title": "Hack night", "place": "305", "startsAt": start, "endsAt": start + 7200,
                                                                "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    add = lambda who, body, org=1: c.post(f"/api/orgs/{org}/links", headers=H[who], json=body)  # noqa: E731
    assert add("head", {"slug": "join-it", "kind": "club"}).status_code == 403                  # Vice and above
    assert add("other", {"slug": "join-it", "kind": "club"}).status_code == 403                 # someone else's club
    assert add("vice", {"slug": "hack", "kind": "event", "eventId": ev["id"]}).status_code == 400  # a draft
    c.post(f"/api/events/{ev['id']}/publish", headers=H["pres"])
    other = c.post("/api/orgs/2/events", headers=H["other"], json={"title": "Blitz", "place": "305", "startsAt": start, "endsAt": start + 60,
                                                                    "emoji": "trophy_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{other['id']}/publish", headers=H["other"])
    assert add("vice", {"slug": "blitz", "kind": "event", "eventId": other["id"]}).status_code == 400  # another club's event
    for bad in ("a", "-it", "it-", "i--t", "\u0430\u0431\u0432", "x" * 33, "it/../x", "https://evil.example"):
        assert add("vice", {"slug": bad, "kind": "club"}).status_code == 400, bad
    assert add("vice", {"slug": "evil", "kind": "url", "url": "https://evil.example"}).status_code == 400  # only into the app
    for taken in ("admin", "api", "login", "assets", "static", "privacy", "chess"):              # the app's own, a club's slug
        assert add("vice", {"slug": taken, "kind": "club"}).json()["message"] == "taken", taken
    assert add("vice", {"slug": "Join-IT", "kind": "club"}).status_code == 200
    assert add("vice", {"slug": "hack-night", "kind": "event", "eventId": ev["id"]}).status_code == 200
    got = add("pres", {"slug": "it-casting", "kind": "round"}).json()
    assert {(x["slug"], x["kind"], x["eventTitle"]) for x in got} == {("join-it", "club", None), ("hack-night", "event", "Hack night"), ("it-casting", "round", None)}
    assert add("other", {"slug": "join-it", "kind": "club"}, 2).json()["message"] == "taken"   # first come, first served
    assert c.patch("/api/orgs/2", headers=H["other"], json={"slug": "hacknight"}).status_code == 200
    assert add("vice", {"slug": "hacknight", "kind": "club"}).json()["message"] == "taken"      # nor a club's slug
    assert logic.slug_for(con, "Join") == "join" and not logic._slug_free(con, "join-it", None)
    assert c.get("/api/orgs/1/links", headers=H["head"]).status_code == 403
    go = lambda p: c.get(p, follow_redirects=False).headers.get("location", "")  # noqa: E731
    assert go("/join-it").endswith("?startapp=cl_1") and go("/HACK-NIGHT").endswith(f"?startapp=ev_{ev['id']}") and go("/it-casting").endswith("?startapp=rc_1")
    assert go("/it").endswith("?startapp=cl_1")                                                   # the club's slug as before
    # its own Vice takes one down; another club can't; the admin revokes any, and the log says which
    assert c.delete("/api/links/join-it", headers=H["other"]).status_code == 403
    assert c.delete("/api/links/join-it", headers=H["vice"]).status_code == 204
    assert go("/join-it").endswith("?startapp=cl_1")                                             # its posters open the club now
    assert add("other", {"slug": "join-it", "kind": "club"}, 2).json()["message"] == "taken"   # never another club's
    assert "it-casting" in next(o for o in c.get("/api/admin/orgs", headers=H["boss"]).json() if o["id"] == 1)["shortLinks"]
    assert c.delete("/api/links/it-casting", headers=H["boss"]).status_code == 204
    assert c.delete("/api/links/it-casting", headers=H["boss"]).status_code == 404
    assert [r[0] for r in con.execute("SELECT action FROM audit_log WHERE action LIKE 'link_%' ORDER BY id")] == ["link_create"] * 3 + ["link_delete", "link_revoke"]
    # a deleted event takes its link along; a hidden club's links lead nowhere
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert c.get("/hack-night", follow_redirects=False).status_code == 200
    con.execute("DELETE FROM events WHERE id = ?", (ev["id"],))
    assert not con.execute("SELECT 1 FROM short_links WHERE slug = 'hack-night'").fetchone()
    # an event deleted in the app keeps its link's name for its club, which may take it again
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 1")
    ev2 = c.post("/api/orgs/1/events", headers=H["pres"], json={"title": "Draft", "place": "305", "startsAt": start, "endsAt": start + 60,
                                                                 "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{ev2['id']}/publish", headers=H["pres"])
    assert add("vice", {"slug": "draft-ev", "kind": "event", "eventId": ev2["id"]}).status_code == 200
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (ev2["id"],))
    assert c.delete(f"/api/events/{ev2['id']}", headers=H["pres"]).status_code in (200, 204)
    assert add("other", {"slug": "draft-ev", "kind": "club"}, 2).json()["message"] == "taken"
    assert add("vice", {"slug": "draft-ev", "kind": "club"}).status_code == 200
    assert logic.kz_phone("\u0667\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668") is None    # Arabic-Indic digits
    assert logic.kz_phone("+7 701 234 56 7") is None and logic.kz_phone("701 234 56 78") == "+77012345678"
    assert logic.kz_phone("8 (701) 234-56-78") == logic.kz_phone("+7 701 234 5678") == "+77012345678"


def test_door_guests(env):
    """A19: a walk-in without the app types their full name at the door (Member+, door open, a free event); the typist
    takes a wrong one back in 10 minutes; Head+ sees full names, a Member short ones. A student confirmed by Microsoft
    with that name counts as came, only when exactly one unlinked entry at that event has it."""
    c, cfg = env
    pres, mem, ali, bota = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali"), login(c, 74, "bota")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    for eid, price in ((1, None), (2, None), (3, 1000)):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at, price,
            pay_to_name, pay_phone) VALUES (?, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0, ?, 'Pres', '+70000000000')""",
            (eid, start, start + 7200, pres["id"], price))
    M, P = tma(71, "Mem"), tma(70, "Pres")
    add = lambda eid, name, h=M: c.post(f"/api/events/{eid}/door/guests", headers=h, json={"name": name})  # noqa: E731
    assert add(1, "Ali Testov", tma(73, "Zhan")).status_code == 403                    # the team only
    assert add(1, "Ali").status_code == 400 and add(1, "Ali 123").status_code == 400   # a first and a last name
    assert add(3, "Ali Testov").json()["message"] == "paid"
    g = add(1, "Ali  Testov").json()
    assert (g["name"], g["undo"]) == ("Ali T.", True)                                  # a Member: the short name
    assert add(1, "testov ali").json()["message"] == "already"
    assert [x["name"] for x in c.get("/api/events/1/door/guests", headers=P).json()] == ["Ali Testov"]
    assert c.delete(f"/api/events/1/door/guests/{g['id']}", headers=P).status_code == 409   # the typist's
    assert c.delete(f"/api/events/1/door/guests/{g['id']}", headers=M).status_code == 204
    add(1, "Ali Testov"); add(1, "Bota Testova"); add(2, "Ali Testov"); add(1, "Mem Testov")
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = 2")                # the door's rules still hold
    ms = lambda uid: logic.ms_link(con, uid, {"oid": f"o{uid}", "email": "a@kbtu.kz", "first": "", "last": "", "profile": {}})  # noqa: E731
    ms(ali["id"])
    came = lambda uid: con.execute("SELECT event_id, checked_in_at IS NOT NULL, walk_in FROM registrations WHERE user_id = ?", (uid,)).fetchall()  # noqa: E731
    assert [tuple(r) for r in came(ali["id"])] == [(1, 1, 1)]
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'rate'", (ali["id"],)).fetchone()  # as a real check-in
    assert {x["name"]: x["linked"] for x in c.get("/api/events/1/door/guests", headers=P).json()}["Ali Testov"] is True
    assert came(bota["id"]) == []                                                      # "Bota Testova" is not "Bota Testov"
    other = login(c, 75, "other")
    con.execute("UPDATE students SET first_name = 'Mem' WHERE user_id = ?", (other["id"],))  # two students named Mem Testov
    ms(mem["id"])
    assert came(mem["id"]) == []                                                       # nobody can tell which one came
    # the check-in a typed name made is taken back within 10 minutes: the name goes with it, and nothing links again
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 204
    assert [tuple(r) for r in came(ali["id"])] == [(1, 0, 1)]
    assert "Ali Testov" not in [x["name"] for x in c.get("/api/events/1/door/guests", headers=P).json()]
    logic.link_door_guests(con, ali["id"])
    assert [tuple(r) for r in came(ali["id"])] == [(1, 0, 1)]
    logic.delete_me(con, logic.Viewer(ali["id"], "user", True))
    assert not con.execute("SELECT 1 FROM door_guests WHERE event_id = 1 AND norm = 'ali testov'").fetchone()


def test_staff_badge_and_chat_order(env):
    """A9: everyone sees who is the app's moderator or admin; A8: the chats directory lists the biggest first."""
    c, cfg = env
    ali, mod = login(c, 61, "ali"), login(c, 62, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    A = tma(61, "Ali")
    assert (c.get(f"/api/users/{mod['id']}", headers=A).json()["staff"], c.get(f"/api/users/{ali['id']}", headers=A).json()["staff"]) == ("moderator", None)
    for title, n, sort in (("Small", 10, 0), ("Big", 900, 5), ("Unknown", None, 0)):
        con.execute("INSERT INTO chats (title, kind, url, members, sort, status, created_at) VALUES (?, 'group', 'https://t.me/x', ?, ?, 'live', 0)", (title, n, sort))
    assert [x["title"] for x in c.get("/api/chats", headers=A).json()["all"]] == ["Big", "Small", "Unknown"]


def test_dm_on(env):
    """Telegram's "allow messages" from inside the app: the bot may write at once, and the event just
    signed up for gets its confirmation with the ticket; nothing for an event I'm not going to."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    for i in (1, 2):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, created_by, created_at, updated_at)
            VALUES (?, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0)""", (i, start, start + 7200, pres["id"]))
    A = tma(21, "Ali")
    con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (ali["id"],))
    assert c.get("/api/me", headers=A).json()["canDm"] is False
    assert c.post("/api/events/1/registration", headers=A, json={}).json()["my"]["status"] == "going"
    assert c.post("/api/me/dm", headers=A, json={"event": 1}).json()["canDm"] is True
    c.post("/api/me/dm", headers=A, json={"event": 2})   # not going there: no message
    c.post("/api/me/dm", headers=A, json={"event": 1})   # twice: one message
    sent = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'going_ok'").fetchall()
    assert [s["ref"] for s in sent] == ["event:1"] and bot._render(con, sent[0])[2] == "tk_1"
    assert c.post("/api/me/dm", headers=tma(30, "Guest"), json={}).status_code == 200   # a guest too: the bot may write


def test_club_people(env):
    """Members are public: President and Vice on the club, everyone behind a button; a club may hide the list."""
    c, cfg = env
    pres, vice, ali, bob = login(c, 70, "pres"), login(c, 71, "vice"), login(c, 72, "ali"), login(c, 73, "bob")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for u, role in ((pres, "president"), (vice, "vice"), (ali, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", (u["id"], role))
    o = c.get("/api/orgs/1", headers=tma(73)).json()
    assert [m["role"] for m in o["leaders"]] == ["president", "vice"] and o["membersHidden"] is False
    everyone = c.get("/api/orgs/1/people", headers=tma(73)).json()
    assert [m["person"]["id"] for m in everyone] == [pres["id"], vice["id"], ali["id"]] and "username" not in everyone[0]
    assert c.patch("/api/orgs/1", headers=tma(72), json={"membersHidden": True}).status_code == 403   # a member can't
    assert c.patch("/api/orgs/1", headers=tma(70), json={"membersHidden": True}).json()["membersHidden"] is True
    assert c.get("/api/orgs/1/people", headers=tma(73)).status_code == 403                             # a stranger now can't
    assert len(c.get("/api/orgs/1/people", headers=tma(72)).json()) == 3                               # its own people can
    assert len(c.get("/api/orgs/1", headers=tma(73)).json()["leaders"]) == 2                           # the leaders still show


def test_club_abbr(env):
    """A club's short name: the clubs made before take their initials at start and keep a set one; a new
    club has its initials from the first day; Vice+ edit it (one word, 2-8 characters), a member can't; DMP and the
    admin may set any club's, and only that."""
    c, cfg = env
    pres, vice, ali, dmp, boss = (login(c, 70 + i, n) for i, n in enumerate(("pres", "vice", "ali", "dmp", "boss")))
    con = db.connect(cfg.db_path)
    film = "\u041a\u043b\u0443\u0431 \u043a\u0438\u043d\u043e \u0438 \u0442\u0435\u0430\u0442\u0440\u0430"  # "Club of film and theatre" in Russian
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic Club of KBTU', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'film', 'club', ?, 'F', 'popcorn_3d', 0)", (film,))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, abbr, emoji, created_at) VALUES (3, 'go', 'club', 'Go Club', 'G', 'Baduk', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, pres["id"], "president"), (1, vice["id"], "vice"), (1, ali["id"], "member"), (9, dmp["id"], "head")])
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    logic.fill_abbrs(con)
    logic.fill_abbrs(con)   # every start: nothing left to fill
    assert [r[0] for r in con.execute("SELECT abbr FROM orgs WHERE id IN (1, 2, 3) ORDER BY id")] == ["OMC", "\u041a\u041a\u0422", "Baduk"]
    assert logic.initials("Studex") == "STUDEX" and logic.initials("The Club") == "CLUB"
    assert con.execute("SELECT abbr FROM orgs WHERE id = ?", (logic.create_org(con, None, "Robotics and AI Society", "R", "laptop_3d", False),)).fetchone()[0] == "RAS"

    patch = lambda uid, body: c.patch("/api/orgs/1", headers=tma(uid), json=body)  # noqa: E731
    assert c.get("/api/orgs/1", headers=tma(72)).json()["abbr"] == "OMC"
    assert patch(72, {"abbr": "MIC"}).status_code == 403                         # a member can't
    assert patch(71, {"abbr": "MIC"}).json()["abbr"] == "MIC"                    # the Vice can
    for bad in ("M", "TOO LONG", "NINECHARS", ""):
        assert patch(70, {"abbr": bad}).status_code == 400, bad
    assert patch(73, {"abbr": "OMC"}).json()["abbr"] == "OMC"                    # DMP on any club
    assert patch(73, {"abbr": "OMC", "name": "Mic Night"}).status_code == 403    # and nothing else
    assert patch(74, {"abbr": "MIC"}).json()["abbr"] == "MIC"                    # the admin too


def test_org_chats(env, monkeypatch):
    """An org's own Telegram chats (PLAN 86): its Vice+ link them in Studio by @name, a t.me link or an invite link; the
    first public channel is the main one; a closed chat shows on the page without its invite link; another org's chat
    is refused, a catalog chat becomes the org's and stays in the catalog with whose it is; the admin links any catalog
    chat; our bot, added by someone who may edit the club, keeps the card, and a suggestion or a catalog delete never
    takes a chat off its club's page."""
    import dataclasses
    from kbtu import media
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({89}))))
    pres, vice, ali, boss = (login(c, 80 + i, n) for i, n in enumerate(("pres", "vice", "ali", "boss")))
    login(c, 89, "admin")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice"), (ali["id"], "member")])
    pages = {"https://t.me/mic_news": {"title": "Open Mic News", "members": 900, "channel": True, "about": "Every Friday"},
             "https://t.me/mic_talk": {"title": "Open Mic Talk", "members": 120, "channel": False},
             "https://t.me/+Secret123": {"title": "Open Mic Team", "members": 14, "channel": False},
             "https://t.me/kbtusite": {"title": "KBTU | SITE", "members": 5000, "channel": True},
             "https://t.me/some_person": {"title": "Someone", "members": None}}
    async def peek(http, url):
        return {"ok": True, "image": None, **pages.get(url, {"title": None, "members": None})}
    monkeypatch.setattr(media, "chat_peek", peek)
    add = lambda uid, link, oid=1: c.post(f"/api/orgs/{oid}/chats", headers=tma(uid), json={"link": link})  # noqa: E731

    assert add(82, "@mic_news").status_code == 403                                     # a member can't
    assert add(81, "@some_person").status_code == 400 and add(81, "hello").status_code == 400
    got = add(81, "https://t.me/mic_news").json()                                       # the Vice can
    assert [(x["title"], x["main"], x["about"], x["bot"]) for x in got] == [("Open Mic News", True, "Every Friday", False)]
    add(80, "@mic_talk"), add(80, "t.me/+Secret123")
    page = c.get("/api/orgs/1", headers=tma(82)).json()["chats"]
    assert [(x["title"], x["kind"], x["closed"], x["url"]) for x in page] == [
        ("Open Mic News", "channel", False, "https://t.me/mic_news"), ("Open Mic Talk", "group", False, "https://t.me/mic_talk"),
        ("Open Mic Team", "group", True, None)]                                         # no way into a closed one from the page
    studio = c.get("/api/orgs/1/chats", headers=tma(80)).json()
    assert studio[2]["url"] == "https://t.me/+Secret123" and c.get("/api/orgs/1/chats", headers=tma(82)).status_code == 403
    assert c.get("/api/chats", headers=tma(82)).json()["all"] == []                     # linked from Studio: not in the catalog
    talk = studio[1]["id"]
    assert c.put(f"/api/orgs/1/chats/{talk}/main", headers=tma(80)).status_code == 400  # a group is no main channel

    # the catalog's chat: SITE's by the admin's hand, and then no club takes it
    site = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/kbtusite", "kind": "channel"}).json()
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(80), json={"orgId": 2}).status_code == 403
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(89), json={"orgId": 2}).json()["org"]["slug"] == "site"
    assert c.get("/api/chats", headers=tma(82)).json()["all"][0]["org"]["id"] == 2      # the catalog says whose
    assert c.get("/api/orgs/2", headers=tma(82)).json()["chats"][0]["main"] is True
    assert add(80, "@kbtusite").status_code == 409

    # a student suggests the club's own chat: that row waits (still the club's); declined, it stays on the page
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "@mic_talk"}).json()["status"] == "sent"
    pending = c.get("/api/chats", headers=tma(89)).json()["pending"]
    assert [x["id"] for x in pending] == [talk]
    assert c.delete(f"/api/admin/chats/{talk}", headers=tma(89)).status_code == 204
    assert talk in [x["id"] for x in c.get("/api/orgs/1", headers=tma(82)).json()["chats"]]

    # our bot: a group added by Studio's link, by someone who may edit the club; a stranger's /start claims nothing
    assert logic.bot_added(con, 99999, {"id": -100500, "type": "supergroup"}, cid=talk) is None
    assert logic.bot_added(con, 82, {"id": -100500, "type": "supergroup"}, cid=talk) is None    # Ali is only a member
    assert logic.bot_added(con, 81, {"id": -100500, "type": "supergroup"}, cid=talk) == talk
    news = studio[0]["id"]
    assert logic.bot_added(con, 80, {"id": -100600, "type": "channel", "username": "Mic_News"}) == news  # a channel by its @name
    assert logic.chat_card(con, news, {"title": "Open Mic", "about": "", "members": 950}) is None
    first = c.get("/api/orgs/1", headers=tma(82)).json()["chats"][0]
    assert (first["title"], first["members"], first["about"]) == ("Open Mic", 950, None)          # Telegram's card; an empty about clears it
    assert [x["bot"] for x in c.get("/api/orgs/1/chats", headers=tma(80)).json()][:2] == [True, True]
    logic.bot_left(con, -100600)
    assert c.get("/api/orgs/1/chats", headers=tma(80)).json()[0]["bot"] is False

    # off the page: the club's own row goes, the catalog's stays in the catalog
    secret = next(x["id"] for x in studio if x["closed"])
    assert [x["title"] for x in c.delete(f"/api/orgs/1/chats/{secret}", headers=tma(81)).json()] == ["Open Mic", "Open Mic Talk"]
    assert not con.execute("SELECT 1 FROM chats WHERE id = ?", (secret,)).fetchone()
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(89), json={"orgId": None}).json()["org"] is None
    assert c.get("/api/orgs/2", headers=tma(82)).json()["chats"] == [] and len(c.get("/api/chats", headers=tma(82)).json()["all"]) == 1


def _chats_club(env, monkeypatch):
    """A club (Pres 80, Vice 81, member 82), the admin 89, a moderator 88, and t.me pages made up for the chats tests."""
    import dataclasses
    from kbtu import media
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({89}))))
    pres, vice, ali = (login(c, 80 + i, n) for i, n in enumerate(("pres", "vice", "ali")))
    login(c, 89, "admin"), login(c, 88, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 88")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice"), (ali["id"], "member")])
    pages = {"https://t.me/+Secret123": {"title": "Open Mic Team", "members": 14, "channel": False},
             "https://t.me/+Waiting99": {"title": "Some Closed Group", "members": 40, "channel": False},
             "https://t.me/kbtu_talk": {"title": "KBTU Talk", "members": 3000, "channel": False}}
    async def peek(http, url):
        return {"ok": True, "image": None, **pages.get(url, {"title": None, "members": None})}
    monkeypatch.setattr(media, "chat_peek", peek)
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    return c, con


def test_org_closed_chat_stays_off_catalog(env, monkeypatch):
    """Review finding 1: a club's closed chat (an invite link) never reaches the catalog: a student's suggestion and the
    admin's add are refused as "already in the app"; the moderator's list says whose a waiting chat is."""
    c, con = _chats_club(env, monkeypatch)
    secret = c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "https://t.me/+Secret123"}).json()[0]["id"]
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "t.me/+Secret123"}).json()["status"] == "org"
    r = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/+Secret123", "kind": "group"})
    assert r.status_code == 409 and r.json()["message"] == "org"
    assert con.execute("SELECT status FROM chats WHERE id = ?", (secret,)).fetchone()[0] == "org"
    assert c.get("/api/chats", headers=tma(82)).json()["all"] == []
    # a public chat of the club may be suggested: it waits with its owner shown, and comes back owned when approved
    c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "@kbtu_talk"})
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "@kbtu_talk"}).json()["status"] == "sent"
    waiting = c.get("/api/chats", headers=tma(88)).json()["pending"]
    assert [(x["title"], x["org"]["slug"]) for x in waiting] == [("KBTU Talk", "mic")]
    assert c.post(f"/api/admin/chats/{waiting[0]['id']}/approve", headers=tma(88)).json()["org"]["slug"] == "mic"


def test_org_drop_closed_pending_chat(env, monkeypatch):
    """Review finding 2: a closed chat waiting for the catalog and given to the club, when the club removes it, goes:
    never left waiting with nobody's name (its invite link would land in the catalog)."""
    c, con = _chats_club(env, monkeypatch)
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "t.me/+Waiting99"}).json()["status"] == "sent"
    cid = c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "t.me/+Waiting99"}).json()[0]["id"]   # the admin gives it to the club
    assert tuple(con.execute("SELECT status, org_id FROM chats WHERE id = ?", (cid,)).fetchone()) == ("pending", 1)
    assert c.delete(f"/api/orgs/1/chats/{cid}", headers=tma(81)).json() == []
    assert con.execute("SELECT 1 FROM chats WHERE id = ?", (cid,)).fetchone() is None
    assert "pending" in c.get("/api/chats", headers=tma(88)).json() and c.get("/api/chats", headers=tma(88)).json()["pending"] == []


def test_org_catalog_chat_is_the_admins_to_give(env, monkeypatch):
    """Review finding 3: a catalog chat nobody owns isn't a Vice's to take (conflict catalog: ask the app's team); the
    admin gives it, and a claimed chat counts toward the club's 12."""
    c, con = _chats_club(env, monkeypatch)
    talk = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/kbtu_talk", "kind": "group"}).json()["id"]
    r = c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "@kbtu_talk"})
    assert r.status_code == 409 and r.json()["message"] == "catalog"
    assert con.execute("SELECT org_id FROM chats WHERE id = ?", (talk,)).fetchone()[0] is None
    con.executemany("INSERT INTO chats (title, kind, url, created_at, status, org_id) VALUES (?, 'group', ?, 0, 'org', 1)",
                    [(f"Chat {i}", f"https://t.me/chat_{i}") for i in range(12)])
    r = c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "@kbtu_talk"})   # the admin, but the club is full
    assert r.status_code == 409 and r.json()["message"] == "limit"
    con.execute("DELETE FROM chats WHERE url = 'https://t.me/chat_0'")
    assert "KBTU Talk" in [x["title"] for x in c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "@kbtu_talk"}).json()]
    assert tuple(con.execute("SELECT org_id, status FROM chats WHERE id = ?", (talk,)).fetchone()) == (1, "live")  # still in the catalog
    con.execute("UPDATE chats SET kind = 'channel' WHERE url = 'https://t.me/chat_1'")
    assert logic.bot_added(con, 89, {"id": -100700, "type": "channel", "title": "Chat 1"}) is None   # the admin: never by a title
    assert logic.bot_added(con, 81, {"id": -100700, "type": "channel", "title": "Chat 1"}) is not None


def test_channel_mirror(env, tmp_path):
    """PLAN 86 part 2: an org's main public channel in its news (mirror.py, fed by userbot.py with fake messages here):
    a post's first line is its title, its photo copied; an album is one post; an edit follows and reads "edited"; a
    video is a link; Telegram's views and reactions show and ours are refused, and so are edits in the app; a deletion
    takes the post down once all its messages went; nobody is notified. Off in Studio, or another main channel: the
    userbot leaves and the posts already there stay."""
    import io
    from PIL import Image
    from kbtu import media, mirror
    c, cfg = env
    pres, ali = login(c, 80, "pres"), login(c, 81, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO chats (id, title, kind, url, created_at, status, org_id, main) VALUES
        (1, 'Open Mic News', 'channel', 'https://t.me/Mic_News', 0, 'org', 1, 1), (2, 'Open Mic Team', 'channel', 'https://t.me/+Secret1', 0, 'org', 1, 0)""")
    assert mirror.wanted(con) == {"mic_news": 1} and mirror.to_join(con) == ["mic_news"]   # the main public channel only
    assert mirror.take(con, 500, mirror.Msg(id=1, date=1000, text="Not joined")) is None    # a channel we don't mirror: dropped
    mirror.joined(con, 500, "mic_news")
    assert mirror.to_join(con) == [] and mirror.last(con, 500) == 0
    png = io.BytesIO(); Image.new("RGB", (64, 48), "red").save(png, "PNG")
    pic = media.save(png.getvalue(), tmp_path)
    outbox = con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0]

    # a post: the first line its title
    p1 = mirror.take(con, 500, mirror.Msg(id=10, date=logic.now() - 60, text="Stand-up night on Friday\nSign up by Thursday.\nFree entry.",
                                           photo=pic, views=120, reactions=[("\U0001F525", 7), ("\u2764", 3), ("\u2605", 0)]))
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[p1]
    assert (got["title"], got["body"]) == ("Stand-up night on Friday", "Sign up by Thursday.\nFree entry.")
    assert got["photo"] and got["tg"] == {"url": "https://t.me/mic_news/10", "views": 120, "reactions": [["\U0001F525", 7], ["\u2764", 3]], "media": None}
    assert got["commentsOn"] is False and got["canEdit"] is False
    assert c.get("/api/posts?scope=org:1", headers=tma(80)).json()[0]["canEdit"] is False   # not even its President: Telegram's
    assert c.put(f"/api/posts/{p1}/reactions/fire", headers=tma(81)).status_code == 400
    assert c.patch(f"/api/posts/{p1}", headers=tma(80), json={"title": "Changed here"}).status_code == 400
    assert c.patch(f"/api/posts/{p1}", headers=tma(80), json={"pinned": True}).json()["pinned"] is True  # a pin is the club's own
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == outbox                      # nobody notified

    # an edit, and the counts later
    assert mirror.take(con, 500, mirror.Msg(id=10, date=0, text="Stand-up night moved to Saturday", views=300, reactions=[("\U0001F525", 9)])) == p1
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[p1]
    assert (got["title"], got["body"], got["tg"]["views"], got["tg"]["reactions"]) == ("Stand-up night moved to Saturday", "", 300, [["\U0001F525", 9]])
    assert got["editedAt"] and got["photo"]                                                             # the photo stays

    # an album: three messages, one post; its caption on the second; a video only a link
    a = [mirror.Msg(id=20, date=logic.now(), grouped=77, photo=pic), mirror.Msg(id=21, date=logic.now(), grouped=77, text="Photos from the night"),
         mirror.Msg(id=22, date=logic.now(), grouped=77, media="video")]
    (ap,) = {mirror.take(con, 500, m) for m in a}
    album = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[ap]
    assert (album["title"], album["tg"]["url"], album["tg"]["media"], album["editedAt"]) == ("Photos from the night", "https://t.me/mic_news/20", "video", None)
    assert album["photo"]
    assert mirror.needs_photo(con, 500, 23, 77) is False and mirror.needs_photo(con, 500, 30, None) is True
    long = mirror.take(con, 500, mirror.Msg(id=30, date=logic.now(), text="word " * 60))
    lp = con.execute("SELECT title, body FROM posts WHERE id = ?", (long,)).fetchone()
    assert len(lp["title"]) <= 120 and lp["title"].endswith("\u2026") and lp["body"] == ("word " * 60).strip()   # nothing lost
    assert mirror.last(con, 500) == 30 and sorted(mirror.recent(con, 500)) == [10, 20, 21, 22, 30]

    # deletions: an album's post goes when all its messages went
    assert mirror.gone(con, 500, [20, 21]) == [] and mirror.gone(con, 500, [22]) == [album["id"]]
    assert album["id"] not in [x["id"] for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()]
    assert mirror.take(con, 500, mirror.Msg(id=22, date=0, text="back?")) != album["id"]                  # a deleted post isn't revived

    # off in Studio: no more posts, the userbot leaves; the posts stay
    assert c.put("/api/orgs/1/chats/1/mirror", headers=tma(81), json={"on": False}).status_code == 403    # not Ali's club
    studio = c.put("/api/orgs/1/chats/1/mirror", headers=tma(80), json={"on": False}).json()
    assert studio[0]["mirror"] is False and mirror.wanted(con) == {} and mirror.to_leave(con) == [(500, "mic_news")]
    assert mirror.take(con, 500, mirror.Msg(id=40, date=logic.now(), text="Unseen")) is None
    assert p1 in [x["id"] for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()]
    mirror.left(con, 500)
    # another main channel: that one is joined next
    c.put("/api/orgs/1/chats/1/mirror", headers=tma(80), json={"on": True})
    con.execute("INSERT INTO chats (id, title, kind, url, created_at, status, org_id) VALUES (3, 'Mic Live', 'channel', 'https://t.me/mic_live', 0, 'org', 1)")
    c.put("/api/orgs/1/chats/3/main", headers=tma(80))
    assert mirror.to_join(con) == ["mic_live"]


def test_userbot_reads_telethon_messages(env):
    """userbot.Mirror with Telethon-shaped messages (a fake client): a photo is downloaded once and copied, a video and
    a file are named, Telegram's reactions read (a custom emoji as a star), service messages and anything from a chat
    that isn't mirrored dropped unread (a group's message never reaches the database), a saved photo nobody uses removed."""
    import datetime
    import io
    from PIL import Image
    from types import SimpleNamespace as NS
    from kbtu import mirror, userbot
    c, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic News', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    png = io.BytesIO(); Image.new("RGB", (40, 30), "blue").save(png, "PNG")
    downloads = []

    class Client:
        async def download_media(self, m, kind):
            downloads.append(m.id)
            return png.getvalue()

    def msg(i, chan=500, text="", photo=None, video=None, document=None, grouped=None, reactions=None, action=None):
        return NS(id=i, peer_id=NS(channel_id=chan) if chan else NS(user_id=5), action=action, message=text, grouped_id=grouped,
                  date=datetime.datetime.now(datetime.timezone.utc), photo=photo, video=video, gif=None, video_note=None,
                  media=photo or video or document, web_preview=None, views=42, reactions=reactions)
    work = userbot.Mirror(cfg, Client(), con)
    run = lambda m: asyncio.run(work.guard(work.post(m)))  # noqa: E731
    likes = NS(results=[NS(reaction=NS(emoticon="\U0001F44D"), count=5), NS(reaction=NS(document_id=1), count=2)])
    run(msg(1, text="Open mic tonight", photo=object(), grouped=9, reactions=likes))
    run(msg(2, photo=object(), grouped=9))                    # the album's second photo: the post has one, not downloaded
    run(msg(3, text="Teaser", video=object()))
    run(msg(4, text="Rules", document=object()))
    run(msg(5, text="pinned a message", action=object()))     # a service message
    run(msg(6, chan=777, text="a group's chatter"))           # not a mirrored chat
    run(msg(7, chan=None, text="a private message"))
    got = {r["title"]: r for r in con.execute("SELECT * FROM posts").fetchall()}
    assert sorted(got) == ["Open mic tonight", "Rules", "Teaser"] and downloads == [1]
    assert got["Open mic tonight"]["photo_file_id"] and json.loads(got["Open mic tonight"]["tg_reactions"]) == [["\U0001F44D", 5], ["\u2605", 2]]
    assert (got["Teaser"]["tg_media"], got["Rules"]["tg_media"], got["Teaser"]["tg_views"]) == ("video", "file", 42)
    assert con.execute("SELECT COUNT(*) FROM tg_post_msgs").fetchone()[0] == 4


def test_mirror_languages(env):
    """A school's channel in three languages: the same announcement posted in kk, ru and en within half an
    hour is one post with the other two as its translations (an album whose caption comes after its photos too); two
    posts in one language stay two; a translation's edit and deletion touch only its language. A one-language post takes
    the translations the channel wrote in its comments; only without any, after 2 h, our AI, and the channel's own
    replace it later."""
    from kbtu import mirror
    c, cfg = env
    login(c, 80, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('KBTU | SITE', 'channel', 'https://t.me/kbtusite', 0, 'org', 1, 1)")
    mirror.joined(con, 700, "kbtusite")
    t0 = logic.now() - 5 * 3600
    kk = "\u0414\u04d9\u0440\u0456\u0441 \u0443\u0430\u049b\u044b\u0442\u044b \u04e9\u0437\u0433\u0435\u0440\u0434\u0456\n\u0421\u04d9\u0440\u0441\u0435\u043d\u0431\u0456 \u043a\u04af\u043d\u0456"  # Kazakh (letters Russian lacks)
    ru = "\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c\n\u0412 \u0441\u0440\u0435\u0434\u0443"
    pid = mirror.take(con, 700, mirror.Msg(id=10, date=t0, text=kk, views=50))
    assert mirror.take(con, 700, mirror.Msg(id=11, date=t0 + 60, text=ru, views=7)) == pid
    assert mirror.take(con, 700, mirror.Msg(id=12, date=t0 + 120, text="Timetable changed\nOn Wednesday")) == pid
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(80)).json()}
    assert list(got) == [pid] and got[pid]["title"].startswith("\u0414\u04d9\u0440\u0456\u0441") and got[pid]["tg"]["views"] == 50  # the first message's counts
    assert got[pid]["i18n"] == {"ru": {"title": ru.split("\n")[0], "body": ru.split("\n")[1]}, "en": {"title": "Timetable changed", "body": "On Wednesday"}}
    two = mirror.take(con, 700, mirror.Msg(id=13, date=t0 + 180, text="Another announcement"))    # English again: another post
    late = mirror.take(con, 700, mirror.Msg(id=14, date=t0 + 7200, text=ru))                     # two hours later: another post
    assert len({pid, two, late}) == 3

    # a translation's edit and deletion touch only its language; the post's own edit stays the post's
    mirror.take(con, 700, mirror.Msg(id=12, date=0, text="Timetable changed again\nOn Thursday"))
    p = con.execute("SELECT title, i18n FROM posts WHERE id = ?", (pid,)).fetchone()
    assert p["title"].startswith("\u0414\u04d9\u0440\u0456\u0441") and json.loads(p["i18n"])["en"]["title"] == "Timetable changed again"
    assert mirror.gone(con, 700, [11]) == []
    assert set(json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (pid,)).fetchone()[0])) == {"en"}

    # an album whose caption comes after its photos, in another language than a post a minute before
    first = mirror.take(con, 700, mirror.Msg(id=20, date=t0 + 4000, text=kk + " 2"))
    temp = mirror.take(con, 700, mirror.Msg(id=21, date=t0 + 4020, grouped=5))
    assert temp != first
    assert mirror.take(con, 700, mirror.Msg(id=22, date=t0 + 4020, grouped=5, text="Photos from the day")) == first
    assert con.execute("SELECT 1 FROM posts WHERE id = ?", (temp,)).fetchone() is None
    assert json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (first,)).fetchone()[0])["en"]["title"] == "Photos from the day"

    # a photo on its own, then the same text in kk, ru and en (SITE): one post, all three its languages
    pic = mirror.take(con, 700, mirror.Msg(id=40, date=t0 + 5000, media="video"))
    for i, x in enumerate((kk, ru, "Football, but agentic\nOn Friday")):
        assert mirror.take(con, 700, mirror.Msg(id=41 + i, date=t0 + 5000, text=x)) == pic
    assert set(json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (pic,)).fetchone()[0])) == {"kk", "ru", "en"}

    # the channel's own comments: the post `two` (English only) gets kk and ru from them, nothing else
    assert 13 in mirror.to_comment(con, 700) and 10 in mirror.to_comment(con, 700)              # pid still lacks ru
    assert mirror.comments(con, 700, 13, [kk, ru, "Another one in English"]) == 2
    tw = con.execute("SELECT i18n, tr_by FROM posts WHERE id = ?", (two,)).fetchone()
    assert set(json.loads(tw["i18n"])) == {"kk", "ru"} and tw["tr_by"] == "tg" and 13 not in mirror.to_comment(con, 700)

    # our AI only for a post with none of its own, after 2 h; the channel's comments replace it
    assert logic.ai_next(con) == ("post", late, {"title": ru.split("\n")[0], "body": ru.split("\n")[1]})
    fresh = mirror.take(con, 700, mirror.Msg(id=30, date=logic.now() - 600, text="Just now"))
    logic.ai_save(con, "post", late, {"title": ru.split("\n")[0], "body": ru.split("\n")[1]}, "ru",
                  {"kk": {"title": "k", "body": "kb"}, "en": {"title": "e", "body": "eb"}})
    assert con.execute("SELECT tr_by FROM posts WHERE id = ?", (late,)).fetchone()[0] == "ai"
    assert logic.ai_next(con) is None                                                             # the fresh one waits its 2 h
    mirror.comments(con, 700, 14, ["Schedule changed, official"])
    lt = con.execute("SELECT i18n, tr_by FROM posts WHERE id = ?", (late,)).fetchone()
    assert json.loads(lt["i18n"]) == {"en": {"title": "Schedule changed, official", "body": ""}} and lt["tr_by"] == "tg"
    assert fresh


def test_userbot_reads_only_the_channels_comments(env):
    """userbot.Mirror.translations: the replies under a post are read in memory and only those sent as the channel itself
    kept; a student's comment never reaches the database."""
    import datetime
    from types import SimpleNamespace as NS
    from telethon.tl.types import PeerChannel, PeerUser
    from kbtu import mirror, userbot
    c, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('KBTU | SITE', 'channel', 'https://t.me/kbtusite', 0, 'org', 1, 1)")
    mirror.joined(con, 700, "kbtusite")
    mirror.take(con, 700, mirror.Msg(id=10, date=logic.now() - 3600, text="Open day on Saturday"))
    ru = "\u0414\u0435\u043d\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0445 \u0434\u0432\u0435\u0440\u0435\u0439"
    secret = "\u043c\u043e\u0439 \u043d\u043e\u043c\u0435\u0440 +7 700 000 0000"  # a student's comment in Russian

    class Client:
        def iter_messages(self, ent, reply_to=None, limit=None):
            assert reply_to == 10
            async def gen():
                for m in (NS(from_id=PeerUser(5), message=secret), NS(from_id=PeerChannel(700), message=ru), NS(from_id=PeerChannel(999), message="other channel")):
                    yield m
            return gen()
    work = userbot.Mirror(cfg, Client(), con)
    asyncio.run(work.translations(None, 700))
    p = con.execute("SELECT i18n FROM posts").fetchone()
    assert json.loads(p["i18n"]) == {"ru": {"title": ru, "body": ""}}
    dump = "\n".join(con.iterdump())
    assert "+7 700 000 0000" not in dump and "other channel" not in dump
    asyncio.run(work.translations(None, 700))                                                     # asked again within 2 h: no call


def test_userbot_off(env, caplog):
    """The userbot stays off, saying why in one line, while any of its three settings is missing (nothing else changes)."""
    import dataclasses
    import logging
    from kbtu import userbot
    c, cfg = env
    assert userbot.missing(cfg) == "no TG_API_ID / TG_API_HASH / TG_SESSION"
    assert userbot.missing(dataclasses.replace(cfg, tg_api_id="12", tg_api_hash="h")) == "no TG_API_ID / TG_API_HASH / TG_SESSION"
    assert userbot.missing(dataclasses.replace(cfg, tg_api_id="x", tg_api_hash="h", tg_session="s")) == "TG_API_ID is not a number"
    assert "tg_session" not in repr(dataclasses.replace(cfg, tg_session="secret")) and "secret" not in repr(dataclasses.replace(cfg, tg_session="secret"))
    with caplog.at_level(logging.WARNING, logger="kbtu.userbot"):
        asyncio.run(userbot.run(cfg))
    assert [r.getMessage() for r in caplog.records] == ["userbot: off (no TG_API_ID / TG_API_HASH / TG_SESSION)"]


def test_membership_oversee(env):
    """DMP is an org in Studio: a membership says whether I lead in an overseeing org, so Studio shows
    the registry with it picked; a plain member of DMP, or a club's Vice, doesn't get it."""
    c, cfg = env
    dana, ali = login(c, 90, "dana"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (1, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, dana["id"], "head"), (2, dana["id"], "vice"), (1, ali["id"], "member")])
    mine = {m["org"]["id"]: m["oversee"] for m in c.get("/api/me", headers=tma(90)).json()["memberships"]}
    assert mine == {1: True, 2: False} and c.get("/api/me", headers=tma(90)).json()["oversee"] is True
    assert [m["oversee"] for m in c.get("/api/me", headers=tma(91)).json()["memberships"]] == [False]


def test_roster_name_match():
    """PLAN 95's name check (made-up names): two words shared in any order and spelling, Cyrillic or Latin, Kazakh
    letters, a patronymic more; one shared word isn't enough."""
    from kbtu import roster
    erlan, nurlan = "\u0415\u0440\u043b\u0430\u043d", "\u041d\u0443\u0440\u043b\u0430\u043d\u043e\u0432"   # Yerlan Nurlanov in Russian
    assert roster.same_person("Nurlanov Yerlan Serikovich", erlan, nurlan)
    assert roster.same_person("Zhanna Ospanova", "Janna", "OSPANOVA") and roster.same_person("Akhmetov Daniyar", "Daniar", "Ahmetov")
    assert roster.same_person("\u049a\u0430\u0441\u044b\u043c \u0410\u043b\u0438", "Kasym", "Ali")                  # Kazakh Q
    assert not roster.same_person("Ivanov Petr", "Pavel", "Ivanov") and not roster.same_person(None, "A", "B")
    assert [roster.classify(p) for p in ("member", "President", "Vice president", "Head of SMM", "HR", "ex president")] == [
        ("member", None, None), ("president", None, None), ("vice", None, None), ("head", "Head of SMM", "SMM"), ("member", "HR", None),
        ("member", "ex president", None)]
    assert (roster.course_of("23BD", 2026), roster.course_of("3rd year"), roster.tg_of("@Some_User"), roster.tg_of("+77001234567")) == (4, 3, "some_user", None)


def test_roster_load_and_join(env):
    """PLAN 95 with made-up rows: the load is idempotent and makes missing clubs official; a student already in the app
    whose username and name match joins at once (role, position as the club role's name, department, city, year,
    phone) with a toast once; listed but not signed in with Microsoft: a welcome with the club and position only; the
    username but another name: asked without the phone or city, "Yes, it's me" goes to the President, who confirms."""
    from kbtu import roster
    c, cfg = env
    pres = login(c, 70, "pres")
    ali = login(c, 71, "ali")          # Ali Testov (login()'s made-up students)
    bek = login(c, 72, "bek")
    guest = c.get("/api/me", headers=tma(73, "Guest")).json()
    con = db.connect(cfg.db_path)
    U = {71: "Ali_T", 72: "bek_t", 73: "new_one"}   # their Telegram usernames, as Telegram signs them
    h = lambda uid: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": "X", "username": U[uid]}, BOT)}  # noqa: E731
    for uid in U:
        c.get("/api/me", headers=h(uid))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    row = lambda **k: {"sheet": "Open Mic sheet", "position": None, "title": None, "role": "member", "dept": None, "full_name": None, "school": "SITE",  # noqa: E731
                       "year": "2", "course": 2, "city": None, "phone": None, "tg": None, "email": None, **k}
    items = [row(full_name="Testov Ali Made", tg="ali_t", position="Head of SMM", title="Head of SMM", role="head", dept="SMM", city="Taraz", phone="8 701 000 00 00"),
             row(full_name="Someone Else", tg="bek_t", position="HR", title="HR", city="Aktau", phone="+77010000001"),
             row(full_name="Not Yet Here", tg="new_one", position="Vice president", role="vice", city="Shymkent"),
             {**row(full_name="New Club Person", tg="nobody_here"), "sheet": "Chess sheet"}]
    orgmap = {"Open Mic sheet": "mic", "Chess sheet": {"new": {"name": "Chess Club KBTU", "short": "CC", "emoji": "game_die_3d"}}}
    got = roster.load(con, items, orgmap)
    assert (got["added"], got["orgs_made"], got["joined"]) == (4, ["Chess Club KBTU"], 1)
    assert roster.load(con, items, orgmap)["added"] == 0                                   # again: nothing new
    assert con.execute("SELECT official FROM orgs WHERE name = 'Chess Club'").fetchone()[0] == 1          # no "KBTU" in a name

    me = c.get("/api/me", headers=h(71)).json()                                         # Ali: joined, told once
    assert [(m["org"]["slug"], m["role"], m["title"]) for m in me["memberships"]] == [("mic", "head", "Head of SMM")]
    assert me["roster"]["joined"][0]["title"] == "Head of SMM" and me["city"] == {"name": "Taraz", "hidden": False} and me["student"]["phone"] == "+77010000000"
    assert c.post("/api/roster/seen", headers=h(71)).status_code == 204 and c.get("/api/me", headers=h(71)).json()["roster"] is None
    assert con.execute("""SELECT g.name FROM member_tags t JOIN org_tags g ON g.id = t.tag_id WHERE t.user_id = ? AND g.department = 1""", (ali["id"],)).fetchone()[0] == "SMM"
    assert c.get(f"/api/users/{ali['id']}", headers=tma(70)).json()["city"] == "Taraz"
    c.patch("/api/me", headers=h(71), json={"cityHidden": True})
    assert c.get(f"/api/users/{ali['id']}", headers=tma(70)).json()["city"] is None
    assert c.patch("/api/me", headers=h(71), json={"city": None}).json()["city"] is None   # deleted

    welcome = c.get("/api/me", headers=h(73)).json()["roster"]                         # not signed in with Microsoft
    assert welcome == {"welcome": [{"org": welcome["welcome"][0]["org"], "title": None, "role": "vice"}]} and welcome["welcome"][0]["org"]["slug"] == "mic"

    ask = c.get("/api/me", headers=h(72)).json()["roster"]["ask"]                      # Bek: the username, another name
    assert len(ask) == 1 and set(ask[0]) == {"id", "org", "title", "role", "dept"} and not c.get("/api/me", headers=h(72)).json()["memberships"]
    assert c.post(f"/api/roster/{ask[0]['id']}/claim", headers=h(72)).status_code == 204
    assert c.get("/api/me", headers=h(72)).json()["roster"] is None                       # asked: waits for the President
    assert con.execute("SELECT kind FROM bot_outbox WHERE user_id = ? AND kind = 'roster_claim'", (pres["id"],)).fetchone()
    assert c.get("/api/roster/requests", headers=h(72)).json() == []                    # not Bek's to confirm
    req = c.get("/api/roster/requests", headers=tma(70)).json()
    assert [(r["sheetName"], r["name"]) for r in req] == [("Someone Else", "Bek Testov")]
    assert c.post(f"/api/roster/requests/{req[0]['id']}", headers=h(72), json={"ok": True}).status_code == 403
    assert c.post(f"/api/roster/requests/{req[0]['id']}", headers=tma(70), json={"ok": True}).status_code == 204
    me = c.get("/api/me", headers=h(72)).json()
    assert [(m["role"], m["title"]) for m in me["memberships"]] == [("member", "HR")] and me["city"]["name"] == "Aktau"


def test_roster_app_wins(env):
    """PLAN 95, students already in the app: what the app has wins. A membership held keeps its role (no
    promotion, no demotion); a missing one is added, a President on the sheet where the club has another in the app
    comes in as Vice (counted in the load's summary); department, title, city, phone and year fill only what's empty."""
    from kbtu import roster
    c, cfg = env
    pres, ali, bek = login(c, 60, "pres"), login(c, 61, "ali"), login(c, 62, "bek")
    con = db.connect(cfg.db_path)
    for uid, name in ((61, "ali_u"), (62, "bek_u")):
        c.get("/api/me", headers={"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": "X", "username": name}, BOT)})
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (ali["id"], "vice")])
    con.execute("UPDATE users SET city = 'Almaty' WHERE id = ?", (ali["id"],))
    con.execute("UPDATE students SET phone = '+77010000009', course = 3 WHERE user_id = ?", (ali["id"],))
    row = lambda **k: {"sheet": "S", "position": "President", "title": None, "role": "president", "dept": None, "school": None, "year": "1",  # noqa: E731
                       "course": 1, "city": "Taraz", "phone": "+77010000001", "email": None, **k}
    got = roster.load(con, [row(full_name="Ali Testov", tg="ali_u", dept="Board"), row(full_name="Bek Testov", tg="bek_u")], {"S": "mic"})
    assert (got["joined"], got["president_as_vice"]) == (2, 1)
    roles = dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())
    assert roles == {pres["id"]: "president", ali["id"]: "vice", bek["id"]: "vice"}            # one President: the app's
    a = con.execute("SELECT u.city, s.phone, s.course FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ?", (ali["id"],)).fetchone()
    assert tuple(a) == ("Almaty", "+77010000009", 3)                                           # ours stayed
    b = con.execute("SELECT u.city, s.phone FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ?", (bek["id"],)).fetchone()
    assert tuple(b) == ("Taraz", "+77010000001")                                               # empty ones filled
    assert con.execute("SELECT g.name FROM member_tags t JOIN org_tags g ON g.id = t.tag_id WHERE t.user_id = ?", (ali["id"],)).fetchone()[0] == "Board"


def test_bot_and_calendar_titles_translated(env):
    """PLAN 9's deferred part: the bot's messages and my calendar feed show an event's title in my language when it has
    a translation (made up here), else as typed."""
    c, cfg = env
    pres, ali = login(c, 92, "pres"), login(c, 93, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    ru = "\u041d\u043e\u0447\u044c \u043d\u0430\u0441\u0442\u043e\u043b\u043e\u043a"  # "Board games night" in Russian
    i18n = json.dumps({"en": {"title": "Board games night", "description": ""}, "kk": {"title": "Kk title", "description": ""}})
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at, i18n, lang)
        VALUES (1, 1, 'published', ?, '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0, ?, 'ru')""", (ru, int(time.time()) + 86400, pres["id"], i18n))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'TABCDEF', 0, 0)", (ali["id"],))
    logic.notify(con, ali["id"], "rate", "rate:1")
    ping = lambda lang: con.execute("SELECT b.*, ? AS lang FROM bot_outbox b WHERE kind = 'rate'", (lang,)).fetchone()  # noqa: E731
    assert "Board games night" in bot._render(con, ping("en"))[0] and ru in bot._render(con, ping("ru"))[0]
    con.execute("UPDATE users SET lang = 'en' WHERE id = ?", (ali["id"],))
    token = c.post("/api/me/calendar", headers=tma(93, "Ali")).json()["page"].rsplit("/", 1)[1]
    assert "SUMMARY:Board games night" in c.get(f"/cal/{token}.ics").text
    con.execute("UPDATE users SET lang = 'ru' WHERE id = ?", (ali["id"],))
    assert ru in c.get(f"/cal/{token}.ics").text                                               # the source language as typed


def test_phone_asked_at_signup(env):
    """PLAN 71: no up-front "My data" step. An event that needs a phone asks for it at sign-up and keeps it, so the next
    such sign-up is one tap; Settings changes or deletes it, and then it's asked again."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    eids = []
    for title in ("Trip", "Hike"):
        ev = c.post("/api/orgs/1/events", headers=tma(20), json={"title": title, "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                                  "color": "#3B6BFF", "needsPhone": True}).json()
        assert ev["needsPhone"] is True
        c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
        eids.append(ev["id"])
    go = lambda eid, **b: c.post(f"/api/events/{eid}/registration", headers=tma(10), json=b)  # noqa: E731
    assert ali["student"]["phone"] is None
    r = go(eids[0])                                                       # none kept: asked, no seat taken
    assert r.status_code == 400 and r.json()["message"] == "phone" and c.get(f"/api/events/{eids[0]}", headers=tma(10)).json()["my"] is None
    assert go(eids[0], phone="12345").json()["message"] == "phone"
    assert go(eids[0], phone="8 (701) 234-56-78").json()["my"]["status"] == "going"
    assert c.get("/api/me", headers=tma(10)).json()["student"]["phone"] == "+77012345678"
    assert go(eids[1]).json()["my"]["status"] == "going"                 # kept: one tap
    # a club whose event never asked doesn't get the kept phone in its guest list
    plain = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Talk", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{plain['id']}/publish", headers=tma(20))
    go(plain["id"])
    v = logic.Viewer(pres["id"], "user", True)
    assert [r["phone"] for r in logic.attendees_export(con, v, plain["id"])[1]] == [None]
    assert [r["phone"] for r in logic.attendees_export(con, v, eids[0])[1]] == ["+77012345678"]
    assert c.patch("/api/me", headers=tma(10), json={"phone": "nope"}).status_code == 400
    assert c.patch("/api/me", headers=tma(10), json={"phone": "+7 702 000 00 00"}).json()["student"]["phone"] == "+77020000000"
    assert c.patch("/api/me", headers=tma(10), json={"phone": None}).json()["student"]["phone"] is None
    c.delete(f"/api/events/{eids[1]}/registration", headers=tma(10))
    assert go(eids[1]).json()["message"] == "phone"                      # deleted: asked again


def test_student_government_mark(env):
    """The Student Government: a mark and first in the clubs list, no rights beyond any club's."""
    c, cfg = env
    login(c, 31, "student")
    h = tma(31)
    con = db.connect(cfg.db_path)
    big = logic.create_org(con, None, "Chess Club", "CH", "trophy_3d", True, "chess")
    gov = logic.create_org(con, None, "Student Government", "SG", "trophy_3d", True, logic.GOV_SLUG)
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) SELECT id, ?, 0 FROM users", (big,))
    con.close()
    found = [o for o in c.get("/api/orgs", headers=h).json() if o["id"] in (big, gov)]
    assert [(o["id"], o.get("gov")) for o in found] == [(gov, True), (big, None)]   # first though followed less
    g = c.get(f"/api/orgs/{gov}", headers=h).json()
    assert g["gov"] is True and not g.get("canOversee") and g["myRole"] is None


def test_bot_binds_club_channel(env, monkeypatch):
    """A chat picked in the bot by a club's President or Vice: "is this your club's?"; yes puts it on
    the club's page (the first public channel its main one) with a link into Studio, no sends it to the catalog. A plain
    member is never asked; someone else's tap does nothing."""
    from kbtu import media
    c, cfg = env
    vice, other, ali = login(c, 40, "vice"), login(c, 41, "other"), login(c, 42, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, vice["id"], "vice"), (1, ali["id"], "member"), (2, other["id"], "vice")])
    pages = {"https://t.me/mic_news": {"title": "Open Mic News", "members": 900, "channel": True}}
    async def peek(http, url):
        return {"ok": True, "image": None, **pages.get(url, {"title": "Some Chat", "members": 10, "channel": False})}
    monkeypatch.setattr(media, "chat_peek", peek)
    sent = []
    async def tg(cfg, http, method, body, files=None):
        sent.append((method, body))
    monkeypatch.setattr(bot, "_tg", tg)
    class Http:
        async def post(self, *a, **k):
            return None
    def pick(tg_id, n, **m):  # a message to the bot, each a while after the last (one t.me look per 10 s)
        con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
        return {"message_id": n, "from": {"id": tg_id}, "chat": {"id": tg_id, "type": "private"}, "date": logic.now(), **m}
    run = lambda coro: asyncio.run(coro)  # noqa: E731

    news = pick(40, 7, chat_shared={"request_id": 1, "chat_id": -100777, "username": "Mic_News", "title": "Open Mic News"})
    q = run(bot._suggest(cfg, None, con, news))
    assert q["text"] == texts.bot_message("ru", "chat_whose_one", club="Open Mic")[0] and q["reply_parameters"] == {"message_id": 7}
    assert [[b["callback_data"] for b in row] for row in q["reply_markup"]["inline_keyboard"]] == [["oc:1"], ["oc:0"]]
    a = run(bot._bound(cfg, None, con, news, 1))
    assert a["text"] == texts.bot_message("ru", "chat_bound", club="Open Mic")[0]
    assert a["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("?startapp=ce_1")
    assert [tuple(r) for r in con.execute("SELECT url, org_id, main, status FROM chats")] == [("https://t.me/mic_news", 1, 1, "org")]
    assert run(bot._bound(cfg, None, con, news, 2))["text"] == texts.bot_message("ru", "chat_bind_no")[0]       # not Chess's Vice
    taken = pick(41, 8, text="@mic_news")
    assert run(bot._bound(cfg, None, con, taken, 2))["text"] == texts.bot_message("ru", "chat_bind_taken")[0]    # Open Mic's already

    talk = pick(40, 9, text="@mic_talk")
    assert run(bot._suggest(cfg, None, con, talk))["reply_markup"]["inline_keyboard"][-1][0]["callback_data"] == "oc:0"
    no = run(bot._bound(cfg, None, con, talk, 0))                                     # "No, just the catalog"
    assert no["text"] == texts.bot_message("ru", "chat_sent", title="Some Chat")[0] and no["reply_markup"] == {"inline_keyboard": []}
    assert tuple(con.execute("SELECT org_id, status FROM chats WHERE url = 'https://t.me/mic_talk'").fetchone()) == (None, "pending")
    assert run(bot._suggest(cfg, None, con, pick(42, 10, text="@ali_chat")))["text"].startswith("✅")             # a member: not asked

    # the tap: the question turns into the answer; someone else's tap on it does nothing
    tap = lambda who, data: {"id": "q", "from": {"id": who}, "data": data, "message": {"message_id": 11, "reply_to_message": pick(40, 12, text="@mic_more")}}  # noqa: E731
    run(bot._tapped(cfg, Http(), con, tap(41, "oc:1")))
    assert sent == []
    run(bot._tapped(cfg, Http(), con, tap(40, "oc:1")))
    assert [(m, b["message_id"], b["text"]) for m, b in sent] == [("editMessageText", 11, texts.bot_message("ru", "chat_bound", club="Open Mic")[0])]
    assert tuple(con.execute("SELECT org_id FROM chats WHERE url = 'https://t.me/mic_more'").fetchone()) == (1,)


def test_org_names(env):
    """Org names, one style: "KBTU" off either end on create and rename, an acronym the name carried
    goes to the abbr (in brackets, or before a dash), else the initials without "KBTU"."""
    import dataclasses
    for typed, name, abbr in [("KBTU Open Mic", "Open Mic", "OM"), ("Debate Club | kbtu", "Debate Club", "DC"),
                              ("IEEE KBTU Chapter", "IEEE", "IEEE"), ("AIESEC in KBTU", "AIESEC", "AIESEC"),
                              ("KBTU’s Music Club", "Music Club", "MC"), ("Society of Petroleum Engineers (SPE)", "Society of Petroleum Engineers", "SPE"),
                              ("SPE – Society of Petroleum Engineers", "Society of Petroleum Engineers", "SPE"),
                              ("Chess (beginners)", "Chess (beginners)", "CB"), ("Data KBTU Club", "Data KBTU Club", "DC"),
                              ("3D Printing (KBTU)", "3D Printing", "3P"), ("KBTU", "KBTU", "KBTU"),
                              ("\u041a\u0411\u0422\u0423 \u0414\u0435\u0431\u0430\u0442\u044b", "\u0414\u0435\u0431\u0430\u0442\u044b", "\u0414\u0415\u0411\u0410\u0422\u042b")]:
        assert (logic.org_name(typed)[0], logic.guess_abbr(typed)) == (name, abbr), typed
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}))))
    A = tma(20)
    c.get("/api/me", headers=A)
    club = c.post("/api/admin/orgs", headers=A, json={"name": "KBTU Society of Petroleum Engineers (SPE)", "short": "sp", "emoji": "trophy_3d"}).json()
    assert (club["name"], club["abbr"], club["slug"]) == ("Society of Petroleum Engineers", "SPE", "societyofpetroleumengi")
    login(c, 21, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT ?, id, 'president', 0 FROM users WHERE tg_id = 21", (club["id"],))
    con.close()
    def edit(body):
        assert c.patch(f"/api/orgs/{club['id']}", headers=tma(21), json=body).status_code == 200
        o = c.get(f"/api/orgs/{club['id']}", headers=tma(21)).json()
        return o["name"], o["abbr"]
    assert edit({"name": "Petroleum Club KBTU"}) == ("Petroleum Club", "SPE")             # renamed: the abbr it had stays
    assert edit({"name": "PC \u2013 Petroleum Club"}) == ("Petroleum Club", "PC")         # one the new name carries
    assert edit({"name": "KBTU Oil Club (OC)", "abbr": "Oil"}) == ("Oil Club", "Oil")     # an abbr sent with it wins


def test_portal_schedule(env, monkeypatch):
    """The week from the portal's schedule page saved on the phone (PLAN 26): a Web Archive or an .mht sent to the bot.
    A made-up page (tests/fixtures/portal_week.html): the phone's one-day layout ignored, the days by name, times as
    written or from the pixels, no label: over 1 h 40 a lecture. Only a page with the student's own name is taken; the
    file isn't kept and the student ID on it is never stored."""
    import plistlib
    from email.message import EmailMessage
    from kbtu import portal
    page = (Path(__file__).parent / "fixtures" / "portal_week.html").read_bytes()
    archive = plistlib.dumps({"WebMainResource": {"WebResourceData": page, "WebResourceTextEncodingName": "UTF-8",
                                                   "WebResourceMIMEType": "text/html", "WebResourceURL": "https://uninet.kbtu.kz/student/schedule"}},
                             fmt=plistlib.FMT_BINARY)
    mht = EmailMessage()
    mht["MIME-Version"] = "1.0"
    mht.make_mixed()
    mht.add_attachment(page, maintype="text", subtype="html", disposition="inline")  # Chrome: UTF-8, no charset
    mht.add_attachment(b"\x89PNG", maintype="image", subtype="png")
    mht = mht.as_bytes().replace(b"multipart/mixed", b"multipart/related")
    want = [(1, "10:00", "11:40", "Physical Education", "practice", "Gym", "Coach Example"),
            (1, "14:00", "15:00", "Imaginary Algebra", "practice", "251", "Teacher One"),
            (3, "12:00", "14:00", "History of Made-Up Things", "lecture", "388", "Teacher Two"),
            (3, "15:00", "17:00", "Unlabelled Long Course", "lecture", "305", "Teacher Three"),
            (6, "08:00", "09:00", "Unlabelled Short Course", "practice", None, "Teacher Four")]
    for data in (page, archive, mht):
        w = portal.parse(portal.page_html(data))
        assert w.name == "Testov A." and [(x.weekday, x.begins, x.ends, x.subject, x.kind, x.room, x.teacher) for x in w.lessons] == want
    for bad in (b"%PDF-1.4", b"bplist00junk", b"<html><body>Grades</body></html>"):
        with pytest.raises(portal.NotSchedule):
            portal.parse(portal.page_html(bad))
    same = portal.same_person
    assert same("Testov A.", "Ali", "Testov") and same("Ali Testov", "Ali", "Testov") and same("Ali T.", "Ali", "Testov")
    assert same("\u0422\u0435\u0441\u0442\u043e\u0432 \u0410.", "Ali", "Testov")         # a Cyrillic page, a Latin Microsoft name
    assert not same("Testov B.", "Ali", "Testov") and not same("Other A.", "Ali", "Testov") and not same(None, "Ali", "Testov")

    c, cfg = env
    login(c, 50, "ali")                                                  # Ali Testov
    login(c, 51, "bek")                                                  # Bek Testov: someone else
    files = {"F1": archive, "F2": mht, "F3": b"<html><body>no grid</body></html>"}
    class Resp:
        def __init__(self, body):
            self.body, self.content = body, body if isinstance(body, bytes) else b""
        def json(self):
            return self.body
    class Http:
        async def get(self, url, params=None):
            if url.endswith("/getFile"):
                return Resp({"ok": True, "result": {"file_path": params["file_id"]}})
            return Resp(files[url.rsplit("/", 1)[1]])
    con = db.connect(cfg.db_path)
    def send(tg, fid, name="Schedule.webarchive", size=7_000_000):
        msg = {"message_id": 1, "from": {"id": tg}, "chat": {"id": tg, "type": "private"}, "date": logic.now(),
               "document": {"file_id": fid, "file_name": name, "file_size": size}}
        assert bot._sched_file(msg)
        return asyncio.run(bot._schedule(cfg, Http(), con, msg))["text"]
    assert send(99, "F1") == texts.bot_message("ru", "sched_signin")[0]
    assert send(51, "F1") == texts.bot_message("ru", "sched_other")[0]            # Bek sends Ali's page: refused
    assert [x["subject"] for x in c.get("/api/me/schedule", headers=tma(51)).json()] == ["Calculus"]   # his own stays
    assert send(50, "F3", "page.html") == texts.bot_message("ru", "sched_not")[0]
    assert send(50, "F1", size=30_000_000) == texts.bot_message("ru", "sched_big")[0]
    assert send(50, "F1") == texts.bot_message("ru", "sched_ok", n=5)[0]
    got = c.get("/api/me/schedule", headers=tma(50)).json()
    assert [(x["weekday"], x["begins"], x["subject"], x["kind"]) for x in got] == [(w[0], w[1], w[3], w[4]) for w in want]
    assert send(50, "F2", "Schedule.mht") == texts.bot_message("ru", "sched_ok", n=5)[0]       # again from Android: replaced, not doubled
    assert len(c.get("/api/me/schedule", headers=tma(50)).json()) == 5
    dump = "\n".join(con.iterdump())
    assert "00X000000" not in dump and "Phone Only Course" not in dump           # the student ID is never kept; the phone layout ignored
    assert not bot._sched_file({"document": {"file_name": "receipt.pdf"}})


def test_bot_cards_for_helpers_and_invites(env):
    """The bot's cards about an event for one person (_render): a volunteer's yes/no, an invitation to a leaders'
    meeting; quiet once the decision changed or they signed up."""
    c, cfg = env
    pres, vol = login(c, 61, "pres"), login(c, 62, "vol")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    start = logic.now() + 3 * 86400
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Jam', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO volunteers (event_id, user_id, status, created_at) VALUES (1, ?, 'yes', 0)", (vol["id"],))
    card = lambda kind, ref: bot._render(con, {"kind": kind, "ref": ref, "lang": "ru", "user_id": vol["id"], "payload": None})  # noqa: E731
    fields = dict(org="Open Mic", title="Jam", when=texts.when(start, "ru"), place=texts.place_or_tba("305", "ru"))
    assert card("volunteer_yes", "vo:1:0") == (*texts.bot_message("ru", "volunteer_yes", **fields), "ev_1")
    assert card("volunteer_no", "vo:1:0") is None                                      # the decision says yes
    for kind in ("leaders_invite", "meeting_invite"):
        assert card(kind, "li:1") == (*texts.bot_message("ru", kind, **fields), "ev_1")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T62ABC', 0, 0)", (vol["id"],))
    assert card("leaders_invite", "li:1") is None                                      # answered by signing up


def test_chat_avatars_on_disk(env, monkeypatch):
    """A chat's avatar from its t.me page: saved with a suggestion (a broken picture: none), replaced by the daily look
    and by the bot's own card for a chat it sits in, the old file then off the disk."""
    import io
    from PIL import Image
    from kbtu import media
    c, cfg = env
    login(c, 63, "ali")
    con = db.connect(cfg.db_path)
    root = Path(cfg.db_path).resolve().parent / "media"
    def png(color):
        b = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(b, "PNG")
        return b.getvalue()
    image = {"https://t.me/jam_news": png((200, 40, 40)), "https://t.me/broken_pic": b"not a picture"}
    async def peek(http, url):
        return {"ok": True, "title": url.rsplit("/", 1)[1], "image": image.get(url), "members": 50, "about": None, "channel": True}
    monkeypatch.setattr(media, "chat_peek", peek)
    def suggest(handle):
        con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
        return asyncio.run(bot._suggest(cfg, None, con, {"chat": {"id": 63, "type": "private"}, "date": logic.now(), "text": handle}))["text"]
    on_disk = lambda p: (root / f"{p}.webp").exists()  # noqa: E731
    assert suggest("@jam_news").startswith("✅") and suggest("@broken_pic").startswith("✅")
    first = con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    assert first and on_disk(first)
    assert con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/broken_pic'").fetchone()[0] is None
    image["https://t.me/jam_news"] = png((40, 200, 40))                                 # a new avatar on t.me
    asyncio.run(bot.refresh_chats(cfg, None, con))
    second = con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    assert second != first and on_disk(second) and not on_disk(first)
    # once our bot sits in the chat, Telegram's own card: title, about, members, avatar
    cid = con.execute("SELECT id FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    class Resp:
        def __init__(self, body=None, content=b""):
            self.body, self.content, self.status_code = body, content, 200
        def json(self):
            return self.body
    class Http:
        async def post(self, url, json=None):
            method = url.rsplit("/", 1)[1]
            return Resp({"getChat": {"ok": True, "result": {"title": "Jam  News", "description": "Every Friday", "photo": {"big_file_id": "F"}}},
                         "getChatMemberCount": {"ok": True, "result": 77}, "getFile": {"ok": True, "result": {"file_path": "p/1.jpg", "file_size": 999}}}[method])
        async def get(self, url):
            return Resp(content=png((40, 40, 200)))
    assert asyncio.run(bot.chat_card(cfg, Http(), con, cid, -100123)) is True
    row = con.execute("SELECT title, about, members, photo FROM chats WHERE id = ?", (cid,)).fetchone()
    assert tuple(row)[:3] == ("Jam News", "Every Friday", 77) and row[3] not in (first, second) and on_disk(row[3]) and not on_disk(second)


def test_paths_no_test_ran(env):
    """What a trace of the whole suite showed no test running: a round's settings changed while it's live and an
    application taken back; a friend request taken back; a volunteer leaving; past events (a hidden club's left out);
    a club tag deleted; the roster's e-mails; a chat's t.me page read."""
    import httpx
    from kbtu import media, roster
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ann"), (22, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, ids[20], oid, "president", "test")
    P, A, B = tma(20), tma(21), tma(22)

    # a live round: its settings change, its questions stay once someone applied; an applicant withdraws; then it closes
    hr = c.post(f"/api/orgs/{oid}/tags", headers=P, json={"name": "HR", "color": "#2FBF71", "department": True}).json()["tags"][0]["id"]
    body = {"title": "Recruitment", "picks": 1, "closesAt": int(time.time()) + 7 * 86400, "departments": [{"tagId": hr}],
            "questions": [{"kind": "long", "text": "Why us?"}]}
    r = c.post(f"/api/orgs/{oid}/round", headers=P, json=body).json()
    q = str(r["questions"][0]["id"])
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=A, json={"departments": [hr], "answers": {q: "I play"}}).status_code == 200
    changed = c.patch(f"/api/rounds/{r['id']}", headers=P, json={**body, "title": "Recruitment 2026", "questions": [{"kind": "long", "text": "Other"}]}).json()
    assert changed["title"] == "Recruitment 2026" and [x["text"] for x in changed["questions"]] == ["Why us?"]  # answers still match
    assert c.patch(f"/api/rounds/{r['id']}", headers=A, json={"close": True}).status_code == 403
    assert c.delete(f"/api/rounds/{r['id']}/apply", headers=A).json()["mine"] is None                  # taken back: not mine any more
    assert con.execute("SELECT stage FROM round_apps WHERE user_id = ?", (ids[21],)).fetchone()[0] == "withdrawn"
    assert c.patch(f"/api/rounds/{r['id']}", headers=P, json={"close": True}).json()["open"] is False
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=B, json={"departments": [hr], "answers": {q: "x"}}).status_code == 409  # closed

    # a friend request taken back: nothing pending, and it can be asked again
    assert c.post("/api/friends/requests", headers=A, json={"userId": ids[22]}).json()["friendship"] == "requested"
    assert c.delete(f"/api/friends/requests/{ids[22]}", headers=A).status_code in (200, 204)
    assert not con.execute("SELECT 1 FROM friend_requests WHERE from_id = ? AND status = 'pending'", (ids[21],)).fetchone()

    # a volunteer leaves before anyone decided
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50, "volunteers": 2}
    e = c.post(f"/api/orgs/{oid}/events", headers=P, json=ev).json()
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=A, json={"note": "I can"}).status_code == 200
    c.delete(f"/api/events/{e['id']}/volunteer", headers=A)
    assert not con.execute("SELECT 1 FROM volunteers WHERE event_id = ? AND user_id = ?", (e["id"], ids[21])).fetchone()

    # past events: an ended one shows; a hidden club's doesn't
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, e["id"]))
    assert [x["id"] for x in c.get("/api/events/past", headers=B).json()] == [e["id"]]
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (oid,))
    assert c.get("/api/events/past", headers=B).json() == []
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (oid,))

    # a club tag deleted: gone from the team's setup and from whoever wore it
    tags = c.post(f"/api/orgs/{oid}/tags", headers=P, json={"name": "SMM", "color": "#18A9DB"}).json()["tags"]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, ids[22]))
    smm = next(t["id"] for t in tags if t["name"] == "SMM")
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (smm, ids[22]))
    assert c.delete(f"/api/orgs/{oid}/tags/{smm}", headers=A).status_code == 403
    assert [t["name"] for t in c.delete(f"/api/orgs/{oid}/tags/{smm}", headers=P).json()["tags"]] == ["HR"]
    assert not con.execute("SELECT 1 FROM member_tags WHERE user_id = ?", (ids[22],)).fetchone()

    # the roster's e-mails: lowercased, the obviously broken ones dropped
    assert [roster.email_of(x) for x in (" Ann@KBTU.kz ", "no-at.kz", "a@b", None, "x y@kbtu.kz")] == ["ann@kbtu.kz", None, None, None, None]

    # a chat's t.me page: title, about, members, channel or group, the avatar only from Telegram's file host
    page = ('<meta property="og:title" content="Chess &amp; Co"><meta property="og:description" content="Fridays at 6">'
            '<meta property="og:image" content="https://cdn4.telesco.pe/file/abc.jpg"><div class="tgme_page_extra">1 204 subscribers</div>')
    def handler(r):
        return httpx.Response(200, content=b"IMG") if "telesco.pe" in str(r.url) else httpx.Response(200, text=page)
    async def peek(text=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler if text is None else (lambda r: httpx.Response(200, text=text)))) as http:
            return await media.chat_peek(http, "https://t.me/chess_co")
    got = asyncio.run(peek())
    assert (got["ok"], got["title"], got["about"], got["members"], got["channel"], got["image"]) == (True, "Chess & Co", "Fridays at 6", 1204, True, b"IMG")
    stock = asyncio.run(peek('<meta property="og:title" content="Group"><meta property="og:description" content="You can view and join @g right away.">'
                             '<meta property="og:image" content="https://telegram.org/img/t_logo.png"><div class="tgme_page_extra">35 members</div>'))
    assert (stock["about"], stock["image"], stock["members"], stock["channel"]) == (None, None, 35, False)  # Telegram's stock line and logo


def test_forum_find_people(env, monkeypatch):
    """F1 find people (PLAN "F1 spec" + "Forum adversarial review"): the gate; the skills catalog; who is matched (open to
    projects, never the author, staff, DMP's people or guests); pings (top 5, 1 a day, 2 a week, project only, never
    twice); nobody's Telegram before Accept; blocks; expiry; a report hides only with 3 old accounts and the AI;
    deleting an account takes all of it."""
    import dataclasses
    from kbtu import ai
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    con = db.connect(cfg.db_path)
    L = lambda uid, name: logic.Viewer(login(c, uid, name)["id"], "user", True)  # noqa: E731
    mod = L(80, "mod")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod.id,))
    mod = logic.Viewer(mod.id, "moderator", True)
    M, S = tma(80), tma(81)
    stu = L(81, "stu")
    assert c.get("/api/forum/me", headers=S).status_code == 403                                     # students: not yet
    assert TestClient(server.create(cfg)).get("/api/forum/me", headers=M).status_code == 404         # the flag off: no forum
    # the catalog: normalised names, the same one found, close ones offered, the AI's no refused
    web = c.post("/api/forum/skills", headers=M, json={"name": "  WEB!! "}).json()["skill"]
    assert web["name"] == "web" and web["public"]
    assert [x["name"] for x in c.post("/api/forum/skills", headers=M, json={"name": "webb"}).json()["didYouMean"]] == ["web"]
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=False))
    assert c.post("/api/forum/skills", headers=M, json={"name": "nasty word"}).json()["message"] == "ai"
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=None))                    # no AI: made, but private
    figma = c.post("/api/forum/skills", headers=M, json={"name": "Figma"}).json()["skill"]
    assert not figma["public"] and "figma" not in [x["name"] for x in logic.skills(con, stu, "fig")]
    assert logic.set_my_forum(con, mod, {"skills": [web["id"], figma["id"]] * 3})["skills"] == [{"id": figma["id"], "name": "figma"}, {"id": web["id"], "name": "web"}]
    with pytest.raises(logic.ApiError):
        logic.set_my_forum(con, mod, {"skills": list(range(1, 7))})                                  # 6: more than 5

    # people: open ones with the skill; never the author, staff, DMP's people, guests or anyone not open
    people = {n: L(82 + i, n) for i, n in enumerate(("bob", "cat", "dmp", "eve", "fay", "gus", "hal", "ivy", "jon"))}
    for n, v in people.items():
        logic.set_my_forum(con, v, {"skills": [web["id"]], "open": n != "cat", "pings": True})
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (9, ?, 'member', 0)", (people["dmp"].id,))
    guest = c.get("/api/me", headers=tma(99, "Guest")).json()["id"]                                # Telegram only, no KBTU
    con.execute("UPDATE users SET open_projects = 1 WHERE id = ?", (guest,))
    con.execute("INSERT INTO user_skills (user_id, skill_id) VALUES (?, ?)", (guest, web["id"]))
    logic.set_my_forum(con, mod, {"open": True, "pings": True})
    found = {x["person"]["id"] for x in logic.search_people(con, stu, web["id"])}
    want = {people[n].id for n in ("bob", "eve", "fay", "gus", "hal", "ivy", "jon")}
    assert found == want                                                                             # not cat, dmp, the guest, the moderator

    # a project request pings the best 5 with pings on, once; the rest of the day nobody gets another
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=True))
    ask = c.post("/api/forum/asks", headers=M, json={"kind": "project", "title": "A site for the jam", "body": "React", "skills": [web["id"]]}).json()
    assert ask["matches"] == 7 and ask["status"] == "live"
    pinged = [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'ask_match'")]
    assert len(pinged) == 5 and set(pinged) <= want
    ask2 = c.post("/api/forum/asks", headers=M, json={"kind": "project", "title": "A logo too", "skills": [web["id"]]}).json()
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'ask_match' AND ref = ?", (f"am:{ask2['id']}",))} == want - set(pinged)
    con.execute("UPDATE ask_pings SET at = at - 2 * 86400")                                          # two days on: a second this week
    help_ = c.post("/api/forum/asks", headers=M, json={"kind": "help", "title": "Who has a charger?", "days": 1}).json()
    assert help_["skills"] == [] and not con.execute("SELECT 1 FROM bot_outbox WHERE ref = ?", (f"am:{help_['id']}",)).fetchone()  # help: no pings
    assert c.post("/api/forum/asks", headers=M, json={"kind": "help", "title": "Fourth"}).json()["message"] == "asks"  # 3 open at most
    logic.close_ask(con, mod, help_["id"], True)
    ask3 = logic.create_ask(con, mod, {"kind": "project", "title": "A third", "skills": [web["id"]]}, True)
    week = [r[0] for r in con.execute("SELECT user_id FROM ask_pings WHERE ask_id = ?", (ask3["id"],))]
    assert len(week) == 5
    con.execute("UPDATE ask_pings SET at = at - 3600 WHERE ask_id = ?", (ask3["id"],))
    logic.close_ask(con, mod, ask3["id"], False)
    ask4 = logic.create_ask(con, mod, {"kind": "project", "title": "A fourth", "skills": [web["id"]]}, True)
    assert not set(r[0] for r in con.execute("SELECT user_id FROM ask_pings WHERE ask_id = ?", (ask4["id"],))) & set(week)  # 2 this week
    logic.close_ask(con, mod, ask4["id"], None)
    held = logic.create_ask(con, mod, {"kind": "help", "title": "No AI answer"}, None)                 # no AI: a moderator first
    assert (held["status"], held["why"]) == ("held", "check") and all(a["id"] != held["id"] for a in logic.asks(con, stu))

    # an offer: nothing of either side's Telegram before Accept, then each gets the other's
    bob = people["bob"]
    con.execute("UPDATE users SET tg_username = 'bob_tg' WHERE id = ?", (bob.id,))
    con.execute("UPDATE users SET tg_username = 'mod_tg' WHERE id = ?", (mod.id,))
    assert logic.contact(con, bob, aid=ask["id"]) == {"status": "pending"}
    before = json.dumps([logic.contacts(con, mod), logic.contacts(con, bob), logic.asks(con, bob), logic.asks(con, mod), logic.search_people(con, stu, web["id"])])
    assert "bob_tg" not in before and "mod_tg" not in before and "telegram" not in before
    cid = con.execute("SELECT id FROM contacts").fetchone()[0]
    assert logic.decide_contact(con, bob.id, cid, True) is None                                      # only the asked side decides
    assert logic.decide_contact(con, mod.id, cid, True) == "accepted"
    assert logic.contacts(con, bob)[0]["telegram"] == "https://t.me/mod_tg" and logic.contacts(con, mod)[0]["telegram"] == "https://t.me/bob_tg"
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'contact_ok'")} == {bob.id, mod.id}

    # a block: no offers either way, out of each other's matches and lists
    eve = people["eve"]
    logic.block(con, eve, mod.id)
    with pytest.raises(logic.ApiError):
        logic.contact(con, eve, aid=ask["id"])
    assert all(a["id"] != ask["id"] for a in logic.asks(con, eve))
    assert eve.id not in {x["person"]["id"] for x in logic.ask_people(con, mod, ask["id"])}

    # expiry: gone from the lists
    con.execute("UPDATE asks SET expires_at = ? WHERE id = ?", (logic.now() - 1, ask2["id"]))
    assert ask2["id"] not in [a["id"] for a in logic.asks(con, bob)]

    # reports: three from accounts over two weeks old AND the AI agreeing hide it; younger accounts or no AI: it stays
    rep = lambda h: c.post("/api/reports", headers=h, json={"target": "ask", "id": ask["id"], "reason": "spam"}).status_code  # noqa: E731
    hs = [tma(82 + i) for i in (1, 3, 4)]                                                             # cat, eve, fay
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=False))
    assert all(rep(h) == 204 for h in hs)
    assert logic.one(con, "SELECT status FROM asks WHERE id = ?", ask["id"])[0] == "live"             # new accounts don't count
    con.execute("UPDATE users SET created_at = created_at - 15 * 86400")
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=None))
    assert rep(hs[0]) == 204 and logic.one(con, "SELECT status FROM asks WHERE id = ?", ask["id"])[0] == "live"  # no AI: a moderator's
    monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=False))
    assert rep(hs[1]) == 204
    assert tuple(con.execute("SELECT status, why FROM asks WHERE id = ?", (ask["id"],)).fetchone()) == ("hidden", "reports")
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'ask_hidden' AND user_id = ?", (mod.id,)).fetchone()  # the author is told

    # deleting an account takes its skills, requests, offers, blocks and pings
    delete_now(c, cfg, tma(85))                                                                       # eve
    for t, col in (("user_skills", "user_id"), ("blocks", "user_id"), ("ask_pings", "user_id"), ("contacts", "from_id")):
        assert not con.execute(f"SELECT 1 FROM {t} WHERE {col} = ?", (eve.id,)).fetchone(), t


def test_forum_bot_cards(env, monkeypatch):
    """The forum's cards in the bot: an offer with Accept / Decline (only the asked side's tap counts), a ping with a
    stop button that turns the pings off, and the keyboard the postman sends."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    a, b = (logic.Viewer(login(c, uid, n)["id"], "user", True) for uid, n in ((90, "ann"), (91, "ben")))
    web = con.execute("SELECT id FROM skills WHERE name = 'web'").fetchone()[0]
    logic.set_my_forum(con, b, {"skills": [web], "open": True, "pings": True})
    ask = logic.create_ask(con, a, {"kind": "project", "title": "A site", "skills": [web]}, True)
    row = lambda kind: {**dict(con.execute("SELECT * FROM bot_outbox WHERE kind = ?", (kind,)).fetchone()), "lang": "en"}  # noqa: E731
    text, _, keys = bot._render(con, row("ask_match"))
    assert text == texts.bot_message("en", "ask_match", skill="web", title="A site")[0]
    assert keys[0][0]["start"] == f"fa_{ask['id']}" and keys[1][0]["callback_data"] == "ps:0"
    logic.contact(con, b, aid=ask["id"])
    text, _, keys = bot._render(con, row("contact_ask"))
    cid = con.execute("SELECT id FROM contacts").fetchone()[0]
    assert "Ben" in text and "A site" in text and [k["callback_data"] for k in keys[0]] == [f"ct:{cid}:y", f"ct:{cid}:n"]
    sent = []
    async def tg(cfg, http, method, body, files=None):
        sent.append(body)
    monkeypatch.setattr(bot, "_tg", tg)
    class Http:
        async def post(self, *a, **k):
            return None
    tap = lambda who, data: asyncio.run(bot._tapped(cfg, Http(), con, {"id": "q", "from": {"id": who}, "data": data,  # noqa: E731
                                                                    "message": {"message_id": 5, "chat": {"id": who}}}))
    tap(91, f"ct:{cid}:y")                                                                            # Ben can't accept his own offer
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "pending" and sent[-1]["text"] == texts.bot_message("ru", "contact_gone")[0]
    tap(90, f"ct:{cid}:y")
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "accepted"
    assert bot._render(con, {**row("contact_ok"), "ref": f"co:{cid}:to"})[2][0][0]["url"].startswith("tg://user?id=")  # no username: by ID
    tap(91, "ps:0")
    assert con.execute("SELECT ask_pings FROM users WHERE id = ?", (b.id,)).fetchone()[0] == 0
    assert bot._render(con, row("ask_match")) is None                                                 # pings off: quiet


def test_forum_moderator_queue(env):
    """What waits for the forum's moderators: requests the AI didn't pass and skills not public yet; release puts a
    request live (and its pings out), hide takes it down and tells its author; only moderators see or act."""
    import dataclasses
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    con = db.connect(cfg.db_path)
    mod = logic.Viewer(login(c, 95, "mod")["id"], "moderator", True)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod.id,))
    stu = logic.Viewer(login(c, 96, "stu")["id"], "user", True)
    held = logic.create_ask(con, stu, {"kind": "help", "title": "Held one"}, None)
    other = logic.create_ask(con, stu, {"kind": "help", "title": "Flagged one"}, False)
    new = logic.add_skill(con, stu, "lockpicking")
    q = c.get("/api/forum/mod", headers=tma(95)).json()
    assert [a["id"] for a in q["held"]] == [held["id"], other["id"]] and [s["name"] for s in q["skills"]] == ["lockpicking"]
    assert c.get("/api/forum/mod", headers=tma(96)).status_code == 403
    with pytest.raises(logic.ApiError):
        logic.mod_queue(con, stu)
    assert c.post(f"/api/forum/asks/{held['id']}/release", headers=tma(95)).status_code == 200
    assert con.execute("SELECT status FROM asks WHERE id = ?", (held["id"],)).fetchone()[0] == "live"
    assert c.post(f"/api/forum/asks/{other['id']}/hide", headers=tma(95)).status_code == 204
    assert con.execute("SELECT status, why FROM asks WHERE id = ?", (other["id"],)).fetchone()[:] == ("hidden", "moderator")
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'ask_hidden' AND user_id = ?", (stu.id,)).fetchone()
    assert c.patch(f"/api/forum/skills/{new['id']}", headers=tma(95), json={"approve": True}).json()["public"] is True
    assert c.get("/api/forum/mod", headers=tma(95)).json() == {"held": [], "skills": []}
    # three reports from old accounts, no AI word: a moderator's day, counted from the third report
    t0 = int(time.time())
    for i, uid in enumerate((97, 98, 99)):
        rid = login(c, uid, f"r{uid}")["id"]
        con.execute("UPDATE users SET created_at = ? WHERE id = ?", (t0 - 30 * 86400, rid))
        con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, status, created_at) VALUES (?, 'ask', ?, 'spam', 'open', ?)",
                    (rid, held["id"], t0 - 3600 + i * 60))
        q = c.get("/api/forum/mod", headers=tma(95)).json()["held"]
        assert q == [] if i < 2 else [(a["id"], a["status"], a["dueAt"]) for a in q] == [(held["id"], "reported", t0 - 3600 + 120 + 86400)]
    # what the privacy policy promises: a request 30 days after it ran out, a ping's record after 30 days
    con.execute("UPDATE asks SET expires_at = ? WHERE id = ?", (t0 - 31 * 86400, held["id"]))
    con.execute("INSERT INTO ask_pings (ask_id, user_id, at) VALUES (?, ?, ?), (?, ?, ?)", (held["id"], mod.id, t0, other["id"], mod.id, t0 - 31 * 86400))
    logic.forum_sweep(con)
    assert [r[0] for r in con.execute("SELECT id FROM asks")] == [other["id"]] and not con.execute("SELECT 1 FROM ask_pings").fetchone()


def test_forum_policy_behind_the_flag(env):
    """The policy's forum part and its consent version count only with FORUM=1: off, the page has no section 11 and
    v3 is in force; on, the section shows, /api/me asks for v4, and only v4 is taken."""
    import dataclasses
    c, cfg = env
    login(c, 90, "stu")
    assert "11." not in c.get("/privacy?lang=en").text and c.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT
    on = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    page = on.get("/privacy?lang=en").text
    assert "11. The forum" in page and "Version of 26 October" in page and "Version of 23" not in page and "<!--" not in page
    assert on.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT_FORUM
    assert on.post("/api/me/consent", headers=tma(90), json={"version": logic.CONSENT}).status_code == 400
    assert on.post("/api/me/consent", headers=tma(90), json={"version": logic.CONSENT_FORUM}).json()["student"]["consent"] == logic.CONSENT_FORUM
    for lang in ("ru", "kk"):
        assert on.get(f"/privacy?lang={lang}").text.count("<h2>11.") == 1 and "<h2>11." not in c.get(f"/privacy?lang={lang}").text


def test_referrals(env):
    """Invite links (PLAN): r_<badge code>, never a user ID; the first link wins, only before the KBTU
    sign-in; it counts once the invitee is confirmed by Microsoft; "Recruiter" at 3; gone with the account."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann = login(c, 100, "ann")
    code = ann["referrals"]["code"]
    assert ann["referrals"] == {"count": 0, "code": code} and len(code) == 10
    other = login(c, 101, "ole")["referrals"]["code"]
    refer = lambda tg, cd: c.post("/api/referral", headers=tma(tg), json={"code": cd}).status_code  # noqa: E731
    assert refer(100, code) == 204 and con.execute("SELECT referred_by FROM users WHERE tg_id = 100").fetchone()[0] is None  # not myself
    assert refer(101, code) == 204 and con.execute("SELECT referred_by FROM users WHERE tg_id = 101").fetchone()[0] is None  # signed in already
    assert refer(102, "nope") == 400
    for tg in (102, 103, 104, 105):
        c.get("/api/me", headers=tma(tg))
        assert refer(tg, code) == 204
    assert refer(102, other) == 204                                                     # the first link wins
    assert con.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (ann["id"],)).fetchone()[0] == 4
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 0          # Telegram accounts alone count nothing
    def confirm(tg):  # typed in, then Microsoft (app.py's two steps)
        uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, manual, synced_at, verified_at)
            VALUES (?, ?, 'X', 'Testov', 1, '1', 0, 1, 0, 0)""", (uid, f"25B{tg:06d}"))
        logic.ms_link(con, uid, {"oid": f"o{tg}", "email": f"x{tg}@kbtu.kz", "first": "X", "last": "Testov"})
    for tg in (102, 103):
        confirm(tg)
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 2
    assert not con.execute("SELECT 1 FROM achievement_levels WHERE code = 'referral'").fetchone()
    confirm(104)
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'referral'", (ann["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:referral:1'", (ann["id"],)).fetchone()
    delete_now(c, cfg, tma(103))                                                         # one of them leaves: no longer counted
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 2


def test_forum_screen_munito_only(monkeypatch):
    """The forum's AI look goes to Munito's links only (privacy policy, section 11), however the chain is set: with
    Cloudflare, OpenRouter and Groq keys present and Munito busy, nobody else gets the text and a moderator decides."""
    import httpx
    from kbtu import ai, llm
    monkeypatch.setattr(llm, "_rest", {})
    cfg = config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=":memory:", web_dist=".", background=False, seed=False,
                        cf_account_id="acc", cf_ai_token="t", openrouter_key="o", groq_key="g", munito_keys=("m1", "m2"))
    hosts, answer = [], {"code": 200, "word": "OK"}
    def handler(r):
        hosts.append(r.url.host)
        if answer["code"] != 200:
            return httpx.Response(answer["code"])
        return httpx.Response(200, json={"choices": [{"message": {"content": answer["word"]}, "finish_reason": "stop"}]})
    async def look(text):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ai.screen(cfg, http, text)
    assert asyncio.run(look("Need a tripod")) is True and set(hosts) == {"api.eu.munito.ai"}
    answer["word"] = "FLAG"; assert asyncio.run(look("buy essays")) is False
    hosts.clear(); answer["code"] = 429
    assert asyncio.run(look("anything")) is None
    assert hosts and set(hosts) == {"api.eu.munito.ai"}   # both keys tried, then no one else
    llm._rest.clear(); hosts.clear(); answer.update(code=200, word="maybe")
    assert asyncio.run(look("anything")) is None and set(hosts) == {"api.eu.munito.ai"}   # nonsense: no other provider either


def test_forum_founder_only(env):
    """FORUM=founder: the Creator alone gets the forum; the staff get 403; the policy and consent stay as they are."""
    import dataclasses
    c, cfg = env
    login(c, 90, "stu")
    c.get("/api/me", headers=tma(91))
    c.get("/api/me", headers=tma(92))
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 91")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 92")
    on = TestClient(server.create(dataclasses.replace(cfg, forum_founder=True)))
    assert on.get("/api/forum/me", headers=tma(91)).status_code == 200
    assert on.get("/api/forum/me", headers=tma(92)).status_code == 403
    assert on.get("/api/forum/me", headers=tma(90)).status_code == 403
    assert on.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT and "11." not in on.get("/privacy?lang=en").text


def test_userpic_copy(env):
    """The Telegram photo is served from /media once the bot copied it; a new t.me photo goes back to t.me until its
    own copy, and the old copy leaves the disk."""
    import asyncio
    import io
    import httpx
    from PIL import Image
    from kbtu import bot
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    pic = lambda k: {"Authorization": "tma " + auth.sign_init_data({"id": 10, "first_name": "Ali", "photo_url": f"https://t.me/i/userpic/320/{k}.jpg"}, BOT)}
    url = "a"
    pics = {}
    for k, rgb in (("a", (200, 40, 40)), ("b", (40, 200, 40))):
        buf = io.BytesIO()
        Image.new("RGB", (320, 320), rgb).save(buf, "JPEG")
        pics[k] = buf.getvalue()

    async def round_():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, content=pics[r.url.path[-5]]))) as http:
            await bot._userpics(cfg, http, con)

    me = lambda: c.get("/api/me", headers=pic(url)).json()["avatar"]
    me()
    asyncio.run(round_())
    first = me()
    assert first.startswith("media/") and first.endswith(".t.webp")
    root = Path(cfg.db_path).resolve().parent
    assert (root / first).is_file()
    url = "b"
    assert me() == "https://t.me/i/userpic/320/b.jpg"
    asyncio.run(round_())
    assert me() not in (first, "https://t.me/i/userpic/320/b.jpg") and not (root / first).exists()


def _club_runs(c, con, uid: int, name: str, slug: str = "vol") -> int:
    """A club whose Head (uid) runs its events, so its check-in sessions too."""
    login(c, uid, name)
    oid = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES (?, 'club', ?, 'V', 'trophy_3d', 0)",
                      (slug, slug.title())).lastrowid
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)",
                (oid, c.get("/api/me", headers=tma(uid)).json()["id"]))
    return oid


def _paired(c, uid: int, sid: int | None = None) -> dict:
    """A laptop's /show paired by the organizer uid: its header for what to show."""
    scr = c.post("/api/screen/pair").json()
    assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"], "session": sid}).status_code == 200
    return {"X-Screen": scr["secret"]}


def _csv(c, uid: int, sid: int) -> str:
    return c.get(c.post(f"/api/screens/{sid}/csv", headers=tma(uid)).json()["url"]).text.lstrip("\ufeff")


def test_qr_checkin(env, monkeypatch):
    """The big screen's QR (checkin.py): paired from the organizer's phone, a scan before the sign-up waits and counts once the
    student signs up (ID prefilled from the organizers' list), a forged or stale QR is refused, the CSV has both."""
    from kbtu import checkin
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    sid = checkin.new(con, "Meeting", [{"email": "S_New@kbtu.kz", "name": "New Person", "studentId": "24B030001"},
                                       {"email": "s_gone@kbtu.kz", "name": "Gone Person"}], org)
    k = _paired(c, 9)                                                                       # Dana's only session
    assert c.get("/api/screen", headers={"X-Screen": "bad"}).status_code == 403
    assert c.get("/api/screen", headers=k).json()["param"] is None                          # not started: no QR
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    con.execute("UPDATE students SET verified_at = verified_at - 60")                     # Ann: a student well before Start
    con.execute("UPDATE qr_sessions SET started_at = started_at - 30")                    # and Start a while ago
    forged = p[:-1] + ("1" if p[-1] == "0" else "0")
    assert c.post("/api/checkin", headers=tma(1), json={"p": forged}).json()["message"] == "qr"   # forged
    _, s, slot, _ = p.split("_")
    old = f"ci_{s}_{int(slot) - 40}_{checkin._sig(cfg.token_key, f'ci.{s}.{int(slot) - 40}')}"
    assert c.post("/api/checkin", headers=tma(1), json={"p": old}).json()["message"] == "qr_old"  # 400 s ago
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]           # a student: at once
    assert not c.post("/api/checkin", headers=tma(2), json={"p": p}).json()["done"]       # not yet: waits
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]           # Ann again: still one mark
    assert not c.post("/api/checkin", headers=tma(2), json={"p": p}).json()["done"]
    st = c.get("/api/screen", headers=k).json()
    assert (st["done"], st["pending"], st["expected"]) == (1, 1, 2)
    uid = c.get("/api/me", headers=tma(2)).json()["id"]
    logic.ms_remember(con, uid, {"oid": "oid-2", "email": "s_new@kbtu.kz", "first": "New", "last": "Person", "employeeId": "", "profile": {}})
    assert c.get("/api/me", headers=tma(2)).json()["msPending"]["prefill"] == {"studentId": "24B030001"}
    r = c.post("/api/kbtu/manual", headers=tma(2), json={"studentId": "24B030001", "consentVersion": logic.CONSENT})
    assert r.status_code == 200, r.text
    assert c.get("/api/screen", headers=k).json()["done"] == 2
    c.post(f"/api/screens/{sid}/finish", headers=tma(9))
    assert c.post("/api/checkin", headers=tma(3), json={"p": p}).status_code == 409       # finished
    rows_ = _csv(c, 9, sid).splitlines()
    assert [r.split(",")[0] for r in rows_[1:]] == ["came (not on the list)", "came", "absent"]
    assert rows_[2].endswith(",B") and rows_[1].endswith(",A")
    con.close()


def test_qr_checkin_edges(env, monkeypatch):
    """The review's holes: a non-ASCII QR is a 400 (not a 500), Finish doesn't
    lose who scanned (30 min to sign in, Microsoft's path too), Start doesn't reopen, the CSV has no formulas and
    matches the list by student ID when the mail differs."""
    from kbtu import checkin
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    sid = checkin.new(con, "Initiation", [{"email": "ann.home@gmail.com", "name": "=HYPERLINK(1)", "studentId": "24Bann",
                                            "phone": "+7 (700) 000-00-00"}], _club_runs(c, con, 9, "dana"))
    k = _paired(c, 9)
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p[:-1] + "\u0436"}).status_code == 400
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    for u in (2, 4):
        assert not c.post("/api/checkin", headers=tma(u), json={"p": p}).json()["done"]  # scanned, not signed in yet
    c.post(f"/api/screens/{sid}/finish", headers=tma(9))
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"] is None    # finished stays finished
    assert c.post("/api/checkin", headers=tma(3), json={"p": p}).status_code == 409       # new after Finish: no
    import csv
    rows_ = list(csv.reader(_csv(c, 9, sid).splitlines()))
    assert [r[0] for r in rows_[1:]] == ["came", "scanned, not signed in", "scanned, not signed in"]   # by ID: not absent
    assert (rows_[1][1], rows_[1][6]) == ("'=HYPERLINK(1)", "'+7 (700) 000-00-00")      # no formulas in Excel
    assert c.post("/api/checkin", headers=tma(2), json={"p": p}).status_code == 200       # had a mark: may come back
    uid2, uid4 = (c.get("/api/me", headers=tma(u)).json()["id"] for u in (2, 4))
    logic.ms_remember(con, uid2, {"oid": "oid-2", "email": "two@kbtu.kz", "first": "Two", "last": "Person", "employeeId": "", "profile": {}})
    assert c.post("/api/kbtu/manual", headers=tma(2), json={"studentId": "24B030002", "consentVersion": logic.CONSENT}).status_code == 200
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B030004', 'Four', 'P', 1, ?, 0, 0, 0, 1)""", (uid4, logic.CONSENT))
    logic.ms_link(con, uid4, {"oid": "oid-4", "email": "four@kbtu.kz", "first": "Four", "last": "P"})  # the relink path
    st = c.get("/api/screen", headers=k).json()
    assert (st["done"], st["pending"]) == (3, 0)
    con.execute("UPDATE qr_sessions SET ended_at = ended_at - ? WHERE id = ?", (checkin.GRACE + 1, sid))
    assert c.post("/api/checkin", headers=tma(2), json={"p": p}).status_code == 409       # past the grace: closed
    con.close()


def test_screen_pairing(env, monkeypatch):
    """/show without a PIN (Oct 29 night): only a session's organizers bind a screen, a stranger's scan changes nothing,
    a paired screen can't be moved to another club's session, the screen never controls or downloads anything, the CSV
    link is the organizer's and short-lived, "disconnect" sends every screen back to pairing."""
    from kbtu import checkin
    c, cfg = env
    con = db.connect(cfg.db_path)
    vol, other = _club_runs(c, con, 9, "dana"), _club_runs(c, con, 8, "omar", "inc")
    login(c, 1, "ann")                                                                       # a student in the hall
    sid = checkin.new(con, "Initiation", [{"email": "x@kbtu.kz", "name": "X Person", "phone": "+7 (700) 000 00 00"}], vol)
    scr = c.post("/api/screen/pair").json()
    me = {"X-Screen": scr["secret"]}
    assert set(c.get("/api/screen", headers=me).json()) == {"code", "left"}                 # waiting: just its QR
    for uid in (1, 8, 3):                                                                    # a student, another club, a guest
        assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"]}).status_code == 403
        assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"], "session": sid}).status_code == 403
    assert "session" not in c.get("/api/screen", headers=me).json()                         # still Dana's to pair
    assert c.get("/api/screens", headers=tma(1)).json() == [] and c.get("/api/screens", headers=tma(8)).json() == []
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": scr["code"]}).json()["session"] == sid
    assert c.get("/api/screen", headers=me).json()["session"] == sid
    theirs = checkin.new(con, "Their party", [], other)
    assert c.post("/api/screens/bind", headers=tma(8), json={"code": scr["code"], "session": theirs}).status_code == 403  # not moved
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": scr["code"], "session": theirs}).json()["session"] == sid
    for act in ("start", "finish", "unpair", "csv"):                                         # nobody else runs it
        assert c.post(f"/api/screens/{sid}/{act}", headers=tma(1)).status_code == 403
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": c.get("/api/screen", headers=me).json()["param"]}).json()["done"]
    url = c.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]
    assert c.get(url.replace("k=", "k=0")).status_code == 403 and c.get(url).status_code == 200
    e = int(url.split("e=")[1].split("&")[0])
    monkeypatch.setattr(checkin, "now", lambda: e + 1)
    assert c.get(url).status_code == 403                                                     # the link is short-lived
    monkeypatch.undo()
    # a stale pairing QR (a photo of it) binds nothing
    old = c.post("/api/screen/pair").json()
    con.execute("UPDATE qr_screens SET created_at = created_at - ? WHERE code = ?", (checkin.PAIR_TTL + 1, old["code"]))
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": old["code"]}).status_code == 404
    # several open sessions: the app has to say which
    sid2 = checkin.new(con, "Second", [], vol)
    two = c.post("/api/screen/pair").json()
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": two["code"]}).json()["message"] == "pick"
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": two["code"], "session": sid2}).json()["session"] == sid2
    assert c.post(f"/api/screens/{sid}/unpair", headers=tma(9)).json()["screens"] == 0
    assert c.get("/api/screen", headers=me).status_code == 403                               # back to a new pairing QR
    assert c.get("/api/screen", headers={"X-Screen": two["secret"]}).json()["session"] == sid2
    monkeypatch.setattr(checkin, "PAIR_MAX", 1)
    c.post("/api/screen/pair")                                                               # one waiting: the cap
    assert c.post("/api/screen/pair").status_code == 429                                     # junk can't fill the table
    con.close()


def test_event_screen(env):
    """An event's own check-in screen (Oct 30): its organizers make it in the app (one per event); a counted scan is
    that event's check-in (a walk-in on a free public event, the ticket checked in, nothing on a paid one); a paid or
    partner's event keeps its door."""
    from kbtu import checkin
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    t0 = int(time.time())
    for eid, price, host in ((1, None, None), (2, 2000, None), (3, None, "Night Owls")):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, price, pay_to_name, pay_phone, guest_host,
            created_by, created_at, updated_at) VALUES (?, ?, 'published', 'Initiation', 'Hall', ?, 'trophy_3d', '#3B6BFF', ?, ?, ?, ?, 1, 0, 0)""",
                    (eid, org, t0 + 600, price, price and "Dana S.", price and "+77071234567", host))
    assert c.post("/api/events/1/screen", headers=tma(1)).status_code == 403                 # a guest at it, not its organizer
    for eid in (2, 3):
        assert c.post(f"/api/events/{eid}/screen", headers=tma(9)).status_code == 409        # tickets / no door
    s = c.post("/api/events/1/screen", headers=tma(9)).json()
    assert (s["event"], s["title"]) == (1, "Initiation") and c.post("/api/events/1/screen", headers=tma(9)).json()["session"] == s["session"]
    p = c.post(f"/api/screens/{s['session']}/start", headers=tma(9)).json()["param"]
    c.post("/api/events/1/registration", headers=tma(2), json={})                            # Bob has a ticket
    for u in (1, 2):
        assert c.post("/api/checkin", headers=tma(u), json={"p": p}).json()["done"]
    came = dict(con.execute("SELECT user_id, walk_in FROM registrations WHERE event_id = 1 AND checked_in_at IS NOT NULL").fetchall())
    assert came == {ann["id"]: 1, bob["id"]: 0}                                              # Ann walked in, Bob's ticket
    # a scan before the sign-up counts for the event once that person is a student
    assert not c.post("/api/checkin", headers=tma(4), json={"p": p}).json()["done"]
    uid = c.get("/api/me", headers=tma(4)).json()["id"]
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B4', 'Four', 'P', 1, ?, 0, 0, 0, 1)""", (uid, logic.CONSENT))
    with db.tx(con):
        checkin.became_student(con, uid)
    assert con.execute("SELECT checked_in_at IS NOT NULL FROM registrations WHERE event_id = 1 AND user_id = ?", (uid,)).fetchone()[0]
    con.close()

def test_student_forum(env, monkeypatch):
    """Oct 30: the student forum. Threads by topic; anonymous ones name nobody (not even moderators) and the admin's
    reveal is audited; the AI holds an anonymous text unless it says yes, a named one only on its no; replies number
    anonymous writers per thread; "I'm in" only on gathering topics; the author hears from the bot without the words;
    three reports from older accounts hide a thing; blocks and deletes; guests can't read."""
    from kbtu import ai
    c, cfg = env
    ann, bob, mod, boss = login(c, 1, "ann"), login(c, 2, "bob"), login(c, 3, "mod"), login(c, 4, "boss")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    ok = lambda r: monkeypatch.setattr(ai, "screen", lambda *a: asyncio.sleep(0, result=r))  # noqa: E731
    A, B, M, X = tma(1), tma(2), tma(3), tma(4)
    assert c.get("/api/threads", headers=tma(9)).status_code == 401                               # a guest: sign in first
    ok(None)                                                                                        # no AI answer
    named = c.post("/api/threads", headers=A, json={"topic": "go", "body": "KFC at 14:00, who's in?"}).json()
    assert named["status"] == "live" and named["author"]["id"] == ann["id"]                         # named: up
    secret = c.post("/api/threads", headers=A, json={"topic": "talk", "body": "Parents call every hour", "anon": True}).json()
    assert secret["status"] == "held" and secret["author"] is None                                  # anonymous: waits
    assert [t["id"] for t in c.get("/api/threads", headers=B).json()] == [named["id"]]
    ok(True)
    lend = c.post("/api/threads", headers=B, json={"topic": "thing", "body": "Need a Type-C charger for an hour", "anon": True}).json()
    assert lend["status"] == "live"
    for bad in ({"topic": "spam", "body": "hi there"}, {"topic": "talk", "body": "x"}, {"topic": "talk", "body": "y" * 1001},
                {"topic": "talk", "body": "ok ok", "anon": "yes"}):
        assert c.post("/api/threads", headers=A, json=bad).status_code == 400
    # the moderator sees the held one without its author, releases it
    q = c.get("/api/threads/mod", headers=M).json()
    assert [t["id"] for t in q["threads"]] == [secret["id"]] and q["threads"][0]["author"] is None
    assert c.get("/api/threads/mod", headers=A).status_code == 403
    assert c.post(f"/api/threads/mod/thread/{secret['id']}", headers=M, json={"ok": True}).status_code == 204
    feed = c.get("/api/threads", headers=B).json()
    assert {t["id"] for t in feed} == {named["id"], secret["id"], lend["id"]} and all("ann" not in json.dumps(t).lower() for t in feed if t["anon"])
    assert [t["id"] for t in c.get("/api/threads", headers=B, params={"topic": "thing"}).json()] == [lend["id"]]
    # the admin alone reveals, and it's logged
    assert c.post(f"/api/threads/reveal/thread/{secret['id']}", headers=M).status_code == 403
    assert c.post(f"/api/threads/reveal/thread/{secret['id']}", headers=X).json()["id"] == ann["id"]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'reveal_anon'").fetchone()[0] == 1
    assert c.post(f"/api/threads/reveal/thread/{named['id']}", headers=X).status_code == 404       # not anonymous: nothing to reveal
    # replies: anonymous writers numbered, the anonymous author is "the author"; the author hears once an hour
    c.post(f"/api/threads/{secret['id']}/replies", headers=B, json={"body": "Same here", "anon": True})
    c.post(f"/api/threads/{secret['id']}/replies", headers=M, json={"body": "Talk to them", "anon": True})
    c.post(f"/api/threads/{secret['id']}/replies", headers=B, json={"body": "Hang in there", "anon": True})
    th = c.post(f"/api/threads/{secret['id']}/replies", headers=A, json={"body": "Thanks all", "anon": True}).json()
    assert [(r.get("n"), r.get("op", False)) for r in th["thread"]] == [(1, False), (2, False), (1, False), (None, True)]
    assert all("person" not in r for r in th["thread"]) and th["replies"] == 4
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'thread_reply' AND user_id = ?", (ann["id"],)).fetchone()[0] == 1
    assert "Same here" not in bot._render(con, con.execute("""SELECT o.*, 'ru' AS lang FROM bot_outbox o WHERE kind = 'thread_reply'""").fetchone())[0]
    # "I'm in": gathering topics only, not my own; the author sees who and how to write
    assert c.put(f"/api/threads/{named['id']}/join", headers=B, json={"on": True}).json()["joins"] == 1
    assert c.put(f"/api/threads/{named['id']}/join", headers=A, json={"on": True}).status_code == 404
    assert c.put(f"/api/threads/{lend['id']}/join", headers=A, json={"on": True}).status_code == 404
    assert [p["id"] for p in c.get(f"/api/threads/{named['id']}/joiners", headers=A).json()] == [bob["id"]]
    assert c.get(f"/api/threads/{named['id']}/joiners", headers=B).status_code == 404
    # three reports from accounts older than two weeks hide it; the queue keeps the author's name out
    con.execute("UPDATE users SET created_at = 0")
    for h in (B, M, X):
        assert c.post("/api/reports", headers=h, json={"target": "thread", "id": named["id"], "reason": "spam"}).status_code in (200, 204)
    assert con.execute("SELECT status FROM threads WHERE id = ?", (named["id"],)).fetchone()[0] == "hidden"
    row = next(r for r in c.get("/api/admin/reports", headers=X).json() if r["target"] == "thread")
    assert row["where"] == {"kind": "thread", "id": named["id"]}
    c.post(f"/api/admin/reports/thread/{named['id']}", headers=X, json={"remove": False})              # left up: back
    assert con.execute("SELECT status FROM threads WHERE id = ?", (named["id"],)).fetchone()[0] == "live"
    # blocks hide each other's threads; deleting mine takes the replies along
    c.post("/api/forum/blocks", headers=B, json={"user": ann["id"], "on": True})
    assert [t["id"] for t in c.get("/api/threads", headers=B).json()] == [lend["id"]]               # Ann's, the anonymous one too
    assert c.delete(f"/api/threads/{secret['id']}", headers=B).status_code == 404
    assert c.delete(f"/api/threads/{secret['id']}", headers=A).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM thread_replies").fetchone()[0] == 0
    con.close()

def test_partner_events(env):
    """Oct 29: a partner's event a club posts. An official club's organizers or DMP name the outside host (no KBTU, DMP,
    council or school in it) with an https link; no price, no sign-up here, no door; followers aren't pinged; it stays
    out of DMP's registry numbers."""
    c, cfg = env
    pres, head, dmp, ali = login(c, 20, "pres"), login(c, 21, "head"), login(c, 80, "dmp"), login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'inc', 'club', 'Incubator', 'IN', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, pres["id"], "president"), (1, head["id"], "head"), (9, dmp["id"], "head"), (1, dmp["id"], "head")])
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (ali["id"],))
    start = int(time.time()) + 86400
    body = {"title": "Halloween", "place": "Bar", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}
    party = {**body, "guestHost": "  Night  Owls ", "externalUrl": "https://owls.kz/halloween"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=party).json()["message"] == "partner"   # a student initiative
    ev = c.post("/api/orgs/1/events", headers=tma(80), json=party).json()                              # DMP may
    assert (ev["guestHost"], ev["externalUrl"]) == ("Night Owls", "https://owls.kz/halloween")
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    for bad in ("KBTU Night", "\u041a\u0411\u0422\u0423 party", "dmp crew", "\u0414\u041c\u041f", "Student Council", "\u0421\u043e\u0432\u0435\u0442",
                "Business School", "x" * 61):
        assert c.post("/api/orgs/1/events", headers=tma(21), json={**party, "guestHost": bad}).json()["message"] == "partner"
    for url in (None, "http://owls.kz", "https://owls", "javascript:alert(1)"):
        assert c.post("/api/orgs/1/events", headers=tma(21), json={**party, "externalUrl": url}).status_code == 400
    priced = {**party, "price": 2000, "payToName": "Alikhan S.", "payPhone": "87071234567"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=priced).json()["message"] == "partner"   # no tickets, no money
    eid = c.post("/api/orgs/1/events", headers=tma(21), json=party).json()["id"]                        # a Head may
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**priced, "guestHost": "Night Owls"}).json()["message"] == "partner"
    assert c.post(f"/api/events/{eid}/publish", headers=tma(21)).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event'").fetchone()[0] == 0    # the feed only
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).status_code == 400         # signed up for on the host's site
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(21), json={"code": "X"}).status_code == 409  # no door
    assert any(e["id"] == eid and e["guestHost"] == "Night Owls" for e in c.get("/api/events", headers=tma(10)).json())
    # a club's own event with people signed up can't turn into a partner's
    own = c.post("/api/orgs/1/events", headers=tma(21), json=body).json()["id"]
    c.post(f"/api/events/{own}/publish", headers=tma(21))
    c.post(f"/api/events/{own}/registration", headers=tma(10), json={})
    assert c.patch(f"/api/events/{own}", headers=tma(21), json=party).json()["message"] == "taken"
    con.execute("UPDATE events SET starts_at = ? WHERE id IN (?, ?)", (int(time.time()), eid, own))  # this month, for the registry
    month = next(x for x in c.get("/api/registry/orgs", headers=tma(80, "Dmp")).json() if x["org"]["id"] == 1)["month"]
    assert (month["events"], month["registrations"]) == (1, 1)                                         # the club's own only
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "guestHost": None}).json()["externalUrl"] is None  # off: the link goes too
