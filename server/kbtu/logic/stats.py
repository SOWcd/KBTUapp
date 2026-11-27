"""Anonymous usage counters: what students open, what nobody opens, how long the app and each screen take to open, where
people drop out of the key flows, which errors they hit (by class only). One table of daily totals, (day, key, n), with
no person in it (no user id, Telegram id, hash, IP or session); that is what keeps it out of the privacy policy. The app
sends batches (web/src/lib/stats.ts). The owner reads the totals with `admin stats-usage`, the week's changes with
`admin stats-week` and the phones' layout numbers with `admin stats-layout`."""
from __future__ import annotations

import math
import time

from ..db import maybe
from . import core
from .core import one, rows

# no sheet.admin: with one moderator, its error count would say who hit it
# the one allowlist: anything else a client sends is ignored. web/src/lib/stats.ts has the same names (a test checks)
SCREENS = ("tab.afisha", "tab.forum", "tab.club", "tab.profile",
           "sheet.event", "sheet.club", "sheet.ticket", "sheet.person", "sheet.friends", "sheet.compose", "sheet.comments",
           "sheet.map", "sheet.week", "sheet.awards", "sheet.studio", "sheet.news", "sheet.feed", "sheet.assistant",
           "sheet.scanner", "sheet.doorpeople", "sheet.attendees", "sheet.manage", "sheet.editor", "sheet.team", "sheet.member", "sheet.joininbox",
           "sheet.pay", "sheet.people", "sheet.sponsors", "sheet.teams")
# what shipped since Nov 20, each counted where it's used (the second row on): `stats-week` shows them as "new"
NEW_ACTIONS = ("do.coming", "do.heart", "do.comment", "do.research", "do.pymk", "do.pymkon", "do.share", "do.filter", "do.past",
               "do.calendar", "do.photo", "do.helpus", "do.anon", "do.chatlink", "do.kri")
ACTIONS = ("do.signup", "do.follow", "do.forum", "do.casting", "do.qr", "do.donate", *NEW_ACTIONS)
SOURCES = ("from.none", "from.event", "from.club", "from.friend", "from.qr", "from.other")  # the startapp's class, never its value
# the appeals' funnel (logic/appeals.py): opened the composer, started typing, asked the AI, sent, closed without
# sending, deleted one; counts only, never a word (the draft stays on the phone)
APPEALS = ("apl.open", "apl.typed", "apl.ai", "apl.sent", "apl.drop", "apl.del")
# the Afisha's personal hero (web/src/lib/hero.ts KINDS, the same names): its cards shown and tapped, by kind only
HERO_KINDS = ("ticket", "friends", "club", "news", "forum", "class", "next", "today", "week")
HERO = tuple(f"hero.{a}.{k}" for a in ("show", "tap") for k in HERO_KINDS)
# the Android tester's funnel: the sheet in the app (shown, tapped), then kbtu.sow.kz/android.html in the phone's
# browser (opened, each Google step's button, the "Item not found" retry); the page has no sign-in, so `page_hit`.
# Beside the chain: andr.again, the sheet's one second showing (3 days on, dismissed); andr.row / andr.rowgo, Profile's
# lasting row drawn (once a launch) and tapped
ANDROID_MORE = ("andr.again", "andr.row", "andr.rowgo")
ANDROID_APP = ("andr.sheet", "andr.go", *ANDROID_MORE)
ANDROID_PAGE = ("page", "join", "optin", "play", "retry")
ANDROID = ("andr.sheet", "andr.go", *(f"andr.{k}" for k in ANDROID_PAGE))
PAGE_CAP = 5000  # a key's day ceiling for the signed-out page: far above real use, so a script can't run it up
# the key flows, step by step (each step's key in order), then what ends one short: where people drop, counts only
FUNNELS = {
    "signup": (("sheet.event", "signup.tap", "signup.done"), ("signup.fail",)),     # a free or paid event's Going
    "paid": (("sheet.pay", "paid.file", "paid.sent"), ("paid.fail", "paid.bot")),    # the receipt, here or by the bot
    "post": (("post.open", "post.typed", "post.sent"), ("post.fail", "post.drop")),  # a new forum post
    "edit": (("edit.open", "edit.saved"), ("edit.fail",)),                           # my live post edited
    "join": (("sheet.club", "join.tap", "join.sent"), ("join.fail",)),               # applying to a club
    "android": (("andr.sheet", "andr.go", "andr.page", "andr.join", "andr.optin", "andr.play"), ("andr.retry",)),  # app, then page
    "appeal": (("apl.open", "apl.typed", "apl.sent"), ("apl.ai", "apl.drop")),
}
STREAK = (*(f"streak.t{i}" for i in range(5)), "streak.tap")  # my flame drawn, by its tier (0..4), and tapped
JS_KINDS = ("type", "ref", "range", "syntax", "chunk", "other")  # an uncaught error's class, never its message
API_KINDS = ("network", "server", "unauthorized", "need_student", "forbidden", "not_found", "full", "closed", "conflict",
             "guest_list", "rate_limited", "bad_input", "unavailable")  # a failed call: no answer, a 5xx, or the server's code
