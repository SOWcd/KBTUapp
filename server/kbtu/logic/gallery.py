"""The Gallery (Afisha → Gallery): one feed of every photo a student may see, the events' albums and KBTU's own, newest
first by when it was taken. A verified student posts under their own name, published at once (GALLERY: unset off,
staff the admins and moderators, 1 everyone; off, the feed is the albums alone). A photo of an event goes into its
album too, only from someone who signed up for it or came. Reports: moderation.py (gone for the reporter at once, for
everyone at PHOTO_HIDE people, until a moderator decides in Admin)."""
from __future__ import annotations

import json

from ..db import tx
from .core import ApiError, Viewer, media_shape, now, one, rows

MODE = ""                # app.create sets it from GALLERY: "all", "staff" or "" (off)
PAGE = 60
A_DAY = 30               # photos one person posts in 24 hours (spam)
MY_EVENTS = 5            # the events a photo may go to, offered in the picker's menu (the newest)
EPOCH = 946684800        # 2000-01-01: an EXIF date before it (or ahead of now) is a camera's unset clock


def on(v: Viewer) -> bool:
    """Posting, and KBTU's own photos in the feed, are for this person."""
    return v.student and (MODE == "all" or MODE == "staff" and v.role in ("admin", "moderator"))


def _shape(f, v: Viewer) -> dict:
    """A photo as the grid and the viewer show it (types.ts AlbumPhoto): who posted it as the album says it (nick or
    "First L."), their profile only for a Gallery post (posted under their name), when it was taken."""
    return {**media_shape(f), "canDelete": f["uid"] == v.id, "by": _photo_by(f), "mine": f["uid"] == v.id, "at": f["at"],
            **({"uid": f["poster"]} if f["poster"] else {}),
            **({"event": {"id": f["event_id"], "title": f["title"],
                          **({"i18n": {k: {"title": x["title"]} for k, x in json.loads(f["i18n"]).items()}} if f["i18n"] else {})}}
               if f["event_id"] else {})}


def feed(con, v: Viewer, before: int | None = None, limit: int = PAGE) -> dict:
    """A page, newest taken first (before: the last photo I have), in one query for all rows. An album's photo only
    from what is open to every student and on their general afisha (stricter than _visible on purpose, for the staff
    and a club's own people too); a file in two albums once, in the newer. The first page also says where I may post."""
    if not v.student:
        return {"photos": [], "more": False}  # as the album: people's faces
    n = max(1, min(limit, PAGE))
    mark = "1" if before is None else """(COALESCE(g.taken_at, f.created_at), f.id) < (COALESCE((SELECT taken_at FROM gallery_photos WHERE file_id = ?),
        (SELECT created_at FROM files WHERE id = ?), 0), ?)"""
    # ponytail: sorted on an expression across a UNION (no index), fine for thousands of photos; a taken_at column on
    # event_photos and two merged index scans if the Gallery grows past that
    found = rows(con, f"""WITH x AS (
            SELECT p.file_id, MAX(p.event_id) AS event_id, p.added_by AS uid
            FROM event_photos p JOIN events e ON e.id = p.event_id JOIN orgs o ON o.id = e.org_id
            WHERE e.status = 'published' AND e.hidden_at IS NULL AND e.visibility = 'public' AND e.meeting = 0 AND o.status != 'hidden'
            AND {on_afisha()} AND (e.first_year = 0 OR (SELECT hide_first_year FROM users WHERE id = ?) = 0)
            GROUP BY p.file_id
            UNION ALL
            SELECT g.file_id, NULL, g.user_id FROM gallery_photos g
            WHERE ? AND g.event_id IS NULL AND NOT EXISTS (SELECT 1 FROM event_photos WHERE file_id = g.file_id))
        SELECT f.*, x.event_id, x.uid, g.user_id AS poster, COALESCE(g.taken_at, f.created_at) AS at, e.title, e.i18n, s.first_name, s.last_name, u.nick
        FROM x JOIN files f ON f.id = x.file_id LEFT JOIN gallery_photos g ON g.file_id = f.id LEFT JOIN events e ON e.id = x.event_id
        LEFT JOIN users u ON u.id = x.uid LEFT JOIN students s ON s.user_id = x.uid
        WHERE {PHOTO_SHOWN} AND {mark}
        ORDER BY at DESC, f.id DESC LIMIT ?""", *on_afisha_args(v), v.id, int(on(v)), v.id, *([] if before is None else [before] * 3), n + 1)
    out = {"photos": [_shape(f, v) for f in found[:n]], "more": len(found) > n}
    if before is None and on(v):
        out["post"] = {"events": [{"id": e["id"], "title": e["title"]} for e in rows(con, f"{_MINE} ORDER BY e.starts_at DESC LIMIT ?", v.id, now(), ALBUM_MAX, MY_EVENTS)]}
    return out


