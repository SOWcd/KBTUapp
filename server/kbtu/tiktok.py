"""Captionless group video replies. Resolve and compare source formats before transferring a video."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import download

API = "https://www.tikwm.com/api/"
LINK = re.compile(
    r"https?://(?:"
    r"(?P<tiktok>(?:(?:www|m|vm|vt)\.)?tiktok\.com/[^\s<>\"']+)|"
    r"(?:(?:(?:www|m)\.)?youtube\.com/shorts/|(?P<short_host>(?:www\.)?youtu\.be)/)(?P<youtube>(?a:[\w-]{11}))"
    r"|(?:www\.)?instagram\.com/(?:reels?|p)/(?P<instagram>(?a:[\w-]+))"
    r")/?(?=$|[\s?#.,!;:)\]}<>\"'])", re.I)
MAX_BYTES = 50 * 1024 * 1024  # the most a bot may upload
URL_BYTES = 20 * 1024 * 1024  # the most Telegram fetches by URL itself
PHOTO_BYTES = 10 * 1024 * 1024  # and one photo
ALBUM = 10                    # photos in one album at most
MAX_SECONDS = 180             # the longest yt-dlp source (a Short's limit; an Instagram reel's too)
MEDIA_TYPES = ("video/", "audio/", "application/mp4", "application/octet-stream", "binary/octet-stream")
PHOTO_TYPES = ("image/",)
log = logging.getLogger("kbtu.tiktok")
# Wall-clock limits, end to end however slowly a source answers (each request step: download.TIMEOUT).
TIMEOUT = 30                  # seconds for one source request (tikwm, one probe)
EXTRACT_SECONDS = 60          # one yt-dlp extraction
DOWNLOAD_SECONDS = 150        # the chosen streams, their remux and thumbnail
REPLY_SECONDS = 300           # one link, from the first request to Telegram's last answer
FFMPEG_SECONDS = 60           # each child process, and never past the deadline of the work it is part of
_extractors = asyncio.Semaphore(2)  # leave the shared thread pool available to receipts and other bot updates
_transfers = asyncio.Semaphore(2)
_probes = asyncio.Semaphore(4)
CHAT_CAP = 5                  # answers a chat a minute: a burst of links never turns the chat into a feed
USER_CAP = 3                  # answers one person gets a minute, all chats together: never a chat's whole CHAT_CAP
WINDOW = 60                   # seconds the caps count over; the same person's same video again only after it
SENT_KEYS = 4096
# ponytail: per worker (the bot polls in one); a table if that changes. Keys idle for a WINDOW are pruned, and the
# least recently used go past SENT_KEYS (a chat, a person, a person's video: ~1400 answers a minute to reach it).
_sent: OrderedDict[tuple, list[float]] = OrderedDict()


def link(msg: dict) -> str | None:
    """The first supported link a person wrote (the text or a caption). Never a bot's: another downloader bot answers its
    links with a video too, and two such bots would answer each other. Never the channel's own copy of a post in its
    discussion group: the post is the channel's, not a message someone sent to the chat."""
    if (msg.get("from") or {}).get("is_bot") or msg.get("is_automatic_forward"):
        return None
    m = LINK.search(str(msg.get("text") or msg.get("caption") or ""))
    return m.group(0) if m else None


def room(chat: int, now: float | None = None, *, user: int = 0, video: str = "") -> bool:
    """One more answer this minute in this chat (CHAT_CAP) and for this person (USER_CAP), and not this person's same
    video (key) again within WINDOW. Counted only when all three say yes."""
    now = time.time() if now is None else now
    while _sent and now - next(iter(_sent.values()))[-1] >= WINDOW:
        _sent.popitem(last=False)
    caps = {("chat", chat): CHAT_CAP, ("user", user): USER_CAP}
    if video:
        caps[("same", user, video)] = 1
    recent = {k: [t for t in _sent.get(k, ()) if now - t < WINDOW] for k in caps}
    if any(len(recent[k]) >= cap for k, cap in caps.items()):
        return False
    for k in caps:
        _sent[k] = [*recent[k], now]
        _sent.move_to_end(k)
    while len(_sent) > SENT_KEYS:
        _sent.popitem(last=False)
    return True


