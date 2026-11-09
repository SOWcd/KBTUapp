"""Anonymous usage counters: what students open, what nobody opens, how long the app takes to open. One table of daily
totals, (day, key, n), with no person in it (no user id, Telegram id, hash, IP or session); that is what keeps it out
of the privacy policy. The app sends batches (web/src/lib/stats.ts); the owner reads a weekly bot message and
`admin stats-usage`."""
from __future__ import annotations

from ..db import maybe
from . import core
from .core import _once, one, rows

# the one allowlist: anything else a client sends is ignored. web/src/lib/stats.ts has the same names (a test checks)
SCREENS = ("tab.afisha", "tab.forum", "tab.club", "tab.profile",
           "sheet.event", "sheet.club", "sheet.ticket", "sheet.person", "sheet.friends", "sheet.compose", "sheet.comments",
           "sheet.map", "sheet.week", "sheet.awards", "sheet.studio", "sheet.admin", "sheet.news", "sheet.feed", "sheet.assistant")
ACTIONS = ("do.signup", "do.follow", "do.forum", "do.casting", "do.qr", "do.donate")
SOURCES = ("from.none", "from.event", "from.club", "from.friend", "from.qr", "from.other")  # the startapp's class, never its value
PLATFORMS = ("ios", "android", "desktop", "web")
BUCKETS = ("≤1", "≤2", "≤3", "≤5", "≤8", "8+")  # seconds from navigation start to the first useful paint
KEYS = frozenset((*SCREENS, *ACTIONS, *SOURCES, *(f"err.{s}" for s in SCREENS),
                  *(f"open.{p}.{b}" for p in PLATFORMS for b in range(len(BUCKETS)))))

KEEP_DAYS = 180
MAX_IN_BATCH = 30   # of one key in one batch; a launch is one open.* sample
BATCH_COST, DAY_BUDGET = 5, 600  # one person's whole day: far above a real one, so one client can't skew the totals much
# ponytail: per worker and in memory only (user id -> counts spent today, never stored), so the ceiling is the budget
# times WEB_CONCURRENCY; a shared table would put a person into this feature's data, the one thing it must not have
_spent: dict[int, int] = {}
_spent_day = 0


def _today() -> int:
    return (core.now() + 5 * 3600) // 86400  # Almaty


def add(con, uid: int, body: dict) -> None:
    """One batch {key: count}: allowlisted, clamped, added in one short transaction, skipped when the budget ran out or the
    database is busy (a lost count is fine)."""
    global _spent, _spent_day
    day = _today()
    if day != _spent_day:
        _spent, _spent_day = {}, day
    counts = {k: min(n, 1 if k.startswith("open.") else MAX_IN_BATCH) for k, n in body.items() if k in KEYS and type(n) is int and n > 0}
    cost = sum(counts.values()) + BATCH_COST
    if not counts or _spent.get(uid, 0) + cost > DAY_BUDGET:
        return
    _spent[uid] = _spent.get(uid, 0) + cost
    maybe(con, con.executemany, """INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)
        ON CONFLICT (day, key) DO UPDATE SET n = n + excluded.n""", [(day, k, n) for k, n in counts.items()])


def forget(con) -> None:
    con.execute("DELETE FROM usage_days WHERE day < ?", (_today() - KEEP_DAYS,))


def week(con) -> None:
    """Monday from 9:00 (Almaty), once: the last seven days' numbers to the creator alone."""
    local = core.now() + 5 * 3600
    day = local // 86400
    if (day + 3) % 7 or local % 86400 < 9 * 3600 or not _once(con, "usage_week", str(day)):
        return
    for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND tg_id > 0"):
        notify(con, uid, "usage_week", f"uw:{day}")


def _percentile(bars: list[int], share: float) -> str:
    """The bucket holding that share of the samples, by its upper edge: a histogram doesn't know more."""
    need, seen = sum(bars) * share, 0
    for label, n in zip(BUCKETS, bars):
        seen += n
        if seen >= need:
            return label
    return BUCKETS[-1]


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
    return {"days": days, "active": one(con, "SELECT COUNT(*) FROM users WHERE seen_at >= ?", (upto - days) * 86400 - 5 * 3600)[0],
            "top": lines(most[:10]), "bottom": lines(most[:-11:-1]), "actions": lines(ACTIONS, 3),
            "sources": lines(sorted(SOURCES, key=lambda k: -got.get(k, 0)), 5),
            "errors": lines(sorted((f"err.{s}" for s in SCREENS if got.get(f"err.{s}")), key=lambda k: -got[k]), 4),
            "opens": "\n".join(opens) or "—"}


from .seats import notify  # noqa: E402  (imported last: seats reaches this package's other modules too)
