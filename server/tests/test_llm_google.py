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


def _ask_async(monkeypatch, google):
    cfg = config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=":memory:", web_dist=".", background=False,
                        seed=False, groq_key="gq", gemini_key=KEY)
    seen = []

    async def handler(r):
        seen.append(r)
        if r.url.host == GOOGLE:
            return await google(1)
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
    """With the student's own yes, ASSIST_LEAD unset or google: the assistant passes lead=llm.GOOGLE; off: never. A student on an earlier
    policy or BOARD=staff (the EU host alone) never reaches Google; nor staff on an earlier version under BOARD=staff
    with the forum channel on (review, Nov 19)."""
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 1")
    con.execute("INSERT INTO kri_consents (user_id, version, at) SELECT id, 'kri-g1', 0 FROM users WHERE tg_id = 1")
    con.close()
    seen = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append(kw.get("lead"))
        return json.dumps({"text": "Room 180.", "actions": []}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    for board, policy, lead, fch, want in (("all", "1", "google", 0, llm.GOOGLE), ("all", "1", "", 0, llm.GOOGLE), ("all", "1", "off", 0, None),
                                           ("staff", "1", "google", 0, None), ("all", "new", "google", 0, None),
                                           ("staff", "1", "google", -100123, llm.GOOGLE), ("staff", "new", "google", -100123, None)):
        x = TestClient(server.create(dataclasses.replace(cfg, board=board, assist_lead=lead, forum_channel=fch, gemini_key=KEY, admins=frozenset({1}))))
        x.app.state.policy = policy  # "1": the version login() writes; "new": the student is on an earlier one
        seen.clear()
        assert x.post("/api/assistant", headers=tma(1), json={"q": "where is the dean's office?"}).status_code == 200
        assert seen == [want], (board, policy, lead, fch)


def test_a_bad_round_never_asks_google_again(env, monkeypatch):
    """Review: the assistant asks once more after unusable answers; that round goes without the lead."""
    c, cfg = env
    me = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO kri_consents (user_id, version, at) VALUES (?, 'kri-g1', 0)", (me["id"],))
    con.close()
    x = TestClient(server.create(dataclasses.replace(cfg, board="all", assist_lead="google", gemini_key=KEY)))
    x.app.state.policy = "1"
    seen = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append(kw.get("lead"))
        if len(seen) == 1:
            raise llm.BadAnswers()
        return json.dumps({"text": "Room 180.", "actions": []}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    assert x.post("/api/assistant", headers=tma(1), json={"q": "where is the dean's office?"}).status_code == 200
    assert seen == [llm.GOOGLE, None]


def test_the_lead_has_a_wall_clock(monkeypatch):
    """Review: a slow Gemini (headers early, body late: no httpx timeout fires) is given up at LEAD_WAIT, then the chain."""
    import time

    async def slow(n):
        await asyncio.sleep(3)
        return _ok(n)
    monkeypatch.setattr(llm, "LEAD_WAIT", 0.3)
    t = time.monotonic()
    (text, link), seen = _ask_async(monkeypatch, slow)
    assert link == "groq:g/m" and time.monotonic() - t < 1.5 and llm._rest["google:gemini-4-hydrogen"] > time.time() + 30


def test_a_strange_answer_is_a_failed_lead(monkeypatch):
    """Review: valid JSON of another shape ("choices" an object) is no answer: the chain runs, nothing raised."""
    (text, link), seen = _ask(monkeypatch, lambda n: httpx.Response(200, json={"choices": {"0": {}}}))
    assert link == "groq:g/m" and [r.url.host for r in seen] == [GOOGLE, GROQ]


def test_retry_after_is_respected(monkeypatch):
    """Review: no retry when a 429 asks to wait longer than the backoff; a rest only grows."""
    import time
    (text, link), seen = _ask(monkeypatch, lambda n: httpx.Response(429, headers={"retry-after": "30"}))
    assert link == "groq:g/m" and [r.url.host for r in seen] == [GOOGLE, GROQ]
    assert llm._rest["google:gemini-4-hydrogen"] > time.time() + 25
    llm._rest_until("x", 100.0)
    llm._rest_until("x", 50.0)
    assert llm._rest["x"] == 100.0


def test_a_refusal_never_logs_the_key(monkeypatch, caplog):
    """Review: a non-200 body that repeats the key is withheld from the log; the status still shows."""
    caplog.set_level(logging.DEBUG)
    (text, link), _ = _ask(monkeypatch, lambda n: httpx.Response(400, text=f"API key {KEY} not valid"))
    said = [r.getMessage() for r in caplog.records if "google" in r.getMessage()]
    assert link == "groq:g/m" and any("http 400" in m and "withheld" in m for m in said)
    assert all(KEY not in r.getMessage() for r in caplog.records)


def test_assist_lead_reads_the_env(monkeypatch, tmp_path):
    """The raw switch: unset is "" (on for who said yes, app.kri_google), "google" the same, "off" never."""
    import base64
    monkeypatch.setattr(config, "_dotenv", lambda: {})
    for k, v in (("TOKEN_KEY", base64.b64encode(os.urandom(32)).decode()), ("BOT_TOKEN", BOT), ("DB_PATH", str(tmp_path / "x.db"))):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ASSIST_LEAD", raising=False)
    monkeypatch.delenv("DB_MUST_EXIST", raising=False)
    assert config.load().assist_lead == ""
    monkeypatch.setenv("ASSIST_LEAD", "google")
    assert config.load().assist_lead == "google"
