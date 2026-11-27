"""Events for students: the lists, registration and seats, receipts, volunteers, event chats, the channel, calendars."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time

from .. import receipt, texts
from ..db import tx

from .core import (ApiError, HOLD, NO_END, PERSON_COLS, RANK, Viewer, _free_seat, _roles, at_least, can, card, cards,
    STAFF_KINDS, deleting, full, log_action, need_student, one, person_ref, role_in, rows, taken)


# ------------------------------------------------------------ volunteers
# An event asks for N volunteers (maybe not year 1); a student applies with a short "why", the organizer (the "events"
# right) says yes or no, the bot tells them. A volunteer is the team's help: no ticket, no seat taken.

def _volunteers_view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict | None:
    if not e["volunteers"]:
        return None
    n = dict(rows(con, "SELECT status, COUNT(*) FROM volunteers WHERE event_id = ? GROUP BY status", e["id"]))
    mine = one(con, "SELECT status FROM volunteers WHERE event_id = ? AND user_id = ?", e["id"], v.id)
    return {"need": e["volunteers"], "senior": bool(e["volunteers_senior"]), "taken": n.get("yes", 0),
            "mine": mine["status"] if mine else None, **({"asked": n.get("asked", 0)} if head else {})}


def volunteer_apply(con, v: Viewer, eid: int, note: object) -> dict:
    need_student(v)
    text = " ".join(str(note or "").split())
    if len(text) > 300:
        raise ApiError("bad_input")
    with tx(con):
        e = _event(con, v, eid)
        if e["status"] != "published" or not e["volunteers"] or e["starts_at"] <= core.now():
            raise ApiError("closed")
        if e["volunteers_senior"] and (one(con, "SELECT course FROM students WHERE user_id = ?", v.id) or {"course": None})["course"] == 1:
            raise ApiError("forbidden", "first_year")
        if one(con, "SELECT COUNT(*) FROM volunteers WHERE event_id = ? AND status = 'yes'", eid)[0] >= e["volunteers"]:
            raise ApiError("closed", "full")
        if con.execute("INSERT OR IGNORE INTO volunteers (event_id, user_id, status, note, created_at) VALUES (?, ?, 'asked', ?, ?)",
                       (eid, v.id, text, core.now())).rowcount == 0:
            raise ApiError("conflict")
    return full(con, v, e)


def volunteer_leave(con, v: Viewer, eid: int) -> dict:
    """Taking my application back (or stepping down): the place opens again."""
    e = _event(con, v, eid)
    # a "no" holds: deleting it would let them apply again into the organizer's queue (Inkar's review, Nov 23)
    con.execute("DELETE FROM volunteers WHERE event_id = ? AND user_id = ? AND status != 'no'", (eid, v.id))
    return full(con, v, e)


def volunteers_list(con, v: Viewer, eid: int) -> list[dict]:
    """The organizer's list: waiting first, then yes, then no; full names and course, as with applications to a club."""
    _staff_event(con, v, eid, "events")
    found = rows(con, f"""SELECT x.status, x.note, x.created_at AS at, {PERSON_COLS}, s.course, s.school, u.tg_username
        FROM volunteers x JOIN users u ON u.id = x.user_id JOIN students s ON s.user_id = u.id
        WHERE x.event_id = ? ORDER BY CASE x.status WHEN 'asked' THEN 0 WHEN 'yes' THEN 1 ELSE 2 END, x.created_at""", eid)
    return [{"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "course": p["course"], "school": p["school"],
             "username": p["tg_username"], "note": p["note"], "status": p["status"], "at": p["at"]} for p in found]


def volunteer_decide(con, v: Viewer, eid: int, uid: int, yes: object) -> list[dict]:
    """Yes or no to one application; the bot tells them (a yes only while there is a place)."""
    if not isinstance(yes, bool):
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if yes and one(con, "SELECT COUNT(*) FROM volunteers WHERE event_id = ? AND status = 'yes' AND user_id != ?", eid, uid)[0] >= (e["volunteers"] or 0):
            raise ApiError("closed", "full")
        if not con.execute("UPDATE volunteers SET status = ?, decided_at = ? WHERE event_id = ? AND user_id = ?",
                           ("yes" if yes else "no", core.now(), eid, uid)).rowcount:
            raise ApiError("not_found")
        notify(con, uid, "volunteer_yes" if yes else "volunteer_no", f"vo:{eid}:{core.now()}")
    return volunteers_list(con, v, eid)


# ------------------------------------------------------------ event chats (no userbot)
# "Create chat" opens t.me/<bot>?startgroup=ec_<token>&admin=...: Telegram lets the organizer make or pick a group and
# adds the bot as its admin; the bot's /start there carries the token, so the group is this event's. The bot makes a
# join-request link and lets in only those signed up, approved volunteers and the club's team. The group is the
# organizer's own (they made it); the bot only lets people in.
# ponytail: someone who cancels stays in the group; the organizer removes them by hand if it matters.

def _chat_ok(con, e: sqlite3.Row, uid: int) -> bool:
    """Who the event's group takes: going (paid ones once paid), an approved volunteer, a member of the club."""
    return bool(one(con, """SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'
        UNION ALL SELECT 1 FROM volunteers WHERE event_id = ? AND user_id = ? AND status = 'yes'
        UNION ALL SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?""", e["id"], uid, e["id"], uid, e["org_id"], uid))


def chat_start(con, v: Viewer, eid: int) -> str:
    """The token for "Create chat" (the organizers'): a new one each time, the old link stops working."""
    if v.staff_org and not v.lent_full:  # the admin from Admin: a new token would cut the organizers' own link (the creator: as its President)
        raise ApiError("forbidden", "staff")
    e = _staff_event(con, v, eid, "events")
    if e["status"] == "cancelled":
        raise ApiError("closed")
    token = secrets.token_urlsafe(12)
    con.execute("UPDATE events SET chat_token = ? WHERE id = ?", (token, eid))
    return token


def chat_set(con, v: Viewer, eid: int, link: str | None) -> str | None:
    """"Paste the group's link": the organizers' own group by any t.me or invite link (chat_link), shown at once to
    those _chat_ok lets in; None removes it. Our bot isn't in that group, so whoever has the link gets in: a group the
    bot linked stops being the event's (its join requests no longer ours to decide). Rights as chat_start's."""
    if v.staff_org and not v.lent_full:
        raise ApiError("forbidden", "staff")
    e = _staff_event(con, v, eid, "events")
    if e["status"] == "cancelled":
        raise ApiError("closed")
    url = chat_link(link[:200]) if link else None
    if link and not url:
        raise ApiError("bad_input", "link")
    con.execute("UPDATE events SET chat_link = ?, chat_id = NULL, chat_token = NULL WHERE id = ?", (url, eid))
    return url


