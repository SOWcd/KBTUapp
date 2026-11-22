"""Group video links (tiktok.py, bot._tiktok; TIKTOK=1): which messages count, the sources' answers, and the bot's
flow: the video (or a slideshow's photos) under the link as a reply, off without the switch, nothing for a bot, a stale message, the app's
banned, a swear-word message the filter deleted, or past a chat's cap a minute."""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import math
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from kbtu import bot, db, download, logic, tgc, tiktok
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
    monkeypatch.setattr(tiktok, "_sent", OrderedDict())
    monkeypatch.setattr(tiktok, "_files", OrderedDict())
    monkeypatch.setattr(tiktok, "_health", {})
    monkeypatch.setattr(tiktok, "_flights", {})
    monkeypatch.setattr(tiktok, "_told", {})
    monkeypatch.setattr(tiktok, "_session_uses", tiktok.deque())
    monkeypatch.delenv(tiktok.COOKIES, raising=False)  # stories off unless a test sets its own made-up cookies
    monkeypatch.setattr(bot, "_video_seen", set())
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
            assert req.method == "POST" and dict(httpx.QueryParams(req.content.decode())) == {"url": URL, "hd": "1"}
            return httpx.Response(status, json=answer)
        if req.url.path.startswith("/p/"):
            return httpx.Response(404) if req.url.path.endswith("gone.jpg") else httpx.Response(200, content=req.url.path.encode())
        return httpx.Response(200, content=file)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _fetch(client):
    async def go():
        async with client:
            got = await tiktok.fetch(client, URL)
            if isinstance(got, list):
                return await tiktok.photos(client, got) or None
            return got
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
    assert all(tiktok.room(-1, 1000, user=u) for u in range(tiktok.CHAT_CAP))
    assert not tiktok.room(-1, 1001, user=99) and tiktok.room(-2, 1001, user=99)  # chats apart
    assert tiktok.room(-1, 1061, user=98)  # a minute later


def test_fetch(media_dns):
    assert _fetch(_tikwm()).formats[0]["url"] == "https://v1.tiktokcdn.com/v.mp4"
    assert _fetch(_tikwm({"code": -1, "msg": "Url parsing is failed!"})) is None  # private or deleted
    with pytest.raises(tiktok.SourceDown):  # the source failed: counted by its breaker, still no reply
        _fetch(_tikwm(status=503))
    assert _fetch(_tikwm({"code": 0, "data": {"play": "http://v1.tiktokcdn.com/v.mp4"}})) is None  # https only
    assert _fetch(_tikwm({"code": 0, "data": {"play": "https://v1.tiktokcdn.com/v.mp4", "size": tiktok.MAX_BYTES + 1}})) is None
    assert _fetch(_tikwm({"code": 0, "data": {"play": "https://outside.example/file.mp4"}})) is None
    # a slideshow: its photos in order (its "play" is the music), ten at most, a missing one skipped, none: nothing
    pics = [f"https://v1.tiktokcdn.com/p/{i}.jpg" for i in range(12)]
    got = _fetch(_tikwm({"code": 0, "data": {"play": "https://v1.tiktokcdn.com/a.mp3", "images": pics}}))
    assert got == [f"/p/{i}.jpg".encode() for i in range(tiktok.ALBUM)]
    got = _fetch(_tikwm({"code": 0, "data": {"images": ["https://v1.tiktokcdn.com/p/gone.jpg", "https://v1.tiktokcdn.com/p/1.jpg"]}}))
    assert got == [b"/p/1.jpg"]
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


FORMAT = {"format_id": "clip", "url": "https://v1.tiktokcdn.com/v.mp4", "ext": "mp4", "protocol": "https", "width": 720,
          "height": 1280, "vcodec": "avc1", "acodec": "aac", "filesize": 4096}
CLIP = tiktok.Clip("tt:123", 14, [FORMAT], "https://v1.tiktokcdn.com/cover.jpg")


def _hear(cfg, monkeypatch, *msgs, fetched=CLIP):
    asked = []

    async def fetch(http, url):
        asked.append(url)
        return fetched
    async def photos(http, urls):
        return [url.encode() for url in urls]
    monkeypatch.setattr(tiktok, "fetch", fetch)
    monkeypatch.setattr(tiktok, "photos", photos)
    http = _Http([{"update_id": m["message_id"], "message": m} for m in msgs])

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
    assert first["chat_id"] == -100 and first["duration"] == 14 and "message_thread_id" not in first
    assert first["reply_parameters"] == {"message_id": 7, "allow_sending_without_reply": True}
    assert first["width"] == 720 and first["height"] == 1280 and first["cover"] == CLIP.cover and first["supports_streaming"]
    assert http.said("sendChatAction") == [({"chat_id": -100, "action": "upload_video"}, None),
                                          ({"chat_id": -100, "message_thread_id": 4, "action": "upload_video"}, None)]
    assert files is None and first["video"] == FORMAT["url"] and "caption" not in first  # no words of the bot's
    assert second["message_thread_id"] == 4 and second["reply_parameters"]["message_id"] == 9
    # a slideshow: one photo alone, more as an album, each photo its own part
    http, _ = _hear(cfg, monkeypatch, _msg(34, mid=11), fetched=["a"])
    ((one_, files),) = http.said("sendPhoto")
    assert files == {"photo": ("tiktok.jpg", b"a", "image/jpeg")} and json.loads(one_["reply_parameters"])["message_id"] == 11
    http, _ = _hear(cfg, monkeypatch, _msg(35, mid=12), fetched=["a", "b", "c"])
    ((album, files),) = http.said("sendMediaGroup")
    assert json.loads(album["media"]) == [{"type": "photo", "media": f"attach://p{i}"} for i in range(3)]
    assert {k: v[1] for k, v in files.items()} == {"p0": b"a", "p1": b"b", "p2": b"c"} and "caption" not in album
    # nothing to send (a private video): nothing at all
    http, asked = _hear(cfg, monkeypatch, _msg(36, mid=10), fetched=None)
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
    _, asked = _hear(cfg, monkeypatch, *[_msg(40 + i, url, mid=20 + i) for i, url in enumerate(urls)])
    assert asked == urls[:tiktok.CHAT_CAP]  # all sources share the same cap


def _file_format(name, width=720, height=1280, ext="mp4", host="rr1.googlevideo.com", **kw):
    size = {} if "filesize" in kw or "filesize_approx" in kw else {"filesize": 4096}
    return {"width": width, "height": height, "ext": ext, "url": f"https://{host}/{name}.{ext}",
            "format_id": name, "vcodec": "avc1", "acodec": "aac", **size, **kw}


def _source(monkeypatch, cfg, link, meta):
    """Use the pinned yt-dlp normalizer and format sorter; extraction never transfers a file."""
    from yt_dlp import YoutubeDL

    urls = []
    def extract(dl, url, *, download, process):
        assert not download and not process and not dl.params["cachedir"]
        urls.append(url)
        return {"extractor": "fixture", "id": "clip", "title": "clip", "duration": 14, **meta}

    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    http = _Http()
    msg = _msg(31, link + "?share=tracking")
    asyncio.run(bot._tiktok(cfg, http, msg, tiktok.link(msg)))
    return urls[0], http.said("sendVideo")


def test_source_formats_and_reply(env, monkeypatch):
    _, cfg = env
    formats = [_file_format("vp9", 2160, 3840, vcodec="vp9"), _file_format("hevc", vcodec="hevc"),
               _file_format("h264"), _file_format("hd", 1080, 1920), _file_format("large", 2160, 3840, filesize=tiktok.MAX_BYTES + 1),
               _file_format("opus", 2160, 3840, acodec="opus"), _file_format("no-sound", acodec="none")]
    url, ((body, files),) = _source(monkeypatch, cfg, YT, {"duration": 179.9, "formats": formats})
    assert url == "https://www.youtube.com/watch?v=aB1234567_-" and body["video"].endswith("/hd.mp4")
    assert files is None and body["duration"] == 179 and body["height"] == 1920
    entry = {"id": "slide", "title": "slide", "duration": 4,
             "formats": [_file_format("silent", acodec="none", host="scontent.cdninstagram.com")]}
    url, ((body, _),) = _source(monkeypatch, cfg, REEL, {"_type": "playlist", "entries": [{"formats": []}, entry]})
    assert url == "https://www.instagram.com/p/Re_123-4/" and body["video"].endswith("/silent.mp4")


def test_source_rejections(env, monkeypatch):
    _, cfg = env
    for duration in (None, 0, 180, 181):
        assert not _source(monkeypatch, cfg, YT, {"duration": duration, "formats": [_file_format("video")]})[1]
    assert _source(monkeypatch, cfg, SHORT, {"duration": 180, "formats": [_file_format("video")]})[1]
    for meta in ({"formats": []}, {"is_live": True}, {"formats": [_file_format("web", ext="webm", vcodec="vp9")]}):
        assert not _source(monkeypatch, cfg, REEL, meta)[1]


@pytest.fixture
def movies(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    def make(name, size, codec="libx264"):
        path = tmp_path / (name + ".mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=size=" + size, "-f", "lavfi", "-i",
                        "sine", "-t", "0.25", "-c:v", codec, "-threads", "1", "-c:a", "aac", str(path)], check=True)
        return path.read_bytes()
    return make


def test_tikwm_compares_real_track_headers(movies, media_dns):
    files = {"/sd": movies("sd", "32x48"), "/hd": movies("hd", "64x96")}
    skip = 128 * 1024
    files["/hd"] = skip.to_bytes(4, "big") + b"free" + bytes(skip - 8) + files["/hd"]
    starts = []
    data = {"id": "123", "play": "https://v1.tiktokcdn.com/sd", "hdplay": "https://v1.tiktokcdn.com/hd"}
    def handle(req):
        if req.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": data})
        # Range reads only; yt-dlp and Telegram never receive a test network request.
        start, end = map(int, req.headers["range"][6:].split("-"))
        starts.append((req.url.path, start))
        return httpx.Response(206, content=files[req.url.path][start:end + 1])
    async def choose():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            clip = await tiktok.fetch(http, URL)
            return await tiktok.versions(http, clip)
    assert asyncio.run(choose())[0].video["height"] == 96
    assert ("/hd", skip) in starts
    files["/hd"] = movies("other", "64x96", "mpeg4")
    (sd,) = asyncio.run(choose())
    assert sd.video["height"] == 48 and sd.video["acodec"] == "aac"


def test_tikwm_without_range_support_still_sends_by_url(env, monkeypatch, movies, media_dns):
    _, cfg = env
    payloads = {"/hd": movies("hd", "64x96", "mpeg4"), "/sd": movies("sd", "32x48")}
    # Put the SD header beyond the initial read, as with a tail-indexed MP4.
    padding = (70000).to_bytes(4, "big") + b"free" + bytes(69992)
    payloads["/sd"] = padding + payloads["/sd"]
    sent, reads = [], []

    def handle(req):
        if req.url.host == "api.telegram.org":
            if req.url.path.endswith("/sendVideo"):
                sent.append(json.loads(req.content))
            return httpx.Response(200, json={"ok": True})
        if req.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": {
                "hdplay": "https://v1.tiktokcdn.com/hd", "play": "https://v1.tiktokcdn.com/sd"}})
        if "range" in req.headers:
            return httpx.Response(416)
        reads.append(req.url.path)
        return httpx.Response(200, content=payloads[req.url.path])

    monkeypatch.setattr(tiktok, "upload", lambda *_: pytest.fail("Telegram accepted the URL"))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            await bot._tiktok(cfg, http, _msg(31), URL)

    asyncio.run(go())
    assert [(b["video"], b["width"], b["height"]) for b in sent] == [("https://v1.tiktokcdn.com/sd", 32, 48)]
    assert sorted(reads) == ["/hd", "/sd"]


def test_tikwm_fallback_pins_the_source_and_counts_bytes(monkeypatch, movies, media_dns):
    payload = movies("fallback", "32x48")
    def handle(req):
        assert req.url.host == "93.184.216.34" and req.extensions["sni_hostname"] == "v1.tiktokcdn.com"
        async def chunks():
            yield payload[:32]
            yield payload[32:]
        return httpx.Response(200, content=chunks())

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            version = tiktok.Version(FORMAT)
            video, thumb, tracks = await tiktok.prepare_upload(http, CLIP, version)
            assert video and thumb and (tracks["width"], tracks["height"]) == (32, 48)
            monkeypatch.setattr(tiktok, "MAX_BYTES", len(payload) - 1)
            assert await tiktok.prepare_upload(http, CLIP, version) is None
    asyncio.run(go())


