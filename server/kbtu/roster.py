"""The clubs' rosters from DMP's Student Union sheet (PLAN 95, owner Oct 26): DMP gave it and allowed its use; every
row waits in roster_pending for its student and stays theirs (the city hidden or deleted any time). A one-off until
everyone has signed up (owner): the table is dropped by hand then.

Listed under my Telegram username but not signed in with Microsoft yet: a welcome with the clubs and positions only,
and the way to sign in. A row is someone's when the Telegram username (or the KBTU e-mail) is theirs AND the sheet's
name is the name on their KBTU account (same_person: any case, Cyrillic or Latin, Kazakh letters, any order, a
patronymic more: two words shared): they join at once and hear it in a toast. When only the username matches, they're asked, with the
club and position only (the sheet's name, phone and city may be someone else's): "Yes, it's me" (a typo, a new
surname) asks the club's President, or DMP for a club without one, who confirms or declines (declined: the row stays
for the right person, flagged in DMP's registry). No student removes a row: a wrong one is for support.

The file never enters the repo: tools/roster_convert.py turns it into JSON beside it, `admin roster load` loads that."""
from __future__ import annotations

import hashlib
import re
import sqlite3

from .logic import academic_year, kz_phone, now, one, rows, set_role, tx

# Cyrillic (Russian and Kazakh) to plain Latin, the way names are spelled both ways; escapes keep the code ASCII
TRANSLIT = {"\u0430": "a", "\u0431": "b", "\u0432": "v", "\u0433": "g", "\u0434": "d", "\u0435": "e", "\u0437": "z",
            "\u0438": "i", "\u043a": "k", "\u043b": "l", "\u043c": "m", "\u043d": "n", "\u043e": "o", "\u043f": "p",
            "\u0440": "r", "\u0441": "s", "\u0442": "t", "\u0443": "u", "\u0444": "f", "\u0451": "e", "\u0436": "zh",
            "\u0439": "i", "\u0445": "h", "\u0446": "ts", "\u0447": "ch", "\u0448": "sh", "\u0449": "sh",
            "\u044a": "", "\u044b": "i", "\u044c": "", "\u044d": "e", "\u044e": "iu", "\u044f": "ia", "\u04d9": "a",
            "\u0493": "g", "\u049b": "k", "\u04a3": "n", "\u04e9": "o", "\u04b1": "u", "\u04af": "u", "\u04bb": "h",
            "\u0456": "i"}


def latin(s: str) -> str:
    return "".join(TRANSLIT.get(c, c) for c in s.lower())


def _words(name: str | None) -> set[str]:
    """A name's words as one spelling: Latin, lowercase, the usual both-ways spellings made one (Yerlan/Erlan,
    Zhanna/Janna, Akhmet/Ahmet, Qasym/Kasym), doubled letters single."""
    out = set()
    for w in re.findall(r"[^\W\d_]+", latin(name or "")):
        for a, b in (("dzh", "zh"), ("kh", "h"), ("q", "k"), ("y", "i"), ("j", "zh")):
            w = w.replace(a, b)
        out.add(re.sub(r"(.)\1+", r"\1", re.sub(r"^ie", "e", w)))
    return out


def same_person(sheet_name: str | None, first: str, last: str) -> bool:
    """The sheet's full name is this KBTU account's: two words shared, in any order (owner: a one-off, keep it simple)."""
    return len(_words(sheet_name) & _words(f"{first} {last}")) >= 2


# ------------------------------------------------------------ a sheet row, read (tools/roster_convert.py, tests)

PLAIN = {"", "member", "uchastnik", "chlen"}      # latin(): member in English, Russian or the sheets' Russian spelling
OFFICIAL = re.compile(r"^(?:vice|vitse)[\s-]*(?:president|prezident|predsedatel|leader)?$|^(?:president|prezident|predsedatel|leader)$")
NOT_DEPT = {"member", "president", "vice-president", "-", "—"}


def _dept(x: str | None) -> str | None:
    d = " ".join(str(x or "").split())
    d = re.sub(r"\s+depart?ament$|\s+department$", "", d, flags=re.I)
    return d if d and d.lower() not in NOT_DEPT and len(d) <= 40 else None  # a sentence typed into the column isn't one


