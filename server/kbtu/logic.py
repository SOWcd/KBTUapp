"""The rules of SPEC §2–§4 over SQLite, answering in the shapes of web/src/lib/api/types.ts (camelCase).

The only copy of the rules (the in-browser mock that repeated them went on Oct 11). Every function takes the connection and the caller (`Viewer`) and either returns
JSON-ready data or raises ApiError. Writes that check and then change (seats, check-in) run in db.tx."""
from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import media, receipt, texts, video
from .db import tx

HOLD = 30 * 60          # an unpaid seat waits 30 min for the receipt (§4.3)
NO_END = 3 * 3600       # an event without an end counts as 3 h long
DOOR_EARLY = 3 * 3600   # check-in opens 3 h before the start (§4.4) …
DOOR_LATE = 6 * 3600    # … and, without an end, closes 6 h after the start
RANK = {"member": 1, "head": 2, "vice": 3, "president": 4}
# A club role's rights (SPEC §2): the toggles of its editor (owner, Oct 7: "as in Telegram"). Each needs a level; the
# highest one a role has is its level, which ranks it for the rank rule (whom it acts on). A level without a club role,
# and a role made before the toggles, has its level's rights; the President has them all.
RIGHTS = {"door": "member", "events": "head", "posts": "head", "people": "head", "casting": "head", "team": "vice", "money": "vice", "memo": "vice", "profile": "vice"}
LEVEL_RIGHTS = {lv: frozenset(r for r, need in RIGHTS.items() if RANK[need] <= RANK[lv]) for lv in RANK}
PROFILE_QR = re.compile(r"\bu_(\d+)_([A-Z2-7]{10})\b")  # a badge QR: …?startapp=u_<id>_<code> (§4.4)
TWO_GIS = re.compile(r"^https://(?:[a-z]+\.)?2gis\.(?:kz|ru|com)/", re.I)
SEASON_MONTHS = (2, 8)  # a season starts in February and in August (§4.11)


class ApiError(Exception):
    STATUS = {"need_student": 401, "forbidden": 403, "not_found": 404, "full": 409, "closed": 409,
              "conflict": 409, "rate_limited": 429, "bad_input": 400, "unavailable": 503}

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code, self.message = code, message

    @property
    def status(self) -> int:
        return self.STATUS[self.code]


@dataclass(frozen=True)
class Viewer:
    id: int
    role: str                   # platform role: user / moderator / admin
    student: bool               # signed in with KBTU (only students act, §2)


def now() -> int:
    return int(time.time())


def one(con: sqlite3.Connection, sql: str, *args) -> sqlite3.Row | None:
    return con.execute(sql, args).fetchone()


def rows(con: sqlite3.Connection, sql: str, *args) -> list[sqlite3.Row]:
    return con.execute(sql, args).fetchall()


def need_student(v: Viewer) -> None:
    if not v.student:
        raise ApiError("need_student")


def role_in(con, v: Viewer, org: int) -> str | None:
    """My role in an org. Only students can be members (a guest's old rows don't count)."""
    if not v.student:
        return None
    r = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", org, v.id)
    return r["role"] if r else None


def at_least(role: str | None, least: str) -> bool:
    return role is not None and RANK[role] >= RANK[least]


def overseer(con, v: Viewer) -> bool:
    """DMP Head+ (an org with can_oversee) or the admin."""
    return v.role == "admin" or (v.student and one(con, """SELECT 1 FROM org_members m JOIN orgs o ON o.id = m.org_id
        WHERE m.user_id = ? AND o.can_oversee = 1 AND m.role != 'member'""", v.id) is not None)


# ---------------------------------------------------------------- shapes

def org_ref(con, o: sqlite3.Row, files: dict | None = None) -> dict:
    """A club wherever it shows: its mark is its uploaded logo, or else its emoji on its cover. `files`: the logos
    already read (_by_id), when building a list."""
    logo = media_shape(files[o["logo_file_id"]]) if files and o["logo_file_id"] in files else photo(con, o["logo_file_id"])
    return {"id": o["id"], "slug": o["slug"], "name": o["name"], "short": o["short"], "emoji": o["emoji"],
            "cover": o["cover"], "kind": o["kind"], "official": bool(o["official"]), "logo": logo["thumb"] if logo else None,
            # the app shows the viewer's language (api/client.ts); a club's description only where it shows (org_shape)
            **({"i18n": {k: {a: b for a, b in x.items() if a != "description"} for k, x in json.loads(o["i18n"]).items()}} if o["i18n"] else {})}


def _org(con, oid: int) -> sqlite3.Row:
    return one(con, "SELECT * FROM orgs WHERE id = ?", oid)


def _qs(ids) -> str:
    return ",".join("?" * len(ids))


def _by_id(con, table: str, ids) -> dict[int, sqlite3.Row]:
    """Rows of `table` by id, in one query: a list of cards reads its clubs and files this way, not one by one."""
    ids = list({i for i in ids if i is not None})
    return {r["id"]: r for r in rows(con, f"SELECT * FROM {table} WHERE id IN ({_qs(ids)})", *ids)} if ids else {}


def _rights_from(role: str, rights: str | None) -> frozenset[str]:
    """A club role's toggles, else its level's; the door is every member's, not a toggle (owner, Oct 15: "scanning
    tickets at the entrance is for absolutely everyone")."""
    return LEVEL_RIGHTS[role] if role == "president" or rights is None else frozenset(filter(None, rights.split(","))) | {"door"}


def rights_of(con, uid: int, oid: int) -> frozenset[str]:
    """What someone may do in a club: their club role's toggles, else their level's (SPEC §2)."""
    m = one(con, "SELECT m.role, t.rights FROM org_members m LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ? AND m.user_id = ?", oid, uid)
    return _rights_from(m["role"], m["rights"]) if m else frozenset()


def can(con, v: Viewer, oid: int | None, right: str) -> bool:
    """I may do this in this club (students only act, §2)."""
    return bool(v.student and oid and right in rights_of(con, v.id, oid))


def _may(con, v: Viewer, oid: int, right: str) -> None:
    if not can(con, v, oid, right):
        raise ApiError("forbidden")


def _rights(con, v: Viewer) -> dict[int, frozenset[str]]:
    """My rights in each club I'm in, read once for a list."""
    return {r["org_id"]: _rights_from(r["role"], r["rights"]) for r in rows(con, """SELECT m.org_id, m.role, t.rights FROM org_members m
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ?""", v.id)} if v.student else {}


def organizes(con, v: Viewer) -> bool:
    """Runs events in some club: may upload covers and photos."""
    return any("events" in r for r in _rights(con, v).values())


def _roles(con, v: Viewer) -> dict[int, str]:
    """My role in each org I'm in (students only: a guest's old rows don't count)."""
    return {r[0]: r[1] for r in rows(con, "SELECT org_id, role FROM org_members WHERE user_id = ?", v.id)} if v.student else {}


PERSON_COLS = ("u.id, u.tg_first_name, u.tg_last_name, u.tg_photo_url, u.is_founder, u.mark, u.show_going, s.first_name, s.last_name, u.nick,"
               " CASE WHEN u.avatar_tg = 0 THEN (SELECT path FROM files WHERE id = u.avatar_file_id) END AS own_photo")
PERSON = f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id"


def short_name(p: sqlite3.Row) -> str:
    """"Alikhan S." for students (§3), the Telegram first name otherwise."""
    if p["first_name"]:
        return f"{p['first_name']} {p['last_name'][:1] + '.' if p['last_name'] else ''}".strip()
    return p["tg_first_name"] or "?"


def shown_name(p: sqlite3.Row) -> str:
    """The name everyone sees: the nickname when there is one (owner, Oct 5). Organizers get the real one too: the
    `fullName` of their lists, the door's `realName`."""
    return p["nick"] or short_name(p)


def avatar_of(p: sqlite3.Row) -> str | None:
    """My own photo while the "Photo from Telegram" switch is off, else Telegram's (refreshed on every open)."""
    return f"media/{p['own_photo']}.t.webp" if p["own_photo"] else p["tg_photo_url"]


def person_ref(p: sqlite3.Row) -> dict:
    return {"id": p["id"], "name": shown_name(p), "nick": p["nick"], "avatar": avatar_of(p), "founder": bool(p["is_founder"]), "mark": p["mark"]}


def _door_ref(p: sqlite3.Row) -> dict:
    """The door checks the real name beside a nick (owner, Oct 5), the short one a Member may see (§3)."""
    return {**person_ref(p), "realName": short_name(p)}


def clean_nick(val: object) -> str | None:
    """2-24 characters, spaces squeezed, nothing invisible; no @handles or links (a nick is a name, not an ad). Empty
    clears it."""
    s = " ".join("".join(ch for ch in str(val or "") if unicodedata.category(ch)[0] != "C").split())
    if not s:
        return None
    if not 2 <= len(s) <= 24 or re.search(r"@|https?:|t\.me/|www\.", s, re.I):
        raise ApiError("bad_input", "nick")
    return s


def taken(con, eid: int) -> int:
    return one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status IN ('hold','going')", eid)[0]


def free_taken(con, eid: int) -> int:
    """A paid event's free seats for 1st-year students already given (§4.3)."""
    return one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = 'going' AND free = 1", eid)[0]


def _free_seat(con, e: sqlite3.Row, uid: int) -> bool:
    """Whether this person gets one of the event's free seats: a 1st-year student while some are left."""
    return bool(e["price"] and e["free_first"] and free_taken(con, e["id"]) < e["free_first"]
                and (one(con, "SELECT course FROM students WHERE user_id = ?", uid) or {"course": None})["course"] == 1)


def friend_ids(con, uid: int) -> list[int]:
    return [r[0] for r in rows(con, "SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?", uid, uid)]


def media_shape(f: sqlite3.Row) -> dict:
    """types.ts Media. Relative URLs: the app resolves them against its own address (app.py serves /media/)."""
    return {"id": f["id"], "url": f"media/{f['path']}.webp", "thumb": f"media/{f['path']}.t.webp", "w": f["width"], "h": f["height"], "blur": "", "color": f["color"]}


def photo(con, file_id: int | None) -> dict | None:
    f = one(con, "SELECT * FROM files WHERE id = ?", file_id) if file_id else None
    return media_shape(f) if f else None


def _event_cover(con, e: sqlite3.Row, files: dict | None = None) -> dict | None:
    cover = media_shape(files[e["cover_file_id"]]) if files and e["cover_file_id"] in files else photo(con, e["cover_file_id"])
    if cover:
        cover["focus"] = [float(c) for c in e["cover_focus"].split(",")] if e["cover_focus"] else None
    return cover


def add_photo(con, v: Viewer, saved: dict) -> dict:
    """A processed upload (media.save) becomes a file the uploader can put on an event. Organizers only (Head+)."""
    if not organizes(con, v):
        raise ApiError("forbidden")
    f = one(con, "SELECT * FROM files WHERE sha256 = ? AND kind = 'event_cover' AND owner_id = ?", saved["sha256"], v.id)
    if not f:
        cur = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_cover', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                        saved["path"], v.id, now(), saved["color"]))
        f = one(con, "SELECT * FROM files WHERE id = ?", cur.lastrowid)
    return media_shape(f)


def card(con, v: Viewer, e: sqlite3.Row) -> dict:
    return cards(con, v, [e])[0]


def cards(con, v: Viewer, evs: list[sqlite3.Row]) -> list[dict]:
    """Event cards (types.ts EventCard). A list asks each thing once for all its events: card by card, the Afisha of a
    few hundred events was 1200 queries and the slowest call of the app's start (load test, Oct 7)."""
    if not evs:
        return []
    ids = [e["id"] for e in evs]
    q = _qs(ids)
    taken = dict(rows(con, f"SELECT event_id, COUNT(*) FROM registrations WHERE event_id IN ({q}) AND status IN ('hold','going') GROUP BY event_id", *ids))
    paid = [e["id"] for e in evs if e["price"] and e["free_first"]]  # free seats for 1st-years are counted only where there are some
    free = dict(rows(con, f"SELECT event_id, COUNT(*) FROM registrations WHERE event_id IN ({_qs(paid)}) AND status = 'going' AND free = 1 GROUP BY event_id",
                     *paid)) if paid else {}
    mine = {r["event_id"]: r for r in rows(con, f"SELECT * FROM registrations WHERE user_id = ? AND event_id IN ({q})", v.id, *ids)}
    regs = [r["id"] for r in mine.values()]
    receipts = {c["registration_id"]: c for c in rows(con, f"SELECT registration_id, status, flags, reviewed_at FROM receipts WHERE registration_id IN ({_qs(regs)}) ORDER BY id", *regs)}  # the last one wins
    rated = dict(rows(con, f"SELECT event_id, score FROM event_ratings WHERE user_id = ? AND event_id IN ({q})", v.id, *ids))
    saved = {r[0] for r in rows(con, f"SELECT event_id FROM saved_events WHERE user_id = ? AND event_id IN ({q})", v.id, *ids)}
    friends: dict[int, list] = {}
    if v.student:  # §3: friends see where you go only if you allow it; guests see nobody
        for p in rows(con, f"""SELECT {PERSON_COLS}, r.event_id AS ev FROM registrations r JOIN users u ON u.id = r.user_id
                LEFT JOIN students s ON s.user_id = u.id WHERE r.event_id IN ({q}) AND r.status = 'going' AND u.show_going = 1
                AND r.user_id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?) ORDER BY r.id""", *ids, v.id, v.id):
            friends.setdefault(p["ev"], []).append(person_ref(p))
    orgs = _by_id(con, "orgs", (e["org_id"] for e in evs))
    slides: dict[int, list] = {}
    for r in rows(con, f"SELECT event_id, file_id FROM event_slides WHERE event_id IN ({q}) ORDER BY pos", *ids):
        slides.setdefault(r["event_id"], []).append(r["file_id"])
    files = _by_id(con, "files", [*(e["cover_file_id"] for e in evs), *(o["logo_file_id"] for o in orgs.values()),
                                  *(i for s in slides.values() for i in s)])
    videos = _by_id(con, "videos", (e["video_id"] for e in evs))
    out = []
    for e in evs:
        reg, my = mine.get(e["id"]), None
        if reg:
            my = {"status": reg["status"], "cancelReason": reg["cancel_reason"], "ticketCode": reg["ticket_code"] if reg["status"] == "going" else None,
                  "holdUntil": reg["hold_until"], "checkedInAt": reg["checked_in_at"], "receipt": c["status"] if (c := receipts.get(reg["id"])) else "none",
                  "receiptFlags": [x for x in c["flags"].split(",") if x] if c and c["status"] == "accepted" and c["reviewed_at"] is None else [],
                  "free": bool(reg["free"]),
                  "ics": f"/api/events/{e['id']}/ics?k={ics_sig(e['id'])}" if reg["status"] == "going" else None,
                  "rating": rated.get(e["id"]) if reg["checked_in_at"] else None, "note": reg["note"]}
        out.append({
            "id": e["id"], "org": org_ref(con, orgs[e["org_id"]], files), "status": e["status"], "title": e["title"],
            "startsAt": e["starts_at"], "endsAt": e["ends_at"], "publishedAt": e["published_at"], "place": e["place"], "placeUrl": e["place_url"],
            "cover": _event_cover(con, e, files),
            "slides": [media_shape(files[i]) for i in slides.get(e["id"], []) if i in files],
            "emoji": e["emoji"], "color": e["color"], "tint": e["tint"] or "#3B6BFF", "seats": e["seats"], "taken": taken.get(e["id"], 0),
            "firstYear": bool(e["first_year"]), "needsVolunteers": e["volunteers"], "externalUrl": e["external_url"], "price": e["price"], "my": my, "visibility": e["visibility"],
            "regUntil": e["reg_until"], "freeFirst": e["free_first"] if e["price"] else None,
            "freeLeft": max(0, e["free_first"] - free.get(e["id"], 0)) if e["price"] and e["free_first"] else None,
            "leadersFrom": e["leaders_from"], "meeting": bool(e["meeting"]),
            "saved": e["id"] in saved,
            "friends": friends.get(e["id"], []),
            "video": video_shape(x) if (x := videos.get(e["video_id"])) and x["status"] == "ready" else None,
            **({"i18n": {k: {"title": x["title"]} for k, x in json.loads(e["i18n"]).items()}} if e["i18n"] else {}),
        })
    return out


def full(con, v: Viewer, e: sqlite3.Row) -> dict:
    head = v.role == "admin" or can(con, v, e["org_id"], "events")
    return {**card(con, v, e), **({"i18n": json.loads(e["i18n"])} if e["i18n"] else {}), "description": e["description"], "payToName": e["pay_to_name"], "payPhone": e["pay_phone"], "meetingTag": e["meeting_tag"],
            "memo": json.loads(e["memo"]) if head and e["memo"] else None,
            "badgeName": e["badge_name"], **_album_view(con, v, e), "commentsOn": bool(e["comments_on"]),
            "discuss": e["channel_link"] if e["comments_on"] else None,  # its post's comments in Telegram (owner, Oct 17: the talk is there)
            "comments": one(con, "SELECT COUNT(*) FROM comments WHERE event_id = ? AND deleted_at IS NULL", e["id"])[0],
            "updates": [{"id": u["id"], "body": u["body"], "at": u["created_at"], "canDelete": head}
                        for u in rows(con, "SELECT * FROM event_updates WHERE event_id = ? ORDER BY created_at DESC, id DESC LIMIT 10", e["id"])],
            **_rating_view(con, v, e, head), "volunteers": _volunteers_view(con, v, e, head),
            "chat": e["chat_link"] if e["chat_link"] and _chat_ok(con, e, v.id) else None, "chatLinked": bool(e["chat_id"]) if head else None,
            "wideVideo": video_shape(x) if (x := one(con, "SELECT * FROM videos WHERE id = ?", e["wide_video_id"])) and (head or x["status"] == "ready") else None,
            # the editor sees its video while it is still being compressed (or why it failed)
            **({"video": video_shape(x)} if head and (x := one(con, "SELECT * FROM videos WHERE id = ?", e["video_id"])) else {})}


# ------------------------------------------------------------ volunteers (owner, Oct 15)
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
        if e["status"] != "published" or not e["volunteers"] or e["starts_at"] <= now():
            raise ApiError("closed")
        if e["volunteers_senior"] and (one(con, "SELECT course FROM students WHERE user_id = ?", v.id) or {"course": None})["course"] == 1:
            raise ApiError("forbidden", "first_year")
        if one(con, "SELECT COUNT(*) FROM volunteers WHERE event_id = ? AND status = 'yes'", eid)[0] >= e["volunteers"]:
            raise ApiError("closed", "full")
        if con.execute("INSERT OR IGNORE INTO volunteers (event_id, user_id, status, note, created_at) VALUES (?, ?, 'asked', ?, ?)",
                       (eid, v.id, text, now())).rowcount == 0:
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
                           ("yes" if yes else "no", now(), eid, uid)).rowcount:
            raise ApiError("not_found")
        notify(con, uid, "volunteer_yes" if yes else "volunteer_no", f"vo:{eid}:{now()}")
    return volunteers_list(con, v, eid)


# ------------------------------------------------------------ event chats (owner, Oct 15: no userbot)
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


# ------------------------------------------------------------ the events channel (owner, Oct 15: @KBTUevents)
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
              AND (e.status = 'published' OR e.status = 'cancelled' AND e.channel_msg IS NOT NULL) ORDER BY e.published_at""", now()):
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


# ------------------------------------------------------------ translations (ai.py, PLAN 9)
# The postman's translator takes one text at a time: an upcoming public event (never drafts, team-only ones or
# meetings: only what anyone may read goes to Cloudflare, as the privacy policy says), else an active club's
# description. An edit clears lang (update_event, update_org), so the row comes back; 3 failed calls leave it as typed.

AI_TRIES = 3
AI_LIMITS = {"title": 80, "description": 2000}
AI_ORG_LIMITS = {"description": 600}


def ai_next(con) -> tuple[str, int, dict[str, str]] | None:
    """("event" | "org", id, its texts as they are now), or None."""
    e = one(con, """SELECT e.id, e.title, e.description FROM events e JOIN orgs o ON o.id = e.org_id
        WHERE e.lang IS NULL AND e.ai_tries < ? AND e.status = 'published' AND e.visibility = 'public' AND e.meeting = 0
          AND e.hidden_at IS NULL AND o.status = 'active' AND COALESCE(e.ends_at, e.starts_at) > ? ORDER BY e.updated_at DESC LIMIT 1""", AI_TRIES, now())
    if e:
        return "event", e["id"], {"title": e["title"], "description": e["description"]}
    o = one(con, "SELECT id, description FROM orgs WHERE lang IS NULL AND ai_tries < ? AND status = 'active' AND trim(description) != '' ORDER BY id DESC LIMIT 1", AI_TRIES)
    return ("org", o["id"], {"description": o["description"]}) if o else None


def ai_save(con, kind: str, rid: int, was: dict[str, str], src: str, tr: dict[str, dict[str, str]]) -> None:
    """The translations, unless the text was edited meanwhile (then the edit's own turn comes)."""
    with tx(con):
        if kind == "event":
            n = con.execute("UPDATE events SET i18n = ?, lang = ? WHERE id = ? AND title = ? AND description = ? AND lang IS NULL",
                        (json.dumps({k: {"title": x.get("title", was["title"]), "description": x.get("description", "")} for k, x in tr.items()}, ensure_ascii=False),
                         src, rid, was["title"], was["description"])).rowcount
            if not n:
                return
        else:
            o = one(con, "SELECT i18n FROM orgs WHERE id = ? AND description = ? AND lang IS NULL", rid, was["description"])
            if not o:
                return
            have = json.loads(o["i18n"]) if o["i18n"] else {}
            have = {k: {a: b for a, b in x.items() if a != "description"} for k, x in have.items()}  # a name or a school's abbr stays
            for k, x in tr.items():
                have.setdefault(k, {})["description"] = x["description"]
            con.execute("UPDATE orgs SET i18n = ?, lang = ? WHERE id = ?", (json.dumps({k: x for k, x in have.items() if x}, ensure_ascii=False), src, rid))
        _ai_note(con, done=True)


def ai_failed(con, kind: str, rid: int, why: str) -> None:
    with tx(con):
        con.execute(f"UPDATE {'events' if kind == 'event' else 'orgs'} SET ai_tries = ai_tries + 1 WHERE id = ?", (rid,))  # the table from the two above
        _ai_note(con, error=f"{kind} {rid}: {why}"[:200])


def _ai_note(con, done: bool = False, error: str | None = None, on: bool | None = None) -> None:
    """What the admin panel shows (admin_stats): on or off, translated today (UTC, Cloudflare's day), the last error."""
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if done:
        n = one(con, "SELECT value FROM meta WHERE key = 'ai:done'")
        count = int(n[0].split()[1]) + 1 if n and n[0].startswith(day) else 1
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:done', ?)", (f"{day} {count}",))
    if error is not None:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:error', ?)", (f"{day} {error}",))
    if on is not None:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('ai:on', ?)", ("1" if on else "0",))


def ai_note(con, error: str | None = None, on: bool | None = None) -> None:
    with tx(con):
        _ai_note(con, error=error, on=on)


def ai_state(con) -> dict:
    meta = dict(rows(con, "SELECT key, value FROM meta WHERE key LIKE 'ai:%'"))
    day = time.strftime("%Y-%m-%d", time.gmtime())
    done = meta.get("ai:done", "")
    return {"on": meta.get("ai:on") == "1", "today": int(done.split()[1]) if done.startswith(day) else 0, "error": meta.get("ai:error")}


# ------------------------------------------------------------ videos (video.py)

def video_shape(x: sqlite3.Row) -> dict:
    """types.ts Video: the poster is a photo named like the video."""
    ready = x["status"] == "ready"
    return {"id": x["id"], "status": x["status"], "url": f"media/{x['path']}.mp4" if ready else None, "duration": x["duration"],
            "poster": {"url": f"media/{x['path']}.webp", "thumb": f"media/{x['path']}.t.webp", "w": x["width"], "h": x["height"],
                       "blur": "", "color": x["color"]} if ready else None, "error": x["error"]}


def new_video(con, v: Viewer, size, wide: object = False) -> dict:
    """An upload starts (Head+, as a cover): its size is said up front, the pieces follow (PUT, app.py). `wide`: for the
    sheet's background (PLAN 32), compressed for it."""
    if not organizes(con, v):
        raise ApiError("forbidden")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= video.MAX_BYTES:
        raise ApiError("bad_input", "too_big")
    vid = con.execute("INSERT INTO videos (owner_id, status, size, created_at, wide) VALUES (?, 'uploading', ?, ?, ?)", (v.id, size, now(), int(wide is True))).lastrowid
    return {"id": vid, "at": 0}


def my_video(con, v: Viewer, vid: int) -> sqlite3.Row:
    x = one(con, "SELECT * FROM videos WHERE id = ? AND owner_id = ?", vid, v.id)
    if not x:
        raise ApiError("not_found")
    return x


def video_uploaded(con, v: Viewer, vid: int, have: int) -> dict:
    """All pieces in: the postman compresses it next."""
    x = my_video(con, v, vid)
    if x["status"] != "uploading" or have != x["size"]:
        raise ApiError("conflict")
    con.execute("UPDATE videos SET status = 'queued' WHERE id = ?", (vid,))
    return video_shape(my_video(con, v, vid))


def next_video(con) -> sqlite3.Row | None:
    with tx(con):
        x = one(con, "SELECT * FROM videos WHERE status = 'queued' ORDER BY id LIMIT 1")
        if x:
            con.execute("UPDATE videos SET status = 'working' WHERE id = ?", (x["id"],))
    return x


def video_done(con, vid: int, out: dict | None, error: str | None = None) -> None:
    if out:
        con.execute("""UPDATE videos SET status = 'ready', path = ?, width = ?, height = ?, duration = ?, bytes = ?, color = ?
            WHERE id = ?""", (out["path"], out["width"], out["height"], out["duration"], out["bytes"], out["color"], vid))
    else:
        con.execute("UPDATE videos SET status = 'failed', error = ? WHERE id = ?", (error, vid))


def stale_videos(con) -> list[tuple[int, str | None]]:
    """Videos no event holds a day after their upload (replaced, taken off, the event deleted, or never saved): their
    rows go; the caller deletes the files. (id, path)."""
    with tx(con):
        old = rows(con, """SELECT id, path FROM videos WHERE created_at < ? AND status != 'working'
            AND id NOT IN (SELECT video_id FROM events WHERE video_id IS NOT NULL
                           UNION SELECT wide_video_id FROM events WHERE wide_video_id IS NOT NULL)""", now() - 86400)
        con.executemany("DELETE FROM videos WHERE id = ?", [(r["id"],) for r in old])
        # files are named by their content: the same clip kept by another row keeps its files
        return [(r["id"], None if r["path"] and one(con, "SELECT 1 FROM videos WHERE path = ?", r["path"]) else r["path"]) for r in old]


def _video(con, v: Viewer, body: dict, keep: int | None, key: str = "videoId") -> int | None:
    """The editor's videoId (wideVideoId: the sheet's background), like coverId: absent keeps, null takes it off, an id
    must be my own upload for that slot that didn't fail."""
    if key not in body:
        return keep
    if body[key] is None:
        return None
    try:
        x = one(con, "SELECT id FROM videos WHERE id = ? AND owner_id = ? AND status != 'failed' AND wide = ?",
                int(body[key]), v.id, int(key == "wideVideoId"))
    except (TypeError, ValueError):
        x = None
    if not x:
        raise ApiError("bad_input")
    return x["id"]


def end_of(e: sqlite3.Row) -> int:
    return e["ends_at"] or e["starts_at"] + NO_END


# "To calendar" on the ticket (§4.2). The phone's browser fetches the file with no session, so the link is signed;
# app.create sets the key from TOKEN_KEY, the same in every worker process (this random one is for scripts).
ICS_KEY = secrets.token_bytes(32)


def ics_sig(eid: int) -> str:
    return hmac.new(ICS_KEY, f"ics:{eid}".encode(), hashlib.sha256).hexdigest()[:32]


def _ics_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


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


def _vevent(e: sqlite3.Row, link: str) -> list[str]:
    """One event (with its org's name as org_name) as VEVENT lines; a cancelled one says so, and calendars strike it."""
    utc = lambda ts: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))  # noqa: E731
    return ["BEGIN:VEVENT", f"UID:ev{e['id']}@kbtu-app", f"DTSTAMP:{utc(now())}", f"DTSTART:{utc(e['starts_at'])}", f"DTEND:{utc(end_of(e))}",
            "SUMMARY:" + _ics_text(e["title"]), "LOCATION:" + _ics_text(e["place"]), "DESCRIPTION:" + _ics_text(f"{e['org_name']}\n{link}"),
            "URL:" + link, *(["STATUS:CANCELLED"] if e["status"] == "cancelled" else []), "END:VEVENT"]


