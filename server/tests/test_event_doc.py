"""An event's one document (its rules, a PDF): the club's people attach it in the editor, everyone sees its pages as
pictures; the PDF itself is never kept (logic/organizing.put_doc)."""
from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium

from kbtu import logic
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

    r = put(_pdf(3), q="?title=%20CS2%20%20rules%20")
    assert r.status_code == 200, r.text
    doc = r.json()["doc"]
    assert doc["title"] == "CS2 rules" and len(doc["pages"]) == 3 and doc["pages"][0]["h"] > doc["pages"][0]["w"]
    first = _files(cfg, doc)
    assert all(f.is_file() for f in first)
    assert c.get("/api/events/1", headers=tma(63)).json()["doc"] == doc  # a student sees the same pages
    assert c.get("/" + doc["pages"][0]["url"]).status_code == 200

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