class Paused(Exception):
    """The source failed FAILURES times in a row and rests: no request goes to it (and nobody is told)."""


class SourceDown(Exception):
    """The source did not answer (a network error, a timeout, a server error, a body that is not its answer)."""


FAILURES = 5   # in a row, then the source rests
REST = 180     # seconds; then one request tries it, and the others wait for that one's answer
_clock = time.monotonic
_health: dict[str, tuple[int, float]] = {}  # source -> (failures in a row, resting until)


def _ready(source: str) -> bool:
    failures, until = _health.get(source, (0, 0.0))
    if failures < FAILURES:
        return True
    if _clock() < until:
        return False
    _health[source] = (failures, _clock() + REST)  # this one tries; if it never reports, another may after REST
    return True


def _report(source: str, ok: bool) -> None:
    failures = 0 if ok else _health.get(source, (0, 0.0))[0] + 1
    if failures == FAILURES:
        log.warning("group video: %s rests %ds", source, REST)
    _health[source] = (failures, _clock() + REST if failures >= FAILURES else 0.0)


@contextmanager
def _source(name: str):
    """A call to a source through its circuit breaker: an exception (a timeout too) counts as its failure."""
    if not _ready(name):
        raise Paused(name)
    ok = False
    try:
        yield
        ok = True
    finally:
        _report(name, ok)


class _Flight:
    def __init__(self):
        self.lock, self.users, self.runs, self.gone = asyncio.Lock(), 0, 0, False


_flights: dict[str, _Flight] = {}


@asynccontextmanager
async def flight(k: str):
    """One request at a time per video key: whoever comes while it is being fetched waits, then finds its file id in
    the cache (or `gone`: the source had nothing). `runs` counts who held it before. Kept only while in use."""
    f = _flights.setdefault(k, _Flight())
    f.users += 1
    try:
        async with f.lock:
            try:
                yield f
            finally:
                f.runs += 1
    finally:
        f.users -= 1
        if not f.users and _flights.get(k) is f:
            del _flights[k]


@dataclass
class Clip:
    key: str
    duration: float
    formats: list[dict]
    cover: str = ""
    hosts: tuple[str, ...] = download.TIKTOK_FILES
    source: str = "tikwm"


@dataclass
class Version:
    video: dict
    audio: dict | None = None

    @property
    def size(self) -> int:
        return _size(self.video) + _size(self.audio or {})

    @property
    def direct(self) -> bool:
        """Telegram may fetch it by URL: one file, its size known (a server's header, not only a listing) and small."""
        f = self.video
        return (not self.audio and f["protocol"] == "https" and f.get("ext") == "mp4" and 0 < self.size <= URL_BYTES
                and bool(f.get("vcodec") and f.get("acodec") and f.get("width") and f.get("height")))


def _size(f: dict) -> int:
    return int(f.get("filesize") or f.get("filesize_approx") or 0)


CACHE_SIZE = 512
_files: OrderedDict[str, tuple[str | tuple[str, ...], float]] = OrderedDict()  # a video's file id, or a slideshow's photos'


def key(url: str) -> str:
    m = LINK.match(url)
    if m["youtube"]:
        return "yt:" + m["youtube"]
    if m["instagram"]:
        return "ig:" + m["instagram"]
    parts = urlsplit(url)
    if found := re.fullmatch(r"/@[^/]+/video/(\d+)/?", parts.path):
        return "tt:" + found[1]
    if parts.hostname in ("vm.tiktok.com", "vt.tiktok.com") and re.fullmatch(r"/[\w-]+/?", parts.path):
        return parts.hostname + parts.path.rstrip("/")
    # Other short links can depend on their query. Keep a bounded alias without storing the shared URL.
    return "link:" + hashlib.sha256(url.encode()).hexdigest()


