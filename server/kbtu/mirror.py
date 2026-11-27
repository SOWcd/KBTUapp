"""An org's main Telegram channel in its news: what the userbot (userbot.py) saw,
written as the org's posts. Here only the database: the Telegram side hands over messages (Msg), so the rules
are tested without Telegram.

The source is the org's MAIN public channel with its Studio switch on (chats.main, chats.mirror) and our bot an admin
there, which proves the channel is the org's (or an admin's say-so: chats.mirror = 2); the userbot joins it
itself and leaves it when it stops being one. A post is a channel post (an album is one post): its text as typed (the
first line the title), its photo copied, a video or a file only as a link to the post; edits follow, a deletion takes
it down and wipes its text and photo; Telegram's views and reaction counts show instead of ours, and comments stay in Telegram. Nobody is notified
of a mirrored post. Nothing but the channel's own posts is kept.

A club that announces in a forum group instead (no channel, an "Announcements" topic) picks that group and topic in
Studio (chats.news_topic; it then replaces the main channel). Our bot must be in the group (tg_chat_id says which one it
is); the userbot joins it by its link (or was added by hand: then it never leaves it, stay) and lists its topics for the
picker. Only that topic's top-level posts by the group's admins (or sent as the group) are taken, like a channel's
posts; every other message (other topics, General, members, replies) is dropped unread."""
from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import ai, media
from .logic import ApiError, now, one, photo_free, rows, tx, wipe_post
from .logic import autoev
from .logic.clubs import stories_open

FIRST_TAKE = 5            # on a first link: at most the last 5 posts ...
FIRST_DAYS = 30           # ... of the last 30 days
COUNT_DAYS = 7            # views and reactions refreshed for the posts of the last week
TITLE, BODY = 120, 2000   # what an app post holds (logic.create_post)
FOLD_GAP = 1800           # the same announcement in another language: posted within half an hour (SITE posts kk/ru/en)
COMMENT_DAYS = 2          # how long the channel's own comments are looked at for a post's translations

Entity = tuple[str, int, int, str | None]


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
    entities: list[Entity] = field(default_factory=list)  # Telegram's UTF-16 offsets
    # a group's message: the topic it opens a post in (None: a reply, or no topic) and whether its sender may announce
    # there (an admin, or the group itself); a channel's post is always the channel's own
    topic: int | None = None
    own: bool = True


def username(url: str) -> str | None:
    """A public chat's name from its t.me link; None for an invite link."""
    m = re.fullmatch(r"https://t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?", url or "")
    return m.group(1).lower() if m else None


def invite(url: str) -> str | None:
    """A closed chat's invite hash from its t.me link; None for a public one."""
    m = re.fullmatch(r"https://t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]{8,64})/?", url or "", re.I)
    return m.group(1) if m else None


def tid(tg_chat_id: int | None) -> int | None:
    """A supergroup's Telethon id from its Bot API id (-100<id>); None for anything else."""
    s = str(tg_chat_id or "")
    return int(s[4:]) if s.startswith("-100") and s[4:].isdigit() else None


_GROUP_SRC = "{a}.news_topic IS NOT NULL AND {a}.kind = 'group' AND {a}.tg_chat_id IS NOT NULL"  # a chats row (alias a) as a group source
# the switch on AND the channel proven the org's own: our bot an admin there (tg_chat_id), or an admin vouched (mirror = 2:
# an office's channel, admin office); else any club could mirror a public channel it doesn't run (logic.chatlist.mirrored)
_MIRRORED = "(c.mirror = 2 OR (c.mirror = 1 AND c.tg_chat_id IS NOT NULL))"


def groups(con) -> dict[int, dict]:
    """The forum groups an active org picked as its news source (chats.news_topic), by Telethon id: the chat row."""
    out = {}
    for c in rows(con, f"""SELECT c.* FROM chats c JOIN orgs o ON o.id = c.org_id
            WHERE {_GROUP_SRC.format(a='c')} AND o.status = 'active' ORDER BY c.id"""):
        if (t := tid(c["tg_chat_id"])) is not None:
            out.setdefault(t, dict(c))
    return out


