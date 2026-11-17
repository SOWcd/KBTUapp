"""An event's one document (its rules, a PDF): the club's people attach it in the editor, everyone sees its pages as
pictures; the PDF itself is never kept (logic/organizing.put_doc)."""
from __future__ import annotations

import io
import threading
import time
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from kbtu import logic, media, receipt
from test_admin_events import _setup
from test_core import env, tma  # noqa: F401  (env: the fixture)
from test_review_fixes import _png


def _pdf(n: int) -> bytes:
    d = pdfium.PdfDocument.new()
    for _ in range(n):
        d.new_page(595, 842)  # A4
    b = io.BytesIO()
    d.save(b)
    d.close()
    return b.getvalue()


def _slow_pdf() -> bytes:
    """One page of a 1 MB stream of fill paths in 2 KB of Flate: PDFium took 135 s on it (the security review)."""
    body = zlib.compress(b"0 0 m 1600 1600 l 0 1600 l h f\n" * 33000, 9)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(body) + body + b"\nendstream"]
    out, offs = bytearray(b"%PDF-1.7\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 5\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return bytes(out + b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % x)


def _files(cfg, doc) -> list[Path]:
    root = Path(cfg.db_path).parent
    return [root / p["url"] for p in doc["pages"]]


def test_event_doc(env):
    c, con, ids = _setup(env)
    cfg = env[1]
    put = lambda body, uid=62, q="": c.put(f"/api/events/1/doc{q}", headers=tma(uid), content=body)  # noqa: E731
    for uid in (63, 64, 61):  # a student, another club's President, a moderator
        assert put(_pdf(1), uid).status_code == 403
    assert put(_png((1, 2, 3))).status_code == 400 and put(b"%PDF-1.7 broken").status_code == 400
    assert put(_pdf(logic.DOC_PAGES + 1)).json()["message"] == "too_many_pages"
    assert put(b"%PDF-" + b"0" * logic.DOC_BYTES).json()["message"] == "too_big"
    assert not con.execute("SELECT 1 FROM event_docs").fetchone()

    r = put(_pdf(3), q="?title=%20CS2%20%E2%80%8F%20rules%07%20")  # a direction mark, a bell: gone
    assert r.status_code == 200, r.text
    doc = r.json()["doc"]
    assert doc["title"] == "CS2 rules" and len(doc["pages"]) == 3 and doc["pages"][0]["h"] > doc["pages"][0]["w"]
    first = _files(cfg, doc)
    assert all(f.is_file() for f in first)
    assert c.get("/api/events/1", headers=tma(63)).json()["doc"] == doc  # a student sees the same pages
    got = c.get("/" + doc["pages"][0]["url"])
    assert got.status_code == 200 and got.headers["cache-control"] == "public, max-age=3600"  # not a year: it may go
    assert doc["pages"][0]["url"].startswith("media/doc/")

    # replaced: the old pages leave the disk; no title: the app's own word
    doc = put(_pdf(2)).json()["doc"]
    assert doc["title"] is None and len(doc["pages"]) == 2 and not any(f.exists() for f in first)
    assert c.delete("/api/events/1/doc", headers=tma(63)).status_code == 403
    assert c.delete("/api/events/1/doc", headers=tma(62)).status_code == 204
    assert c.get("/api/events/1", headers=tma(62)).json()["doc"] is None and not any(f.exists() for f in _files(cfg, doc))

    # deleting the event takes its document, the row and the files
    doc = put(_pdf(1)).json()["doc"]
    con.execute("UPDATE events SET status = 'draft' WHERE id = 1")
    assert c.delete("/api/events/1", headers=tma(62)).status_code == 204
    assert not con.execute("SELECT 1 FROM event_docs").fetchone() and not any(f.exists() for f in _files(cfg, doc))


def test_a_slow_pdf_is_cut_off_and_blocks_no_receipt(env, monkeypatch):
    c, con, ids = _setup(env)
    monkeypatch.setattr(logic.organizing, "DOC_SECONDS", 2)
    res = {}

    def upload():
        t = time.monotonic()
        res["r"] = c.put("/api/events/1/doc", headers=tma(62), content=_slow_pdf())
        res["t"] = time.monotonic() - t
    th = threading.Thread(target=upload)
    th.start()
    time.sleep(0.5)  # the child is rendering now
    t = time.monotonic()
    receipt.picture(_pdf(1))  # a Kaspi receipt's PDF: no lock held by the document
    assert time.monotonic() - t < 1
    th.join(30)
    assert res["r"].status_code == 400 and res["r"].json()["message"] == "not_a_pdf"
    assert res["t"] < 2 + 3, res["t"]  # the budget, plus the child's start
    root = Path(env[1].db_path).parent
    assert not con.execute("SELECT 1 FROM event_docs").fetchone() and not list(root.glob(".doc-*"))
    assert not (root / "media" / "doc").exists() or not any((root / "media" / "doc").rglob("*.*"))


def test_no_file_outlives_a_failure(env, monkeypatch):
    c, con, ids = _setup(env)
    media_root = Path(env[1].db_path).parent / "media"
    left = lambda: [p for p in media_root.rglob("*.*") if "doc" in p.parts]  # noqa: E731
    # a store that dies halfway through a page (the disk filled): that page's files go with the others
    real, n = media.store, [0]

    def flaky(im, key, root):
        n[0] += 1
        if n[0] == 2:
            real(im, key, root)
            raise OSError("disk full")
        return real(im, key, root)
    monkeypatch.setattr(media, "store", flaky)
    with pytest.raises(OSError):
        c.put("/api/events/1/doc", headers=tma(62), content=_pdf(3))
    assert not left()
    monkeypatch.setattr(media, "store", real)
    # a failure after the pages are stored, before their row: none stays on disk
    monkeypatch.setattr(logic, "put_doc", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        c.put("/api/events/1/doc", headers=tma(62), content=_pdf(2))
    assert not left() and not con.execute("SELECT 1 FROM event_docs").fetchone()
    # more than 5 MB said up front: refused before it is read
    r = c.put("/api/events/1/doc", headers={**tma(62), "Content-Length": str(logic.DOC_BYTES + 1)}, content=b"%PDF-" + b"0" * (logic.DOC_BYTES - 4))
    assert r.status_code == 400 and r.json()["message"] == "too_big"
