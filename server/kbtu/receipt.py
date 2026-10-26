"""Kaspi receipts (SPEC §4.3): whatever a student sends (Kaspi's PDF, a screenshot) becomes one picture, and what the
receipt says is read off that picture. Kaspi's iPhone PDF has no text in it (iOS draws the glyphs; checked on the
owner's receipts, Oct 10), so everything goes through OCR: Tesseract with the rus and kaz "fast" models (Debian's
tesseract-ocr-rus/-kaz), about half a second a receipt. Fields are found by their shape, not by the labels next to
them, since Kaspi may speak Kazakh. Nothing read here rejects a receipt: it only raises flags for the organizer."""
from __future__ import annotations

import difflib
import io
import logging
import os
import re
import subprocess
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageStat

from . import media

log = logging.getLogger("kbtu.receipt")

ASTANA = timezone(timedelta(hours=5))   # Kaspi prints "date and time in Astana"
SIDE = 3000                             # a PDF page is rendered at ~300 dpi, at most this many pixels long
_pdfium = threading.Lock()              # PDFium isn't thread-safe; rendering takes ~0.1 s
_ocr = threading.BoundedSemaphore(2)    # ponytail: two OCRs at a time; a rush of receipts waits its turn (~0.5 s each)


def picture(data: bytes) -> Image.Image:
    """The upload as one upright RGB picture: an image as for photos, or the first page of a PDF."""
    if data[:5] != b"%PDF-":
        return media.decode(data)
    with _pdfium:
        try:
            pdf = pdfium.PdfDocument(data)
            try:
                page = pdf[0]
                w, h = page.get_size()
                im = page.render(scale=min(300 / 72, SIDE / max(w, h, 1))).to_pil()
            finally:
                pdf.close()
        except (pdfium.PdfiumError, IndexError, ValueError) as exc:
            raise media.BadImage(type(exc).__name__) from None
    return im.convert("RGB")


def ready() -> str:
    """For the start-up log: whether OCR can run here (the image installs tesseract with the rus and kaz models)."""
    try:
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return "no tesseract"
    return "rus+kaz" if {"rus", "kaz"} <= set(langs) else "no rus/kaz models"


class NotReceipt(Exception):
    """OCR ran and found neither a sum nor a receipt number: not a Kaspi receipt (people sent selfies)."""


def take(data: bytes, root: Path) -> tuple[dict, dict | None]:
    """Reads the picture and, if it is a receipt, stores it privately under root (like a photo): (saved, fields).
    Anything else is refused before it is written (NotReceipt); without OCR every picture passes."""
    im = picture(data)
    got = read(im)
    if got is not None and not got.get("amount") and not got.get("no"):
        raise NotReceipt
    return media.store(im, data, root), got


