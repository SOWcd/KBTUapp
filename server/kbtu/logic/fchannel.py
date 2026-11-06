"""The forum channel (owner, Nov 1: replaces the in-app student forum). A Microsoft-verified student writes a post in
the app, under their name or anonymously; the bot publishes it in the public channel (FORUM_CHANNEL), where the
comments happen in its Telegram discussion group (tgc.py). One post a day per student. The AI looks first: its exact
OK publishes at once (the bot's next round, seconds); anything else, or an anonymous post aimed at a person, waits for
a moderator. Plain text only: no links, @mentions or phone numbers (the bot is the publisher, nobody pings or doxes
through it). The author deletes, a moderator takes down, a deleted account's posts leave too: all through tg_unpost,
which keeps only the channel's message id. Only the owner reveals an anonymous author, each look in the audit log."""
from __future__ import annotations

import difflib
import json
import re
import secrets
import unicodedata

from .. import texts
from . import profiles
from ..db import tx

from .core import ApiError, PERSON, PERSON_COLS, Viewer, avatar_of, log_action, need_student, one, person_ref, rows, short_name, shown_name

BODY_MAX = 1000
POSTS_A_GAP, POST_GAP = 2, 10 * 60  # a pace: at most two posts in any ten minutes (owner, Nov 6: no daily cap, nobody hit it)
CHANNEL_AN_HOUR = 20     # live posts in the channel an hour; past it, a moderator lets the next ones out (a burst can't flood it)
MOD_RECENT = 7 * 86400   # live posts the moderators' list shows, to take one down
UNDO_WINDOW = 60         # a moderator's take-down leaves the channel after it: Undo inside keeps the message and its comments
# what Telegram turns into a link or a ping even in plain text, looked for in the text NFKC-normalised (fullwidth
# letters and dots fold to ASCII; the ideographic dots count as dots): a scheme, www., a domain (Latin or IDN labels,
# a Latin TLD or a Cyrillic one Telegram links), an e-mail, @handle, a phone or a card number (+..., a Kazakh 8/7 7xx
# number; ten digits or more in any spacing: _long_number). ponytail: any "word.letters" counts as a domain ("node.js"
# too), since Telegram knows every Latin TLD; a TLD list if students trip on it. The app mirrors these as you type
# (web/src/lib/forumRules.ts); tests/fchannel_rules.json holds the cases both must agree on
_CYR_TLD = "\u0440\u0444|\u0440\u0443\u0441|\u043e\u043d\u043b\u0430\u0439\u043d|\u0441\u0430\u0439\u0442|\u043e\u0440\u0433|\u043a\u043e\u043c|\u043c\u043e\u0441\u043a\u0432\u0430|\u049b\u0430\u0437|\u0431\u0435\u043b|\u0443\u043a\u0440|\u0441\u0440\u0431|\u0434\u0435\u0442\u0438"
LINKY = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://|\bwww\.|\b[^\W_][\w-]*(\.[^\W_][\w-]*)*\.(?:[a-z]{2,}|" + _CYR_TLD + r")\b|@\w{3,}"
                   r"|\+\d[\d\s().-]{7,}\d|\b[78][\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b)")
# a link disguised so Telegram won't make it one but a reader still can (Nov 4: "https ://www .instagram. com/reel/..."
# went out): a scheme or www. with spaces, a TLD before a slash, a known site's name with a spaced dot, "dot com",
# a bracketed dot ("x[.]com" reads as a dot, then LINKY). ponytail: lists, not every TLD; the AI is told too
_TLDS = "com|ru|kz|org|net|io|me|ly|gg|app|xyz|link|site|info|tv|co|be|to|dev|ai|su|uk|us|cc|pro|online|store|shop"
_SITES = "t|telegram|tg|instagram|insta|tiktok|youtube|youtu|wa|vk|discord|x|twitter|facebook|fb|threads|linktr|bit|clck|vm"
SPACED = re.compile(r"(?i)\b[a-z]{3,6}\s*:\s*/\s*/|\bwww\s*[.,]|[.,]\s*(?:" + _TLDS + r")\s*/|\b(?:" + _SITES + r")\s*[.,]\s*(?:"
                    + _TLDS + r")\b|\b(?:dot|\u0442\u043e\u0447\u043a\u0430|\u0442\u0447\u043a)\s*(?:" + _TLDS + r")\b")
BRACKET_DOT = re.compile(r"(?i)\s*[\[({]\s*(?:\.|dot|\u0442\u043e\u0447\u043a\u0430)\s*[\])}]\s*")
DIGITS = re.compile(r"\d(?:[\s-]?\d){9,}")  # ten digits or more, one space or dash between any two
SUM = re.compile(r"[1-9]\d{0,2}(?:\s\d{3})*\s\d00")  # a sum in thousands, round to the hundred ("15 000", "12 500", "1 500 000")
MONEY = re.compile(r"\s*(?:\u20b8|\u0442\u0433|\u0442\u0435\u043d\u0433|tg\b|kzt\b)", re.I)  # tenge right after it


def _long_number(s: str) -> bool:
    """A phone or a card: ten digits or more in a run, unless it is a price: one round sum or a range of two ("10 000-15 000
    \u0442\u0433", Nov 3), each under ten digits, twelve at most in all (a card is 16), with the tenge right after. A date's dots and a time's colons break a run anyway.
    ponytail: a phone shaped as such a range with tenge after it ("8 700-1 234 500 \u0442\u0433") still passes; the AI looks too"""
    for m in DIGITS.finditer(s):
        parts = m[0].split("-")
        if not (len(parts) <= 2 and sum(c.isdigit() for c in m[0]) <= 12 and all(SUM.fullmatch(x) and sum(c.isdigit() for c in x) < 10 for x in parts) and MONEY.match(s, m.end())):
            return True
    return False


DOTS = str.maketrans({"\u3002": ".", "\uff61": ".", "\uff0e": "."})
FILLERS = {"\u034f", "\u115f", "\u1160", "\u3164", "\uffa0"}  # invisible letters a model reads and a moderator doesn't see
ZWJ = "\u200d"   # kept in the words (emoji families, flags); out of the text the link check reads
SIGNED = "\u2212\u2500\u2501\u2796\u30fc"  # with every dash (Pd), what reads as one: minus, box lines, heavy minus, the long vowel mark. A last line like a "- Name L." signature (the bot signed so until Nov 2; still reads as one) (read NFKC: fullwidth, small dashes fold)


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
    seen = BRACKET_DOT.sub(".", unicodedata.normalize("NFKC", s.replace(ZWJ, "")).translate(DOTS))
    if LINKY.search(seen) or SPACED.search(seen) or _long_number(seen):
        raise ApiError("bad_input", "links")
    last = unicodedata.normalize("NFKC", s.rsplit("\n", 1)[1].replace(ZWJ, "")).lstrip() if "\n" in s else ""
    if last and (unicodedata.category(last[0]) == "Pd" or last[0] in SIGNED):
        raise ApiError("bad_input", "signature")
    return s


