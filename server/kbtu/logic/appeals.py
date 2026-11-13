"""Appeals to the Student Government (APPEALS=1 everyone, APPEALS=staff the admins, moderators and SG's people; owner,
Nov 10; Codex's reviews .claude/reports/codex/night/appeal*.log).

A verified student writes anything in any form; only technical limits stop it (length, a day's count). Named or
anonymous: the author's link lives apart (appeal_authors), for "my appeals", the quota and the answer's bot message;
SG's people never get it for an anonymous one (no name, user id, profile or contact through any route, audit line or
message), only the app's creator reveals it, from the server (admin `appeals reveal`), each look in the audit log.
SG's people: a right of its own (appeal_staff), granted and revoked by the creator from the server, never by a club
role. 5 working days to answer; overdue stays overdue whatever the status. Closing needs an answer. Every look, status
change, answer, grant, revoke and reveal goes to the audit log (ids only, never the words). Kept 90 days after
closing, 180 at most from sending; the author deletes theirs whenever. No drafts here: those stay on the phone."""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

from ..db import tx
from . import core
from .core import PERSON, ApiError, Viewer, log_action, need_student, one, rows, short_name
from .seats import notify

TOPICS = ("study", "dorm", "food", "campus", "events", "money", "other")  # the composer's optional chips (broad on purpose)
STATUSES = ("new", "work", "closed")    # Received / In progress / Closed
MAX = 4000
A_DAY = 3                               # sent in 24 h; deleting one gives nothing back (appeal_sends)
CONSENT = "apl1"                        # the privacy policy's appeals section, agreed to on the first send (or AI help)
DUE_DAYS = 5                            # working days to answer
KEEP_CLOSED, KEEP_MAX = 90 * 86400, 180 * 86400
FEW = 5                                 # a topic's month with fewer authors goes into "other" in SG's numbers
ALMATY = dt.timezone(dt.timedelta(hours=5))


