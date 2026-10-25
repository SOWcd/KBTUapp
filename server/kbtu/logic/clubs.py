"""Clubs and schools as everyone sees them: the list, joining, the club's own profile, starting a club."""
from __future__ import annotations

import json
import re
import sqlite3

from ..db import tx

from .core import (ApiError, PERSON_COLS, RANK, Viewer, log_action, need_student, one, overseer, role_in, rows)


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
        AND starts_at > ? GROUP BY org_id""", *ids, core.now()))
    mine = {r["org_id"]: r for r in rows(con, f"""SELECT m.org_id, m.role, t.name AS title, t.rights FROM org_members m
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND m.org_id IN ({q})""", v.id, *ids)} if v.student else {}
    subscribed = {r[0] for r in rows(con, f"SELECT org_id FROM subscriptions WHERE user_id = ? AND org_id IN ({q})", v.id, *ids)} if v.student else set()
    asked = {r["org_id"]: r for r in rows(con, f"SELECT org_id, status, decided_at FROM join_requests WHERE user_id = ? AND org_id IN ({q}) ORDER BY id",
                                          v.id, *ids)} if v.student else {}  # the last one wins
    files = _by_id(con, "files", (o["logo_file_id"] for o in found))
    # a recruitment round taking applications (casting.py), and whether I applied to it
    live = {r["org_id"]: r for r in rows(con, f"SELECT id, org_id, closes_at FROM rounds WHERE org_id IN ({q}) AND status = 'open' AND closes_at > ?", *ids, core.now())}
    applied = {r[0] for r in rows(con, f"""SELECT r.org_id FROM round_apps a JOIN rounds r ON r.id = a.round_id WHERE a.user_id = ? AND r.org_id IN ({q})
        AND r.status != 'done' AND a.stage != 'withdrawn'""", v.id, *ids)} if v.student and live else set()
    return [{
        **org_ref(con, o, files), "description": o["description"], "links": json.loads(o["links"]),
        **({"i18n": json.loads(o["i18n"])} if o["i18n"] else {}),
        "round": {"id": live[o["id"]]["id"], "closesAt": live[o["id"]]["closes_at"], "applied": o["id"] in applied} if o["id"] in live else None,
        "subscribers": subs.get(o["id"], 0), "members": members.get(o["id"], 0), "upcoming": upcoming.get(o["id"], 0),
        "recruiting": bool(o["recruiting"]), "membersHidden": bool(o["members_hidden"]), "myRequest": _request_state(asked.get(o["id"])),
        "subscribed": o["id"] in subscribed,
        "myRole": mine[o["id"]]["role"] if o["id"] in mine else None, "canBroadcast": bool(o["can_broadcast"]), "canOversee": bool(o["can_oversee"]),
        "myTitle": mine[o["id"]]["title"] if o["id"] in mine else None,
        "myRights": _ordered(_rights_from(mine[o["id"]]["role"], mine[o["id"]]["rights"])) if o["id"] in mine else [],
    } for o in found]


def orgs(con, v: Viewer) -> list[dict]:
    found = org_shapes(con, v, rows(con, "SELECT * FROM orgs WHERE status = 'active' AND kind NOT IN ('office','app')"))
    return sorted(found, key=lambda o: (not o.get("gov"), not o["subscribed"], -o["subscribers"]))


def org(con, v: Viewer, oid: int) -> dict:
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND (status = 'active' OR status = 'hidden' AND ?)", oid, v.role == "admin")
    if not o:
        raise ApiError("not_found")
    return {**org_shape(con, v, o), "leaders": _people(con, oid, "AND m.role IN ('president', 'vice')"), "chats": org_chats(con, oid)}


def _people(con, oid: int, where: str = "") -> list[dict]:
    found = rows(con, f"""SELECT {PERSON_COLS}, m.role, t.name AS title FROM org_members m JOIN users u ON u.id = m.user_id
        JOIN students s ON s.user_id = u.id LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ? {where}""", oid)
    return sorted(({"person": person_ref(p), "role": p["role"], "title": p["title"]} for p in found),
                  key=lambda m: (-RANK[m["role"]], m["person"]["name"]))


def people(con, v: Viewer, oid: int) -> list[dict]:
    """Everyone in a club or school, for anyone (owner, Oct 24: President and Vice first, a button for the rest), unless
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
            con.execute("INSERT INTO join_requests (org_id, user_id, created_at) VALUES (?, ?, ?)", (oid, v.id, core.now()))
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
                           ("accepted" if accept else "rejected", v.id, core.now(), rid)).rowcount:
            raise ApiError("conflict")  # withdrawn, or another Vice answered first
        if accept:
            con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (r["org_id"], r["user_id"], core.now()))
        notify(con, r["user_id"], "join_decided", f"jr:{rid}:{'yes' if accept else 'no'}")


