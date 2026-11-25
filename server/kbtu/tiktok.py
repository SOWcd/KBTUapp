"""Captionless group video replies. Resolve and compare source formats before transferring a video."""
from __future__ import annotations

import asyncio
import hashlib
import http.cookiejar
import io
import itertools
import json
import logging
import math
import os
import re
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict, deque
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
    # a post, a reel, an IGTV video, also under its author's name (/<name>/p/<code>); never a story or a share link
    r"|(?:www\.)?instagram\.com/(?:(?!stories/|share/)(?a:[\w.]+)/)?(?:reels?|p|tv)/(?P<instagram>(?a:[\w-]+))"
    # one story (never a highlights reel: a playlist of a hundred): acted on only with INSTAGRAM_COOKIES (link)
    r"|(?:www\.)?instagram\.com/stories/(?!highlights/)(?P<story_user>(?a:[\w.]{1,30}))/(?P<story>[0-9]{1,30})"
    r")/?(?=$|[\s?#.,!;:)\]}<>\"'])", re.I)
MAX_BYTES = 50 * 1024 * 1024  # the most a bot may upload
URL_BYTES = 20 * 1024 * 1024  # the most Telegram fetches by URL itself
PHOTO_BYTES = 10 * 1024 * 1024  # and one photo
ALBUM = 10                    # items in one album at most (Telegram's limit)
ALBUM_BYTES = MAX_BYTES - 1024 * 1024  # an album's files together: one request, with room for the form around them
THUMB_BYTES = 200_000         # a video's thumbnail at most
INSTAGRAM_FILES = ("cdninstagram.com", "fbcdn.net", "instagram.com")
MAX_SECONDS = 180             # the longest yt-dlp source (a Short's limit; an Instagram reel's too)
MEDIA_TYPES = ("video/", "audio/", "application/mp4", "application/octet-stream", "binary/octet-stream")
PHOTO_TYPES = ("image/",)
log = logging.getLogger("kbtu.tiktok")
# Instagram stories, and posts Instagram shows only to a signed-in account, through the owner's spare account
# (README "Instagram stories"). Only the env variable says where its cookies are, read at each call; the path and the
# cookies never reach a log line, an error, the database or yt-dlp's own cookie file (it would write the jar back).
COOKIES = "INSTAGRAM_COOKIES"
COOKIE_BYTES = 256 * 1024              # a cookies file of instagram.com is a few kB; past this it's not one
SESSION_HOSTS = ("instagram.com",)     # the only hosts a signed-in request may connect to, its cookies' only domain
SIGNED = "instagram-session"           # the breaker of signed-in extractions: a dead session never rests reels
SESSION_CAP = 60                       # signed-in extractions an hour, all chats together (the account reads like a person)
SESSION_CHAT_CAP = 15                  # of them for one chat, an hour
SESSION_USER_CAP = 5                   # and for one person, all chats together: nobody drains the rest's
MISS_SECONDS = 3600                    # a link the session found nothing behind isn't asked with it again for this long
CHECK_SECONDS = 30                     # the event loop looks at the cookies file at most this often (_configured)
_PLAIN_HEADERS = frozenset(("user-agent", "accept", "accept-language", "sec-fetch-mode", "referer", "origin"))
# Wall-clock limits, end to end however slowly a source answers (each request step: download.TIMEOUT).
TIMEOUT = 30                  # seconds for one source request (tikwm, one probe)
EXTRACT_SECONDS = 60          # one yt-dlp extraction
DOWNLOAD_SECONDS = 150        # yt-dlp: the chosen streams, their remux and thumbnail; tikwm: the file alone
REMUX_SECONDS = 90            # tikwm: the remux and thumbnail of the downloaded file
REPLY_SECONDS = 300           # one link, from the first request to Telegram's last answer
ALBUM_SECONDS = 120           # an album's items together (after extraction, before the upload): what is ready is sent
FFMPEG_SECONDS = 60           # each child process, and never past the deadline of the work it is part of
_extractors = asyncio.Semaphore(2)  # leave the shared thread pool available to receipts and other bot updates
_transfers = asyncio.Semaphore(2)
_probes = asyncio.Semaphore(4)
CHAT_CAP = 5                  # answers a chat a minute: a burst of links never turns the chat into a feed
USER_CAP = 3                  # answers one person gets a minute, all chats together: never a chat's whole CHAT_CAP
WINDOW = 60                   # seconds the caps count over; the same person's same video in a chat again only after it
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
    for m in LINK.finditer(str(msg.get("text") or msg.get("caption") or "")):
        if not m["story"] or _configured():  # a story without the cookies: as if it weren't there (no request at all)
            return m.group(0)
    return None