def _calendar(lines: list[str], *head: str) -> str:
    return "\r\n".join(_fold(x) for x in ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//KBTU App//EN", "METHOD:PUBLISH", *head, *lines, "END:VCALENDAR"]) + "\r\n"


def event_ics(con, eid: int, link: str) -> str:
    e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published'", eid)
    if not e or not e["starts_at"]:
        raise ApiError("not_found")
    return _calendar(_vevent(e, link))


def cal_token(con, v: Viewer) -> str:
    """My calendar feed's secret (Oct 5): made once and kept, so a subscribed calendar stays subscribed."""
    need_student(v)
    t = one(con, "SELECT cal_token FROM users WHERE id = ?", v.id)[0]
    if not t:
        t = secrets.token_urlsafe(18)
        con.execute("UPDATE users SET cal_token = ? WHERE id = ?", (t, v.id))
    return t


def cal_feed(con, token: str, link) -> str:
    """Everything I go to, from a month ago on: the phone's calendar refreshes it on its own (hourly asked), so a new
    registration shows up and a cancelled one goes; a cancelled event stays, struck through."""
    u = one(con, "SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE u.cal_token = ?", token) if token else None
    if not u:
        raise ApiError("not_found")
    evs = rows(con, """SELECT e.*, o.name AS org_name FROM registrations r JOIN events e ON e.id = r.event_id JOIN orgs o ON o.id = e.org_id
        WHERE r.user_id = ? AND r.status IN ('going', 'hold') AND e.status IN ('published', 'cancelled') AND e.hidden_at IS NULL
        AND COALESCE(e.ends_at, e.starts_at + ?) > ? ORDER BY e.starts_at LIMIT 300""", u["id"], NO_END, now() - 30 * 86400)
    return _calendar([x for e in evs for x in _vevent(e, link(e["id"]))], "X-WR-CALNAME:KBTU App", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H")


SETTINGS = {"lang": "lang", "theme": "theme", "nRemind": "n_remind", "nNewEvents": "n_new_events",
            "nFriends": "n_friends", "showGoing": "show_going", "hideFirstYear": "hide_first_year"}


def ms_link(con, uid: int, who: dict) -> None:
    """A student signed in with the KBTU Microsoft account (msauth.py): confirmed, with that account's email, and its
    names over typed ones (review, Oct 19: otherwise "confirmed" proved nothing about who it is); the old portal's
    names stay (they came from KBTU already)"""
    con.execute("""UPDATE students SET ms_oid = ?, email = ?, manual = 0, verified_at = ?, ms_profile = ?,
        first_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), first_name) ELSE first_name END,
        last_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), last_name) ELSE last_name END WHERE user_id = ?""",
                (who["oid"], who["email"], now(), json.dumps(who.get("profile") or {}, ensure_ascii=False), who["first"], who["last"], uid))
    con.execute("DELETE FROM meta WHERE key = ?", (f"ms:{uid}",))


def ms_remember(con, uid: int, who: dict) -> None:
    """Signed in with Microsoft before typing the student ID and year: kept a week (MS_KEEP) for kbtu_manual"""
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (f"ms:{uid}", json.dumps({**who, "at": now()})))


MS_KEEP = 7 * 86400  # a Microsoft sign-in waits a week for the student ID and year (review 3: a day was too short)


def ms_pending(con, uid: int) -> dict | None:
    r = one(con, "SELECT value FROM meta WHERE key = ?", f"ms:{uid}")
    who = json.loads(r[0]) if r else None
    return who if who and who["at"] > now() - MS_KEEP else None


def ms_sweep(con) -> None:
    """Each bot round: Microsoft sign-ins never finished (they hold the Graph profile) and the used-link marks"""
    con.execute("DELETE FROM meta WHERE key LIKE 'ms:%' AND (NOT json_valid(value) OR json_extract(value, '$.at') < ?)", (now() - MS_KEEP,))
    con.execute("DELETE FROM meta WHERE key LIKE 'ms_used:%' AND CAST(value AS INTEGER) < ?", (now() - 86400,))


def id_clash(con, sid: str, new: int, old: int) -> None:
    """Someone signed in with Microsoft typed a student ID another account holds: every admin hears, with both
    people's contacts, and asks them (owner, Oct 20). Once per pair, 3 a day per person (review: no admin spam). The
    holder's name and email are kept in the message: their row may be gone by the time it's sent."""
    day = now() // 86400
    if one(con, "SELECT COUNT(DISTINCT ref) FROM bot_outbox WHERE kind = 'id_clash' AND ref LIKE ? AND send_after >= ?",
           f"ic:%:{new}:%", day * 86400)[0] >= 3:
        return
    h = one(con, "SELECT first_name, last_name, email FROM students WHERE user_id = ?", old)
    held = json.dumps({"name": " ".join(x for x in (h["first_name"], h["last_name"]) if x), "email": h["email"]} if h else {})
    for (uid,) in rows(con, "SELECT id FROM users WHERE role = 'admin'"):
        notify(con, uid, "id_clash", f"ic:{sid}:{new}:{old}", held)


def me(con, v: Viewer) -> dict:
    u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    relink = bool(s and s["manual"])  # typed in before Microsoft only: signed out until Microsoft confirms (owner, Oct 20)
    s = None if relink else s
    members = rows(con, """SELECT m.role, t.name AS title, t.rights, o.* FROM org_members m JOIN orgs o ON o.id = m.org_id
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND o.status = 'active'""", v.id) if s else []
    tickets = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status = 'going' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""", v.id, NO_END, now())[0]
    name_row = one(con, PERSON + " WHERE u.id = ?", v.id)
    own = one(con, "SELECT path FROM files WHERE id = ?", u["avatar_file_id"]) if u["avatar_file_id"] else None
    # signed in while the previous version still ran (a deploy); staff (kbtu.admin staff) take none: it's the students' order
    # typed in by hand counts too (owner, Oct 19: "give the number at once"; the Microsoft sign-in confirms them later)
    if s and u["card_no"] is None and not u["is_founder"] and s["consent_version"] != "staff":
        first_fifty(con, v.id)  # the number and, with it, "First 500"
        u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    return {
        "id": u["id"], "tg": {"id": u["tg_id"], "username": u["tg_username"], "firstName": u["tg_first_name"], "lastName": u["tg_last_name"]},
        "avatar": avatar_of(name_row), "name": shown_name(name_row), "nick": u["nick"],
        "photo": {"telegram": bool(u["avatar_tg"]), "tg": u["tg_photo_url"], "own": f"media/{own['path']}.t.webp" if own else None},
        "student": {"studentId": s["student_id"], "firstName": s["first_name"], "lastName": s["last_name"], "email": s["email"],
                    "phone": s["phone"], "course": s["course"], "school": s["school"], "program": s["program"], "syncedAt": s["synced_at"],
                    "ms": s["ms_oid"] is not None} if s else None,
        # signed in with Microsoft, the student ID and year still to type: the form shows the account's names
        "msPending": {k: p[k] for k in ("first", "last", "email")} if not s and not relink and (p := ms_pending(con, v.id)) else None,
        "relink": relink,
        "role": u["role"], "founder": bool(u["is_founder"]), "mark": u["mark"], "qr": f"{v.id}_{_qr_code(con, v.id)}" if s else None,
        "no": (0 if u["is_founder"] else u["card_no"]) if s else None,
        "oversee": any(m["can_oversee"] and m["role"] != "member" for m in members),
        "bio": u["bio"], "showcase": [x for x in u["showcase"].split(",") if x],
        "settings": {k: (u[c] if k in ("lang", "theme") else bool(u[c])) for k, c in SETTINGS.items()},
        "memberships": [{"org": org_ref(con, m), "role": m["role"], "title": m["title"], "rights": _ordered(_rights_from(m["role"], m["rights"]))}
                        for m in members],
        "counters": {"tickets": tickets, "unreadBroadcasts": unread_broadcasts(con, v),
                     "friendRequests": one(con, "SELECT COUNT(*) FROM friend_requests WHERE to_id = ? AND status = 'pending'", v.id)[0] if v.student else 0,
                     "reports": one(con, "SELECT COUNT(DISTINCT target || target_id) FROM reports WHERE status = 'open'")[0] if v.role == "admin" else 0,
                     "clubApps": one(con, "SELECT COUNT(*) FROM club_applications WHERE status = 'pending'")[0] if v.role in ("admin", "moderator") else 0},
        "unlocked": unlocked(con, v),
        "skin": _skin(con, v.id) if s else None,
        "deleteAt": u["delete_at"] if s or relink else None,  # a relink account's week shows too (review)
    }


# the clubs with a badge of their own (web: awards.ts `skinned`)
SKINNED = ("o.official = 1 AND o.status = 'active' AND (lower(o.name) LIKE '%studex%' OR lower(o.name) LIKE '%cheer%'"
           " OR lower(o.name) LIKE '%knight%')")


def _skin(con, uid: int) -> int | str | None:
    """The badge I show (owner, Oct 13: badges as skins): a club's id, "sower" (the creator's own), None for KBTU's.
    My pick holds; a club picked holds while I'm in it. Never picked (or that club left): the newest club I joined
    that has a badge, the creator's own for the creator (owner, Oct 13: a new club's badge comes by itself); of
    several, the one where my role is highest, as the picker lists them (LookSheet)."""
    u = one(con, "SELECT skin_pick, skin_org, is_founder FROM users WHERE id = ?", uid)
    if u["skin_pick"] == "kbtu":
        return None
    if u["is_founder"] and u["skin_pick"] in ("sower", None):
        return "sower"
    if u["skin_pick"] == "org" and _skin_ok(con, uid, u["skin_org"]):
        return u["skin_org"]
    r = one(con, f"""SELECT o.id FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ? AND {SKINNED}
        ORDER BY CASE m.role WHEN 'president' THEN 4 WHEN 'vice' THEN 3 WHEN 'head' THEN 2 ELSE 1 END DESC, m.joined_at DESC LIMIT 1""", uid)
    return r[0] if r else None


def _skin_ok(con, uid: int, oid: int):
    """Any club's lanyard can be tried on, member or not (owner, Oct 20: "let everyone try on another club's"); the
    creator's own stays his. ponytail: uid unused while it's open to all; a membership check comes back if he closes it."""
    return one(con, f"SELECT 1 FROM orgs o WHERE o.id = ? AND {SKINNED}", oid)


def _qr_code(con, uid: int) -> str:
    """The secret half of my badge QR (§4.4): made on first use, random like a ticket code."""
    code = one(con, "SELECT qr_code FROM users WHERE id = ?", uid)["qr_code"]
    if not code:
        con.execute("UPDATE users SET qr_code = ? WHERE id = ? AND qr_code IS NULL",
                    ("".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(10)), uid))
        code = one(con, "SELECT qr_code FROM users WHERE id = ?", uid)["qr_code"]
    return code


def update_me(con, v: Viewer, patch: dict) -> dict:
    sets: dict[str, object] = {}
    for k, col in SETTINGS.items():
        if k not in patch:
            continue
        val = patch[k]
        if k == "lang" and val not in ("ru", "kk", "en") or k == "theme" and val not in ("light", "dark", None):
            raise ApiError("bad_input")
        sets[col] = val if k in ("lang", "theme") else int(bool(val))
    if "bio" in patch or "showcase" in patch or "nick" in patch:
        need_student(v)
    if "nick" in patch:
        sets["nick"] = clean_nick(patch["nick"])
    if "skin" in patch:  # my pick: a club with a lanyard (`_skin_ok`), "sower" for the creator, null = the KBTU one (`_skin`)
        need_student(v)
        val = patch["skin"]
        if val is None:
            sets.update(skin_pick="kbtu", skin_org=None)
        elif val == "sower" and one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)[0]:
            sets.update(skin_pick="sower", skin_org=None)
        elif type(val) is int and _skin_ok(con, v.id, val):
            sets.update(skin_pick="org", skin_org=val)
        else:
            raise ApiError("bad_input")
    if "avatarTg" in patch:  # off only with a photo of my own to show (the upload turns it off by itself)
        if not patch["avatarTg"] and not one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]:
            raise ApiError("bad_input")
        sets["avatar_tg"] = int(bool(patch["avatarTg"]))
    if "bio" in patch:
        sets["bio"] = str(patch["bio"])[:150]
    if "showcase" in patch:  # up to 6 keys: achievement codes and badges as b<event id>, in the order picked (§4.11)
        codes = {a[0] for a in ACHIEVEMENTS}
        keys = [k for k in (patch["showcase"] if isinstance(patch["showcase"], list) else [])
                if isinstance(k, str) and (k in codes or re.fullmatch(r"b\d{1,9}", k))]
        sets["showcase"] = ",".join(list(dict.fromkeys(keys))[:6])
    if sets:
        con.execute(f"UPDATE users SET {', '.join(c + ' = ?' for c in sets)} WHERE id = ?", (*sets.values(), v.id))
    if "nRemind" in patch:  # the switch acts at once on reminders already queued: off drops them, on arms the upcoming ones
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND sent_at IS NULL", (v.id,))
        for e in rows(con, "SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id WHERE r.user_id = ? AND r.status = 'going'", v.id):
            _remind(con, v.id, e)
    return me(con, v)


def _drop_photo(con, fid: int | None) -> list[str]:
    """A photo of mine nobody shows any more: its row goes, and its files on disk (returned) unless another row has
    the same picture (files are named by their content)."""
    f = one(con, "SELECT id, path FROM files WHERE id = ?", fid) if fid else None
    if not f:
        return []
    con.execute("DELETE FROM files WHERE id = ?", (f["id"],))
    return [] if one(con, "SELECT 1 FROM files WHERE path = ?", f["path"]) else [f["path"]]


def set_photo(con, v: Viewer, saved: dict) -> list[str]:
    """My own photo (a processed upload, media.save) instead of Telegram's: the "Photo from Telegram" switch goes off
    (owner, Oct 5). The one it replaces is deleted; returns its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'avatar' AND owner_id = ?", saved["sha256"], v.id)
    fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'avatar', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                saved["path"], v.id, now(), saved["color"])).lastrowid
    con.execute("UPDATE users SET avatar_file_id = ?, avatar_tg = 0 WHERE id = ?", (fid, v.id))
    return _drop_photo(con, old) if old and old != fid else []


def drop_my_photo(con, v: Viewer) -> list[str]:
    """My own photo deleted (owner's list, Oct 10: the upload shouldn't stay on the server): Telegram's is back; returns
    its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    con.execute("UPDATE users SET avatar_file_id = NULL, avatar_tg = 1 WHERE id = ?", (v.id,))
    return _drop_photo(con, old) if old else []


DELETE_WAIT = 7 * 86400


def ask_delete(con, v: Viewer) -> dict:
    """"Delete my account" (§4.8) waits a week, then `delete_due` runs it (owner, Oct 13: a change of heart, or someone
    holding my phone, shouldn't cost the awards; the KBTU password asked before shut out whoever no longer has it).
    The bot says so at once, with the way back; nothing is hidden meanwhile."""
    need_student(v)
    if one(con, "SELECT 1 FROM org_members WHERE user_id = ? AND role = 'president'", v.id):
        raise ApiError("conflict", "president")  # a club can't be left without its president: hand it over first
    at = now() + DELETE_WAIT
    if con.execute("UPDATE users SET delete_at = ? WHERE id = ? AND delete_at IS NULL", (at, v.id)).rowcount:
        notify(con, v.id, "delete_soon", f"del:{at}")
    return me(con, v)


def keep_me(con, v: Viewer) -> dict:
    con.execute("UPDATE users SET delete_at = NULL WHERE id = ?", (v.id,))
    return me(con, v)


def delete_due(con) -> tuple[list[str], list[str]]:
    """The accounts whose week ran out (a President by then waits on: the club needs one), deleted; their files to
    remove from disk, as delete_me's."""
    gone: tuple[list[str], list[str]] = ([], [])
    for u in rows(con, """SELECT id, role FROM users WHERE delete_at <= ?
            AND id NOT IN (SELECT user_id FROM org_members WHERE role = 'president')""", now()):
        receipts, photos = delete_me(con, Viewer(u["id"], u["role"], True))
        con.execute("UPDATE users SET delete_at = NULL WHERE id = ?", (u["id"],))
        gone[0].extend(receipts)
        gone[1].extend(photos)
    return gone


def delete_me(con, v: Viewer) -> tuple[list[str], list[str]]:
    """Delete my data (§4.8): the KBTU profile and everything tied to it. The Telegram account stays a guest, so its
    settings and a ban stay on the Telegram ID. Future tickets are given up first, so seats free up and the
    waitlist moves. What belongs to a club stays without the person: posts, comments written as the club."""
    need_student(v)
    if one(con, "SELECT 1 FROM org_members WHERE user_id = ? AND role = 'president'", v.id):
        raise ApiError("conflict", "president")  # a club can't be left without its president: hand it over first
    for (eid,) in rows(con, """SELECT r.event_id FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ? AND r.status IN ('going', 'hold', 'waitlist') AND e.starts_at > ?""", v.id, now()):
        unregister(con, v, eid)
    with tx(con):
        receipts = [f["path"] for f in rows(con, "SELECT path FROM files WHERE owner_id = ? AND kind = 'receipt'", v.id)]
        con.execute("DELETE FROM receipts WHERE file_id IN (SELECT id FROM files WHERE owner_id = ? AND kind = 'receipt')", (v.id,))
        con.execute("DELETE FROM files WHERE owner_id = ? AND kind = 'receipt'", (v.id,))
        for t in ("students", "schedule_classes", "org_members", "join_requests", "club_applications", "subscriptions",
                  "registrations", "saved_events", "post_reactions", "post_reads", "friend_links", "achievement_grants",
                  "achievement_levels", "chat_opens", "bot_outbox", "event_ratings", "member_tags", "strikes", "removal_requests", "comment_reads",
                  "org_history"):  # org_history after org_members: its trigger closes the rows first
            con.execute(f"DELETE FROM {t} WHERE user_id = ?", (v.id,))
        for t, c in (("strikes", "by_id"), ("strikes", "cleared_by"), ("removal_requests", "by_id"), ("removal_requests", "decided_by"), ("org_bans", "by_id")):
            con.execute(f"UPDATE {t} SET {c} = NULL WHERE {c} = ?", (v.id,))
        con.execute("DELETE FROM meta WHERE key = ?", (f"ms:{v.id}",))  # an unfinished Microsoft sign-in: its profile too
        con.execute("DELETE FROM comments WHERE user_id = ? AND as_org = 0", (v.id,))
        con.execute("DELETE FROM friendships WHERE a = ? OR b = ?", (v.id, v.id))
        for t in ("friend_requests", "friend_invites"):
            con.execute(f"DELETE FROM {t} WHERE from_id = ? OR to_id = ?", (v.id, v.id))
        con.execute("UPDATE posts SET author_id = NULL WHERE author_id = ?", (v.id,))
        con.execute("UPDATE event_updates SET author_id = NULL WHERE author_id = ?", (v.id,))  # the club's words stay
        con.execute("DELETE FROM event_photos WHERE added_by = ?", (v.id,))                      # my photos leave the albums
        con.execute("UPDATE reports SET reporter_id = NULL WHERE reporter_id = ?", (v.id,))
        con.execute("""UPDATE users SET bio = '', showcase = '', qr_code = NULL, cal_token = NULL, nick = NULL, avatar_tg = 1, avatar_file_id = NULL
            WHERE id = ?""", (v.id,))
        photos = [p for f in rows(con, "SELECT id FROM files WHERE kind = 'avatar' AND owner_id = ?", v.id) for p in _drop_photo(con, f["id"])]
        con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'delete_my_data', ?, ?)", (v.id, f"user:{v.id}", now()))
    # the receipt images and my own photo, to delete from disk
    return [p for p in receipts if not one(con, "SELECT 1 FROM files WHERE path = ?", p)], photos


# ---------------------------------------------------------------- events

def _visible(con, v: Viewer, e: sqlite3.Row, roles: dict[int, str] | None = None) -> bool:
    """Drafts and hidden events only for the organizing team (and the admin); team-only events for members. `roles`:
    _roles(), read once when checking a list."""
    if one(con, "SELECT 1 FROM orgs WHERE id = ? AND status = 'hidden'", e["org_id"]):
        return False  # a club the admin hid: its events are gone for everyone (owner, Oct 16)
    roles = _roles(con, v) if roles is None else roles
    team = at_least(roles.get(e["org_id"]), "member")
    if e["status"] == "draft" or e["hidden_at"]:
        return team or v.role == "admin"
    if e["visibility"] == "members":
        return team
    if e["visibility"] == "leaders":
        return team or at_least(max(roles.values(), key=RANK.__getitem__, default=None), e["leaders_from"] or "president")
    return True


def sweep_holds(con) -> None:
    """Expired holds give their seats back, and the waitlist moves (a worker does this too)."""
    expired = rows(con, "SELECT DISTINCT event_id FROM registrations WHERE status = 'hold' AND hold_until < ?", now())
    if not expired:
        return
    with tx(con):
        con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'hold_expired', updated_at = ? WHERE status = 'hold' AND hold_until < ?", (now(), now()))
        for r in expired:
            promote(con, one(con, "SELECT * FROM events WHERE id = ?", r[0]))


def events(con, v: Viewer, frm: int | None = None, to: int | None = None, org: int | None = None) -> list[dict]:
    sweep_holds(con)
    hide_first = v.student and one(con, "SELECT hide_first_year FROM users WHERE id = ?", v.id)[0]
    sql = "SELECT * FROM events WHERE status != 'draft' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) > ?"
    args: list = [NO_END, now()]
    if org is not None:
        sql += " AND org_id = ?"; args.append(org)
    if frm is not None:
        sql += " AND starts_at >= ?"; args.append(frm)
    if to is not None:
        sql += " AND starts_at < ?"; args.append(to)
    if hide_first:
        sql += " AND first_year = 0"
    roles = _roles(con, v)
    return cards(con, v, [e for e in rows(con, sql + " ORDER BY starts_at", *args) if _visible(con, v, e, roles)])


def past_events(con, v: Viewer) -> list[dict]:
    found = rows(con, """SELECT * FROM events WHERE status = 'published' AND hidden_at IS NULL AND COALESCE(ends_at, starts_at + ?) <= ?
        ORDER BY starts_at DESC LIMIT 50""", NO_END, now())
    roles = _roles(con, v)
    return cards(con, v, [e for e in found if _visible(con, v, e, roles)])


def _event(con, v: Viewer, eid: int) -> sqlite3.Row:
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or not _visible(con, v, e):
        raise ApiError("not_found")
    return e


def event(con, v: Viewer, eid: int) -> dict:
    sweep_holds(con)
    return full(con, v, _event(con, v, eid))


def _ticket_code(con) -> str:
    """6 characters to read out and type at the door, no 0/O or 1/I/L (owner, Oct 4: 12 were too long, his QR
    didn't scan). ~30 bits is enough: only a club's door staff can check a code, and the scanner shows the
    holder's face. The QR holds 'KBTU' + this, 10 characters: the smallest QR there is (§4.4)."""
    while True:
        c = "".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(6))
        if not one(con, "SELECT 1 FROM registrations WHERE ticket_code = ?", c):
            return c


def notify(con, uid: int, kind: str, ref: str, payload: str = "{}", after: int | None = None) -> None:
    """Queue a bot message (§7). (user, kind, ref) is unique, so a repeat is a no-op."""
    con.execute("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, ?, ?, ?, ?)",
                (uid, kind, ref, payload, after or now()))


def add_seats(con, v: Viewer, eid: int, n: object) -> dict:
    """"+N seats" (§4.2), the club's Head+: the waitlist moves into them at once, in order."""
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 500:
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published" or e["seats"] is None or e["starts_at"] <= now():
            raise ApiError("closed")
        con.execute("UPDATE events SET seats = seats + ?, updated_at = ? WHERE id = ?", (n, now(), eid))
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
            con.execute("UPDATE registrations SET status = 'hold', hold_until = ?, waitlisted_at = NULL, updated_at = ? WHERE id = ?", (now() + HOLD, now(), nxt["id"]))
        else:
            con.execute("UPDATE registrations SET status = 'going', free = ?, waitlisted_at = NULL, updated_at = ? WHERE id = ?",
                        (int(bool(e["price"])), now(), nxt["id"]))
            _remind(con, nxt["user_id"], e)
        notify(con, nxt["user_id"], "seat_hold" if pay else "seat_free", f"event:{e['id']}")  # a hold: pay within 30 min


def register(con, v: Viewer, eid: int, invited_by: int | None = None) -> dict:
    need_student(v)
    sweep_holds(con)
    with tx(con):  # count and insert under one write lock: the last seat goes to one person
        e = _event(con, v, eid)
        if e["status"] == "draft":
            raise ApiError("not_found")
        if e["status"] == "cancelled" or e["starts_at"] <= now():
            raise ApiError("closed")
        if e["reg_until"] and e["reg_until"] <= now():
            raise ApiError("closed", "deadline")
        if e["external_url"]:
            raise ApiError("bad_input")
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if r and r["status"] in ("going", "hold", "waitlist"):
            return card(con, v, e)
        is_full = e["seats"] is not None and taken(con, eid) >= e["seats"]
        free = not is_full and _free_seat(con, e, v.id)
        status = "waitlist" if is_full else "hold" if e["price"] and not free else "going"
        hold = now() + HOLD if status == "hold" else None
        wait = now() if status == "waitlist" else None
        if r:
            con.execute("""UPDATE registrations SET status = ?, cancel_reason = NULL, hold_until = ?, waitlisted_at = ?, free = ?, note = NULL, updated_at = ?
                WHERE id = ?""", (status, hold, wait, int(free), now(), r["id"]))
        else:
            inviter = invited_by if invited_by in friend_ids(con, v.id) else None
            if inviter is None:  # "Bring a friend": the first friend who asked gets the credit ("Life of the party", §4.7)
                first = one(con, "SELECT from_id FROM friend_invites WHERE event_id = ? AND to_id = ? ORDER BY created_at LIMIT 1", eid, v.id)
                inviter = first["from_id"] if first else None
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, waitlisted_at, invited_by, free, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (eid, v.id, status, _ticket_code(con), hold, wait, inviter, int(free), now(), now()))
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
    says when a receipt looks wrong: owner, Oct 11, "upload another?")."""
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('hold', 'going')", eid, v.id)
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    old = None
    if r and r["status"] == "going":
        old = one(con, "SELECT * FROM receipts WHERE registration_id = ? AND status = 'accepted' AND reviewed_at IS NULL ORDER BY id DESC", r["id"])
        if not old or (e["ends_at"] or e["starts_at"] + 3 * 3600) < now():
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
            VALUES (?, 'receipt', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"], saved["path"], v.id, now())).lastrowid
        con.execute("""INSERT INTO receipts (registration_id, file_id, via, amount, receipt_no, sender_name, recipient_name, paid_at, flags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (r["id"], fid, via, got.get("amount"), got.get("no"), got.get("sender"), got.get("recipient"),
                                                      got.get("paid_at"), flags, now()))
        if not old:
            con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE id = ?", (now(), r["id"]))
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
        con.execute("UPDATE receipts SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?", ("rejected" if reject else "accepted", v.id, now(), rid))
        if reject:
            con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'receipt_reject', ?, ?)", (v.id, f"receipt:{rid}", now()))
            if c["reg"] == "going":
                con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'receipt_rejected', updated_at = ? WHERE id = ?", (now(), c["registration_id"]))
                con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (c["user_id"], f"event:{e['id']}:%"))
                notify(con, c["user_id"], "receipt_rejected", f"event:{e['id']}:{rid}")
                promote(con, e)


def _remind(con, uid: int, e: sqlite3.Row) -> None:
    """The 2-hour reminder (§7), unless the person turned it off; ref carries the start, so a moved event re-arms it."""
    if one(con, "SELECT n_remind FROM users WHERE id = ?", uid)[0] and e["starts_at"] - 7200 > now():
        notify(con, uid, "remind_2h", f"event:{e['id']}:{e['starts_at']}", after=e["starts_at"] - 7200)


def unregister(con, v: Viewer, eid: int) -> dict:
    need_student(v)
    with tx(con):
        e = _event(con, v, eid)
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
        if not r:
            raise ApiError("not_found")
        if e["starts_at"] <= now():
            raise ApiError("closed")
        freed = r["status"] in ("going", "hold")
        con.execute("""UPDATE registrations SET status = 'cancelled', cancel_reason = 'self', hold_until = NULL, waitlisted_at = NULL, updated_at = ?
            WHERE id = ?""", (now(), r["id"]))
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (v.id, f"event:{eid}:%"))
        if freed:
            promote(con, e)
    return card(con, v, e)


def set_saved(con, v: Viewer, eid: int, on: bool) -> None:
    need_student(v)
    _event(con, v, eid)
    if on:
        con.execute("INSERT OR IGNORE INTO saved_events (user_id, event_id, created_at) VALUES (?, ?, ?)", (v.id, eid, now()))
    else:
        con.execute("DELETE FROM saved_events WHERE user_id = ? AND event_id = ?", (v.id, eid))


