"""Comments, reports, take-downs and their undo."""
from __future__ import annotations

import json
import sqlite3

from ..db import tx

from .core import (ApiError, PERSON, PERSON_COLS, Viewer, _org, can, log_action, need_student, one, org_ref,
    person_ref, rows, shown_name)


# ---------------------------------------------------------------- comments and reports (§4.10)

COMMENTS_A_MINUTE, REPORTS_A_DAY = 10, 20


def _thread(con, v: Viewer, kind: str, tid: int) -> sqlite3.Row:
    """The post or event a comment thread hangs under, if the viewer can see it."""
    if kind == "post":
        p = one(con, """SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL
                     AND org_id NOT IN (SELECT id FROM orgs WHERE status = 'hidden')""", tid)  # the feed's own rules (posts())
        if not p or (p["audience"] == "clubs" and not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id)):
            raise ApiError("not_found")
        return p
    if kind == "event":
        return _event(con, v, tid)
    raise ApiError("not_found")


def _moderates(con, v: Viewer, org: int) -> bool:
    return v.role in ("admin", "moderator") or can(con, v, org, "posts")


def comments(con, v: Viewer, kind: str, tid: int) -> dict:
    """Comments under a post or an event: questions to the organizer ("where's the entrance?"). Students read and write
    (short names, §3); the club's Head+ answer as the club, take any down and turn the thread off; authors take theirs."""
    need_student(v)
    t = _thread(con, v, kind, tid)
    head, org = _moderates(con, v, t["org_id"]), org_ref(con, _org(con, t["org_id"]))
    lead = can(con, v, t["org_id"], "posts")
    if lead and kind == "event":  # read: Studio's "questions waiting" go, for me
        con.execute("INSERT OR REPLACE INTO comment_reads (event_id, user_id, last_id) SELECT ?, ?, COALESCE(MAX(id), 0) FROM comments WHERE event_id = ?",
                    (tid, v.id, tid))
    col = "post_id" if kind == "post" else "event_id"
    found = rows(con, f"""SELECT c.id AS cid, c.user_id, c.as_org, c.body, c.created_at, c.reply_to, {PERSON_COLS} FROM comments c
                 JOIN users u ON u.id = c.user_id LEFT JOIN students s ON s.user_id = u.id
                 WHERE c.{col} = ? AND c.deleted_at IS NULL ORDER BY c.created_at, c.id LIMIT 300""", tid)
    by_id = {c["cid"]: c for c in found}  # a reply quotes the comment it answers while that is still up
    quote = lambda q: {"id": q["cid"], "name": org["name"] if q["as_org"] else person_ref(q)["name"], "body": q["body"][:140]} if q else None  # noqa: E731
    items = [{"id": c["cid"], "person": None if c["as_org"] else person_ref(c), "org": org if c["as_org"] else None, "body": c["body"],
              "at": c["created_at"], "mine": c["user_id"] == v.id, "canDelete": head or c["user_id"] == v.id, "replyTo": quote(by_id.get(c["reply_to"]))}
             for c in found]
    return {"items": items, "on": bool(t["comments_on"]), "canModerate": head, "asOrg": org if lead else None}


def add_comment(con, v: Viewer, kind: str, tid: int, body: object, as_org: object, reply_to: object = None) -> dict:
    need_student(v)
    t = _thread(con, v, kind, tid)
    text = str(body or "").strip()
    col = "post_id" if kind == "post" else "event_id"
    to = None
    if reply_to is not None:  # a reply: to a comment still up in this thread
        to = one(con, f"SELECT id, user_id FROM comments WHERE id = ? AND {col} = ? AND deleted_at IS NULL", reply_to, tid) if isinstance(reply_to, int) else None
        if not to:
            raise ApiError("bad_input")
    if not 1 <= len(text) <= 500:
        raise ApiError("bad_input")
    if not t["comments_on"]:
        raise ApiError("closed")
    lead = can(con, v, t["org_id"], "posts")
    if as_org and not lead:
        raise ApiError("forbidden")
    if one(con, "SELECT COUNT(*) FROM comments WHERE user_id = ? AND created_at > ?", v.id, core.now() - 60)[0] >= COMMENTS_A_MINUTE:
        raise ApiError("rate_limited")
    askers: list[tuple[int]] = []
    if kind == "event":  # the bot: a question pings the club's Head+ (hourly at most); an answer (the club's
        # Head+ write, as the club or as themselves) pings the askers
        if lead:
            askers = [(u,) for u in sorted({r["user_id"] for r in _asking(con, tid)})]
        else:
            heads = rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice', 'head') AND user_id != ?", t["org_id"], v.id)
    cid = con.execute(f"INSERT INTO comments ({col}, user_id, as_org, body, created_at, reply_to) VALUES (?, ?, ?, ?, ?, ?)",
                      (tid, v.id, int(bool(as_org)), text, core.now(), to["id"] if to else None)).lastrowid
    if kind == "event":
        for (uid,) in (askers if lead else heads):
            notify(con, uid, "comment_answer", f"ca:{tid}:{cid}") if lead else notify(con, uid, "comment_question", f"cq:{tid}:{core.now() // 3600}")
    if to and to["user_id"] != v.id and (to["user_id"],) not in askers:  # its author hears it, replies in a thread merged by the hour
        notify(con, to["user_id"], "comment_reply", f"cr:{kind}:{tid}:{core.now() // 3600}")
    return comments(con, v, kind, tid)


