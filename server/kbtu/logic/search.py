"""One search across a row's names and translations. The caller decides which rows are visible."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import NamedTuple

from .core import Viewer, _by_id, _roles, cards, evdel, now, org_ref, rows


# Keep the matching rules in step with web/src/lib/search.ts.
_KK = str.maketrans("\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456", "\u0435\u0430\u0433\u043a\u043d\u043e\u0443\u0443\u0445\u0438")
_WORDS = re.compile(r"[^\W_]+")
_PARTS = re.compile(r"""(?:[^\W_]|[`\[\];',.=~{}:"<>@#$%*()_+\-])+""")
_EN_KEYS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,."
_RU_KEYS = "\u0451\u0439\u0446\u0443\u043a\u0435\u043d\u0433\u0448\u0449\u0437\u0445\u044a\u0444\u044b\u0432\u0430\u043f\u0440\u043e\u043b\u0434\u0436\u044d\u044f\u0447\u0441\u043c\u0438\u0442\u044c\u0431\u044e"
_KK_ROW = "\u04d9\u0456\u04a3\u0493\u04af\u04b1\u049b\u04e9\u04bb"
_EN_ROW = "2345890-="
_UNSHIFTED = str.maketrans('~{}:"<>@#$%*()_+', "`[];',." + _EN_ROW)
_LAYOUTS = (
    (_EN_KEYS, _RU_KEYS),
    (_EN_KEYS + _EN_ROW, _RU_KEYS + _KK_ROW),
    (_RU_KEYS + _KK_ROW, _EN_KEYS + _EN_ROW),
    (_RU_KEYS + _EN_ROW, _RU_KEYS + _KK_ROW),
    (_RU_KEYS + _KK_ROW, _RU_KEYS + _EN_ROW),
)
_LAYOUTS = tuple((set(keys), str.maketrans(keys, letters)) for keys, letters in _LAYOUTS)

_LAT = str.maketrans({
    "\u0430": "a", "\u0431": "b", "\u0432": "v", "\u0433": "g", "\u0434": "d", "\u0435": "e", "\u0436": "zh", "\u0437": "z",
    "\u0438": "i", "\u0439": "y", "\u043a": "k", "\u043b": "l", "\u043c": "m", "\u043d": "n", "\u043e": "o", "\u043f": "p",
    "\u0440": "r", "\u0441": "s", "\u0442": "t", "\u0443": "u", "\u0444": "f", "\u0445": "h", "\u0446": "ts", "\u0447": "ch",
    "\u0448": "sh", "\u0449": "sh", "\u044a": "", "\u044b": "y", "\u044c": "", "\u044d": "e", "\u044e": "yu", "\u044f": "ya",
    "\u00e4": "a", "\u00e1": "a", "\u011f": "g", "\u01f5": "g", "\u0131": "i", "\u00ed": "i", "\u00f1": "n", "\u0144": "n",
    "\u00f6": "o", "\u00f3": "o", "\u00fc": "u", "\u016b": "u", "\u00fa": "u", "\u00fd": "u", "\u015f": "sh", "\u015b": "sh",
    "\u00e7": "ch", "\u0107": "ch", "\u010d": "ch", "\u017e": "zh", "j": "zh", "q": "k",
})
_ALIAS = {"shch": "sh", "kh": "h", "gh": "g", "ng": "n", "yu": "iu", "ye": "e", "y": "i"}
_ALIASES = re.compile(r"shch|kh|gh|ng|[yi]+a|yu|ye|y")
_DOUBLE = re.compile(r"(.)\1+")


def fold(s: object) -> str:
    """Keep the case-insensitive spelling used for literal lookups such as usernames and IDs."""
    return " ".join(unicodedata.normalize("NFKC", str(s or "")).casefold().translate(_KK).split())


class _Word(NamedTuple):
    text: str
    latin: str


def _word(s: str) -> _Word:
    text = s.casefold().translate(_KK)
    latin = _undouble(text).translate(_LAT)
    latin = _ALIASES.sub(lambda m: _ALIAS.get(m[0], "a"), latin)
    return _Word(text, _undouble(latin))


def _undouble(s: str) -> str:
    return _DOUBLE.sub(lambda m: m[1] if m[1].isalpha() else m[0], s)


def _query_words(terms):
    return [(_word(s), min(3, len(s) // 4) if s.isalpha() else 0) for s in terms]


def _group(part, literal):
    forms = [(3, _query_words(literal))]
    split = [_group(s, [s]) for s in literal] if len(literal) > 1 else []
    if part.isnumeric():
        return forms, split
    unshifted = part.translate(_UNSHIFTED)
    previous = part
    for keys, layout in _LAYOUTS:
        if not keys.issuperset(unshifted):
            continue
        fixed = unshifted.translate(layout)
        if fixed == part or fixed == previous:
            continue
        previous = fixed
        terms = _WORDS.findall(fixed)
        if terms:
            forms.append((2, _query_words(terms)))
    return forms, split


def _prepare(q: str):
    groups = []
    for part in _PARTS.findall(unicodedata.normalize("NFKC", q).lower()):
        literal = _WORDS.findall(part)
        if literal:
            groups.append(_group(part, literal))
    return groups


def _near(w: str, t: str, limit: int, scratch) -> bool:
    """Banded edit distance to a word prefix, with adjacent transpositions."""
    if len(t) + limit < len(w):
        return False
    older, prev, cur = scratch
    end, stop = min(len(w) + limit, len(t)), limit + 1
    for j in range(limit + 1):
        prev[j] = j
    prev[limit + 1] = stop
    for i in range(1, len(w) + 1):
        lo, hi = max(1, i - limit), min(end, i + limit)
        cur[lo - 1] = i if lo == 1 else stop
        cur[hi + 1] = stop
        best = cur[lo - 1]
        for j in range(lo, hi + 1):
            distance = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (w[i - 1] != t[j - 1]))
            if i > 1 and j > 1 and w[i - 1] == t[j - 2] and w[i - 2] == t[j - 1]:
                distance = min(distance, older[j - 2] + 1)
            cur[j] = distance
            if distance < best:
                best = distance
        if best > limit:
            return False
        older, prev, cur = prev, cur, older
    return True


def _word_score(w, edits, terms, prefix, best, scratch) -> int:
    result = 0
    for t in terms:
        if t.text.startswith(w.text):
            return prefix
        if prefix == 3 and w.latin and t.latin.startswith(w.latin):
            result = 2
    if result or best >= 1 or not edits:
        return result
    latin_edits = min(edits, len(w.latin) // 4) if prefix == 3 else 0
    for t in terms:
        if _near(w.text, t.text, edits, scratch):
            return 1
        if latin_edits and (w.text != w.latin or t.text != t.latin) and _near(w.latin, t.latin, latin_edits, scratch):
            return 1
    return 0


def _name_score(query, terms, scratch) -> int:
    level = 3
    for forms, split in query:
        best = 0
        for prefix, words in forms:
            if prefix <= best:
                continue
            match = prefix
            for w, edits in words:
                match = min(match, _word_score(w, edits, terms, prefix, best, scratch))
                if match <= best:
                    break
            if match > best:
                best = match
        if best < 2 and split:
            best = max(best, _name_score(split, terms, scratch))
        if not best:
            return 0
        level = min(level, best)
    return level


class _Search:
    def __init__(self, q: str):
        self.query = _prepare(q)
        width = max((max(len(w.text), len(w.latin)) for forms, _ in self.query for _, words in forms for w, _ in words), default=0)
        self.scratch = [[0] * (width + 5) for _ in range(3)]

    def score(self, texts) -> int:
        if not self.query:
            return 0
        best = 0
        for text in texts:
            if not text:
                continue
            terms = [_word(w) for w in _WORDS.findall(unicodedata.normalize("NFKC", str(text)).lower())]
            best = max(best, _name_score(self.query, terms, self.scratch))
            if best == 3:
                break
        return best

    def person_score(self, p) -> int:
        return self.score(_person_names(p))


def score(q: str, texts) -> int:
    """Exact prefix (3), transliterated or layout-corrected prefix (2), typo (1), no match (0)."""
    return _Search(q).score(texts)


def hit(k: str, texts) -> bool:
    return score(k, texts) > 0


def names(row, *keys: str) -> list[str]:
    """A row's columns `keys` as typed and the same fields of each of its translations (the i18n JSON, ai.py)."""
    tr = json.loads(row["i18n"]) if "i18n" in row.keys() and row["i18n"] else {}
    return [x for k in keys for x in (row[k], *((t or {}).get(k) for t in tr.values())) if x]


def _person_names(p) -> tuple:
    return (f"{p['first_name'] or ''} {p['last_name'] or ''}", f"{p['first_lat'] or ''} {p['last_lat'] or ''}", p["nick"])


def people(found, q: str, n: int = 20) -> list:
    """Out of `found` (rows with u.id, u.tg_username, s.student_id and the name columns; the caller's query decides who
    may come back): the exact @username first, then by app id, exact student ID or any name (students only)."""
    k = fold(q.lstrip("@"))
    qid = int(k) if k.isdecimal() else -1
    first = [p for p in found if p["tg_username"] and fold(p["tg_username"]) == k]
    seen = {p["id"] for p in first}
    matcher = _Search(q)
    return (first + [p for p in found if p["id"] not in seen and (p["id"] == qid or p["student_id"] is not None
                       and (fold(p["student_id"]) == k or matcher.person_score(p)))])[:n]


def events(con, v: Viewer, q: object, n: int = 20) -> list[dict]:
    """Events by any of their titles, upcoming first (the soonest), then the past (the latest). The admin: any club's, any
    status, hidden too; everyone else: only what seats._visible lets them open (their club's drafts to its team)."""
    if len(fold(q)) < 2:
        return []
    matcher = _Search(str(q or ""))
    t = now()
    found = [e for e in rows(con, f"""SELECT * FROM events e WHERE memo_only = 0 AND NOT {evdel()}
        ORDER BY starts_at < ?, CASE WHEN starts_at >= ? THEN starts_at END, starts_at DESC""", t, t) if matcher.score(names(e, "title"))]
    if v.role != "admin":
        roles, hidden = _roles(con, v), _hidden_orgs(con)
        found = [e for e in found if _visible(con, v, e, roles, hidden)]
    else:  # a school's own event: the admin finds it from Admin, not in the app's search
        found = [e for e in found if school_ok(con, v, e)]
    return cards(con, v, found[:n])


def clubs(con, v: Viewer, q: object, n: int = 20) -> list[dict]:
    """Clubs (types.ts OrgRef) by name, short or abbreviation in any language. The admin: every org, hidden too;
    everyone else: the registry's (clubs.listed)."""
    if len(fold(q)) < 2:
        return []
    matcher = _Search(str(q or ""))
    found = rows(con, "SELECT * FROM orgs") if v.role == "admin" else listed(con, v, small=True)
    found = sorted((o for o in found if matcher.score(names(o, "name", "short", "abbr"))), key=lambda o: fold(o["name"]))[:n]
    logos = _by_id(con, "files", (o["logo_file_id"] for o in found))
    return [org_ref(con, o, logos) for o in found]


MORE_AN_HOUR = 240   # the app asks after a pause in typing (web/src/lib/find.ts), a few times a query
POSTS_SCANNED = 2000  # ponytail: the newest live posts are read and matched in Python; past a few thousand, an FTS table


def more(con, v: Viewer, q: object, *, forum: bool, channel: bool, n: int = 8) -> dict:
    """The app's global search, the part it doesn't hold in memory: people who made themselves findable, and the forum
    channel's live posts. People are only (a) an exact @username of a student who lets anyone add them as a friend (the
    Friends page's own rule, counted as a profile opened) and (b) with the find-people forum open to me (`forum`), those
    "open to projects" there, by name; never anyone else by name. Posts: what the feed shows (`channel`: it is on)."""
    q = str(q or "")[:80]
    if len(fold(q)) < 2:
        return {"people": [], "posts": []}
    key = f"gsearch:{v.id}:{now() // 3600}"
    with tx(con):
        k = int((one(con, "SELECT value FROM meta WHERE key = ?", key) or [0])[0])
        if k >= MORE_AN_HOUR:
            raise ApiError("rate_limited", "search")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(k + 1)))
        # one counter per person: the past hours' go, so meta never grows with every hour anyone searched
        con.execute("DELETE FROM meta WHERE key >= ? AND key < ? AND key != ?", (f"gsearch:{v.id}:", f"gsearch:{v.id};", key))
    return {"people": _findable(con, v, q, forum, n) if v.student else [], "posts": _posts(con, v, q, n) if channel else []}


def _findable(con, v: Viewer, q: str, forum: bool, n: int) -> list[dict]:
    out = []
    # a block either way, or a banned account: not found, and not counted as a profile opened (find_student checks neither)
    hidden = re.fullmatch(r"@[A-Za-z0-9_]{4,32}", q.strip()) and con.execute(f"""SELECT 1 FROM users u WHERE lower(u.tg_username) = lower(:name)
        AND (u.banned_at IS NOT NULL OR NOT {forum_mod._UNBLOCKED.format(u='u.id')})""", {"name": q.strip()[1:], "me": v.id}).fetchone()
    if re.fullmatch(r"@[A-Za-z0-9_]{4,32}", q.strip()) and not hidden:
        try:
            s = profiles.find_student(con, v, q.strip())
        except ApiError:
            s = None
        if s and not s["me"] and not s.get("closed"):
            out.append({"person": s["person"], "course": s["course"]})
    if forum:
        matcher = _Search(q)
        found = con.execute(f"""SELECT {PERSON_COLS}, s.student_id FROM users u JOIN students s ON s.user_id = u.id
            WHERE {forum_mod._FINDABLE} AND u.id != :me AND {forum_mod._UNBLOCKED.format(u='u.id')}""", {"me": v.id}).fetchall()
        scored = sorted(((matcher.person_score(p), p) for p in found), key=lambda x: -x[0])
        seen = {x["person"]["id"] for x in out}
        out += [{"person": person_ref(p), "course": course_of(p["student_id"])} for k, p in scored if k and p["id"] not in seen]
    return out[:n]


def _posts(con, v: Viewer, q: str, n: int) -> list[dict]:
    """Live channel posts whose words match (a typo alone isn't enough in a long text), the newest first."""
    matcher = _Search(q)
    with tx(con, write=False):
        ids = [p["id"] for p in rows(con, "SELECT id, body FROM fchan_posts WHERE status = 'live' AND tg_msg > 0 ORDER BY tg_msg DESC LIMIT ?",
                                     POSTS_SCANNED) if matcher.score([p["body"]]) >= 2][:n]
        return fchannel._feed_cards(con, v, fchannel._feed_rows(con, v, ids))


from . import fchannel, forum as forum_mod, profiles  # noqa: E402
from ..db import tx  # noqa: E402
from .clubs import listed  # noqa: E402
from .core import PERSON_COLS, ApiError, course_of, one, person_ref  # noqa: E402
from .seats import _hidden_orgs, _visible, school_ok  # noqa: E402
