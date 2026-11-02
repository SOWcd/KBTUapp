"""People's pages, awards and friends: streaks, achievements, grants, the first 500, friend requests and links."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time

from ..db import tx

from .core import (ApiError, NO_END, PERSON, PERSON_COLS, PROFILE_QR, SEASON_MONTHS, Viewer, _org, _roles, cards,
    log_action, need_student, one, org_ref, person_ref, rows, short_name)


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
    current one. A week without a public event neither breaks nor adds (nothing to go to is no reason to
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
    ("team", "cloud_with_lightning_and_rain_3d", (3, 10, 25, 50), False),  # "Teambuilding thunder": a club's own events, meetings too
    ("season", "sparkles_3d", (3, 7, 12, 20), False),
    ("first50", "medal_first500", (1,), False),  # the drawn First 500 medal (owner, Nov 1)
    ("creator_laugh", "face_with_tears_of_joy_3d", (1,), True), ("creator_found", "waving_hand_3d_default", (1,), True),
    ("bugs", "lady_beetle_3d", (1, 5, 10, 25), False),  # a bug, literally (no emoji twice)
    ("referral", "megaphone_3d", (1, 3, 5, 10, 15, 25, 50, 75, 100), False),  # students brought by my invite link who signed in with KBTU (9 levels since Nov 2)
    ("init26", "medal_init26_2", (1,), False),  # volunteered at the 2026 freshmen's initiation (given to a check-in session's people)
    ("init26f", "medal_init26f_2", (1,), False),  # was at the 2026 initiation as a freshman (the freshmen list's mark, at sign-in: account.ms_link)
    ("init26p", "medal_init26p_2", (1,), False),  # performed on stage at the 2026 initiation (Admin → Badges)
    ("anthem", "headphone_3d", (1,), False),  # listened to KBTU's anthem start to finish without skipping (the anthem sheet: anthem_heard)
]


def _counts(con, uid: int) -> dict[str, int]:
    times = attended(con, uid)
    grants = dict(rows(con, "SELECT code, COUNT(*) FROM achievement_grants WHERE user_id = ? GROUP BY code", uid))
    first_in = one(con, """SELECT COUNT(*) FROM registrations r WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND r.checked_in_at =
        (SELECT MIN(x.checked_in_at) FROM registrations x WHERE x.event_id = r.event_id)""", uid)[0]
    soul = one(con, "SELECT COUNT(*) FROM registrations WHERE invited_by = ? AND checked_in_at IS NOT NULL AND checked_in_by IS NOT ?", uid, uid)[0]  # not by my own door scan
    referral = brought(con, uid)
    team = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.status = 'published' AND e.visibility = 'members'""", uid)[0]
    seasons = [_season_start(t) for t in times]  # the best semester counts: every semester is a new chance
    # a partner's week has nothing to check in at. Only weeks from my first check-in's on count (_streak): an index
    # range from that week's Monday, O(my weeks' events), not every event ever under the door's write lock (review 7)
    busy = {_week(r[0]) for r in rows(con, """SELECT starts_at FROM events WHERE status = 'published' AND starts_at >= ?
        AND visibility = 'public' AND guest_host IS NULL""", _week(times[0]) * 7 * 86400 - 3 * 86400 - 5 * 3600)} if times else set()
    streak, streak_now = _streak({_week(t) for t in times}, busy, _week(core.now()))
    return {"regular": len(times), "streak": streak, "streak_now": streak_now, "first_in": first_in, "soul": soul, "team": team,
            "season": max(map(seasons.count, set(seasons)), default=0), "first50": grants.get("first50", 0),
            "creator_laugh": grants.get("creator_laugh", 0), "creator_found": grants.get("creator_found", 0), "bugs": grants.get("bugs", 0), "referral": referral,
            "init26": grants.get("init26", 0), "init26f": grants.get("init26f", 0), "init26p": grants.get("init26p", 0), "anthem": grants.get("anthem", 0)}


