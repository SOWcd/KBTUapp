"""An org's main Telegram channel in its news (PLAN 86 part 2): what the userbot (userbot.py) saw,
written as the org's posts. Here only the database: the Telegram side hands over plain messages (Msg), so the rules
are tested without Telegram.

The source is the org's MAIN public channel with its Studio switch on (chats.main, chats.mirror); the userbot joins it
itself and leaves it when it stops being one. A post is a channel post (an album is one post): its text as typed (the
first line the title), its photo copied, a video or a file only as a link to the post; edits follow, a deletion takes
it down and wipes its text and photo; Telegram's views and reaction counts show instead of ours, and comments stay in Telegram. Nobody is notified
of a mirrored post. Nothing but the channel's own posts is kept."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import ai, media
from .logic import _drop_unused, now, one, photo_free, rows, tx

FIRST_TAKE = 5            # on a first link: at most the last 5 posts ...
FIRST_DAYS = 30           # ... of the last 30 days
COUNT_DAYS = 7            # views and reactions refreshed for the posts of the last week
TITLE, BODY = 120, 2000   # what an app post holds (logic.create_post)
FOLD_GAP = 1800           # the same announcement in another language: posted within half an hour (SITE posts kk/ru/en)
COMMENT_DAYS = 2          # how long the channel's own comments are looked at for a post's translations


@dataclass
class Msg:
    """A channel post as the userbot read it. photo: media.save's answer for its photo (saved by the caller); media:
    'video' or 'file' when it carries one the app only links to; reactions: [(emoji, count)], a custom emoji as '★'."""
    id: int
    date: int
    text: str = ""
    grouped: int | None = None
    photo: dict | None = None
    media: str | None = None
    views: int | None = None
    reactions: list[tuple[str, int]] | None = field(default=None)


def username(url: str) -> str | None:
    """A public chat's name from its t.me link; None for an invite link."""
    m = re.fullmatch(r"https://t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?", url or "")
    return m.group(1).lower() if m else None


def wanted(con) -> dict[str, int]:
    """The channels to mirror, by name: each active org's main public channel with the switch on. name -> org id."""
    out = {}
    for c in rows(con, """SELECT c.url, c.org_id FROM chats c JOIN orgs o ON o.id = c.org_id
            WHERE c.main = 1 AND c.mirror = 1 AND c.kind = 'channel' AND o.status = 'active' ORDER BY c.id"""):
        if name := username(c["url"]):
            out.setdefault(name, c["org_id"])
    return out


def has_channel(con, oid: int) -> bool:
    """The org's main chat is a public channel: one the userbot can mirror (admin channel-ask asks the rest for one)."""
    c = one(con, "SELECT kind, url FROM chats WHERE org_id = ? AND main = 1", oid)
    return bool(c and c["kind"] == "channel" and username(c["url"]))


def to_join(con) -> list[str]:
    have = {r[0] for r in rows(con, "SELECT username FROM tg_channels")}
    return [n for n in wanted(con) if n not in have]


def to_leave(con) -> list[tuple[int, str]]:
    """Channels the userbot joined that are no mirror any more (never one it didn't join itself)."""
    keep = wanted(con)
    return [(r["id"], r["username"]) for r in rows(con, "SELECT id, username FROM tg_channels ORDER BY id") if r["username"] not in keep]


def joined(con, channel: int, name: str) -> None:
    con.execute("INSERT INTO tg_channels (id, username, joined_at) VALUES (?, ?, ?) ON CONFLICT (id) DO UPDATE SET username = excluded.username",
                (channel, name.lower(), now()))


def left(con, channel: int) -> None:
    con.execute("DELETE FROM tg_channels WHERE id = ?", (channel,))


def source(con, channel: int) -> int | None:
    """The org a joined channel is mirrored into now; None: not (or no more) a mirror: its posts are let be."""
    c = one(con, "SELECT username FROM tg_channels WHERE id = ?", channel)
    return wanted(con).get(c["username"]) if c else None


def last(con, channel: int) -> int:
    """The newest post taken from the channel; 0 on a first link (then FIRST_TAKE of the last FIRST_DAYS)."""
    c = one(con, "SELECT last_msg FROM tg_channels WHERE id = ?", channel)
    return c["last_msg"] if c else 0


