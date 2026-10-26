"""Photos (SPEC §9): whatever a phone sends is decoded, checked and re-encoded, never stored or served as it
came. That also strips EXIF (a phone photo carries the GPS spot where it was taken) and anything hidden in
the file. Three files per photo, named by the content hash so they can be cached forever: the cover (WebP,
longest side 1600 px), a thumbnail (WebP, 480 px) and a JPEG for Telegram's share cards (JPEG only)."""
from __future__ import annotations

import functools
import hashlib
import html
import io
import re
import threading
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageOps

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 50_000_000          # what a header may claim (Pillow refuses past twice this, warns between): a 48 MP iPhone JPEG, read smaller below (draft)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
DECODED = 16_000_000             # what is actually unpacked: 126 KB of PNG claiming 40 MP took ~460 MB
JPEG_SIDE = 2400                 # a JPEG is decoded at 1/2, 1/4 or 1/8 straight from the file, keeping both sides at
                                 # least this (the receipt's OCR reads 2400 px; photos keep 1600) unless that would
                                 # still be over DECODED (a 24 MP 6000x4000 photo goes to 3000x2000)
FORMATS = ("JPEG", "PNG", "WEBP", "GIF")   # the only parsers that see the bytes; JPEG's opens iPhone MPO files too
# two pictures at a time at most: each can take a few hundred MB while it is unpacked, and a burst of uploads
# shouldn't take the whole app (and its bot) down with it
_busy = threading.BoundedSemaphore(2)


class BadImage(ValueError):
    pass


def _fit(im: Image.Image, side: int) -> Image.Image:
    out = im.copy()
    out.thumbnail((side, side), Image.Resampling.LANCZOS)  # never upscales
    return out


def drop(root: Path, paths) -> None:
    """A saved picture's files (store: the picture, its thumbnail, a JPEG) gone from disk; one already gone, or None, is fine."""
    for rel in filter(None, paths):
        for ext in (".webp", ".t.webp", ".jpg"):
            (root / f"{rel}{ext}").unlink(missing_ok=True)


def save(data: bytes, root: Path) -> dict:
    with _busy:
        return store(_decode(data), data, root)


def decode(data: bytes) -> Image.Image:
    """The picture in an upload, upright, as RGB; anything else is BadImage."""
    with _busy:
        return _decode(data)


def _decode(data: bytes) -> Image.Image:
    try:
        # formats=: no other parser (TIFF, EPS, PSD...) ever reads the bytes, not even to say no
        with Image.open(io.BytesIO(data), formats=FORMATS) as probe:
            probe.verify()
        im = Image.open(io.BytesIO(data), formats=FORMATS)
        if im.format in ("JPEG", "MPO"):   # iPhone photos with a depth map open as MPO
            w, h, k = im.width, im.height, 1
            while k < 8 and (min(w, h) // (2 * k) >= JPEG_SIDE or (w // k) * (h // k) > DECODED):
                k *= 2
            im.draft("RGB", (w // k, h // k))   # draft takes one call only: the scale is chosen up front (rounded up, 6001 px wouldn't halve)
        if im.width * im.height > DECODED:
            raise BadImage(f"{im.format} {im.width}x{im.height}")
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            # transparent parts (a club's PNG logo) go white, not black
            return Image.alpha_composite(Image.new("RGBA", im.size, "white"), im.convert("RGBA")).convert("RGB")
        return im.convert("RGB")
    except BadImage:
        raise
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise BadImage(type(exc).__name__) from None


def store(im: Image.Image, data: bytes, root: Path) -> dict:
    """Writes the three files of a decoded picture under root/<2 hex>/<sha256 of the upload>.*; returns what the
    files table keeps."""
    sha = hashlib.sha256(data).hexdigest()
    rel = f"{sha[:2]}/{sha}"
    (root / sha[:2]).mkdir(parents=True, exist_ok=True)
    big = _fit(im, 1600)
    big.save(root / f"{rel}.webp", "WEBP", quality=80, method=6)
    _fit(im, 480).save(root / f"{rel}.t.webp", "WEBP", quality=74, method=6)
    _fit(im, 1200).save(root / f"{rel}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    r, g, b = im.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))  # the average colour, for the sheet tint
    return {"sha256": sha, "path": rel, "width": big.width, "height": big.height,
            "bytes": (root / f"{rel}.webp").stat().st_size, "color": f"#{r:02x}{g:02x}{b:02x}"}


@functools.lru_cache(maxsize=64)
def poster_jpg(color: str, emoji: Path) -> bytes:
    """A coverless event's picture for its share card, as the app draws it (ui/Poster.svelte): the 3D emoji on the
    event's colour under a soft white light at the top left. The emoji is drawn at its own size (160 px): scaled up it
    blurs, so the canvas is small instead and Telegram scales the whole card evenly."""
    w, h = 512, 320
    base = Image.new("RGB", (w, h), color)
    light = Image.new("L", (w, h), 0)
    ImageDraw.Draw(light).ellipse((-0.3 * w, -0.3 * h, 0.9 * w, 0.6 * h), fill=72)  # ~0.28 white, as the app's
    base.paste((255, 255, 255), mask=light.filter(ImageFilter.GaussianBlur(70)))
    with Image.open(emoji) as em:
        em = em.convert("RGBA")
        base.paste(em, ((w - em.width) // 2, (h - em.height) // 2), em)
    out = io.BytesIO()
    base.save(out, "JPEG", quality=90)
    return out.getvalue()


_OG = re.compile(r'<meta property="og:(title|image|description)" content="([^"]*)"')
_EXTRA = re.compile(r'class="tgme_page_extra">\s*([\d\s]+)\s+(subscribers?|members?)')


async def chat_peek(http: httpx.AsyncClient, url: str) -> dict:
    """A Telegram chat's public face from its t.me page (works for public links and invite links alike): title, avatar
    bytes, members. Empty fields when the page has none or Telegram is unreachable; the caller keeps what it had."""
    out: dict = {"title": None, "image": None, "members": None, "about": None, "ok": False}
    try:
        r = await http.get(url, follow_redirects=True)
        out["ok"] = r.status_code == 200  # False: Telegram didn't answer (a timeout, a 429), not "no such chat"
        page = r.text
        og = {k: html.unescape(v) for k, v in _OG.findall(page)}
        out["title"] = og.get("title") or None
        # the chat's own line; Telegram's stock "You can view and join ... right away" when it has none
        out["about"] = og.get("description") if og.get("description") and not re.match(r"You can (view|contact)", og["description"]) else None
        if m := _EXTRA.search(page):
            out["members"] = int(re.sub(r"\D", "", m.group(1)))
            out["channel"] = m.group(2).startswith("subscriber")  # a channel counts subscribers, a group members
        img = og.get("image", "")
        # Telegram's own placeholder (a chat without a picture) is its logo from telegram.org: not an avatar
        if re.match(r"https://[a-z0-9.-]+\.(?:telesco\.pe|cdn-telegram\.org)/file/", img):
            r = await http.get(img)
            if r.status_code == 200 and len(r.content) <= MAX_BYTES:
                out["image"] = r.content
    except (httpx.HTTPError, ValueError):
        pass
    return out