def brought(con, uid: int) -> int:
    """Students my invite link brought: only those who finished the KBTU sign-in count (a Telegram account alone is free)."""
    return one(con, """SELECT COUNT(*) FROM users u JOIN students s ON s.user_id = u.id AND s.manual = 0
        WHERE u.referred_by = ?""", uid)[0]


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
                ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at""", (uid, code, level, core.now()))
            notify(con, uid, "achievement", f"ach:{code}:{level}")


def sync_levels(con) -> None:
    """Levels already reached, recorded once the achievements change (a new one, a new level): counts never stop at the
    top, so a level added later is reached by whoever already did it. At start, under the migration
    lock (db.init), only when the list differs from the last run. No bot message. A new achievement's levels get the
    app's unlock moment; new levels of one that was there already come quietly (Nov 2: "Recruiter" went from 4 levels to
    9, a burst of moments for what was done weeks ago): a stored level is a place in the list, so it moves to the level
    of the same need first."""
    mark = json.dumps([[code, needs] for code, _, needs, _ in ACHIEVEMENTS])
    last, filled = (one(con, "SELECT value FROM meta WHERE key = ?", k) for k in ("achievements", "achievements_filled"))
    if last and last[0] == mark and filled and filled[0] == mark:
        return
    was = {code: needs for code, needs in json.loads(last[0])} if last else {}
    now = {code: needs for code, _, needs, _ in ACHIEVEMENTS}
    to = lambda code, lv: sum(1 for n in now[code] if n <= was[code][lv - 1]) if lv > 0 else 0  # noqa: E731
    put = lambda key: con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, mark))  # noqa: E731
    if not last or last[0] != mark:
        with tx(con):  # the re-tier moves stored levels once: done with its mark in one transaction, never twice
            for code in was.keys() & now.keys():
                if list(was[code]) != list(now[code]):
                    for r in rows(con, "SELECT user_id, level, seen FROM achievement_levels WHERE code = ?", code):
                        con.execute("UPDATE achievement_levels SET level = ?, seen = ? WHERE user_id = ? AND code = ?",
                                    (to(code, min(r["level"], len(was[code]))), to(code, min(r["seen"], len(was[code]))), r["user_id"], code))
            put("achievements")
    # the fill only raises levels (safe to repeat): ~300 students a commit, so one write lock isn't held over all of them
    # (3.2 s at 5k). Stopped midway, the next start finishes it, quietly (`was` is the new list by then).
    students = [r[0] for r in rows(con, "SELECT user_id FROM students")]
    for i in range(0, len(students), 300):
        with tx(con):
            for uid in students[i:i + 300]:
                have = dict(rows(con, "SELECT code, level FROM achievement_levels WHERE user_id = ?", uid))
                for code, level in _levels(con, uid).items():
                    if level > have.get(code, 0):
                        seen = level if code in was else 0
                        con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at, seen) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at, seen = MAX(seen, excluded.seen)""",
                                    (uid, code, level, core.now(), seen))
    put("achievements_filled")


# A badge with variants (owner, Nov 2): one award on the profile and in the count, the medal of my variant; each variant
# is its own grant code underneath (levels, the bot's card, take-back stay per variant). The highest variant first.
BADGES = {"init26": ("init26p", "init26", "init26f")}  # performer, volunteer, guest (first-year)
BADGE_OF = {c: b for b, vs in BADGES.items() for c in vs}

GRANTABLE = ("bugs", "creator_laugh", "creator_found", "init26", "init26f", "init26p")  # the manual ones (§4.11); "First 500" is given at verification


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
    gid = con.execute("INSERT INTO achievement_grants (user_id, code, granted_by, created_at) VALUES (?, ?, ?, ?)", (uid, code, by, core.now())).lastrowid
    log_action(con, by, "grant", f"user:{uid}", json.dumps({"code": code}))
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
    return {"id": gid, "code": code, "at": core.now(), "person": person_ref(one(con, PERSON + " WHERE u.id = ?", int(b[1])))}


GRANT_LINK_TTL = 7 * 86400


def grant_link(con, v: Viewer, code: object) -> str:
    """The admin's one-time award link ("Bug hunter" is earned in a chat, so it goes as a link there;
    the face-to-face ones stay on the badge QR): one student, once, within 7 days."""
    _admin(v)
    if code not in GRANTABLE:
        raise ApiError("bad_input")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (token, code, v.id, core.now(), core.now() + GRANT_LINK_TTL))
    log_action(con, v.id, "grant_link", f"link:{token[:8]}", json.dumps({"code": code}))  # who made it; its use: "grant_link_used"
    return token


def use_grant_link(con, v: Viewer, token: str) -> dict:
    """A student opened an award link: theirs, celebrated like any new level. A used or old link is 'closed'. A link
    for many (`multi`, admin claim new) gives each student the award once until it expires; opened again by one who
    has it: fine, nothing more (a chat's link gets tapped twice)."""
    need_student(v)
    with tx(con):
        # the maker still an admin: a demoted or banned one's links stop with the role
        r = one(con, """SELECT g.* FROM grant_links g JOIN users u ON u.id = g.created_by AND u.role = 'admin' AND u.banned_at IS NULL
            WHERE g.token = ? AND (g.multi = 1 OR g.used_by IS NULL) AND g.expires_at > ?""", token, core.now())
        if not r:
            raise ApiError("closed")
        if not r["multi"]:
            _grant(con, r["created_by"], v.id, r["code"])
            con.execute("UPDATE grant_links SET used_by = ?, used_at = ? WHERE token = ?", (v.id, core.now(), token))
            log_action(con, v.id, "grant_link_used", f"link:{token[:8]}", json.dumps({"code": r["code"], "by": r["created_by"]}))
        elif not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = ?", v.id, r["code"]):
            _grant(con, r["created_by"], v.id, r["code"])
    return {"code": r["code"]}


