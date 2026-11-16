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


def test_race_goes_on_down_the_chain(monkeypatch):
    """Nov 15: the first link hung, the other company's failed: the rest joined one by one, not after the hang."""
    asked = []

    async def reply(req):
        asked.append(req.url.host)
        if req.url.host.startswith("hang"):
            await asyncio.sleep(5)
        if req.url.host.startswith("down"):
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})
    links = [N(name=f"{p}:m", provider=p, url=f"https://{h}.example/v1", token="t", model="m")
             for p, h in (("munitoeu", "hang"), ("groq", "down"), ("munito", "good"))]
    monkeypatch.setattr(llm, "links", lambda cfg, chain=None: links)
    monkeypatch.setattr(llm, "HEDGE", 0.2)

    async def go():
        llm._rest.clear()
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            t = asyncio.get_running_loop().time()
            out = await llm.chat(None, http, [], race=True, check=lambda w: w == "OK")
            return out, asyncio.get_running_loop().time() - t
    (_, link), took = asyncio.run(go())
    llm._rest.clear()
    assert link == "munito:m" and took < 1 and asked == ["hang.example", "down.example", "good.example"]


def test_effort_goes_to_munito_alone(monkeypatch):
    """effort="none" (the event form: DeepSeek reasoned through its whole allowance, Nov 16) is sent to Munito's hosts
    only: another provider may refuse the field, and a 400 rests its link for hours."""
    import json
    sent = {}

    async def reply(req):
        sent[req.url.host] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "no" if "eu" in req.url.host else "OK"}, "finish_reason": "stop"}]})
    links = [N(name=f"{p}:m", provider=p, url=f"https://{h}.example/v1", token="t", model="m") for p, h in (("munitoeu", "eu"), ("groq", "gq"))]
    monkeypatch.setattr(llm, "links", lambda cfg, chain=None: links)
    monkeypatch.setattr(llm, "_rest", {})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            return await llm.chat(None, http, [], check=lambda w: w == "OK", effort="none")
    assert asyncio.run(go())[1] == "groq:m"
    assert sent["eu.example"]["reasoning_effort"] == "none" and "reasoning_effort" not in sent["gq.example"]


def test_the_questions_language_is_named():
    """assistant.with_lang: English and Kazakh questions name their language at the system message's end; a Russian one
    (or Kazakh without its letters) is left to the model; the question itself is untouched."""
    from kbtu.logic import assistant as A
    sys = lambda q: A.with_lang([{"role": "system", "content": "S"}, {"role": "user", "content": q}])  # noqa: E731
    assert "in English" in sys("how do I get a transcript?")[0]["content"] and sys("ok?")[1]["content"] == "ok?"
    assert "in Kazakh." in sys("\u0441\u0442\u0438\u043f\u0435\u043d\u0434\u0438\u044f \u049b\u0430\u0448\u0430\u043d \u0442\u04af\u0441\u0435\u0434\u0456?")[0]["content"]
    assert sys("\u0433\u0434\u0435 256 \u043a\u0430\u0431\u0438\u043d\u0435\u0442?")[0]["content"] == "S" and sys("256?")[0]["content"] == "S"


def test_three_languages_are_kept():
    """An announcement in ru, kk and en: the fill gives the other two as written, and the save keeps them as the
    event's translations (lang set: the AI translator skips it); two languages or a bad shape: nothing."""
    import json
    from kbtu.logic import assistant, organizing
    got = {"title": "Stretching", "description": "Come", "lang": "en",
           "tr": {"kk": {"title": "\u0421\u0442\u0440\u0435\u0442\u0447\u0438\u043d\u0433", "description": "a\n\n\n\nb"}, "ru": {"title": "\u0420\u0430\u0441\u0442\u044f\u0436\u043a\u0430", "description": "c"}}}
    out = assistant.filled(json.dumps(got))
    assert out["tr"]["lang"] == "en" and out["tr"]["kk"]["description"] == "a\n\nb" and set(out["tr"]) == {"lang", "kk", "ru"}
    assert "tr" not in assistant.filled(json.dumps({**got, "tr": {"kk": got["tr"]["kk"]}}))
    assert "tr" not in assistant.filled(json.dumps({**got, "lang": None}))
    f = organizing._own_tr({"tr": out["tr"]}, {"description": "Come"})
    assert f["lang"] == "en" and set(json.loads(f["i18n"])) == {"kk", "ru"}
    assert organizing._own_tr({"tr": {"lang": "en", "kk": {"title": "x", "description": ""}}}, {"description": ""}) == {}
    assert organizing._own_tr({}, {"description": ""}) == {}