PLATFORMS = ("ios", "android", "desktop", "web")
BUCKETS = ("≤1", "≤2", "≤3", "≤5", "≤8", "8+")  # seconds from navigation start to the first useful paint
TTI = ("≤100ms", "≤250ms", "≤500ms", "≤1s", "≤2s", "2s+")  # a tab's or a sheet's tap to its first frame
SESSIONS = ("≤30s", "≤1m", "≤3m", "≤5m", "≤10m", "≤20m", "20m+")  # one visit's visible time, ended by 30 s or more hidden
DAY_TIMES = ("≤1m", "≤5m", "≤10m", "≤20m", "≤40m", "≤60m", "60m+")  # one device's visible time over a calendar day
# the phone's layout, once a launch (web stats.ts layout()): Telegram's safe-area insets, env(safe-area-inset-bottom),
# the window's height over Telegram's stable one, the tab bar's gap to the window bottom; by platform and Telegram's
# major version ('x': another or none), each value by its bucket only, so no exact size can name a device
LAY = ("0", "1-8", "9-16", "17-24", "25-32", "33-48", "49-64", "65+")  # px
LAY_VALUES = {"safe_b": "tg safeAreaInset.bottom", "safe_t": "tg safeAreaInset.top", "content_b": "tg contentSafeAreaInset.bottom",
              "content_t": "tg contentSafeAreaInset.top", "env_b": "env(safe-area-inset-bottom)",
              "stable": "innerHeight - viewportStableHeight", "gap": "nav bottom gap (10 by design)"}
TG_MAJORS = ("6", "7", "8", "9", "10", "11", "12", "x")
LAY_KEYS = (*(f"lay.{p}.{v}.{m}.{b}" for p in PLATFORMS for v in TG_MAJORS for m in LAY_VALUES for b in range(len(LAY))),
            *(f"lay.{p}.{v}.full.{b}" for p in PLATFORMS for v in TG_MAJORS for b in (0, 1)))
USES = (*SCREENS, *ACTIONS)  # uniq.<key>: at most once a day per device (a flag kept on the device), for "N% of those active used it"
FLOW_KEYS = tuple(k for steps, ends in FUNNELS.values() for k in (*steps, *ends))
KEYS = frozenset((*SCREENS, *ACTIONS, *SOURCES, *APPEALS, *HERO, *ANDROID_APP, *STREAK,
                  *(k for k in FLOW_KEYS if not k.startswith("andr.")),  # the page's own come by page_hit only
                  *(f"err.{s}" for s in SCREENS), *(f"uniq.{k}" for k in USES),
                  *(f"js.{s}.{k}" for s in SCREENS for k in JS_KINDS), *(f"api.{s}.{k}" for s in SCREENS for k in API_KINDS),
                  *(f"tti.{s}.{p}.{b}" for s in SCREENS for p in PLATFORMS for b in range(len(TTI))),
                  *(f"open.{p}.{b}" for p in PLATFORMS for b in range(len(BUCKETS))),
                  *(f"sess.{b}" for b in range(len(SESSIONS))), *(f"time.{b}" for b in range(len(DAY_TIMES))), *LAY_KEYS))
ONE_A_BATCH = ("open.", "uniq.", "sess.", "time.", "lay.")  # samples, not taps

KEEP_DAYS = 180
WINDOW = 30  # what `visits` keeps
MAX_IN_BATCH = 30   # of one key in one batch
BATCH_COST, DAY_BUDGET = 5, 1500  # one person's whole day: far above a real one, so one client can't skew the totals much
# ponytail: per worker and in memory only (user id -> counts spent today, never stored), so the ceiling is the budget
# times WEB_CONCURRENCY; a shared table would put a person into this feature's data, the one thing it must not have
_spent: dict[int, int] = {}
_spent_day = 0
# ponytail: same ceiling (per worker, in memory): who already counted a uniq.* key today; a repeat is dropped, so one client can't inflate uniques
_uniq: set[tuple[int, str]] = set()


