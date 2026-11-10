"""The university's documents for the assistant (owner, Nov 10): handbooks, the academic calendar, curricula, syllabi,
electives lists. Built once by hand into a SEPARATE SQLite file (DOCS_DB, never the app's database, never the repo: the
documents and their text stay off GitHub), searched at each question: FTS5 bm25 over trigrams (Russian and Kazakh
endings match without a stemmer), plus cosine over Cloudflare Workers AI's bge-m3 embeddings when the file has them
(DOCS=hybrid), the two lists merged by reciprocal rank fusion. Only the documents' own text goes to Cloudflare at
build time; personal contacts are cut out before anything is stored (redact).

    python -m kbtu.docs build SRC_DIR OUT_DB   # text (scanned pages through tesseract), chunks, FTS; embeddings if CF_* set
    python -m kbtu.docs embed OUT_DB           # the chunks still without an embedding (CF_ACCOUNT_ID, CF_AI_TOKEN)
    python -m kbtu.docs ask OUT_DB "question"  # the top chunks, to look at
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
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
# personal contacts (the owner: documents go in without them): a person's mailbox (initial.surname@, any mail outside
# kbtu.kz), a mobile number (+7 70x, 74x-78x; city lines, 72x and 71x, stay), an IIN, a student ID
_MAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)+")
_PERSON_MAIL = re.compile(r"^[a-z]{1,2}\.[a-z-]+@|@(?!kbtu\.kz$)", re.I)
_MOBILE = re.compile(r"(?<![\d+])(?:\+7|8)[\s(-]*7[04-8]\d[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
_IDS = re.compile(r"(?<!\d)\d{12}(?!\d)|\b\d{2}[Bb\u041c\u043c]\d{6}\b")


def redact(text: str) -> tuple[str, int]:
    """The text without personal contacts, and how many were cut."""
    n = 0

    def cut(m: re.Match, keep=lambda s: False) -> str:
        nonlocal n
        if keep(m.group(0)):
            return m.group(0)
        n += 1
        return "[...]"
    text = _MAIL.sub(lambda m: cut(m, lambda s: not _PERSON_MAIL.search(s)), text)
    text = _MOBILE.sub(cut, text)
    return _IDS.sub(cut, text), n


# ------------------------------------------------------------ text out of the files

def _ocr(page) -> str:
    """A scanned page (no text layer) through tesseract, as receipt.py reads receipts; no tesseract: nothing."""
    im = page.render(scale=300 / 72).to_pil().convert("L")
    import io
    png = io.BytesIO()
    im.save(png, "PNG")
    try:
        r = subprocess.run(["tesseract", "stdin", "stdout", "-l", os.environ.get("DOCS_OCR", "rus+kaz+eng"), "--psm", "3"],
                           input=png.getvalue(), capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.decode("utf-8", "replace")


def pages(path: Path) -> list[tuple[str, str]]:
    """(where, text) for each page of a PDF ("p. 3"), each heading's part of a .docx (its heading, or "")."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        try:
            out = []
            for i in range(len(pdf)):
                t = pdf[i].get_textpage().get_text_range()
                if len(t.strip()) < 40:  # a scan, or a page of pictures
                    t = _ocr(pdf[i])
                out.append((f"p. {i + 1}", t))
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


def title(path: Path) -> str:
    """A file's name as a source the student reads: no extension, no "(3)" copy marks, spaces for underscores."""
    t = re.sub(r"\s*\(\d+\)", "", path.stem).replace("_", " ")
    return " ".join(t.split())


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
CREATE TABLE chunks (id INTEGER PRIMARY KEY, doc TEXT NOT NULL, title TEXT NOT NULL, at TEXT NOT NULL, text TEXT NOT NULL, vec BLOB);
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
        try:
            got = pages(f)
        except Exception as exc:  # a broken file: the rest still builds
            got = []
            log.warning("%s: %s", rel, exc)
        n = 0
        for at, text in got:
            text, cut = redact(text)
            report["redacted"] += cut
            for c in split(text):
                con.execute("INSERT INTO chunks (doc, title, at, text) VALUES (?, ?, ?, ?)", (rel, title(f), at, c))
                n += 1
        if n:
            report["docs"] += 1
            report["chunks"] += n
        else:
            report["skipped"].append(rel)  # .doc, pictures, an empty scan
    con.execute("INSERT INTO fts (fts) VALUES ('rebuild')")
    con.commit()
    con.close()
    if account and token:
        embed_all(tmp, account, token)
    tmp.replace(out)
    return report


# ------------------------------------------------------------ embeddings (Cloudflare Workers AI)

