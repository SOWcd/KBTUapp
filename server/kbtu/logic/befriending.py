"""Friends (§4.7): requests, links, invites."""
from __future__ import annotations

import re
import secrets
import sqlite3

from ..db import tx

from .core import ApiError, NO_END, PERSON, PERSON_COLS, Viewer, need_student, one, rows


# ---------------------------------------------------------------- friends (§4.7)

FRIEND_ASKS_A_DAY = 20
REASK_AFTER = 30 * 86400    # a declined request looks pending to the asker this long, then they may ask again
LINK_TTL = 7 * 86400


def friendship(con, me: int, uid: int) -> str:
    """'friends' | 'requested' (mine, waiting; a quiet decline looks the same for 30 days) | 'incoming' | 'none'."""
    if one(con, "SELECT 1 FROM friendships WHERE a = ? AND b = ?", min(me, uid), max(me, uid)):
        return "friends"
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND (status = 'pending' OR (status = 'declined' AND decided_at > ?))",
           me, uid, core.now() - REASK_AFTER):
        return "requested"
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", uid, me):
        return "incoming"
    return "none"


def _student(con, uid: int | None) -> sqlite3.Row:
    p = one(con, PERSON + " WHERE u.id = ? AND s.user_id IS NOT NULL", uid) if uid else None
    if not p:
        raise ApiError("not_found")
    return p


def _befriend(con, a: int, b: int) -> None:
    """Friends from now on; requests between the two, either way, are settled by it. Each hears it from the bot
    except the one who made it happen (the caller notifies the other)."""
    con.execute("INSERT OR IGNORE INTO friendships (a, b, created_at) VALUES (?, ?, ?)", (min(a, b), max(a, b), core.now()))
    con.execute("""UPDATE friend_requests SET status = 'accepted', decided_at = ? WHERE status = 'pending'
        AND ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))""", (core.now(), a, b, b, a))


def _friend_row(p: sqlite3.Row, at: int, friend: bool = True) -> dict:
    """Full names only between friends (§3); a request shows the short one, with course and school like any card."""
    name = f"{p['first_name']} {p['last_name']}".strip() if friend else short_name(p)
    return {"person": person_ref(p), "fullName": name, "course": p["course"], "school": p["school"], "at": at}


def friends(con, v: Viewer) -> dict:
    """The Friends page: friends (full names, §3), requests both ways, and the coming events friends go to (only
    those who let friends see it; the card lists them)."""
    need_student(v)
    cols = PERSON_COLS + ", s.course, s.school"
    mine = [_friend_row(p, p["since"]) for p in rows(con, f"""SELECT {cols}, f.created_at AS since FROM friendships f
        JOIN users u ON u.id = CASE WHEN f.a = ? THEN f.b ELSE f.a END JOIN students s ON s.user_id = u.id
        WHERE f.a = ? OR f.b = ? ORDER BY s.first_name, s.last_name""", v.id, v.id, v.id)]
    incoming = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.from_id JOIN students s ON s.user_id = u.id
        WHERE r.to_id = ? AND r.status = 'pending' ORDER BY r.created_at DESC""", v.id)]
    outgoing = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.to_id JOIN students s ON s.user_id = u.id
        WHERE r.from_id = ? AND (r.status = 'pending' OR (r.status = 'declined' AND r.decided_at > ?)) ORDER BY r.created_at DESC""",
        v.id, core.now() - REASK_AFTER)]
    roles = _roles(con, v)
    going = [e for e in rows(con, f"""SELECT DISTINCT e.* FROM registrations r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
        WHERE r.status = 'going' AND u.show_going = 1 AND e.status = 'published' AND COALESCE(e.ends_at, e.starts_at + {NO_END}) > ?
        AND r.user_id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)
        ORDER BY e.starts_at LIMIT 30""", core.now(), v.id, v.id) if _visible(con, v, e, roles)]
    return {"friends": mine, "incoming": incoming, "outgoing": outgoing, "going": cards(con, v, going)}


def find_student(con, v: Viewer, username: str) -> dict:
    """A student by Telegram @username (public in Telegram anyway, §4.7), with where the two of us stand."""
    need_student(v)
    name = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ApiError("bad_input")
    u = one(con, "SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE lower(u.tg_username) = lower(?)", name)
    p = _student(con, u["id"] if u else None)
    s = one(con, "SELECT course, school FROM students WHERE user_id = ?", p["id"])
    return {"person": person_ref(p), "course": s["course"], "school": s["school"],
            "friendship": "none" if p["id"] == v.id else friendship(con, v.id, p["id"]), "me": p["id"] == v.id}


