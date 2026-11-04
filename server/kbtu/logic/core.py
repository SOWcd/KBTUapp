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
# typed in by the student: a name in any alphabet (hyphen, apostrophe, space), and a student ID like 24B031234 or a
# master's 26MD1234 (year, a degree letter and 5-7 digits, or two letters and 4-7: the registrar's masters); ASCII digits only
NAME = re.compile(r"[^\W\d_](?:[^\W\d_]|[-' ]){0,39}")
_LAT = "A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f"  # Latin letters, accented too (U+00D7 and U+00F7 are signs)
LATIN_NAME = re.compile(f"[{_LAT}](?:[{_LAT}]|[-' ]){{0,39}}")  # the Latin name columns (My data)
STUDENT_ID = re.compile(r"\d{2}(?:[A-Z]\d{5,7}|[A-Z]{2}\d{4,7})", re.ASCII)  # a fullwidth digit would clone a real ID


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


def titled(r, key: str = "title") -> dict:
    """A club role's name and its Kazakh and English ones (the app picks by its language, roleName), from a row
    with `{key}`, `{key}_kk`, `{key}_en`."""
    return {key: r[key], f"{key}Kk": r[f"{key}_kk"], f"{key}En": r[f"{key}_en"]}


TITLES = "t.name AS title, t.name_kk AS title_kk, t.name_en AS title_en"


def now() -> int:
    return int(time.time())


def one(con: sqlite3.Connection, sql: str, *args) -> sqlite3.Row | None:
    return con.execute(sql, args).fetchone()


def rows(con: sqlite3.Connection, sql: str, *args) -> list[sqlite3.Row]:
    return con.execute(sql, args).fetchall()


def log_action(con, actor: int | None, action: str, target: str, data: str = "{}") -> None:
    """A line of the audit log, now: who (None: the app itself), what, on what ('user:5'), the details as JSON."""
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, ?, ?, ?, ?)", (actor, action, target, data, now()))


# the staff's decisions on what waits (Admin → Inbox), and their undos: the audit lines Done shows and decided() reads
MOD_DONE = ("report_remove", "report_keep", "tg_confirm", "tg_keep", "tg_restore", "post_hide", "fchan_hide", "fchan_release",
            "fchan_reply_hide", "fchan_reply_release", "fchan_reply_keep", "chat_approve", "chat_decline", "chat_remove")
ADMIN_DONE = ("capp_yes", "capp_no", "opath_yes", "opath_no", "roster_ok", "roster_no", "event_delete", "tg_report_close")
UNDOES = ("restore", "fchan_undo", "fchan_restore", "fchan_reply_undo", "fchan_reply_restore", "capp_undo", "opath_undo", "chat_undo", "event_undo",
          "tg_report_open")
DECISIONS = MOD_DONE + ADMIN_DONE + UNDOES


def same_targets(target: str) -> tuple[str, ...]:
    """One thing's audit targets: a forum channel post is fpost:N for its reports and fchan:N for its moderation."""
    kind, _, ref = target.partition(":")
    return (f"fpost:{ref}", f"fchan:{ref}") if kind in ("fpost", "fchan") else (target,)


def decided(con, target: str) -> ApiError:
    """Two staff on one item: the second decision is a conflict that names who came first, from the audit log's
    decision lines only (never another kind of line: a look-up or a ban is nobody's business here). No line: the thing
    went by itself, its author deleted it."""
    ts = same_targets(target)
    a = one(con, f"""SELECT actor_id, action, at FROM audit_log WHERE target IN ({','.join('?' * len(ts))})
        AND action IN ({','.join('?' * len(DECISIONS))}) ORDER BY id DESC LIMIT 1""", *ts, *DECISIONS)
    p = one(con, PERSON + " WHERE u.id = ?", a["actor_id"]) if a and a["actor_id"] else None
    return ApiError("conflict", "decided", {"by": shown_name(p) if p else None, "action": a["action"] if a else None, "at": a["at"] if a else None})


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


