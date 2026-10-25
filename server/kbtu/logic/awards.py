"""People's pages and awards: streaks, achievements, grants, the first 500."""
from __future__ import annotations

import json
import secrets
import sqlite3
import time

from ..db import tx

from .core import (ApiError, PERSON, PERSON_COLS, PROFILE_QR, SEASON_MONTHS, Viewer, log_action, need_student, one,
    rows)


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
    ("referral", "megaphone_3d", (3, 10, 25, 50), False),  # students brought by my invite link who signed in with KBTU
]


def _counts(con, uid: int) -> dict[str, int]:
    times = attended(con, uid)
    grants = dict(rows(con, "SELECT code, COUNT(*) FROM achievement_grants WHERE user_id = ? GROUP BY code", uid))
    first_in = one(con, """SELECT COUNT(*) FROM registrations r WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND r.checked_in_at =
        (SELECT MIN(x.checked_in_at) FROM registrations x WHERE x.event_id = r.event_id)""", uid)[0]
    soul = one(con, "SELECT COUNT(*) FROM registrations WHERE invited_by = ? AND checked_in_at IS NOT NULL", uid)[0]
    referral = brought(con, uid)
    team = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.checked_in_at IS NOT NULL AND e.status = 'published' AND e.visibility = 'members'""", uid)[0]
    seasons = [_season_start(t) for t in times]  # the best semester counts: every semester is a new chance
    busy = {_week(r[0]) for r in rows(con, "SELECT starts_at FROM events WHERE status = 'published' AND visibility = 'public'")}
    streak, streak_now = _streak({_week(t) for t in times}, busy, _week(core.now()))
    return {"regular": len(times), "streak": streak, "streak_now": streak_now, "first_in": first_in, "soul": soul, "team": team,
            "season": max(map(seasons.count, set(seasons)), default=0), "first50": grants.get("first50", 0),
            "creator_laugh": grants.get("creator_laugh", 0), "creator_found": grants.get("creator_found", 0), "bugs": grants.get("bugs", 0), "referral": referral}


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
                        ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at""", (uid, code, level, core.now()))
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
    """The admin's one-time award link (owner, Oct 13: "Bug hunter" is earned in a chat, so it goes as a link there;
    the face-to-face ones stay on the badge QR): one student, once, within 7 days."""
    _admin(v)
    if code not in GRANTABLE:
        raise ApiError("bad_input")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (token, code, v.id, core.now(), core.now() + GRANT_LINK_TTL))
    return token


def use_grant_link(con, v: Viewer, token: str) -> dict:
    """A student opened an award link: theirs, celebrated like any new level. A used or old link is 'closed'."""
    need_student(v)
    with tx(con):
        r = one(con, "SELECT * FROM grant_links WHERE token = ? AND used_by IS NULL AND expires_at > ?", token, core.now())
        if not r:
            raise ApiError("closed")
        _grant(con, r["created_by"], v.id, r["code"])
        con.execute("UPDATE grant_links SET used_by = ?, used_at = ? WHERE token = ?", (v.id, core.now(), token))
    return {"code": r["code"]}


