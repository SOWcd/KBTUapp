"""Captionless group video replies. Resolve and compare source formats before transferring a video."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import tempfile
import time
from collections import OrderedDict
from contextlib import nullcontext
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
URL_BYTES = 20 * 1024 * 1024
PHOTO_BYTES = 10 * 1024 * 1024  # and one photo
ALBUM = 10                    # photos in one album at most
TIMEOUT = 30                  # seconds per source request
_extractors = asyncio.Semaphore(2)  # leave the shared thread pool available to receipts and other bot updates
_probes = asyncio.Semaphore(4)
CHAT_CAP = 5                  # answers a chat a minute: a burst of links never turns the chat into a feed
# ponytail: per worker (the bot polls in one) and its keys never pruned (a few bytes a chat); a table if that changes
_sent: dict[int, list[float]] = {}


def link(msg: dict) -> str | None:
    """The first supported link a person wrote (the text or a caption). Never a bot's: another downloader bot answers its
    links with a video too, and two such bots would answer each other. Never the channel's own copy of a post in its
    discussion group: the post is the channel's, not a message someone sent to the chat."""
    if (msg.get("from") or {}).get("is_bot") or msg.get("is_automatic_forward"):
        return None
    m = LINK.search(str(msg.get("text") or msg.get("caption") or ""))
    return m.group(0) if m else None


def room(chat: int, now: float | None = None) -> bool:
    """One more video in this chat this minute (CHAT_CAP), counted when it says yes."""
    now = time.time() if now is None else now
    recent = [t for t in _sent.get(chat, ()) if now - t < 60]
    if len(recent) >= CHAT_CAP:
        _sent[chat] = recent
        return False
    _sent[chat] = [*recent, now]
    return True


@dataclass
class Clip:
    key: str
    duration: float
    formats: list[dict]
    cover: str = ""
    hosts: tuple[str, ...] = download.TIKTOK_FILES


@dataclass
class Version:
    video: dict
    audio: dict | None = None

    @property
    def size(self) -> int:
        return _size(self.video) + _size(self.audio or {})

    @property
    def direct(self) -> bool:
        f = self.video
        return (not self.audio and f["protocol"] == "https" and f.get("ext") == "mp4" and self.size <= URL_BYTES
                and bool(f.get("vcodec") and f.get("acodec") and f.get("width") and f.get("height")))


def _size(f: dict) -> int:
    return int(f.get("filesize") or f.get("filesize_approx") or 0)


CACHE_SIZE = 512
_files: OrderedDict[str, tuple[str, float]] = OrderedDict()


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


def cached(k: str) -> tuple[str, float] | None:
    if entry := _files.get(k):
        _files.move_to_end(k)
        return entry
    return None


def forget(k: str) -> None:
    _files.pop(k, None)


def remember(k: str, file_id: str, duration: float) -> None:
    if k:
        _files[k] = (file_id, duration)
        _files.move_to_end(k)
        if len(_files) > CACHE_SIZE:
            _files.popitem(last=False)


class TooLarge(ValueError):
    pass


def _limit(progress: dict) -> None:
    if (progress.get("downloaded_bytes") or 0) > MAX_BYTES:
        raise TooLarge("video too large")


