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
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import media, pdfpages, texts
from ..db import tx
from . import ako, core
from .core import ApiError, Viewer, one, rows

TEMPLATE_BYTES = 10 * 1024 * 1024
CSV_BYTES = 256 * 1024
SIDE = 3000                 # a template's background, its long side: ~260 dpi on A4, sharp in print
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
    """The template's look as a picture: a PDF's first page (drawn in pdfpages' child, the admissions' two at a time),
    or an image upright."""
    if data[:5] == b"%PDF-":
        if not ako._pdf.acquire(blocking=False):
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
            ako._pdf.release()
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


def preview(con, v: Viewer, oid: int, tid: int, domain: str) -> bytes:
    """The template with made-up values as a JPEG: what its certificates will look like (the server's font, not the
    browser's)."""
    team(con, v, oid)
    t = _of(con, oid, tid, "image, fields")
    im = draw(_bg(t["image"]), json.loads(t["fields"]), {**SAMPLE, "link": url_of(domain, "ABCDEFGHJK")})
    im.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82)
    return out.getvalue()


# ---------------------------------------------------------------- the bulk run

def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")  # Excel's "CSV" from a Russian Windows


def parse(data: bytes) -> tuple[list[dict], list[dict]]:
    """The list's rows as {row, name, program, date, number}, and what is wrong in it as [{row, field, why}]. A first row
    naming the columns (en, ru, kk: i18n/ako.json certColumns) sets their order; without one, the order is name,
    program, date, number. Blank lines are skipped; row numbers are the lines a spreadsheet shows."""
    text = _decode(data)
    first = text.lstrip("\r\n").split("\n", 1)[0]
    lines = list(csv.reader(io.StringIO(text), delimiter=max(";,\t", key=first.count)))  # the first line's commonest (ties: ";")
    order: list[str | None] = list(COLUMNS)
    start = 0
    if lines:
        named = [next((k for k, ws in _HEADERS.items() if " ".join(c.split()).casefold() in ws), None) for c in lines[0]]
        if set(COLUMNS) <= set(named):
            order, start = named, 1
    out, errors, seen = [], [], {}
    for n, cells in enumerate(lines[start:], start + 1):
        if not any(c.strip() for c in cells):
            continue
        if len(out) == MAX_ROWS:
            raise ApiError("bad_input", "cert_too_many", {"most": MAX_ROWS})
        r: dict = {"row": n}
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
    """Nightly (daily.stats_day): certificates revoked REVOKED_KEEP ago."""
    with tx(con):
        con.execute("DELETE FROM certs WHERE revoked_at < ?", (core.now() - REVOKED_KEEP,))


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
    if not one(con, f"SELECT 1 FROM {'certs' if what == 'f' else 'cert_runs'} WHERE id = ? AND org_id = ?", xid, oid):
        raise ApiError("not_found")
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
        JOIN cert_templates t ON t.id = c.template_id WHERE c.id = ?""", cid)
    if not c:
        raise ApiError("not_found")
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
    if not c:
        body = f'<h1>{e(t["none"])}</h1><p>{e(t["noneLine"])}</p>'
    elif c["revoked_at"] is not None:
        body = f'<p class="bad">{e(t["revoked"])}</p><dl><dt>{e(t["number"])}</dt><dd>{e(c["number"])}</dd></dl>'
    else:
        org = ako._org(con, c["org_id"])["name"]
        facts = "".join(f"<dt>{e(t[k])}</dt><dd>{e(c[k])}</dd>" for k in ("program", "date", "number"))
        body = (f'<p class="ok">{e(t["valid"])}</p><h1>{e(c["name"])}</h1><dl>{facts}</dl>'
                f'<p class="by">{e(org.get(lang) or org["ru"])}</p>')
    return (200 if c else 404), _HTML.replace("__LANG__", lang).replace("__TITLE__", e(t["title"])).replace("__BODY__", body)


# ponytail: a plain page in the forms page's colours (logic/forms.py); the designer's brief is .claude/handoff/ako-certs.md
_CSS = """:root{color-scheme:light dark;--bg:#F2F2F7;--card:#FFF;--text:#0A0A0C;--t2:rgba(60,60,67,.86);--ok:#1F8A4C;--bad:#BA342E}
@media(prefers-color-scheme:dark){:root{--bg:#000;--card:#131314;--text:#FFF;--t2:rgba(235,235,245,.74);--ok:#5FD08A;--bad:#FF8A80}}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,system-ui,'Segoe UI',Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:32px 16px}section{padding:24px;border-radius:24px;background:var(--card)}
h1{margin:8px 0 16px;font-size:26px;line-height:1.2}.ok{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
dl{margin:0}dt{color:var(--t2);font-size:13px}dd{margin:0 0 12px}.by{color:var(--t2);margin:0}"""
CSP = (f"default-src 'none'; style-src 'sha256-{base64.b64encode(hashlib.sha256(_CSS.encode()).digest()).decode()}'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_HTML = ('<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
         f'<meta name="robots" content="noindex"><title>__TITLE__</title><style>{_CSS}</style></head>'
         '<body><main><section>__BODY__</section></main></body></html>')
