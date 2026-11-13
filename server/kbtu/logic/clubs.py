"""Clubs and schools: the list, joining, the club's own profile, starting a club, creating and naming orgs."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from .. import media
from ..db import tx

from .core import (ApiError, PERSON_COLS, RANK, Viewer, _by_id, _may, _org, _qs, _rights_from, _roles, can, log_action,
    _once, need_student, one, org_ref, overseer, person_ref, role_in, rows, short_name)


# ---------------------------------------------------------------- orgs

def org_shape(con, v: Viewer, o: sqlite3.Row) -> dict:
    return org_shapes(con, v, [o])[0]


def org_shapes(con, v: Viewer, found: list[sqlite3.Row], share: bool = False) -> list[dict]:
    """Clubs (types.ts Org), each count and each of my marks read once for the whole list (Clubs was 560 queries).
    share: the list everyone opens takes the part that is the same for all from core.shared()."""
    if not found:
        return []
    ids = [o["id"] for o in found]
    q = _qs(ids)
    part = core.shared("org", found, lambda f: _org_parts(con, f)) if share else _org_parts(con, found)
    mine = {r["org_id"]: r for r in rows(con, f"""SELECT m.org_id, m.role, {core.TITLES}, t.rights FROM org_members m
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND m.org_id IN ({q})""", v.id, *ids)} if v.student else {}
    subscribed = {r[0] for r in rows(con, f"SELECT org_id FROM subscriptions WHERE user_id = ? AND org_id IN ({q})", v.id, *ids)} if v.student else set()
    asked = {r["org_id"]: r for r in rows(con, f"SELECT org_id, status, decided_at FROM join_requests WHERE user_id = ? AND org_id IN ({q}) ORDER BY id",
                                          v.id, *ids)} if v.student else {}  # the last one wins
    live = [i for i in ids if part[i]["round"]]
    applied = {r[0] for r in rows(con, f"""SELECT r.org_id FROM round_apps a JOIN rounds r ON r.id = a.round_id WHERE a.user_id = ? AND r.org_id IN ({_qs(live)})
        AND r.status != 'done' AND a.stage != 'withdrawn'""", v.id, *live)} if v.student and live else set()
    # my friends in each club: friends already see each other's clubs (profiles.person); a club hiding its members, or a
    # friend who hides where they go, shows nobody. One query for the whole list; two faces and the total are all a card needs
    pals: dict[int, list] = {}
    if v.student:
        for p in rows(con, f"""SELECT {PERSON_COLS}, m.org_id AS in_org FROM org_members m JOIN orgs o ON o.id = m.org_id JOIN users u ON u.id = m.user_id
                LEFT JOIN students s ON s.user_id = u.id WHERE m.org_id IN ({q}) AND o.members_hidden = 0 AND u.show_going = 1 AND u.banned_at IS NULL
                AND m.user_id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?) ORDER BY m.joined_at, u.id""", *ids, v.id, v.id):
            pals.setdefault(p["in_org"], []).append(person_ref(p))
    return [{
        **part[o["id"]], "friends": pals.get(o["id"], [])[:2], "friendsN": len(pals.get(o["id"], [])), "round": {**r, "applied": o["id"] in applied} if (r := part[o["id"]]["round"]) else None,
        "myRequest": _request_state(asked.get(o["id"])), "subscribed": o["id"] in subscribed,
        "myRole": mine[o["id"]]["role"] if o["id"] in mine else None,
        **({"myTitle": mine[o["id"]]["title"], "myTitleKk": mine[o["id"]]["title_kk"], "myTitleEn": mine[o["id"]]["title_en"]} if o["id"] in mine else {"myTitle": None}),
        "myRights": _ordered(core.club_rights(mine[o["id"]]["role"], mine[o["id"]]["rights"], o)) if o["id"] in mine else [],
    } for o in found]


def _org_parts(con, found: list[sqlite3.Row]) -> dict[int, dict]:
    """The part of each club's shape that is the same for every viewer."""
    ids = [o["id"] for o in found]
    q = _qs(ids)
    count = lambda table, where="": dict(rows(con, f"SELECT org_id, COUNT(*) FROM {table} WHERE org_id IN ({q}) {where} GROUP BY org_id", *ids))  # noqa: E731
    subs, members = count("subscriptions"), count("org_members")
    upcoming = dict(rows(con, f"""SELECT org_id, COUNT(*) FROM events WHERE org_id IN ({q}) AND status = 'published' AND hidden_at IS NULL
        AND starts_at > ? GROUP BY org_id""", *ids, core.now()))
    for o, n in rows(con, f"""SELECT c.org_id, COUNT(*) FROM event_cohosts c JOIN events e ON e.id = c.event_id JOIN orgs o ON o.id = c.org_id AND o.status = 'active' WHERE c.org_id IN ({q})
            AND c.status = 'accepted' AND e.status = 'published' AND e.hidden_at IS NULL AND e.starts_at > ? GROUP BY c.org_id""", *ids, core.now()):
        upcoming[o] = upcoming.get(o, 0) + n  # and the ones it co-hosts (cohosts.py)
    # its latest public event that ended in the last 30 days: the Clubs list's line when nothing is coming. One query for
    # all (SQLite's bare columns follow MAX); the same for every viewer, so public ones only
    last = {r["org_id"]: r for r in rows(con, f"""SELECT org_id, id, title, i18n, MAX(starts_at) AS starts_at FROM events
        WHERE org_id IN ({q}) AND status = 'published' AND hidden_at IS NULL AND visibility = 'public' AND starts_at > ?
        AND COALESCE(ends_at, starts_at + ?) <= ? GROUP BY org_id""", *ids, core.now() - 30 * 86400, core.NO_END, core.now())}
    files = _by_id(con, "files", (o["logo_file_id"] for o in found))
    # a recruitment round taking applications (casting.py); whether I applied to it is mine (org_shapes)
    live = {r["org_id"]: r for r in rows(con, f"SELECT id, org_id, closes_at FROM rounds WHERE org_id IN ({q}) AND status = 'open' AND closes_at > ?", *ids, core.now())}
    # quick: nothing to answer or pick, so one tap sends it (the app skips the sheet)
    quick = {r[0] for r in rows(con, f"""SELECT r.id FROM rounds r WHERE r.id IN ({_qs([x["id"] for x in live.values()])})
        AND NOT EXISTS (SELECT 1 FROM round_questions WHERE round_id = r.id) AND (SELECT COUNT(*) FROM round_departments WHERE round_id = r.id) <= 1""",
        *[x["id"] for x in live.values()])} if live else set()
    # the last CLUB_QUIET: what makes a club quiet (no event, post or round) and what Popular's rank counts.
    # Sent to every viewer, so public ones only: the numbers must not give away a team's closed meetings or posts
    cut = core.now() - CLUB_QUIET
    events = dict(rows(con, f"""SELECT org_id, COUNT(*) FROM events WHERE org_id IN ({q}) AND status = 'published' AND hidden_at IS NULL
        AND visibility = 'public' AND MAX(created_at, COALESCE(starts_at, 0)) > ? GROUP BY org_id""", *ids, cut))
    posts = dict(rows(con, f"""SELECT org_id, COUNT(*) FROM posts WHERE org_id IN ({q}) AND hidden_at IS NULL AND audience = 'public'
        AND created_at > ? GROUP BY org_id""", *ids, cut))
    rounds = {r[0] for r in rows(con, f"SELECT DISTINCT org_id FROM rounds WHERE org_id IN ({q}) AND closes_at > ?", *ids, cut)}  # open now or closed inside it
    return {o["id"]: {
        **org_ref(con, o, files), "description": o["description"], "links": shown_links(o["links"]),
        **({"i18n": json.loads(o["i18n"])} if o["i18n"] else {}),
        "round": {"id": (rid := live[o["id"]]["id"]), "closesAt": live[o["id"]]["closes_at"], "quick": rid in quick} if o["id"] in live else None,
        "subscribers": subs.get(o["id"], 0), "members": members.get(o["id"], 0), "upcoming": upcoming.get(o["id"], 0),
        "last": {"id": e["id"], "title": e["title"], "startsAt": e["starts_at"], **({"i18n": json.loads(e["i18n"])} if e["i18n"] else {})}
        if (e := last.get(o["id"])) else None,
        "recruiting": bool(o["recruiting"]), "membersHidden": bool(o["members_hidden"]), "joinQuestions": _join_qs(o),
        "canBroadcast": bool(o["can_broadcast"]), "canOversee": bool(o["can_oversee"]),
        "top": bool(o["top_at"]) and not o["official"],  # the Ascent's top: its own block in the clubs list
        "category": o["category"],
        "quiet": o["kind"] == "club" and not o["official"] and o["created_at"] <= cut
        and not (events.get(o["id"]) or posts.get(o["id"]) or o["id"] in rounds),
        "rank": members.get(o["id"], 0) + 5 * events.get(o["id"], 0) + 2 * posts.get(o["id"], 0),  # Popular's order
    } for o in found}