def cached(k: str) -> tuple[str | tuple[str, ...], float] | None:
    if entry := _files.get(k):
        _files.move_to_end(k)
        return entry
    return None


def forget(k: str) -> None:
    _files.pop(k, None)


def remember(k: str, file_id: str | tuple[str, ...], duration: float) -> None:
    if k:
        _files[k] = (file_id, duration)
        _files.move_to_end(k)
        if len(_files) > CACHE_SIZE:
            _files.popitem(last=False)


class TooLarge(ValueError):
    pass


class Expired(TimeoutError):
    """The work's deadline passed (raised inside its thread)."""


@dataclass(frozen=True)
class _Bound:
    end: float                    # time.monotonic() deadline
    hosts: tuple[str, ...] = ()   # the hosts its connections may reach; () any (each connection: public addresses only)


_bound: ContextVar[_Bound | None] = ContextVar("tiktok_bound", default=None)  # set for work run by _threaded


def _left() -> float:
    """Seconds left for this thread's work (inf outside _threaded); Expired once none are."""
    bound = _bound.get()
    if bound is None:
        return math.inf
    left = bound.end - time.monotonic()
    if left <= 0:
        raise Expired("deadline")
    return left


async def _threaded(gate: asyncio.Semaphore, end: float, fn, *args, hosts: tuple[str, ...] = ()):
    """Blocking yt-dlp and ffmpeg work in a thread, done by `end` (time.monotonic()). A thread can't be killed, so the
    caller stops waiting at `end` and the thread sees the same deadline: in each progress hook, at each new connection
    (_guard), before each child process, whose own limit is cut to it, and in yt-dlp's waits for its children. Each read
    is bounded by socket_timeout. It keeps its slot in `gate` until it has really ended, so late threads never pile up."""
    async with asyncio.timeout(max(end - time.monotonic(), 0)):
        await gate.acquire()
    token = _bound.set(_Bound(end, hosts))
    try:  # no await from the acquire to the callback: the slot is always given back, by the thread's end
        job = asyncio.ensure_future(asyncio.to_thread(fn, *args))  # the task copies the context, the thread too
    finally:
        _bound.reset(token)
    job.add_done_callback(lambda j: (gate.release(), j.cancelled() or j.exception()))
    return await asyncio.wait_for(asyncio.shield(job), max(end - time.monotonic(), 0))


def _limit(progress: dict) -> None:
    _left()
    if (progress.get("downloaded_bytes") or 0) > MAX_BYTES:
        raise TooLarge("video too large")


def _connect(original):
    """yt-dlp's every new connection, inside _threaded: its host on the allowlist (when the work names one), every
    address the name resolves to public (SSRF: a redirect, a manifest's segment, an API's answer pointing inside), and
    the connection made to those vetted addresses, not to a second lookup's."""
    def connect(address, *args, **kwargs):
        bound = _bound.get()
        if bound is None:
            return original(address, *args, **kwargs)
        timeout = args[0] if args else kwargs.pop("timeout", None)
        args = args[1:]
        host, port = address[:2]
        left = _left()
        if bound.hosts and not download.host_allowed(str(host), bound.hosts):
            raise OSError("host not allowed")
        found = [row[4][0] for row in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)]
        if not found or not all(download.public(a) for a in found):
            raise OSError("address not public")
        timeout = min(timeout, left) if isinstance(timeout, (int, float)) else left  # None or a library's "default"
        error = None
        for a in dict.fromkeys(found):
            try:
                return original((a, port), timeout, *args, **kwargs)
            except OSError as exc:
                error = exc
        raise error
    connect.guarded = True
    return connect


_guarding = threading.Lock()


