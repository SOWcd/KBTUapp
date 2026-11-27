"""Events found in a club's channel (clubs announce in Telegram and rarely add the event to Afisha).
A NEW post the mirror takes (mirror.take, from userbot.Mirror.post; never an edit, no sweep) that reads like an
announcement (`worth`: long enough, a date or a time in it, no model) gets ONE model call: the event form's own fill
prompt (assistant.FILL, "today" being the post's day), which may also say it's no event. A future date and time: a DRAFT
of that club, never published by itself (a wrong date in Afisha is worse than none), with the post as its source.
Its leaders see it on top of Studio, the app's admins in Admin's queue (open it, or dismiss: Admin's event delete, with
its Undo); the club's President hears it once from the bot. Each post is looked at once (auto_events), whatever came of it."""
from __future__ import annotations

import difflib
import logging
import re
import time

import httpx

from .. import ai, llm
from ..db import tx
from .core import TZ, _event_cover, at, day_start, now, one, org_ref, rows

log = logging.getLogger("kbtu.autoev")

MIN_TEXT = 60     # shorter is a caption, not an announcement
DAY_MAX = 10      # model calls per club a day at most: a channel posting dates all day costs no more

_MONTHS = (r"(?:\u044f\u043d\u0432\u0430\u0440|\u0444\u0435\u0432\u0440\u0430\u043b|\u043c\u0430\u0440\u0442|\u0430\u043f\u0440\u0435\u043b|\u043c\u0430[\u0439\u044f]|\u0438\u044e\u043d|\u0438\u044e\u043b|\u0430\u0432\u0433\u0443\u0441\u0442|\u0441\u0435\u043d\u0442\u044f\u0431\u0440|\u043e\u043a\u0442\u044f\u0431\u0440|\u043d\u043e\u044f\u0431\u0440|\u0434\u0435\u043a\u0430\u0431\u0440"
           r"|\u049b\u0430\u04a3\u0442\u0430\u0440|\u0430\u049b\u043f\u0430\u043d|\u043d\u0430\u0443\u0440\u044b\u0437|\u0441\u04d9\u0443\u0456\u0440|\u043c\u0430\u043c\u044b\u0440|\u043c\u0430\u0443\u0441\u044b\u043c|\u0448\u0456\u043b\u0434\u0435|\u0442\u0430\u043c\u044b\u0437|\u049b\u044b\u0440\u043a\u04af\u0439\u0435\u043a|\u049b\u0430\u0437\u0430\u043d|\u049b\u0430\u0440\u0430\u0448\u0430|\u0436\u0435\u043b\u0442\u043e\u049b\u0441\u0430\u043d"
           r"|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)")