PERSON_COLS = ("u.id, u.tg_first_name, u.tg_last_name, u.tg_photo_url, u.tg_photo_path, u.tg_photo_src, u.is_founder, u.mark, u.show_going, s.first_name, s.last_name, s.first_lat, s.last_lat, u.nick,"
               " u.role AS platform_role,"  # aliased: lists join a club role as `role`
               " CASE WHEN u.avatar_tg = 0 THEN (SELECT path FROM files WHERE id = u.avatar_file_id) END AS own_photo")
PERSON = f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id"


def _once(con, key: str, value: str) -> bool:
    """True the first time a periodic job runs for `value` (a week, a day): the bot's rounds come every few seconds."""
    if one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, value):
        return False
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
    return True




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


def short_name(p: sqlite3.Row) -> str:
    """"Alikhan S" for students (§3; no dot, owner Nov 2), the Telegram first name otherwise."""
    if p["first_name"]:
        return f"{p['first_name']} {p['last_name'][:1] if p['last_name'] else ''}".strip()
    return p["tg_first_name"] or GONE["ru"]  # Telegram never has an empty first name: a deleted account's


# a deleted account's name where its posts and comments stay (owner, Nov 2: content stays, the person goes)
GONE = {"ru": "\u0423\u0434\u0430\u043b\u0451\u043d\u043d\u044b\u0439 \u0430\u043a\u043a\u0430\u0443\u043d\u0442",
        "kk": "\u0416\u043e\u0439\u044b\u043b\u0493\u0430\u043d \u0430\u043a\u043a\u0430\u0443\u043d\u0442", "en": "Deleted account"}


def shown_name(p: sqlite3.Row) -> str:
    """The name lists, cards and feeds show: the nickname when there is one. A nick is a display name, not a mask (owner,
    Nov 2): the profile shows the real short name too (person_ref's `realName`)."""
    return p["nick"] or short_name(p)


def name_i18n(p) -> dict:
    """The short name in the English UI: the Latin one where KBTU's directory, the freshmen list or the student gave it
    (the client's localize() swaps it in, `name` unless a nick stands there, and `realName`); no Latin name: as in every
    language. ponytail: never a generated transliteration (latin-names-review.md: a spelling is personal); a display-only
    one needs its own title-cased table."""
    if "first_lat" not in p.keys() or not p["first_lat"]:
        return {}
    lat = f"{p['first_lat']} {p['last_lat'][:1] if p['last_lat'] else ''}".strip()
    return {"i18n": {"en": {"realName": lat} if p["nick"] else {"name": lat, "realName": lat}}}


def avatar_of(p: sqlite3.Row) -> str | None:
    """My own photo while the "Photo from Telegram" switch is off, else Telegram's (refreshed on every open): our copy
    once the bot has made it, t.me until then."""
    copy = p["tg_photo_path"] if p["tg_photo_src"] == p["tg_photo_url"] else None  # a new t.me photo: t.me till copied
    return f"media/{p['own_photo'] or copy}.t.webp" if p["own_photo"] or copy else p["tg_photo_url"]


def person_ref(p: sqlite3.Row) -> dict:
    # A9: the app's moderators and admins carry a badge everyone sees, like the founder's
    staff = p["platform_role"] if "platform_role" in p.keys() and p["platform_role"] in ("admin", "moderator") else None
    return {"id": p["id"], "name": shown_name(p), "nick": p["nick"], "avatar": avatar_of(p), "founder": bool(p["is_founder"]), "mark": p["mark"], "staff": staff,
            **({"realName": short_name(p)} if p["nick"] else {}),  # a nick never hides the name (§4)
            **({"i18n": {k: {"name": x} for k, x in GONE.items()}} if not p["first_name"] and not p["tg_first_name"] else name_i18n(p))}


def _door_ref(p: sqlite3.Row) -> dict:
    """The door checks the real short name beside a nick, and without one."""
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