def _today() -> int:
    return core.day_of(core.now())


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


def page_hit(con, key: str) -> None:
    """One tap on android.html, signed out: one of ANDROID_PAGE, +1, never past PAGE_CAP a day; anything else is ignored."""
    if key in ANDROID_PAGE:
        maybe(con, con.execute, """INSERT INTO usage_days (day, key, n) VALUES (?, ?, 1)
            ON CONFLICT (day, key) DO UPDATE SET n = n + 1 WHERE n < ?""", (_today(), f"andr.{key}", PAGE_CAP))


def forget(con) -> None:
    con.execute("DELETE FROM usage_days WHERE day < ?", (_today() - KEEP_DAYS,))


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
    totals = got if days <= WINDOW else dict(rows(con, """SELECT key, SUM(n) FROM usage_days
        WHERE day >= ? AND day < ? AND key GLOB 'uniq.*' GROUP BY key""", seen, upto))
    used = {k: totals.get(f"uniq.{k}", 0) for k in USES}
    uses = "\n".join(f"{k} {_pct(used[k], active_days)}" for k in sorted(USES, key=lambda k: -used[k])) if active_days else "—"
    return {**_retention(con, upto), "sessions": spread("sess", SESSIONS), "day_times": spread("time", DAY_TIMES), "uses": uses,
            "days": days, "active": _active(con, upto - days, upto),
            "top": lines(most[:10]), "bottom": lines(most[:-11:-1]), "actions": lines(ACTIONS, 3),
            "sources": lines(sorted(SOURCES, key=lambda k: -got.get(k, 0)), 5),
            "errors": lines(sorted((f"err.{s}" for s in SCREENS if got.get(f"err.{s}")), key=lambda k: -got[k]), 4),
            "hero": "\n".join(f"{k} {got.get(f'hero.tap.{k}', 0)}/{got.get(f'hero.show.{k}', 0)}" for k in HERO_KINDS),
            "android": " → ".join(f"{k[5:]} {got.get(k, 0)}" for k in ANDROID) + "".join(f" · {k[5:]} {got.get(k, 0)}" for k in ANDROID_MORE),
            "opens": "\n".join(opens) or "—"}


def layout(con, days: int) -> str:
    """`admin stats-layout`: per platform and Telegram version, how many launches were fullscreen, then each layout
    value's spread over the buckets (px), for `days` days up to and including today."""
    upto = _today() + 1
    got = {r[0]: r[1] for r in rows(con, """SELECT key, SUM(n) FROM usage_days WHERE day >= ? AND day < ?
        AND key GLOB 'lay.*' GROUP BY key""", upto - days, upto)}
    out = []
    for p in PLATFORMS:
        for v in TG_MAJORS:
            full, rest = got.get(f"lay.{p}.{v}.full.1", 0), got.get(f"lay.{p}.{v}.full.0", 0)
            lines = []
            for m, name in LAY_VALUES.items():
                bars = [(label, got.get(f"lay.{p}.{v}.{m}.{b}", 0)) for b, label in enumerate(LAY)]
                if any(n for _, n in bars):
                    lines.append(f"  {name}: " + " · ".join(f"{label} {n}" for label, n in bars if n))
            if lines or full or rest:
                out += [f"{p} tg {v}: fullscreen {full}/{full + rest}", *lines]
    return "\n".join(out) or "—"


# ---- the weekly digest (`admin stats-week`): the last 7 whole days against the 7 before ----
FLOW_MARK = {"signup": "🎟", "paid": "💳", "post": "✍️", "edit": "✏️", "join": "🤝", "android": "🤖", "appeal": "📮"}
TAPS = tuple(dict.fromkeys((*SCREENS, *ACTIONS, *SOURCES, *HERO, *FLOW_KEYS, *STREAK)))  # compared week on week (no samples)
MOVED_FLOOR = 10  # a key under this in both weeks is noise, not a change


def _sums(con, lo: int, hi: int) -> dict:
    return {r[0]: r[1] for r in rows(con, "SELECT key, SUM(n) FROM usage_days WHERE day >= ? AND day < ? GROUP BY key", lo, hi)}


