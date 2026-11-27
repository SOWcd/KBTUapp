"""People you may know: clubmates suggested to each other on the Friends page (idea: a student, in People of the app).

Opt-in on both sides: a row of `pymk_consents` is the "Suggest me" switch on, with the text it answered (CONSENT,
its own, as appeals.CONSENT; the policy's People you may know clause). Reciprocal: only someone who can be suggested sees
suggestions, so nobody watches without being seen. Off, the row goes and so do my suggestions both ways, at once.

Phase 1 is clubs only. On prod (Nov 2026) 178 students had a timetable, too few to match on, and a timetable can be
forged slot by slot to learn who sits in a room when (the review's probing attack): classes need a copy frozen per
term and a minimum of two before they count. Clubs are safe to count: their members see each other's membership already
(policy §8). A club counts when it is an active club whose roster isn't hidden, of at most BIG members (a crowd says
nothing), and neither person is on probation there. The card says how many, never which.

Never suggested to each other (`_barred`, both directions): friends, any request either way (waiting, declined at any
age, or accepted once: friends before), a block, a dismissal (either one's, or an unfriend), an open report by one on
the other. Neither is told anything. Worked out at night for everyone (TOP each), and for me alone when I switch it on;
SHOWN at a time, the next one moving up as I add or dismiss: at most TOP people a day, no paging."""
from __future__ import annotations

from collections import Counter, defaultdict

from . import core
from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, need_student, one, person_ref, rows

CONSENT = "pymk1"  # the switch's text (web: pymk.ask*); a reworded one is a new version, and old yeses ask again
TOP, SHOWN, BIG = 10, 5, 300
DISMISS_A_DAY = 100  # far past a person's x taps; only a script walking ids meets it

# who may be suggested and see suggestions, over `users u`: a signed-in student (not a typed-in row) who takes friend
# requests, opted in to this text, not banned, not leaving
_JOIN = f"JOIN students s ON s.user_id = u.id JOIN pymk_consents c ON c.user_id = u.id AND c.version = '{CONSENT}'"
_OK = "s.manual = 0 AND u.can_friend = 1 AND u.banned_at IS NULL AND u.delete_at IS NULL"
# (table, one side, the other, which rows): each a pair that is never suggested, read once for every pair
_BARS = (("friendships", "a", "b", ""), ("friend_requests", "from_id", "to_id", ""), ("blocks", "user_id", "blocked_id", ""),
         ("pymk_dismissed", "user_id", "other_id", ""), ("reports", "reporter_id", "target_id", "target = 'user' AND status = 'open'"))
# a club that counts, over `orgs o` and a membership `m` in it (the night's pairs, and the count a card shows now)
_OPEN = f"""o.kind = 'club' AND o.status = 'active' AND o.members_hidden = 0 AND m.probation = 0
    AND (SELECT COUNT(*) FROM org_members x WHERE x.org_id = m.org_id) <= {BIG}"""
_CLUBS = f"SELECT m.org_id, m.user_id FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE {_OPEN}"


def _barred(con, uid: int | None = None) -> set[tuple[int, int]]:
    """The pairs never suggested, as (lower id, higher id); only those with `uid` in them when given."""
    out = set()
    for t, a, b, which in _BARS:
        where = " AND ".join(x for x in (which, f"({a} = :u OR {b} = :u)" if uid is not None else "") if x)
        for x, y in con.execute(f"SELECT {a}, {b} FROM {t}" + (f" WHERE {where}" if where else ""), {"u": uid}):
            if x is not None and y is not None:
                out.add((min(x, y), max(x, y)))
    return out


def _rank(con, uid: int | None = None) -> list[tuple[int, int, int, int]]:
    """(person, suggested, shared clubs, score), the best TOP for each; for `uid` alone when given. Score: 2 a club, and
    1 for the same school and year (a tie-break only: never a suggestion by itself). One person's counts at a time:
    every pair of the night in one Counter is millions of tuples (hundreds of MB) at 4,000 people in full clubs."""
    ok = {r[0] for r in con.execute(f"SELECT u.id FROM users u {_JOIN} WHERE {_OK}")}
    if uid is not None and uid not in ok:
        return []
    barred = _barred(con, uid)
    members: dict[int, list[int]] = defaultdict(list)
    clubs_of: dict[int, list[int]] = defaultdict(list)
    # for me alone (switch, inside the settings' write): only my clubs are read
    mine = (" AND m.org_id IN (SELECT org_id FROM org_members WHERE user_id = ?)", (uid,)) if uid is not None else ("", ())
    for org, who in con.execute(_CLUBS + mine[0], mine[1]):
        if who in ok:
            members[org].append(who)
            clubs_of[who].append(org)
    year = {r[0]: (r[1], r[2]) for r in con.execute("SELECT user_id, school, course FROM students")}
    out = []
    for a in [uid] if uid is not None else list(clubs_of):  # ponytail: ~BIG² steps a club, fine to 4,000 opted-in people
        shared = Counter(b for org in clubs_of.get(a, ()) for b in members[org] if b != a)
        ya = year.get(a, (None, None))
        best = sorted(((2 * n + (all(ya) and year.get(b) == ya), n, b) for b, n in shared.items() if (min(a, b), max(a, b)) not in barred),
                      key=lambda x: (-x[0], x[2]))
        out += [(a, b, n, score) for score, n, b in best[:TOP]]
    return out


