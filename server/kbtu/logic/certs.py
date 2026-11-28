"""Certificates an org issues in bulk (first: AKO's course certificates, instead of a paid Zapier flow). Studio uploads a
template (a PDF's first page or a picture) and places fields on it (name, program, date, number, the verify link, its
QR); then a list (CSV: name, program, date, number) makes one numbered certificate per row, each with a public page
/c/<code> that says it is valid and whose it is.

No certificate's PDF is kept: it is drawn again from its row, its run's field layout and its template's background
whenever the team downloads it. Who runs it: the org's head and up where the org takes AKO applications (ako._access
"manage": never the creator's lent Studio; an org whose programs are all removed loses this desk, while /c/ keeps
answering). Holders have no account; what /c/ shows is in the privacy policy (section 17)."""
from __future__ import annotations

import base64
import contextlib
import csv
import hashlib
import hmac
import html
import io
import json
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import media, pdfpages, texts
from ..db import tx
from . import ako, core
from .core import ApiError, Viewer, one, rows

TEMPLATE_BYTES = 10 * 1024 * 1024
CSV_BYTES = 256 * 1024
SIDE = 2480                 # a template's background, its long side: ~210 dpi on A4, sharp in print, and a run's
                            # ZIP of 300 drawn well inside Cloudflare's 100 s
MAX_TEMPLATES = 30
MAX_ROWS = 300              # one run; its ZIP is drawn in one request
CERTS_A_DAY = 1000          # certificates one org may issue in a rolling day (Zapier's plan was 750 a month)
REVOKED_KEEP = 90 * 86400   # a revoked certificate's page says so this long, then it is gone
LINK_TTL = 300
FIELDS = ("name", "program", "date", "number", "link", "qr")
COLUMNS = ("name", "program", "date", "number")
LONGEST = {"name": 120, "program": 200, "date": 40, "number": 40}
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O, 1/I: read off paper; 10 of them are 50 bits
_CODE = re.compile(f"[{_ALPHABET}]{{10}}")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_FONTS = {False: ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
                  "/usr/share/fonts/noto/NotoSans-Regular.ttf"),
          True: ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/noto/NotoSans-Bold.ttf")}
# ponytail: one system font (the Dockerfile's fonts-dejavu-core: Latin, Cyrillic, Kazakh); the upgrade is an OFL font
# the designer picks, kept in the repository, or the template's own font uploaded beside it
_zip = threading.BoundedSemaphore(1)  # one ZIP drawn at a time; another is refused, never waits on a thread
_draw = threading.BoundedSemaphore(2)  # one PDF or preview is ~50 MB in flight: two at a time, the rest refused
_page = threading.BoundedSemaphore(1)  # a template PDF's first page: its own child, so applicants' uploads keep ako._pdf
_HEADERS = {k: {w.casefold() for w in ws} for k, ws in json.loads(ako.DATA.read_text(encoding="utf-8"))["certColumns"].items()}


def team(con, v: Viewer, oid: int) -> None:
    """The org's head and up (checked before an upload's body is read, and again by each step)."""
    if ako._access(con, v, oid) != "manage":
        raise ApiError("forbidden")


def url_of(domain: str, code: str) -> str:
    return f"https://{domain}/c/{code}"


def lang_of(accept: str) -> str:
    """The public page's language from the browser's Accept-Language: the first of ours it names, else Russian."""
    for part in accept.split(","):
        tag = part.split(";")[0].strip().lower()[:2]
        if tag in ako.LANGS:
            return tag
    return "ru"


# ---------------------------------------------------------------- templates

_COLS = "id, org_id, name, w, h, fields, created_at"  # all but the image


def _template(r, n: int = 0) -> dict:
    return {"id": r["id"], "name": r["name"], "w": r["w"], "h": r["h"], "fields": json.loads(r["fields"]), "certs": n,
            "createdAt": r["created_at"]}


