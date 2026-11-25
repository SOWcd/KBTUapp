"""Public forms (logic/forms.py): the spec's checks, the page (escaped, closed, unknown), an answer sheet's rules
(options, other, required, caps, the honeypot, the day's cap), nothing about the sender kept, and the CLI's CSV."""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json

import pytest

from kbtu import admin, db, logic
from kbtu.logic import forms
from test_core import env, set_clock  # noqa: F401  (env is a fixture)

SPEC = {"title": "Study <abroad>", "intro": "Who & why.\nTen minutes.", "thanks": "See you!", "lang": "en", "sections": [
    {"title": "About \"you\"", "questions": [
        {"id": "age", "type": "text", "label": "Age", "required": True},
        {"id": "level", "type": "choice", "label": "Program", "options": ["Bachelor", "Master <b>"], "other": True},
        {"id": "why", "type": "multi", "label": "Why", "options": ["Quality", "Prestige"], "other": True},
        {"id": "pay", "type": "choice", "label": "Paid by", "options": ["Self", "Grant"]}]},
    {"title": "Plans", "questions": [
        {"id": "ties", "type": "scale", "label": "Ties", "low": "weak", "high": "strong"},
        {"id": "story", "type": "long", "label": "=Story", "hint": "Anything <i>else</i>"}]}]}


def _gz(spec) -> str:
    return base64.b64encode(gzip.compress(json.dumps(spec).encode())).decode()


@pytest.fixture
def form(env, monkeypatch):  # noqa: F811
    c, cfg = env
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    admin.main(["form", "new", "abroad", "--gz", _gz(SPEC)])
    return c, db.connect(cfg.db_path)


def _answers(con) -> list[dict]:
    return [json.loads(r[0]) for r in con.execute("SELECT answers FROM form_answers ORDER BY id")]


def test_spec_checked(form):
    c, con = form
    for flaw in ({"title": ""}, {"lang": "de"}, {"sections": []}, {"sections": [{"questions": []}]},
                 {"sections": [{"questions": [{"id": "Bad Id", "type": "text", "label": "x"}]}]},
                 {"sections": [{"questions": [{"id": "a", "type": "file", "label": "x"}]}]},
                 {"sections": [{"questions": [{"id": "a", "type": "choice", "label": "x", "options": ["one"]}]}]},
                 {"sections": [{"questions": [{"id": "a", "type": "choice", "label": "x", "options": ["one", "one"]}]}]},
                 {"sections": [{"questions": [{"id": "a", "type": "text", "label": "x"}, {"id": "a", "type": "text", "label": "y"}]}]}):
        with pytest.raises(logic.ApiError):
            forms.check_spec(SPEC | flaw)
    for slug in ("A", "x", "a b", "../x"):
        with pytest.raises(logic.ApiError):
            forms.create(con, slug, SPEC)
    with pytest.raises(logic.ApiError):
        forms.create(con, "abroad", SPEC)  # taken
    assert "junk" not in forms.check_spec(SPEC | {"junk": 1})  # known keys only
    with pytest.raises(SystemExit):
        admin.main(["form", "new", "other", "--gz", base64.b64encode(gzip.compress(b"not json")).decode()])


def test_page(form):
    c, con = form
    r = c.get("/f/abroad")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "script-src 'sha256-" in r.headers["content-security-policy"]
    t = r.text
    assert "Study &lt;abroad&gt;" in t and "<abroad>" not in t and "Master &lt;b&gt;" in t and "Anything &lt;i&gt;else&lt;/i&gt;" in t
    assert "About &quot;you&quot;" in t and 'value="Master &lt;b&gt;"' in t and 'name="level~"' in t and 'name="website"' in t
    assert t.count("<fieldset") == 6 and t.count(' data-req>') == 1 and "1 / 2" in t and "weak" in t and "Submit" in t
    r = c.get("/f/nothing")
    assert r.status_code == 404 and "<form" not in r.text and "\u0444\u043e\u0440\u043c\u044b" in r.text  # calm, in Russian
    admin.main(["form", "close", "abroad"])
    r = c.get("/f/abroad")
    assert r.status_code == 410 and "<form" not in r.text and "This form is closed" in r.text


def test_submit(form):
    c, con = form
    post = lambda **a: c.post("/api/f/abroad", json=a)  # noqa: E731
    ok = post(age=["21"], level=[forms.OTHER], **{"level~": ["  Foundation\x00 year "]}, why=["Quality", forms.OTHER, "Quality"],
              **{"why~": "Family"}, ties=["4"], story=["Line one\r\nLine two"], extra=["dropped"], pay="Grant")
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    assert _answers(con) == [{"age": "21", "level": "Foundation year", "why": ["Quality", "Family"], "pay": "Grant", "ties": "4", "story": "Line one\nLine two"}]
    assert post(age="19", why=[forms.OTHER], story="x" * 9000).status_code == 200  # Other left empty: no answer; the text is cut
    assert _answers(con)[1] == {"age": "19", "story": "x" * forms.LONG}
    for bad in ({"level": "PhD"}, {"why": ["Quality", "Money"]}, {"pay": forms.OTHER}, {"ties": "6"}, {"ties": "five"}):
        r = post(age="20", **bad)
        assert r.status_code == 400 and r.json()["error"] == "bad_input", bad
    for missing in ({}, {"age": "   "}, {"age": 21}, {"story": "no age"}):
        r = post(**missing)
        assert r.status_code == 400 and r.json()["message"] == "required", missing
    assert c.post("/api/f/abroad", json=[1]).status_code in (400, 422) and c.post("/api/f/nothing", json={"age": "1"}).status_code == 404
    assert post(age="20", website="http://spam").json() == {"ok": True}  # the honeypot: an ok, nothing kept
    assert len(_answers(con)) == 2
    # nothing about the sender: the tables hold the answers and the time, no more
    assert [r[1] for r in con.execute("PRAGMA table_info(form_answers)")] == ["id", "form_id", "answers", "created_at"]
    assert "set-cookie" not in ok.headers