# Meaningless posts (owner, Nov 2: "\u0444\u0440\u0440\u0440" went out): a cheap gate before the AI. The letters counted with every run of
# one letter squeezed to one ("\u0444\u0440\u0440\u0440" is "\u0444\u0440"), a word is two letters or more with a vowel in it; a post needs two
# words ("who is here?"), or one of ten letters. Then not the same as one of my posts this week
# (near: SequenceMatcher on those squeezed letters). What gets past and is still noise, the AI calls NOISE (ai.py).
VOWELS = set("aeiouy\u0430\u0435\u0451\u0438\u043e\u0443\u044b\u044d\u044e\u044f\u04d9\u04e9\u04af\u04b1\u0456")  # Latin, Russian, Kazakh
SAME_DAYS, SAME_AT = 7, 0.9


def _squeeze(s: str) -> list[str]:
    """The post's words as letters only, lower case, each run of one letter as one."""
    return [re.sub(r"(.)\1+", r"\1", w) for w in re.findall(r"[^\W\d_]+", s.lower())]


def _meaningful(s: str) -> bool:
    words = _squeeze(s)
    letters = sum(map(len, words))
    real = sum(1 for w in words if len(w) >= 2 and VOWELS & set(w))
    return real >= 2 or real >= 1 and letters >= 10  # "who is here?" passes; one short word ("hello", "\u0444\u0440\u0440\u0440") is a comment, not a post


def _repeat(con, uid: int, text: str) -> bool:
    """The same words (or nearly) as one of my posts this week, still up or waiting."""
    me = " ".join(_squeeze(text))
    return any(difflib.SequenceMatcher(None, me, " ".join(_squeeze(p["body"]))).ratio() >= SAME_AT for p in rows(con,
        "SELECT body FROM fchan_posts WHERE user_id = ? AND status != 'gone' AND created_at > ? ORDER BY id DESC LIMIT 20", uid, _now() - SAME_DAYS * 86400))


def _nick(p) -> list[int] | None:
    """An anonymous post's nick as indexes (the app words it in its language); None for one from before nicks."""
    return [p["nick_a"], p["nick_n"]] if p["anon"] and p["nick_a"] is not None else None


def _shape(p) -> dict:
    return {"id": p["id"], "body": p["body"], "anon": bool(p["anon"]), "nick": _nick(p), "status": p["status"], "at": p["created_at"]}


def mine(con, v: Viewer) -> list[dict]:
    """My posts, newest first: published, under review, removed (the ones I deleted are gone)."""
    need_student(v)
    return [_shape(p) for p in rows(con, "SELECT * FROM fchan_posts WHERE user_id = ? AND status != 'gone' ORDER BY id DESC LIMIT 30", v.id)]


FEED_MAX = 50  # a page; the next one by the cursor (before: the last id shown), "Show earlier" in the app


def feed(con, v: Viewer, before: int | None = None) -> list[dict]:
    """The Forum tab: what the channel shows (live posts the bot sent), newest first, signed as there (the name, or the
    anonymous line in the channel's language), plus my own posts on their way or removed. Never whose an anonymous post
    is: no user id, no person, no avatar, for every viewer (staff too), and `mine` true on my own rows alone. A signed
    one carries its author (person: the app's avatar, name with the nick first, and profile), read once for all rows; its
    signature is the one it went out with (the app shows `person` instead; `sign` for an author no longer here).
    One order, the channel's own (owner, Nov 3): by the message's id in the channel, so a post a moderator let out late
    sits where Telegram shows it, not where it was written; mine not out yet on top. before: the page under that message."""
    cursor = before if isinstance(before, int) and before > 0 else (1 << 63) - 1
    # Each side contributes at most a page: the public side walks its message index, instead of sorting the whole
    # channel's history on every poll. UNION deduplicates my live posts before the final page limit.
    ps = rows(con, """SELECT * FROM fchan_posts WHERE id IN (
        SELECT id FROM (SELECT id FROM fchan_posts WHERE status = 'live' AND tg_msg > 0 AND tg_msg < ?
            ORDER BY tg_msg DESC, id DESC LIMIT ?)
        UNION
        SELECT id FROM (SELECT id FROM fchan_posts WHERE user_id = ? AND status != 'gone'
            AND COALESCE(NULLIF(tg_msg, 0), 1 << 62) < ?
            ORDER BY COALESCE(NULLIF(tg_msg, 0), 1 << 62) DESC, id DESC LIMIT ?)
        ) ORDER BY COALESCE(NULLIF(tg_msg, 0), 1 << 62) DESC, id DESC LIMIT ?""",
              cursor, FEED_MAX, v.id, cursor, FEED_MAX, FEED_MAX)
    ids = {p["user_id"] for p in ps if not p["anon"]}
    who = {p["id"]: p for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)} if ids else {}
    faces = _faces(con, [p["id"] for p in ps if p["comments"]]) if v.student else {}  # people for students alone (a guest: none)
    hot = _hot(con, [p["id"] for p in ps if p["comments"] >= HOT]) | _talked(con, [p["id"] for p in ps if p["status"] == "live" and p["tg_msg"]])
    out = []
    for p in ps:
        a = None if p["anon"] else who.get(p["user_id"])  # an anonymous row never reads its author's person
        out.append({"id": p["id"], "body": p["body"], "status": p["status"], "at": p["created_at"], "msg": p["tg_msg"] or None, "anon": bool(p["anon"]), "nick": _nick(p),
             "sign": _anon_sign(p) if p["anon"] else p["sign"] or (short_name(a) if a else "?"), "person": person_ref(a) if a else None,
             "mine": p["user_id"] == v.id,
             # the comments: the students' count, and the bot's first comment (the link opens the thread there)
             "comments": p["comments"], "thread": p["rules_msg"] if p["tg_msg"] else None,
             # Telegram's side of the post: the latest commenters' faces (app students only), its top reactions
             "faces": faces.get(p["id"], []), "reactions": _top(p["reactions"]),
             "hot": p["id"] in hot,  # being discussed (one label, in place): a busy hour, or several people over the day
             # my own held post: the AI passed it to a person (why != 'check': not still being checked); nobody else's
             "human": p["user_id"] == v.id and p["status"] == "held" and p["why"] != "check"})
    return out


