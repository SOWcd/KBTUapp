"""TikTok links in a group (TIKTOK=1): the bot answers a link with the video itself, so the chat watches it in place
instead of opening TikTok for each one. The file comes through tikwm.com, which hands out TikTok's own file without the
watermark; only the link goes there, never who sent it or where. The plain version is taken, H.264: TikTok's HD one is
HEVC, which Telegram's apps take long to process and some don't play (video.py keeps H.264 for the same reason). Nothing
is kept: the file lives in memory until it is sent. A photo slideshow (TikTok's photo mode) comes as its photos, an
album of up to ten (Telegram's most for one album). Anything that fails (a private or deleted video, one over Telegram's
50 MB, tikwm down) is no answer at all: the link stays a link, the chat gets no error."""
from __future__ import annotations

import re
import time
from typing import NamedTuple

import httpx

API = "https://www.tikwm.com/api/"
# tiktok.com and its short links (vm., vt.: what the app's Share copies)
LINK = re.compile(r"https?://(?:(?:www|m|vm|vt)\.)?tiktok\.com/[^\s<>\"']+", re.I)
MAX_BYTES = 50 * 1024 * 1024  # the most a bot may upload
PHOTO_BYTES = 10 * 1024 * 1024  # and one photo
ALBUM = 10                    # photos in one album at most
TIMEOUT = 30                  # each request: a stuck one never holds the queue behind it longer
CHAT_CAP = 5                  # answers a chat a minute: a burst of links never turns the chat into a feed
# ponytail: per worker (the bot polls in one) and its keys never pruned (a few bytes a chat); a table if that changes
_sent: dict[int, list[float]] = {}


def link(msg: dict) -> str | None:
    """The first TikTok link a person wrote (the text or a caption). Never a bot's: another downloader bot answers its
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


async def _get(http: httpx.AsyncClient, url: str, cap: int) -> bytes | None:
    """A file from TikTok's servers into memory; None past `cap` (a "size" that said less, or none) or on an error."""
    if not url.startswith("https://"):
        return None
    out = bytearray()
    async with http.stream("GET", url, timeout=TIMEOUT, follow_redirects=True) as r:
        if r.status_code != 200:
            return None
        async for chunk in r.aiter_bytes():
            out += chunk
            if len(out) > cap:
                return None
    return bytes(out)


async def fetch(http: httpx.AsyncClient, url: str) -> Media | None:
    """What a link holds, ready to send; None when there is nothing to send."""
    r = await http.post(API, data={"url": url}, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    body = r.json()
    data = body.get("data") if isinstance(body, dict) and body.get("code") == 0 else None
    if not isinstance(data, dict):
        return None
    if images := data.get("images"):  # a slideshow: its "play" is only the music
        photos = [p for u in images[:ALBUM] if isinstance(u, str) and (p := await _get(http, u, PHOTO_BYTES))]
        return Media(None, 0, photos) if photos and sum(map(len, photos)) <= MAX_BYTES else None
    if int(data.get("size") or 0) > MAX_BYTES:
        return None
    video = await _get(http, str(data.get("play") or ""), MAX_BYTES)
    return Media(video, int(data.get("duration") or 0), []) if video else None