def room(chat: int, now: float | None = None, *, user: int = 0, video: str = "") -> bool:
    """One more answer this minute in this chat (CHAT_CAP) and for this person (USER_CAP), and not this person's same
    video (key) again in this chat within WINDOW (sharing it to another group is fine). Counted only when all three
    say yes."""
    now = time.time() if now is None else now
    while _sent and now - next(iter(_sent.values()))[-1] >= WINDOW:
        _sent.popitem(last=False)
    caps = {("chat", chat): CHAT_CAP, ("user", user): USER_CAP}
    if video:
        caps[("same", chat, user, video)] = 1
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
def _source(name: str, count: bool = True):
    """A call to a source through its circuit breaker: an exception (a timeout too) counts as its failure, an answer as
    its success. A cancellation (the reply's own deadline, a shutdown) says nothing about the source: not counted (a
    trial cancelled so leaves the source resting until REST runs out, then another tries). `count` False: neither
    asked nor told (the same clip's next version after a failure already counted)."""
    if not count:
        yield
        return
    if not _ready(name):
        raise Paused(name)
    try:
        yield
    except asyncio.CancelledError:
        raise
    except BaseException:
        _report(name, False)
        raise
    _report(name, True)


def _outage(exc: BaseException) -> bool:
    """The source failed (counts for its breaker) rather than this one video having nothing to send. Failures: transport
    errors, timeouts, HTTP 429 and 5xx, anything unknown. Not: HTTP 4xx (403, 404, 410: gone, forbidden, region) and
    yt-dlp's expected errors (private, deleted, age-gated, geo-blocked, login-only)."""
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    from yt_dlp.utils import ExtractorError
    chain = _chain(exc)
    for e in chain:
        if isinstance(e, HTTPError):
            return e.status == 429 or e.status >= 500
    if any(isinstance(e, (TransportError, TimeoutError, SourceDown)) for e in chain):
        return True
    return not any(isinstance(e, ExtractorError) and e.expected for e in chain)


def _chain(exc: BaseException) -> list[BaseException]:
    """The exception and what it wraps: DownloadError.exc_info, ExtractorError.cause, __cause__, __context__."""
    chain, todo = [], [exc]
    while todo and len(chain) < 12:
        e = todo.pop(0)
        if isinstance(e, BaseException) and all(e is not c for c in chain):
            chain.append(e)
            info = getattr(e, "exc_info", None)
            todo += [info[1] if isinstance(info, tuple) and len(info) > 1 else None,
                     getattr(e, "cause", None), e.__cause__, e.__context__]
    return chain


def _login_wall(exc: BaseException) -> bool:
    """Instagram sent an anonymous reader to its login page (the pinned extractor's raise_login_required for it), and
    nothing else is wrong: never an HTTP error (404: gone), a post it found empty, a private account (the spare account
    follows none) or a "Restricted Video" (age or sensitivity: the adult spare account would see what anonymous readers
    don't). Only then is the session worth a request. Unknown wording: no (fails closed; a test pins the wording)."""
    from yt_dlp.networking.exceptions import HTTPError
    from yt_dlp.utils import ExtractorError
    chain = _chain(exc)
    if any(isinstance(e, HTTPError) for e in chain):
        return False
    said = [str(getattr(e, "orig_msg", "")) for e in chain if isinstance(e, ExtractorError) and e.expected]
    return any("redirected to the login page" in m and "--cookies" in m and "restricted" not in m.lower() for m in said)


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
    down: bool = False  # one of its downloads failed and was counted: the next versions don't count again
    private: bool = False  # extracted with the session: its files are fetched by us only (_sealed)


@dataclass
class Version:
    video: dict
    audio: dict | None = None
    private: bool = False  # its clip's: never a URL for Telegram to fetch

    @property
    def size(self) -> int:
        return _size(self.video) + _size(self.audio or {})

    @property
    def direct(self) -> bool:
        """Telegram may fetch it by URL: one file, its size known (a server's header, not only a listing) and small."""
        f = self.video
        return (not self.private and not self.audio and f["protocol"] == "https" and f.get("ext") == "mp4" and 0 < self.size <= URL_BYTES
                and bool(f.get("vcodec") and f.get("acodec") and f.get("width") and f.get("height")))


def _size(f: dict) -> int:
    return int(f.get("filesize") or f.get("filesize_approx") or 0)