def test_split_tracks_and_thumbnail(env, monkeypatch, movies, tmp_path):
    from yt_dlp import YoutubeDL
    from PIL import Image
    import io

    _, cfg = env
    hd = _file_format("hd", 1440, 2560, acodec="none")
    audio = _file_format("sound", vcodec="none", acodec="mp4a.40.2", language_preference=10)
    dub = {**audio, "format_id": "dub", "language_preference": 5}
    original = movies("original", "48x64")
    downloaded = []
    def transfer(dl, path, info):
        downloaded.append(info["format_id"])
        Path(path).write_bytes(original)
        return True, True
    monkeypatch.setattr(YoutubeDL, "dl", transfer)
    _, ((body, files),) = _source(monkeypatch, cfg, SHORT, {"formats": [_file_format("sd"), hd, audio, dub]})
    assert downloaded == ["hd", "sound"] and body["supports_streaming"] == "true"
    out = tmp_path / "merged.mp4"
    out.write_bytes(files["video"][1])
    assert files["video"][1].index(b"moov") < files["video"][1].index(b"mdat")
    def hashes(path):
        return subprocess.check_output(["ffprobe", "-v", "error", "-show_packets", "-show_data_hash", "sha256",
                                        "-show_entries", "packet=stream_index,data_hash", "-of", "csv", str(path)]).splitlines()
    assert sorted(hashes(out)) == sorted(hashes(tmp_path / "original.mp4"))
    thumb = Image.open(io.BytesIO(files["thumbnail"][1]))
    assert thumb.format == "JPEG" and max(thumb.size) <= 320


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
        return CLIP
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = Rights([{"update_id": 1, "message": _msg(31, f"\u0441\u0443\u043a\u0430 {URL}")}])

    async def go():
        await bot.hear(cfg, http, 0)
        await _drain()
    asyncio.run(go())
    assert http.said("deleteMessage") and asked == [] and not http.said("sendVideo")


@pytest.mark.parametrize("cache_route", ["url", "upload"])
def test_send_once_then_reuse_across_chats(env, monkeypatch, cache_route, caplog):
    _, cfg = env
    attempts, resolved, uploaded = [], [], []
    async def fetch(http, url):
        resolved.append(url)
        return CLIP

    async def upload(http, clip, version):
        uploaded.append(version)
        return VIDEO, b"jpeg", {**FORMAT, "duration": 14}

    class Telegram(_Http):
        async def post(self, url, json=None, data=None, files=None, **_):
            if url.endswith("/sendChatAction"):
                raise httpx.ConnectError("action failed")
            attempts.append((json or data, files))
            if json and json["video"] == FORMAT["url"] and cache_route == "upload":
                return _Resp({"ok": False}, 400)
            return _Resp({"ok": True, "result": {"video": {"file_id": "cached-file"}}})

    monkeypatch.setattr(tiktok, "fetch", fetch)
    monkeypatch.setattr(tiktok, "prepare_upload", upload)
    caplog.set_level("INFO", logger="uvicorn.error")
    http = Telegram()
    for mid, url in enumerate((URL, URL + "?tracking=1", "https://www.tiktok.com/@x/video/123"), start=10):
        msg = _msg(31, url, mid=mid, chat={"type": "group", "id": -mid})
        asyncio.run(bot._tiktok(cfg, http, msg, url))
    assert resolved == [URL] and len(uploaded) == int(cache_route == "upload")
    if uploaded:
        body, files = attempts[1]
        assert body["height"] == 1280 and files["thumbnail"][1] == b"jpeg" and files["video"][1] == VIDEO
    assert [(b["chat_id"], b["reply_parameters"]["message_id"], b["video"]) for b, _ in attempts[-2:]] == [
        (-11, 11, "cached-file"), (-12, 12, "cached-file")]
    assert [line.split()[2] for line in caplog.messages] == [cache_route, "cache", "cache"]
    assert all(line.startswith("group video ") and float(line.split()[-1][:-1]) >= 0 for line in caplog.messages)
    assert all(x not in caplog.text for x in (URL, "v1.tiktokcdn.com", "cached-file", "tracking"))


def test_lru_and_video_ids(monkeypatch):
    monkeypatch.setattr(tiktok, "CACHE_SIZE", 2)
    assert tiktok.key(YT) == tiktok.key(SHORT) != tiktok.key(REEL)
    assert tiktok.key(REEL) == tiktok.key(REEL.replace("/reel/", "/p/"))
    tiktok.remember("a", "one", 10)
    tiktok.remember("b", "two", 20)
    assert tiktok.cached("a") == ("one", 10)
    tiktok.remember("c", "three", 30)
    assert not tiktok.cached("b") and len(tiktok._files) == 2


def test_large_video_skips_remote_fetch_and_checks_actual_size(env, monkeypatch):
    _, cfg = env
    from yt_dlp import YoutubeDL
    monkeypatch.setattr(tiktok, "URL_BYTES", 10)
    monkeypatch.setattr(tiktok, "MAX_BYTES", len(VIDEO) - 1)
    touched = []
    def transfer(dl, path, info):
        touched.append(info["format_id"])
        Path(path).write_bytes(VIDEO)
        return True, True
    monkeypatch.setattr(YoutubeDL, "dl", transfer)
    hd = _file_format("hd", 1080, 1920, filesize_approx=50)
    _, ((body, _),) = _source(monkeypatch, cfg, SHORT, {"formats": [hd, _file_format("smaller", filesize=8)]})
    assert touched == ["hd"] and body["video"].endswith("/smaller.mp4")
    with pytest.raises(ValueError):
        tiktok._limit({"downloaded_bytes": len(VIDEO)})


def test_timeout_does_not_duplicate_a_reply(env, monkeypatch):
    _, cfg = env
    class Telegram(_Http):
        async def post(self, url, **kw):
            if url.endswith("/sendVideo"):
                self.calls.append(("sendVideo", kw["json"], None))
                raise httpx.ReadTimeout("reply may already have arrived")
            return await super().post(url, **kw)
    async def fetch(http, url):
        return CLIP
    monkeypatch.setattr(tiktok, "fetch", fetch)
    monkeypatch.setattr(tiktok, "upload", lambda *args: pytest.fail("ambiguous Telegram result"))
    http = Telegram()
    asyncio.run(bot._tiktok(cfg, http, _msg(31), URL))
    assert len(http.said("sendVideo")) == 1 and not tiktok.cached(tiktok.key(URL))


def test_checkout_is_answered_even_if_video_admission_cannot_open_db(env, monkeypatch):
    import sqlite3
    from test_stars import checkout

    _, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    http = _Http([checkout("video-batch"), {"update_id": 2, "message": _msg(31, SHORT)}])

    def broken(_):
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr(db, "connect", broken)
    async def go():
        with pytest.raises(sqlite3.OperationalError):
            await bot.hear(cfg, http, 0)
        await _drain()

    asyncio.run(go())
    assert http.said("answerPreCheckoutQuery") and not http.said("sendChatAction")


def test_links_start_while_earlier_updates_and_other_links_wait(env, monkeypatch):
    _, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    async def go():
        ready = asyncio.Event()
        release = asyncio.Event()
        started = []
        async def fetch(http, url):
            started.append(url)
            if len(started) == 2:
                ready.set()
            await release.wait()
            return CLIP

        async def group(cfg, http, con, msg):
            if msg["message_id"] == 1:
                async with asyncio.timeout(3):
                    await ready.wait()
                assert len(http.said("sendChatAction")) == 2
                release.set()

        monkeypatch.setattr(tiktok, "fetch", fetch)
        monkeypatch.setattr(bot, "_group", group)
        updates = [{"update_id": i, "message": _msg(31, url, mid=i)} for i, url in enumerate(("other", SHORT, REEL), 1)]
        http = _Http(updates)
        try:
            assert await bot.hear(cfg, http, 0) == 4
            assert started == [SHORT, REEL] and release.is_set()
            # An unconfirmed batch can be delivered twice.
            http.updates = updates
            await bot.hear(cfg, http, 0)
            assert started == [SHORT, REEL]
        finally:
            release.set()
            await _drain()
    asyncio.run(go())


def test_link_arriving_during_a_slow_batch(env, monkeypatch):
    _, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    monkeypatch.setattr(bot, "PEEK", 0.01)
    async def go():
        sent = asyncio.Event()
        first = {"update_id": 1, "message": _msg(31, "other")}
        later = {"update_id": 2, "message": _msg(31, SHORT, mid=8)}
        class Telegram(_Http):
            async def get(self, url, params, **kw):
                updates = [first, later] if not params["timeout"] else ([first] if not params["offset"] else [later])
                return _Resp({"ok": True, "result": updates})

        async def fetch(http, url):
            sent.set()
            return CLIP

        async def group(cfg, http, con, msg):
            if msg is first["message"]:
                await asyncio.wait_for(sent.wait(), 3)

        monkeypatch.setattr(tiktok, "fetch", fetch)
        monkeypatch.setattr(bot, "_group", group)
        http = Telegram()
        assert await bot.hear(cfg, http, 0) == 2 and sent.is_set()
        assert await bot.hear(cfg, http, 2) == 3
        await _drain()
        assert len(http.said("sendVideo")) == 1
    asyncio.run(go())


def test_stale_file_id_resolves_again_and_respects_short_host_limit(env, monkeypatch):
    _, cfg = env
    class Telegram(_Http):
        async def post(self, url, **kw):
            r = await super().post(url, **kw)
            return _Resp({"ok": False}, 400) if kw.get("json", {}).get("video") == "expired" else r
    async def fetch(http, url):
        return tiktok.Clip(tiktok.key(SHORT), 180, [FORMAT])
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = Telegram()
    tiktok.remember(tiktok.key(SHORT), "expired", 180)
    asyncio.run(bot._tiktok(cfg, http, _msg(31, YT), YT))
    assert not http.said("sendVideo")
    asyncio.run(bot._tiktok(cfg, http, _msg(31, SHORT), SHORT))
    assert [b["video"] for b, _ in http.said("sendVideo")] == ["expired", FORMAT["url"]]
    assert not tiktok.cached(tiktok.key(SHORT))


# --- Robustness (issue #170, task 1): dedupe, caps, deadlines, sizes, hosts, the breaker, bounded memory. ---

CFG = SimpleNamespace(bot_token="t")


class _Telegram(_Http):
    """Telegram that answers every send with a file id (a video's, or a photo's sizes) and keeps every call."""
    async def post(self, url, json=None, data=None, files=None, **_):
        method = url.rsplit("/", 1)[1]
        self.calls.append((method, json if json is not None else data, files))
        if method == "sendMediaGroup":
            count = len(files or ()) or len((json or {}).get("media", ()))
            return _Resp({"ok": True, "result": [{"photo": [{"file_id": f"small{i}"}, {"file_id": f"ph{i}"}]} for i in range(count)]})
        if method == "sendPhoto":
            return _Resp({"ok": True, "result": {"photo": [{"file_id": "ph0"}]}})
        return _Resp({"ok": True, "result": {"video": {"file_id": "fid"}}})


def _routes(caplog):
    return sorted(m.split()[2] for m in caplog.messages if m.startswith("group video "))


def test_same_video_at_once_is_fetched_once(monkeypatch, caplog):
    """Three chats at once: two with the same short link, one with the video's full link. The short link resolves once,
    the file goes to Telegram once, and the others get its file id."""
    caplog.set_level("INFO", logger="uvicorn.error")
    fetched = []
    full = "https://www.tiktok.com/@x/video/123"

    async def go():
        gate = asyncio.Event()

        async def fetch(http, url):
            fetched.append(url)
            await gate.wait()
            return CLIP
        monkeypatch.setattr(tiktok, "fetch", fetch)
        http = _Telegram()
        msgs = [_msg(31 + i, url, mid=10 + i, chat={"type": "group", "id": -10 - i}) for i, url in enumerate((URL, URL, full))]
        jobs = [asyncio.create_task(bot._tiktok(CFG, http, m, tiktok.link(m))) for m in msgs]
        await asyncio.sleep(0.05)
        assert fetched == [URL, full] and len(tiktok._flights) == 2  # the second short link waits for the first
        gate.set()
        await asyncio.gather(*jobs)
        return http
    http = asyncio.run(go())
    sent = [b["video"] for b, _ in http.said("sendVideo")]
    assert sorted(sent) == ["fid", "fid", FORMAT["url"]] and fetched == [URL, full]
    assert {b["chat_id"] for b, _ in http.said("sendVideo")} == {-10, -11, -12}
    assert _routes(caplog) == ["cache", "cache", "url"] and tiktok._flights == {}


def test_dedupe_shares_nothing_there_but_not_a_failure(monkeypatch):
    """A link with nothing behind it is asked for once for everyone waiting; a failure lets the next one try itself."""
    asked = []

    async def go(answer):
        gate = asyncio.Event()

        async def fetch(http, url):
            asked.append(url)
            await gate.wait()
            if isinstance(answer, Exception):
                raise answer
            return answer
        monkeypatch.setattr(tiktok, "fetch", fetch)
        http = _Telegram()
        jobs = [asyncio.create_task(bot._tiktok(CFG, http, _msg(31 + i, mid=10 + i, chat={"type": "group", "id": -i}), URL))
                for i in range(3)]
        await asyncio.sleep(0.02)
        gate.set()
        await asyncio.gather(*jobs)
        return http
    http = asyncio.run(go(None))
    assert asked == [URL] and not http.said("sendVideo")
    asked.clear()
    http = asyncio.run(go(tiktok.SourceDown("tikwm")))
    assert asked == [URL] * 3 and not http.said("sendVideo") and tiktok._flights == {}