def classify(position: str | None, dept_col: str | None = None) -> tuple[str, str | None, str | None]:
    """(role, title, department) from a sheet's position: president / vice / head / member; a head "of X" (or "X head")
    leads department X; a position that isn't a plain member or an official title is kept as the club role's name
    (HR, a dancer, Head of SMM). A former president ("ex ...") is a member who keeps the title."""
    raw = " ".join(str(position or "").split())
    p = latin(raw).strip(" .")
    dept = _dept(dept_col)
    if p in PLAIN:
        return "member", None, dept
    if p.startswith("ex"):
        return "member", raw, dept
    if re.match(r"^vi[ct]s?e[\s-]*head", p):  # the head's deputy: a member of that department
        m = re.search(r"head(?:\s+of)?\s+(.+)$", p)
        return "member", raw, dept or (_dept(raw[-len(m.group(1)):]) if m else None)
    if OFFICIAL.match(p):
        return ("vice" if p.startswith("vi") else "president"), None, dept
    if re.match(r"^vi[ct]s?e\b|^vice", p):
        return "vice", raw, dept
    if p == "head" or re.match(r"^head\b", p) or p.endswith(" head"):
        m = re.match(r"(?i)^head(?:\s+of)?\s+(.+)$", raw) or re.match(r"(?i)^(.+?)\s+head$", raw)
        x = _dept(m.group(1)) if m else None
        return "head", (raw if p != "head" else None), dept or (x if x and x.lower() not in ("department", "departament") else None)
    m = re.match(r"(?i)^manager\s+of\s+(.+)$", raw)  # a department's manager: a member of it
    return "member", raw, dept or (_dept(m.group(1)) if m else None)


def course_of(year: str | None, ay: int | None = None) -> int | None:
    """The year of study from what the sheet says: 2, "3rd year", or the intake (23BD: entered in 2023)."""
    y = str(year or "").strip().upper()
    if m := re.match(r"^(\d{2})(?:B|M)", y):
        n = (ay or academic_year()) % 100 - int(m.group(1)) + 1
        return n if 1 <= n <= 6 else None
    m = re.match(r"^([1-6])(?:\D|$)", y)
    return int(m.group(1)) if m else None


def tg_of(x: str | None) -> str | None:
    t = re.sub(r"^(?:https?://)?(?:t|telegram)\.me/|^@", "", str(x or "").strip(), flags=re.I).strip().lstrip("@").lower()
    return t if re.fullmatch(r"[a-z][a-z0-9_]{3,31}", t) else None


def email_of(x: str | None) -> str | None:
    e = str(x or "").strip().lower()
    return e if re.fullmatch(r"[^@\s]{1,64}@[a-z0-9.-]{3,190}\.[a-z]{2,}", e) else None


def row_key(r: dict) -> str:
    return hashlib.sha1("|".join(str(r.get(k) or "") for k in ("sheet", "full_name", "tg", "email", "position")).encode()).hexdigest()


# ------------------------------------------------------------ loading (admin roster load)

COLS = ("sheet", "position", "title", "role", "dept", "full_name", "school", "year", "course", "city", "phone", "tg", "email")


def load(con, items: list[dict], orgmap: dict) -> dict:
    """The converter's rows, each sheet into the org the map names (a slug, or {"new": {name, short, emoji}}: created
    official). Again with the same file: nothing more. Then everyone already in the app whose row it is joins."""
    from .logic import create_org, org_name
    missing = sorted({r["sheet"] for r in items} - set(orgmap))
    if missing:
        raise ValueError(f"sheets without an org in the map: {missing}")
    added, made = 0, []
    with tx(con):
        org = {}
        for sheet, to in orgmap.items():
            if isinstance(to, str):
                o = one(con, "SELECT id FROM orgs WHERE slug = ?", to)
                if not o:
                    raise ValueError(f"{sheet}: no org {to}")
                org[sheet] = o["id"]
            else:
                new = to["new"]
                o = one(con, "SELECT id FROM orgs WHERE lower(name) = lower(?) AND status != 'archived'", org_name(new["name"])[0])  # as create_org names it
                if not o:
                    made.append(new["name"])
                org[sheet] = o["id"] if o else create_org(con, None, new["name"], new["short"], new.get("emoji", "sparkles_3d"), True)
        for r in items:
            if one(con, "SELECT 1 FROM meta WHERE key = ?", f"roster_done:{row_key(r)}"):
                continue  # joined already
            v = {k: r.get(k) for k in COLS}
            v["phone"] = kz_phone(v["phone"]) if v["phone"] else None
            added += con.execute(f"""INSERT OR IGNORE INTO roster_pending (key, org_id, {', '.join(COLS)}, created_at)
                VALUES (?, ?, {', '.join('?' * len(COLS))}, ?)""", (row_key(r), org[r["sheet"]], *v.values(), now())).rowcount
    joined, as_vice = 0, 0
    for (uid,) in rows(con, """SELECT DISTINCT u.id FROM users u LEFT JOIN students s ON s.user_id = u.id
            WHERE lower(u.tg_username) IN (SELECT tg FROM roster_pending) OR lower(s.email) IN (SELECT email FROM roster_pending)"""):
        got = match(con, uid)
        joined += len(got)
        as_vice += sum(v for _, v in got)
    return {"rows": len(items), "added": added, "orgs_made": made, "joined": joined, "president_as_vice": as_vice}