@dataclass
class Album:
    """A post of several items, or of photos only (Instagram). Each item a photo's URL or a video, in the post's order."""
    key: str
    items: list[str | Clip]
    hosts: tuple[str, ...] = INSTAGRAM_FILES  # where its photos may come from


@dataclass
class Part:
    """One album item ready to upload: a photo, or a video (tracks: its duration, width, height) and its thumbnail."""
    data: bytes
    thumb: bytes = b""
    tracks: dict | None = None

    @property
    def size(self) -> int:
        return len(self.data) + len(self.thumb)


CACHE_SIZE = 512
# A video's file id, or an album's items (a slideshow's photos, a post's photos and videos) as Telegram's InputMedia
_files: OrderedDict[str, tuple[str | tuple[dict, ...], float]] = OrderedDict()


def key(url: str) -> str:
    m = LINK.match(url)
    if m["youtube"]:
        return "yt:" + m["youtube"]
    if m["instagram"]:
        return "ig:" + m["instagram"]
    if m["story"]:
        return "igs:" + m["story"]
    parts = urlsplit(url)
    if found := re.fullmatch(r"/@[^/]+/video/(\d+)/?", parts.path):
        return "tt:" + found[1]
    if parts.hostname in ("vm.tiktok.com", "vt.tiktok.com") and re.fullmatch(r"/[\w-]+/?", parts.path):
        return parts.hostname + parts.path.rstrip("/")
    # Other short links can depend on their query. Keep a bounded alias without storing the shared URL.
    return "link:" + hashlib.sha256(url.encode()).hexdigest()


def cached(k: str) -> tuple[str | tuple[dict, ...], float] | None:
    if entry := _files.get(k):
        _files.move_to_end(k)
        return entry
    return None


def forget(k: str) -> None:
    _files.pop(k, None)


def remember(k: str, file_id: str | tuple[dict, ...], duration: float) -> None:
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
    cap: int = 0                  # the most bytes its download may come to; 0: MAX_BYTES


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


def _cap() -> int:
    bound = _bound.get()
    return bound.cap if bound is not None and bound.cap else MAX_BYTES


async def _threaded(gate: asyncio.Semaphore, seconds: float, fn, *args, hosts: tuple[str, ...] = (),
                    source: str = "", count: bool = True, cap: int = 0):
    """Blocking yt-dlp and ffmpeg work in a thread, done within `seconds` of getting its slot in `gate`. Waiting for the
    slot is our own queue: neither the work's time nor the source's failure (the reply's deadline bounds that wait).
    A thread can't be killed, so the caller stops waiting at the deadline and the thread sees the same deadline: in
    each progress hook, at each new connection (_guard), before each child process, whose own limit is cut to it, and
    in yt-dlp's waits for its children. Each read is bounded by socket_timeout. It keeps its slot until it has really
    ended, so late threads never pile up. With `source`, it goes through that source's breaker (`count`: see _source):
    an outage raises and counts, a video with nothing to send (_outage says no) returns None. `cap`: the most bytes its
    download may come to (0: MAX_BYTES)."""
    await gate.acquire()
    handed = False
    try:
        with _source(source, count) if source else nullcontext():
            token = _bound.set(_Bound(time.monotonic() + seconds, hosts, cap))
            try:  # no await from here to the callback: the slot is given back by the thread's end
                job = asyncio.ensure_future(asyncio.to_thread(fn, *args))  # the task copies the context, the thread too
            finally:
                _bound.reset(token)
            job.add_done_callback(lambda j: (gate.release(), j.cancelled() or j.exception()))
            handed = True
            try:
                return await asyncio.wait_for(asyncio.shield(job), seconds)
            except Exception as exc:
                if source and not _outage(exc):
                    return None
                raise
    finally:
        if not handed:
            gate.release()


def _limit(progress: dict) -> None:
    _left()
    if (progress.get("downloaded_bytes") or 0) > _cap():
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
    from yt_dlp.networking import _requests, _urllib, _websockets
    from yt_dlp.networking.common import _REQUEST_HANDLERS
    from yt_dlp.utils import Popen
    if set(_REQUEST_HANDLERS) - {"Urllib", "Requests", "Websockets"}:  # e.g. curl_cffi: its own sockets, unguarded
        raise RuntimeError("an unguarded yt-dlp request handler is installed")
    with _guarding:  # threads build downloaders
        for module in (urllib3_connection, _urllib, _requests, _websockets):
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
        "proxy": "",  # never HTTPS_PROXY/ALL_PROXY from the environment: a proxy's socket would bypass _connect
        "socket_timeout": min(TIMEOUT, _left()), "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
        "max_filesize": _cap(), "progress_hooks": [_limit],
        "concurrent_fragment_downloads": 1,  # no threads of its own: _bound (deadline, host checks) is this thread's
        "format_sort": ["res", "vcodec:h264", "acodec:aac"], "format_sort_force": True,
        "hls_prefer_native": True, "skip_unavailable_fragments": False,
        # No ffmpeg of yt-dlp's own (its fallback for unusual HLS): it would fetch past _connect and run unbounded.
        # Our ffmpeg remuxes local files only (upload).
        "ffmpeg_location": os.devnull, **options,
    })


