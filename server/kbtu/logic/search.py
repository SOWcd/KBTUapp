"""One search for the whole app (owner, Nov 8): a query against every name a thing has (an event's title in each
language the AI wrote, a club's name, short and abbreviation in each, a person's Cyrillic and Latin names and nick),
case-free in any script (SQLite's LOWER/LIKE fold ASCII only), with yo as ye. What comes back is what the searcher may
already see: the admin everything, everyone else through the same rules as their lists (seats._visible, clubs.listed).

ponytail: every row folded in Python on each query (thousands of rows: milliseconds); a folded column or FTS past ~50k."""
from __future__ import annotations

import json
import re
import unicodedata

from .core import Viewer, _by_id, _roles, cards, now, org_ref, rows


def fold(s: object) -> str:
    """The form both sides are compared in: NFKC, Unicode case-folded (Cyrillic, Kazakh), yo as ye, spaces squeezed."""
    return " ".join(unicodedata.normalize("NFKC", str(s or "")).casefold().replace("\u0451", "\u0435").split())


def names(row, *keys: str) -> list[str]:
    """A row's columns `keys` as typed and the same fields of each of its translations (the i18n JSON, ai.py)."""
    tr = json.loads(row["i18n"]) if "i18n" in row.keys() and row["i18n"] else {}
    return [x for k in keys for x in (row[k], *((t or {}).get(k) for t in tr.values())) if x]


def hit(k: str, texts) -> bool:
    """Every word of the folded query `k` starts a word of one of the texts, in any order ("tole bi" and "nightm" find
    "A Nightmare on Tole Bi Street"; "b" isn't in "IT Club")."""
    ws = re.findall(r"\w+", k)
    return bool(ws) and any(all(any(t.startswith(w) for t in ts) for w in ws) for ts in (re.findall(r"\w+", fold(x)) for x in texts))


def person_hit(k: str, p) -> bool:
    """A person (the students' name columns, the users' nick) by any of their names."""
    return hit(k, (f"{p['first_name'] or ''} {p['last_name'] or ''}", f"{p['first_lat'] or ''} {p['last_lat'] or ''}", p["nick"]))


def people(found, q: str, n: int = 20) -> list:
    """Out of `found` (rows with u.id, u.tg_username, s.student_id and the name columns; the caller's query decides who
    may come back): the exact @username first, then by app id, exact student ID or any name (students only)."""
    k = fold(q)
    qid = int(k) if k.isdecimal() else -1
    first = [p for p in found if p["tg_username"] and fold(p["tg_username"]) == k]
    seen = {p["id"] for p in first}
    return (first + [p for p in found if p["id"] not in seen and (p["id"] == qid or p["student_id"] is not None
                                                                  and (fold(p["student_id"]) == k or person_hit(k, p)))])[:n]


def events(con, v: Viewer, q: object, n: int = 20) -> list[dict]:
    """Events by any of their titles, upcoming first (the soonest), then the past (the latest). The admin: any club's, any
    status, hidden too; everyone else: only what seats._visible lets them open (their club's drafts to its team)."""
    k = fold(q)
    if len(k) < 2:
        return []
    t = now()
    found = [e for e in rows(con, """SELECT * FROM events e WHERE memo_only = 0 AND NOT EXISTS (SELECT 1 FROM meta WHERE key = 'evdel:' || e.id)
        ORDER BY starts_at < ?, CASE WHEN starts_at >= ? THEN starts_at END, starts_at DESC""", t, t) if hit(k, names(e, "title"))]
    if v.role != "admin":
        roles, hidden = _roles(con, v), _hidden_orgs(con)
        found = [e for e in found if _visible(con, v, e, roles, hidden)]
    return cards(con, v, found[:n])


def clubs(con, v: Viewer, q: object, n: int = 20) -> list[dict]:
    """Clubs (types.ts OrgRef) by name, short or abbreviation in any language. The admin: every org, hidden too;
    everyone else: the registry's (clubs.listed)."""
    k = fold(q)
    if len(k) < 2:
        return []
    found = rows(con, "SELECT * FROM orgs") if v.role == "admin" else listed(con, v, small=True)
    found = sorted((o for o in found if hit(k, names(o, "name", "short", "abbr"))), key=lambda o: fold(o["name"]))[:n]
    logos = _by_id(con, "files", (o["logo_file_id"] for o in found))
    return [org_ref(con, o, logos) for o in found]


from .clubs import listed  # noqa: E402
from .seats import _hidden_orgs, _visible  # noqa: E402