def test_empty_sheet(env):  # noqa: F811
    c, cfg = env
    con = db.connect(cfg.db_path)
    forms.create(con, "free", {"title": "T", "sections": [{"questions": [{"id": "a", "type": "text", "label": "A"}]}]})
    r = c.post("/api/f/free", json={"a": ""})
    assert r.status_code == 400 and r.json()["message"] == "empty"


def test_day_cap_and_close(form, monkeypatch):
    c, con = form
    monkeypatch.setattr(forms, "A_DAY", 2)
    clock = [logic.now()]
    set_clock(monkeypatch, lambda: clock[0])
    post = lambda: c.post("/api/f/abroad", json={"age": "20"})  # noqa: E731
    assert [post().status_code for _ in range(3)] == [200, 200, 429]
    assert post().json()["error"] == "rate_limited"
    clock[0] += 86401
    assert post().status_code == 200  # a day on, the form takes answers again
    forms.close(con, "abroad")
    r = post()
    assert r.status_code == 409 and r.json()["error"] == "closed" and len(_answers(con)) == 3


def test_cli_csv(form, capsys):
    c, con = form
    c.post("/api/f/abroad", json={"age": "21", "why": ["Quality", "Prestige"], "story": "=SUM(A1)\nsecond, line"})
    c.post("/api/f/abroad", json={"age": "30"})
    capsys.readouterr()
    admin.main(["form", "answers", "abroad"])
    got = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert got[0] == ["at", "Age", "Program", "Why", "Paid by", "Ties", "'=Story"] and len(got) == 3  # a label is a cell too
    assert got[1][1:] == ["21", "", "Quality; Prestige", "", "", "'=SUM(A1)\nsecond, line"] and got[2][1:] == ["30", "", "", "", "", ""]
    admin.main(["form", "list"])
    assert capsys.readouterr().out.split() == ["open", "2", "/f/abroad"]
    admin.main(["form", "close", "abroad"])
    admin.main(["form", "list"])
    assert capsys.readouterr().out.split() == ["closed", "/f/abroad", "closed", "2", "/f/abroad"]
    with pytest.raises(SystemExit):
        admin.main(["form", "answers", "nothing"])


def test_closed_answers_expire_from_exports_and_nightly_storage(form, monkeypatch):
    c, con = form
    now = logic.now()
    deadline = (now // 86400 + 366) * 86400 - 5 * 3600 + 600  # nightly retention window
    clock = [deadline - forms.KEEP]
    set_clock(monkeypatch, lambda: clock[0])
    assert c.post("/api/f/abroad", json={"age": "21", "story": "Example private answer"}).status_code == 200
    forms.close(con, "abroad")
    forms.create(con, "open", SPEC)
    forms.submit(con, "open", {"age": "22"})
    forms.create(con, "recent", SPEC)
    forms.submit(con, "recent", {"age": "23"})
    clock[0] = deadline - 1
    forms.close(con, "recent")
    assert "Example private answer" in forms.export(con, "abroad")
    clock[0] = deadline
    assert len(list(csv.reader(io.StringIO(forms.export(con, "abroad"))))) == 1
    assert len(_answers(con)) == 3  # export is safe even before the scheduled sweep
    logic.stats_day(con)
    assert _answers(con) == [{"age": "22"}, {"age": "23"}]


def test_csp_hashes(form):  # the inline script and style run by their hashes; an injected tag wouldn't
    c, con = form
    r = c.get("/f/abroad")
    csp, t = r.headers["content-security-policy"], r.text
    assert "unsafe-inline" not in csp
    for tag in ("script", "style"):
        inline = t.split(f"<{tag}>")[1].split(f"</{tag}>")[0]
        assert f"'sha256-{base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()}'" in csp, tag


def test_placeholders_in_spec(env):  # noqa: F811  (the spec's words are never read as the page's own slots)
    c, cfg = env
    con = db.connect(cfg.db_path)
    forms.create(con, "slots", {"title": "__BODY__", "intro": "__FOOT__ __LANG__", "sections": [{"questions": [{"id": "a", "type": "text", "label": "A"}]}]})
    t = c.get("/f/slots").text
    assert "<title>__BODY__</title>" in t and "__FOOT__ __LANG__" in t


def test_body_capped(form):  # no account in front of this route: a huge or deep body is refused before it is parsed
    c, con = form
    r = c.post("/api/f/abroad", content=b'{"age": "' + b"x" * (forms.MOST + 1) + b'"}', headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["message"] == "too_big"
    r = c.post("/api/f/abroad", content=b"[" * 200000, headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert c.post("/api/f/abroad", content=b'{"age": "1"', headers={"content-type": "application/json"}).status_code == 400
    assert not _answers(con)