_SIGN_IN = object()  # _extract's answer: Instagram shows this post only to a signed-in account


def _extract(match: re.Match) -> Clip | Album | object | None:
    youtube = match["youtube"]
    if not youtube:
        try:
            return _post(match)
        except Exception as exc:
            # Instagram's login wall for anonymous readers: the session may see it (no outage, so not counted for the
            # anonymous breaker either way). Anything else, or without the cookies: exactly as before.
            if not _login_wall(exc) or not _cookie_path():
                raise
        return _SIGN_IN
    url = f"https://www.youtube.com/watch?v={youtube}"
    with _downloader(allowed_extractors=["youtube"], format="best*") as dl:
        info = dl.extract_info(url, download=False, process=False)
        if not info:
            return None
        duration = info.get("duration") or 0
        if not 0 < duration <= MAX_SECONDS or (match["short_host"] and duration >= 180):
            return None
        return _clip(dl, info, key(match[0]), "youtube")


def _clip(dl, info: dict, k: str, source: str) -> Clip | None:
    duration = info.get("duration") or 0
    if info.get("_type", "video") != "video" or info.get("is_live") or duration > MAX_SECONDS + 1:  # 180.04 s reels
        return None
    _left()
    info = dl.process_ie_result(info, download=False)
    hosts = ("googlevideo.com",) if source == "youtube" else INSTAGRAM_FILES
    cover = info.get("thumbnail") or ""
    cover = cover if isinstance(cover, str) and download.allowed(cover, (*hosts, "ytimg.com")) else ""
    return Clip(k, duration, info.get("formats") or [info], cover, hosts, source)


def _post(match: re.Match, cookies: list[http.cookiejar.Cookie] | None = None) -> Clip | Album | None:
    """An Instagram post: a reel or a video post as a Clip; photos, or several items (a carousel), as an Album of its
    first ALBUM items. A carousel with a single video that can be sent is that video. Each video is checked as a reel.
    With `cookies`: as the signed-in account (_signed), its videos _sealed."""
    url = f"https://www.instagram.com/p/{match['instagram']}/"
    k = key(match[0])
    # a photo post has no formats: not an error here (it would count against the source's breaker)
    options = {"allowed_extractors": ["instagram"], "format": "best*", "ignore_no_formats_error": True}
    with _signed_in(cookies, **options) if cookies else _downloader(**options) as dl:
        info = dl.extract_info(url, download=False, process=False)
        if not info:
            return None
        entries = (info.get("entries") or ()) if info.get("_type") == "playlist" else (info,)
        items: list[str | Clip] = []
        for entry in itertools.islice(entries, ALBUM):
            if not isinstance(entry, dict) or entry.get("_type", "video") != "video":
                continue
            if entry.get("formats"):
                if entry is not info:
                    dl.add_default_extra_info(entry, dl.get_info_extractor("Instagram"), url)
                try:
                    clip = _clip(dl, entry, "", "instagram")
                except Expired:
                    raise
                except Exception as exc:  # noqa: BLE001 - one item yt-dlp can't make sense of: the others still go
                    log.debug("group video: an album item failed: %s", type(exc).__name__)
                    clip = None
                if clip:
                    items.append(_sealed(clip) if cookies else clip)
            elif not entry.get("duration") and (photo := _photo_url(entry)):  # a video without formats is no photo
                items.append(photo)
        if len(items) == 1 and isinstance(items[0], Clip):
            items[0].key = k
            return items[0]
        return Album(k, items) if items else None


# (chat, person) whose link is being answered (bot._tiktok sets it): the session's caps per chat and per person
asker: ContextVar[tuple[int, int] | None] = ContextVar("tiktok_asker", default=None)
_NO_SESSION = object()  # _signed's answer: no usable cookies, nothing was asked
# ponytail: per worker (the bot polls in one), as _sent; keys idle an hour pruned, at most SENT_KEYS of them
_session_uses: OrderedDict[tuple, list[float]] = OrderedDict()
_session_misses: OrderedDict[str, float] = OrderedDict()