# the events my photo may go to: I was signed up or came, it has begun, its album has room
_MINE = """SELECT e.id, e.title FROM registrations r JOIN events e ON e.id = r.event_id
    WHERE r.user_id = ? AND (r.status = 'going' OR r.checked_in_at IS NOT NULL) AND e.status = 'published' AND e.hidden_at IS NULL
    AND e.starts_at <= ? AND (SELECT COUNT(*) FROM event_photos WHERE event_id = e.id) < ?"""


def check(con, v: Viewer, eid: int | None = None) -> None:
    """May I post one more photo now (to this event)? Asked before the upload is decoded, and again as it is saved."""
    if not on(v):
        raise ApiError("not_found")
    if one(con, "SELECT COUNT(*) FROM gallery_photos WHERE user_id = ? AND created_at > ?", v.id, now() - 86400)[0] >= A_DAY:
        raise ApiError("rate_limited", "gallery")
    if eid is not None and not one(con, f"{_MINE} AND e.id = ?", v.id, now(), ALBUM_MAX, eid):
        raise ApiError("forbidden")


def post(con, v: Viewer, saved: dict, eid: int | None = None) -> dict:
    """A processed upload (media.save) into the Gallery under my name, and into the event's album when given."""
    t = now()
    taken = saved.get("taken") if isinstance(saved.get("taken"), int) and EPOCH <= saved["taken"] <= t + 86400 else t
    with tx(con):
        check(con, v, eid)
        f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'event_photo' AND owner_id = ?", saved["sha256"], v.id)
        fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                         saved["path"], v.id, t, saved["color"])).lastrowid
        if con.execute("INSERT OR IGNORE INTO gallery_photos (file_id, user_id, event_id, taken_at, created_at) VALUES (?, ?, ?, ?, ?)",
                       (fid, v.id, eid, taken, t)).rowcount and eid is not None:  # the same photo again: the one I posted
            con.execute("""INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by)
                VALUES (?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM event_photos WHERE event_id = ?), ?)""", (eid, fid, eid, v.id))
    f = one(con, """SELECT f.*, g.user_id AS uid, g.user_id AS poster, g.taken_at AS at, g.event_id, e.title, e.i18n, s.first_name, s.last_name, u.nick
        FROM gallery_photos g JOIN files f ON f.id = g.file_id LEFT JOIN events e ON e.id = g.event_id
        LEFT JOIN users u ON u.id = g.user_id LEFT JOIN students s ON s.user_id = g.user_id WHERE g.file_id = ?""", fid)
    return _shape(f, v)


def delete_mine(con, v: Viewer, fid: int) -> list[str]:
    """My photo out of the Gallery and the albums I put it in; its files go from the disk (returned)."""
    with tx(con):
        n = con.execute("DELETE FROM gallery_photos WHERE file_id = ? AND user_id = ?", (fid, v.id)).rowcount
        n += con.execute("DELETE FROM event_photos WHERE file_id = ? AND added_by = ?", (fid, v.id)).rowcount
        if not n:
            raise ApiError("not_found")
        return _drop_unused(con, fid)


def is_post(con, fid: int) -> bool:
    return one(con, "SELECT 1 FROM gallery_photos WHERE file_id = ?", fid) is not None


def erase(con, fid: int) -> list[str]:
    """A moderator's Delete of a Gallery post: gone from everywhere, its files too (returned); joins the caller's tx."""
    con.execute("DELETE FROM gallery_photos WHERE file_id = ?", (fid,))
    con.execute("DELETE FROM event_photos WHERE file_id = ?", (fid,))
    return _drop_unused(con, fid)


def mine_gone(con, uid: int) -> list[int]:
    """Deleting an account: my Gallery posts out of the feed and the albums (their files: the caller drops them)."""
    fids = [r[0] for r in rows(con, "DELETE FROM gallery_photos WHERE user_id = ? RETURNING file_id", uid)]
    for fid in fids:
        con.execute("DELETE FROM event_photos WHERE file_id = ?", (fid,))
        con.execute("DELETE FROM reports WHERE target = 'photo' AND target_id = ?", (fid,))
    return fids


from .account import _drop_unused  # noqa: E402
from .organizing import ALBUM_MAX, PHOTO_SHOWN, _photo_by  # noqa: E402
from .seats import on_afisha, on_afisha_args  # noqa: E402