_WORDS = (r"\u0437\u0430\u0432\u0442\u0440\u0430|\u043f\u043e\u0441\u043b\u0435\u0437\u0430\u0432\u0442\u0440\u0430|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0435\u0440\u0442\u0435\u04a3|\u0431\u04af\u0433\u0456\u043d|tomorrow|tonight|today"
          r"|\u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a|\u0432\u0442\u043e\u0440\u043d\u0438\u043a|\u0441\u0440\u0435\u0434[\u0430\u0443]|\u0447\u0435\u0442\u0432\u0435\u0440\u0433|\u043f\u044f\u0442\u043d\u0438\u0446|\u0441\u0443\u0431\u0431\u043e\u0442|\u0432\u043e\u0441\u043a\u0440\u0435\u0441\u0435\u043d|\u0434\u04af\u0439\u0441\u0435\u043d\u0431\u0456|\u0441\u0435\u0439\u0441\u0435\u043d\u0431\u0456|\u0441\u04d9\u0440\u0441\u0435\u043d\u0431\u0456|\u0431\u0435\u0439\u0441\u0435\u043d\u0431\u0456|\u0436\u04b1\u043c\u0430|\u0441\u0435\u043d\u0431\u0456|\u0436\u0435\u043a\u0441\u0435\u043d\u0431\u0456"
          r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday")
_DATEISH = re.compile(
    r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b"                        # 19:00, 19.00
    r"|\b[0-3]?\d[./][01]?\d\b"                                 # 21.11, 21/11
    rf"|\b[0-3]?\d(?:-?(?:\u0433\u043e|\u0448\u0456|\u0448\u044b|th|st|nd|rd))?\s+{_MONTHS}"  # 21 \u043d\u043e\u044f\u0431\u0440\u044f, 21-\u0433\u043e \u043d\u043e\u044f\u0431\u0440\u044f, 21 \u049b\u0430\u0440\u0430\u0448\u0430, 21st Nov
    rf"|\b{_MONTHS}[a-z\u0430-\u044f\u04d9\u0456\u04a3\u0493\u04af\u04b1\u049b\u04e9\u04bb]*\s+[0-3]?\d\b"             # November 21, \u049b\u0430\u0440\u0430\u0448\u0430 21
    rf"|\b(?:{_WORDS})", re.I)


def worth(text: str) -> bool:
    """A channel post worth the model's look: long enough, with a date or a time expression in it (ru, kk, en)."""
    return len(text.strip()) >= MIN_TEXT and bool(_DATEISH.search(text))


NOT_ONE = """
First decide whether this is an announcement of one upcoming event people can come to. If it is not (a report on a past
event, news, a recruitment call, a list of several events, an ad), reply {"event": false} and nothing else. The same
announcement repeated in several languages (Russian, Kazakh, English) in one post is ONE event, never a list (lang and
tr above say how to fill it)."""


def answered(text: str) -> bool:
    """The model filled the form, or said it's no event."""
    x = assistant._parse(text)
    return x is not None and (x.get("event") is False or assistant.fill_answered(text))


def claim(con, pid: int, text: str, posted: int) -> list[dict] | None:
    """The post taken for its one look (none before, its club active, under the day's cap): the model's messages; None: let be."""
    with tx(con):
        p = one(con, """SELECT p.org_id FROM posts p JOIN orgs o ON o.id = p.org_id AND o.status = 'active'
            WHERE p.id = ? AND p.hidden_at IS NULL""", pid)
        if not p or one(con, "SELECT 1 FROM auto_events WHERE post_id = ?", pid) \
                or one(con, "SELECT COUNT(*) FROM auto_events WHERE org_id = ? AND at > ?", p["org_id"], now() - 86400)[0] >= DAY_MAX:
            return None
        con.execute("INSERT INTO auto_events (post_id, org_id, at) VALUES (?, ?, ?)", (pid, p["org_id"], now()))
    day = time.gmtime(posted + TZ)  # "tomorrow" is the post's tomorrow (a first link takes posts of the last month)
    system = assistant.FILL.format(today=f"{assistant.WEEKDAYS[day.tm_wday]}, {time.strftime('%Y-%m-%d', day)}") + NOT_ONE
    return [{"role": "system", "content": system}, {"role": "user", "content": text.strip()[:assistant.FILL_MAX]}]


def _similar(a: str, b: str) -> bool:
    a, b = " ".join(a.casefold().split()), " ".join(b.casefold().split())
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def made(con, pid: int, answer: str, text: str = "") -> int | None:
    """The model's answer as the club's draft: the event's id; None when it's no event, has no future day and time, or
    the club has it already (any event that day with a like title)."""
    x = assistant._parse(answer) or {}
    f = assistant.filled(answer, text)  # the post's meeting link: an online event
    if x.get("event") is False or not {"title", "date", "start"} <= f.keys():
        return None
    starts = at(f["date"], f["start"])
    if starts <= now():
        return None
    ends = at(f.get("endDate") or f["date"], f.get("end") or "23:59") if f.get("endDate") or f.get("end") else None
    if ends is not None and ends <= starts and not f.get("endDate"):
        ends += 86400  # till past midnight
    if ends is not None and not starts < ends <= starts + 31 * 86400:
        ends = None
    with tx(con):
        a = one(con, "SELECT org_id, event_id FROM auto_events WHERE post_id = ?", pid)
        if not a or a["event_id"]:
            return None
        day = day_start(starts)
        if any(_similar(e["title"], f["title"]) for e in rows(con, "SELECT title FROM events WHERE org_id = ? AND starts_at >= ? AND starts_at < ?",
                                                             a["org_id"], day, day + 86400)):
            return None
        e = {"title": f["title"], "description": f.get("description", ""), "starts_at": starts, "ends_at": ends, "place": f.get("place", ""),
             "emoji": f.get("emoji", "party_popper_3d"), "color": f.get("color", "#3B6BFF")}
        if "onlineUrl" in f:  # a known meeting host's only (core.meet_link): online, no place
            e.update(place="", online=f["onlineUrl"])
        # ponytail: a stated price stays in the description: a paid event needs the club's own Kaspi details first
        if "tr" in f:
            e.update(organizing._own_tr({"tr": f["tr"]}, e))
        e["tint"] = organizing.shade(e["color"])
        t = now()  # one time for both: an untouched draft is one whose updated_at is its created_at (cover)
        eid = con.execute(f"""INSERT INTO events (org_id, status, {', '.join(e)}, created_at, updated_at)
            VALUES (?, 'draft', {', '.join('?' * len(e))}, ?, ?)""", (a["org_id"], *e.values(), t, t)).lastrowid  # keys from above
        con.execute("UPDATE auto_events SET event_id = ? WHERE post_id = ?", (eid, pid))
        cover(con, pid)
        for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", a["org_id"]):
            notify(con, uid, "auto_event", f"ae:{eid}")
    return eid


async def propose(con, cfg, http: httpx.AsyncClient, pid: int, text: str, posted: int) -> int | None:
    """A new channel post's one look (userbot.Mirror.post): the draft's id, or None. The model's failure drops it, said
    in the log only (the post stays looked at: no retries)."""
    if not worth(text) or not llm.available(cfg) or not (msgs := claim(con, pid, text, posted)):
        return None
    try:
        # a club's public announcement: the providers the policy names for public texts
        answer, _ = await llm.chat(cfg, http, msgs, con=con, only=ai.PUBLIC_PROVIDERS if ai_on(cfg) else ai.EU_ONLY, chain=ai.chain(cfg),
                                   max_tokens=3500, temperature=0.1, check=answered, timeout=30, effort="none")
    except (llm.Busy, llm.BadAnswers) as exc:
        log.warning("autoev: post %d: %s", pid, type(exc).__name__)
        return None
    return made(con, pid, answer, text)


TALL_FOCUS = "0.500,0.200"  # a poster taller than wide (4:5, 3:4): its title sits high, the wide frames keep it in view
# an untouched draft: nobody saved it yet (the editor's save sets updated_at); +1: rows made before `at` above
UNTOUCHED = "e.status = 'draft' AND e.updated_at <= e.created_at + 1"


def cover(con, pid: int) -> None:
    """The post's picture as its draft's cover (the draft is the finished post), whenever it reaches the
    post (an album's photo after its caption: mirror.take calls this too), only while the draft is untouched and has none:
    a cover a person set, or took off, stays. The event gets its own file row (event_cover, no owner) over the same
    stored picture (files are named by their content, media.store): the draft's delete drops that row, the post's
    take-down the post's (uncover), and the picture leaves the disk with the last row (account._drop_photo)."""
    with tx(con):
        r = one(con, f"""SELECT e.id AS eid, f.* FROM auto_events a
            JOIN events e ON e.id = a.event_id AND {UNTOUCHED} AND e.hidden_at IS NULL AND e.cover_file_id IS NULL
            JOIN posts p ON p.id = a.post_id AND p.hidden_at IS NULL JOIN files f ON f.id = p.photo_file_id WHERE a.post_id = ?""", pid)
        if not r:
            return
        own = one(con, "SELECT id FROM files WHERE path = ? AND kind = 'event_cover' AND owner_id IS NULL ORDER BY id LIMIT 1", r["path"])
        fid = own["id"] if own else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_cover', ?, ?, ?, ?, ?, NULL, ?, ?)""", (r["sha256"], r["mime"], r["bytes"], r["width"], r["height"],
                                                                   r["path"], now(), r["color"])).lastrowid
        con.execute("UPDATE events SET cover_file_id = ?, cover_focus = ? WHERE id = ?",
                    (fid, TALL_FOCUS if (r["height"] or 0) > (r["width"] or 0) else None, r["eid"]))


