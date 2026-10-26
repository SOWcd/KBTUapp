"""The bot's background work queues: the AI translator (ai.py) and videos (video.py)."""
from __future__ import annotations

import json
import sqlite3
import time

from .. import video
from ..db import tx

from .core import ApiError, Viewer, one, organizes, rows


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




# ------------------------------------------------------------ videos (video.py)

def video_shape(x: sqlite3.Row) -> dict:
    """types.ts Video: the poster is a photo named like the video."""
    ready = x["status"] == "ready"
    return {"id": x["id"], "status": x["status"], "url": f"media/{x['path']}.mp4" if ready else None, "duration": x["duration"],
            "poster": {"url": f"media/{x['path']}.webp", "thumb": f"media/{x['path']}.t.webp", "w": x["width"], "h": x["height"],
                       "blur": "", "color": x["color"]} if ready else None, "error": x["error"]}


def new_video(con, v: Viewer, size, wide: object = False) -> dict:
    """An upload starts (Head+, as a cover): its size is said up front, the pieces follow (PUT, app.py). `wide`: for the
    sheet's background (PLAN 32), compressed for it."""
    if not organizes(con, v):
        raise ApiError("forbidden")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= video.MAX_BYTES:
        raise ApiError("bad_input", "too_big")
    vid = con.execute("INSERT INTO videos (owner_id, status, size, created_at, wide) VALUES (?, 'uploading', ?, ?, ?)", (v.id, size, core.now(), int(wide is True))).lastrowid
    return {"id": vid, "at": 0}


def my_video(con, v: Viewer, vid: int) -> sqlite3.Row:
    x = one(con, "SELECT * FROM videos WHERE id = ? AND owner_id = ?", vid, v.id)
    if not x:
        raise ApiError("not_found")
    return x


def video_uploaded(con, v: Viewer, vid: int, have: int) -> dict:
    """All pieces in: the postman compresses it next."""
    x = my_video(con, v, vid)
    if x["status"] != "uploading" or have != x["size"]:
        raise ApiError("conflict")
    con.execute("UPDATE videos SET status = 'queued' WHERE id = ?", (vid,))
    return video_shape(my_video(con, v, vid))


def next_video(con) -> sqlite3.Row | None:
    with tx(con):
        x = one(con, "SELECT * FROM videos WHERE status = 'queued' ORDER BY id LIMIT 1")
        if x:
            con.execute("UPDATE videos SET status = 'working' WHERE id = ?", (x["id"],))
    return x


def video_done(con, vid: int, out: dict | None, error: str | None = None) -> None:
    if out:
        con.execute("""UPDATE videos SET status = 'ready', path = ?, width = ?, height = ?, duration = ?, bytes = ?, color = ?
            WHERE id = ?""", (out["path"], out["width"], out["height"], out["duration"], out["bytes"], out["color"], vid))
    else:
        con.execute("UPDATE videos SET status = 'failed', error = ? WHERE id = ?", (error, vid))


def stale_videos(con) -> list[tuple[int, str | None]]:
    """Videos no event holds a day after their upload (replaced, taken off, the event deleted, or never saved): their
    rows go; the caller deletes the files. (id, path)."""
    with tx(con):
        old = rows(con, """SELECT id, path FROM videos WHERE created_at < ? AND status != 'working'
            AND id NOT IN (SELECT video_id FROM events WHERE video_id IS NOT NULL
                           UNION SELECT wide_video_id FROM events WHERE wide_video_id IS NOT NULL)""", core.now() - 86400)
        con.executemany("DELETE FROM videos WHERE id = ?", [(r["id"],) for r in old])
        # files are named by their content: the same clip kept by another row keeps its files
        return [(r["id"], None if r["path"] and one(con, "SELECT 1 FROM videos WHERE path = ?", r["path"]) else r["path"]) for r in old]


def _video(con, v: Viewer, body: dict, keep: int | None, key: str = "videoId") -> int | None:
    """The editor's videoId (wideVideoId: the sheet's background), like coverId: absent keeps, null takes it off, an id
    must be my own upload for that slot that didn't fail."""
    if key not in body:
        return keep
    if body[key] is None:
        return None
    try:
        x = one(con, "SELECT id FROM videos WHERE id = ? AND owner_id = ? AND status != 'failed' AND wide = ?",
                int(body[key]), v.id, int(key == "wideVideoId"))
    except (TypeError, ValueError):
        x = None
    if not x:
        raise ApiError("bad_input")
    return x["id"]


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