def embed(texts: list[str], account: str, token: str, timeout: float = 60) -> np.ndarray:
    """bge-m3's vectors for these texts, normalised (rows of float32). Raises httpx.HTTPError on any failure."""
    r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}",
                   headers={"Authorization": f"Bearer {token}"}, json={"text": texts}, timeout=timeout)
    r.raise_for_status()
    v = np.asarray(r.json()["result"]["data"], dtype=np.float32)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def embed_all(path: Path, account: str, token: str, batch: int = 20) -> int:
    """Each chunk still without a vector gets one (its title with its text); resumable."""
    con = sqlite3.connect(path)
    todo = con.execute("SELECT id, title, at, text FROM chunks WHERE vec IS NULL").fetchall()
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        vecs = embed([f"{t} {a}\n{x}" for _, t, a, x in part], account, token)
        con.executemany("UPDATE chunks SET vec = ? WHERE id = ?", [(v.tobytes(), r[0]) for v, r in zip(vecs, part)])
        con.commit()
    con.close()
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
    """A docs file, opened read-only per search; its vectors held in memory once per worker (reread when the file
    changes, so a rebuild needs no restart)."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._ids = self._vecs = None
        self._n = 0

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def _load(self, con) -> None:
        m = os.stat(self.path).st_mtime_ns
        with self._lock:
            if m == self._mtime:
                return
            got = con.execute("SELECT id, vec FROM chunks WHERE vec IS NOT NULL").fetchall()
            self._ids = np.asarray([r[0] for r in got], dtype=np.int64)
            self._vecs = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in got]) if got else None
            self._n = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            self._mtime = m

    @property
    def vectors(self) -> bool:
        return self._vecs is not None

    def ready(self) -> bool:
        try:
            with self._con() as con:
                self._load(con)
            return True
        except (OSError, sqlite3.Error):
            return False

    def _fts(self, con, q: str) -> list[int]:
        terms = list(dict.fromkeys(stem(w) for w in _WORD.findall(q.lower().replace("\u0451", "\u0435")) if w not in STOP))
        keep = []
        for t in terms:  # the index's own common words drop out: no stop-word lists to keep in three languages
            m = '"' + t.replace('"', "") + '"'
            if con.execute("SELECT COUNT(*) FROM fts WHERE fts MATCH ?", (m,)).fetchone()[0] <= max(COMMON * self._n, 3):
                keep.append(m)
        if not keep:
            return []
        return [r[0] for r in con.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts, 0.5, 1) LIMIT ?",
                                          (" OR ".join(keep), POOL))]

    def search(self, q: str, qvec: np.ndarray | None = None, k: int = 4) -> list[dict]:
        """The k best chunks for a question: bm25's list and, with a question's vector, cosine's, fused by rank."""
        with self._con() as con:
            self._load(con)
            lists = [self._fts(con, q)]
            if qvec is not None and self._vecs is not None:
                sims = self._vecs @ qvec.astype(np.float32).ravel()
                lists.append(self._ids[np.argsort(-sims)[:POOL]].tolist())
            score: dict[int, float] = {}
            for got in lists:
                for rank, cid in enumerate(got):
                    score[cid] = score.get(cid, 0) + 1 / (RRF + rank + 1)
            best = sorted(score, key=score.get, reverse=True)[:k]
            by = {r["id"]: dict(r) for r in con.execute(
                f"SELECT id, doc, title, at, text FROM chunks WHERE id IN ({','.join('?' * len(best))})", best)} if best else {}
        return [by[i] for i in best]


def cite(hits: list[dict]) -> str:
    """The chunks as the assistant's brief reads them: each with its source to cite."""
    return "\n".join(f"[{h['title']}{', ' + h['at'] if h['at'] else ''}] {' '.join(h['text'].split())}" for h in hits)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    acc, tok = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_AI_TOKEN", "").strip()
    cmd = sys.argv[1:2]
    if cmd == ["build"] and len(sys.argv) == 4:
        print(build(Path(sys.argv[2]), Path(sys.argv[3]), acc, tok))
    elif cmd == ["embed"] and len(sys.argv) == 3 and acc and tok:
        print(embed_all(Path(sys.argv[2]), acc, tok), "embedded")
    elif cmd == ["ask"] and len(sys.argv) == 4:
        ix = Index(sys.argv[2])
        qv = embed([sys.argv[3]], acc, tok)[0] if acc and tok and ix.ready() and ix.vectors else None
        print(cite(ix.search(sys.argv[3], qv, k=5)))
    else:
        sys.exit(__doc__)