def _of(con, oid: int, tid: object, cols: str = _COLS):
    t = one(con, f"SELECT {cols} FROM cert_templates WHERE id = ? AND org_id = ?", ako._id(tid), oid) if ako._id(tid) else None
    if not t:
        raise ApiError("not_found")
    return t


def _background(data: bytes) -> Image.Image:
    """The template's look as a picture: a PDF's first page (drawn in pdfpages' child, one at a time),
    or an image upright."""
    if data[:5] == b"%PDF-":
        if not _page.acquire(blocking=False):
            raise ApiError("rate_limited", "ako_busy")
        try:
            with tempfile.TemporaryDirectory(prefix="cert-pdf-") as out:
                try:
                    page = pdfpages.run(data, Path(out), 1, SIDE, 20, 1 << 30, cut=True)[0]
                except ValueError:
                    raise ApiError("bad_input", "bad_file") from None
                with Image.open(page) as im:
                    return im.convert("RGB")
        finally:
            _page.release()
    try:
        im = media.decode(data)
    except media.BadImage:
        raise ApiError("bad_input", "bad_file") from None
    im.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    return im.convert("RGB")


def add_template(con, v: Viewer, oid: int, name: object, data: bytes) -> dict:
    team(con, v, oid)
    im = _background(data)
    if min(im.size) < 300:
        raise ApiError("bad_input", "too_small")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88, optimize=True)
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM cert_templates WHERE org_id = ?", oid)[0] >= MAX_TEMPLATES:
            raise ApiError("rate_limited", "cert_templates")
        tid = con.execute("""INSERT INTO cert_templates (org_id, name, image, w, h, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (oid, ako._line(name, 80) or "Certificate", out.getvalue(), im.width, im.height,
                                              v.id, core.now())).lastrowid
        core.log_action(con, v.id, "cert_template", f"org:{oid}", json.dumps({"template": tid}))
    return _template(_of(con, oid, tid))


def _fields(x: object) -> list[dict]:
    """A layout: [{key, x, y, size, align?, color?, bold?, width?}] as fractions of the page: x, y the anchor; size the
    text's height, or the QR's side, as a share of the page's height; width the most a line may take (a longer one
    shrinks to fit)."""
    num = lambda f, lo, hi: isinstance(f, (int, float)) and not isinstance(f, bool) and lo <= f <= hi  # noqa: E731
    if not isinstance(x, list) or len(x) > 12:
        raise ApiError("bad_input", "fields")
    out = []
    for f in x:
        if not isinstance(f, dict) or f.get("key") not in FIELDS or not num(f.get("x"), 0, 1) or not num(f.get("y"), 0, 1) \
                or not num(f.get("size"), 0.005, 0.5) or f.get("align", "center") not in ("left", "center", "right") \
                or not isinstance(f.get("color", "#000000"), str) or not _COLOR.fullmatch(f.get("color", "#000000")) \
                or not isinstance(f.get("bold", False), bool) or not num(f.get("width", 1), 0.02, 1):
            raise ApiError("bad_input", "fields")
        out.append({"key": f["key"], "x": f["x"], "y": f["y"], "size": f["size"], "align": f.get("align", "center"),
                    "color": f.get("color", "#000000"), "bold": f.get("bold", False), "width": f.get("width", 1)})
    return out


def _count(con, tid: int) -> int:
    return one(con, "SELECT COUNT(*) FROM certs WHERE template_id = ?", tid)[0]


def update_template(con, v: Viewer, oid: int, tid: int, body: dict) -> dict:
    """A template's name or field layout. Certificates already issued keep their run's layout."""
    team(con, v, oid)
    with tx(con):
        _of(con, oid, tid)
        if "name" in body:
            con.execute("UPDATE cert_templates SET name = ? WHERE id = ?", (ako._line(body["name"], 80) or "Certificate", tid))
        if "fields" in body:
            con.execute("UPDATE cert_templates SET fields = ? WHERE id = ?", (json.dumps(_fields(body["fields"])), tid))
        core.log_action(con, v.id, "cert_template_edit", f"org:{oid}", json.dumps({"template": tid}))
    return _template(_of(con, oid, tid), _count(con, tid))


def drop_template(con, v: Viewer, oid: int, tid: int) -> None:
    """A template no certificate is drawn from: gone."""
    team(con, v, oid)
    with tx(con):
        _of(con, oid, tid)
        if one(con, "SELECT 1 FROM cert_runs WHERE template_id = ? LIMIT 1", tid):
            raise ApiError("conflict", "cert_template_used")
        con.execute("DELETE FROM cert_templates WHERE id = ?", (tid,))
        core.log_action(con, v.id, "cert_template_drop", f"org:{oid}", json.dumps({"template": tid}))


# ---------------------------------------------------------------- drawing

def _font(bold: bool, px: int) -> ImageFont.FreeTypeFont:
    for p in _FONTS[bold]:
        if Path(p).is_file():
            return ImageFont.truetype(p, px)
    raise RuntimeError("no font for certificates: install fonts-dejavu-core")


def _qr(d: ImageDraw.ImageDraw, text: str, x: int, y: int, side: int, align: str, color: str) -> None:
    import segno  # only where a certificate is drawn
    m = segno.make_qr(text, error="m").matrix
    n = len(m) + 4  # a light quiet zone of two modules, whatever the background
    unit = max(1, side // n)
    side = unit * n
    left, top = x - (side // 2 if align == "center" else side if align == "right" else 0), y - side // 2
    d.rectangle((left, top, left + side - 1, top + side - 1), fill="#ffffff")
    for r, line in enumerate(m):
        for c, dark in enumerate(line):
            if dark:
                d.rectangle((left + (c + 2) * unit, top + (r + 2) * unit, left + (c + 3) * unit - 1, top + (r + 3) * unit - 1), fill=color)


def draw(background: Image.Image, fields: list[dict], values: dict) -> Image.Image:
    """One certificate: the background with each field's value on it."""
    im = background.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    for f in fields:
        x, y = round(f["x"] * w), round(f["y"] * h)
        if f["key"] == "qr":
            _qr(d, values["link"], x, y, round(f["size"] * h), f["align"], f["color"])
            continue
        text = values.get(f["key"]) or ""
        if not text:
            continue
        px = max(8, round(f["size"] * h))
        font = _font(f["bold"], px)
        while px > 8 and d.textlength(text, font=font) > f["width"] * w:
            px = max(8, int(px * 0.92))
            font = _font(f["bold"], px)
        d.text((x, y), text, font=font, fill=f["color"], anchor={"left": "lm", "center": "mm", "right": "rm"}[f["align"]])
    return im