def _store(con, ranked: list[tuple[int, int, int, int]]) -> None:
    con.executemany("INSERT OR REPLACE INTO pymk (user_id, other_id, clubs, score) VALUES (?, ?, ?, ?)", ranked)


def night(con) -> None:
    """Once a day (chores._chores): everyone's suggestions worked out afresh."""
    if not core._once(con, "pymk_day", str(core.day_of(core.now()))):
        return
    ranked = _rank(con)  # reads only: the write lock just for the swap
    with tx(con):
        con.execute("DELETE FROM pymk")
        _store(con, ranked)
        # whoever switched off or dismissed while it was being worked out: gone now, not tomorrow
        con.execute(f"""DELETE FROM pymk WHERE user_id NOT IN (SELECT user_id FROM pymk_consents WHERE version = '{CONSENT}')
            OR other_id NOT IN (SELECT user_id FROM pymk_consents WHERE version = '{CONSENT}')
            OR EXISTS (SELECT 1 FROM pymk_dismissed d WHERE (d.user_id = pymk.user_id AND d.other_id = pymk.other_id)
                                                       OR (d.user_id = pymk.other_id AND d.other_id = pymk.user_id))""")


def switch(con, uid: int, on: bool) -> None:
    """Settings' "Suggest me" (account._update_me, inside its transaction). On: the yes to this text, and my own
    suggestions at once (the others' lists catch up tonight), once a day: off and on again deals no fresh TOP past the
    day's (the dismissed barred), nor holds the write lock for a script's loop. Off: gone both ways now."""
    if not on:
        con.execute("DELETE FROM pymk WHERE user_id = ? OR other_id = ?", (uid, uid))
        con.execute("DELETE FROM pymk_consents WHERE user_id = ?", (uid,))
        return
    if is_on(con, uid):
        return
    con.execute("INSERT OR REPLACE INTO pymk_consents (user_id, version, at) VALUES (?, ?, ?)", (uid, CONSENT, core.now()))
    if core._once(con, f"pymk_live:{uid}", str(core.day_of(core.now()))):
        con.execute("DELETE FROM pymk WHERE user_id = ?", (uid,))
        _store(con, _rank(con, uid))


def is_on(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM pymk_consents WHERE user_id = ? AND version = ?", uid, CONSENT) is not None


def shown(con, v: Viewer) -> list[dict] | None:
    """The Friends page's strip (in friends()): SHOWN people, each with how many clubs we share and nothing about which.
    None: I haven't switched it on (the page offers it). Everyone is checked again now: a pair barred since the night
    (a request, a block, a switch turned off) is gone already."""
    if not v.student or not is_on(con, v.id):
        return None
    if not one(con, f"SELECT 1 FROM users u {_JOIN} WHERE u.id = ? AND {_OK}", v.id):
        return []  # switched on, yet not suggestable now (requests closed, say): nothing to see either
    barred = _barred(con, v.id)
    # the clubs counted as they stand now, for all of them in one read: a roster hidden since the night, a probation,
    # a leave say nothing (the stored count only ranked them)
    shared = dict(con.execute(f"""SELECT b.user_id, COUNT(*) FROM org_members m JOIN orgs o ON o.id = m.org_id
        JOIN org_members b ON b.org_id = m.org_id AND b.probation = 0 AND b.user_id IN (SELECT other_id FROM pymk WHERE user_id = :me)
        WHERE m.user_id = :me AND {_OPEN} GROUP BY b.user_id""", {"me": v.id}).fetchall())
    out = []
    for p in rows(con, f"""SELECT {PERSON_COLS}, s.course, s.school FROM pymk p JOIN users u ON u.id = p.other_id {_JOIN}
            WHERE p.user_id = ? AND {_OK} ORDER BY p.score DESC, p.other_id""", v.id):
        if (min(v.id, p["id"]), max(v.id, p["id"])) not in barred and shared.get(p["id"]):
            out.append({"person": person_ref(p), "course": p["course"], "school": p["school"], "clubs": shared[p["id"]]})
            if len(out) == SHOWN:
                break
    return out


def dismiss(con, v: Viewer, uid: object) -> None:
    """The card's x: never suggested to each other again, quietly (until one of us deletes the account)."""
    need_student(v)
    if not isinstance(uid, int) or isinstance(uid, bool) or not 0 < uid < 2 ** 53 or uid == v.id:
        raise ApiError("bad_input")
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM pymk_dismissed WHERE user_id = ? AND at > ?", v.id, core.now() - 86400)[0] >= DISMISS_A_DAY:
            raise ApiError("rate_limited", "pymk dismissals a day")
        forget(con, v.id, uid)


def forget(con, me: int, uid: int) -> None:
    """A pair never suggested again, for good: dismissed, unfriended, a request taken back, a block or a report on a
    person (an ex, or someone I reported, doesn't come back once it's undone or resolved)."""
    con.execute("INSERT OR IGNORE INTO pymk_dismissed (user_id, other_id, at) SELECT ?, id, ? FROM users WHERE id = ?", (me, core.now(), uid))
    con.execute("DELETE FROM pymk WHERE (user_id = ? AND other_id = ?) OR (user_id = ? AND other_id = ?)", (me, uid, uid, me))
