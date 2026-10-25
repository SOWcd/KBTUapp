"""The daily rounds, the weekly memo to DMP, and the admin's numbers."""
from __future__ import annotations

import json
import re

from .. import receipt, texts
from ..db import tx

from .core import ApiError, PERSON, Viewer, _may, _once, _org, _rights_from, can, one, rows, shown_name


MEMO_ASKS = ("room", "guests", "provide", "promo", "gear", "print", "film")


def _memo(body: dict, keep: str | None) -> str | None:
    """The editor's "For the memo" block (what DMP is asked for, texts.memo_asks): absent keeps it, null clears it.
    Free-form inside each request, bounded: plain values, or a short list of them (printing, a promo's days, more times)."""
    if "memo" not in body:
        return keep
    m = body["memo"]
    if m is None or m == {}:
        return None
    plain = lambda x: x is None or isinstance(x, (bool, int)) or isinstance(x, str) and len(x) <= 1500  # noqa: E731
    ok = isinstance(m, dict) and set(m) <= set(MEMO_ASKS) and all(
        isinstance(a, dict) and all(plain(x) or isinstance(x, list) and len(x) <= 31 and all(plain(y) or isinstance(y, dict) and all(plain(z) for z in y.values()) for y in x)
                                    for x in a.values()) for a in m.values())
    out = json.dumps(m, ensure_ascii=False) if ok else ""
    if not ok or len(out) > 8000:
        raise ApiError("bad_input")
    return out


def _next_week(t: int | None = None) -> int:
    """Monday 00:00 (Almaty) of the week the coming Wednesday's memo covers: DMP takes next week's memos on Wednesdays,
    so from Thursday on it's the week after next (1970-01-01 was a Thursday: Monday = 0)."""
    day = ((t or core.now()) + 5 * 3600) // 86400
    return (day + (2 - (day + 3) % 7) % 7 + 5) * 86400 - 5 * 3600


def _room_no(place: str, url: str | None) -> str | None:
    """The room number in a campus place ("Aud. 305", "332b"), as the memo names it; none off campus."""
    m = None if url else re.search(r"(?<!\d)(\d{2,3}[a-z\u0430-\u044f\u0451]?)(?!\d)", place.lower())
    return m[1] if m else None


def _memo_sender(con, v: Viewer, oid: int) -> dict:
    """Who signs the memo: the sender's "First Last" (kk, ru), in Latin for en (passport style; fixed once by hand), the
    position in three languages from the club role (texts.memo_pos), the portal's phone; `memo_sign` keeps the fixes."""
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    m = one(con, "SELECT m.role, m.memo_sign, r.name FROM org_members m LEFT JOIN org_roles r ON r.id = m.role_id WHERE m.org_id = ? AND m.user_id = ?", oid, v.id)
    fixed = json.loads(m["memo_sign"]) if m and m["memo_sign"] else {}
    name = f"{s['first_name']} {s['last_name']}" if s else ""
    lat = " ".join(w.capitalize() for w in "".join(receipt._LAT.get(c, c) for c in name.lower()).split())
    pos = texts.memo_pos(m["role"] if m else "member", m["name"] if m else None)
    return {"name": name, "nameEn": fixed.get("nameEn") or lat, "phone": texts.phone_line(s["phone"]) if s else None,
            **{k: fixed.get(k) or pos[k] for k in ("kk", "ru", "en")}, "fixed": bool(fixed)}


def memo(con, v: Viewer, oid: int, later: bool = False) -> dict:
    """The week's memo for DMP (PLAN stage 2): one memo of next week's events that ask DMP for something (drafts too:
    rooms are booked before the poster), with `later` the later ones too, signed once by the caller; events already
    sent are left out (listed in `sent`). The app opens it in Outlook to youth_policy@kbtu.kz or copies it. `without`: next
    week's events that ask for nothing, to check."""
    _may(con, v, oid, "memo")
    o = _org(con, oid)
    monday = _next_week()
    evs = rows(con, "SELECT * FROM events WHERE org_id = ? AND status IN ('draft', 'published') AND memo_only = 0 AND starts_at >= ? ORDER BY starts_at", oid, monday)
    week = [e for e in evs if e["starts_at"] < monday + 7 * 86400]
    todo = [e for e in evs if e["memo"] and not e["memo_sent_at"]]
    asked = [e for e in todo if later or e["starts_at"] < monday + 7 * 86400]
    me = _memo_sender(con, v, oid)
    sign = texts.memo_sign(o["name"], me, me["name"], me["nameEn"], me["phone"])
    shape = lambda e: {"title": e["title"], "starts_at": e["starts_at"], "ends_at": e["ends_at"], "place": e["place"], "meeting": e["meeting"],  # noqa: E731
                       "room": _room_no(e["place"], e["place_url"]), "off": bool(e["place_url"]), "seats": e["seats"]}
    asks = [(shape(e), json.loads(e["memo"])) for e in asked]
    dmp = [(e, m) for e, m in asks if set(m) - {"print"}]  # an event asking only for printing has nothing for DMP
    text = texts.memo_text(o["name"], dmp, sign)
    prints = [(e, m) for e, m in asks if m.get("print")]
    pr = texts.print_letter(o["name"], prints, me["ru"], me["name"], me["phone"]) if prints else None
    who = lambda uid: (lambda p: shown_name(p) if p else None)(one(con, PERSON + " WHERE u.id = ?", uid)) if uid else None  # noqa: E731
    brief = lambda e: {"id": e["id"], "title": e["title"], "startsAt": e["starts_at"], "draft": e["status"] == "draft"}  # noqa: E731
    return {"to": texts.MEMO_TO, "subject": texts.memo_subject(o["name"], monday), "text": text, "from": monday, "until": monday + 7 * 86400,
            "print": {"to": texts.PRINT_TO, "subject": pr[0], "text": pr[1]} if pr else None, "guests": any("guests" in json.loads(e["memo"]) for e in asked),
            "events": [brief(e) for e in asked], "later": [brief(e) for e in todo if e["starts_at"] >= monday + 7 * 86400],
            "sent": [{**brief(e), "sentAt": e["memo_sent_at"], "sentBy": who(e["memo_sent_by"])} for e in evs if e["memo"] and e["memo_sent_at"]],
            "without": [brief(e) for e in week if not e["memo"]], "canEdit": can(con, v, oid, "events"),
            "opened": {"at": o["memo_opened_at"], "by": who(o["memo_opened_by"])} if o["memo_opened_at"] else None,
            "sign": {k: me[k] for k in ("name", "nameEn", "kk", "ru", "en", "fixed")},
            "signFrom": texts.MEMO2_SIGN["kk"][0]}  # the sheet's items go in before the signature


