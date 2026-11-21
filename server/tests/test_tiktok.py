"""Group video links (tiktok.py, bot._tiktok; TIKTOK=1): which messages count, the sources' answers, and the bot's
flow: the video (or a slideshow's photos) under the link as a reply, off without the switch, nothing for a bot, a stale message, the app's
banned, a swear-word message the filter deleted, or past a chat's cap a minute."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from kbtu import bot, db, logic, tgc, tiktok
from test_core import env, login  # noqa: F401  (env: the fixture)

VIDEO = b"\0\0\0\x18ftypmp42" + b"x" * 100
URL = "https://vm.tiktok.com/ZMk8xQ/"
SHORT = "https://m.youtube.com/shorts/aB1234567_-"
YT = "https://youtu.be/aB1234567_-"
REEL = "https://www.instagram.com/reel/Re_123-4/"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    """The per-worker memories these tests touch start empty and go back as they were: the cap's, the swear filter's,
    and chatlist's "no club holds this chat" (a chat -100 left there would read as unheld in the next test's database)."""
    monkeypatch.setattr(tiktok, "_sent", {})
    monkeypatch.setattr(bot, "_swore", {})
    monkeypatch.setattr(logic.chatlist, "_unheld", {})
    logic.chatmod.stale()
    yield
    logic.chatmod.stale()


def _tikwm(answer: dict | None = None, file: bytes = VIDEO, status: int = 200) -> httpx.AsyncClient:
    """tikwm.com and TikTok's file server (a photo's file is its name)."""
    answer = answer if answer is not None else {"code": 0, "data": {"play": "https://v1.tiktokcdn.com/v.mp4", "size": len(file), "duration": 14}}

    def handle(req: httpx.Request) -> httpx.Response:
        if req.headers["Host"] == "www.tikwm.com":
            assert req.method == "POST" and dict(httpx.QueryParams(req.content.decode())) == {"url": URL}  # the link alone
            return httpx.Response(status, json=answer)
        if req.url.path.startswith("/p/"):
            return httpx.Response(404) if req.url.path.endswith("gone.jpg") else httpx.Response(200, content=req.url.path.encode())
        return httpx.Response(200, content=file)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _fetch(client):
    async def go():
        async with client:
            return await tiktok.fetch(client, URL)
    return asyncio.run(go())


def test_link():
    say = lambda text, **kw: tiktok.link({"text": text, "from": {"id": 1}, **kw})  # noqa: E731
    assert say(f"look {URL} lol") == URL
    assert say(f"{URL}\u00a0words") == URL
    assert say("https://www.tiktok.com/@chess/video/7312345678901234567?is_from_webapp=1") == \
        "https://www.tiktok.com/@chess/video/7312345678901234567?is_from_webapp=1"
    assert say("https://vt.tiktok.com/ZS1/") and say("HTTPS://TIKTOK.COM/@x/video/1")
    assert tiktok.link({"caption": URL, "from": {"id": 1}}) == URL  # under a photo
    assert say("https://nottiktok.com/x") is None and say("tiktok.com/@x") is None and say("") is None
    assert say(URL, **{"from": {"id": 1, "is_bot": True}}) is None  # another downloader bot: no loop
    assert say(URL, is_automatic_forward=True) is None  # the channel's copy in its discussion group
    for url in (SHORT, YT, REEL, REEL.replace("/reel/", "/reels/"), REEL.replace("/reel/", "/p/")):
        assert tiktok.link({"caption": f"({url}?share=abc) {URL}"}) == url
        assert say(f"{URL} {url}") == URL
    for url in ("https://youtube.com/watch?v=aB1234567_-", YT + "x", REEL.replace(".com", ".com.example"),
                "https://instagram.com/reels/audio/123/", "https://instagram.com/someone/"):
        assert say(url) is None


def test_room():
    assert all(tiktok.room(-1, 1000) for _ in range(tiktok.CHAT_CAP))
    assert not tiktok.room(-1, 1001) and tiktok.room(-2, 1001)  # chats apart
    assert tiktok.room(-1, 1061)  # a minute later


def test_fetch(media_dns):
    assert _fetch(_tikwm()) == tiktok.Media(VIDEO, 14, [])
    assert _fetch(_tikwm({"code": -1, "msg": "Url parsing is failed!"})) is None  # private or deleted
    assert _fetch(_tikwm(status=503)) is None
    assert _fetch(_tikwm({"code": 0, "data": {"play": "https://outside.example/file.mp4"}})) is None
    assert _fetch(_tikwm({"code": 0, "data": {"play": "http://v1.tiktokcdn.com/v.mp4"}})) is None  # https only
    assert _fetch(_tikwm({"code": 0, "data": {"play": "https://v1.tiktokcdn.com/v.mp4", "size": tiktok.MAX_BYTES + 1}})) is None
    big = b"x" * (tiktok.MAX_BYTES + 1)
    assert _fetch(_tikwm({"code": 0, "data": {"play": "https://v1.tiktokcdn.com/v.mp4"}}, file=big)) is None  # no size said: counted
    # a slideshow: its photos in order (its "play" is the music), ten at most, a missing one skipped, none: nothing
    pics = [f"https://v1.tiktokcdn.com/p/{i}.jpg" for i in range(12)]
    got = _fetch(_tikwm({"code": 0, "data": {"play": "https://v1.tiktokcdn.com/a.mp3", "images": pics}}))
    assert got.video is None and got.photos == [f"/p/{i}.jpg".encode() for i in range(tiktok.ALBUM)]
    got = _fetch(_tikwm({"code": 0, "data": {"images": ["https://v1.tiktokcdn.com/p/gone.jpg", "https://v1.tiktokcdn.com/p/1.jpg"]}}))
    assert got.photos == [b"/p/1.jpg"]
    assert _fetch(_tikwm({"code": 0, "data": {"images": ["https://v1.tiktokcdn.com/p/gone.jpg"]}})) is None


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class _Http:
    """Telegram (the updates once, then nothing; every call kept)."""
    def __init__(self, updates=()):
        self.updates, self.calls = list(updates), []

    async def post(self, url, json=None, data=None, files=None, **_):
        self.calls.append((url.rsplit("/", 1)[1], json if json is not None else data, files))
        return _Resp({"ok": True, "result": {"message_id": 900}})

    async def get(self, url, params=None, **_):
        out, self.updates = self.updates, []
        return _Resp({"ok": True, "result": out})

    def said(self, method):
        return [(j, f) for m, j, f in self.calls if m == method]


async def _drain():
    """The jobs the batch left beside the ears (tgc.spawn); a finished one leaves the set on the loop's next turn."""
    while tgc._tasks:
        await asyncio.gather(*list(tgc._tasks))
        await asyncio.sleep(0)