def claim_link(con, code: str, until: int, v: Viewer | None = None) -> str:
    """admin claim new, or the owner's "Link for everyone" in Admin → Badges (v): a link many students open for `code`
    (not Bug hunter: that one is earned one by one), given by the owner, until `until`. Signed-in KBTU students only, one
    award each; forwarded beyond those it's meant for: accepted (owner, Nov 2: too many performers to give one by one)."""
    owner = one(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin'")
    if v is not None and (not owner or v.id != owner[0]):
        raise ApiError("forbidden")
    if v is not None and (type(code) is not str or code not in BADGE_OF):  # from the app: badges only (the CLI keeps the rest)
        raise ApiError("bad_input")
    if not owner or code not in GRANTABLE or code == "bugs" or until <= core.now():
        raise ApiError("bad_input")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at, multi) VALUES (?, ?, ?, ?, ?, 1)",
                (token, code, owner[0], core.now(), until))
    if v is not None:
        log_action(con, v.id, "grant_link", f"link:{token[:8]}", json.dumps({"code": code, "many": True}))
    return token


def ungrant(con, v: Viewer, gid: int) -> None:
    """Undo a grant of mine within a minute (the scanner's undo): the level goes back, its unsent bot card goes."""
    _admin(v)
    g = one(con, "SELECT * FROM achievement_grants WHERE id = ? AND granted_by = ? AND created_at >= ?", gid, v.id, core.now() - 60)
    if not g:
        raise ApiError("not_found")
    _drop_grant(con, v, g)


def take_back(con, v: Viewer, uid: object, code: object) -> dict:
    """The admin takes back a manual award from a profile at any time (Bug hunter given to a friend
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
        log_action(con, v.id, "ungrant", f"user:{g['user_id']}", json.dumps({"code": g["code"]}))


def my_grants(con, v: Viewer) -> list[dict]:
    """"You gave: N" on the Awards page: the owner's grants, newest first."""
    _admin(v)
    return [{"id": g["gid"], "code": g["code"], "at": g["created_at"], "person": person_ref(g)}
            for g in rows(con, f"""SELECT g.id AS gid, g.code, g.created_at, {PERSON_COLS} FROM achievement_grants g JOIN users u ON u.id = g.user_id
                LEFT JOIN students s ON s.user_id = u.id WHERE g.granted_by = ? AND g.code IN ({','.join('?' * len(GRANTABLE))})
                ORDER BY g.created_at DESC, g.id DESC LIMIT 300""", v.id, *GRANTABLE)]


# ---------------------------------------------------------------- Admin → Badges: a badge variant by hand

def _badge_row(con, p) -> dict:
    has = sorted((r[0] for r in rows(con, f"SELECT DISTINCT code FROM achievement_grants WHERE user_id = ? AND code IN ({','.join('?' * len(BADGE_OF))})", p["id"], *BADGE_OF)), key=list(BADGE_OF).index)  # the highest variant first
    return {"person": person_ref(p), "username": p["tg_username"], "has": has}


def badge_people(con, v: Viewer, q: object) -> list[dict]:
    """Students by name, @username, student ID or app id (the admin's search), each with the badge variants they hold.
    The student ID only matches, it is never sent back."""
    _admin(v)
    q = str(q or "").strip().lstrip("@")
    if not (2 <= len(q) or q.isdigit()) or len(q) > 64:  # an app id may be one digit
        raise ApiError("bad_input")
    like = "%" + re.sub(r"([\\%_])", r"\\\1", q) + "%"
    # ponytail: SQLite's LIKE folds ASCII case only: a lower-case Cyrillic name misses its capitalized row (the Latin spelling still finds it); a lower() column if it bites
    found = rows(con, PERSON.replace("SELECT ", "SELECT u.tg_username, ", 1) + r""" WHERE s.user_id IS NOT NULL AND (
            lower(u.tg_username) = lower(?) OR upper(s.student_id) = upper(?) OR u.id = ?
            OR s.first_name || ' ' || s.last_name LIKE ? ESCAPE '\' OR s.last_name || ' ' || s.first_name LIKE ? ESCAPE '\'
            OR coalesce(s.first_lat, '') || ' ' || coalesce(s.last_lat, '') LIKE ? ESCAPE '\'
            OR coalesce(s.last_lat, '') || ' ' || coalesce(s.first_lat, '') LIKE ? ESCAPE '\' OR u.nick LIKE ? ESCAPE '\')
        ORDER BY s.last_name, s.first_name LIMIT 20""", q, q, int(q) if q.isdigit() else -1, *[like] * 5)
    return [_badge_row(con, p) for p in found]


def badge_set(con, v: Viewer, uid: int, code: str, on: bool) -> dict:
    """Give a badge variant (idempotent: held already, nothing more) or take it back (every grant of it). Both audited
    and celebrated or undone as any manual award; the variants' undo is the other call."""
    _admin(v)
    if code not in BADGE_OF:
        raise ApiError("bad_input")
    p = one(con, PERSON.replace("SELECT ", "SELECT u.tg_username, ", 1) + " WHERE u.id = ? AND s.user_id IS NOT NULL", uid)
    if not p:
        raise ApiError("not_found")
    with tx(con):
        held = rows(con, "SELECT * FROM achievement_grants WHERE user_id = ? AND code = ? ORDER BY id DESC", uid, code)
        if on and not held:
            _grant(con, v.id, uid, code)
        for g in held if not on else ():
            _drop_grant(con, v, g)
    return _badge_row(con, p)