def ask_friend(con, v: Viewer, uid: int) -> dict:
    """Add friend: a request the other one answers; if they had asked me already, this is the answer (friends now).
    A request after a quiet decline changes nothing for 30 days and says nothing to anyone."""
    need_student(v)
    p = _student(con, uid)
    if uid == v.id:
        raise ApiError("bad_input")
    state = friendship(con, v.id, uid)
    if state == "incoming":
        with tx(con):
            _befriend(con, v.id, uid)
            notify(con, uid, "friend_new", f"fn:{v.id}:{core.now() // 86400}")
        state = "friends"
    elif state == "none":
        if one(con, "SELECT COUNT(*) FROM friend_requests WHERE from_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= FRIEND_ASKS_A_DAY:
            raise ApiError("rate_limited")
        with tx(con):
            con.execute("""INSERT INTO friend_requests (from_id, to_id, status, created_at) VALUES (?, ?, 'pending', ?)
                ON CONFLICT (from_id, to_id) DO UPDATE SET status = 'pending', created_at = excluded.created_at, decided_at = NULL""", (v.id, uid, core.now()))
            notify(con, uid, "friend_request", f"fq:{v.id}:{core.now() // 86400}")
        state = "requested"
    return {"person": person_ref(p), "friendship": state}


def answer_friend(con, v: Viewer, uid: int, accept: bool) -> dict:
    need_student(v)
    if not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", uid, v.id):
        raise ApiError("not_found")
    with tx(con):
        if accept:
            _befriend(con, v.id, uid)
            notify(con, uid, "friend_new", f"fn:{v.id}:{core.now() // 86400}")
        else:  # quietly: the asker keeps seeing "request sent" (§4.7)
            con.execute("UPDATE friend_requests SET status = 'declined', decided_at = ? WHERE from_id = ? AND to_id = ?", (core.now(), uid, v.id))
    return friends(con, v)


def take_back_request(con, v: Viewer, uid: int) -> None:
    """Cancel my waiting request (a quietly declined one stays: it still holds the 30 days)."""
    need_student(v)
    con.execute("DELETE FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", (v.id, uid))


def unfriend(con, v: Viewer, uid: int) -> None:
    """Quietly; either side, any time (§4.7)."""
    need_student(v)
    con.execute("DELETE FROM friendships WHERE a = ? AND b = ?", (min(uid, v.id), max(uid, v.id)))


def friend_link(con, v: Viewer) -> dict:
    """My live one-time link (§4.7): the same one until somebody uses it or it expires, then a fresh one (96 random bits)."""
    need_student(v)
    r = one(con, "SELECT token, expires_at FROM friend_links WHERE user_id = ? AND used_by IS NULL AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            v.id, core.now() + 3600)  # never hand out one that dies within the hour
    if r:
        return {"token": r["token"], "expiresAt": r["expires_at"]}
    token, until = secrets.token_hex(12), core.now() + LINK_TTL
    con.execute("INSERT INTO friend_links (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)", (token, v.id, core.now(), until))
    return {"token": token, "expiresAt": until}


def friend_link_used(con, v: Viewer, token: str) -> dict:
    """While my QR is on screen: who has just used it (the sheet celebrates and shows the next one)."""
    need_student(v)
    r = one(con, "SELECT used_by FROM friend_links WHERE token = ? AND user_id = ?", token, v.id)
    if not r:
        raise ApiError("not_found")
    return {"usedBy": person_ref(_student(con, r["used_by"])) if r["used_by"] else None}


def use_friend_link(con, v: Viewer, token: str) -> dict:
    """Someone opened my link: the first student becomes my friend at once; after that it's 'used' and they may ask
    the usual way. Results: friends | already | used | self."""
    need_student(v)
    r = one(con, "SELECT * FROM friend_links WHERE token = ?", token)
    if not r:
        raise ApiError("not_found")
    owner = _student(con, r["user_id"])
    out = {"person": person_ref(owner)}
    if r["user_id"] == v.id:
        return {**out, "result": "self"}
    if friendship(con, v.id, r["user_id"]) == "friends":
        return {**out, "result": "already"}
    with tx(con):  # one write lock: of two people opening it at once, one wins
        won = r["expires_at"] > core.now() and con.execute("UPDATE friend_links SET used_by = ?, used_at = ? WHERE token = ? AND used_by IS NULL",
                                                       (v.id, core.now(), token)).rowcount
        if won:
            _befriend(con, v.id, r["user_id"])
            notify(con, r["user_id"], "friend_new", f"fn:{v.id}:{core.now() // 86400}")
    return {**out, "result": "friends" if won else "used"}


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import me  # noqa: E402
from .seats import _visible, notify  # noqa: E402
from .shapes import _roles, cards, person_ref, short_name  # noqa: E402
