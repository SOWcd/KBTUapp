"""The university's documents for the assistant (owner, Nov 10): handbooks, the academic calendar, curricula, syllabi,
electives lists. Built once by hand into a SEPARATE SQLite file (DOCS_DB, never the app's database, never the repo: the
documents and their text stay off GitHub), searched at each question: FTS5 bm25 over trigrams (Russian and Kazakh
endings match without a stemmer), plus cosine over Cloudflare Workers AI's bge-m3 embeddings when the file has them
(DOCS=hybrid), the two lists merged by reciprocal rank fusion. Only the documents' own text goes to Cloudflare at
build time; personal contacts are cut out before anything is stored (redact).

    python -m kbtu.docs build SRC_DIR OUT_DB   # text (scanned pages through tesseract), chunks, FTS; embeddings if CF_* set
    python -m kbtu.docs embed OUT_DB           # the chunks still without an embedding (CF_ACCOUNT_ID, CF_AI_TOKEN)
    python -m kbtu.docs ask OUT_DB "question"  # the top chunks, to look at
    python -m kbtu.docs audit OUT_DB           # anything left that looks like a contact: read it before DOCS=1
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import numpy as np

log = logging.getLogger("kbtu.docs")

MODEL = "@cf/baai/bge-m3"
CHUNK, OVERLAP = 900, 150      # characters: a chunk holds a rule with its context; four of them fit the prompt
POOL, RRF = 30, 60             # candidates per list; the fusion's constant (the usual 60)
COMMON = 0.2                   # a question's word in more than this share of chunks says nothing ("how", "can I")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEAD = re.compile(r"^(?:[Hh]eading ?|[Tt]itle)?[1-3]$|^[Tt]itle$")  # Word's heading styles ("1"-"3" in a Russian Word)
# personal contacts (the owner: documents go in without them; review, Nov 10). Every mailbox but the university offices'
# own (a person's is any other; one cut by a line break counts too), a mobile number with or without +7/8 (70x, 74x-78x;
# city lines, 71x and 72x, stay), a WhatsApp link, a Telegram handle that isn't the university's or a club's ("kbtu" in
# it), an IIN, a student ID (with the Cyrillic lookalikes OCR gives)
OFFICES = {"helpdesk", "officeregistrar", "library", "medcenter", "studentfee", "startup", "site_1course", "helpingstudents"}
_MAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*")
_MOBILE = re.compile(r"(?<![\d+])(?:(?:\+7|8)[\s(-]*7[04-8]\d[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}|7?7[04-8]\d{8})(?!\d)")
_WA = re.compile(r"(?:https?://)?(?:wa\.me|api\.whatsapp\.com)/\S+", re.I)
_IDS = re.compile(r"(?<!\d)\d{12}(?!\d)|\b\d{2}[Bb\u041c\u043c\u0412\u0432]\d{6}\b")
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z][\w.]{3,}")
_GLUE = re.compile(r"(@[\w-]+)\s*\n\s*(?=[\w-]*\.(?:com|ru|kz|org|net)\b)")  # "name@gmai" + line break + "l.com"


def _office(addr: str) -> bool:
    local, _, domain = addr.rpartition("@")
    return domain.lower() == "kbtu.kz" and re.sub(r"^[^A-Za-z0-9]+", "", local).lower() in OFFICES


def redact(text: str) -> tuple[str, int]:
    """The text without personal contacts, and how many were cut."""
    n = 0

    def cut(m: re.Match) -> str:
        nonlocal n
        n += 1
        return re.match(r"[^\x00-\x7f]*", m.group(0)).group(0) + "[...]"  # Cyrillic glued before an address stays
    text = _MAIL.sub(lambda m: m.group(0) if _office(m.group(0)) else cut(m), _GLUE.sub(r"\1", text))
    for rx in (_WA, _MOBILE, _IDS):
        text = rx.sub(cut, text)
    text = _HANDLE.sub(lambda m: m.group(0) if "kbtu" in m.group(0).lower() else cut(m), text)
    return text, n


def audit(path: str) -> dict:
    """What a built docs file still holds that looks like a contact (each kind's count and a few masked shapes); what
    redact keeps (office mailboxes, kbtu handles, city lines) is counted apart. For a person to read before going live."""
    looks = {"mail": _MAIL, "handle": re.compile(r"(?<![\w.])@[A-Za-z][\w.]{2,}"),
             "phone": re.compile(r"(?<![\d+])(?:(?:\+7|8)?[ (-]*7\d\d[ )-]*\d{3}[ -]*\d{2}[ -]*\d{2}|[78]?7\d{9})(?!\d)"), "whatsapp": re.compile(r"wa\.me|whatsapp\.com", re.I),
             "id": _IDS}
    out = {k: {"left": 0, "kept": 0, "shapes": []} for k in looks}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for (text,) in con.execute("SELECT title || ' \n' || at || ' \n' || text FROM chunks"):
        for kind, rx in looks.items():
            for m in rx.finditer(text):
                s = m.group(0)
                d = re.sub(r"\D", "", s)[-10:]
                ok = kind == "mail" and _office(s) or kind == "handle" and "kbtu" in s.lower() \
                    or kind == "phone" and d[:1] == "7" and d[1:2] in "12"  # a city line (727 Almaty, 717 Astana, ...)
                out[kind]["kept" if ok else "left"] += 1
                if not ok and len(out[kind]["shapes"]) < 5:
                    out[kind]["shapes"].append(re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "0", s)))
    con.close()
    return out


# ------------------------------------------------------------ text out of the files

def _runs(d: np.ndarray) -> np.ndarray:
    """Along each row: how long the run of True ending at each pixel is."""
    pos = np.arange(1, d.shape[1] + 1)
    return pos - np.maximum.accumulate(np.where(d, 0, pos), axis=1)


def _ruled_off(a: np.ndarray) -> np.ndarray:
    """A scanned table without its ruling (tesseract reads the cells' lines as letters and loses the rows): dark runs
    longer than an eighth of an inch across or down whitened, a pixel around them too."""
    d, m = a < 200, np.zeros(a.shape, bool)
    for t, back in ((d, lambda x: x), (d.T, lambda x: x.T)):
        m |= back(_runs(t) + _runs(t[:, ::-1])[:, ::-1] > 300 // 8)
    m[1:] |= m[:-1].copy()
    m[:, 1:] |= m[:, :-1].copy()
    return np.where(m, 255, a).astype(np.uint8)


def _ocr(page, *conf: str) -> str:
    """A scanned page (no text layer) through tesseract, as receipt.py reads receipts; no tesseract: nothing. With
    tesseract's "tsv": its words with their boxes, a table's ruling taken off first."""
    im = page.render(scale=300 / 72).to_pil().convert("L")
    if conf:
        from PIL import Image
        im = Image.fromarray(_ruled_off(np.asarray(im)))
    import io
    png = io.BytesIO()
    im.save(png, "PNG")
    try:
        r = subprocess.run(["tesseract", "stdin", "stdout", "-l", os.environ.get("DOCS_OCR", "rus+kaz+eng"), "--psm", "3", *conf],
                           input=png.getvalue(), capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.decode("utf-8", "replace")


def garbled(text: str) -> bool:
    """A text layer that's an old OCR's guess (Cyrillic read as Latin: "PFouoaucqL", "o6n0cru"): read it again."""
    ws = re.findall(r"[^\W_]{3,}", text)
    odd = sum(1 for w in ws if re.search(r"[a-z][A-Z]|[A-Za-z]\d+[a-z]|\d[a-z]", w) or re.search("[A-Za-z]", w) and re.search("[\u0400-\u04ff]", w))
    return len(ws) >= 10 and odd > 0.25 * len(ws)


def _cells(page, scan: bool) -> list[tuple]:
    """A page's text as (left, bottom, right, top, text) pieces in points: the text layer's runs (a table's cells), or a
    scan's words through tesseract glued along their line while closer than a letter's height (a cell's words)."""
    out = []
    if not scan:
        tp = page.get_textpage()
        for r in (tp.get_rect(i) for i in range(tp.count_rects())):
            s = " ".join(tp.get_text_bounded(*r).split())
            if out and min(r[3], out[-1][3]) - max(r[1], out[-1][1]) > 1 and -1 < r[0] - out[-1][2] < 1:  # a letter in another font (Kazakh's)
                p = out[-1]
                out[-1] = (p[0], min(p[1], r[1]), r[2], max(p[3], r[3]), p[4] + s)
            elif s:
                out.append((*r, s))
        return out
    k, h, line = 300 / 72, page.get_size()[1], None
    for row in _ocr(page, "tsv").splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        x, y, w, hh = (int(v) / k for v in f[6:10])
        cell = (x, h - y - hh, x + w, h - y, f[11].strip())
        if line == f[1:5] and out and x - out[-1][2] < hh:
            p = out[-1]
            out[-1] = (p[0], min(p[1], cell[1]), cell[2], max(p[3], cell[3]), f"{p[4]} {cell[4]}")
        else:
            out.append(cell)
        line = f[1:5]
    return out


# a curriculum (RUP): two tables side by side, odd semesters on the left, even on the right, each semester's rows ending
# in its total. Its rows start with a component (ru, kk, en: required, university's, elective)
_COMP = {"\u041e\u041a", "\u0412\u041a", "\u041a\u0412", "\u041c\u041a", "\u0416\u041a", "\u0422\u041a", "RC", "UC", "EC"}
_TOTAL = re.compile("^(?:\u0412\u0441\u0435\u0433\u043e|\u0418\u0442\u043e\u0433\u043e|\u0411\u0430\u0440\u043b\u044b\u0493\u044b|\u0416\u0438\u044b\u043d\u044b|Total|\\d{2,3}$)", re.I)  # or its sum alone
_SEM = re.compile("^(\\d{1,2})(?:st|nd|rd|th)?\\s*-?\\s*(?:\u0441\u0435\u043c\u0435\u0441\u0442\u0440|semester)", re.I)  # "3 semestr" as a scan reads
_PROG = re.compile("[\"\u00ab\u201c]\\s*(6[B\u0412]\\d{5}\\s*[-–]?\\s*[^\"\u00bb\u201d]{3,80})[\"\u00bb\u201d]")
RUP = re.compile("(?<![^\\W\\d_])(?:\u0440\u0443\u043f|rup)", re.I)  # a curriculum's file or folder: "RUP ..", "rupy 23bd"
CURR = "Curriculum (\u0420\u0423\u041f)"  # every curriculum chunk's first words: "RUP" as students say it
RUP_COLS = ("columns: component, code, course, cycle, credits (ECTS), contact hours a week, lectures/labs/seminars, "
            "assessment, prerequisites")


def _rows(cells: list[tuple]) -> list[str]:
    """Cells in table rows, top to bottom: cells that overlap in height are one row (a wrapped course name with its
    credits), read by column (cells overlapping in width are one, read downwards)."""
    rows, cur, low = [], [], None
    for c in sorted(cells, key=lambda c: -c[3]):
        if cur and c[3] - 0.3 <= low:
            rows.append(cur)
            cur = []
        cur.append(c)
        low = c[1] if len(cur) == 1 else min(low, c[1])
    rows.append(cur)
    out = []
    for row in filter(None, rows):
        cols, right = [], None
        for c in sorted(row):
            if cols and c[0] < right - 0.5:
                cols[-1].append(c)
                right = max(right, c[2])
            else:
                cols.append([c])
                right = c[2]
        out.append(" ".join(c[4] for col in cols for c in sorted(col, key=lambda c: -c[3])))
    return out


def rup(cells: list[tuple], head: str) -> list[str] | None:
    """A curriculum page as one text per semester, each opening with `head` and its semester ("semester 3", found
    by a question naming it), the rows one per line; the page's rest (titles, the cycles' totals) last. None: not a
    curriculum's table (no rows starting with a component)."""
    marks = sorted(c[0] for c in cells if c[4] in _COMP)
    if len(marks) < 4:
        return None
    gap, cut = max((b - a, b) for a, b in zip(marks, marks[1:]))
    cut = cut - 1 if gap > 100 else 1e9  # the right table's first column; one table across the page: no cut
    prog = next((m[1] for c in cells if (m := _PROG.search(c[4]))), "")
    sems: dict[int, list[str]] = {}
    rest: list[str] = []
    for side in (0, 1):
        n = 1 + side
        for line in _rows([c for c in cells if (c[0] >= cut) == side]):
            if m := _SEM.match(line):
                n = int(m[1])
            elif _TOTAL.match(line) and n in sems:
                sems[n].append(line)
                n += 2
            elif n in sems and not re.search(r"\d", line) and line.split(" ", 1)[0] not in _COMP:
                sems[n][-1] += f" {line}"  # a course name's wrapped end
            elif line.split(" ", 1)[0] in _COMP or n in sems:
                sems.setdefault(n, []).append(line)
            else:
                rest.append(line)
    if not sems:
        return None
    # the programme as the page names it, with its initials as students say it ("VTiPO")
    acr = "".join(w if w.isupper() else w[0].upper() if len(w) > 2 else w for w in re.findall(r"[^\W\d_]+", prog[8:]))
    top = f"{head}{' ' + prog if prog else ''}{f' ({acr})' if len(acr) > 2 else ''}"
    return [f"{top}, semester {n} ({RUP_COLS}):\n" + "\n".join(sems[n]) for n in sorted(sems)] + ([f"{top}:\n" + "\n".join(rest)] if rest else [])


def pages(path: Path, head: str = "") -> list[tuple[str, str]]:
    """(where, text) for each page of a PDF ("p. 3"), each heading's part of a .docx (its heading, or ""). With a
    curriculum's `head` (its programme and intake), its table pages come one text per semester (rup)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        try:
            out = []
            for i in range(len(pdf)):
                t = pdf[i].get_textpage().get_text_range()
                scan = len(t.strip()) < 40 or garbled(t)  # a scan, or a page of pictures
                if head:  # a curriculum: its table's rows, or at least its lines in order
                    cells = _cells(pdf[i], scan)
                    sems = rup(cells, head) or [f"{head}:\n" + "\n".join(_rows(cells))] if cells else []
                    out += [(f"p. {i + 1}", s) for s in sems]
                    continue
                out.append((f"p. {i + 1}", _ocr(pdf[i]) if scan else t))
            return out
        finally:
            pdf.close()
    if ext == ".docx":
        x = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
        out, head, buf = [], "", []
        for p in x.iter(_W + "p"):
            line = "".join(t.text or "" for t in p.iter(_W + "t")).strip()
            style = p.find(f"{_W}pPr/{_W}pStyle")
            if line and style is not None and _HEAD.match(style.get(_W + "val", "")):
                out.append((head, "\n".join(buf)))
                head, buf = line[:80], []
            buf.append(line)
        out.append((head, "\n".join(buf)))
        return [(h, t) for h, t in out if t.strip()]
    if ext == ".txt":
        return [("", path.read_text(errors="replace"))]
    return []


# files whose name says nothing to a student: the name to cite instead
NAMES = {"Q^0A": "FAQ \u043f\u0435\u0440\u0432\u043e\u043a\u0443\u0440\u0441\u043d\u0438\u043a\u0430"}  # "first-year FAQ"


def title(path: Path) -> str:
    """A file's name as a source the student reads: no extension, no "(3)" copy marks, spaces for underscores."""
    t = re.sub(r"\s*\(\d+\)", "", path.stem).replace("_", " ")
    return NAMES.get(path.stem) or " ".join(t.split())


_SPRING = re.compile("spring|\u0432\u0435\u0441\u043d|(?<![A-Za-z])S(?=\\d\\d(?!\\d))", re.I)  # spring, vesna, S26
_FALL = re.compile("fall|autumn|\u043e\u0441\u0435\u043d|(?<![A-Za-z])F(?=\\d\\d(?!\\d))", re.I)  # fall, osen, F26


def year(name: str) -> str | None:
    """The academic year a file's name says ("2026-27"): two years, "23-24", or a year with its semester (spring
    2024 is 2023-24, F26 is 2026-27); a bare year as it is; none: None."""
    if m := re.search(r"(20\d\d)\s*[-–_ ]\s*(?:20)?(\d\d)(?!\d)", name):
        return f"{m[1]}-{m[2]}"
    if (m := re.search(r"(?<!\d)(\d\d)[-_ ](\d\d)(?!\d)", name)) and int(m[2]) == int(m[1]) + 1:
        return f"20{m[1]}-{m[2]}"
    m = re.search(r"(?<!\d)20(\d\d)(?!\d)", name) or re.search(r"(?<![A-Za-z])[FS](\d\d)(?!\d)", name)
    if not m:
        return None
    y = 2000 + int(m[1])
    return f"{y - 1}-{y % 100:02d}" if _SPRING.search(name) else f"{y}-{(y + 1) % 100:02d}" if _FALL.search(name) else str(y)


def split(text: str) -> list[str]:
    """A page in chunks of about CHUNK characters along its lines, each starting with the last OVERLAP of the one before."""
    lines = [" ".join(x.split()) for x in text.splitlines()]
    out, cur = [], ""
    for line in filter(None, lines):
        while len(line) > CHUNK:  # a table row run together
            cut = line.rfind(" ", 0, CHUNK) if " " in line[:CHUNK] else CHUNK
            cur, line = f"{cur} {line[:cut]}".strip(), line[cut:].strip()
            out.append(cur)
            cur = cur[-OVERLAP:]
        cur = f"{cur}\n{line}".strip()
        if len(cur) >= CHUNK:
            out.append(cur)
            cur = cur[-OVERLAP:]
    if cur and (not out or len(cur) > OVERLAP):
        out.append(cur)
    return out


SCHEMA = """
CREATE TABLE chunks (id INTEGER PRIMARY KEY, doc TEXT NOT NULL, title TEXT NOT NULL, at TEXT NOT NULL, year TEXT, text TEXT NOT NULL, vec BLOB);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE fts USING fts5(title, text, content='chunks', content_rowid='id', tokenize='trigram remove_diacritics 1');
"""


def build(src: Path, out: Path, account: str = "", token: str = "") -> dict:
    """The documents under src into a new file at out (replaced whole at the end: a running server reads the old one
    until then). Returns what was read, skipped and cut."""
    tmp = out.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    report = {"docs": 0, "chunks": 0, "redacted": 0, "skipped": []}
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = str(f.relative_to(src))
        name = redact(title(f))[0]  # a file's name and a heading reach citations and embeddings too
        yr = year(f.stem) or year(str(Path(rel).parent))  # "2024-2025/6V04101 Management.pdf"
        # a curriculum's every chunk says whose and which intake (its year: the intake's, not the year it's in force)
        head = f"{CURR} {name}, intake {yr[:4] if yr else 'unknown'}" if RUP.search(rel) else ""
        try:
            got = pages(f, head)
        except Exception as exc:  # a broken file: the rest still builds
            got = []
            log.warning("%s: %s", rel, exc)
        n = 0
        for at, text in got:
            at, (text, cut) = redact(at)[0], redact(text)
            report["redacted"] += cut
            top, _, body = text.partition("\n") if head and text.startswith(head) else ("", "", text)
            for c in split(body):
                con.execute("INSERT INTO chunks (doc, title, at, year, text) VALUES (?, ?, ?, ?, ?)",
                            (rel, name, at, yr, f"{top}\n{c}" if top else c))
                n += 1
        if n:
            report["docs"] += 1
            report["chunks"] += n
        else:
            report["skipped"].append(rel)  # .doc, pictures, an empty scan
    con.execute("INSERT INTO fts (fts) VALUES ('rebuild')")
    con.execute("INSERT INTO meta (key, value) VALUES ('gen', ?)", (secrets.token_hex(8),))  # a search's snapshot key
    con.commit()
    con.close()
    tmp.replace(out)  # the words' search is ready; the embeddings come next, swapped in on their own
    if account and token:
        try:
            embed_all(out, account, token)
        except Exception as exc:  # the OCR pass isn't lost to Cloudflare's bad minute
            log.warning("embeddings stopped (%s): run `python -m kbtu.docs embed %s`", type(exc).__name__, out)
            report["embed"] = "stopped"
    return report


# ------------------------------------------------------------ embeddings (Cloudflare Workers AI)

def request(texts: list[str], account: str, token: str) -> dict:
    """The Cloudflare call for these texts' embeddings (httpx.post's or an AsyncClient.post's arguments)."""
    return {"url": f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}",
            "headers": {"Authorization": f"Bearer {token}"}, "json": {"text": texts}}


def vectors(r: httpx.Response) -> np.ndarray:
    """The answer's vectors, normalised (rows of float32). Raises httpx.HTTPError, or KeyError/ValueError on a bad body."""
    r.raise_for_status()
    v = np.asarray(r.json()["result"]["data"], dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def embed(texts: list[str], account: str, token: str, timeout: float = 60, tries: int = 4) -> np.ndarray:
    """bge-m3's vectors for these texts; a refusal or a network error is tried again after 2, 4, 8 s."""
    for i in range(tries):
        try:
            return vectors(httpx.post(**request(texts, account, token), timeout=timeout))
        except httpx.HTTPError:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))
    raise AssertionError  # not reached


def embed_all(path: Path, account: str, token: str, batch: int = 20) -> int:
    """Each chunk still without a vector gets one (its title with its text), in a copy swapped in at the end (a running
    server never reads a half-written file); resumable: what was done stays even when it stops."""
    work = path.with_suffix(".embedding")
    src, dst = sqlite3.connect(path), sqlite3.connect(work)
    src.backup(dst)
    src.close(), dst.close()
    con = sqlite3.connect(work)
    todo = con.execute("SELECT id, title, at, text FROM chunks WHERE vec IS NULL").fetchall()
    try:
        for i in range(0, len(todo), batch):
            part = todo[i:i + batch]
            vecs = embed([f"{t} {a}\n{x}" for _, t, a, x in part], account, token)
            con.executemany("UPDATE chunks SET vec = ? WHERE id = ?", [(v.tobytes(), r[0]) for v, r in zip(vecs, part)])
            con.commit()
    finally:
        con.execute("UPDATE meta SET value = ? WHERE key = 'gen'", (secrets.token_hex(8),))  # new vectors: a new snapshot
        con.commit()
        con.close()
        work.replace(path)
    return len(todo)


# ------------------------------------------------------------ search

_WORD = re.compile(r"\w{3,}")
# a question's own words ("when", "where", "can I", ...: Russian, Kazakh, English): the documents are mostly English
# tables, so these are rare there and bm25 would take any FAQ line that asks "when ..." for the answer
STOP = set((
    "\u043a\u043e\u0433\u0434\u0430 \u0433\u0434\u0435 \u043a\u0430\u043a \u043a\u0430\u043a\u043e\u0439 \u043a\u0430\u043a\u0430\u044f "
    "\u043a\u0430\u043a\u0438\u0435 \u043a\u0430\u043a\u0438\u0445 \u043a\u0430\u043a\u0443\u044e \u0447\u0442\u043e \u0447\u0435\u043c "
    "\u043a\u0442\u043e \u043c\u043e\u0436\u043d\u043e \u043d\u0443\u0436\u043d\u043e \u043d\u0430\u0434\u043e \u0441\u043a\u043e\u043b\u044c\u043a\u043e "
    "\u0431\u0443\u0434\u0435\u0442 \u0431\u0443\u0434\u0443\u0442 \u0435\u0441\u0442\u044c \u044d\u0442\u043e \u0434\u043b\u044f \u043f\u0440\u0438 "
    "\u0435\u0441\u043b\u0438 \u043c\u0435\u043d\u044f \u043c\u043d\u0435 \u0437\u0430\u0447\u0435\u043c \u043f\u043e\u0447\u0435\u043c\u0443 "
    "\u0447\u0435\u0440\u0435\u0437 \u043f\u043e\u0441\u043b\u0435 \u0438\u043b\u0438 \u0431\u044b\u043b \u0431\u044b\u043b\u0430 \u044d\u0442\u043e\u043c "
    "\u044d\u0442\u043e\u0442 \u0433\u043e\u0434\u0443 \u043d\u0430\u0441 \u043d\u0430\u043c \u0432\u0430\u0441 \u0432\u0430\u043c \u0441\u0432\u043e\u0439 "
    "\u043c\u043e\u0439 \u043c\u043e\u044f \u043c\u043e\u0438\u0445 \u0442\u043e\u0436\u0435 \u0443\u0436\u0435 \u0435\u0449\u0435 "
    "\u0431\u044b\u0432\u0430\u0435\u0442 \u0434\u0435\u043b\u0430\u0442\u044c \u0441\u0434\u0435\u043b\u0430\u0442\u044c "
    "\u049b\u0430\u0448\u0430\u043d \u049b\u0430\u0439\u0434\u0430 \u049b\u0430\u043b\u0430\u0439 \u049b\u0430\u043d\u0434\u0430\u0439 "
    "\u0434\u0435\u0433\u0435\u043d \u0436\u04d9\u043d\u0435 \u043c\u0435\u043d \u04af\u0448\u0456\u043d \u043a\u0435\u0440\u0435\u043a \u049b\u0430\u0439 \u0431\u0430\u0440 "
    "when where how what which who can the and for does need there are with this that from about you your"
).split())


def stem(w: str) -> str:
    """A light stemmer for trigram search: a long word loses its last two or three letters (a case or plural ending in
    Russian, a suffix in Kazakh), so "stipendiyu" finds "stipendiya"; short words and codes stay whole."""
    if w.isdigit() or not w.isalpha() or len(w) <= 5:
        return w
    return w[:-3] if len(w) > 8 else w[:-2]


class Index:
    """A docs file, opened read-only per search; its vectors held in memory once per worker, as one read-only snapshot
    keyed to the build's generation (meta.gen, read from the very connection that searches): a rebuild or an embed pass
    swapped in mid-search is seen by the next search, never mixed into this one."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._snap: tuple = (None, None, None, 0)  # (generation, ids, vectors or None, chunks)

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def _load(self, con) -> tuple:
        """This connection's build's snapshot: the one held, or read now (vectors of mixed lengths or not finite:
        none, the words' search alone)."""
        gen = con.execute("SELECT value FROM meta WHERE key = 'gen'").fetchone()[0]
        snap = self._snap
        if snap[0] == gen:
            return snap
        with self._lock:
            got = con.execute("SELECT id, vec FROM chunks WHERE vec IS NOT NULL").fetchall()
            ids = np.asarray([r[0] for r in got], dtype=np.int64)
            try:
                vecs = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in got]) if got else None
                if vecs is not None and not np.isfinite(vecs).all():
                    raise ValueError("not finite")
            except ValueError as exc:
                log.warning("docs: vectors unusable (%s): words only", exc)
                vecs = None
            if vecs is not None:
                vecs.setflags(write=False)
            self._snap = snap = (gen, ids, vecs, con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        return snap

    @property
    def vectors(self) -> bool:
        return self._snap[2] is not None

    def ready(self) -> bool:
        try:
            with self._con() as con:
                self._load(con)
            return True
        except (OSError, sqlite3.Error, TypeError):  # no file, or not a docs file
            return False

    def _fts(self, con, q: str, n: int, intake: int | None = None) -> list[list[int]]:
        q = q.lower().replace("\u0451", "\u0435")
        terms = list(dict.fromkeys(stem(w) for w in _WORD.findall(q) if w not in STOP))
        # a question about a curriculum: its semester and intake as the chunks say them (a year is too common a word
        # alone), the question's year, else the student's intake
        sems, cur = semesters(q), _CURQ.search(q)
        years = (re.findall(r"(?<!\d)20\d\d(?!\d)", q) or ([intake] if intake else [])) if cur or sems else []
        keep = [f'"semester {s}"' for s in sems] + [f'"intake {y}"' for y in dict.fromkeys(years)]
        for t in terms:  # the index's own common words drop out: no stop-word lists to keep in three languages
            m = '"' + t.replace('"', "") + '"'
            if con.execute("SELECT COUNT(*) FROM fts WHERE fts MATCH ?", (m,)).fetchone()[0] <= max(COMMON * n, 3):
                keep.append(m)
        if not keep:
            return []
        ask = lambda m: [r[0] for r in con.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts, 0.5, 1) LIMIT ?", (m, POOL))]  # noqa: E731
        # a question about a curriculum: the curricula's semesters ranked on their own beside the whole index (a FAQ's
        # "subjects" and "intake" outrank a table's rows), fused like the vectors' list
        return [ask(" OR ".join(keep))] + ([ask(f'"{CURR}" AND "(columns:" AND ({" OR ".join(keep)})')] if cur or sems else [])

    def search(self, q: str, qvec: np.ndarray | None = None, k: int = 4, intake: int | None = None) -> list[dict]:
        """The k best chunks for a question: bm25's list and, with a question's vector of the file's length, cosine's,
        fused by rank. One edition per handbook (the question's language when it has hits there): the three say the same.
        `intake`: the student's year of entry, its curricula first when the question names no year."""
        with self._con() as con:
            _, ids, vecs, n = self._load(con)
            lists = self._fts(con, q, n, intake)
            qv = None if qvec is None else np.asarray(qvec, dtype=np.float32).ravel()
            if vecs is not None and qv is not None and qv.shape == (vecs.shape[1],) and np.isfinite(qv).all():
                lists.append(ids[np.argsort(-(vecs @ qv))[:POOL]].tolist())
            score: dict[int, float] = {}
            for got in lists:
                for rank, cid in enumerate(got):
                    score[cid] = score.get(cid, 0) + 1 / (RRF + rank + 1)
            ranked = sorted(score, key=score.get, reverse=True)
            by = {r["id"]: dict(r) for r in con.execute(
                f"SELECT id, doc, title, at, year, text FROM chunks WHERE id IN ({','.join('?' * len(ranked))})", ranked)} if ranked else {}
        hits = [by[i] for i in ranked if i in by]
        mine, keep = _EDITION[lang_of(q)], {}
        for h in hits:
            if e := _ED.match(h["title"]):
                keep[e[2]] = mine if e[1] == mine else keep.get(e[2], e[1])  # the question's edition, else the best-ranked
        return [h for h in hits if not (e := _ED.match(h["title"])) or keep[e[2]] == e[1]][:k]


# ordinals 1-8 (en, ru, kk); "N semester" or "N year of study" ("kurs": its two semesters)
_ORD = ("first|\u043f\u0435\u0440\u0432|\u0431\u0456\u0440\u0456\u043d\u0448\u0456", "second|\u0432\u0442\u043e\u0440|\u0435\u043a\u0456\u043d\u0448\u0456",
        "third|\u0442\u0440\u0435\u0442|\u04af\u0448\u0456\u043d\u0448\u0456", "fourth|\u0447\u0435\u0442\u0432\u0435\u0440\u0442|\u0442\u04e9\u0440\u0442\u0456\u043d\u0448\u0456",
        "fifth|\u043f\u044f\u0442|\u0431\u0435\u0441\u0456\u043d\u0448\u0456", "sixth|\u0448\u0435\u0441\u0442|\u0430\u043b\u0442\u044b\u043d\u0448\u044b",
        "seventh|\u0441\u0435\u0434\u044c\u043c|\u0436\u0435\u0442\u0456\u043d\u0448\u0456", "eighth|\u0432\u043e\u0441\u044c\u043c|\u0441\u0435\u0433\u0456\u0437\u0456\u043d\u0448\u0456")
_SEMQ = re.compile("(?<!\\w)(?:(\\d{1,2})(?:-?[^\\W\\d]{0,3})?|" + "|".join(f"({o})[^\\W\\d]*" for o in _ORD)
                   + ")[\\s-]*(\u0441\u0435\u043c\u0435\u0441\u0442\u0440|semester|\u043a\u0443\u0440\u0441|year)"
                   "|(?:\u0441\u0435\u043c\u0435\u0441\u0442\u0440|semester)\\s*(\\d{1,2})(?!\\d)")


# a question about a curriculum (ru, kk, en): a semester, a year of study, the plan itself, credits, prerequisites, a code
_CURQ = re.compile("\u0441\u0435\u043c\u0435\u0441\u0442\u0440|semester|\u043a\u0443\u0440\u0441|year of study|\u0440\u0443\u043f|rup\\b|curricul"
                   "|\u0443\u0447\u0435\u0431\u043d\\w* \u043f\u043b\u0430\u043d|\u043e\u049b\u0443 \u0436\u043e\u0441\u043f\u0430\u0440|\u043a\u0440\u0435\u0434\u0438\u0442|credit|\u043f\u0440\u0435\u0440\u0435\u043a\u0432\u0438\u0437\u0438\u0442|prerequisit"
                   "|\\b[a-z]{3,4}\\d{3,4}\\b")


def semesters(q: str) -> list[int]:
    """The semesters a question names: "3rd semester", "semestr 3", "tretiy semestr", "2 kurs" (3 and 4)."""
    out = []
    for m in _SEMQ.finditer(q.lower()):
        n = int(m[1] or m[11] or next(i for i in range(1, 9) if m[i + 1]))
        out += [n] if m[11] or m[10] in ("semester", "\u0441\u0435\u043c\u0435\u0441\u0442\u0440") else [2 * n - 1, 2 * n]
    return [n for n in dict.fromkeys(out) if 1 <= n <= 12]


_ED = re.compile(r"^(RUS|KAZ|ENG) (.+)$")      # a handbook's three editions: "RUS Handbook 2026-2027"
_EDITION = {"ru": "RUS", "kk": "KAZ", "en": "ENG"}


def lang_of(q: str) -> str:
    """kk with a Kazakh letter, ru with any other Cyrillic, else en."""
    if re.search("[\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456]", q.lower()):
        return "kk"
    return "ru" if re.search("[\u0400-\u04ff]", q) else "en"


def cite(hits: list[dict]) -> str:
    """The chunks as the assistant's brief reads them: each with its source to cite."""
    def body(h: dict) -> str:  # a curriculum's rows stay one a line; its intake is in its text, not a year in force
        rows = [" ".join(x.split()) for x in h["text"].splitlines()]
        return "\n".join(filter(None, rows)) if h["text"].startswith(CURR) else " ".join(rows).strip()
    return "\n".join(f"[{h['title']}{', ' + h['at'] if h['at'] else ''}]"
                     f"{' (academic year ' + h['year'] + ')' if h.get('year') and not h['text'].startswith(CURR) else ''} {body(h)}"
                     for h in hits)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    acc, tok = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_AI_TOKEN", "").strip()
    cmd = sys.argv[1:2]
    if cmd == ["build"] and len(sys.argv) == 4:
        print(build(Path(sys.argv[2]), Path(sys.argv[3]), acc, tok))
    elif cmd == ["embed"] and len(sys.argv) == 3 and acc and tok:
        print(embed_all(Path(sys.argv[2]), acc, tok), "embedded")
    elif cmd == ["audit"] and len(sys.argv) == 3:
        print(json.dumps(audit(sys.argv[2]), indent=1))
    elif cmd == ["ask"] and len(sys.argv) == 4:
        ix = Index(sys.argv[2])
        qv = embed([sys.argv[3]], acc, tok)[0] if acc and tok and ix.ready() and ix.vectors else None
        print(cite(ix.search(sys.argv[3], qv, k=5)))
    else:
        sys.exit(__doc__)
