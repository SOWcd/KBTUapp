"""The ground every rule stands on: the caller, errors, the clock, queries, rights; and the shapes the app gets (web/src/lib/api/types.ts)."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass


HOLD = 30 * 60          # an unpaid seat waits 30 min for the receipt (§4.3)
log = logging.getLogger("kbtu.logic")
NO_END = 3 * 3600       # an event without an end counts as 3 h long
DOOR_EARLY = 3 * 3600   # check-in opens 3 h before the start (§4.4) …
DOOR_LATE = 6 * 3600    # … and, without an end, closes 6 h after the start
RANK = {"member": 1, "head": 2, "vice": 3, "president": 4}
# A club role's rights (SPEC §2): the toggles of its editor. Each needs a level; the
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

    def __init__(self, code: str, message: str = "", extra: dict | None = None):
        super().__init__(code)
        self.code, self.message, self.extra = code, message, extra or {}

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


def log_action(con, actor: int | None, action: str, target: str, data: str = "{}") -> None:
    """A line of the audit log, now: who (None: the app itself), what, on what ('user:5'), the details as JSON."""
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, ?, ?, ?, ?)", (actor, action, target, data, now()))


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

# the Student Government: a mark "Student Government" and first in lists, no rights beyond any club's
GOV_SLUG = "studentgovernment"


def org_ref(con, o: sqlite3.Row, files: dict | None = None) -> dict:
    """A club wherever it shows: its mark is its uploaded logo, or else its emoji on its cover. `files`: the logos
    already read (_by_id), when building a list."""
    logo = media_shape(files[o["logo_file_id"]]) if files and o["logo_file_id"] in files else photo(con, o["logo_file_id"])
    return {"id": o["id"], "slug": o["slug"], "name": o["name"], "short": o["short"], "abbr": o["abbr"],
            "emoji": o["emoji"], "cover": o["cover"], "kind": o["kind"], "official": bool(o["official"]), "logo": logo["thumb"] if logo else None,
            **({"gov": True} if o["slug"] == GOV_SLUG else {}),
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
    """A club role's toggles, else its level's; the door is every member's, not a toggle."""
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
               " u.role AS platform_role,"  # aliased: lists join a club role as `role`
               " CASE WHEN u.avatar_tg = 0 THEN (SELECT path FROM files WHERE id = u.avatar_file_id) END AS own_photo")
PERSON = f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id"


def short_name(p: sqlite3.Row) -> str:
    """"Alikhan S." for students (§3), the Telegram first name otherwise."""
    if p["first_name"]:
        return f"{p['first_name']} {p['last_name'][:1] + '.' if p['last_name'] else ''}".strip()
    return p["tg_first_name"] or "?"


def shown_name(p: sqlite3.Row) -> str:
    """The name everyone sees: the nickname when there is one. Organizers get the real one too: the
    `fullName` of their lists, the door's `realName`."""
    return p["nick"] or short_name(p)


def avatar_of(p: sqlite3.Row) -> str | None:
    """My own photo while the "Photo from Telegram" switch is off, else Telegram's (refreshed on every open)."""
    return f"media/{p['own_photo']}.t.webp" if p["own_photo"] else p["tg_photo_url"]


def person_ref(p: sqlite3.Row) -> dict:
    # A9: the app's moderators and admins carry a badge everyone sees, like the founder's
    staff = p["platform_role"] if "platform_role" in p.keys() and p["platform_role"] in ("admin", "moderator") else None
    return {"id": p["id"], "name": shown_name(p), "nick": p["nick"], "avatar": avatar_of(p), "founder": bool(p["is_founder"]), "mark": p["mark"], "staff": staff}


def _door_ref(p: sqlite3.Row) -> dict:
    """The door checks the real name beside a nick, the short one a Member may see (§3)."""
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


def course_of(sid: str | None, t: int | None = None) -> int | None:
    """The year of study from the student ID: 24B031234 entered in 2024, the academic year turning on September 1
    (Almaty); 1 to 6 (an ID handed out in August for the coming intake is a 1st year already). None for an ID without
    that shape (staff, an admin's own marks)."""
    m = re.match(r"(\d{2})[A-Z]", sid or "")
    if not m:
        return None
    n = academic_year(t) - (2000 + int(m.group(1))) + 1
    return None if n < 0 else max(1, min(course_cap(sid), n))  # an ID from a year still ahead is made up (the coming intake's: 0 -> 1)


def course_cap(sid: str | None) -> int:
    """The last year of the degree the ID's letter names: B bachelor 4, M master 2; any other letter 6.
    Nobody is ever marked graduated: the app can't know (repeaters, leave), so the year stops at the last one."""
    m = re.match(r"\d{2}([A-Z])", sid or "")
    return {"B": 4, "M": 2}.get(m.group(1) if m else "", 6)


