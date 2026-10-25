"""Clubs and schools: the list, joining, the club's own profile, starting a club, creating and naming orgs."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .. import media
from ..db import tx

from .core import (ApiError, PERSON_COLS, RANK, Viewer, _by_id, _may, _org, _qs, _rights_from, _roles, can, log_action,
    need_student, one, org_ref, overseer, person_ref, role_in, rows, short_name)


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
            oversight.set_role(con, v.id, a["user_id"], oid, "president", "club_application")
        con.execute("UPDATE club_applications SET status = ?, reason = ?, org_id = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                    ("approved" if approve else "rejected", None if approve else why, oid, v.id, core.now(), aid))
        notify(con, a["user_id"], "club_application_decided", f"cad:{aid}:{'yes' if approve else 'no'}")
    return _club_app(con, one(con, "SELECT * FROM club_applications WHERE id = ?", aid), True)


def create_org(con, actor: int | None, name: str, short: str, emoji: str, official: bool, slug: str | None = None,
               kind: str = "club") -> int:
    """A club or a school, by the admin (the app or the CLI). A school (owner, Oct 13: KBTU's own, a few, made by the
    admin, never by an application) is official from the start and never closes; its President has a club
    President's rights. A slug nobody chose comes from the name (A5: kbtu.sow.kz/<slug>). Recruiting starts closed:
    the club opens it in Studio (owner, Oct 24)."""
    abbr = guess_abbr(name)
    name = org_name(name)[0]  # no "KBTU", the short form to abbr (owner, Oct 25)
    slug = slug or slug_for(con, name)
    cur = con.execute("INSERT INTO orgs (slug, kind, name, short, abbr, emoji, official, created_by, created_at, recruiting) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                      (slug, kind, name, short, abbr, emoji, int(official or kind == "school"), actor, core.now()))
    for rn, color, lv in OFFICIAL_ROLES:
        con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (?, ?, ?, ?, 1, ?)", (cur.lastrowid, rn, color, lv, core.now()))
    log_action(con, actor, "org_create", f"org:{cur.lastrowid}", json.dumps({"name": name}))
    return cur.lastrowid


# A5 short links kbtu.sow.kz/<slug> (owner, Oct 23): the name in Latin letters, the app's own paths never
# Cyrillic a..ya (U+0430..U+044F) in order, then yo and the Kazakh letters (code points: the code stays ASCII)
TRANSLIT = str.maketrans({**dict(zip(range(0x430, 0x450), "a b v g d e zh z i i k l m n o p r s t u f h c ch sh sch _ y _ e yu ya".split())),
    0x451: "e", 0x4D9: "a", 0x493: "g", 0x49B: "k", 0x4A3: "n", 0x4E9: "o", 0x4B1: "u", 0x4AF: "u", 0x4BB: "h", 0x456: "i", 0x44A: "", 0x44C: ""})
SLUG = re.compile(r"[a-z0-9]{2,24}")
RESERVED = {"api", "cal", "healthz", "exit", "privacy", "terms", "og", "media", "demo", "old", "assets", "emoji", "map", "admin",
            "app", "kbtu", "help", "login", "ms", "static", "www", "bot", "support", "settings", "outlook", "club", "clubs", "events",
            # and for the clubs' own links (Oct 25): what a phishing page would like to be
            "favicon", "apple-touch-icon", "robots", "sitemap", "auth", "oauth", "logout", "signin", "signup", "register", "account",
            "me", "profile", "dmp", "pay", "kaspi", "telegram", "tg", "security", "official", "news", "about", "wp-admin"}
# a club's own short link (owner, Oct 25): a club slug, or words joined by single hyphens, 2-32 characters
SHORT = re.compile(r"(?=.{2,32}$)[a-z0-9]+(?:-[a-z0-9]+)*")
LINKS_MAX = 20  # a club's: the names are everyone's, first come, first served


def slug_for(con, name: str, oid: int | None = None) -> str:
    """A free slug from a name: "Open Mic Club" -> openmicclub, then openmicclub2, ..."""
    base = re.sub(r"[^a-z0-9]", "", name.lower().translate(TRANSLIT))[:22]
    base = base if len(base) >= 2 else f"club{base}"
    return next(s for s in (base if n == 1 else f"{base}{n}" for n in range(1, 10_000))
                if _slug_free(con, s, oid))


def name_slugs(con) -> None:
    """At start: the clubs made before A5 got club<N>; they take their names' slugs, once (review: every start renamed
    a club<N> its President chose)."""
    if one(con, "SELECT 1 FROM meta WHERE key = 'slugs_named'"):
        return
    with tx(con):
        con.execute("INSERT INTO meta (key, value) VALUES ('slugs_named', '1')")
        for o in rows(con, "SELECT id, name FROM orgs WHERE slug GLOB 'club[0-9]*'"):
            con.execute("UPDATE orgs SET slug = ? WHERE id = ?", (slug_for(con, o["name"], o["id"]), o["id"]))


# words a club's initials leave out (owner, Oct 25): "Club of Film and Theatre" is CFT; Russian and Kazakh ones as code
# points (the code stays ASCII)
LINK_WORDS = {*"\u0438 \u0432 \u0432\u043e \u043d\u0430 \u043f\u043e \u0434\u043b\u044f \u0441 \u0441\u043e \u043e \u043e\u0431 \u043e\u0442 \u043f\u0440\u0438 \u0437\u0430 \u0438\u0437 \u043a \u0436\u04d9\u043d\u0435 \u043c\u0435\u043d \u043f\u0435\u043d \u0431\u0435\u043d".split(),
              "and", "of", "the", "for", "in", "on", "at", "a", "an", "to", "by"}


def initials(name: str) -> str:
    """A club's short name until it types its own: the first letters of its words, uppercase; one word stays whole
    (the first three letters of a long one). "KBTU" is no letter of it (owner, Oct 25)."""
    words = re.findall(r"[^\W_]+", name)
    words = [w for w in words if w.lower() not in LINK_WORDS and w.upper() not in KBTU] or words
    if len(words) == 1:
        return (words[0] if len(words[0]) <= 8 else words[0][:3]).upper()
    return "".join(w[0] for w in words).upper()[:8]


# Org names, one style (owner, Oct 25): no "KBTU" in a name (the whole app is KBTU's), and no "short + long": the short
# one is the abbr. Done to a name as it's created or renamed; the names already there were fixed by hand.
KBTU = {"KBTU", "\u041a\u0411\u0422\u0423"}  # and in Cyrillic
_KB = r"(?:kbtu|\u043a\u0431\u0442\u0443)"
_SEP = r"[\s\-\u2013\u2014|:,.]"
_HEAD = re.compile(rf"^{_KB}(?:['\u2019]s)?\b{_SEP}*", re.I)
# "... in KBTU", "... at KBTU", "... \u0432 / \u043f\u0440\u0438 \u041a\u0411\u0422\u0423": the little word goes too
_TAIL = re.compile(rf"(?:\s+(?:in|at|of|\u0432|\u043f\u0440\u0438))?{_SEP}*\(?\b{_KB}(?:\s+chapter)?\)?$", re.I)


def _acronym(w: str) -> bool:
    """One word of 2-8 capitals (digits too, "3D" no: a letter first), and not KBTU."""
    return 2 <= len(w) <= 8 and bool(re.fullmatch(r"[^\W\d_][^\W_]*", w)) and w.isupper() and w not in KBTU


def org_name(name: str) -> tuple[str, str | None]:
    """A name as typed -> (the name, the acronym it carried, for the abbr): "KBTU" off either end ("KBTU Open Mic",
    "Debate Club | KBTU", "IEEE KBTU Chapter"); "Society of Petroleum Engineers (SPE)" and "SPE \u2013 Society of ..."
    give SPE and keep the long name. A name that would be left under 2 characters stays as typed."""
    typed = " ".join(name.split())
    def bare(n: str) -> str:
        for _ in range(3):
            n = _TAIL.sub("", _HEAD.sub("", n)).strip()
        return n
    n, acro = bare(typed), None
    if (m := re.fullmatch(r"(.+?)\s*\(\s*([^\s()]+)\s*\)", n)) and _acronym(m[2]):
        n, acro = bare(m[1]), m[2]
    elif (m := re.fullmatch(r"(\S+)(?:\s*[\u2013\u2014]\s*|\s+[-|:]\s+)(.+)", n)) and _acronym(m[1]):
        acro, n = m[1], bare(m[2])
    return (n, acro) if len(n) >= 2 else (typed, None)


def guess_abbr(name: str) -> str:
    """The short name an org starts with: the acronym its name carried, else its initials."""
    n, acro = org_name(name)
    return acro or initials(n)


def fill_abbrs(con) -> None:
    """At start: an org without a short name takes its initials (the clubs made before it existed); a set one stays."""
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
    """A gone short link's name stays its club's and leads to the club (review, Oct 26: printed posters of one club
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


SCHOOLS_VERSION = "2"  # 2: the short names (SITE, ISE, KMA), owner Oct 14
SCHOOLS = json.loads((Path(__file__).parent.with_name("i18n") / "schools.json").read_text(encoding="utf-8"))


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
                slug = s["slug"] if _slug_free(con, s["slug"], None) else None
                o = _org(con, create_org(con, None, s["ru"]["name"], s["short"], s["emoji"], True, slug, "school"))
            logo = o["logo_file_id"]
            if logo is None:
                saved = media.save((Path(__file__).parent.with_name("schools") / f"{s['slug']}.png").read_bytes(), root)
                logo = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, created_at, color)
                    VALUES (?, 'org_logo', 'image/webp', ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                          saved["path"], core.now(), saved["color"])).lastrowid
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


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core, oversight  # noqa: E402
from .chatlist import org_chats  # noqa: E402
from .oversight import DMP_COLS, _admin, staff  # noqa: E402
from .seats import notify  # noqa: E402
from .teams import _ordered, banned  # noqa: E402
