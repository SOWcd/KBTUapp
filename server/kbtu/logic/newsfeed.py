"""News: posts, the feed, reactions."""
from __future__ import annotations

import json
import re
import sqlite3

from ..db import tx

from .core import (FULL_TOOLS, ApiError, Viewer, _by_id, _may, _org, _qs, _rights, can, log_action, media_shape, need_student, one,
    org_ref, rows)


# ---------------------------------------------------------------- news

def post_shape(con, v: Viewer, p: sqlite3.Row) -> dict:
    return post_shapes(con, v, [p])[0]


def post_shapes(con, v: Viewer, found: list[sqlite3.Row]) -> list[dict]:
    """Posts (types.ts Post), counts and my marks read once for the whole list (News was 900 queries)."""
    if not found:
        return []
    ids = [p["id"] for p in found]
    q = _qs(ids)
    reactions = {(r[0], r[1]): r[2] for r in rows(con, f"SELECT post_id, kind, COUNT(*) FROM post_reactions WHERE post_id IN ({q}) GROUP BY post_id, kind", *ids)}
    mine = {(r[0], r[1]) for r in rows(con, f"SELECT post_id, kind FROM post_reactions WHERE user_id = ? AND post_id IN ({q})", v.id, *ids)}
    comments = dict(rows(con, f"SELECT post_id, COUNT(*) FROM comments WHERE post_id IN ({q}) AND deleted_at IS NULL GROUP BY post_id", *ids))
    read = {r[0] for r in rows(con, f"SELECT post_id FROM post_reads WHERE user_id = ? AND post_id IN ({q})", v.id, *ids)}
    rights, orgs = _rights(con, v), _by_id(con, "orgs", (p["org_id"] for p in found))
    files = _by_id(con, "files", [*(p["photo_file_id"] for p in found), *(o["logo_file_id"] for o in orgs.values())])
    return [{
        "id": p["id"], "org": org_ref(con, orgs[p["org_id"]], files), "audience": p["audience"], "title": p["title"], "body": p["body"],
        "tag": p["tag"], "photo": media_shape(files[p["photo_file_id"]]) if p["photo_file_id"] in files else None,
        "pinned": bool(p["pinned"]), "featured": bool(p["featured_until"] and p["featured_until"] > core.now()),
        # the club's own writers; the app's staff take a post down and feature one in Admin, not in the feed
        "canDelete": "posts" in rights.get(p["org_id"], ()) and not p["hidden_at"] and casting_state(p, core.now()) not in ("scheduled", "open"),  # a live casting is cancelled, not deleted
        # a channel's post (mirror.py) is edited in Telegram, and its reactions and comments live there
        "canEdit": "posts" in rights.get(p["org_id"], ()) and not p["tg_url"] and not p["hidden_at"], "editedAt": p["edited_at"], "tg": _tg_shape(p),
        "commentsOn": bool(p["comments_on"]),
        "comments": comments.get(p["id"], 0),
        "reactions": {k: reactions.get((p["id"], k), 0) for k in ("fire", "heart")}, "mine": {k: (p["id"], k) in mine for k in ("fire", "heart")},
        "read": p["id"] in read, "createdAt": p["created_at"],
        "casting": _casting_shape(p),
        **({"i18n": _tg_i18n(p)} if p["i18n"] else {}),  # a channel's post in the viewer's language (mirror.py)
    } for p in found]


def _tg_shape(p: sqlite3.Row) -> dict | None:
    from .. import mirror  # mirror.py imports this module
    return mirror.shape(p)


def _tg_i18n(p: sqlite3.Row) -> dict | None:
    from .. import mirror
    return mirror.i18n(p)


# who a club's post reaches outside its own page: an official org's everyone, a student initiative's its members and followers
_REACH = f"""(org_id IN (SELECT id FROM orgs WHERE {FULL_TOOLS}) OR org_id IN (SELECT org_id FROM subscriptions WHERE user_id = ?)
    OR org_id IN (SELECT org_id FROM org_members WHERE user_id = ?))"""


