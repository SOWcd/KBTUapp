"""The Gallery (Afisha → Gallery): one feed of every photo a student may see, the events' albums and KBTU's own, newest
first (upload order). A verified student posts under their own name, published at once (GALLERY: unset off, staff the
admins and moderators, 1 everyone; off, the feed is the albums alone, as before). A photo of an event goes into its
album too, on the album's own rules (_album_room). Reports: moderation.py (gone for the reporter at once, for everyone
at PHOTO_HIDE people, until a moderator decides in Admin; a take-down is kept 30 days for an undo)."""
from __future__ import annotations

import json

from ..db import tx
from .core import ApiError, Viewer, media_shape, now, one, rows

MODE = ""                # app.create sets it from GALLERY: "all", "staff" or "" (off)
PAGE = 60
A_DAY = 30               # uploads one person starts in a day (attempts: deleting doesn't give any back)
TOPICS = ("campus", "study", "life", "other")  # what a photo of no event is about (gallery_photos.topic); "events": the feed's filter for the rest
ALBUMS = 60              # the albums the Gallery lists
MY_EVENTS = 5            # the events a photo may go to, offered in the picker's menu (the newest)


def on(v: Viewer) -> bool:
    """Posting, and KBTU's own photos in the feed, are for this person."""
    return v.student and (MODE == "all" or MODE == "staff" and v.role in ("admin", "moderator"))


def _shape(f, v: Viewer) -> dict:
    """A photo as the grid and the viewer show it (types.ts AlbumPhoto): who posted it as the album says it (nick or
    "First L."); a Gallery post also its author's profile; when it was posted (an album's photo: uploaded), for the
    feed's days, where the Gallery is on for me."""
    return {**media_shape(f), "canDelete": f["uid"] == v.id and on(v), "by": _photo_by(f), "mine": f["uid"] == v.id,
            **({"uid": f["poster"]} if f["poster"] else {}),
            **({"at": f["posted"] or f["created_at"]} if f["poster"] or on(v) else {}),  # the feed's days; off: no more than the album says
            **({"topic": f["topic"] or "other"} if f["poster"] and not f["event_id"] else {}),  # one posted before topics, or its event gone: other
            **({"event": {"id": f["event_id"], "title": f["title"],
                          **({"i18n": {k: {"title": x["title"]} for k, x in json.loads(f["i18n"]).items()}} if f["i18n"] else {})}}
               if f["event_id"] else {})}


def _open() -> str:
    """SQL: the event `e` of the club `o` shows its album in the Gallery (args: on_afisha_args, my id)."""
    return f"""e.status = 'published' AND e.hidden_at IS NULL AND e.visibility = 'public' AND e.meeting = 0 AND o.status != 'hidden'
            AND {on_afisha()} AND (e.first_year = 0 OR (SELECT hide_first_year FROM users WHERE id = ?) = 0)"""


def albums(con, v: Viewer) -> list[dict]:
    """The events' albums the feed draws from, the one with the newest photo first: its cover (the event's own, else its
    newest photo), its day and how many photos I see in it, in one query for all rows."""
    # ponytail: the ALBUMS newest, all at once (the shelf and "All"); page it when there are more albums than that
    found = rows(con, f"""WITH a AS (
            SELECT e.id AS eid, e.title, e.i18n, e.starts_at, e.cover_file_id, e.cover_focus, COUNT(*) AS n, MAX(f.id) AS newest
            FROM event_photos p JOIN files f ON f.id = p.file_id JOIN events e ON e.id = p.event_id JOIN orgs o ON o.id = e.org_id
            WHERE {_open()} AND {PHOTO_SHOWN} GROUP BY e.id)
        SELECT a.eid, a.title, a.i18n, a.starts_at, a.n, a.cover_file_id, a.cover_focus, c.* FROM a JOIN files c ON c.id = COALESCE(a.cover_file_id, a.newest)
        ORDER BY a.newest DESC LIMIT ?""", *on_afisha_args(v), v.id, v.id, ALBUMS)
    return [{"id": a["eid"], "title": a["title"], "n": a["n"], "at": a["starts_at"],
             "cover": {**media_shape(a), "focus": [float(c) for c in a["cover_focus"].split(",")] if a["cover_file_id"] and a["cover_focus"] else None},
             **({"i18n": {k: {"title": x["title"]} for k, x in json.loads(a["i18n"]).items()}} if a["i18n"] else {})} for a in found]


