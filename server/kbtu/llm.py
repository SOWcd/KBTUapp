"""The AI provider chain: one OpenAI-shaped client over every free account the owner has, an ordered chain
of (provider, model) links from the strongest to the weakest. A link that is rate-limited, busy, slow or answers
nonsense hands over to the next and rests for its reset time; a missing key drops that provider's links; Munito runs
on both its keys (the second when the first is limited). Which link answered is logged and counted per day (never
the prompt). The chain's model names are measured from the providers' lists on prod; AI_CHAIN overrides them
("provider:model,provider:model"), so a renamed model is fixed without a deploy of code."""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

log = logging.getLogger("kbtu.llm")

URLS = {
    "cf": "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
    "munito": "https://api.munito.ai/inference/v1/chat/completions",
    # Munito's EU host: the global one "can run in any region" (docs.munito.ai/gdpr-data-residency); the forum's look
    # must stay in the EU (privacy policy, section 11).
    "munitoeu": "https://api.eu.munito.ai/inference/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    # APInex (apinex.bond/llms.txt): an OpenAI-compatible reseller; free/* models spend a daily allowance
    # (20M weighted tokens, V4.1 Flash weighs 3) at 15 req/min per account (api/public/subscriptions, /rate-limits)
    "apinex": "https://api.apinex.bond/v1/chat/completions",
    # Google's OpenAI-compatible endpoint (aistudio.google.com/docs/openai): the key as a Bearer header, never in the URL
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}
# the biggest free limits first: APInex, Munito (rate limits only, no daily cap), Groq (~1K
# req/day per model), Cloudflare (10k neurons/day for all its models; these three
# answer on the free plan in 1.2-1.5 s), OpenRouter (50 free req/day)
CHAIN = ("apinex:free/deepseek-v4.1-flash,munito:deepseek-ai/deepseek-v4.1-flash-1017,munito:zai-org/glm-5.3-flash,"
         "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b,cf:@cf/qwen/qwen3-30b-a3b-fp8,"
         "cf:@cf/meta/llama-3.3-70b-instruct-fp8-fast,cf:@cf/mistralai/mistral-small-3.1-24b-instruct,openrouter:nvidia/nemotron-3-ultra-550b-a55b:free")
RETRY_WAIT = 1.0     # before the one retry of a lone link
REST = 60             # a limited or busy link without a Retry-After rests this long
REST_BROKEN = 6 * 3600  # a refused key or an unknown model: hours, then a fresh try
TIMEOUT = 60
HEDGE = 1.5     # race: how long the first link has alone before another company's is asked too
EFFORT_OK = ("munito", "munitoeu")  # the providers known to take reasoning_effort (chat's effort)
# Google, the assistant's first try (chat's lead=; app.py: ASSIST_LEAD not off and the student's own yes,
# assistant.GOOGLE_YES): series 4 only, the one on the free tier. Free tier: often 503 "high demand"
# (2 of 3 calls answered), so one quick retry, then the usual chain; both tries share LEAD_WAIT of wall clock, the most a student waits longer when Google fails.
# ponytail: real answers took 3.1 to 6.5 s (effort low, 700 tokens), so 9 s lets them through; a failing Google
# costs a student up to 9 s more than the chain alone, and leaves the chain 21 s of the assistant's 30 s (eu_ai's whole).
# Lower it once the admin's AI page shows Google's average (ms / ok)
GOOGLE = "google:gemini-4-hydrogen"
LEAD_WAIT = 9.0
LEAD_BACKOFF = 0.4
# Gemini 4 can't stop thinking and its thinking counts in max_tokens (aistudio.google.com/docs/thinking): any
# effort asked becomes its lowest level, "low" ("none" and "minimal" are refused there)
GOOGLE_EFFORT = "low"
RACE_MOST = 3   # race: links asked at once, at most (each a request on someone's rate limit)


class Busy(Exception):
    """No link answered (all resting, limited or down): try again later."""


class BadAnswers(Exception):
    """Links answered, but nothing the caller could use."""