def test_dedupe_survives_a_cancelled_waiter_and_a_cancelled_first(monkeypatch):
    fetched = []

    async def go():
        gate = asyncio.Event()

        async def fetch(http, url):
            fetched.append(url)
            await gate.wait()
            return CLIP
        monkeypatch.setattr(tiktok, "fetch", fetch)
        http = _Telegram()
        start = lambda i: asyncio.create_task(bot._tiktok(CFG, http, _msg(31, mid=i, chat={"type": "group", "id": -i}), URL))  # noqa: E731
        first = start(1)
        await asyncio.sleep(0.01)
        waiter = start(2)
        await asyncio.sleep(0.01)
        waiter.cancel()  # gave up while waiting: the first one carries on, the flight is let go
        gate.set()
        await first
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert tiktok._flights == {} and fetched == [URL] and len(http.said("sendVideo")) == 1
        tiktok._files.clear()
        gate.clear()
        first, second = start(3), None
        await asyncio.sleep(0.01)
        second = start(4)
        await asyncio.sleep(0.01)
        first.cancel()  # the first one cancelled mid-fetch: the next one fetches itself, nothing hangs
        await asyncio.sleep(0.01)
        assert fetched == [URL, URL, URL]
        gate.set()
        await second
        assert tiktok._flights == {} and http.said("sendVideo")[-1][0]["chat_id"] == -4
    asyncio.run(go())


def test_a_slideshow_is_downloaded_once_for_every_chat(monkeypatch):
    downloads = []

    async def fetch(http, url):
        return ["https://v1.tiktokcdn.com/p/1.jpg", "https://v1.tiktokcdn.com/p/2.jpg"]

    async def photos(http, urls):
        downloads.append(urls)
        return [b"1", b"2"]
    monkeypatch.setattr(tiktok, "fetch", fetch)
    monkeypatch.setattr(tiktok, "photos", photos)
    http = _Telegram()
    for i in (1, 2):
        asyncio.run(bot._tiktok(CFG, http, _msg(31, mid=i, chat={"type": "group", "id": -i}), URL))
    (first, files), (again, none) = http.said("sendMediaGroup")
    assert len(downloads) == 1 and set(files) == {"p0", "p1"} and none is None
    assert again["media"] == [{"type": "photo", "media": "ph0"}, {"type": "photo", "media": "ph1"}]
    assert again["chat_id"] == -2 and again["reply_parameters"]["message_id"] == 2 and "caption" not in again


def test_per_person_caps_and_bounded_memory(monkeypatch):
    t = 1000
    assert all(tiktok.room(-1, t, user=7, video=f"v{i}") for i in range(tiktok.USER_CAP))
    assert not tiktok.room(-1, t, user=7, video="other") and not tiktok.room(-2, t, user=7, video="other")  # all chats
    # one person never takes the chat's whole budget: the others still have the rest of it
    assert all(tiktok.room(-1, t, user=8 + i, video="v") for i in range(tiktok.CHAT_CAP - tiktok.USER_CAP))
    assert not tiktok.room(-1, t, user=20, video="v")  # the chat's cap
    # the same person's same video: once a WINDOW in a chat (another group may get it); a refusal costs no budget
    assert tiktok.room(-3, t, user=30, video="same") and not tiktok.room(-3, t + 1, user=30, video="same")
    assert tiktok.room(-4, t + 2, user=30, video="same") and tiktok.room(-3, t + tiktok.WINDOW, user=30, video="same")
    # idle keys go, and there are never more than SENT_KEYS
    assert tiktok.room(-9, t + 10 * tiktok.WINDOW, user=1) and len(tiktok._sent) == 2
    monkeypatch.setattr(tiktok, "SENT_KEYS", 50)
    for i in range(200):
        tiktok.room(-100 - i, t + 10 * tiktok.WINDOW, user=i, video=str(i))
    assert len(tiktok._sent) == 50


def test_one_person_cannot_use_up_a_chat(env, monkeypatch):
    c, cfg = env
    cfg = dataclasses.replace(cfg, tiktok=True)
    links = [f"https://vm.tiktok.com/Z{i}/" for i in range(tiktok.CHAT_CAP)]
    _, asked = _hear(cfg, monkeypatch, *[_msg(31, url, mid=20 + i) for i, url in enumerate(links)],
                     _msg(32, URL, mid=40), _msg(32, URL, mid=41))  # the same link twice: answered once
    assert asked == [*links[:tiktok.USER_CAP], URL]


def test_fetch_has_a_wall_clock_limit(media_dns):
    """A server that sends a byte now and then (each read within its step timeout) is cut off at the deadline."""
    async def trickle():
        while True:
            yield b"x"
            await asyncio.sleep(0.02)

    async def go():
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=trickle()))
        async with httpx.AsyncClient(transport=transport) as http:
            start = time.monotonic()
            got = await download.fetch(http, "https://v1.tiktokcdn.com/v.mp4", download.TIKTOK_FILES, 10**9, seconds=0.2)
            return got, time.monotonic() - start
    got, took = asyncio.run(go())
    assert got is None and took < 2