def wanted(con) -> dict[str, int]:
    """The channels to mirror, by name: each active org's main public channel with the switch on and proven its own
    (_MIRRORED), unless the org picked a group's topic instead. name -> org id."""
    out = {}
    for c in rows(con, f"""SELECT c.url, c.org_id FROM chats c JOIN orgs o ON o.id = c.org_id
            WHERE c.main = 1 AND {_MIRRORED} AND c.kind = 'channel' AND o.status = 'active'
            AND NOT EXISTS (SELECT 1 FROM chats g WHERE g.org_id = o.id AND {_GROUP_SRC.format(a='g')}) ORDER BY c.id"""):
        if name := username(c["url"]):
            out.setdefault(name, c["org_id"])
    return out


def has_channel(con, oid: int) -> bool:
    """The org's main chat is a public channel, or it announces in a group's topic: one the userbot can mirror (admin
    channel-ask asks the rest for one)."""
    if one(con, f"SELECT 1 FROM chats c WHERE c.org_id = ? AND {_GROUP_SRC.format(a='c')} AND c.news_topic > 0", oid):
        return True
    c = one(con, "SELECT kind, url FROM chats WHERE org_id = ? AND main = 1", oid)
    return bool(c and c["kind"] == "channel" and username(c["url"]))


def to_join(con) -> list[str]:
    have = {r[0] for r in rows(con, "SELECT username FROM tg_channels")}
    return [n for n in wanted(con) if n not in have]


def groups_to_join(con) -> list[tuple[int, str]]:
    """The source groups the userbot is not known to be in yet: (Telethon id, the group's link to join by)."""
    have = {r[0] for r in rows(con, "SELECT id FROM tg_channels")}
    return [(t, c["url"]) for t, c in groups(con).items() if t not in have]


def to_leave(con) -> list[tuple[int, str]]:
    """Channels and groups the userbot joined that are no source any more."""
    keep, gs = wanted(con), groups(con)
    return [(r["id"], r["username"]) for r in rows(con, "SELECT id, username FROM tg_channels ORDER BY id")
            if r["username"] not in keep and r["id"] not in gs]


def stays(con, channel: int) -> bool:
    """The userbot was in this group before it became a source (added by hand): forgotten, never left."""
    return bool(one(con, "SELECT stay FROM tg_channels WHERE id = ?", channel)["stay"])


def joined(con, channel: int, name: str, stay: bool = False) -> None:
    """A channel by its t.me name, a group as '#<id>' (never a channel's name)."""
    con.execute("""INSERT INTO tg_channels (id, username, joined_at, stay) VALUES (?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET username = excluded.username""", (channel, name.lower(), now(), int(stay)))


def left(con, channel: int) -> None:
    con.execute("DELETE FROM tg_channels WHERE id = ?", (channel,))


def unpick(con, group: int) -> None:
    """The userbot can't use the group the club picked (not a forum, another group behind the link, it asks to be let
    in): no more its source (Studio shows the channel again), so it is never tried again by itself."""
    con.execute("UPDATE chats SET news_topic = NULL WHERE tg_chat_id = ?", (int(f"-100{group}"),))


def seen(con, channel: int, msg_id: int) -> None:
    """A source read up to here: its post taken or intentionally skipped. The next sweep starts after it."""
    con.execute("UPDATE tg_channels SET last_msg = MAX(last_msg, ?) WHERE id = ?", (msg_id, channel))


def _source(con, channel: int) -> dict | None:
    """What a joined chat is mirrored as now: org, topic (None: a channel; 0: a group whose topic isn't picked yet)
    and the title an untitled post takes; None: not (or no more) a source."""
    c = one(con, "SELECT username FROM tg_channels WHERE id = ?", channel)
    if not c:
        return None
    if g := groups(con).get(channel):
        return {"org": g["org_id"], "topic": g["news_topic"], "title": g["title"], "url": g["url"]}
    if (oid := wanted(con).get(c["username"])) is None:
        return None
    m = one(con, "SELECT title FROM chats WHERE org_id = ? AND main = 1", oid)
    return {"org": oid, "topic": None, "title": m["title"] if m else c["username"], "url": f"https://t.me/{c['username']}"}