def _pdf(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.save(out, "PDF", resolution=round(max(im.size) / 11.69), quality=86)  # the long side as A4's 11.69 inches
    return out.getvalue()


def _bg(blob: bytes) -> Image.Image:
    with Image.open(io.BytesIO(blob)) as im:
        return im.convert("RGB")


SAMPLE = {"name": "Aigerim Nurlanovna Seitkali", "program": "Executive MBA: Business Administration for Executives",
          "date": "28.11.2026", "number": "AKO-2026-0001"}


@contextlib.contextmanager
def _drawing():
    if not _draw.acquire(blocking=False):
        raise ApiError("rate_limited", "cert_busy")  # the app tries again in a moment
    try:
        yield
    finally:
        _draw.release()


def preview(con, v: Viewer, oid: int, tid: int, domain: str) -> bytes:
    """The template with made-up values as a JPEG: what its certificates will look like (the server's font, not the
    browser's)."""
    team(con, v, oid)
    t = _of(con, oid, tid, "image, fields")
    with _drawing():
        im = draw(_bg(t["image"]), json.loads(t["fields"]), {**SAMPLE, "link": url_of(domain, "ABCDEFGHJK")})
        im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82)
        return out.getvalue()


# ---------------------------------------------------------------- the bulk run

def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # Excel's "Unicode text"
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")  # Excel's "CSV" from a Russian Windows


