"""The assistant's documents (kbtu/docs.py): a made-up handbook and FAQ (no real document's text in the repo) built into a
docs file; personal contacts cut out, Russian endings found by the trigram search, an embedding-only hit fused in, and
the excerpts with their sources in the assistant's brief only when DOCS is on."""
from __future__ import annotations

import json
import sqlite3
import zipfile

import numpy as np

from kbtu import docs, llm, logic
from test_core import _board_on, env, login, tma  # noqa: F401  (env: the fixture)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
# "The scholarship is paid on the 25th of each month to a Halyk card." / "Questions about the scholarship"
SCHOLARSHIP = "\u0421\u0442\u0438\u043f\u0435\u043d\u0434\u0438\u044f \u0432\u044b\u043f\u043b\u0430\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f 25 \u0447\u0438\u0441\u043b\u0430 \u043d\u0430 \u043a\u0430\u0440\u0442\u0443 Halyk."
ASK = "\u041a\u043e\u0433\u0434\u0430 \u043f\u0440\u0438\u0434\u0451\u0442 \u0441\u0442\u0438\u043f\u0435\u043d\u0434\u0438\u044e?"  # "when does the scholarship (acc.) come?"


def _docx(path, paras: list[tuple[str | None, str]]) -> None:
    body = "".join(f'<w:p>{f"<w:pPr><w:pStyle w:val=\"{s}\"/></w:pPr>" if s else ""}<w:r><w:t>{t}</w:t></w:r></w:p>' for s, t in paras)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')


def _build(tmp_path):
    src = tmp_path / "src"
    (src / "faq").mkdir(parents=True)
    _docx(src / "faq" / "First_year_FAQ (3).docx", [
        ("2", "Money"), (None, SCHOLARSHIP),
        ("2", "Dorm"), (None, "The dormitory office is in room 110. Write to dorm@kbtu.kz or a.petrova@kbtu.kz, "
                              "call +7 701 234 56 78 or the call centre +7 727 357 42 42."),
        (None, "Student 24B031234, IIN 990101300123, mail jdoe1999@gmail.com.")])
    (src / "Fixture Handbook.txt").write_text("Retake: missing more than 30% of a course's classes means a paid retake of the whole course.\n"
                                              + "Filler line about campus life and its many clubs.\n" * 40)
    (src / "old.doc").write_bytes(b"\xd0\xcf\x11\xe0")  # Word 97: not read (convert it to .docx first)
    out = tmp_path / "docs.db"
    return docs.build(src, out), out


def test_build_redacts_and_searches(tmp_path):
    rep, out = _build(tmp_path)
    assert rep["docs"] == 2 and rep["skipped"] == ["old.doc"] and rep["redacted"] == 5
    con = sqlite3.connect(out)
    text = " ".join(r[0] for r in con.execute("SELECT text FROM chunks"))
    for gone in ("a.petrova", "234 56 78", "24B031234", "990101300123", "jdoe1999"):
        assert gone not in text
    assert "dorm@kbtu.kz" in text and "357 42 42" in text  # an office's mailbox and the university's line stay
    assert {r[0] for r in con.execute("SELECT at FROM chunks WHERE title = 'First year FAQ'")} >= {"Money", "Dorm"}
    assert not tmp_path.joinpath("docs.building").exists()
    con.close()

    ix = docs.Index(str(out))
    hit = ix.search(ASK, k=1)[0]                     # another ending of the same word, found without a stemmer list
    assert hit["title"] == "First year FAQ" and hit["at"] == "Money"
    assert ix.search("what happens if I miss classes, the retake?", k=1)[0]["title"] == "Fixture Handbook"
    assert docs.cite([hit]).startswith("[First year FAQ, Money] ")
    assert ix.search("zzzz qqqq") == []


def test_hybrid_fuses_an_embedding_hit(tmp_path):
    _, out = _build(tmp_path)
    con = sqlite3.connect(out)
    ids = [r[0] for r in con.execute("SELECT id FROM chunks ORDER BY id")]
    dorm = con.execute("SELECT id FROM chunks WHERE at = 'Dorm'").fetchone()[0]
    for i in ids:  # the dorm chunk alone points along the question's vector
        v = np.zeros(4, dtype=np.float32)
        v[0 if i == dorm else 1] = 1
        con.execute("UPDATE chunks SET vec = ? WHERE id = ?", (v.tobytes(), i))
    con.commit()
    con.close()
    ix = docs.Index(str(out))
    q = "where can I sleep at night?"     # no word of the dorm chunk: bm25 alone can't find it
    assert all(h["at"] != "Dorm" for h in ix.search(q, k=3))
    assert ix.search(q, np.array([1, 0, 0, 0], dtype=np.float32), k=1)[0]["at"] == "Dorm"


def test_assistant_brief_has_the_documents(env, tmp_path, monkeypatch):
    c, cfg = env
    login(c, 1, "ann")
    _board_on(c, cfg)
    _, out = _build(tmp_path)
    seen: list = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append(msgs[0]["content"])
        return json.dumps({"text": "On the 25th (First year FAQ, Money).", "actions": []}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    ask = lambda q, h=(): c.post("/api/assistant", headers=tma(1), json={"q": q, "history": list(h)})  # noqa: E731

    assert ask(ASK).status_code == 200 and "University documents" not in seen[-1]  # DOCS off: nothing
    monkeypatch.setattr(logic.assistant, "DOCS", docs.Index(str(out)))
    assert ask(ASK).json()["text"].startswith("On the 25th")
    assert "[First year FAQ, Money] Money " + SCHOLARSHIP in seen[-1] and "a.petrova" not in seen[-1]
    ask("and when?", [{"role": "user", "text": ASK}, {"role": "assistant", "text": "..."}])  # a follow-up searches with the turn before
    assert "[First year FAQ, Money]" in seen[-1]
    monkeypatch.setattr(logic.assistant, "DOCS", docs.Index(str(tmp_path / "missing.db")))
    assert ask(ASK).status_code == 200 and "University documents" not in seen[-1]  # no file yet: answers without