def posts(con, v: Viewer, scope: str) -> list[dict]:
    # the club's page is a casting's stable address: one its club deleted before the end reads "Cancelled" there till then
    # (the text is wiped, the time and place stay; hide_post marks it so); a moderator's takedown just goes
    live, args = ("(hidden_at IS NULL OR (casting_cancelled_at = hidden_at AND casting_to > ?))", [core.now()]) if scope.startswith("org:") else ("hidden_at IS NULL", [])
    sql = f"SELECT * FROM posts WHERE {live} AND org_id NOT IN (SELECT id FROM orgs WHERE status = 'hidden')"
    if scope == "clubs":  # broadcasts reach club members only
        if not v.student or not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id):
            return []
        sql += " AND audience = 'clubs'"
    else:
        sql += " AND audience = 'public'"
        if scope == "subs":
            sql += " AND (org_id IN (SELECT org_id FROM subscriptions WHERE user_id = ?) OR org_id IN (SELECT org_id FROM org_members WHERE user_id = ?))"
            args += [v.id, v.id]
        elif scope.startswith("org:"):
            sql += " AND org_id = ?"; args.append(int(scope[4:]))
        elif scope == "all":
            sql += f" AND (featured_until > ? OR {_REACH})"  # a featured post is for everyone
            args += [core.now(), v.id, v.id]
        else:
            raise ApiError("bad_input")
    return post_shapes(con, v, rows(con, sql + " ORDER BY pinned DESC, created_at DESC LIMIT 100", *args))


def casting_state(p: sqlite3.Row, now: int) -> str | None:
    """scheduled, open, ended or cancelled; None for an ordinary post. Computed, never stored (web lib/posts.ts: the same
    rule on the phone's clock, for the copy it holds)."""
    if p["casting_to"] is None:
        return None
    if p["casting_cancelled_at"] is not None:
        return "cancelled"
    return "ended" if now >= p["casting_to"] else "open" if now >= p["casting_from"] else "scheduled"


def _casting_shape(p: sqlite3.Row) -> dict | None:
    return None if p["casting_to"] is None else {
        "from": p["casting_from"], "to": p["casting_to"], "place": p["casting_place"], "cancelled": p["casting_cancelled_at"] is not None}


CASTING_DAYS, CASTING_AHEAD_DAYS = 14, 180  # a casting's longest run and how far ahead it can be announced


def _casting_input(c: object) -> tuple[int, int, str]:
    """(from, to, place) of the composer's casting; it must not be over already."""
    if not isinstance(c, dict):
        raise ApiError("bad_input")
    start, end, place = c.get("from"), c.get("to"), " ".join(str(c.get("place") or "").split())
    if type(start) is not int or type(end) is not int or not 2 <= len(place) <= 80 or not start < end <= start + CASTING_DAYS * 86400 \
            or not core.now() < end <= core.now() + CASTING_AHEAD_DAYS * 86400:
        raise ApiError("bad_input")
    return start, end, place


def castings(con, v: Viewer) -> list[dict]:
    """The Clubs tab's "Recruiting" strip: castings not over yet, soonest first, by the same rule for every viewer. A public
    post's reach; a club under CLUB_MIN isn't in the registry, so not here either, not even for its own people."""
    return post_shapes(con, v, rows(con, f"""SELECT * FROM posts WHERE hidden_at IS NULL AND audience = 'public'
        AND casting_to > ? AND casting_cancelled_at IS NULL AND {_REACH}
        AND org_id IN (SELECT id FROM orgs o WHERE status = 'active' AND kind NOT IN ('office','app')
            AND (kind != 'club' OR (SELECT COUNT(*) FROM org_members m WHERE m.org_id = o.id) >= ?))
        ORDER BY casting_from, id LIMIT 30""", core.now(), v.id, v.id, clubs.CLUB_MIN))