def _downloader(**options):
    from yt_dlp import YoutubeDL
    return YoutubeDL({
        "js_runtimes": {"node": {}}, "cachedir": False, "noplaylist": True, "check_formats": False,
        "quiet": True, "noprogress": True,
        "logger": logging.Logger("yt-dlp", logging.CRITICAL + 1),  # extractor messages may contain the link
        "socket_timeout": TIMEOUT, "retries": 1, "max_filesize": MAX_BYTES, "progress_hooks": [_limit],
        "format_sort": ["res", "vcodec:h264", "acodec:aac"], "format_sort_force": True,
        "hls_prefer_native": True, "skip_unavailable_fragments": False,
        "external_downloader_args": {"ffmpeg_o": ["-fs", str(MAX_BYTES + 1)]}, **options,
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
        if info.get("_type", "video") != "video" or info.get("is_live"):
            return None
        if youtube and (not 0 < duration <= 180 or (match["short_host"] and duration >= 180)):
            return None
        info = dl.process_ie_result(info, download=False)
        hosts = ("googlevideo.com",) if youtube else ("cdninstagram.com", "fbcdn.net", "instagram.com")
        return Clip(key(match[0]), duration, info.get("formats") or [info], info.get("thumbnail") or "", hosts)


async def photos(http: httpx.AsyncClient, urls: list[str]) -> list[bytes]:
    album = []
    remaining = MAX_BYTES
    for u in urls:
        if p := await download.fetch(http, u, download.TIKTOK_FILES, PHOTO_BYTES):
            remaining -= len(p)
            if remaining < 0:
                return []
            album.append(p)
    return album


async def fetch(http: httpx.AsyncClient, url: str) -> Clip | list[str] | None:
    match = LINK.match(url)
    if not match:
        return None
    if not match["tiktok"]:
        async with _extractors:
            return await asyncio.to_thread(_extract, match)
    raw = await download.fetch(http, API, ("www.tikwm.com",), 1024 * 1024, form={"url": match[0], "hd": "1"})
    if not raw:
        return None
    body = json.loads(raw)
    data = body.get("data") if isinstance(body, dict) and body.get("code") == 0 else None
    if not isinstance(data, dict):
        return None
    if images := data.get("images"):  # its "play" is only the music
        return [u for u in images[:ALBUM] if isinstance(u, str)] or None
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
            if r.status_code not in (200, 206):
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


def _tracks(source: bytes | Path) -> dict:
    pipe = isinstance(source, bytes)
    proc = subprocess.run(["ffprobe", "-v", "quiet", "-protocol_whitelist", "pipe" if pipe else "file", "-f", "mov",
                           "-show_entries", "stream=codec_type,codec_name,width,height:stream_side_data=rotation:format=duration",
                           "-of", "json", "pipe:0" if pipe else str(source)],
                          input=source if pipe else None, stdout=subprocess.PIPE, timeout=10)
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
    formats = [f for f in clip.formats if f.get("protocol") in ("https", "m3u8", "m3u8_native", "http_dash_segments")
               and f["url"].startswith("https://") and not f.get("has_drm")]
    # Some Instagram variants also omit their codecs. Inspect those just as we do tikwm's two files.
    async def inspect(f):
        codecs = f.get("vcodec") and f.get("acodec")
        shape = f.get("vcodec") == "none" or (f.get("width") and f.get("height") and (clip.duration or f.get("duration")))
        if not (codecs and shape) and _size(f) <= MAX_BYTES and f["protocol"] == "https":
            try:
                async with _probes:
                    f.update(await _mp4_info(http, f, clip.hosts))
            except (OSError, httpx.HTTPError, httpx.InvalidURL, ValueError, subprocess.SubprocessError):
                pass
    await asyncio.gather(*(inspect(f) for f in formats))
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
    if clip.hosts == download.TIKTOK_FILES:
        data = await download.fetch(http, version.video["url"], clip.hosts, MAX_BYTES)
        return await asyncio.to_thread(upload, version, data) if data else None
    return await asyncio.to_thread(upload, version)


def upload(version: Version, source: bytes | None = None) -> tuple[bytes, bytes, dict] | None:
    """Download only the chosen streams. Copy them into a fast-start MP4 and take one frame for Telegram."""
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
                except (TooLarge, DownloadError, RequestError):
                    return None
                if not ok or not path.is_file():
                    return None
            size += path.stat().st_size
            if not 0 < size <= MAX_BYTES:
                return None
            inputs.extend(["-protocol_whitelist", "file", "-format_whitelist", FORMATS + ",mpegts,aac", "-i", str(path)])
        mp4 = Path(tmp, "video.mp4")
        ffmpeg = ["ffmpeg", "-nostdin", "-v", "error"]
        remux = subprocess.run([*ffmpeg, *inputs, "-map", "0:v:0", "-map", "1:a:0" if version.audio else "0:a:0?",
                                "-c", "copy", "-movflags", "+faststart", str(mp4)], stderr=subprocess.DEVNULL, timeout=60)
        if remux.returncode or not 0 < mp4.stat().st_size <= MAX_BYTES:
            return None
        tracks = _tracks(mp4)
        if tracks.get("vcodec") != "h264" or tracks.get("acodec") not in ("aac", "none"):
            return None
        thumb = subprocess.run([*ffmpeg, *SAFE_IN, "-i", str(mp4), "-frames:v", "1", "-vf",
                                "scale=320:320:force_original_aspect_ratio=decrease", "-c:v", "mjpeg", "-threads", "1",
                                "-f", "image2pipe", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
        return mp4.read_bytes(), thumb.stdout if thumb.returncode == 0 and len(thumb.stdout) < 200_000 else b"", tracks