def test_a_hanging_source_and_a_hanging_reply_time_out(monkeypatch, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    monkeypatch.setattr(tiktok, "REPLY_SECONDS", 0.2)

    async def fetch(http, url):
        await asyncio.sleep(30)
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = _Telegram()
    start = time.monotonic()
    asyncio.run(bot._tiktok(CFG, http, _msg(31), URL))
    assert time.monotonic() - start < 2 and not http.said("sendVideo") and _routes(caplog) == ["TimeoutError"]
    assert tiktok._flights == {}


def test_a_thread_past_its_deadline_keeps_its_slot_until_it_ends(monkeypatch):
    """yt-dlp runs in a thread, which can't be killed: the caller stops waiting at the deadline, the thread sees it
    (here: like a progress hook), and its slot frees only when it has really ended."""
    ended = []

    def work():
        try:
            while True:
                tiktok._limit({"downloaded_bytes": 1})  # raises Expired past the deadline
                time.sleep(0.01)
        finally:
            time.sleep(0.2)  # the thread is still busy for a while after the caller gave up
            ended.append(True)

    async def go():
        gate = asyncio.Semaphore(1)
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            await tiktok._threaded(gate, 0.1, work)
        assert time.monotonic() - start < 1 and gate.locked() and not ended
        with pytest.raises(TimeoutError):  # no second thread starts while the first one runs (the reply's deadline)
            async with asyncio.timeout(0.05):
                await tiktok._threaded(gate, 1, lambda: pytest.fail("ran beside a late thread"))
        while gate.locked():
            await asyncio.sleep(0.01)
        assert ended and await tiktok._threaded(gate, 1, lambda: 42) == 42
    asyncio.run(go())


def test_extraction_has_a_deadline(monkeypatch):
    monkeypatch.setattr(tiktok, "EXTRACT_SECONDS", 1)
    seen = []

    def extract(match):
        seen.append(tiktok._downloader().params["socket_timeout"])  # each read: never past the deadline either
        while True:
            tiktok._left()
            time.sleep(0.01)
    monkeypatch.setattr(tiktok, "_extract", extract)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(tiktok.fetch(None, SHORT))  # asyncio.run returns once the thread has ended too
    assert time.monotonic() - start < 5 and seen[0] <= 1


def _gone(pid: int, orphan: bool = False) -> bool:
    """The process no longer exists. An orphan (a killed child's child) counts once it is a zombie: reaping it is init's."""
    for _ in range(300):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        stat = Path(f"/proc/{pid}/stat")
        if orphan and stat.exists() and stat.read_text().rpartition(")")[2].split()[:1] == ["Z"]:
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def stuck_ffmpeg(tmp_path, monkeypatch):
    """An ffmpeg that starts a child of its own and never ends; it writes both process ids."""
    bin_dir, pids = tmp_path / "bin", tmp_path / "pids"
    bin_dir.mkdir()
    fake = bin_dir / "ffmpeg"
    fake.write_text('#!/bin/sh\nsleep 30 &\necho "$$ $!" > "$FAKE_PIDS"\nsleep 30\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_PIDS", str(pids))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))
    return pids, work


def test_a_stuck_ffmpeg_is_killed_with_its_children_and_leaves_no_files(monkeypatch, stuck_ffmpeg):
    pids, work = stuck_ffmpeg
    monkeypatch.setattr(tiktok, "FFMPEG_SECONDS", 2)  # time enough for the fake to start, under load too
    start = time.monotonic()
    assert tiktok.upload(tiktok.Version(FORMAT), VIDEO) is None
    assert time.monotonic() - start < 8
    ffmpeg, child = map(int, pids.read_text().split())
    assert _gone(ffmpeg) and _gone(child, orphan=True) and not list(work.iterdir())
    with pytest.raises(ChildProcessError):  # reaped: no zombie left for anyone to wait on
        os.waitpid(ffmpeg, os.WNOHANG)


def test_the_deadline_cuts_a_child_process_short(stuck_ffmpeg):
    pids, work = stuck_ffmpeg

    async def go():
        gate = asyncio.Semaphore(1)
        with contextlib.suppress(TimeoutError):  # the caller's limit and the child's are the same deadline
            assert await tiktok._threaded(gate, 2, tiktok.upload, tiktok.Version(FORMAT), VIDEO) is None
        while gate.locked():
            await asyncio.sleep(0.01)
    start = time.monotonic()
    asyncio.run(go())
    assert time.monotonic() - start < 8
    ffmpeg, child = map(int, pids.read_text().split())
    assert _gone(ffmpeg) and _gone(child, orphan=True) and not list(work.iterdir())


def test_ytdlp_children_are_bounded_by_the_deadline():
    """yt-dlp's own children (the YouTube challenge solver) wait no longer than the work's deadline."""
    from yt_dlp.utils import Popen
    tiktok._guard()
    pid = []

    def solve():
        with Popen(["sleep", "30"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            pid.append(proc.pid)
            proc.communicate_or_kill(b"")

    async def go():
        with pytest.raises((subprocess.TimeoutExpired, TimeoutError)):
            await tiktok._threaded(asyncio.Semaphore(1), 0.2, solve)
    start = time.monotonic()
    asyncio.run(go())
    assert time.monotonic() - start < 5 and _gone(pid[0])


def test_sizes_are_counted_on_the_bytes_that_arrive(media_dns):
    body = b"x" * 100

    def handle(req):
        if req.url.path == "/lies":  # says 10 bytes, sends 100
            return httpx.Response(200, headers={"Content-Length": "10"}, content=body)
        if req.url.path == "/chunked":  # says nothing
            async def chunks():
                for _ in range(10):
                    yield body[:10]
            return httpx.Response(200, content=chunks())
        if req.url.path == "/page":
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>")
        return httpx.Response(200, headers={"Content-Type": "video/mp4"}, content=body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            get = lambda path, cap, types=(): download.fetch(  # noqa: E731
                http, f"https://v1.tiktokcdn.com{path}", download.TIKTOK_FILES, cap, types=types)
            return [await get("/lies", 50), await get("/chunked", 50), await get("/chunked", 100),
                    await get("/page", 100, tiktok.MEDIA_TYPES), await get("/v.mp4", 100, tiktok.MEDIA_TYPES)]
    lies, chunked, fits, page, video = asyncio.run(go())
    assert lies is None and chunked is None and fits == body and page is None and video == body


def test_photo_caps_and_types(media_dns, monkeypatch):
    sizes = {"/p/big.jpg": tiktok.PHOTO_BYTES + 1}

    def handle(req):
        if req.url.path == "/p/page.jpg":
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>")
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, content=b"j" * sizes.get(req.url.path, 10))

    async def go(names):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            return await tiktok.photos(http, [f"https://v1.tiktokcdn.com/p/{n}.jpg" for n in names])
    assert asyncio.run(go(["big", "page", "ok"])) == [b"j" * 10]  # too large, not a photo: skipped
    assert len(asyncio.run(go([str(i) for i in range(20)]))) == tiktok.ALBUM
    monkeypatch.setattr(tiktok, "MAX_BYTES", 25)
    assert asyncio.run(go(["a", "b", "c"])) == []  # the album together past the cap: nothing


def test_url_cap_needs_a_known_size():
    assert not tiktok.Version({**FORMAT, "filesize": 0}).direct  # unknown: we download (counting) instead
    assert tiktok.Version(FORMAT).direct
    assert not tiktok.Version({**FORMAT, "filesize": tiktok.URL_BYTES + 1}).direct


def test_a_probe_refuses_a_page_and_learns_the_size(media_dns, movies):
    payload = movies("probe", "32x48")
    kinds = {"/v.mp4": "video/mp4", "/page.mp4": "text/html"}

    def handle(req):
        start, end = map(int, req.headers["range"][6:].split("-"))
        return httpx.Response(206, headers={"Content-Type": kinds[req.url.path],
                                            "Content-Range": f"bytes {start}-{len(payload) - 1}/{len(payload)}"},
                              content=payload[start:end + 1])
    video = {"url": "https://v1.tiktokcdn.com/v.mp4", "ext": "mp4", "protocol": "https"}
    page = {**video, "url": "https://v1.tiktokcdn.com/page.mp4"}

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            return await tiktok.versions(http, tiktok.Clip("tt:1", 0, [video, page]))
    (only,) = asyncio.run(go())
    assert only.video is video and video["filesize"] == len(payload) and "filesize" not in page


def test_duration_cap_for_ytdlp_sources(env, monkeypatch, movies):
    _, cfg = env
    reel = [_file_format("reel", host="scontent.cdninstagram.com")]
    assert not _source(monkeypatch, cfg, REEL, {"duration": tiktok.MAX_SECONDS + 1.5, "formats": reel})[1]
    assert _source(monkeypatch, cfg, REEL, {"duration": tiktok.MAX_SECONDS + 0.04, "formats": reel})[1]  # a full reel
    # the length the file itself has, whatever the listing said (yt-dlp's download writes a 0.25 s movie)
    from yt_dlp import YoutubeDL
    movie = movies("long", "32x48")
    monkeypatch.setattr(YoutubeDL, "dl", lambda dl, path, info: (Path(path).write_bytes(movie), (True, True))[1])
    monkeypatch.setattr(tiktok, "MAX_SECONDS", -0.9)
    assert tiktok.upload(tiktok.Version(_file_format("x", acodec="aac"))) is None
    monkeypatch.setattr(tiktok, "MAX_SECONDS", 10)
    assert tiktok.upload(tiktok.Version(_file_format("x", acodec="aac")))


@pytest.mark.parametrize("location, resolves", [
    ("https://localhost/x", None), ("https://127.0.0.1/x", None), ("https://169.254.169.254/latest", None),
    ("https://[::1]/x", None), ("http://v2.tiktokcdn.com/x", None), ("https://v2.tiktokcdn.com:8443/x", None),
    ("https://v2.tiktokcdn.com/x", "10.0.0.5"), ("https://v2.tiktokcdn.com/x", "169.254.169.254"),
    ("https://v2.tiktokcdn.com/x", "::ffff:127.0.0.1"), ("https://v2.tiktokcdn.com/x", "fd00::1"),
    ("https://v2.tiktokcdn.com/x", "100.64.0.1")])
def test_redirects_never_reach_inside(monkeypatch, location, resolves):
    """Each hop: on the allowlist, https on 443, and every address its name has public."""
    names = {"v1.tiktokcdn.com": ["93.184.216.34"], "v2.tiktokcdn.com": ["93.184.216.35", resolves]}

    async def addresses(host):
        return [a for a in names.get(host, ["93.184.216.36"]) if a]
    monkeypatch.setattr(download, "_addresses", addresses)
    seen = []

    def handle(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"Location": location})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            return await download.fetch(http, "https://v1.tiktokcdn.com/v.mp4", download.TIKTOK_FILES, 100)
    assert asyncio.run(go()) is None and seen == ["93.184.216.34"]


def test_media_urls_outside_the_source_are_dropped(monkeypatch):
    """yt-dlp's formats and covers, and tikwm's photos, only from the source's own hosts."""
    inside = _file_format("ok", protocol="https")
    outside = [_file_format("a", host="127.0.0.1", protocol="https"), _file_format("b", host="evil.example", protocol="https"),
               {**_file_format("c", protocol="https"), "url": "https://rr1.googlevideo.com.evil.example/c.mp4"},
               {**_file_format("d", protocol="https"), "url": "https://user@rr1.googlevideo.com/d.mp4"}]
    clip = tiktok.Clip("yt:1", 10, [*outside, inside], hosts=("googlevideo.com",), source="youtube")
    assert [v.video for v in asyncio.run(tiktok.versions(None, clip))] == [inside]

    def handle(req):
        return httpx.Response(200, json={"code": 0, "data": {"images": [
            "https://127.0.0.1/p/1.jpg", "https://v1.tiktokcdn.com.evil.example/p/2.jpg", "https://v1.tiktokcdn.com/p/3.jpg"]}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            return await tiktok.fetch(http, URL)
    monkeypatch.setattr(download, "_addresses", lambda host: asyncio.sleep(0, ["93.184.216.34"]))
    assert asyncio.run(go()) == ["https://v1.tiktokcdn.com/p/3.jpg"]


def test_ytdlp_connections_are_pinned(monkeypatch):
    """yt-dlp's own requests (its downloads, every redirect hop, extraction too) reach only public addresses, and in a
    download only the source's hosts: a refused hop never gets a connection."""
    import http.server
    import threading

    hits = []

    class Hop(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append((self.server.server_port, self.path))
            self.send_response(302)
            self.send_header("Location", self.server.location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hop) for _ in range(2)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    first, inner = (s.server_port for s in servers)
    names = {"a.googlevideo.com": "127.0.0.1", "b.googlevideo.com": "127.0.0.2", "evil.example": "10.1.2.3"}
    real_resolve, real_public = socket.getaddrinfo, download.public
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **kw: real_resolve(names.get(host, host), *a, **kw))
    monkeypatch.setattr(download, "public", lambda a: a == "127.0.0.1" or real_public(a))  # the first hop stands for a CDN

    def get(url):
        with tiktok._downloader() as dl:
            dl.urlopen(url).read()

    async def run(url, hosts):
        with pytest.raises(Exception) as caught:
            await tiktok._threaded(asyncio.Semaphore(1), 10, get, url, hosts=hosts)
        return caught.value

    try:
        for location, why in ((f"http://localhost:{inner}/", "host not allowed"),
                              (f"http://127.0.0.1:{inner}/", "host not allowed"),
                              (f"http://b.googlevideo.com:{inner}/", "address not public")):
            servers[0].location = location
            hits.clear()
            error = asyncio.run(run(f"http://a.googlevideo.com:{first}/v", ("googlevideo.com",)))
            assert why in str(error) and hits == [(first, "/v")]
        hits.clear()
        error = asyncio.run(run(f"http://evil.example:{inner}/", ()))  # extraction: any host, public addresses only
        assert "address not public" in str(error) and not hits
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def test_ytdlp_guard_is_installed():
    """The guard wraps the pinned yt-dlp's and urllib3's connection functions: if an upgrade moves them, this fails."""
    import urllib3.util.connection
    from yt_dlp.networking import _urllib
    from yt_dlp.utils import Popen
    tiktok._downloader().close()
    assert urllib3.util.connection.create_connection.guarded and _urllib.create_connection.guarded
    assert Popen.communicate_or_kill.guarded
    tiktok._guard()  # once only
    assert not getattr(urllib3.util.connection.create_connection.__closure__[0].cell_contents, "guarded", False)
    dl = tiktok._downloader()
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
    assert not FFmpegPostProcessor(dl).available  # yt-dlp never runs an ffmpeg of its own
    dl.close()


def test_breaker_rests_a_failing_source_and_tries_it_again(media_dns, monkeypatch, caplog):
    now = [1000.0]
    monkeypatch.setattr(tiktok, "_clock", lambda: now[0])
    hits, status = [], [503]

    async def handle(req):
        hits.append(1)
        if status[0] == "slow":
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={"code": -1})
        return httpx.Response(status[0], json={"code": 0, "data": {"play": "https://v1.tiktokcdn.com/v.mp4", "size": 10}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            get = lambda: tiktok.fetch(http, URL)  # noqa: E731
            for _ in range(tiktok.FAILURES):
                with pytest.raises(tiktok.SourceDown):
                    await get()
            with pytest.raises(tiktok.Paused):
                await get()
            assert len(hits) == tiktok.FAILURES
            now[0] += tiktok.REST - 1
            with pytest.raises(tiktok.Paused):
                await get()
            now[0] += 2  # rested: one request tries; it fails, and the source rests again
            with pytest.raises(tiktok.SourceDown):
                await get()
            with pytest.raises(tiktok.Paused):
                await get()
            assert len(hits) == tiktok.FAILURES + 1
            now[0] += tiktok.REST + 1  # while one tries, the others don't
            status[0] = "slow"
            trial = asyncio.create_task(get())
            await asyncio.sleep(0.02)
            with pytest.raises(tiktok.Paused):
                await get()
            assert await trial is None  # an answer (here: nothing to send) closes it
            status[0] = 200
            assert isinstance(await get(), tiktok.Clip)
            assert len(hits) == tiktok.FAILURES + 3
            # a trial that never reports (cancelled) can't keep the source shut for good
            for _ in range(tiktok.FAILURES):
                status[0] = 503
                with pytest.raises(tiktok.SourceDown):
                    await get()
            now[0] += tiktok.REST + 1
            status[0] = "slow"
            trial = asyncio.create_task(get())
            await asyncio.sleep(0.02)
            trial.cancel()
            with pytest.raises(asyncio.CancelledError):
                await trial
            now[0] += tiktok.REST + 1
            status[0] = 200
            assert await get()
    asyncio.run(go())
    assert [m for m in caplog.messages if "rests" in m] == [f"group video: tikwm rests {tiktok.REST}s"] * 2


def test_breaker_per_source_and_silent(monkeypatch, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    calls = []

    def extract(match):
        calls.append(match[0])
        raise RuntimeError("source down")
    monkeypatch.setattr(tiktok, "_extract", extract)
    for _ in range(tiktok.FAILURES):
        with pytest.raises(RuntimeError):
            asyncio.run(tiktok.fetch(None, SHORT))
    with pytest.raises(tiktok.Paused):
        asyncio.run(tiktok.fetch(None, SHORT))
    with pytest.raises(RuntimeError):  # Instagram is another source
        asyncio.run(tiktok.fetch(None, REEL))
    assert len(calls) == tiktok.FAILURES + 1
    http = _Telegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, SHORT), SHORT))
    assert [m for m, _, _ in http.calls] == ["sendChatAction"] and _routes(caplog) == ["Paused"]  # no words to anyone


def _ytdlp_error(kind: str):
    """yt-dlp's errors as they reach us: a DownloadError around what happened."""
    import io
    import sys
    from yt_dlp.networking import Response
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    from yt_dlp.utils import DownloadError, ExtractorError
    try:
        if kind == "private":
            raise ExtractorError("This content isn't available", expected=True)
        if kind == "network":
            raise ExtractorError("Unable to download webpage", cause=TransportError("reset"))
        if kind == "broken":
            raise ExtractorError("Unable to extract data")  # the site changed: the source is broken for everyone
        status = int(kind)
        raise ExtractorError("HTTP Error", cause=HTTPError(Response(io.BytesIO(b""), "https://x.example", {}, status=status)))
    except ExtractorError:
        return DownloadError("ERROR", sys.exc_info())


def test_what_counts_as_an_outage():
    assert not tiktok._outage(_ytdlp_error("private"))
    assert not any(tiktok._outage(_ytdlp_error(code)) for code in ("403", "404", "410"))
    assert all(tiktok._outage(_ytdlp_error(kind)) for kind in ("429", "500", "503", "network", "broken"))
    assert tiktok._outage(TimeoutError()) and tiktok._outage(tiktok.SourceDown("x")) and tiktok._outage(RuntimeError())


def test_a_bad_link_never_rests_a_source(monkeypatch):
    """Private, deleted, age-gated links: nothing to send, and the source is fine (one person can't shut it)."""
    calls = []

    def extract(match):
        calls.append(1)
        raise _ytdlp_error("private" if len(calls) % 2 else "404")
    monkeypatch.setattr(tiktok, "_extract", extract)
    for _ in range(3 * tiktok.FAILURES):
        assert asyncio.run(tiktok.fetch(None, REEL)) is None
    assert len(calls) == 3 * tiktok.FAILURES and tiktok._health["instagram"] == (0, 0.0)


def test_our_own_queue_is_not_a_source_failure(monkeypatch):
    """Seven links at once on a healthy source: they wait for the two extraction slots, and none of that waiting is
    the source's time or its failure."""
    monkeypatch.setattr(tiktok, "_extractors", asyncio.Semaphore(2))
    monkeypatch.setattr(tiktok, "EXTRACT_SECONDS", 0.3)

    def extract(match):
        time.sleep(0.2)
        return None
    monkeypatch.setattr(tiktok, "_extract", extract)

    async def go():
        return await asyncio.gather(*(tiktok.fetch(None, SHORT) for _ in range(7)))
    assert asyncio.run(go()) == [None] * 7 and tiktok._health["youtube"] == (0, 0.0)


def test_a_cancelled_call_is_not_counted(monkeypatch):
    def extract(match):
        time.sleep(0.2)
    monkeypatch.setattr(tiktok, "_extract", extract)

    async def go():
        job = asyncio.create_task(tiktok.fetch(None, SHORT))
        await asyncio.sleep(0.05)
        job.cancel()  # the reply's own deadline, or a shutdown
        with pytest.raises(asyncio.CancelledError):
            await job
    for _ in range(tiktok.FAILURES + 1):
        asyncio.run(go())
    assert tiktok._health.get("youtube", (0, 0.0))[0] == 0


def test_ytdlp_download_failures_count_once_per_clip(monkeypatch):
    from yt_dlp import YoutubeDL
    outcome = []

    def transfer(dl, path, info):
        raise outcome[0]
    monkeypatch.setattr(YoutubeDL, "dl", transfer)
    clip = lambda: tiktok.Clip("yt:1", 10, [], hosts=("googlevideo.com",), source="youtube")  # noqa: E731
    version = tiktok.Version(_file_format("v"))
    for gone in (tiktok.TooLarge("big"), _ytdlp_error("403"), _ytdlp_error("private")):  # this video, not the source
        outcome[:] = [gone]
        assert asyncio.run(tiktok.prepare_upload(None, clip(), version)) is None
    assert tiktok._health["youtube"] == (0, 0.0)
    outcome[:] = [_ytdlp_error("network")]
    one = clip()
    for _ in range(tiktok.FAILURES + 2):  # every version of one clip fails: one failure, never Paused mid-reply
        assert asyncio.run(tiktok.prepare_upload(None, one, version)) is None
    assert tiktok._health["youtube"][0] == 1
    for _ in range(tiktok.FAILURES - 1):
        assert asyncio.run(tiktok.prepare_upload(None, clip(), version)) is None
    with pytest.raises(tiktok.Paused):
        asyncio.run(tiktok.prepare_upload(None, clip(), version))


def test_a_resting_source_still_lets_a_later_version_go_by_url(monkeypatch, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    big = {**_file_format("big", 1080, 1920), "protocol": "https", "filesize": tiktok.URL_BYTES + 1}
    small = {**_file_format("small"), "protocol": "https"}
    got = tiktok.Clip("yt:aB1234567_-", 10, [small, big], hosts=("googlevideo.com",), source="youtube")

    async def fetch(http, url):
        return got
    monkeypatch.setattr(tiktok, "fetch", fetch)
    tiktok._health["youtube"] = (tiktok.FAILURES, time.monotonic() + 3600)
    http = _Telegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, SHORT), SHORT))
    assert [b["video"] for b, _ in http.said("sendVideo")] == [small["url"]] and _routes(caplog) == ["url"]


def test_a_format_available_only_past_the_deadline_is_skipped(monkeypatch):
    from yt_dlp import YoutubeDL
    monkeypatch.setattr(YoutubeDL, "dl", lambda *a: pytest.fail("yt-dlp would sleep until it is available"))
    later = tiktok.Version({**_file_format("v"), "available_at": time.time() + 3600})
    assert asyncio.run(tiktok._threaded(asyncio.Semaphore(1), 5, tiktok.upload, later)) is None


def test_a_slow_tiktok_download_leaves_the_remux_its_time(monkeypatch):
    monkeypatch.setattr(tiktok, "DOWNLOAD_SECONDS", 0.3)
    monkeypatch.setattr(tiktok, "REMUX_SECONDS", 0.5)
    remux = [0.1]

    async def fetch(http, url, hosts, cap, **kw):
        await asyncio.sleep(0.2)  # most of the download's time
        return VIDEO

    def upload(version, data):
        time.sleep(remux[0])
        return VIDEO, b"", {}
    monkeypatch.setattr(download, "fetch", fetch)
    monkeypatch.setattr(tiktok, "upload", upload)
    assert asyncio.run(tiktok.prepare_upload(None, CLIP, tiktok.Version(FORMAT))) == (VIDEO, b"", {})
    remux[0] = 0.8  # a remux out of time: this version gives None, the next one is still tried
    assert asyncio.run(tiktok.prepare_upload(None, CLIP, tiktok.Version(FORMAT))) is None


def test_the_guard_covers_every_handler_and_ignores_proxies(monkeypatch):
    from yt_dlp.networking import _requests, _websockets
    from yt_dlp.networking.common import _REQUEST_HANDLERS
    with tiktok._downloader() as dl:
        assert dl.params["proxy"] == ""  # HTTPS_PROXY / ALL_PROXY from the environment never apply
    assert _requests.create_connection.guarded and _websockets.create_connection.guarded
    monkeypatch.setitem(_REQUEST_HANDLERS, "CurlCFFI", object)  # e.g. curl_cffi installed: its own sockets
    with pytest.raises(RuntimeError):
        tiktok._downloader()


def test_failures_log_no_link_and_no_ids(monkeypatch, caplog):
    caplog.set_level("DEBUG")
    secret = "https://vm.tiktok.com/ZSecret9/"

    async def fetch(http, url):
        raise tiktok.SourceDown("tikwm")
    monkeypatch.setattr(tiktok, "fetch", fetch)
    msg = _msg(7777123, secret, mid=4242, chat={"type": "group", "id": -100987654})
    for _ in range(3):
        asyncio.run(bot._tiktok(CFG, _Telegram(), msg, secret))
    monkeypatch.setattr(tiktok, "REPLY_SECONDS", 0.05)
    monkeypatch.setattr(tiktok, "fetch", lambda http, url: asyncio.sleep(1))
    asyncio.run(bot._tiktok(CFG, _Telegram(), msg, secret))
    for _ in range(tiktok.FAILURES):
        tiktok._report("tikwm", False)
    assert caplog.messages and all(x not in caplog.text for x in ("ZSecret9", "7777123", "100987654", "4242"))


# --- Instagram carousels and photo posts (issue #170, task 2): one album, the items that fail left out. ---

POST = "https://www.instagram.com/p/Car_0-sel/"
IG = "https://scontent-ams2-1.cdninstagram.com"


def _image(width=8, height=8, kind="JPEG", mode="RGB") -> bytes:
    from io import BytesIO
    from PIL import Image
    out = BytesIO()
    Image.new(mode, (width, height)).save(out, kind)
    return out.getvalue()


def _shot(name, width=1080, height=1350, host=IG):
    """A photo item as yt-dlp's Instagram extractor lists it (no formats; its image sizes as thumbnails)."""
    return {"id": name, "title": "Post by x", "formats": [], "thumbnails": [
        {"url": f"{host}/{name}_small.jpg", "width": 320, "height": 400},
        {"url": f"{host}/{name}.jpg", "width": width, "height": height}]}


def _reel(name, duration=5.0, **kw):
    return {"id": name, "title": "Post by x", "duration": duration, "thumbnails": [{"url": f"{IG}/{name}_cover.jpg"}],
            "formats": [_file_format(name, host="scontent.cdninstagram.com", **kw)]}


def _post(monkeypatch, info, link=POST):
    """The Instagram extraction with a made-up yt-dlp answer (the pinned yt-dlp normalizes the videos' formats)."""
    from yt_dlp import YoutubeDL
    asked = []

    def extract(dl, url, *, download, process):
        assert not download and not process and dl.params["ignore_no_formats_error"]
        asked.append(url)
        return {"extractor": "fixture", "id": "post", "title": "post", **info}
    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    got = tiktok._extract(tiktok.LINK.match(link))
    assert asked == ["https://www.instagram.com/p/Car_0-sel/"]
    return got


def test_instagram_post_links():
    say = lambda text: tiktok.link({"text": text, "from": {"id": 1}})  # noqa: E731
    shapes = ("https://www.instagram.com/p/Car_0-sel/", "https://instagram.com/p/Car_0-sel",
              "https://www.instagram.com/some.one_1/p/Car_0-sel/", "https://www.instagram.com/some.one_1/reel/Car_0-sel/",
              "https://www.instagram.com/tv/Car_0-sel/")
    for url in shapes:
        assert say(f"look {url}?img_index=3 wow") == url and say(f"({url})") == url
        assert tiktok.key(url) == "ig:Car_0-sel"
    for url in ("https://www.instagram.com/stories/p/3141592653589793238/", "https://www.instagram.com/stories/someone/31415/",
                "https://www.instagram.com/share/p/BAcd1234/", "https://www.instagram.com/someone/reels/",
                "https://www.instagram.com/a/b/p/Car_0-sel/", "https://www.instagram.com/p/", "https://instagram.com/someone/tagged/",
                "https://notinstagram.com/p/Car_0-sel/", "https://www.instagram.com.example/p/Car_0-sel/",
                "https://www.instagram.com/explore/tags/p/", "https://www.instagram.com/p/Car_0-sel/c/1/",
                "https://www.instagram.com/some\u043eone/p/Car_0-sel/", "instagram.com/p/Car_0-sel/"):
        assert say(url) is None, url
    assert "(?<" not in tiktok.LINK.pattern  # no lookbehind (the web build refuses it; the server keeps it simple too)


def test_instagram_photo_posts_and_carousels(monkeypatch):
    # a photo post: one photo, its largest image on Instagram's own hosts
    got = _post(monkeypatch, _shot("one"))
    assert got == tiktok.Album("ig:Car_0-sel", [f"{IG}/one.jpg"]) and got.hosts == tiktok.INSTAGRAM_FILES
    # a carousel of photos, in its order; a photo only off Instagram's hosts is left out, a smaller one on them is taken
    off = _shot("off", host="https://evil.example")
    mixed_hosts = {**_shot("mixed"), "thumbnails": [{"url": f"{IG}/mixed_small.jpg", "width": 320, "height": 400},
                                                    {"url": "https://127.0.0.1/mixed.jpg", "width": 1080, "height": 1350}]}
    got = _post(monkeypatch, {"_type": "playlist", "entries": [_shot("a"), off, mixed_hosts, _shot("b")]})
    assert got.items == [f"{IG}/a.jpg", f"{IG}/mixed_small.jpg", f"{IG}/b.jpg"]
    # a mixed post: photos and videos in place; a video past MAX_SECONDS and one without formats or photo left out
    entries = [_shot("a"), _reel("v1"), _reel("long", duration=tiktok.MAX_SECONDS + 2),
               {"id": "x", "duration": 4, "formats": [], "thumbnails": [{"url": f"{IG}/cover.jpg"}]}, _shot("b"), _reel("v2")]
    got = _post(monkeypatch, {"_type": "playlist", "entries": entries})
    a, v1, b, v2 = got.items
    assert (a, b) == (f"{IG}/a.jpg", f"{IG}/b.jpg") and isinstance(v1, tiktok.Clip) and isinstance(v2, tiktok.Clip)
    assert v1.source == "instagram" and v1.hosts == tiktok.INSTAGRAM_FILES and v1.duration == 5
    assert [f["format_id"] for f in v1.formats] == ["v1"] and v2.formats[0]["url"].endswith("/v2.mp4")
    # 11 and more items: the first ten (Telegram's limit for an album)
    got = _post(monkeypatch, {"_type": "playlist", "entries": [_shot(str(i)) for i in range(12)]})
    assert got.items == [f"{IG}/{i}.jpg" for i in range(tiktok.ALBUM)]
    # a carousel with one video that can be sent is that video (by URL first, as a reel); nothing sendable: nothing
    got = _post(monkeypatch, {"_type": "playlist", "entries": [_reel("v1"), _reel("long", duration=999)]})
    assert isinstance(got, tiktok.Clip) and got.key == "ig:Car_0-sel"
    assert _post(monkeypatch, {"_type": "playlist", "entries": [off, {"formats": []}, "junk"]}) is None
    # an item yt-dlp fails on, or a link to elsewhere, is left out; the others still go
    real = tiktok._clip

    def clip(dl, entry, k, source):
        if entry["id"] == "bad":
            raise ValueError("unreadable")
        return real(dl, entry, k, source)
    monkeypatch.setattr(tiktok, "_clip", clip)
    elsewhere = {"_type": "url", "url": "https://instagram.com/p/Other", "thumbnail": f"{IG}/other.jpg"}
    got = _post(monkeypatch, {"_type": "playlist", "entries": [_reel("bad"), elsewhere, _shot("a"), _reel("v1")]})
    assert got.items[0] == f"{IG}/a.jpg" and len(got.items) == 2
    assert _post(monkeypatch, {"formats": [], "thumbnails": []}) is None


def test_sendable_photos():
    assert tiktok.sendable(_image()) and tiktok.sendable(_image(kind="PNG")) and tiktok.sendable(_image(kind="WEBP"))
    assert tiktok.sendable(_image(200, 10))  # 20:1
    assert not tiktok.sendable(_image(210, 10)) and not tiktok.sendable(_image(10, 210))
    assert not tiktok.sendable(_image(5001, 5000, "PNG", "1"))  # width and height past 10000 together
    assert not tiktok.sendable(_image(kind="GIF")) and not tiktok.sendable(b"\0\0\0\x18ftypheic" + b"x" * 64)
    assert not tiktok.sendable(b"") and not tiktok.sendable(_image()[:20])


TRACKS = {"duration": 5.4, "width": 720, "height": 1280, "vcodec": "h264", "acodec": "aac"}


def _uploads(monkeypatch, sizes: dict, fail=(), hang=(), pause=()):
    """prepare_upload made up: a version's file is its listed size; `fail` raise, `hang` never end, `pause` rest."""
    calls = []

    async def prepare(http, clip, version, *, cap=0):
        name = version.video["format_id"]
        calls.append((name, cap))
        if name in fail:
            raise tiktok.SourceDown("instagram")
        if name in pause:
            raise tiktok.Paused("instagram")
        if name in hang:
            await asyncio.sleep(3600)
        size = sizes.get(name, 100)
        return None if cap and size > cap else (b"v" * size, b"t" * 10, dict(TRACKS))
    monkeypatch.setattr(tiktok, "prepare_upload", prepare)
    return calls


def _ig_format(name, **kw):
    return _file_format(name, host="scontent.cdninstagram.com", protocol="https", **kw)


def _ig_clip(*formats):
    return tiktok.Clip("", 5, list(formats), hosts=tiktok.INSTAGRAM_FILES, source="instagram")


def _gather(album, photos=None, monkeypatch=None):
    if photos is not None:
        async def fake(http, urls, hosts=download.TIKTOK_FILES):
            assert hosts == album.hosts and len(urls) == 1
            p = photos.get(urls[0])
            return [p] if p else []
        monkeypatch.setattr(tiktok, "photos", fake)
    return asyncio.run(tiktok.gather(None, album))


def test_gather_skips_what_fails_and_keeps_the_order(monkeypatch, media_dns):
    """Photos over a fake transport: a missing one, a page, one too large, one Telegram can't take; a video that fails
    and one whose only stream is HEVC. The rest go, in the post's order."""
    good, wide = _image(), _image(210, 10)
    files = {"/a.jpg": good, "/big.jpg": good + b"x" * 64, "/wide.jpg": wide, "/b.jpg": good, "/heic.jpg": b"ftypheic"}

    def handle(req):
        if req.url.path == "/page.jpg":
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>")
        body = files.get(req.url.path)
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, content=body) if body else httpx.Response(404)
    monkeypatch.setattr(tiktok, "PHOTO_BYTES", len(good) + 1)
    calls = _uploads(monkeypatch, {}, fail=("broken",))
    hevc = _ig_clip(_ig_format("hevc", vcodec="hevc"))
    album = tiktok.Album("ig:x", [f"{IG}/a.jpg", f"{IG}/gone.jpg", _ig_clip(_ig_format("broken")),
                                  f"{IG}/page.jpg", f"{IG}/big.jpg", f"{IG}/wide.jpg", hevc, f"{IG}/heic.jpg",
                                  _ig_clip(_ig_format("ok")), f"{IG}/b.jpg"])

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            return await tiktok.gather(http, album)
    parts = asyncio.run(go())
    assert [(p.data[:1] if p.tracks else p.data) for p in parts] == [good, b"v", good]
    assert parts[1].thumb == b"t" * 10 and parts[1].tracks["width"] == 720
    assert [name for name, _ in calls] == ["broken", "ok"]  # the HEVC-only video has no version to try


def test_gather_keeps_one_request_within_the_size_budget(monkeypatch):
    """Photos first; then each video gets an even share of what is left, its best version within it, and a share it
    leaves unused goes to the next. An item too large for its share is left out, never the whole album."""
    monkeypatch.setattr(tiktok, "THUMB_BYTES", 10)
    monkeypatch.setattr(tiktok, "ALBUM_BYTES", 3020)
    photo = _image()
    fmt = lambda name, size, h=1280: _ig_format(name, width=720, height=h, filesize=size)  # noqa: E731
    sizes = {"big": 5000, "hd": 2500, "sd": 900, "small": 400, "unknown": 1000}
    calls = _uploads(monkeypatch, sizes)
    album = tiktok.Album("ig:x", [_ig_clip(fmt("big", 5000, 1920)), f"{IG}/p.jpg",
                                  _ig_clip(fmt("hd", 2500, 1920), fmt("sd", 900)), _ig_clip(fmt("small", 400))])
    parts = _gather(album, {f"{IG}/p.jpg": photo}, monkeypatch)
    left = 3020 - len(photo)
    # the first video's only version is past its third: left out; the second takes half of the rest (sd), the third the rest
    assert [len(p.data) for p in parts] == [len(photo), 900, 400]
    assert [c for c in calls] == [("sd", left // 2 - 10), ("small", left - 910 - 10)]
    assert sum(p.size for p in parts) <= tiktok.ALBUM_BYTES
    # photos past the budget: the later ones are left out
    monkeypatch.setattr(tiktok, "ALBUM_BYTES", 2 * len(photo))
    album = tiktok.Album("ig:x", [f"{IG}/{i}.jpg" for i in range(3)])
    assert len(_gather(album, {f"{IG}/{i}.jpg": photo for i in range(3)}, monkeypatch)) == 2


def test_upload_cap_reaches_the_download(monkeypatch):
    """prepare_upload's cap is the download's own: yt-dlp's max_filesize and progress hook, and the file's real size."""
    async def go():
        out = await tiktok._threaded(asyncio.Semaphore(1), 5, tiktok.upload, tiktok.Version(FORMAT),
                                     VIDEO, cap=len(VIDEO) - 1)
        seen = await tiktok._threaded(asyncio.Semaphore(1), 5,
                                      lambda: (tiktok._downloader().params["max_filesize"], tiktok._cap()), cap=77)
        return out, seen
    out, seen = asyncio.run(go())
    assert out is None and seen == (77, 77) and tiktok._cap() == tiktok.MAX_BYTES

    def over():
        tiktok._limit({"downloaded_bytes": 78})
    with pytest.raises(tiktok.TooLarge):
        asyncio.run(tiktok._threaded(asyncio.Semaphore(1), 5, over, cap=77))


def test_gather_sends_what_is_ready_by_its_deadline(monkeypatch):
    monkeypatch.setattr(tiktok, "ALBUM_SECONDS", 0.2)
    _uploads(monkeypatch, {}, hang=("slow",))
    album = tiktok.Album("ig:x", [_ig_clip(_ig_format("slow")), f"{IG}/p.jpg"])
    start = time.monotonic()
    parts = _gather(album, {f"{IG}/p.jpg": _image()}, monkeypatch)
    assert time.monotonic() - start < 2 and [p.tracks for p in parts] == [None]


class _AlbumTelegram(_Http):
    """Telegram answering each item of an album with its file id; `refuse(method, data)` may answer an error instead."""
    def __init__(self, refuse=None):
        super().__init__()
        self.refuse = refuse

    async def post(self, url, json=None, data=None, files=None, **_):
        method = url.rsplit("/", 1)[1]
        body = json if json is not None else data
        self.calls.append((method, body, files))
        if self.refuse and (error := self.refuse(method, body)):
            return _Resp({"ok": False, **error}, error.get("error_code", 400))
        if method == "sendMediaGroup":
            media = body["media"] if json is not None else __import__("json").loads(body["media"])
            return _Resp({"ok": True, "result": [
                {"video": {"file_id": f"vid-{m['media'].rsplit('/', 1)[-1]}"}} if m["type"] == "video"
                else {"photo": [{"file_id": "small"}, {"file_id": f"ph-{m['media'].rsplit('/', 1)[-1]}"}]} for m in media]})
        if method == "sendPhoto":
            return _Resp({"ok": True, "result": {"photo": [{"file_id": "ph-one"}]}})
        return _Resp({"ok": True, "result": {"video": {"file_id": "vid-one"}}})


def _mixed(monkeypatch, *items, photos=None):
    async def fetch(http, url):
        return tiktok.Album(tiktok.key(url), list(items))
    monkeypatch.setattr(tiktok, "fetch", fetch)
    photo = _image()
    _uploads(monkeypatch, {})

    async def fake(http, urls, hosts=download.TIKTOK_FILES):
        return [photo] if not (photos and urls[0] not in photos) else []
    monkeypatch.setattr(tiktok, "photos", fake)
    return photo


def test_mixed_post_is_one_album_in_its_topic(monkeypatch, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    photo = _mixed(monkeypatch, f"{IG}/a.jpg", _ig_clip(_ig_format("v")), f"{IG}/b.jpg")
    http = _AlbumTelegram()
    msg = _msg(31, f"look {POST}", mid=17, is_topic_message=True, message_thread_id=6)
    asyncio.run(bot._tiktok(CFG, http, msg, tiktok.link(msg)))
    ((form, files),) = http.said("sendMediaGroup")
    assert form["chat_id"] == -100 and form["message_thread_id"] == 6 and json.loads(form["reply_parameters"])["message_id"] == 17
    assert "caption" not in form and all("caption" not in m for m in json.loads(form["media"]))
    assert json.loads(form["media"]) == [
        {"type": "photo", "media": "attach://p0"},
        {"type": "video", "media": "attach://v1", "duration": 5, "width": 720, "height": 1280,
         "thumbnail": "attach://t1", "supports_streaming": True},
        {"type": "photo", "media": "attach://p2"}]
    assert {k: (v[1], v[2]) for k, v in files.items()} == {
        "p0": (photo, "image/jpeg"), "v1": (b"v" * 100, "video/mp4"), "t1": (b"t" * 10, "image/jpeg"), "p2": (photo, "image/jpeg")}
    assert http.said("sendChatAction")[0][0]["message_thread_id"] == 6
    assert _routes(caplog) == ["album"] and POST not in caplog.text
    # another chat: the same album by file ids, nothing downloaded again
    monkeypatch.setattr(tiktok, "fetch", lambda http, url: pytest.fail("fetched again"))
    asyncio.run(bot._tiktok(CFG, http, _msg(32, POST, mid=18, chat={"type": "group", "id": -5}), POST))
    (again, none), = [c for c in http.said("sendMediaGroup") if c[0]["chat_id"] == -5]
    assert none is None and again["reply_parameters"]["message_id"] == 18 and "caption" not in again
    assert again["media"] == [{"type": "photo", "media": "ph-p0"},
                              {"type": "video", "media": "vid-v1", "duration": 5, "width": 720, "height": 1280,
                               "supports_streaming": True},
                              {"type": "photo", "media": "ph-p2"}]


def test_one_item_left_goes_alone_and_none_left_sends_nothing(monkeypatch):
    # a photo post: one photo
    _mixed(monkeypatch, f"{IG}/a.jpg")
    http = _AlbumTelegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=3), POST))
    ((form, files),) = http.said("sendPhoto")
    assert set(files) == {"photo"} and "caption" not in form and not http.said("sendMediaGroup")
    assert tiktok.cached("ig:Car_0-sel") == (({"type": "photo", "media": "ph-one"},), 0)
    # a carousel where only its video came through: that video, uploaded with its thumbnail and size, then by id
    tiktok._files.clear()
    _mixed(monkeypatch, f"{IG}/gone.jpg", _ig_clip(_ig_format("v")), photos={"none"})
    http = _AlbumTelegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=4), POST))
    ((form, files),) = http.said("sendVideo")
    assert set(files) == {"video", "thumbnail"} and form["thumbnail"] == "attach://thumbnail" and form["width"] == 720
    asyncio.run(bot._tiktok(CFG, http, _msg(32, POST, mid=5, chat={"type": "group", "id": -7}), POST))
    body, none = http.said("sendVideo")[-1]
    assert none is None and body["video"] == "vid-one" and body["chat_id"] == -7 and body["height"] == 1280
    # every item failed: nothing at all, and nobody is told
    tiktok._files.clear()
    _mixed(monkeypatch, f"{IG}/gone.jpg", _ig_clip(_ig_format("hevc", vcodec="hevc")),
           photos={"none"})
    http = _AlbumTelegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=6), POST))
    assert [m for m, _, _ in http.calls] == ["sendChatAction"]


