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
from collections import OrderedDict
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
    monkeypatch.setattr(tiktok, "_files", OrderedDict())
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
    assert all(tiktok.room(-1, 1000) for _ in range(tiktok.CHAT_CAP))
    assert not tiktok.room(-1, 1001) and tiktok.room(-2, 1001)  # chats apart
    assert tiktok.room(-1, 1061)  # a minute later


def test_fetch(media_dns):
    assert _fetch(_tikwm()).formats[0]["url"] == "https://v1.tiktokcdn.com/v.mp4"
    assert _fetch(_tikwm({"code": -1, "msg": "Url parsing is failed!"})) is None  # private or deleted
    assert _fetch(_tikwm(status=503)) is None
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
          "height": 1280, "vcodec": "avc1", "acodec": "aac"}
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
    http, _ = _hear(cfg, monkeypatch, _msg(31, mid=11), fetched=["a"])
    ((one_, files),) = http.said("sendPhoto")
    assert files == {"photo": ("tiktok.jpg", b"a", "image/jpeg")} and json.loads(one_["reply_parameters"])["message_id"] == 11
    http, _ = _hear(cfg, monkeypatch, _msg(31, mid=12), fetched=["a", "b", "c"])
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
    return {"width": width, "height": height, "ext": ext, "url": f"https://v1.tiktokcdn.com/{name}.{ext}",
            "format_id": name, "vcodec": "avc1", "acodec": "aac", **kw}


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
    entry = {"id": "slide", "title": "slide", "duration": 4, "formats": [_file_format("silent", acodec="none")]}
    url, ((body, _),) = _source(monkeypatch, cfg, REEL, {"_type": "playlist", "entries": [{"formats": []}, entry, entry]})
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
