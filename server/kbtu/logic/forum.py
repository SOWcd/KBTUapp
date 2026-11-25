"""F1 find people: skills, requests, contact by double opt-in, blocks, pings (PLAN F1)."""
from __future__ import annotations

import difflib
import json
import re
import secrets
import unicodedata

from ..db import tx

from . import notifications
from .core import (ApiError, PERSON_COLS, Viewer, _qs, course_of, log_action, need_student, one, person_ref, rows, short_name)


PUBLIC_AT = 3            # a skill someone made shows in everyone's suggestions once this many people have it (or a moderator approves)
MY_SKILLS, ASK_SKILLS, NAME_MAX = 5, 3, 24
NEW_SKILLS_A_DAY = 10
STALE = 30 * 86400       # a made-up skill nobody has, untouched this long, leaves the suggestions
TITLE_MAX, BODY_MAX = 80, 500
DAYS = (1, 3, 7, 30)
OPEN_ASKS = 3            # live or waiting requests per person
CONTACTS_A_DAY = 10
SEARCHES_AN_HOUR = 30
SCREENS_AN_HOUR = 30     # paid looks, including rejected skill names and requests closed again
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


def _holders(con, sid: int) -> int:
    return one(con, "SELECT COUNT(*) FROM user_skills WHERE skill_id = ?", sid)[0]


def _skill(con, s) -> dict:
    n = s["n"] if "n" in s.keys() else _holders(con, s["id"])
    return {"id": s["id"], "name": s["name"], "people": n, "public": bool(s["approved"]) or n >= PUBLIC_AT}


def skills(con, v: Viewer, q: object = "") -> list[dict]:
    """Suggestions while typing: the public skills (and the ones I made), the most common first."""
    q = norm_skill(q) or ""
    found = rows(con, f"""SELECT s.*, (SELECT COUNT(*) FROM user_skills x WHERE x.skill_id = s.id) AS n FROM skills s
        WHERE s.name LIKE ? AND (s.approved = 1 OR s.created_by = ?
            OR (SELECT COUNT(*) FROM user_skills x WHERE x.skill_id = s.id) >= {PUBLIC_AT})
        ORDER BY n DESC, s.name LIMIT 12""", f"%{q}%", v.id)
    return [_skill(con, s) for s in found if s["approved"] or s["n"] or s["used_at"] > core.now() - STALE or s["created_by"] == v.id]


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
        core.need_current_student(con, v)
        if s := one(con, "SELECT * FROM skills WHERE name = ?", name):  # two people at once
            return _skill(con, s)
        if one(con, "SELECT COUNT(*) FROM skills WHERE created_by = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= NEW_SKILLS_A_DAY:
            raise ApiError("rate_limited")
        sid = con.execute("INSERT INTO skills (name, created_by, created_at, used_at) VALUES (?, ?, ?, ?)", (name, v.id, core.now(), core.now())).lastrowid
    return _skill(con, one(con, "SELECT * FROM skills WHERE id = ?", sid))


def _screen_room(con, v: Viewer) -> None:
    """Reserve a paid look inside the caller's transaction, including when screening rejects the words."""
    core.need_current_student(con, v)
    key = f"flook:{v.id}:{core.now() // 3600}"
    n = int((one(con, "SELECT value FROM meta WHERE key = ?", key) or [0])[0])
    if n >= SCREENS_AN_HOUR:
        raise ApiError("rate_limited", "forum")
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(n + 1)))