def hidden_day(con) -> None:
    """11:00 (Almaty) daily: the president of a club under CLUB_MIN hears once that the registry doesn't show it
    (notify's unique key is the once). Two days' grace: a new club is still gathering its people."""
    local = core.now() + 5 * 3600
    if local % 86400 < 11 * 3600 or not core._once(con, "club_hidden_day", str(local // 86400)):
        return
    for uid, oid in rows(con, """SELECT m.user_id, o.id FROM orgs o JOIN org_members m ON m.org_id = o.id AND m.role = 'president'
            WHERE o.kind = 'club' AND o.status = 'active' AND o.created_at < ?
            AND (SELECT COUNT(*) FROM org_members x WHERE x.org_id = o.id) < ?""", core.now() - 2 * 86400, CLUB_MIN):
        notify(con, uid, "club_hidden", f"chid:{oid}")


def _join_qs(o: sqlite3.Row) -> list[dict]:
    """The always-open applications' questions (types.ts RoundQuestion; the id is the position)."""
    return [{"id": i, "kind": k, "text": t, "options": opts or None, "required": req, "tagId": None}
            for i, (k, t, opts, req, _) in enumerate(json.loads(o["join_questions"] or "[]"))]


CLUB_MIN = 5  # owner, Nov 8: a club of fewer isn't in the registry (official ones too)
CLUB_QUIET = 30 * 86400  # no event, post or round this long: "quiet" (_org_parts), folded at the end of Initiatives; new clubs get this long too
CATEGORIES = ("it", "art", "sport", "business", "science", "volunteer")  # types.ts OrgCategory; the Clubs tab's tiles


def listed(con, v: Viewer, small: bool = False) -> list[sqlite3.Row]:
    """The clubs the registry shows me (orgs(), search.clubs). A club under CLUB_MIN people isn't a club yet (owner,
    Nov 7-8): off the registry for everyone but its own (the admin too: one interface); its page (org) and its events
    stay reachable, and search finds it (owner, Nov 9: small=True, every club not hidden). One subquery for all, never per card."""
    return rows(con, """SELECT * FROM orgs o WHERE status = 'active' AND kind NOT IN ('office','app')
        AND (kind != 'club' OR EXISTS (SELECT 1 FROM org_members m WHERE m.org_id = o.id AND m.user_id = ?)
             OR (SELECT COUNT(*) FROM org_members m WHERE m.org_id = o.id) >= ?)""", v.id, 0 if small else CLUB_MIN)


def orgs(con, v: Viewer) -> list[dict]:
    # the registry's own, and those under its size bar marked `small`: the app keeps them for search alone
    shown = {o["id"] for o in listed(con, v)}
    found = [{**o, "small": o["id"] not in shown} for o in org_shapes(con, v, listed(con, v, small=True), share=True)]
    return sorted(found, key=lambda o: (not o.get("gov"), not o["subscribed"], -o["subscribers"]))


def org(con, v: Viewer, oid: int) -> dict:
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND (status = 'active' OR status = 'hidden' AND ?)", oid, v.role == "admin")
    if not o:
        raise ApiError("not_found")
    from ..casting import group_link  # imports logic: here, not at the top
    return {**org_shape(con, v, o), "leaders": _people(con, oid, "AND m.role IN ('president', 'vice')"), "chats": org_chats(con, oid),
            "contact": _contact(con, oid) if v.student else None, "groupLink": group_link(con, v, oid)}


def _contact(con, oid: int) -> str | None:
    """Whom "Message the club" writes to: the President's @username, else a Vice's (public roles, owner Nov 6; never a
    Head's). None for a club that hides its members. Only to signed-in students (the people list never shows usernames)."""
    r = one(con, """SELECT u.tg_username FROM orgs o JOIN org_members m ON m.org_id = o.id JOIN users u ON u.id = m.user_id
        WHERE o.id = ? AND o.members_hidden = 0 AND m.role IN ('president', 'vice') AND u.tg_username IS NOT NULL
        AND u.tg_username != '' AND u.banned_at IS NULL
        ORDER BY m.role = 'vice', m.joined_at, m.user_id LIMIT 1""", oid)
    return r[0] if r else None


def _people(con, oid: int, where: str = "") -> list[dict]:
    found = rows(con, f"""SELECT {PERSON_COLS}, m.role, {core.TITLES} FROM org_members m JOIN users u ON u.id = m.user_id
        JOIN students s ON s.user_id = u.id LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ? {where}""", oid)
    return sorted(({"person": person_ref(p), "role": p["role"], **core.titled(p)} for p in found),
                  key=lambda m: (-RANK[m["role"]], m["person"]["name"]))


def people(con, v: Viewer, oid: int) -> list[dict]:
    """Everyone in a club or school, for anyone (President and Vice first, a button for the rest), unless
    the club hides the list: then its own people and the app's staff only. Names and roles, never @usernames (team())."""
    o = one(con, "SELECT members_hidden FROM orgs WHERE id = ? AND status = 'active'", oid)
    if not o:
        raise ApiError("not_found")
    if o["members_hidden"] and not role_in(con, v, oid) and v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    return _people(con, oid)


def subscribe(con, v: Viewer, oid: int, on: bool) -> dict:
    need_student(v)
    if on:
        con.execute("INSERT OR IGNORE INTO subscriptions (user_id, org_id, created_at) VALUES (?, ?, ?)", (v.id, oid, core.now()))
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
    return r["status"] if r and (r["status"] == "pending" or r["status"] == "rejected" and r["decided_at"] > core.now() - REAPPLY) else None


def apply(con, v: Viewer, oid: int, body: dict | None = None) -> dict:
    """Ask to join, answering the club's own questions if it has any; the club's Vice+ hear from the bot. Asking again
    while it's pending changes nothing."""
    from ..casting import check_answers  # imports logic: here, not at the top
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
            qs = _join_qs(o)
            try:
                given = {str(k): x for k, x in dict((body or {}).get("answers") or {}).items()}
            except (TypeError, ValueError):
                raise ApiError("bad_input")
            # ponytail: answers match the questions by position; the club editing them while one is typed may mismatch
            # one answer (the text kept with it says which question it answered)
            got = check_answers([{**q, "tag": None} for q in qs], given, [])
            answers = [{"q": q["text"], "a": got[str(q["id"])]} for q in qs if str(q["id"]) in got]
            con.execute("INSERT INTO join_requests (org_id, user_id, created_at, answers) VALUES (?, ?, ?, ?)",
                        (oid, v.id, core.now(), json.dumps(answers, ensure_ascii=False) if answers else None))
            for m in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('vice','president')", oid):
                notify(con, m["user_id"], "join_request", f"jr:{oid}:{v.id}:{core.now() // 86400}")  # withdraw and ask again: one ping a day
    return org(con, v, oid)


def withdraw(con, v: Viewer, oid: int) -> dict:
    need_student(v)
    con.execute("UPDATE join_requests SET status = 'withdrawn', decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'", (core.now(), oid, v.id))
    return org(con, v, oid)


def join_requests(con, v: Viewer, oid: int) -> list[dict]:
    """Pending applications, oldest first, with what the club needs to write to the person first (§3: Vice+ see contacts)."""
    _may(con, v, oid, "team")
    found = rows(con, f"""SELECT j.id AS rid, j.created_at AS at, j.answers, {PERSON_COLS}, s.course, s.school, u.tg_username
        FROM join_requests j JOIN users u ON u.id = j.user_id JOIN students s ON s.user_id = u.id
        WHERE j.org_id = ? AND j.status = 'pending' ORDER BY j.id""", oid)
    return [{"id": p["rid"], "person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "course": p["course"],
             "school": p["school"], "username": p["tg_username"], "createdAt": p["at"], "answers": json.loads(p["answers"] or "[]")} for p in found]


def decide_join(con, v: Viewer, rid: int, accept: bool) -> None:
    r = one(con, "SELECT * FROM join_requests WHERE id = ?", rid)
    if not r:
        raise ApiError("not_found")
    _may(con, v, r["org_id"], "team")
    with tx(con):
        if not con.execute("UPDATE join_requests SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                           ("accepted" if accept else "rejected", v.id, core.now(), rid)).rowcount:
            raise ApiError("conflict")  # withdrawn, or another Vice answered first
        if accept:
            con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (r["org_id"], r["user_id"], core.now()))
            joined(con, r["org_id"], r["user_id"])
        notify(con, r["user_id"], "join_decided", f"jr:{rid}:{'yes' if accept else 'no'}")


def update_org(con, v: Viewer, oid: int, body: dict) -> dict:
    """The club's own profile and settings (Vice+, §2): whether it takes applications, and what students see on its
    sheet — the name and its short one, its logo (an upload of the editor's; null: the emoji on its cover again), emoji
    and cover, about, up to 6 links. Only what is sent changes, all or nothing. DMP may set any club's short name and its name (an official club's name is DMP's alone)."""
    # DMP: any club's abbr, and an official club's name (the club's own Vice+ renames a student initiative)
    if not (body and body.keys() <= {"abbr", "name"} and ("name" not in body or _org(con, oid)["official"]) and overseer(con, v)):
        _may(con, v, oid, "profile")
    bad, sets = object(), {}
    text = lambda k: str(body.get(k) or "").strip()  # noqa: E731
    if "recruiting" in body:
        sets["recruiting"] = body["recruiting"] if isinstance(body["recruiting"], bool) else bad
    if "joinQuestions" in body:  # the always-open applications' own questions, as a round's (casting.py)
        from ..casting import clean_questions
        sets["join_questions"] = json.dumps(clean_questions(body["joinQuestions"], []), ensure_ascii=False) if isinstance(body["joinQuestions"], list) else bad
    if "category" in body:
        sets["category"] = body["category"] if body["category"] is None or body["category"] in CATEGORIES else bad
    if "membersHidden" in body:
        sets["members_hidden"] = body["membersHidden"] if isinstance(body["membersHidden"], bool) else bad
    if "name" in body:  # no "KBTU" in it; an acronym it carried becomes the abbr, unless one is sent too; "Club" stays
        named, acro = org_name(text("name"), club=False)  # the club's own choice (a President's "Cheerleading Club" came back cut)
        sets["name"] = named if 2 <= len(text("name")) <= 60 else bad
        if acro and "abbr" not in body:
            sets["abbr"] = acro
    if "slug" in body:  # the short link is the President's
        if _roles(con, v).get(oid) != "president":
            raise ApiError("forbidden")
        s = text("slug").lower()
        sets["slug"] = s if SLUG.fullmatch(s) and s not in RESERVED else bad
        if sets["slug"] is not bad and not _slug_free(con, s, oid):
            raise ApiError("conflict", "taken")
    if "short" in body:
        sets["short"] = text("short").upper() if 1 <= len(text("short")) <= 2 else bad
    if "abbr" in body:  # one word, 2-8 letters or digits (no "_", dots or signs: "JCC_KBTU" got in): it sits inline beside a role or a place
        sets["abbr"] = text("abbr") if re.fullmatch(r"[^\W_]{2,8}", text("abbr")) else bad
    if "emoji" in body:
        sets["emoji"] = text("emoji") if re.fullmatch(r"[a-z0-9_]{1,40}", text("emoji")) else bad
    if "cover" in body:
        c = body["cover"]
        sets["cover"] = c if isinstance(c, int) and not isinstance(c, bool) and 0 <= c < COVERS else bad
    if "description" in body:
        sets["description"] = text("description") if len(text("description")) <= 600 else bad
    if "links" in body:
        sets["links"] = json.dumps(body["links"]) if _links_ok(body["links"]) else bad
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
        with tx(con):  # the name checked and taken at once
            if sets.get("name", before["name"]) != before["name"]:
                if before["official"] and not overseer(con, v):  # the ✓ was given to this name: DMP renames an official club
                    raise ApiError("forbidden", "name")
                _rename_ok(con, oid, sets["name"])
            for k in ("abbr", "short"):
                if sets.get(k, before[k]) != before[k]:
                    _looks_ok(sets[k])
            if sets.get("slug", before["slug"]) != before["slug"]:  # the old short link stays this club's
                if not _slug_free(con, sets["slug"], oid):
                    raise ApiError("conflict", "taken")
                con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"slug:{before['slug']}", str(oid)))
            con.execute(f"UPDATE orgs SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), oid))  # keys from the list above
        if "description" in sets and sets["description"] != before["description"]:
            con.execute("UPDATE orgs SET lang = NULL, ai_tries = 0 WHERE id = ?", (oid,))  # translated again (ai.py)
        if before["i18n"] and (gone := {k for k in ("name", "description") if k in sets and sets[k] != before[k]}):
            # a field edited by hand (in Russian, or whatever was typed) is shown as typed in every language
            tr = {lang: g for lang, f in json.loads(before["i18n"]).items() if (g := {k: x for k, x in f.items() if k not in gone})}
            con.execute("UPDATE orgs SET i18n = ? WHERE id = ?", (json.dumps(tr, ensure_ascii=False), oid))
    if sets.keys() - {"recruiting"}:
        log_action(con, v.id, "org_edit", f"org:{oid}", json.dumps(sorted(sets.keys() - {"recruiting"})))
    core._SHARED.clear()  # event cards carry the club's name and logo: seen at once here (other workers: SHARED_TTL)
    return org(con, v, oid)


def delete_org(con, v: Viewer, oid: int) -> None:
    """A President's own club made by mistake goes (club presidents, Nov 6: one was stuck as the President of one): only
    a student club nobody else is in, that never published an event and isn't official; otherwise conflict says why
    (members / events / official). As the admin's hide (oversight.admin_hide_org): hidden, never removed, so the admin
    can bring it back; audit-logged. The President leaves it (role history by its trigger)."""
    with tx(con):
        o = one(con, "SELECT * FROM orgs WHERE id = ? AND status = 'active'", oid)
        if not o:
            raise ApiError("not_found")
        if role_in(con, v, oid) != "president":
            raise ApiError("forbidden")
        if o["official"] or o["kind"] != "club":
            raise ApiError("conflict", "official")
        if one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id != ?", oid, v.id):
            raise ApiError("conflict", "members")
        if one(con, "SELECT 1 FROM events WHERE org_id = ? AND status != 'draft'", oid):
            raise ApiError("conflict", "events")
        con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (oid,))
        con.execute("DELETE FROM org_members WHERE org_id = ?", (oid,))
        log_action(con, v.id, "org_delete", f"org:{oid}", json.dumps({"name": o["name"]}, ensure_ascii=False))
    core._SHARED.clear()


