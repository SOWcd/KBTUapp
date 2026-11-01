"""The forum channel (owner, Nov 1: replaces the in-app student forum). A Microsoft-verified student writes a post in
the app, under their name or anonymously; the bot publishes it in the public channel (FORUM_CHANNEL), where the
comments happen in its Telegram discussion group (tgc.py). One post a day per student. The AI looks first: its exact
OK publishes at once (the bot's next round, seconds); anything else, or an anonymous post aimed at a person, waits for
a moderator. Plain text only: no links, @mentions or phone numbers (the bot is the publisher, nobody pings or doxes
through it). The author deletes, a moderator takes down, a deleted account's posts leave too: all through tg_unpost,
which keeps only the channel's message id. Only the owner reveals an anonymous author, each look in the audit log."""
from __future__ import annotations

import re
import secrets
import unicodedata

from .. import texts
from ..db import tx

from .core import ApiError, PERSON, Viewer, log_action, need_student, one, person_ref, rows, short_name

BODY_MAX = 1000
POSTS_A_DAY = 1
UNPOST_SPREAD = 72 * 3600  # a deleted account's anonymous posts leave within it, each at its own moment
CHANNEL_AN_HOUR = 20     # live posts in the channel an hour; past it, a moderator lets the next ones out (a burst can't flood it)
MOD_RECENT = 7 * 86400   # live posts the moderators' list shows, to take one down
# what Telegram turns into a link or a ping even in plain text, looked for in the text NFKC-normalised (fullwidth
# letters and dots fold to ASCII; the ideographic dots count as dots): a scheme, www., a domain (Latin or IDN labels,
# a Latin TLD or a Cyrillic one Telegram links), an e-mail, @handle, a phone or a card number (+..., a Kazakh 8/7 7xx
# number, ten digits or more in any spacing). ponytail: any "word.letters" counts as a domain ("node.js" too), since
# Telegram knows every Latin TLD; a TLD list if students trip on it
_CYR_TLD = "\u0440\u0444|\u0440\u0443\u0441|\u043e\u043d\u043b\u0430\u0439\u043d|\u0441\u0430\u0439\u0442|\u043e\u0440\u0433|\u043a\u043e\u043c|\u043c\u043e\u0441\u043a\u0432\u0430|\u049b\u0430\u0437|\u0431\u0435\u043b|\u0443\u043a\u0440|\u0441\u0440\u0431|\u0434\u0435\u0442\u0438"
LINKY = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://|\bwww\.|\b[^\W_][\w-]*(\.[^\W_][\w-]*)*\.(?:[a-z]{2,}|" + _CYR_TLD + r")\b|@\w{3,}"
                   r"|\+\d[\d\s().-]{7,}\d|\b[78][\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b|\d(?:[\s-]?\d){9,})")
DOTS = str.maketrans({"\u3002": ".", "\uff61": ".", "\uff0e": "."})
FILLERS = {"\u034f", "\u115f", "\u1160", "\u3164", "\uffa0"}  # invisible letters a model reads and a moderator doesn't see
ZWJ = "\u200d"   # kept in the words (emoji families, flags); out of the text the link check reads
SIGNED = re.compile("^[\u2010-\u2015\u2212-]")  # a last line like the bot's "- Name L." signature (read NFKC: fullwidth, small dashes fold)


def _visible(c: str) -> bool:
    """Not a format, private-use or unassigned character (tag letters, zero-width and direction marks), not a filler
    letter, not an ideographic variation selector: what can hide words from the check and the moderators."""
    return c == ZWJ or (unicodedata.category(c) not in ("Cf", "Co", "Cn") and c not in FILLERS and not "\U000e0100" <= c <= "\U000e01ef")


def _clean(raw: object) -> str:
    """The words as published and as the AI reads them: invisible characters out, lines trimmed; refused with a link,
    a mention, a phone or a signature-like last line (an anonymous post posing as a named one)."""
    s = "".join(c for c in str(raw or "") if _visible(c) or c == "\n")
    s = "\n".join(line.rstrip() for line in s.strip().splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s)
    if not 2 <= len(s) <= BODY_MAX:
        raise ApiError("bad_input")
    if LINKY.search(unicodedata.normalize("NFKC", s.replace(ZWJ, "")).translate(DOTS)):
        raise ApiError("bad_input", "links")
    if "\n" in s and SIGNED.match(unicodedata.normalize("NFKC", s.rsplit("\n", 1)[1]).lstrip()):
        raise ApiError("bad_input", "signature")
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
    """The AI's word on a reserved post (untouched meanwhile): only 'ok' goes live (the bot's round sends it); 'person'
    (named or not: an accusation goes out under the bot's name), a 'flag' or no answer wait for a moderator, and so does
    anything past the hour's cap."""
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND status = 'held' AND why = 'check'", pid)
        if p:
            if verdict == "ok":
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
    """A deleted account's published posts leave the channel (account.delete_me, before the rows cascade away). The
    anonymous ones each at a random moment within 3 days (the privacy policy says so): gone all in one second together
    with a named one, they'd tell the channel whose they were, and that they share an author."""
    for p in rows(con, "SELECT tg_msg, anon FROM fchan_posts WHERE user_id = ? AND tg_msg > 0", uid):
        at = _now() + (secrets.randbelow(UNPOST_SPREAD) if p["anon"] else 0)
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, 'author', ?)", (p["tg_msg"], at))


# ---- the bot's side (tgc.py): what to send, what was sent, what to take down