def _session_take(now: float) -> list[tuple] | None:
    """One signed-in extraction counted against SESSION_CAP, and the asker's chat and person caps; None past any."""
    while _session_uses and now - next(iter(_session_uses.values()))[-1] >= 3600:
        _session_uses.popitem(last=False)
    who = asker.get()
    caps = {("all",): SESSION_CAP}
    if who is not None:
        caps |= {("chat", who[0]): SESSION_CHAT_CAP, ("user", who[1]): SESSION_USER_CAP}
    recent = {k: [t for t in _session_uses.get(k, ()) if now - t < 3600] for k in caps}
    if len(recent[("all",)]) >= SESSION_CAP:
        _tell("the Instagram session's hourly cap is reached; stories and login-only posts wait")
        return None
    if any(len(recent[k]) >= cap for k, cap in caps.items()):
        return None
    for k in caps:
        _session_uses[k] = [*recent[k], now]
        _session_uses.move_to_end(k)
    while len(_session_uses) > SENT_KEYS:
        _session_uses.popitem(last=False)
    return list(caps)


def _session_refund(taken: list[tuple], now: float) -> None:
    """Nothing was asked after all (no usable cookies, the breaker said no): the slots go back."""
    for k in taken:
        uses = _session_uses.get(k)
        if uses and now in uses:
            uses.remove(now)
            if not uses:
                del _session_uses[k]


async def _signed_fetch(match: re.Match) -> Clip | Album | None:
    """_signed in a thread, or None without a request: no readable cookies file, the link found empty with the session
    within MISS_SECONDS, or past a cap. A resting breaker raises Paused before a slot is taken; a call that asked
    nothing (no session in the file, Paused) gives its slot back. A link with nothing behind it is remembered."""
    if not _configured():
        return None
    k = key(match[0])
    now = _clock()
    if now - _session_misses.get(k, -math.inf) < MISS_SECONDS:
        return None
    failures, until = _health.get(SIGNED, (0, 0.0))
    if failures >= FAILURES and now < until:
        raise Paused(SIGNED)
    if (taken := _session_take(now)) is None:
        return None
    try:
        got = await _threaded(_extractors, EXTRACT_SECONDS, _signed, match, hosts=SESSION_HOSTS, source=SIGNED)
    except Paused:
        _session_refund(taken, now)
        raise
    if got is _NO_SESSION:
        _session_refund(taken, now)
        return None
    if got is None:
        _session_misses[k] = now
        _session_misses.move_to_end(k)
        while len(_session_misses) > CACHE_SIZE:
            _session_misses.popitem(last=False)
    return got


def _story(match: re.Match, cookies: list[http.cookiejar.Cookie]) -> Clip | None:
    """One story's video, as the signed-in account sees it. The pinned yt-dlp lists a story's videos only (a photo
    story: nothing) and, with noplaylist, returns the linked one alone (None if it is gone)."""
    url = f"https://www.instagram.com/stories/{match['story_user']}/{match['story']}/"
    with _signed_in(cookies, allowed_extractors=["instagram:story"], format="best*") as dl:
        info = dl.extract_info(url, download=False, process=False)
        clip = _clip(dl, info, key(match[0]), "instagram") if isinstance(info, dict) else None
    return _sealed(clip) if clip else None


def _signed(match: re.Match) -> Clip | Album | None:
    """A story, or a post only a signed-in account sees, through the owner's spare account. Runs in _threaded with
    SESSION_HOSTS alone (no connection anywhere else, a redirect neither) under its own breaker (SIGNED). The cookies are
    read here, at call time, and live only in this thread's yt-dlp jar: no cookie file of yt-dlp's, nothing written
    back. No readable cookies: _NO_SESSION before any request."""
    cookies = _cookies()
    if not cookies:
        return _NO_SESSION
    return _story(match, cookies) if match["story"] else _post(match, cookies)


@contextmanager
def _signed_in(cookies: list[http.cookiejar.Cookie], **options):
    """A downloader whose jar holds the session's cookies (instagram.com's only, secure only: never sent to a CDN, a
    redirect elsewhere or over plain HTTP). Never `cookiefile`: yt-dlp would save the jar to it on close (rewriting
    the owner's file, failing on a read-only mount). Instagram's answers may update the jar: dropped with it."""
    with _downloader(**options) as dl:
        jar = dl.cookiejar
        for cookie in cookies:
            jar.set_cookie(cookie)
        try:
            yield dl
        finally:
            # yt-dlp drops the session when Instagram sends the login page; Instagram may also expire it itself
            if not any(c.name == "sessionid" for c in jar):
                _tell("the Instagram cookies were signed out; stories wait for new ones (README)")
            jar.clear()