def badge_sessions(con, v: Viewer) -> list[dict]:
    """The owner's batch grant (it was on /show's sheet): check-in sessions, newest first, with how many were counted."""
    if not _owner(con, v):
        raise ApiError("forbidden")
    return [{"id": r["id"], "title": r["title"], "at": r["started_at"] or r["created_at"], "done": r["done"]} for r in rows(con, """
        SELECT q.*, (SELECT COUNT(*) FROM qr_marks m WHERE m.session_id = q.id AND m.done_at IS NOT NULL) AS done
        FROM qr_sessions q ORDER BY q.id DESC LIMIT 20""")]


FIRST_N = 500  # cards 1-500; the code stays "first50": it was 50 until launch day, a pilot club alone could have taken them all


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
    Kept as a grant; celebrated in the app only."""
    card_no(con, uid)
    u = one(con, "SELECT card_no, is_founder FROM users WHERE id = ?", uid)
    if not (u["is_founder"] or (u["card_no"] or FIRST_N + 1) <= FIRST_N) or one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'first50'", uid):
        return
    con.execute("INSERT INTO achievement_grants (user_id, code, note, created_at) VALUES (?, 'first50', 'verification', ?)", (uid, core.now()))
    log_action(con, None, "first50", f"user:{uid}")
    con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'first50', 1, ?)
        ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1), reached_at = excluded.reached_at""", (uid, core.now()))
    # no bot push: the app shows it the same minute (the lanyard's drop on the first Profile open), a DM on top of the
    # first run was one window too many (onboarding plan, Oct 31)


def anthem_heard(con, v: Viewer) -> list[dict]:
    """The anthem heard start to finish without skipping: the app knows (the sheet tracks skips) and says so at the song's
    end; once per student, again is a no-op. Celebrated in the app only (it is open right then), no bot message."""
    # ponytail: the app's word is trusted (owner, Nov 2: an award for fun, kept light); a server-side play token if it is ever farmed
    need_student(v)
    with tx(con):
        if not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'anthem'", v.id):
            con.execute("INSERT INTO achievement_grants (user_id, code, note, created_at) VALUES (?, 'anthem', 'listened', ?)", (v.id, core.now()))
            con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'anthem', 1, ?)
                ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1)""", (v.id, core.now()))
    return unlocked(con, v)


def unlocked(con, v: Viewer) -> list[dict]:
    """Levels reached that the app hasn't celebrated yet (the unlock moment, §4.11), oldest first."""
    if not v.student:
        return []
    return [{"code": BADGE_OF.get(r["code"], r["code"]), "level": r["level"]} for r in
            rows(con, "SELECT code, level FROM achievement_levels WHERE user_id = ? AND level > seen ORDER BY reached_at", v.id)]


def seen_unlock(con, v: Viewer, code: object, level: object) -> None:
    need_student(v)
    if not isinstance(code, str) or not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 10:
        raise ApiError("bad_input")
    for c in BADGES.get(code, (code,)):  # a badge's moment shows once for all its variants
        con.execute("UPDATE achievement_levels SET seen = MAX(seen, ?) WHERE user_id = ? AND code = ?", (level, v.id, c))


def achievements(con, uid: int) -> list[dict]:
    """Mine, each level with its rarity: the share of students who have reached it. Rarity comes from the levels everyone
    reached (achievement_levels: an earned level stays), one query; counting every student's check-ins for every
    profile view was thousands of queries once a few hundred students had signed in (load test)."""
    mine = _counts(con, uid)
    total, at_level, badges = _rarity(con)
    out = []
    reached = {r["code"]: r for r in rows(con, "SELECT code, level, reached_at FROM achievement_levels WHERE user_id = ?", uid)}
    for code, emoji, needs, secret in ACHIEVEMENTS:
        have = lambda level: sum(n for (c, lv), n in at_level.items() if c == code and lv >= level) / total  # noqa: E731
        out.append({"code": code, "emoji": emoji, "secret": secret, "count": mine[code], "level": sum(1 for n in needs if mine[code] >= n),
                    "levels": [{"need": n, "reached": mine[code] >= n, "rarity": have(i + 1)} for i, n in enumerate(needs)], "rarity": have(1),
                    "at": reached[code]["reached_at"] if code in reached else None,
                    **({"now": mine["streak_now"]} if code == "streak" else {})})
    return _fold(out, badges)


_RARITY: list = [0.0, None]  # (until, what _rarity read): the same for every profile view, so read once a minute per worker


