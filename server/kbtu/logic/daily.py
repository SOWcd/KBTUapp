"""The daily rounds and the admin's numbers."""
from __future__ import annotations

from ..db import tx

from .core import Viewer, _once, one, rows


def saved_day(con) -> None:
    """12:00 (Almaty) daily: whoever saved an event that's tomorrow and isn't going to it hears it once (all such events in
    one message), with the 2-hour reminders' switch: "Save" with a purpose (owner, Oct 11; instead of a like)."""
    local = core.now() + 5 * 3600
    day = local // 86400
    if local % 86400 < 12 * 3600 or not _once(con, "saved_day", str(day)):
        return
    lo, hi = (day + 1) * 86400 - 5 * 3600, (day + 2) * 86400 - 5 * 3600
    for (uid,) in rows(con, """SELECT DISTINCT s.user_id FROM saved_events s JOIN events e ON e.id = s.event_id JOIN users u ON u.id = s.user_id
            WHERE e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ? AND u.n_remind = 1
            AND NOT EXISTS (SELECT 1 FROM registrations r WHERE r.event_id = e.id AND r.user_id = s.user_id AND r.status IN ('going', 'hold', 'waitlist'))""",
                        lo, hi):
        notify(con, uid, "saved_tomorrow", f"sv:{day}")


def tba_day(con) -> None:
    """10:00 (Almaty) daily: whoever made a published event that still has no place hears it 7, 3 and 1 day before and
    on the day; all of theirs in one message (the bot lists them), until the room is typed in."""
    local = core.now() + 5 * 3600
    day = local // 86400
    if local % 86400 < 10 * 3600 or not _once(con, "tba_day", str(day)):
        return
    for e in rows(con, "SELECT created_by, starts_at FROM events WHERE status = 'published' AND place = '' AND created_by IS NOT NULL AND starts_at > ?", core.now()):
        if (e["starts_at"] + 5 * 3600) // 86400 - day in (7, 3, 1, 0):
            notify(con, e["created_by"], "place_tba", f"tba:{day}")


def day_of(ts: int) -> int:
    """The Almaty day number of a moment."""
    return (ts + 5 * 3600) // 86400


def visit(con, uid: int, t: int) -> None:
    """Someone opened the app today (the admin's chart, admin_day); written with seen_at, at most every 10 minutes."""
    con.execute("INSERT OR IGNORE INTO visits (day, user_id) VALUES (?, ?)", (day_of(t), uid))


def stats_day(con) -> None:
    """Just after midnight (Almaty), once: yesterday's row for the admin's chart. seen_at is the last time someone opened
    the app, so seen_at >= yesterday's start counts exactly who opened it since (a few minutes of today included)."""
    local = core.now() + 5 * 3600
    day = local // 86400 - 1
    if local % 86400 >= 3 * 3600 or not _once(con, "stats_day", str(day)):  # later in the day today's visits would count too
        return
    lo, hi = day * 86400 - 5 * 3600, (day + 1) * 86400 - 5 * 3600
    con.execute("INSERT OR REPLACE INTO stats_days (day, active, new, students) VALUES (?, ?, ?, ?)",
                (day, one(con, "SELECT COUNT(*) FROM users WHERE seen_at >= ?", lo)[0],
                 one(con, "SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?", lo, hi)[0],
                 one(con, "SELECT COUNT(*) FROM students WHERE verified_at < ? AND consent_version != 'staff'", hi)[0]))
    con.execute("DELETE FROM visits WHERE day < ?", (day - 30,))  # 30 days, as the privacy policy says
    # the bot's copy of a message older than 30 days loses its words; the row stays, its key keeps it from going twice
    con.execute("UPDATE bot_outbox SET payload = '{}' WHERE send_after < ? AND payload != '{}' AND (sent_at IS NOT NULL OR error IS NOT NULL)",
                (core.now() - 30 * 86400,))  # one still waiting keeps its words
    con.execute("UPDATE audit_log SET data = '{}' WHERE action = 'registry_search' AND at < ? AND data != '{}'", (core.now() - 30 * 86400,))
    con.execute("DELETE FROM bot_outbox WHERE kind = 'id_clash' AND send_after < ?", (core.now() - 30 * 86400,))  # the ref names a student ID
    forum_sweep(con)
    _prune_deletion_log(con)