def is_sg(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM appeal_staff WHERE user_id = ?", uid) is not None


def on(con, mode: str, v: Viewer) -> bool:
    """APPEALS=all: everyone; staff: admins, moderators and SG's people (the pilot)."""
    return mode == "all" or mode == "staff" and (v.role in ("admin", "moderator") or is_sg(con, v.id))


def summary(con, v: Viewer) -> dict:
    """/api/me's part: agreed to the section yet, and SG's queue mine to open."""
    return {"consent": one(con, "SELECT 1 FROM appeal_consents WHERE user_id = ? AND version = ?", v.id, CONSENT) is not None,
            "sg": is_sg(con, v.id)}


def due(t: int) -> int:
    """DUE_DAYS working days (Mon-Fri, Almaty) after t, the same time of day."""
    d, left = dt.datetime.fromtimestamp(t, ALMATY), DUE_DAYS
    while left:
        d += dt.timedelta(days=1)
        left -= d.weekday() < 5
    return int(d.timestamp())


def _agree(con, v: Viewer, body: dict) -> None:
    """The section agreed to once (the staff pilot too: the section promises its own consent); the app sends `consent`
    with the first send or AI help after asking."""
    if one(con, "SELECT 1 FROM appeal_consents WHERE user_id = ? AND version = ?", v.id, CONSENT):
        return
    if body.get("consent") != CONSENT:
        raise ApiError("forbidden", "consent")
    con.execute("INSERT OR REPLACE INTO appeal_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))


def agree_given(con, v: Viewer, body: dict) -> None:
    """The helplines' path (app.py, before every limit): a first consent sent with it is kept too, as the app now
    counts it given; nothing else is required there."""
    if v.student and body.get("consent") == CONSENT:
        with tx(con):
            _agree(con, v, body)


def _text(x: object) -> str:
    t = x.strip() if isinstance(x, str) else ""
    if not t or len(t) > MAX:
        raise ApiError("bad_input", "length")
    return t


def _shape(a, t: int) -> dict:
    return {"id": a["id"], "topic": a["topic"], "text": a["body"], "anon": bool(a["anon"]), "status": a["status"], "answer": a["answer"],
            "at": a["created_at"], "due": a["due_at"], "answeredAt": a["answered_at"], "closedAt": a["closed_at"],
            "overdue": (a["answered_at"] or t) > a["due_at"]}


def help_ok(con, v: Viewer, body: dict) -> str:
    """Before the AI looks at a draft: a verified student, the section agreed to, the text in limits, the day's AI
    allowance. A text with signs of crisis never gets here (app.py: the helplines come first, past every limit)."""
    from .assistant import _spend
    need_student(v)
    text = _text(body.get("text"))
    with tx(con):
        _agree(con, v, body)
    _spend(con, v)
    return text


SYSTEM = """You help a university student make an appeal to the Student Government clearer. You never rewrite it and
never judge it: rude, angry, short or messy appeals are fine. Look at what is missing for the Student Government to act:
where, when, who is affected, what happened, what outcome the student wants. Answer only with JSON:
{{"tips": ["...", "..."], "care": false}}
tips: 2 or 3 short questions or suggestions in {lang}, each under 90 characters, addressed to the student ("you"),
about what to add; none about style or tone. If nothing important is missing, one tip saying it is clear.
care: true only when the text speaks of wanting to die, hurting oneself or being in danger now (not jokes or
exaggeration about studies)."""
LANGS = {"ru": "Russian", "kk": "Kazakh", "en": "English"}


def help_prompt(text: str, lang: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM.format(lang=LANGS.get(lang, "Russian"))}, {"role": "user", "content": text}]


def _tips(answer: str) -> dict | None:
    m = re.search(r"\{.*\}", answer or "", re.S)
    try:
        x = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    if not isinstance(x, dict) or not isinstance(x.get("tips"), list):
        return None
    tips = [" ".join(s.split())[:140] for s in x["tips"] if isinstance(s, str) and s.strip()][:3]
    return {"tips": tips, "care": x.get("care") is True} if tips or x.get("care") is True else None


def tips_usable(answer: str) -> bool:
    return _tips(answer) is not None


def help_reply(con, answer: str, text: str, lang: str) -> dict:
    """The model's 2-3 tips; signs of self-harm (its own flag or the assistant's keywords) bring the helplines instead.
    Nothing of it is kept."""
    from .assistant import care, distress
    x = _tips(answer) or {"tips": [], "care": False}
    if x["care"] or distress(text):
        return {"tips": [], **care(con, lang)}
    return {"tips": x["tips"]}


def send(con, v: Viewer, body: dict) -> dict:
    need_student(v)
    text = _text(body.get("text"))
    topic = body.get("topic") if body.get("topic") in TOPICS else None
    key = body.get("key") if isinstance(body.get("key"), str) and 8 <= len(body["key"]) <= 64 else None
    t = core.now()
    with tx(con):
        _agree(con, v, body)
        if key:  # the same tap sent twice (a retry after a lost answer): the one already there
            a = one(con, "SELECT a.* FROM appeals a JOIN appeal_authors w ON w.appeal_id = a.id WHERE a.nonce = ? AND w.user_id = ?", key, v.id)
            if a:
                return _shape(a, t)
        if one(con, "SELECT COUNT(*) FROM appeal_sends WHERE user_id = ? AND at > ?", v.id, t - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "appeals")
        aid = con.execute("INSERT INTO appeals (topic, body, anon, created_at, due_at, nonce) VALUES (?, ?, ?, ?, ?, ?)",
                          (topic, text, 1 if body.get("anon") is True else 0, t, due(t), key)).lastrowid
        con.execute("INSERT INTO appeal_authors (appeal_id, user_id) VALUES (?, ?)", (aid, v.id))
        con.execute("INSERT INTO appeal_sends (user_id, at) VALUES (?, ?)", (v.id, t))
    return _shape(one(con, "SELECT * FROM appeals WHERE id = ?", aid), t)


def mine(con, v: Viewer) -> dict:
    """My appeals and the "Solved" feed, in one request (the screen's only one)."""
    t = core.now()
    return {"items": [_shape(a, t) for a in rows(con, """SELECT a.* FROM appeals a JOIN appeal_authors w ON w.appeal_id = a.id
        WHERE w.user_id = ? ORDER BY a.id DESC""", v.id)], "solved": solved(con, is_sg(con, v.id))}


def _drop(con, aid: int) -> None:
    con.execute("DELETE FROM bot_outbox WHERE kind = 'appeal_answer' AND ref = ?", (f"apl:{aid}",))
    con.execute("DELETE FROM appeals WHERE id = ?", (aid,))  # its author link goes with it (ON DELETE CASCADE)


def delete(con, v: Viewer, aid: int) -> None:
    with tx(con):
        if not one(con, "SELECT 1 FROM appeal_authors WHERE appeal_id = ? AND user_id = ?", aid, v.id):
            raise ApiError("not_found")
        _drop(con, aid)
        log_action(con, None, "appeal_delete", f"appeal:{aid}")  # no actor: the line would tie me to it


# ------------------------------------------------------------ SG's queue

def _sg(con, v: Viewer) -> None:
    if not is_sg(con, v.id):
        raise ApiError("forbidden")


def _for_sg(con, a, t: int) -> dict:
    """An appeal as SG sees it: a named one's author as a short name only (no id, profile or contact); an anonymous one, nothing."""
    out = _shape(a, t)
    if not a["anon"]:
        p = one(con, PERSON + " JOIN appeal_authors w ON w.user_id = u.id WHERE w.appeal_id = ?", a["id"])
        out["author"] = short_name(p) if p else None
    return out


def queue(con, v: Viewer) -> dict:
    """The whole queue (one audit line for the look) and the months' counts by topic."""
    _sg(con, v)
    t = core.now()
    items = [_for_sg(con, a, t) for a in rows(con, "SELECT * FROM appeals ORDER BY status = 'closed', id DESC")]
    log_action(con, v.id, "appeal_queue", "appeals")
    return {"items": items, "months": months(con)}


def detail(con, v: Viewer, aid: int) -> dict:
    _sg(con, v)
    a = one(con, "SELECT * FROM appeals WHERE id = ?", aid)
    if not a:
        raise ApiError("not_found")
    log_action(con, v.id, "appeal_view", f"appeal:{aid}")
    return _for_sg(con, a, core.now())


def act(con, v: Viewer, aid: int, body: dict) -> dict:
    """A status and/or the answer. Closing needs an answer (the new one or the one already given). The author's bot
    message (a template, no words) goes once, with the first answer."""
    _sg(con, v)
    status = body.get("status")
    if status is not None and status not in STATUSES:
        raise ApiError("bad_input")
    answer = body.get("answer")
    if answer is not None:
        answer = answer.strip() if isinstance(answer, str) else ""
        if len(answer) > MAX:
            raise ApiError("bad_input", "length")
    t = core.now()
    with tx(con):
        a = one(con, "SELECT * FROM appeals WHERE id = ?", aid)
        if not a:
            raise ApiError("not_found")
        new_answer = answer if answer is not None else a["answer"]
        status = status or a["status"]
        if status == "closed" and not new_answer:
            raise ApiError("bad_input", "answer")
        if answer is not None and answer != (a["answer"] or ""):
            con.execute("UPDATE appeals SET answer = ?, answered_at = COALESCE(answered_at, ?) WHERE id = ?", (answer or None, t, aid))
            log_action(con, v.id, "appeal_answer", f"appeal:{aid}")
            if answer:
                w = one(con, "SELECT user_id FROM appeal_authors WHERE appeal_id = ?", aid)
                if w:
                    notify(con, w[0], "appeal_answer", f"apl:{aid}")
        if status != a["status"]:
            con.execute("UPDATE appeals SET status = ?, closed_at = ? WHERE id = ?", (status, t if status == "closed" else None, aid))
            log_action(con, v.id, "appeal_status", f"appeal:{aid}", json.dumps({"from": a["status"], "to": status}))
    return _for_sg(con, one(con, "SELECT * FROM appeals WHERE id = ?", aid), t)


def months(con) -> list[dict]:
    """Sent appeals a month by topic (Almaty months); a topic with fewer than FEW appeals that month goes into "other"
    (none chosen counts as other). Read from the appeals alone, never their authors: the numbers say nothing the queue
    doesn't (counting authors told SG when a named and an anonymous appeal were one person's; Codex, Nov 10)."""
    got: dict[str, dict[str, int]] = {}
    for r in rows(con, "SELECT created_at, topic FROM appeals"):
        m = dt.datetime.fromtimestamp(r["created_at"], ALMATY).strftime("%Y-%m")
        t = got.setdefault(m, {})
        t[r["topic"] or "other"] = t.get(r["topic"] or "other", 0) + 1
    out = []
    for m in sorted(got, reverse=True):
        counts: dict[str, int] = {}
        for topic, n in got[m].items():
            k = topic if n >= FEW else "other"
            counts[k] = counts.get(k, 0) + n
        out.append({"month": m, "total": sum(counts.values()), "topics": counts})
    return out


# ------------------------------------------------------------ "Solved by your appeals": SG's public lines

# Two general lines, never an appeal's words and never linked to one (no appeal id anywhere): proof that writing
# changes things. Who wrote it is kept for the audit only and never sent. The shapes below could point at an
# anonymous author (a room, a floor, a date, an id, a contact), so they never pass; names no regex catches: the SG
# writer is told why. Owner + adversarial review, Nov 13.
SOLVED_LEN = (10, 140)
SOLVED_MONTH = 10                       # new entries a calendar month (Almaty); a deleted one still counts
SOLVED_TOPIC = 90 * 86400               # an entry's topic shows only if FEW appeals had it in this time before
SOLVED_QUOTE = 6                        # words in a row the same as in an appeal: its words, not SG's
SOLVED_SHOWN = 3                        # students see the feed from this many entries; SG always
_CONTACT = re.compile(r"@|\((?:at|dog)\)|\[(?:at|dog)\]|\d(?:[\s().+-]*\d){5,}", re.I)  # mentions, e-mails, phones
# a room, a floor, a date, an id (Unicode digits too): two digits however split ("4 0 5", keycaps' marks between),
# a digit beside a letter that reads as one ("4O5", "l2"), Roman numerals ("XII", Cyrillic look-alikes too), a day
# and its month ("5 March"); one digit alone passes ("Floor 3")
_LOOKS = "Oo\u041e\u043eIl\u0406\u0417"
_NUMBER = re.compile(rf"\d[\W_]*\d|\d[{_LOOKS}]|[{_LOOKS}]\d|(?<!\w)[IVXLC\u0406\u0425\u0421]{{2,}}(?!\w)")
_DATE = re.compile(r"\d[\W_]*(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
                   r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])|\u044f\u043d\u0432\u0430\u0440|\u0444\u0435\u0432\u0440\u0430\u043b|\u043c\u0430\u0440\u0442|\u0430\u043f\u0440\u0435\u043b|\u043c\u0430[\u0439\u044f]|\u0438\u044e\u043d|\u0438\u044e\u043b"
                   r"|\u0430\u0432\u0433\u0443\u0441\u0442|\u0441\u0435\u043d\u0442\u044f\u0431\u0440|\u043e\u043a\u0442\u044f\u0431\u0440|\u043d\u043e\u044f\u0431\u0440|\u0434\u0435\u043a\u0430\u0431\u0440|\u049b\u0430\u04a3\u0442\u0430\u0440|\u0430\u049b\u043f\u0430\u043d|\u043d\u0430\u0443\u0440\u044b\u0437|\u0441\u04d9\u0443\u0456\u0440|\u043c\u0430\u043c\u044b\u0440|\u043c\u0430\u0443\u0441\u044b\u043c"
                   r"|\u0448\u0456\u043b\u0434\u0435|\u0442\u0430\u043c\u044b\u0437|\u049b\u044b\u0440\u043a\u04af\u0439\u0435\u043a|\u049b\u0430\u0437\u0430\u043d|\u049b\u0430\u0440\u0430\u0448\u0430|\u0436\u0435\u043b\u0442\u043e\u049b\u0441\u0430\u043d)", re.I)
