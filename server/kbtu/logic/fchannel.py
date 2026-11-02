"""The forum channel (owner, Nov 1: replaces the in-app student forum). A Microsoft-verified student writes a post in
the app, under their name or anonymously; the bot publishes it in the public channel (FORUM_CHANNEL), where the
comments happen in its Telegram discussion group (tgc.py). One post a day per student. The AI looks first: its exact
OK publishes at once (the bot's next round, seconds); anything else, or an anonymous post aimed at a person, waits for
a moderator. Plain text only: no links, @mentions or phone numbers (the bot is the publisher, nobody pings or doxes
through it). The author deletes, a moderator takes down, a deleted account's posts leave too: all through tg_unpost,
which keeps only the channel's message id. Only the owner reveals an anonymous author, each look in the audit log."""
from __future__ import annotations

import json
import re
import secrets
import unicodedata

from .. import texts
from ..db import tx

from .core import ApiError, PERSON, PERSON_COLS, Viewer, avatar_of, log_action, need_student, one, person_ref, rows, short_name, shown_name

BODY_MAX = 1000
POSTS_A_DAY = 5           # owner, Nov 1: one a day was too strict; a pace, not a ration
POST_GAP = 10 * 60        # and one at a time: ten minutes between a person's posts
UNPOST_SPREAD = 72 * 3600  # a deleted account's anonymous posts leave within it, each at its own moment
CHANNEL_AN_HOUR = 20     # live posts in the channel an hour; past it, a moderator lets the next ones out (a burst can't flood it)
MOD_RECENT = 7 * 86400   # live posts the moderators' list shows, to take one down
UNDO_WINDOW = 60         # a moderator's take-down leaves the channel after it: Undo inside keeps the message and its comments
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
SIGNED = re.compile("^[\u2010-\u2015\u2212-]")  # a last line like a "- Name L." signature (the bot signed so until Nov 2; still reads as one) (read NFKC: fullwidth, small dashes fold)


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


FEED_MAX = 50  # ponytail: the newest 50, no paging; a cursor when the channel outgrows a scroll


def feed(con, v: Viewer) -> list[dict]:
    """The Forum tab: what the channel shows (live posts the bot sent), newest first, signed as there (the name, or the
    anonymous line in the channel's language), plus my own posts on their way or removed. Never whose an anonymous post
    is: no user id, no person, no avatar, for every viewer (staff too), and `mine` true on my own rows alone. A signed
    one carries its author (person: the app's avatar, name with the nick first, and profile), read once for all rows; its
    signature is the one it went out with (the app shows `person` instead; `sign` for an author no longer here)."""
    ps = rows(con, """SELECT * FROM fchan_posts WHERE status = 'live' AND tg_msg > 0 OR user_id = ? AND status != 'gone'
                      ORDER BY id DESC LIMIT ?""", v.id, FEED_MAX)
    ids = {p["user_id"] for p in ps if not p["anon"]}
    who = {p["id"]: p for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)} if ids else {}
    faces = _faces(con, [p["id"] for p in ps if p["comments"]]) if v.student else {}  # people for students alone (a guest: none)
    out = []
    for p in ps:
        a = None if p["anon"] else who.get(p["user_id"])  # an anonymous row never reads its author's person
        out.append({"id": p["id"], "body": p["body"], "status": p["status"], "at": p["created_at"], "msg": p["tg_msg"] or None, "anon": bool(p["anon"]),
             "sign": anon_sign(p["body"]) if p["anon"] else p["sign"] or (short_name(a) if a else "?"), "person": person_ref(a) if a else None,
             "mine": p["user_id"] == v.id,
             # the comments: the students' count, and the bot's first comment (the link opens the thread there)
             "comments": p["comments"], "thread": p["rules_msg"] if p["tg_msg"] else None,
             # Telegram's side of the post: the latest commenters' faces (app students only), its top reactions
             "faces": faces.get(p["id"], []), "reactions": _top(p["reactions"])})
    return out


FACES = 3  # the newest commenters a card shows