def chat_claim(con, token: str, tg_id: int, chat_id: int) -> sqlite3.Row | None:
    """The bot's /start ec_<token> in a group from someone who may run the event: the event, its token spent; else None."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE chat_token = ?", token)
        u = one(con, """SELECT u.id, u.role FROM users u JOIN students s ON s.user_id = u.id
            WHERE u.tg_id = ? AND u.banned_at IS NULL AND s.manual = 0""", tg_id)
        if not e or not u or not can(con, Viewer(u["id"], u["role"], True), e["org_id"], "events"):
            return None
        # a group another club's event or any chat of the app's list already holds stays theirs; the same club's earlier
        # event gives its group up to this one
        if core.chat_owners(con, chat_id) - {e["org_id"]} or one(con, "SELECT 1 FROM chats WHERE tg_chat_id = ? AND org_id IS NOT ?", chat_id, e["org_id"]):
            return None  # a synced chat too
        con.execute("UPDATE events SET chat_id = NULL, chat_link = NULL WHERE chat_id = ? AND id != ?", (chat_id, e["id"]))
        con.execute("UPDATE events SET chat_token = NULL, chat_id = ?, chat_link = NULL WHERE id = ?", (chat_id, e["id"]))
        return e


def chat_join(con, chat_id: int, tg_id: int) -> bool | None:
    """A join request to an event's group: True let in, False not; None when the group is no event's."""
    e = one(con, "SELECT * FROM events WHERE chat_id = ?", chat_id)
    if not e:
        return None
    u = one(con, "SELECT id FROM users WHERE tg_id = ?", tg_id)
    return bool(u and _chat_ok(con, e, u["id"]))


def guard_join(con, chat_id: int, tg_id: int) -> str:
    """A join request in a chat that made our bot its guard (Bot API 10.1 join request queries): an event's group keeps
    its own rule; a chat linked in the app (a club's, the chats list): a confirmed student in, a banned person out, the
    rest ("app") get the app to sign up; a chat the app doesn't know: its admins decide ("queue"; any chat can name us
    its guard, and it mustn't learn who our students are)."""
    ev = chat_join(con, chat_id, tg_id)
    if ev is not None:  # a ban outranks a ticket: else a banned attendee is let in
        return "approve" if ev and not one(con, "SELECT 1 FROM users WHERE tg_id = ? AND banned_at IS NOT NULL", tg_id) else "decline"
    if not one(con, "SELECT 1 FROM chats WHERE tg_chat_id = ? AND status IN ('live', 'org')", chat_id):
        return "queue"
    u = one(con, """SELECT u.banned_at, s.user_id AS student FROM users u
        LEFT JOIN students s ON s.user_id = u.id AND s.manual = 0 WHERE u.tg_id = ?""", tg_id)  # typed-in, unconfirmed: not yet
    return "decline" if u and u["banned_at"] else "approve" if u and u["student"] else "app"


GUARD_TTL = 15 * 60  # a guarded request's app link, then join again


def guard_token(key: bytes, chat_id: int, tg_id: int, qid: str) -> str:
    """The app's link for a guarded join request: who, where, which query, when, signed (no row kept: nothing to delete)."""
    body = base64.urlsafe_b64encode(json.dumps([chat_id, tg_id, qid, int(time.time())], separators=(",", ":")).encode()).decode().rstrip("=")
    return body + "." + hmac.new(key, body.encode(), hashlib.sha256).hexdigest()[:24]


def guard_read(key: bytes, token: str) -> tuple[int, int, str]:
    """(chat, Telegram id, query) from guard_token's link; forbidden when it's forged, gone when it's old."""
    body, _, sig = (token or "").partition(".")
    if not body or not hmac.compare_digest(sig.encode(), hmac.new(key, body.encode(), hashlib.sha256).hexdigest()[:24].encode()):  # bytes: a forged é is a 403, not a 500
        raise ApiError("forbidden")
    chat_id, tg_id, qid, at = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if at < time.time() - GUARD_TTL:
        raise ApiError("conflict", "expired")
    return int(chat_id), int(tg_id), str(qid)


# ------------------------------------------------------------ the events channel (@KBTUevents)
# Public events go to the channel once published: the cover, title, club, when, where, price and "Sign up"; a change of
# any of that edits the post, a cancel marks it. A few a round, so the first run fills the channel without a flood.
# ponytail: one post per event; a morning digest when there are many a day.

def for_me(con, v: Viewer, e: sqlite3.Row, role: str | None) -> bool:
    """A team-only event's "For whom" includes me (a member): the whole team; a tag's people; the board (Head+). The
    club's Vice+ and whoever runs its events see every one (they needn't come)."""
    if not e["meeting_tag"] and not e["for_board"]:
        return True
    if at_least(role, "vice") or can(con, v, e["org_id"], "events") or e["for_board"] and at_least(role, "head"):
        return True
    return bool(e["meeting_tag"] and one(con, "SELECT 1 FROM member_tags WHERE tag_id = ? AND user_id = ?", e["meeting_tag"], v.id))  # ponytail: a query per tagged card, rare


def channel_due(con, bot: str = "", limit: int = 3) -> list[tuple[sqlite3.Row, str, str | None, str]]:
    """Posts to make or fix: (event, caption, the cover's path or None, its signature). bot: our bot's username, for
    the sign-up link in the text. Who may be in the channel: an active official club or KBTU's own office; an
    initiative's free event while an official club co-hosts it ("Official × Initiative": the post then
    hangs on that club, channel_via); a post made before the ✓ went is kept in step. A post that may no longer be
    there (its official co-host left or lost the ✓, its club is archived or hidden) is deleted; it comes back with a
    new yes."""
    out = []
    t = core.now()
    for e in rows(con, """SELECT e.*, o.name AS org_name, o.official AS h_off, o.kind AS h_kind, o.status AS h_status,
            c.id AS co_id, c.name AS co_name, c.official AS co_off, f.path AS cover,
            e.starts_at > ? AND e.visibility = 'public' AND e.meeting = 0 AND e.hidden_at IS NULL AND e.school IS NULL
              AND e.silent_publish = 0
              AND (e.guest_host IS NULL OR e.channel_msg IS NOT NULL)  -- a partner's event isn't announced; one posted before it became one is kept in step
              AND (e.status = 'published' OR e.status = 'cancelled' AND e.channel_msg IS NOT NULL) AS live
            FROM events e JOIN orgs o ON o.id = e.org_id
            LEFT JOIN event_cohosts x ON x.event_id = e.id AND x.status = 'accepted'
            LEFT JOIN orgs c ON c.id = x.org_id AND c.status = 'active' AND c.kind = 'club'
            LEFT JOIN files f ON f.id = e.cover_file_id
            WHERE e.starts_at > ? AND (e.status != 'draft' OR e.channel_msg IS NOT NULL) OR e.channel_via IS NOT NULL
            ORDER BY e.published_at""", t, t):
        on = e["h_status"] == "active"
        own = on and (e["h_off"] or e["h_kind"] != "club")
        kept = on and e["channel_msg"] and e["channel_via"] is None
        vouch = on and e["co_off"] and not e["price"]  # free only
        if not e["live"] or not (own or kept or vouch):
            # one still to come that may not be there, or a past one that hung on a co-host now gone
            # (a collab a moderator hid goes too: the official club's name stays on nothing taken down)
            # a school's own event never: one posted before it was made so goes too
            upcoming = e["starts_at"] is not None and e["starts_at"] > t
            if e["channel_msg"] and (upcoming or e["school"] or e["channel_via"] is not None
                                     and (e["hidden_at"] or not (own or vouch and e["co_id"] == e["channel_via"]))):
                _unpost(con, e)
            continue
        via = None if own or kept else e["co_id"]
        if via != e["channel_via"]:
            con.execute("UPDATE events SET channel_via = ? WHERE id = ?", (via, e["id"]))
        # a co-hosted event names both clubs, the official one first
        names = [e["org_name"]] + ([e["co_name"]] if e["co_id"] else [])
        if e["co_id"] and e["co_off"] and not e["h_off"]:
            names.reverse()
        text = texts.channel_post(e["title"], " × ".join(names), e["starts_at"], e["ends_at"], texts.where(e["place"], e["online"] is not None, "en"), e["price"],
                                  e["status"] == "cancelled", f"https://t.me/{bot}?startapp=ev_{e['id']}" if bot else "")
        sig = hashlib.sha256(f"{text}|{e['cover']}".encode()).hexdigest()[:16]
        if sig != e["channel_sig"] and len(out) < limit:
            out.append((e, text, e["cover"], sig))
    return out


def _unpost(con, e: sqlite3.Row) -> None:
    """The event's channel post (and its copy in the discussion group) goes on the bot's next round (channel_gone)."""
    with tx(con):
        thread = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"thread:{e['id']}")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"channel_gone:{e['channel_msg']}", thread[0] if thread else ""))
        con.execute("""UPDATE events SET channel_msg = NULL, channel_photo = 0, channel_sig = NULL, channel_via = NULL, channel_link = NULL
            WHERE id = ?""", (e["id"],))


def channel_gone(con) -> list[tuple[int, str]]:
    """Channel posts of deleted events, still to delete: (the post's id, "chat_id message_id" of its discussion copy or "")."""
    return [(int(k.split(":")[1]), v) for k, v in rows(con, "SELECT key, value FROM meta WHERE key >= 'channel_gone:' AND key < 'channel_gone;'")]


def channel_discussion(con, post: int) -> sqlite3.Row | None:
    """The channel's post reached its discussion group (Telegram forwards it there by itself): the event whose post it is
    and that has no first comment yet, else None. The bot then writes the rules under it (bot_groups._discussion)."""
    return one(con, "SELECT * FROM events WHERE channel_msg = ? AND channel_link IS NULL", post)


def end_of(e: sqlite3.Row) -> int:
    return e["ends_at"] or e["starts_at"] + NO_END


def signup_open(e: sqlite3.Row) -> bool:
    """Its time lets one sign up or step out: before the start, or until the end with late sign-up on."""
    return e["starts_at"] > core.now() or bool(e["late_signup"]) and core.now() < end_of(e)


