"""Events for students: the lists, registration and seats, receipts, volunteers, event chats, the channel, calendars."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time

from .. import receipt, texts
from ..db import tx

from .core import (ApiError, HOLD, NO_END, PERSON_COLS, RANK, Viewer, _free_seat, _roles, at_least, can, card, cards,
    full, log_action, need_student, one, person_ref, rows, taken)


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
    con.execute("DELETE FROM volunteers WHERE event_id = ? AND user_id = ?", (eid, v.id))
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
    e = _staff_event(con, v, eid, "events")
    if e["status"] == "cancelled":
        raise ApiError("closed")
    token = secrets.token_urlsafe(12)
    con.execute("UPDATE events SET chat_token = ? WHERE id = ?", (token, eid))
    return token


def chat_claim(con, token: str, tg_id: int, chat_id: int) -> sqlite3.Row | None:
    """The bot's /start ec_<token> in a group from someone who may run the event: the event, its token spent; else None."""
    e = one(con, "SELECT * FROM events WHERE chat_token = ?", token)
    u = one(con, "SELECT id, role FROM users WHERE tg_id = ?", tg_id)
    if not e or not u or not can(con, Viewer(u["id"], u["role"], True), e["org_id"], "events"):
        return None
    con.execute("UPDATE events SET chat_token = NULL, chat_id = ?, chat_link = NULL WHERE id = ?", (chat_id, e["id"]))
    return e


def chat_join(con, chat_id: int, tg_id: int) -> bool | None:
    """A join request to an event's group: True let in, False not; None when the group is no event's."""
    e = one(con, "SELECT * FROM events WHERE chat_id = ?", chat_id)
    if not e:
        return None
    u = one(con, "SELECT id FROM users WHERE tg_id = ?", tg_id)
    return bool(u and _chat_ok(con, e, u["id"]))


# ------------------------------------------------------------ the events channel (@KBTUevents)
# Public events go to the channel once published: the cover, title, club, when, where, price and "Sign up"; a change of
# any of that edits the post, a cancel marks it. A few a round, so the first run fills the channel without a flood.
# ponytail: one post per event; a morning digest when there are many a day.

def channel_due(con, bot: str = "", limit: int = 3) -> list[tuple[sqlite3.Row, str, str | None, str]]:
    """Posts to make or fix: (event, caption, the cover's path or None, its signature). bot: our bot's username, for
    the sign-up link in the text."""
    out = []
    for e in rows(con, """SELECT e.*, o.name AS org_name, f.path AS cover FROM events e JOIN orgs o ON o.id = e.org_id
            LEFT JOIN files f ON f.id = e.cover_file_id
            WHERE e.visibility = 'public' AND e.meeting = 0 AND e.hidden_at IS NULL AND o.status != 'hidden' AND e.starts_at > ?
              AND (e.guest_host IS NULL OR e.channel_msg IS NOT NULL)  -- a partner's event isn't announced; one posted before it became one is kept in step
              AND (e.status = 'published' OR e.status = 'cancelled' AND e.channel_msg IS NOT NULL) ORDER BY e.published_at""", core.now()):
        tr = json.loads(e["i18n"]) if e["i18n"] else {}  # the channel is everyone's: the other languages' titles under it (PLAN 9)
        also = [x for k in ("kk", "ru", "en") if (x := tr.get(k, {}).get("title")) and x.strip().lower() != e["title"].strip().lower()]
        text = texts.channel_post(e["title"], e["org_name"], e["starts_at"], e["place"], e["price"], e["status"] == "cancelled",
                                  f"https://t.me/{bot}?startapp=ev_{e['id']}" if bot else "", also)
        sig = hashlib.sha256(f"{text}|{e['cover']}".encode()).hexdigest()[:16]
        if sig != e["channel_sig"]:
            out.append((e, text, e["cover"], sig))
        if len(out) >= limit:
            break
    return out


def channel_gone(con) -> list[tuple[int, str]]:
    """Channel posts of deleted events, still to delete: (the post's id, "chat_id message_id" of its discussion copy or "")."""
    return [(int(k.split(":")[1]), v) for k, v in rows(con, "SELECT key, value FROM meta WHERE key LIKE 'channel_gone:%'")]