def cancel_casting(con, v: Viewer, pid: int) -> dict:
    """The club's writers call a casting off: the post stays, marked. Ended ones can't be; a second tap changes nothing."""
    need_student(v)
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL AND casting_to IS NOT NULL", pid)
    if not p:
        raise ApiError("not_found")
    _may(con, v, p["org_id"], "posts")
    if casting_state(p, core.now()) == "ended":
        raise ApiError("bad_input")
    con.execute("UPDATE posts SET casting_cancelled_at = ? WHERE id = ? AND casting_cancelled_at IS NULL AND hidden_at IS NULL", (core.now(), pid))
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


POST_TAGS = ("important", "recruiting", "results", "news")  # the composer's chips; the UI names them per language
_LINK = re.compile(r"(https?://|www\.|t\.me/)\S+", re.I)


def _worded(title: str) -> bool:
    """A title says something besides a link (owner, Nov 3: a post titled with a bare invite link): links go in the text,
    where the app turns them into a button."""
    return len(re.findall(r"\w", _LINK.sub("", title))) >= 2


def create_post(con, v: Viewer, oid: int, body: dict) -> dict:
    """A club's post (Head+, SPEC §4.10): public — its members and subscribers see it in News and on the club page; a
    broadcast org (DMP, KBTU App) may write to every member of every club instead (`clubs`), and the bot tells them.
    The photo is one of the caller's own uploads; one pinned post per club."""
    need_student(v)
    _may(con, v, oid, "posts")
    o = _org(con, oid)
    if not stories_open(con, o) and body.get("casting") is None:  # a casting is open to every club: it's how an initiative finds people
        raise ApiError("forbidden", "ascent")  # Studio's composer says which Ascent step opens them
    title, text = str(body.get("title") or "").strip(), str(body.get("body") or "").strip()
    tag, audience = body.get("tag"), body.get("audience") or "public"
    if title and not _worded(title):
        raise ApiError("bad_input", "link_title")
    if not 2 <= len(title) <= 120 or len(text) > 2000 or (tag is not None and tag not in POST_TAGS) \
            or audience not in ("public", "clubs") or (audience == "clubs" and not o["can_broadcast"]):
        raise ApiError("bad_input")
    if tag == "important":  # it messages the members, so Vice+ only
        _may(con, v, oid, "team")
    pic = None
    if body.get("photoId") is not None:
        try:
            pic = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", int(body["photoId"]), v.id)
        except (TypeError, ValueError):
            pic = None
        if not pic:
            raise ApiError("bad_input")
    pinned = body.get("pinned") is True
    start, end, place = _casting_input(body["casting"]) if body.get("casting") is not None else (None, None, None)
    with tx(con):
        if end is not None and one(con, "SELECT 1 FROM posts WHERE org_id = ? AND hidden_at IS NULL AND casting_cancelled_at IS NULL AND casting_to > ?", oid, core.now()):
            raise ApiError("conflict", "casting_live")  # one at a time: the strip's first place is no permanent pin
        if pinned:
            con.execute("UPDATE posts SET pinned = 0 WHERE org_id = ?", (oid,))
        pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, tag, photo_file_id, pinned, created_at, casting_from, casting_to, casting_place)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (oid, v.id, audience, title, text, tag, pic["id"] if pic else None, int(pinned), core.now(), start, end, place)).lastrowid
        con.execute("INSERT INTO post_reads (post_id, user_id, read_at) VALUES (?, ?, ?)", (pid, v.id, core.now()))
        if end is not None and audience == "public":  # its followers outside it hear it once, as for a round (casting.open_round)
            for (uid,) in rows(con, "SELECT user_id FROM subscriptions WHERE org_id = ? AND user_id NOT IN (SELECT user_id FROM org_members WHERE org_id = ?)", oid, oid):
                notify(con, uid, "casting_open", f"cst:{pid}")
        if audience == "clubs":  # every member of every club hears it (§7 broadcast), except the author
            for (uid,) in rows(con, "SELECT DISTINCT user_id FROM org_members WHERE user_id != ?", v.id):
                notify(con, uid, "broadcast", f"post:{pid}")
        elif tag == "important" and not one(con, """SELECT 1 FROM bot_outbox b JOIN posts p ON b.ref = 'post:' || p.id
                WHERE b.kind = 'important' AND p.org_id = ? AND p.created_at > ?""", oid, core.now() - 86400):
            # the club's members hear an "Important" post (not its followers), one a day per club at most: the only club post
            # the bot sends, so nobody mutes it
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND user_id != ?", oid, v.id):
                notify(con, uid, "important", f"post:{pid}")
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def update_post(con, v: Viewer, pid: int, body: dict) -> dict:
    """Edit a club's post or pin it (its Head+, §2): the title, text, label and photo as in the composer — then it
    reads "edited" — and the pin (one per club). Who sees it stays: a broadcast has already gone out."""
    need_student(v)
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid)
    if not p:
        raise ApiError("not_found")
    _may(con, v, p["org_id"], "posts")
    if p["tg_url"] and body.keys() - {"pinned"}:
        raise ApiError("bad_input")  # a channel's post is edited in Telegram; here it is only pinned
    bad, sets = object(), {}
    text = lambda k: str(body.get(k) or "").strip()  # noqa: E731
    if "title" in body:
        if text("title") and not _worded(text("title")):
            raise ApiError("bad_input", "link_title")
        sets["title"] = text("title") if 2 <= len(text("title")) <= 120 else bad
    if "body" in body:
        sets["body"] = text("body") if len(text("body")) <= 2000 else bad
    if "tag" in body:
        sets["tag"] = body["tag"] if body["tag"] is None or body["tag"] in POST_TAGS else bad
        if body["tag"] == "important" and p["tag"] != "important":  # Vice+, as when writing it; an edit messages nobody
            _may(con, v, p["org_id"], "team")
    if "photoId" in body and body["photoId"] != p["photo_file_id"]:  # the photo it has stays, whoever uploaded it
        ph = body["photoId"]
        own = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", ph, v.id) \
            if isinstance(ph, int) and not isinstance(ph, bool) else None
        sets["photo_file_id"] = None if ph is None else own["id"] if own else bad
    if "casting" in body:  # its time and place, while it's on; an ordinary post stays one
        if casting_state(p, core.now()) not in ("scheduled", "open"):
            raise ApiError("bad_input")
        sets["casting_from"], sets["casting_to"], sets["casting_place"] = _casting_input(body["casting"])
    if "pinned" in body:
        sets["pinned"] = int(body["pinned"]) if isinstance(body["pinned"], bool) else bad
    if not body or any(x is bad for x in sets.values()):
        raise ApiError("bad_input")
    if sets.keys() - {"pinned"}:
        sets["edited_at"] = core.now()
    with tx(con):  # checked again under the write lock: a delete meanwhile wiped it, and an edit mustn't refill it
        if not one(con, "SELECT 1 FROM posts WHERE id = ? AND hidden_at IS NULL", pid):
            raise ApiError("not_found")
        if sets.get("pinned"):
            con.execute("UPDATE posts SET pinned = 0 WHERE org_id = ? AND id != ?", (p["org_id"], pid))
        if sets:
            con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ? AND hidden_at IS NULL", (*sets.values(), pid))  # keys from above
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def hide_post(con, v: Viewer, pid: int) -> list[str]:
    """Take a post down (whoever has its club's posts right, or an admin or moderator). Its club's delete wipes it at once (wipe_post); an admin's or
    moderator's without the club's right only hides it (a moderation act, undone within 30 days; daily wipes it then).
    The row stays for reactions and the audit trail. Returns files to remove from disk."""
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid)
    if not p:
        raise ApiError("not_found")
    club = can(con, v, p["org_id"], "posts")
    if v.role not in ("admin", "moderator") and not club:
        raise ApiError("forbidden")
    with tx(con):
        at = core.now()
        # its club's delete of a casting not over yet is a cancellation (posts(): hidden_at matches it there)
        con.execute("UPDATE posts SET hidden_at = ?, casting_cancelled_at = CASE WHEN ? AND casting_to > ? THEN ? ELSE casting_cancelled_at END WHERE id = ?",
                    (at, bool(club), at, at, pid))
        log_action(con, v.id, "post_hide", f"post:{pid}")
        return wipe_post(con, pid) if club else []


