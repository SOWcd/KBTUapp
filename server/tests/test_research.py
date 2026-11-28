"""Native research access, signed/anonymous answers, proposals, deletion and manual approval.
Written for CI; the owner's local gate forbids running tests, type checks and builds.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from kbtu import admin, db, logic, texts
from kbtu.logic import forms, research
from kbtu.logic.core import ApiError, Viewer
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401
from test_forms import SPEC

A, B, OWNER, ADMIN, MOD = 31, 32, 33, 34, 35
PROPOSAL = {"title": "Library spaces", "goal": "Find useful improvements", "questions": "What helps?\nWhat is missing?",
            "organizer": "Student research group", "consent": research.CONSENT}


def setup(env):
    c, cfg = env
    ids = {u: login(c, u, name)["id"] for u, name in ((A, "ali"), (B, "bota"), (OWNER, "owner"), (ADMIN, "admin"), (MOD, "mod"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (ids[OWNER],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ids[ADMIN],))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (ids[MOD],))
    return c, cfg, con, ids


def test_only_open_research_specs_and_my_participation(env):
    c, cfg, con, ids = setup(env)
    forms.create(con, "public", SPEC)
    fid = forms.create(con, "study", SPEC | {"research": True, "about": "One line\nabout the study"})
    forms.create(con, "closed", SPEC | {"research": True, "about": "Finished"})
    forms.close(con, "closed")
    assert c.get("/api/research").status_code == 403
    r = c.get("/api/research", headers=tma(A))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == [{"slug": "study", "title": SPEC["title"], "about": "One line about the study",
                         "answers": 0, "answered": False, "spec": forms.check_spec(SPEC)}]
    assert c.post("/api/research/study/answers", headers=tma(A), json=ANSWER).status_code == 204
    assert c.get("/api/research", headers=tma(A)).json()[0]["answered"] is True
    other = c.get("/api/research", headers=tma(B)).json()[0]
    assert other["answers"] == 1 and other["answered"] is False
    assert "user_id" not in json.dumps(other)  # no results or participant list on the student's route
    assert forms.listing(con) == [("public", True, 0), ("study", True, 1), ("closed", False, 0)]
    forms.close(con, "study")
    assert c.get("/api/research", headers=tma(A)).json() == []
    for invalid in ({"research": "true"}, {"research": True}, {"research": True, "about": " "}):
        with pytest.raises(ApiError, match="bad_input"):
            forms.create(con, "invalid", SPEC | invalid)
    assert not con.execute("SELECT 1 FROM forms WHERE slug = 'invalid'").fetchone()


ANSWER = {"answers": {"age": "21"}, "consent": research.ANSWER_CONSENT}


def test_public_research_page_and_submission_are_locked(env):
    c, cfg, con, ids = setup(env)
    for lang in ("ru", "kk", "en"):
        slug = "study-" + lang
        forms.create(con, slug, SPEC | {"lang": lang, "research": True, "about": "Study"})
        r = c.get("/f/" + slug)
        assert r.status_code == 200 and texts.FORM_PAGE[lang]["openApp"] in r.text
        assert "?startapp=research" in r.text and "<form" not in r.text and "<script>" not in r.text
        for body in ({"age": "21"}, {"age": "21", "website": "spam"}):
            for headers in ({}, tma(A), tma(OWNER)):
                r = c.post("/api/f/" + slug, json=body, headers=headers)
                assert r.status_code == 403 and r.json()["message"] == "research_app"
    assert not con.execute("SELECT 1 FROM form_answers").fetchone()
    forms.create(con, "public", SPEC)
    assert c.post("/api/f/public", json={"age": "21"}).status_code == 200
    assert c.post("/api/research/public/answers", headers=tma(A), json=ANSWER).status_code == 404


def test_signed_default_anonymous_opt_in_and_once_each(env, monkeypatch, capsys):
    c, cfg, con, ids = setup(env)
    forms.create(con, "study", SPEC | {"research": True, "about": "Study"})
    url = "/api/research/study/answers"
    assert c.post(url, headers=tma(99), json=ANSWER).status_code == 401
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (ids[A],))
    assert c.post(url, headers=tma(A), json=ANSWER).json()["error"] == "need_student"
    con.execute("UPDATE students SET manual = 0, first_name = '=Name' WHERE user_id = ?", (ids[A],))
    con.execute("UPDATE students SET student_id = 'staff34' WHERE user_id = ?", (ids[ADMIN],))
    assert c.post(url, headers=tma(ADMIN), json=ANSWER).json()["error"] == "need_student"
    assert c.post("/api/research/requests", headers=tma(ADMIN), json=PROPOSAL).json()["error"] == "need_student"
    assert c.post(url, headers=tma(A), json=ANSWER | {"user_id": ids[B]}).status_code == 204
    signed = con.execute("SELECT * FROM research_answers").fetchone()
    assert signed["user_id"] == ids[A] and signed["consent"] == research.ANSWER_CONSENT
    assert c.post(url, headers=tma(A), json=ANSWER | {"anonymous": True}).json() == {"error": "conflict", "message": "answered"}
    assert c.post(url, headers=tma(B), json=ANSWER | {"anonymous": True, "answers": {"age": "22"}, "user_id": ids[B]}).status_code == 204
    anon = con.execute("SELECT * FROM research_answers WHERE user_id IS NULL").fetchone()
    assert anon["day"] is None and len(anon["id"]) == 32
    assert c.post(url, headers=tma(B), json=ANSWER).status_code == 409
    assert con.execute("SELECT COUNT(*) FROM research_answers").fetchone()[0] == 2
    assert {r[1] for r in con.execute("PRAGMA table_info(research_participants)")} == {"form_id", "user_id"}
    for table in ("research_participants", "research_answers"):
        assert "WITHOUT ROWID" in con.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
        with pytest.raises(sqlite3.OperationalError):
            con.execute(f"SELECT rowid FROM {table}").fetchall()
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    admin.main(["form", "answers", "study"])
    exported = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    signed_csv = next(r for r in exported if r["user_id"])
    anon_csv = next(r for r in exported if not r["user_id"])
    assert signed_csv["user_id"] == str(ids[A]) and signed_csv["name"] == "'=Name Testov"
    assert anon_csv["name"] == "" and anon_csv["Age"] == "22"
    assert anon_csv["at"] == "" and len(signed_csv["at"]) == 10


def test_research_validation_does_not_consume_participation(env):
    c, cfg, con, ids = setup(env)
    forms.create(con, "study", SPEC | {"research": True, "about": "Study"})
    url = "/api/research/study/answers"
    for body in ([], {}, ANSWER | {"consent": "old"}, ANSWER | {"anonymous": "false"}, ANSWER | {"anonymous": 1},
                 ANSWER | {"answers": {}}, ANSWER | {"answers": {"age": "21", "ties": "6"}},
                 ANSWER | {"answers": {"age": "21", "why": ["invalid"]}}):
        assert c.post(url, headers=tma(A), json=body).status_code == 400
    body = json.dumps(ANSWER | {"answers": {"age": "\ud800"}})
    assert c.post(url, headers=tma(A), content=body).status_code == 400
    assert c.post(url, headers=tma(A), content=b"x" * (forms.MOST + 1)).status_code == 400
    assert not con.execute("SELECT 1 FROM research_participants").fetchone()
    all_types = {"age": "21", "level": forms.OTHER, "level~": "Other study", "why": ["Quality", "Prestige"],
                 "ties": "5", "story": "Long\nanswer"}
    assert c.post(url, headers=tma(A), json=ANSWER | {"answers": all_types}).status_code == 204
    stored = json.loads(con.execute("SELECT answers FROM research_answers").fetchone()[0])
    assert stored == {k: v for k, v in (all_types | {"level": "Other study"}).items() if k != "level~"}
    forms.close(con, "study")
    assert c.post(url, headers=tma(B), json=ANSWER).json()["error"] == "closed"


def test_concurrent_answer_and_stale_verification(env):
    c, cfg, con, ids = setup(env)
    forms.create(con, "study", SPEC | {"research": True, "about": "Study"})
    viewer = Viewer(ids[A], "user", True)

    def send(anonymous):
        other = db.connect(cfg.db_path)
        try:
            research.answer(other, viewer, "study", ANSWER | {"anonymous": anonymous})
            return "ok"
        except ApiError as e:
            return e.code
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, (False, True))) == ["conflict", "ok"]
    assert con.execute("SELECT COUNT(*) FROM research_answers").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM research_participants").fetchone()[0] == 1
    stale = Viewer(ids[B], "user", True)
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids[B],))
    with pytest.raises(ApiError, match="need_student"):
        research.answer(con, stale, "study", ANSWER)
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ids[B],))
    con.execute("DELETE FROM students WHERE user_id = ?", (ids[B],))
    with pytest.raises(ApiError, match="need_student"):
        research.answer(con, stale, "study", ANSWER)


def test_signed_answers_deleted_anonymous_answers_unlinked(env):
    c, cfg, con, ids = setup(env)
    forms.create(con, "study", SPEC | {"research": True, "about": "Study"})
    for who, anonymous in ((A, False), (B, True)):
        assert c.post("/api/research/study/answers", headers=tma(who), json=ANSWER | {"anonymous": anonymous}).status_code == 204
    anon = dict(con.execute("SELECT * FROM research_answers WHERE user_id IS NULL").fetchone())
    delete_now(c, cfg, tma(B))
    assert dict(con.execute("SELECT * FROM research_answers WHERE user_id IS NULL").fetchone()) == anon
    assert not con.execute("SELECT 1 FROM research_participants WHERE user_id = ?", (ids[B],)).fetchone()
    delete_now(c, cfg, tma(A))
    assert not con.execute("SELECT 1 FROM research_answers WHERE user_id IS NOT NULL").fetchone()
    assert not con.execute("SELECT 1 FROM research_participants").fetchone()
    assert con.execute("SELECT COUNT(*) FROM research_answers").fetchone()[0] == 1


def test_answer_retention_after_closure(env, monkeypatch):
    c, cfg, con, ids = setup(env)
    clock = [logic.now()]
    set_clock(monkeypatch, lambda: clock[0])
    old = forms.create(con, "study", SPEC | {"research": True, "about": "Study"})
    forms.create(con, "open", SPEC | {"research": True, "about": "Still open"})
    public = forms.create(con, "public", SPEC)
    forms.submit(con, "public", {"age": "20"})
    forms.close(con, "public")
    for slug in ("study", "open"):
        assert c.post(f"/api/research/{slug}/answers", headers=tma(A), json=ANSWER).status_code == 204
    con.execute("INSERT INTO form_answers (form_id, answers, created_at) VALUES (?, ?, ?)", (old, '{"age":"20"}', clock[0]))
    forms.close(con, "study")
    clock[0] += research.ANSWER_KEEP - 1
    research.sweep(con)
    assert con.execute("SELECT COUNT(*) FROM research_answers").fetchone()[0] == 2
    clock[0] += 2
    research.sweep(con)
    for table in ("research_answers", "research_participants", "form_answers"):
        assert not con.execute(f"SELECT 1 FROM {table} WHERE form_id = ?", (old,)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM research_answers").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM form_answers WHERE form_id = ?", (public,)).fetchone()[0] == 1


def test_verified_proposals_and_owner_approval_are_separate_from_forms(env):
    c, cfg, con, ids = setup(env)
    post = lambda uid, body=PROPOSAL: c.post("/api/research/requests", headers=tma(uid), json=body)  # noqa: E731
    assert post(99).status_code == 401
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (ids[B],))
    assert post(B).json()["error"] == "need_student"
    assert post(A).status_code == 204
    row = con.execute("SELECT * FROM research_requests").fetchone()
    assert row["user_id"] == ids[A] and row["consent"] == research.CONSENT
    assert c.get("/api/admin/research", headers=tma(A)).status_code == 403
    for who in (OWNER, ADMIN, MOD):
        r = c.get("/api/admin/research", headers=tma(who))
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert r.json()[0]["person"]["id"] == ids[A] and not r.json()[0]["approved"]
        assert r.json()[0]["questions"] == PROPOSAL["questions"]
    url = f"/api/admin/research/{row['id']}"
    for who in (A, ADMIN, MOD):
        assert c.post(url, headers=tma(who), json={"approved": True}).status_code == 403
    for bad in ({}, {"approved": 1}, {"approved": "false"}, []):
        assert c.post(url, headers=tma(OWNER), json=bad).status_code == 400
    assert c.post(url, headers=tma(OWNER), json={"approved": True}).status_code == 204
    assert c.get("/api/admin/research", headers=tma(OWNER)).json()[0]["approved"] is True
    assert not con.execute("SELECT 1 FROM forms").fetchone()  # the owner still creates the spec manually
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind IN ('app_broadcast', 'research_launch')").fetchone()
    assert c.post(url, headers=tma(OWNER), json={"approved": False}).status_code == 204
    assert c.get("/api/admin/research", headers=tma(OWNER)).json()[0]["approved"] is False
    con.execute("UPDATE users SET is_founder = 0 WHERE id = ?", (ids[OWNER],))
    assert c.post(url, headers=tma(OWNER), json={"approved": True}).status_code == 403


def test_request_validation_and_rolling_daily_cap(env, monkeypatch):
    c, cfg, con, ids = setup(env)
    clock = [logic.now()]
    set_clock(monkeypatch, lambda: clock[0])
    post = lambda body: c.post("/api/research/requests", headers=tma(A), json=body)  # noqa: E731
    bad = [[], {}, PROPOSAL | {"consent": "old"}, PROPOSAL | {"questions": "\n".join(["Q"] * 11)},
           PROPOSAL | {"questions": "\u2028".join(["Q"] * 11)}]
    for key, cap in research.LIMITS.items():
        bad += [PROPOSAL | {key: value} for value in (" ", "x" * (cap + 1), None, 5, "\x00", "before\x00after")]
    for body in bad:
        assert post(body).status_code == 400, body
    body = json.dumps(PROPOSAL | {"title": "\ud800"})
    assert c.post("/api/research/requests", headers=tma(A), content=body).status_code == 400
    assert c.post("/api/research/requests", headers=tma(A), content=b"x" * (research.BODY_MOST + 1)).status_code == 400
    for i in range(research.A_DAY):
        assert post(PROPOSAL | {"questions": "First?\r\n\r\nSecond?"}).status_code == 204
    assert con.execute("SELECT questions FROM research_requests LIMIT 1").fetchone()[0] == "First?\nSecond?"
    assert post(PROPOSAL).json() == {"error": "rate_limited", "message": "research_day"}
    rid = con.execute("SELECT id FROM research_requests LIMIT 1").fetchone()[0]
    assert c.post(f"/api/admin/research/{rid}", headers=tma(OWNER), json={"approved": True}).status_code == 204
    assert post(PROPOSAL).status_code == 429  # approving does not refund the cap
    assert c.post("/api/research/requests", headers=tma(B), json=PROPOSAL).status_code == 204
    clock[0] += 86401
    assert post(PROPOSAL).status_code == 204


def test_concurrent_cap_and_stale_student(env, monkeypatch):
    c, cfg, con, ids = setup(env)
    monkeypatch.setattr(research, "A_DAY", 1)
    viewer = Viewer(ids[A], "user", True)

    def send():
        other = db.connect(cfg.db_path)
        try:
            research.propose(other, viewer, PROPOSAL)
            return "ok"
        except ApiError as e:
            return e.code
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: send(), range(2))) == ["ok", "rate_limited"]
    con.execute("DELETE FROM students WHERE user_id = ?", (ids[A],))
    with pytest.raises(ApiError, match="need_student"):
        research.propose(con, viewer, PROPOSAL)


def test_account_deletion_ids_and_retention(env, monkeypatch):
    c, cfg, con, ids = setup(env)
    now = logic.now()
    set_clock(monkeypatch, lambda: now)
    assert c.post("/api/research/requests", headers=tma(A), json=PROPOSAL).status_code == 204
    old = con.execute("SELECT id FROM research_requests").fetchone()[0]
    delete_now(c, cfg, tma(A))
    assert not con.execute("SELECT 1 FROM research_requests WHERE user_id = ?", (ids[A],)).fetchone()
    assert c.post("/api/research/requests", headers=tma(B), json=PROPOSAL).status_code == 204
    new = con.execute("SELECT id FROM research_requests").fetchone()[0]
    assert new > old
    assert c.post(f"/api/admin/research/{old}", headers=tma(OWNER), json={"approved": True}).status_code == 404
    set_clock(monkeypatch, lambda: now + research.KEEP + 1)
    assert c.get("/api/admin/research", headers=tma(OWNER)).json() == []
    assert c.post(f"/api/admin/research/{new}", headers=tma(OWNER), json={"approved": True}).status_code == 404
    with db.tx(con):
        research.sweep(con)
    assert not con.execute("SELECT 1 FROM research_requests").fetchone()


def test_preview_template_only(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    for lang in ("ru", "kk", "en"):
        text, button = texts.broadcast_message(lang, "research_launch")
        assert text.startswith("\U0001f4ca") and button
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'app_broadcast'").fetchone()