def _guard() -> None:
    """Route yt-dlp's connections through _connect and bound its waits for its own children (the YouTube challenge
    solver) by the deadline. yt-dlp sends through requests/urllib3 or, without them, urllib; both are wrapped.
    ponytail: patches named internals of the pinned yt-dlp and urllib3 (a test fails if they move); outside _threaded
    they change nothing. Upgrade: run yt-dlp in a child process behind an egress proxy and kill it at the deadline."""
    import urllib3.util.connection as urllib3_connection
    from yt_dlp.networking import _urllib
    from yt_dlp.utils import Popen
    with _guarding:  # threads build downloaders
        for module in (urllib3_connection, _urllib):
            if not getattr(module.create_connection, "guarded", False):
                module.create_connection = _connect(module.create_connection)
        if not getattr(Popen.communicate_or_kill, "guarded", False):
            original = Popen.communicate_or_kill

            def communicate_or_kill(self, *args, **kwargs):
                bound = _bound.get()
                if bound is not None and kwargs.get("timeout") is None and len(args) < 2:
                    kwargs["timeout"] = max(bound.end - time.monotonic(), 0.01)  # past it: killed and reaped at once
                return original(self, *args, **kwargs)
            communicate_or_kill.guarded = True
            Popen.communicate_or_kill = communicate_or_kill


def _downloader(**options):
    from yt_dlp import YoutubeDL
    _guard()
    return YoutubeDL({
        "js_runtimes": {"node": {}}, "cachedir": False, "noplaylist": True, "check_formats": False,
        "quiet": True, "noprogress": True,
        "logger": logging.Logger("yt-dlp", logging.CRITICAL + 1),  # extractor messages may contain the link
        "socket_timeout": min(TIMEOUT, _left()), "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
        "max_filesize": MAX_BYTES, "progress_hooks": [_limit],
        "concurrent_fragment_downloads": 1,  # no threads of its own: _bound (deadline, host checks) is this thread's
        "format_sort": ["res", "vcodec:h264", "acodec:aac"], "format_sort_force": True,
        "hls_prefer_native": True, "skip_unavailable_fragments": False,
        # No ffmpeg of yt-dlp's own (its fallback for unusual HLS): it would fetch past _connect and run unbounded.
        # Our ffmpeg remuxes local files only (upload).
        "ffmpeg_location": os.devnull, **options,
    })


def _extract(match: re.Match) -> Clip | None:
    youtube = match["youtube"]
    url = f"https://www.youtube.com/watch?v={youtube}" if youtube else f"https://www.instagram.com/p/{match['instagram']}/"
    with _downloader(allowed_extractors=["youtube" if youtube else "instagram"], format="best*") as dl:
        info = dl.extract_info(url, download=False, process=False)
        if not info:
            return None
        if not youtube and info.get("_type") == "playlist":
            info = next((e for e in info["entries"] if e.get("formats")), None)
            if not info:
                return None
            dl.add_default_extra_info(info, dl.get_info_extractor("Instagram"), url)
        duration = info.get("duration") or 0
        if info.get("_type", "video") != "video" or info.get("is_live") or duration > MAX_SECONDS:
            return None
        if youtube and (not 0 < duration <= MAX_SECONDS or (match["short_host"] and duration >= 180)):
            return None
        _left()
        info = dl.process_ie_result(info, download=False)
        hosts = ("googlevideo.com",) if youtube else ("cdninstagram.com", "fbcdn.net", "instagram.com")
        cover = info.get("thumbnail") or ""
        cover = cover if isinstance(cover, str) and download.allowed(cover, (*hosts, "ytimg.com")) else ""
        return Clip(key(match[0]), duration, info.get("formats") or [info], cover, hosts,
                    "youtube" if youtube else "instagram")


async def photos(http: httpx.AsyncClient, urls: list[str]) -> list[bytes]:
    album = []
    remaining = MAX_BYTES
    for u in urls[:ALBUM]:
        if p := await download.fetch(http, u, download.TIKTOK_FILES, PHOTO_BYTES, types=PHOTO_TYPES, seconds=TIMEOUT):
            remaining -= len(p)
            if remaining < 0:
                return []
            album.append(p)
    return album