def academic_year(t: int | None = None) -> int:
    """2026 from September 1, 2026 to August 31, 2027 (Almaty)."""
    d = time.gmtime((now() if t is None else t) + 5 * 3600)
    return d.tm_year if d.tm_mon >= 9 else d.tm_year - 1


def course_day(con) -> None:
    """Daily, so on September 1 (Almaty): every year of study a year on, up to the degree's last (course_cap; a
    stored year already past it, the portal's, is never lowered). A course was right for
    course_year, or else for the academic year it was written in (synced_at; an August ID of the coming intake: its own
    year). Moved on, not re-read from the ID: the portal's years stay (a repeater's ID is older than their year)."""
    if not _once(con, "course_day", str((now() + 5 * 3600) // 86400)):
        return
    ay = academic_year()
    for r in rows(con, "SELECT user_id, student_id, course, course_year, synced_at FROM students WHERE course IS NOT NULL"):
        m = re.match(r"(\d{2})[A-Z]", r["student_id"])
        since = r["course_year"] or max(academic_year(r["synced_at"]), 2000 + int(m.group(1)) if m else 0)
        if since < ay:
            con.execute("UPDATE students SET course = ?, course_year = ? WHERE user_id = ?", (min(max(course_cap(r["student_id"]), r["course"]), r["course"] + ay - since), ay, r["user_id"]))


def _free_seat(con, e: sqlite3.Row, uid: int) -> bool:
    """Whether this person gets one of the event's free seats: a 1st-year bachelor (a B after the year in the ID; masters have no such seats) while some are left."""
    return bool(e["price"] and e["free_first"] and free_taken(con, e["id"]) < e["free_first"]
                and one(con, "SELECT 1 FROM students WHERE user_id = ? AND course = 1 AND student_id GLOB '[0-9][0-9]B*'", uid))


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
    few hundred events was 1200 queries and the slowest call of the app's start (load test)."""
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
            "firstYear": bool(e["first_year"]), "needsPhone": bool(e["needs_phone"]), "needsVolunteers": e["volunteers"], "externalUrl": e["external_url"], "price": e["price"], "my": my, "visibility": e["visibility"],
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
    c = card(con, v, e)
    # the treasurer's Kaspi name and phone: only to who pays (a held or taken seat) and the club's team, never to all
    pay = head or can(con, v, e["org_id"], "money") or (c["my"] or {}).get("status") in ("hold", "going")
    return {**c, **({"i18n": json.loads(e["i18n"])} if e["i18n"] else {}), "description": e["description"],
            "payToName": e["pay_to_name"] if pay else None, "payPhone": e["pay_phone"] if pay else None, "meetingTag": e["meeting_tag"],
            "memo": json.loads(e["memo"]) if head and e["memo"] else None,
            "badgeName": e["badge_name"], **_album_view(con, v, e), "commentsOn": bool(e["comments_on"]),
            "discuss": e["channel_link"] if e["comments_on"] else None,  # its post's comments in Telegram (the talk is there)
            "comments": one(con, "SELECT COUNT(*) FROM comments WHERE event_id = ? AND deleted_at IS NULL", e["id"])[0],
            "updates": [{"id": u["id"], "body": u["body"], "at": u["created_at"], "canDelete": head}
                        for u in rows(con, "SELECT * FROM event_updates WHERE event_id = ? ORDER BY created_at DESC, id DESC LIMIT 10", e["id"])],
            **_rating_view(con, v, e, head), "volunteers": _volunteers_view(con, v, e, head),
            "chat": e["chat_link"] if e["chat_link"] and _chat_ok(con, e, v.id) else None, "chatLinked": bool(e["chat_id"]) if head else None,
            "wideVideo": video_shape(x) if (x := one(con, "SELECT * FROM videos WHERE id = ?", e["wide_video_id"])) and (head or x["status"] == "ready") else None,
            # the editor sees its video while it is still being compressed (or why it failed)
            **({"video": video_shape(x)} if head and (x := one(con, "SELECT * FROM videos WHERE id = ?", e["video_id"])) else {})}


def _once(con, key: str, value: str) -> bool:
    """True the first time a periodic job runs for `value` (a week, a day): the bot's rounds come every few seconds."""
    if one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, value):
        return False
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
    return True


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from .clubs import org, orgs  # noqa: E402
from .organizing import _album_view, _rating_view  # noqa: E402
from .oversight import staff  # noqa: E402
from .profiles import friends  # noqa: E402
from .queues import video_shape  # noqa: E402
from .seats import _chat_ok, _volunteers_view, ics_sig  # noqa: E402