def _rarity(con) -> tuple[int, dict, dict]:
    """How many students reached each level, out of how many, and each badge's share (any of its variants). Global and
    slow to move: a minute stale is fine, and it was a GROUP BY over every level on every profile view (load review)."""
    if _RARITY[0] > time.monotonic():
        return _RARITY[1]
    # out of students only: staff take no card and no "First 500", counted they made it "95%"
    total = max(1, one(con, "SELECT COUNT(*) FROM students WHERE consent_version != 'staff'")[0])
    at_level = {(r[0], r[1]): r[2] for r in rows(con, """SELECT l.code, l.level, COUNT(*) FROM achievement_levels l
        JOIN students s ON s.user_id = l.user_id WHERE s.consent_version != 'staff' GROUP BY l.code, l.level""")}
    badges = {b: one(con, f"""SELECT COUNT(DISTINCT l.user_id) FROM achievement_levels l JOIN students s ON s.user_id = l.user_id
        WHERE s.consent_version != 'staff' AND l.code IN ({','.join('?' * len(vs))})""", *vs)[0] / total for b, vs in BADGES.items()}
    _RARITY[:] = [time.monotonic() + 60, (total, at_level, badges)]
    return _RARITY[1]


def _fold(out: list[dict], badges: dict[str, float]) -> list[dict]:
    """A badge's variants as one entry at the badge's place: mine is the highest I have (`variant`), its medal shown;
    `variants` all of them, held or not, for the detail view. How rare: students with any of them."""
    by = {a["code"]: a for a in out}
    for b, vs in BADGES.items():
        held = [by[c] for c in vs if by[c]["level"]]
        top = held[0] if held else by[vs[-1]]
        rarity = badges[b]
        by[b] = {**top, "code": b, "count": len(held), "level": 1 if held else 0, "rarity": rarity, "variant": held[0]["code"] if held else None,
                 "levels": [{"need": 1, "reached": bool(held), "rarity": rarity}], "at": min((a["at"] for a in held if a["at"]), default=None),
                 "variants": [{"code": c, "emoji": by[c]["emoji"], "have": bool(by[c]["level"]), "rarity": by[c]["rarity"]} for c in vs]}
    return [by[a["code"]] for a in out if a["code"] not in BADGE_OF or a["code"] in BADGES]


PROFILES_A_DAY = 200  # strangers' profiles a day (audit M2): browsing needs a few dozen, a scrape needs thousands


def _stranger_view(con, v: Viewer, uid: int) -> None:
    """Counts a profile opened by someone who is neither a friend nor a clubmate; past the day's limit, refused. One
    row per (Almaty day, viewer, profile), so reopening the same one is free; old days go in the daily job (stats_day)."""
    day = (core.now() + 5 * 3600) // 86400
    if one(con, "SELECT 1 FROM profile_views WHERE day = ? AND viewer_id = ? AND user_id = ?", day, v.id, uid):
        return
    # ponytail: count then insert, a burst can pass 200 by a few
    if one(con, "SELECT COUNT(*) FROM profile_views WHERE day = ? AND viewer_id = ?", day, v.id)[0] >= PROFILES_A_DAY:
        raise ApiError("rate_limited")
    con.execute("INSERT INTO profile_views (day, viewer_id, user_id) VALUES (?, ?, ?)", (day, v.id, uid))