def _msg(tg, text=f"look {URL}", mid=7, **kw):
    return {"chat": {"id": -100, "type": "supergroup"}, "message_id": mid, "text": text, "date": int(time.time()), "from": {"id": tg}, **kw}


def _hear(cfg, monkeypatch, *msgs, fetched=tiktok.Media(VIDEO, 14, [])):
    asked = []

    async def fetch(http, url):
        asked.append(url)
        return fetched
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = _Http([{"update_id": i + 1, "message": m} for i, m in enumerate(msgs)])

    async def go():
        await bot.hear(cfg, http, 0)
        await _drain()
    asyncio.run(go())
    return http, asked


def test_group_gets_the_video(env, monkeypatch):
    c, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    login(c, 31, "u31")
    http, asked = _hear(cfg, monkeypatch, _msg(31), _msg(32, "no link here", mid=8),
                        _msg(33, URL, mid=9, is_topic_message=True, message_thread_id=4))
    assert asked == [URL, URL]  # a person without an account too: the chat is everyone's
    (first, files), (second, _) = http.said("sendVideo")
    assert first["chat_id"] == "-100" and first["duration"] == "14" and "message_thread_id" not in first
    assert json.loads(first["reply_parameters"]) == {"message_id": 7, "allow_sending_without_reply": True}
    assert files == {"video": ("tiktok.mp4", VIDEO, "video/mp4")} and "caption" not in first  # no words of the bot's
    assert second["message_thread_id"] == "4" and json.loads(second["reply_parameters"])["message_id"] == 9
    # a slideshow: one photo alone, more as an album, each photo its own part
    http, _ = _hear(cfg, monkeypatch, _msg(31, mid=11), fetched=tiktok.Media(None, 0, [b"a"]))
    ((one_, files),) = http.said("sendPhoto")
    assert files == {"photo": ("tiktok.jpg", b"a", "image/jpeg")} and json.loads(one_["reply_parameters"])["message_id"] == 11
    http, _ = _hear(cfg, monkeypatch, _msg(31, mid=12), fetched=tiktok.Media(None, 0, [b"a", b"b", b"c"]))
    ((album, files),) = http.said("sendMediaGroup")
    assert json.loads(album["media"]) == [{"type": "photo", "media": f"attach://p{i}"} for i in range(3)]
    assert {k: v[1] for k, v in files.items()} == {"p0": b"a", "p1": b"b", "p2": b"c"} and "caption" not in album
    # nothing to send (a private video): nothing at all
    http, asked = _hear(cfg, monkeypatch, _msg(31, mid=10), fetched=None)
    assert asked == [URL] and not http.said("sendVideo")