# ---------------------------------------------------------------- starting a club (§4.6)

CLUB_REAPPLY = 30 * 86400   # after a decline, a new application in 30 days
COVERS = 6                  # the cover palette (OrgLogo.svelte's COVERS)
LINK = re.compile(r"https://[A-Za-z0-9.-]+\.[a-z]{2,}(/[^\s]*)?")
# Telegram is not a social (owner, Nov 6): its chats are linked in the club's Chats, and "Message the club" goes to the President
TG_LINK = re.compile(r"https://(?:www\.)?(?:t|telegram)\.(?:me|dog)(?:/|$)", re.I)


def shown_links(raw: str) -> list[str]:
    """The club's stored links as shown: t.me ones saved before Nov 6 stay stored, unseen (an edit drops them)."""
    return [x for x in json.loads(raw) if not TG_LINK.match(x)]


def _links_ok(ls: object) -> bool:
    """A club's social links: up to 6 https addresses (the app draws Instagram, Telegram, TikTok... from the host)."""
    return isinstance(ls, list) and len(ls) <= 6 and len(set(map(str, ls))) == len(ls) \
        and all(isinstance(x, str) and len(x) <= 200 and LINK.fullmatch(x) and not TG_LINK.match(x) for x in ls)  # the app keys them: no twins