def ungrant(con, v: Viewer, gid: int) -> None:
    """Undo a grant of mine within a minute (the scanner's undo): the level goes back, its unsent bot card goes."""
    _admin(v)
    g = one(con, "SELECT * FROM achievement_grants WHERE id = ? AND granted_by = ? AND created_at >= ?", gid, v.id, core.now() - 60)
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
        log_action(con, v.id, "ungrant", f"user:{g['user_id']}", json.dumps({"code": g["code"]}))


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
    con.execute("INSERT INTO achievement_grants (user_id, code, note, created_at) VALUES (?, 'first50', 'verification', ?)", (uid, core.now()))
    log_action(con, None, "first50", f"user:{uid}")
    con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'first50', 1, ?)
        ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1), reached_at = excluded.reached_at""", (uid, core.now()))
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


PROFILES_A_DAY = 200  # strangers' profiles a day (audit M2): browsing needs a few dozen, a scrape needs thousands


def _stranger_view(con, v: Viewer, uid: int) -> None:
    """Counts a profile opened by someone who is neither a friend nor a clubmate; past the day's limit, refused. One
    row per (Almaty day, viewer, profile), so reopening the same one is free; the day before yesterday's rows go."""
    day = (core.now() + 5 * 3600) // 86400
    if one(con, "SELECT 1 FROM profile_views WHERE day = ? AND viewer_id = ? AND user_id = ?", day, v.id, uid):
        return
    con.execute("DELETE FROM profile_views WHERE day < ?", (day - 1,))  # ponytail: count then insert, a burst can pass 200 by a few
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
    u = one(con, "SELECT bio, showcase, show_going, card_no, is_founder, tg_username, skin_pick, skin_org, city, city_hidden FROM users WHERE id = ?", uid)
    link = one(con, "SELECT created_at FROM friendships WHERE a = ? AND b = ?", min(uid, v.id), max(uid, v.id))
    # their @username, to their own club's team only (§3: the team sees it in its roster anyway): "Message on Telegram"
    team = uid != v.id and one(con, "SELECT 1 FROM org_members a JOIN org_members b ON b.org_id = a.org_id WHERE a.user_id = ? AND b.user_id = ?",
                               v.id, uid) is not None
    state = "none" if uid == v.id else friendship(con, v.id, uid)
    close = uid == v.id or link is not None or team or v.role in ("admin", "moderator")  # the team: reports need it all
    if not close:
        _stranger_view(con, v, uid)
    # when a level was reached is the second of a check-in: matched against the Afisha it names the event (review, Oct 23)
    ach = [a if close else {**a, "at": None} for a in achievements(con, uid)]
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
        # the role shows only to the club's own team (owner, Oct 15): outside, just the club
        "clubs": [{"org": org_ref(con, m), "role": m["role"] if m["mine"] else None, "title": m["title"] if m["mine"] else None} for m in rows(con, """
            SELECT m.role, t.name AS title, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = m.org_id AND x.user_id = ?) AS mine, o.* FROM org_members m
            JOIN orgs o ON o.id = m.org_id LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ?""", v.id, uid) if close],
        # where they were before (org_history, written by triggers): a role held at least a day, the club still shown;
        # the role by the same rule as above. Newest first
        "past": [{"org": org_ref(con, h), "role": h["role"] if h["mine"] else None, "since": h["since"], "until": h["until"]} for h in rows(con, """
            SELECT h.role, h.since, h.until, EXISTS (SELECT 1 FROM org_members x WHERE x.org_id = h.org_id AND x.user_id = ?) AS mine, o.*
            FROM org_history h JOIN orgs o ON o.id = h.org_id
            WHERE h.user_id = ? AND h.until IS NOT NULL AND h.until - h.since >= 86400 AND o.status = 'active'
            ORDER BY h.until DESC LIMIT 20""", v.id, uid) if close],
        "showcase": [a for c in u["showcase"].split(",") for a in ach if a["code"] == c and a["level"] > 0],
        # the showcase as picked (achievements earned, badges owned), in order; empty = never picked, the badge shows a default
        "shelf": [k for k in u["showcase"].split(",") if any(a["code"] == k and a["level"] > 0 for a in ach) or any(f"b{b['eventId']}" == k for b in badges)],
        "awards": {"achievements": ach, "badges": badges},
        "friendship": state, "friendsSince": link["created_at"] if link else None, "going": going,
        "username": u["tg_username"] if team else None,
        # a badge picked to be shown, shows; the one that came by itself from a club would tell a stranger the club
        "skin": _skin(con, uid) if close else "sower" if u["is_founder"] and u["skin_pick"] in ("sower", None)
                else u["skin_org"] if u["skin_pick"] == "org" and _skin_ok(con, uid, u["skin_org"]) else None,
        **({} if close else {"limited": True}),
    }


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import _skin, _skin_ok  # noqa: E402
from .appteam import _admin  # noqa: E402
from .befriending import friendship  # noqa: E402
from .clubs import people  # noqa: E402
from .organizing import _ask_rating  # noqa: E402
from .seats import _visible, notify  # noqa: E402
from .shapes import _org, _roles, cards, org_ref, person_ref  # noqa: E402
from .teams import team  # noqa: E402