def channel_discussion(con, post: int) -> sqlite3.Row | None:
    """The channel's post reached its discussion group (Telegram forwards it there by itself): the event whose post it is
    and that has no first comment yet, else None. The bot then writes the rules under it (bot._discussion)."""
    return one(con, "SELECT * FROM events WHERE channel_msg = ? AND channel_link IS NULL", post)


def end_of(e: sqlite3.Row) -> int:
    return e["ends_at"] or e["starts_at"] + NO_END


# "To calendar" on the ticket (§4.2). The phone's browser fetches the file with no session, so the link is signed;
# app.create sets the key from TOKEN_KEY, the same in every worker process (this random one is for scripts).
ICS_KEY = secrets.token_bytes(32)


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
    """A title in a reader's language (PLAN 9, deferred then): an event's or a post's translation (ai.py, mirror.py) where
    there is one, else as typed. For the bot's messages and the calendar, which knew only the source language."""
    tr = json.loads(row["i18n"]) if "i18n" in row.keys() and row["i18n"] else {}
    return (tr.get(lang) or {}).get("title") or row["title"]


def _vevent(e: sqlite3.Row, link: str, lang: str | None = None) -> list[str]:
    """One event (with its org's name as org_name) as VEVENT lines, its title in lang where translated; a cancelled one
    says so, and calendars strike it."""
    utc = lambda ts: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))  # noqa: E731
    return ["BEGIN:VEVENT", f"UID:ev{e['id']}@kbtu-app", f"DTSTAMP:{utc(core.now())}", f"DTSTART:{utc(e['starts_at'])}", f"DTEND:{utc(end_of(e))}",
            "SUMMARY:" + _ics_text(title_in(e, lang)), "LOCATION:" + _ics_text(e["place"]), "DESCRIPTION:" + _ics_text(f"{e['org_name']}\n{link}"),
            "URL:" + link, *(["STATUS:CANCELLED"] if e["status"] == "cancelled" else []), "END:VEVENT"]