def source(con, channel: int) -> int | None:
    """The org a joined channel is mirrored into now; None: not (or no more) a mirror: its posts are let be."""
    s = _source(con, channel)
    return s["org"] if s else None


def topic(con, channel: int) -> int | None:
    """A source group's picked topic (0: none yet); None for a channel or no source."""
    s = _source(con, channel)
    return s["topic"] if s else None


def topics(con, channel: int, got: list[tuple[int, str]]) -> None:
    """A source group's topics as the userbot listed them, for Studio's picker: titles only, all anew; never General
    (id 1: the members' chat)."""
    if not (g := groups(con).get(channel)):
        return
    with tx(con):
        con.execute("DELETE FROM chat_topics WHERE chat_id = ?", (g["id"],))
        con.executemany("INSERT OR IGNORE INTO chat_topics (chat_id, topic, title) VALUES (?, ?, ?)",
                        [(g["id"], int(t), " ".join(str(x).split())[:80] or "#") for t, x in got[:100] if int(t) > 1])


def _link(s: dict, channel: int, msg: int) -> str:
    """A taken message's t.me address: a public chat's, or a closed group's (opens for its members)."""
    name = username(s["url"])
    return f"https://t.me/{name}/{msg}" if name else f"https://t.me/c/{channel}/{s['topic']}/{msg}"


def last(con, channel: int) -> int:
    """The newest message handled from the source; 0 on a first link (then FIRST_TAKE of the last FIRST_DAYS)."""
    c = one(con, "SELECT last_msg FROM tg_channels WHERE id = ?", channel)
    return c["last_msg"] if c else 0


def _slice_fmt(text: bytes, start: int, end: int, entities: list[Entity]) -> list[Entity]:
    out = []
    for kind, offset, length, url in entities:
        left, right = max(start, offset), min(end, offset + length)
        if left >= right:
            continue
        if kind == "text_link" and not re.match(r"https?://[^/\s?#]+", url or "", re.I):
            continue
        if kind == "url" and (left, right) != (offset, offset + length):
            url = text[2 * offset:2 * (offset + length)].decode("utf-16-le", errors="replace")
        out.append((kind, left - start, right - left, url))
    return out


def _split(text: str, fallback: str, entities: list[Entity] | None = None) -> dict:
    """A post's title and text: its first line, the rest under it; a long first line is cut at a word and the whole
    text follows it, so nothing is lost; past what a post holds, the rest is a tap away in Telegram."""
    start = len(text) - len(text.lstrip())
    text = text.rstrip()
    if start >= len(text):
        return {"title": fallback[:TITLE], "body": ""}
    first, _, rest = text[start:].partition("\n")
    first = first.rstrip()
    if len(first) <= TITLE:
        title, body = first, rest.lstrip()
        title_end = start + len(title)
        body_start = len(text) - len(body)
    else:
        cut = first[:TITLE - 1].rsplit(" ", 1)[0] or first[:TITLE - 1]
        cut = cut.rstrip(" ,.;:-")
        title, body = cut + "…", text[start:]
        title_end, body_start = start + len(cut), start
    body_end = len(text)
    if len(body) > BODY:
        cut = body[:BODY - 1].rsplit(" ", 1)[0]
        body, body_end = cut + "…", body_start + len(cut)
    post = {"title": title, "body": body}
    if entities:
        encoded = text.encode("utf-16-le")
        for key, left, right in (("titleFmt", start, title_end), ("fmt", body_start, body_end)):
            # The split uses Python string indices; Telegram counts UTF-16 code units.
            left_units = len(text[:left].encode("utf-16-le")) // 2
            right_units = left_units + len(text[left:right].encode("utf-16-le")) // 2
            if fmt := _slice_fmt(encoded, left_units, right_units, entities):
                post[key] = fmt
    return post


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
    """Whether a message's photo is worth downloading: a new post, or one (or its album) without a photo yet; never
    one taken down (an edit in Telegram doesn't bring a deleted post's photo back)."""
    p = one(con, """SELECT p.photo_file_id, p.hidden_at FROM tg_post_msgs t JOIN posts p ON p.id = t.post_id
        WHERE t.channel = ? AND (t.msg_id = ? OR (? IS NOT NULL AND t.grouped = ?)) LIMIT 1""", channel, m_id, grouped, grouped)
    return not p or p["photo_file_id"] is None and p["hidden_at"] is None


