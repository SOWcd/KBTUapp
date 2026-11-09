"""Anonymous usage counters: what students open, what nobody opens, how long the app takes to open. One table of daily
totals, (day, key, n), with no person in it (no user id, Telegram id, hash, IP or session); that is what keeps it out
of the privacy policy. The app sends batches (web/src/lib/stats.ts); the owner reads a weekly bot message and
`admin stats-usage`."""
from __future__ import annotations

from ..db import maybe, tx
from . import core
from .core import _once, one, rows

# no sheet.admin: with one moderator, its error count would say who hit it
# the one allowlist: anything else a client sends is ignored. web/src/lib/stats.ts has the same names (a test checks)
SCREENS = ("tab.afisha", "tab.forum", "tab.club", "tab.profile",
           "sheet.event", "sheet.club", "sheet.ticket", "sheet.person", "sheet.friends", "sheet.compose", "sheet.comments",
           "sheet.map", "sheet.week", "sheet.awards", "sheet.studio", "sheet.news", "sheet.feed", "sheet.assistant")
ACTIONS = ("do.signup", "do.follow", "do.forum", "do.casting", "do.qr", "do.donate")
SOURCES = ("from.none", "from.event", "from.club", "from.friend", "from.qr", "from.other")  # the startapp's class, never its value
PLATFORMS = ("ios", "android", "desktop", "web")
BUCKETS = ("≤1", "≤2", "≤3", "≤5", "≤8", "8+")  # seconds from navigation start to the first useful paint
SESSIONS = ("≤30s", "≤1m", "≤3m", "≤5m", "≤10m", "≤20m", "20m+")  # one visit's visible time, ended by 30 s or more hidden
DAY_TIMES = ("≤1m", "≤5m", "≤10m", "≤20m", "≤40m", "≤60m", "60m+")  # one device's visible time over a calendar day
USES = (*SCREENS, *ACTIONS)  # uniq.<key>: at most once a day per device (a flag kept on the device), for "N% of those active used it"
KEYS = frozenset((*SCREENS, *ACTIONS, *SOURCES, *(f"err.{s}" for s in SCREENS), *(f"uniq.{k}" for k in USES),
                  *(f"open.{p}.{b}" for p in PLATFORMS for b in range(len(BUCKETS))),
                  *(f"sess.{b}" for b in range(len(SESSIONS))), *(f"time.{b}" for b in range(len(DAY_TIMES)))))
ONE_A_BATCH = ("open.", "uniq.", "sess.", "time.")  # samples, not taps

KEEP_DAYS = 180
WINDOW = 30  # what `visits` keeps
MAX_IN_BATCH = 30   # of one key in one batch
BATCH_COST, DAY_BUDGET = 5, 600  # one person's whole day: far above a real one, so one client can't skew the totals much
# ponytail: per worker and in memory only (user id -> counts spent today, never stored), so the ceiling is the budget
# times WEB_CONCURRENCY; a shared table would put a person into this feature's data, the one thing it must not have
_spent: dict[int, int] = {}
_spent_day = 0
# ponytail: same ceiling (per worker, in memory): who already counted a uniq.* key today; a repeat is dropped, so one client can't inflate uniques
_uniq: set[tuple[int, str]] = set()


def _today() -> int:
    return (core.now() + 5 * 3600) // 86400  # Almaty


def add(con, uid: int, body: dict) -> None:
    """One batch {key: count}: allowlisted, clamped, added in one short transaction, skipped when the budget ran out or the
    database is busy (a lost count is fine)."""
    global _spent, _spent_day
    day = _today()
    if day != _spent_day:
        _spent, _spent_day = {}, day
        _uniq.clear()
    counts = {k: min(n, 1 if k.startswith(ONE_A_BATCH) else MAX_IN_BATCH) for k, n in body.items() if k in KEYS and type(n) is int and n > 0 and (uid, k) not in _uniq}
    cost = sum(counts.values()) + BATCH_COST
    if not counts or _spent.get(uid, 0) + cost > DAY_BUDGET:
        return
    _spent[uid] = _spent.get(uid, 0) + cost
    _uniq.update((uid, k) for k in counts if k.startswith("uniq."))
    maybe(con, con.executemany, """INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)
        ON CONFLICT (day, key) DO UPDATE SET n = n + excluded.n""", [(day, k, n) for k, n in counts.items()])


def forget(con) -> None:
    con.execute("DELETE FROM usage_days WHERE day < ?", (_today() - KEEP_DAYS,))


def week(con) -> None:
    """Monday from 9:00 (Almaty), once: the last seven days' numbers to the creator alone."""
    local = core.now() + 5 * 3600
    day = local // 86400
    if (day + 3) % 7 or local % 86400 < 9 * 3600:
        return
    with tx(con):  # the mark and the queue together: a restart between them can't lose the digest
        if not _once(con, "usage_week", str(day)):
            return
        for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND tg_id > 0"):
            notify(con, uid, "usage_week", f"uw:{day}")


