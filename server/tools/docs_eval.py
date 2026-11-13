"""The documents search's eval: realistic student questions (docs_eval.json, no document text in it) with the source that
answers each; hit@3 of the words' search alone and of the hybrid one. A Handbook page counts within one page (the three
languages' editions shift by a page); a curriculum's answer is its chunk with the semester or the course code asked.

    cd server && .venv/bin/python tools/docs_eval.py /var/lib/kbtu/docs.db   # hybrid too with CF_ACCOUNT_ID, CF_AI_TOKEN
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kbtu import docs  # noqa: E402

QUESTIONS = Path(__file__).with_name("docs_eval.json")


def hit(h: dict, expect: list) -> bool:
    """A source, its page if given, and the words its chunk must hold if given (a curriculum's "semester 3", a course code)."""
    page = int(h["at"][3:]) if h["at"].startswith("p. ") else None
    return any(doc in h["doc"] and (want is None or page is not None and abs(page - want) <= 1) and all(w in h["text"] for w in must)
               for doc, want, *must in expect)


def run(path: str, embed=None, k: int = 3) -> dict:
    """embed: texts → normalised vectors (Cloudflare's by default when CF_* are set); None: the words' search alone."""
    ix = docs.Index(path)
    ix.ready()
    qs = json.loads(QUESTIONS.read_text())
    out = {"n": len(qs), "fts": 0, "hybrid": 0 if embed and ix.vectors else None, "missed": []}
    for x in qs:
        f = any(hit(h, x["expect"]) for h in ix.search(x["q"], k=k))
        out["fts"] += f
        if out["hybrid"] is not None:
            hy = any(hit(h, x["expect"]) for h in ix.search(x["q"], embed([x["q"]])[0], k=k))
            out["hybrid"] += hy
        else:
            hy = None
        if not f or hy is False:
            out["missed"].append({"q": x["q"], "fts": f, "hybrid": hy})
    return out


if __name__ == "__main__":
    acc, tok = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_AI_TOKEN", "").strip()
    print(json.dumps(run(sys.argv[1], (lambda t: docs.embed(t, acc, tok)) if acc and tok else None), ensure_ascii=False, indent=1))