_INITIALS = re.compile(r"(?<!\w)(\w)\. ?(\w)\.")  # "A. B.": a name's initials (both capitals)


def solved_line(x: object) -> str:
    """One line, plain: the forum channel's invisible characters out (they could split a number past the checks) and
    control ones, whitespace collapsed; then the length and, read as the forum channel reads it (NFKC, odd dots), a
    contact, a link (its LINKY, SPACED), a number or initials. ApiError's message: which. The app mirrors it (web/src/lib/solved.ts;
    the cases both agree on: server/tests/solved_rules.json)."""
    from .fchannel import BRACKET_DOT, DOTS, LINKY, SPACED, ZWJ, _visible
    s = x if isinstance(x, str) else ""
    s = " ".join("".join(c for c in s if c.isspace() or (_visible(c) and c != ZWJ and unicodedata.category(c) != "Cc")).split())
    if not SOLVED_LEN[0] <= len(s) <= SOLVED_LEN[1]:
        raise ApiError("bad_input", "length")
    seen = BRACKET_DOT.sub(".", unicodedata.normalize("NFKC", s).translate(DOTS))
    for why, bad in (("contact", _CONTACT.search(seen)), ("link", LINKY.search(seen) or SPACED.search(seen)),
                     ("number", _NUMBER.search(seen) or _DATE.search(seen)),
                     ("name", any(a.isupper() and b.isupper() for a, b in _INITIALS.findall(seen)))):
        if bad:
            raise ApiError("bad_input", why)
    return s