def _vs(a: int, b: int) -> str:
    return "=" if a == b else "new" if not b else f"{'+' if a > b else '−'}{round(abs(a - b) * 100 / b)}%"


def _rates(got: dict, steps: tuple) -> list:
    """Each step's share of the step before it (None: nobody reached the one before)."""
    return [got.get(b, 0) / got[a] if got.get(a) else None for a, b in zip(steps, steps[1:])]


def week(con, upto: int | None = None) -> str:
    """Short, emoji-led lines for the owner: what moved most, each funnel's biggest drop, the slowest screens, the
    errors, and how much the newest features are used. `upto`: the day after the week (default today, so whole days)."""
    upto = _today() if upto is None else upto
    now, was = _sums(con, upto - 7, upto), _sums(con, upto - 14, upto - 7)
    date = lambda d: time.strftime("%d %b", time.gmtime(d * 86400))  # noqa: E731  (an Almaty day number's date)
    active, before = _active(con, upto - 7, upto), _active(con, upto - 14, upto - 7)
    out = [f"📊 {date(upto - 7)} – {date(upto - 1)}: {active} active ({_vs(active, before)})"]

    moved = [k for k in TAPS if max(now.get(k, 0), was.get(k, 0)) >= MOVED_FLOOR]
    moved.sort(key=lambda k: -abs(math.log((now.get(k, 0) + 5) / (was.get(k, 0) + 5))))
    out.append("📈 Moved most")
    out += [f"  {'▲' if now.get(k, 0) >= was.get(k, 0) else '▼'} {k} {now.get(k, 0)} ({_vs(now.get(k, 0), was.get(k, 0))})" for k in moved[:6]] or ["  —"]

    out.append("🪜 Funnels (step's share of the one before; 🔻 the biggest drop, pts vs the week before)")
    short = lambda k: k.split(".", 1)[1]  # noqa: E731
    for name, (steps, ends) in FUNNELS.items():
        if not any(now.get(k) for k in steps):
            out.append(f"  {FLOW_MARK[name]} {name}: —")
            continue
        rate, old = _rates(now, steps), _rates(was, steps)
        chain = f"{short(steps[0])} {now.get(steps[0], 0)}" + "".join(
            f" → {short(s)} {now.get(s, 0)}" + (f" ({round(100 * r)}%)" if r is not None else "") for s, r in zip(steps[1:], rate))
        tail = "".join(f" · {short(k)} {now[k]}" for k in ends if now.get(k))
        seen = [(r, i) for i, r in enumerate(rate) if r is not None]
        if seen:
            r, i = min(seen)
            pts = f", {'+' if r >= old[i] else '−'}{round(abs(r - old[i]) * 100)} pts" if old[i] is not None else ""
            tail += f" · 🔻{short(steps[i])}→{short(steps[i + 1])} {round(100 * r)}%{pts}"
        out.append(f"  {FLOW_MARK[name]} {name}: {chain}{tail}")
    out.append("  🔥 streak: " + " · ".join(f"{short(k)} {now.get(k, 0)}" for k in STREAK))

    slow = []
    for s in SCREENS:
        for p in PLATFORMS:
            bars = [now.get(f"tti.{s}.{p}.{b}", 0) for b in range(len(TTI))]
            if sum(bars) >= 5:  # fewer samples say nothing
                old = [was.get(f"tti.{s}.{p}.{b}", 0) for b in range(len(TTI))]
                p75 = _percentile(bars, .75, TTI)
                slow.append((-TTI.index(p75), -sum(bars), s, p, p75, _percentile(old, .75, TTI) if sum(old) >= 5 else None))
    out.append("🐢 Slowest (p75, tap → first frame)")
    out += [f"  {s} {p} {p75} ({-n}{f', was {o}' if o and o != p75 else ''})" for _, n, s, p, p75, o in sorted(slow)[:6]] or ["  —"]

    errs = sorted((k for k in now if k.startswith(("js.", "api.", "err."))), key=lambda k: -now[k])
    out.append("💥 Errors (js: a crash, api: a failed call, err: the error toast)")
    out += [f"  {k} {now[k]} ({_vs(now[k], was.get(k, 0))})" for k in errs[:6]] or ["  —"]

    out.append("🆕 Since Nov 20: " + " · ".join(f"{k[3:]} {now.get(k, 0)}" for k in sorted(NEW_ACTIONS, key=lambda k: -now.get(k, 0))))
    return "\n".join(out)
