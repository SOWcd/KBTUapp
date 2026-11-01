"""The forum channel (owner, Nov 1: replaces the in-app student forum). A Microsoft-verified student writes a post in
the app, under their name or anonymously; the bot publishes it in the public channel (FORUM_CHANNEL), where the
comments happen in its Telegram discussion group (tgc.py). One post a day per student. The AI looks first: its exact
OK publishes at once (the bot's next round, seconds); anything else, or an anonymous post aimed at a person, waits for
a moderator. Plain text only: no links, @mentions or phone numbers (the bot is the publisher, nobody pings or doxes
through it). The author deletes, a moderator takes down, a deleted account's posts leave too: all through tg_unpost,
which keeps only the channel's message id. Only the owner reveals an anonymous author, each look in the audit log."""
from __future__ import annotations

import re

from ..db import tx

from .core import ApiError, PERSON, Viewer, log_action, need_student, one, person_ref, rows, short_name

BODY_MAX = 1000
POSTS_A_DAY = 1
CHANNEL_AN_HOUR = 20     # live posts in the channel an hour; past it, a moderator lets the next ones out (a burst can't flood it)
MOD_RECENT = 7 * 86400   # live posts the moderators' list shows, to take one down
# what Telegram turns into a link or a ping even in plain text: a scheme, www., a domain, an e-mail, @handle, a phone
# (+..., a Kazakh 8/7 7xx number in any spacing, ten digits in a row). ponytail: any "word.letters" counts as a domain
# ("node.js" too), since Telegram knows every TLD; a TLD list if students trip on it
LINKY = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://|\bwww\.|\b[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}\b|@\w{3,}|\+\d[\d\s().-]{7,}\d"
                   r"|\b[78][\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b|\b\d{10,}\b)")
INVISIBLE = re.compile("[­؜᠎​-‏‪-‮⁠-⁤⁦-⁯﻿]")  # zero-width and direction marks


def _clean(raw: object) -> str:
    """The words as published: invisible characters out (they'd hide a link from the check), lines trimmed."""
    s = INVISIBLE.sub("", str(raw or ""))
    s = "\n".join(line.rstrip() for line in s.strip().splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s)
    if not 2 <= len(s) <= BODY_MAX:
        raise ApiError("bad_input")
    if LINKY.search(s):
        raise ApiError("bad_input", "links")
    return s


def _shape(p) -> dict:
    return {"id": p["id"], "body": p["body"], "anon": bool(p["anon"]), "status": p["status"], "at": p["created_at"]}


def mine(con, v: Viewer) -> list[dict]:
    """My posts, newest first: published, under review, removed (the ones I deleted are gone)."""
    need_student(v)
    return [_shape(p) for p in rows(con, "SELECT * FROM fchan_posts WHERE user_id = ? AND status != 'gone' ORDER BY id DESC LIMIT 30", v.id)]


def reserve(con, v: Viewer, body: dict) -> int:
    """A new post, held ('check') before the AI is asked, the day's allowance counted in the same transaction (posts
    sent at the same moment can't all pass it, nor all cost the AI a look). settle() puts the verdict on it."""
    need_student(v)
    anon = body.get("anon", False)
    if not isinstance(anon, bool):
        raise ApiError("bad_input")
    text = _clean(body.get("body"))
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM fchan_posts WHERE user_id = ? AND created_at > ?", v.id, _now() - 86400)[0] >= POSTS_A_DAY:
            raise ApiError("rate_limited", "posts")
        return con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, ?, ?, 'held', 'check', ?)",
                           (v.id, text, int(anon), _now())).lastrowid


def settle(con, v: Viewer, pid: int, verdict: str | None) -> dict:
    """The AI's word on a reserved post (untouched meanwhile): 'ok' goes live (the bot's round sends it), as does a named
    'person'; an anonymous 'person', a 'flag' or no answer wait for a moderator, and so does anything past the hour's cap."""
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND status = 'held' AND why = 'check'", pid)
        if p:
            if verdict == "ok" or verdict == "person" and not p["anon"]:
                busy = one(con, "SELECT COUNT(*) FROM fchan_posts WHERE status = 'live' AND created_at > ?", _now() - 3600)[0] >= CHANNEL_AN_HOUR
                status, why = ("held", "busy") if busy else ("live", None)
            else:
                status, why = "held", {"person": "person", "flag": "ai"}.get(verdict or "", "check")
            con.execute("UPDATE fchan_posts SET status = ?, why = ? WHERE id = ?", (status, why, pid))
    return _shape(one(con, "SELECT * FROM fchan_posts WHERE id = ?", pid))


def _unpost(con, p, why: str) -> None:
    """Its channel message (if it went out) to the bot's round: deleted there, or edited to a template."""
    if p["tg_msg"]:
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, ?, ?)", (p["tg_msg"], why, _now()))