def test_telegram_refusing_one_item_sends_the_rest(monkeypatch):
    """Telegram refuses an album whole for one bad item and names it: once, the album goes without it (and only the
    items that went are remembered). An error naming nothing, or a second refusal: nothing, silently."""
    items = (f"{IG}/a.jpg", _ig_clip(_ig_format("v")), f"{IG}/b.jpg")
    _mixed(monkeypatch, *items)

    def refuse(method, body):
        if method == "sendMediaGroup" and "attach://v1" in body["media"]:
            return {"error_code": 400, "description": 'Bad Request: failed to send message #2 with the error message "VIDEO_CONTENT_TYPE_INVALID"'}
    http = _AlbumTelegram(refuse)
    asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=3), POST))
    first, second = http.said("sendMediaGroup")
    assert [m["media"] for m in json.loads(second[0]["media"])] == ["attach://p0", "attach://p1"] and set(second[1]) == {"p0", "p1"}
    assert [m["media"] for m in tiktok.cached("ig:Car_0-sel")[0]] == ["ph-p0", "ph-p1"]
    for description in ("Bad Request: wrong file identifier", 'Bad Request: failed to send message #9 with the error message "X"'):
        tiktok._files.clear()
        tiktok._sent.clear()
        http = _AlbumTelegram(lambda method, body, d=description: {"error_code": 400, "description": d})
        asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=3), POST))
        assert len(http.said("sendMediaGroup")) == 1 and not tiktok.cached("ig:Car_0-sel")
    http = _AlbumTelegram(lambda method, body: {"error_code": 400, "description": "failed to send message #1 with x"})
    asyncio.run(bot._tiktok(CFG, http, _msg(31, POST, mid=3), POST))
    assert len(http.said("sendMediaGroup")) == 2 and not http.said("sendPhoto") and not tiktok.cached("ig:Car_0-sel")