# "To calendar" on the ticket. The phone's browser fetches the file with no session, so the link is signed;
# app.create sets the key from TOKEN_KEY, the same in every worker process (this random one is for scripts).
ICS_KEY = secrets.token_bytes(32)


# "My link" to an event (ev_<id>_<code>): a code of its own, derived from the member's id, never their friend link's
# code (r_<link code> adds a friend at once); app.create sets the key from TOKEN_KEY, like ICS_KEY
REF_KEY = secrets.token_bytes(32)


def ev_ref(uid: int) -> str:
    return base64.b32encode(hmac.new(REF_KEY, f"evref:{uid}".encode(), hashlib.sha256).digest())[:10].decode()


def ics_sig(eid: int) -> str:
    return hmac.new(ICS_KEY, f"ics:{eid}".encode(), hashlib.sha256).hexdigest()[:32]


def _ics_text(s: str) -> str:
    # a bare CR is a line break to some calendar apps: an organizer's title could add properties to every feed
    return s.replace("\r", "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: at most 75 octets a line, continued after a space, never inside a UTF-8 character."""
    out, cur, n = [], "", 0
    for ch in line:
        b = len(ch.encode())
        if n + b > 75:
            out.append(cur)
            cur, n = " ", 1
        cur, n = cur + ch, n + b
    return "\r\n".join([*out, cur])


def title_in(row: sqlite3.Row, lang: str | None) -> str:
    """A title in a reader's language: an event's or a post's translation (ai.py, mirror.py) where
    there is one, else as typed. For the bot's messages and the calendar, which otherwise show only the source language."""
    tr = json.loads(row["i18n"]) if "i18n" in row.keys() and row["i18n"] else {}
    return (tr.get(lang) or {}).get("title") or row["title"]


def _vevent(e: sqlite3.Row, link: str, lang: str | None = None) -> list[str]:
    """One event (with its org's name as org_name) as VEVENT lines, its title in lang where translated; a cancelled one
    says so, and calendars strike it."""
    utc = lambda ts: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))  # noqa: E731
    return ["BEGIN:VEVENT", f"UID:ev{e['id']}@kbtu-app", f"DTSTAMP:{utc(core.now())}", f"DTSTART:{utc(e['starts_at'])}", f"DTEND:{utc(end_of(e))}",
            # an online event: the word, never its link (event_ics checks no visibility)
            "SUMMARY:" + _ics_text(title_in(e, lang)), "LOCATION:" + _ics_text(texts.where(e["place"], e["online"] is not None, lang or "en")),
            "DESCRIPTION:" + _ics_text(f"{e['org_name']}\n{link}"),
            "URL:" + link, *(["STATUS:CANCELLED"] if e["status"] == "cancelled" else []), "END:VEVENT"]