def _club_app(con, a: sqlite3.Row, staff: bool) -> dict:
    out = {"id": a["id"], "name": a["name"], "short": a["short"], "description": a["description"], "emoji": a["emoji"], "cover": a["cover"],
           "links": json.loads(a["links"]), "why": a["why"], "status": a["status"], "reason": a["reason"], "orgId": a["org_id"], "createdAt": a["created_at"],
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
    about, why = str(body.get("description") or "").strip(), str(body.get("why") or "").strip() or None
    # up to 6 social links, the club's own rule (A4); the form before the refactor sends one "link"
    links = body["links"] if "links" in body else [x] if (x := str(body.get("link") or "").strip()) else []
    emoji, cover = str(body.get("emoji") or ""), body.get("cover")
    if not (2 <= len(name) <= 60 and 1 <= len(short) <= 2 and 10 <= len(about) <= 600 and (why is None or len(why) <= 500)
            and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and isinstance(cover, int) and not isinstance(cover, bool) and 0 <= cover < COVERS
            and _links_ok(links)):
        raise ApiError("bad_input")
    with tx(con):  # a double tap must not make two pending applications
        last = one(con, "SELECT * FROM club_applications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", v.id)
        if last and last["status"] == "pending":
            raise ApiError("conflict", "pending")
        if last and last["status"] == "rejected" and last["decided_at"] + CLUB_REAPPLY > core.now():
            raise ApiError("rate_limited")
        _new_club_ok(con, name, short)
        aid = con.execute("""INSERT INTO club_applications (user_id, name, short, description, emoji, cover, links, why, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (v.id, name, short, about, emoji, cover, json.dumps(links), why, core.now())).lastrowid
        notify_staff(con, [r[0] for r in rows(con, "SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL")], "club_application", f"capp:{aid}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), False)


def club_applications(con, v: Viewer) -> list[dict]:
    """The check (the admin; clubs are his): pending first, then the last decisions."""
    _admin(v)
    return [_club_app(con, a, True) for a in rows(con, """SELECT * FROM club_applications ORDER BY status = 'pending' DESC,
        COALESCE(decided_at, created_at) DESC LIMIT 40""")]


def decide_club_application(con, v: Viewer, aid: int, approve: bool, reason: object) -> dict:
    """Yes: the club exists at once as a student initiative and the applicant is its President. No: with a reason the
    applicant reads in the app (the bot's message is our template only, §9)."""
    _admin(v)
    why = str(reason or "").strip()
    if not approve and not 3 <= len(why) <= 300:
        raise ApiError("bad_input")
    with tx(con):  # all or nothing: never a club without its President, never two clubs from one application
        a = one(con, "SELECT * FROM club_applications WHERE id = ? AND status = 'pending'", aid)
        if not a:
            raise core.decided(con, f"capp:{aid}") if one(con, "SELECT 1 FROM club_applications WHERE id = ?", aid) else ApiError("not_found")
        oid = None
        if approve:
            _new_club_ok(con, a["name"], a["short"])  # the same check as when applying: a club named since may have taken it
            oid = create_org(con, v.id, a["name"], a["short"], a["emoji"], False)
            con.execute("UPDATE orgs SET cover = ?, description = ?, links = ? WHERE id = ?", (a["cover"], a["description"], a["links"], oid))
            oversight.set_role(con, v.id, a["user_id"], oid, "president", "club_application")
        con.execute("UPDATE club_applications SET status = ?, reason = ?, org_id = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                    ("approved" if approve else "rejected", None if approve else why, oid, v.id, core.now(), aid))
        # a refusal's message waits the Undo's minute
        notify(con, a["user_id"], "club_application_decided", f"cad:{aid}:{'yes' if approve else 'no'}", after=None if approve else core.now() + UNDO_WAIT)
        log_action(con, v.id, "capp_yes" if approve else "capp_no", f"capp:{aid}", json.dumps({"title": a["name"]}))
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), True)


UNDO_WAIT = 60  # a staff decision's bot message waits this long: an Undo inside it leaves no trace


def undo_club_refusal(con, v: Viewer, aid: int) -> None:
    """A refusal taken back (Admin → Done): pending again, its message unsent if still waiting. Not once the student
    has applied anew."""
    _admin(v)
    with tx(con):
        a = one(con, "SELECT * FROM club_applications WHERE id = ? AND status = 'rejected'", aid)
        if not a:
            raise ApiError("not_found")
        if one(con, "SELECT 1 FROM club_applications WHERE user_id = ? AND id > ?", a["user_id"], aid):
            raise ApiError("conflict", "newer")
        con.execute("UPDATE club_applications SET status = 'pending', reason = NULL, decided_by = NULL, decided_at = NULL WHERE id = ?", (aid,))
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'club_application_decided' AND ref = ? AND sent_at IS NULL", (a["user_id"], f"cad:{aid}:no"))
        log_action(con, v.id, "capp_undo", f"capp:{aid}")


# ---------------------------------------------------------------- the Ascent (owner, Nov 6; was the path to the ✓)
# A student initiative's checklist, any order, each read live when Studio opens (one query, every fact once). It never
# locks a tool (owner, Nov 6): a checklist and a reward. A collab with an official club puts that event in the afisha
# (its co-host's right); the top (every step, and two events with outside guests: _path_guests) gives the full tools of an official club but
# no ✓ (orgs.top_at, kept once reached; the owner makes its lanyard by hand). The ✓ is DMP's own decision: a club at the
# top may ask (ask_official), the path never asks for it.

PATH_STEPS = ("profile", "round", "channel", "collab", "top")
PATH_MEMBERS = 5   # members in the app for a ready profile
PATH_GUESTS = 5    # outside guests scanned at the door for an own event to count (owner, Nov 10)
PATH_EVENTS = 2    # such events for the top
PATH_REACH = 10    # different outside guests across those two


def _path_facts(con, oid: int) -> sqlite3.Row:
    return con.execute("""SELECT
        (SELECT COUNT(*) FROM org_members m JOIN students s ON s.user_id = m.user_id JOIN users u ON u.id = m.user_id
          WHERE m.org_id = :o AND u.banned_at IS NULL) AS members,
        (SELECT logo_file_id IS NOT NULL AND length(trim(description)) >= 10 FROM orgs WHERE id = :o) AS look,
        EXISTS (SELECT 1 FROM rounds r JOIN round_apps a ON a.round_id = r.id WHERE r.org_id = :o AND r.status = 'done' AND a.stage = 'yes') AS round,
        EXISTS (SELECT 1 FROM chats WHERE org_id = :o AND kind = 'channel') AS channel,
        -- an accepted co-host row with an official club, whichever of the two hosted
        EXISTS (SELECT 1 FROM event_cohosts c JOIN events e ON e.id = c.event_id
          JOIN orgs x ON x.id = CASE WHEN e.org_id = :o THEN c.org_id ELSE e.org_id END
          WHERE c.status = 'accepted' AND :o IN (e.org_id, c.org_id) AND x.official = 1 AND e.status = 'published' AND e.hidden_at IS NULL) AS collab,
        (SELECT top_at FROM orgs WHERE id = :o) AS top_at""",
        {"o": oid}).fetchone()


def _path_guests(con, oid: int) -> tuple[int, int]:
    """(own events over with PATH_GUESTS outside guests, the most different guests any two of them drew). A guest: scanned
    at the door (not ticked by hand), not the event's creator or helper (Studio's or the QR screen's), never in the club or its co-host before it began
    (current and former members alike: org_history keeps who left; joining after counts). One query for all events.
    ponytail: no anti-cheat review (owner, Nov 10: proven cheating cancels the top); add a staff undo of top_at when needed.
    Helpers (event_crew, qr_helpers) and co-hosts are read as they are now: one removed after the event counts as a guest;
    keep their history if that gets abused."""
    by: dict[int, set[int]] = {}
    for eid, uid in con.execute("""SELECT e.id, g.user_id FROM events e JOIN registrations g ON g.event_id = e.id
            WHERE e.org_id = :o AND e.status = 'published' AND e.hidden_at IS NULL AND e.guest_host IS NULL
            AND COALESCE(e.ends_at, e.starts_at + 3 * 3600) <= :t AND g.checked_in_at IS NOT NULL AND g.checkin_manual = 0
            AND g.user_id IS NOT e.created_by
            AND NOT EXISTS (SELECT 1 FROM event_crew w WHERE w.event_id = e.id AND w.user_id = g.user_id)
            AND NOT EXISTS (SELECT 1 FROM qr_helpers q JOIN qr_sessions x ON x.id = q.session_id WHERE x.event_id = e.id AND q.user_id = g.user_id)
            AND NOT EXISTS (SELECT 1 FROM (SELECT org_id, joined_at AS at FROM org_members WHERE user_id = g.user_id
                UNION ALL SELECT org_id, since FROM org_history WHERE user_id = g.user_id) h
              WHERE h.at < e.starts_at AND (h.org_id IN (e.org_id, e.co_org_id)
                OR h.org_id IN (SELECT org_id FROM event_cohosts WHERE event_id = e.id AND status = 'accepted')))""",
            {"o": oid, "t": core.now()}).fetchall():
        by.setdefault(eid, set()).add(uid)
    ok = [s for s in by.values() if len(s) >= PATH_GUESTS]
    reach = max((len(a | b) for i, a in enumerate(ok) for b in ok[i + 1:]), default=max(map(len, ok), default=0))  # ponytail: pairs, O(n^2) on a club's few events
    return len(ok), reach


def _path_steps(con, oid: int) -> tuple[dict[str, bool], dict]:
    """Each step done or not, any order; the top needs every other one too (and, once reached, stays)."""
    f = dict(_path_facts(con, oid))
    out = {"profile": bool(f["look"]) and f["members"] >= PATH_MEMBERS, "round": bool(f["round"]), "channel": bool(f["channel"]),
           "collab": bool(f["collab"])}
    if f["top_at"] is not None:
        return {k: True for k in (*out, "top")}, {**f, "events": PATH_EVENTS, "guests": PATH_REACH}
    f["events"], f["guests"] = _path_guests(con, oid)
    out["top"] = all(out.values()) and f["events"] >= PATH_EVENTS and f["guests"] >= PATH_REACH
    return out, f


def path_top(con, oid: int) -> bool:
    """A student initiative at the top: an official club's tools, no ✓; its events reach the afisha (seats.afisha_ok)."""
    return bool(one(con, "SELECT top_at IS NOT NULL FROM orgs WHERE id = ?", oid)[0])


def stories_open(con, o: sqlite3.Row) -> bool:
    """A club may post stories (newsfeed.create_post, the channel mirror): official, not a club, or a student initiative
    past the Ascent's collab step (owner, Nov 7: an official club vouched for it, it's on the afisha). Old posts stay."""
    return bool(o["official"] or o["kind"] != "club" or o["top_at"]) or _path_steps(con, o["id"])[0]["collab"]


def _reached_top(con, oid: int) -> None:
    """Once: the top kept, the owner told (the lanyard is made by hand)."""
    with tx(con):
        if con.execute("UPDATE orgs SET top_at = ? WHERE id = ? AND top_at IS NULL", (core.now(), oid)).rowcount:
            log_action(con, None, "path_top", f"org:{oid}")
            for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
                notify(con, uid, "club_top", f"top:{oid}")
    core._SHARED.clear()  # the clubs list's block


def _official_request(r: sqlite3.Row | None) -> dict | None:
    return r and {"id": r["id"], "status": r["status"], "reason": r["reason"], "createdAt": r["created_at"], "decidedAt": r["decided_at"],
                  "againAt": r["decided_at"] + CLUB_REAPPLY if r["status"] == "rejected" else None}


def official_path(con, v: Viewer, oid: int) -> dict | None:
    """The ladder in Studio, for the club's team: each level, the counts toward the next, and the latest request for
    the ✓. None: official, or not a club."""
    if not role_in(con, v, oid):
        raise ApiError("forbidden")
    o = _org(con, oid)
    if o["official"] or o["kind"] != "club":
        return None
    steps, f = _path_steps(con, oid)
    if steps["top"] and not o["top_at"]:
        _reached_top(con, oid)
    last = one(con, "SELECT * FROM official_requests WHERE org_id = ? ORDER BY id DESC LIMIT 1", oid)
    return {"steps": steps, "members": f["members"], "events": f["events"], "guests": f["guests"], "request": _official_request(last)}


def ask_official(con, v: Viewer, oid: int) -> dict | None:
    """At the top, the President or a Vice may ask DMP for the ✓ (not a level). One pending request per club; after a
    no, again in 30 days."""
    if role_in(con, v, oid) not in ("president", "vice"):
        raise ApiError("forbidden")
    o = _org(con, oid)
    if o["official"] or o["kind"] != "club" or o["status"] != "active":
        raise ApiError("bad_input")
    with tx(con):  # a double tap makes one request
        last = one(con, "SELECT * FROM official_requests WHERE org_id = ? ORDER BY id DESC LIMIT 1", oid)
        if last and last["status"] == "pending":
            raise ApiError("conflict", "pending")
        if last and last["status"] == "rejected" and last["decided_at"] + CLUB_REAPPLY > core.now():
            raise ApiError("rate_limited")
        if not o["top_at"]:
            raise ApiError("bad_input", "steps")
        # its President already leads an official organization: one post goes first (owner, Nov 9); DMP's own ✓ stays free
        if one(con, """SELECT 1 FROM org_members me JOIN org_members m ON m.user_id = me.user_id AND m.role = 'president' JOIN orgs b ON b.id = m.org_id
                WHERE me.org_id = ? AND me.role = 'president' AND b.official = 1 AND b.status = 'active' AND b.id != ?""", oid, oid):
            raise ApiError("conflict", "president_elsewhere")
        rid = con.execute("INSERT INTO official_requests (org_id, created_at) VALUES (?, ?)", (oid, core.now())).lastrowid
        log_action(con, v.id, "opath_ask", f"opath:{rid}", json.dumps({"title": o["name"]}))
        notify_staff(con, [r[0] for r in rows(con, "SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL")], "club_path", f"opath:{rid}")
    return official_path(con, v, oid)


def official_requests(con, v: Viewer) -> list[dict]:
    """Admin → Inbox: the requests waiting, oldest first (a club given the ✓ meanwhile by DMP drops out)."""
    _admin(v)
    found = rows(con, """SELECT r.*, (SELECT COUNT(*) FROM org_members m WHERE m.org_id = r.org_id) AS members FROM official_requests r
        JOIN orgs o ON o.id = r.org_id WHERE r.status = 'pending' AND o.official = 0 ORDER BY r.id""")
    orgs = {o["id"]: o for o in rows(con, f"SELECT * FROM orgs WHERE id IN ({_qs(found)})", *(r["org_id"] for r in found))} if found else {}
    logos = _by_id(con, "files", (o["logo_file_id"] for o in orgs.values()))
    return [{**_official_request(r), "org": org_ref(con, orgs[r["org_id"]], logos), "members": r["members"]} for r in found]


def decide_official(con, v: Viewer, rid: int, approve: bool, reason: object) -> dict:
    """Yes: the club is official (its name is DMP's from now on, update_org); its President hears it from the bot after
    the Undo's minute. No: a reason the club reads in Studio, no message (the card says it)."""
    _admin(v)
    why = str(reason or "").strip()
    if not approve and not 3 <= len(why) <= 300:
        raise ApiError("bad_input")
    with tx(con):
        r = one(con, "SELECT r.*, o.name FROM official_requests r JOIN orgs o ON o.id = r.org_id WHERE r.id = ?", rid)
        if not r:
            raise ApiError("not_found")
        if r["status"] != "pending":
            raise core.decided(con, f"opath:{rid}")
        con.execute("UPDATE official_requests SET status = ?, reason = ?, decided_at = ? WHERE id = ?",
                    ("approved" if approve else "rejected", None if approve else why, core.now(), rid))
        if approve:
            con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (r["org_id"],))
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", r["org_id"]):
                notify(con, uid, "club_official", f"off:{r['org_id']}", after=core.now() + UNDO_WAIT)  # said only while still so (bot)
        log_action(con, v.id, "opath_yes" if approve else "opath_no", f"opath:{rid}", json.dumps({"title": r["name"]}))
    core._SHARED.clear()  # event cards carry the club's ✓
    return _official_request(one(con, "SELECT * FROM official_requests WHERE id = ?", rid))


def undo_official(con, v: Viewer, rid: int) -> None:
    """Admin → Done: a yes or a no taken back, the request waits again (a yes takes the ✓ back, its message unsent if
    still waiting). Not once the club has asked anew."""
    _admin(v)
    with tx(con):
        r = one(con, "SELECT * FROM official_requests WHERE id = ? AND status != 'pending'", rid)
        if not r:
            raise ApiError("not_found")
        if one(con, "SELECT 1 FROM official_requests WHERE org_id = ? AND id > ?", r["org_id"], rid):
            raise ApiError("conflict", "newer")
        if r["status"] == "approved":
            con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (r["org_id"],))
            con.execute("DELETE FROM bot_outbox WHERE kind = 'club_official' AND ref = ? AND sent_at IS NULL", (f"off:{r['org_id']}",))
        con.execute("UPDATE official_requests SET status = 'pending', reason = NULL, decided_at = NULL WHERE id = ?", (rid,))
        log_action(con, v.id, "opath_undo", f"opath:{rid}")
    core._SHARED.clear()