async def fetch(http: httpx.AsyncClient, url: str) -> Clip | list[str] | None:
    """What the link holds: a Clip, a slideshow's photo URLs, or None (nothing to send). Paused while the source rests
    after failures; a failure itself raises (SourceDown, TimeoutError, yt-dlp's errors)."""
    match = LINK.match(url)
    if not match:
        return None
    if not match["tiktok"]:
        with _source("youtube" if match["youtube"] else "instagram"):
            return await _threaded(_extractors, time.monotonic() + EXTRACT_SECONDS, _extract, match)
    with _source("tikwm"):
        raw = await download.fetch(http, API, ("www.tikwm.com",), 1024 * 1024, form={"url": match[0], "hd": "1"},
                                   seconds=TIMEOUT)
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise SourceDown("tikwm")
    data = body.get("data") if body.get("code") == 0 else None  # not 0: private, deleted, or not a video
    if not isinstance(data, dict):
        return None
    if images := data.get("images"):  # its "play" is only the music
        if not isinstance(images, list):
            return None
        return [u for u in images[:ALBUM] if isinstance(u, str) and download.allowed(u, download.TIKTOK_FILES)] or None
    formats = [{"url": data[field], "ext": "mp4", "protocol": "https", "filesize": int(data.get(size) or 0)}
               for field, size in (("play", "size"), ("hdplay", "hd_size"))
               if download.allowed(str(data.get(field) or ""), download.TIKTOK_FILES) and int(data.get(size) or 0) <= MAX_BYTES]
    if formats:
        cover = data.get("origin_cover") or data.get("cover") or ""
        return Clip("tt:" + str(data["id"]) if data.get("id") else key(url),
                    data.get("duration") or 0, list({f["url"]: f for f in formats}.values()),
                    cover if isinstance(cover, str) and download.allowed(cover, download.TIKTOK_FILES) else "")


async def _mp4_info(http, f, hosts) -> dict:
    """Read MP4 track headers. Seek over large media boxes, or stream past them once on a CDN without ranges."""
    offset, budget = 0, MAX_BYTES
    ranged = True
    boxes = 0
    while boxes < 24 and offset < MAX_BYTES:
        header = f"bytes={offset}-{MAX_BYTES - 1}" if ranged else None
        async with download.stream(http, f["url"], hosts, byte_range=header, media_headers=f.get("http_headers")) as r:
            if r is None:
                return {}
            if ranged and r.status_code in (400, 403, 405, 416):
                ranged = False
                continue
            if r.status_code not in (200, 206) or not download.typed(r, MEDIA_TYPES):
                return {}
            seek = ranged and r.status_code == 206
            total = r.headers.get("Content-Range", "").partition("/")[2] if seek else r.headers.get("Content-Length", "")
            if total.isdecimal():
                f["filesize"] = int(total)
                if f["filesize"] > MAX_BYTES:
                    return {}
            if not seek:
                offset = 0
            chunks = r.aiter_bytes(chunk_size=32768)
            buf = memoryview(b"")

            async def read(count, *, discard=False):
                nonlocal buf, budget
                out = bytearray()
                while count:
                    if not buf:
                        buf = memoryview(await anext(chunks, b""))
                        budget -= len(buf)
                        if not buf or budget < 0:
                            raise EOFError
                    take = min(count, len(buf))
                    if not discard:
                        out.extend(buf[:take])
                    buf = buf[take:]
                    count -= take
                return out

            try:
                while boxes < 24:
                    boxes += 1
                    box = await read(8)
                    size = int.from_bytes(box[:4])
                    if size == 1:
                        box += await read(8)
                        size = int.from_bytes(box[8:])
                    if size < len(box) or offset + size > MAX_BYTES:
                        return {}
                    payload = size - len(box)
                    if box[4:8] == b"moov":
                        if size > 1024 * 1024:
                            return {}
                        box += await read(payload)
                        return await asyncio.to_thread(_tracks, bytes(box))
                    offset += size
                    if seek and payload > len(buf) + 32768:
                        break
                    await read(payload, discard=True)
            except EOFError:
                return {}
    return {}