def delete(con, v: Viewer, pid: int) -> None:
    """The author takes it down: the words wiped at once, the channel message after it; a wordless row stays for the
    day's count (deleting can't buy another post)."""
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND user_id = ? AND status != 'gone'", pid, v.id)
        if not p:
            raise ApiError("not_found")
        _unpost(con, p, "author")
        con.execute("UPDATE fchan_posts SET status = 'gone', body = '', why = NULL, tg_msg = NULL WHERE id = ?", (pid,))


def unpost_account(con, uid: int) -> None:
    """A deleted account's published posts leave the channel (account.delete_me, before the rows cascade away)."""
    con.execute("""INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) SELECT tg_msg, 'author', ? FROM fchan_posts
        WHERE user_id = ? AND tg_msg IS NOT NULL""", (_now(), uid))


# ---- the bot's side (tgc.py): what to send, what was sent, what to take down

def to_send(con) -> list:
    """Live posts not in the channel yet, oldest first, with their signature: the name (first name, last initial,
    never a nick or @username) or nothing for an anonymous one."""
    out = []
    for p in rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND tg_msg IS NULL ORDER BY id LIMIT 5"):
        who = None if p["anon"] else one(con, PERSON + " WHERE u.id = ?", p["user_id"])
        out.append((p["id"], p["body"], short_name(who) if who else None))
    return out


def sent(con, pid: int, msg_id: int) -> None:
    """The bot sent it: its message id kept; deleted or taken down meanwhile, the message goes right back out."""
    if not con.execute("UPDATE fchan_posts SET tg_msg = ? WHERE id = ? AND status = 'live' AND tg_msg IS NULL", (msg_id, pid)).rowcount:
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, 'author', ?)", (msg_id, _now()))


def sweep(con) -> None:
    """What the privacy policy promises: a deleted post's wordless row after its day, a taken-down one after 30 days."""
    con.execute("DELETE FROM fchan_posts WHERE status = 'gone' AND created_at < ? OR status = 'hidden' AND created_at < ?",
                (_now() - 86400, _now() - 30 * 86400))


def unposts(con) -> list:
    return rows(con, "SELECT msg_id, why FROM tg_unpost ORDER BY at LIMIT 20")


def unposted(con, msg_id: int) -> None:
    con.execute("DELETE FROM tg_unpost WHERE msg_id = ?", (msg_id,))


# ---- moderators: held posts, recent live ones; the owner's reveal

def mod_queue(con, v: Viewer) -> dict:
    """What waits (oldest first) and what went out this week (newest first, to take one down). Named posts show the
    author's name; anonymous ones show nobody, to moderators too."""
    _mod(v)
    # 'check' is also the AI's look under way (seconds): shown once it's clearly over (no answer, or the server restarted)
    held = rows(con, "SELECT * FROM fchan_posts WHERE status = 'held' AND (why != 'check' OR created_at < ?) ORDER BY id", _now() - 60)
    live = rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND created_at > ? ORDER BY id DESC LIMIT 50", _now() - MOD_RECENT)
    ids = {p["user_id"] for p in held + live if not p["anon"]}
    people = {p["id"]: person_ref(p) for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)} if ids else {}
    shape = lambda p: _shape(p) | {"why": p["why"], "author": None if p["anon"] else people.get(p["user_id"])}  # noqa: E731
    return {"held": [shape(p) for p in held], "live": [shape(p) for p in live]}


def mod_decide(con, v: Viewer, pid: int, ok: object) -> None:
    """A held post goes out (ok) or is removed; a live one can only be taken down (it leaves the channel)."""
    _mod(v)
    if not isinstance(ok, bool):
        raise ApiError("bad_input")
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND status IN ('held', 'live')", pid)
        if not p or p["status"] == "live" and ok:
            raise ApiError("not_found")
        if p["user_id"] == v.id:  # their own: another moderator decides
            raise ApiError("forbidden")
        if ok:
            con.execute("UPDATE fchan_posts SET status = 'live', why = NULL WHERE id = ?", (pid,))
        else:
            _unpost(con, p, "moderator")
            con.execute("UPDATE fchan_posts SET status = 'hidden', why = 'moderator', tg_msg = NULL WHERE id = ?", (pid,))
        log_action(con, v.id, "fchan_release" if ok else "fchan_hide", f"fchan:{pid}")


def reveal(con, v: Viewer, pid: int) -> dict:
    """The app's owner alone (the founder admin, not every admin) learns who wrote an anonymous post; the audit log,
    which only the owner reads, keeps every look."""
    if not _owner(con, v):
        raise ApiError("forbidden")
    p = one(con, "SELECT user_id, anon FROM fchan_posts WHERE id = ? AND status != 'gone'", pid)
    if not p or not p["anon"]:
        raise ApiError("not_found")
    log_action(con, v.id, "reveal_anon", f"fchan:{pid}")
    return person_ref(one(con, PERSON + " WHERE u.id = ?", p["user_id"]))


def _now() -> int:
    return core.now()


# the other domains', imported last: they import this one too
from . import core  # noqa: E402
from .oversight import _mod, _owner  # noqa: E402
