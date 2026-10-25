"""Videos (video.py): uploads in parts, the converter's queue."""
from __future__ import annotations

import sqlite3

from .. import video
from ..db import tx

from .core import ApiError, Viewer, one, rows


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
from .shapes import organizes  # noqa: E402
