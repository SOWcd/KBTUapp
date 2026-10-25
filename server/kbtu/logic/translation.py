"""The AI translator's queue and state (ai.py, PLAN 9)."""
from __future__ import annotations

import json
import time

from ..db import tx

from .core import one, rows


# ------------------------------------------------------------ translations (ai.py, PLAN 9)
# The postman's translator takes one text at a time: an upcoming public event (never drafts, team-only ones or
# meetings: only what anyone may read goes to Cloudflare, as the privacy policy says), else an active club's
# description, else a public channel's mirrored post that got no translation from the channel itself (mirror.py) in
# AI_POST_WAIT. An edit clears lang (update_event, update_org, mirror.take), so the row comes back; 3 failed calls
# leave it as typed.

AI_TRIES = 3
AI_LIMITS = {"title": 80, "description": 2000}
AI_ORG_LIMITS = {"description": 600}
AI_POST_LIMITS = {"title": 120, "body": 2000}
AI_POST_WAIT = 7200       # a channel's post waits 2 h for its own translations (folded posts, its comments) before AI
AI_LIMIT = {"event": AI_LIMITS, "org": AI_ORG_LIMITS, "post": AI_POST_LIMITS}


def ai_next(con) -> tuple[str, int, dict[str, str]] | None:
    """("event" | "org" | "post", id, its texts as they are now), or None."""
    e = one(con, """SELECT e.id, e.title, e.description FROM events e JOIN orgs o ON o.id = e.org_id
        WHERE e.lang IS NULL AND e.ai_tries < ? AND e.status = 'published' AND e.visibility = 'public' AND e.meeting = 0
          AND e.hidden_at IS NULL AND o.status = 'active' AND COALESCE(e.ends_at, e.starts_at) > ? ORDER BY e.updated_at DESC LIMIT 1""", AI_TRIES, core.now())
    if e:
        return "event", e["id"], {"title": e["title"], "description": e["description"]}
    o = one(con, "SELECT id, description FROM orgs WHERE lang IS NULL AND ai_tries < ? AND status = 'active' AND trim(description) != '' ORDER BY id DESC LIMIT 1", AI_TRIES)
    if o:
        return "org", o["id"], {"description": o["description"]}
    p = one(con, """SELECT p.id, p.title, p.body FROM posts p JOIN orgs o ON o.id = p.org_id WHERE p.tg_url IS NOT NULL AND p.lang IS NULL
        AND p.tr_by IS NULL AND p.ai_tries < ? AND p.hidden_at IS NULL AND o.status = 'active' AND p.created_at BETWEEN ? AND ?
        ORDER BY p.created_at DESC LIMIT 1""", AI_TRIES, core.now() - 7 * 86400, core.now() - AI_POST_WAIT)
    return ("post", p["id"], {"title": p["title"], "body": p["body"]}) if p else None


def ai_save(con, kind: str, rid: int, was: dict[str, str], src: str, tr: dict[str, dict[str, str]]) -> None:
    """The translations, unless the text was edited meanwhile (then the edit's own turn comes)."""
    with tx(con):
        if kind == "event":
            n = con.execute("UPDATE events SET i18n = ?, lang = ? WHERE id = ? AND title = ? AND description = ? AND lang IS NULL",
                        (json.dumps({k: {"title": x.get("title", was["title"]), "description": x.get("description", "")} for k, x in tr.items()}, ensure_ascii=False),
                         src, rid, was["title"], was["description"])).rowcount
            if not n:
                return
        elif kind == "post":  # unless the channel's own translations came meanwhile
            if not con.execute("UPDATE posts SET i18n = ?, lang = ?, tr_by = 'ai' WHERE id = ? AND title = ? AND body = ? AND tr_by IS NULL",
                               (json.dumps({k: {"title": x.get("title", was["title"]), "body": x.get("body", "")} for k, x in tr.items()}, ensure_ascii=False),
                                src, rid, was["title"], was["body"])).rowcount:
                return
        else:
            o = one(con, "SELECT i18n FROM orgs WHERE id = ? AND description = ? AND lang IS NULL", rid, was["description"])
            if not o:
                return
            have = json.loads(o["i18n"]) if o["i18n"] else {}
            have = {k: {a: b for a, b in x.items() if a != "description"} for k, x in have.items()}  # a name or a school's abbr stays
            for k, x in tr.items():
                have.setdefault(k, {})["description"] = x["description"]
            con.execute("UPDATE orgs SET i18n = ?, lang = ? WHERE id = ?", (json.dumps({k: x for k, x in have.items() if x}, ensure_ascii=False), src, rid))
        _ai_note(con, done=True)


def ai_failed(con, kind: str, rid: int, why: str) -> None:
    with tx(con):
        con.execute(f"UPDATE {({'event': 'events', 'post': 'posts'}).get(kind, 'orgs')} SET ai_tries = ai_tries + 1 WHERE id = ?", (rid,))  # a table from the three above
        _ai_note(con, error=f"{kind} {rid}: {why}"[:200])


def _ai_note(con, done: bool = False, error: str | None = None, on: bool | None = None) -> None:
    """What the admin panel shows (admin_stats): on or off, translated today (UTC, Cloudflare's day), the last error."""
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if done:
        n = one(con, "SELECT value FROM meta WHERE key = 'ai:done'")
        count = int(n[0].split()[1]) + 1 if n and n[0].startswith(day) else 1
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:done', ?)", (f"{day} {count}",))
    if error is not None:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:error', ?)", (f"{day} {error}",))
    if on is not None:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:on', ?)", ("1" if on else "0",))


def ai_note(con, error: str | None = None, on: bool | None = None) -> None:
    with tx(con):
        _ai_note(con, error=error, on=on)


def ai_state(con) -> dict:
    meta = dict(rows(con, "SELECT key, value FROM meta WHERE key LIKE 'ai:%'"))
    day = time.strftime("%Y-%m-%d", time.gmtime())
    done = meta.get("ai:done", "")
    return {"on": meta.get("ai:on") == "1", "today": int(done.split()[1]) if done.startswith(day) else 0, "error": meta.get("ai:error")}


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