@dataclass(frozen=True)
class Link:
    provider: str
    model: str
    key: str                     # which key (munito, munito2): its own rest
    url: str
    token: str

    @property
    def name(self) -> str:
        return f"{self.key}:{self.model}"


_rest: dict[str, float] = {}     # link name -> resting until (this process)
_turn = itertools.count()        # which key of a provider goes first this time: the keys share the load


def links(cfg, chain: str | None = None) -> list[Link]:
    """The chain for this config: every (provider, model) whose key is set, Munito once per key."""
    keys = {"cf": [("cf", cfg.cf_ai_token)] if cfg.cf_account_id and cfg.cf_ai_token else [],
            "munito": [(f"munito{i + 1 if i else ''}", k) for i, k in enumerate(cfg.munito_keys) if k],
            "munitoeu": [(f"munitoeu{i + 1 if i else ''}", k) for i, k in enumerate(cfg.munito_keys) if k],
            "openrouter": [("openrouter", cfg.openrouter_key)] if cfg.openrouter_key else [],
            "groq": [("groq", cfg.groq_key)] if cfg.groq_key else [],
            "apinex": [("apinex", cfg.apinex_key)] if cfg.apinex_key else [],
            "google": [("google", cfg.gemini_key)] if cfg.gemini_key else []}
    out = []
    for item in (chain or cfg.ai_chain or CHAIN).split(","):
        provider, _, model = item.strip().partition(":")
        for name, token in keys.get(provider, []):
            out.append(Link(provider, model, name, URLS[provider].format(account=cfg.cf_account_id), token))
    return out


def available(cfg) -> bool:
    return bool(links(cfg))


def _count(path: str | None, link: str, ok: bool, ms: int = 0) -> None:
    """Today's answers and failures per link, for the admin's AI page (meta ai_use:<day>): [ok, fail, ms, timed], ms the
    sum of the timed answers' milliseconds (average = ms / timed; older rows are [ok, fail]). Its own short
    connection: a request cut at the 30 s cap abandons this thread, which must never touch the request's pooled one."""
    if not path:
        return
    from . import db  # here: llm is imported by db's users
    c = db.connect(path)
    try:
        with c:
            key = f"ai_use:{time.strftime('%Y-%m-%d', time.gmtime())}"
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            use = json.loads(row[0]) if row else {}
            n = use.setdefault(link, [0, 0])
            n += [0] * (4 - len(n))  # Supply zero timing totals for counters stored without latency samples.
            n[0 if ok else 1] += 1
            if ok:
                n[2] += ms
                n[3] += 1
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, json.dumps(use)))
    finally:
        c.close()


def _rest_until(name: str, until: float) -> None:
    """A rest only ever grows: a later failure (a lead's retry) never shortens one a Retry-After set."""
    _rest[name] = max(_rest.get(name, 0), until)


def _rest_for(r: httpx.Response) -> float:
    try:
        return max(1.0, min(float(r.headers.get("retry-after") or REST), 86400.0))
    except ValueError:
        return REST