def tickets(con, v: Viewer) -> list[dict]:
    if not v.student:
        return []
    found = rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status IN ('going','hold','waitlist') AND COALESCE(e.ends_at, e.starts_at + ?) > ?
        ORDER BY e.starts_at""", v.id, NO_END, now())
    return cards(con, v, found)


# ---------------------------------------------------------------- orgs

def org_shape(con, v: Viewer, o: sqlite3.Row) -> dict:
    return org_shapes(con, v, [o])[0]


def org_shapes(con, v: Viewer, found: list[sqlite3.Row]) -> list[dict]:
    """Clubs (types.ts Org), each count and each of my marks read once for the whole list (Clubs was 560 queries)."""
    if not found:
        return []
    ids = [o["id"] for o in found]
    q = _qs(ids)
    count = lambda table, where="": dict(rows(con, f"SELECT org_id, COUNT(*) FROM {table} WHERE org_id IN ({q}) {where} GROUP BY org_id", *ids))  # noqa: E731
    subs, members = count("subscriptions"), count("org_members")
    upcoming = dict(rows(con, f"""SELECT org_id, COUNT(*) FROM events WHERE org_id IN ({q}) AND status = 'published' AND hidden_at IS NULL
        AND starts_at > ? GROUP BY org_id""", *ids, now()))
    mine = {r["org_id"]: r for r in rows(con, f"""SELECT m.org_id, m.role, t.name AS title, t.rights FROM org_members m
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND m.org_id IN ({q})""", v.id, *ids)} if v.student else {}
    subscribed = {r[0] for r in rows(con, f"SELECT org_id FROM subscriptions WHERE user_id = ? AND org_id IN ({q})", v.id, *ids)} if v.student else set()
    asked = {r["org_id"]: r for r in rows(con, f"SELECT org_id, status, decided_at FROM join_requests WHERE user_id = ? AND org_id IN ({q}) ORDER BY id",
                                          v.id, *ids)} if v.student else {}  # the last one wins
    files = _by_id(con, "files", (o["logo_file_id"] for o in found))
    # a recruitment round taking applications (casting.py), and whether I applied to it
    live = {r["org_id"]: r for r in rows(con, f"SELECT id, org_id, closes_at FROM rounds WHERE org_id IN ({q}) AND status = 'open' AND closes_at > ?", *ids, now())}
    applied = {r[0] for r in rows(con, f"""SELECT r.org_id FROM round_apps a JOIN rounds r ON r.id = a.round_id WHERE a.user_id = ? AND r.org_id IN ({q})
        AND r.status != 'done' AND a.stage != 'withdrawn'""", v.id, *ids)} if v.student and live else set()
    return [{
        **org_ref(con, o, files), "description": o["description"], "links": json.loads(o["links"]),
        **({"i18n": json.loads(o["i18n"])} if o["i18n"] else {}),
        "round": {"id": live[o["id"]]["id"], "closesAt": live[o["id"]]["closes_at"], "applied": o["id"] in applied} if o["id"] in live else None,
        "subscribers": subs.get(o["id"], 0), "members": members.get(o["id"], 0), "upcoming": upcoming.get(o["id"], 0),
        "recruiting": bool(o["recruiting"]), "myRequest": _request_state(asked.get(o["id"])),
        "subscribed": o["id"] in subscribed,
        "myRole": mine[o["id"]]["role"] if o["id"] in mine else None, "canBroadcast": bool(o["can_broadcast"]), "canOversee": bool(o["can_oversee"]),
        "myTitle": mine[o["id"]]["title"] if o["id"] in mine else None,
        "myRights": _ordered(_rights_from(mine[o["id"]]["role"], mine[o["id"]]["rights"])) if o["id"] in mine else [],
    } for o in found]


def orgs(con, v: Viewer) -> list[dict]:
    found = org_shapes(con, v, rows(con, "SELECT * FROM orgs WHERE status = 'active' AND kind NOT IN ('office','app')"))
    return sorted(found, key=lambda o: (not o["subscribed"], -o["subscribers"]))


def org(con, v: Viewer, oid: int) -> dict:
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND (status = 'active' OR status = 'hidden' AND ?)", oid, v.role == "admin")
    if not o:
        raise ApiError("not_found")
    return org_shape(con, v, o)


def subscribe(con, v: Viewer, oid: int, on: bool) -> dict:
    need_student(v)
    if on:
        con.execute("INSERT OR IGNORE INTO subscriptions (user_id, org_id, created_at) VALUES (?, ?, ?)", (v.id, oid, now()))
    else:
        con.execute("DELETE FROM subscriptions WHERE user_id = ? AND org_id = ?", (v.id, oid))
    return org(con, v, oid)


# ---------------------------------------------------------------- joining a club (§4.5)

REAPPLY = 30 * 86400    # after a decline, a new application to the same club only in 30 days


def _my_request(con, v: Viewer, oid: int) -> str | None:
    """'pending', 'rejected' (declined less than 30 days ago, so no new one yet) or None."""
    if not v.student:
        return None
    return _request_state(one(con, "SELECT status, decided_at FROM join_requests WHERE org_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", oid, v.id))


def _request_state(r: sqlite3.Row | None) -> str | None:
    return r["status"] if r and (r["status"] == "pending" or r["status"] == "rejected" and r["decided_at"] > now() - REAPPLY) else None


def apply(con, v: Viewer, oid: int) -> dict:
    """Ask to join; the club's Vice+ hear from the bot. Asking again while it's pending changes nothing."""
    need_student(v)
    with tx(con):
        o = one(con, "SELECT * FROM orgs WHERE id = ? AND status = 'active'", oid)
        if not o:
            raise ApiError("not_found")
        if role_in(con, v, oid):
            raise ApiError("conflict", "member")
        if banned(con, oid, v.id):
            raise ApiError("forbidden", "banned")
        mine = _my_request(con, v, oid)
        if mine == "rejected":
            raise ApiError("rate_limited", "declined")
        if mine is None:
            if not o["recruiting"]:
                raise ApiError("closed")
            con.execute("INSERT INTO join_requests (org_id, user_id, created_at) VALUES (?, ?, ?)", (oid, v.id, now()))
            for m in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('vice','president')", oid):
                notify(con, m["user_id"], "join_request", f"jr:{oid}:{v.id}:{now() // 86400}")  # withdraw and ask again: one ping a day
    return org(con, v, oid)


def withdraw(con, v: Viewer, oid: int) -> dict:
    need_student(v)
    con.execute("UPDATE join_requests SET status = 'withdrawn', decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'", (now(), oid, v.id))
    return org(con, v, oid)


def join_requests(con, v: Viewer, oid: int) -> list[dict]:
    """Pending applications, oldest first, with what the club needs to write to the person first (§3: Vice+ see contacts)."""
    _may(con, v, oid, "team")
    found = rows(con, f"""SELECT j.id AS rid, j.created_at AS at, {PERSON_COLS}, s.course, s.school, u.tg_username
        FROM join_requests j JOIN users u ON u.id = j.user_id JOIN students s ON s.user_id = u.id
        WHERE j.org_id = ? AND j.status = 'pending' ORDER BY j.id""", oid)
    return [{"id": p["rid"], "person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "course": p["course"],
             "school": p["school"], "username": p["tg_username"], "createdAt": p["at"]} for p in found]


def decide_join(con, v: Viewer, rid: int, accept: bool) -> None:
    r = one(con, "SELECT * FROM join_requests WHERE id = ?", rid)
    if not r:
        raise ApiError("not_found")
    _may(con, v, r["org_id"], "team")
    with tx(con):
        if not con.execute("UPDATE join_requests SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                           ("accepted" if accept else "rejected", v.id, now(), rid)).rowcount:
            raise ApiError("conflict")  # withdrawn, or another Vice answered first
        if accept:
            con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (r["org_id"], r["user_id"], now()))
        notify(con, r["user_id"], "join_decided", f"jr:{rid}:{'yes' if accept else 'no'}")


def update_org(con, v: Viewer, oid: int, body: dict) -> dict:
    """The club's own profile and settings (Vice+, §2): whether it takes applications, and what students see on its
    sheet — the name, its logo (an upload of the editor's; null: the emoji on its cover again), emoji and cover, about,
    up to 6 links. Only what is sent changes, all or nothing."""
    _may(con, v, oid, "profile")
    bad, sets = object(), {}
    text = lambda k: str(body.get(k) or "").strip()  # noqa: E731
    if "recruiting" in body:
        sets["recruiting"] = body["recruiting"] if isinstance(body["recruiting"], bool) else bad
    if "name" in body:
        sets["name"] = text("name") if 2 <= len(text("name")) <= 60 else bad
        if sets["name"] is not bad and one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived' AND id != ?", sets["name"], oid):
            raise ApiError("conflict", "taken")
    if "short" in body:
        sets["short"] = text("short").upper() if 1 <= len(text("short")) <= 2 else bad
    if "emoji" in body:
        sets["emoji"] = text("emoji") if re.fullmatch(r"[a-z0-9_]{1,40}", text("emoji")) else bad
    if "cover" in body:
        c = body["cover"]
        sets["cover"] = c if isinstance(c, int) and not isinstance(c, bool) and 0 <= c < COVERS else bad
    if "description" in body:
        sets["description"] = text("description") if len(text("description")) <= 600 else bad
    if "links" in body:
        ls = body["links"]
        ok = isinstance(ls, list) and len(ls) <= 6 and all(isinstance(x, str) and len(x) <= 200 and LINK.fullmatch(x) for x in ls)
        sets["links"] = json.dumps(ls) if ok else bad
    if "logoId" in body:
        lg = body["logoId"]
        if lg is not None and (not isinstance(lg, int) or isinstance(lg, bool)):
            sets["logo_file_id"] = bad
        elif lg != _org(con, oid)["logo_file_id"]:  # the logo it has stays, whoever uploaded it
            own = lg is None or one(con, "SELECT 1 FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", lg, v.id)
            sets["logo_file_id"] = lg if own else bad
    if not body or any(x is bad for x in sets.values()):
        raise ApiError("bad_input")
    if sets:
        before = _org(con, oid)
        shown = json.loads(before["i18n"]) if before["i18n"] else {}
        for k in ("name", "description"):  # the app showed a translation in the form: sent back unchanged, it's no edit
            if k in sets and any(sets[k] == f.get(k) for f in shown.values()):
                sets[k] = before[k]
        con.execute(f"UPDATE orgs SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), oid))  # keys from the list above
        if "description" in sets and sets["description"] != before["description"]:
            con.execute("UPDATE orgs SET lang = NULL, ai_tries = 0 WHERE id = ?", (oid,))  # translated again (ai.py)
        if before["i18n"] and (gone := {k for k in ("name", "description") if k in sets and sets[k] != before[k]}):
            # a field edited by hand (in Russian, or whatever was typed) is shown as typed in every language
            tr = {lang: g for lang, f in json.loads(before["i18n"]).items() if (g := {k: x for k, x in f.items() if k not in gone})}
            con.execute("UPDATE orgs SET i18n = ? WHERE id = ?", (json.dumps(tr, ensure_ascii=False), oid))
    if sets.keys() - {"recruiting"}:
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'org_edit', ?, ?, ?)",
                    (v.id, f"org:{oid}", json.dumps(sorted(sets.keys() - {"recruiting"})), now()))
    return org(con, v, oid)


def schedule(con, v: Viewer) -> list[dict]:
    if not v.student:
        return []
    return [{"weekday": c["weekday"], "begins": c["begins"], "ends": c["ends"], "subject": c["subject"], "kind": c["kind"],
             "room": c["room"], "teacher": c["teacher"], "names": json.loads(c["names"]) if c["names"] else None}
            for c in rows(con, "SELECT * FROM schedule_classes WHERE user_id = ? ORDER BY weekday, begins", v.id)]


def save_schedule(con, uid: int, lessons: list) -> None:
    """Replaces the student's weekly classes (inside the caller's transaction)."""
    con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (uid,))
    con.executemany("""INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, code, kind, room, teacher, names)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [(uid, x.weekday, x.begins, x.ends, x.subject, x.code, x.kind, x.room, x.teacher,
                                                     json.dumps(x.names, ensure_ascii=False) if getattr(x, "names", None) else None) for x in lessons])


# ---------------------------------------------------------------- news

def post_shape(con, v: Viewer, p: sqlite3.Row) -> dict:
    return post_shapes(con, v, [p])[0]


def post_shapes(con, v: Viewer, found: list[sqlite3.Row]) -> list[dict]:
    """Posts (types.ts Post), counts and my marks read once for the whole list (News was 900 queries)."""
    if not found:
        return []
    ids = [p["id"] for p in found]
    q = _qs(ids)
    reactions = {(r[0], r[1]): r[2] for r in rows(con, f"SELECT post_id, kind, COUNT(*) FROM post_reactions WHERE post_id IN ({q}) GROUP BY post_id, kind", *ids)}
    mine = {(r[0], r[1]) for r in rows(con, f"SELECT post_id, kind FROM post_reactions WHERE user_id = ? AND post_id IN ({q})", v.id, *ids)}
    comments = dict(rows(con, f"SELECT post_id, COUNT(*) FROM comments WHERE post_id IN ({q}) AND deleted_at IS NULL GROUP BY post_id", *ids))
    read = {r[0] for r in rows(con, f"SELECT post_id FROM post_reads WHERE user_id = ? AND post_id IN ({q})", v.id, *ids)}
    rights, orgs = _rights(con, v), _by_id(con, "orgs", (p["org_id"] for p in found))
    files = _by_id(con, "files", [*(p["photo_file_id"] for p in found), *(o["logo_file_id"] for o in orgs.values())])
    return [{
        "id": p["id"], "org": org_ref(con, orgs[p["org_id"]], files), "audience": p["audience"], "title": p["title"], "body": p["body"],
        "tag": p["tag"], "photo": media_shape(files[p["photo_file_id"]]) if p["photo_file_id"] in files else None,
        "pinned": bool(p["pinned"]), "featured": bool(p["featured_until"] and p["featured_until"] > now()),
        "canDelete": v.role == "admin" or "posts" in rights.get(p["org_id"], ()),
        "canEdit": "posts" in rights.get(p["org_id"], ()), "editedAt": p["edited_at"],
        "canFeature": v.role in ("admin", "moderator") and p["audience"] == "public",
        "commentsOn": bool(p["comments_on"]),
        "comments": comments.get(p["id"], 0),
        "reactions": {k: reactions.get((p["id"], k), 0) for k in ("fire", "heart")}, "mine": {k: (p["id"], k) in mine for k in ("fire", "heart")},
        "read": p["id"] in read, "createdAt": p["created_at"],
    } for p in found]


def posts(con, v: Viewer, scope: str) -> list[dict]:
    sql, args = "SELECT * FROM posts WHERE hidden_at IS NULL AND org_id NOT IN (SELECT id FROM orgs WHERE status = 'hidden')", []
    if scope == "clubs":  # broadcasts reach club members only
        if not v.student or not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id):
            return []
        sql += " AND audience = 'clubs'"
    else:
        sql += " AND audience = 'public'"
        if scope == "subs":
            sql += " AND (org_id IN (SELECT org_id FROM subscriptions WHERE user_id = ?) OR org_id IN (SELECT org_id FROM org_members WHERE user_id = ?))"
            args += [v.id, v.id]
        elif scope.startswith("org:"):
            sql += " AND org_id = ?"; args.append(int(scope[4:]))
        elif scope != "all":
            raise ApiError("bad_input")
    return post_shapes(con, v, rows(con, sql + " ORDER BY pinned DESC, created_at DESC LIMIT 100", *args))


POST_TAGS = ("important", "recruiting", "results", "news")  # the composer's chips; the UI names them per language


def create_post(con, v: Viewer, oid: int, body: dict) -> dict:
    """A club's post (Head+, SPEC §4.10): public — its members and subscribers see it in News and on the club page; a
    broadcast org (DMP, KBTU App) may write to every member of every club instead (`clubs`), and the bot tells them.
    The photo is one of the caller's own uploads; one pinned post per club."""
    need_student(v)
    _may(con, v, oid, "posts")
    o = _org(con, oid)
    title, text = str(body.get("title") or "").strip(), str(body.get("body") or "").strip()
    tag, audience = body.get("tag"), body.get("audience") or "public"
    if not 2 <= len(title) <= 120 or len(text) > 2000 or (tag is not None and tag not in POST_TAGS) \
            or audience not in ("public", "clubs") or (audience == "clubs" and not o["can_broadcast"]):
        raise ApiError("bad_input")
    if tag == "important":  # it messages the members, so Vice+ only (owner, Oct 13)
        _may(con, v, oid, "team")
    pic = None
    if body.get("photoId") is not None:
        try:
            pic = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", int(body["photoId"]), v.id)
        except (TypeError, ValueError):
            pic = None
        if not pic:
            raise ApiError("bad_input")
    pinned = body.get("pinned") is True
    with tx(con):
        if pinned:
            con.execute("UPDATE posts SET pinned = 0 WHERE org_id = ?", (oid,))
        pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, tag, photo_file_id, pinned, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (oid, v.id, audience, title, text, tag, pic["id"] if pic else None, int(pinned), now())).lastrowid
        con.execute("INSERT INTO post_reads (post_id, user_id, read_at) VALUES (?, ?, ?)", (pid, v.id, now()))
        if audience == "clubs":  # every member of every club hears it (§7 broadcast), except the author
            for (uid,) in rows(con, "SELECT DISTINCT user_id FROM org_members WHERE user_id != ?", v.id):
                notify(con, uid, "broadcast", f"post:{pid}")
        elif tag == "important" and not one(con, """SELECT 1 FROM bot_outbox b JOIN posts p ON b.ref = 'post:' || p.id
                WHERE b.kind = 'important' AND p.org_id = ? AND p.created_at > ?""", oid, now() - 86400):
            # the club's members hear an "Important" post (not its followers), one a day per club at most: the only club post
            # the bot sends, so nobody mutes it (owner, Oct 13)
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND user_id != ?", oid, v.id):
                notify(con, uid, "important", f"post:{pid}")
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def update_post(con, v: Viewer, pid: int, body: dict) -> dict:
    """Edit a club's post or pin it (its Head+, §2): the title, text, label and photo as in the composer — then it
    reads "edited" — and the pin (one per club). Who sees it stays: a broadcast has already gone out."""
    need_student(v)
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid)
    if not p:
        raise ApiError("not_found")
    _may(con, v, p["org_id"], "posts")
    bad, sets = object(), {}
    text = lambda k: str(body.get(k) or "").strip()  # noqa: E731
    if "title" in body:
        sets["title"] = text("title") if 2 <= len(text("title")) <= 120 else bad
    if "body" in body:
        sets["body"] = text("body") if len(text("body")) <= 2000 else bad
    if "tag" in body:
        sets["tag"] = body["tag"] if body["tag"] is None or body["tag"] in POST_TAGS else bad
        if body["tag"] == "important" and p["tag"] != "important":  # Vice+, as when writing it; an edit messages nobody
            _may(con, v, p["org_id"], "team")
    if "photoId" in body and body["photoId"] != p["photo_file_id"]:  # the photo it has stays, whoever uploaded it
        ph = body["photoId"]
        own = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", ph, v.id) \
            if isinstance(ph, int) and not isinstance(ph, bool) else None
        sets["photo_file_id"] = None if ph is None else own["id"] if own else bad
    if "pinned" in body:
        sets["pinned"] = int(body["pinned"]) if isinstance(body["pinned"], bool) else bad
    if not body or any(x is bad for x in sets.values()):
        raise ApiError("bad_input")
    if sets.keys() - {"pinned"}:
        sets["edited_at"] = now()
    with tx(con):
        if sets.get("pinned"):
            con.execute("UPDATE posts SET pinned = 0 WHERE org_id = ? AND id != ?", (p["org_id"], pid))
        if sets:
            con.execute(f"UPDATE posts SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), pid))  # keys from above
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def hide_post(con, v: Viewer, pid: int) -> None:
    """Take a post down (its club's Head+ or the admin). Hidden, not erased: reactions and the audit trail stay."""
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid)
    if not p:
        raise ApiError("not_found")
    if v.role != "admin" and not can(con, v, p["org_id"], "posts"):
        raise ApiError("forbidden")
    con.execute("UPDATE posts SET hidden_at = ? WHERE id = ?", (now(), pid))
    con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'post_hide', ?, ?)", (v.id, f"post:{pid}", now()))


def read_posts(con, v: Viewer, ids: list) -> None:
    """Posts seen in News: their unread marks go, and the club tab's dot with them."""
    need_student(v)
    for pid in [i for i in ids if isinstance(i, int) and not isinstance(i, bool)][:100]:
        con.execute("INSERT OR IGNORE INTO post_reads (post_id, user_id, read_at) SELECT id, ?, ? FROM posts WHERE id = ?", (v.id, now(), pid))


def unread_broadcasts(con, v: Viewer) -> int:
    """Broadcasts of the last 30 days a club member hasn't opened yet (the dot on tab 2)."""
    if not v.student or not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id):
        return 0
    return one(con, """SELECT COUNT(*) FROM posts p WHERE p.audience = 'clubs' AND p.hidden_at IS NULL AND p.created_at > ?
        AND NOT EXISTS (SELECT 1 FROM post_reads r WHERE r.post_id = p.id AND r.user_id = ?)""", now() - 30 * 86400, v.id)[0]