def _run(cmd: list[str], seconds: float, *, input: bytes | None = None, stdout=subprocess.DEVNULL) -> subprocess.CompletedProcess:
    """A child process with a hard wall-clock limit, cut to the work's deadline. On expiry (TimeoutExpired) it is killed
    with anything it started (its own process group) and reaped: no zombie, nothing left holding a pipe."""
    seconds = min(seconds, _left())
    with subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL, stdout=stdout,
                          stderr=subprocess.DEVNULL, start_new_session=True) as proc:
        try:
            out, _ = proc.communicate(input, timeout=seconds)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out)


def _tracks(source: bytes | Path) -> dict:
    pipe = isinstance(source, bytes)
    proc = _run(["ffprobe", "-v", "quiet", "-protocol_whitelist", "pipe" if pipe else "file", "-f", "mov",
                 "-show_entries", "stream=codec_type,codec_name,width,height:stream_side_data=rotation:format=duration",
                 "-of", "json", "pipe:0" if pipe else str(source)], 10, input=source if pipe else None, stdout=subprocess.PIPE)
    if proc.returncode:
        return {}
    info = json.loads(proc.stdout)
    streams = info.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"), {})
    a = next((s for s in streams if s["codec_type"] == "audio"), {})
    width, height = v.get("width"), v.get("height")
    if any(int(side.get("rotation") or 0) % 180 == 90 for side in v.get("side_data_list", ())):
        width, height = height, width
    return {"vcodec": v.get("codec_name", "none"), "acodec": a.get("codec_name", "none"),
            "width": width, "height": height, "duration": float(info.get("format", {}).get("duration") or 0)}


async def versions(http, clip: Clip) -> list[Version]:
    # Only the source's own media hosts: these URLs go to our downloads and to Telegram.
    formats = [f for f in clip.formats if f.get("protocol") in ("https", "m3u8", "m3u8_native", "http_dash_segments")
               and isinstance(f.get("url"), str) and download.allowed(f["url"], clip.hosts) and not f.get("has_drm")]
    # Some Instagram variants also omit their codecs. Inspect those just as we do tikwm's two files, and any file
    # whose size is unknown (its server's Content-Range then says it, before Telegram is given the URL).
    async def inspect(f):
        codecs = f.get("vcodec") and f.get("acodec")
        shape = f.get("vcodec") == "none" or (f.get("width") and f.get("height") and (clip.duration or f.get("duration")))
        if not (codecs and shape and _size(f)) and _size(f) <= MAX_BYTES and f["protocol"] == "https":
            try:
                async with _probes, asyncio.timeout(TIMEOUT):
                    f.update(await _mp4_info(http, f, clip.hosts))
            except (OSError, httpx.HTTPError, httpx.InvalidURL, ValueError, subprocess.SubprocessError):
                pass  # TimeoutError is an OSError
    await asyncio.gather(*(inspect(f) for f in formats))
    if clip.source != "tikwm":  # a duration the file's own header gives
        formats = [f for f in formats if (f.get("duration") or 0) <= MAX_SECONDS + 1]
    silent = bool(formats) and all(f.get("acodec") == "none" for f in clip.formats)
    # yt-dlp marks the original YouTube audio track with a higher language preference than any dub.
    preference = max((f.get("language_preference") or 0 for f in formats if f.get("acodec") != "none"), default=0)
    audio = [f for f in reversed(formats) if (f.get("acodec") or "").startswith(("aac", "mp4a.40"))
             and (f.get("language_preference") or 0) >= preference]
    pairs = []
    for f in reversed(formats):
        if not (f.get("vcodec") or "").startswith(("avc1", "h264")):
            continue
        if f in audio or silent:
            pairs.append(Version(f))
        else:
            pairs.extend(Version(f, a) for a in audio if a.get("vcodec") == "none")
    def quality(v: Version) -> tuple:
        width, height = v.video.get("width") or 0, v.video.get("height") or 0
        return min(width, height), width * height, v.direct, not v.audio, v.video.get("vbr") or 0

    return sorted((v for v in pairs if v.size <= MAX_BYTES), key=quality, reverse=True)