HOT = 5  # comments in the last hour that make a post "being discussed" (the feed's label)


def _hot(con, ids: list[int]) -> set[int]:
    """The posts with HOT or more students' comments (still up) in the last hour, one query for all of them."""
    if not ids:
        return set()
    return {r[0] for r in rows(con, f"""SELECT post_id FROM fchan_comments WHERE gone = 0 AND at > ? AND post_id IN ({','.join('?' * len(ids))})
        GROUP BY post_id HAVING COUNT(*) >= ?""", _now() - 3600, *ids, HOT)}


TALK_MIN, TALK_AGE = 3, 86400  # "being discussed" over the day too: TALK_MIN people or more (not its author) commenting


def _talked(con, ids: list[int]) -> set[int]:
    """The posts TALK_MIN or more distinct people commented on in the last day, one query for all of them: comments still
    up; a signed post's author left out (it takes others). An anonymous one counts everyone: leaving its author out
    would tell, by the label, whether a commenter is the author (review, Nov 3). ponytail: so its author can pad it by
    one; fine for a hint"""
    if not ids:
        return set()
    return {r[0] for r in rows(con, f"""SELECT p.id FROM fchan_posts p JOIN fchan_comments c ON c.post_id = p.id
        WHERE p.id IN ({','.join('?' * len(ids))}) AND c.gone = 0 AND c.at > ? AND (p.anon = 1 OR c.user_id != p.user_id)
        GROUP BY p.id HAVING COUNT(DISTINCT c.user_id) >= ?""", *ids, _now() - TALK_AGE, TALK_MIN)}


FACES = 10  # the newest commenters a card has room for at most (the card shows as many as fit)


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
    """A new post, held ('check') before the AI is asked, the pace counted in the same transaction (posts
    sent at the same moment can't all pass it, nor all cost the AI a look). settle() puts the verdict on it."""
    need_student(v)
    anon = body.get("anon", False)
    if not isinstance(anon, bool):
        raise ApiError("bad_input")
    text = _clean(body.get("body"))
    if not _meaningful(text):
        raise ApiError("bad_input", "short")
    with tx(con):
        # the pace: two in any ten minutes; a post the AI called noise doesn't count (its author rewrites it now: told
        # why, ChannelCompose gives the words back); an ad does, and so does one I deleted myself (owner, Nov 6: a
        # delete refunds nothing, else post-delete-post floods the channel)
        n = one(con, "SELECT COUNT(*) FROM fchan_posts WHERE user_id = ? AND created_at > ? AND why IS NOT 'noise'", v.id, _now() - POST_GAP)[0]
        if n >= POSTS_A_GAP:
            raise ApiError("rate_limited", "posts")
        if _repeat(con, v.id, text):
            raise ApiError("bad_input", "duplicate")
        sign = None if anon else signature(one(con, PERSON + " WHERE u.id = ?", v.id))
        a, n = pick_nick(con) if anon else (None, None)
        return con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at, sign, nick_a, nick_n) VALUES (?, ?, ?, 'held', 'check', ?, ?, ?, ?)",
                           (v.id, text, int(anon), _now(), sign, a, n)).lastrowid


NICK_FRESH = 800  # a new nick is none of the last this many anonymous posts' (review: no false links, no drawing another's)


def pick_nick(con) -> tuple[int, int]:
    """A fresh random nick for an anonymous post (texts.NICK_*): secrets over the ones no recent anonymous post holds, the
    same for every author; nothing of the person goes in. ponytail: past NICK_FRESH posts an old one's nick can return"""
    taken = {(r[0], r[1]) for r in rows(con, "SELECT nick_a, nick_n FROM fchan_posts WHERE anon = 1 AND nick_a IS NOT NULL ORDER BY id DESC LIMIT ?", NICK_FRESH)}
    free = [(a, n) for a in range(len(texts.NICK_ADJ)) for n in range(len(texts.NICK_NOUN)) if (a, n) not in taken]
    return secrets.choice(free)


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
            if verdict in ("noise", "ad"):  # no message in it, or an ad: refused, its author told (the route), the words wiped
                con.execute("UPDATE fchan_posts SET status = 'gone', why = ?, body = '', sign = NULL, refused = ? WHERE id = ?",
                            (verdict, _refused(pid, p["body"]), pid))
                return _shape(one(con, "SELECT * FROM fchan_posts WHERE id = ?", pid))
            if verdict == "ok":
                busy = one(con, "SELECT COUNT(*) FROM fchan_posts WHERE status = 'live' AND created_at > ?", _now() - 3600)[0] >= CHANNEL_AN_HOUR
                status, why = ("held", "busy") if busy else ("live", None)
            else:
                status, why = "held", {"person": "person", "flag": "ai"}.get(verdict or "", "check")
            con.execute("UPDATE fchan_posts SET status = ?, why = ? WHERE id = ?", (status, why, pid))
    return _shape(one(con, "SELECT * FROM fchan_posts WHERE id = ?", pid))


def _refused(pid: int, text: str) -> str:
    """A refused post's words as a hash (the words are wiped): the words given back later must be these (review: an
    appeal with other words reached a moderator labelled with the AI's word on the first ones)."""
    import hashlib
    return hashlib.sha256(f"{pid}\0{text}".encode()).hexdigest()


APPEALS_A_DAY = 3      # an author's "Send to a moderator" a day (owner, Nov 4): a human's time is the scarce thing
APPEAL_WINDOW = 3600   # a refusal can be appealed this long after it (the app asks right away; a reload loses it anyway)


def appeals_left(con, uid: int) -> int:
    """My appeals left today: the refused posts I sent to a moderator in the last day (a deleted one still counts)."""
    return APPEALS_A_DAY - one(con, "SELECT COUNT(*) FROM fchan_posts WHERE user_id = ? AND appealed_at > ?", uid, _now() - 86400)[0]