# MS_AGE_CUTOFF (env, "MM-DD", e.g. "06-01"; app.py sets it): a free 1st-year seat also needs a KBTU Microsoft
# account made on or after that day of the academic year's first calendar year (audit finding 2): KBTU makes the
# intake's accounts the summer before year one, so a senior who types a 1st-year's ID is years older. None (unset,
# the default): recorded only, never refused, until Admin's "accounts by month" (daily.admin_stats) shows the real
# dates split by intake (a bulk migration could give every account one date). Graph's createdDateTime is UTC ISO
# ("2025-07-14T09:30:00Z"): compared as text; Almaty's 5 hours at midnight don't matter. Unknown (no Microsoft
# sign-in, one before Graph gave it, or Graph left it out): the course alone, as before; ms_link stores the whole
# profile again at every sign-in, so the date arrives with the next one.
MS_AGE_CUTOFF: str | None = None


def first_year_free(con, uid: int) -> bool:
    """Whether this person may take a paid event's free 1st-year seat: a 1st-year bachelor (a B after the year in the
    ID; masters have no such seats) whose Microsoft account isn't older than this year's intake (MS_AGE_CUTOFF)."""
    cut = f"{academic_year()}-{MS_AGE_CUTOFF}" if MS_AGE_CUTOFF else None  # None: `>= NULL` is NULL, COALESCE lets in
    return bool(one(con, """SELECT 1 FROM students WHERE user_id = ? AND course = 1 AND student_id GLOB '[0-9][0-9]B*'
                            AND COALESCE(json_extract(ms_profile, '$.createdDateTime') >= ?, 1)""", uid, cut))


def _free_seat(con, e: sqlite3.Row, uid: int) -> bool:
    """Whether this person gets one of the event's free seats: first_year_free, while some are left."""
    return bool(e["price"] and e["free_first"] and free_taken(con, e["id"]) < e["free_first"] and first_year_free(con, uid))


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


_SHARED: dict = {}  # (kind, id) -> (until, the row it was made from, its part that is the same for every viewer)
SHARED_TTL = 15


def shared(kind: str, found: list[sqlite3.Row], build) -> dict[int, dict]:
    """The viewer-independent part of each row's shape (build(rows) -> {id: part}), kept per worker SHARED_TTL seconds
    (load review: ~100 ms CPU per app open). Keyed by the whole row: an edit of it is seen at once, in every worker;
    what is counted around it (seats taken, an org's logo) may lag up to SHARED_TTL. Only rows the viewer may see are
    passed in: who sees what is decided per request, before this, never cached."""
    t, out, miss = time.monotonic(), {}, []
    for x in found:
        hit = _SHARED.get((kind, x["id"]))
        if hit and hit[0] > t and hit[1] == tuple(x):
            out[x["id"]] = hit[2]
        else:
            miss.append(x)
    if miss:
        if len(_SHARED) > 5000:  # ponytail: drop all at a size cap, an LRU if lists ever outgrow it
            _SHARED.clear()
        made = build(miss)
        for x in miss:
            _SHARED[(kind, x["id"])] = (t + SHARED_TTL, tuple(x), made[x["id"]])
        out |= made
    return out


def cards(con, v: Viewer, evs: list[sqlite3.Row], share: bool = False) -> list[dict]:
    """Event cards (types.ts EventCard). A list asks each thing once for all its events: card by card, the Afisha of a
    few hundred events was 1200 queries and the slowest call of the app's start (load test). share: the lists everyone
    opens (Afisha) take the part that is the same for all from shared(); a single card is always read fresh."""
    if not evs:
        return []
    ids = [e["id"] for e in evs]
    q = _qs(ids)
    part = shared("event", evs, lambda found: _event_parts(con, found)) if share else _event_parts(con, evs)
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
        out.append({**part[e["id"]], "my": my, "saved": e["id"] in saved, "friends": friends.get(e["id"], [])})
    return out