# ------------------------------------------------------------ claiming

def _mine(con, uid: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    """The student's KBTU account and the rows that may be theirs (their username or e-mail; none they said aren't)."""
    s = one(con, """SELECT s.first_name, s.last_name, s.email, u.tg_username FROM users u JOIN students s ON s.user_id = u.id
        WHERE u.id = ? AND s.manual = 0""", uid)
    if not s:
        return None, []
    found = rows(con, """SELECT * FROM roster_pending WHERE ((tg IS NOT NULL AND tg = lower(?)) OR (email IS NOT NULL AND email = lower(?)))
        AND (rejected_by IS NULL OR rejected_by != ?) ORDER BY id""", s["tg_username"] or "", s["email"] or "", uid)
    return s, found


def match(con, uid: int) -> list[tuple[int, bool]]:
    """Every row that is this student's (username or e-mail, and the name): joined now. (org, came in as Vice) each."""
    s, found = _mine(con, uid)
    return [(r["org_id"], join(con, uid, r)) for r in found if same_person(r["full_name"], s["first_name"], s["last_name"])]


def asks(con, uid: int) -> list[sqlite3.Row]:
    """Rows with this student's username or e-mail but another name: theirs only if they say so."""
    s, found = _mine(con, uid)
    return [r for r in found if r["claimed_by"] != uid and not same_person(r["full_name"], s["first_name"], s["last_name"])] if s else []


def join(con, uid: int, r: sqlite3.Row) -> bool:
    """The row made real; what the app already has wins (owner, Oct 26): a membership held keeps its role, a missing one
    is added (a President on the sheet where the club already has another in the app: Vice), and the position as the
    club role's name, the department, the city, the year and the phone fill only what's empty. Then the row goes.
    True when a President on the sheet came in as Vice."""
    oid = r["org_id"]
    vice = False
    with tx(con):
        m = one(con, "SELECT role, role_id FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)
        role = m["role"] if m else r["role"]
        if not m:
            if role == "president" and one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND role = 'president'", oid):
                role, vice = "vice", True
            set_role(con, None, uid, oid, role, "roster")
        if r["title"] and role != "president":
            mine = one(con, "SELECT role_id FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["role_id"]
            fixed = mine is None or one(con, "SELECT fixed FROM org_roles WHERE id = ?", mine)["fixed"]
            if fixed:  # a role name the club gave in the app stays
                t = one(con, "SELECT id FROM org_roles WHERE org_id = ? AND lower(name) = lower(?)", oid, r["title"][:40])
                tid = t["id"] if t else con.execute("""INSERT INTO org_roles (org_id, name, color, level, created_at) VALUES (?, ?, ?, ?, ?)""",
                                                    (oid, r["title"][:40], {"vice": "#7C4DFF", "head": "#3B6BFF"}.get(role, "#8E8E93"), role, now())).lastrowid
                con.execute("UPDATE org_members SET role_id = ? WHERE org_id = ? AND user_id = ?", (tid, oid, uid))
        if r["dept"] and not one(con, """SELECT 1 FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id
                WHERE g.org_id = ? AND mt.user_id = ? AND g.department = 1""", oid, uid):
            g = one(con, "SELECT id, department FROM org_tags WHERE org_id = ? AND lower(name) = lower(?)", oid, r["dept"][:40])
            gid = g["id"] if g else con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, ?, '#3B6BFF', 1, ?)",
                                                (oid, r["dept"][:40], now())).lastrowid
            if g and not g["department"]:
                con.execute("UPDATE org_tags SET department = 1 WHERE id = ?", (gid,))
            con.execute("INSERT OR IGNORE INTO member_tags (tag_id, user_id) VALUES (?, ?)", (gid, uid))
        if r["city"]:
            con.execute("UPDATE users SET city = COALESCE(city, ?) WHERE id = ?", (r["city"][:60], uid))
        con.execute("UPDATE students SET course = COALESCE(course, ?), phone = COALESCE(phone, ?) WHERE user_id = ?", (r["course"], r["phone"], uid))
        con.execute("INSERT INTO roster_toasts (user_id, org_id, title, at) VALUES (?, ?, ?, ?)", (uid, oid, r["title"], now()))
        con.execute("DELETE FROM roster_pending WHERE id = ?", (r["id"],))
        con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", (f"roster_done:{r['key']}", str(now())))  # a reload skips it
    return vice


def claim(con, uid: int, rid: int) -> None:
    """"Yes, it's me" on a row listed under another name (a typo, a new surname): whoever confirms hears it (the club's
    President, or DMP's leads for a club without one). A student never removes a row (owner, Oct 26): a wrong one goes
    to support from the app."""
    from .logic import ApiError, notify
    r = next((x for x in asks(con, uid) if x["id"] == rid), None)
    if r is None:
        raise ApiError("not_found")
    with tx(con):
        con.execute("UPDATE roster_pending SET claimed_by = ? WHERE id = ?", (uid, rid))
        for (aid,) in _approvers(con, r["org_id"]):
            notify(con, aid, "roster_claim", f"rq:{rid}:{uid}")


def _approvers(con, oid: int) -> list:
    """Who confirms a claim: the club's President; with none, DMP's leads (an overseeing org's non-members)."""
    p = rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", oid)
    return p or rows(con, """SELECT DISTINCT m.user_id FROM org_members m JOIN orgs o ON o.id = m.org_id
        WHERE o.can_oversee = 1 AND m.role != 'member'""")


def _approves(con, v, oid: int) -> bool:
    from .logic import overseer
    pres = one(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", oid)
    return (pres and pres["user_id"] == v.id and v.student) or (not pres and overseer(con, v))


def requests(con, v) -> list[dict]:
    """The claims I confirm: the student's KBTU name beside the sheet's (the President knows their people), the
    position and department; for DMP, the clubs with no President."""
    out = []
    for r in rows(con, """SELECT r.*, s.first_name, s.last_name FROM roster_pending r JOIN students s ON s.user_id = r.claimed_by
            WHERE r.claimed_by IS NOT NULL ORDER BY r.id"""):
        if _approves(con, v, r["org_id"]):
            out.append({"id": r["id"], "org": r["org_id"], "title": r["title"], "role": r["role"], "dept": r["dept"],
                        "sheetName": r["full_name"], "name": f"{r['first_name']} {r['last_name']}".strip(), "user": r["claimed_by"]})
    return out


def decide(con, v, rid: int, ok: bool) -> None:
    """The President (or DMP) on a claim: it's them (joined with the row's data, a toast on their next open) or not
    (the row stays for the right person, flagged)."""
    from .logic import ApiError
    r = one(con, "SELECT * FROM roster_pending WHERE id = ? AND claimed_by IS NOT NULL", rid)
    if not r:
        raise ApiError("not_found")
    if not _approves(con, v, r["org_id"]):
        raise ApiError("forbidden")
    with tx(con):
        if ok:
            join(con, r["claimed_by"], r)
        else:
            con.execute("UPDATE roster_pending SET rejected_by = claimed_by, claimed_by = NULL WHERE id = ?", (rid,))


def mine(con, uid: int) -> dict | None:
    """For /api/me. Not signed in with Microsoft yet but listed under my Telegram username: the welcome (owner, Oct 26:
    the way in), only the clubs and positions, nothing more before Microsoft says who I am. Signed in: the clubs just
    joined (a toast each, until seen) and the rows to ask about (no phone, no city: maybe someone else's)."""
    s, _ = _mine(con, uid)
    if not s:
        u = one(con, "SELECT tg_username FROM users WHERE id = ?", uid)
        found = rows(con, """SELECT DISTINCT org_id, title, role FROM roster_pending WHERE tg = lower(?) AND rejected_by IS NULL ORDER BY id""",
                     u["tg_username"] or "") if u and u["tg_username"] else []
        return {"welcome": [{"org": r["org_id"], "title": r["title"], "role": r["role"]} for r in found]} if found else None
    joined = rows(con, "SELECT org_id, title FROM roster_toasts WHERE user_id = ? ORDER BY at", uid)
    ask = asks(con, uid)
    if not joined and not ask:
        return None
    return {"joined": [{"org": r["org_id"], "title": r["title"]} for r in joined],
            "ask": [{"id": r["id"], "org": r["org_id"], "title": r["title"], "role": r["role"], "dept": r["dept"]} for r in ask]}


def seen(con, uid: int) -> None:
    con.execute("DELETE FROM roster_toasts WHERE user_id = ?", (uid,))