def _faces(con, ids: list[int]) -> dict[int, list[dict]]:
    """The newest FACES distinct commenters of each post, one query for all of them: students of the app alone (a
    stranger's comment never gets here) who agreed to the policy that says so (CONSENT_FCH in their version; staff
    too), not banned, comments still in Telegram; a deleted account's rows went with it. Rows are kept either way: a
    face shows once its owner agrees. A face is an avatar and nothing more (no id, no name: who is there, not a list)."""
    from .account import CONSENT_FCH  # here: account imports this module
    if not ids:
        return {}
    got = rows(con, f"""SELECT f.post_id, {PERSON_COLS} FROM (SELECT post_id, user_id, ROW_NUMBER() OVER
        (PARTITION BY post_id ORDER BY MAX(at) DESC, user_id) AS n FROM fchan_comments WHERE gone = 0 AND post_id IN ({','.join('?' * len(ids))})
        AND user_id IN (SELECT u.id FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.banned_at IS NULL
            AND (instr(s.consent_version, ?) > 0 OR s.consent_version = 'staff' OR u.role IN ('admin', 'moderator')))
        GROUP BY post_id, user_id) f
        JOIN users u ON u.id = f.user_id LEFT JOIN students s ON s.user_id = u.id WHERE f.n <= ? ORDER BY f.post_id, f.n""", *ids, CONSENT_FCH, FACES)
    out: dict[int, list[dict]] = {}
    for r in got:
        # name: one letter, the avatar's fallback without a photo (the name the app shows, its first letter)
        out.setdefault(r["post_id"], []).append({"avatar": avatar_of(r), "name": (shown_name(r) or "?")[:1].upper()})
    return out


def _top(raw: str | None) -> list[dict]:
    """The three biggest reactions, as Telegram shows them first."""
    got = json.loads(raw) if raw else {}
    return [{"emoji": k, "n": n} for k, n in sorted(got.items(), key=lambda kv: -kv[1])[:3]]


def reserve(con, v: Viewer, body: dict) -> int:
    """A new post, held ('check') before the AI is asked, the day's allowance counted in the same transaction (posts
    sent at the same moment can't all pass it, nor all cost the AI a look). settle() puts the verdict on it."""
    need_student(v)
    anon = body.get("anon", False)
    if not isinstance(anon, bool):
        raise ApiError("bad_input")
    text = _clean(body.get("body"))
    with tx(con):
        n, last = one(con, "SELECT COUNT(*), MAX(created_at) FROM fchan_posts WHERE user_id = ? AND created_at > ?", v.id, _now() - 86400)
        if n >= POSTS_A_DAY or last and last > _now() - POST_GAP:
            raise ApiError("rate_limited", "posts")
        sign = None if anon else signature(one(con, PERSON + " WHERE u.id = ?", v.id))
        return con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at, sign) VALUES (?, ?, ?, 'held', 'check', ?, ?)",
                           (v.id, text, int(anon), _now(), sign)).lastrowid


def signature(p) -> str:
    """A signed post's name in the channel, fixed as it's written: the first name and last initial, a nick or not (the
    nick rule, owner Nov 2: the app's feed shows the nick, the channel the name; posts signed with a nick before it keep
    theirs). Escaped when sent."""
    return short_name(p)


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


def _unpost(con, p, why: str, delay: int = 0) -> None:
    """Its channel message (if it went out) to the bot's round: deleted there, or edited to a template."""
    if p["tg_msg"]:
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, ?, ?)", (p["tg_msg"], why, _now() + delay))


def delete(con, v: Viewer, pid: int) -> None:
    """The author takes it down: the words wiped at once, the channel message after it; a wordless row stays for the
    day's count (deleting can't buy another post)."""
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND user_id = ? AND status != 'gone'", pid, v.id)
        if not p:
            raise ApiError("not_found")
        _unpost(con, p, "author")
        con.execute("UPDATE fchan_posts SET status = 'gone', body = '', sign = NULL, why = NULL, tg_msg = NULL WHERE id = ?", (pid,))


def unpost_account(con, uid: int) -> None:
    """A deleted account's published posts leave the channel (account.delete_me, before the rows cascade away). The
    anonymous ones each at a random moment within 3 days (the privacy policy says so): gone all in one second together
    with a named one, they'd tell the channel whose they were, and that they share an author."""
    for p in rows(con, "SELECT tg_msg, anon FROM fchan_posts WHERE user_id = ? AND tg_msg > 0", uid):
        at = _now() + (secrets.randbelow(UNPOST_SPREAD) if p["anon"] else 0)
        con.execute("INSERT OR IGNORE INTO tg_unpost (msg_id, why, at) VALUES (?, 'author', ?)", (p["tg_msg"], at))