def _split(text: str, fallback: str) -> tuple[str, str]:
    """A post's title and text: its first line, the rest under it; a long first line is cut at a word and the whole
    text follows it, so nothing is lost; past what a post holds, the rest is a tap away in Telegram."""
    text = text.strip()
    if not text:
        return fallback[:TITLE], ""
    first, _, rest = text.partition("\n")
    first = first.strip()
    if len(first) <= TITLE:
        title, body = first, rest.strip()
    else:
        cut = first[:TITLE - 1].rsplit(" ", 1)[0] or first[:TITLE - 1]
        title, body = cut.rstrip(" ,.;:-") + "…", text
    if len(body) > BODY:
        body = body[:BODY - 1].rsplit(" ", 1)[0] + "…"
    return title or fallback[:TITLE], body


def _photo(con, saved: dict) -> int:
    """A copied photo's file row (one per picture: the same one twice is one file)."""
    if f := one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'post_photo' AND owner_id IS NULL", saved["sha256"]):
        return f["id"]
    return con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'post_photo', 'image/webp', ?, ?, ?, ?, NULL, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                         saved["path"], now(), saved.get("color"))).lastrowid


def _counts(m: Msg) -> dict:
    out = {}
    if m.views is not None:
        out["tg_views"] = m.views
    if m.reactions is not None:
        out["tg_reactions"] = json.dumps(sorted(([str(e)[:8], int(n)] for e, n in m.reactions if n > 0), key=lambda x: -x[1]), ensure_ascii=False)
    return out


def needs_photo(con, channel: int, m_id: int, grouped: int | None) -> bool:
    """Whether a message's photo is worth downloading: a new post, or one (or its album) without a photo yet."""
    p = one(con, """SELECT p.photo_file_id FROM tg_post_msgs t JOIN posts p ON p.id = t.post_id
        WHERE t.channel = ? AND (t.msg_id = ? OR (? IS NOT NULL AND t.grouped = ?)) LIMIT 1""", channel, m_id, grouped, grouped)
    return not p or p["photo_file_id"] is None