def reserve_skill(con, v: Viewer, raw: object, force: bool) -> dict:
    found = skill_lookup(con, v, raw, force)
    if "name" in found:
        with tx(con):
            if one(con, "SELECT COUNT(*) FROM skills WHERE created_by = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= NEW_SKILLS_A_DAY:
                raise ApiError("rate_limited")
            _screen_room(con, v)
    return found


def _skills_by(con, table: str, col: str, ids: list[int]) -> dict[int, list[dict]]:
    skills = {}
    if ids:
        for rid, sid, name in rows(con, f"""SELECT t.{col}, s.id, s.name FROM {table} t JOIN skills s ON s.id = t.skill_id
                WHERE t.{col} IN ({_qs(ids)}) ORDER BY s.name""", *ids):  # table and column from this module only
            skills.setdefault(rid, []).append({"id": sid, "name": name})
    return skills


def _skills_of(con, table: str, col: str, rid: int) -> list[dict]:
    return _skills_by(con, table, col, [rid]).get(rid, [])


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
            con.executemany("UPDATE skills SET used_at = ? WHERE id = ?", [(core.now(), i) for i in ids])
        for key in ("open", "pings"):
            if key in body and not isinstance(body[key], bool):
                raise ApiError("bad_input")
        if "open" in body:
            con.execute("UPDATE users SET open_projects = ? WHERE id = ?", (int(body["open"]), v.id))
        if "pings" in body:
            notifications.set_preference(con, v.id, "nProjectPings", body["pings"])
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


def public_profile(con, v: Viewer, uid: int) -> dict | None:
    public = con.execute(f"""SELECT 1 FROM users u WHERE u.id = :id AND {_FINDABLE}
        AND {_UNBLOCKED.format(u='u.id')}""", {"id": uid, "me": v.id}).fetchone()
    if public:
        return {"skills": _skills_of(con, "user_skills", "user_id", uid), "open": True}
    return None


def _matches(con, me: int, skill_ids: list[int], skip: int) -> list[int]:
    """Open-to-projects people with any of these skills, the most shared first, then the most recently seen."""
    if not skill_ids:
        return []
    q = ",".join(str(int(i)) for i in skill_ids)
    return [r[0] for r in con.execute(f"""SELECT u.id FROM users u JOIN user_skills k ON k.user_id = u.id AND k.skill_id IN ({q})
        WHERE {_FINDABLE} AND u.id != :skip AND {_UNBLOCKED.format(u='u.id')}
        GROUP BY u.id ORDER BY COUNT(*) DESC, u.seen_at DESC""", {"me": me, "skip": skip}).fetchall()]


def _cards(con, uids: list[int], *, with_skills: bool = True) -> dict[int, dict]:
    """People as the forum shows them before any contact: the short name, year of study and skills. No @username.
    One read per fact for the whole list."""
    ids = list(set(uids))
    if not ids:
        return {}
    skills = _skills_by(con, "user_skills", "user_id", ids) if with_skills else {}
    people = rows(con, f"""SELECT {PERSON_COLS}, s.student_id FROM users u LEFT JOIN students s ON s.user_id = u.id
        WHERE u.id IN ({_qs(ids)})""", *ids)
    return {p["id"]: {"person": person_ref(p), "name": short_name(p), "course": course_of(p["student_id"]),
                      "skills": skills.get(p["id"], [])} for p in people}


def search_people(con, v: Viewer, skill: object = None, q: object = None) -> list[dict]:
    """People by a skill (its id) or by words in their skills' names; open to projects only; 30 searches an hour."""
    need_student(v)
    key = f"fsearch:{v.id}:{core.now() // 3600}"
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
    found = _matches(con, v.id, ids, v.id)[:50]
    cards = _cards(con, found)
    return [cards[uid] for uid in found]


# ---- requests

def _ask_shapes(con, v: Viewer, found) -> list[dict]:
    if not found:
        return []
    ids = [a["id"] for a in found]
    authors = _cards(con, [a["user_id"] for a in found], with_skills=False)
    skills = _skills_by(con, "ask_skills", "ask_id", ids)
    # The same pool as _matches: a person with two of the requested skills still counts once.
    matches = dict(con.execute(f"""SELECT a.id, COUNT(DISTINCT u.id) FROM asks a
        JOIN ask_skills s ON s.ask_id = a.id JOIN user_skills k ON k.skill_id = s.skill_id JOIN users u ON u.id = k.user_id
        WHERE a.id IN (SELECT value FROM json_each(:ids)) AND u.id != a.user_id AND {_FINDABLE} AND {_UNBLOCKED.format(u='u.id')}
        GROUP BY a.id""", {"ids": json.dumps(ids), "me": v.id})) if skills else {}

    own = [a["id"] for a in found if a["user_id"] == v.id]
    incoming = rows(con, f"""SELECT ask_id, from_id, id, status FROM contacts WHERE ask_id IN ({_qs(own)})
        AND status != 'declined' ORDER BY id DESC""", *own) if own else []
    cards = _cards(con, [c["from_id"] for c in incoming])
    offers = {}
    for c in incoming:
        offers.setdefault(c["ask_id"], []).append({"id": c["id"], "status": c["status"], **cards[c["from_id"]]})
    others = [a["id"] for a in found if a["user_id"] != v.id]
    offered = dict(rows(con, f"SELECT ask_id, status FROM contacts WHERE from_id = ? AND ask_id IN ({_qs(others)}) AND withdrawn_at IS NULL",
                        v.id, *others)) if others else {}

    out = []
    for a in found:
        aid, mine = a["id"], a["user_id"] == v.id
        details = {"status": a["status"], "why": a["why"], "found": a["found"], "offers": offers.get(aid, [])} if mine else {"offered": offered.get(aid)}
        out.append({"id": aid, "kind": a["kind"], "title": a["title"], "body": a["body"], "skills": skills.get(aid, []),
                    "createdAt": a["created_at"], "expiresAt": a["expires_at"], "mine": mine, "author": authors[a["user_id"]],
                    "matches": matches.get(aid, 0), **details})
    return out


def _ask_shape(con, v: Viewer, a) -> dict:
    return _ask_shapes(con, v, [a])[0]


def asks(con, v: Viewer, skill: object = None) -> list[dict]:
    """Live requests, mine first (whatever their state, until they run out), then the newest; a skill to filter by."""
    need_student(v)
    by = "AND EXISTS (SELECT 1 FROM ask_skills k WHERE k.ask_id = a.id AND k.skill_id = :skill)" if isinstance(skill, int) else ""
    found = con.execute(f"""SELECT a.* FROM asks a WHERE a.expires_at > :now AND (a.user_id = :me OR (a.status = 'live'
            AND {_UNBLOCKED.format(u='a.user_id')} AND a.id NOT IN (SELECT target_id FROM reports WHERE target = 'ask'
                AND reporter_id = :me AND status = 'open'))) AND a.subject IS NULL {by}
        ORDER BY a.user_id = :me DESC, a.id DESC LIMIT 100""", {"now": core.now(), "me": v.id, "skill": skill}).fetchall()
    return _ask_shapes(con, v, found)


def create_ask(con, v: Viewer, body: dict, verdict: bool | None, *, screening: bool = False) -> dict:
    """A request: project (1-3 skills) or help (skills optional), for 1, 3, 7 or 30 days. verdict: the AI's look at the
    words (True fine, False flagged, None no answer): anything but fine waits for a moderator."""
    need_student(v)
    kind, title, text = body.get("kind"), str(body.get("title") or "").strip(), str(body.get("body") or "").strip()
    ids, days = body.get("skills") or [], body.get("days", 7 if body.get("kind") == "project" else 1)
    if kind not in ("project", "help") or not 3 <= len(title) <= TITLE_MAX or len(text) > BODY_MAX or days not in DAYS \
            or not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids) \
            or len(set(ids)) != len(ids) or len(ids) > ASK_SKILLS or (kind == "project" and not ids):
        raise ApiError("bad_input")
    with tx(con):
        if ids and len(rows(con, f"SELECT id FROM skills WHERE id IN ({','.join('?' * len(ids))})", *ids)) != len(ids):
            raise ApiError("bad_input")
        if one(con, "SELECT COUNT(*) FROM asks WHERE user_id = ? AND status IN ('live', 'held') AND expires_at > ? AND subject IS NULL", v.id, core.now())[0] >= OPEN_ASKS:
            raise ApiError("rate_limited", "asks")
        if screening:
            _screen_room(con, v)
        status, why = ("live", None) if verdict else ("held", "ai" if verdict is False else "check")
        aid = con.execute("INSERT INTO asks (id, user_id, kind, title, body, status, why, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (core.next_id(con, "asks"), v.id, kind, title, text, status, why, core.now(), core.now() + days * 86400)).lastrowid
        con.executemany("INSERT INTO ask_skills (ask_id, skill_id) VALUES (?, ?)", [(aid, i) for i in ids])
        con.executemany("UPDATE skills SET used_at = ? WHERE id = ?", [(core.now(), i) for i in ids])
        if status == "live":
            _ping(con, aid)
        return _ask_shape(con, v, one(con, "SELECT * FROM asks WHERE id = ?", aid))


def settle_ask(con, v: Viewer, aid: int, verdict: bool | None) -> dict:
    with tx(con):
        status, why = ("live", None) if verdict else ("held", "ai" if verdict is False else "check")
        changed = con.execute("UPDATE asks SET status = ?, why = ? WHERE id = ? AND user_id = ? AND status = 'held' AND why = 'check'",
                              (status, why, aid, v.id)).rowcount
        a = one(con, "SELECT * FROM asks WHERE id = ? AND user_id = ?", aid, v.id)
        if not a:
            raise ApiError("not_found")
        if changed and status == "live":
            _ping(con, aid)
        return _ask_shape(con, v, a)


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
                or one(con, "SELECT COUNT(*) FROM ask_pings WHERE user_id = ? AND at > ?", uid, core.now() - 86400)[0] >= PING_DAY \
                or one(con, "SELECT COUNT(*) FROM ask_pings WHERE user_id = ? AND at > ?", uid, core.now() - 7 * 86400)[0] >= PING_WEEK:
            continue
        if con.execute("INSERT OR IGNORE INTO ask_pings (ask_id, user_id, at) VALUES (?, ?, ?)", (aid, uid, core.now())).rowcount:
            notify(con, uid, "ask_match", f"am:{aid}")
            sent += 1


_SUBJ = " AND subject IS NOT NULL"  # only a subject's listings: the forum's own requests stay the forum's (FORUM)


def may_touch_ask(con, aid: object) -> bool:
    """The one rule for whether a request may surface for this caller at all (reporting it, the reports' queue and its
    decision, Admin's count and Done): every one for the forum's people (app.viewer's asks_all: FORUM's gate), else a
    subject's listing alone (logic/subjects.py), and that only to a student on the policy in force. No caller (the bot,
    a job): every one."""
    c = core.CALLER.get()
    return c is None or c.get("asks_all", True) or bool(
        isinstance(aid, int) and one(con, "SELECT 1 FROM asks WHERE id = ? AND subject IS NOT NULL", aid)
        and subjects.may_read(con, c.get("uid", 0)))  # the subject reads' own gate, wherever a report shows one


def release_ask(con, v: Viewer, aid: int, subjects_only: bool = False) -> dict:
    """A moderator lets a held request go live (its pings go out then). A take-down is undone apart (subjects.lift)."""
    _mod(v)
    with tx(con):
        if not con.execute("UPDATE asks SET status = 'live', why = NULL WHERE id = ? AND status = 'held'" + (_SUBJ if subjects_only else ""), (aid,)).rowcount:
            raise ApiError("not_found")
        _ping(con, aid)
        log_action(con, v.id, "ask_release", f"ask:{aid}")
    return _ask_shape(con, v, one(con, "SELECT * FROM asks WHERE id = ?", aid))


def mod_queue(con, v: Viewer, catalog: bool = True, subjects_only: bool = False) -> dict:
    """What waits for a moderator: requests the AI didn't pass (or couldn't read), a subject's listings too
    (logic/subjects.py), and skills not public yet (catalog: the forum is on; else null). subjects_only: the caller
    isn't the forum's (FORUM off or not theirs): a subject's listings alone."""
    _mod(v)
    only = _SUBJ if subjects_only else ""
    held = [_ask_shape(con, v, a) | {"status": "held", "why": a["why"], "dueAt": a["created_at"] + DECIDE_IN}
            for a in rows(con, f"SELECT * FROM asks WHERE status = 'held' AND expires_at > ?{only} ORDER BY id", core.now())]
    # reported enough without the AI's agreement: a moderator decides within a day of the report that made it enough
    for a in rows(con, f"SELECT * FROM asks WHERE status = 'live' AND expires_at > ?{only} AND id IN (SELECT target_id FROM reports WHERE target = 'ask' AND status = 'open') ORDER BY id", core.now()):
        if at := _enough_at(con, a["id"]):
            held.append(_ask_shape(con, v, a) | {"status": "reported", "why": "reports", "dueAt": at + DECIDE_IN})
    held.sort(key=lambda a: a["dueAt"])
    holds = subjects.holds(con)  # the subjects' take-downs standing this term (and lifted ones, to put back)
    fresh = [s for s in (_skill(con, x) for x in rows(con, "SELECT * FROM skills WHERE approved = 0 ORDER BY created_at DESC LIMIT 100")) if not s["public"]]
    return {"held": held, "skills": fresh if catalog else None, "holds": holds}


def mod_hide_ask(con, v: Viewer, aid: int, subjects_only: bool = False) -> None:
    """A moderator takes a request down (held or live); its author is told."""
    _mod(v)
    if not one(con, "SELECT 1 FROM asks WHERE id = ? AND status IN ('live', 'held')" + (_SUBJ if subjects_only else ""), aid):
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
    found = _matches(con, v.id, ids, a["user_id"])[:50]
    cards = _cards(con, found)
    return [cards[uid] for uid in found]


# ---- contact: an offer the other side accepts or declines in the bot; then each gets the other's Telegram

def contact(con, v: Viewer, to: object = None, aid: object = None) -> dict:
    """"I can help" on a request (to its author), or "get in touch" with someone found by a skill (open to projects)."""
    need_student(v)
    with tx(con):  # whose the request is, read in the same write as the offer: never a row that changed hands meanwhile
        if isinstance(aid, int) and not isinstance(aid, bool):
            a = one(con, "SELECT user_id FROM asks WHERE id = ? AND status = 'live' AND expires_at > ?", aid, core.now())
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
        if one(con, "SELECT COUNT(*) FROM contacts WHERE from_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= CONTACTS_A_DAY:
            raise ApiError("rate_limited")
        token = secrets.token_hex(4)  # the offer's own, beside an id that never comes back (core.next_id)
        cur = con.execute("INSERT OR IGNORE INTO contacts (id, from_id, to_id, ask_id, created_at, token) VALUES (?, ?, ?, ?, ?, ?)",
                          (core.next_id(con, "contacts"), v.id, to, aid, core.now(), token))
        if cur.rowcount:
            notify(con, to, "contact_ask", f"ct:{cur.lastrowid}:{token}")
        # Give tokenless offers a fresh card so its buttons can identify the exact offer.
        elif old := one(con, """SELECT id FROM contacts WHERE from_id = ? AND to_id = ? AND COALESCE(ask_id, 0) = COALESCE(?, 0)
                        AND token IS NULL AND withdrawn_at IS NULL""",
                        v.id, to, aid):
            con.execute("UPDATE contacts SET token = ? WHERE id = ?", (token, old["id"]))
            notify(con, to, "contact_ask", f"ct:{old['id']}:{token}")
    return {"status": "pending"}


def decide_contact(con, uid: int, cid: int, yes: bool, token: str | None = None) -> str | None:
    """The asked side's answer (the bot's buttons or the app): accepted, both get the other's Telegram. The new status.
    token: the offer's own (the button or the app's list carries it): an id freed by a deleted offer and taken by
    another never answers that other one. None (an old button): nothing, the person offers again."""
    if not token:
        return None
    with tx(con):
        c = one(con, "SELECT * FROM contacts WHERE id = ? AND to_id = ? AND status = 'pending' AND token = ?", cid, uid, token)
        if not c:
            return None
        con.execute("UPDATE contacts SET status = ?, decided_at = ?, offer_message = NULL WHERE id = ?", ("accepted" if yes else "declined", core.now(), cid))
        if yes:
            notify(con, c["from_id"], "contact_ok", f"co:{cid}:to:{token}")    # to the one who offered: the other's contact
            notify(con, c["to_id"], "contact_ok", f"co:{cid}:from:{token}")
    return "accepted" if yes else "declined"


def contacts(con, v: Viewer) -> list[dict]:
    """My offers both ways: pending ones to answer, and, once accepted, the other's Telegram to write to."""
    out = []
    got = con.execute("SELECT * FROM contacts WHERE (from_id = :me OR to_id = :me) AND status != 'declined' ORDER BY id DESC LIMIT 50", {"me": v.id}).fetchall()
    others = [c["to_id"] if c["from_id"] == v.id else c["from_id"] for c in got]
    asks = [c["ask_id"] for c in got if c["ask_id"]]
    titles = dict(rows(con, f"SELECT id, title FROM asks WHERE id IN ({','.join('?' * len(asks))})", *asks))  # one read each for the list
    cards = _cards(con, others)
    tg = {u["id"]: u for u in rows(con, f"SELECT id, tg_id, tg_username FROM users WHERE id IN ({','.join('?' * len(others))})", *others)}
    for c, other in zip(got, others):
        x = {"id": c["id"], "token": c["token"], "status": c["status"], "incoming": c["to_id"] == v.id, "ask": titles.get(c["ask_id"]), **cards[other]}
        if c["status"] == "accepted":
            x["telegram"] = _link(tg[other])
        out.append(x)
    return out


def telegram_of(con, uid: int) -> str:
    """Where to write to someone: their t.me link, or Telegram's own link by ID when they have no username."""
    return _link(one(con, "SELECT tg_id, tg_username FROM users WHERE id = ?", uid))


def _link(u) -> str:
    return f"https://t.me/{u['tg_username']}" if u["tg_username"] else f"tg://user?id={u['tg_id']}"


def block(con, v: Viewer, uid: object, on: object = True) -> None:
    """Never see each other in the forum again: no offers either way, out of each other's matches and lists."""
    need_student(v)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid == v.id or not isinstance(on, bool):
        raise ApiError("bad_input")
    if on:
        con.execute("INSERT OR IGNORE INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, ?)", (v.id, uid, core.now()))
        pymk.forget(con, v.id, uid)  # never suggested to each other, an unblock later included
        con.execute("UPDATE contacts SET status = 'declined', decided_at = ?, offer_message = NULL WHERE status = 'pending' AND ((from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?))",
                    (core.now(), v.id, uid, uid, v.id))
    else:
        con.execute("DELETE FROM blocks WHERE user_id = ? AND blocked_id = ?", (v.id, uid))


# ---- reports: hidden only by 3 reports from accounts older than two weeks AND the AI or a moderator

def reported_enough(con, aid: int) -> bool:
    """Three open reports from accounts at least two weeks old: worth the AI's look (app.py), else a moderator's."""
    return one(con, """SELECT COUNT(DISTINCT r.reporter_id) FROM reports r JOIN users u ON u.id = r.reporter_id
        WHERE r.target = 'ask' AND r.target_id = ? AND r.status = 'open' AND u.created_at <= ?""", aid, core.now() - REPORTER_AGE)[0] >= HIDE_AT


def _enough_at(con, aid: int) -> int | None:
    """When the open reports from old enough accounts reached three: the moderators' day starts then."""
    at = [r[0] for r in con.execute("""SELECT MIN(r.created_at) FROM reports r JOIN users u ON u.id = r.reporter_id
        WHERE r.target = 'ask' AND r.target_id = ? AND r.status = 'open' AND u.created_at <= ? GROUP BY r.reporter_id ORDER BY 1""",
        (aid, core.now() - REPORTER_AGE))]
    return at[HIDE_AT - 1] if len(at) >= HIDE_AT else None


def hide_ask(con, aid: int, why: str, by: int | None = None, close_reports: bool = True, made: tuple[int, int] | None = None) -> None:
    """Out of the lists, the author told why (the AI agreeing with the reports, or a moderator). A subject's listing
    gets its take-down on record too (logic/subjects.hold). One already over is left as it is (no take-down for a
    term gone). close_reports: False when the caller closes them itself in the same decision (moderation.resolve_report).
    made: (author, created_at) the decision was taken on (a deferred AI verdict): any other row, nothing."""
    guard = " AND user_id = ? AND created_at = ?" if made else ""
    with tx(con):  # one write (joins the caller's): a leave in between finds it whole or not at all
        a = one(con, "UPDATE asks SET status = 'hidden', why = ? WHERE id = ? AND status IN ('live', 'held') AND expires_at > ?" + guard
                + " RETURNING user_id, subject, expires_at", why, aid, core.now(), *(made or ()))
        if a:
            if a["subject"]:
                subjects.hold(con, a["user_id"], a["subject"], by, why, a["expires_at"])
            notify(con, a["user_id"], "ask_hidden", f"ah:{aid}")
        if close_reports:
            con.execute("UPDATE reports SET status = 'actioned', resolved_by = ?, resolved_at = ? WHERE target = 'ask' AND target_id = ? AND status = 'open'",
                        (by, core.now(), aid))


def forum_sweep(con) -> None:
    """What the privacy policy promises: a request goes 30 days after it ran out (its skills, offers and pings with
    it), and the record of who was pinged after 30 days (the caps look back a week)."""
    con.execute("DELETE FROM asks WHERE expires_at < ?", (core.now() - KEEP,))
    con.execute("DELETE FROM ask_pings WHERE at < ?", (core.now() - KEEP,))
    subjects.sweep_counters(con)  # the hourly search and listing counters past their hour


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core, pymk, subjects  # noqa: E402
from .account import me  # noqa: E402
from .oversight import _mod  # noqa: E402
from .seats import notify  # noqa: E402