def appeal(con, v: Viewer, pid: int, body: dict) -> dict:
    """The AI refused my post (noise, an ad) and I think it's wrong: the post waits for a moderator like any held one
    (mod_queue, the Admin inbox; why stays the AI's word), who publishes or declines it; I hear as for any held post.
    The words come back with the appeal (the refusal wiped them) and must be the ones the AI read (their hash); the
    cheap gates run again. Not the AI again: it already said no."""
    need_student(v)
    text = _clean(body.get("body"))
    if not _meaningful(text):
        raise ApiError("bad_input", "short")
    with tx(con):
        p = one(con, """SELECT * FROM fchan_posts WHERE id = ? AND user_id = ? AND status = 'gone' AND why IN ('noise', 'ad')
                        AND appealed_at IS NULL AND created_at > ?""", pid, v.id, _now() - APPEAL_WINDOW)
        if not p:
            raise ApiError("not_found")
        if p["refused"] != _refused(pid, text):
            raise ApiError("bad_input", "changed")
        if appeals_left(con, v.id) <= 0:
            raise ApiError("rate_limited", "appeals")
        if _repeat(con, v.id, text):
            raise ApiError("bad_input", "duplicate")
        sign = None if p["anon"] else signature(one(con, PERSON + " WHERE u.id = ?", v.id))
        con.execute("UPDATE fchan_posts SET status = 'held', body = ?, sign = ?, appealed_at = ?, refused = NULL WHERE id = ?", (text, sign, _now(), pid))
        # the moderators hear: a template with the count and a button into Admin, at most once an hour each (the ref);
        # all of them, an appealing moderator too (review: the one who got no notice was the anonymous author)
        from .tgcomments import _mods
        notify_staff(con, _mods(con), "fch_appeal", f"fq:{_now() // 3600}")
    return _shape(one(con, "SELECT * FROM fchan_posts WHERE id = ?", pid))


# The AI's reason for a refusal (ai.explain, phase 2) is asked apart from the post (owner, Nov 4: the outcome shows at
# once, the reason comes in when ready): my own refused or held post or reply, fresh, once each (explained), so the
# endpoint is no free model for any text. A refused post's words were wiped: the app sends them back (checked as a
# post); a held one's are on the row.
WHY_OF = {"noise": "noise", "ad": "ad", "person": "person", "ai": "flag"}  # the row's why -> the AI's word


def why_post(con, v: Viewer, pid: int, body: dict) -> tuple[str, str]:
    """(the words, the AI's word) for ai.explain; not found if not mine, not refused or held by the AI, stale or asked."""
    need_student(v)
    with tx(con):
        p = one(con, """SELECT * FROM fchan_posts WHERE id = ? AND user_id = ? AND explained IS NULL AND created_at > ?
                        AND (status = 'gone' AND why IN ('noise', 'ad') OR status = 'held' AND why IN ('person', 'ai'))""", pid, v.id, _now() - APPEAL_WINDOW)
        if not p:
            raise ApiError("not_found")
        text = p["body"] or _clean(body.get("body"))
        if p["status"] == "gone" and p["refused"] != _refused(pid, text):  # only the words the AI refused
            raise ApiError("not_found")
        con.execute("UPDATE fchan_posts SET explained = 1 WHERE id = ?", (pid,))
    return text, WHY_OF[p["why"]]


def why_reply(con, v: Viewer, rid: int) -> tuple[str, str]:
    """The same for my reply the AI held (through the post: no user id on a reply)."""
    need_student(v)
    with tx(con):
        r = one(con, """SELECT r.* FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.id = ? AND p.user_id = ?
                        AND r.status = 'held' AND r.why IN ('person', 'ai') AND r.explained IS NULL AND r.created_at > ?""", rid, v.id, _now() - APPEAL_WINDOW)
        if not r:
            raise ApiError("not_found")
        con.execute("UPDATE fchan_replies SET explained = 1 WHERE id = ?", (rid,))
    return r["body"], WHY_OF[r["why"]]


def said(con, table: str, rid: int, got: dict | None) -> None:
    """The AI's validated reason onto its row, for the moderator who decides on it (the Admin queue's reason line)."""
    if got:
        # only while the row still waits (held) or is a fresh refusal: an author's delete during the model's seconds wipes
        # the words, and the reason (it often quotes them) must not land after it (review)
        live = "status = 'held'" if table == "fchan_replies" else "(status = 'held' OR status = 'gone' AND refused IS NOT NULL)"
        con.execute(f"UPDATE {table} SET ai_reason = ? WHERE id = ? AND {live}", (got["reason"], rid))  # table: the route's own literal


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
        _post_off(con, pid)
        con.execute("UPDATE fchan_posts SET status = 'gone', body = '', sign = NULL, why = NULL, tg_msg = NULL, ai_reason = NULL, refused = NULL WHERE id = ?", (pid,))
        _notes_off(con, pid)


def _notes_off(con, pid: int) -> None:
    """The bot's notes to the author about this post (fch_posted, fch_declined): out of the outbox with it, so no row ties
    them to a removed post (a sent one's time would match the channel's)."""
    con.execute("DELETE FROM bot_outbox WHERE kind IN ('fch_posted', 'fch_declined') AND ref IN (?, ?)", (f"fp:{pid}", f"fd:{pid}"))


def resigns(con) -> list:
    """A deleted account's named posts still signed with its name in the channel (account.delete_me): (message, words,
    the deleted account's signature), a few a round; one whose post is gone meanwhile leaves the queue."""
    out = []
    for (k,) in rows(con, "SELECT key FROM meta WHERE key >= 'fch_resign:' AND key < 'fch_resign;' LIMIT 5"):
        p = one(con, "SELECT body, sign FROM fchan_posts WHERE tg_msg = ? AND status = 'live'", int(k[11:]))
        if p:
            out.append((int(k[11:]), p["body"], p["sign"]))
        else:
            resigned(con, int(k[11:]))
    return out


def resigned(con, msg: int) -> None:
    con.execute("DELETE FROM meta WHERE key = ?", (f"fch_resign:{msg}",))


# ---- the bot's side (tgc.py): what to send, what was sent, what to take down

def to_send(con) -> list:
    """Live posts not in the channel yet, oldest first, with their signature: the one fixed when written (signature(),
    never a @username) or the anonymous line."""
    return [(p["id"], p["body"], _sign(con, p)) for p in rows(con, "SELECT * FROM fchan_posts WHERE status = 'live' AND tg_msg IS NULL ORDER BY id LIMIT 5")]


def anon_sign(body: str) -> str:
    """An anonymous post's signature, short and in the post's own script (owner, Nov 2): "Anon" in Russian and Kazakh
    alike for any Cyrillic, else English."""
    return "\u0410\u043d\u043e\u043d\u0438\u043c" if re.search("[\u0400-\u04ff]", body or "") else "Anonymous"