def memo_item(con, v: Viewer, oid: int, body: dict) -> str:
    """One item of the memo, written from the sheet's small form (a request needs no event): `kind` and its
    fields as the editor's memo block has them, the day and hours, the place. The sheet shows it and puts it in the text."""
    _may(con, v, oid, "memo")
    kind, place = body.get("kind"), " ".join(str(body.get("place") or "").split())[:80]
    try:
        starts, ends = int(body["startsAt"]), int(body["endsAt"]) if body.get("endsAt") else None
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    if kind not in MEMO_ASKS or kind == "print" or (ends is not None and ends <= starts):
        raise ApiError("bad_input")
    memo = json.loads(_memo({"memo": {kind: body.get("fields") or {}}}, None) or "{}")
    e = {"title": "", "starts_at": starts, "ends_at": ends, "place": place, "room": _room_no(place, None), "off": False, "seats": None, "meeting": 0}
    return (texts.memo_asks(e, memo) or [""])[0]


def memo_opened(con, v: Viewer, oid: int) -> None:
    """"Open in Outlook" or "Copy": the sheet shows it to the others, so nobody sends the week twice."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE orgs SET memo_opened_at = ?, memo_opened_by = ? WHERE id = ?", (core.now(), v.id, oid))


def memo_sent(con, v: Viewer, oid: int, ids: object) -> None:
    """"Sent it to DMP?" -> Yes: these events leave the next memos (an edit of their requests brings them back)."""
    _may(con, v, oid, "memo")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids) or len(ids) > 100:
        raise ApiError("bad_input")
    for i in ids:
        con.execute("UPDATE events SET memo_sent_at = ?, memo_sent_by = ? WHERE id = ? AND org_id = ? AND memo IS NOT NULL", (core.now(), v.id, i, oid))


def memo_again(con, v: Viewer, oid: int, eid: int) -> None:
    """"Include again": a sent event goes back into the memo."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE events SET memo_sent_at = NULL, memo_sent_by = NULL WHERE id = ? AND org_id = ?", (eid, oid))


def memo_sign(con, v: Viewer, oid: int, body: dict) -> dict:
    """The sender fixes the Latin name and the three positions once; an empty field goes back to the computed one."""
    _may(con, v, oid, "memo")
    keep = {k: " ".join(str(body.get(k) or "").split()) for k in ("nameEn", "kk", "ru", "en")}
    if any(len(x) > 120 for x in keep.values()):
        raise ApiError("bad_input")
    keep = {k: x for k, x in keep.items() if x}
    con.execute("UPDATE org_members SET memo_sign = ? WHERE org_id = ? AND user_id = ?", (json.dumps(keep, ensure_ascii=False) if keep else None, oid, v.id))
    return memo(con, v, oid)


def memo_week(con) -> None:
    """Wednesday 9:00-18:00 (Almaty), once a week: everyone with the club's "memo" right, where next week has events
    asking DMP for something not sent yet, hears the memo is ready (DMP takes them until 18:00 that day; later there's no
    point). The sheet shows who opened it already."""
    local = core.now() + 5 * 3600
    if (local // 86400 + 3) % 7 != 2 or not 9 * 3600 <= local % 86400 < 18 * 3600:
        return
    monday = _next_week()
    if not _once(con, "memo_week", str(monday)):
        return
    for (oid,) in rows(con, """SELECT DISTINCT org_id FROM events WHERE status IN ('draft', 'published') AND memo IS NOT NULL
            AND memo_sent_at IS NULL AND starts_at >= ? AND starts_at < ?""", monday, monday + 7 * 86400):
        for m in rows(con, "SELECT m.user_id, m.role, t.rights FROM org_members m LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ?", oid):
            if "memo" in _rights_from(m["role"], m["rights"]):
                notify(con, m["user_id"], "memo_ready", f"memo:{oid}:{monday}")


def saved_day(con) -> None:
    """12:00 (Almaty) daily: whoever saved an event that's tomorrow and isn't going to it hears it once (all such events in
    one message), with the 2-hour reminders' switch: "Save" with a purpose (instead of a like)."""
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
    """One day of the chart how many opened the app and who, the newcomers marked. `people` is None for
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
    """The AI page in Admin the translator's state, what it has done and what waits or failed."""
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
from .account import _prune_deletion_log, me  # noqa: E402
from .oversight import _admin  # noqa: E402
from .queues import AI_TRIES, ai_state  # noqa: E402
from .seats import notify  # noqa: E402