# ---- the bot's side (tgc.py): what to send, what was sent, what to take down

def to_send(con) -> list:
    """Live posts not in the channel yet, oldest first, with their signature: the one fixed when written (signature(),
    never a @username) or the anonymous line."""
    return [(p["id"], p["body"], _sign(con, p)) for p in rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND tg_msg IS NULL ORDER BY id LIMIT 5")]


def anon_sign(body: str) -> str:
    """An anonymous post's signature, short and in the post's own script (owner, Nov 2): "Anon" in Russian and Kazakh
    alike for any Cyrillic, else English."""
    return "\u0410\u043d\u043e\u043d\u0438\u043c" if re.search("[\u0400-\u04ff]", body or "") else "Anonymous"


def _sign(con, p) -> str:
    """The post's signature in the channel (its last line, after the dash): the one fixed when written, or the anonymous
    line (the channel speaks Russian). A post from before signatures were kept: the short name, as it was signed then."""
    if p["anon"]:
        return anon_sign(p["body"])
    if p["sign"]:
        return p["sign"]
    who = one(con, PERSON + " WHERE u.id = ?", p["user_id"])
    return short_name(who) if who else "?"


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
    held as lost since) is in the channel after all. Its message id kept, so the author's delete and a take-down reach
    it; it was live when sent, so live again. Matched by the whole text as the copy shows it, in any format the bot
    used (a send lost across a deploy): the words, an empty line and "— name" (tgc.post_tick's, its italic gone; also
    the plain one before Nov 2), or the signature line first, an empty one, the words (bold gone; Nov 2 for a day);
    and only when exactly one post matches and no post holds that message yet:
    another student's same words must never become this one's (review)."""
    if one(con, "SELECT 1 FROM fchan_posts WHERE tg_msg = ?", msg_id):
        return
    hits = [p["id"] for p in rows(con, """SELECT * FROM fchan_posts WHERE (status = 'live' AND tg_msg = 0 OR status = 'held' AND why = 'lost')
            AND ? LIKE '%' || body || '%'""", text) if text in (f"{_sign(con, p)}\n\n{p['body']}", f"{p['body']}\n\n— {_sign(con, p)}")]
    if len(hits) == 1:
        con.execute("UPDATE fchan_posts SET status = 'live', why = NULL, tg_msg = ? WHERE id = ?", (msg_id, hits[0]))


RULES_LATE = 7 * 86400  # a post older than this gets no first comment (its copy never came: no group linked, updates lost)


def rules_due(con) -> list[tuple[int, int]]:
    """Live posts in the channel whose copy reached the group (tgc.gate maps it, fchcopy:<channel message>, the forum
    channel's alone) and that have no first comment of the bot's yet: (post, the copy's id in the group). Whichever
    comes first, the copy or the send's answer, the round after both finds it. rules_for is the channel message it was
    written under: a post brought back (a new message) gets one again."""
    return [(p[0], int(p[1])) for p in rows(con, """SELECT p.id, m.value FROM fchan_posts p JOIN meta m ON m.key = 'fchcopy:' || p.tg_msg
        WHERE p.status = 'live' AND p.tg_msg > 0 AND p.rules_for IS NOT p.tg_msg AND p.created_at > ? ORDER BY p.id LIMIT 5""", _now() - RULES_LATE)]


def copied(con, msg_id: int, copy: int) -> None:
    """A forum channel message's copy in the group (tgc.gate, the sender checked): never another channel's same number."""
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"fchcopy:{msg_id}", str(copy)))


RULES_TRIES = 3  # a 400 that isn't "the copy is gone" (rights, a setup slip): tried again, this often, within a day


def rules_retry(con, pid: int) -> bool:
    """One more failed try of a post's first comment: True to try again next round (released), False to give up."""
    key = f"fchrules:{pid}"
    n, first = map(int, ((one(con, "SELECT value FROM meta WHERE key = ?", key) or ["0 " + str(_now())])[0]).split())
    if n + 1 < RULES_TRIES and first > _now() - 86400:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, f"{n + 1} {first}"))
        rules_unclaim(con, pid)
        return True
    con.execute("DELETE FROM meta WHERE key = ?", (key,))
    return False