def parse(data: bytes) -> tuple[list[dict], list[dict]]:
    """The list's rows as {row, name, program, date, number}, and what is wrong in it as [{row, field, why}]. A first row
    naming the columns (en, ru, kk: i18n/ako.json certColumns) sets their order; one naming only some of them is refused
    (never issued as a certificate); without one, the order is name, program, date, number. Blank lines are skipped;
    row numbers are the lines a spreadsheet shows."""
    text = _decode(data)
    first = next((ln for ln in text.splitlines() if ln.strip(" ;,\t")), "")  # the header's line, as `head` below finds it
    try:
        lines = list(csv.reader(io.StringIO(text), delimiter=max(";,\t", key=first.count)))  # the first line's commonest (ties: ";")
    except csv.Error:  # an unclosed quote running past the field limit
        raise ApiError("bad_input", "bad_file") from None
    order: list[str | None] = list(COLUMNS)
    head = next((i for i, cells in enumerate(lines) if any(c.strip() for c in cells)), 0)
    start = 0
    if lines:
        named = [next((k for k, ws in _HEADERS.items() if " ".join(c.split()).casefold() in ws), None) for c in lines[head]]
        if set(COLUMNS) <= set(named):
            order, start = named, head + 1
        elif set(named) - {None}:  # one known word is enough: "Student,Course,..." must never become a certificate
            raise ApiError("bad_input", "cert_columns", {"row": head + 1, "missing": [k for k in COLUMNS if k not in named]})
    out, errors, seen = [], [], {}
    for n, cells in enumerate(lines[start:], start + 1):
        if not any(c.strip() for c in cells):
            continue
        if len(out) == MAX_ROWS:
            raise ApiError("bad_input", "cert_too_many", {"most": MAX_ROWS})
        r: dict = {"row": n}
        if not start and any(c.strip() for c in cells[len(COLUMNS):]):  # no header: a fifth column (an index?) shifts them all
            errors.append({"row": n, "field": "columns", "why": "extra"})
        for k, c in zip(order, cells):
            if k:
                r[k] = " ".join(ako._CTRL.sub(" ", c).split())
        for k in COLUMNS:
            got = r.setdefault(k, "")
            if not got or len(got) > LONGEST[k]:
                errors.append({"row": n, "field": k, "why": "empty" if not got else "long"})
        if r["number"] in seen:
            errors.append({"row": n, "field": "number", "why": "repeated", "first": seen[r["number"]]})
        elif r["number"]:
            seen[r["number"]] = n
        out.append(r)
    if not out:
        raise ApiError("bad_input", "cert_empty")
    return out, errors


def _code(con) -> str:
    while True:
        c = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        if not one(con, "SELECT 1 FROM certs WHERE code = ?", c):
            return c