def person(con, v: Viewer, uid: int) -> dict:
    """A profile (§4.12). Friends and clubmates see it all; anyone else (audit M2) the card, the bio and achievements
    (the "team" medal says only "some club", accepted), but not the clubs, past roles, event badges or a club's badge
    that came by itself (where someone goes can say more than they chose to show: a
    support group, a faith club) and at most PROFILES_A_DAY of them, so the student body can't be scraped by id."""
    need_student(v)
    p = one(con, PERSON + " WHERE u.id = ?", uid)
    s = one(con, "SELECT * FROM students WHERE user_id = ?", uid)
    if not p or not s:
        raise ApiError("not_found")
    u = one(con, "SELECT bio, showcase, show_going, can_friend, card_no, is_founder, tg_username, skin_pick, skin_org, city, city_hidden, frame FROM users WHERE id = ?", uid)
    link = one(con, "SELECT created_at FROM friendships WHERE a = ? AND b = ?", min(uid, v.id), max(uid, v.id))
    # their @username, to their own club's team only (§3: the team sees it in its roster anyway): "Message on Telegram"
    team = uid != v.id and one(con, "SELECT 1 FROM org_members a JOIN org_members b ON b.org_id = a.org_id WHERE a.user_id = ? AND b.user_id = ?",
                               v.id, uid) is not None
    state = "none" if uid == v.id else friendship(con, v.id, uid)
    close = uid == v.id or link is not None or team or v.role in ("admin", "moderator")  # the team: reports need it all
    if not close:
        _stranger_view(con, v, uid)
    # when a level was reached is the second of a check-in: matched against the Afisha it names the event
    ach = [a if close else {**a, "at": None} for a in achievements(con, uid)]
    picked = list(dict.fromkeys(BADGE_OF.get(k, k) for k in u["showcase"].split(",")))  # an old "init26f" is the badge now
    going = []
    if link and u["show_going"]:  # only events I may see myself: a friend's team-only meeting stays theirs
        roles = _roles(con, v)
        going = cards(con, v, [e for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
            WHERE r.user_id = ? AND r.status = 'going' AND e.status = 'published' AND e.starts_at > ? ORDER BY e.starts_at""", uid, core.now())
            if _visible(con, v, e, roles)])
    badges = [{"eventId": e["id"], "title": e["badge_name"], "org": org_ref(con, _org(con, e["org_id"])), "emoji": e["emoji"] or "party_popper_3d",
               "color": e["tint"] or "#3B6BFF", "at": e["starts_at"]}
              for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
                  WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.badge_name IS NOT NULL ORDER BY e.starts_at DESC""", uid)] if close else []
    return {
        **person_ref(p), "no": 0 if u["is_founder"] else u["card_no"], "course": s["course"], "school": s["school"], "bio": u["bio"],
        "city": u["city"] if u["city"] and not u["city_hidden"] else None,  # from the club's roster (PLAN 95), unless hidden
        "attended": len(attended(con, uid)),
        # the role shows only to the club's own team: outside, just the club
        "clubs": [{"org": org_ref(con, m), "role": m["role"] if m["mine"] else None, **(core.titled(m) if m["mine"] else {"title": None})} for m in rows(con, f"""
            SELECT m.role, {core.TITLES}, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = m.org_id AND x.user_id = ?) AS mine, o.* FROM org_members m
            JOIN orgs o ON o.id = m.org_id LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ?""", v.id, uid) if close],
        # where they were before (org_history, written by triggers): a role held at least a day, the club still shown;
        # the role by the same rule as above. Newest first
        "past": [{"org": org_ref(con, h), "role": h["role"] if h["mine"] else None, "since": h["since"], "until": h["until"]} for h in rows(con, """
            SELECT h.role, h.since, h.until, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = h.org_id AND x.user_id = ?) AS mine, o.*
            FROM org_history h JOIN orgs o ON o.id = h.org_id
            WHERE h.user_id = ? AND h.until IS NOT NULL AND h.until - h.since >= 86400 AND o.status = 'active'
            ORDER BY h.until DESC LIMIT 20""", v.id, uid) if close],
        "showcase": [a for c in picked for a in ach if a["code"] == c and a["level"] > 0],
        # the showcase as picked (achievements earned, badges owned), in order; empty = never picked, the badge shows a default
        "shelf": [k for k in picked if any(a["code"] == k and a["level"] > 0 for a in ach) or any(f"b{b['eventId']}" == k for b in badges)],
        "awards": {"achievements": ach, "badges": badges},
        "friendship": state, "friendsSince": link["created_at"] if link else None, "going": going,
        "username": u["tg_username"] if team else None,
        # a badge picked to be shown, shows; the one that came by itself from a club would tell a stranger the club
        "frame": u["frame"] if u["frame"] in FRAMES else None,  # on the lanyard, as the photo under it: seen by anyone who sees the card
        "skin": _skin(con, uid) if close else "sower" if u["is_founder"] and u["skin_pick"] in ("sower", None)
                else u["skin_org"] if u["skin_pick"] == "org" and _skin_ok(con, uid, u["skin_org"]) else None,
        **({} if close else {"limited": True}),
        **({"closed": True} if state == "none" and not u["can_friend"] else {}),  # no "Add friend" for them (their setting)
    }




# ---------------------------------------------------------------- friends (§4.7)

FRIEND_ASKS_A_DAY = 500  # no limit for a person (owner, Nov 2: 20 a day stopped the initiation crowd); only a script hits it
REASK_AFTER = 30 * 86400    # a declined request looks pending to the asker this long, then they may ask again
LINK_TTL = 7 * 86400


def friendship(con, me: int, uid: int) -> str:
    """'friends' | 'requested' (mine, waiting; a quiet decline looks the same for 30 days) | 'incoming' | 'none'."""
    if one(con, "SELECT 1 FROM friendships WHERE a = ? AND b = ?", min(me, uid), max(me, uid)):
        return "friends"
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND (status = 'pending' OR (status = 'declined' AND decided_at > ?))",
           me, uid, core.now() - REASK_AFTER):
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
    con.execute("INSERT OR IGNORE INTO friendships (a, b, created_at) VALUES (?, ?, ?)", (min(a, b), max(a, b), core.now()))
    con.execute("""UPDATE friend_requests SET status = 'accepted', decided_at = ? WHERE status = 'pending'
        AND ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))""", (core.now(), a, b, b, a))


def _friend_row(p: sqlite3.Row, at: int, friend: bool = True) -> dict:
    """Full names only between friends (§3); a request shows the short one, with course and school like any card."""
    name = f"{p['first_name']} {p['last_name']}".strip() if friend else short_name(p)
    return {"person": person_ref(p), "fullName": name, "course": p["course"], "school": p["school"], "at": at}