def create_org(con, actor: int | None, name: str, short: str, emoji: str, official: bool, slug: str | None = None,
               kind: str = "club") -> int:
    """A club or a school, by the admin (the app or the CLI). A school (KBTU's own, a few, made by the
    admin, never by an application) is official from the start and never closes; its President has a club
    President's rights. A slug nobody chose comes from the name (A5: kbtu.sow.kz/<slug>). Recruiting starts closed:
    the club opens it in Studio."""
    abbr = guess_abbr(name)
    name = org_name(name)[0]  # no "KBTU", the short form to abbr
    slug = slug or slug_for(con, name)
    cur = con.execute("INSERT INTO orgs (slug, kind, name, short, abbr, emoji, official, created_by, created_at, recruiting) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                      (slug, kind, name, short, abbr, emoji, int(official or kind == "school"), actor, core.now()))
    for rn, color, lv in OFFICIAL_ROLES:
        con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (?, ?, ?, ?, 1, ?)", (cur.lastrowid, rn, color, lv, core.now()))
    log_action(con, actor, "org_create", f"org:{cur.lastrowid}", json.dumps({"name": name}))
    return cur.lastrowid


# A5 short links kbtu.sow.kz/<slug>: the name in Latin letters, the app's own paths never
# Cyrillic a..ya (U+0430..U+044F) in order, then yo and the Kazakh letters (code points: the code stays ASCII)
TRANSLIT = str.maketrans({**dict(zip(range(0x430, 0x450), "a b v g d e zh z i i k l m n o p r s t u f h c ch sh sch _ y _ e yu ya".split())),
    0x451: "e", 0x4D9: "a", 0x493: "g", 0x49B: "k", 0x4A3: "n", 0x4E9: "o", 0x4B1: "u", 0x4AF: "u", 0x4BB: "h", 0x456: "i", 0x44A: "", 0x44C: ""})
SLUG = re.compile(r"[a-z0-9]{2,24}")
RESERVED = {"api", "cal", "healthz", "exit", "privacy", "terms", "og", "media", "demo", "old", "assets", "emoji", "map", "admin",
            "app", "kbtu", "help", "login", "ms", "static", "www", "bot", "support", "settings", "outlook", "club", "clubs", "events",
            # and for the clubs' own links: what a phishing page would like to be
            "favicon", "apple-touch-icon", "robots", "sitemap", "auth", "oauth", "logout", "signin", "signup", "register", "account",
            "me", "profile", "dmp", "pay", "kaspi", "telegram", "tg", "security", "official", "news", "about", "wp-admin"}
# a club's own short link: a club slug, or words joined by single hyphens, 2-32 characters
SHORT = re.compile(r"(?=.{2,32}$)[a-z0-9]+(?:-[a-z0-9]+)*")
LINKS_MAX = 20  # a club's: the names are everyone's, first come, first served


def slug_for(con, name: str, oid: int | None = None) -> str:
    """A free slug from a name: "Open Mic Club" -> openmicclub, then openmicclub2, ..."""
    base = re.sub(r"[^a-z0-9]", "", name.lower().translate(TRANSLIT))[:22]
    base = base if len(base) >= 2 else f"club{base}"
    return next(s for s in (base if n == 1 else f"{base}{n}" for n in range(1, 10_000))
                if _slug_free(con, s, oid))


def name_slugs(con) -> None:
    """At start: the clubs made before A5 got club<N>; they take their names' slugs, once (every start renamed
    a club<N> its President chose)."""
    if one(con, "SELECT 1 FROM meta WHERE key = 'slugs_named'"):
        return
    with tx(con):
        con.execute("INSERT INTO meta (key, value) VALUES ('slugs_named', '1')")
        for o in rows(con, "SELECT id, name FROM orgs WHERE slug GLOB 'club[0-9]*'"):
            con.execute("UPDATE orgs SET slug = ? WHERE id = ?", (slug_for(con, o["name"], o["id"]), o["id"]))


# words a club's initials leave out: "Club of Film and Theatre" is CFT; Russian and Kazakh ones as code
# points (the code stays ASCII)
LINK_WORDS = {*"\u0438 \u0432 \u0432\u043e \u043d\u0430 \u043f\u043e \u0434\u043b\u044f \u0441 \u0441\u043e \u043e \u043e\u0431 \u043e\u0442 \u043f\u0440\u0438 \u0437\u0430 \u0438\u0437 \u043a \u0436\u04d9\u043d\u0435 \u043c\u0435\u043d \u043f\u0435\u043d \u0431\u0435\u043d".split(),
              "and", "of", "the", "for", "in", "on", "at", "a", "an", "to", "by"}


def initials(name: str) -> str:
    """A club's short name until it types its own: the first letters of its words, uppercase; one word stays whole
    (the first three letters of a long one). "KBTU" is no letter of it."""
    words = re.findall(r"[^\W_]+", name)
    words = [w for w in words if w.lower() not in LINK_WORDS and w.upper() not in KBTU] or words
    if len(words) == 1:
        return (words[0] if len(words[0]) <= 8 else words[0][:3]).upper()
    return "".join(w[0] for w in words).upper()[:8]


# Org names, one style: no "KBTU" in a name (the whole app is KBTU's), and no "short + long": the short
# one is the abbr. Done to a name as it's created or renamed; the names already there were fixed by hand.
KBTU = {"KBTU", "\u041a\u0411\u0422\u0423", "\u049a\u0411\u0422\u0423"}  # and in Russian and Kazakh
_KB = r"(?:kbtu|\u043a\u0431\u0442\u0443|\u049b\u0431\u0442\u0443)"
_SEP = r"[\s\-\u2013\u2014|:,.]"
_HEAD = re.compile(rf"^{_KB}(?:['\u2019]s)?\b{_SEP}*", re.I)
# "... in KBTU", "... at KBTU", "... \u0432 / \u043f\u0440\u0438 \u041a\u0411\u0422\u0423": the little word goes too
_TAIL = re.compile(rf"(?:\s+(?:in|at|of|\u0432|\u043f\u0440\u0438))?{_SEP}*\(?\b{_KB}(?:\s+chapter)?\)?$", re.I)
# no "Club" either, the Clubs tab says it (owner, Nov 2): "Chess Club", Kazakh "\u0428\u0430\u0445\u043c\u0430\u0442 \u043a\u043b\u0443\u0431\u044b", Russian
# \u041a\u043b\u0443\u0431 \u00abX\u00bb. A Russian "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u0443\u0431" or "\u041a\u043b\u0443\u0431 \u0434\u0435\u0431\u0430\u0442\u043e\u0432" keeps it: an adjective or a genitive alone isn't a name
_CLUB_TAIL = re.compile(rf"{_SEP}+(?:club|\u043a\u043b\u0443\u0431\u044b)$", re.I)
_CLUB_QUOTED = re.compile(r"^(?:club|\u043a\u043b\u0443\u0431)\s*[\u00ab\"\u201c\u201e'](.+)[\u00bb\"\u201d']$", re.I)


def _acronym(w: str) -> bool:
    """One word of 2-8 capitals (digits too, "3D" no: a letter first), and not KBTU."""
    return 2 <= len(w) <= 8 and bool(re.fullmatch(r"[^\W\d_][^\W_]*", w)) and w.isupper() and w not in KBTU


def org_name(name: str, club: bool = True) -> tuple[str, str | None]:
    """A name as typed -> (the name, the acronym it carried, for the abbr): "KBTU" off either end ("KBTU Open Mic",
    "Debate Club | KBTU", "IEEE KBTU Chapter"), and "Club" (club=False keeps it, for the initials); "Society of
    Petroleum Engineers (SPE)" and "SPE \u2013 Society of ..." give SPE and keep the long name. A name that would be left
    under 2 characters stays as typed."""
    typed = " ".join(name.split())
    def bare(n: str) -> str:
        for _ in range(3):
            n = _TAIL.sub("", _HEAD.sub("", n)).strip()
            if club and len(c := _CLUB_QUOTED.sub(r"\1", _CLUB_TAIL.sub("", n)).strip()) >= 2:
                n = c
        return n
    n, acro = bare(typed), None
    if (m := re.fullmatch(r"(.+?)\s*\(\s*([^\s()]+)\s*\)", n)) and _acronym(m[2]):
        n, acro = bare(m[1]), m[2]
    elif (m := re.fullmatch(r"(\S+)(?:\s*[\u2013\u2014]\s*|\s+[-|:]\s+)(.+)", n)) and _acronym(m[1]):
        acro, n = m[1], bare(m[2])
    return (n, acro) if len(n) >= 2 else (typed, None)


# letters that read as Latin ones (Cyrillic, Greek): with NFKC and case folded, a Cyrillic KBTU, fullwidth or dotted
# KBTU read as KBTU, a "Chess" with a Cyrillic C as "Chess". ponytail: the common look-alikes only; Unicode's confusables.txt if one slips by
_LOOK = str.maketrans(dict(zip("\u0430\u0431\u0432\u0435\u043a\u043c\u043d\u043e\u0440\u0441\u0442\u0443\u0445\u0456\u0458\u049b\u04af\u04b1\u03b1\u03b2\u03b5\u03b9\u03ba\u03bd\u03bf\u03c1\u03c4\u03c5\u03c7",
                                 "abbekmhopctyxijkyyabeikvoptux")))
_TICKS = set("✓✔☑✅\U0001f5f8\U0001f5f9")  # the official badge's look, typed into a name


def _skeleton(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).casefold().translate(_LOOK)
    return "".join(c for c in s if c.isalnum() or c in "+#&")


def _looks_ok(name: str) -> None:
    """No KBTU in look-alike letters (org_name took the plain one off a name's ends), no check mark posing as the
    official one: a club's name, short name and abbr."""
    if re.search("kbt[uy]", _skeleton(name)) or _TICKS & set(name):
        raise ApiError("bad_input", "name")


# what a name may not carry (owner, Nov 3): "Club" as a word ("\u041a\u043b\u0443\u0431 \u0434\u0435\u0431\u0430\u0442\u043e\u0432" can't be cut to a genitive, so it's refused), and
# emoji (the logo is the picture; they break lists and initials)
_CLUB_WORD = re.compile(r"(?<![^\W_])(?:club|\u043a\u043b\u0443\u0431(?:\u044b|\u0430|\u0443)?)(?![^\W_])", re.I)


_PAIR = re.compile("[×✕✖⨯⨉⨰⤫╳]|\\s[x\u0445]\\s", re.I)  # a times sign, or x (Latin, Cyrillic) between words; on the NFKC form


def _emoji(c: str) -> bool:
    return unicodedata.category(c) == "So" or 0x1F000 <= ord(c) <= 0x1FAFF or c in "\u200d\ufe0f\u20e3"


def no_emoji(name: str) -> None:
    """Every org name (create, rename, application, the admin's create)."""
    if any(map(_emoji, name)):
        raise ApiError("bad_input", "emoji")


def _plain(name: str) -> None:
    if _CLUB_WORD.search(name):
        raise ApiError("bad_input", "club_word")
    no_emoji(name)


def strip_emoji_names(con) -> None:
    """Once (Nov 6): names from before the rule lose their emoji ("Chess larpers\U0001f976" -> "Chess larpers"; letters
    like \u00f3 stay), the slug kept, audit-logged, and the club's President told how (the club's look has an emoji)."""
    if one(con, "SELECT 1 FROM meta WHERE key = 'emoji_names'"):  # done: no write lock every bot round
        return
    clean = lambda n: re.sub(r"\s+", " ", "".join(c for c in n if not _emoji(c))).strip()  # noqa: E731
    with tx(con):  # the marker, the reads and the writes at once: a failure leaves it to the next round, a rename can't race
        if not _once(con, "emoji_names", "1"):
            return
        for o in rows(con, "SELECT id, name, i18n FROM orgs"):
            if (new := clean(o["name"])) == o["name"] or len(new) < 2:
                continue  # ponytail: a name that was all emoji stays for the admin to rename by hand
            tr = {lang: {**f, **({"name": clean(f["name"])} if isinstance(f.get("name"), str) else {})}
                  for lang, f in json.loads(o["i18n"]).items()} if o["i18n"] else None
            con.execute("UPDATE orgs SET name = ?, i18n = ? WHERE id = ?",
                        (new, None if tr is None else json.dumps(tr, ensure_ascii=False), o["id"]))
            log_action(con, None, "org_edit", f"org:{o['id']}", json.dumps({"emoji": [o["name"], new]}, ensure_ascii=False))
            for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", o["id"]):
                notify(con, uid, "club_emoji", f"emo:{o['id']}")
    core._SHARED.clear()


def _rename_ok(con, oid: int | None, name: str) -> None:
    """A club's name, at application, approval and rename (the admin's create_org is the admin's): _looks_ok, _plain,
    and not another org's in any letters or case (oid: the club itself, None before it exists). Lanyards go by slug: a
    rename neither gains nor loses one. Names already there stay till they're changed."""
    _looks_ok(name)
    _plain(name)
    if _PAIR.search(unicodedata.normalize("NFKC", name)):  # "JCC × Crystal" would pose as a collab's signature in the channel (collab-review I1)
        raise ApiError("bad_input", "name")
    skel = _skeleton(name)
    if any(_skeleton(r[0]) == skel for r in rows(con, "SELECT name FROM orgs WHERE status != 'archived' AND id IS NOT ?", oid)):
        raise ApiError("conflict", "taken")
    if oid is None or not _org(con, oid)["official"]:  # an initiative can't wear an official club's name or abbr (I2)
        words = [_skeleton(w) for w in re.split(r"[\W_]+", name) if w]
        runs = {"".join(words[i:j]) for i in range(len(words)) for j in range(i + 1, len(words) + 1)}
        for o in rows(con, "SELECT name, abbr FROM orgs WHERE official = 1 AND status = 'active' AND id IS NOT ?", oid):
            if _skeleton(o["name"]) in runs or o["abbr"] and len(_skeleton(o["abbr"])) >= 3 and _skeleton(o["abbr"]) in words:
                raise ApiError("conflict", "taken")


def _new_club_ok(con, name: str, short: str) -> None:
    """An application's name as the club will be named (org_name), its short name and the abbr it would get."""
    _rename_ok(con, None, org_name(name)[0])
    _looks_ok(short)
    _looks_ok(guess_abbr(name))


def guess_abbr(name: str) -> str:
    """The short name an org starts with: the acronym its name carried, else its initials."""
    n, acro = org_name(name, club=False)  # "Debate Club": DC, not DEBATE
    return acro or initials(n)


def fill_abbrs(con) -> None:
    """At start: an org without a short name takes its initials (the clubs made before it existed); a set one stays.
    (The one-time "Club" cut of the old names ran with 20c7f1b's deploys; run at every start it cut a club's own
    "Club" from its rename again, review 3.)"""
    with tx(con):
        for o in rows(con, "SELECT id, name FROM orgs WHERE abbr IS NULL"):
            con.execute("UPDATE orgs SET abbr = ? WHERE id = ?", (guess_abbr(o["name"]), o["id"]))


def org_by_slug(con, slug: str) -> int | None:
    s = slug.lower()
    if not SLUG.fullmatch(s):
        return None
    o = one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", s) \
        or one(con, "SELECT o.id FROM meta m JOIN orgs o ON o.id = CAST(m.value AS INTEGER) WHERE m.key = ? AND o.status = 'active'", f"slug:{s}")
    return o[0] if o else None


def start_by_slug(con, slug: str) -> str | None:
    """What kbtu.sow.kz/<slug> opens, as the bot's startapp: a club by its slug, else a club's own short link."""
    s = slug.lower()
    if oid := org_by_slug(con, s):
        return f"cl_{oid}"
    sl = one(con, "SELECT l.* FROM short_links l JOIN orgs o ON o.id = l.org_id WHERE l.slug = ? AND o.status = 'active'", s)
    if sl:
        return {"club": f"cl_{sl['org_id']}", "event": f"ev_{sl['event_id']}", "round": f"rc_{sl['org_id']}"}[sl["kind"]]
    gone = one(con, "SELECT o.id FROM meta m JOIN orgs o ON o.id = CAST(m.value AS INTEGER) WHERE m.key = ? AND o.status = 'active'", f"slug:{s}")
    return f"cl_{gone[0]}" if gone else None  # a gone link's name leads to its club (_keep_name)


def org_links(con, v: Viewer, oid: int) -> list[dict]:
    _may(con, v, oid, "profile")
    return [{"slug": sl["slug"], "kind": sl["kind"], "eventId": sl["event_id"], "eventTitle": sl["title"], "createdAt": sl["created_at"]}
            for sl in rows(con, "SELECT l.*, e.title FROM short_links l LEFT JOIN events e ON e.id = l.event_id WHERE l.org_id = ? ORDER BY l.created_at DESC, l.slug", oid)]


def add_link(con, v: Viewer, oid: int, body: dict) -> list[dict]:
    """Vice+ (the club's profile right) points kbtu.sow.kz/<slug> at the club, one of its published events, or its round;
    never anywhere outside the app (a phishing page on our domain)."""
    _may(con, v, oid, "profile")
    s, kind, eid = str(body.get("slug") or "").strip().lower(), body.get("kind"), body.get("eventId")
    if not SHORT.fullmatch(s) or kind not in ("club", "event", "round") or (kind == "event") != (eid is not None):
        raise ApiError("bad_input")
    if kind == "event" and not (type(eid) is int and one(con, "SELECT 1 FROM events WHERE id = ? AND org_id = ? AND status = 'published'", eid, oid)):
        raise ApiError("bad_input")
    with tx(con):
        held = one(con, "SELECT value FROM meta WHERE key = ?", f"slug:{s}")
        if held and held[0] == str(oid):  # its own old name (a gone link, an old club slug) comes back to it
            con.execute("DELETE FROM meta WHERE key = ?", (f"slug:{s}",))
        if not _slug_free(con, s, None):
            raise ApiError("conflict", "taken")
        if one(con, "SELECT COUNT(*) FROM short_links WHERE org_id = ?", oid)[0] >= LINKS_MAX:
            raise ApiError("conflict", "limit")
        con.execute("INSERT INTO short_links (slug, org_id, kind, event_id, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)", (s, oid, kind, eid, v.id, core.now()))
        log_action(con, v.id, "link_create", f"org:{oid}", json.dumps({"slug": s, "kind": kind}))
    return org_links(con, v, oid)


def drop_link(con, v: Viewer, slug: str) -> None:
    """Its club's Vice+ takes a link down; the app's admin (DMP) revokes anyone's."""
    sl = one(con, "SELECT * FROM short_links WHERE slug = ?", slug.lower())
    if not sl:
        raise ApiError("not_found")
    own = can(con, v, sl["org_id"], "profile")
    if not own:
        _admin(v)
    with tx(con):
        con.execute("DELETE FROM short_links WHERE slug = ?", (sl["slug"],))
        _keep_name(con, sl["slug"], sl["org_id"])
        log_action(con, v.id, "link_delete" if own else "link_revoke", f"org:{sl['org_id']}", json.dumps({"slug": sl["slug"]}))


def _keep_name(con, s: str, oid: int) -> None:
    """A gone short link's name stays its club's and leads to the club (printed posters of one club
    would open another's), as a changed club slug does."""
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"slug:{s}", str(oid)))