def test_the_same_post_at_once_is_gathered_once(monkeypatch):
    """Three chats, two link shapes of one post: one extraction, one download of its items, the others by file id."""
    gathered = []
    real = tiktok.gather

    async def go():
        gate = asyncio.Event()
        _mixed(monkeypatch, f"{IG}/a.jpg", _ig_clip(_ig_format("v")))
        fetch = tiktok.fetch

        async def slow(http, url):
            await gate.wait()
            return await fetch(http, url)

        async def gather(http, album):
            gathered.append(album.key)
            return await real(http, album)
        monkeypatch.setattr(tiktok, "fetch", slow)
        monkeypatch.setattr(tiktok, "gather", gather)
        http = _AlbumTelegram()
        links = (POST, "https://www.instagram.com/some.one/p/Car_0-sel/?img_index=2", POST)
        msgs = [_msg(31 + i, url, mid=10 + i, chat={"type": "group", "id": -10 - i}) for i, url in enumerate(links)]
        jobs = [asyncio.create_task(bot._tiktok(CFG, http, m, tiktok.link(m))) for m in msgs]
        await asyncio.sleep(0.05)
        assert list(tiktok._flights) == ["ig:Car_0-sel"]
        gate.set()
        await asyncio.gather(*jobs)
        return http
    http = asyncio.run(go())
    sent = http.said("sendMediaGroup")
    assert gathered == ["ig:Car_0-sel"] and len(sent) == 3 and sum(files is not None for _, files in sent) == 1
    assert {body["chat_id"] for body, _ in sent} == {-10, -11, -12} and tiktok._flights == {}