def friends(con, v: Viewer) -> dict:
    """The Friends page: friends (full names, §3), requests both ways, and the coming events friends go to (only
    those who let friends see it; the card lists them)."""
    need_student(v)
    cols = PERSON_COLS + ", s.course, s.school"
    # closest first, not by the alphabet (owner, Nov 2): the events we both went to, the clubs we share (a club weighs two
    # events), then the newest friends
    mine = [_friend_row(p, p["since"]) for p in rows(con, f"""SELECT {cols}, f.created_at AS since FROM friendships f
        JOIN users u ON u.id = CASE WHEN f.a = ? THEN f.b ELSE f.a END JOIN students s ON s.user_id = u.id
        WHERE f.a = ? OR f.b = ?
        ORDER BY (SELECT COUNT(*) FROM registrations r1 JOIN registrations r2 ON r2.event_id = r1.event_id
                  WHERE r1.user_id = ? AND r2.user_id = u.id AND r1.status = 'going' AND r2.status = 'going')
               + 2 * (SELECT COUNT(*) FROM org_members a JOIN org_members b ON b.org_id = a.org_id WHERE a.user_id = ? AND b.user_id = u.id) DESC,
               f.created_at DESC, s.first_name""", v.id, v.id, v.id, v.id, v.id)]
    incoming = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.from_id JOIN students s ON s.user_id = u.id
        WHERE r.to_id = ? AND r.status = 'pending' ORDER BY r.created_at DESC""", v.id)]
    outgoing = [_friend_row(p, p["at"], False) for p in rows(con, f"""SELECT {cols}, r.created_at AS at FROM friend_requests r
        JOIN users u ON u.id = r.to_id JOIN students s ON s.user_id = u.id
        WHERE r.from_id = ? AND (r.status = 'pending' OR (r.status = 'declined' AND r.decided_at > ?)) ORDER BY r.created_at DESC""",
        v.id, core.now() - REASK_AFTER)]
    roles = _roles(con, v)
    going = [e for e in rows(con, f"""SELECT DISTINCT e.* FROM registrations r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
        WHERE r.status = 'going' AND u.show_going = 1 AND e.status = 'published' AND COALESCE(e.ends_at, e.starts_at + {NO_END}) > ?
        AND r.user_id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)
        ORDER BY e.starts_at LIMIT 30""", core.now(), v.id, v.id) if _visible(con, v, e, roles)]
    return {"friends": mine, "incoming": incoming, "outgoing": outgoing, "going": cards(con, v, going)}


def find_student(con, v: Viewer, username: str) -> dict:
    """A student by Telegram @username (public in Telegram anyway, §4.7), with where the two of us stand."""
    need_student(v)
    name = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ApiError("bad_input")
    u = one(con, "SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE lower(u.tg_username) = lower(?)", name)
    p = _student(con, u["id"] if u else None)
    me = p["id"] == v.id
    state = "none" if me else friendship(con, v.id, p["id"])
    # a stranger's real name counts as a profile opened, as in person(): @usernames from the chats can't be mapped to names in bulk
    if not me and state != "friends" and v.role not in ("admin", "moderator") and not one(
            con, "SELECT 1 FROM org_members a JOIN org_members b ON b.org_id = a.org_id WHERE a.user_id = ? AND b.user_id = ?", v.id, p["id"]):
        _stranger_view(con, v, p["id"])
    s = one(con, "SELECT course, school FROM students WHERE user_id = ?", p["id"])
    out = {"person": person_ref(p), "course": s["course"], "school": s["school"], "friendship": state, "me": me}
    return {**out, "closed": True} if state == "none" and not _can_friend(con, p["id"]) else out


def _can_friend(con, uid: int) -> bool:
    """Their "Can add me as a friend" (Settings): off, nobody may send them a new request."""
    return bool(one(con, "SELECT can_friend FROM users WHERE id = ?", uid)[0])


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
            notify(con, uid, "friend_new", f"fn:{v.id}:{core.now() // 86400}")
        state = "friends"
    elif state == "none":
        if not _can_friend(con, uid):
            raise ApiError("closed")
        _stranger_view(con, v, uid)  # a person opened the profile already (free); a script walking ids meets the 200 a day (review)
        if one(con, "SELECT COUNT(*) FROM friend_requests WHERE from_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= FRIEND_ASKS_A_DAY:
            raise ApiError("rate_limited")
        with tx(con):
            con.execute("""INSERT INTO friend_requests (from_id, to_id, status, created_at) VALUES (?, ?, 'pending', ?)
                ON CONFLICT (from_id, to_id) DO UPDATE SET status = 'pending', created_at = excluded.created_at, decided_at = NULL""", (v.id, uid, core.now()))
            notify(con, uid, "friend_request", f"fq:{v.id}:{core.now() // 86400}")
        state = "requested"
    return {"person": person_ref(p), "friendship": state}


def answer_friend(con, v: Viewer, uid: int, accept: bool) -> dict:
    need_student(v)
    if not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", uid, v.id):
        raise ApiError("not_found")
    with tx(con):
        if accept:
            _befriend(con, v.id, uid)
            notify(con, uid, "friend_new", f"fn:{v.id}:{core.now() // 86400}")
        else:  # quietly: the asker keeps seeing "request sent" (§4.7)
            con.execute("UPDATE friend_requests SET status = 'declined', decided_at = ? WHERE from_id = ? AND to_id = ?", (core.now(), uid, v.id))
    return friends(con, v)


def take_back_request(con, v: Viewer, uid: int) -> None:
    """Cancel my waiting request (a quietly declined one stays: it still holds the 30 days)."""
    need_student(v)
    con.execute("DELETE FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", (v.id, uid))


def unfriend(con, v: Viewer, uid: int) -> None:
    """Quietly; either side, any time (§4.7)."""
    need_student(v)
    con.execute("DELETE FROM friendships WHERE a = ? AND b = ?", (min(uid, v.id), max(uid, v.id)))


def _inviter(con, code: object) -> sqlite3.Row:
    """Whose invite link r_<link code> this is (a student's; the code, never a user ID)."""
    p = one(con, PERSON + " WHERE u.link_code = ? AND s.user_id IS NOT NULL", code) \
        if isinstance(code, str) and re.fullmatch(r"[A-Z2-7]{10}", code) else None
    if not p:
        raise ApiError("not_found")
    return p


def link_card(con, v: Viewer, code: object) -> dict:
    """My one invite link opened (owner, Nov 2: the referral link and the friend link are one): whose it is and where we
    stand ('self' on my own). Adds nobody. Guests too: the inviter posted it, and the bot's card already shows their
    name; the 50-bit code can't be walked."""
    p = _inviter(con, code)
    state = "self" if p["id"] == v.id else friendship(con, v.id, p["id"]) if v.student else "none"
    ref = person_ref(p)
    if not v.student:  # the real name behind a nick is for students (policy §4), not anyone holding the link
        ref.pop("realName", None)
    return {"person": ref, "friendship": state}


def add_by_link(con, v: Viewer, code: object) -> dict:
    """The landing's one tap: friends at once, no request (sharing the link was the inviter's yes). My request they
    quietly declined still holds for its 30 days (it stays 'requested', as everywhere)."""
    need_student(v)
    p = _inviter(con, code)
    if p["id"] == v.id:
        raise ApiError("bad_input")
    out = {"person": person_ref(p)}
    if one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'declined' AND decided_at > ?",
           v.id, p["id"], core.now() - REASK_AFTER):
        return {**out, "friendship": "requested"}
    if friendship(con, v.id, p["id"]) == "friends":
        return {**out, "friendship": "friends"}
    # ponytail: counts every new friend of mine today, not only by links; a per-link log if that ever bites
    if one(con, "SELECT COUNT(*) FROM friendships WHERE (a = ? OR b = ?) AND created_at > ?", v.id, v.id, core.now() - 86400)[0] >= FRIEND_ASKS_A_DAY:
        raise ApiError("rate_limited")  # a stranger collecting posted links for friends' full names and plans
    with tx(con):
        _befriend(con, v.id, p["id"])
        notify(con, p["id"], "friend_new", f"fn:{v.id}:{core.now() // 86400}")
    return {**out, "friendship": "friends"}