def rules_claim(con, pid: int) -> bool:
    return con.execute("UPDATE fchan_posts SET rules_for = tg_msg WHERE id = ? AND tg_msg > 0 AND rules_for IS NOT tg_msg", (pid,)).rowcount > 0


def rules_unclaim(con, pid: int) -> None:
    con.execute("UPDATE fchan_posts SET rules_for = NULL WHERE id = ?", (pid,))


def rules_sent(con, pid: int, msg_id: int) -> None:
    """The first comment's id in the group: the Forum tab's link opens the comments there (?comment=)."""
    con.execute("UPDATE fchan_posts SET rules_msg = ? WHERE id = ?", (msg_id, pid))
    con.execute("DELETE FROM meta WHERE key = ?", (f"fchrules:{pid}",))


def commented(con, root: int, msg_id: int, tg: int) -> None:
    """A student's comment (msg_id in the group) in the thread under this group copy (tgc.gate): counted on the forum
    post it copies, if it is one, once per message (a batch replayed after a restart counts nothing twice), his face
    kept for the card. ponytail: a comment its author deletes in Telegram stays counted (the Bot API never says); a
    report's deletion leaves (migration 107's trigger); fine for a hint. A LIKE over meta per comment; an index if it grows"""
    with tx(con):
        p = one(con, """SELECT id FROM fchan_posts WHERE tg_msg > 0 AND tg_msg =
            (SELECT CAST(substr(key, 9) AS INTEGER) FROM meta WHERE key LIKE 'fchcopy:%' AND value = ?)""", str(root))
        u = one(con, "SELECT id FROM users WHERE tg_id = ?", tg)
        if p and u and con.execute("INSERT OR IGNORE INTO fchan_comments (msg_id, post_id, user_id, at) VALUES (?, ?, ?, ?)",
                                   (msg_id, p["id"], u["id"], _now())).rowcount:
            con.execute("UPDATE fchan_posts SET comments = comments + 1 WHERE id = ?", (p["id"],))


def reacted(con, upd: dict) -> None:
    """Telegram's message_reaction_count on a channel post (the bot is the channel's admin): the post's reactions now,
    {"👍": 3, "custom:<id>": 1, "paid": 2}, replacing the last ones (Telegram sends totals, a few minutes apart)."""
    out = {}
    for r in upd.get("reactions") or []:
        ty = r.get("type") or {}
        key = ty.get("emoji") if ty.get("type") == "emoji" else f"custom:{ty.get('custom_emoji_id')}" if ty.get("type") == "custom_emoji" else ty.get("type")
        if key and isinstance(r.get("total_count"), int) and r["total_count"] > 0:
            out[str(key)[:64]] = r["total_count"]
    con.execute("UPDATE fchan_posts SET reactions = ? WHERE tg_msg = ? AND tg_msg > 0",
                (json.dumps(out, ensure_ascii=False) if out else None, int(upd.get("message_id") or 0)))


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
        root = one(con, "SELECT value FROM meta WHERE key = ?", f"fchcopy:{key.split(':')[1]}")  # the forum channel's copy alone
        if root:
            out.append((key, int(root[0])))
        elif int(at) < _now() - 7 * 86400:
            out.append((key, None))
    return out


def copy_done(con, key: str, root: int | None) -> None:
    con.execute("DELETE FROM meta WHERE key IN (?, ?, ?)", (key, f"tgcpost:{root}", f"fchcopy:{key.split(':')[1]}"))


def unposted(con, msg_id: int) -> None:
    """Out of the channel: a taken-down post forgets its message (a Bring back is a new one)."""
    con.execute("DELETE FROM tg_unpost WHERE msg_id = ?", (msg_id,))
    con.execute("DELETE FROM meta WHERE key = ?", (f"fchmoved:{msg_id}",))
    con.execute("UPDATE fchan_posts SET tg_msg = NULL, rules_msg = NULL, comments = 0 WHERE tg_msg = ? AND status = 'hidden'", (msg_id,))


# ---- moderators: held posts, recent live ones; the owner's reveal