def _anon_sign(p) -> str:
    """An anonymous post's signature: its nick (Russian, the channel's), or "Anon" for one from before nicks."""
    return texts.nick(p["nick_a"], p["nick_n"]) if p["nick_a"] is not None else anon_sign(p["body"])


def _sign(con, p) -> str:
    """The post's signature in the channel (its last line, after the dash): the one fixed when written, or the anonymous
    line (the channel speaks Russian). A post from before signatures were kept: the short name, as it was signed then."""
    if p["anon"]:
        return _anon_sign(p)
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
    if con.execute("UPDATE fchan_posts SET tg_msg = ? WHERE id = ? AND status = 'live' AND tg_msg IN (0, ?)", (msg_id, pid, msg_id)).rowcount:
        # its author hears it went out (a template, to their own chat alone: an anonymous post stays so); once a post, and
        # only after a moderator let it out (owner, Nov 5: the AI's yes is instant, the app already says so)
        a = one(con, """SELECT f.user_id FROM fchan_posts f JOIN users u ON u.id = f.user_id WHERE f.id = ? AND u.tg_id > 0
                        AND EXISTS (SELECT 1 FROM audit_log WHERE action IN ('fchan_release', 'fchan_undo', 'fchan_restore', 'fchan_republish')
                                    AND target = 'fchan:' || f.id)""", pid)
        if a:
            notify(con, a["user_id"], "fch_posted", f"fp:{pid}")
        # its author deleted the account while it went out, signed with the name: the signature rewritten next round
        if one(con, "SELECT 1 FROM fchan_posts f JOIN users u ON u.id = f.user_id WHERE f.id = ? AND f.anon = 0 AND u.tg_id < 0", pid):
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"fch_resign:{msg_id}",))
    else:
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
    report's deletion leaves (migration 107's trigger); fine for a hint. A scan of fchcopy: keys per comment; an index on value if it grows"""
    with tx(con):
        p = one(con, """SELECT id FROM fchan_posts WHERE tg_msg > 0 AND tg_msg =
            (SELECT CAST(substr(key, 9) AS INTEGER) FROM meta WHERE key >= 'fchcopy:' AND key < 'fchcopy;' AND value = ?)""", str(root))
        u = one(con, "SELECT id FROM users WHERE tg_id = ?", tg)
        # Couch critic: a first comment under a post may raise its level (profiles.CRITIC), told like any level
        before = profiles._levels(con, u["id"]) if p and u and profiles.CRITIC_ON else None
        if p and u and con.execute("INSERT OR IGNORE INTO fchan_comments (msg_id, post_id, user_id, at) VALUES (?, ?, ?, ?)",
                                   (msg_id, p["id"], u["id"], _now())).rowcount:
            con.execute("UPDATE fchan_posts SET comments = comments + 1 WHERE id = ?", (p["id"],))
            if before is not None:
                profiles._celebrate(con, u["id"], before)


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
    """What the privacy policy promises: a deleted post's wordless row after its day, a taken-down one after 30 days.
    Every 5 minutes (the bot's round): a DELETE takes the write lock even finding nothing."""
    if not core._once(con, "fch_sweep", str(_now() // 300)):
        return
    # (an appealed one stays its day from the appeal: appeals_left counts it)
    con.execute("DELETE FROM fchan_posts WHERE status = 'gone' AND created_at < ? AND COALESCE(appealed_at, 0) < ? OR status = 'hidden' AND created_at < ?",
                (_now() - 86400, _now() - 86400, _now() - 30 * 86400))
    con.execute("""DELETE FROM bot_outbox WHERE kind IN ('fch_posted', 'fch_declined')
        AND CAST(substr(ref, 4) AS INTEGER) NOT IN (SELECT id FROM fchan_posts)""")  # a swept post's notes too
    # replies deleted, taken down or never decided, out of the group: after the same 30 days (a deleted one is wordless already)
    con.execute("DELETE FROM fchan_replies WHERE status IN ('gone', 'hidden', 'held') AND tg_msg IS NULL AND created_at < ?", (_now() - 30 * 86400,))


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
    for key, at in rows(con, "SELECT key, value FROM meta WHERE key >= 'fchgone:' AND key < 'fchgone;'"):
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
    shape = lambda p: _shape(p) | {"why": p["why"], "aiWhy": p["ai_reason"], "author": None if p["anon"] else people.get(p["user_id"])}  # noqa: E731
    return {"held": [shape(p) for p in held], "live": [shape(p) for p in live],
            "removed": [shape(p) | {"undo": _pending(con, p["tg_msg"])} for p in removed], "replies": reply_mod_queue(con)}


def mod_decide(con, v: Viewer, pid: int, ok: object) -> None:
    """A held post goes out (ok) or is removed; a live one can only be taken down (it leaves the channel)."""
    _mod(v)
    if not isinstance(ok, bool):
        raise ApiError("bad_input")
    with tx(con):
        p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND status IN ('held', 'live')", pid)
        if not p or p["status"] == "live" and ok:  # gone, or published meanwhile: by whom, when the log says
            raise core.decided(con, f"fchan:{pid}") if one(con, "SELECT 1 FROM fchan_posts WHERE id = ?", pid) else ApiError("not_found")
        if p["user_id"] == v.id:  # their own: another moderator decides
            raise ApiError("forbidden")
        if ok:
            con.execute("UPDATE fchan_posts SET status = 'live', why = NULL WHERE id = ?", (pid,))
        else:
            # its message stays a minute (UNDO_WINDOW), kept on the row: Undo puts it back as it was, comments and all
            _unpost(con, p, "moderator", UNDO_WINDOW)
            _post_off(con, pid, UNDO_WINDOW)
            con.execute("UPDATE fchan_posts SET status = 'hidden', why = 'moderator', tg_msg = NULLIF(tg_msg, 0) WHERE id = ?", (pid,))
            if p["status"] == "held":  # declined before it went out: its author hears, after the undo minute (bot.py checks it still is)
                notify(con, p["user_id"], "fch_declined", f"fd:{pid}", after=_now() + UNDO_WINDOW)
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
    p = one(con, "SELECT f.user_id, f.anon, u.tg_id FROM fchan_posts f JOIN users u ON u.id = f.user_id WHERE f.id = ? AND f.status != 'gone'", pid)
    if not p or not p["anon"] or p["tg_id"] < 0:  # a deleted account's: its author is gone, for the owner too (policy, section 7)
        raise ApiError("not_found")
    log_action(con, v.id, "reveal_anon", f"fchan:{pid}")
    return person_ref(one(con, PERSON + " WHERE u.id = ?", p["user_id"]))


# ---- the anonymous author's replies in the comments (Nov 3, .claude/reports/anon-reply/review.md)
# The author of an anonymous post answers under it through the bot, so the answer doesn't carry their Telegram account.
# No comment list in the app (other people's words are never stored): the reply goes to the thread, or to a comment
# whose Telegram link the author pasted, checked against fchan_comments. Its own AI look, then a random wait (the time
# it lands can't be matched to the author's "online"), then the bot sends it once. Stored without a user id: the post
# is the only way to its author (the owner's reveal, account deletion), and the replies go with it.

REPLY_GAP = 10            # seconds between an author's replies (owner, Nov 4: a minute stalled a live talk)
# a post's replies a day: the others' comments under it the bot saw (fchan_comments: students', still up or not; the
# author's own from their account left out, or they could buy replies with them) and REPLIES_MORE on top: as many
# answers as there are people talking, plus a few for the thread (owner, Nov 4; the per-comment cap went)
REPLIES_MORE = 5
# seconds, at random, from the author's tap (the AI's look inside it) to the bot's send. ponytail: owner, Nov 3: 30-120 s
# felt too slow; 5-20 s blurs the moment less (the author's "online" in Telegram and a reply seconds later still line up
# across many replies), the composer warns of it; widen it if timing ever narrows an author down
REPLY_WAIT = (5, 20)
COMMENT_LINK = re.compile(r"(?:https?://)?(?:t|telegram)\.me/(?:s/)?(\w{4,32})/(\d+)/?\?(?:[^#\s]*&)?comment=(\d+)(?:[&#]\S*)?", re.I)


def _wait(base: int | None = None) -> int:
    return (base or _now()) + REPLY_WAIT[0] + secrets.randbelow(REPLY_WAIT[1] - REPLY_WAIT[0] + 1)


def _my_anon_post(con, v: Viewer, pid: int):
    """My anonymous post, in the channel with its copy in the group (the thread to answer in); else not found."""
    p = one(con, "SELECT * FROM fchan_posts WHERE id = ? AND user_id = ? AND anon = 1 AND status = 'live' AND tg_msg > 0", pid, v.id)
    if not p or not one(con, "SELECT 1 FROM meta WHERE key = ?", f"fchcopy:{p['tg_msg']}"):
        raise ApiError("not_found")
    return p


def _reply_shape(r) -> dict:
    """What the author sees of a reply: its words and where it stands (checking, held, soon, sent, removed)."""
    state = ("checking" if r["why"] == "check" else "maybe" if r["why"] == "lost" else "held") if r["status"] == "held" else \
        ("sent" if r["tg_msg"] else "soon") if r["status"] == "live" else "missing" if r["why"] == "missing" else "removed"
    return {"id": r["id"], "body": r["body"], "comment": r["comment_msg"], "state": state, "at": r["created_at"]}


def replies(con, v: Viewer, pid: int) -> list[dict]:
    """My replies under my post, newest first (the author's own view, the only one that ties them to anyone)."""
    need_student(v)
    if not one(con, "SELECT 1 FROM fchan_posts WHERE id = ? AND user_id = ? AND anon = 1", pid, v.id):
        raise ApiError("not_found")
    return [_reply_shape(r) for r in rows(con, "SELECT * FROM fchan_replies WHERE post_id = ? AND status != 'gone' OR post_id = ? AND why = 'missing' ORDER BY id DESC LIMIT 30", pid, pid)]


def reply_reserve(con, v: Viewer, pid: int, body: dict) -> int:
    """A reply, held ('check') before the AI looks, the caps counted in the same transaction: REPLY_GAP apart (all my
    posts), the day's cap under a post (REPLIES_MORE; deleting one buys nothing back). The comment by its link: under
    this post's message, a student's comment the bot saw (fchan_comments) and still up."""
    need_student(v)
    text = _clean(body.get("body"))
    link = str(body.get("link") or "").strip()
    with tx(con):
        p = _my_anon_post(con, v, pid)
        comment = None
        if link:
            m = COMMENT_LINK.fullmatch(link)
            if not m or int(m[2]) != p["tg_msg"] or not one(con, "SELECT 1 FROM fchan_comments WHERE msg_id = ? AND post_id = ? AND gone = 0", int(m[3]), pid):
                raise ApiError("bad_input", "comment")
            comment = int(m[3])
        last = one(con, """SELECT MAX(r.created_at) FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE p.user_id = ?""", v.id)[0]
        if last and last > _now() - REPLY_GAP:
            raise ApiError("rate_limited", "replies")
        if one(con, "SELECT COUNT(*) FROM fchan_replies WHERE post_id = ? AND created_at > ?", pid, _now() - 86400)[0] >= reply_cap(con, p):
            raise ApiError("rate_limited", "replies")
        return con.execute("INSERT INTO fchan_replies (post_id, comment_msg, body, status, why, created_at) VALUES (?, ?, ?, 'held', 'check', ?)",
                           (pid, comment, text, _now())).lastrowid


def reply_cap(con, p) -> int:
    """This post's replies a day: the others' comments under it the bot saw, and REPLIES_MORE. ponytail: a friend's
    comments deleted in Telegram still count (no delete event reaches the bot); each reply still has its AI look and
    REPLY_GAP. Count DISTINCT user_id if friends ever farm it."""
    return one(con, """SELECT COUNT(*) FROM fchan_comments c JOIN students s ON s.user_id = c.user_id
                       WHERE c.post_id = ? AND c.user_id != ?""", p["id"], p["user_id"])[0] + REPLIES_MORE


def reply_settle(con, rid: int, verdict: str | None) -> dict:
    """The AI's word (ai.screen_reply): 'ok' goes out after a random wait; 'person', 'flag' or no answer wait for a moderator."""
    with tx(con):
        if verdict == "ok":
            r = one(con, "SELECT created_at FROM fchan_replies WHERE id = ?", rid)
            con.execute("UPDATE fchan_replies SET status = 'live', why = NULL, send_at = ? WHERE id = ? AND status = 'held' AND why = 'check'",
                        (_wait(r["created_at"]) if r else _now(), rid))
        else:
            con.execute("UPDATE fchan_replies SET why = ? WHERE id = ? AND status = 'held' AND why = 'check'",
                        ({"person": "person", "flag": "ai"}.get(verdict or "", "check"), rid))
    return _reply_shape(one(con, "SELECT * FROM fchan_replies WHERE id = ?", rid))


def _drop(con, r, why: str, status: str = "gone", delay: int = 0) -> None:
    """A reply off: the words wiped when its author deletes it (a takedown keeps them 30 days for an undo); out of the
    group in the bot's round (now, or after the undo minute)."""
    con.execute("""UPDATE fchan_replies SET status = ?, why = ?, body = CASE WHEN ? = 'gone' THEN '' ELSE body END,
                   ai_reason = CASE WHEN ? = 'gone' THEN NULL ELSE ai_reason END, drop_at = ? WHERE id = ?""",
                (status, why, status, status, _now() + delay, r["id"]))


def reply_delete(con, v: Viewer, rid: int) -> None:
    """The author deletes their reply: through the post (no user id on the reply)."""
    with tx(con):
        r = one(con, "SELECT r.* FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.id = ? AND p.user_id = ? AND r.status != 'gone'", rid, v.id)
        if not r:
            raise ApiError("not_found")
        _drop(con, r, "author")


def _post_off(con, pid: int, delay: int = 0) -> None:
    """The post left (deleted, taken down): its replies leave the group with it (an undo of the post inside the minute
    keeps the sent ones: the round only takes a live reply out while its post isn't live); unsent ones never go."""
    con.execute("UPDATE fchan_replies SET drop_at = ? WHERE post_id = ? AND tg_msg >= 0", (_now() + delay, pid))  # 0: on its way, reply_sent keeps it
    con.execute("UPDATE fchan_replies SET status = 'hidden', why = 'post' WHERE post_id = ? AND status IN ('held', 'live') AND tg_msg IS NULL", (pid,))


REPLY_HIDE_AT = 3  # distinct reporters, each verified over tgcomments.REPORTER_AGE ago: the reply leaves at once, a moderator decides


def reply_reported(con, reporter_tg: int, msg_id: int) -> bool:
    """/report on the bot's reply in the group (tgc._report): once per reporter (fchan_reply_reports), the reporter told
    as for a comment, the moderators pinged at once (one note a reply, at its first report; the Admin sheet lists it). REPLY_HIDE_AT
    long-verified reporters take it down at once (as a moderator's take-down: Undo, Bring back). False: not ours."""
    from .tgcomments import REPORTER_AGE, _mods
    r = one(con, "SELECT r.*, p.user_id AS author FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.tg_msg = ? AND r.tg_msg > 0 AND r.status = 'live'", msg_id)
    u = one(con, "SELECT id FROM users WHERE tg_id = ?", reporter_tg)
    if not r or not u:
        return bool(r)
    with tx(con):
        if u["id"] != r["author"] and con.execute("INSERT OR IGNORE INTO fchan_reply_reports (reply_id, user_id, at) VALUES (?, ?, ?)",
                                                  (r["id"], u["id"], _now())).rowcount:
            notify_staff(con, _mods(con), "fch_reply_queue", f"rq:{r['id']}")
            n = one(con, """SELECT COUNT(*) FROM fchan_reply_reports x JOIN students s ON s.user_id = x.user_id AND s.manual = 0
                WHERE x.reply_id = ? AND s.verified_at < ?""", r["id"], _now() - REPORTER_AGE)[0]
            if n >= REPLY_HIDE_AT:
                _drop(con, r, "reports", "hidden", UNDO_WINDOW)
                log_action(con, None, "fchan_reply_auto_hide", f"fchanr:{r['id']}")
        notify(con, u["id"], "tgc_report_ok", f"rr:{r['id']}")
    return True


def reply_answered(con, msg_id: int, tg: int) -> None:
    """A student answered the bot's reply in the group (tgc.gate): its author hears, a template with a button to the
    post, at most once an hour per reply (never their own answer)."""
    r = one(con, """SELECT r.id, p.id AS pid, p.user_id FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id JOIN users u ON u.id = p.user_id
        WHERE r.tg_msg = ? AND r.tg_msg > 0 AND r.status = 'live' AND u.tg_id > 0 AND u.tg_id != ?""", msg_id, tg)
    if r:
        notify(con, r["user_id"], "fch_reply_answer", f"fa:{r['id']}:{_now() // 3600}")


# the bot's side (tgc.post_tick)

def replies_to_send(con) -> list:
    """Replies due now: live, their wait over, the post live in the channel, its author not banned: (id, words, the
    message to answer: the comment or the post's copy in the group, the signature: the post's nick or the plain mark)."""
    return [(r["id"], r["body"], r["comment_msg"] or int(r["root"]),
             texts.FCH_REPLY_NICK.format(nick=texts.nick(r["nick_a"], r["nick_n"])) if r["nick_a"] is not None else texts.FCH_REPLY_SIGN)
            for r in rows(con, """SELECT r.*, m.value AS root, p.nick_a, p.nick_n FROM fchan_replies r
        JOIN fchan_posts p ON p.id = r.post_id AND p.status = 'live' AND p.tg_msg > 0 JOIN users u ON u.id = p.user_id AND u.banned_at IS NULL
        JOIN meta m ON m.key = 'fchcopy:' || p.tg_msg WHERE r.status = 'live' AND r.tg_msg IS NULL AND r.send_at <= ? ORDER BY r.send_at LIMIT 5""", _now())]


def reply_sending(con, rid: int) -> bool:
    return con.execute("UPDATE fchan_replies SET tg_msg = 0 WHERE id = ? AND status = 'live' AND tg_msg IS NULL", (rid,)).rowcount > 0


def reply_sent(con, rid: int, msg_id: int) -> None:
    """Its message id kept; it or its post deleted or taken down meanwhile, it leaves the group right away (a post's
    take-down keeps its undo minute: _post_off stamped drop_at). ponytail: an account deleted while one is on its way
    takes the row with a non-live post (cascade) and the message stays; a one-second window in the bot's one process"""
    con.execute("UPDATE fchan_replies SET tg_msg = ? WHERE id = ? AND tg_msg = 0", (msg_id, rid))
    con.execute("""UPDATE fchan_replies SET drop_at = COALESCE(drop_at, ?) WHERE id = ? AND (status != 'live'
        OR post_id IN (SELECT id FROM fchan_posts WHERE status != 'live'))""", (_now(), rid))


def reply_unsend(con, rid: int) -> None:
    con.execute("UPDATE fchan_replies SET tg_msg = NULL WHERE id = ? AND tg_msg = 0", (rid,))


def reply_missing(con, rid: int) -> None:
    """Telegram: the comment answered is gone. The reply is dropped (never sent elsewhere), its author told."""
    r = one(con, "SELECT p.user_id FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.id = ? AND r.tg_msg = 0", rid)
    if r:
        con.execute("UPDATE fchan_replies SET status = 'gone', why = 'missing', body = '', ai_reason = NULL, tg_msg = NULL WHERE id = ?", (rid,))
        notify(con, r["user_id"], "fch_reply_gone", f"fg:{rid}")


def replies_lost(con) -> None:
    """A send with no answer: to a moderator, never sent twice by itself (as lost())."""
    con.execute("UPDATE fchan_replies SET status = 'held', why = 'lost', tg_msg = NULL WHERE status = 'live' AND tg_msg = 0")


def reply_drops(con) -> list:
    """Replies to take out of the group now: (id, message, why) deleted by the author, taken down, or their post left."""
    return [tuple(r) for r in rows(con, """SELECT r.id, r.tg_msg, CASE WHEN r.status = 'hidden' THEN 'moderator' ELSE 'author' END FROM fchan_replies r
        JOIN fchan_posts p ON p.id = r.post_id WHERE r.tg_msg > 0 AND r.drop_at <= ? AND (r.status != 'live' OR p.status != 'live') LIMIT 20""", _now())]


def reply_dropped(con, rid: int) -> None:
    """Out of the group: a live one whose post left is removed with it."""
    con.execute("""UPDATE fchan_replies SET tg_msg = NULL, drop_at = NULL, status = CASE WHEN status = 'live' THEN 'hidden' ELSE status END,
        why = CASE WHEN status = 'live' THEN 'post' ELSE why END WHERE id = ?""", (rid,))


def reply_drop_later(con, rid: int) -> None:
    con.execute("UPDATE fchan_replies SET drop_at = ? WHERE id = ?", (_now() + 600, rid))


# moderators (the Admin sheet): held replies, this week's live ones (reported first), this week's take-downs

def _reply_mod_shape(r) -> dict:
    return {"id": r["id"], "body": r["body"], "post": r["post_id"], "postBody": r["pbody"], "why": r["why"], "reports": r["reports"], "anon": bool(r["anon"]), "nick": _nick(r),
            "aiWhy": r["ai_reason"], "at": r["created_at"], "undo": bool(r["tg_msg"]) and (r["drop_at"] or 0) > _now()}


def reply_mod_queue(con) -> dict:
    """Shown as anonymous posts are: the words and the post they answer, never whose (the author is the post's)."""
    q = """SELECT r.*, p.body AS pbody, p.anon, p.nick_a, p.nick_n, (SELECT COUNT(*) FROM fchan_reply_reports x WHERE x.reply_id = r.id) AS reports
        FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE """
    held = rows(con, q + "r.status = 'held' AND (r.why != 'check' OR r.created_at < ?) ORDER BY r.id", _now() - 60)
    # reported ones whatever their age (a report must reach someone), first; then this week's
    live = rows(con, q + """r.status = 'live' AND p.status = 'live' AND (r.created_at > ? OR EXISTS (SELECT 1 FROM fchan_reply_reports x WHERE x.reply_id = r.id))
        ORDER BY reports DESC, r.id DESC LIMIT 50""", _now() - MOD_RECENT)
    removed = rows(con, q + "r.status = 'hidden' AND r.why IN ('moderator', 'reports') AND (r.created_at > ? OR r.why = 'reports') ORDER BY r.id DESC LIMIT 50", _now() - MOD_RECENT)
    return {"held": [_reply_mod_shape(r) for r in held], "live": [_reply_mod_shape(r) for r in live], "removed": [_reply_mod_shape(r) for r in removed]}


def _mod_reply(con, v: Viewer, rid: int, where: str):
    _mod(v)
    r = one(con, "SELECT r.*, p.user_id FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.id = ? AND " + where, rid)
    if not r:
        raise core.decided(con, f"fchanr:{rid}") if one(con, "SELECT 1 FROM fchan_replies WHERE id = ?", rid) else ApiError("not_found")
    if r["user_id"] == v.id:  # their own post's: another moderator decides
        raise ApiError("forbidden")
    return r


def reply_mod_decide(con, v: Viewer, rid: int, ok: object, again: object = False) -> None:
    """A held reply goes out (after the random wait) or is removed; a live one: ok clears its reports (kept), else it
    is taken down (out of the group after the undo minute). A lost send (may be in the group already, the bot can't
    tell) goes out again only on the moderator's explicit again=True, after looking at the comments. Audited."""
    if not isinstance(ok, bool):
        raise ApiError("bad_input")
    with tx(con):
        r = _mod_reply(con, v, rid, "r.status IN ('held', 'live')")
        if ok and r["status"] == "held" and r["why"] == "lost" and again is not True:
            raise ApiError("conflict", "lost")
        if ok and r["status"] == "held":
            con.execute("UPDATE fchan_replies SET status = 'live', why = NULL, send_at = ? WHERE id = ?", (_wait(), rid))
            act = "fchan_reply_release"
        elif ok:  # the reports were wrong: cleared (a new one brings it back)
            con.execute("DELETE FROM fchan_reply_reports WHERE reply_id = ?", (rid,))
            act = "fchan_reply_keep"
        else:
            _drop(con, r, "moderator", "hidden", UNDO_WINDOW)
            act = "fchan_reply_hide"
        log_action(con, v.id, act, f"fchanr:{rid}")


def reply_mod_restore(con, v: Viewer, rid: int) -> None:
    """A take-down undone: inside the minute the message stays as it was; later the reply goes out anew (after the wait)."""
    with tx(con):
        r = _mod_reply(con, v, rid, "r.status = 'hidden' AND r.why IN ('moderator', 'reports') AND p.status = 'live'")
        con.execute("DELETE FROM fchan_reply_reports WHERE reply_id = ?", (rid,))
        kept = bool(r["tg_msg"]) and (r["drop_at"] or 0) > _now()
        con.execute("UPDATE fchan_replies SET status = 'live', why = NULL, drop_at = NULL, send_at = ? WHERE id = ?",
                    (r["send_at"] if kept else _wait(), rid))
        log_action(con, v.id, "fchan_reply_undo" if kept else "fchan_reply_restore", f"fchanr:{rid}")


def _now() -> int:
    return core.now()


# the other domains', imported last: they import this one too
from . import core  # noqa: E402
from .oversight import _mod, _owner  # noqa: E402
from .seats import notify, notify_staff  # noqa: E402
