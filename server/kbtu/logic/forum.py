"""F1 find people (the forum, PLAN "F1 spec" + "Forum adversarial review"): skills from one shared catalog, requests
for help, contact only by double opt-in (nothing of either side shows until the other accepts), blocks, a few pings.
The forum's gate (a server flag, staff only for now) is app.py's; everything here assumes the caller may use it."""
from __future__ import annotations

import difflib
import re
import unicodedata

from ..db import tx
from .core import ApiError, Viewer, need_student, one, rows

PUBLIC_AT = 3            # a skill someone made shows in everyone's suggestions once this many people have it (or a moderator approves)
MY_SKILLS, ASK_SKILLS, NAME_MAX = 5, 3, 24
NEW_SKILLS_A_DAY = 10
STALE = 30 * 86400       # a made-up skill nobody has, untouched this long, leaves the suggestions
TITLE_MAX, BODY_MAX = 80, 500
DAYS = (1, 3, 7, 30)
OPEN_ASKS = 3            # live or waiting requests per person
CONTACTS_A_DAY = 10
SEARCHES_AN_HOUR = 30
PING_TOP, PING_DAY, PING_WEEK = 5, 1, 2   # a project request pings its best five matches; nobody gets more than 1 a day, 2 a week
KEEP = 30 * 86400        # a request this long after it ran out, and a ping's record, then gone (the privacy policy)
DECIDE_IN = 86400  # a held or reported request waits a moderator's word this long (shown as a deadline)
HIDE_AT, REPORTER_AGE = 3, 14 * 86400     # reports from accounts older than two weeks; with an AI flag or a moderator: hidden


def norm_skill(raw: object) -> str | None:
    """A skill's name as stored: no emoji or symbols, single spaces, lowercase; None if nothing is left or it's too long."""
    s = unicodedata.normalize("NFKC", str(raw or ""))
    s = re.sub(r"[^\w+#.\- ]", " ", s).replace("_", " ")
    s = " ".join(s.split()).strip(" .-").lower()
    return s if s and len(s) <= NAME_MAX and re.search(r"[^\W_]", s) else None


def _people(con, sid: int) -> int:
    return one(con, "SELECT COUNT(*) FROM user_skills WHERE skill_id = ?", sid)[0]


def _skill(con, s) -> dict:
    n = _people(con, s["id"])
    return {"id": s["id"], "name": s["name"], "people": n, "public": bool(s["approved"]) or n >= PUBLIC_AT}


def skills(con, v: Viewer, q: object = "") -> list[dict]:
    """Suggestions while typing: the public skills (and the ones I made), the most common first."""
    q = norm_skill(q) or ""
    found = rows(con, f"""SELECT s.*, (SELECT COUNT(*) FROM user_skills x WHERE x.skill_id = s.id) AS n FROM skills s
        WHERE s.name LIKE ? AND (s.approved = 1 OR s.created_by = ?
            OR (SELECT COUNT(*) FROM user_skills x WHERE x.skill_id = s.id) >= {PUBLIC_AT})
        ORDER BY n DESC, s.name LIMIT 12""", f"%{q}%", v.id)
    return [_skill(con, s) for s in found if s["approved"] or s["n"] or s["used_at"] > _now() - STALE or s["created_by"] == v.id]


def skill_lookup(con, v: Viewer, raw: object, force: bool = False) -> dict:
    """Before a new skill: the same one if it exists ({skill}), close ones to pick instead ({didYouMean}), else the
    normalised name to create ({name}) once the AI has looked at it."""
    need_student(v)
    name = norm_skill(raw)
    if not name:
        raise ApiError("bad_input")
    if s := one(con, "SELECT * FROM skills WHERE name = ?", name):
        return {"skill": _skill(con, s)}
    if not force:
        flat = re.sub(r"[^\w]", "", name)
        near = [s for s in rows(con, "SELECT * FROM skills") if re.sub(r"[^\w]", "", s["name"]) == flat
                or difflib.SequenceMatcher(None, s["name"], name).ratio() >= 0.8]
        if near:
            return {"didYouMean": [_skill(con, s) for s in near[:3]]}
    return {"name": name}