def feed(con, v: Viewer, before: int | None = None, limit: int = PAGE, topic: str | None = None) -> dict:
    """A page, newest first (a file id is the page mark), in one query for all rows. An album's photo only from what is
    open to every student and on their general afisha (stricter than _visible on purpose, for the staff and a club's
    own people too); a file in two albums once, in the newer. The first page of everything also has the albums (albums) and
    says where I may post. topic: one of TOPICS (photos of no event about it) or
    "events" (the albums alone)."""
    if topic is not None and topic not in TOPICS + ("events",):
        raise ApiError("bad_input", "topic")
    if not v.student:
        return {"photos": [], "more": False}  # as the album: people's faces
    n = max(1, min(limit, PAGE))
    found = rows(con, f"""WITH x AS (
            SELECT p.file_id, MAX(p.event_id) AS event_id, p.added_by AS uid
            FROM event_photos p JOIN events e ON e.id = p.event_id JOIN orgs o ON o.id = e.org_id
            WHERE {_open()} AND ?
            GROUP BY p.file_id
            UNION ALL
            SELECT g.file_id, NULL, g.user_id FROM gallery_photos g
            WHERE ? AND g.event_id IS NULL AND COALESCE(g.topic, 'other') = COALESCE(?, g.topic, 'other') AND NOT EXISTS (SELECT 1 FROM event_photos WHERE file_id = g.file_id))
        SELECT f.*, x.event_id, x.uid, g.user_id AS poster, g.created_at AS posted, g.topic, e.title, e.i18n, s.first_name, s.last_name, u.nick
        FROM x JOIN files f ON f.id = x.file_id LEFT JOIN gallery_photos g ON g.file_id = f.id LEFT JOIN events e ON e.id = x.event_id
        LEFT JOIN users u ON u.id = x.uid LEFT JOIN students s ON s.user_id = x.uid
        WHERE {PHOTO_SHOWN} AND f.id < ?
        ORDER BY f.id DESC LIMIT ?""", *on_afisha_args(v), v.id, int(topic in (None, "events")),
                 int(on(v) and topic != "events"), topic, v.id, before if before is not None else 1 << 62, n + 1)
    out = {"photos": [_shape(f, v) for f in found[:n]], "more": len(found) > n}
    if before is None and topic is None:
        out["albums"] = albums(con, v)
    if before is None and on(v):
        out["post"] = {"events": my_events(con, v)}
    return out


def my_events(con, v: Viewer) -> list[dict]:
    """The events my photo may go to: their albums take one from me now (_album_room: I came or I'm the team, from
    the start to a week after the end, my share not used up)."""
    # ponytail: _album_room per candidate (a few queries each, MY_EVENTS * 2 candidates at most); one query if it grows
    found = rows(con, """SELECT e.* FROM events e WHERE e.status = 'published' AND e.hidden_at IS NULL AND e.starts_at <= ? AND e.starts_at > ?
        AND (e.id IN (SELECT event_id FROM registrations WHERE user_id = ? AND checked_in_at IS NOT NULL)
             OR e.org_id IN (SELECT org_id FROM org_members WHERE user_id = ?))
        ORDER BY e.starts_at DESC LIMIT ?""", now(), now() - 60 * 86400, v.id, v.id, MY_EVENTS * 2)
    return [{"id": e["id"], "title": e["title"]} for e in found if _album_room(con, v, e) > 0][:MY_EVENTS]


def _day_key(v: Viewer) -> str:
    return f"gal:{v.id}:{now() // 86400}"


def check(con, v: Viewer, eid: int | None = None, topic: str | None = None) -> None:
    """May I post to the Gallery (to this event's album, or about this topic)? Asked before the upload is decoded, and
    again as it is saved. A photo of no event says its topic (none yet from an old bundle); an event's never does."""
    if not on(v):
        raise ApiError("not_found")
    # ponytail: until 2026-11-25, then require: an old web bundle posts with neither (saved as topic NULL, reads as other)
    if topic is not None and (eid is not None or topic not in TOPICS):  # never both
        raise ApiError("bad_input", "topic")
    if eid is not None and _album_room(con, v, _event(con, v, eid)) <= 0:
        raise ApiError("forbidden")


def attempt(con, v: Viewer, eid: int | None = None, topic: str | None = None) -> None:
    """One more upload today, counted before the work (a deleted photo or a refused one still counts: a person can't
    keep the picture workers busy for everyone, receipts included)."""
    with tx(con):
        check(con, v, eid, topic)
        k = _day_key(v)
        if int((one(con, "SELECT value FROM meta WHERE key = ?", k) or ["0"])[0]) >= A_DAY:
            raise ApiError("rate_limited", "gallery")
        con.execute("DELETE FROM meta WHERE key LIKE ? AND key != ?", (f"gal:{v.id}:%", k))  # yesterday's count
        con.execute("INSERT INTO meta (key, value) VALUES (?, '1') ON CONFLICT (key) DO UPDATE SET value = CAST(value AS INTEGER) + 1", (k,))


def post(con, v: Viewer, saved: dict, eid: int | None = None, topic: str | None = None) -> dict:
    """A processed upload (media.save) into the Gallery under my name, and into the event's album when given; of no
    event, about a topic."""
    with tx(con):
        check(con, v, eid, topic)
        f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'event_photo' AND owner_id = ?", saved["sha256"], v.id)
        fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                         saved["path"], v.id, now(), saved["color"])).lastrowid
        if con.execute("INSERT OR IGNORE INTO gallery_photos (file_id, user_id, event_id, created_at, topic) VALUES (?, ?, ?, ?, ?)",
                       (fid, v.id, eid, now(), topic)).rowcount and eid is not None:  # the same photo again: the one I posted
            con.execute("""INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by)
                VALUES (?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM event_photos WHERE event_id = ?), ?)""", (eid, fid, eid, v.id))
    f = one(con, """SELECT f.*, g.user_id AS uid, g.user_id AS poster, g.created_at AS posted, g.topic, g.event_id, e.title, e.i18n, s.first_name, s.last_name, u.nick
        FROM gallery_photos g JOIN files f ON f.id = g.file_id LEFT JOIN events e ON e.id = g.event_id
        LEFT JOIN users u ON u.id = g.user_id LEFT JOIN students s ON s.user_id = g.user_id WHERE g.file_id = ?""", fid)
    return _shape(f, v)