def _calendar(lines: list[str], *head: str) -> str:
    return "\r\n".join(_fold(x) for x in ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//KBTU App//EN", "METHOD:PUBLISH", *head, *lines, "END:VCALENDAR"]) + "\r\n"


def event_ics(con, eid: int, link: str) -> str:
    e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published'", eid)
    if not e or not e["starts_at"]:
        raise ApiError("not_found")
    return _calendar(_vevent(e, link))


def cal_token(con, v: Viewer) -> str:
    """My calendar feed's secret: made once and kept, so a subscribed calendar stays subscribed."""
    need_student(v)
    t = one(con, "SELECT cal_token FROM users WHERE id = ?", v.id)[0]
    if not t:
        t = secrets.token_urlsafe(18)
        con.execute("UPDATE users SET cal_token = ? WHERE id = ?", (t, v.id))
    return t


def reset_cal_token(con, v: Viewer) -> None:
    """A leaked feed address told where I'd be: the old one stops at once, the next tap on Calendar makes a new one."""
    need_student(v)
    con.execute("UPDATE users SET cal_token = NULL WHERE id = ?", (v.id,))


def cal_feed(con, token: str, link) -> str:
    """Everything I go to, from a month ago on: the phone's calendar refreshes it on its own (hourly asked), so a new
    registration shows up and a cancelled one goes; a cancelled event stays, struck through."""
    u = one(con, "SELECT u.id, u.lang FROM users u JOIN students s ON s.user_id = u.id WHERE u.cal_token = ?", token) if token else None
    if not u:
        raise ApiError("not_found")
    evs = rows(con, """SELECT e.*, o.name AS org_name FROM registrations r JOIN events e ON e.id = r.event_id JOIN orgs o ON o.id = e.org_id
        WHERE r.user_id = ? AND r.status IN ('going', 'hold') AND e.status IN ('published', 'cancelled') AND e.hidden_at IS NULL
        AND COALESCE(e.ends_at, e.starts_at + ?) > ? ORDER BY e.starts_at LIMIT 300""", u["id"], NO_END, core.now() - 30 * 86400)
    return _calendar([x for e in evs for x in _vevent(e, link(e["id"]), u["lang"])], "X-WR-CALNAME:KBTU App", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H")


# ---------------------------------------------------------------- events

def _visible(con, v: Viewer, e: sqlite3.Row, roles: dict[int, str] | None = None, hidden: set[int] | None = None) -> bool:
    """Drafts and hidden events only for the organizing team (and the admin); team-only events for members. `roles`
    (_roles()) and `hidden` (_hidden_orgs()): read once when checking a list."""
    if (e["org_id"] in hidden) if hidden is not None else one(con, "SELECT 1 FROM orgs WHERE id = ? AND status = 'hidden'", e["org_id"]):
        return False  # a club the admin hid: its events are gone for everyone
    roles = _roles(con, v) if roles is None else roles
    team = at_least(roles.get(e["org_id"]), "member")
    if e["status"] == "draft" or e["hidden_at"]:
        return team or v.role == "admin"
    if e["visibility"] == "members":
        return team
    if e["visibility"] == "leaders":
        return team or at_least(max(roles.values(), key=RANK.__getitem__, default=None), e["leaders_from"] or "president")
    return True


def _hidden_orgs(con) -> set[int]:
    return {r[0] for r in rows(con, "SELECT id FROM orgs WHERE status = 'hidden'")}


def sweep_holds(con) -> None:
    """Expired holds give their seats back, and the waitlist moves (a worker does this too)."""
    expired = rows(con, "SELECT DISTINCT event_id FROM registrations WHERE status = 'hold' AND hold_until < ?", core.now())
    if not expired:
        return
    with tx(con):
        con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'hold_expired', updated_at = ? WHERE status = 'hold' AND hold_until < ?", (core.now(), core.now()))
        for r in expired:
            promote(con, one(con, "SELECT * FROM events WHERE id = ?", r[0]))


def events(con, v: Viewer, frm: int | None = None, to: int | None = None, org: int | None = None) -> list[dict]:
    sweep_holds(con)
    hide_first = v.student and one(con, "SELECT hide_first_year FROM users WHERE id = ?", v.id)[0]
    sql = "SELECT * FROM events WHERE status != 'draft' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) > ?"
    args: list = [NO_END, core.now()]
    if org is not None:
        sql += " AND org_id = ?"; args.append(org)
    if frm is not None:
        sql += " AND starts_at >= ?"; args.append(frm)
    if to is not None:
        sql += " AND starts_at < ?"; args.append(to)
    if hide_first:
        sql += " AND first_year = 0"
    roles, hidden = _roles(con, v), _hidden_orgs(con)
    return cards(con, v, [e for e in rows(con, sql + " ORDER BY starts_at", *args) if _visible(con, v, e, roles, hidden)])


def past_events(con, v: Viewer) -> list[dict]:
    found = rows(con, """SELECT * FROM events WHERE status = 'published' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) <= ?
        ORDER BY starts_at DESC LIMIT 50""", NO_END, core.now())
    roles, hidden = _roles(con, v), _hidden_orgs(con)
    return cards(con, v, [e for e in found if _visible(con, v, e, roles, hidden)])


def _event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or not _visible(con, v, e):
        raise ApiError("not_found")
    return e


def event(con, v: Viewer, eid: int) -> dict:
    sweep_holds(con)
    return full(con, v, _event(con, v, eid))


def _ticket_code(con) -> str:
    """6 characters to read out and type at the door, no 0/O or 1/I/L (12 were too long, his QR
    didn't scan). ~30 bits is enough: only a club's door staff can check a code, and the scanner shows the
    holder's face. The QR holds 'KBTU' + this, 10 characters: the smallest QR there is (§4.4)."""
    while True:
        c = "".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(6))
        if not one(con, "SELECT 1 FROM registrations WHERE ticket_code = ?", c):
            return c


def notify(con, uid: int, kind: str, ref: str, payload: str = "{}", after: int | None = None) -> None:
    """Queue a bot message (§7). (user, kind, ref) is unique, so a repeat is a no-op."""
    con.execute("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, ?, ?, ?, ?)",
                (uid, kind, ref, payload, after or core.now()))


def add_seats(con, v: Viewer, eid: int, n: object) -> dict:
    """"+N seats" (§4.2), the club's Head+: the waitlist moves into them at once, in order."""
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
    """Free seats go to the waitlist in order: going, or a 30-min hold for paid events (§4.2); a 1st-year student
    takes one of a paid event's free seats while any are left (§4.3)."""
    while e["seats"] is None or taken(con, e["id"]) < e["seats"]:
        nxt = one(con, "SELECT * FROM registrations WHERE event_id = ? AND status = 'waitlist' ORDER BY waitlisted_at, id LIMIT 1", e["id"])
        if not nxt:
            return
        pay = bool(e["price"]) and not _free_seat(con, e, nxt["user_id"])
        if pay:
            con.execute("UPDATE registrations SET status = 'hold', hold_until = ?, waitlisted_at = NULL, updated_at = ? WHERE id = ?", (core.now() + HOLD, core.now(), nxt["id"]))
        else:
            con.execute("UPDATE registrations SET status = 'going', free = ?, waitlisted_at = NULL, updated_at = ? WHERE id = ?",
                        (int(bool(e["price"])), core.now(), nxt["id"]))
            _remind(con, nxt["user_id"], e)
        notify(con, nxt["user_id"], "seat_hold" if pay else "seat_free", f"event:{e['id']}")  # a hold: pay within 30 min


ANSWER_MAX = 200  # one answer to an event's question at sign-up


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


def register(con, v: Viewer, eid: int, ref: object = None, phone: object = None, answers: object = None) -> dict:
    """phone: typed in the sign-up when the event asks for it and none is kept yet; it's kept (Settings shows it, PLAN 71).
    ref: the badge code of the club member whose link they came by ("My link", ev_<id>_<code>): the member gets the
    credit, the organizers see it in "Who brought"."""
    need_student(v)
    sweep_holds(con)
    with tx(con):  # count and insert under one write lock: the last seat goes to one person
        e = _event(con, v, eid)
        if e["status"] == "draft":
            raise ApiError("not_found")
        if e["status"] == "cancelled" or e["starts_at"] <= core.now():
            raise ApiError("closed")
        if e["reg_until"] and e["reg_until"] <= core.now():
            raise ApiError("closed", "deadline")
        if e["external_url"] or e["guest_host"]:  # signed up for elsewhere
            raise ApiError("bad_input")
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if r and r["status"] in ("going", "hold", "waitlist"):
            return card(con, v, e)
        if e["needs_phone"] and phone is not None:
            if not (phone := kz_phone(phone)):
                raise ApiError("bad_input", "phone")
            con.execute("UPDATE students SET phone = ? WHERE user_id = ?", (phone, v.id))
        elif e["needs_phone"] and not one(con, "SELECT phone FROM students WHERE user_id = ?", v.id)[0]:
            raise ApiError("bad_input", "phone")  # the app asks for it and sends it with the same tap
        given = _answers(e, answers)  # the app asks the event's questions first and sends them with the same tap
        is_full = e["seats"] is not None and taken(con, eid) >= e["seats"]
        free = not is_full and _free_seat(con, e, v.id)
        status = "waitlist" if is_full else "hold" if e["price"] and not free else "going"
        hold = core.now() + HOLD if status == "hold" else None
        wait = core.now() if status == "waitlist" else None
        if r:
            con.execute("""UPDATE registrations SET status = ?, cancel_reason = NULL, hold_until = ?, waitlisted_at = ?, free = ?, note = NULL, answers = ?, updated_at = ?
                WHERE id = ?""", (status, hold, wait, int(free), given, core.now(), r["id"]))
        else:
            # someone already in keeps whoever was first (this branch is new rows only); never myself
            by = one(con, "SELECT m.user_id FROM users u JOIN org_members m ON m.user_id = u.id AND m.org_id = ? WHERE u.link_code = ? AND u.id != ?",
                     e["org_id"], ref, v.id) if isinstance(ref, str) else None
            inviter = by["user_id"] if by else None
            if inviter is None:  # "Bring a friend": the first friend who asked gets the credit ("Life of the party", §4.7)
                first = one(con, "SELECT from_id FROM friend_invites WHERE event_id = ? AND to_id = ? ORDER BY created_at LIMIT 1", eid, v.id)
                inviter = first["from_id"] if first else None
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, waitlisted_at, invited_by, free, answers, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (eid, v.id, status, _ticket_code(con), hold, wait, inviter, int(free), given, core.now(), core.now()))
        if status == "going":
            _remind(con, v.id, e)
    return card(con, v, e)