def add_skill(con, v: Viewer, name: str) -> dict:
    """A new skill in the catalog (lookup said it's new, the AI didn't object): mine at once, everyone's at PUBLIC_AT."""
    with tx(con):
        if s := one(con, "SELECT * FROM skills WHERE name = ?", name):  # two people at once
            return _skill(con, s)
        if one(con, "SELECT COUNT(*) FROM skills WHERE created_by = ? AND created_at > ?", v.id, _now() - 86400)[0] >= NEW_SKILLS_A_DAY:
            raise ApiError("rate_limited")
        sid = con.execute("INSERT INTO skills (name, created_by, created_at, used_at) VALUES (?, ?, ?, ?)", (name, v.id, _now(), _now())).lastrowid
    return _skill(con, one(con, "SELECT * FROM skills WHERE id = ?", sid))


def _skills_of(con, table: str, col: str, rid: int) -> list[dict]:
    return [{"id": s["id"], "name": s["name"]} for s in rows(con, f"""SELECT s.id, s.name FROM {table} t JOIN skills s ON s.id = t.skill_id
        WHERE t.{col} = ? ORDER BY s.name""", rid)]  # table and column from this module only


def my_forum(con, v: Viewer) -> dict:
    u = one(con, "SELECT open_projects, ask_pings FROM users WHERE id = ?", v.id)
    return {"skills": _skills_of(con, "user_skills", "user_id", v.id), "open": bool(u["open_projects"]), "pings": bool(u["ask_pings"])}


def set_my_forum(con, v: Viewer, body: dict) -> dict:
    """My skills (up to MY_SKILLS), "open to projects" and the pings (both off until I turn them on)."""
    need_student(v)
    with tx(con):
        if "skills" in body:
            ids = body["skills"]
            if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
                raise ApiError("bad_input")
            ids = list(dict.fromkeys(ids))
            if len(ids) > MY_SKILLS:
                raise ApiError("bad_input")
            if len(rows(con, f"SELECT id FROM skills WHERE id IN ({','.join('?' * len(ids))})", *ids)) != len(ids) if ids else False:
                raise ApiError("bad_input")
            con.execute("DELETE FROM user_skills WHERE user_id = ?", (v.id,))
            con.executemany("INSERT INTO user_skills (user_id, skill_id) VALUES (?, ?)", [(v.id, i) for i in ids])
            con.executemany("UPDATE skills SET used_at = ? WHERE id = ?", [(_now(), i) for i in ids])
        for key, col in (("open", "open_projects"), ("pings", "ask_pings")):
            if key in body:
                if not isinstance(body[key], bool):
                    raise ApiError("bad_input")
                con.execute(f"UPDATE users SET {col} = ? WHERE id = ?", (int(body[key]), v.id))  # col from the pair above
    return my_forum(con, v)


def skill_mod(con, v: Viewer, sid: int, body: dict) -> dict | None:
    """A moderator's say over the catalog: approve, rename, merge into another, delete."""
    _mod(v)
    s = one(con, "SELECT * FROM skills WHERE id = ?", sid)
    if not s:
        raise ApiError("not_found")
    with tx(con):
        if body.get("delete") is True:
            con.execute("DELETE FROM skills WHERE id = ?", (sid,))
            log_action(con, v.id, "skill_delete", f"skill:{sid}", s["name"])
            return None
        if "into" in body:
            into = body["into"]
            if not isinstance(into, int) or into == sid or not one(con, "SELECT 1 FROM skills WHERE id = ?", into):
                raise ApiError("bad_input")
            for t, col in (("user_skills", "user_id"), ("ask_skills", "ask_id")):  # names from this module only
                con.execute(f"INSERT OR IGNORE INTO {t} ({col}, skill_id) SELECT {col}, ? FROM {t} WHERE skill_id = ?", (into, sid))
            con.execute("DELETE FROM skills WHERE id = ?", (sid,))
            log_action(con, v.id, "skill_merge", f"skill:{sid}", str(into))
            return _skill(con, one(con, "SELECT * FROM skills WHERE id = ?", into))
        if "name" in body:
            name = norm_skill(body["name"])
            if not name:
                raise ApiError("bad_input")
            if one(con, "SELECT 1 FROM skills WHERE name = ? AND id != ?", name, sid):
                raise ApiError("conflict", "taken")  # merge instead
            con.execute("UPDATE skills SET name = ? WHERE id = ?", (name, sid))
        if body.get("approve") is True:
            con.execute("UPDATE skills SET approved = 1 WHERE id = ?", (sid,))
        log_action(con, v.id, "skill_edit", f"skill:{sid}", s["name"])
    return _skill(con, one(con, "SELECT * FROM skills WHERE id = ?", sid))


# ---- who may be matched and found: a signed-in student, open to projects; never staff, DMP's people or guests