def read(im: Image.Image) -> dict | None:
    """The receipt's fields, {} when nothing could be read, None when OCR isn't there to run (no flags then).
    Page segmentation 3 (automatic): of 26 variants (3 real receipts as PDF, phone screenshot and 727 px, JPEG q70,
    dark; a made-up one at 5 sizes) it read every field of 25, mode 4 of 23 (it dropped the big sum at some sizes),
    mode 6 missed the sum outright. Without the sum or the number (the two checks that matter), one more pass at 2/3
    of the size fills what's missing (Tesseract reads a line at one scale it drops at another)."""
    g = ImageOps.grayscale(im)
    if max(g.size) > SIDE:
        g.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    if ImageStat.Stat(g).mean[0] < 128:  # a dark-mode screenshot: light text on black
        g = ImageOps.invert(g)
    got = _ocr_pass(g)
    if got is not None and not ("amount" in got and "no" in got):
        again = _ocr_pass(g.resize((g.width * 2 // 3, g.height * 2 // 3), Image.Resampling.LANCZOS)) or {}
        got = {**again, **got}
    return got


def _ocr_pass(g: Image.Image) -> dict | None:
    # grey labels and the big green sum go black, the pale green band white (75 %: what worked on real receipts)
    png = io.BytesIO()
    g.point(lambda p: 255 if p > 191 else 0).save(png, "PNG")
    try:
        with _ocr:
            out = subprocess.run(["tesseract", "stdin", "stdout", "-l", "rus+kaz", "--psm", "3"], input=png.getvalue(),
                                 capture_output=True, timeout=30, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("ocr: %s", type(exc).__name__)
        return None
    if out.returncode:
        log.warning("ocr: exit %d", out.returncode)
        return None
    return parse(out.stdout.decode("utf-8", "replace"))


# "4 680 <tenge sign>", often read as "4680" and a Latin T or a Cyrillic capital te (U+0422) or small te (U+0442)
AMOUNT = re.compile(r"[-+]?\s*(\d{1,3}(?:[ \u00a0\u202f]?\d{3})*)(?:[.,]\d{2})?\s*[\u20b8T\u0422\u0442]")
WHEN = re.compile(r"(\d{2})[.,](\d{2})[.,](\d{4})\D{0,3}(\d{1,2})[:.](\d{2})")
NAME = re.compile(r"[^\W\d_]{2,}(?:-[^\W\d_]+)?\s+[^\W\d_]\.\s?(?:[^\W\d_]\.)?$")       # "Surname I.O." at a line's end
TO = re.compile(r"[^\W\d_]{2,}(?:-[^\W\d_]+)?\s+[^\W\d_]\.?")                          # the recipient's line: "Name S."


def parse(text: str) -> dict:
    """Fields by shape: the first "<number> ₸" line alone is the sum (the commission's line has a label), the first
    line that is only "Name S." the recipient, the first long digit run (and the digits-only line under it: Kaspi
    wraps the 18 digits) the receipt number, dd.mm.yyyy hh:mm the time, "Surname I.O." ending a line the sender."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    out: dict = {}
    if m := next((m for x in lines if (m := AMOUNT.fullmatch(x)) and int(re.sub(r"\D", "", m[1])) > 0), None):
        out["amount"] = int(re.sub(r"\D", "", m[1]))
    rec = next((i for i, x in enumerate(lines) if TO.fullmatch(x)), -1)
    if rec >= 0:
        out["recipient"] = lines[rec]
    for i, x in enumerate(lines):
        if m := re.search(r"\d{10,}", x):
            no = m[0] + (lines[i + 1] if i + 1 < len(lines) and re.fullmatch(r"\d{1,10}", lines[i + 1]) else "")
            if 15 <= len(no) <= 20:
                out["no"] = no
                break
    if m := WHEN.search(text):
        d, mo, y, h, mi = map(int, m.groups())
        try:
            out["paid_at"] = int(datetime(y, mo, d, h, mi, tzinfo=ASTANA).timestamp())
        except ValueError:
            pass
    for i, x in enumerate(lines):
        if i != rec and (m := NAME.search(x)):
            out["sender"] = m[0]
    return out


# Tesseract reads a Latin name with Russian shapes ("Arman A." comes out in Cyrillic letters: r, m and n as the
# italic ghe, te and pe), and an organizer may type the recipient in either alphabet: names are compared through both
# mappings. Cyrillic letters go by their Unicode names here (the repo's text is English).
_LOOK = str.maketrans({lat: unicodedata.lookup("CYRILLIC " + name) for lat, name in {
    "a": "SMALL LETTER A", "b": "SMALL LETTER SOFT SIGN", "c": "SMALL LETTER ES", "e": "SMALL LETTER IE", "h": "SMALL LETTER SHHA",
    "i": "SMALL LETTER BYELORUSSIAN-UKRAINIAN I", "k": "SMALL LETTER KA", "m": "SMALL LETTER TE", "n": "SMALL LETTER PE",
    "o": "SMALL LETTER O", "p": "SMALL LETTER ER", "r": "SMALL LETTER GHE", "u": "SMALL LETTER I", "x": "SMALL LETTER HA",
    "y": "SMALL LETTER U", "A": "CAPITAL LETTER A", "B": "CAPITAL LETTER VE", "C": "CAPITAL LETTER ES", "E": "CAPITAL LETTER IE",
    "H": "CAPITAL LETTER EN", "I": "CAPITAL LETTER BYELORUSSIAN-UKRAINIAN I", "K": "CAPITAL LETTER KA", "M": "CAPITAL LETTER EM",
    "O": "CAPITAL LETTER O", "P": "CAPITAL LETTER ER", "T": "CAPITAL LETTER TE", "X": "CAPITAL LETTER HA", "Y": "CAPITAL LETTER U"}.items()})
# Russian and Kazakh letters in Latin, as Kazakhstan's passports spell names
_LAT = {unicodedata.lookup("CYRILLIC SMALL LETTER " + name): lat for name, lat in {
    "A": "a", "SCHWA": "a", "BE": "b", "VE": "v", "GHE": "g", "GHE WITH STROKE": "g", "DE": "d", "IE": "e", "IO": "e", "ZHE": "zh",
    "ZE": "z", "I": "i", "SHORT I": "i", "BYELORUSSIAN-UKRAINIAN I": "i", "KA": "k", "KA WITH DESCENDER": "k", "EL": "l", "EM": "m",
    "EN": "n", "EN WITH DESCENDER": "n", "O": "o", "BARRED O": "o", "PE": "p", "ER": "r", "ES": "s", "TE": "t", "U": "u",
    "STRAIGHT U": "u", "STRAIGHT U WITH STROKE": "u", "EF": "f", "HA": "kh", "SHHA": "h", "TSE": "ts", "CHE": "ch", "SHA": "sh",
    "SHCHA": "sh", "HARD SIGN": "", "YERU": "y", "SOFT SIGN": "", "E": "e", "YU": "iu", "YA": "ia"}.items()}


def _letters(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalpha())


def same_person(printed: str, expected: str) -> bool:
    """Whether the name read off the receipt is the one the organizer set ("Name S." as Kaspi prints it): the
    initial must match, the name may differ by a letter or two (OCR). Typed without the initial (a first name alone; the owner's own event, Oct 11), the first names are compared."""
    lone = len(expected.split()) == 1
    if lone:
        printed = (printed.split() or [""])[0]
    lat = lambda s: "".join(_LAT.get(c, c) for c in s.lower())  # noqa: E731
    pairs = [(printed, expected), (printed, expected.translate(_LOOK)), (printed, lat(expected).translate(_LOOK)), (lat(printed), lat(expected))]
    for a, b in ((_letters(a), _letters(b)) for a, b in pairs):
        if a and b and (lone or a[-1] == b[-1]) and difflib.SequenceMatcher(None, *((a, b) if lone else (a[:-1], b[:-1]))).ratio() >= 0.75:
            return True
    return False