def receipt_open(con, v: Viewer, eid: int) -> None:
    """Checked before a receipt's image is processed: the person holds a seat on this event, or has a receipt on it
    nobody looked at yet (§4.3)."""
    need_student(v)
    sweep_holds(con)
    _receipt_slot(con, v, eid)


def _receipt_slot(con, v: Viewer, eid: int) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row | None]:
    """Where a receipt goes: (registration, event, the receipt it replaces). A seat on hold takes one; a ticket takes
    another file in place of its receipt while the organizer hasn't looked at it and the event isn't over (the app
    says when a receipt looks wrong, "upload another?")."""
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('hold', 'going')", eid, v.id)
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    old = None
    if r and r["status"] == "going":
        old = one(con, "SELECT * FROM receipts WHERE registration_id = ? AND status = 'accepted' AND reviewed_at IS NULL ORDER BY id DESC", r["id"])
        if not old or (e["ends_at"] or e["starts_at"] + 3 * 3600) < core.now():
            r = None
    if not r:
        raise ApiError("closed")
    return r, e, old


def add_receipt(con, v: Viewer, eid: int, saved: dict, read: dict | None = None, via: str = "app") -> dict:
    """The receipt is in (§4.3), from the app or the bot: the seat becomes a ticket at once. What OCR read off it
    (receipt.py; None = OCR didn't run) only raises flags (what isn't a receipt at all never gets here) the organizer sees first, and the
    student too (my.receiptFlags), who may then send another file in its place (_receipt_slot)."""
    with tx(con):
        r, e, old = _receipt_slot(con, v, eid)
        if old:  # ponytail: the replaced picture stays on disk, unreachable (no row points at it); sweep if it ever matters
            con.execute("DELETE FROM receipts WHERE id = ?", (old["id"],))
            con.execute("DELETE FROM files WHERE id = ? AND NOT EXISTS (SELECT 1 FROM receipts WHERE file_id = ?)", (old["file_id"], old["file_id"]))
        got = read or {}
        flags = _receipt_flags(con, e, saved["sha256"], read)
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at)
            VALUES (?, 'receipt', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"], saved["path"], v.id, core.now())).lastrowid
        con.execute("""INSERT INTO receipts (registration_id, file_id, via, amount, receipt_no, sender_name, recipient_name, paid_at, flags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (r["id"], fid, via, got.get("amount"), got.get("no"), got.get("sender"), got.get("recipient"),
                                                      got.get("paid_at"), flags, core.now()))
        if not old:
            con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE id = ?", (core.now(), r["id"]))
            _remind(con, v.id, e)
    return card(con, v, e)


def _receipt_flags(con, e: sqlite3.Row, sha: str, read: dict | None) -> str:
    """The checks (§4.3), the owner's list after the Oct 11 review: the same file or receipt number came before, a
    smaller sum or a bigger one that isn't a whole number of tickets (his test: a 1 090 receipt for 164 passed), another recipient, a receipt older than the event itself (an old one reused), (nothing readable,
    not a Kaspi receipt, is refused before: receipt.NotReceipt). No sender check: parents and friends pay, the organizer just sees the name."""
    got = read or {}
    out = []
    if one(con, "SELECT 1 FROM files WHERE sha256 = ? AND kind = 'receipt'", sha) or \
            got.get("no") and one(con, "SELECT 1 FROM receipts WHERE receipt_no = ?", got["no"]):
        out.append("duplicate")
    if got.get("amount") and e["price"] and got["amount"] < e["price"]:
        out.append("amount_short")
    elif got.get("amount") and e["price"] and got["amount"] % e["price"]:
        out.append("amount_over")
    if got.get("recipient") and e["pay_to_name"] and not receipt.same_person(got["recipient"], e["pay_to_name"]):
        out.append("recipient_mismatch")
    if got.get("paid_at") and got["paid_at"] < e["created_at"]:
        out.append("too_early")
    return ",".join(out)


def receipt_path(con, v: Viewer, rid: int) -> str:
    """A receipt's image is private (§4.3): its sender, the event's Head+ and the admin see it."""
    c = one(con, """SELECT f.path, r.user_id, e.org_id FROM receipts c JOIN files f ON f.id = c.file_id
        JOIN registrations r ON r.id = c.registration_id JOIN events e ON e.id = r.event_id WHERE c.id = ?""", rid)
    if not c or not (c["user_id"] == v.id or v.role == "admin" or can(con, v, c["org_id"], "events")):
        raise ApiError("not_found")
    return c["path"]


def review_receipt(con, v: Viewer, rid: int, reject: object) -> None:
    """The organizer checked a receipt against their Kaspi history (§4.3): fine, or rejected — then the ticket stops
    working, the seat goes to the waitlist and the bot tells the student to talk to the club. Refunds happen outside."""
    if not isinstance(reject, bool):
        raise ApiError("bad_input")
    with tx(con):
        c = one(con, "SELECT c.*, r.event_id, r.user_id, r.status AS reg FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE c.id = ?", rid)
        if not c:
            raise ApiError("not_found")
        e = _staff_event(con, v, c["event_id"], "events")
        if c["status"] == "rejected":
            return
        con.execute("UPDATE receipts SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?", ("rejected" if reject else "accepted", v.id, core.now(), rid))
        if reject:
            log_action(con, v.id, "receipt_reject", f"receipt:{rid}")
            if c["reg"] == "going":
                con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'receipt_rejected', updated_at = ? WHERE id = ?", (core.now(), c["registration_id"]))
                con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (c["user_id"], f"event:{e['id']}:%"))
                notify(con, c["user_id"], "receipt_rejected", f"event:{e['id']}:{rid}")
                promote(con, e)


def _remind(con, uid: int, e: sqlite3.Row) -> None:
    """The 2-hour reminder (§7), unless the person turned it off; ref carries the start, so a moved event re-arms it."""
    if one(con, "SELECT n_remind FROM users WHERE id = ?", uid)[0] and e["starts_at"] - 7200 > core.now():
        notify(con, uid, "remind_2h", f"event:{e['id']}:{e['starts_at']}", after=e["starts_at"] - 7200)


def unregister(con, v: Viewer, eid: int) -> dict:
    need_student(v)
    with tx(con):
        e = _event(con, v, eid)
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if not r:
            raise ApiError("not_found")
        if e["starts_at"] <= core.now():
            raise ApiError("closed")
        freed = r["status"] in ("going", "hold")
        con.execute("""UPDATE registrations SET status = 'cancelled', cancel_reason = 'self', hold_until = NULL, waitlisted_at = NULL, updated_at = ?
            WHERE id = ?""", (core.now(), r["id"]))
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (v.id, f"event:{eid}:%"))
        if freed:
            promote(con, e)
    return card(con, v, e)


def set_saved(con, v: Viewer, eid: int, on: bool) -> None:
    need_student(v)
    _event(con, v, eid)
    if on:
        con.execute("INSERT OR IGNORE INTO saved_events (user_id, event_id, created_at) VALUES (?, ?, ?)", (v.id, eid, core.now()))
    else:
        con.execute("DELETE FROM saved_events WHERE user_id = ? AND event_id = ?", (v.id, eid))


def tickets(con, v: Viewer) -> list[dict]:
    if not v.student:
        return []
    found = rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status IN ('going','hold','waitlist') AND COALESCE(e.ends_at, e.starts_at + ?) > ?
        ORDER BY e.starts_at""", v.id, NO_END, core.now())
    return cards(con, v, found)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .clubs import org  # noqa: E402
from .organizing import _staff_event, kz_phone  # noqa: E402
from .teams import team  # noqa: E402