def feature(con, v: Viewer, pid: object, days: object) -> dict:
    """A post for everyone on top of Events → List (moderators and the admin, §2) for 1–14 days; 0 takes it off. Public
    posts only: a broadcast to club members stays theirs. One at a time: featuring one ends the other."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid) if isinstance(pid, int) else None
    if not p or p["audience"] != "public" or not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 14:
        raise ApiError("bad_input")
    with tx(con):
        if days:
            con.execute("UPDATE posts SET featured_until = NULL WHERE featured_until IS NOT NULL AND id != ?", (pid,))
        con.execute("UPDATE posts SET featured_until = ? WHERE id = ?", (now() + days * 86400 if days else None, pid))
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'feature', ?, ?, ?)", (v.id, f"post:{pid}", json.dumps({"days": days}), now()))
    return post_shape(con, v, one(con, "SELECT * FROM posts WHERE id = ?", pid))


def react(con, v: Viewer, pid: int, kind: str, on: bool) -> dict:
    need_student(v)
    p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", pid)
    if not p or kind not in ("fire", "heart"):
        raise ApiError("not_found")
    if on:
        con.execute("INSERT OR IGNORE INTO post_reactions (post_id, user_id, kind) VALUES (?, ?, ?)", (pid, v.id, kind))
    else:
        con.execute("DELETE FROM post_reactions WHERE post_id = ? AND user_id = ? AND kind = ?", (pid, v.id, kind))
    return post_shape(con, v, p)


# ---------------------------------------------------------------- starting a club (§4.6)

CLUB_REAPPLY = 30 * 86400   # after a decline, a new application in 30 days
COVERS = 6                  # the cover palette (OrgLogo.svelte's COVERS)
LINK = re.compile(r"https://[A-Za-z0-9.-]+\.[a-z]{2,}(/[^\s]*)?")


def _club_app(con, a: sqlite3.Row, staff: bool) -> dict:
    out = {"id": a["id"], "name": a["name"], "short": a["short"], "description": a["description"], "emoji": a["emoji"], "cover": a["cover"],
           "link": a["link"], "why": a["why"], "status": a["status"], "reason": a["reason"], "orgId": a["org_id"], "createdAt": a["created_at"],
           "decidedAt": a["decided_at"], "reapplyAt": a["decided_at"] + CLUB_REAPPLY if a["status"] == "rejected" else None}
    if staff:  # who asks: what the admin needs to judge and to write to them first (§4.6)
        p = one(con, f"SELECT {DMP_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.id = ?", a["user_id"])
        out["applicant"] = {"person": person_ref(p), "fullName": f"{p['last_name'] or ''} {p['first_name'] or ''}".strip() or short_name(p),
                            "username": p["tg_username"], "course": p["course"], "school": p["school"]} if p else None
    return out


def my_club_application(con, v: Viewer) -> dict | None:
    need_student(v)
    a = one(con, "SELECT * FROM club_applications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", v.id)
    return _club_app(con, a, False) if a else None


def apply_club(con, v: Viewer, body: dict) -> dict:
    """A student asks to start a club (§4.6): it opens after the creator's check, said up front. One pending application
    per person; after a decline, a new one in 30 days. The admins hear about it from the bot."""
    need_student(v)
    name, short = str(body.get("name") or "").strip(), str(body.get("short") or "").strip().upper()
    about, why, link = str(body.get("description") or "").strip(), str(body.get("why") or "").strip(), str(body.get("link") or "").strip() or None
    emoji, cover = str(body.get("emoji") or ""), body.get("cover")
    if not (2 <= len(name) <= 60 and 1 <= len(short) <= 2 and 10 <= len(about) <= 600 and 20 <= len(why) <= 500
            and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and isinstance(cover, int) and not isinstance(cover, bool) and 0 <= cover < COVERS
            and (link is None or (len(link) <= 200 and LINK.fullmatch(link)))):
        raise ApiError("bad_input")
    with tx(con):  # a double tap must not make two pending applications
        last = one(con, "SELECT * FROM club_applications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", v.id)
        if last and last["status"] == "pending":
            raise ApiError("conflict", "pending")
        if last and last["status"] == "rejected" and last["decided_at"] + CLUB_REAPPLY > now():
            raise ApiError("rate_limited")
        if one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived'", name):
            raise ApiError("conflict", "taken")
        aid = con.execute("""INSERT INTO club_applications (user_id, name, short, description, emoji, cover, link, why, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (v.id, name, short, about, emoji, cover, link, why, now())).lastrowid
        for (uid,) in rows(con, "SELECT id FROM users WHERE role IN ('admin', 'moderator')"):
            notify(con, uid, "club_application", f"capp:{aid}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), False)


def club_applications(con, v: Viewer) -> list[dict]:
    """The check (moderators and the admin): pending first, then the last decisions."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    return [_club_app(con, a, True) for a in rows(con, """SELECT * FROM club_applications ORDER BY status = 'pending' DESC,
        COALESCE(decided_at, created_at) DESC LIMIT 40""")]


def decide_club_application(con, v: Viewer, aid: int, approve: bool, reason: object) -> dict:
    """Yes: the club exists at once as a student initiative and the applicant is its President. No: with a reason the
    applicant reads in the app (the bot's message is our template only, §9)."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    why = str(reason or "").strip()
    if not approve and not 3 <= len(why) <= 300:
        raise ApiError("bad_input")
    with tx(con):  # all or nothing: never a club without its President, never two clubs from one application
        a = one(con, "SELECT * FROM club_applications WHERE id = ? AND status = 'pending'", aid)
        if not a:
            raise ApiError("not_found")
        oid = None
        if approve:
            if one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived'", a["name"]):
                raise ApiError("conflict", "taken")
            oid = create_org(con, v.id, a["name"], a["short"], a["emoji"], False)
            con.execute("UPDATE orgs SET cover = ?, description = ?, links = ? WHERE id = ?", (a["cover"], a["description"], json.dumps([a["link"]] if a["link"] else []), oid))
            set_role(con, v.id, a["user_id"], oid, "president", "club_application")
        con.execute("UPDATE club_applications SET status = ?, reason = ?, org_id = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                    ("approved" if approve else "rejected", None if approve else why, oid, v.id, now(), aid))
        notify(con, a["user_id"], "club_application_decided", f"cad:{aid}:{'yes' if approve else 'no'}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), True)


# ---------------------------------------------------------------- the chats directory (§4.11)

TG_LINK = re.compile(r"https://t\.me/[A-Za-z0-9_+\-/]{3,80}")


def _chat(c: sqlite3.Row, opened: set[int]) -> dict:
    return {"id": c["id"], "title": c["title"], "kind": "forum" if c["forum"] else c["kind"], "url": c["url"], "members": c["members"],
            "photo": f"media/{c['photo']}.t.webp" if c["photo"] else None, "school": c["school"], "course": c["course"], "opened": c["id"] in opened}


def chats(con, v: Viewer) -> dict:
    """Curated Telegram chats (§4.11): "for you" are the ones aimed at my school and course plus those for everyone; a
    tick once I've opened one (an honest nudge, the bot checks nothing yet)."""
    st = one(con, "SELECT school, course FROM students WHERE user_id = ?", v.id) if v.student else None
    opened = {r[0] for r in rows(con, "SELECT chat_id FROM chat_opens WHERE user_id = ?", v.id)} if v.student else set()
    everything = [_chat(c, opened) for c in rows(con, "SELECT * FROM chats WHERE status = 'live' ORDER BY sort, course IS NULL DESC, course, title")]
    fits = lambda c: (c["school"] in (None, st["school"])) and (c["course"] in (None, st["course"]))  # noqa: E731
    aim = lambda c: (c["school"] is not None) * 2 + (c["course"] is not None)  # noqa: E731  — my school and course first, everyone's last
    mine = sorted((c for c in everything if st and fits(c)), key=lambda c: -aim(c))
    out = {"forYou": mine if st else [c for c in everything if c["school"] is None and c["course"] is None], "all": everything}
    if v.role in ("admin", "moderator"):  # the suggestions waiting for a look, newest first
        out["pending"] = [{**_chat(c, set()), "at": c["created_at"]} for c in rows(con, "SELECT * FROM chats WHERE status = 'pending' ORDER BY id DESC")]
    return out


def chat_opened(con, v: Viewer, cid: int) -> None:
    need_student(v)
    if not one(con, "SELECT 1 FROM chats WHERE id = ? AND status = 'live'", cid):
        raise ApiError("not_found")
    con.execute("INSERT OR IGNORE INTO chat_opens (user_id, chat_id, opened_at) VALUES (?, ?, ?)", (v.id, cid, now()))


def chat_input(v: Viewer, body: dict) -> str:
    """Checks a new chat before the app looks it up on t.me; returns its link."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    title, url, kind = str(body.get("title") or "").strip(), str(body.get("url") or "").strip(), body.get("kind")
    school = str(body.get("school") or "").strip() or None
    course = body.get("course")
    if not len(title) <= 80 or not TG_LINK.fullmatch(url) or kind not in ("channel", "group", "forum") or (school and len(school) > 40) \
            or not (course is None or (isinstance(course, int) and not isinstance(course, bool) and 1 <= course <= 6)):
        raise ApiError("bad_input")
    return url


def add_chat(con, v: Viewer, body: dict, peek: dict) -> dict:
    """A chat for the directory (moderators and the admin): a t.me link, a channel, a group or a topics group, for
    everyone or a school and/or a course. The title may be left empty: then the chat's own; peek (its t.me page) brings
    the avatar (a saved photo's path) and the members."""
    chat_input(v, body)
    title = str(body.get("title") or "").strip() or " ".join(str(peek.get("title") or "").split())[:80]
    if len(title) < 2:
        raise ApiError("bad_input")
    kind = body["kind"]
    cid = con.execute("""INSERT INTO chats (title, kind, forum, url, photo, members, school, course, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (title, "channel" if kind == "channel" else "group", int(kind == "forum"), body["url"].strip(),
                                                  peek.get("photo"), peek.get("members"), str(body.get("school") or "").strip() or None,
                                                  body.get("course"), v.id, now())).lastrowid
    return _chat(one(con, "SELECT * FROM chats WHERE id = ?", cid), set())


def chat_refreshed(con, cid: int, peek: dict) -> str | None:
    """The daily look at a chat's t.me page: a new avatar and members count; returns the old photo's path to remove."""
    c = one(con, "SELECT photo FROM chats WHERE id = ?", cid)
    if not c:
        return None
    photo = peek.get("photo") or c["photo"]
    con.execute("UPDATE chats SET photo = ?, members = COALESCE(?, members) WHERE id = ?", (photo, peek.get("members"), cid))
    return c["photo"] if c["photo"] and c["photo"] != photo else None


# A chat any student suggests (PLAN item 45, owner Oct 20: "as Telegram-native as possible"): picked in the bot's own
# chat picker or sent to it as @name or a t.me link; public chats only (an invite link would publish a closed group).
HANDLE = re.compile(r"(?:@|(?:https?://)?(?:t|telegram)\.me/(?:s/)?)([A-Za-z][A-Za-z0-9_]{3,31})/?", re.I)


def chat_handle(text: str) -> str | None:
    """A public chat's @name from "@name" or a t.me link, lowercased; None for anything else (an invite link too)."""
    m = HANDLE.fullmatch(text.strip())
    return m.group(1).lower() if m else None


def suggest_check(con, uid: int, name: str, tg_chat: int | None) -> None:
    """Before the server looks the chat up on t.me: 10 suggestions a day (owner, Oct 20: a club head with several chats
    mustn't hit it), nothing twice: "already in the catalog" or "already waiting" (owner, Oct 20)."""
    if c := one(con, "SELECT status FROM chats WHERE rtrim(lower(url), '/') = ? OR (tg_chat_id IS NOT NULL AND tg_chat_id = ?)", f"https://t.me/{name}", tg_chat):
        raise ApiError("conflict", c["status"])  # live | pending
    if one(con, "SELECT COUNT(*) FROM chats WHERE added_by = ? AND created_at > ?", uid, now() - 86400)[0] >= 10:
        raise ApiError("rate_limited")


def suggest_chat(con, uid: int, name: str, kind: str, tg_chat: int | None, peek: dict) -> str:
    """The suggestion, waiting; the admins and moderators hear of it once a day at most. Its title."""
    title = " ".join(str(peek.get("title") or "").split())[:80] or "@" + name
    with tx(con):
        suggest_check(con, uid, name, tg_chat)  # again inside the write: two taps at once
        con.execute("""INSERT INTO chats (title, kind, forum, url, tg_chat_id, photo, members, added_by, created_at, status)
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 'pending')""", (title, kind, f"https://t.me/{name}", tg_chat, peek.get("photo"), peek.get("members"), uid, now()))
        for (aid,) in rows(con, "SELECT id FROM users WHERE role IN ('admin', 'moderator')"):
            notify(con, aid, "chat_suggested", f"cs:{(now() + 5 * 3600) // 86400}")
    return title


def approve_chat(con, v: Viewer, cid: int) -> dict:
    """A suggested chat goes into the catalog; whoever suggested it hears so."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    with tx(con):
        c = one(con, "SELECT * FROM chats WHERE id = ? AND status = 'pending'", cid)
        if not c:
            raise ApiError("not_found")
        con.execute("UPDATE chats SET status = 'live' WHERE id = ?", (cid,))
        if c["added_by"]:
            notify(con, c["added_by"], "chat_approved", f"ca:{cid}")
    return _chat(one(con, "SELECT * FROM chats WHERE id = ?", cid), set())


def delete_chat(con, v: Viewer, cid: int) -> str | None:
    """A chat out of the catalog, or a suggestion declined; its avatar's path when nothing else shows it (to remove)."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    c = one(con, "SELECT photo FROM chats WHERE id = ?", cid)
    con.execute("DELETE FROM chats WHERE id = ?", (cid,))
    return c["photo"] if c and c["photo"] and photo_free(con, c["photo"]) else None


def photo_free(con, path: str) -> bool:
    """No chat and no file record shows this picture any more (pictures are named by their content: shared)."""
    return not one(con, "SELECT 1 FROM chats WHERE photo = ?", path) and not one(con, "SELECT 1 FROM files WHERE path = ?", path)


# ---------------------------------------------------------------- the clubs registry for DMP (§4.13)

QUIET_FOR = 60 * 86400  # "hasn't come in a while": no check-in at the club's events for this long
DMP_COLS = PERSON_COLS + ", u.tg_username, s.student_id, s.course, s.school, s.email, s.phone"


def _overseer_only(con, v: Viewer) -> None:
    if not overseer(con, v):
        raise ApiError("forbidden")


def _month(back: int = 0) -> tuple[int, int]:
    """A month in Almaty (UTC+5), `back` months before this one: its first second and the next month's."""
    t = time.gmtime(now() + 5 * 3600)
    y, m = divmod(t.tm_year * 12 + t.tm_mon - 1 - back, 12)
    start = lambda y, m: calendar.timegm((y, m + 1, 1, 0, 0, 0)) - 5 * 3600  # noqa: E731  (m is 0-based here)
    return start(y, m), start(y + (m == 11), (m + 1) % 12)


def _dmp_person(p: sqlite3.Row, role: str | None = None) -> dict:
    """What DMP sees of a club member (§3): full name, student ID, course, school; contacts only of Presidents and Vices."""
    lead = role in ("president", "vice")
    return {"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "studentId": p["student_id"],
            "course": p["course"], "school": p["school"], "username": p["tg_username"] if lead else None,
            "email": p["email"] if lead else None, "phone": p["phone"] if lead else None}


def registry_memos(con, v: Viewer) -> list[dict]:
    """The memos clubs marked sent in the last 7 days (owner, Oct 13: DMP sees them in the app): the club, its events, who
    said "sent" and when, newest first. One "Yes, sent" stamps its events at once, so one memo is (club, time). It's the
    club's word: the email itself is in DMP's mailbox, not here."""
    _overseer_only(con, v)
    out: dict[tuple[int, int], dict] = {}
    for e in rows(con, """SELECT id, org_id, title, starts_at, memo_sent_at, memo_sent_by FROM events
            WHERE memo_sent_at > ? ORDER BY memo_sent_at DESC, starts_at""", now() - 7 * 86400):
        m = out.get((e["org_id"], e["memo_sent_at"]))
        if not m:
            p = one(con, PERSON + " WHERE u.id = ?", e["memo_sent_by"]) if e["memo_sent_by"] else None
            m = out[(e["org_id"], e["memo_sent_at"])] = {"org": org_ref(con, _org(con, e["org_id"])), "sentAt": e["memo_sent_at"],
                                                          "by": short_name(p) if p else None, "events": []}
        m["events"].append({"id": e["id"], "title": e["title"], "startsAt": e["starts_at"]})
    return list(out.values())


def registry(con, v: Viewer, back: int = 0) -> list[dict]:
    """Every club with its live numbers (members; a month's events, registrations, who came; this month or up to a year
    back) and its President — instead of monthly reports, and instead of asking in chats who leads what."""
    _overseer_only(con, v)
    if not 0 <= back <= 12:
        raise ApiError("bad_input")
    m0, m1 = _month(back)
    out = []
    for o in rows(con, "SELECT * FROM orgs WHERE kind IN ('club', 'school', 'council') AND status != 'archived' ORDER BY official DESC, name"):
        pres = one(con, f"SELECT {DMP_COLS} FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id "
                        "WHERE m.org_id = ? AND m.role = 'president'", o["id"])
        st = one(con, """SELECT COUNT(DISTINCT e.id) AS events, COUNT(r.id) AS regs, COUNT(r.checked_in_at) AS came FROM events e
            LEFT JOIN registrations r ON r.event_id = e.id AND r.status = 'going'
            WHERE e.org_id = ? AND e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ?""", o["id"], m0, m1)
        out.append({"org": org_ref(con, o), "members": one(con, "SELECT COUNT(*) FROM org_members WHERE org_id = ?", o["id"])[0],
                    "president": _dmp_person(pres, "president") if pres else None,
                    "month": {"events": st["events"], "registrations": st["regs"], "came": st["came"]}})
    return out


def registry_roster(con, v: Viewer, oid: int) -> list[dict]:
    """A club's roster for DMP, leaders first; who hasn't come to the club's events in 60 days is marked (§4.13). A look at
    personal data: audit-logged (§9)."""
    _overseer_only(con, v)
    if not _org(con, oid):
        raise ApiError("not_found")
    con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'registry_roster', ?, ?)", (v.id, f"org:{oid}", now()))
    out = []
    for p in rows(con, f"""SELECT {DMP_COLS}, m.role, m.joined_at, (SELECT MAX(r.checked_in_at) FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE e.org_id = m.org_id AND r.user_id = u.id) AS seen FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
            WHERE m.org_id = ?""", oid):
        out.append({**_dmp_person(p, p["role"]), "role": p["role"], "joinedAt": p["joined_at"], "lastCame": p["seen"],
                    "quiet": (p["seen"] or p["joined_at"]) < now() - QUIET_FOR})
    return sorted(out, key=lambda x: (-RANK[x["role"]], x["fullName"]))


def registry_search(con, v: Viewer, q: str) -> list[dict]:
    """A club member by name or student ID → their clubs and roles (only people in some club: DMP sees club members)."""
    _overseer_only(con, v)
    q = str(q or "").strip()
    if len(q) < 2 or len(q) > 60:
        raise ApiError("bad_input")
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    found = rows(con, f"""SELECT DISTINCT {DMP_COLS} FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        WHERE s.student_id LIKE ? OR (s.last_name || ' ' || s.first_name) LIKE ? OR (s.first_name || ' ' || s.last_name) LIKE ? LIMIT 30""", like, like, like)
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'registry_search', 'registry', ?, ?)",
                (v.id, json.dumps({"q": q, "found": len(found)}), now()))  # a look at personal data (§9)
    out = []
    for p in found:
        clubs = rows(con, "SELECT o.*, m.role FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ? ORDER BY o.name", p["id"])
        top = max((c["role"] for c in clubs), key=lambda r: RANK[r], default=None)
        out.append({**_dmp_person(p, top), "clubs": [{"org": org_ref(con, c), "role": c["role"]} for c in clubs]})
    return out


def set_official(con, v: Viewer, oid: int, on: object) -> dict:
    """DMP marks a club official ✓ or takes it back (DMP Head+ and the admin, §2) — the growth path's last step (§4.6):
    a student initiative becomes an official club. Its President hears it from the bot (once); the audit log keeps who."""
    _overseer_only(con, v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND kind = 'club' AND status != 'archived'", oid)
    if not o:
        raise ApiError("not_found")
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    if bool(o["official"]) != on:
        with tx(con):
            con.execute("UPDATE orgs SET official = ? WHERE id = ?", (int(on), oid))
            con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'official', ?, ?, ?)", (v.id, f"org:{oid}", json.dumps({"on": on}), now()))
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", oid) if on else []:
                notify(con, uid, "club_official", f"off:{oid}")
    return org_ref(con, _org(con, oid))


def registry_export(con, v: Viewer) -> list[sqlite3.Row]:
    """Every roster at once for the CSV the bot sends (contacts of Presidents and Vices only, as on screen). Personal
    data leaving the app: every export goes to the audit log (§2)."""
    _overseer_only(con, v)
    out = rows(con, f"""SELECT o.name AS club, m.role, m.joined_at, {DMP_COLS} FROM org_members m JOIN orgs o ON o.id = m.org_id
        JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        WHERE o.kind IN ('club', 'school', 'council') AND o.status != 'archived' ORDER BY o.name, m.role, s.last_name""")
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'registry_export', 'registry', ?, ?)",
                (v.id, json.dumps({"rows": len(out)}), now()))
    return out


# ---------------------------------------------------------------- comments and reports (§4.10)

COMMENTS_A_MINUTE, REPORTS_A_DAY = 10, 20


def _thread(con, v: Viewer, kind: str, tid: int) -> sqlite3.Row:
    """The post or event a comment thread hangs under, if the viewer can see it."""
    if kind == "post":
        p = one(con, "SELECT * FROM posts WHERE id = ? AND hidden_at IS NULL", tid)
        if not p or (p["audience"] == "clubs" and not one(con, "SELECT 1 FROM org_members WHERE user_id = ?", v.id)):
            raise ApiError("not_found")
        return p
    if kind == "event":
        return _event(con, v, tid)
    raise ApiError("not_found")


def _moderates(con, v: Viewer, org: int) -> bool:
    return v.role == "admin" or can(con, v, org, "posts")


def comments(con, v: Viewer, kind: str, tid: int) -> dict:
    """Comments under a post or an event: questions to the organizer ("where's the entrance?"). Students read and write
    (short names, §3); the club's Head+ answer as the club, take any down and turn the thread off; authors take theirs."""
    need_student(v)
    t = _thread(con, v, kind, tid)
    head, org = _moderates(con, v, t["org_id"]), org_ref(con, _org(con, t["org_id"]))
    lead = can(con, v, t["org_id"], "posts")
    if lead and kind == "event":  # read: Studio's "questions waiting" go, for me
        con.execute("INSERT OR REPLACE INTO comment_reads (event_id, user_id, last_id) SELECT ?, ?, COALESCE(MAX(id), 0) FROM comments WHERE event_id = ?",
                    (tid, v.id, tid))
    col = "post_id" if kind == "post" else "event_id"
    found = rows(con, f"""SELECT c.id AS cid, c.user_id, c.as_org, c.body, c.created_at, c.reply_to, {PERSON_COLS} FROM comments c
                 JOIN users u ON u.id = c.user_id LEFT JOIN students s ON s.user_id = u.id
                 WHERE c.{col} = ? AND c.deleted_at IS NULL ORDER BY c.created_at, c.id LIMIT 300""", tid)
    by_id = {c["cid"]: c for c in found}  # a reply quotes the comment it answers while that is still up
    quote = lambda q: {"id": q["cid"], "name": org["name"] if q["as_org"] else person_ref(q)["name"], "body": q["body"][:140]} if q else None  # noqa: E731
    items = [{"id": c["cid"], "person": None if c["as_org"] else person_ref(c), "org": org if c["as_org"] else None, "body": c["body"],
              "at": c["created_at"], "mine": c["user_id"] == v.id, "canDelete": head or c["user_id"] == v.id, "replyTo": quote(by_id.get(c["reply_to"]))}
             for c in found]
    return {"items": items, "on": bool(t["comments_on"]), "canModerate": head, "asOrg": org if lead else None}


def add_comment(con, v: Viewer, kind: str, tid: int, body: object, as_org: object, reply_to: object = None) -> dict:
    need_student(v)
    t = _thread(con, v, kind, tid)
    text = str(body or "").strip()
    col = "post_id" if kind == "post" else "event_id"
    to = None
    if reply_to is not None:  # a reply: to a comment still up in this thread
        to = one(con, f"SELECT id, user_id FROM comments WHERE id = ? AND {col} = ? AND deleted_at IS NULL", reply_to, tid) if isinstance(reply_to, int) else None
        if not to:
            raise ApiError("bad_input")
    if not 1 <= len(text) <= 500:
        raise ApiError("bad_input")
    if not t["comments_on"]:
        raise ApiError("closed")
    lead = can(con, v, t["org_id"], "posts")
    if as_org and not lead:
        raise ApiError("forbidden")
    if one(con, "SELECT COUNT(*) FROM comments WHERE user_id = ? AND created_at > ?", v.id, now() - 60)[0] >= COMMENTS_A_MINUTE:
        raise ApiError("rate_limited")
    askers: list[tuple[int]] = []
    if kind == "event":  # the bot (owner, Oct 5): a question pings the club's Head+ (hourly at most); an answer (the club's
        # Head+ write, as the club or as themselves) pings the askers
        if lead:
            askers = [(u,) for u in sorted({r["user_id"] for r in _asking(con, tid)})]
        else:
            heads = rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice', 'head') AND user_id != ?", t["org_id"], v.id)
    cid = con.execute(f"INSERT INTO comments ({col}, user_id, as_org, body, created_at, reply_to) VALUES (?, ?, ?, ?, ?, ?)",
                      (tid, v.id, int(bool(as_org)), text, now(), to["id"] if to else None)).lastrowid
    if kind == "event":
        for (uid,) in (askers if lead else heads):
            notify(con, uid, "comment_answer", f"ca:{tid}:{cid}") if lead else notify(con, uid, "comment_question", f"cq:{tid}:{now() // 3600}")
    if to and to["user_id"] != v.id and (to["user_id"],) not in askers:  # its author hears it, replies in a thread merged by the hour
        notify(con, to["user_id"], "comment_reply", f"cr:{kind}:{tid}:{now() // 3600}")
    return comments(con, v, kind, tid)


def delete_comment(con, v: Viewer, cid: int) -> None:
    """Taken down, not erased (the reports keep pointing at something)."""
    c = one(con, "SELECT * FROM comments WHERE id = ? AND deleted_at IS NULL", cid)
    if not c:
        raise ApiError("not_found")
    org = one(con, "SELECT org_id FROM posts WHERE id = ?", c["post_id"]) if c["post_id"] else one(con, "SELECT org_id FROM events WHERE id = ?", c["event_id"])
    if c["user_id"] != v.id and not _moderates(con, v, org["org_id"]):
        raise ApiError("forbidden")
    con.execute("UPDATE comments SET deleted_at = ?, deleted_by = ? WHERE id = ?", (now(), v.id, cid))


def set_comments_on(con, v: Viewer, kind: str, tid: int, on: object) -> dict:
    t = _thread(con, v, kind, tid)
    if not _moderates(con, v, t["org_id"]):
        raise ApiError("forbidden")
    con.execute(f"UPDATE {'posts' if kind == 'post' else 'events'} SET comments_on = ? WHERE id = ?", (int(bool(on)), tid))
    return comments(con, v, kind, tid)


def report(con, v: Viewer, target: object, tid: object, reason: object) -> None:
    """"Report" → the Admin panel's queue. Once per person and thing (a repeat is quiet), 20 a day."""
    need_student(v)
    if target not in ("post", "comment", "event", "user", "photo") or reason not in ("spam", "insult", "danger", "other") or not isinstance(tid, int):
        raise ApiError("bad_input")
    if target == "photo":  # an album photo (its file id): hidden for me at once, for everyone once two people reported it
        p = one(con, "SELECT event_id, added_by FROM event_photos WHERE file_id = ?", tid)
        if not p or p["added_by"] == v.id:
            raise ApiError("not_found")
        _thread(con, v, "event", p["event_id"])
    elif target == "user":  # a profile: its nick, own photo and "about me" (owner, Oct 5)
        if tid == v.id or not one(con, "SELECT 1 FROM students WHERE user_id = ?", tid):
            raise ApiError("not_found")
    elif target == "comment":
        c = one(con, "SELECT post_id, event_id FROM comments WHERE id = ? AND deleted_at IS NULL", tid)
        if not c:
            raise ApiError("not_found")
        _thread(con, v, "post" if c["post_id"] else "event", c["post_id"] or c["event_id"])
    else:
        _thread(con, v, target, tid)
    if one(con, "SELECT COUNT(*) FROM reports WHERE reporter_id = ? AND created_at > ?", v.id, now() - 86400)[0] >= REPORTS_A_DAY:
        raise ApiError("rate_limited")
    con.execute("INSERT OR IGNORE INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, ?, ?, ?, ?)", (v.id, target, tid, reason, now()))


def report_queue(con, v: Viewer) -> list[dict]:
    """The admin's queue: one row per reported thing still up, the reasons counted, oldest first."""
    _admin(v)
    out = []
    for r in rows(con, """SELECT target, target_id, MIN(created_at) AS first, COUNT(*) AS n, GROUP_CONCAT(reason) AS reasons FROM reports
            WHERE status = 'open' GROUP BY target, target_id ORDER BY first"""):
        if r["target"] == "comment":
            c = one(con, "SELECT body, post_id, event_id FROM comments WHERE id = ? AND deleted_at IS NULL", r["target_id"])
            text, where = (c["body"], ("post", c["post_id"]) if c["post_id"] else ("event", c["event_id"])) if c else (None, None)
        elif r["target"] == "user":  # what the person wrote about themselves: the nick and "about me" (the photo shows on the card)
            p = one(con, PERSON + " WHERE u.id = ?", r["target_id"])
            text, where = (" · ".join(x for x in (shown_name(p), one(con, "SELECT bio FROM users WHERE id = ?", p["id"])[0]) if x),
                           ("person", r["target_id"])) if p else (None, None)
        elif r["target"] == "photo":  # the picture itself is the thing to look at
            p = one(con, "SELECT p.event_id, f.path FROM event_photos p JOIN files f ON f.id = p.file_id WHERE p.file_id = ?", r["target_id"])
            text, where = (f"media/{p['path']}.t.webp", ("event", p["event_id"])) if p else (None, None)
        elif r["target"] == "post":
            p = one(con, "SELECT title FROM posts WHERE id = ? AND hidden_at IS NULL", r["target_id"])
            text, where = (p["title"], ("post", r["target_id"])) if p else (None, None)
        else:
            e = one(con, "SELECT title FROM events WHERE id = ? AND hidden_at IS NULL", r["target_id"])
            text, where = (e["title"], ("event", r["target_id"])) if e else (None, None)
        if text is None:  # already gone: nothing to decide
            con.execute("UPDATE reports SET status = 'actioned', resolved_at = ? WHERE target = ? AND target_id = ? AND status = 'open'", (now(), r["target"], r["target_id"]))
            continue
        reasons = r["reasons"].split(",")
        out.append({"target": r["target"], "id": r["target_id"], "text": text, "where": {"kind": where[0], "id": where[1]}, "count": r["n"],
                    "reasons": {k: reasons.count(k) for k in dict.fromkeys(reasons)}, "at": r["first"]})
    return out


def resolve_report(con, v: Viewer, target: str, tid: int, remove: bool) -> list[str]:
    """Take the thing down (a comment deleted, a post or an event hidden, a profile's own words and photo gone) or leave
    it; either way its reports close. Returns a removed photo's files to delete from disk."""
    _admin(v)
    photos: list[str] = []
    if remove:
        if target == "comment":
            con.execute("UPDATE comments SET deleted_at = ?, deleted_by = ? WHERE id = ? AND deleted_at IS NULL", (now(), v.id, tid))
        elif target in ("post", "event"):
            con.execute(f"UPDATE {target}s SET hidden_at = ? WHERE id = ? AND hidden_at IS NULL", (now(), tid))
        elif target == "photo":  # out of the album (its file stays for other rows naming the same picture; app.py removes it if none)
            con.execute("DELETE FROM event_photos WHERE file_id = ?", (tid,))
            photos = _drop_photo(con, tid)
        elif target == "user":  # the nick, the own photo and "about me" go; the Telegram photo is back.
            # ponytail: not in "taken down" (no undo): nothing to restore, they can set them again
            photo = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", tid)
            con.execute("UPDATE users SET nick = NULL, avatar_tg = 1, avatar_file_id = NULL, bio = '' WHERE id = ?", (tid,))
            photos = _drop_photo(con, photo[0] if photo else None)
        else:
            raise ApiError("bad_input")
    con.execute("UPDATE reports SET status = ?, resolved_by = ?, resolved_at = ? WHERE target = ? AND target_id = ? AND status = 'open'",
                ("actioned" if remove else "dismissed", v.id, now(), target, tid))
    con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, ?, ?, ?)", (v.id, "report_remove" if remove else "report_keep", f"{target}:{tid}", now()))
    return photos


def taken_down(con, v: Viewer) -> list[dict]:
    """What the admin took down from the report queue in the last 30 days and is still down, newest first: a wrong call
    can be undone (§2 "hide / restore"). Things their own authors or clubs removed aren't here — that was their choice."""
    _admin(v)
    out = []
    for a in rows(con, """SELECT target, MAX(at) AS at FROM audit_log a WHERE action = 'report_remove' AND at > ?
            AND NOT EXISTS (SELECT 1 FROM audit_log r WHERE r.action = 'restore' AND r.target = a.target AND r.at >= a.at)
            GROUP BY target ORDER BY MAX(at) DESC LIMIT 50""", now() - 30 * 86400):  # undone ones stay undone
        kind, _, ref = a["target"].partition(":")
        tid = int(ref) if ref.isdigit() else 0
        if kind == "comment":
            x = one(con, "SELECT body AS text FROM comments WHERE id = ? AND deleted_at IS NOT NULL", tid)
        elif kind in ("post", "event"):
            x = one(con, f"SELECT title AS text FROM {kind}s WHERE id = ? AND hidden_at IS NOT NULL", tid)  # kind from the list above
        else:
            x = None
        if x:
            out.append({"target": kind, "id": tid, "text": x["text"], "at": a["at"]})
    return out


def restore(con, v: Viewer, target: str, tid: int) -> None:
    """Undo a take-down: the comment, post or event is back as it was; audited."""
    _admin(v)
    if target == "comment":
        n = con.execute("UPDATE comments SET deleted_at = NULL, deleted_by = NULL WHERE id = ? AND deleted_at IS NOT NULL", (tid,)).rowcount
    elif target in ("post", "event"):
        n = con.execute(f"UPDATE {target}s SET hidden_at = NULL WHERE id = ? AND hidden_at IS NOT NULL", (tid,)).rowcount
    else:
        raise ApiError("bad_input")
    if not n:
        raise ApiError("not_found")
    con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'restore', ?, ?)", (v.id, f"{target}:{tid}", now()))


# ---------------------------------------------------------------- people and awards

def attended(con, uid: int) -> list[int]:
    """Check-in times at published events, oldest first (achievements are computed from these, §4.11)."""
    return [r[0] for r in rows(con, """SELECT r.checked_in_at FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.status = 'published' ORDER BY r.checked_in_at""", uid)]


def _season_start(ts: int) -> int:
    t = time.gmtime(ts + 5 * 3600)
    y, m = t.tm_year, max((x for x in SEASON_MONTHS if x <= t.tm_mon), default=None)
    if m is None:
        y, m = y - 1, SEASON_MONTHS[-1]
    return int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, 0))) - time.timezone - 5 * 3600


def _week(t: int) -> int:
    return (t + 5 * 3600 + 3 * 86400) // (7 * 86400)  # Almaty weeks, from Monday


def _streak(mine: set[int], busy: set[int], this_week: int) -> tuple[int, int]:
    """Weeks in a row with a check-in (§4.11): the longest run (the medal's: an earned level never goes away) and the
    current one. A week without a public event neither breaks nor adds (owner, Oct 7: nothing to go to is no reason to
    lose it), and this week breaks nothing until it's over."""
    # ponytail: holidays and the session pause it only when they have no events; read the academic calendar if one bites
    best = run = 0
    for w in range(min(mine, default=this_week + 1), this_week + 1):
        if w in mine:
            run += 1
        elif w in busy and w < this_week:
            run = 0
        best = max(best, run)
    return best, run


ACHIEVEMENTS = [  # code, emoji, needs, secret (§4.11)
    ("regular", "trophy_3d", (5, 15, 30, 50), False), ("streak", "fire_3d", (2, 4, 8, 16), False),
    ("first_in", "high_voltage_3d", (1, 3, 10), False), ("soul", "raising_hands_3d_default", (3, 10, 25, 50), False),
    ("team", "cloud_with_lightning_and_rain_3d", (3, 10, 25, 50), False),  # "Teambuilding thunder": a club's own events, meetings too (owner, Oct 6)
    ("season", "sparkles_3d", (3, 7, 12, 20), False),
    ("first50", "n500", (1,), False),  # not an emoji: the medal strikes the number (web ui/Medal, owner Oct 13)
    ("creator_laugh", "face_with_tears_of_joy_3d", (1,), True), ("creator_found", "waving_hand_3d_default", (1,), True),
    ("bugs", "lady_beetle_3d", (1, 5, 10, 25), False),  # a bug, literally (owner, Oct 13: no emoji twice)
]