_FINDABLE = """u.open_projects = 1 AND u.banned_at IS NULL AND u.role = 'user'
    AND EXISTS (SELECT 1 FROM students s WHERE s.user_id = u.id AND s.manual = 0)
    AND NOT EXISTS (SELECT 1 FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = u.id AND o.can_oversee = 1)"""
_UNBLOCKED = "NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.user_id = :me AND b.blocked_id = {u}) OR (b.user_id = {u} AND b.blocked_id = :me))"


def _matches(con, me: int, skill_ids: list[int], skip: int) -> list[int]:
    """Open-to-projects people with any of these skills, the most shared first, then the most recently seen."""
    if not skill_ids:
        return []
    q = ",".join(str(int(i)) for i in skill_ids)
    return [r[0] for r in con.execute(f"""SELECT u.id FROM users u JOIN user_skills k ON k.user_id = u.id AND k.skill_id IN ({q})
        WHERE {_FINDABLE} AND u.id != :skip AND {_UNBLOCKED.format(u='u.id')}
        GROUP BY u.id ORDER BY COUNT(*) DESC, u.seen_at DESC""", {"me": me, "skip": skip}).fetchall()]


def _card(con, uid: int) -> dict:
    """A person as the forum shows them before any contact: the short name, year of study and skills. No @username."""
    p = one(con, PERSON + " WHERE u.id = ?", uid)
    s = one(con, "SELECT student_id FROM students WHERE user_id = ?", uid)
    return {"person": person_ref(p), "name": short_name(p), "course": course_of(s["student_id"]) if s else None,
            "skills": _skills_of(con, "user_skills", "user_id", uid)}


def search_people(con, v: Viewer, skill: object = None, q: object = None) -> list[dict]:
    """People by a skill (its id) or by words in their skills' names; open to projects only; 30 searches an hour."""
    need_student(v)
    key = f"fsearch:{v.id}:{_now() // 3600}"
    with tx(con):
        n = int((one(con, "SELECT value FROM meta WHERE key = ?", key) or [0])[0])
        if n >= SEARCHES_AN_HOUR:
            raise ApiError("rate_limited")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(n + 1)))
    if isinstance(skill, int) and not isinstance(skill, bool):
        ids = [skill]
    else:
        words = norm_skill(q)
        ids = [r[0] for r in rows(con, "SELECT id FROM skills WHERE name LIKE ?", f"%{words}%")] if words else []
    return [_card(con, uid) for uid in _matches(con, v.id, ids, v.id)[:50]]


# ---- requests

def _ask_shape(con, v: Viewer, a) -> dict:
    mine = a["user_id"] == v.id
    sk = _skills_of(con, "ask_skills", "ask_id", a["id"])
    out = {"id": a["id"], "kind": a["kind"], "title": a["title"], "body": a["body"], "skills": sk, "createdAt": a["created_at"],
           "expiresAt": a["expires_at"], "mine": mine, "author": _card(con, a["user_id"]) | {"skills": []},
           "matches": len(_matches(con, v.id, [s["id"] for s in sk], a["user_id"]))}
    if mine:  # how it stands, and who offered to help (by the card only, until I accept)
        out |= {"status": a["status"], "why": a["why"], "found": a["found"],
                "offers": [{"id": c["id"], "status": c["status"], **_card(con, c["from_id"])} for c in
                           rows(con, "SELECT * FROM contacts WHERE ask_id = ? AND status != 'declined' ORDER BY id DESC", a["id"])]}
    else:
        c = one(con, "SELECT status FROM contacts WHERE ask_id = ? AND from_id = ?", a["id"], v.id)
        out["offered"] = c["status"] if c else None
    return out


def asks(con, v: Viewer, skill: object = None) -> list[dict]:
    """Live requests, mine first (whatever their state, until they run out), then the newest; a skill to filter by."""
    need_student(v)
    by = "AND EXISTS (SELECT 1 FROM ask_skills k WHERE k.ask_id = a.id AND k.skill_id = :skill)" if isinstance(skill, int) else ""
    found = con.execute(f"""SELECT a.* FROM asks a WHERE a.expires_at > :now AND (a.user_id = :me OR (a.status = 'live'
            AND {_UNBLOCKED.format(u='a.user_id')} AND a.id NOT IN (SELECT target_id FROM reports WHERE target = 'ask'
                AND reporter_id = :me AND status = 'open'))) {by}
        ORDER BY a.user_id = :me DESC, a.id DESC LIMIT 100""", {"now": _now(), "me": v.id, "skill": skill}).fetchall()
    return [_ask_shape(con, v, a) for a in found]