def _event_parts(con, evs: list[sqlite3.Row]) -> dict[int, dict]:
    """The part of each event's card that is the same for every viewer."""
    ids = [e["id"] for e in evs]
    q = _qs(ids)
    taken = dict(rows(con, f"SELECT event_id, COUNT(*) FROM registrations WHERE event_id IN ({q}) AND status IN ('hold','going') GROUP BY event_id", *ids))
    paid = [e["id"] for e in evs if e["price"] and e["free_first"]]  # free seats for 1st-years are counted only where there are some
    free = dict(rows(con, f"SELECT event_id, COUNT(*) FROM registrations WHERE event_id IN ({_qs(paid)}) AND status = 'going' AND free = 1 GROUP BY event_id",
                     *paid)) if paid else {}
    orgs = _by_id(con, "orgs", (e["org_id"] for e in evs))
    co = cohosts_of(con, ids)  # the accepted co-host club, shown beside the host ("Crystal × JCC")
    slides: dict[int, list] = {}
    for r in rows(con, f"SELECT event_id, file_id FROM event_slides WHERE event_id IN ({q}) ORDER BY pos", *ids):
        slides.setdefault(r["event_id"], []).append(r["file_id"])
    files = _by_id(con, "files", [*(e["cover_file_id"] for e in evs), *(o["logo_file_id"] for o in [*orgs.values(), *co.values()]),
                                  *(i for s in slides.values() for i in s)])
    videos = _by_id(con, "videos", (e["video_id"] for e in evs))
    return {e["id"]: {
        "id": e["id"], "org": org_ref(con, orgs[e["org_id"]], files), "coHost": org_ref(con, co[e["id"]], files) if e["id"] in co else None,
        "status": e["status"], "title": e["title"],
        "startsAt": e["starts_at"], "endsAt": e["ends_at"], "publishedAt": e["published_at"], "place": e["place"], "placeUrl": e["place_url"],
        "cover": _event_cover(con, e, files),
        "slides": [media_shape(files[i]) for i in slides.get(e["id"], []) if i in files],
        "emoji": e["emoji"], "color": e["color"], "tint": e["tint"] or "#3B6BFF", "seats": e["seats"], "taken": taken.get(e["id"], 0),
        "firstYear": bool(e["first_year"]), "needsPhone": bool(e["needs_phone"]), "needsVolunteers": e["volunteers"], "externalUrl": e["external_url"], "guestHost": e["guest_host"],
        # its own questions at sign-up ("questions" is Studio's count)
        "form": json.loads(e["questions"]) if e["questions"] else None, "price": e["price"], "visibility": e["visibility"],
        "regUntil": e["reg_until"], "lateSignup": bool(e["late_signup"]), "freeFirst": e["free_first"] if e["price"] else None,
        "freeLeft": max(0, e["free_first"] - free.get(e["id"], 0)) if e["price"] and e["free_first"] else None,
        "leadersFrom": e["leaders_from"], "meeting": bool(e["meeting"]),
        "video": video_shape(x) if (x := videos.get(e["video_id"])) and x["status"] == "ready" else None,
        **({"i18n": {k: {"title": x["title"]} for k, x in json.loads(e["i18n"]).items()}} if e["i18n"] else {}),
    } for e in evs}


def full(con, v: Viewer, e: sqlite3.Row) -> dict:
    head = can(con, v, e["org_id"], "events")  # the club's team only: the app's admin sees the event as a student does
    c = card(con, v, e)
    # the treasurer's Kaspi name and phone: only to who pays (a held or taken seat) and the club's team, never to all
    pay = head or can(con, v, e["org_id"], "money") or (c["my"] or {}).get("status") in ("hold", "going")
    return {**c, **({"i18n": json.loads(e["i18n"])} if e["i18n"] else {}), "description": e["description"],
            "payToName": e["pay_to_name"] if pay else None, "payPhone": e["pay_phone"] if pay else None, "meetingTag": e["meeting_tag"],
            "memo": json.loads(e["memo"]) if head and e["memo"] else None, "cohost": cohost_view(con, e) if head else None,
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


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from .clubs import org, orgs  # noqa: E402
from .cohosts import cohost_view, cohosts_of  # noqa: E402
from .organizing import _album_view, _rating_view  # noqa: E402
from .oversight import staff  # noqa: E402
from .profiles import friends  # noqa: E402
from .queues import video_shape  # noqa: E402
from .seats import _chat_ok, _volunteers_view, ics_sig  # noqa: E402