def legacy_album_siblings(con, channel: int, m: Msg) -> list[int] | None:
    """The other mirrored members of an album whose caption source was never recorded."""
    p = one(con, """SELECT p.id FROM tg_post_msgs t JOIN posts p ON p.id = t.post_id
        WHERE t.channel = ? AND t.msg_id = ? AND t.lang IS NULL AND p.tg_fmt IS NULL AND p.hidden_at IS NULL""", channel, m.id)
    return [r[0] for r in rows(con, """SELECT msg_id FROM tg_post_msgs WHERE post_id = ? AND channel = ?
        AND grouped = ? AND lang IS NULL AND msg_id != ? ORDER BY msg_id DESC""", p[0], channel, m.grouped, m.id)] if p else None


def take(con, channel: int, m: Msg, *, album_empty: bool = False, advance: bool = True) -> int | None:
    """A new channel post, an edit of one, or one more piece of an album: the org's post for it (a post without text
    is titled by the channel). The post's id; None when the channel is no mirror now, or (a group) the message is not
    an admin's post opening in the picked topic. An individual refresh leaves the history cursor where it was."""
    s = _source(con, channel)
    if s is None or s["topic"] is not None and not (s["topic"] and m.topic == s["topic"] and m.own):
        return None
    oid, title = s["org"], s["title"]
    with tx(con):
        if advance:
            seen(con, channel, m.id)
        had = one(con, "SELECT post_id, lang FROM tg_post_msgs WHERE channel = ? AND msg_id = ?", channel, m.id)
        album = one(con, "SELECT post_id FROM tg_post_msgs WHERE channel = ? AND grouped = ?", channel, m.grouped) if m.grouped and not had else None
        pid = (had or album)["post_id"] if (had or album) else None
        lang = ai.lang_of(m.text) if m.text.strip() else None
        if pid and one(con, "SELECT hidden_at FROM posts WHERE id = ?", pid)["hidden_at"]:
            # taken down here (by its club or a moderator): an edit in Telegram brings back neither its text nor its photo
            if not had:
                con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped, lang) VALUES (?, ?, ?, ?, NULL)", (channel, m.id, pid, m.grouped))
            _counted(con, pid, m)
            return pid
        post = _split(m.text, title, m.entities)
        if had and had["lang"]:  # a translation folded into another post: its edit is that language's text
            if m.text.strip():
                _set_tr(con, pid, had["lang"], post)
            _counted(con, pid, m)
            return pid
        if pid is None and lang and (into := _fold_target(con, channel, m.date, lang)):
            # the same announcement in another language: one post, this text as its translation
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped, lang) VALUES (?, ?, ?, ?, ?)", (channel, m.id, into, m.grouped, lang))
            _set_tr(con, into, lang, post)
            if m.photo and not one(con, "SELECT photo_file_id FROM posts WHERE id = ?", into)["photo_file_id"]:
                con.execute("UPDATE posts SET photo_file_id = ? WHERE id = ?", (_photo(con, m.photo), into))
                autoev.cover(con, into)  # the photo after the text: the draft found in it gets it too
            _counted(con, into, m)
            return into
        if album and lang and not one(con, "SELECT 1 FROM posts WHERE id = ? AND body != ''", pid) and _untitled(con, pid, title) \
                and (into := _fold_target(con, channel, m.date, lang, but=pid)):
            # an album's caption came after its photos: the whole album is a translation of an earlier post
            con.execute("UPDATE tg_post_msgs SET post_id = ?, lang = ? WHERE post_id = ?", (into, lang, pid))
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped, lang) VALUES (?, ?, ?, ?, ?)", (channel, m.id, into, m.grouped, lang))
            gone_photo = one(con, "SELECT photo_file_id FROM posts WHERE id = ?", pid)["photo_file_id"]
            if gone_photo and not one(con, "SELECT photo_file_id FROM posts WHERE id = ?", into)["photo_file_id"]:
                con.execute("UPDATE posts SET photo_file_id = ? WHERE id = ?", (gone_photo, into))
                autoev.cover(con, into)
            con.execute("DELETE FROM posts WHERE id = ?", (pid,))  # made a moment ago, nobody saw it yet
            _set_tr(con, into, lang, post)
            _counted(con, into, m)
            return into
        t, b = post["title"], post["body"]
        fmt = {k: post[k] for k in ("titleFmt", "fmt") if k in post}
        # An album's caption source survives formatting changes and caption removal.
        tg_fmt = json.dumps({"msg": m.id, **fmt}, ensure_ascii=False) if fmt or m.grouped else None
        if pid is None:
            if not stories_open(con, one(con, "SELECT * FROM orgs WHERE id = ?", oid)):
                return None  # a student initiative below the Ascent's collab step posts no stories, mirrored ones neither
            pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, tg_fmt, photo_file_id, comments_on,
                    created_at, tg_channel, tg_url, tg_media) VALUES (?, NULL, 'public', ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                              (oid, t, b, tg_fmt, _photo(con, m.photo) if m.photo else None, m.date, channel,
                               _link(s, channel, m.id), m.media)).lastrowid
        else:
            p = one(con, "SELECT * FROM posts WHERE id = ?", pid)
            sets = {}
            caption = json.loads(p["tg_fmt"])["msg"] == m.id if p["tg_fmt"] else album_empty
            if m.text.strip() or (had and (not m.grouped or caption)):
                text_changed = (t, b) != (p["title"], p["body"])
                if text_changed or tg_fmt != p["tg_fmt"]:
                    sets.update(title=t, body=b, tg_fmt=tg_fmt)
                    if had:
                        sets["edited_at"] = now()
                    if text_changed and p["tr_by"] == "ai":  # our translation was of the old text: done again
                        sets.update(i18n=None, lang=None, tr_by=None, ai_tries=0)
            if m.photo and not p["photo_file_id"]:
                sets["photo_file_id"] = _photo(con, m.photo)
            if m.media and not p["tg_media"]:
                sets["tg_media"] = m.media
            if sets:
                con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), pid))  # keys from above
                if "photo_file_id" in sets:
                    autoev.cover(con, pid)
        if not had:
            con.execute("INSERT INTO tg_post_msgs (channel, msg_id, post_id, grouped) VALUES (?, ?, ?, ?)", (channel, m.id, pid, m.grouped))
        _counted(con, pid, m)
    return pid