def _sealed(clip: Clip) -> Clip:
    """A clip found with the session: its files are fetched without it. No cookies of the extraction go with its
    formats (upload() would load them), no headers but plain ones, no URL handed to Telegram (Version.private), no
    remote cover."""
    clip.private, clip.cover = True, ""
    for f in clip.formats:
        f.pop("cookies", None)
        headers = f.get("http_headers") or {}
        f["http_headers"] = {k: v for k, v in headers.items() if str(k).lower() in _PLAIN_HEADERS}
    return clip


def _cookie_path() -> str:
    """INSTAGRAM_COOKIES, read at each call: the path if it names a readable file, else "" (stories off)."""
    path = os.environ.get(COOKIES, "").strip()
    return path if path and os.path.isfile(path) and os.access(path, os.R_OK) else ""


_checked: tuple[str, float, str] | None = None  # (the variable's value, when, _cookie_path's answer)


def _configured() -> str:
    """_cookie_path() for the event loop (link, before a signed-in fetch): unset costs nothing, a set one is looked at
    once per CHECK_SECONDS (a stalled network mount would hold up the poller on every story link). The thread's own
    read (_cookies) is the one that counts."""
    global _checked
    value = os.environ.get(COOKIES, "")
    if not value.strip():
        return ""
    now = _clock()
    if _checked is None or _checked[0] != value or not 0 <= now - _checked[1] < CHECK_SECONDS:
        _checked = (value, now, _cookie_path())
    return _checked[2]


def _cookies() -> list[http.cookiejar.Cookie]:
    """The session's cookies from the file, read-only and at most COOKIE_BYTES; [] if it can't be read or holds no
    Instagram session. An error here names the path: dropped where it happens, the log gets a fixed line only."""
    path = _cookie_path()
    if not path:
        return []
    raw = None
    try:  # O_NONBLOCK: a FIFO put there never hangs the thread
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC), "rb") as f:
            if stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raw = f.read(COOKIE_BYTES + 1)
    except OSError:
        pass
    if raw is None or len(raw) > COOKIE_BYTES:
        _tell("the Instagram cookies can't be read; stories wait for new ones (README)")
        return []
    cookies = _netscape(raw.decode("utf-8", "replace"))
    if not any(c.name == "sessionid" for c in cookies):
        _tell("the Instagram cookies hold no session; stories wait for new ones (README)")
        return []
    return cookies


_NAME = re.compile(r"[!#-+\-.0-9A-Z^-z|~]{1,256}")    # a cookie's name: a token
_VALUE = re.compile(r"[!-:<-~]{0,4096}")                # its value: printable ASCII but ';' (nothing to break a header)
_DOMAIN = re.compile(r"\.?(?:[a-z0-9-]{1,63}\.){1,8}[a-z]{2,63}")
_PATH = re.compile(r"/[!-~]{0,1024}")


def _netscape(text: str) -> list[http.cookiejar.Cookie]:
    """Netscape cookies-file lines (as browsers' exporters write them), instagram.com's only, unexpired, each made
    secure. Anything else is skipped without a word (a line may hold a value)."""
    now = time.time()
    out = []
    for line in text.split("\n"):  # not splitlines: a value's \v or \x1c would split it into a "line" of its own
        line = line.removesuffix("\r")
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            continue
        domain, _, path, _, expires, name, value = fields
        domain = domain.lower()
        if not (_DOMAIN.fullmatch(domain) and download.host_allowed(domain.lstrip("."), SESSION_HOSTS)
                and _NAME.fullmatch(name) and _VALUE.fullmatch(value) and re.fullmatch(r"[0-9]{1,12}", expires)):
            continue
        expiry = int(expires) or None  # 0: a session cookie
        if expiry is not None and expiry <= now:
            continue
        dot = domain.startswith(".")
        out.append(http.cookiejar.Cookie(
            0, name, value, None, False, domain, dot, dot, path if _PATH.fullmatch(path) else "/", True, True,
            expiry, expiry is None, None, None, {"HttpOnly": None} if http_only else {}))
    return out


_told: dict[str, float] = {}


def _tell(what: str) -> None:
    """The owner's hint in the log, once an hour for each: a fixed phrase of ours, never the path or a cookie."""
    now = _clock()
    if now - _told.get(what, -math.inf) >= 3600:
        _told[what] = now
        log.warning("group video: %s", what)