def _calendar(lines: list[str], *head: str) -> str:
    return "\r\n".join(_fold(x) for x in ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//KBTU App//EN", "METHOD:PUBLISH", *head, *lines, "END:VCALENDAR"]) + "\r\n"


def event_ics(con, eid: int, link: str) -> str:
    # Shared links have no viewer. Restricted events use the personal feed.
    e = one(con, """SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published'
        AND e.hidden_at IS NULL AND o.status != 'hidden' AND e.school IS NULL AND e.visibility = 'public'""", eid)
    if not e or not e["starts_at"]:
        raise ApiError("not_found")
    return _calendar(_vevent(e, link))


def cal_token(con, v: Viewer) -> str:
    """My calendar feed's secret: made once and kept, so a subscribed calendar stays subscribed."""
    need_student(v)
    t = one(con, "SELECT cal_token FROM users WHERE id = ?", v.id)[0]
    if not t:  # two first taps at once: only an empty one is set, both answer with the one kept
        con.execute("UPDATE users SET cal_token = ? WHERE id = ? AND cal_token IS NULL", (secrets.token_urlsafe(18), v.id))
        t = one(con, "SELECT cal_token FROM users WHERE id = ?", v.id)[0]
    return t


def reset_cal_token(con, v: Viewer) -> None:
    """A leaked feed address told where I'd be: the old one stops at once, the next tap on Calendar makes a new one."""
    need_student(v)
    con.execute("UPDATE users SET cal_token = NULL WHERE id = ?", (v.id,))


def calendar_owner(con, token: str) -> sqlite3.Row:
    u = one(con, """SELECT u.id, u.lang, u.role FROM users u JOIN students s ON s.user_id = u.id
        WHERE u.cal_token = ? AND s.manual = 0 AND u.banned_at IS NULL""", token) if token else None
    if not u:
        raise ApiError("not_found")
    return u


def cal_feed(con, token: str, link) -> str:
    """Everything I go to, from a month ago on: the phone's calendar refreshes it on its own (hourly asked), so a new
    registration shows up and a cancelled one goes; a cancelled event stays, struck through."""
    u = calendar_owner(con, token)
    # what the app would show me now: a club I left or was banned from keeps its team-only events to itself, a club the
    # admin hid is gone (else the feed keeps telling them)
    v = Viewer(u["id"], u["role"], True)
    roles, hidden = _roles(con, v), _hidden_orgs(con)
    evs = [e for e in rows(con, """SELECT e.*, o.name AS org_name FROM registrations r JOIN events e ON e.id = r.event_id JOIN orgs o ON o.id = e.org_id
        WHERE r.user_id = ? AND r.status IN ('going', 'hold') AND e.status IN ('published', 'cancelled') AND e.hidden_at IS NULL
        AND COALESCE(e.ends_at, e.starts_at + ?) > ? ORDER BY e.starts_at LIMIT 300""", u["id"], NO_END, core.now() - 30 * 86400)
        if _visible(con, v, e, roles, hidden)]
    return _calendar([x for e in evs for x in _vevent(e, link(e["id"]), u["lang"])], "X-WR-CALNAME:KBTU App", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H")


# ---------------------------------------------------------------- events

def school_ok(con, v: Viewer, e: sqlite3.Row) -> bool:
    """A school's own event (events.school, its slug) shows to that school's verified students, whoever runs it (the
    host's team, an accepted co-host's) and the admin acting from Admin. Not advertised to others, not access
    control: a student can change their school once (Settings); one signed up before keeps the event and the ticket."""
    if not e["school"] or v.staff_org == e["org_id"]:  # staff_org: the admin from Admin alone (app.viewer)
        return True
    if not v.student:
        return False
    if role_in(con, v, e["org_id"]) \
            or one(con, """SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status != 'cancelled'
                UNION ALL SELECT 1 FROM event_crew WHERE event_id = ? AND user_id = ?""", e["id"], v.id, e["id"], v.id):  # signed up, or its door helper
        return True
    s = one(con, "SELECT school FROM students WHERE user_id = ?", v.id)  # ponytail: a query per school card, rare
    from .account import school_slug  # account imports this module
    from .cohosts import ACCEPTED
    return school_slug(s["school"] if s else None) == e["school"] \
        or bool(one(con, ACCEPTED + " AND x.org_id IN (SELECT org_id FROM org_members WHERE user_id = ?)", e["id"], v.id))  # a co-host's team


def _school_unset(con, v: Viewer) -> bool:
    """A verified student whose school isn't known (empty, or no KBTU school): the refusal says to set it in Settings."""
    from .account import school_slug  # account imports this module
    s = one(con, "SELECT school FROM students WHERE user_id = ?", v.id) if v.student else None
    return bool(s) and school_slug(s["school"]) is None


def sees_school(con, uid: int, e: sqlite3.Row) -> bool:
    """school_ok for someone who isn't the one asking: a friend invited, the bot's message to them (app.viewer's rule
    for a student: a verified row, not a hand-made one)."""
    if not e["school"]:
        return True
    u = one(con, "SELECT role, EXISTS (SELECT 1 FROM students WHERE user_id = users.id AND manual = 0) AS st FROM users WHERE id = ?", uid)
    return bool(u) and school_ok(con, Viewer(uid, u["role"], bool(u["st"])), e)


def _visible(con, v: Viewer, e: sqlite3.Row, roles: dict[int, str] | None = None, hidden: set[int] | None = None,
             school: bool = True) -> bool:
    """Drafts and hidden events only for the organizing team (and the admin); team-only events for members; a school's
    own event for its students (school_ok). `roles` (_roles()) and `hidden` (_hidden_orgs()): read once when checking
    a list."""
    if (e["org_id"] in hidden) if hidden is not None else one(con, "SELECT 1 FROM orgs WHERE id = ? AND status = 'hidden'", e["org_id"]):
        return False  # a club the admin hid: its events are gone for everyone
    roles = _roles(con, v) if roles is None else roles
    team = at_least(roles.get(e["org_id"]), "member")
    if school and e["school"] and not (team or school_ok(con, v, e)):
        return False
    if e["status"] == "draft" or e["hidden_at"]:
        # the admin's delete hides it (hidden_at) from its team and the admin too; read only for hidden rows, so rare
        return (team or v.role == "admin") and not (e["hidden_at"] and deleting(con, e["id"]))
    if e["visibility"] == "members":
        return team and for_me(con, v, e, roles[e["org_id"]])
    if e["visibility"] == "leaders":
        return team or at_least(max(roles.values(), key=RANK.__getitem__, default=None), e["leaders_from"] or "president")
    return True


def _hidden_orgs(con) -> set[int]:
    return {r[0] for r in rows(con, "SELECT id FROM orgs WHERE status = 'hidden'")}


def sweep_holds(con) -> None:
    """Expired holds give their seats back, and the waitlist moves (a worker does this too). The lock-free look first;
    under the lock again, so the GETs that saw the same expiry at once don't each promote() it."""
    if not one(con, "SELECT 1 FROM registrations WHERE status = 'hold' AND hold_until < ?", core.now()):
        return
    with tx(con):
        t = core.now()
        expired = rows(con, "SELECT DISTINCT event_id FROM registrations WHERE status = 'hold' AND hold_until < ?", t)
        if not expired:
            return  # another request swept them meanwhile
        con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'hold_expired', updated_at = ? WHERE status = 'hold' AND hold_until < ?", (t, t))
        for r in expired:
            promote(con, one(con, "SELECT * FROM events WHERE id = ?", r[0]))


def events(con, v: Viewer, frm: int | None = None, to: int | None = None, org: int | None = None, *,
           sweep: bool = True) -> list[dict]:
    if sweep:  # off for the read-only demo (app.is_demo): the worker sweeps anyway
        sweep_holds(con)
    hide_first = v.student and one(con, "SELECT hide_first_year FROM users WHERE id = ?", v.id)[0]
    # Bound starts_at to use an index range. The lookback covers even stored events longer than the
    # 31-day cap in organizing.clean_event, so they stay visible while they run.
    sql = "SELECT * FROM events e WHERE starts_at > ? AND status != 'draft' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) > ?"
    args: list = [core.now() - 366 * 86400, NO_END, core.now()]
    if org is None:
        sql += " AND " + on_afisha(); args += on_afisha_args(v)
        # a cancelled event stays a day, struck through, for those who meant to go; then it leaves the Afisha (owner)
        sql += " AND (status != 'cancelled' OR cancelled_at > ?)"; args.append(core.now() - CANCELLED_SHOWN)
    else:
        sql += " AND " + OF_ORG; args += [org, org]
    if frm is not None:
        sql += " AND starts_at >= ?"; args.append(frm)
    if to is not None:
        sql += " AND starts_at < ?"; args.append(to)
    if hide_first:
        sql += " AND first_year = 0"
    roles, hidden = _roles(con, v), _hidden_orgs(con)
    return cards(con, v, [e for e in rows(con, sql + " ORDER BY starts_at", *args) if _visible(con, v, e, roles, hidden)], share=True)


# a club's page: its own events and the ones it co-hosts (accepted, cohosts.py); args: the club twice
OF_ORG = """(org_id = ? OR id IN (SELECT x.event_id FROM event_cohosts x JOIN orgs c ON c.id = x.org_id AND c.status = 'active'
    WHERE x.org_id = ? AND x.status = 'accepted'))"""
CANCELLED_SHOWN = 86400  # a cancelled event's day on the Afisha
PAST_DAYS = 30  # the Afisha's "Past" reaches back a month


def past_events(con, v: Viewer, org: int | None = None, mine: bool = False, attended: bool = False) -> list[dict]:
    """The afisha's past events of the last PAST_DAYS (Afisha's "Past": what happened on campus, mine marked by the
    card's `my`), or a club's latest few (its page's "Recent": its own and the ones it co-hosts), or mine: the ones I
    was signed up for or came to. Attended: only my recent check-ins, including events off the Afisha."""
    where, args, n = (f"{on_afisha()} AND COALESCE(ends_at, starts_at + ?) > ?", [*on_afisha_args(v), NO_END, core.now() - PAST_DAYS * 86400], 50) \
        if org is None else (OF_ORG, [org, org], 6)
    if attended:
        if not v.student:
            return []
        where, args, n = ("""id IN (SELECT event_id FROM registrations WHERE user_id = ? AND checked_in_at IS NOT NULL)
                          AND COALESCE(ends_at, starts_at + ?) > ?""", [v.id, NO_END, core.now() - PAST_DAYS * 86400], -1)
    elif mine:
        where, args, n = ("id IN (SELECT event_id FROM registrations WHERE user_id = ? AND (status = 'going' OR checked_in_at IS NOT NULL))",
                          [v.id if v.student else 0], 50)
    found = rows(con, f"""SELECT * FROM events e WHERE status = 'published' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) <= ?
        AND {where} ORDER BY starts_at DESC LIMIT {n}""", NO_END, core.now(), *args)
    roles, hidden = _roles(con, v), _hidden_orgs(con)
    return cards(con, v, [e for e in found if _visible(con, v, e, roles, hidden)], share=True)


def afisha_ok(o: str) -> str:
    """SQL: the org `o` (its alias) puts its events on the general afisha by itself (no pre-moderation, so
    a student initiative's don't): an official club, a school, a council, KBTU's own office, or a student initiative at
    the path's top (orgs.top_at)."""
    return f"({o}.official = 1 OR {o}.kind != 'club' OR {o}.top_at IS NOT NULL)"


def on_afisha() -> str:
    """SQL: the event `e` (every caller's alias) is on the general afisha (no club asked) for the viewer (on_afisha_args): its
    host or an accepted, active co-host is afisha_ok, or it's mine whoever hosts it (my club's, signed up for, saved). The
    rest open on their club's page and by link. In the query, so a LIMIT counts only these."""
    e = "e"
    mine = "SELECT org_id FROM org_members WHERE user_id = ?"
    return f"""(EXISTS (SELECT 1 FROM orgs h WHERE h.id = {e}.org_id AND {afisha_ok('h')}) OR {e}.org_id IN ({mine})
        OR EXISTS (SELECT 1 FROM event_cohosts x JOIN orgs c ON c.id = x.org_id WHERE x.event_id = {e}.id AND x.status = 'accepted'
                   AND c.status = 'active' AND ({afisha_ok('c')} OR c.id IN ({mine})))
        OR {e}.id IN (SELECT event_id FROM registrations WHERE user_id = ? AND status != 'cancelled')
        OR {e}.id IN (SELECT event_id FROM saved_events WHERE user_id = ?))"""


def on_afisha_args(v: Viewer) -> list[int]:
    return [v.id if v.student else 0] * 4  # a guest's old rows don't count (_roles)


def _event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or not _visible(con, v, e):
        if e and e["school"] and _visible(con, v, e, school=False):
            raise ApiError("forbidden", "school", {"school": e["school"], **({"unset": True} if _school_unset(con, v) else {})})  # by its link: whose it is, nothing else
        raise ApiError("not_found")
    return e


def event(con, v: Viewer, eid: int, *, sweep: bool = True) -> dict:
    if sweep:
        sweep_holds(con)
    return full(con, v, _event(con, v, eid))


def _ticket_code(con, eid: int) -> str:
    """4 characters to read out and type at the door, no 0/O or 1/I/L, unique within the event (6 are
    long to type). ~20 bits is enough: only the event's door staff can check a code, and the scanner shows the holder's
    face. Stored as '<event id>-<code>', so the column's global UNIQUE is per-event uniqueness and the door finds a
    code by (event, code) alone; the API and the QR ('KBTU' + code, the smallest QR there is) carry the code."""
    while True:
        c = f"{eid}-" + "".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(4))
        if not one(con, """SELECT 1 FROM registrations WHERE ticket_code = ?
                UNION ALL SELECT 1 FROM retired_tickets WHERE ticket_code = ?""", c, c):
            return c


def renew_cancelled_ticket(con, eid: int, r: sqlite3.Row) -> None:
    """A reissued seat starts with a fresh credential and no attendance or phone from the old seat."""
    if r["status"] == "cancelled":
        con.execute("INSERT INTO retired_tickets (ticket_code, event_id) SELECT ticket_code, event_id FROM registrations WHERE id = ?", (r["id"],))
        con.execute("""UPDATE registrations SET ticket_code = ?, phone_shared = 0, checked_in_at = NULL,
            checked_in_by = NULL, checkin_manual = 0, walk_in = 0 WHERE id = ?""", (_ticket_code(con, eid), r["id"]))
        con.execute("DELETE FROM reg_age WHERE registration_id = ?", (r["id"],))


def notify(con, uid: int, kind: str, ref: str, payload: str = "{}", after: int | None = None) -> None:
    """Queue a bot message. (user, kind, ref) is unique, so a repeat is a no-op."""
    con.execute("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, ?, ?, ?, ?)",
                (uid, kind, ref, payload, after or core.now()))


def notify_staff(con, uids, kind: str, ref: str) -> None:
    """A staff work item to those of `uids` who haven't muted it. None of them the bot can write to (muted all, or no
    DMs: the Postman skips those), the owner gets it too (his own mute aside): nothing waits unheard."""
    uids = list(uids)
    if not uids:
        return
    muted = {r[0] for r in rows(con, "SELECT user_id FROM staff_mutes WHERE kind = ?", STAFF_KINDS[kind])}
    to = [u for u in uids if u not in muted]
    if not to or not one(con, f"SELECT 1 FROM users WHERE id IN ({','.join('?' * len(to))}) AND can_dm = 1 AND banned_at IS NULL AND tg_id > 0", *to):
        to += [r[0] for r in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0") if r[0] not in to]
    for uid in to:
        notify(con, uid, kind, ref)


def add_seats(con, v: Viewer, eid: int, n: object) -> dict:
    """"+N seats", the club's Head+: the waitlist moves into them at once, in order."""
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 500:
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published" or e["seats"] is None or e["starts_at"] <= core.now():
            raise ApiError("closed")
        con.execute("UPDATE events SET seats = seats + ?, updated_at = ? WHERE id = ?", (n, core.now(), eid))
        promote(con, one(con, "SELECT * FROM events WHERE id = ?", eid))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def promote(con, e: sqlite3.Row) -> None:
    """Free seats go to the waitlist in order: going, or a 30-min hold for paid events; a 1st-year student
    takes one of a paid event's free seats while any are left."""
    if e["guest_list"] or e["status"] != "published" or end_of(e) <= core.now():
        return  # a cancelled or finished event hands out no seats (a hold to pay for nothing)
    if one(con, "SELECT 1 FROM santa_events WHERE event_id = ? AND drawn_at IS NOT NULL", e["id"]):
        return  # Secret Santa is drawn: nobody new comes in, they would have no Santa (santa.py)
    places = -1 if e["seats"] is None else max(0, e["seats"] - taken(con, e["id"]))
    waiting = rows(con, """SELECT id, user_id FROM registrations WHERE event_id = ? AND status = 'waitlist'
        ORDER BY waitlisted_at, id LIMIT ?""", e["id"], places)
    for nxt in waiting:
        pay = bool(e["price"]) and not _free_seat(con, e, nxt["user_id"])
        if pay:
            con.execute("UPDATE registrations SET status = 'hold', hold_until = ?, waitlisted_at = NULL, created_at = ?, updated_at = ? WHERE id = ?",
                        (min(core.now() + HOLD, end_of(e)), core.now(), core.now(), nxt["id"]))
        else:
            con.execute("UPDATE registrations SET status = 'going', free = ?, waitlisted_at = NULL, updated_at = ? WHERE id = ?",
                        (int(bool(e["price"])), core.now(), nxt["id"]))
            _remind(con, nxt["user_id"], e)
        notify(con, nxt["user_id"], "seat_hold" if pay else "seat_free", f"event:{e['id']}:{core.now()}")  # a hold: pay within 30 min; each promotion its own


ANSWER_MAX = 200  # one answer to an event's question at sign-up


# a host club's member's guest seat at its own upcoming public event: a free event's, or a waitlist place anywhere (a
# paid seat or hold stays to preserve payments, and a check-in stays as an attendance record).
# A President's or a Vice's seat stays, and so does a member's whom one of them let in (team_ask).
# ponytail: clubs whose own people sign up to its events like anyone (CyberSport's members play its
# cups); a per-club switch in Admin if more clubs want it
GUESTS_OK = frozenset({"cybersportkbtu"})


TEAM_SEATS = """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id WHERE r.user_id = ? AND e.org_id = ?
    AND e.status = 'published' AND e.visibility = 'public' AND e.team_max IS NULL AND e.starts_at > ? AND e.guest_list = 0
    AND (SELECT slug FROM orgs WHERE id = e.org_id) NOT IN ({}) AND r.checked_in_at IS NULL
    AND (r.status = 'waitlist' OR r.status IN ('going', 'hold') AND e.price IS NULL)
    AND NOT EXISTS (SELECT 1 FROM team_asks a WHERE a.event_id = e.id AND a.user_id = r.user_id AND a.status = 'yes')
    AND NOT EXISTS (SELECT 1 FROM org_members m WHERE m.org_id = e.org_id AND m.user_id = r.user_id AND m.role IN ('president', 'vice'))""".format(", ".join(f"'{x}'" for x in sorted(GUESTS_OK)))


def joined(con, oid: int, uid: int) -> None:
    """Someone is now in club oid (any path that adds a member, inside its transaction): their guest seats at its own
    upcoming events go back ('removed', no message: they're the team) and the waitlist moves into them."""
    for e in rows(con, TEAM_SEATS, uid, oid, core.now()):
        _seat_out(con, one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid), "removed", captain=False)
        promote(con, e)


def refill(con) -> None:
    """At start: the upcoming events migration 135 took team seats from hand them to their waitlists (a migration is SQL,
    promote() is not); after that it finds nothing to move."""
    with tx(con):
        for e in rows(con, """SELECT * FROM events WHERE status = 'published' AND starts_at > ?
                AND id IN (SELECT event_id FROM registrations WHERE cancel_reason = 'removed')
                AND id IN (SELECT event_id FROM registrations WHERE status = 'waitlist')""", core.now()):
            promote(con, e)


# A host club's member comes to its public event as a guest only by its President's or a Vice's yes:
# they ask once per event (team_asks), each President and Vice hears it from the bot and answers on the event's
# Studio screen. A President or a Vice needs nobody's yes (they'd be answering themselves). Their role, not a right:
# the app's admin has no path here. ponytail: a yes can't be taken back; a no can be asked again (one ping a day).
def team_guest(con, e: sqlite3.Row, uid: int) -> bool | None:
    """None: not of the host club; True: of it and may sign up (President, Vice, or let in); False: needs a yes."""
    m = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", e["org_id"], uid)
    if not m:
        return None
    # a team event (a tournament) is the club's members' to play in too (CyberSport's own play its cups)
    if e["team_max"] is not None or one(con, "SELECT slug FROM orgs WHERE id = ?", e["org_id"])["slug"] in GUESTS_OK:
        return True
    return m["role"] in ("president", "vice") or bool(one(
        con, "SELECT 1 FROM team_asks WHERE event_id = ? AND user_id = ? AND status = 'yes'", e["id"], uid))


def team_ask(con, v: Viewer, eid: int) -> dict:
    """A member asks to come as a guest; asking again while it waits changes nothing."""
    need_student(v)
    with tx(con):
        e = _event(con, v, eid)
        if e["guest_list"]:
            raise ApiError("guest_list")
        if e["status"] != "published" or e["visibility"] != "public" or not signup_open(e) or e["external_url"] or e["guest_host"]:
            raise ApiError("closed")
        if team_guest(con, e, v.id) is not False:
            raise ApiError("conflict")  # not of the club, or may sign up already
        if con.execute("""INSERT INTO team_asks (event_id, user_id, created_at) VALUES (?, ?, ?) ON CONFLICT (event_id, user_id)
                DO UPDATE SET status = 'pending', created_at = excluded.created_at, decided_by = NULL, decided_at = NULL
                WHERE status = 'no'""", (eid, v.id, core.now())).rowcount:
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice')", e["org_id"]):
                notify(con, uid, "team_ask", f"ta:{eid}:{v.id}:{core.now() // 86400}")  # asked again after a no: one ping a day
    return card(con, v, e)


def team_unask(con, v: Viewer, eid: int) -> dict:
    """Withdraw my ask while it waits."""
    need_student(v)
    e = _event(con, v, eid)
    con.execute("DELETE FROM team_asks WHERE event_id = ? AND user_id = ? AND status = 'pending'", (eid, v.id))
    return card(con, v, e)


def _team_decider(con, v: Viewer, eid: int) -> None:
    e = one(con, "SELECT org_id FROM events WHERE id = ?", eid)
    if not e or core.role_in(con, v, e["org_id"]) not in ("president", "vice"):
        raise ApiError("forbidden")


def team_asks(con, v: Viewer, eid: int) -> list[dict]:
    """The asks waiting on the event, oldest first (of those still in the club): its President and Vices only."""
    _team_decider(con, v, eid)
    return [{"person": person_ref(p), "createdAt": p["at"]} for p in rows(con, f"""SELECT {PERSON_COLS}, a.created_at AS at FROM team_asks a
        JOIN users u ON u.id = a.user_id LEFT JOIN students s ON s.user_id = u.id
        JOIN events e ON e.id = a.event_id JOIN org_members m ON m.org_id = e.org_id AND m.user_id = a.user_id
        WHERE a.event_id = ? AND a.status = 'pending' ORDER BY a.created_at""", eid)]


def team_decide(con, v: Viewer, eid: int, uid: int, yes: object) -> None:
    if not isinstance(yes, bool):
        raise ApiError("bad_input")
    with tx(con):
        _team_decider(con, v, eid)
        if not con.execute("UPDATE team_asks SET status = ?, decided_by = ?, decided_at = ? WHERE event_id = ? AND user_id = ? AND status = 'pending'",
                           ("yes" if yes else "no", v.id, core.now(), eid, uid)).rowcount:
            raise ApiError("conflict")  # withdrawn, or another one answered first
        notify(con, uid, "team_ask_yes" if yes else "team_ask_no", f"tad:{eid}:{core.now() // 86400}")


def _answers(e: sqlite3.Row, given: object) -> str | None:
    """The answers to an event's questions, one per question in order, each {q: the question's words as the form showed
    them, a: the answer}: a question changed since the form loaded refuses the lot (the app reloads it), a required one
    not empty, a choice one of its options, text up to 200. Kept with each question's words."""
    qs = json.loads(e["questions"]) if e["questions"] else []
    if not qs:
        return None
    if not isinstance(given, list) or len(given) != len(qs):
        raise ApiError("bad_input", "answers")
    out = []
    for q, x in zip(qs, given):
        if not isinstance(x, dict) or x.get("q") != q["label"] or not isinstance(x.get("a", ""), (str, type(None))):
            raise ApiError("conflict", "answers")
        a = " ".join((x.get("a") or "").split())
        if q["required"] and not a or len(a) > ANSWER_MAX or q["kind"] == "choice" and a and a not in q["options"]:
            raise ApiError("bad_input", "answers")
        if a:
            out.append({"q": q["label"], "a": a})
    return json.dumps(out, ensure_ascii=False)


def register(con, v: Viewer, eid: int, ref: object = None, phone: object = None, answers: object = None, wish: object = None) -> dict:
    """phone: typed in the sign-up when the event asks for it and none is kept yet; it's kept (Settings shows it).
    ref: the badge code of the club member whose link they came by ("My link", ev_<id>_<code>): the member gets the
    credit, the organizers see it in "Who brought"."""
    need_student(v)
    sweep_holds(con)
    with tx(con):  # count and insert under one write lock: the last seat goes to one person
        e = _event(con, v, eid)
        if e["status"] == "draft":
            raise ApiError("not_found")
        if e["guest_list"]:
            raise ApiError("guest_list")
        if e["status"] == "cancelled" or not signup_open(e):
            raise ApiError("closed")
        if e["reg_until"] and e["reg_until"] <= core.now():
            raise ApiError("closed", "deadline")
        if e["external_url"] or e["guest_host"]:  # signed up for elsewhere
            raise ApiError("bad_input")
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if r and r["status"] in ("going", "hold", "waitlist"):
            return card(con, v, e)
        if e["visibility"] == "public" and team_guest(con, e, v.id) is False:
            raise ApiError("forbidden", "team")  # the host club's own people run it, never its guests; co-hosts' may
        if e["needs_phone"] and phone is not None:
            if not (phone := kz_phone(phone)):
                raise ApiError("bad_input", "phone")
            con.execute("UPDATE students SET phone = ? WHERE user_id = ?", (phone, v.id))
        elif e["needs_phone"] and not one(con, "SELECT phone FROM students WHERE user_id = ?", v.id)[0]:
            raise ApiError("bad_input", "phone")  # the app asks for it and sends it with the same tap
        given = _answers(e, answers)  # the app asks the event's questions first and sends them with the same tap
        santa.wish(con, eid, v.id, wish)  # Secret Santa: the wishlist with the same tap, kept apart from the answers
        is_full = e["seats"] is not None and taken(con, eid) >= e["seats"]
        free = not is_full and _free_seat(con, e, v.id)
        status = "waitlist" if is_full else "hold" if e["price"] and not free else "going"
        hold = min(core.now() + HOLD, end_of(e)) if status == "hold" else None
        wait = core.now() if status == "waitlist" else None
        if r:
            renew_cancelled_ticket(con, eid, r)
            # signing up again starts a new seat: created_at is its start, so receipts from before it (a removal, a
            # self-cancel) don't count for it (organizing.flagged, the attendee list, the card)
            con.execute("""UPDATE registrations SET status = ?, cancel_reason = NULL, hold_until = ?, waitlisted_at = ?, free = ?, note = NULL, answers = ?, team_want = NULL, updated_at = ?,
                created_at = ?, phone_shared = ? WHERE id = ?""", (status, hold, wait, int(free), given, core.now(), core.now(), bool(e["needs_phone"]), r["id"]))
        else:
            # someone already in keeps whoever was first (this branch is new rows only); never myself
            # ponytail: one HMAC per member of the club; a stored code if a club ever has thousands
            inviter = next((m["user_id"] for m in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND user_id != ?", e["org_id"], v.id)
                            if hmac.compare_digest(ev_ref(m["user_id"]), ref)), None) if isinstance(ref, str) and ref.isascii() else None
            if inviter is None and isinstance(ref, str):  # an older event link carries the link code itself
                by = one(con, "SELECT m.user_id FROM users u JOIN org_members m ON m.user_id = u.id AND m.org_id = ? WHERE u.link_code = ? AND u.id != ?",
                         e["org_id"], ref, v.id)
                inviter = by["user_id"] if by else None
            if inviter is None:  # "Bring a friend": the first friend who asked gets the credit ("Life of the party")
                first = one(con, "SELECT from_id FROM friend_invites WHERE event_id = ? AND to_id = ? ORDER BY created_at LIMIT 1", eid, v.id)
                inviter = first["from_id"] if first else None
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, waitlisted_at, invited_by, free, answers, created_at, updated_at, phone_shared)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (eid, v.id, status, _ticket_code(con, eid), hold, wait, inviter, int(free), given, core.now(), core.now(), bool(e["needs_phone"])))
        if status == "going":
            _remind(con, v.id, e)
    return card(con, v, e)