async def prepare_upload(http: httpx.AsyncClient, clip: Clip, version: Version):
    """The chosen version as (MP4, thumbnail, tracks), or None (too large, not H.264, a source that failed), all within
    DOWNLOAD_SECONDS (TimeoutError past it). Paused while the source rests."""
    end = time.monotonic() + DOWNLOAD_SECONDS
    if clip.hosts == download.TIKTOK_FILES:
        data = await download.fetch(http, version.video["url"], clip.hosts, MAX_BYTES, types=MEDIA_TYPES,
                                    seconds=DOWNLOAD_SECONDS)
        return await _threaded(_transfers, end, upload, version, data) if data else None
    try:
        with _source(clip.source):
            return await _threaded(_transfers, end, upload, version, hosts=clip.hosts)
    except SourceDown:
        return None  # counted; the next version may still come through


def upload(version: Version, source: bytes | None = None) -> tuple[bytes, bytes, dict] | None:
    """Download only the chosen streams. Copy them into a fast-start MP4 and take one frame for Telegram.
    Runs in _threaded: yt-dlp's connections pass _connect, every step sees the deadline. Raises SourceDown when
    yt-dlp's download fails; None for anything else that isn't sendable (too large, too long, not H.264, too slow)."""
    try:
        return _upload(version, source)
    except subprocess.SubprocessError:  # ffmpeg ran out of time (killed)
        return None


def _upload(version: Version, source: bytes | None) -> tuple[bytes, bytes, dict] | None:
    from .video import FORMATS, SAFE_IN
    if source is None:
        from yt_dlp.utils import DownloadError
        from yt_dlp.networking.exceptions import RequestError
    with tempfile.TemporaryDirectory() as tmp, (_downloader() if source is None else nullcontext()) as dl:
        inputs = []
        size = 0
        for i, f in enumerate(filter(None, (version.video, version.audio))):
            path = Path(tmp, f"source{i}")
            if source is not None:
                path.write_bytes(source)
            else:
                if f.get("cookies"):
                    dl._load_cookies(f["cookies"], autoscope=False)  # keep the extractor's domain and path
                try:
                    ok, _ = dl.dl(str(path), f)
                except TooLarge:
                    return None
                except (DownloadError, RequestError) as exc:
                    raise SourceDown(type(exc).__name__) from None
                if not ok or not path.is_file():  # e.g. its Content-Length is past max_filesize
                    return None
            size += path.stat().st_size
            if not 0 < size <= MAX_BYTES:
                return None
            inputs.extend(["-protocol_whitelist", "file", "-format_whitelist", FORMATS + ",mpegts,aac", "-i", str(path)])
        mp4 = Path(tmp, "video.mp4")
        ffmpeg = ["ffmpeg", "-nostdin", "-v", "error"]
        remux = _run([*ffmpeg, *inputs, "-map", "0:v:0", "-map", "1:a:0" if version.audio else "0:a:0?",
                      "-c", "copy", "-movflags", "+faststart", str(mp4)], FFMPEG_SECONDS)
        if remux.returncode or not mp4.is_file() or not 0 < mp4.stat().st_size <= MAX_BYTES:
            return None
        tracks = _tracks(mp4)
        if tracks.get("vcodec") != "h264" or tracks.get("acodec") not in ("aac", "none"):
            return None
        if source is None and tracks.get("duration", 0) > MAX_SECONDS + 1:  # the real length, whatever was listed
            return None
        thumb = _run([*ffmpeg, *SAFE_IN, "-i", str(mp4), "-frames:v", "1", "-vf",
                      "scale=320:320:force_original_aspect_ratio=decrease", "-c:v", "mjpeg", "-threads", "1",
                      "-f", "image2pipe", "-"], 20, stdout=subprocess.PIPE)
        return mp4.read_bytes(), thumb.stdout if thumb.returncode == 0 and len(thumb.stdout) < 200_000 else b"", tracks