def _month_start(t: int) -> int:
    return int(dt.datetime.fromtimestamp(t, ALMATY).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def _solved_shape(r, sg: bool = True) -> dict:
    """The id for SG's delete only: students get none (its gaps would count what was deleted)."""
    return {**({"id": r["id"]} if sg else {}), "raised": r["raised"], "changed": r["changed"], "topic": r["topic"],
            "month": dt.datetime.fromtimestamp(r["created_at"], ALMATY).strftime("%Y-%m")}


def solved(con, sg: bool) -> list[dict]:
    """Newest first; empty for students until SOLVED_SHOWN entries (a lonely one proves nothing)."""
    rs = rows(con, "SELECT * FROM appeal_solved WHERE gone_at IS NULL ORDER BY id DESC")
    return [_solved_shape(r, sg) for r in rs] if sg or len(rs) >= SOLVED_SHOWN else []


def _room(con, t: int) -> None:
    if one(con, "SELECT COUNT(*) FROM appeal_solved WHERE created_at >= ?", _month_start(t))[0] >= SOLVED_MONTH:
        raise ApiError("rate_limited", "solved")


def _quoted(con, *lines: str) -> None:
    """SOLVED_QUOTE words in a row from any appeal: an author's own words could give them away; SG says it in theirs.
    (SG reads every appeal anyway: the refusal tells them nothing new.)"""
    def runs(s: str) -> set:
        w = re.findall(r"\w+", unicodedata.normalize("NFKC", s).casefold())
        return {tuple(w[i:i + SOLVED_QUOTE]) for i in range(len(w) - SOLVED_QUOTE + 1)}
    mine = set().union(*map(runs, lines))
    # ponytail: every appeal read on each add (hundreds at most, 10 adds a month); an index if appeals grow to many thousands
    if mine and any(mine & runs(b) for (b,) in rows(con, "SELECT body FROM appeals")):
        raise ApiError("bad_input", "quote")


def solved_add(con, v: Viewer, body: dict) -> dict:
    _sg(con, v)
    raised, changed = solved_line(body.get("raised")), solved_line(body.get("changed"))
    topic = body.get("topic") if body.get("topic") in TOPICS else None
    t = core.now()
    with tx(con):
        _room(con, t)
        _quoted(con, raised, changed)
        # a topic few wrote about could point at them (an entry right after the one appeal): none then, as SG's
        # numbers merge a small one into "other" (appeals counted, never authors: months())
        if topic and one(con, "SELECT COUNT(*) FROM appeals WHERE topic = ? AND created_at >= ?", topic, t - SOLVED_TOPIC)[0] < FEW:
            topic = None
        sid = con.execute("INSERT INTO appeal_solved (raised, changed, topic, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                          (raised, changed, topic, v.id, t)).lastrowid
        log_action(con, v.id, "solved_add", f"solved:{sid}")
    return _solved_shape(one(con, "SELECT * FROM appeal_solved WHERE id = ?", sid))


def solved_delete(con, v: Viewer, sid: int) -> None:
    """Any of SG's people, any entry; undoable for a day (solved_restore), then its words gone for good (forget)."""
    _sg(con, v)
    with tx(con):
        if not con.execute("UPDATE appeal_solved SET gone_at = ? WHERE id = ? AND gone_at IS NULL", (core.now(), sid)).rowcount:
            raise ApiError("not_found")
        log_action(con, v.id, "solved_delete", f"solved:{sid}")


def solved_restore(con, v: Viewer, sid: int) -> dict:
    _sg(con, v)
    t = core.now()
    with tx(con):
        r = one(con, "SELECT * FROM appeal_solved WHERE id = ? AND gone_at > ?", sid, t - 86400)
        if not r:
            raise ApiError("not_found")
        con.execute("UPDATE appeal_solved SET gone_at = NULL WHERE id = ?", (sid,))
        log_action(con, v.id, "solved_restore", f"solved:{sid}")
    return _solved_shape(r)


# ------------------------------------------------------------ the creator, from the server (admin.py)

def grant(con, actor: int | None, uid: int, on_: bool) -> None:
    with tx(con):
        if on_:
            con.execute("INSERT OR IGNORE INTO appeal_staff (user_id, at) VALUES (?, ?)", (uid, core.now()))
        else:
            con.execute("DELETE FROM appeal_staff WHERE user_id = ?", (uid,))
        log_action(con, actor, "appeal_grant" if on_ else "appeal_revoke", f"user:{uid}")


def reveal(con, actor: int, aid: int):
    """Who wrote an appeal: the creator alone, from the server, each look in the audit log."""
    with tx(con):
        p = one(con, PERSON + " JOIN appeal_authors w ON w.user_id = u.id WHERE w.appeal_id = ?", aid)
        if p:
            log_action(con, actor, "appeal_reveal", f"appeal:{aid}")
    return p


def forget(con) -> None:
    """Nightly: 90 days after closing, 180 at most from sending; the day's quota rows and deleted "Solved" entries' words after a day."""
    t = core.now()
    for (aid,) in rows(con, "SELECT id FROM appeals WHERE closed_at < ? OR created_at < ?", t - KEEP_CLOSED, t - KEEP_MAX):
        _drop(con, aid)
    con.execute("DELETE FROM appeal_sends WHERE at < ?", (t - 86400,))
    # "Solved" entries deleted a day ago: their words and writer out; the row itself stays to its month's end (the cap
    # counts it: delete and add again can't pass SOLVED_MONTH)
    con.execute("UPDATE appeal_solved SET raised = '', changed = '', topic = NULL, created_by = NULL WHERE gone_at < ?", (t - 86400,))
    con.execute("DELETE FROM appeal_solved WHERE gone_at < ? AND created_at < ?", (t - 86400, _month_start(t)))
