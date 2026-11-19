"""Google (Gemini) is the KRI assistant's first try (llm.GOOGLE, chat's lead=): a busy answer gets one quick retry,
then the chain exactly as before; no key: never asked. Its key goes in a header only, never a URL or a log line.
Every other caller keeps its order: only the assistant's answer passes lead."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from kbtu import ai, config, db, llm
from kbtu import app as server
from test_core import BOT, env, login, tma  # noqa: F401  (env: the fixture)

KEY = "gk-test-not-a-real-key-7f3a"
GOOGLE = "generativelanguage.googleapis.com"
GROQ = "api.groq.com"


def _ask(monkeypatch, google, gemini_key=KEY):
    """One assistant-shaped call with Google led and Groq as the whole chain; google(attempt) -> a Response or raises."""
    cfg = config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=":memory:", web_dist=".", background=False,
                        seed=False, groq_key="gq", gemini_key=gemini_key)
    monkeypatch.setattr(llm, "LEAD_BACKOFF", 0)
    seen = []

    def handler(r):
        seen.append(r)
        if r.url.host == GOOGLE:
            return google(sum(x.url.host == GOOGLE for x in seen))
        return httpx.Response(200, json={"choices": [{"message": {"content": "groq"}, "finish_reason": "stop"}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await llm.chat(cfg, http, [{"role": "user", "content": "hi"}], only=ai.ASSIST_PROVIDERS, chain="groq:g/m",
                                  race=True, effort="none", lead=llm.GOOGLE)
    return asyncio.run(go()), seen


def _ok(_):
    return httpx.Response(200, json={"choices": [{"message": {"content": "gemini"}, "finish_reason": "stop"}]})


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(llm, "_rest", {})


def test_google_answers_first(monkeypatch):
    (text, link), seen = _ask(monkeypatch, _ok)
    assert (text, link) == ("gemini", "google:gemini-4-hydrogen") and [r.url.host for r in seen] == [GOOGLE]
    r = seen[0]
    assert str(r.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert r.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(r.content)
    assert body["model"] == "gemini-4-hydrogen" and body["reasoning_effort"] == "low"  # Gemini 4 refuses "none"


@pytest.mark.parametrize("fail", [lambda n: httpx.Response(503), lambda n: httpx.Response(429), "timeout"])
def test_google_busy_twice_falls_to_the_chain(monkeypatch, caplog, fail):
    def google(n):
        if fail == "timeout":
            raise httpx.ReadTimeout("slow")
        return fail(n)
    caplog.set_level(logging.DEBUG)
    (text, link), seen = _ask(monkeypatch, google)
    assert (text, link) == ("groq", "groq:g/m") and [r.url.host for r in seen] == [GOOGLE, GOOGLE, GROQ]  # exactly one retry
    (text, _), seen = _ask(monkeypatch, google)
    assert text == "groq" and [r.url.host for r in seen] == [GROQ]   # failed twice: resting, the next student doesn't wait on it
    for r in caplog.records:
        assert KEY not in r.getMessage()
    assert all(KEY not in str(r.url) for r in seen)


def test_the_retry_can_answer(monkeypatch):
    (text, link), seen = _ask(monkeypatch, lambda n: httpx.Response(503) if n == 1 else _ok(n))
    assert link == "google:gemini-4-hydrogen" and len(seen) == 2 and "google:gemini-4-hydrogen" not in llm._rest


def test_no_key_no_google(monkeypatch):
    (text, link), seen = _ask(monkeypatch, _ok, gemini_key="")
    assert link == "groq:g/m" and [r.url.host for r in seen] == [GROQ]
    assert not llm.links(config.Config(bot_token=BOT, token_key=b"x" * 32, db_path=":memory:", web_dist="."), llm.GOOGLE)


def test_only_the_assistants_answer_leads_with_google(env, monkeypatch):
    """The assistant passes lead=llm.GOOGLE; a student on an earlier policy or
    BOARD=staff (the EU host alone) never reaches Google."""
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 1")
    con.close()
    seen = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append(kw.get("lead"))
        return json.dumps({"text": "Room 180.", "actions": []}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    for board, policy, want in (("all", "1", llm.GOOGLE), ("staff", "1", None), ("all", "new", None)):
        x = TestClient(server.create(dataclasses.replace(cfg, board=board)))
        x.app.state.policy = policy  # "1": the version login() writes; "new": the student is on an earlier one
        seen.clear()
        assert x.post("/api/assistant", headers=tma(1), json={"q": "where is the dean's office?"}).status_code == 200
        assert seen == [want], (board, policy)