def _photo_url(entry: dict) -> str:
    """A photo item's largest image on Instagram's own hosts ("" if none)."""
    def area(t: dict) -> int:
        try:
            return int(t.get("width") or 0) * int(t.get("height") or 0)
        except (TypeError, ValueError):
            return 0
    shots = [t for t in entry.get("thumbnails") or () if isinstance(t, dict) and isinstance(t.get("url"), str)]
    shots.sort(key=area)
    if isinstance(entry.get("thumbnail"), str):
        shots.insert(0, {"url": entry["thumbnail"]})
    return next((t["url"] for t in reversed(shots) if download.allowed(t["url"], INSTAGRAM_FILES)), "")


async def photos(http: httpx.AsyncClient, urls: list[str],
                 hosts: tuple[str, ...] = download.TIKTOK_FILES) -> list[bytes]:
    album = []
    remaining = MAX_BYTES
    for u in urls[:ALBUM]:
        if p := await download.fetch(http, u, hosts, PHOTO_BYTES, types=PHOTO_TYPES, seconds=TIMEOUT):
            remaining -= len(p)
            if remaining < 0:
                return []
            album.append(p)
    return album


def sendable(photo: bytes) -> bool:
    """Telegram makes a photo of it: a JPEG, PNG or WebP, width and height at most 10000 together, the sides at most
    20:1 (Telegram refuses an album whole for one item it can't take). Reads only the header."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(photo)) as im:
            width, height = im.size
            return (im.format in ("JPEG", "PNG", "WEBP") and 0 < width + height <= 10000
                    and max(width, height) <= 20 * min(width, height))
    except Exception:  # noqa: BLE001 - Pillow raises many kinds on a broken or oversized header
        return False


async def gather(http: httpx.AsyncClient, album: Album) -> list[Part]:
    """The album's items ready to upload, in the post's order, within ALBUM_SECONDS. An item that fails (too large, not a
    photo Telegram takes, not H.264, a source error, out of time) is skipped and never holds up the others. All files
    together stay within ALBUM_BYTES: the photos first, then each video gets an even share of what is left (a share a
    video leaves unused goes to the next ones), and its best version within that share."""
    end = time.monotonic() + ALBUM_SECONDS
    ready: dict[int, Part] = {}
    budget = ALBUM_BYTES
    for i, url in enumerate(album.items):
        if not isinstance(url, str):
            continue
        try:
            async with asyncio.timeout(max(end - time.monotonic(), 0)):
                got = await photos(http, [url], album.hosts)
        except TimeoutError:
            break
        if got and len(got[0]) <= budget and sendable(got[0]):
            ready[i] = Part(got[0])
            budget -= len(got[0])
    videos = [(i, clip) for i, clip in enumerate(album.items) if isinstance(clip, Clip)]
    for n, (i, clip) in enumerate(videos):
        if time.monotonic() >= end:
            break
        clip.down = clip.down or any(c.down for _, c in videos)  # an album's outage counts once, as a clip's does
        try:
            part = await _video_part(http, clip, budget // (len(videos) - n), end)
        except Paused:
            break  # the source rests: its other videos would wait for a slot only to be refused; the photos still go
        if part:
            ready[i] = part
            budget -= part.size
    return [ready[i] for i in sorted(ready)]


async def _video_part(http: httpx.AsyncClient, clip: Clip, share: int, end: float) -> Part | None:
    """The clip's best version within `share` bytes, or None. Its download keeps its own time; the album's deadline
    only stops the wait (a cancellation: not the source's failure). Paused while the source rests."""
    cap = share - THUMB_BYTES
    try:
        async with asyncio.timeout(max(end - time.monotonic(), 0)):
            for version in await versions(http, clip):
                if cap <= 0 or version.size > cap:
                    continue  # a smaller version may fit
                # None: past the share for real, not H.264 after all, gone, or an outage (counted): the next may do
                upload = await prepare_upload(http, clip, version, cap=cap)
                if upload and len(upload[0]) <= cap and len(upload[1]) <= THUMB_BYTES:
                    return Part(*upload)
    except Paused:
        raise
    except Exception as exc:  # noqa: BLE001 - one item's failure (the album's deadline, ...) never sinks the album
        log.debug("group video: an album item failed: %s", type(exc).__name__)
    return None


async def fetch(http: httpx.AsyncClient, url: str) -> Clip | Album | list[str] | None:
    """What the link holds: a Clip, an Album (an Instagram post of photos or several items), a slideshow's photo URLs,
    or None (nothing to send: private, deleted, ...). Paused while the source rests after failures; a failure of the
    source itself raises (SourceDown, TimeoutError, yt-dlp's transport errors) and counts."""
    match = LINK.match(url)
    if not match:
        return None
    if match["story"]:
        return await _signed_fetch(match)  # stories need the session; none: no request at all
    if not match["tiktok"]:
        got = await _threaded(_extractors, EXTRACT_SECONDS, _extract, match,
                              source="youtube" if match["youtube"] else "instagram")
        return await _signed_fetch(match) if got is _SIGN_IN else got
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
            pairs.append(Version(f, private=clip.private))
        else:
            pairs.extend(Version(f, a, clip.private) for a in audio if a.get("vcodec") == "none")
    def quality(v: Version) -> tuple:
        width, height = v.video.get("width") or 0, v.video.get("height") or 0
        return min(width, height), width * height, v.direct, not v.audio, v.video.get("vbr") or 0

    return sorted((v for v in pairs if v.size <= MAX_BYTES), key=quality, reverse=True)



async def prepare_upload(http: httpx.AsyncClient, clip: Clip, version: Version, *, cap: int = 0):
    """The chosen version as (MP4, thumbnail, tracks), or None: past `cap` bytes (MAX_BYTES by default), not H.264,
    gone, too slow, or its source failed, so the next version may still come through. A clip's failures count once for
    its source's breaker. Paused while the source rests (the caller moves on)."""
    if clip.hosts == download.TIKTOK_FILES:
        data = await download.fetch(http, version.video["url"], clip.hosts, cap or MAX_BYTES, types=MEDIA_TYPES,
                                    seconds=DOWNLOAD_SECONDS)
        if not data:
            return None
        try:  # the remux has its own time: a slow download leaves it the same
            return await _threaded(_transfers, REMUX_SECONDS, upload, version, data, cap=cap)
        except TimeoutError:
            return None
    try:
        return await _threaded(_transfers, DOWNLOAD_SECONDS, upload, version, hosts=clip.hosts, source=clip.source,
                               count=not clip.down, cap=cap)
    except Paused:
        raise
    except Exception:  # an outage (_threaded returned None for the rest): counted, once for this clip
        clip.down = True
        return None


def upload(version: Version, source: bytes | None = None) -> tuple[bytes, bytes, dict] | None:
    """Download only the chosen streams. Copy them into a fast-start MP4 and take one frame for Telegram.
    Runs in _threaded: yt-dlp's connections pass _connect, every step sees the deadline. yt-dlp's errors propagate
    (_threaded tells an outage from a gone video); None for anything else that isn't sendable (too large, too long,
    not H.264, a child process out of time, or a format that becomes available only past the deadline)."""
    try:
        return _upload(version, source)
    except subprocess.SubprocessError:  # ffmpeg ran out of time (killed)
        return None


def _upload(version: Version, source: bytes | None) -> tuple[bytes, bytes, dict] | None:
    from .video import FORMATS, SAFE_IN
    if source is None and any((f.get("available_at") or 0) - time.time() >= _left()
                              for f in filter(None, (version.video, version.audio))):
        return None  # yt-dlp would sleep until then, past any deadline
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
                if not ok or not path.is_file():  # e.g. its Content-Length is past max_filesize
                    return None
            size += path.stat().st_size
            if not 0 < size <= _cap():
                return None
            inputs.extend(["-protocol_whitelist", "file", "-format_whitelist", FORMATS + ",mpegts,aac", "-i", str(path)])
        mp4 = Path(tmp, "video.mp4")
        ffmpeg = ["ffmpeg", "-nostdin", "-v", "error"]
        remux = _run([*ffmpeg, *inputs, "-map", "0:v:0", "-map", "1:a:0" if version.audio else "0:a:0?",
                      "-c", "copy", "-movflags", "+faststart", str(mp4)], FFMPEG_SECONDS)
        if remux.returncode or not mp4.is_file() or not 0 < mp4.stat().st_size <= _cap():
            return None
        tracks = _tracks(mp4)
        if tracks.get("vcodec") != "h264" or tracks.get("acodec") not in ("aac", "none"):
            return None
        if source is None and tracks.get("duration", 0) > MAX_SECONDS + 1:  # the real length, whatever was listed
            return None
        thumb = _run([*ffmpeg, *SAFE_IN, "-i", str(mp4), "-frames:v", "1", "-vf",
                      "scale=320:320:force_original_aspect_ratio=decrease", "-c:v", "mjpeg", "-threads", "1",
                      "-f", "image2pipe", "-"], 20, stdout=subprocess.PIPE)
        return mp4.read_bytes(), thumb.stdout if thumb.returncode == 0 and len(thumb.stdout) < THUMB_BYTES else b"", tracks