def uncover(con, pid: int) -> list[str]:
    """A post taken down (newsfeed.wipe_post): its picture leaves its draft too while that is still the untouched draft
    wearing it; a published event, or a cover a person chose, keeps its own. Inside the caller's tx, before the post's
    photo goes; the files to remove from disk (none: the post's row still has the picture)."""
    r = one(con, f"""SELECT e.id, e.cover_file_id FROM auto_events a JOIN events e ON e.id = a.event_id AND {UNTOUCHED}
        JOIN files c ON c.id = e.cover_file_id AND c.kind = 'event_cover' AND c.owner_id IS NULL
        JOIN posts p ON p.id = a.post_id JOIN files f ON f.id = p.photo_file_id AND f.path = c.path WHERE a.post_id = ?""", pid)
    if not r:
        return []
    con.execute("UPDATE events SET cover_file_id = NULL, cover_focus = NULL WHERE id = ?", (r["id"],))
    return _drop_unused(con, r["cover_file_id"])


def from_posts(con, eids: list[int]) -> dict[int, str]:
    """Which of these drafts came from a channel post: event id -> the post's link."""
    if not eids:
        return {}
    return dict(rows(con, f"""SELECT a.event_id, p.tg_url FROM auto_events a JOIN posts p ON p.id = a.post_id
        WHERE a.event_id IN ({','.join('?' * len(eids))}) AND p.tg_url IS NOT NULL""", *eids))


def queue(con) -> list[dict]:
    """Admin's queue: the drafts found in channels, still drafts, not dismissed (an admin's delete hides it at once)."""
    found = rows(con, """SELECT o.*, e.id AS ev, e.title AS ev_title, e.starts_at AS ev_at, e.place AS ev_place, a.at AS found_at, p.tg_url AS ev_url,
            e.cover_file_id, e.cover_focus, e.emoji AS ev_emoji, e.color AS ev_color, e.tint AS ev_tint
        FROM auto_events a JOIN events e ON e.id = a.event_id AND e.status = 'draft' AND e.hidden_at IS NULL
        JOIN posts p ON p.id = a.post_id JOIN orgs o ON o.id = e.org_id AND o.status = 'active' ORDER BY a.at""")
    return [{"id": r["ev"], "title": r["ev_title"], "startsAt": r["ev_at"], "place": r["ev_place"], "at": r["found_at"], "url": r["ev_url"],
             "org": org_ref(con, r), "cover": _event_cover(con, r, by=[]), "emoji": r["ev_emoji"], "color": r["ev_color"], "tint": r["ev_tint"]} for r in found]


from . import assistant, organizing  # noqa: E402  (they import the other domains last too)
from .account import _drop_unused, ai_on  # noqa: E402
from .seats import notify  # noqa: E402
