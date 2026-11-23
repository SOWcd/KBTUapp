import asyncio
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from PIL import Image

from kbtu import bot, db, download, logic, receipt, texts
from test_core import env, login, tma  # noqa: F401


def test_download_checks_each_hop_and_pins_the_connection(monkeypatch):
    addresses = ["93.184.216.34"]
    async def resolve(host):
        return addresses
    monkeypatch.setattr(download, "_addresses", resolve)
    seen = []
    async def fetch(location, body=b"ok", cap=8):
        def handle(request):
            assert request.url.host == addresses[0]
            assert request.extensions["sni_hostname"] == request.headers["Host"]
            seen.append(request.headers["Host"])
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": location})
            async def chunks():
                for i in range(0, len(body), 2):
                    yield body[i:i + 2]
            return httpx.Response(200, content=chunks())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
            return await download.fetch(client, "https://t.me/start", download.TELEGRAM_PAGE + download.TELEGRAM_FILES, cap)

    assert asyncio.run(fetch("https://cdn4.telesco.pe/file/1")) == b"ok"
    assert seen == ["t.me", "cdn4.telesco.pe"]
    seen.clear()
    assert asyncio.run(fetch("https://outside.example/file")) is None and seen == ["t.me"]
    assert asyncio.run(fetch("/end", b"over budget", 2)) is None
    seen.clear()
    addresses.append("127.0.0.1")
    assert asyncio.run(fetch("/end")) is None and seen == []


@pytest.fixture
def organizer(env):
    c, cfg = env
    uid = login(c, 20, "pres")["id"]
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1,'it','club','IT','IT','laptop_3d',1,0)")
    con.execute("INSERT INTO org_members (org_id,user_id,role,joined_at) VALUES (1,?,'president',0)", (uid,))
    try:
        yield c, cfg, con, logic.Viewer(uid, "user", True)
    finally:
        con.close()


def test_receipt_rejections_share_one_budget_across_app_and_bot(organizer, monkeypatch):
    c, cfg, con, _ = organizer
    login(c, 10, "ali")
    event = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, "title": "Gala", "place": "Hall", "startsAt": logic.now() + 3600,
        "emoji": "laptop_3d", "color": "#3B6BFF", "price": 2000, "payToName": "Test A.", "payPhone": "87071234567"}).json()
    eid = event["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    decoded = []
    def reject(data, root):
        decoded.append(data)
        raise receipt.NotReceipt()
    monkeypatch.setattr(receipt, "take", reject)
    monkeypatch.setitem(logic.core.UPLOAD_LIMIT, "receipt", 2)
    def send_app():
        return c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=b"app")
    msg = {"message_id": 1, "chat": {"id": 10, "type": "private"}, "document": {"file_id": "F", "file_size": 3, "mime_type": "image/jpeg"}}
    async def send_bot():
        def handle(req):
            return httpx.Response(200, json={"result": {"file_path": "p.jpg"}}) if req.url.path.endswith("getFile") else httpx.Response(200, content=b"bot")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await bot._receipt(cfg, client, con, msg)
    assert send_app().json()["message"] == "not_receipt"
    assert asyncio.run(send_bot())["text"] == texts.bot_message("ru", "receipt_not")[0]
    assert send_app().status_code == 429
    assert asyncio.run(send_bot())["text"] == texts.bot_message("ru", "receipt_wait")[0]
    assert decoded == [b"app", b"bot"]


def test_avatar_attempts_include_bad_images_and_expire(organizer, monkeypatch):
    c, _, _, _ = organizer
    t = logic.now()
    monkeypatch.setattr(logic.core, "now", lambda: t)
    monkeypatch.setitem(logic.core.UPLOAD_LIMIT, "avatar", 1)
    def upload():
        return c.post("/api/me/photo", headers=tma(20), content=b"bad image")
    assert upload().status_code == 400
    assert upload().status_code == 429
    t += logic.core.UPLOAD_WINDOW
    assert upload().status_code == 400


def test_unused_covers_bounded_without_removing_a_club_logo(organizer, monkeypatch):
    c, cfg, con, _ = organizer
    monkeypatch.setattr(logic.account, "UNUSED_COVERS", 1)
    def cover(color):
        raw = io.BytesIO()
        Image.new("RGB", (3, 3), color).save(raw, "PNG")
        return c.post("/api/photos", headers=tma(20), content=raw.getvalue()).json()
    logo = cover("red")
    con.execute("UPDATE orgs SET logo_file_id = ? WHERE id = 1", (logo["id"],))
    old, keep = cover("green"), cover("blue")
    assert [r[0] for r in con.execute("SELECT id FROM files ORDER BY id")] == [logo["id"], keep["id"]]
    home = Path(cfg.db_path).parent
    assert (home / logo["url"]).is_file() and (home / keep["url"]).is_file()
    assert not (home / old["url"]).exists()


def test_concurrent_video_reservations_respect_owner_quota(organizer):
    _, cfg, con, v = organizer
    logic.new_video(con, v, 4)
    checking = threading.Event()
    def start():
        other = db.connect(cfg.db_path)
        try:
            other.set_trace_callback(lambda q: checking.set() if q.startswith(("BEGIN IMMEDIATE", "INSERT INTO videos")) else None)
            return logic.new_video(other, v, 4)
        finally:
            other.close()
    with ThreadPoolExecutor(1) as workers:
        with db.tx(con):
            logic.new_video(con, v, 4)
            result = workers.submit(start)
            assert checking.wait(5)
        with pytest.raises(logic.ApiError, match="rate_limited"):
            result.result()
    assert con.execute("SELECT count(*) FROM videos").fetchone()[0] == 2


def test_simultaneous_video_piece_retries_are_idempotent(organizer):
    c, cfg, _, _ = organizer
    headers = tma(20)
    vid = c.post("/api/videos", headers=headers, json={"size": 4}).json()["id"]
    async def send_both():
        ready = asyncio.Barrier(2)
        async def piece():
            await ready.wait()
            yield b"abcd"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app), base_url="http://test") as client:
            return await asyncio.gather(*(client.put(f"/api/videos/{vid}?at=0", headers=headers, content=piece()) for _ in range(2)))
    assert [r.json() for r in asyncio.run(send_both())] == [{"at": 4}, {"at": 4}]
    assert (Path(cfg.db_path).parent / "uploads" / str(vid)).read_bytes() == b"abcd"
    assert c.post(f"/api/videos/{vid}/done", headers=headers).json()["status"] == "queued"
    assert c.put(f"/api/videos/{vid}?at=4", headers=headers, content=b"x").status_code == 409