def friend_joined(con, v: Viewer, since: int) -> dict:
    """While my invite QR is on screen (AddFriend): the newest friend since then, to celebrate."""
    need_student(v)
    r = one(con, """SELECT CASE WHEN a = ? THEN b ELSE a END AS uid, created_at FROM friendships WHERE (a = ? OR b = ?) AND created_at > ?
        ORDER BY created_at DESC LIMIT 1""", v.id, v.id, v.id, since)
    return {"usedBy": person_ref(_student(con, r["uid"])) if r else None, "at": r["created_at"] if r else since}


# ponytail: the old one-time fr_<token> links, no longer issued (Nov 2: one link, r_); the last ones die 7 days
# after that deploy (LINK_TTL): remove this, its route, LINK_TTL and the friend_links table after 2026-11-10.
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
        won = r["expires_at"] > core.now() and con.execute("UPDATE friend_links SET used_by = ?, used_at = ? WHERE token = ? AND used_by IS NULL",
                                                       (v.id, core.now(), token)).rowcount
        if won:
            _befriend(con, v.id, r["user_id"])
            notify(con, r["user_id"], "friend_new", f"fn:{v.id}:{core.now() // 86400}")
    return {**out, "result": "friends" if won else "used"}


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import FRAMES, _skin, _skin_ok, me  # noqa: E402
from .clubs import people  # noqa: E402
from .organizing import _ask_rating  # noqa: E402
from .oversight import _admin, _owner  # noqa: E402
from .seats import _visible, notify  # noqa: E402
from .teams import team  # noqa: E402
