"""Group video replies (TIKTOK=1). TikTok's plain H.264 file or photo album comes through tikwm.com.
YouTube and Instagram supply their own media through yt-dlp. Only the link goes to the source.
The bot holds the finished upload in memory and a failed download leaves the chat alone."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

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
PHOTO_BYTES = 10 * 1024 * 1024  # and one photo
ALBUM = 10                    # photos in one album at most
TIMEOUT = 30                  # each request: a stuck one never holds the queue behind it longer
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


class Media(NamedTuple):
    video: bytes | None   # a video, or None for a slideshow
    seconds: int          # the video's length (0: unknown)
    photos: list[bytes]   # a slideshow's photos, in order
    filename: str = "tiktok.mp4"


def _format(ctx: dict):
    """Choose one complete source file. yt-dlp supplies formats in ascending quality order."""
    formats = ctx["formats"]
    silent = all(f.get("acodec") == "none" for f in formats)
    candidates = []
    for f in reversed(formats):
        if f["protocol"] != "https" or f.get("vcodec") == "none" or (f.get("acodec") == "none" and not silent):
            continue
        # A vertical 720p reel is 720x1280.
        side = min(f.get("width") or float("inf"), f.get("height") or float("inf"))
        if side <= 720 and (f.get("filesize") or f.get("filesize_approx") or 0) < MAX_BYTES:
            candidates.append(f)
    if candidates:
        yield max(candidates, key=lambda f: (f["ext"] == "mp4", (f.get("vcodec") or "").startswith(("avc", "h264"))))


def _limit(progress: dict) -> None:
    if (progress.get("downloaded_bytes") or 0) >= MAX_BYTES:
        raise ValueError("video too large")


def _download(match: re.Match) -> Media | None:
    from yt_dlp import YoutubeDL  # loaded on the download thread, only when the feature is used
    from .video import SAFE_IN

    youtube = match["youtube"]
    url = f"https://www.youtube.com/watch?v={youtube}" if youtube else f"https://www.instagram.com/p/{match['instagram']}/"
    with tempfile.TemporaryDirectory() as tmp, YoutubeDL({
        "allowed_extractors": ["youtube" if youtube else "instagram"], "js_runtimes": {"node": {}},
        "outtmpl": f"{tmp}/source", "cachedir": False, "noplaylist": True,
        "logger": logging.Logger("yt-dlp", logging.CRITICAL + 1),  # extractor messages can contain the shared URL
        "socket_timeout": TIMEOUT, "retries": 1, "format": _format, "max_filesize": MAX_BYTES - 1,
        "progress_hooks": [_limit], "fixup": "never",
    }) as dl:
        info = dl.extract_info(url, download=False, process=False)
        if not info:
            return None
        if not youtube and info.get("_type") == "playlist":
            # A mixed Instagram carousel may begin with photos. Reply with its first video.
            info = next((e for e in info["entries"] if e.get("formats")), None)
            if not info:
                return None
            dl.add_default_extra_info(info, dl.get_info_extractor("Instagram"), url)
        duration = info.get("duration") or 0
        if info.get("_type", "video") != "video" or info.get("is_live"):
            return None
        if youtube and (not 0 < duration <= 180 or (match["short_host"] and duration >= 180)):
            return None
        selected = dl.process_ie_result(info)
        path = Path(tmp, "source")
        if not path.is_file() or not 0 < path.stat().st_size < MAX_BYTES:
            return None
        if selected["ext"] != "mp4":
            mp4 = Path(tmp, "video.mp4")
            # Stop oversized encodes beyond the upload cap so the final check also rejects a truncated output.
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", *SAFE_IN, "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-threads", "2", "-movflags", "+faststart",
                            "-fs", str(MAX_BYTES + 1024 * 1024), str(mp4)], stderr=subprocess.DEVNULL, check=True, timeout=120)
            if not 0 < mp4.stat().st_size < MAX_BYTES:
                return None
            path = mp4
        return Media(path.read_bytes(), int(duration), [], "video.mp4")


async def fetch(http: httpx.AsyncClient, url: str) -> Media | None:
    """What a link holds, ready to send; None when there is nothing to send."""
    match = LINK.match(url)
    if not match:
        return None
    if not match["tiktok"]:
        return await asyncio.to_thread(_download, match)
    raw = await download.fetch(http, API, ("www.tikwm.com",), 1024 * 1024, form={"url": match[0]})
    if not raw:
        return None
    body = json.loads(raw)
    data = body.get("data") if isinstance(body, dict) and body.get("code") == 0 else None
    if not isinstance(data, dict):
        return None
    if images := data.get("images"):  # a slideshow: its "play" is only the music
        photos, total = [], 0
        for u in images[:ALBUM]:
            if isinstance(u, str) and (p := await download.fetch(http, u, download.TIKTOK_FILES, PHOTO_BYTES)):
                total += len(p)
                if total > MAX_BYTES:
                    return None
                photos.append(p)
        return Media(None, 0, photos) if photos else None
    if int(data.get("size") or 0) > MAX_BYTES:
        return None
    video = await download.fetch(http, str(data.get("play") or ""), download.TIKTOK_FILES, MAX_BYTES)
    return Media(video, int(data.get("duration") or 0), []) if video else None