def _counts(con, uid: int) -> dict[str, int]:
    times = attended(con, uid)
    grants = dict(rows(con, "SELECT code, COUNT(*) FROM achievement_grants WHERE user_id = ? GROUP BY code", uid))
    first_in = one(con, """SELECT COUNT(*) FROM registrations r WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND r.checked_in_at =
        (SELECT MIN(x.checked_in_at) FROM registrations x WHERE x.event_id = r.event_id)""", uid)[0]
    soul = one(con, "SELECT COUNT(*) FROM registrations WHERE invited_by = ? AND checked_in_at IS NOT NULL", uid)[0]
    team = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.status = 'published' AND e.visibility = 'members'""", uid)[0]
    seasons = [_season_start(t) for t in times]  # the best semester counts: every semester is a new chance
    busy = {_week(r[0]) for r in rows(con, "SELECT starts_at FROM events WHERE status = 'published' AND visibility = 'public'")}
    streak, streak_now = _streak({_week(t) for t in times}, busy, _week(now()))
    return {"regular": len(times), "streak": streak, "streak_now": streak_now, "first_in": first_in, "soul": soul, "team": team,
            "season": max(map(seasons.count, set(seasons)), default=0), "first50": grants.get("first50", 0),
            "creator_laugh": grants.get("creator_laugh", 0), "creator_found": grants.get("creator_found", 0), "bugs": grants.get("bugs", 0)}


def _levels(con, uid: int) -> dict[str, int]:
    c = _counts(con, uid)
    return {code: sum(1 for n in needs if c[code] >= n) for code, _, needs, _ in ACHIEVEMENTS}


def _came(con, e: sqlite3.Row, uid: int, write) -> None:
    """A check-in and what follows it: the rating ask, and every achievement level it brings — to the one who came and to
    the friend who invited them ("Life of the party"): the date it was reached, the bot's message, the unlock moment."""
    inviter = one(con, "SELECT invited_by FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)["invited_by"]
    people = [p for p in dict.fromkeys((uid, inviter)) if p]
    before = {p: _levels(con, p) for p in people}
    write()
    _ask_rating(con, uid, e)
    for p in people:
        _celebrate(con, p, before[p])


def _celebrate(con, uid: int, before: dict[str, int]) -> None:
    """Every level above `before` gets its date, the bot's card (once) and the app's unlock moment."""
    for code, level in _levels(con, uid).items():
        if level > before[code]:
            con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, ?, ?, ?)
                ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at""", (uid, code, level, now()))
            notify(con, uid, "achievement", f"ach:{code}:{level}")


def sync_levels(con) -> None:
    """Levels already reached, recorded once the achievements change (a new one, a new level): counts never stop at the
    top, so a level added later is reached by whoever already did it (owner, Oct 6). At start, under the migration
    lock (db.init), only when the list differs from the last run. No bot message: the app's unlock moment shows them."""
    mark = json.dumps([[code, needs] for code, _, needs, _ in ACHIEVEMENTS])
    last = one(con, "SELECT value FROM meta WHERE key = 'achievements'")
    if last and last[0] == mark:
        return
    with tx(con):
        for (uid,) in rows(con, "SELECT user_id FROM students"):
            have = dict(rows(con, "SELECT code, level FROM achievement_levels WHERE user_id = ?", uid))
            for code, level in _levels(con, uid).items():
                if level > have.get(code, 0):
                    con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, ?, ?, ?)
                        ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at""", (uid, code, level, now()))
        con.execute("INSERT INTO meta (key, value) VALUES ('achievements', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (mark,))


GRANTABLE = ("bugs", "creator_laugh", "creator_found")  # the manual ones (§4.11); "First 500" is given at verification


def grant(con, v: Viewer, uid: object, code: object) -> dict:
    """The admin gives a manual achievement: "Bug hunter" one more time, or a secret one (once). Celebrated like any
    new level; written to the audit log."""
    _admin(v)
    if code not in GRANTABLE or not isinstance(uid, int) or isinstance(uid, bool) or not one(con, "SELECT 1 FROM students WHERE user_id = ?", uid):
        raise ApiError("bad_input")
    with tx(con):
        _grant(con, v.id, uid, str(code))
    return person(con, v, uid)


def _grant(con, by: int, uid: int, code: str) -> int:
    if code != "bugs" and one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = ?", uid, code):
        raise ApiError("conflict")
    before = _levels(con, uid)
    gid = con.execute("INSERT INTO achievement_grants (user_id, code, granted_by, created_at) VALUES (?, ?, ?, ?)", (uid, code, by, now())).lastrowid
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'grant', ?, ?, ?)", (by, f"user:{uid}", json.dumps({"code": code}), now()))
    _celebrate(con, uid, before)
    return gid


def grant_scan(con, v: Viewer, raw: object, code: object) -> dict:
    """The owner's batch scanner on the Awards page (PLAN "Creator awards"): a badge QR is one grant of `code`; the app
    keeps the camera open for the next one and offers a 5-second undo."""
    _admin(v)
    b = PROFILE_QR.search(str(raw or ""))
    if code not in GRANTABLE:
        raise ApiError("bad_input")
    if not b or not one(con, "SELECT 1 FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ? AND u.qr_code = ?", int(b[1]), b[2]):
        raise ApiError("not_found")
    with tx(con):
        gid = _grant(con, v.id, int(b[1]), str(code))
    return {"id": gid, "code": code, "at": now(), "person": person_ref(one(con, PERSON + " WHERE u.id = ?", int(b[1])))}


GRANT_LINK_TTL = 7 * 86400


def grant_link(con, v: Viewer, code: object) -> str:
    """The admin's one-time award link (owner, Oct 13: "Bug hunter" is earned in a chat, so it goes as a link there;
    the face-to-face ones stay on the badge QR): one student, once, within 7 days."""
    _admin(v)
    if code not in GRANTABLE:
        raise ApiError("bad_input")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (token, code, v.id, now(), now() + GRANT_LINK_TTL))
    return token


def use_grant_link(con, v: Viewer, token: str) -> dict:
    """A student opened an award link: theirs, celebrated like any new level. A used or old link is 'closed'."""
    need_student(v)
    with tx(con):
        r = one(con, "SELECT * FROM grant_links WHERE token = ? AND used_by IS NULL AND expires_at > ?", token, now())
        if not r:
            raise ApiError("closed")
        _grant(con, r["created_by"], v.id, r["code"])
        con.execute("UPDATE grant_links SET used_by = ?, used_at = ? WHERE token = ?", (v.id, now(), token))
    return {"code": r["code"]}


def ungrant(con, v: Viewer, gid: int) -> None:
    """Undo a grant of mine within a minute (the scanner's undo): the level goes back, its unsent bot card goes."""
    _admin(v)
    g = one(con, "SELECT * FROM achievement_grants WHERE id = ? AND granted_by = ? AND created_at >= ?", gid, v.id, now() - 60)
    if not g:
        raise ApiError("not_found")
    _drop_grant(con, v, g)


def take_back(con, v: Viewer, uid: object, code: object) -> dict:
    """The admin takes back a manual award from a profile at any time (owner, Oct 13: Bug hunter given to a friend
    by mistake while testing, ten times over): every grant of it, by a person or a link; never the sign-in's "First 500"."""
    _admin(v)
    if code not in GRANTABLE or not isinstance(uid, int) or isinstance(uid, bool):
        raise ApiError("bad_input")
    gs = rows(con, "SELECT * FROM achievement_grants WHERE user_id = ? AND code = ? ORDER BY id DESC", uid, code)
    if not gs:
        raise ApiError("not_found")
    with tx(con):
        for g in gs:
            _drop_grant(con, v, g)
    return person(con, v, uid)


def _drop_grant(con, v: Viewer, g) -> None:
    with tx(con):
        con.execute("DELETE FROM achievement_grants WHERE id = ?", (g["id"],))
        level = _levels(con, g["user_id"])[g["code"]]
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'achievement' AND ref LIKE ? AND sent_at IS NULL AND CAST(substr(ref, ?) AS INTEGER) > ?",
                    (g["user_id"], f"ach:{g['code']}:%", len(f"ach:{g['code']}:") + 1, level))
        if level:
            con.execute("UPDATE achievement_levels SET level = ? WHERE user_id = ? AND code = ? AND level > ?", (level, g["user_id"], g["code"], level))
        else:
            con.execute("DELETE FROM achievement_levels WHERE user_id = ? AND code = ?", (g["user_id"], g["code"]))
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'ungrant', ?, ?, ?)",
                    (v.id, f"user:{g['user_id']}", json.dumps({"code": g["code"]}), now()))


def my_grants(con, v: Viewer) -> list[dict]:
    """"You gave: N" on the Awards page: the owner's grants, newest first."""
    _admin(v)
    return [{"id": g["gid"], "code": g["code"], "at": g["created_at"], "person": person_ref(g)}
            for g in rows(con, f"""SELECT g.id AS gid, g.code, g.created_at, {PERSON_COLS} FROM achievement_grants g JOIN users u ON u.id = g.user_id
                LEFT JOIN students s ON s.user_id = u.id WHERE g.granted_by = ? AND g.code IN ({','.join('?' * len(GRANTABLE))})
                ORDER BY g.created_at DESC, g.id DESC LIMIT 300""", v.id, *GRANTABLE)]


FIRST_N = 500  # cards 1-500; the code stays "first50": it was 50 until launch day (Oct 5), a pilot club alone could have taken them all


def card_no(con, uid: int) -> None:
    """A student's number on the card (§4.4): the order of first KBTU sign-in, kept for good, so a deleted account never
    frees it. The Creator's card shows 00000 and takes no number, staff none at all: the numbers count students."""
    # the last number given lives in meta: MAX + 1 alone gave the last card's number again once its account was purged
    n = con.execute("""UPDATE users SET card_no = 1 + MAX((SELECT COALESCE(MAX(card_no), 0) FROM users),
            (SELECT COALESCE(MAX(CAST(value AS INTEGER)), 0) FROM meta WHERE key = 'card_last'))
        WHERE id = ? AND card_no IS NULL AND is_founder = 0
        AND id NOT IN (SELECT user_id FROM students WHERE consent_version = 'staff') RETURNING card_no""", (uid,)).fetchone()
    if n:
        con.execute("""INSERT INTO meta (key, value) VALUES ('card_last', ?)
            ON CONFLICT (key) DO UPDATE SET value = MAX(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER))""", (str(n[0]),))


def first_fifty(con, uid: int) -> None:
    """At a KBTU sign-in: the card number, then "First 500" (§4.11), the cards 00001-00500 (and the Creator's 00000).
    Kept as a grant; celebrated like any new level."""
    card_no(con, uid)
    u = one(con, "SELECT card_no, is_founder FROM users WHERE id = ?", uid)
    if not (u["is_founder"] or (u["card_no"] or FIRST_N + 1) <= FIRST_N) or one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'first50'", uid):
        return
    con.execute("INSERT INTO achievement_grants (user_id, code, note, created_at) VALUES (?, 'first50', 'verification', ?)", (uid, now()))
    con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (NULL, 'first50', ?, ?)", (f"user:{uid}", now()))
    con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'first50', 1, ?)
        ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1), reached_at = excluded.reached_at""", (uid, now()))
    notify(con, uid, "achievement", "ach:first50:1")


def unlocked(con, v: Viewer) -> list[dict]:
    """Levels reached that the app hasn't celebrated yet (the unlock moment, §4.11), oldest first."""
    if not v.student:
        return []
    return [{"code": r["code"], "level": r["level"]} for r in
            rows(con, "SELECT code, level FROM achievement_levels WHERE user_id = ? AND level > seen ORDER BY reached_at", v.id)]


def seen_unlock(con, v: Viewer, code: object, level: object) -> None:
    need_student(v)
    if not isinstance(code, str) or not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 10:
        raise ApiError("bad_input")
    con.execute("UPDATE achievement_levels SET seen = MAX(seen, ?) WHERE user_id = ? AND code = ?", (level, v.id, code))


def achievements(con, uid: int) -> list[dict]:
    """Mine, each level with its rarity: the share of students who have reached it. Rarity comes from the levels everyone
    reached (achievement_levels: an earned level stays), one query; counting every student's check-ins for every
    profile view was thousands of queries once a few hundred students had signed in (load test, Oct 7)."""
    mine = _counts(con, uid)
    # out of students only: staff take no card and no "First 500", counted they made it "95%" (Oct 14)
    total = max(1, one(con, "SELECT COUNT(*) FROM students WHERE consent_version != 'staff'")[0])
    at_level = {(r[0], r[1]): r[2] for r in rows(con, """SELECT l.code, l.level, COUNT(*) FROM achievement_levels l
        JOIN students s ON s.user_id = l.user_id WHERE s.consent_version != 'staff' GROUP BY l.code, l.level""")}
    out = []
    reached = {r["code"]: r for r in rows(con, "SELECT code, level, reached_at FROM achievement_levels WHERE user_id = ?", uid)}
    for code, emoji, needs, secret in ACHIEVEMENTS:
        have = lambda level: sum(n for (c, lv), n in at_level.items() if c == code and lv >= level) / total  # noqa: E731
        out.append({"code": code, "emoji": emoji, "secret": secret, "count": mine[code], "level": sum(1 for n in needs if mine[code] >= n),
                    "levels": [{"need": n, "reached": mine[code] >= n, "rarity": have(i + 1)} for i, n in enumerate(needs)], "rarity": have(1),
                    "at": reached[code]["reached_at"] if code in reached else None,
                    **({"now": mine["streak_now"]} if code == "streak" else {})})
    return out


def person(con, v: Viewer, uid: int) -> dict:
    need_student(v)
    p = one(con, PERSON + " WHERE u.id = ?", uid)
    s = one(con, "SELECT * FROM students WHERE user_id = ?", uid)
    if not p or not s:
        raise ApiError("not_found")
    u = one(con, "SELECT bio, showcase, show_going, card_no, is_founder, tg_username FROM users WHERE id = ?", uid)
    link = one(con, "SELECT created_at FROM friendships WHERE a = ? AND b = ?", min(uid, v.id), max(uid, v.id))
    # their @username, to their own club's team only (§3: the team sees it in its roster anyway): "Message on Telegram"
    team = uid != v.id and one(con, "SELECT 1 FROM org_members a JOIN org_members b ON b.org_id = a.org_id WHERE a.user_id = ? AND b.user_id = ?",
                               v.id, uid) is not None
    state = "none" if uid == v.id else friendship(con, v.id, uid)
    ach = achievements(con, uid)
    going = []
    if link and u["show_going"]:  # only events I may see myself: a friend's team-only meeting stays theirs
        roles = _roles(con, v)
        going = cards(con, v, [e for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ? AND r.status = 'going' AND e.status = 'published' AND e.starts_at > ? ORDER BY e.starts_at""", uid, now())
            if _visible(con, v, e, roles)])
    badges = [{"eventId": e["id"], "title": e["badge_name"], "org": org_ref(con, _org(con, e["org_id"])), "emoji": e["emoji"] or "party_popper_3d",
               "color": e["tint"] or "#3B6BFF", "at": e["starts_at"]}
              for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
                  WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.badge_name IS NOT NULL ORDER BY e.starts_at DESC""", uid)]
    return {
        **person_ref(p), "no": 0 if u["is_founder"] else u["card_no"], "course": s["course"], "school": s["school"], "bio": u["bio"],
        "attended": len(attended(con, uid)),
        # the role shows only to the club's own team (owner, Oct 15): outside, just the club
        "clubs": [{"org": org_ref(con, m), "role": m["role"] if m["mine"] else None, "title": m["title"] if m["mine"] else None} for m in rows(con, """
            SELECT m.role, t.name AS title, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = m.org_id AND x.user_id = ?) AS mine, o.* FROM org_members m
            JOIN orgs o ON o.id = m.org_id LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ?""", v.id, uid)],
        # where they were before (org_history, written by triggers): a role held at least a day, the club still shown;
        # the role by the same rule as above. Newest first
        "past": [{"org": org_ref(con, h), "role": h["role"] if h["mine"] else None, "since": h["since"], "until": h["until"]} for h in rows(con, """
            SELECT h.role, h.since, h.until, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = h.org_id AND x.user_id = ?) AS mine, o.*
            FROM org_history h JOIN orgs o ON o.id = h.org_id
            WHERE h.user_id = ? AND h.until IS NOT NULL AND h.until - h.since >= 86400 AND o.status = 'active'
            ORDER BY h.until DESC LIMIT 20""", v.id, uid)],
        "showcase": [a for c in u["showcase"].split(",") for a in ach if a["code"] == c and a["level"] > 0],
        # the showcase as picked (achievements earned, badges owned), in order; empty = never picked, the badge shows a default
        "shelf": [k for k in u["showcase"].split(",") if any(a["code"] == k and a["level"] > 0 for a in ach) or any(f"b{b['eventId']}" == k for b in badges)],
        "awards": {"achievements": ach, "badges": badges},
        "friendship": state, "friendsSince": link["created_at"] if link else None, "going": going,
        "username": u["tg_username"] if team else None,
        "skin": _skin(con, uid),
    }


# ---------------------------------------------------------------- friends (§4.7)

FRIEND_ASKS_A_DAY = 20
REASK_AFTER = 30 * 86400    # a declined request looks pending to the asker this long, then they may ask again
LINK_TTL = 7 * 86400


def friendship(con, me: int, uid: int) -> str:
    """'friends' | 'requested' (mine, waiting; a quiet decline looks the same for 30 days) | 'incoming' | 'none'."""
    if one(con, "SELECT 1 FROM friendships WHERE a = ? AND b = ?", min(me, uid), max(me, uid)):
        return "friends"
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND (status = 'pending' OR (status = 'declined' AND decided_at > ?))",
           me, uid, now() - REASK_AFTER):
        return "requested"
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", uid, me):
        return "incoming"
    return "none"


def _student(con, uid: int | None) -> sqlite3.Row:
    p = one(con, PERSON + " WHERE u.id = ? AND s.user_id IS NOT NULL", uid) if uid else None
    if not p:
        raise ApiError("not_found")
    return p


def _befriend(con, a: int, b: int) -> None:
    """Friends from now on; requests between the two, either way, are settled by it. Each hears it from the bot
    except the one who made it happen (the caller notifies the other)."""
    con.execute("INSERT OR IGNORE INTO friendships (a, b, created_at) VALUES (?, ?, ?)", (min(a, b), max(a, b), now()))
    con.execute("""UPDATE friend_requests SET status = 'accepted', decided_at = ? WHERE status = 'pending'
        AND ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))""", (now(), a, b, b, a))


def _friend_row(p: sqlite3.Row, at: int, friend: bool = True) -> dict:
    """Full names only between friends (§3); a request shows the short one, with course and school like any card."""
    name = f"{p['first_name']} {p['last_name']}".strip() if friend else short_name(p)
    return {"person": person_ref(p), "fullName": name, "course": p["course"], "school": p["school"], "at": at}


def friends(con, v: Viewer) -> dict:
    """The Friends page: friends (full names, §3), requests both ways, and the coming events friends go to (only
    those who let friends see it; the card lists them)."""
    need_student(v)
    cols = PERSON_COLS + ", s.course, s.school"
    mine = [_friend_row(p, p["since"]) for p in rows(con, f"""SELECT {cols}, f.created_at AS since FROM friendships f
        JOIN users u ON u.id = CASE WHEN f.a = ? THEN f.b ELSE f.a END JOIN students s ON s.user_id = u.id
        WHERE f.a = ? OR f.b = ? ORDER BY s.first_name, s.last_name""", v.id, v.id, v.id)]
    incoming = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.from_id JOIN students s ON s.user_id = u.id
        WHERE r.to_id = ? AND r.status = 'pending' ORDER BY r.created_at DESC""", v.id)]
    outgoing = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.to_id JOIN students s ON s.user_id = u.id
        WHERE r.from_id = ? AND (r.status = 'pending' OR (r.status = 'declined' AND r.decided_at > ?)) ORDER BY r.created_at DESC""",
        v.id, now() - REASK_AFTER)]
    roles = _roles(con, v)
    going = [e for e in rows(con, f"""SELECT DISTINCT e.* FROM registrations r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
        WHERE r.status = 'going' AND u.show_going = 1 AND e.status = 'published' AND COALESCE(e.ends_at, e.starts_at + {NO_END}) > ?
        AND r.user_id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)
        ORDER BY e.starts_at LIMIT 30""", now(), v.id, v.id) if _visible(con, v, e, roles)]
    return {"friends": mine, "incoming": incoming, "outgoing": outgoing, "going": cards(con, v, going)}


def find_student(con, v: Viewer, username: str) -> dict:
    """A student by Telegram @username (public in Telegram anyway, §4.7), with where the two of us stand."""
    need_student(v)
    name = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ApiError("bad_input")
    u = one(con, "SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE lower(u.tg_username) = lower(?)", name)
    p = _student(con, u["id"] if u else None)
    s = one(con, "SELECT course, school FROM students WHERE user_id = ?", p["id"])
    return {"person": person_ref(p), "course": s["course"], "school": s["school"],
            "friendship": "none" if p["id"] == v.id else friendship(con, v.id, p["id"]), "me": p["id"] == v.id}


def ask_friend(con, v: Viewer, uid: int) -> dict:
    """Add friend: a request the other one answers; if they had asked me already, this is the answer (friends now).
    A request after a quiet decline changes nothing for 30 days and says nothing to anyone."""
    need_student(v)
    p = _student(con, uid)
    if uid == v.id:
        raise ApiError("bad_input")
    state = friendship(con, v.id, uid)
    if state == "incoming":
        with tx(con):
            _befriend(con, v.id, uid)
            notify(con, uid, "friend_new", f"fn:{v.id}:{now() // 86400}")
        state = "friends"
    elif state == "none":
        if one(con, "SELECT COUNT(*) FROM friend_requests WHERE from_id = ? AND created_at > ?", v.id, now() - 86400)[0] >= FRIEND_ASKS_A_DAY:
            raise ApiError("rate_limited")
        with tx(con):
            con.execute("""INSERT INTO friend_requests (from_id, to_id, status, created_at) VALUES (?, ?, 'pending', ?)
                ON CONFLICT (from_id, to_id) DO UPDATE SET status = 'pending', created_at = excluded.created_at, decided_at = NULL""", (v.id, uid, now()))
            notify(con, uid, "friend_request", f"fq:{v.id}:{now() // 86400}")
        state = "requested"
    return {"person": person_ref(p), "friendship": state}


def answer_friend(con, v: Viewer, uid: int, accept: bool) -> dict:
    need_student(v)
    if not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", uid, v.id):
        raise ApiError("not_found")
    with tx(con):
        if accept:
            _befriend(con, v.id, uid)
            notify(con, uid, "friend_new", f"fn:{v.id}:{now() // 86400}")
        else:  # quietly: the asker keeps seeing "request sent" (§4.7)
            con.execute("UPDATE friend_requests SET status = 'declined', decided_at = ? WHERE from_id = ? AND to_id = ?", (now(), uid, v.id))
    return friends(con, v)


def take_back_request(con, v: Viewer, uid: int) -> None:
    """Cancel my waiting request (a quietly declined one stays: it still holds the 30 days)."""
    need_student(v)
    con.execute("DELETE FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", (v.id, uid))


def unfriend(con, v: Viewer, uid: int) -> None:
    """Quietly; either side, any time (§4.7)."""
    need_student(v)
    con.execute("DELETE FROM friendships WHERE a = ? AND b = ?", (min(uid, v.id), max(uid, v.id)))