def _slug_free(con, s: str, oid: int | None) -> bool:
    """Not the app's, nobody's now, nobody's before (a changed slug keeps leading to its club: the old bios)."""
    held = one(con, "SELECT value FROM meta WHERE key = ?", f"slug:{s}")
    return s not in RESERVED and not one(con, "SELECT 1 FROM orgs WHERE slug = ? AND id IS NOT ?", s, oid) and (not held or held[0] == str(oid)) \
        and not one(con, "SELECT 1 FROM short_links WHERE slug = ?", s)


OFFICIAL_ROLES = (("Vice", "#7C4DFF", "vice"), ("Head", "#3B6BFF", "head"))  # with the President: db migration 40


def _official(con, oid: int, level: str) -> int | None:
    """The club's fixed role of a level (Vice, Head), which a Vice or Head without a role name holds."""
    r = one(con, "SELECT id FROM org_roles WHERE org_id = ? AND fixed = 1 AND level = ?", oid, level)
    return r[0] if r else None


SCHOOLS_VERSION = "3"  # 2: the short names (SITE, ISE, KMA), owner Oct 14; 3: SEPI's Russian short name fixed (a student, Nov 3)
SCHOOLS = json.loads((Path(__file__).parent.with_name("i18n") / "schools.json").read_text(encoding="utf-8"))


