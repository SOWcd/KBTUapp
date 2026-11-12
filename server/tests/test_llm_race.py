"""A student waits on a post's check: race=True asks the first link alone for llm.HEDGE seconds, then another
company's too; the first usable answer wins (owner, Nov 4: the check was slow)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace as N

import httpx

from kbtu import llm


def _run(monkeypatch, first_host):
    asked = []

    async def reply(req):
        asked.append(req.url.host)
        if "slow" in req.url.host:
            await asyncio.sleep(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})
    links = [N(name=f"{p}:m", provider=p, url=f"https://{h}.example/v1", token="t", model="m")
             for p, h in (("munitoeu", first_host), ("munito", "slow2"), ("groq", "fast"))]
    monkeypatch.setattr(llm, "links", lambda cfg, chain=None: links)
    monkeypatch.setattr(llm, "HEDGE", 0.2)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            t = asyncio.get_running_loop().time()
            out = await llm.chat(None, http, [], race=True, check=lambda w: w == "OK")
            return out, asyncio.get_running_loop().time() - t
    (_, link), took = asyncio.run(go())
    return link, took, asked


def test_race_asks_one_on_a_good_day(monkeypatch):
    link, _, asked = _run(monkeypatch, "quick")
    assert link == "munitoeu:m" and asked == ["quick.example"]          # no second call spent


def test_race_hedges_to_another_company(monkeypatch):
    link, took, asked = _run(monkeypatch, "slow")
    assert link == "groq:m" and took < 0.8 and asked == ["slow.example", "fast.example"]   # not munito's second host


def test_a_lone_link_gets_one_more_try(monkeypatch):
    """Nov 12: a text only one provider may take (only=...) said "busy" on that provider's single 502; one retry."""
    hits = []

    async def reply(req):
        hits.append(1)
        if len(hits) <= fails:
            return httpx.Response(502)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})
    links = [N(name=f"{p}:m", provider=p, url=f"https://{p}.example/v1", token="t", model="m") for p in ("munitoeu", "groq")]
    monkeypatch.setattr(llm, "links", lambda cfg, chain=None: links)
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)

    async def go():
        llm._rest.clear()
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            return await llm.chat(None, http, [], only=("munitoeu",))
    fails = 1
    assert asyncio.run(go()) == ("OK", "munitoeu:m") and len(hits) == 2
    hits.clear()
    fails = 2  # a real outage still says busy, after exactly one retry
    try:
        asyncio.run(go())
        raise AssertionError("not busy")
    except llm.Busy:
        assert len(hits) == 2