def test_album_items_follow_the_breaker_rules(monkeypatch):
    """A photo post is no outage; an item with nothing to send (gone, too large) is none either; an outage of several
    videos in one album counts once, as one clip's does; a resting source stops the videos and the photos still go."""
    from yt_dlp.networking.exceptions import TransportError
    from yt_dlp.utils import ExtractorError
    got = _post(monkeypatch, _shot("one"))
    assert isinstance(got, tiktok.Album) and tiktok._health == {}
    got = asyncio.run(tiktok.fetch(None, POST))
    assert isinstance(got, tiktok.Album) and tiktok._health["instagram"][0] == 0

    def run(error):
        def upload(version, source=None):
            if error is None:
                return None  # too large, not H.264 after all
            raise error
        monkeypatch.setattr(tiktok, "upload", upload)
        clips = [_ig_clip(_ig_format(f"v{i}"), _ig_format(f"w{i}", width=480, height=854)) for i in range(3)]
        return _gather(tiktok.Album("ig:x", [*clips, f"{IG}/p.jpg"]), {f"{IG}/p.jpg": _image()}, monkeypatch)
    for gone in (ExtractorError("This post is gone", expected=True), None):
        tiktok._health.clear()
        assert [p.tracks for p in run(gone)] == [None] and tiktok._health["instagram"][0] == 0
    tiktok._health.clear()
    assert [p.tracks for p in run(TransportError("reset"))] == [None] and tiktok._health["instagram"][0] == 1
    # resting: the first video is refused at once, the others are not even tried; the photo goes
    tried = _uploads(monkeypatch, {}, pause=("a", "b"))
    album = tiktok.Album("ig:x", [_ig_clip(_ig_format("a")), _ig_clip(_ig_format("b")), f"{IG}/p.jpg"])
    parts = _gather(album, {f"{IG}/p.jpg": _image()}, monkeypatch)
    assert [p.tracks for p in parts] == [None] and [name for name, _ in tried] == ["a"]


# --- Instagram stories with the owner's cookies (issue #170, task 3): nothing without INSTAGRAM_COOKIES, the session
# only to Instagram's own hosts, never written back, and its path and values in no log, error or reply. The cookies
# here are made up at run time: the repo holds no cookies-file line and no session value (test_no_cookies_in_the_repo).

STORY = "https://www.instagram.com/stories/some.one_1/3141592653589793238/"


def _line(domain, name, value, *, expires=0, subdomains="TRUE", secure="TRUE", path="/"):
    """One line of a browser's cookies export, put together at run time."""
    return "\t".join((domain, subdomains, path, secure, str(expires), name, value))


@pytest.fixture
def jar(tmp_path, monkeypatch):
    """A made-up cookies file, read-only, and INSTAGRAM_COOKIES naming it; `secrets`: what nothing may ever show."""
    mark = secrets.token_hex(6)
    path = tmp_path / f"owner-{mark}" / "cookies.txt"
    path.parent.mkdir()
    values = {name: f"{name}{secrets.token_hex(10)}" for name in ("sessionid", "csrftoken", "elsewhere", "cdn")}
    path.write_text("\n".join((
        "# a header and comments are skipped",
        _line(".instagram.com", "sessionid", values["sessionid"], expires=int(time.time()) + 86400),
        "#HttpOnly_" + _line("www.instagram.com", "csrftoken", values["csrftoken"], subdomains="FALSE", secure="FALSE"),
        _line(".facebook.com", "c_user", values["elsewhere"]), _line(".cdninstagram.com", "cdn", values["cdn"]),
        "not a cookie line", "")))
    path.chmod(0o400)
    monkeypatch.setenv(tiktok.COOKIES, str(path))
    return SimpleNamespace(path=path, values=values, secrets=(mark, str(path), *values.values()))


def _no_extraction(monkeypatch):
    calls = []

    async def threaded(*args, **kw):
        calls.append(args)
    monkeypatch.setattr(tiktok, "_threaded", threaded)
    return calls


def test_story_links_only_with_the_cookies(env, tmp_path, monkeypatch):
    say = lambda text: tiktok.link({"text": text, "from": {"id": 1}})  # noqa: E731
    shared = STORY + "?utm_source=ig_story_item_share&igsh=abc"
    # unset: exactly as before (a story is no link; a link after it still is), no request
    assert say(f"look {shared}") is None and say(f"{STORY} {REEL}") == REEL
    calls = _no_extraction(monkeypatch)
    assert asyncio.run(tiktok.fetch(None, STORY)) is None and not calls
    # set, but no readable file there (missing, a folder, a FIFO, no permission): the same
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    locked = tmp_path / "locked.txt"
    locked.write_text("x")
    locked.chmod(0)
    for path in (tmp_path / "missing.txt", tmp_path, fifo, *([locked] if os.geteuid() else [])):
        monkeypatch.setenv(tiktok.COOKIES, str(path))
        assert say(shared) is None and say(f"{STORY} {REEL}") == REEL
        assert asyncio.run(tiktok.fetch(None, STORY)) is None and not calls
    # a readable file: a story is a link (its query, the sharer's tracking id, left out)
    ok = tmp_path / "cookies.txt"
    ok.write_text("x")
    monkeypatch.setenv(tiktok.COOKIES, f" {ok} ")
    for url in (STORY, STORY.rstrip("/"), "https://instagram.com/stories/x/1/"):
        assert say(f"look {url}?igsh=abc wow") == url and say(f"({url})") == url
    assert say(f"{STORY} {REEL}") == STORY and tiktok.key(STORY) == "igs:3141592653589793238"
    for url in ("https://www.instagram.com/stories/highlights/18090946048123978/", "https://www.instagram.com/stories/someone/",
                "https://www.instagram.com/stories/someone/12ab/", "https://www.instagram.com/stories/some\u043eone/1/",
                "https://www.instagram.com/stories/someone/\u0661\u0662/", "https://www.instagram.com.example/stories/x/1/",
                "https://www.instagram.com/stories/a/b/1/", "https://m.instagram.com/stories/x/1/"):
        assert say(url) is None, url
    assert "(?<" not in tiktok.LINK.pattern
    # the bot, unset: the story is heard as no link at all, not even "sending a video..."
    monkeypatch.delenv(tiktok.COOKIES)
    _, cfg = env
    http, asked = _hear(dataclasses.replace(cfg, tiktok=True), monkeypatch, _msg(31, f"look {shared}"))
    assert asked == [] and not http.said("sendChatAction")


def test_the_cookies_file_is_read_strictly():
    """instagram.com's cookies only, each made secure (never over plain HTTP); expired, malformed, or another site's
    lines skipped without a word."""
    now = int(time.time())
    text = "\r\n".join((
        "# comment", "", _line(".instagram.com", "sessionid", "v1"),
        "#HttpOnly_" + _line("I.Instagram.COM", "ds_user_id", "42", expires=now + 60, secure="FALSE", subdomains="FALSE"),
        _line(".instagram.com", "old", "x", expires=now - 1), _line(".instagram.com", "soon", "x", expires="soon"),
        _line(".instagram.com.evil.example", "a", "x"), _line("evilinstagram.com", "b", "x"), _line(".facebook.com", "c", "x"),
        _line("instagram.com:443", "d", "x"), _line("", "e", "x"), _line("..instagram.com", "f", "x"),
        _line(".instagram.com", "g", "x", expires="1e9"), _line(".instagram.com", "h", "x", expires="\u0661"),
        _line(".instagram.com", "semi", "a;b"),
        _line(".instagram.com", "bad name", "x"), _line(".instagram.com", "ctl", "a\x0bb"),
        "\t".join((".instagram.com", "TRUE", "/", "TRUE", "0", "six"))))
    got = {c.name: c for c in tiktok._netscape(text)}
    assert set(got) == {"sessionid", "ds_user_id"}
    session, user = got["sessionid"], got["ds_user_id"]
    assert session.secure and user.secure and session.domain == ".instagram.com" and user.domain == "i.instagram.com"
    assert session.expires is None and session.discard and user.expires == now + 60 and user.has_nonstandard_attr("HttpOnly")
    assert not user.domain_specified and session.domain_specified


def test_a_story_through_the_session(jar, monkeypatch):
    """The session goes to yt-dlp as a jar (never a cookie file it would save to on close), scoped to Instagram and to
    HTTPS; the extraction's connections reach Instagram only; the owner's read-only file is never written, whatever
    Instagram's answers set; the story's video is fetched by us without the session and uploaded, never sent by URL."""
    from yt_dlp import YoutubeDL
    before = (jar.path.read_bytes(), jar.path.stat().st_mtime_ns, jar.path.stat().st_mode)
    seen = []
    leak = "sessionid=" + jar.values["sessionid"]

    def extract(dl, url, *, download, process):
        header = dl.cookiejar.get_cookie_header
        seen.append({"url": url, "params": dict(dl.params), "hosts": tiktok._bound.get().hosts,
                     "www": header("https://www.instagram.com/api/v1/feed/reels_media/"), "i": header("https://i.instagram.com/"),
                     "away": [header(u) for u in ("https://scontent.cdninstagram.com/v.mp4", "https://www.facebook.com/",
                                                  "https://www.instagram.com.evil.example/", "https://evil.example/",
                                                  "http://www.instagram.com/")]})
        dl.cookiejar.set_cookie(tiktok._netscape(_line(".instagram.com", "rur", "rotated"))[0])  # Instagram's Set-Cookie
        headers = {"Referer": "https://www.instagram.com/", "X-IG-App-ID": "936619743392459", "Cookie": leak}
        return {"extractor": "fixture", "id": "story", "title": "story", "duration": 5, "thumbnail": f"{IG}/cover.jpg",
                "formats": [_file_format("s", host="scontent.cdninstagram.com", protocol="https",
                                         cookies=leak + "; Domain=.instagram.com", http_headers=headers)]}
    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    got = asyncio.run(tiktok.fetch(None, STORY))
    (call,) = seen
    assert call["url"] == STORY and call["hosts"] == tiktok.SESSION_HOSTS
    assert "cookiefile" not in call["params"] and call["params"]["allowed_extractors"] == ["instagram:story"]
    assert jar.values["sessionid"] in call["www"] and jar.values["csrftoken"] in call["www"]
    assert jar.values["sessionid"] in call["i"] and jar.values["csrftoken"] not in call["i"]  # www's own cookie
    assert not any(jar.values[k] in call["www"] + call["i"] for k in ("elsewhere", "cdn"))  # other sites' lines dropped
    assert call["away"] == [None] * 5  # a CDN, another site, a look-alike, plain HTTP: no cookie
    assert (jar.path.read_bytes(), jar.path.stat().st_mtime_ns, jar.path.stat().st_mode) == before
    assert set(tiktok._health) == {tiktok.SIGNED}  # its own breaker
    assert isinstance(got, tiktok.Clip) and got.key == "igs:3141592653589793238" and got.private and got.cover == ""
    assert got.source == "instagram" and got.hosts == tiktok.INSTAGRAM_FILES
    (f,) = got.formats
    assert "cookies" not in f and {k.lower() for k in f["http_headers"]} <= tiktok._PLAIN_HEADERS
    assert f["http_headers"]["Referer"] == "https://www.instagram.com/"
    (version,) = asyncio.run(tiktok.versions(None, got))
    assert version.private and not version.direct  # Telegram never gets a URL found with the session
    # the reply: uploaded by us, no URL, no cover, no caption
    asked = _uploads(monkeypatch, {"s": 100})

    async def fetch(http, url):
        return got
    monkeypatch.setattr(tiktok, "fetch", fetch)
    http = _Telegram()
    asyncio.run(bot._tiktok(CFG, http, _msg(31, STORY), STORY))
    ((body, files),) = http.said("sendVideo")
    assert asked == [("s", 0)] and set(files) == {"video", "thumbnail"} and "caption" not in body
    assert not any(isinstance(v, str) and "cdninstagram" in v for v in body.values()) and "cover" not in body