def delete_mine(con, v: Viewer, fid: int) -> list[str]:
    """My photo out of the Gallery and the albums I put it in; its files go from the disk (returned)."""
    if not on(v):
        raise ApiError("not_found")
    with tx(con):
        n = con.execute("DELETE FROM gallery_photos WHERE file_id = ? AND user_id = ?", (fid, v.id)).rowcount
        n += con.execute("DELETE FROM event_photos WHERE file_id = ? AND added_by = ?", (fid, v.id)).rowcount
        if not n:
            raise ApiError("not_found")
        return _drop_unused(con, fid)


def take_down(con, fid: int) -> bool:
    """A moderator's Delete of a Gallery post: out of the feed and its album, kept 30 days for an undo (takedowns,
    purge_takedowns) like an album photo; joins the caller's tx. False: not a Gallery post."""
    g = one(con, "DELETE FROM gallery_photos WHERE file_id = ? RETURNING *", fid)
    if not g:
        return False
    g = {**dict(g), "open": bool(g["event_id"] and _was_open(con, g["event_id"]))}  # for restore, should its event go meanwhile
    albums = [dict(p) for p in rows(con, "DELETE FROM event_photos WHERE file_id = ? RETURNING *", fid)]
    con.execute("INSERT INTO takedowns (target, target_id, user_id, data, file_id, at) VALUES ('photo', ?, ?, ?, ?, ?)",
                (fid, g["user_id"], json.dumps({"gallery": g, "albums": albums}), fid, now()))
    return True


def _was_open(con, eid: int) -> bool:
    """The event's album was open to every student whoever they are (public, not a meeting, its club on the afisha by
    itself): only such an event's Gallery posts may outlive the album as plain KBTU photos."""
    return bool(one(con, f"""SELECT 1 FROM events e JOIN orgs o ON o.id = e.org_id
        WHERE e.id = ? AND e.visibility = 'public' AND e.meeting = 0 AND {afisha_ok('o')}""", eid))


def album_gone(con, eid: int, fid: int | None = None) -> list[int]:
    """An event is about to be deleted (or one photo leaves its album: fid): a closed event's Gallery posts go with it,
    never into everyone's feed (their files: the caller drops them); an open one's stay, plain. Joins the caller's tx."""
    if _was_open(con, eid):
        con.execute("UPDATE gallery_photos SET event_id = NULL WHERE event_id = ? AND file_id = COALESCE(?, file_id)", (eid, fid))
        return []
    return [r[0] for r in rows(con, "DELETE FROM gallery_photos WHERE event_id = ? AND file_id = COALESCE(?, file_id) RETURNING file_id", eid, fid)]


def restore(con, d: dict) -> None:
    """take_down undone: the post back, in the albums still there. Its event gone meanwhile: a plain KBTU photo if that
    event was open to every student, else it stays gone (the caller drops the file)."""
    g = d["gallery"]
    eid = g["event_id"] if g["event_id"] and one(con, "SELECT 1 FROM events WHERE id = ?", g["event_id"]) else None
    if g["event_id"] and not eid and not g.get("open"):
        return
    con.execute("INSERT OR IGNORE INTO gallery_photos (file_id, user_id, event_id, created_at, topic) VALUES (?, ?, ?, ?, ?)",
                (g["file_id"], g["user_id"], eid, g["created_at"], g.get("topic")))  # taken down before topics: none
    for p in d["albums"]:
        if one(con, "SELECT 1 FROM events WHERE id = ?", p["event_id"]):
            con.execute("INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by) VALUES (?, ?, ?, ?)",
                        (p["event_id"], p["file_id"], p["sort"], p["added_by"]))


def mine_gone(con, uid: int) -> list[int]:
    """Deleting an account: my Gallery posts out of the feed and the albums (their files: the caller drops them)."""
    con.execute("DELETE FROM meta WHERE key LIKE ?", (f"gal:{uid}:%",))
    fids = [r[0] for r in rows(con, "DELETE FROM gallery_photos WHERE user_id = ? RETURNING file_id", uid)]
    for fid in fids:
        con.execute("DELETE FROM event_photos WHERE file_id = ?", (fid,))
    return fids


from .account import _drop_unused  # noqa: E402
from .organizing import PHOTO_SHOWN, _album_room, _photo_by  # noqa: E402
from .seats import _event, afisha_ok, on_afisha, on_afisha_args  # noqa: E402