RECEIPT_TRIES = 3  # another file in place of a receipt nobody looked at yet: this many times


def receipt_open(con, v: Viewer, eid: int) -> None:
    """Checked before a receipt's image is processed: the person holds a seat on this event, or has a receipt on it
    nobody looked at yet."""
    need_student(v)
    sweep_holds(con)
    with tx(con):
        _receipt_slot(con, v, eid)
        core.upload_attempt(con, v, "receipt")


def _receipt_slot(con, v: Viewer, eid: int) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row | None]:
    """Where a receipt goes: (registration, event, the receipt it replaces). A seat on hold takes one; a ticket takes
    another file in place of its receipt while the organizer hasn't looked at it and the event isn't over (the app
    says when a receipt looks wrong, "upload another?")."""
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('hold', 'going')", eid, v.id)
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if e and e["guest_list"] and (r or _visible(con, v, e)):
        raise ApiError("guest_list")
    old = None
    if r and (e["status"] != "published" or end_of(e) <= core.now() or r["status"] == "hold" and r["hold_until"] < core.now()):
        r = None  # cancelled since, or the hold ran out while the file was read (OCR): the waitlist's seat
    if r and r["status"] == "going":
        old = one(con, """SELECT * FROM receipts WHERE id = (SELECT MAX(id) FROM receipts WHERE registration_id = ?)
            AND status = 'accepted' AND reviewed_at IS NULL AND flags != 'spot' AND created_at >= ?""", r["id"], r["created_at"])  # this seat's own  # a spot one: as final as a checked one
        if not old:
            r = None
        elif one(con, "SELECT COUNT(*) FROM receipt_replaced WHERE registration_id = ?", r["id"])[0] >= RECEIPT_TRIES:
            raise ApiError("rate_limited", "receipt")  # enough: the organizer looks at the last one
    if not r:
        raise ApiError("closed")
    return r, e, old