def test_a_signed_in_downloader_reaches_instagram_only(jar, monkeypatch):
    """Even a redirect from Instagram itself can't take the signed-in downloader elsewhere (Task 1's guard with the
    session's hosts), and the session never goes over plain HTTP, not even to Instagram."""
    import http.server
    import threading
    hits = []

    class Hop(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append((self.headers.get("Host").split(":")[0], self.headers.get("Cookie")))
            self.send_response(302)
            self.send_header("Location", self.server.location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hop) for _ in range(2)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    first, inner = (s.server_port for s in servers)
    real_resolve, real_public = socket.getaddrinfo, download.public
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **kw: real_resolve(
        "127.0.0.1" if host in ("www.instagram.com", "scontent.cdninstagram.com", "evil.example") else host, *a, **kw))
    monkeypatch.setattr(download, "public", lambda a: a == "127.0.0.1" or real_public(a))

    def get(url):
        with tiktok._signed_in(tiktok._cookies()) as dl:
            dl.urlopen(url).read()

    async def run(url):
        with pytest.raises(Exception) as caught:
            await tiktok._threaded(asyncio.Semaphore(1), 10, get, url, hosts=tiktok.SESSION_HOSTS, source=tiktok.SIGNED)
        return caught.value
    try:
        for away in ("scontent.cdninstagram.com", "evil.example"):
            servers[0].location = f"http://{away}:{inner}/v.mp4"
            hits.clear()
            error = asyncio.run(run(f"http://www.instagram.com:{first}/stories/x/1/"))
            assert "host not allowed" in str(error) and hits == [("www.instagram.com", None)]
        hits.clear()
        assert "host not allowed" in str(asyncio.run(run(f"http://evil.example:{inner}/"))) and not hits
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def test_a_post_only_signed_in_readers_see(jar, monkeypatch):
    """A post first as today, without the session; only when Instagram keeps it from anonymous readers (login-only,
    rate-limited, private) once more with it. An outage is no reason to try the session; unset: exactly as before."""
    from yt_dlp import YoutubeDL
    from yt_dlp.networking.exceptions import TransportError
    from yt_dlp.utils import ExtractorError
    calls, outcome = [], []

    def extract(dl, url, *, download, process):
        signed = any(c.name == "sessionid" for c in dl.cookiejar)
        calls.append((url, signed, tiktok._bound.get().hosts))
        if not signed and outcome[0]:
            raise outcome[0]
        return {"extractor": "fixture", "id": "post", "title": "post", **_reel("v1")}
    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    canonical = "https://www.instagram.com/p/Re_123-4/"
    outcome[:] = [ExtractorError("This content is only available for registered users", expected=True)]
    got = asyncio.run(tiktok.fetch(None, REEL))
    assert calls == [(canonical, False, ()), (canonical, True, tiktok.SESSION_HOSTS)]
    assert isinstance(got, tiktok.Clip) and got.private and got.key == "ig:Re_123-4" and "cookies" not in got.formats[0]
    assert tiktok._health == {"instagram": (0, 0.0), tiktok.SIGNED: (0, 0.0)}
    calls.clear()
    outcome[:] = [None]  # anonymous readers see it: the session is never used
    got = asyncio.run(tiktok.fetch(None, REEL))
    assert calls == [(canonical, False, ())] and not got.private
    calls.clear()
    outcome[:] = [TransportError("reset")]
    with pytest.raises(TransportError):
        asyncio.run(tiktok.fetch(None, REEL))
    assert calls == [(canonical, False, ())] and tiktok._health["instagram"][0] == 1
    calls.clear()
    monkeypatch.delenv(tiktok.COOKIES)
    outcome[:] = [ExtractorError("login required", expected=True)]
    assert asyncio.run(tiktok.fetch(None, REEL)) is None and calls == [(canonical, False, ())]


def test_a_dead_session_never_rests_reels(jar, monkeypatch, caplog):
    """Signed-in extractions have their own breaker. An expired session (Instagram signs it out, yt-dlp sees the
    login page) is no outage at all: no reply, one hint an hour for the owner. An outage of the signed-in requests
    (a checkpoint, a 429 for the account) rests stories alone, for REST, then a story tries again; reels never wait."""
    from yt_dlp import YoutubeDL
    from yt_dlp.networking.exceptions import TransportError
    from yt_dlp.utils import ExtractorError
    now = [1000.0]
    monkeypatch.setattr(tiktok, "_clock", lambda: now[0])
    mode = ["expired"]

    def extract(dl, url, *, download, process):
        if not any(c.name == "sessionid" for c in dl.cookiejar):
            return {"extractor": "fixture", "id": "post", "title": "post", **_reel("v1")}
        if mode[0] == "expired":
            dl.cookiejar.clear(".instagram.com", "/", "sessionid")
            raise ExtractorError("You need to log in to access this content", expected=True)
        raise TransportError("checkpoint")
    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    for _ in range(tiktok.FAILURES + 2):
        assert asyncio.run(tiktok.fetch(None, STORY)) is None
    assert tiktok._health[tiktok.SIGNED] == (0, 0.0)
    hints = [m for m in caplog.messages if "Instagram cookies" in m]
    assert hints == ["group video: the Instagram cookies were signed out; stories wait for new ones (README)"]
    mode[0] = "outage"
    for _ in range(tiktok.FAILURES):
        with pytest.raises(TransportError):
            asyncio.run(tiktok.fetch(None, STORY))
    with pytest.raises(tiktok.Paused):
        asyncio.run(tiktok.fetch(None, STORY))
    assert isinstance(asyncio.run(tiktok.fetch(None, REEL)), tiktok.Clip)  # reels go on
    assert tiktok._health["instagram"] == (0, 0.0)
    now[0] += tiktok.REST + 1
    mode[0] = "expired"
    assert asyncio.run(tiktok.fetch(None, STORY)) is None and tiktok._health[tiktok.SIGNED] == (0, 0.0)
    now[0] += 3600
    asyncio.run(tiktok.fetch(None, STORY))
    assert len([m for m in caplog.messages if "were signed out" in m]) == 2  # once an hour


def test_the_session_is_used_sparingly(jar, monkeypatch, caplog):
    """SESSION_CAP signed-in extractions an hour, all chats together: past it, nothing is asked (one hint an hour)."""
    now = [1000.0]
    monkeypatch.setattr(tiktok, "_clock", lambda: now[0])
    monkeypatch.setattr(tiktok, "SESSION_CAP", 3)
    calls = []

    def signed(match):
        calls.append(match[0])
    monkeypatch.setattr(tiktok, "_signed", signed)
    for _ in range(5):
        assert asyncio.run(tiktok.fetch(None, STORY)) is None
        now[0] += 60
    assert len(calls) == 3 and len([m for m in caplog.messages if "hourly cap" in m]) == 1
    now[0] += 3600 - 4 * 60
    asyncio.run(tiktok.fetch(None, STORY))
    assert len(calls) == 4


def test_story_failures_are_silent_and_show_no_path_or_cookie(env, jar, monkeypatch, caplog, capfd):
    """Every way a story can fail, with every log at DEBUG and the process's own output captured: the bot says
    nothing, and the cookies' path and values appear in no log line, no traceback, no output, no request to Telegram
    and no database row, even when yt-dlp's errors carry them."""
    from yt_dlp import YoutubeDL
    from yt_dlp.networking.exceptions import TransportError
    from yt_dlp.utils import DownloadError, ExtractorError
    caplog.set_level("DEBUG")
    caplog.set_level("DEBUG", logger="uvicorn.error")
    _, cfg = env
    leak = " ".join(jar.secrets)
    errors = [ExtractorError(f"login required {leak}", expected=True),
              ExtractorError(f"Unable to download {leak}", cause=TransportError(f"reset {leak}")),
              DownloadError(f"ERROR: {leak}"), OSError(leak), ExtractorError(f"broken {leak}")]
    extracted = []

    def extract(dl, url, *, download, process):
        extracted.append(url)
        raise errors[len(extracted) - 1]
    monkeypatch.setattr(YoutubeDL, "extract_info", extract)
    replies = []

    def ask():
        http = _Telegram()
        msg = _msg(31, f"look {STORY}")
        if url := tiktok.link(msg):
            asyncio.run(bot._tiktok(CFG, http, msg, url))
        replies.extend(c for c in http.calls if c[0] != "sendChatAction")
        return http
    for _ in errors:
        ask()
    assert len(extracted) == len(errors)

    def rewrite(data: bytes):
        jar.path.chmod(0o600)
        jar.path.write_bytes(data)
    rewrite(_line(".instagram.com", "csrftoken", jar.values["csrftoken"]).encode())  # no session in it
    ask()
    rewrite(b"#" * (tiktok.COOKIE_BYTES + 1))
    ask()
    rewrite(b"\xff\xfe" + leak.encode() + b"\x00\t\t\t")
    ask()
    if os.geteuid():
        jar.path.chmod(0)
        tiktok._told.clear()
        ask()
    jar.path.unlink()  # gone between the message and the extraction: the call-time check finds nothing
    asyncio.run(bot._tiktok(CFG, _Telegram(), _msg(31, STORY), STORY))
    # gone, or a FIFO, between that check and the read itself: the read's own error (it names the path) is dropped
    monkeypatch.setattr(tiktok, "_cookie_path", lambda: str(jar.path))
    for make in (lambda: None, lambda: os.mkfifo(jar.path)):
        make()
        tiktok._told.clear()
        http = _Telegram()
        asyncio.run(bot._tiktok(CFG, http, _msg(31, STORY), STORY))
        assert any("can't be read" in m for m in tiktok._told) and [m for m, _, _ in http.calls] == ["sendChatAction"]
    assert len(extracted) == len(errors) and replies == []  # no reply, no words, ever
    out, err = capfd.readouterr()
    import logging
    shown = [caplog.text, out, err, *(r.getMessage() for r in caplog.records),
             *(logging.Formatter().formatException(r.exc_info) for r in caplog.records if r.exc_info)]
    con = db.connect(cfg.db_path)
    shown.append("\n".join(con.iterdump()))
    con.close()
    assert not [s for s in jar.secrets for text in shown if s in text]
    hints = {m for m in caplog.messages if "Instagram cookies" in m}
    assert hints == {f"group video: the Instagram cookies {why}; stories wait for new ones (README)"
                     for why in ("hold no session", "can't be read")}
    assert any(m.startswith("group video ") for m in caplog.messages)  # the routes are still logged (types only)


def test_no_cookies_in_the_repo():
    """`git grep`'s view: no tracked file holds a line of a cookies export or an Instagram session value."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("not a git checkout")
    line = re.compile(rb"^(?:#HttpOnly_)?[^\s#]+\t(?:TRUE|FALSE)\t[^\t\n]*\t(?:TRUE|FALSE)\t\d*\t[^\t\n]+\t", re.M | re.I)
    session = re.compile(rb"\d{5,}(?:%3A|:)[A-Za-z0-9]{8,}(?:%3A|:)\d+(?:%3A|:)")
    bad = []
    for name in filter(None, listed.stdout.split(b"\0")):
        path = root / name.decode()
        if path.is_file() and (line.search(data := path.read_bytes()) or session.search(data)):
            bad.append(name.decode())
    assert bad == []