def friend_link(con, v: Viewer) -> dict:
    """My live one-time link (§4.7): the same one until somebody uses it or it expires, then a fresh one (96 random bits)."""
    need_student(v)
    r = one(con, "SELECT token, expires_at FROM friend_links WHERE user_id = ? AND used_by IS NULL AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            v.id, now() + 3600)  # never hand out one that dies within the hour
    if r:
        return {"token": r["token"], "expiresAt": r["expires_at"]}
    token, until = secrets.token_hex(12), now() + LINK_TTL
    con.execute("INSERT INTO friend_links (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)", (token, v.id, now(), until))
    return {"token": token, "expiresAt": until}


def friend_link_used(con, v: Viewer, token: str) -> dict:
    """While my QR is on screen: who has just used it (the sheet celebrates and shows the next one)."""
    need_student(v)
    r = one(con, "SELECT used_by FROM friend_links WHERE token = ? AND user_id = ?", token, v.id)
    if not r:
        raise ApiError("not_found")
    return {"usedBy": person_ref(_student(con, r["used_by"])) if r["used_by"] else None}


def use_friend_link(con, v: Viewer, token: str) -> dict:
    """Someone opened my link: the first student becomes my friend at once; after that it's 'used' and they may ask
    the usual way. Results: friends | already | used | self."""
    need_student(v)
    r = one(con, "SELECT * FROM friend_links WHERE token = ?", token)
    if not r:
        raise ApiError("not_found")
    owner = _student(con, r["user_id"])
    out = {"person": person_ref(owner)}
    if r["user_id"] == v.id:
        return {**out, "result": "self"}
    if friendship(con, v.id, r["user_id"]) == "friends":
        return {**out, "result": "already"}
    with tx(con):  # one write lock: of two people opening it at once, one wins
        won = r["expires_at"] > now() and con.execute("UPDATE friend_links SET used_by = ?, used_at = ? WHERE token = ? AND used_by IS NULL",
                                                       (v.id, now(), token)).rowcount
        if won:
            _befriend(con, v.id, r["user_id"])
            notify(con, r["user_id"], "friend_new", f"fn:{v.id}:{now() // 86400}")
    return {**out, "result": "friends" if won else "used"}


# ---------------------------------------------------------------- Studio (own org)

def _staff_event(con, v: Viewer, eid: int, right: str) -> sqlite3.Row:
    """The event, if I have this right in its club: "events" to run it, "door" to check people in."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e:
        raise ApiError("not_found")
    _may(con, v, e["org_id"], right)
    return e


def org_events(con, v: Viewer, oid: int) -> list[dict]:
    """Studio's list; for the club's Head+ each event also says how many questions wait for them (`_asking`) and how
    many receipts to check, so they show on top of Studio."""
    role = role_in(con, v, oid)
    if not at_least(role, "member"):
        raise ApiError("forbidden")
    head = can(con, v, oid, "events")
    found = rows(con, "SELECT * FROM events WHERE org_id = ? AND memo_only = 0 ORDER BY starts_at", oid)  # Oct 15's requests without an event: left, hidden
    # receipts that look wrong and nobody looked at yet (§4.3; a registration's last receipt counts), on top of Studio too
    check = dict(rows(con, """SELECT r.event_id, COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id)
        WHERE e.org_id = ? AND r.status = 'going' AND c.status = 'accepted' AND c.flags != '' AND c.reviewed_at IS NULL GROUP BY r.event_id""", oid)) if head else {}
    saved = dict(rows(con, f"SELECT event_id, COUNT(*) FROM saved_events WHERE event_id IN ({_qs([e['id'] for e in found])}) GROUP BY event_id",
                      *[e["id"] for e in found])) if head and found else {}
    asked = dict(rows(con, """SELECT x.event_id, COUNT(*) FROM volunteers x JOIN events e ON e.id = x.event_id
        WHERE e.org_id = ? AND x.status = 'asked' GROUP BY x.event_id""", oid)) if head else {}  # volunteers waiting for an answer
    return [{**c, "questions": len(_asking(con, e["id"], v.id)) if head else 0, "toCheck": check.get(e["id"], 0), "savedBy": saved.get(e["id"], 0),
             "volunteersAsked": asked.get(e["id"], 0)}
            for e, c in zip(found, cards(con, v, found))]


def _asking(con, eid: int, reader: int = 0) -> list:
    """Students' comments under an event that wait for the club: after its last answer (as the club, or by any of its
    Head+ as themselves; their own words are never questions) and, for a `reader`, after they last read the thread
    (owner, Oct 5: Studio's count stayed after he had read and answered). By ids, so the same second never hides one.
    ponytail: an id freed by a deleted account's last comment can come back; a reader may then miss one question."""
    return rows(con, """WITH leads AS (SELECT m.user_id FROM org_members m JOIN events e ON e.org_id = m.org_id
            WHERE e.id = ? AND m.role IN ('president', 'vice', 'head')),
          live AS (SELECT * FROM comments WHERE event_id = ? AND deleted_at IS NULL)
        SELECT user_id FROM live WHERE as_org = 0 AND user_id NOT IN leads
          AND id > COALESCE((SELECT MAX(id) FROM live WHERE as_org = 1 OR user_id IN leads), 0)
          AND id > COALESCE((SELECT last_id FROM comment_reads WHERE event_id = ? AND user_id = ?), 0)""", eid, eid, eid, reader)


def shade(color: str) -> str:
    """Sheet tint from the event's colour (with a cover the editor sends the photo's own, §4.8b): the same hue, a quarter darker."""
    n = int(color[1:], 16)
    return "#" + "".join(f"{round(((n >> s) & 255) * 0.75):02x}" for s in (16, 8, 0))


LEAD_ROLES = {"president": ("president",), "vice": ("president", "vice"), "head": ("president", "vice", "head")}
CLUB_KINDS = ("club", "school", "council")


def _invited_leaders(con, e: sqlite3.Row, exclude: int | None = None) -> list[sqlite3.Row]:
    """Who a leaders meeting invites: every club's people from its lowest invited role up (each person once)."""
    roles = LEAD_ROLES[e["leaders_from"] or "president"]
    return rows(con, f"""SELECT DISTINCT m.user_id FROM org_members m JOIN orgs o ON o.id = m.org_id JOIN students s ON s.user_id = m.user_id
        WHERE o.kind IN ('club', 'school', 'council') AND o.status = 'active' AND m.role IN ({','.join('?' * len(roles))}) AND m.user_id != ?""",
                *roles, exclude or 0)


def decline(con, v: Viewer, eid: int, note: object = None) -> dict:
    """"Can't make it" (a leaders meeting, §4.10; a club meeting, §2b, says why, which its Head+ read): the answer is
    kept, a seat or a ticket given back."""
    need_student(v)
    e = _event(con, v, eid)
    if e["status"] != "published" or e["starts_at"] <= now():
        raise ApiError("closed")
    why = " ".join(str(note or "").split())
    if len(why) > 140 or (e["meeting"] and len(why) < 2):
        raise ApiError("bad_input", "note")
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
    if r and r["status"] in ("going", "hold", "waitlist"):
        unregister(con, v, eid)
    elif not r:
        con.execute("""INSERT INTO registrations (event_id, user_id, status, cancel_reason, ticket_code, created_at, updated_at)
            VALUES (?, ?, 'cancelled', 'self', ?, ?, ?)""", (eid, v.id, _ticket_code(con), now(), now()))
    con.execute("UPDATE registrations SET note = ? WHERE event_id = ? AND user_id = ?", (why or None, eid, v.id))
    return card(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _team_door(e: sqlite3.Row) -> bool:
    """A club meeting, or a free team-only event: no tickets (owner, Oct 6), so the door has the whole team (a meeting's
    tag) to mark, and someone who came without signing up is let in by name."""
    return bool(e["meeting"]) or (e["visibility"] == "members" and not e["price"])


def _expected(con, e: sqlite3.Row) -> list[int]:
    """Who a club meeting expects (§2b): the club's students, or only those with its tag."""
    tag = e["meeting_tag"]
    return [r[0] for r in rows(con, "SELECT m.user_id FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ?"
                                    + (" AND m.user_id IN (SELECT user_id FROM member_tags WHERE tag_id = ?)" if tag else ""), e["org_id"], *([tag] if tag else []))]


def meeting_answers(con, v: Viewer, eid: int) -> list[dict]:
    """A club meeting's people for its Head+ (§2b): each one's answer (yes, no with the reason, none) and whether they
    came; once it's over, who missed it without a reason and is on probation can get its strike, one tap, once."""
    e = _staff_event(con, v, eid, "events")
    if not e["meeting"]:
        raise ApiError("bad_input")
    over, mine = end_of(e) <= now(), role_in(con, v, e["org_id"])
    expected = _expected(con, e)
    found = rows(con, f"""SELECT {PERSON_COLS}, m.role, m.probation, r.status, r.note, r.checked_in_at,
            EXISTS (SELECT 1 FROM strikes x WHERE x.event_id = ? AND x.user_id = u.id) AS struck
        FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        LEFT JOIN registrations r ON r.event_id = ? AND r.user_id = u.id
        WHERE m.org_id = ? AND u.id IN ({_qs(expected)})""", eid, eid, e["org_id"], *expected) if expected else []
    out = []
    for p in found:
        answer = "yes" if p["status"] in ("going", "hold") else "no" if p["status"] == "cancelled" else "none"
        came = p["checked_in_at"] is not None
        out.append({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "role": p["role"],
                    "answer": answer, "note": p["note"] if answer == "no" else None, "came": came, "probation": bool(p["probation"]),
                    "struck": bool(p["struck"]),
                    "canStrike": over and not came and not (answer == "no" and p["note"]) and bool(p["probation"]) and not p["struck"]
                    and RANK[mine] > RANK[p["role"]]})  # a "no" with a reason is excused; one without (a cancelled ticket) isn't
    return sorted(out, key=lambda x: (-RANK[x["role"]], x["fullName"]))


def leaders_answers(con, v: Viewer, eid: int) -> list[dict]:
    """DMP's view of a leaders meeting (§4.10): per club, who said yes, who no, who hasn't answered."""
    e = _staff_event(con, v, eid, "events")
    if e["visibility"] != "leaders":
        raise ApiError("bad_input")
    roles = LEAD_ROLES[e["leaders_from"] or "president"]
    out = []
    for o in rows(con, "SELECT * FROM orgs WHERE kind IN ('club', 'school', 'council') AND status = 'active' ORDER BY official DESC, name"):
        people = rows(con, f"""SELECT {PERSON_COLS}, m.role, r.status AS answer FROM org_members m JOIN users u ON u.id = m.user_id
            JOIN students s ON s.user_id = u.id LEFT JOIN registrations r ON r.event_id = ? AND r.user_id = u.id
            WHERE m.org_id = ? AND m.role IN ({','.join('?' * len(roles))})""", eid, o["id"], *roles)
        if not people:
            continue
        said = lambda p: "yes" if p["answer"] in ("going", "hold") else "no" if p["answer"] == "cancelled" else "none"  # noqa: E731
        out.append({"org": org_ref(con, o), "people": sorted(({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(),
                                                          "role": p["role"], "answer": said(p)} for p in people), key=lambda x: -RANK[x["role"]])})
    return out


def clean_event(i: dict, oversee: bool = False) -> dict:
    """The editor's input, checked. A leaders meeting (§4.10) only from an oversight org
    (DMP), with the lowest role invited."""
    try:
        title, place = str(i["title"]).strip(), str(i["place"]).strip()
        description = str(i.get("description") or "").strip()
        url = (str(i.get("placeUrl") or "")).strip() or None
        starts, ends = int(i["startsAt"]), (int(i["endsAt"]) if i.get("endsAt") is not None else None)
        seats = int(i["seats"]) if i.get("seats") is not None else None
        reg_until = int(i["regUntil"]) if i.get("regUntil") is not None else None
        emoji, color = str(i["emoji"]), str(i["color"])
        visibility = None if i.get("visibility") is None else str(i["visibility"])  # left out: kept as it is
        leaders = str(i.get("leadersFrom") or "president") if visibility == "leaders" else None
        meeting = i.get("meeting") is True  # a club meeting (§2b): team-only, someone's tag or the whole club expected
        tag = int(i["meetingTag"]) if meeting and i.get("meetingTag") is not None else None
        vol = int(i["volunteers"]) if i.get("volunteers") else None  # how many volunteers it needs; none: off
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    ok = (0 < len(title) <= 80 and len(place) <= 80 and len(description) <= 2000  # no place: to be confirmed (a room asked of DMP) and (ends is None or ends > starts)
          and (seats is None or 0 < seats <= 5000) and (url is None or TWO_GIS.match(url)) and (reg_until is None or reg_until <= starts)
          and re.fullmatch(r"#[0-9a-fA-F]{6}", color) and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and visibility in (None, "public", "members", *(("leaders",) if oversee else ()))
          and leaders in (None, "president", "vice", "head") and (not meeting or visibility == "members" and seats is None)
          and (vol is None or 1 <= vol <= 500 and not meeting))
    if not ok:
        raise ApiError("bad_input")
    return {"title": title, "description": description, "starts_at": starts, "ends_at": ends, "place": place, "place_url": url,
            "emoji": emoji, "color": color, "seats": seats, "reg_until": reg_until, "first_year": int(bool(i.get("firstYear"))),
            "album_open": int(i.get("albumOpen") is not False),  # "Photos from participants" (off: the team's only)
            "meeting": int(meeting), "meeting_tag": tag, "volunteers": vol, "volunteers_senior": int(bool(vol and i.get("volunteersSenior"))),
            **({"visibility": visibility, "leaders_from": leaders} if visibility else {})}


MEMO_ASKS = ("room", "guests", "provide", "promo", "gear", "print", "film")


def _memo(body: dict, keep: str | None) -> str | None:
    """The editor's "For the memo" block (what DMP is asked for, texts.memo_asks): absent keeps it, null clears it.
    Free-form inside each request, bounded: plain values, or a short list of them (printing, a promo's days, more times)."""
    if "memo" not in body:
        return keep
    m = body["memo"]
    if m is None or m == {}:
        return None
    plain = lambda x: x is None or isinstance(x, (bool, int)) or isinstance(x, str) and len(x) <= 1500  # noqa: E731
    ok = isinstance(m, dict) and set(m) <= set(MEMO_ASKS) and all(
        isinstance(a, dict) and all(plain(x) or isinstance(x, list) and len(x) <= 31 and all(plain(y) or isinstance(y, dict) and all(plain(z) for z in y.values()) for y in x)
                                    for x in a.values()) for a in m.values())
    out = json.dumps(m, ensure_ascii=False) if ok else ""
    if not ok or len(out) > 8000:
        raise ApiError("bad_input")
    return out


def _next_week(t: int | None = None) -> int:
    """Monday 00:00 (Almaty) of the week the coming Wednesday's memo covers: DMP takes next week's memos on Wednesdays,
    so from Thursday on it's the week after next (1970-01-01 was a Thursday: Monday = 0)."""
    day = ((t or now()) + 5 * 3600) // 86400
    return (day + (2 - (day + 3) % 7) % 7 + 5) * 86400 - 5 * 3600


def _room_no(place: str, url: str | None) -> str | None:
    """The room number in a campus place ("Aud. 305", "332b"), as the memo names it; none off campus."""
    m = None if url else re.search(r"(?<!\d)(\d{2,3}[a-z\u0430-\u044f\u0451]?)(?!\d)", place.lower())
    return m[1] if m else None


def _memo_sender(con, v: Viewer, oid: int) -> dict:
    """Who signs the memo: the sender's "First Last" (kk, ru), in Latin for en (passport style; fixed once by hand), the
    position in three languages from the club role (texts.memo_pos), the portal's phone; `memo_sign` keeps the fixes."""
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    m = one(con, "SELECT m.role, m.memo_sign, r.name FROM org_members m LEFT JOIN org_roles r ON r.id = m.role_id WHERE m.org_id = ? AND m.user_id = ?", oid, v.id)
    fixed = json.loads(m["memo_sign"]) if m and m["memo_sign"] else {}
    name = f"{s['first_name']} {s['last_name']}" if s else ""
    lat = " ".join(w.capitalize() for w in "".join(receipt._LAT.get(c, c) for c in name.lower()).split())
    pos = texts.memo_pos(m["role"] if m else "member", m["name"] if m else None)
    return {"name": name, "nameEn": fixed.get("nameEn") or lat, "phone": texts.phone_line(s["phone"]) if s else None,
            **{k: fixed.get(k) or pos[k] for k in ("kk", "ru", "en")}, "fixed": bool(fixed)}


def memo(con, v: Viewer, oid: int, later: bool = False) -> dict:
    """The week's memo for DMP (PLAN stage 2): one memo of next week's events that ask DMP for something (drafts too:
    rooms are booked before the poster), with `later` the later ones too, signed once by the caller; events already
    sent are left out (listed in `sent`). The app opens it in Outlook to youth_policy@kbtu.kz or copies it. `without`: next
    week's events that ask for nothing, to check."""
    _may(con, v, oid, "memo")
    o = _org(con, oid)
    monday = _next_week()
    evs = rows(con, "SELECT * FROM events WHERE org_id = ? AND status IN ('draft', 'published') AND memo_only = 0 AND starts_at >= ? ORDER BY starts_at", oid, monday)
    week = [e for e in evs if e["starts_at"] < monday + 7 * 86400]
    todo = [e for e in evs if e["memo"] and not e["memo_sent_at"]]
    asked = [e for e in todo if later or e["starts_at"] < monday + 7 * 86400]
    me = _memo_sender(con, v, oid)
    sign = texts.memo_sign(o["name"], me, me["name"], me["nameEn"], me["phone"])
    shape = lambda e: {"title": e["title"], "starts_at": e["starts_at"], "ends_at": e["ends_at"], "place": e["place"], "meeting": e["meeting"],  # noqa: E731
                       "room": _room_no(e["place"], e["place_url"]), "off": bool(e["place_url"]), "seats": e["seats"]}
    asks = [(shape(e), json.loads(e["memo"])) for e in asked]
    dmp = [(e, m) for e, m in asks if set(m) - {"print"}]  # an event asking only for printing has nothing for DMP
    text = texts.memo_text(o["name"], dmp, sign)
    prints = [(e, m) for e, m in asks if m.get("print")]
    pr = texts.print_letter(o["name"], prints, me["ru"], me["name"], me["phone"]) if prints else None
    who = lambda uid: (lambda p: shown_name(p) if p else None)(one(con, PERSON + " WHERE u.id = ?", uid)) if uid else None  # noqa: E731
    brief = lambda e: {"id": e["id"], "title": e["title"], "startsAt": e["starts_at"], "draft": e["status"] == "draft"}  # noqa: E731
    return {"to": texts.MEMO_TO, "subject": texts.memo_subject(o["name"], monday), "text": text, "from": monday, "until": monday + 7 * 86400,
            "print": {"to": texts.PRINT_TO, "subject": pr[0], "text": pr[1]} if pr else None, "guests": any("guests" in json.loads(e["memo"]) for e in asked),
            "events": [brief(e) for e in asked], "later": [brief(e) for e in todo if e["starts_at"] >= monday + 7 * 86400],
            "sent": [{**brief(e), "sentAt": e["memo_sent_at"], "sentBy": who(e["memo_sent_by"])} for e in evs if e["memo"] and e["memo_sent_at"]],
            "without": [brief(e) for e in week if not e["memo"]], "canEdit": can(con, v, oid, "events"),
            "opened": {"at": o["memo_opened_at"], "by": who(o["memo_opened_by"])} if o["memo_opened_at"] else None,
            "sign": {k: me[k] for k in ("name", "nameEn", "kk", "ru", "en", "fixed")},
            "signFrom": texts.MEMO2_SIGN["kk"][0]}  # the sheet's items go in before the signature


def memo_item(con, v: Viewer, oid: int, body: dict) -> str:
    """One item of the memo, written from the sheet's small form (owner, Oct 15: a request needs no event): `kind` and its
    fields as the editor's memo block has them, the day and hours, the place. The sheet shows it and puts it in the text."""
    _may(con, v, oid, "memo")
    kind, place = body.get("kind"), " ".join(str(body.get("place") or "").split())[:80]
    try:
        starts, ends = int(body["startsAt"]), int(body["endsAt"]) if body.get("endsAt") else None
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    if kind not in MEMO_ASKS or kind == "print" or (ends is not None and ends <= starts):
        raise ApiError("bad_input")
    memo = json.loads(_memo({"memo": {kind: body.get("fields") or {}}}, None) or "{}")
    e = {"title": "", "starts_at": starts, "ends_at": ends, "place": place, "room": _room_no(place, None), "off": False, "seats": None, "meeting": 0}
    return (texts.memo_asks(e, memo) or [""])[0]


def memo_opened(con, v: Viewer, oid: int) -> None:
    """"Open in Outlook" or "Copy": the sheet shows it to the others, so nobody sends the week twice."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE orgs SET memo_opened_at = ?, memo_opened_by = ? WHERE id = ?", (now(), v.id, oid))


def memo_sent(con, v: Viewer, oid: int, ids: object) -> None:
    """"Sent it to DMP?" -> Yes: these events leave the next memos (an edit of their requests brings them back)."""
    _may(con, v, oid, "memo")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids) or len(ids) > 100:
        raise ApiError("bad_input")
    for i in ids:
        con.execute("UPDATE events SET memo_sent_at = ?, memo_sent_by = ? WHERE id = ? AND org_id = ? AND memo IS NOT NULL", (now(), v.id, i, oid))


def memo_again(con, v: Viewer, oid: int, eid: int) -> None:
    """"Include again": a sent event goes back into the memo."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE events SET memo_sent_at = NULL, memo_sent_by = NULL WHERE id = ? AND org_id = ?", (eid, oid))


def memo_sign(con, v: Viewer, oid: int, body: dict) -> dict:
    """The sender fixes the Latin name and the three positions once; an empty field goes back to the computed one."""
    _may(con, v, oid, "memo")
    keep = {k: " ".join(str(body.get(k) or "").split()) for k in ("nameEn", "kk", "ru", "en")}
    if any(len(x) > 120 for x in keep.values()):
        raise ApiError("bad_input")
    keep = {k: x for k, x in keep.items() if x}
    con.execute("UPDATE org_members SET memo_sign = ? WHERE org_id = ? AND user_id = ?", (json.dumps(keep, ensure_ascii=False) if keep else None, oid, v.id))
    return memo(con, v, oid)


def _once(con, key: str, value: str) -> bool:
    """True the first time a periodic job runs for `value` (a week, a day): the bot's rounds come every few seconds."""
    if one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, value):
        return False
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
    return True


def memo_week(con) -> None:
    """Wednesday 9:00-18:00 (Almaty), once a week: everyone with the club's "memo" right, where next week has events
    asking DMP for something not sent yet, hears the memo is ready (DMP takes them until 18:00 that day; later there's no
    point). The sheet shows who opened it already."""
    local = now() + 5 * 3600
    if (local // 86400 + 3) % 7 != 2 or not 9 * 3600 <= local % 86400 < 18 * 3600:
        return
    monday = _next_week()
    if not _once(con, "memo_week", str(monday)):
        return
    for (oid,) in rows(con, """SELECT DISTINCT org_id FROM events WHERE status IN ('draft', 'published') AND memo IS NOT NULL
            AND memo_sent_at IS NULL AND starts_at >= ? AND starts_at < ?""", monday, monday + 7 * 86400):
        for m in rows(con, "SELECT m.user_id, m.role, t.rights FROM org_members m LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ?", oid):
            if "memo" in _rights_from(m["role"], m["rights"]):
                notify(con, m["user_id"], "memo_ready", f"memo:{oid}:{monday}")


def saved_day(con) -> None:
    """12:00 (Almaty) daily: whoever saved an event that's tomorrow and isn't going to it hears it once (all such events in
    one message), with the 2-hour reminders' switch: "Save" with a purpose (owner, Oct 11; instead of a like)."""
    local = now() + 5 * 3600
    day = local // 86400
    if local % 86400 < 12 * 3600 or not _once(con, "saved_day", str(day)):
        return
    lo, hi = (day + 1) * 86400 - 5 * 3600, (day + 2) * 86400 - 5 * 3600
    for (uid,) in rows(con, """SELECT DISTINCT s.user_id FROM saved_events s JOIN events e ON e.id = s.event_id JOIN users u ON u.id = s.user_id
            WHERE e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ? AND u.n_remind = 1
            AND NOT EXISTS (SELECT 1 FROM registrations r WHERE r.event_id = e.id AND r.user_id = s.user_id AND r.status IN ('going', 'hold', 'waitlist'))""",
                        lo, hi):
        notify(con, uid, "saved_tomorrow", f"sv:{day}")


def tba_day(con) -> None:
    """10:00 (Almaty) daily: whoever made a published event that still has no place hears it 7, 3 and 1 day before and
    on the day; all of theirs in one message (the bot lists them), until the room is typed in."""
    local = now() + 5 * 3600
    day = local // 86400
    if local % 86400 < 10 * 3600 or not _once(con, "tba_day", str(day)):
        return
    for e in rows(con, "SELECT created_by, starts_at FROM events WHERE status = 'published' AND place = '' AND created_by IS NOT NULL AND starts_at > ?", now()):
        if (e["starts_at"] + 5 * 3600) // 86400 - day in (7, 3, 1, 0):
            notify(con, e["created_by"], "place_tba", f"tba:{day}")


def stats_day(con) -> None:
    """Just after midnight (Almaty), once: yesterday's row for the admin's chart. seen_at is the last time someone opened
    the app, so seen_at >= yesterday's start counts exactly who opened it since (a few minutes of today included)."""
    local = now() + 5 * 3600
    day = local // 86400 - 1
    if local % 86400 >= 3 * 3600 or not _once(con, "stats_day", str(day)):  # later in the day today's visits would count too
        return
    lo, hi = day * 86400 - 5 * 3600, (day + 1) * 86400 - 5 * 3600
    con.execute("INSERT OR REPLACE INTO stats_days (day, active, new, students) VALUES (?, ?, ?, ?)",
                (day, one(con, "SELECT COUNT(*) FROM users WHERE seen_at >= ?", lo)[0],
                 one(con, "SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?", lo, hi)[0],
                 one(con, "SELECT COUNT(*) FROM students WHERE verified_at < ? AND consent_version != 'staff'", hi)[0]))


def admin_stats(con, v: Viewer) -> dict:
    """The admin panel's numbers (PLAN "Admin stats"): online now (opened in the last 10 minutes: seen_at is refreshed
    at most every 10), active in a day / week / month, students (DMP staff aside, §1), new today; the last 30 days from the nightly rows."""
    _admin(v)
    t = now()
    since = lambda s: one(con, "SELECT COUNT(*) FROM users WHERE seen_at >= ?", t - s)[0]  # noqa: E731
    today = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    return {"online": since(600), "day": since(86400), "week": since(7 * 86400), "month": since(30 * 86400),
            "users": one(con, "SELECT COUNT(*) FROM users")[0], "students": one(con, "SELECT COUNT(*) FROM students WHERE consent_version != 'staff'")[0],
            "newToday": one(con, "SELECT COUNT(*) FROM users WHERE created_at >= ?", today)[0],
            "ai": ai_state(con),
            "days": [{"day": r["day"], "active": r["active"], "new": r["new"], "students": r["students"]}
                     for r in rows(con, "SELECT * FROM stats_days WHERE day >= ? ORDER BY day", (t + 5 * 3600) // 86400 - 30)]}


def _meeting_ok(con, v: Viewer, oid: int, f: dict, priced: bool, was: tuple | None = None) -> None:
    """A meeting's tag is one of the club's own, and a meeting has no price. A Head with a department calls only that
    department (PLAN item 35, owner Oct 19); `was` (meeting, tag) before an edit: what someone else set stays as it is."""
    if f["meeting"] and (priced or f["meeting_tag"] and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ?", f["meeting_tag"], oid)):
        raise ApiError("bad_input")
    if f["meeting"] and (f["meeting"], f["meeting_tag"]) != was and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
        own = dept_of(con, oid, v.id)
        if own is not None and f["meeting_tag"] != own:
            raise ApiError("forbidden", "dept")


def _cover(con, v: Viewer, body: dict, keep: int | None) -> int | None:
    """The editor's coverId: absent keeps the current photo, null removes it, an id must be the caller's upload."""
    if "coverId" not in body:
        return keep
    if body["coverId"] is None:
        return None
    try:
        f = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", int(body["coverId"]), v.id)
    except (TypeError, ValueError):
        f = None
    if not f:
        raise ApiError("bad_input")
    return f["id"]


def _focus(body: dict, keep: str | None) -> str | None:
    """The editor's coverFocus: the point of the photo every frame keeps in view, [x, y] from 0 to 1; absent keeps it."""
    if "coverFocus" not in body:
        return keep
    if body["coverFocus"] is None:
        return None
    try:
        x, y = (float(c) for c in body["coverFocus"])
    except (TypeError, ValueError):
        raise ApiError("bad_input")
    if not (0 <= x <= 1 and 0 <= y <= 1):  # NaN fails here too
        raise ApiError("bad_input")
    return f"{x:.3f},{y:.3f}"


def _pay(con, v: Viewer, body: dict, org: sqlite3.Row, e: sqlite3.Row | None = None) -> dict:
    """The price and where students send it (§4.3): only an official club's Vice+ set them, and they are fixed once the
    first receipt is in. Absent keeps them; a null price makes the event free. The phone is kept as +7XXXXXXXXXX.
    freeFirst: how many 1st-year students come free (the first ones to register); it can change any time.
    ponytail: a raised freeFirst doesn't turn 1st-years already holding a seat free; they pay or let it go."""
    if not any(k in body for k in ("price", "payToName", "payPhone", "freeFirst")):
        return {}
    price, name, phone, first = body.get("price"), None, None, None
    if price is not None:
        name = " ".join(str(body.get("payToName") or "").split())
        phone = re.sub(r"\D", "", str(body.get("payPhone") or ""))
        phone = "7" + phone[1:] if len(phone) == 11 and phone[0] == "8" else "7" + phone if len(phone) == 10 else phone
        first = body.get("freeFirst") or None
        if (not isinstance(price, int) or isinstance(price, bool) or not 1 <= price <= 1_000_000
                or not 2 <= len(name) <= 80 or not re.fullmatch(r"7\d{10}", phone)
                or not (first is None or (isinstance(first, int) and not isinstance(first, bool) and 1 <= first <= 5000))):
            raise ApiError("bad_input")
        phone = "+" + phone
    new = {"price": price, "pay_to_name": name, "pay_phone": phone, "free_first": first}
    old = {k: e[k] for k in new} if e else dict.fromkeys(new)
    if new == old:
        return {}
    if not org["official"] or not can(con, v, org["id"], "money"):
        raise ApiError("forbidden", "price")
    if e and any(new[k] != old[k] for k in ("price", "pay_to_name", "pay_phone")) \
            and one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", e["id"]):
        raise ApiError("conflict", "paid")  # someone has paid by these details already
    return new


def create_event(con, v: Viewer, oid: int, body: dict) -> dict:
    _may(con, v, oid, "events")
    org = _org(con, oid)
    f = {**clean_event(body, bool(org["can_oversee"])), **_pay(con, v, body, org)}
    _meeting_ok(con, v, oid, f, bool(f.get("price")))
    f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, None), _focus(body, None), _memo(body, None)
    f["video_id"], f["wide_video_id"] = _video(con, v, body, None), _video(con, v, body, None, "wideVideoId")
    with tx(con):  # bad slides leave no draft behind
        cur = con.execute(f"""INSERT INTO events (org_id, status, {', '.join(f)}, tint, created_by, created_at, updated_at)
            VALUES (?, 'draft', {', '.join('?' * len(f))}, ?, ?, ?, ?)""", (oid, *f.values(), shade(f["color"]), v.id, now(), now()))
        e = one(con, "SELECT * FROM events WHERE id = ?", cur.lastrowid)
        _slides(con, v, body, e, f["cover_file_id"])
    return full(con, v, e)


SLIDES = 9   # photos after the cover (PLAN 33): ten in all, as an Instagram or TikTok photo post


def _slides(con, v: Viewer, body: dict, e: sqlite3.Row, cover: int | None) -> None:
    """The editor's slideIds: absent keeps, [] clears; each one already on this event (a co-organizer's) or my own upload."""
    if "slideIds" not in body:
        return
    ids = body["slideIds"]
    if not isinstance(ids, list) or len(ids) > SLIDES or len(set(ids)) != len(ids) \
            or any(not isinstance(i, int) or isinstance(i, bool) for i in ids) or (cover is not None and cover in ids):
        raise ApiError("bad_input")
    for i in ids:
        if not one(con, """SELECT 1 FROM event_slides WHERE event_id = ? AND file_id = ?
                UNION ALL SELECT 1 FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?""", e["id"], i, i, v.id):
            raise ApiError("bad_input")
    con.execute("DELETE FROM event_slides WHERE event_id = ?", (e["id"],))
    con.executemany("INSERT INTO event_slides (event_id, pos, file_id) VALUES (?, ?, ?)", [(e["id"], n, i) for n, i in enumerate(ids)])


def update_event(con, v: Viewer, eid: int, body: dict) -> dict:
    org = one(con, "SELECT o.* FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ?", eid)
    f = clean_event(body, bool(org and org["can_oversee"]))
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] == "cancelled":
            raise ApiError("closed")
        f |= _pay(con, v, body, org, e)
        _meeting_ok(con, v, e["org_id"], f, bool(f["price"] if "price" in f else e["price"]), (e["meeting"], e["meeting_tag"]))
        if f["seats"] is not None and f["seats"] < taken(con, eid):
            raise ApiError("conflict")  # seats can't drop below who is already in
        f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, e["cover_file_id"]), _focus(body, e["cover_focus"]), _memo(body, e["memo"])
        f["video_id"], f["wide_video_id"] = _video(con, v, body, e["video_id"]), _video(con, v, body, e["wide_video_id"], "wideVideoId")
        _slides(con, v, body, e, f["cover_file_id"])
        if (f["memo"], f["starts_at"], f["ends_at"]) != (e["memo"], e["starts_at"], e["ends_at"]):
            f["memo_sent_at"] = f["memo_sent_by"] = None  # changed requests go to DMP again
        if (f["title"], f["description"]) != (e["title"], e["description"]):
            f["i18n"], f["lang"], f["ai_tries"] = None, None, 0  # translated again (ai.py)
        con.execute(f"UPDATE events SET {', '.join(k + ' = ?' for k in f)}, tint = ?, updated_at = ? WHERE id = ?",
                    (*f.values(), shade(f["color"]), now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if e["price"] and not after["price"]:  # free now: whoever was about to pay is simply in
            for (uid,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
                con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE event_id = ? AND user_id = ?", (now(), eid, uid))
                _remind(con, uid, after)
        _changed(con, v, e, after)
        promote(con, after)
    return full(con, v, after)


def _changed(con, v: Viewer, e: sqlite3.Row, after: sqlite3.Row) -> None:
    """Who hears that a published event moved (PLAN "Place and time", §4.9): the room DMP gave for a place to be confirmed,
    or one KBTU room for another, tells nobody now (the 2-hour reminder shows it; at once for those with reminders off);
    another venue or a new time tells them, edits within 10 minutes in one message (the bot reads the event when it
    sends); within 2 hours of the start or during it, at once and only to those not checked in. A new place also gets a
    line in the event's Updates."""
    eid, moved = e["id"], e["starts_at"] != after["starts_at"]
    placed = (e["place"], e["place_url"]) != (after["place"], after["place_url"])
    if e["status"] != "published" or not (moved or placed):
        return
    soon = now() >= after["starts_at"] - 2 * 3600
    quiet = not moved and not e["place_url"] and not after["place_url"] and after["place"]  # a room on campus: TBA -> room, room -> room
    for r in rows(con, """SELECT r.user_id, r.checked_in_at, u.n_remind FROM registrations r JOIN users u ON u.id = r.user_id
            WHERE r.event_id = ? AND r.status IN ('going','hold','waitlist')""", eid):
        if moved:
            con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (r[0], f"event:{eid}:%"))
            _remind(con, r[0], after)
        if soon and r["checked_in_at"] or quiet and not soon and r["n_remind"]:
            continue
        if not one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'event_changed' AND ref LIKE ? AND sent_at IS NULL", r[0], f"event:{eid}:%"):
            notify(con, r[0], "event_changed", f"event:{eid}:{after['updated_at']}", after=now() if soon or moved else now() + 600)  # always on (§4.9)
    if placed and after["place"]:
        con.execute("INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (?, ?, ?, ?)", (eid, v.id, f"📍 → {after['place']}", now()))


def change_place(con, v: Viewer, eid: int, place: object) -> dict:
    """Studio's "Change room" during an event (rooms change on the spot): a KBTU room in one tap, the rules above."""
    text = " ".join(str(place or "").split())
    if not 0 < len(text) <= 80:
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published" or end_of(e) < now():
            raise ApiError("closed")
        con.execute("UPDATE events SET place = ?, place_url = NULL, updated_at = ? WHERE id = ?", (text, now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        _changed(con, v, e, after)
    return full(con, v, after)


def publish_event(con, v: Viewer, eid: int) -> dict:
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "draft":
            raise ApiError("conflict")
        if e["starts_at"] <= now():
            raise ApiError("closed")
        con.execute("UPDATE events SET status = 'published', published_at = ?, updated_at = ? WHERE id = ?", (now(), now(), eid))
        if e["visibility"] == "leaders":  # §4.10: every invited leader hears at once (always on)
            for (uid,) in _invited_leaders(con, e, exclude=v.id):
                notify(con, uid, "leaders_invite", f"li:{eid}")
        if e["meeting"]:  # §2b: everyone expected hears at once (always on)
            for uid in _expected(con, e):
                if uid != v.id:
                    notify(con, uid, "meeting_invite", f"mi:{eid}")
        if e["visibility"] == "public":  # subscribers hear about it (§7, can be turned off)
            for r in rows(con, """SELECT s.user_id FROM subscriptions s JOIN users u ON u.id = s.user_id
                WHERE s.org_id = ? AND u.n_new_events = 1 AND s.user_id != ?""", e["org_id"], v.id):
                notify(con, r[0], "new_event", f"event:{eid}")
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def cancel_event(con, v: Viewer, eid: int) -> dict:
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published":
            raise ApiError("conflict")
        con.execute("UPDATE events SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?", (now(), now(), eid))
        for r in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status IN ('going','hold','waitlist')", eid):
            notify(con, r[0], "event_cancelled", f"event:{eid}")
        con.execute("DELETE FROM bot_outbox WHERE kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (f"event:{eid}:%",))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def delete_event(con, v: Viewer, eid: int) -> tuple[list[str], list[str]]:
    """A draft, or a cancelled event (owner, Oct 13: a test or a mistake shouldn't hang in Studio forever). Not one
    with payments: deleting it would take the receipts with it, the only record of money that changed hands.
    The admin may delete any event, paid and photographed too: a club asks him to remove a test (owner, Oct 13; the
    button is in Admin only, its confirm names what goes). Returns the receipt images and photos to delete from disk:
    a receipt is personal and nobody could open it any more."""
    if v.role != "admin":
        e = _staff_event(con, v, eid, "events")
        if e["status"] not in ("draft", "cancelled"):
            raise ApiError("conflict")
        if one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", eid):
            raise ApiError("conflict", "paid")
    with tx(con):
        paid = [r[0] for r in rows(con, """SELECT c.file_id FROM receipts c JOIN registrations r ON r.id = c.registration_id
            WHERE r.event_id = ?""", eid)]
        pics = [r[0] for r in rows(con, """SELECT file_id FROM event_photos WHERE event_id = ?
            UNION SELECT cover_file_id FROM events WHERE id = ? AND cover_file_id IS NOT NULL
            UNION SELECT file_id FROM event_slides WHERE event_id = ?""", eid, eid, eid)]
        post = one(con, "SELECT channel_msg FROM events WHERE id = ?", eid)
        if not con.execute("DELETE FROM events WHERE id = ?", (eid,)).rowcount:
            raise ApiError("not_found")
        # its channel post goes too (owner, Oct 18: it stayed), with the copy in the discussion group: the bot's next
        # round deletes them (bot.post_channel), the event's row is gone by then
        thread = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"thread:{eid}")
        if post and post[0]:
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"channel_gone:{post[0]}", thread[0] if thread else ""))
        receipts = [p for f in paid for p in _drop_photo(con, f)]
        photos = [p for f in pics if not con.execute("""SELECT 1 FROM users WHERE avatar_file_id = :f UNION ALL SELECT 1 FROM orgs
            WHERE logo_file_id = :f UNION ALL SELECT 1 FROM events WHERE cover_file_id = :f UNION ALL SELECT 1 FROM receipts WHERE
            file_id = :f UNION ALL SELECT 1 FROM event_photos WHERE file_id = :f UNION ALL SELECT 1 FROM posts WHERE photo_file_id = :f
            UNION ALL SELECT 1 FROM event_slides WHERE file_id = :f""",
            {"f": f}).fetchone() for p in _drop_photo(con, f)]
    return receipts, photos


def attendees(con, v: Viewer, eid: int) -> list[dict]:
    _staff_event(con, v, eid, "events")
    order = {"going": 0, "hold": 1, "waitlist": 2}
    found = rows(con, f"""SELECT {PERSON_COLS}, r.status, r.checked_in_at, r.walk_in, r.checkin_manual, r.created_at AS at, r.free,
            c.id AS rid, c.flags, c.reviewed_at, c.created_at AS sent_at, c.amount, c.receipt_no, c.sender_name, c.recipient_name, c.paid_at
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        LEFT JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id AND status = 'accepted')
        WHERE r.event_id = ? AND r.status != 'cancelled'""", eid)
    out = [{"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "status": p["status"],
            "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"]), "at": p["at"], "free": bool(p["free"]),
            "receipt": {"id": p["rid"], "flags": [x for x in p["flags"].split(",") if x], "reviewed": p["reviewed_at"] is not None, "at": p["sent_at"],
                        "amount": p["amount"], "no": p["receipt_no"], "sender": p["sender_name"], "recipient": p["recipient_name"], "paidAt": p["paid_at"]}
            if p["rid"] else None} for p in found]
    flagged = lambda a: bool(a["receipt"] and a["receipt"]["flags"] and not a["receipt"]["reviewed"])  # noqa: E731
    return sorted(out, key=lambda a: (not flagged(a), order[a["status"]], a["fullName"]))  # §4.3: flagged receipts first


def attendees_export(con, v: Viewer, eid: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    """The event and its people for the CSV (Head+, §3: an organizer sees contacts for their own event). Every export
    of personal data goes to the audit log."""
    e = _staff_event(con, v, eid, "events")
    found = rows(con, """SELECT s.last_name, s.first_name, u.tg_username, s.student_id, s.course, s.school, s.email, s.phone,
            r.status, r.created_at, r.checked_in_at, r.walk_in, r.checkin_manual
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        WHERE r.event_id = ? AND r.status != 'cancelled' ORDER BY s.last_name, s.first_name""", eid)
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'attendees_export', ?, ?, ?)",
                (v.id, f"event:{eid}", json.dumps({"rows": len(found)}), now()))
    return e, found


def _walk_in(con, e: sqlite3.Row, uid: int, code: str, t: int) -> sqlite3.Row | str:
    """A badge QR at the door (owner, Oct 4): someone who forgot to register, or was just passing by, comes in.
    A ticket they hold is checked in as usual; a free event registers them on the spot (walk_in); a paid one
    needs a ticket."""
    if e["status"] != "published":
        return "closed"
    if not one(con, "SELECT 1 FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ? AND u.qr_code = ?", uid, code):
        return "not_found"
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)
    if r and r["status"] == "going":
        return r
    if e["price"]:
        return "paid"
    if r:  # waitlisted or cancelled earlier, at the door now
        con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, hold_until = NULL, waitlisted_at = NULL, walk_in = 1, updated_at = ? WHERE id = ?",
                    (t, r["id"]))
    else:
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                    (e["id"], uid, _ticket_code(con), t, t))
    return one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)