def run(con, v: Viewer, oid: int, tid: object, data: bytes, dry: bool) -> dict:
    """A list made into certificates on a template, all or none: every row is checked first (a number this org has
    issued already is an error too). dry: only the check, nothing issued (the preview before the real run)."""
    team(con, v, oid)
    t = _of(con, oid, tid)
    if not json.loads(t["fields"]):
        raise ApiError("bad_input", "cert_no_fields")
    parsed, errors = parse(data)
    nums = [r["number"] for r in parsed if r["number"]]
    taken = {r[0] for r in rows(con, f"SELECT number FROM certs WHERE org_id = ? AND number IN ({core._qs(nums)})", oid, *nums)} if nums else set()
    errors = sorted(errors + [{"row": r["row"], "field": "number", "why": "issued"} for r in parsed if r["number"] in taken],
                    key=lambda e: e["row"])
    if dry:
        return {"rows": parsed, "errors": errors[:200]}
    if errors:
        raise ApiError("bad_input", "cert_rows", {"errors": errors[:200]})
    t0 = core.now()
    with tx(con):
        _of(con, oid, t["id"])  # not deleted meanwhile (its runs' foreign key would fail as a 500)
        if one(con, "SELECT COALESCE(SUM(count), 0) FROM cert_runs WHERE org_id = ? AND at > ?", oid, t0 - 86400)[0] + len(parsed) > CERTS_A_DAY:
            raise ApiError("rate_limited", "cert_runs")  # the runs' own rows: a certificate deleted still counts for its day
        rid = con.execute("INSERT INTO cert_runs (org_id, template_id, fields, count, by, at) VALUES (?, ?, ?, ?, ?, ?)",
                          (oid, t["id"], t["fields"], len(parsed), v.id, t0)).lastrowid
        for r in parsed:
            try:
                con.execute("""INSERT INTO certs (org_id, run_id, template_id, code, number, name, program, date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (oid, rid, t["id"], _code(con), r["number"], r["name"], r["program"], r["date"], t0))
            except sqlite3.IntegrityError:  # the same number issued meanwhile by another run
                raise ApiError("bad_input", "cert_rows", {"errors": [{"row": r["row"], "field": "number", "why": "issued"}]}) from None
        core.log_action(con, v.id, "cert_run", f"org:{oid}", json.dumps({"run": rid, "template": t["id"], "count": len(parsed)}))
    return {"run": rid, "count": len(parsed)}


# ---------------------------------------------------------------- the team's view and moves

def _cert(r) -> dict:
    return {"id": r["id"], "code": r["code"], "number": r["number"], "name": r["name"], "program": r["program"], "date": r["date"],
            "run": r["run_id"], "revoked": r["revoked_at"] is not None, "at": r["created_at"]}


def desk(con, v: Viewer, oid: int) -> dict:
    """Studio's certificates: the templates, the runs, the latest certificates (the client searches these)."""
    team(con, v, oid)
    counts = {r[0]: r[1] for r in rows(con, "SELECT template_id, COUNT(*) FROM certs WHERE org_id = ? GROUP BY template_id", oid)}
    return {"templates": [_template(t, counts.get(t["id"], 0)) for t in rows(con, f"SELECT {_COLS} FROM cert_templates WHERE org_id = ? ORDER BY id DESC", oid)],
            "runs": [{"id": r["id"], "template": r["template_id"], "count": r["count"], "at": r["at"]}
                     for r in rows(con, "SELECT id, template_id, count, at FROM cert_runs WHERE org_id = ? ORDER BY id DESC LIMIT 100", oid)],
            "certs": [_cert(r) for r in rows(con, "SELECT * FROM certs WHERE org_id = ? ORDER BY id DESC LIMIT 2000", oid)],
            "maxRows": MAX_ROWS, "perDay": CERTS_A_DAY}


def _mine(con, oid: int, cid: object):
    c = one(con, "SELECT * FROM certs WHERE id = ? AND org_id = ?", ako._id(cid), oid) if ako._id(cid) else None
    if not c:
        raise ApiError("not_found")
    return c


def update_cert(con, v: Viewer, oid: int, cid: int, body: dict) -> None:
    """Revoked (its page says so, without the name) or valid again: the undo."""
    team(con, v, oid)
    if not isinstance(body.get("revoked"), bool):
        raise ApiError("bad_input")
    with tx(con):
        c = _mine(con, oid, cid)
        con.execute("UPDATE certs SET revoked_at = ? WHERE id = ?", (core.now() if body["revoked"] else None, c["id"]))
        core.log_action(con, v.id, "cert_revoke" if body["revoked"] else "cert_restore", f"org:{oid}", json.dumps({"cert": c["id"]}))


def drop_cert(con, v: Viewer, oid: int, cid: int) -> None:
    """A certificate gone for good (its holder asked, or issued by mistake): its page says there is none."""
    team(con, v, oid)
    with tx(con):
        c = _mine(con, oid, cid)
        con.execute("DELETE FROM certs WHERE id = ?", (c["id"],))
        core.log_action(con, v.id, "cert_drop", f"org:{oid}", json.dumps({"cert": c["id"]}))


def sweep(con) -> None:
    """Nightly (daily.stats_day): certificates revoked REVOKED_KEEP ago; a ZIP a dropped download left behind."""
    with tx(con):
        con.execute("DELETE FROM certs WHERE revoked_at < ?", (core.now() - REVOKED_KEEP,))
    old = time.time() - 86400  # the disk's clock, not the rules'
    for f in Path(tempfile.gettempdir()).glob("certs-*.zip"):
        try:
            if f.stat().st_mtime < old:
                f.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- downloads: signed five-minute links

def _bound(con, what: str, xid: int) -> str | None:
    """What a link names besides the id, so an id used again later is another thing: a certificate's code, a run's org
    and time."""
    r = one(con, "SELECT code FROM certs WHERE id = ?", xid) if what == "f" else one(con, "SELECT org_id || ':' || at FROM cert_runs WHERE id = ?", xid)
    return f"{what}{xid}:{r[0]}" if r else None


def _sig(key: bytes, bound: str, exp: int) -> str:
    return hmac.new(key, f"cert-dl:{bound}:{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def link(con, v: Viewer, oid: int, what: str, xid: int, key: bytes) -> dict:
    """A link for a run's ZIP ("z") or one certificate's PDF ("f") of this org (Telegram's downloadFile and a browser tab
    send none of our headers)."""
    team(con, v, oid)
    r = one(con, f"SELECT {'revoked_at' if what == 'f' else 'NULL'} FROM {'certs' if what == 'f' else 'cert_runs'} WHERE id = ? AND org_id = ?", xid, oid)
    if not r:
        raise ApiError("not_found")
    if r[0] is not None:
        raise ApiError("closed", "cert_revoked")  # never printed again while its page says revoked
    exp = core.now() + LINK_TTL
    core.log_action(con, v.id, "cert_download", f"org:{oid}", json.dumps({what: xid}))
    return {"url": f"/api/certs/{what}/{xid}?e={exp}&s={_sig(key, _bound(con, what, xid), exp)}"}


def signed(con, what: str, xid: int, e: object, s: object, key: bytes) -> None:
    b = _bound(con, what, xid)
    if not (b and isinstance(e, str) and e.isascii() and e.isdigit() and len(e) < 12 and isinstance(s, str) and s.isascii()
            and hmac.compare_digest(s, _sig(key, b, int(e))) and int(e) >= core.now()):
        raise ApiError("not_found")


def _filename(c) -> str:
    """A certificate's file name from its number and name, nothing but word characters, spaces, dots and dashes (never
    a path)."""
    return (re.sub(r"[^\w .-]+", "", f"{c['number']} {c['name']}").strip(" .")[:100] or f"certificate {c['id']}") + ".pdf"


def _values(c, domain: str) -> dict:
    return {"name": c["name"], "program": c["program"], "date": c["date"], "number": c["number"], "link": url_of(domain, c["code"])}


def pdf_of(con, cid: int, domain: str) -> tuple[bytes, str]:
    """One certificate as a PDF (its link checked by signed()) and its download name."""
    c = one(con, """SELECT c.*, r.fields, t.image FROM certs c JOIN cert_runs r ON r.id = c.run_id
        JOIN cert_templates t ON t.id = c.template_id WHERE c.id = ? AND c.revoked_at IS NULL""", cid)
    if not c:
        raise ApiError("not_found")  # revoked after its link was made: never printed again
    with _drawing():
        return _pdf(draw(_bg(c["image"]), json.loads(c["fields"]), _values(c, domain))), _filename(c)


def zip_of(con, rid: int, domain: str) -> tuple[Path, str]:
    """A run's valid certificates as one ZIP in a temporary file (the caller removes it once sent), a PDF each."""
    r = one(con, "SELECT r.id, r.fields, t.image FROM cert_runs r JOIN cert_templates t ON t.id = r.template_id WHERE r.id = ?", rid)
    if not r:
        raise ApiError("not_found")
    if not _zip.acquire(blocking=False):
        raise ApiError("rate_limited", "cert_busy")  # the app tries again in a moment
    try:
        bg, fields, names = _bg(r["image"]), json.loads(r["fields"]), set()
        fd, tmp = tempfile.mkstemp(prefix="certs-", suffix=".zip")
        try:
            with open(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_STORED) as z:  # JPEG inside: compressed already
                for c in rows(con, "SELECT * FROM certs WHERE run_id = ? AND revoked_at IS NULL ORDER BY id", rid):
                    name = _filename(c)
                    if name in names:
                        name = f"{c['id']} {name}"
                    names.add(name)
                    z.writestr(name, _pdf(draw(bg, fields, _values(c, domain))))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    finally:
        _zip.release()
    return Path(tmp), f"certificates {rid}.zip"


# ---------------------------------------------------------------- the public page

def page(con, code: str, lang: str) -> tuple[int, str]:
    """(status, html) of /c/<code>: valid with whose and for what; revoked with its number only; or none (404)."""
    c = one(con, "SELECT * FROM certs WHERE code = ?", code.upper()) if _CODE.fullmatch(code.upper()) else None
    t, e = texts.CERT_PAGE[lang], html.escape

    def facts(*kv):
        return "<dl>" + "".join(f"<div><dt>{e(t[k])}</dt><dd>{e(v)}</dd></div>" for k, v in kv) + "</dl>"
    if not c:
        body = f'<div class="none">{_SEAL % _MARK["none"]}<h1>{e(t["none"])}</h1><p>{e(t["noneLine"])}</p></div>'
    elif c["revoked_at"] is not None:
        body = (f'<div class="obj">{_COLONNADE}<h1 class="st bad">{_SEAL % _MARK["bad"]}{e(t["revoked"])}</h1></div>'
                + facts(("number", c["number"])))
    else:
        org = ako._org(con, c["org_id"])["name"]
        body = (f'<div class="obj">{_COLONNADE}<p class="cap">{e(t["name"])}</p><h1 class="nm">{e(c["name"])}</h1>'
                f'<p class="st ok">{_SEAL % _MARK["ok"]}{e(t["valid"])}</p></div>'
                + facts(*((k, c[k]) for k in ("program", "date", "number")), ("by", org.get(lang) or org["ru"])))
    return (200 if c else 404), _HTML.replace("__LANG__", lang).replace("__TITLE__", e(t["title"])).replace("__BODY__", body)


# The app's look without its bundle (this page loads nothing; tokens.css's colours by hand), as Profile opens: one
# physical object first (the certificate, an ink card with the colonnade, its sheen kept inside it, the same in both
# themes as the lanyard badge is), its status a glass capsule on it with a tinted mark, then the facts as grouped rows on
# a solid 24 px card. No style attributes: the CSP allows this one sheet by hash.
_COLONNADE = ('<svg class="mark" viewBox="0 0 28 24" aria-hidden="true"><g fill="currentColor"><rect x="1" y="1.5" width="26" height="4" rx="1.5"/>'
              + "".join(f'<rect x="{x}" y="7" width="3" height="11" rx="1.5"/>' for x in (2, 7.25, 12.5, 17.75, 23))
              + '<rect y="19.5" width="28" height="3" rx="1.5"/></g></svg>')
_SEAL = ('<svg class="seal" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
         'aria-hidden="true"><path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 '
         '4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/><path d="%s"/></svg>')
_MARK = {"ok": "m9 12 2 2 4-4", "bad": "m15 9-6 6m0-6 6 6", "none": "M9.1 9a3 3 0 0 1 5.8 1c0 2-2.9 2.6-2.9 3.6M12 17h.01"}
_CSS = """:root{color-scheme:light dark;--bg:#F2F2F7;--card:#FFF;--rim:inset 0 0 0 .5px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.03),0 10px 24px -14px rgba(0,0,0,.12);--sep:rgba(60,60,67,.16);--text:#0A0A0C;--t2:rgba(60,60,67,.86);--t3:rgba(60,60,67,.72);--lift:0 24px 44px -20px rgba(11,20,51,.55)}
@media(prefers-color-scheme:dark){:root{--bg:#000;--card:#131314;--rim:inset 0 0 0 1px rgba(255,255,255,.075);--sep:rgba(255,255,255,.1);--text:#FFF;--t2:rgba(235,235,245,.74);--t3:rgba(235,235,245,.54);--lift:none}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:450 15px/1.4 'Inter Variable',Inter,-apple-system,system-ui,'Segoe UI',Roboto,sans-serif;letter-spacing:-.011em}
main{max-width:440px;margin:0 auto;padding:max(20px,7vh) 16px 32px}h1,p{margin:0}
.obj{position:relative;overflow:hidden;min-height:212px;display:flex;flex-direction:column;align-items:flex-start;padding:22px 22px 20px;border-radius:28px;color:#FFF;
background:radial-gradient(120% 90% at 0% 0%,rgba(255,120,200,.16),transparent 46%),radial-gradient(110% 90% at 100% 100%,rgba(90,190,255,.2),transparent 50%),linear-gradient(150deg,#1C2748,#0B1433 58%,#111A3C);
box-shadow:inset 0 1px 0 rgba(255,255,255,.28),inset 0 0 0 1px rgba(255,255,255,.1),var(--lift)}
.mark{display:block;width:34px;height:29px;margin-bottom:auto}
.obj::after{content:'';position:absolute;inset:0;border-radius:inherit;pointer-events:none;background:linear-gradient(115deg,transparent 38%,rgba(255,255,255,.07) 47%,transparent 58%)}
.cap{margin-top:28px;color:rgba(235,235,245,.7);font-size:13px;font-weight:600}
h1{font-size:22px;line-height:1.2;font-weight:700;letter-spacing:-.02em;overflow-wrap:anywhere}
.nm{margin-top:2px;font-size:clamp(24px,7.4vw,30px);line-height:1.12;letter-spacing:-.025em;text-wrap:balance}
.st{display:inline-flex;align-items:center;gap:6px;min-height:34px;margin-top:16px;padding:0 13px 0 9px;border-radius:999px;font-size:13px;line-height:1.2;font-weight:600;letter-spacing:0;
background:rgba(255,255,255,.1);box-shadow:inset 0 1px 0 rgba(255,255,255,.3),inset 0 0 0 1px rgba(255,255,255,.1)}
.seal{flex:none;width:20px;height:20px}.ok .seal{color:#5FD99A}.bad .seal{color:#FF8A80}
dl{margin:12px 0 0;padding:4px 20px;border-radius:24px;background:var(--card);box-shadow:var(--rim)}
dl div{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:14px 0}dl div+div{border-top:.5px solid var(--sep)}
dt{flex:none;color:var(--t2)}dd{margin:0;text-align:right;font-weight:600;letter-spacing:-.012em;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.none{padding:36px 24px;border-radius:24px;background:var(--card);box-shadow:var(--rim);text-align:center}.none .seal{width:40px;height:40px;margin:0 auto 14px;color:var(--t3);stroke-width:1.5}
.none p{margin-top:8px;color:var(--t2)}.foot{margin-top:20px;text-align:center;color:var(--t3);font-size:13px}"""
CSP = (f"default-src 'none'; style-src 'sha256-{base64.b64encode(hashlib.sha256(_CSS.encode()).digest()).decode()}'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_HTML = ('<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
         '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#F2F2F7">'
         '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000">'
         f'<meta name="robots" content="noindex"><title>__TITLE__</title><style>{_CSS}</style></head>'
         '<body><main>__BODY__<p class="foot">__TITLE__ · KBTU App</p></main></body></html>')
