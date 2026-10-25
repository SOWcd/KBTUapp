"""Creating orgs and naming them: slugs, short links, names and abbreviations, KBTU's schools."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import media
from ..db import tx

from .core import ApiError, Viewer, log_action, one, rows


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
from . import core  # noqa: E402
from .appteam import _admin  # noqa: E402
from .shapes import _may, _org, can  # noqa: E402