def add_receipt(con, v: Viewer, eid: int, saved: dict, read: dict | None = None, via: str = "app") -> tuple[dict, list[str]]:
    """The receipt is in, from the app or the bot: the seat becomes a ticket at once. What OCR read off it
    (receipt.py; None = OCR didn't run) raises flags the organizer and student see (my.receiptFlags). Only a fully
    read, matching receipt is checked by the app; the others may be replaced (_receipt_slot, RECEIPT_TRIES times).
    Returns the card and the replaced picture's path, for the caller to drop from disk once this is committed."""
    with tx(con):
        r, e, old = _receipt_slot(con, v, eid)
        cid = core.next_id(con, "receipts")  # before deleting the old upload: stale reviews must never name its replacement
        f = None
        if old:  # its fingerprint stays (the duplicate check, the cap); its row and picture go
            f = one(con, "SELECT sha256, path FROM files WHERE id = ?", old["file_id"])
            con.execute("INSERT INTO receipt_replaced (registration_id, sha256, receipt_no, at) VALUES (?, ?, ?, ?)",
                        (r["id"], f["sha256"], old["receipt_no"], core.now()))
            con.execute("DELETE FROM receipts WHERE id = ?", (old["id"],))
            con.execute("DELETE FROM files WHERE id = ? AND NOT EXISTS (SELECT 1 FROM receipts WHERE file_id = ?)", (old["file_id"], old["file_id"]))
        got = read or {}
        flags = _receipt_flags(con, e, saved["sha256"], read, r["id"])
        # a clean one is checked by the app, but 1 in AUDIT waits for the organizer flagged 'spot' (their "Check receipts"),
        # so a forgery that beats OCR gets seen. The draw is once per seat: a seat that had any receipt before (replaced,
        # or before a cancel; one row per person and event) is always picked, so neither re-rolls it. Not clean and no
        # warning either (a field unread): 'partial', in "Check receipts" too, and held at the door until reviewed.
        # A payment predating this hold also needs review: deleted accounts erase duplicate evidence. Kaspi prints minutes.
        clean = _receipt_clean(con, e, saved["sha256"], read, flags) and got["paid_at"] >= r["created_at"] // 60 * 60
        if clean and (_audit() or one(con, """SELECT 1 FROM receipts WHERE registration_id = ?
                UNION ALL SELECT 1 FROM receipt_replaced WHERE registration_id = ?""", r["id"], r["id"])):
            flags, clean = SPOT, False
        elif not clean and not flags:
            flags = PARTIAL
        reviewed_at = core.now() if clean else None
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at)
            VALUES (?, 'receipt', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"], saved["path"], v.id, core.now())).lastrowid
        con.execute("""INSERT INTO receipts (id, registration_id, file_id, via, amount, receipt_no, sender_name, recipient_name, paid_at, flags, reviewed_at, reviewed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)""", (cid, r["id"], fid, via, got.get("amount"), got.get("no"), got.get("sender"), got.get("recipient"),
                                                                got.get("paid_at"), flags, reviewed_at, core.now()))
        if reviewed_at is not None:
            con.execute("INSERT INTO receipt_auto_checks (receipt_id) VALUES (?)", (cid,))
        if not old:
            con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE id = ?", (core.now(), r["id"]))
            evteams.paid(con, r["id"])  # the team its invite link was for, if it still has room
            _remind(con, v.id, e)
        # files are named by their content: the picture stays while any row (this new one too) has the same path
        gone = [f["path"]] if f and not one(con, "SELECT 1 FROM files WHERE path = ?", f["path"]) else []
    return card(con, v, e), gone


def _receipt_flags(con, e: sqlite3.Row, sha: str, read: dict | None, rid: int = 0) -> str:
    """The checks: the same file or receipt number came before, a
    smaller sum or a bigger one that isn't a whole number of tickets (else a 1 090 receipt for 164 passes), another recipient, a receipt older than the event itself (an old one reused), (nothing readable,
    not a Kaspi receipt, is refused before: receipt.NotReceipt). No sender check: parents and friends pay, the organizer just sees the name."""
    got = read or {}
    out = []
    # a receipt someone else replaced counts too, or replacing it would wash a reused one clean
    if one(con, "SELECT 1 FROM donations WHERE sha256 = ? OR receipt_no = ?", sha, got.get("no")) or \
            one(con, "SELECT 1 FROM files WHERE sha256 = ? AND kind = 'receipt'", sha) or \
            one(con, "SELECT 1 FROM receipt_replaced WHERE sha256 = ? AND registration_id != ?", sha, rid) or \
            got.get("no") and (one(con, "SELECT 1 FROM receipts WHERE receipt_no = ?", got["no"])
                               or one(con, "SELECT 1 FROM receipt_replaced WHERE receipt_no = ? AND registration_id != ?", got["no"], rid)) or \
            any(not (got.get("sender") and x["sender_name"] and got["sender"] != x["sender_name"]) for x in _same_minute(con, got)):
        # the same minute, sum and payee under another number: a used receipt with its number edited; from another
        # sender (two friends paying together) it's no warning, only not the app's to pass (_receipt_clean: 'partial')
        out.append("duplicate")
    if read is None:
        out.append("ocr_unavailable")
    elif not (got.get("no") and got.get("amount")):
        out.append("unreadable")  # no number or sum: the duplicate check couldn't run, the organizer looks
    if got.get("amount") and e["price"] and got["amount"] < e["price"]:
        out.append("amount_short")
    elif got.get("amount") and e["price"] and got["amount"] % e["price"]:
        out.append("amount_over")
    if got.get("recipient") and e["pay_to_name"] and not receipt.same_person(got["recipient"], e["pay_to_name"]):
        out.append("recipient_mismatch")
    if got.get("paid_at") and got["paid_at"] < e["created_at"]:
        out.append("too_early")
    return ",".join(out)


AUDIT = 5
SPOT = "spot"  # the only flag a clean receipt carries: picked for a person's look, nothing wrong found
PARTIAL = "partial"  # payment not fully verified: a person must check before admission


def _audit() -> bool:
    return secrets.randbelow(AUDIT) == 0  # tests patch it


def _same_minute(con, got: dict) -> list[sqlite3.Row]:
    """Receipts with this one's minute, sum and payee (Kaspi prints the minute)."""
    if not (got.get("paid_at") and got.get("amount") and got.get("recipient")):
        return []
    return rows(con, """SELECT sender_name FROM receipts WHERE paid_at = ? AND amount = ? AND recipient_name = ?
        UNION ALL SELECT sender_name FROM donations WHERE paid_at = ? AND read_amount = ? AND recipient_name = ?""",
                *([got["paid_at"], got["amount"], got["recipient"]] * 2))


def _receipt_clean(con, e: sqlite3.Row, sha: str, read: dict | None, flags: str) -> bool:
    """Auto-review requires every essential field, not just no flags. Sender isn't essential (others may pay).
    The flags already check the payee and duplicates; this seat's replaced files and numbers also aren't new.
    A payee typed as a first name alone matches any namesake (receipt.same_person skips the initial): a person looks."""
    return bool(read and flags == "" and e["price"] and read.get("amount") == e["price"] and not read.get("signed")
                and read.get("recipient") and e["pay_to_name"] and len(e["pay_to_name"].split()) > 1
                and receipt.same_person(read["recipient"], e["pay_to_name"], strict=True)
                and read.get("no") and read.get("paid_at")
                and e["created_at"] <= read["paid_at"] <= core.now()
                and not one(con, "SELECT 1 FROM receipt_replaced WHERE receipt_no = ? OR sha256 = ?", read["no"], sha)
                and not _same_minute(con, read))


def receipt_path(con, v: Viewer, rid: int) -> str:
    """The sender or a verified member of the host club with its events right may open the original."""
    c = one(con, """SELECT f.path, r.user_id, e.org_id FROM receipts c JOIN files f ON f.id = c.file_id
        JOIN registrations r ON r.id = c.registration_id JOIN events e ON e.id = r.event_id WHERE c.id = ?""", rid)
    if not c or not (c["user_id"] == v.id or v.student and "events" in core.rights_of(con, v.id, c["org_id"])):
        raise ApiError("not_found")
    return c["path"]


REJECT_WHY = ("short", "other_event", "used", "unclear")  # texts.REJECT_WHY: the bot names it to the student


def review_receipt(con, v: Viewer, rid: int, reject: object, why: object = None) -> None:
    """The organizer checked a receipt against their Kaspi history: fine, or rejected — then the ticket stops
    working, the seat goes to the waitlist and the bot tells the student to talk to the club. Refunds happen outside.
    why: a rejection's reason, one of REJECT_WHY (never words); none (an old client): the bot's old text."""
    if not isinstance(reject, bool) or why is not None and (not reject or why not in REJECT_WHY):
        raise ApiError("bad_input")
    with tx(con):
        c = one(con, "SELECT c.*, r.event_id, r.user_id, r.status AS reg, r.free, r.created_at AS since FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE c.id = ?", rid)
        if not c:
            raise ApiError("not_found")
        e = _staff_event(con, v, c["event_id"], "events")
        if c["status"] == "rejected":
            return
        con.execute("UPDATE receipts SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?", ("rejected" if reject else "accepted", v.id, core.now(), rid))
        con.execute("DELETE FROM receipt_auto_checks WHERE receipt_id = ?", (rid,))
        if reject:
            log_action(con, v.id, "receipt_reject", f"receipt:{rid}", json.dumps({"why": why}) if why else "{}")
            # an old receipt from before a cancel and a new sign-up (the same row) doesn't end the new ticket: not a
            # free one (1st-year seat), not one on an event free now, not one paid by a newer receipt
            if not e["guest_list"] and c["reg"] == "going" and not c["free"] and e["price"] and c["created_at"] >= c["since"] and rid == one(con, "SELECT MAX(id) FROM receipts WHERE registration_id = ?", c["registration_id"])[0]:
                _seat_out(con, one(con, "SELECT * FROM registrations WHERE id = ?", c["registration_id"]), "receipt_rejected")  # the captain hears it
                notify(con, c["user_id"], "receipt_rejected", f"event:{e['id']}:{rid}", json.dumps({"why": why}) if why else "{}")
                promote(con, e)


def seat_by_hand(con, uid: int, eid: int) -> str:
    """`kbtu.admin seat`: the creator seats a student on an event himself, a paid one too, with no receipt (their bank
    would not share the file; the organizer vouches for the money). Whatever the seat was (a hold, the waitlist, a
    cancelled one, none), it is a ticket now, past the cap; the team its invite link was for, the reminder and the audit
    log as after a receipt. Nothing about money is recorded: the attendee list shows the seat without a receipt."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published'", eid)
        if not e or not one(con, "SELECT 1 FROM students WHERE user_id = ?", uid):
            return "no such published event, or not a student"
        if e["guest_list"]:
            return "use guests for this event"
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if r and r["status"] == "going":
            return "already going"
        if r:
            renew_cancelled_ticket(con, eid, r)
            # a new seat starts now, as on a sign-up: receipts from before it aren't this seat's
            con.execute("""UPDATE registrations SET status = 'going', cancel_reason = NULL, hold_until = NULL, waitlisted_at = NULL,
                free = 0, updated_at = ?, created_at = ? WHERE id = ?""", (core.now(), core.now(), r["id"]))
            rid = r["id"]
        else:
            rid = con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, ?, ?)",
                              (eid, uid, _ticket_code(con, eid), core.now(), core.now())).lastrowid
        evteams.paid(con, rid)
        _remind(con, uid, e)
        core.log_action(con, None, "seat_by_hand", f"registration:{rid}", json.dumps({"event": eid, "was": r["status"] if r else None}))
    return f"seated (was: {r['status'] if r else 'no seat'})"


def _remind(con, uid: int, e: sqlite3.Row) -> None:
    """The 2-hour reminder, unless the person turned it off; ref carries the start, so a moved event re-arms it."""
    if one(con, "SELECT n_remind FROM users WHERE id = ?", uid)[0] and e["starts_at"] - 7200 > core.now():
        notify(con, uid, "remind_2h", f"event:{e['id']}:{e['starts_at']}", after=e["starts_at"] - 7200)


def unregister(con, v: Viewer, eid: int) -> dict:
    need_student(v)
    with tx(con):
        e = _event(con, v, eid)
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if not r:
            raise ApiError("not_found")
        if r["checked_in_at"]:  # in the room already (a late-sign-up event): the seat stays, as remove_seats keeps it
            raise ApiError("conflict", "checked_in")
        if not signup_open(e):
            raise ApiError("closed")
        if r["status"] != "cancelled" and _seat_out(con, r, "self"):  # a stale second cancel keeps why it ended
            promote(con, e)
    return card(con, v, e)


def _seat_out(con, r: sqlite3.Row, why: str, captain: bool = True) -> bool:
    """A seat ends (a self-cancel, the organizer's removal): out of its team (migration 161's trigger; the captain hears
    it unless the whole team goes), the 2-hour reminder unsent. Receipts stay as they are (refunds happen outside the
    app, the duplicate check keeps knowing the file). True when a seat was freed: the caller promotes the waitlist."""
    if captain:
        evteams.left(con, r["event_id"], r["user_id"])
    con.execute("""UPDATE registrations SET status = 'cancelled', cancel_reason = ?, hold_until = NULL, waitlisted_at = NULL, updated_at = ?
        WHERE id = ?""", (why, core.now(), r["id"]))
    con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (r["user_id"], f"event:{r['event_id']}:%"))
    return r["status"] in ("going", "hold")


def remove_seats(con, v: Viewer, eid: int, uid: int | None = None, team: int | None = None, people: object = None) -> None:
    """The organizer (the "events" right, not a co-host) takes one person, or a whole team, off the event before it
    starts: each seat ends as a self-cancel does (cancel_reason 'removed'), the waitlist moves in, each hears the bot's
    template, the audit log keeps who removed whom. A paid seat's receipts stay (the refund is the club's, by hand); a
    removed person may sign up again like anyone, and an old receipt sent again is flagged a duplicate. Someone already
    checked in is refused: they came, and the door's record stays. A team goes only as the roster the organizer
    confirmed (people: its user ids): a player who joined since, or a team id reused, is `changed` and nothing moves.
    The app's admin from Admin (STAFF_RIGHTS: never money) removes on a free event only."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if team is not None and not (isinstance(people, list) and people and all(type(x) is int for x in people)):
            raise ApiError("bad_input")
        if e["price"] and v.staff_org == e["org_id"] and not v.lent_full and not (v.student and "events" in core.rights_of(con, v.id, e["org_id"])):
            raise ApiError("forbidden", "staff")  # a paid seat is money: the club's own, or the creator's as its President
        if e["status"] != "published" or e["starts_at"] <= core.now():
            raise ApiError("closed")
        name = None
        if team is not None:
            uids = [x[0] for x in rows(con, "SELECT user_id FROM event_team_members WHERE team_id = ? AND event_id = ?", team, eid)]
            if uids and set(uids) != set(people):
                raise ApiError("conflict", "changed")
            name = (one(con, "SELECT name FROM event_teams WHERE id = ?", team) or [None])[0]
        else:
            uids = [uid]
        regs = [one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')", eid, u) for u in uids]
        if not regs or None in regs:
            raise ApiError("not_found")
        if any(r["checked_in_at"] for r in regs):
            raise ApiError("conflict", "checked_in")
        freed = False
        for r in regs:
            freed = _seat_out(con, r, "removed", captain=team is None) or freed
            notify(con, r["user_id"], "seat_removed", f"event:{eid}:{core.now()}")
            log_action(con, v.id, "seat_remove", f"registration:{r['id']}",
                       json.dumps({"event": eid, "user": r["user_id"], "was": r["status"], "team": team, "teamName": name}, ensure_ascii=False))
        if freed:
            promote(con, e)


def set_saved(con, v: Viewer, eid: int, on: bool) -> None:
    need_student(v)
    _event(con, v, eid)
    if on:
        con.execute("INSERT OR IGNORE INTO saved_events (user_id, event_id, created_at) VALUES (?, ?, ?)", (v.id, eid, core.now()))
    else:
        con.execute("DELETE FROM saved_events WHERE user_id = ? AND event_id = ?", (v.id, eid))


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core, evteams, santa  # noqa: E402
from .chatlist import chat_link  # noqa: E402
from .organizing import _staff_event, kz_phone  # noqa: E402