def wipe_post(con, pid: int) -> list[str]:
    """A taken-down post erased: its text, translations and photo (the file too when nothing else shows it) and the
    comments under it. The row stays (reactions, the audit). Inside the caller's tx; returns files to remove from disk."""
    fid = one(con, "SELECT photo_file_id FROM posts WHERE id = ?", pid)[0]
    con.execute("UPDATE posts SET title = '', body = '', i18n = NULL, lang = NULL, tr_by = NULL, photo_file_id = NULL WHERE id = ?", (pid,))
    con.execute("DELETE FROM comments WHERE post_id = ?", (pid,))
    return _drop_unused(con, fid)


def read_posts(con, v: Viewer, ids: list) -> None:
    """Posts seen in News: their unread marks go, and the club tab's dot with them."""
    need_student(v)
    for pid in [i for i in ids if isinstance(i, int) and not isinstance(i, bool)][:100]:
        con.execute("INSERT OR IGNORE INTO post_reads (post_id, user_id, read_at) SELECT id, ?, ? FROM posts WHERE id = ?", (v.id, core.now(), pid))


def unread_broadcasts(con, v: Viewer) -> int:
    """Broadcasts of the last 30 days a club member hasn't opened yet (the dot on tab 2)."""
    if not v.student or not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id):
        return 0
    return one(con, """SELECT COUNT(*) FROM posts p WHERE p.audience = 'clubs' AND p.hidden_at IS NULL AND p.created_at > ?
        AND p.org_id NOT IN (SELECT id FROM orgs WHERE status = 'hidden')
        AND NOT EXISTS (SELECT 1 FROM post_reads r WHERE r.post_id = p.id AND r.user_id = ?)""", core.now() - 30 * 86400, v.id)[0]