def test_who_gets_none(env, monkeypatch):
    c, cfg = env
    login(c, 31, "u31")
    login(c, 66, "u66")
    _, asked = _hear(cfg, monkeypatch, _msg(31))  # TIKTOK unset
    assert asked == []
    cfg = dataclasses.replace(cfg, tiktok=True)
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 66")
    cfg = dataclasses.replace(cfg, tgc_chat=-222)
    _, asked = _hear(cfg, monkeypatch,
                     _msg(31, SHORT, date=int(time.time()) - bot.FRESH - 60),
                     _msg(66, REEL, mid=8),  # the app's banned
                     _msg(77, YT, mid=9, **{"from": {"id": 77, "is_bot": True}}),
                     _msg(31, REEL, mid=10, chat={"type": "private", "id": 31}),
                     _msg(31, SHORT, mid=11, chat={"type": "supergroup", "id": -222}))
    assert asked == []
    urls = [URL, YT, REEL] * 3
    _, asked = _hear(cfg, monkeypatch, *[_msg(31, url, mid=20 + i) for i, url in enumerate(urls)])
    assert asked == urls[:tiktok.CHAT_CAP]  # all sources share the same cap


def _file_format(name, width=720, height=1280, ext="mp4", **kw):
    return {"width": width, "height": height, "ext": ext, "url": f"https://cdn.example/{name}.{ext}",
            "format_id": name, "vcodec": "avc1", "acodec": "aac", **kw}


def _source(monkeypatch, cfg, link, meta, payload=VIDEO, progress=None):
    """Real yt-dlp selection and postprocessing with just extraction and the media transfer stubbed."""
    from yt_dlp import YoutubeDL

    urls, downloads, dirs = [], [], []

    def extract(dl, url, *, download, process):
        assert not download and not process and dl.params["cachedir"] is False
        urls.append(url)
        dirs.append(Path(dl.params["outtmpl"]["default"]).parent)
        return {"extractor": "fixture", "id": "clip", "title": "clip", "duration": 14, **meta}

    def transfer(dl, filename, info):
        downloads.append(info["format_id"])
        Path(filename).write_bytes(payload)
        if progress:
            for hook in dl.params["progress_hooks"]:
                hook(progress)
        return True, True

    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    monkeypatch.setattr(YoutubeDL, "dl", transfer)
    http = _Http()
    msg = _msg(31, link + "?share=tracking")
    asyncio.run(bot._tiktok(cfg, http, msg, tiktok.link(msg)))
    assert len(dirs) == 1 and not dirs[0].exists()
    return urls[0], downloads, http.calls