def checkin(con, v: Viewer, eid: int, raw: str) -> dict:
    """The door scanner: a ticket (KBTU<code>) or a badge QR (§4.4). Says how late they are, for the organizer."""
    with tx(con):
        e = _staff_event(con, v, eid, "door")
        t = now()
        if t < e["starts_at"] - DOOR_EARLY or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            return {"result": "closed"}
        badge = PROFILE_QR.search(str(raw))
        if badge:
            r = _walk_in(con, e, int(badge[1]), badge[2], t)
            if isinstance(r, str):
                return {"result": r}
        else:
            c = re.sub(r"[\s-]+", "", str(raw)).upper()  # typed as "7k4 m2p", or the QR's KBTU<code> (KBTU-<code> before Oct 5)
            r = one(con, "SELECT * FROM registrations WHERE ticket_code IN (?, ?)", c, c.removeprefix("KBTU"))
            if not r:
                return {"result": "not_found"}
            if r["event_id"] != eid:
                return {"result": "other_event"}
            if r["status"] != "going":
                return {"result": "cancelled"}
        if not r["checked_in_at"]:
            _came(con, e, r["user_id"], lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, updated_at = ? WHERE id = ?",
                                                           (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"])),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": one(con, "SELECT 1 FROM receipts WHERE registration_id = ? AND status = 'accepted' AND flags != '' AND reviewed_at IS NULL", r["id"]) is not None}


RATE_FOR = 7 * 86400   # a rating is taken from the end of the event this long
RATE_SHOW = 3          # the club sees the ratings from this many on, so a small club can't tell who wrote what


def _rating_view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict:
    """What the event sheet shows about ratings: mine (and whether I may still give one: checked in, ended, within 7
    days), and for the club's Head+ the anonymous summary — average, the five counts, the comments, no names; under
    RATE_SHOW of them, only how many."""
    mine = one(con, "SELECT score FROM event_ratings WHERE event_id = ? AND user_id = ?", e["id"], v.id) if v.student else None
    came = v.student and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", e["id"], v.id)
    out = {"myRating": mine["score"] if mine else None, "canRate": bool(came) and end_of(e) <= now() <= end_of(e) + RATE_FOR, "ratings": None}
    if head:
        rs = rows(con, "SELECT score, comment, created_at FROM event_ratings WHERE event_id = ? ORDER BY created_at DESC", e["id"])
        if 0 < len(rs) < RATE_SHOW:  # so few the club could tell who wrote what: the count alone (owner, Oct 17)
            out["ratings"] = {"avg": None, "count": len(rs), "dist": [], "comments": []}
        elif rs:
            out["ratings"] = {"avg": round(sum(r["score"] for r in rs) / len(rs), 1), "count": len(rs),
                              "dist": [sum(1 for r in rs if r["score"] == s) for s in range(1, 6)],
                              "comments": [{"score": r["score"], "body": r["comment"], "at": r["created_at"]} for r in rs if r["comment"]][:50]}
    return out


def rate_event(con, v: Viewer, eid: int, score: object, comment: object) -> dict:
    """One tap after the event (Oct 4, from the Luma review): only those checked in, from the end until 7 days later;
    changing one's mind is fine. Anonymous to the club."""
    need_student(v)
    e = _event(con, v, eid)
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        raise ApiError("bad_input")
    text = str(comment or "").strip()[:300]
    if not _rating_view(con, v, e, False)["canRate"]:
        raise ApiError("forbidden")
    con.execute("""INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_id, user_id) DO UPDATE SET score = excluded.score, comment = excluded.comment, created_at = excluded.created_at""",
                (eid, v.id, score, text, now()))
    return full(con, v, e)


def _ask_rating(con, uid: int, e: sqlite3.Row) -> None:
    """Checked in: an hour after the end the bot asks how it was (follows the reminders switch)."""
    notify(con, uid, "rate", f"rate:{e['id']}", after=end_of(e) + 3600)


INVITES_A_DAY = 30


def event_invites(con, v: Viewer, eid: int) -> list[dict]:
    """"Bring a friend" (§4.7): my friends and where each one stands with this event — to invite, invited by me, or
    going (only for those who show where they go, §3; the rest look invitable and the bot simply stays quiet)."""
    need_student(v)
    _event(con, v, eid)
    out = []
    for p in rows(con, PERSON + " WHERE u.id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)", v.id, v.id):
        going = p["show_going"] and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')", eid, p["id"])
        asked = one(con, "SELECT 1 FROM friend_invites WHERE from_id = ? AND to_id = ? AND event_id = ?", v.id, p["id"], eid)
        out.append({"person": person_ref(p), "state": "going" if going else "invited" if asked else "none"})
    rank = {"none": 0, "invited": 1, "going": 2}
    return sorted(out, key=lambda x: (rank[x["state"]], x["person"]["name"]))


def invite_friend(con, v: Viewer, eid: int, uid: object) -> list[dict]:
    """The bot brings my friend our card: "<name> invites you to <title>" + Open. Once per friend and event; public
    events that haven't started; 30 invites a day."""
    need_student(v)
    e = _event(con, v, eid)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid not in friend_ids(con, v.id):
        raise ApiError("forbidden")
    if e["status"] != "published" or e["starts_at"] <= now() or e["visibility"] != "public":
        raise ApiError("closed")
    if one(con, "SELECT COUNT(*) FROM friend_invites WHERE from_id = ? AND created_at > ?", v.id, now() - 86400)[0] >= INVITES_A_DAY:
        raise ApiError("rate_limited")
    if con.execute("INSERT OR IGNORE INTO friend_invites (from_id, to_id, event_id, created_at) VALUES (?, ?, ?, ?)", (v.id, uid, eid, now())).rowcount:
        notify(con, uid, "friend_invite", f"fi:{eid}:{v.id}")  # the bot skips it if they're already in by then
    return event_invites(con, v, eid)


ALBUM_EACH, ALBUM_TEAM, ALBUM_MAX = 10, 40, 300  # a guest's photos, the organizing team's (the photographer's set), all
ALBUM_FOR = 7 * 86400                            # photos are added from the start until a week after the end
PHOTO_REPORT_AT = 3                              # the third photo tells everyone who came (an hour after the end at the earliest)


def _album_view(con, v: Viewer, e: sqlite3.Row) -> dict:
    """The guests' album (Oct 4, from the Luma review). Students see it (guests don't: people's faces); who came adds
    photos, and so does the team; the one who added a photo or the club's Head+ take it out."""
    if not v.student:
        return {"photos": [], "canAddPhotos": False}
    head = can(con, v, e["org_id"], "events")
    ps = rows(con, f"""SELECT f.*, p.added_by, s.first_name, s.last_name, u.nick FROM event_photos p JOIN files f ON f.id = p.file_id
        LEFT JOIN users u ON u.id = p.added_by LEFT JOIN students s ON s.user_id = p.added_by WHERE p.event_id = ?
        AND f.id NOT IN (SELECT target_id FROM reports WHERE target = 'photo' AND status = 'open'
                         GROUP BY target_id HAVING COUNT(DISTINCT reporter_id) >= 2 OR SUM(reporter_id = ?) > 0)
        ORDER BY p.sort""", e["id"], v.id)
    by = lambda f: f["nick"] or (f"{f['first_name']} {f['last_name'][:1]}." if f["first_name"] else None)  # noqa: E731
    return {"photos": [{**media_shape(f), "canDelete": head or f["added_by"] == v.id, "by": by(f), "mine": f["added_by"] == v.id} for f in ps],
            "canAddPhotos": _album_room(con, v, e) > 0, "albumOpen": bool(e["album_open"])}


def _album_room(con, v: Viewer, e: sqlite3.Row) -> int:
    """How many more photos I may add to this event's album now."""
    if not v.student or e["status"] != "published" or not e["starts_at"] <= now() <= end_of(e) + ALBUM_FOR:
        return 0
    team = at_least(role_in(con, v, e["org_id"]), "member") or bool(e["co_org_id"] and at_least(role_in(con, v, e["co_org_id"]), "member"))
    if not team and (not e["album_open"] or not one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", e["id"], v.id)):
        return 0
    mine = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ? AND added_by = ?", e["id"], v.id)["n"]
    total = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ?", e["id"])["n"]
    return max(0, min((ALBUM_TEAM if team else ALBUM_EACH) - mine, ALBUM_MAX - total))


def can_add_album_photo(con, v: Viewer, eid: int) -> bool:
    return _album_room(con, v, _event(con, v, eid)) > 0


def add_album_photo(con, v: Viewer, eid: int, saved: dict) -> dict:
    e = _event(con, v, eid)
    if _album_room(con, v, e) <= 0:
        raise ApiError("forbidden")
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'event_photo' AND owner_id = ?", saved["sha256"], v.id)
    fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                     saved["path"], v.id, now(), saved["color"])).lastrowid
    con.execute("""INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by)
        VALUES (?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM event_photos WHERE event_id = ?), ?)""", (eid, fid, eid, v.id))
    if one(con, "SELECT COUNT(*) FROM event_photos WHERE event_id = ?", eid)[0] == PHOTO_REPORT_AT:  # the album has a story now
        for (uid,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL AND user_id != ?", eid, v.id):
            notify(con, uid, "photo_report", f"ph:{eid}", after=max(now(), end_of(e) + 3600))  # once per event (§7)
    return full(con, v, e)


def remove_album_photo(con, v: Viewer, eid: int, fid: int) -> dict:
    e = _event(con, v, eid)
    p = one(con, "SELECT added_by FROM event_photos WHERE event_id = ? AND file_id = ?", eid, fid)
    if not p:
        raise ApiError("not_found")
    if p["added_by"] != v.id and v.role != "admin" and not can(con, v, e["org_id"], "events"):
        raise ApiError("forbidden")
    con.execute("DELETE FROM event_photos WHERE event_id = ? AND file_id = ?", (eid, fid))
    return full(con, v, e)


UPDATES_A_DAY = 3


def post_update(con, v: Viewer, eid: int, body: str) -> list[dict]:
    """An organizer's update (Head+, Oct 4: "the entrance is round the side"): pinned under the event's title for everyone,
    and the bot tells the people going, holding a seat or waiting — with our template, never the organizer's words (§9).
    Three a day per event at most, so it stays news and never spam."""
    e = _staff_event(con, v, eid, "events")
    text = str(body or "").strip()
    if e["status"] != "published" or not 2 <= len(text) <= 300:
        raise ApiError("bad_input")
    if one(con, "SELECT COUNT(*) FROM event_updates WHERE event_id = ? AND created_at > ?", eid, now() - 86400)[0] >= UPDATES_A_DAY:
        raise ApiError("rate_limited")
    with tx(con):
        uid = con.execute("INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (?, ?, ?, ?)", (eid, v.id, text, now())).lastrowid
        for (who,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status IN ('going','hold','waitlist') AND user_id != ?", eid, v.id):
            notify(con, who, "event_update", f"upd:{uid}")
    return full(con, v, e)["updates"]


def delete_update(con, v: Viewer, eid: int, uid: int) -> None:
    _staff_event(con, v, eid, "events")
    if not con.execute("DELETE FROM event_updates WHERE id = ? AND event_id = ?", (uid, eid)).rowcount:
        raise ApiError("not_found")


UNDO = 600  # a check-in by name can be taken back this long (a wrong tap at the door)


def door(con, v: Viewer, eid: int) -> list[dict]:
    """The door list for check-in by name (Member+, like the scanner; §3: a Member sees short names only): who is going,
    the ones still to come first."""
    e = _staff_event(con, v, eid, "door")
    found = rows(con, f"""SELECT {PERSON_COLS}, r.checked_in_at, r.walk_in, r.checkin_manual FROM registrations r
        JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id WHERE r.event_id = ? AND r.status = 'going'""", eid)
    out = [{"person": _door_ref(p), "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"])} for p in found]
    if _team_door(e):  # §2b: everyone expected is on the list, answered or not
        rest = [u for u in _expected(con, e) if u not in {p["id"] for p in found}]
        out += [{"person": _door_ref(p), "checkedInAt": None, "walkIn": False, "manual": False}
                for p in (rows(con, PERSON + f" WHERE u.id IN ({_qs(rest)})", *rest) if rest else [])]
    return sorted(out, key=lambda a: (a["checkedInAt"] is not None, -(a["checkedInAt"] or 0), a["person"]["name"]))


def checkin_by_name(con, v: Viewer, eid: int, uid: int) -> dict:
    """No QR (a dead phone): a person going to the event is checked in by hand from the door list (§4.4). The same answer
    as the scanner; marked "by hand" for the organizer and the CSV."""
    with tx(con):
        e = _staff_event(con, v, eid, "door")
        t = now()
        if t < e["starts_at"] - DOOR_EARLY or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            return {"result": "closed"}
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if _team_door(e) and (not r or r["status"] != "going") and uid in _expected(con, e):  # §2b: came anyway
            if r:
                con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, walk_in = 1, updated_at = ? WHERE id = ?", (t, r["id"]))
            else:
                con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                            (eid, uid, _ticket_code(con), t, t))
            r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if not r:
            return {"result": "not_found"}
        if r["status"] != "going":
            return {"result": "cancelled"}
        if not r["checked_in_at"]:
            _came(con, e, uid, lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, checkin_manual = 1, updated_at = ? WHERE id = ?",
                                                  (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", uid)),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": one(con, "SELECT 1 FROM receipts WHERE registration_id = ? AND status = 'accepted' AND flags != '' AND reviewed_at IS NULL", r["id"]) is not None}


def undo_checkin(con, v: Viewer, eid: int, uid: int) -> None:
    """Take back a check-in by name made in the last 10 minutes (a scanned ticket stays: it proves the person came)."""
    _staff_event(con, v, eid, "door")
    cur = con.execute("""UPDATE registrations SET checked_in_at = NULL, checked_in_by = NULL, checkin_manual = 0, updated_at = ?
        WHERE event_id = ? AND user_id = ? AND checkin_manual = 1 AND checked_in_at > ?""", (now(), eid, uid, now() - UNDO))
    if not cur.rowcount:
        raise ApiError("conflict")


# ---------------------------------------------------------------- admin: clubs and their teams (pilot, SPEC §2)

def _admin(v: Viewer) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")


def create_org(con, actor: int | None, name: str, short: str, emoji: str, official: bool, slug: str | None = None,
               kind: str = "club") -> int:
    """A club or a school, by the admin (the app or the CLI). A school (owner, Oct 13: KBTU's own, a few, made by the
    admin, never by an application) is official from the start and never closes; its President has a club
    President's rights. A slug nobody chose becomes club<N>: deep links use ids anyway."""
    if slug is None:
        n = one(con, "SELECT COALESCE(MAX(id), 0) + 1 FROM orgs")[0]
        slug = next(s for s in (f"club{n + i}" for i in range(1000)) if not one(con, "SELECT 1 FROM orgs WHERE slug = ?", s))
    cur = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, official, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (slug, kind, name, short, emoji, int(official or kind == "school"), actor, now()))
    for rn, color, lv in OFFICIAL_ROLES:
        con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (?, ?, ?, ?, 1, ?)", (cur.lastrowid, rn, color, lv, now()))
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'org_create', ?, ?, ?)",
                (actor, f"org:{cur.lastrowid}", json.dumps({"name": name}), now()))
    return cur.lastrowid


OFFICIAL_ROLES = (("Vice", "#7C4DFF", "vice"), ("Head", "#3B6BFF", "head"))  # with the President: db migration 40


def _official(con, oid: int, level: str) -> int | None:
    """The club's fixed role of a level (Vice, Head), which a Vice or Head without a role name holds."""
    r = one(con, "SELECT id FROM org_roles WHERE org_id = ? AND fixed = 1 AND level = ?", oid, level)
    return r[0] if r else None


SCHOOLS_VERSION = "2"  # 2: the short names (SITE, ISE, KMA), owner Oct 14
SCHOOLS = json.loads((Path(__file__).with_name("i18n") / "schools.json").read_text(encoding="utf-8"))


def seed_schools(con, root: Path) -> None:
    """KBTU's schools from its site (kbtu.edu.kz/ru/shkoly, /kz/mektepter, /en/schools; owner Oct 14: "nobody should
    create them by hand"): once, at start under the migration lock, with their crests (kbtu/schools/<slug>.png) and
    names in three languages. A school made by hand before is found by its slug or any of its names and filled in."""
    done = one(con, "SELECT value FROM meta WHERE key = 'schools'")
    if done and done[0] == SCHOOLS_VERSION:
        return
    with tx(con):
        for s in SCHOOLS:
            names = {s[lang]["name"].lower() for lang in ("ru", "kk", "en")}
            o = next((o for o in rows(con, "SELECT * FROM orgs WHERE kind = 'school'") if o["slug"] == s["slug"] or o["name"].strip().lower() in names), None)
            if o is None:
                slug = s["slug"] if not one(con, "SELECT 1 FROM orgs WHERE slug = ?", s["slug"]) else None
                o = _org(con, create_org(con, None, s["ru"]["name"], s["short"], s["emoji"], True, slug, "school"))
            logo = o["logo_file_id"]
            if logo is None:
                saved = media.save((Path(__file__).with_name("schools") / f"{s['slug']}.png").read_bytes(), root)
                logo = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, created_at, color)
                    VALUES (?, 'org_logo', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                          saved["path"], now(), saved["color"])).lastrowid
            # a later version brings new translations (the short names, Oct 14) and leaves what the school typed
            tr = {"ru": {"abbr": s["ru"]["abbr"]}, **{k: s[k] for k in ("kk", "en")}}
            own = done and o["description"] != s["ru"]["description"]  # the school's own text: the AI translates it (ai.py), not the site's
            if own:
                tr = {k: {a: b for a, b in x.items() if a != "description"} for k, x in tr.items()}
            con.execute("UPDATE orgs SET i18n = ?, logo_file_id = ?, official = 1, lang = ? WHERE id = ?",
                        (json.dumps(tr, ensure_ascii=False), logo, None if own else "ru", o["id"]))
            if not done:
                con.execute("UPDATE orgs SET name = ?, description = ? WHERE id = ?", (s["ru"]["name"], s["ru"]["description"], o["id"]))
        con.execute("INSERT INTO meta (key, value) VALUES ('schools', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (SCHOOLS_VERSION,))


def set_role(con, actor: int | None, uid: int, oid: int, role: str, by: str) -> None:
    """One person's role in a club, by the admin (the app or the CLI). One president per club: the old one steps down
    to vice. A role counts once the person has signed in with KBTU (only students act, SPEC §2)."""
    if role not in (*RANK, "none"):
        raise ApiError("bad_input")
    with tx(con):
        if role == "president":
            con.execute("UPDATE org_members SET role = 'vice', role_id = ? WHERE org_id = ? AND role = 'president' AND user_id != ?", (_official(con, oid, "vice"), oid, uid))
        if role == "none":
            con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, uid))
        else:
            con.execute("""INSERT INTO org_members (org_id, user_id, role, joined_at, role_id) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (org_id, user_id) DO UPDATE SET role = excluded.role, role_id = excluded.role_id""", (oid, uid, role, now(), _official(con, oid, role)))
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'role_change', ?, ?, ?)",
                    (actor, f"user:{uid}", json.dumps({"org": oid, "role": role, "by": by}), now()))


def find_user(con, who: str) -> sqlite3.Row | None:
    """A Telegram account by @username or Telegram ID: the person must have opened the app once."""
    who = who.strip()
    if who.isdigit():
        return one(con, "SELECT * FROM users WHERE tg_id = ?", int(who))
    return one(con, "SELECT * FROM users WHERE lower(tg_username) = lower(?)", who.lstrip("@")) if who.lstrip("@") else None


def _admin_org(con, o: sqlite3.Row) -> dict:
    """A club as the admin sees it: the leaders (Telegram names only, as the CLI prints them) and the member count."""
    team = rows(con, """SELECT m.role, u.id, u.tg_username, u.tg_first_name, u.tg_last_name, s.user_id IS NOT NULL AS student
        FROM org_members m JOIN users u ON u.id = m.user_id LEFT JOIN students s ON s.user_id = u.id
        WHERE m.org_id = ? AND m.role != 'member'""", o["id"])
    return {**org_ref(con, o), "hidden": o["status"] == "hidden", "members": one(con, "SELECT COUNT(*) FROM org_members WHERE org_id = ?", o["id"])[0],
            "team": sorted(({"id": m["id"], "role": m["role"], "username": m["tg_username"], "name": f"{m['tg_first_name']} {m['tg_last_name']}".strip(),
                             "student": bool(m["student"])} for m in team), key=lambda m: (-RANK[m["role"]], m["name"]))}


def admin_orgs(con, v: Viewer) -> list[dict]:
    _admin(v)
    return [_admin_org(con, o) for o in rows(con, "SELECT * FROM orgs WHERE status != 'archived' ORDER BY id DESC")]


def admin_hide_org(con, v: Viewer, oid: int, hidden: bool) -> dict:
    """Hide a club, or bring it back: never a delete, so a lost phone can't wipe the clubs (owner, Oct 16). Hidden, it
    leaves the lists, search and its members' profiles, and its events and posts go with it; nothing is removed."""
    _admin(v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND status != 'archived'", oid)
    if not o:
        raise ApiError("not_found")
    with tx(con):
        con.execute("UPDATE orgs SET status = ? WHERE id = ?", ("hidden" if hidden else "active", oid))
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'org_hide', ?, ?, ?)",
                    (v.id, f"org:{oid}", json.dumps({"hidden": hidden}), now()))
    return _admin_org(con, one(con, "SELECT * FROM orgs WHERE id = ?", oid))


def admin_org_events(con, v: Viewer, oid: int) -> list[dict]:
    """A club's events for Admin's delete, each with what deleting it takes along (the confirm names it)."""
    _admin(v)
    return [{"id": e["id"], "title": e["title"], "status": e["status"], "startsAt": e["starts_at"], "people": e["people"],
             "came": e["came"], "paid": e["paid"], "photos": e["photos"]} for e in rows(con, """SELECT e.id, e.title, e.status, e.starts_at,
        (SELECT COUNT(*) FROM registrations WHERE event_id = e.id AND status != 'cancelled') AS people,
        (SELECT COUNT(*) FROM registrations WHERE event_id = e.id AND checked_in_at IS NOT NULL) AS came,
        (SELECT COUNT(*) FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = e.id) AS paid,
        (SELECT COUNT(*) FROM event_photos WHERE event_id = e.id) AS photos
        FROM events e WHERE e.org_id = ? ORDER BY COALESCE(e.starts_at, 0) DESC, e.id DESC""", oid)]


def admin_create_org(con, v: Viewer, body: dict) -> dict:
    _admin(v)
    name, short, emoji = str(body.get("name") or "").strip(), str(body.get("short") or "").strip().upper(), str(body.get("emoji") or "")
    # a school is never made by hand: KBTU's come from its site (seed_schools, owner Oct 14)
    if not (2 <= len(name) <= 60 and 1 <= len(short) <= 2 and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and body.get("kind", "club") == "club"):
        raise ApiError("bad_input")
    return _admin_org(con, _org(con, create_org(con, v.id, name, short, emoji, bool(body.get("official")))))


def admin_set_role(con, v: Viewer, oid: int, body: dict) -> dict:
    _admin(v)
    o = _org(con, oid)
    if not o:
        raise ApiError("not_found")
    u = find_user(con, str(body.get("who") or ""))
    if not u:
        raise ApiError("not_found", "who")
    set_role(con, v.id, u["id"], oid, str(body.get("role") or ""), "app")
    return _admin_org(con, o)