def feature(con, v: Viewer, pid: object, days: object) -> dict:
    """A post for everyone on top of Events → List (the admin, §2; moderators only filter) for 1–14 days;
    0 takes it off. Public posts only: a broadcast to club members stays theirs. One at a time: featuring one ends the other."""
    _admin(v)
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid) if isinstance(pid, int) else None
    if not p or p["audience"] != "public" or not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 14:
        raise ApiError("bad_input")
    with tx(con):
        if days:
            con.execute("UPDATE posts SET featured_until = NULL WHERE featured_until IS NOT NULL AND id != ?", (pid,))
        con.execute("UPDATE posts SET featured_until = ? WHERE id = ?", (core.now() + days * 86400 if days else None, pid))
        log_action(con, v.id, "feature", f"post:{pid}", json.dumps({"days": days}))
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def react(con, v: Viewer, pid: int, kind: str, on: bool) -> dict:
    need_student(v)
    if kind not in ("fire", "heart"):
        raise ApiError("not_found")
    p = _thread(con, v, "post", pid)  # it answers with the post: only one the viewer may read
    if p["tg_url"]:
        raise ApiError("bad_input")  # a channel's post shows Telegram's reactions; a tap opens it there
    if on:
        con.execute("INSERT OR IGNORE INTO post_reactions (post_id, user_id, kind) VALUES (?, ?, ?)", (pid, v.id, kind))
    else:
        con.execute("DELETE FROM post_reactions WHERE post_id = ? AND user_id = ? AND kind = ?", (pid, v.id, kind))
    return post_shape(con, v, p)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import clubs, core  # noqa: E402
from .account import _drop_unused  # noqa: E402
from .clubs import orgs, stories_open  # noqa: E402
from .moderation import _thread, comments  # noqa: E402
from .oversight import _admin  # noqa: E402
from .seats import notify  # noqa: E402