def _percentile(bars: list[int], share: float, labels: tuple = BUCKETS) -> str:
    """The bucket holding that share of the samples, by its upper edge: a histogram doesn't know more."""
    need, seen = sum(bars) * share, 0
    for label, n in zip(labels, bars):
        seen += n
        if seen >= need:
            return label
    return labels[-1]


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%"


def _active(con, lo: int, hi: int) -> int:
    return one(con, "SELECT COUNT(DISTINCT user_id) FROM visits WHERE day >= ? AND day < ?", lo, hi)[0]


def _retention(con, upto: int) -> dict:
    """From what the privacy policy already allows, read only: `visits` (the days someone opened the app, kept 30 days,
    for statistics the creator alone sees) and users.created_at. Only totals leave this function."""
    lo = upto - WINDOW
    active = lambda days: _active(con, upto - days, upto)  # noqa: E731
    back = []
    for n in (1, 7, 30):  # of those who joined on a day whose n-th day after it is inside the window: came back on that day
        new, came = one(con, """SELECT COUNT(*), COALESCE(SUM(EXISTS (SELECT 1 FROM visits v WHERE v.user_id = u.id AND v.day = (u.created_at + 18000) / 86400 + ?)), 0)
            FROM users u WHERE u.tg_id > 0 AND u.created_at >= ? AND u.created_at < ?""", n, (lo - n) * 86400 - 18000, (upto - n) * 86400 - 18000)
        back.append(f"D{n}: {_pct(came, new)} ({came}/{new})" if new else f"D{n}: —")
    per_person = [r[0] for r in rows(con, "SELECT COUNT(*) FROM visits WHERE day >= ? AND day < ? GROUP BY user_id", lo, upto)]
    bands = (("1", 1, 1), ("2-3", 2, 3), ("4-7", 4, 7), ("8-15", 8, 15), ("16+", 16, 99))
    spread = [f"{name}: {_pct(sum(a <= n <= b for n in per_person), len(per_person))}" for name, a, b in bands] if per_person else []
    return {"dau": active(1), "wau": active(7), "mau": active(WINDOW), "retention": "\n".join(back), "spread": "\n".join(spread) or "—"}


def fields(con, days: int, upto: int | None = None) -> dict:
    """The template's fields (texts: usage_week) for `days` days before day `upto`; none given: up to and including today."""
    upto = _today() + 1 if upto is None else upto
    got = {r[0]: r[1] for r in rows(con, "SELECT key, SUM(n) FROM usage_days WHERE day >= ? AND day < ? GROUP BY key", upto - days, upto)}
    lines = lambda ks, cut=0: "\n".join(f"{k[cut:]} {got.get(k, 0)}" for k in ks) or "—"  # noqa: E731
    most = sorted(SCREENS, key=lambda k: (-got.get(k, 0), k))
    opens = []
    for p in PLATFORMS:
        bars = [got.get(f"open.{p}.{b}", 0) for b in range(len(BUCKETS))]
        if sum(bars):
            opens.append(f"{p}: {_percentile(bars, .5)} / {_percentile(bars, .75)} ({sum(bars)})")
    def spread(prefix: str, labels: tuple) -> str:
        bars = [got.get(f"{prefix}.{b}", 0) for b in range(len(labels))]
        if not sum(bars):
            return "—"
        return " · ".join(f"{a} {n}" for a, n in zip(labels, bars)) + f"\np50 {_percentile(bars, .5, labels)}, p75 {_percentile(bars, .75, labels)}"
    # uniq.* is per device and day, `visits` per person and day: the share of those active on the days of the window
    seen = upto - min(days, WINDOW)
    active_days = one(con, "SELECT COUNT(*) FROM visits WHERE day >= ? AND day < ?", seen, upto)[0]
    used = {k: one(con, "SELECT COALESCE(SUM(n), 0) FROM usage_days WHERE key = ? AND day >= ? AND day < ?", f"uniq.{k}", seen, upto)[0] for k in USES}
    uses = "\n".join(f"{k} {_pct(used[k], active_days)}" for k in sorted(USES, key=lambda k: -used[k])) if active_days else "—"
    return {**_retention(con, upto), "sessions": spread("sess", SESSIONS), "day_times": spread("time", DAY_TIMES), "uses": uses,
            "days": days, "active": _active(con, upto - days, upto),
            "top": lines(most[:10]), "bottom": lines(most[:-11:-1]), "actions": lines(ACTIONS, 3),
            "sources": lines(sorted(SOURCES, key=lambda k: -got.get(k, 0)), 5),
            "errors": lines(sorted((f"err.{s}" for s in SCREENS if got.get(f"err.{s}")), key=lambda k: -got[k]), 4),
            "opens": "\n".join(opens) or "—"}


from .seats import notify  # noqa: E402  (imported last: seats reaches this package's other modules too)
