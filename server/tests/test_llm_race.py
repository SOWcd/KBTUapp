"""A student waits on a post's check: race=True asks the first link and another company's at once, the first usable
answer wins (owner, Nov 4: the check was slow)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace as N

import httpx

from kbtu import llm


def test_race_takes_the_fastest_company(monkeypatch):
    async def reply(req):
        if "slow" in req.url.host:
            await asyncio.sleep(2)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})
    links = [N(name=f"{p}:m", provider=p, url=f"https://{h}.example/v1", token="t", model="m")
             for p, h in (("munitoeu", "slow"), ("munito", "slow2"), ("groq", "fast"))]
    monkeypatch.setattr(llm, "links", lambda cfg, chain=None: links)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            t = asyncio.get_running_loop().time()
            out = await llm.chat(None, http, [], race=True, check=lambda w: w == "OK")
            return out, asyncio.get_running_loop().time() - t
    (text, link), took = asyncio.run(go())
    assert (text, link) == ("OK", "groq:m") and took < 1   # munito's second host is the same company: groq raced instead