def admin_stats(con, v: Viewer) -> dict:
    """The admin panel's numbers (PLAN "Admin stats"): online now (opened in the last 10 minutes: seen_at is refreshed
    at most every 10), active in a day / week / month, students (DMP staff aside, §1), new today; the last 30 days from the nightly rows."""
    _admin(v)
    t = core.now()
    since = lambda s: one(con, "SELECT COUNT(*) FROM users WHERE seen_at >= ?", t - s)[0]  # noqa: E731
    today = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    return {"online": since(600), "day": since(86400), "week": since(7 * 86400), "month": since(30 * 86400),
            "users": one(con, "SELECT COUNT(*) FROM users WHERE tg_id > 0")[0], "students": one(con, "SELECT COUNT(*) FROM students WHERE consent_version != 'staff'")[0],
            "newToday": one(con, "SELECT COUNT(*) FROM users WHERE created_at >= ?", today)[0],
            "ai": ai_state(con), "today": one(con, "SELECT COUNT(*) FROM visits WHERE day = ?", day_of(t))[0],
            "days": [{"day": r["day"], "active": r["active"], "new": r["new"], "students": r["students"]}
                     for r in rows(con, "SELECT * FROM stats_days WHERE day >= ? ORDER BY day", (t + 5 * 3600) // 86400 - 30)]}


def admin_day(con, v: Viewer, day: int) -> dict:
    """One day of the chart (owner, Oct 21): how many opened the app and who, the newcomers marked. `people` is None for
    a day before the visits were kept (or past their 30 days): only the nightly count is known."""
    _admin(v)
    lo = day * 86400 - 5 * 3600
    who = rows(con, """SELECT u.id, u.tg_first_name, u.tg_last_name, u.tg_username, u.nick, u.created_at >= ? AS new, s.user_id IS NOT NULL AS student,
        EXISTS (SELECT 1 FROM students p WHERE p.user_id = u.id) AS profile
        FROM visits x JOIN users u ON u.id = x.user_id LEFT JOIN students s ON s.user_id = u.id AND s.manual = 0
        WHERE x.day = ? ORDER BY u.created_at DESC""", lo, day)
    kept = day <= day_of(core.now()) and one(con, "SELECT 1 FROM visits WHERE day <= ? LIMIT 1", day) is not None
    row = one(con, "SELECT active, new FROM stats_days WHERE day = ?", day)
    return {"day": day, "active": len(who) if kept else (row["active"] if row else 0), "new": sum(r["new"] for r in who) if kept else (row["new"] if row else 0),
            "people": [{"id": r["id"], "name": r["nick"] or " ".join(x for x in (r["tg_first_name"], r["tg_last_name"]) if x) or "—",
                        "username": r["tg_username"], "new": bool(r["new"]), "student": bool(r["student"]),
                        "profile": bool(r["profile"])} for r in who] if kept else None}   # no profile (only opened the app): the row opens Telegram


# what the translator works on (ai_next's own conditions): what the AI page counts and its retry resets
_AI_EVENTS = """FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.status = 'published' AND e.visibility = 'public' AND e.meeting = 0
        AND e.hidden_at IS NULL AND o.status = 'active' AND COALESCE(e.ends_at, e.starts_at) > ?"""
_AI_ORGS = "FROM orgs WHERE status = 'active' AND trim(description) != ''"


def admin_ai(con, v: Viewer) -> dict:
    """The AI page in Admin (owner, Oct 21): the translator's state, what it has done and what waits or failed."""
    _admin(v)
    from .. import ai  # the model's name; ai.py doesn't import logic
    ev, og = _AI_EVENTS, _AI_ORGS
    count = lambda sql, *a: one(con, "SELECT COUNT(*) " + sql, *a)[0]  # noqa: E731
    failed = [{"kind": "event", "id": r["id"], "title": r["title"]} for r in rows(con, f"SELECT e.id, e.title {ev} AND e.lang IS NULL AND e.ai_tries >= ?", core.now(), AI_TRIES)] \
        + [{"kind": "org", "id": r["id"], "title": r["name"]} for r in rows(con, f"SELECT id, name {og} AND lang IS NULL AND ai_tries >= ?", AI_TRIES)]
    return {**ai_state(con), "model": ai.MODEL,
            "events": {"done": count(f"{ev} AND e.lang IS NOT NULL", core.now()), "waiting": count(f"{ev} AND e.lang IS NULL AND e.ai_tries < ?", core.now(), AI_TRIES)},
            "clubs": {"done": count(f"{og} AND lang IS NOT NULL"), "waiting": count(f"{og} AND lang IS NULL AND ai_tries < ?", AI_TRIES)},
            "failed": failed}


def ai_retry(con, v: Viewer) -> None:
    """What failed three times gets three more tries."""
    _admin(v)
    with tx(con):
        con.execute(f"UPDATE events SET ai_tries = 0 WHERE lang IS NULL AND ai_tries >= ? AND id IN (SELECT e.id {_AI_EVENTS})", (AI_TRIES, core.now()))
        con.execute(f"UPDATE orgs SET ai_tries = 0 WHERE lang IS NULL AND ai_tries >= ? AND id IN (SELECT id {_AI_ORGS})", (AI_TRIES,))


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import _prune_deletion_log  # noqa: E402
from .appteam import _admin  # noqa: E402
from .forum import forum_sweep  # noqa: E402
from .seats import notify  # noqa: E402
from .translation import AI_TRIES, ai_state  # noqa: E402