def _counted(con, pid: int, m: Msg) -> None:
    """Views and reactions from the post's first message (the one its link opens; Telegram keeps them per message: an
    album's other pieces, a folded translation)."""
    if (c := _counts(m)) and not one(con, "SELECT 1 FROM tg_post_msgs WHERE post_id = ? AND msg_id < ?", pid, m.id):
        con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in c)} WHERE id = ?", (*c.values(), pid))  # keys from _counts


def _untitled(con, pid: int, fallback: str) -> bool:
    return one(con, "SELECT title FROM posts WHERE id = ?", pid)["title"] == fallback[:TITLE]


def _langs(con, p) -> tuple[str | None, set[str]]:
    """A post's own language and the ones the channel itself gave it (folded posts, its comments); our AI's don't count.
    A picture with no words of its own (SITE posts the photo, then the kk, ru and en texts) has none: all three fold in."""
    s = _source(con, p["tg_channel"]) if p["tg_channel"] else None
    bare = not p["body"].strip() and _untitled(con, p["id"], s["title"] if s else "")
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


def _set_tr(con, pid: int, lang: str, post: dict) -> None:
    """One language of a post from the channel itself; an AI translation it had is dropped (official only)."""
    p = one(con, "SELECT * FROM posts WHERE id = ?", pid)
    have = json.loads(p["i18n"]) if p["i18n"] and p["tr_by"] == "tg" else {}
    have[lang] = post
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
        t = one(con, """SELECT post_id FROM tg_post_msgs WHERE channel = ? AND msg_id = ? AND lang IS NULL
            AND post_id IN (SELECT id FROM posts WHERE hidden_at IS NULL)""", channel, msg_id)  # a post deleted meanwhile stays wiped
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
                con.execute("UPDATE posts SET hidden_at = COALESCE(hidden_at, ?) WHERE id = ?", (now(), pid))
                paths += wipe_post(con, pid)
                down.append(pid)
    if root:
        media.drop(root, [p for p in paths if photo_free(con, p)])
    return down


