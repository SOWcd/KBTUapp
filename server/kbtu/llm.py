"""AI0 (PLAN "AI0 spec", "AI provider"): one OpenAI-shaped client over every free account the owner has, an ordered chain
of (provider, model) links from the strongest to the weakest. A link that is rate-limited, busy, slow or answers
nonsense hands over to the next and rests for its reset time; a missing key drops that provider's links; Munito runs
on both its keys (the second when the first is limited). Which link answered is logged and counted per day (never
the prompt). The chain's model names are measured from the providers' lists on prod; AI_CHAIN overrides them
("provider:model,provider:model"), so a renamed model is fixed without a deploy of code."""
from __future__ import annotations

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
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}
CHAIN = ("cf:@cf/deepseek-ai/deepseek-v4-pro,munito:deepseek-v4.1-flash,openrouter:nvidia/nemotron-3-ultra:free,"
         "groq:openai/gpt-oss-120b,cf:@cf/moonshotai/kimi-k2.6,munito:glm-5.3-flash,groq:qwen/qwen3.8-27b,"
         "cf:@cf/zai-org/glm-5.3-flash,groq:openai/gpt-oss-20b")
REST = 60             # a limited or busy link without a Retry-After rests this long
REST_BROKEN = 6 * 3600  # a refused key or an unknown model: hours, then a fresh try
TIMEOUT = 60


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


def links(cfg) -> list[Link]:
    """The chain for this config: every (provider, model) whose key is set, Munito once per key."""
    keys = {"cf": [("cf", cfg.cf_ai_token)] if cfg.cf_account_id and cfg.cf_ai_token else [],
            "munito": [(f"munito{i + 1 if i else ''}", k) for i, k in enumerate(cfg.munito_keys) if k],
            "openrouter": [("openrouter", cfg.openrouter_key)] if cfg.openrouter_key else [],
            "groq": [("groq", cfg.groq_key)] if cfg.groq_key else []}
    out = []
    for item in (cfg.ai_chain or CHAIN).split(","):
        provider, _, model = item.strip().partition(":")
        for name, token in keys.get(provider, []):
            out.append(Link(provider, model, name, URLS[provider].format(account=cfg.cf_account_id), token))
    return out


def available(cfg) -> bool:
    return bool(links(cfg))


def _count(con, link: str, ok: bool) -> None:
    """Today's answers and failures per link, for the admin's AI page (meta ai_use:<day>)."""
    if con is None:
        return
    key = f"ai_use:{time.strftime('%Y-%m-%d', time.gmtime())}"
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    use = json.loads(row[0]) if row else {}
    use.setdefault(link, [0, 0])[0 if ok else 1] += 1
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, json.dumps(use)))


def _rest_for(r: httpx.Response) -> float:
    try:
        return max(1.0, min(float(r.headers.get("retry-after") or REST), 86400.0))
    except ValueError:
        return REST


async def chat(cfg, http: httpx.AsyncClient, messages: list[dict], *, max_tokens: int = 800, temperature: float = 0.2,
               check: Callable[[str], bool] | None = None, con=None) -> tuple[str, str]:
    """(the answer's text, the link that gave it). check: is this answer usable (JSON that parses, ...)? If not, the next
    link is asked; the one that answered doesn't rest for it. Busy: none answered; BadAnswers: none usable."""
    answered = False
    for link in links(cfg):
        if _rest.get(link.name, 0) > time.time():
            continue
        t0 = time.time()
        try:
            r = await http.post(link.url, headers={"Authorization": f"Bearer {link.token}"}, timeout=TIMEOUT,
                                json={"model": link.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        except httpx.HTTPError as exc:
            log.warning("ai %s: %s", link.name, type(exc).__name__)
            _rest[link.name] = time.time() + REST
            _count(con, link.name, False)
            continue
        if r.status_code in (429, 503) or r.status_code >= 500:
            _rest[link.name] = time.time() + _rest_for(r)
            log.warning("ai %s: http %d, resting", link.name, r.status_code)
            _count(con, link.name, False)
            continue
        if r.status_code != 200:  # a refused key, an unknown model, Cloudflare's spent day (4006)
            _rest[link.name] = time.time() + REST_BROKEN
            log.warning("ai %s: http %d: %s", link.name, r.status_code, r.text[:160].replace("\n", " "))
            _count(con, link.name, False)
            continue
        try:
            body = r.json()
            choice = (body.get("choices") or body.get("result", {}).get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content")
            cut = choice.get("finish_reason") == "length"
        except (ValueError, AttributeError, TypeError):
            text, cut = None, False
        answered = True
        if not isinstance(text, str) or not text.strip() or cut or (check and not check(text)):
            log.warning("ai %s: unusable answer", link.name)
            _count(con, link.name, False)
            continue
        log.info("ai %s answered in %.1f s", link.name, time.time() - t0)
        _count(con, link.name, True)
        return text, link.name
    raise BadAnswers() if answered else Busy()


def usage(con, days: int = 7) -> dict[str, dict[str, list[int]]]:
    """{day: {link: [answers, failures]}} for the last days; and which links rest now (this process's)."""
    out = {}
    for k, v in con.execute("SELECT key, value FROM meta WHERE key LIKE 'ai_use:%' ORDER BY key DESC LIMIT ?", (days,)).fetchall():
        out[k.split(":", 1)[1]] = json.loads(v)
    return out