# ---------------------------------------------------------------- the club's own team (SPEC §2: the rank rule)

def team(con, v: Viewer, oid: int) -> list[dict]:
    """The full roster for the club's own team (§3): full names and @usernames, highest role first, with the club's own
    role name and the tags (§2b). Probation and strikes: for the club's Head+ and the person. Vice+ also see who
    hasn't been checked in at the club's events for 60 days, to keep the roster real (§4.13)."""
    mine = role_in(con, v, oid)
    if not mine:
        raise ApiError("forbidden")
    r = rights_of(con, v.id, oid)
    vice, head = "team" in r, "people" in r
    found = rows(con, f"""SELECT {PERSON_COLS}, u.tg_username, m.role, m.joined_at, m.role_id, m.probation, t.name AS title, t.color AS title_color,
        (SELECT MAX(r.checked_in_at) FROM registrations r JOIN events e ON e.id = r.event_id WHERE e.org_id = m.org_id AND r.user_id = u.id) AS seen,
        (SELECT COUNT(*) FROM strikes x WHERE x.org_id = m.org_id AND x.user_id = u.id AND x.cleared_at IS NULL) AS strikes,
        (SELECT group_concat(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id WHERE g.org_id = m.org_id AND mt.user_id = u.id) AS tags,
        (SELECT MIN(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id WHERE g.org_id = m.org_id AND mt.user_id = u.id AND g.department) AS dept
        FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id LEFT JOIN org_roles t ON t.id = m.role_id
        WHERE m.org_id = ?""", oid)
    return sorted(({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "username": p["tg_username"],
                    "role": p["role"], "roleId": p["role_id"], "title": p["title"], "titleColor": p["title_color"],
                    "tags": sorted(int(x) for x in (p["tags"] or "").split(",") if x), "dept": p["dept"], "joinedAt": p["joined_at"],
                    "quiet": vice and (p["seen"] or p["joined_at"]) < now() - QUIET_FOR,
                    **({"probation": bool(p["probation"]), "strikes": p["strikes"]} if head or p["id"] == v.id else {})}
                   for p in found), key=lambda m: (-RANK[m["role"]], m["fullName"]))


def _below(con, v: Viewer, oid: int, uid: int, right: str) -> str:
    """My role, if I may act on them: the right, and strictly above them by the rank rule (§2)."""
    mine = role_in(con, v, oid)
    theirs = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)
    if not theirs:
        raise ApiError("not_found")
    if not can(con, v, oid, right) or RANK[mine] <= RANK[theirs["role"]]:
        raise ApiError("forbidden")
    return mine


def dept_of(con, oid: int, uid: int) -> int | None:
    """Their department in the club: a tag marked department (one per person; several from before: the first)"""
    r = one(con, """SELECT MIN(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id
        WHERE g.org_id = ? AND mt.user_id = ? AND g.department = 1""", oid, uid)
    return r[0] if r else None


def _manage(con, v: Viewer, oid: int, uid: int) -> str:
    """My role, if the rank rule lets me manage them: Vice+, and strictly above them."""
    return _below(con, v, oid, uid, "team")


def _remove(con, actor: int, oid: int, uid: int, ban: bool, by: str) -> None:
    """Someone is out of the club: their tags, strikes and open removal requests there go too; banned, they can't come
    back by an application or the link until a Vice+ lifts it (§2b)."""
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, uid))
    con.execute("DELETE FROM member_tags WHERE user_id = ? AND tag_id IN (SELECT id FROM org_tags WHERE org_id = ?)", (uid, oid))
    con.execute("DELETE FROM strikes WHERE org_id = ? AND user_id = ?", (oid, uid))
    con.execute("UPDATE removal_requests SET status = 'done', decided_by = ?, decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'",
                (actor, now(), oid, uid))
    if ban:
        con.execute("INSERT OR REPLACE INTO org_bans (org_id, user_id, by_id, created_at) VALUES (?, ?, ?, ?)", (oid, uid, actor, now()))
        con.execute("UPDATE join_requests SET status = 'rejected', decided_by = ?, decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'",
                    (actor, now(), oid, uid))
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'role_change', ?, ?, ?)",
                (actor, f"user:{uid}", json.dumps({"org": oid, "role": "none", "by": by, **({"ban": True} if ban else {})}), now()))


def remove_member(con, v: Viewer, oid: int, uid: int) -> None:
    """Vice+ remove someone below them; anyone leaves by themselves, except the President, who hands the club over first."""
    if uid == v.id:
        r = role_in(con, v, oid)
        if not r:
            raise ApiError("not_found")
        if r == "president":
            raise ApiError("conflict", "president")
    else:
        _manage(con, v, oid, uid)
    with tx(con):
        _remove(con, v.id, oid, uid, False, "self" if uid == v.id else "team")


def transfer(con, v: Viewer, oid: int, uid: int) -> list[dict]:
    """Only the President hands the club over, to someone already in it; they become Vice (§2)."""
    if role_in(con, v, oid) != "president":
        raise ApiError("forbidden")
    if uid == v.id or not one(con, "SELECT 1 FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ? AND m.user_id = ?", oid, uid):
        raise ApiError("not_found")
    with tx(con):  # the club's own role names stay below the President: both start plain
        con.execute("UPDATE org_members SET role = 'vice', role_id = ? WHERE org_id = ? AND user_id = ?", (_official(con, oid, "vice"), oid, v.id))
        con.execute("UPDATE org_members SET role = 'president', role_id = NULL, probation = 0 WHERE org_id = ? AND user_id = ?", (oid, uid))
        con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'presidency_transfer', ?, ?, ?)",
                    (v.id, f"org:{oid}", json.dumps({"to": uid}), now()))
    return team(con, v, oid)


# ---------------------------------------------------------------- Team 2.0 (owner, Oct 5; SPEC §2b)
# A club's own roles are a name and colour on one of the levels, so every rights check stays on the level. Tags are
# groups of people. Probation: Head+ put someone below them on it and give strikes; the third strike asks the President
# or Vice to remove them. A Head asks to remove someone; a Vice+ removes at once; either may ban from coming back.

STRIKES_OUT = 3
STRIKE_REASONS = ("meeting", "event", "other")
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _named(body: dict) -> tuple[str, str]:
    name, color = " ".join(str(body.get("name") or "").split()), str(body.get("color") or "")
    if not (1 <= len(name) <= 24 and HEX.fullmatch(color)):
        raise ApiError("bad_input")
    return name, color


def team_setup(con, v: Viewer, oid: int) -> dict:
    """What Team needs besides the roster: the club's roles and tags (the whole team sees them), and for Vice+ the open
    removal requests (each says whether I outrank the person and so may decide) and the bans."""
    mine = role_in(con, v, oid)
    if not mine:
        raise ApiError("forbidden")
    out: dict = {
        "roles": [{"id": r["id"], "name": r["name"], "color": r["color"], "level": r["level"], "rights": _ordered(_rights_from(r["level"], r["rights"])),
                   "count": r["n"], "fixed": bool(r["fixed"])} for r in rows(con, """SELECT r.*,
            (SELECT COUNT(*) FROM org_members m WHERE m.role_id = r.id) AS n FROM org_roles r WHERE r.org_id = ?
            ORDER BY r.fixed DESC, r.fixed AND r.level = 'head', r.id""", oid)],
        "tags": [{"id": g["id"], "name": g["name"], "color": g["color"], "count": g["n"], "department": bool(g["department"])} for g in rows(con, """SELECT g.*,
            (SELECT COUNT(*) FROM member_tags mt JOIN org_members m ON m.user_id = mt.user_id AND m.org_id = g.org_id WHERE mt.tag_id = g.id) AS n
            FROM org_tags g WHERE g.org_id = ? ORDER BY g.id""", oid)],
        "myDept": dept_of(con, oid, v.id),
    }
    if can(con, v, oid, "team"):
        asks = rows(con, f"""SELECT q.*, m.role, {PERSON_COLS} FROM removal_requests q JOIN org_members m ON m.org_id = q.org_id AND m.user_id = q.user_id
            JOIN users u ON u.id = q.user_id JOIN students s ON s.user_id = u.id WHERE q.org_id = ? AND q.status = 'pending' ORDER BY q.id""", oid)
        by = {b["id"]: b for b in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(asks))})", *[a["by_id"] for a in asks])} if asks else {}
        out["removals"] = [{"id": a["id"], "person": person_ref(a), "fullName": f"{a['last_name']} {a['first_name']}".strip(),
                            "by": person_ref(by[a["by_id"]]) if a["by_id"] in by else None, "ban": bool(a["ban"]), "note": a["note"],
                            "strikes": one(con, "SELECT COUNT(*) FROM strikes WHERE org_id = ? AND user_id = ? AND cleared_at IS NULL", oid, a["user_id"])[0],
                            "at": a["created_at"], "canDecide": RANK[mine] > RANK[a["role"]]} for a in asks]
        out["bans"] = [{"person": person_ref(b), "fullName": f"{b['last_name'] or ''} {b['first_name'] or ''}".strip() or short_name(b), "at": b["created_at"]}
                       for b in rows(con, f"""SELECT {PERSON_COLS}, x.created_at FROM org_bans x JOIN users u ON u.id = x.user_id
                           LEFT JOIN students s ON s.user_id = u.id WHERE x.org_id = ? ORDER BY x.created_at DESC""", oid)]
    return out


def _ordered(rights) -> list[str]:
    return [r for r in RIGHTS if r in rights]


def save_role(con, v: Viewer, oid: int, body: dict, rid: int | None = None) -> dict:
    """Whoever runs the team ("team") makes the club's own roles: a name, a colour and toggles of rights (SPEC §2), only
    rights they have themselves and below their own level (the rights' highest level is the role's); a changed level
    moves everyone holding the role (they are all below the editor). A `level` alone (an older app) means its rights.
    The official Vice and Head (`fixed`) keep their name and level."""
    mine = role_in(con, v, oid)
    if not can(con, v, oid, "team"):
        raise ApiError("forbidden")
    name, color = _named(body)
    rights = body["rights"] if "rights" in body else list(LEVEL_RIGHTS[body["level"]]) if body.get("level") in ("member", "head", "vice") else None
    if not isinstance(rights, list) or any(r not in RIGHTS for r in rights):
        raise ApiError("bad_input")
    rights = _ordered(rights)
    level = max((RIGHTS[r] for r in rights), key=RANK.__getitem__, default="member")
    if RANK[level] >= RANK[mine] or not set(rights) <= rights_of(con, v.id, oid):
        raise ApiError("forbidden")
    with tx(con):
        if rid is None:
            if one(con, "SELECT COUNT(*) FROM org_roles WHERE org_id = ?", oid)[0] >= 20:
                raise ApiError("conflict", "many")
        else:
            r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid)
            if not r:
                raise ApiError("not_found")
            if RANK[r["level"]] >= RANK[mine] or r["fixed"] and RANK[level] > RANK[r["level"]]:
                raise ApiError("forbidden")
            if r["fixed"]:  # an official role keeps its name and level; its rights below the level may be tuned
                name, level = r["name"], r["level"]
        try:
            if rid is None:
                con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (oid, name, color, level, ",".join(rights), now()))
            else:
                con.execute("UPDATE org_roles SET name = ?, color = ?, level = ?, rights = ? WHERE id = ?", (name, color, level, ",".join(rights), rid))
                con.execute("UPDATE org_members SET role = ? WHERE org_id = ? AND role_id = ?", (level, oid, rid))
        except sqlite3.IntegrityError:
            raise ApiError("conflict", "taken") from None
    return team_setup(con, v, oid)


def delete_role(con, v: Viewer, oid: int, rid: int) -> dict:
    """A role goes; whoever held it keeps the level and its rights, without the name."""
    mine = role_in(con, v, oid)
    r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid)
    if not can(con, v, oid, "team"):
        raise ApiError("forbidden")
    if not r:
        raise ApiError("not_found")
    if RANK[r["level"]] >= RANK[mine] or r["fixed"]:
        raise ApiError("forbidden")
    con.execute("DELETE FROM org_roles WHERE id = ?", (rid,))
    return team_setup(con, v, oid)


def save_tag(con, v: Viewer, oid: int, body: dict, tid: int | None = None) -> dict:
    """Head+ make the club's tags (SMM, Design, ...): a name and a colour; `department` marks it a department (PLAN 47:
    one per person, Team groups by it). Unmarking leaves the people tagged."""
    _may(con, v, oid, "people")
    name, color = _named(body)
    dept = body.get("department")
    if dept is not None and not isinstance(dept, bool):
        raise ApiError("bad_input")
    was = one(con, "SELECT department FROM org_tags WHERE id = ? AND org_id = ?", tid, oid) if tid is not None else None
    if dept is not None and bool(dept) != bool(was and was[0]) and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
        raise ApiError("forbidden")  # a Head unmarking a department would sidestep its rules (review): Vice+ only
    with tx(con):
        if tid is None and one(con, "SELECT COUNT(*) FROM org_tags WHERE org_id = ?", oid)[0] >= 30:
            raise ApiError("conflict", "many")
        if tid is not None and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ?", tid, oid):
            raise ApiError("not_found")
        try:
            if tid is None:
                con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, ?, ?, ?, ?)", (oid, name, color, int(bool(dept)), now()))
            else:
                con.execute("UPDATE org_tags SET name = ?, color = ?, department = COALESCE(?, department) WHERE id = ?",
                            (name, color, None if dept is None else int(dept), tid))
        except sqlite3.IntegrityError:
            raise ApiError("conflict", "taken") from None
    return team_setup(con, v, oid)


def delete_tag(con, v: Viewer, oid: int, tid: int) -> dict:
    _may(con, v, oid, "people")
    if not con.execute("DELETE FROM org_tags WHERE id = ? AND org_id = ?", (tid, oid)).rowcount:
        raise ApiError("not_found")
    return team_setup(con, v, oid)


def update_member(con, v: Viewer, oid: int, uid: int, body: dict) -> list[dict]:
    """One person in Team (§2b), only what is sent: `role` (a level) or `roleId` (one of the club's roles; null: just the
    level) — Vice+ by the rank rule, and on myself one of the club's roles at my own level (a name, no more rights: owner,
    Oct 12); `tags` — Head+ on themselves or anyone below them, Vice+ on anyone (labels, no power: owner, Oct 12, the
    President and the Vice tag each other; departments in it are left as they are); `dept` — the department (a tag
    marked so) or null for none (PLAN 47): Vice+ on anyone; a Head on those below them, only into or out of the Head's
    own department, never their own; `probation` — Head+ put someone
    below them on it, only the President or Vice take it off (passed: the strikes go, the bot congratulates)."""
    if not body or not set(body) <= {"role", "roleId", "tags", "dept", "probation"}:
        raise ApiError("bad_input")
    with tx(con):
        if "role" in body or "roleId" in body:
            rid = body.get("roleId")
            mine = role_in(con, v, oid) if uid == v.id and rid is not None else _manage(con, v, oid, uid)
            if not mine:
                raise ApiError("forbidden")
            if rid is not None:
                r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid) if isinstance(rid, int) and not isinstance(rid, bool) else None
                if not r:
                    raise ApiError("bad_input")
                role, given = r["level"], _rights_from(r["level"], r["rights"])
            else:
                role = str(body.get("role") or "")
                if role not in RANK:
                    raise ApiError("bad_input")
                given = LEVEL_RIGHTS[role]
                rid = _official(con, oid, role)  # a Vice or Head level is its official role (owner, Oct 15)
                if rid:
                    given = _rights_from(role, one(con, "SELECT rights FROM org_roles WHERE id = ?", rid)[0])
            if (RANK[role] != RANK[mine] if uid == v.id else RANK[role] >= RANK[mine]) or not given <= rights_of(con, v.id, oid):  # only rights I have myself (as in Telegram)
                raise ApiError("forbidden")
            con.execute("UPDATE org_members SET role = ?, role_id = ? WHERE org_id = ? AND user_id = ?", (role, rid, oid, uid))
            con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'role_change', ?, ?, ?)",
                        (v.id, f"user:{uid}", json.dumps({"org": oid, "role": role, "roleId": rid, "by": "team"}), now()))
        if "tags" in body:
            tags = body["tags"]
            if uid != v.id and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
                _below(con, v, oid, uid, "people")
            elif not can(con, v, oid, "people") or not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
                raise ApiError("forbidden")
            if not isinstance(tags, list) or len(tags) > 10 or any(not isinstance(x, int) or isinstance(x, bool) for x in tags):
                raise ApiError("bad_input")
            if len(set(tags)) != one(con, f"SELECT COUNT(*) FROM org_tags WHERE org_id = ? AND id IN ({','.join('?' * len(set(tags))) or 'NULL'})", oid, *set(tags))[0]:
                raise ApiError("bad_input")
            depts = {r[0] for r in rows(con, "SELECT id FROM org_tags WHERE org_id = ? AND department = 1", oid)}
            con.execute("DELETE FROM member_tags WHERE user_id = ? AND tag_id IN (SELECT id FROM org_tags WHERE org_id = ? AND department = 0)", (uid, oid))
            con.executemany("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", [(t, uid) for t in set(tags) - depts])
        if "dept" in body:
            d = body["dept"]
            depts = {r[0] for r in rows(con, "SELECT id FROM org_tags WHERE org_id = ? AND department = 1", oid)}
            if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d not in depts):
                raise ApiError("bad_input")
            if RANK[role_in(con, v, oid) or "member"] >= RANK["vice"]:
                if not can(con, v, oid, "people") or not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
                    raise ApiError("forbidden")
            else:  # a Head: their own department's people only, and not themselves
                if uid == v.id:
                    raise ApiError("forbidden")
                _below(con, v, oid, uid, "people")
                own = dept_of(con, oid, v.id)
                if own is None or dept_of(con, oid, uid) not in (None, own) or d not in (None, own):
                    raise ApiError("forbidden")
            gone = depts if RANK[role_in(con, v, oid) or "member"] >= RANK["vice"] else {own}  # a Head touches their own only
            con.execute(f"DELETE FROM member_tags WHERE user_id = ? AND tag_id IN ({','.join('?' * len(gone)) or 'NULL'})", (uid, *gone))
            if d is not None:
                con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (d, uid))
        if "probation" in body:
            on = body["probation"]
            if not isinstance(on, bool):
                raise ApiError("bad_input")
            _below(con, v, oid, uid, "people" if on else "team")
            was = one(con, "SELECT probation FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["probation"]
            con.execute("UPDATE org_members SET probation = ? WHERE org_id = ? AND user_id = ?", (int(on), oid, uid))
            if was and not on:
                con.execute("UPDATE strikes SET cleared_at = ?, cleared_by = ? WHERE org_id = ? AND user_id = ? AND cleared_at IS NULL", (now(), v.id, oid, uid))
                con.execute("""UPDATE removal_requests SET status = 'declined', decided_by = ?, decided_at = ?
                    WHERE org_id = ? AND user_id = ? AND status = 'pending' AND by_id IS NULL""", (v.id, now(), oid, uid))
                notify(con, uid, "probation_passed", f"pp:{oid}:{now() // 86400}")
    return team(con, v, oid)


def _ask_removal(con, oid: int, uid: int, by: int | None, ban: bool, note: str) -> None:
    """A removal request (one open per person; a second ask joins it, a ban asked for sticks), and a bot message to
    every President and Vice who outranks the person."""
    con.execute("""INSERT INTO removal_requests (org_id, user_id, by_id, ban, note, created_at) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (org_id, user_id) WHERE status = 'pending' DO UPDATE SET ban = max(ban, excluded.ban)""", (oid, uid, by, int(ban), note, now()))
    rid = one(con, "SELECT id FROM removal_requests WHERE org_id = ? AND user_id = ? AND status = 'pending'", oid, uid)["id"]
    theirs = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["role"]
    for m in rows(con, "SELECT user_id, role FROM org_members WHERE org_id = ? AND role IN ('vice', 'president') AND user_id != ?", oid, by or 0):
        if RANK[m["role"]] > RANK[theirs]:
            notify(con, m["user_id"], "removal_ask", f"rm:{rid}")


def add_strike(con, v: Viewer, oid: int, uid: int, body: dict) -> list[dict]:
    """Head+ give a strike to someone below them who is on probation (§2b): why (a missed meeting, a missed important
    event, or something else said in the note). The bot tells them "n of 3"; the third asks the President and Vice."""
    reason, note = str(body.get("reason") or ""), " ".join(str(body.get("note") or "").split())
    meeting = body.get("eventId")  # from a meeting's answers (§2b): that meeting, missed, once
    if reason not in STRIKE_REASONS or len(note) > 140 or (reason == "other" and not note) \
            or meeting is not None and (reason != "meeting" or not isinstance(meeting, int) or isinstance(meeting, bool)):
        raise ApiError("bad_input")
    with tx(con):
        _below(con, v, oid, uid, "people")
        if not one(con, "SELECT probation FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["probation"]:
            raise ApiError("conflict", "probation")
        if meeting is not None:
            e = one(con, "SELECT * FROM events WHERE id = ? AND org_id = ? AND meeting = 1 AND status = 'published'", meeting, oid)
            if not e or end_of(e) > now() or uid not in _expected(con, e):
                raise ApiError("bad_input")
            if one(con, "SELECT 1 FROM strikes WHERE event_id = ? AND user_id = ?", meeting, uid):
                raise ApiError("conflict", "struck")
            if one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", meeting, uid):
                raise ApiError("conflict", "came")
            note = note or e["title"]
        sid = con.execute("INSERT INTO strikes (org_id, user_id, reason, note, by_id, created_at, event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (oid, uid, reason, note, v.id, now(), meeting)).lastrowid
        notify(con, uid, "strike", f"st:{sid}")
        if one(con, "SELECT COUNT(*) FROM strikes WHERE org_id = ? AND user_id = ? AND cleared_at IS NULL", oid, uid)[0] >= STRIKES_OUT:
            _ask_removal(con, oid, uid, None, False, "")
    return team(con, v, oid)


def strikes(con, v: Viewer, oid: int, uid: int) -> list[dict]:
    """A person's strikes in the club, newest first, cleared ones too: for them and the club's Head+."""
    if uid != v.id and not can(con, v, oid, "people"):
        raise ApiError("forbidden")
    if not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
        raise ApiError("not_found")
    found = rows(con, "SELECT * FROM strikes WHERE org_id = ? AND user_id = ? ORDER BY id DESC", oid, uid)
    by = {p["id"]: p for p in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(found))})", *[x["by_id"] for x in found])} if found else {}
    return [{"id": x["id"], "reason": x["reason"], "note": x["note"], "at": x["created_at"], "by": person_ref(by[x["by_id"]]) if x["by_id"] in by else None,
             "clearedAt": x["cleared_at"]} for x in found]


def clear_strike(con, v: Viewer, sid: int) -> None:
    """A Vice+ above them clears a strike ("made up for it"); below three, the app's own removal request closes."""
    x = one(con, "SELECT * FROM strikes WHERE id = ?", sid)
    if not x:
        raise ApiError("not_found")
    with tx(con):
        _below(con, v, x["org_id"], x["user_id"], "team")
        con.execute("UPDATE strikes SET cleared_at = ?, cleared_by = ? WHERE id = ? AND cleared_at IS NULL", (now(), v.id, sid))
        if one(con, "SELECT COUNT(*) FROM strikes WHERE org_id = ? AND user_id = ? AND cleared_at IS NULL", x["org_id"], x["user_id"])[0] < STRIKES_OUT:
            con.execute("""UPDATE removal_requests SET status = 'declined', decided_by = ?, decided_at = ?
                WHERE org_id = ? AND user_id = ? AND status = 'pending' AND by_id IS NULL""", (v.id, now(), x["org_id"], x["user_id"]))


def remove(con, v: Viewer, oid: int, uid: int, body: dict) -> dict:
    """Removing someone below me (§2b): a Vice+ does it at once, banned too if asked; a Head's tap is a request the
    President or Vice decide. {done}: whether they are out already."""
    ban, note = body.get("ban", False), " ".join(str(body.get("note") or "").split())
    if not isinstance(ban, bool) or len(note) > 140:
        raise ApiError("bad_input")
    with tx(con):
        _below(con, v, oid, uid, "people")
        if can(con, v, oid, "team"):
            _remove(con, v.id, oid, uid, ban, "team")
            return {"done": True}
        _ask_removal(con, oid, uid, v.id, ban, note)
    return {"done": False}


def decide_removal(con, v: Viewer, rid: int, approve: object) -> None:
    """The President or a Vice who outranks the person answers a removal request."""
    if not isinstance(approve, bool):
        raise ApiError("bad_input")
    q = one(con, "SELECT * FROM removal_requests WHERE id = ?", rid)
    if not q:
        raise ApiError("not_found")
    with tx(con):
        if one(con, "SELECT status FROM removal_requests WHERE id = ?", rid)["status"] != "pending":
            raise ApiError("conflict")  # another Vice answered first
        _below(con, v, q["org_id"], q["user_id"], "team")
        if approve:
            _remove(con, v.id, q["org_id"], q["user_id"], bool(q["ban"]), "request")
        else:
            con.execute("UPDATE removal_requests SET status = 'declined', decided_by = ?, decided_at = ? WHERE id = ?", (v.id, now(), rid))


def unban(con, v: Viewer, oid: int, uid: int) -> None:
    _may(con, v, oid, "team")
    if not con.execute("DELETE FROM org_bans WHERE org_id = ? AND user_id = ?", (oid, uid)).rowcount:
        raise ApiError("not_found")


def banned(con, oid: int, uid: int) -> bool:
    return one(con, "SELECT 1 FROM org_bans WHERE org_id = ? AND user_id = ?", oid, uid) is not None


# ---------------------------------------------------------------- invite links (§4.5: Vice+, one person, 48 h → instant Member)

INVITE_TTL = 2 * 86400


def invite(con, v: Viewer, oid: int, dept: object = None) -> dict:
    """A fresh member link for one person (owner, Oct 14: sent in a DM, so it needn't live long; one that went
    somewhere it shouldn't lets in one person at most). 96 random bits. `dept`: the department the newcomer lands in;
    below Vice, only one's own."""
    _may(con, v, oid, "team")
    if dept is not None:
        if not isinstance(dept, int) or isinstance(dept, bool) or not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", dept, oid):
            raise ApiError("bad_input")
        if RANK[role_in(con, v, oid) or "member"] < RANK["vice"] and dept != dept_of(con, oid, v.id):
            raise ApiError("forbidden", "dept")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO org_invites (token, org_id, role, created_by, created_at, expires_at, dept_id) VALUES (?, ?, 'member', ?, ?, ?, ?)",
                (token, oid, v.id, now(), now() + INVITE_TTL, dept))
    return {"token": token}


PRESIDENT_LINK_TTL = 7 * 86400


def president_link(con, v: Viewer, oid: int) -> dict:
    """The admin makes a new club's President with a link (§2): one person, once, within 7 days — no need for them to
    have opened the app before. A new link ends the unused old one."""
    _admin(v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND kind IN ('club', 'school', 'council') AND status = 'active'", oid)
    if not o:
        raise ApiError("not_found")
    token = secrets.token_hex(12)
    with tx(con):
        con.execute("UPDATE org_invites SET revoked_at = ? WHERE org_id = ? AND role = 'president' AND used_by IS NULL AND revoked_at IS NULL", (now(), oid))
        con.execute("INSERT INTO org_invites (token, org_id, role, created_by, created_at, expires_at) VALUES (?, ?, 'president', ?, ?, ?)",
                    (token, oid, v.id, now(), now() + PRESIDENT_LINK_TTL))
        con.execute("INSERT INTO audit_log (actor_id, action, target, at) VALUES (?, 'president_link', ?, ?)", (v.id, f"org:{oid}", now()))
    return {"token": token, "expiresAt": now() + PRESIDENT_LINK_TTL}


def accept_invite(con, v: Viewer, token: str) -> dict:
    """A student opens a club's one-time link. A member link: a Member at once, no application (a pending one is settled
    by it). A President link (the admin's): they lead the club, the old President steps down to Vice."""
    need_student(v)
    r = one(con, "SELECT * FROM org_invites WHERE token = ? AND revoked_at IS NULL", token)
    o = _org(con, r["org_id"]) if r else None
    if not o or o["status"] != "active" or r["used_by"] or (r["expires_at"] or 0) < now():
        raise ApiError("not_found")   # every link is one person's, once; the old reusable ones (no expiry) are dead
    member = r["role"] == "member"
    if member and banned(con, o["id"], v.id):
        raise ApiError("forbidden", "banned")
    if member and one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", o["id"], v.id):
        return org_shape(con, v, o)   # already in: the link stays for the one it was meant for
    with tx(con):
        if not con.execute("UPDATE org_invites SET used_by = ? WHERE token = ? AND used_by IS NULL", (v.id, token)).rowcount:
            raise ApiError("not_found")
        if member:
            con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (o["id"], v.id, now()))
            if r["dept_id"] and dept_of(con, o["id"], v.id) is None:
                con.execute("INSERT OR IGNORE INTO member_tags (tag_id, user_id) SELECT id, ? FROM org_tags WHERE id = ? AND department = 1", (v.id, r["dept_id"]))
        else:
            set_role(con, r["created_by"], v.id, o["id"], "president", "link")
        con.execute("UPDATE join_requests SET status = 'accepted', decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'", (now(), o["id"], v.id))
    return org_shape(con, v, o)


# ---- indoor routes (PLAN item 22): the graph the owner edits on the map; the app finds the ways over it ----
MAP_DRAFT = Path(__file__).with_name("map_graph.json")  # Claude's graph from UNI-Q's plans, the only one (owner, Oct 16: the
# editor is off, his saves were by accident; the old map_graph table's row is ignored)


def map_graph(con) -> dict:
    return {**json.loads(MAP_DRAFT.read_text()), "ver": 0}