def alive(con) -> None:
    """The userbot's heartbeat (each sign-in, each finished sweep): chores.userbot_round tells the owner when it stops."""
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
    return {k: {"title": x.get("title", ""), "body": x.get("body", ""), **{f: x[f] for f in ("titleFmt", "fmt") if f in x}}
            for k, x in json.loads(p["i18n"]).items()} if p["i18n"] else None


# Read the public embed page (t.me/<channel>/<id>?embed=1) for the CDN URL so the app can play the video inline.
# The address is built from our own row, never the
# client's; what comes back must be a CDN file, or it's not_found and the app frames Telegram's widget instead (a long
# video's embed has no file either). The file's token expires: resolved on a tap, kept a few minutes, never stored.
_POST = re.compile(r"https://t\.me/([A-Za-z0-9_]{4,32})/(\d{1,12})")
_CDN = re.compile(r"https://[a-z0-9-]+\.(?:telesco\.pe|cdn-telegram\.org)/file/[^\s\"'<>()\\]+")
_SRC = re.compile(r"<video\b[^>]*?\bsrc=\"([^\"]+)\"")
_THUMB = re.compile(r"tgme_widget_message_video_thumb\"[^>]*?background-image:url\('([^']+)'\)")
VIDEO_TTL, VIDEO_PER_MIN, PAGE_MAX = 300, 20, 256 * 1024
# ponytail: per-worker memory (each uvicorn worker resolves on its own, a per-user limit is per worker); fine at our
# size, a shared table if it ever matters
_videos: dict[str, tuple[float, dict]] = {}
_asks: dict[int, list[float]] = {}


def video_page(tg_url: str | None) -> str | None:
    """The embed page of a mirrored post's own t.me address; None for anything else."""
    m = _POST.fullmatch(tg_url or "")
    return m and f"https://t.me/{m[1]}/{m[2]}?embed=1"


def parse_video(page: str) -> dict | None:
    """The first video's file and its poster on an embed page; None when it has no CDN file."""
    m = _SRC.search(page)
    src = html.unescape(m[1]) if m else ""
    if not _CDN.fullmatch(src):
        return None
    t = _THUMB.search(page)
    poster = html.unescape(t[1]) if t else None
    return {"src": src, "poster": poster if poster and _CDN.fullmatch(poster) else None}


def _asked(uid: int, t: float) -> None:
    if len(_asks) > 5000:
        for k in [k for k, x in _asks.items() if x[-1] <= t - 60]:
            del _asks[k]
    recent = [x for x in _asks.get(uid, ()) if x > t - 60]
    if len(recent) >= VIDEO_PER_MIN:
        raise ApiError("rate_limited")
    _asks[uid] = [*recent, t]


def _video_url(con, pid: int) -> str | None:
    p = one(con, """SELECT p.tg_url FROM posts p JOIN orgs o ON o.id = p.org_id
        WHERE p.id = ? AND p.tg_media = 'video' AND p.hidden_at IS NULL AND o.status != 'hidden'""", pid)
    return video_page(p[0]) if p else None


async def video(con, uid: int, pid: int, http: httpx.AsyncClient) -> dict:
    """A visible mirrored video's playable file and poster."""
    url = _video_url(con, pid)
    if not url:
        raise ApiError("not_found")
    t = time.monotonic()
    if (hit := _videos.get(url)) and hit[0] > t:
        return hit[1]
    _asked(uid, t)
    try:
        async with http.stream("GET", url, follow_redirects=False) as r:
            page = b""
            async for chunk in r.aiter_bytes():
                page += chunk
                if len(page) > PAGE_MAX:
                    break
            ok = r.status_code == 200
    except httpx.HTTPError:
        ok = False
    found = parse_video(page.decode("utf-8", "replace")) if ok else None
    if not found or _video_url(con, pid) != url:
        raise ApiError("not_found")
    if len(_videos) > 500:
        _videos.clear()  # stale tokens only; the next taps fetch again
    _videos[url] = (t + VIDEO_TTL, found)
    return found
