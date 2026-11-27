"""Photos: whatever a phone sends is decoded, checked and re-encoded, never stored or served as it
came. That also strips EXIF (a phone photo carries the GPS spot where it was taken) and anything hidden in
the file; only the time it was taken is read first (taken: an album's order), nothing else of it is kept. Three
files per photo, named by the content hash so they can be cached forever: the cover (WebP, longest side 1600 px), a
thumbnail (WebP, 480 px) and a JPEG for Telegram's share cards (JPEG only)."""
from __future__ import annotations

import functools
import hashlib
import html
import io
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import download

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


def save(data: bytes, root: Path, key: bytes | None = None, trim: bool = False, logo: bool = False) -> dict:
    """key: what names the files instead of the upload's bytes (a random one: no hash that matches the same picture elsewhere).
    trim: an album photo, its baked-in bars cut off (trim_bars). logo: a club's logo, its dark frame cut off (trim_frame)."""
    with _busy:
        im = _decode(data)
        im = trim_bars(im) if trim else trim_frame(im) if logo else im
        return {**store(im, key or data, root), "taken": taken(data)}


def trim_frame(im: Image.Image, dark: int = 48) -> Image.Image:
    """A logo without the dark bars or frame a screenshot or an export bakes round it (Startup Inc's, Nov 27: thin black
    bars down its sides, read as the avatar's own edges). The frame is near-black on all four corners; the logo is the
    box of pixels lighter than that (a 3x3 min filter first: JPEG specks and the antialiased seam don't count). Cut only
    when each bar is under a third of its side and the logo's own edge just inside is mostly light, so a logo drawn on a
    dark ground keeps its ground. The rest goes back to a square on its own edge colour (the avatar shows it whole)."""
    g = im.convert("L")
    w, h = g.size
    if max(g.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))) > dark:
        return im
    box = g.point(lambda p: 255 if p > dark else 0).filter(ImageFilter.MinFilter(3)).getbbox()
    if not box or box == (0, 0, w, h):
        return im
    left, top, right, bottom = box
    if left > w / 3 or w - right > w / 3 or top > h / 3 or h - bottom > h / 3:
        return im
    # 2 px further in on a cut side: JPEG's ringing leaves a grey hairline along the seam
    box = (left + 2 * (left > 0), top + 2 * (top > 0), right - 2 * (right < w), bottom - 2 * (bottom < h))
    inner = g.crop(box)
    iw, ih = inner.size
    if iw < 8 or ih < 8:
        return im
    ring = [inner.getpixel((x, y)) for x in range(iw) for y in (1, ih - 2)] + [inner.getpixel((x, y)) for y in range(ih) for x in (1, iw - 2)]
    if sum(p > dark for p in ring) < 0.6 * len(ring):
        return im
    out = im.crop(box)
    edge = [out.getpixel(p) for p in ((1, 1), (iw - 2, 1), (1, ih - 2), (iw - 2, ih - 2))]
    fill = tuple(sorted(c[i] for c in edge)[1] for i in range(3))  # the lower middle of the four corners, per channel
    side = max(iw, ih)
    square = Image.new("RGB", (side, side), fill)
    square.paste(out, ((side - iw) // 2, (side - ih) // 2))
    return square


def trim_bars(im: Image.Image, tol: int = 12) -> Image.Image:
    """An album photo without the uniform near-black or near-white bars a screenshot bakes around it (a landscape
    shot saved as a 3:4 portrait). The bars are the colour of at least two corners; the photo is the box of pixels
    further than tol from it (a 3x3 min filter first, so JPEG specks in a bar don't count). A side is cut only when
    its bar is over 4% of the side, and never below half of the image."""
    g = im.convert("L")  # luminance near 0 (or 255) only when every channel is: a coloured pixel never passes for a bar
    w, h = g.size
    corners = [g.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    for edge in ([v for v in corners if v <= 16], [v for v in corners if v >= 239]):
        if len(edge) >= 2:
            break
    else:
        return im
    bg = sorted(edge)[len(edge) // 2]
    box = g.point(lambda p: 255 if abs(p - bg) > tol else 0).filter(ImageFilter.MinFilter(3)).getbbox()
    if not box:
        return im  # all one colour: nothing to keep apart from
    left, top, right, bottom = box
    left, right = (0 if left <= w * 0.04 else left), (w if w - right <= w * 0.04 else right)
    top, bottom = (0 if top <= h * 0.04 else top), (h if h - bottom <= h * 0.04 else bottom)
    if right - left < w / 2:
        left, right = 0, w
    if bottom - top < h / 2:
        top, bottom = 0, h
    return im if (left, top, right, bottom) == (0, 0, w, h) else im.crop((left, top, right, bottom))


_JPEG_MARKER = re.compile(rb"\xff([^\x00\xff\xd0-\xd7])")  # skip stuffed bytes and restart markers in a scan
_JPEG_IMAGE = frozenset((0xc0, 0xc1, 0xc2, 0xc4, 0xda, 0xdb, 0xdd))


def _gallery_jpeg(data: bytes) -> bool:
    """Only JPEG image segments and a thumbnail-free JFIF header, across every scan."""
    if not data.startswith(b"\xff\xd8"):
        return False
    pos, scan = 2, False
    while pos < len(data):
        while not scan and data[pos:pos + 2] == b"\xff\xff":
            pos += 1
        m = _JPEG_MARKER.search(data, pos) if scan else _JPEG_MARKER.match(data, pos)
        if m is None:
            return False
        marker, pos = m[1][0], m.end()
        if marker == 0xd9:
            return scan and pos == len(data)
        if pos + 2 > len(data):
            return False
        length = int.from_bytes(data[pos:pos + 2], "big")
        end = pos + length
        if length < 2 or end > len(data):
            return False
        if marker == 0xe0:
            if length != 16 or data[pos + 2:pos + 7] != b"JFIF\x00" or data[end - 2:end] != b"\x00\x00":
                return False
        elif marker not in _JPEG_IMAGE:
            return False
        pos, scan = end, marker == 0xda
    return False


def save_gallery(data: bytes, root: Path) -> dict:
    """The Gallery accepts canvas JPEGs and never reads an EXIF capture time."""
    if not _gallery_jpeg(data):
        raise BadImage("gallery metadata or format")
    with _busy:
        return store(trim_bars(_decode(data)), data, root)


ALMATY = timezone(timedelta(hours=5))  # a camera's clock without an offset tag: the campus's
# (time, its sub-seconds, its offset): DateTimeOriginal, then DateTimeDigitized (Exif IFD), then DateTime (IFD0)
_WHEN = ((0x9003, 0x9291, 0x9011), (0x9004, 0x9292, 0x9012), (0x0132, 0x9290, 0x9010))


def taken(data: bytes) -> float | None:
    """When a photo was taken (unix seconds) by its EXIF: the one fact read from it, for an album's order. None: no
    such tag, or one that can't be a real photo's (0000:00:00, before 2000, later than tomorrow)."""
    try:
        with Image.open(io.BytesIO(data), formats=FORMATS) as im:  # the header only: nothing is decoded
            ifd0 = im.getexif()
            exif = ifd0.get_ifd(0x8769)
        for at, sub, off in _WHEN:
            raw = exif.get(at) or ifd0.get(at)
            if not isinstance(raw, str):
                continue
            try:
                t = datetime.strptime(raw.strip("\0 ")[:19], "%Y:%m:%d %H:%M:%S")
                o = exif.get(off)
                tz = datetime.strptime(o.strip("\0 "), "%z").tzinfo if isinstance(o, str) and o.strip("\0 ") else ALMATY
            except ValueError:
                continue
            frac = str(exif.get(sub) or "").strip("\0 ")
            ts = t.replace(tzinfo=tz).timestamp() + (float(f"0.{frac}") if frac.isdigit() else 0)
            if 946684800 <= ts <= time.time() + 86400:  # 2000-01-01; a day ahead: a camera a time zone off
                return ts
    except Exception:  # a broken EXIF block is no reason to refuse the photo itself
        return None
    return None


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


@functools.lru_cache(maxsize=1)
def blank_jpg() -> bytes:
    """A plain grey picture: what a removed photo in the channel is edited to once Telegram won't delete it (48 h)."""
    out = io.BytesIO()
    Image.new("RGB", (320, 320), (142, 142, 147)).save(out, "JPEG", quality=70)
    return out.getvalue()


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
_EXTRA = re.compile(r'class="tgme_page_extra">\s*([\d\s]+|no)\s+(subscribers?|members?)')  # "no members": a group that hides its count


async def chat_peek(http: httpx.AsyncClient, url: str) -> dict:
    """A Telegram chat's public face from its t.me page (works for public links and invite links alike): title, avatar
    bytes, members. Empty fields when the page has none or Telegram is unreachable; the caller keeps what it had."""
    out: dict = {"title": None, "image": None, "members": None, "about": None, "ok": False}
    try:
        raw = await download.fetch(http, url, download.TELEGRAM_PAGE, 512 * 1024)
        if raw is None:
            return out
        out["ok"] = True
        page = raw.decode("utf-8", "replace")
        og = {k: html.unescape(v) for k, v in _OG.findall(page)}
        out["title"] = og.get("title") or None
        # the chat's own line; Telegram's stock "You can view and join ... right away" when it has none
        out["about"] = og.get("description") if og.get("description") and not re.match(r"You can (view|contact)", og["description"]) else None
        if m := _EXTRA.search(page):
            out["members"] = int(re.sub(r"\D", "", m.group(1)) or 0)
            out["channel"] = m.group(2).startswith("subscriber")  # a channel counts subscribers, a group members
        img = og.get("image", "")
        # Telegram's own placeholder (a chat without a picture) is its logo from telegram.org: not an avatar
        if re.match(r"https://[a-z0-9.-]+\.(?:telesco\.pe|cdn-telegram\.org)/file/", img):
            out["image"] = await download.fetch(http, img, download.TELEGRAM_FILES, MAX_BYTES)
    except (httpx.HTTPError, ValueError):
        pass
    return out