def to_send(con) -> list:
    """Live posts not in the channel yet, oldest first, with their signature: the name (first name, last initial,
    never a nick or @username) or nothing for an anonymous one."""
    out = []
    for p in rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND tg_msg IS NULL ORDER BY id LIMIT 5"):
        who = None if p["anon"] else one(con, PERSON + " WHERE u.id = ?", p["user_id"])
        out.append((p["id"], p["body"], short_name(who) if who else None))
    return out


def sending(con, pid: int) -> bool:
    """Marked as on its way (tg_msg 0) before the bot sends it: a send cut off can't go twice by itself (lost())."""
    return con.execute("UPDATE fchan_posts SET tg_msg = 0 WHERE id = ? AND status = 'live' AND tg_msg IS NULL", (pid,)).rowcount > 0


def sent(con, pid: int, msg_id: int) -> None:
    """The bot sent it: its message id kept; deleted or taken down meanwhile, the message goes right back out (with the
    right words if it's past 48 h: a moderator's take-down isn't the author's delete)."""
    if not con.execute("UPDATE fchan_posts SET tg_msg = ? WHERE id = ? AND status = 'live' AND tg_msg IN (0, ?)", (msg_id, pid, msg_id)).rowcount:
        p = one(con, "SELECT status FROM fchan_posts WHERE id = ?", pid)
        why = "moderator" if p and p["status"] == "hidden" else "author"
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, ?, ?)", (msg_id, why, _now()))


def unsend(con, pid: int) -> None:
    """Telegram refused it (it isn't in the channel): the next round tries again."""
    con.execute("UPDATE fchan_posts SET tg_msg = NULL WHERE id = ? AND tg_msg = 0", (pid,))


def lost(con) -> None:
    """Sends with no answer (a timeout, a crash between the send and sent()): the post may be in the channel or not, and
    a second send would leave a copy nobody can take down. A moderator looks at the channel and decides. ponytail: one
    deleted or taken down while its send was lost stays untracked if it did go out; the bot's one process makes that a
    crash in a two-second window"""
    con.execute("UPDATE fchan_posts SET status = 'held', why = 'lost', tg_msg = NULL WHERE status = 'live' AND tg_msg = 0")


def found(con, msg_id: int, text: str) -> None:
    """The channel post's copy reached the discussion group (tgc.gate): a send whose answer never came (on its way, or
    held as lost since) is in the channel after all. Matched by its words (the text without the bot's signature), its
    message id kept, so the author's delete and a take-down reach it; it was live when sent, so live again. Matched by
    the whole text as sent (the words and the signature, as to_send makes it), and only when exactly one post matches
    and no post holds that message yet: another student's same words must never become this one's (review)."""
    if one(con, "SELECT 1 FROM fchan_posts WHERE tg_msg = ?", msg_id):
        return
    anon = texts.bot_message("ru", "fch_anon")[0]  # the channel's language, as tgc.post_tick signs
    hits = []
    for p in rows(con, """SELECT * FROM fchan_posts WHERE (status = 'live' AND tg_msg = 0 OR status = 'held' AND why = 'lost')
            AND ? LIKE body || '%'""", text):
        who = None if p["anon"] else one(con, PERSON + " WHERE u.id = ?", p["user_id"])
        if f"{p['body']}\n\n\u2014 {short_name(who) if who else anon}" == text:
            hits.append(p["id"])
    if len(hits) == 1:
        con.execute("UPDATE fchan_posts SET status = 'live', why = NULL, tg_msg = ? WHERE id = ?", (msg_id, hits[0]))


def sweep(con) -> None:
    """What the privacy policy promises: a deleted post's wordless row after its day, a taken-down one after 30 days."""
    con.execute("DELETE FROM fchan_posts WHERE status = 'gone' AND created_at < ? OR status = 'hidden' AND created_at < ?",
                (_now() - 86400, _now() - 30 * 86400))


def unposts(con) -> list:
    """Channel messages due to leave now, oldest first."""
    return rows(con, "SELECT msg_id, why FROM tg_unpost WHERE at <= ? ORDER BY at LIMIT 20", _now())


def unpost_later(con, msg_id: int) -> None:
    """Neither deleted nor edited (rights lost?): still public, so tried again in 10 minutes, never dropped."""
    con.execute("UPDATE tg_unpost SET at = ? WHERE msg_id = ?", (_now() + 600, msg_id))


def copy_gone(con, msg_id: int) -> None:
    """A channel post left: its copy in the discussion group (the words again, the comments' root) is to go too, now or
    once the copy's mapping arrives (tgc.gate writes it when Telegram forwards the post into the group)."""
    con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", (f"fchgone:{msg_id}", str(_now())))


def copies(con) -> list[tuple[str, int | None]]:
    """Group copies to delete: (key, the copy's id); None once a week passed with no mapping (no group linked)."""
    out = []
    for key, at in rows(con, "SELECT key, value FROM meta WHERE key LIKE 'fchgone:%'"):
        root = one(con, "SELECT key FROM meta WHERE key LIKE 'tgcpost:%' AND value LIKE ?", f"% {key.split(':')[1]}")
        if root:
            out.append((key, int(root[0].split(":")[1])))
        elif int(at) < _now() - 7 * 86400:
            out.append((key, None))
    return out


def copy_done(con, key: str, root: int | None) -> None:
    con.execute("DELETE FROM meta WHERE key = ? OR key = ?", (key, f"tgcpost:{root}"))


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