async def chat(cfg, http: httpx.AsyncClient, messages: list[dict], *, max_tokens: int = 800, temperature: float = 0.2,
               check: Callable[[str], bool] | None = None, con=None, only: tuple[str, ...] | None = None,
               timeout: float = TIMEOUT, chain: str | None = None, race: bool = False, effort: str | None = None,
               lead: str | None = None, lead_ok: Callable[[], bool] | None = None) -> tuple[str, str]:
    """(the answer's text, the link that gave it). check: is this answer usable (JSON that parses, ...)? If not, the next
    link is asked; the one that answered doesn't rest for it. only: these providers and no other, whatever AI_CHAIN says
    (what the privacy policy names for a text), asked in that order; chain: a caller's own links instead of the shared
    chain. race: a student waits: the first link, and if it hasn't answered in HEDGE seconds (or failed),
    another company's at once; the first usable answer wins, then the rest one by one. Busy: none answered; BadAnswers: none usable.
    effort: Munito's `reasoning_effort` ("none": no thinking first). Measured on prod: an event's announcement sent
    both DeepSeek flash models reasoning through all 3500 tokens with no answer (21-37 s each, then the next link); with
    "none" the same form came in 1-2 s. Only Munito's hosts get the field: another provider may refuse an unknown one,
    and a 400 rests its link for hours. lead: links ("provider:model,...", outside only= and chain=) asked first, each
    within LEAD_WAIT and once more after a busy failure; then everything above as without it. No key: nothing asked.
    lead_ok: asked (in a thread) right before each send to a lead; False: that lead is skipped, the chain runs (the
    student's yes withdrawn while the question was on its way)."""
    answered = busy = False
    after = None  # the last busy answer's Retry-After, in seconds (inf: one we can't read)
    path = con.execute("PRAGMA database_list").fetchone()[2] if con is not None else None  # the file, for _count's own connection
    pool = [x for x in links(cfg, chain) if only is None or x.provider in only]
    if only:  # stable: each provider's links keep the chain's order
        pool.sort(key=lambda x: only.index(x.provider))
    turn = next(_turn)  # one model on several keys: each call starts from the next key, the others stay its spares
    pool = [x for _, g in itertools.groupby(pool, key=lambda x: (x.provider, x.model)) for g in [list(g)]
            for x in g[turn % len(g):] + g[:turn % len(g)]]
    awake = [x for x in pool if _rest.get(x.name, 0) <= time.time()]

    async def ask(link, wait: float = timeout) -> str | None:
        nonlocal answered, busy, after
        t0 = time.time()
        busy, after = False, None
        thought = effort if link.provider in EFFORT_OK else GOOGLE_EFFORT if link.provider == "google" else None
        try:
            r = await http.post(link.url, headers={"Authorization": f"Bearer {link.token}"}, timeout=wait,
                                json={"model": link.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                                      **({"reasoning_effort": thought} if effort and thought else {})})
        except httpx.HTTPError as exc:
            busy = True
            log.warning("ai %s: %s", link.name, type(exc).__name__)
            _rest_until(link.name, time.time() + REST)
            await asyncio.to_thread(_count, path, link.name, False)
            return None
        if r.status_code in (429, 503) or r.status_code >= 500:
            busy = True
            if (hint := r.headers.get("retry-after")) is not None:
                try:
                    after = float(hint)
                except ValueError:
                    after = float("inf")
            _rest_until(link.name, time.time() + _rest_for(r))
            log.warning("ai %s: http %d, resting", link.name, r.status_code)
            await asyncio.to_thread(_count, path, link.name, False)
            return None
        if r.status_code != 200:  # a refused key, an unknown model, Cloudflare's spent day (4006)
            _rest_until(link.name, time.time() + REST_BROKEN)
            said = "(withheld: it repeats the key)" if link.token in r.text else r.text[:160].replace("\n", " ")  # never headers
            log.warning("ai %s: http %d: %s", link.name, r.status_code, said)
            await asyncio.to_thread(_count, path, link.name, False)
            return None
        try:
            body = r.json()
            choice = (body.get("choices") or body.get("result", {}).get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content")
            cut = choice.get("finish_reason") == "length"
        except (ValueError, AttributeError, TypeError, KeyError, IndexError):  # JSON of another shape ("choices": {...})
            text, cut = None, False
        answered = True
        if not isinstance(text, str) or not text.strip() or cut or (check and not check(text)):
            log.warning("ai %s: unusable answer (%s)", link.name, "cut at max_tokens" if cut else "empty" if not isinstance(text, str) or not text.strip() else "failed the check")
            await asyncio.to_thread(_count, path, link.name, False)
            return None
        log.warning("ai %s answered in %.1f s", link.name, time.time() - t0)  # a warning: the server's log keeps warnings, the timing shows there
        await asyncio.to_thread(_count, path, link.name, True, round((time.time() - t0) * 1000))  # a write: never on the event loop
        return text

    async def lead_try(link) -> str | None:
        for again in (False, True):
            if lead_ok is not None and not await asyncio.to_thread(lead_ok):
                return None
            text = await ask(link, LEAD_WAIT)
            # a retry only after a busy answer that didn't ask for a longer wait than ours
            if text is not None or again or not busy or (after or 0) > LEAD_BACKOFF:
                return text
            await asyncio.sleep(LEAD_BACKOFF)

    for link in links(cfg, lead) if lead else ():
        if _rest.get(link.name, 0) > time.time():  # failed both tries lately: the chain at once
            continue
        try:  # the wall clock for both tries and their counting: the chain starts within LEAD_WAIT whatever happens
            text = await asyncio.wait_for(lead_try(link), LEAD_WAIT)
        except Exception as exc:  # noqa: BLE001 - out of time, or anything its answer raised: a failed lead, the chain runs
            log.warning("ai %s: lead given up (%s)", link.name, type(exc).__name__)
            _rest_until(link.name, time.time() + REST)
            continue
        if text is not None:
            _rest.pop(link.name, None)  # the retry answered: not resting for the first try's 503
            return text, link.name

    # every link resting: a rest is a guess (one timeout or 429 a minute ago), so the soonest to wake is asked anyway
    # rather than "busy" for everyone (else the assistant says busy too often)
    order = awake or sorted(pool, key=lambda x: _rest.get(x.name, 0))[:1]
    if race and len(order) > 1:
        firm = lambda x: x.provider.removesuffix("eu")  # noqa: E731  munitoeu and munito: one company's two hosts
        other = next((x for x in order[1:] if firm(x) != firm(order[0])), order[1])  # another company: its own outage
        # staggered (asked one by one, a 30 s ReadTimeout on the EU host and a resting second can hold the fill a
        # minute): each HEDGE s without an answer, or at once on a failure, the next link joins, at most
        # RACE_MOST in flight; the usual day is still one call
        waiting = [order[0], other] + [x for x in order if x not in (order[0], other)]
        order, tasks = [], {}
        try:
            while waiting or tasks:
                if waiting and len(tasks) < RACE_MOST:
                    link = waiting.pop(0)
                    tasks[asyncio.ensure_future(ask(link))] = link
                done, _ = await asyncio.wait(tasks, timeout=HEDGE if waiting and len(tasks) < RACE_MOST else None,
                                             return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    link = tasks.pop(t)
                    if t.result() is not None:
                        return t.result(), link.name
        finally:
            for t in tasks:
                t.cancel()
    for link in order:
        text = await ask(link)
        if text is not None:
            return text, link.name
    if not answered and len(pool) == 1:
        # one provider alone may take this text (only=EU_ONLY): its single 502 or timeout would be "busy" for the student.
        # One more try after a breath; a real outage still says busy
        await asyncio.sleep(RETRY_WAIT)
        text = await ask(pool[0])
        if text is not None:
            return text, pool[0].name
    raise BadAnswers() if answered else Busy()


MUNITO_ADMIN = "https://api.munito.ai/admin/v1"


async def munito_account(cfg, http: httpx.AsyncClient) -> dict:
    """Munito's own view of each key (the keys can read their account): today's usage and the limits, as Munito
    gives them; a key that won't say is left out. Never the key itself."""
    out = {}
    for i, key in enumerate(cfg.munito_keys):
        got = {}
        for part in ("usage", "limits"):
            try:
                r = await http.get(f"{MUNITO_ADMIN}/{part}", headers={"Authorization": f"Bearer {key}"}, timeout=10)
                if r.status_code == 200:
                    got[part] = r.json()
            except (httpx.HTTPError, ValueError):
                pass
        if got:
            out[f"munito{i + 1 if i else ''}"] = got
    return out


def usage(con) -> dict[str, dict[str, list[int]]]:
    """{day: {link: [answers, failures, ms, timed]}} for the last 7 days (old [ok, fail] rows padded with zeros)."""
    out = {}
    for k, v in con.execute("SELECT key, value FROM meta WHERE key LIKE 'ai_use:%' ORDER BY key DESC LIMIT 7").fetchall():
        out[k.split(":", 1)[1]] = {link: n + [0] * (4 - len(n)) for link, n in json.loads(v).items()}
    return out
