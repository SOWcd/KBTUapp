"""Google answers the KRI assistant first only for a student who said its own yes (assistant.GOOGLE_YES, the card in the
assistant; kri_consents): no yes, a withdrawn one, ASSIST_LEAD=off, no key or an earlier policy: Google is never asked
and the chain answers as before. The answer times per link (llm._count) read old [ok, fail] rows too."""
from __future__ import annotations

import dataclasses
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from kbtu import app as server
from kbtu import db, llm, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

KEY = "gk-test-not-a-real-key-7f3a"
GOOGLE = "generativelanguage.googleapis.com"
ANSWER = json.dumps({"text": "Room 180.", "actions": []})


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(llm, "_rest", {})


@pytest.fixture
def kri(env):
    """make(**cfg) -> (client, hosts asked); a signed-in student, tg id 1, on the policy in force ("1")."""
    c, cfg = env
    me = login(c, 1, "ann")

    def make(policy="1", **kw):
        kw = {"board": "all", "gemini_key": KEY, "groq_key": "gq", "ai_chain": "groq:g/m", **kw}
        x = TestClient(server.create(dataclasses.replace(cfg, **kw)))
        x.app.state.policy = policy
        hosts = []

        def handler(r):
            hosts.append(r.url.host)
            return httpx.Response(200, json={"choices": [{"message": {"content": ANSWER}, "finish_reason": "stop"}]})
        x.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return x, hosts
    make.uid, make.db = me["id"], cfg.db_path
    return make


def _ask(x):
    return x.post("/api/assistant", headers=tma(1), json={"q": "where is the dean's office?"})


def _row(kri, version="kri-g1"):
    con = db.connect(kri.db)
    con.execute("INSERT OR REPLACE INTO kri_consents (user_id, version, at) VALUES (?, ?, 0)", (kri.uid, version))
    con.close()


def test_no_yes_google_never_asked(kri):
    x, hosts = kri()
    assert x.get("/api/me", headers=tma(1)).json()["kriGoogle"] is False
    assert _ask(x).status_code == 200 and hosts == ["api.groq.com"]


def test_yes_google_first_withdrawn_from_the_next_question(kri):
    x, hosts = kri()
    assert x.post("/api/assistant/google", headers=tma(1), json={"consent": "nope"}).status_code == 400
    assert x.post("/api/assistant/google", headers=tma(1), json={"consent": "kri-g1"}).json() == {"yes": True}
    assert x.get("/api/me", headers=tma(1)).json()["kriGoogle"] is True
    assert _ask(x).status_code == 200 and hosts == [GOOGLE]
    hosts.clear()
    assert x.delete("/api/assistant/google", headers=tma(1)).json() == {"yes": False}
    assert x.get("/api/me", headers=tma(1)).json()["kriGoogle"] is False
    assert _ask(x).status_code == 200 and hosts == ["api.groq.com"]


def test_an_older_cards_yes_unlocks_nothing(kri):
    """A reworded card is a new version: a yes to another one is no yes."""
    _row(kri, "kri-g0")
    x, hosts = kri()
    assert x.get("/api/me", headers=tma(1)).json()["kriGoogle"] is False
    assert _ask(x).status_code == 200 and GOOGLE not in hosts


@pytest.mark.parametrize("why", ["off", "no_key", "earlier_policy", "board_staff"])
def test_unavailable_never_google_even_with_a_yes(kri, why):
    """The operator's ASSIST_LEAD=off, no GEMINI_API_KEY, a student on an earlier policy (the EU host alone,
    board_writer), BOARD=staff without the forum channel (the visible policy names the EU host alone): the client is
    told nothing (no kriGoogle: the card and the Settings row stay hidden), a yes can't be given, and a yes kept from
    before never reaches Google. Withdrawing still works."""
    _row(kri)
    x, hosts = kri(**{"off": {"assist_lead": "off"}, "no_key": {"gemini_key": ""}, "earlier_policy": {"policy": "new"},
                      "board_staff": {"board": "staff"}}[why])
    if why == "board_staff":
        con = db.connect(kri.db)
        con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (kri.uid,))
        con.close()
    assert "kriGoogle" not in x.get("/api/me", headers=tma(1)).json()
    assert x.post("/api/assistant/google", headers=tma(1), json={"consent": "kri-g1"}).status_code == 404
    _ask(x)  # an earlier policy: only the EU host may take it, and it has no key here (busy); the others answer
    assert GOOGLE not in hosts
    assert x.delete("/api/assistant/google", headers=tma(1)).status_code == 200


def test_deleting_the_account_removes_the_yes(kri):
    _row(kri)
    con = db.connect(kri.db)
    logic.delete_me(con, logic.Viewer(kri.uid, "user", True))
    assert con.execute("SELECT COUNT(*) FROM kri_consents").fetchone()[0] == 0
    assert ("kri_consents", "user_id") in logic.account._DEL_GONE


def test_answer_times_with_old_rows(env):
    _, cfg = env
    con = db.connect(cfg.db_path)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"ai_use:{day}", json.dumps({"groq:g/m": [2, 1]})))
    con.execute("INSERT INTO meta (key, value) VALUES ('ai_use:2026-01-01', ?)", (json.dumps({"cf:x": [5, 0]}),))
    llm._count(cfg.db_path, "groq:g/m", True, 1500)
    llm._count(cfg.db_path, "groq:g/m", False)
    llm._count(cfg.db_path, llm.GOOGLE, True, 4000)
    llm._count(cfg.db_path, llm.GOOGLE, True, 3000)
    use = llm.usage(con)
    assert use[day] == {"groq:g/m": [3, 2, 1500, 1], llm.GOOGLE: [2, 0, 7000, 2]}  # average: ms / timed
    assert use["2026-01-01"] == {"cf:x": [5, 0, 0, 0]}