def mod_queue(con, v: Viewer) -> dict:
    """What waits (oldest first) and what went out this week (newest first, to take one down). Named posts show the
    author's name; anonymous ones show nobody, to moderators too."""
    _mod(v)
    # 'check' is also the AI's look under way (seconds): shown once it's clearly over (no answer, or the server restarted)
    held = rows(con, "SELECT * FROM fchan_posts WHERE status = 'held' AND (why != 'check' OR created_at < ?) ORDER BY id", _now() - 60)
    live = rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND created_at > ? ORDER BY id DESC LIMIT 50", _now() - MOD_RECENT)
    # removed by a moderator this week (by the take-down's audit line, newest first): the way back for a wrong call
    removed = rows(con, """SELECT p.*, MAX(a.at) AS gone_at FROM fchan_posts p
                           JOIN audit_log a ON a.target = 'fchan:' || p.id AND a.action = 'fchan_hide'
                           WHERE p.status = 'hidden' AND p.why = 'moderator' GROUP BY p.id HAVING gone_at > ?
                           ORDER BY gone_at DESC LIMIT 50""", _now() - MOD_RECENT)
    ids = {p["user_id"] for p in held + live + removed if not p["anon"]}
    people = {p["id"]: person_ref(p) for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)} if ids else {}
    shape = lambda p: _shape(p) | {"why": p["why"], "author": None if p["anon"] else people.get(p["user_id"])}  # noqa: E731
    return {"held": [shape(p) for p in held], "live": [shape(p) for p in live],
            "removed": [shape(p) | {"undo": _pending(con, p["tg_msg"])} for p in removed]}


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
            # its message stays a minute (UNDO_WINDOW), kept on the row: Undo puts it back as it was, comments and all
            _unpost(con, p, "moderator", UNDO_WINDOW)
            con.execute("UPDATE fchan_posts SET status = 'hidden', why = 'moderator', tg_msg = NULLIF(tg_msg, 0) WHERE id = ?", (pid,))
        log_action(con, v.id, "fchan_release" if ok else "fchan_hide", f"fchan:{pid}")


def _pending(con, msg_id) -> bool:
    """Its message is still in the channel, its delete not due yet (the undo minute, or a retry after a failed one)."""
    return bool(msg_id) and one(con, "SELECT 1 FROM tg_unpost WHERE msg_id = ? AND at > ?", msg_id, _now()) is not None


def mod_restore(con, v: Viewer, pid: int) -> None:
    """A moderator's take-down undone. Inside the minute (its message still up): Undo, the pending delete dropped and the
    message kept, comments and all. Later: live with no message, the bot's round publishes it anew (the old one was
    deleted, or edited to the template). Same rules as mod_decide: not their own, audited."""
    _mod(v)
    with tx(con):
        p = one(con, "SELECT user_id, tg_msg FROM fchan_posts WHERE id = ? AND status = 'hidden' AND why = 'moderator'", pid)
        if not p:
            raise ApiError("not_found")
        if p["user_id"] == v.id:
            raise ApiError("forbidden")
        # only a delete not yet due is dropped: one the bot already took is under way, so the post goes out anew
        kept = bool(p["tg_msg"]) and con.execute("DELETE FROM tg_unpost WHERE msg_id = ? AND at > ?", (p["tg_msg"], _now())).rowcount > 0
        con.execute("UPDATE fchan_posts SET status = 'live', why = NULL, tg_msg = ? WHERE id = ?", (p["tg_msg"] if kept else None, pid))
        log_action(con, v.id, "fchan_undo" if kept else "fchan_restore", f"fchan:{pid}")


def mod_republish(con, v: Viewer, pid: int) -> None:
    """A live post sent anew (its channel message deleted by hand: the Bot API never says): the old message goes in the
    bot's round (already gone: fine; too old to delete: edited to say it moved), the post, same id, goes out as a new
    message the normal way, the bot's first comment under it. Audited."""
    _mod(v)
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND status = 'live' AND tg_msg > 0", pid)
        if not p:
            raise ApiError("not_found")  # not out yet (or on its way): the round sends it anyway
        _unpost(con, p, "moderator")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, '1')", (f"fchmoved:{p['tg_msg']}",))
        con.execute("UPDATE fchan_posts SET tg_msg = NULL, rules_msg = NULL, comments = 0 WHERE id = ?", (pid,))
        log_action(con, v.id, "fchan_republish", f"fchan:{pid}")


def moved(con, msg_id: int) -> bool:
    """This message's post went out anew (mod_republish): too old to delete, it says so, not "removed"."""
    return one(con, "SELECT 1 FROM meta WHERE key = ?", f"fchmoved:{msg_id}") is not None


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