def create_ask(con, v: Viewer, body: dict, verdict: bool | None) -> dict:
    """A request: project (1-3 skills) or help (skills optional), for 1, 3, 7 or 30 days. verdict: the AI's look at the
    words (True fine, False flagged, None no answer): anything but fine waits for a moderator."""
    need_student(v)
    kind, title, text = body.get("kind"), str(body.get("title") or "").strip(), str(body.get("body") or "").strip()
    ids, days = body.get("skills") or [], body.get("days", 7 if body.get("kind") == "project" else 1)
    if kind not in ("project", "help") or not 3 <= len(title) <= TITLE_MAX or len(text) > BODY_MAX or days not in DAYS \
            or not isinstance(ids, list) or len(set(ids)) != len(ids) or len(ids) > ASK_SKILLS or (kind == "project" and not ids) \
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ApiError("bad_input")
    with tx(con):
        if ids and len(rows(con, f"SELECT id FROM skills WHERE id IN ({','.join('?' * len(ids))})", *ids)) != len(ids):
            raise ApiError("bad_input")
        if one(con, "SELECT COUNT(*) FROM asks WHERE user_id = ? AND status IN ('live', 'held') AND expires_at > ?", v.id, _now())[0] >= OPEN_ASKS:
            raise ApiError("rate_limited", "asks")
        status, why = ("live", None) if verdict else ("held", "ai" if verdict is False else "check")
        aid = con.execute("INSERT INTO asks (user_id, kind, title, body, status, why, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (v.id, kind, title, text, status, why, _now(), _now() + days * 86400)).lastrowid
        con.executemany("INSERT INTO ask_skills (ask_id, skill_id) VALUES (?, ?)", [(aid, i) for i in ids])
        con.executemany("UPDATE skills SET used_at = ? WHERE id = ?", [(_now(), i) for i in ids])
        if status == "live":
            _ping(con, aid)
    return _ask_shape(con, v, one(con, "SELECT * FROM asks WHERE id = ?", aid))


def _ping(con, aid: int) -> None:
    """A live project request: a bot card to its best matches who turned pings on, within the caps; never twice."""
    a = one(con, "SELECT * FROM asks WHERE id = ?", aid)
    if a["kind"] != "project" or a["status"] != "live":
        return
    sent = 0
    for uid in _matches(con, a["user_id"], [s["id"] for s in _skills_of(con, "ask_skills", "ask_id", aid)], a["user_id"]):
        if sent >= PING_TOP:
            break
        if not one(con, "SELECT ask_pings FROM users WHERE id = ?", uid)[0] \
                or one(con, "SELECT COUNT(*) FROM ask_pings WHERE user_id = ? AND at > ?", uid, _now() - 86400)[0] >= PING_DAY \
                or one(con, "SELECT COUNT(*) FROM ask_pings WHERE user_id = ? AND at > ?", uid, _now() - 7 * 86400)[0] >= PING_WEEK:
            continue
        if con.execute("INSERT OR IGNORE INTO ask_pings (ask_id, user_id, at) VALUES (?, ?, ?)", (aid, uid, _now())).rowcount:
            notify(con, uid, "ask_match", f"am:{aid}")
            sent += 1


def release_ask(con, v: Viewer, aid: int) -> dict:
    """A moderator lets a held request go live (its pings go out then)."""
    _mod(v)
    with tx(con):
        if not con.execute("UPDATE asks SET status = 'live', why = NULL WHERE id = ? AND status = 'held'", (aid,)).rowcount:
            raise ApiError("not_found")
        _ping(con, aid)
        log_action(con, v.id, "ask_release", f"ask:{aid}")
    return _ask_shape(con, v, one(con, "SELECT * FROM asks WHERE id = ?", aid))


def mod_queue(con, v: Viewer) -> dict:
    """What waits for a moderator: requests the AI didn't pass (or couldn't read), and skills not public yet."""
    _mod(v)
    held = [_ask_shape(con, v, a) | {"status": "held", "why": a["why"], "dueAt": a["created_at"] + DECIDE_IN}
            for a in rows(con, "SELECT * FROM asks WHERE status = 'held' AND expires_at > ? ORDER BY id", _now())]
    # reported enough without the AI's agreement: a moderator decides within a day of the report that made it enough
    for a in rows(con, "SELECT * FROM asks WHERE status = 'live' AND expires_at > ? AND id IN (SELECT target_id FROM reports WHERE target = 'ask' AND status = 'open') ORDER BY id", _now()):
        if at := _enough_at(con, a["id"]):
            held.append(_ask_shape(con, v, a) | {"status": "reported", "why": "reports", "dueAt": at + DECIDE_IN})
    held.sort(key=lambda a: a["dueAt"])
    fresh = [s for s in (_skill(con, x) for x in rows(con, "SELECT * FROM skills WHERE approved = 0 ORDER BY created_at DESC LIMIT 100")) if not s["public"]]
    return {"held": held, "skills": fresh}


def mod_hide_ask(con, v: Viewer, aid: int) -> None:
    """A moderator takes a request down (held or live); its author is told."""
    _mod(v)
    if not one(con, "SELECT 1 FROM asks WHERE id = ? AND status IN ('live', 'held')", aid):
        raise ApiError("not_found")
    with tx(con):
        hide_ask(con, aid, "moderator", v.id)
        log_action(con, v.id, "ask_hide", f"ask:{aid}")


def close_ask(con, v: Viewer, aid: int, found: object) -> dict:
    """The author: found someone (through the app or not), or no longer needed."""
    if not (found is None or isinstance(found, bool)):
        raise ApiError("bad_input")
    if not con.execute("UPDATE asks SET status = 'closed', found = ? WHERE id = ? AND user_id = ? AND status != 'hidden'",
                       (None if found is None else int(found), aid, v.id)).rowcount:
        raise ApiError("not_found")
    return _ask_shape(con, v, one(con, "SELECT * FROM asks WHERE id = ?", aid))


def ask_people(con, v: Viewer, aid: int) -> list[dict]:
    """Who has the skills a request asks for (open to projects): cards only; contact goes through an offer."""
    a = one(con, "SELECT * FROM asks WHERE id = ? AND (status = 'live' OR user_id = ?)", aid, v.id)
    if not a:
        raise ApiError("not_found")
    ids = [s["id"] for s in _skills_of(con, "ask_skills", "ask_id", aid)]
    return [_card(con, uid) for uid in _matches(con, v.id, ids, a["user_id"])[:50]]


# ---- contact: an offer the other side accepts or declines in the bot; then each gets the other's Telegram

def contact(con, v: Viewer, to: object = None, aid: object = None) -> dict:
    """"I can help" on a request (to its author), or "get in touch" with someone found by a skill (open to projects)."""
    need_student(v)
    if isinstance(aid, int) and not isinstance(aid, bool):
        a = one(con, "SELECT user_id FROM asks WHERE id = ? AND status = 'live' AND expires_at > ?", aid, _now())
        if not a:
            raise ApiError("not_found")
        to = a["user_id"]
    elif isinstance(to, int) and not isinstance(to, bool):
        aid = None
        if not one(con, f"SELECT 1 FROM users u WHERE u.id = ? AND {_FINDABLE}", to):
            raise ApiError("not_found")
    else:
        raise ApiError("bad_input")
    if to == v.id or one(con, "SELECT 1 FROM blocks WHERE (user_id = ? AND blocked_id = ?) OR (user_id = ? AND blocked_id = ?)", to, v.id, v.id, to):
        raise ApiError("not_found")
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM contacts WHERE from_id = ? AND created_at > ?", v.id, _now() - 86400)[0] >= CONTACTS_A_DAY:
            raise ApiError("rate_limited")
        cur = con.execute("INSERT OR IGNORE INTO contacts (from_id, to_id, ask_id, created_at) VALUES (?, ?, ?, ?)", (v.id, to, aid, _now()))
        if cur.rowcount:
            notify(con, to, "contact_ask", f"ct:{cur.lastrowid}")
    return {"status": "pending"}


def decide_contact(con, uid: int, cid: int, yes: bool) -> str | None:
    """The asked side's answer (the bot's buttons or the app): accepted, both get the other's Telegram. The new status."""
    with tx(con):
        c = one(con, "SELECT * FROM contacts WHERE id = ? AND to_id = ? AND status = 'pending'", cid, uid)
        if not c:
            return None
        con.execute("UPDATE contacts SET status = ?, decided_at = ? WHERE id = ?", ("accepted" if yes else "declined", _now(), cid))
        if yes:
            notify(con, c["from_id"], "contact_ok", f"co:{cid}:to")    # to the one who offered: the other's contact
            notify(con, c["to_id"], "contact_ok", f"co:{cid}:from")
    return "accepted" if yes else "declined"


def contacts(con, v: Viewer) -> list[dict]:
    """My offers both ways: pending ones to answer, and, once accepted, the other's Telegram to write to."""
    out = []
    for c in con.execute("SELECT * FROM contacts WHERE (from_id = :me OR to_id = :me) AND status != 'declined' ORDER BY id DESC LIMIT 50", {"me": v.id}).fetchall():
        other = c["to_id"] if c["from_id"] == v.id else c["from_id"]
        a = one(con, "SELECT title FROM asks WHERE id = ?", c["ask_id"]) if c["ask_id"] else None
        x = {"id": c["id"], "status": c["status"], "incoming": c["to_id"] == v.id, "ask": a["title"] if a else None, **_card(con, other)}
        if c["status"] == "accepted":
            x["telegram"] = telegram_of(con, other)
        out.append(x)
    return out


def telegram_of(con, uid: int) -> str:
    """Where to write to someone: their t.me link, or Telegram's own link by ID when they have no username."""
    u = one(con, "SELECT tg_id, tg_username FROM users WHERE id = ?", uid)
    return f"https://t.me/{u['tg_username']}" if u["tg_username"] else f"tg://user?id={u['tg_id']}"


def block(con, v: Viewer, uid: object, on: object = True) -> None:
    """Never see each other in the forum again: no offers either way, out of each other's matches and lists."""
    need_student(v)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid == v.id or not isinstance(on, bool):
        raise ApiError("bad_input")
    if on:
        con.execute("INSERT OR IGNORE INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, ?)", (v.id, uid, _now()))
        con.execute("UPDATE contacts SET status = 'declined', decided_at = ? WHERE status = 'pending' AND ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))",
                    (_now(), v.id, uid, uid, v.id))
    else:
        con.execute("DELETE FROM blocks WHERE user_id = ? AND blocked_id = ?", (v.id, uid))


# ---- reports: hidden only by 3 reports from accounts older than two weeks AND the AI or a moderator

def reported_enough(con, aid: int) -> bool:
    """Three open reports from accounts at least two weeks old: worth the AI's look (app.py), else a moderator's."""
    return one(con, """SELECT COUNT(DISTINCT r.reporter_id) FROM reports r JOIN users u ON u.id = r.reporter_id
        WHERE r.target = 'ask' AND r.target_id = ? AND r.status = 'open' AND u.created_at <= ?""", aid, _now() - REPORTER_AGE)[0] >= HIDE_AT


def _enough_at(con, aid: int) -> int | None:
    """When the open reports from old enough accounts reached three: the moderators' day starts then."""
    at = [r[0] for r in con.execute("""SELECT MIN(r.created_at) FROM reports r JOIN users u ON u.id = r.reporter_id
        WHERE r.target = 'ask' AND r.target_id = ? AND r.status = 'open' AND u.created_at <= ? GROUP BY r.reporter_id ORDER BY 1""",
        (aid, _now() - REPORTER_AGE))]
    return at[HIDE_AT - 1] if len(at) >= HIDE_AT else None


def hide_ask(con, aid: int, why: str, by: int | None = None) -> None:
    """Out of the lists, the author told why (the AI agreeing with the reports, or a moderator)."""
    if con.execute("UPDATE asks SET status = 'hidden', why = ? WHERE id = ? AND status IN ('live', 'held')", (why, aid)).rowcount:
        a = one(con, "SELECT user_id FROM asks WHERE id = ?", aid)
        notify(con, a["user_id"], "ask_hidden", f"ah:{aid}")
        con.execute("UPDATE reports SET status = 'actioned', resolved_by = ?, resolved_at = ? WHERE target = 'ask' AND target_id = ? AND status = 'open'",
                    (by, _now(), aid))


def forum_sweep(con) -> None:
    """What the privacy policy promises: a request goes 30 days after it ran out (its skills, offers and pings with
    it), and the record of who was pinged after 30 days (the caps look back a week)."""
    con.execute("DELETE FROM asks WHERE expires_at < ?", (_now() - KEEP,))
    con.execute("DELETE FROM ask_pings WHERE at < ?", (_now() - KEEP,))


def _now() -> int:
    return core.now()


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .appteam import _mod  # noqa: E402
from .core import PERSON, log_action  # noqa: E402
from .seats import notify  # noqa: E402
from .shapes import course_of, person_ref, short_name  # noqa: E402