def update_org(con, v: Viewer, oid: int, body: dict) -> dict:
    """The club's own profile and settings (Vice+, §2): whether it takes applications, and what students see on its
    sheet — the name and its short one, its logo (an upload of the editor's; null: the emoji on its cover again), emoji
    and cover, about, up to 6 links. Only what is sent changes, all or nothing. DMP may set any club's short name."""
    if body.keys() != {"abbr"} or not overseer(con, v):
        _may(con, v, oid, "profile")
    bad, sets = object(), {}
    text = lambda k: str(body.get(k) or "").strip()  # noqa: E731
    if "recruiting" in body:
        sets["recruiting"] = body["recruiting"] if isinstance(body["recruiting"], bool) else bad
    if "membersHidden" in body:
        sets["members_hidden"] = body["membersHidden"] if isinstance(body["membersHidden"], bool) else bad
    if "name" in body:  # no "KBTU" in it; an acronym it carried becomes the abbr, unless one is sent too (owner, Oct 25)
        named, acro = org_name(text("name"))
        sets["name"] = named if 2 <= len(text("name")) <= 60 else bad
        if acro and "abbr" not in body:
            sets["abbr"] = acro
        if sets["name"] is not bad and one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived' AND id != ?", sets["name"], oid):
            raise ApiError("conflict", "taken")
    if "slug" in body:  # the short link is the President's (owner, Oct 23)
        if _roles(con, v).get(oid) != "president":
            raise ApiError("forbidden")
        s = text("slug").lower()
        sets["slug"] = s if SLUG.fullmatch(s) and s not in RESERVED else bad
        if sets["slug"] is not bad and not _slug_free(con, s, oid):
            raise ApiError("conflict", "taken")
    if "short" in body:
        sets["short"] = text("short").upper() if 1 <= len(text("short")) <= 2 else bad
    if "abbr" in body:  # one word, 2-8 characters: it sits inline beside a role or a place
        sets["abbr"] = text("abbr") if re.fullmatch(r"\S{2,8}", text("abbr")) else bad
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
        with tx(con):  # the name checked and taken at once (review, Oct 26)
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
    return org(con, v, oid)


# ---------------------------------------------------------------- starting a club (§4.6)

CLUB_REAPPLY = 30 * 86400   # after a decline, a new application in 30 days
COVERS = 6                  # the cover palette (OrgLogo.svelte's COVERS)
LINK = re.compile(r"https://[A-Za-z0-9.-]+\.[a-z]{2,}(/[^\s]*)?")


def _links_ok(ls: object) -> bool:
    """A club's social links: up to 6 https addresses (the app draws Instagram, Telegram, TikTok... from the host)."""
    return isinstance(ls, list) and len(ls) <= 6 and len(set(map(str, ls))) == len(ls) \
        and all(isinstance(x, str) and len(x) <= 200 and LINK.fullmatch(x) for x in ls)  # the app keys them: no twins


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
    # up to 6 social links, the club's own rule (A4, owner Oct 23); the form before the refactor sends one "link"
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
        if one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived'", org_name(name)[0]):  # as it'll be named
            raise ApiError("conflict", "taken")
        aid = con.execute("""INSERT INTO club_applications (user_id, name, short, description, emoji, cover, links, why, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (v.id, name, short, about, emoji, cover, json.dumps(links), why, core.now())).lastrowid
        for (uid,) in rows(con, "SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL"):
            notify(con, uid, "club_application", f"capp:{aid}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), False)


def club_applications(con, v: Viewer) -> list[dict]:
    """The check (the admin: clubs are his, owner Oct 22): pending first, then the last decisions."""
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
            raise ApiError("not_found")
        oid = None
        if approve:
            if one(con, "SELECT 1 FROM orgs WHERE lower(name) = lower(?) AND status != 'archived'", a["name"]):
                raise ApiError("conflict", "taken")
            oid = create_org(con, v.id, a["name"], a["short"], a["emoji"], False)
            con.execute("UPDATE orgs SET cover = ?, description = ?, links = ? WHERE id = ?", (a["cover"], a["description"], a["links"], oid))
            appteam.set_role(con, v.id, a["user_id"], oid, "president", "club_application")
        con.execute("UPDATE club_applications SET status = ?, reason = ?, org_id = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                    ("approved" if approve else "rejected", None if approve else why, oid, v.id, core.now(), aid))
        notify(con, a["user_id"], "club_application_decided", f"cad:{aid}:{'yes' if approve else 'no'}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), True)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import appteam, core  # noqa: E402
from .appteam import _admin, staff  # noqa: E402
from .chatlist import org_chats  # noqa: E402
from .dmpregistry import DMP_COLS  # noqa: E402
from .orgnames import RESERVED, SLUG, _slug_free, create_org, org_name  # noqa: E402
from .seats import notify  # noqa: E402
from .shapes import _by_id, _may, _org, _qs, _rights_from, _roles, org_ref, person_ref, short_name  # noqa: E402
from .teams import _ordered, banned  # noqa: E402