def test_source_formats_and_reply(env, monkeypatch):
    _, cfg = env
    formats = [_file_format("webm", ext="webm"), _file_format("hevc", vcodec="hevc"),
               _file_format("h264"), _file_format("hd", 1080, 1920), _file_format("large", filesize=tiktok.MAX_BYTES),
               _file_format("no-sound", acodec="none"), _file_format("audio", vcodec="none")]
    url, downloads, calls = _source(monkeypatch, cfg, YT, {"duration": 179.9, "formats": formats})
    assert url == "https://www.youtube.com/watch?v=aB1234567_-" and downloads == ["h264"]
    (method, body, files), = calls
    assert method == "sendVideo" and body["duration"] == "179" and "caption" not in body
    assert files["video"][1] == VIDEO and json.loads(body["reply_parameters"])["message_id"] == 7
    # A carousel beginning with a photo. A silent video is legitimate when the source has no audio.
    entry = {"id": "slide", "title": "slide", "formats": [_file_format("silent", acodec="none")]}
    url, downloads, calls = _source(monkeypatch, cfg, REEL, {"_type": "playlist", "entries": [{"formats": []}, entry, entry]})
    assert url == "https://www.instagram.com/p/Re_123-4/" and downloads == ["silent"]
    assert calls[0][0] == "sendVideo" and "caption" not in calls[0][1]


def test_source_rejections(env, monkeypatch):
    _, cfg = env
    for duration in (None, 0, 180, 181):
        assert _source(monkeypatch, cfg, YT, {"duration": duration, "formats": [_file_format("video")]})[1:] == ([], [])
    assert _source(monkeypatch, cfg, SHORT, {"duration": 180, "formats": [_file_format("video")]})[1] == ["video"]
    for meta in ({"formats": []}, {"is_live": True}, {"formats": [_file_format("hd", 1920, 1080)]}):
        assert _source(monkeypatch, cfg, REEL, meta)[1:] == ([], [])
    monkeypatch.setattr(tiktok, "MAX_BYTES", len(VIDEO))
    meta = {"formats": [_file_format("video")]}
    assert _source(monkeypatch, cfg, REEL, meta)[1:] == (["video"], [])  # final size check
    assert _source(monkeypatch, cfg, REEL, meta, b"partial", {"downloaded_bytes": len(VIDEO)})[1:] == (["video"], [])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_source_webm_converts_to_mp4(env, monkeypatch):
    _, cfg = env
    webm = subprocess.check_output(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=size=32x48",
                                    "-frames:v", "1", "-c:v", "libvpx-vp9", "-f", "webm", "-"])
    _, downloads, calls = _source(monkeypatch, cfg, REEL, {"formats": [_file_format("web", ext="webm", vcodec="vp9")]}, webm)
    assert downloads == ["web"] and calls[0][2]["video"][1][4:8] == b"ftyp"


def test_swear_deleted_gets_none(env, monkeypatch):
    """A message the swear filter deleted is gone: no video under it."""
    c, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    for tg in (21, 31):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    con.execute("""INSERT INTO chats (title, kind, url, tg_chat_id, created_at, status, org_id, swear)
        VALUES ('Chess', 'group', 'https://t.me/+c', -100, 0, 'org', ?, 1)""", (oid,))
    monkeypatch.setattr(bot, "WARN_FOR", 0)

    class Rights(_Http):
        async def post(self, url, json=None, data=None, files=None, **_):
            if url.endswith("/getChatMember"):
                self.calls.append(("getChatMember", json, None))
                return _Resp({"ok": True, "result": {"status": "administrator" if json["user_id"] == 123 else "member",
                                                     "can_delete_messages": True, "can_restrict_members": True}})
            return await super().post(url, json, data, files)
    asked = []

    async def fetch(http, url):
        asked.append(url)
        return tiktok.Media(VIDEO, 14, [])
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = Rights([{"update_id": 1, "message": _msg(31, f"\u0441\u0443\u043a\u0430 {URL}")}])

    async def go():
        await bot.hear(cfg, http, 0)
        await _drain()
    asyncio.run(go())
    assert http.said("deleteMessage") and asked == [] and not http.said("sendVideo")