def take(con, channel: int, m: Msg) -> int | None:
    """A new channel post, an edit of one, or one more piece of an album: the org's post for it (a post without text
    is titled by the channel). The post's id; None when the channel is no mirror now."""
    oid = source(con, channel)
    if oid is None:
        return None
    name = one(con, "SELECT username FROM tg_channels WHERE id = ?", channel)["username"]
    title = (one(con, "SELECT title FROM chats WHERE org_id = ? AND main = 1", oid) or {"title": name})["title"]
    with tx(con):
        had = one(con, "SELECT post_id, lang FROM tg_post_msgs WHERE channel = ? AND msg_id = ?", channel, m.id)
        album = one(con, "SELECT post_id FROM tg_post_msgs WHERE channel = ? AND grouped = ?", channel, m.grouped) if m.grouped and not had else None
        pid = (had or album)["post_id"] if (had or album) else None
        lang = ai.lang_of(m.text) if m.text.strip() else None
        if had and had["lang"]:  # a translation folded into another post: its edit is that language's text
            if m.text.strip():
                _set_tr(con, pid, had["lang"], _split(m.text, title))
            _counted(con, channel, pid, m)
            return pid
        if pid is None and lang and (into := _fold_target(con, channel, m.date, lang)):
            # the same announcement in another language: one post, this text as its translation
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped, lang) VALUES (?, ?, ?, ?, ?)", (channel, m.id, into, m.grouped, lang))
            _set_tr(con, into, lang, _split(m.text, title))
            if m.photo and not one(con, "SELECT photo_file_id FROM posts WHERE id = ?", into)["photo_file_id"]:
                con.execute("UPDATE posts SET photo_file_id = ? WHERE id = ?", (_photo(con, m.photo), into))
            _counted(con, channel, into, m)
            return into
        if album and lang and not one(con, "SELECT 1 FROM posts WHERE id = ? AND body != ''", pid) and _untitled(con, pid, title) \
                and (into := _fold_target(con, channel, m.date, lang, but=pid)):
            # an album's caption came after its photos: the whole album is a translation of an earlier post
            con.execute("UPDATE tg_post_msgs SET post_id = ?, lang = ? WHERE post_id = ?", (into, lang, pid))
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped, lang) VALUES (?, ?, ?, ?, ?)", (channel, m.id, into, m.grouped, lang))
            gone_photo = one(con, "SELECT photo_file_id FROM posts WHERE id = ?", pid)["photo_file_id"]
            if gone_photo and not one(con, "SELECT photo_file_id FROM posts WHERE id = ?", into)["photo_file_id"]:
                con.execute("UPDATE posts SET photo_file_id = ? WHERE id = ?", (gone_photo, into))
            con.execute("DELETE FROM posts WHERE id = ?", (pid,))  # made a moment ago, nobody saw it yet
            _set_tr(con, into, lang, _split(m.text, title))
            _counted(con, channel, into, m)
            return into
        if pid is None:
            t, b = _split(m.text, title)
            pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, photo_file_id, comments_on, created_at,
                    tg_channel, tg_url, tg_media) VALUES (?, NULL, 'public', ?, ?, ?, 0, ?, ?, ?, ?)""",
                              (oid, t, b, _photo(con, m.photo) if m.photo else None, m.date, channel, f"https://t.me/{name}/{m.id}", m.media)).lastrowid
        else:
            p = one(con, "SELECT * FROM posts WHERE id = ?", pid)
            sets = {}
            if m.text.strip() or had:  # an album's caption sits on one of its messages; an edit may empty the text
                t, b = _split(m.text, title)
                if (t, b) != (p["title"], p["body"]) and (m.text.strip() or not p["body"]):
                    sets.update(title=t, body=b)
                    if had:
                        sets["edited_at"] = now()
                    if p["tr_by"] == "ai":  # our translation was of the old text: done again
                        sets.update(i18n=None, lang=None, tr_by=None, ai_tries=0)
            if m.photo and not p["photo_file_id"]:
                sets["photo_file_id"] = _photo(con, m.photo)
            if m.media and not p["tg_media"]:
                sets["tg_media"] = m.media
            if sets:
                con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), pid))  # keys from above
        if not had:
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped) VALUES (?, ?, ?, ?)", (channel, m.id, pid, m.grouped))
        _counted(con, channel, pid, m)
    return pid


def _counted(con, channel: int, pid: int, m: Msg) -> None:
    """Views and reactions from the post's first message (the one its link opens; Telegram keeps them per message: an
    album's other pieces, a folded translation), and the channel's newest post taken."""
    if (c := _counts(m)) and not one(con, "SELECT 1 FROM tg_post_msgs WHERE post_id = ? AND msg_id < ?", pid, m.id):
        con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in c)} WHERE id = ?", (*c.values(), pid))  # keys from _counts
    con.execute("UPDATE tg_channels SET last_msg = MAX(last_msg, ?) WHERE id = ?", (m.id, channel))


def _untitled(con, pid: int, fallback: str) -> bool:
    return one(con, "SELECT title FROM posts WHERE id = ?", pid)["title"] == fallback[:TITLE]


def _langs(con, p) -> tuple[str | None, set[str]]:
    """A post's own language and the ones the channel itself gave it (folded posts, its comments); our AI's don't count.
    A picture with no words of its own (SITE posts the photo, then the kk, ru and en texts) has none: all three fold in."""
    bare = not p["body"].strip() and _untitled(con, p["id"], (one(con, "SELECT title FROM chats WHERE org_id = ? AND main = 1", p["org_id"]) or {"title": ""})["title"])
    own = None if bare else ai.lang_of(f"{p['title']} {p['body']}")
    tr = set(json.loads(p["i18n"])) if p["i18n"] and p["tr_by"] == "tg" else set()
    return own, tr | ({own} if own else set())


def _fold_target(con, channel: int, date: int, lang: str, but: int | None = None) -> int | None:
    """The channel's post this one translates: posted within FOLD_GAP of it, up, and without this language yet
    (two posts in one language are two announcements); the nearest in time."""
    for p in rows(con, """SELECT * FROM posts WHERE tg_channel = ? AND hidden_at IS NULL AND id IS NOT ? AND abs(created_at - ?) <= ?
            ORDER BY abs(created_at - ?)""", channel, but, date, FOLD_GAP, date):
        if lang not in _langs(con, p)[1]:
            return p["id"]
    return None


def _set_tr(con, pid: int, lang: str, tb: tuple[str, str]) -> None:
    """One language of a post from the channel itself; an AI translation it had is dropped (official only)."""
    p = one(con, "SELECT * FROM posts WHERE id = ?", pid)
    have = json.loads(p["i18n"]) if p["i18n"] and p["tr_by"] == "tg" else {}
    have[lang] = {"title": tb[0], "body": tb[1]}
    con.execute("UPDATE posts SET i18n = ?, lang = ?, tr_by = 'tg' WHERE id = ?",
                (json.dumps(have, ensure_ascii=False), _langs(con, p)[0], pid))


def to_comment(con, channel: int) -> list[int]:
    """Posts that may still get their translations as the channel's own comments: a few days old at most, past the
    folding half hour, one language short at least. The message the comments hang under (the post's own first one)."""
    out = []
    for p in rows(con, """SELECT p.*, (SELECT MIN(msg_id) FROM tg_post_msgs t WHERE t.post_id = p.id AND t.lang IS NULL) AS first
            FROM posts p WHERE p.tg_channel = ? AND p.hidden_at IS NULL AND p.created_at BETWEEN ? AND ?""",
                      channel, now() - COMMENT_DAYS * 86400, now() - FOLD_GAP):
        if p["first"] and len(_langs(con, p)[1]) < len(ai.LANGS) and (p["title"].strip() or p["body"].strip()):
            out.append(p["first"])
    return out


def comments(con, channel: int, msg_id: int, texts: list[str]) -> int:
    """The channel's own comments under its post (only those: the caller drops everyone else's unread): one in a language
    the post lacks is that language's text. How many languages it gave."""
    n = 0
    with tx(con):
        t = one(con, "SELECT post_id FROM tg_post_msgs WHERE channel = ? AND msg_id = ? AND lang IS NULL", channel, msg_id)
        if not t:
            return 0
        for text in texts:
            p = one(con, "SELECT * FROM posts WHERE id = ?", t["post_id"])
            lang = ai.lang_of(text) if text.strip() else None
            if lang and lang not in _langs(con, p)[1]:
                _set_tr(con, p["id"], lang, _split(text, p["title"]))
                n += 1
    return n


def gone(con, channel: int, ids: list[int], root: Path | None = None) -> list[int]:
    """Channel posts deleted: a post whose every message went is taken down (hidden: our reactions and the audit stay)
    and wiped: its text emptied, its copied photo deleted (from disk too, under root, when nothing else shows it).
    The posts taken down."""
    down, paths = [], []
    with tx(con):
        for t in rows(con, f"SELECT post_id, lang FROM tg_post_msgs WHERE channel = ? AND lang IS NOT NULL AND msg_id IN ({','.join('?' * len(ids))})",
                      channel, *ids) if ids else []:
            p = one(con, "SELECT i18n FROM posts WHERE id = ?", t["post_id"])
            left = {k: x for k, x in (json.loads(p["i18n"]) if p["i18n"] else {}).items() if k != t["lang"]}
            con.execute("UPDATE posts SET i18n = ?, lang = CASE WHEN ? THEN lang END, tr_by = CASE WHEN ? THEN tr_by END WHERE id = ?",
                        (json.dumps(left, ensure_ascii=False) if left else None, bool(left), bool(left), t["post_id"]))
        for pid in {r[0] for r in rows(con, f"SELECT post_id FROM tg_post_msgs WHERE channel = ? AND msg_id IN ({','.join('?' * len(ids))})",
                                           channel, *ids)} if ids else set():
            con.execute(f"DELETE FROM tg_post_msgs WHERE channel = ? AND post_id = ? AND msg_id IN ({','.join('?' * len(ids))})", (channel, pid, *ids))
            if not one(con, "SELECT 1 FROM tg_post_msgs WHERE post_id = ?", pid):
                fid = one(con, "SELECT photo_file_id FROM posts WHERE id = ?", pid)[0]
                con.execute("""UPDATE posts SET hidden_at = COALESCE(hidden_at, ?), title = '', body = '', i18n = NULL, lang = NULL,
                    tr_by = NULL, photo_file_id = NULL WHERE id = ?""", (now(), pid))
                paths += _drop_unused(con, fid)
                down.append(pid)
    if root:
        media.drop(root, [p for p in paths if photo_free(con, p)])
    return down


def alive(con) -> None:
    """The userbot's heartbeat (each sign-in, each finished sweep): bot.userbot_round tells the owner when it stops."""
    con.execute("INSERT INTO meta (key, value) VALUES ('userbot_ok', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (str(now()),))


def recent(con, channel: int) -> list[int]:
    """The messages of the channel's posts of the last week, still up: their counts are refreshed now and then (and
    one gone missing meanwhile was deleted)."""
    return [r[0] for r in rows(con, """SELECT m.msg_id FROM tg_post_msgs m JOIN posts p ON p.id = m.post_id
        WHERE m.channel = ? AND p.hidden_at IS NULL AND p.created_at > ? ORDER BY m.msg_id""", channel, now() - COUNT_DAYS * 86400)]


def shape(p) -> dict | None:
    """What a mirrored post shows instead of our reactions and comments (types.ts Post.tg); None for an app post."""
    if not p["tg_url"]:
        return None
    return {"url": p["tg_url"], "views": p["tg_views"], "reactions": json.loads(p["tg_reactions"]) if p["tg_reactions"] else [], "media": p["tg_media"]}


def i18n(p) -> dict | None:
    """A post's other languages for the app (api/client.ts localize: title and body), official or our AI's."""
    return {k: {"title": x.get("title", ""), "body": x.get("body", "")} for k, x in json.loads(p["i18n"]).items()} if p["i18n"] else None