def seed_schools(con, root: Path) -> None:
    """KBTU's schools from its site (kbtu.edu.kz/ru/shkoly, /kz/mektepter, /en/schools): once, at start under the migration lock, with their crests (kbtu/schools/<slug>.png) and
    names in three languages. A school made by hand before is found by its slug or any of its names and filled in."""
    done = one(con, "SELECT value FROM meta WHERE key = 'schools'")
    if done and done[0] == SCHOOLS_VERSION:
        return
    with tx(con):
        for s in SCHOOLS:
            names = {s[lang]["name"].lower() for lang in ("ru", "kk", "en")}
            o = next((o for o in rows(con, "SELECT * FROM orgs WHERE kind = 'school'") if o["slug"] == s["slug"] or o["name"].strip().lower() in names), None)
            if o is None:
                slug = s["slug"] if _slug_free(con, s["slug"], None) else None
                o = _org(con, create_org(con, None, s["ru"]["name"], s["short"], s["emoji"], True, slug, "school"))
            logo = o["logo_file_id"]
            if logo is None:
                saved = media.save((Path(__file__).parent.with_name("schools") / f"{s['slug']}.png").read_bytes(), root)
                logo = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, created_at, color)
                    VALUES (?, 'org_logo', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                          saved["path"], core.now(), saved["color"])).lastrowid
            # a later version brings new translations (the short names) and leaves what the school typed
            tr = {"ru": {"abbr": s["ru"]["abbr"]}, **{k: s[k] for k in ("kk", "en")}}
            own = done and o["description"] != s["ru"]["description"]  # the school's own text: the AI translates it (ai.py), not the site's
            if own:
                tr = {k: {a: b for a, b in x.items() if a != "description"} for k, x in tr.items()}
            con.execute("UPDATE orgs SET i18n = ?, logo_file_id = ?, official = 1, lang = ? WHERE id = ?",
                        (json.dumps(tr, ensure_ascii=False), logo, None if own else "ru", o["id"]))
            if not done:
                con.execute("UPDATE orgs SET name = ?, description = ? WHERE id = ?", (s["ru"]["name"], s["ru"]["description"], o["id"]))
        con.execute("INSERT INTO meta (key, value) VALUES ('schools', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (SCHOOLS_VERSION,))


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core, oversight  # noqa: E402
from .chatlist import org_chats  # noqa: E402
from .oversight import DMP_COLS, _admin, staff  # noqa: E402
from .seats import joined, notify, notify_staff  # noqa: E402
from .teams import _ordered, banned  # noqa: E402