def delete_comment(con, v: Viewer, cid: int) -> None:
    """Taken down, not erased (the reports keep pointing at something)."""
    c = one(con, "SELECT * FROM comments WHERE id = ? AND deleted_at IS NULL", cid)
    if not c:
        raise ApiError("not_found")
    org = one(con, "SELECT org_id FROM posts WHERE id = ?", c["post_id"]) if c["post_id"] else one(con, "SELECT org_id FROM events WHERE id = ?", c["event_id"])
    if c["user_id"] != v.id and not _moderates(con, v, org["org_id"]):
        raise ApiError("forbidden")
    con.execute("UPDATE comments SET deleted_at = ?, deleted_by = ? WHERE id = ?", (core.now(), v.id, cid))


def set_comments_on(con, v: Viewer, kind: str, tid: int, on: object) -> dict:
    t = _thread(con, v, kind, tid)
    if not _moderates(con, v, t["org_id"]):
        raise ApiError("forbidden")
    con.execute(f"UPDATE {'posts' if kind == 'post' else 'events'} SET comments_on = ? WHERE id = ?", (int(bool(on)), tid))
    return comments(con, v, kind, tid)


REPORT_NOTE = 500  # characters of "what's wrong", optional


def report(con, v: Viewer, target: object, tid: object, reason: object, note: object = None) -> None:
    """"Report" → the moderators' queue (one sheet for every thing: a reason and, if they like, a few words). One open
    report per person and thing: a repeat while it waits updates it, free; after a decision they may report again.
    20 new a day."""
    need_student(v)
    if target not in ("post", "comment", "event", "user", "photo", "ask", "thread", "reply") or reason not in ("spam", "insult", "danger", "other") \
            or not isinstance(tid, int) or isinstance(tid, bool) or not (note is None or isinstance(note, str)):
        raise ApiError("bad_input")
    note = (note or "").strip() or None
    if note and len(note) > REPORT_NOTE:
        raise ApiError("bad_input")
    if target == "photo":  # an album photo (its file id): hidden for me at once, for everyone once two people reported it
        p = one(con, "SELECT event_id, added_by FROM event_photos WHERE file_id = ?", tid)
        if not p or p["added_by"] == v.id:
            raise ApiError("not_found")
        _thread(con, v, "event", p["event_id"])
    elif target == "user":  # a profile: its nick, own photo and "about me"
        if tid == v.id or not one(con, "SELECT 1 FROM students WHERE user_id = ?", tid):
            raise ApiError("not_found")
    elif target == "ask":  # a forum request (forum.py): not my own, still up
        if not one(con, "SELECT 1 FROM asks WHERE id = ? AND status = 'live' AND user_id != ?", tid, v.id):
            raise ApiError("not_found")
    elif target in ("thread", "reply"):  # the student forum (threads.py): not my own, still up
        if not threads.reportable(con, v, target, tid):
            raise ApiError("not_found")
    elif target == "comment":
        c = one(con, "SELECT post_id, event_id, user_id FROM comments WHERE id = ? AND deleted_at IS NULL", tid)
        if not c or c["user_id"] == v.id:  # my own comment I delete, not report
            raise ApiError("not_found")
        _thread(con, v, "post" if c["post_id"] else "event", c["post_id"] or c["event_id"])
    else:
        _thread(con, v, target, tid)
    if con.execute("UPDATE reports SET reason = ?, note = COALESCE(?, note) WHERE reporter_id = ? AND target = ? AND target_id = ? AND status = 'open'",
                   (reason, note, v.id, target, tid)).rowcount:
        return
    if one(con, "SELECT COUNT(*) FROM reports WHERE reporter_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= REPORTS_A_DAY:
        raise ApiError("rate_limited")
    con.execute("INSERT OR IGNORE INTO reports (reporter_id, target, target_id, reason, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (v.id, target, tid, reason, note, core.now()))
    if target in ("thread", "reply"):
        threads.after_report(con, target, tid)


def _about(con, target: str, tid: int) -> int | None:
    """Whose the reported thing is: the person, a comment's author, a photo's uploader (a club's post or event: nobody's)."""
    r = (one(con, "SELECT ?", tid) if target == "user" else one(con, "SELECT user_id FROM comments WHERE id = ?", tid) if target == "comment"
         else one(con, "SELECT added_by FROM event_photos WHERE file_id = ?", tid) if target == "photo"
         else one(con, "SELECT user_id FROM asks WHERE id = ?", tid) if target == "ask" else None)
    if target in ("thread", "reply"):
        return threads.owner_of(con, target, tid)
    return r[0] if r else None


def report_queue(con, v: Viewer) -> list[dict]:
    """The admin's queue: one row per reported thing still up, the reasons counted, oldest first."""
    _mod(v)
    out = []
    for r in rows(con, """SELECT target, target_id, MIN(created_at) AS first, COUNT(*) AS n, GROUP_CONCAT(reason) AS reasons FROM reports
            WHERE status = 'open' GROUP BY target, target_id ORDER BY first"""):
        if r["target"] == "comment":
            c = one(con, "SELECT body, post_id, event_id FROM comments WHERE id = ? AND deleted_at IS NULL", r["target_id"])
            text, where = (c["body"], ("post", c["post_id"]) if c["post_id"] else ("event", c["event_id"])) if c else (None, None)
        elif r["target"] == "user":  # what the person wrote about themselves: the nick and "about me" (the photo shows on the card)
            p = one(con, PERSON + " WHERE u.id = ?", r["target_id"])
            text, where = (" · ".join(x for x in (shown_name(p), one(con, "SELECT bio FROM users WHERE id = ?", p["id"])[0]) if x),
                           ("person", r["target_id"])) if p else (None, None)
        elif r["target"] == "photo":  # the picture itself is the thing to look at
            p = one(con, "SELECT p.event_id, f.path FROM event_photos p JOIN files f ON f.id = p.file_id WHERE p.file_id = ?", r["target_id"])
            text, where = (f"media/{p['path']}.t.webp", ("event", p["event_id"])) if p else (None, None)
        elif r["target"] == "ask":  # a forum request: its words (forum.py hides it only with three reports and the AI, or here)
            a = one(con, "SELECT title, body FROM asks WHERE id = ? AND status IN ('live', 'held')", r["target_id"])
            text, where = (" · ".join(x for x in (a["title"], a["body"][:400]) if x), ("ask", r["target_id"])) if a else (None, None)
        elif r["target"] in ("thread", "reply"):  # the student forum: the words (never an anonymous writer's name)
            w = threads.words(con, r["target"], r["target_id"])
            text, where = (w[0], ("thread", w[1])) if w else (None, None)
        elif r["target"] == "post":
            # no post screen of its own to open: its words are the thing to judge, title and body
            p = one(con, "SELECT title, body FROM posts WHERE id = ? AND hidden_at IS NULL", r["target_id"])
            text, where = (" · ".join(x for x in (p["title"], (p["body"] or "")[:400]) if x), ("post", r["target_id"])) if p else (None, None)
        else:
            e = one(con, "SELECT title FROM events WHERE id = ? AND hidden_at IS NULL", r["target_id"])
            text, where = (e["title"], ("event", r["target_id"])) if e else (None, None)
        if _about(con, r["target"], r["target_id"]) == v.id:  # about me: another moderator decides (the notes could name the reporter)
            continue
        if text is None:  # already gone: nothing to decide
            con.execute("UPDATE reports SET status = 'actioned', resolved_at = ? WHERE target = ? AND target_id = ? AND status = 'open'", (core.now(), r["target"], r["target_id"]))
            continue
        reasons = r["reasons"].split(",")
        # what the reporters wrote, newest first, never who wrote it
        notes = [{"reason": n["reason"], "note": n["note"], "at": n["created_at"]} for n in rows(con, """SELECT reason, note, created_at FROM reports
            WHERE status = 'open' AND target = ? AND target_id = ? AND note IS NOT NULL ORDER BY created_at DESC, id DESC LIMIT 5""", r["target"], r["target_id"])]
        out.append({"target": r["target"], "id": r["target_id"], "text": text, "where": {"kind": where[0], "id": where[1]}, "count": r["n"],
                    "reasons": {k: reasons.count(k) for k in dict.fromkeys(reasons)}, "notes": notes, "at": r["first"]})
    return out


def resolve_report(con, v: Viewer, target: str, tid: int, remove: bool) -> list[str]:
    """Take the thing down (a comment deleted, a post or an event hidden, an album photo out, a profile's own words and
    photo gone) or leave it; either way its reports close. A photo and a profile's words are kept 30 days for an undo
    (takedowns: restore, purge_takedowns). Returns files to delete from disk (none now; kept for the route's shape)."""
    _mod(v)
    if _about(con, target, tid) == v.id:
        raise ApiError("forbidden")
    photos: list[str] = []
    if remove:
        if target == "comment":
            con.execute("UPDATE comments SET deleted_at = ?, deleted_by = ? WHERE id = ? AND deleted_at IS NULL", (core.now(), v.id, tid))
        elif target in ("post", "event"):
            con.execute(f"UPDATE {target}s SET hidden_at = ? WHERE id = ? AND hidden_at IS NULL", (core.now(), tid))
        elif target == "photo":  # out of the album; the row and the file kept 30 days for an undo (purge_takedowns)
            for p in rows(con, "DELETE FROM event_photos WHERE file_id = ? RETURNING *", tid):
                con.execute("INSERT INTO takedowns (target, target_id, user_id, data, file_id, at) VALUES ('photo', ?, ?, ?, ?, ?)",
                            (tid, p["added_by"], json.dumps(dict(p)), tid, core.now()))
        elif target == "ask":
            hide_ask(con, tid, "moderator", v.id)
        elif target in ("thread", "reply"):
            threads.take_down(con, target, tid)
        elif target == "user":  # the nick, the own photo and "about me" go, the Telegram photo is back; kept 30 days for an undo
            u = one(con, "SELECT nick, bio, avatar_tg, avatar_file_id FROM users WHERE id = ?", tid)
            if u and (u["nick"] or u["bio"] or u["avatar_file_id"]):
                con.execute("INSERT INTO takedowns (target, target_id, user_id, data, file_id, at) VALUES ('user', ?, ?, ?, ?, ?)",
                            (tid, tid, json.dumps(dict(u)), u["avatar_file_id"], core.now()))
            con.execute("UPDATE users SET nick = NULL, avatar_tg = 1, avatar_file_id = NULL, bio = '' WHERE id = ?", (tid,))
        else:
            raise ApiError("bad_input")
    elif target in ("thread", "reply"):  # left up: back if three reports had hidden it meanwhile
        threads.put_back(con, target, tid, reported_only=True)
    con.execute("UPDATE reports SET status = ?, resolved_by = ?, resolved_at = ? WHERE target = ? AND target_id = ? AND status = 'open'",
                ("actioned" if remove else "dismissed", v.id, core.now(), target, tid))
    log_action(con, v.id, "report_remove" if remove else "report_keep", f"{target}:{tid}")
    return photos


def taken_down(con, v: Viewer) -> list[dict]:
    """What the admin took down from the report queue in the last 30 days and is still down, newest first: a wrong call
    can be undone (§2 "hide / restore"). Things their own authors or clubs removed aren't here — that was their choice."""
    _mod(v)
    out = []
    for a in rows(con, """SELECT target, MAX(at) AS at FROM audit_log a WHERE action IN ('report_remove', 'thread_hide') AND at > ?
            AND NOT EXISTS (SELECT 1 FROM audit_log r WHERE r.action = 'restore' AND r.target = a.target AND r.at >= a.at)
            GROUP BY target ORDER BY MAX(at) DESC LIMIT 50""", core.now() - 30 * 86400):  # undone ones stay undone
        kind, _, ref = a["target"].partition(":")
        tid = int(ref) if ref.isdigit() else 0
        if kind == "comment":
            x = one(con, "SELECT body AS text FROM comments WHERE id = ? AND deleted_at IS NOT NULL", tid)
        elif kind in ("post", "event"):
            x = one(con, f"SELECT title AS text FROM {kind}s WHERE id = ? AND hidden_at IS NOT NULL", tid)  # kind from the list above
        elif kind == "photo":  # the picture itself, as the queue showed it
            x = one(con, """SELECT 'media/' || f.path || '.t.webp' AS text FROM takedowns k JOIN files f ON f.id = k.file_id
                WHERE k.target = 'photo' AND k.target_id = ?""", tid)
        elif kind in ("thread", "reply"):
            w = threads.words(con, kind, tid, hidden=True)
            x = {"text": w[0]} if w else None
        elif kind == "user":  # what the person wrote about themselves
            k = one(con, "SELECT data FROM takedowns WHERE target = 'user' AND target_id = ? ORDER BY id DESC", tid)
            d = json.loads(k["data"]) if k else None
            x = {"text": " · ".join(t for t in (d["nick"], d["bio"]) if t) or "\u2014"} if d else None
        else:
            x = None
        if x:
            out.append({"target": kind, "id": tid, "text": x["text"], "at": a["at"]})
    return out


def restore(con, v: Viewer, target: str, tid: int) -> list[str]:
    """Undo a take-down: the comment, post or event is back as it was; an album photo back in its album; a profile's
    nick, photo and "about me" back where the person hasn't set new ones since (a kept photo not used then goes).
    Audited. Returns files to remove from disk."""
    _mod(v)
    gone: list[str] = []
    with tx(con):
        if target == "comment":
            n = con.execute("UPDATE comments SET deleted_at = NULL, deleted_by = NULL WHERE id = ? AND deleted_at IS NOT NULL", (tid,)).rowcount
        elif target in ("post", "event"):
            n = con.execute(f"UPDATE {target}s SET hidden_at = NULL WHERE id = ? AND hidden_at IS NOT NULL", (tid,)).rowcount
        elif target in ("thread", "reply"):
            n = threads.put_back(con, target, tid)
        elif target in ("photo", "user"):
            k = one(con, "DELETE FROM takedowns WHERE id = (SELECT MAX(id) FROM takedowns WHERE target = ? AND target_id = ?) RETURNING *", target, tid)
            n = 1 if k else 0
            d = json.loads(k["data"]) if k else {}
            if k and target == "photo" and one(con, "SELECT 1 FROM events WHERE id = ?", d["event_id"]):
                con.execute("INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by) VALUES (?, ?, ?, ?)",
                            (d["event_id"], d["file_id"], d["sort"], d["added_by"]))
            elif k and target == "user":
                con.execute("""UPDATE users SET nick = COALESCE(nick, ?), bio = CASE WHEN bio = '' THEN ? ELSE bio END,
                    avatar_file_id = COALESCE(avatar_file_id, ?), avatar_tg = CASE WHEN avatar_file_id IS NULL AND ? IS NOT NULL THEN 0 ELSE avatar_tg END
                    WHERE id = ?""", (d["nick"], d["bio"], d["avatar_file_id"], d["avatar_file_id"], tid))
            if k:
                gone = _drop_unused(con, k["file_id"])  # an event gone meanwhile, a new photo set since: the kept one isn't shown
        else:
            raise ApiError("bad_input")
        if not n:
            raise ApiError("not_found")
        log_action(con, v.id, "restore", f"{target}:{tid}")
    return gone


TAKEDOWN_KEEP = 30 * 86400


def purge_takedowns(con) -> list[str]:
    """Daily: what was taken down 30 days ago and not restored is gone for good, its files from disk too (returned)."""
    with tx(con):
        kept = [r[0] for r in rows(con, "DELETE FROM takedowns WHERE at <= ? RETURNING file_id", core.now() - TAKEDOWN_KEEP)]
        return [p for f in kept for p in _drop_unused(con, f)]


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import _drop_unused  # noqa: E402
from .clubs import org  # noqa: E402
from .forum import hide_ask  # noqa: E402
from .organizing import _asking  # noqa: E402
from .oversight import _mod  # noqa: E402
from .seats import _event, notify  # noqa: E402
from .teams import remove  # noqa: E402
from . import threads  # noqa: E402
