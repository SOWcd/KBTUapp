"""Check-in by a QR on a big screen (owner, Oct 29: the volunteers' meetings were marked by hand in a 220-row sheet).
The organizer opens /show on a laptop and pairs it from the app (below); Start in the app: a QR rotating every 10 s
(t.me/KBTUappBot?startapp=ci_<session>_<slot>_<sig>). A scan posts at once, signed in or not, and waits as "pending";
it counts once that person is a KBTU student (signed in now or before), until Finish. Tier A: a student before Start,
B: became one during it (a forwarded sign-in link could do that for someone absent: the CSV says which).
The session's expected list (the organizers' sheet, never in the repo) prefills the student ID at sign-up by KBTU mail.
A session is made by `admin checkin new`, with the club whose organizers run it."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
import time

from . import logic
from .logic import ApiError, Viewer, can, now, one, rows, tx

SLOT = 10           # the QR on the screen changes this often (s)
SCAN_OK = 90        # a scan is taken this long after its QR was shown: 5 min let a photo relay too long, 60 s was tight for
                    # a cold Telegram start on crowded wifi (owner, Oct 29)
GRACE = 30 * 60     # after Finish, someone who scanned in time may still finish signing in this long
PAIR_TTL = 120      # a screen's pairing QR turns this often while nobody has bound it (a photo of it goes stale)
PAIR_MAX = 500      # unpaired screens at once, all together: junk requests can't fill the table
CSV_TTL = 300       # the CSV link the app hands Telegram's download works this long


def _sig(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()[:16]


def _same(sig: str, given: object) -> bool:
    """compare_digest on bytes: a non-ASCII str would raise TypeError (a 500)"""
    return hmac.compare_digest(sig.encode(), str(given or "").encode())


def new(con, title: str, people: list[dict], org_id: int | None = None) -> int:
    """A session with its expected people, run by the club's organizers (none: the admin only)."""
    with tx(con):
        # pin_hash: the PIN went (pairing replaced it); the column is NOT NULL UNIQUE, so a random one
        sid = con.execute("INSERT INTO qr_sessions (title, pin_hash, org_id, created_at) VALUES (?, ?, ?, ?)",
                          (title, secrets.token_hex(32), org_id, now())).lastrowid
        for p in people:
            if p.get("email"):
                con.execute("""INSERT OR IGNORE INTO qr_expected (session_id, email, full_name, student_id, school, course, phone, tg, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (sid, p["email"].strip().lower(), p.get("name") or "", p.get("studentId"),
                     p.get("school"), p.get("course"), p.get("phone"), p.get("tg"), json.dumps(p.get("extra") or {}, ensure_ascii=False)))
    return sid


# ------------------------------------------------------------ the screen, paired from an organizer's phone
# (owner, Oct 29 night: a PIN typed in view of the hall let anyone open the screen elsewhere, press Finish and take the
# CSV with the volunteers' phones). The laptop shows a pairing QR (sh_<code>); only an organizer of a session may bind
# it (anyone else's scan changes nothing, so nobody can lock the organizer out). The screen then only shows: Start,
# Finish, the CSV and "disconnect" live in the app, for any of the session's organizers (a flat phone loses nothing).

def _hash(secret: str) -> str:
    return hashlib.sha256(f"kbtu-screen:{secret}".encode()).hexdigest()


def pair(con) -> dict:
    """A new screen: its pairing code (public, in the QR) and its secret (stays in that browser, only its hash here)."""
    t = now()
    # unpaired ones rotate every PAIR_TTL; a paired one goes a day after its session ended
    con.execute("""DELETE FROM qr_screens WHERE session_id IS NULL AND created_at < ? OR session_id IN
        (SELECT id FROM qr_sessions WHERE ended_at < ?)""", (t - PAIR_TTL, t - 86400))
    if one(con, "SELECT COUNT(*) FROM qr_screens WHERE session_id IS NULL")[0] >= PAIR_MAX:
        raise ApiError("rate_limited")
    code, secret = secrets.token_hex(8), secrets.token_urlsafe(24)
    con.execute("INSERT INTO qr_screens (code, secret, created_at) VALUES (?, ?, ?)", (code, _hash(secret), t))
    return {"code": code, "secret": secret, "ttl": PAIR_TTL}


def screen(con, key: bytes, secret: str) -> dict:
    """What the screen shows: its pairing code until an organizer binds it, then the session (no controls)."""
    r = one(con, "SELECT * FROM qr_screens WHERE secret = ?", _hash(str(secret or "")))
    if not r:
        raise ApiError("forbidden", "screen")
    if r["session_id"] is None:
        return {"code": r["code"], "left": max(0, r["created_at"] + PAIR_TTL - now())}
    return {"code": r["code"], **_state(con, key, one(con, "SELECT * FROM qr_sessions WHERE id = ?", r["session_id"]))}


def _state(con, key: bytes, s) -> dict:
    sid = s["id"]
    running = s["started_at"] is not None and s["ended_at"] is None
    slot = int(time.time()) // SLOT
    c = one(con, """SELECT COUNT(*) FILTER (WHERE done_at IS NOT NULL), COUNT(*) FILTER (WHERE done_at IS NULL)
        FROM qr_marks WHERE session_id = ?""", sid)
    return {"session": sid, "event": s["event_id"], "title": s["title"], "started": s["started_at"], "ended": s["ended_at"], "done": c[0], "pending": c[1],
            "expected": one(con, "SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", sid)[0],
            "param": f"ci_{sid}_{slot}_{_sig(key, f'ci.{sid}.{slot}')}" if running else None, "next": SLOT - int(time.time()) % SLOT}


def _runs(con, v: Viewer, s) -> bool:
    """A session's organizers: the admin, or who runs events in its club (an admin-made session without a club: the admin)."""
    return v.role == "admin" or bool(s["org_id"] and can(con, v, s["org_id"], "events"))


def _mine(con, v: Viewer, sid: int):
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or not _runs(con, v, s):
        raise ApiError("forbidden", "screen")
    return s


def _row(con, key: bytes, s) -> dict:
    return {**_state(con, key, s), "screens": one(con, "SELECT COUNT(*) FROM qr_screens WHERE session_id = ?", s["id"])[0]}


def sessions(con, key: bytes, v: Viewer) -> list[dict]:
    """The sessions I run: open ones and those finished in the last day (for the list), newest first."""
    return [_row(con, key, s) for s in rows(con, "SELECT * FROM qr_sessions WHERE ended_at IS NULL OR ended_at > ? ORDER BY id DESC",
                                              now() - 86400) if _runs(con, v, s)]


def bind(con, key: bytes, v: Viewer, code: str, sid: int | None) -> dict:
    """An organizer's scan of the screen's QR. Unpaired: bound to the session picked (or my only one). Already
    paired: its session's controls, never moved to another session (another club's organizer can't take it)."""
    r = one(con, "SELECT * FROM qr_screens WHERE code = ?", str(code or ""))
    if not r or r["session_id"] is None and r["created_at"] < now() - PAIR_TTL:
        raise ApiError("not_found", "pair")  # rotated away: scan the screen again
    if r["session_id"] is not None:
        return _row(con, key, _mine(con, v, r["session_id"]))
    if sid is None:
        mine = sessions(con, key, v)
        live = [x for x in mine if x["ended"] is None]
        if not mine:
            raise ApiError("forbidden", "screen")
        if len(live) != 1:
            raise ApiError("conflict", "pick")  # none open or several: the app asks which
        sid = live[0]["session"]
    s = _mine(con, v, sid)
    con.execute("UPDATE qr_screens SET session_id = ?, paired_by = ? WHERE code = ? AND session_id IS NULL", (sid, v.id, r["code"]))
    return _row(con, key, s)


def control(con, key: bytes, v: Viewer, sid: int, act: str) -> dict:
    s = _mine(con, v, sid)
    if act == "start":  # once: a finished session stays finished (reopened, its CSV and tiers would mix two meetings)
        con.execute("UPDATE qr_sessions SET started_at = ? WHERE id = ? AND started_at IS NULL", (now(), sid))
    elif act == "finish":
        con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (now(), sid))
    elif act == "unpair":  # every screen of it goes back to its pairing QR
        con.execute("DELETE FROM qr_screens WHERE session_id = ?", (sid,))
    else:
        raise ApiError("not_found")
    return _row(con, key, one(con, "SELECT * FROM qr_sessions WHERE id = ?", s["id"]))


def for_event(con, key: bytes, v: Viewer, eid: int) -> dict:
    """An event's own session (its organizer's "Check-in screen" in the app), made on first use: its title, its club. A
    paid event keeps its tickets at the door, a partner's has no door (Oct 29)."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or not can(con, v, e["org_id"], "events") and v.role != "admin":
        raise ApiError("forbidden", "screen")
    if e["status"] != "published" or e["price"] or e["guest_host"]:
        raise ApiError("closed", "screen")
    with tx(con):
        if not one(con, "SELECT 1 FROM qr_sessions WHERE event_id = ?", eid):
            con.execute("INSERT INTO qr_sessions (title, pin_hash, org_id, event_id, created_at) VALUES (?, ?, ?, ?, ?)",
                        (e["title"], secrets.token_hex(32), e["org_id"], eid, now()))
        return _row(con, key, one(con, "SELECT * FROM qr_sessions WHERE event_id = ?", eid))


def csv_link(con, key: bytes, v: Viewer, sid: int) -> dict:
    """A link Telegram's downloadFile can open without our headers: signed, for CSV_TTL."""
    _mine(con, v, sid)
    e = now() + CSV_TTL
    return {"url": f"/api/screen/{sid}/csv?e={e}&k={_sig(key, f'csv.{sid}.{e}')}", "name": f"checkin-{sid}.csv"}


def _cell(v) -> str:
    """No formulas in Excel: a cell starting = + - @ or a tab/CR gets a ' (phones "+7 ..." show it; harmless)"""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def export(con, key: bytes, sid: int, e: int, k: str) -> str:
    """Who came (tier, time), who scanned but never signed in, then who of the expected list didn't; a BOM so Excel
    reads the Cyrillic. The list is matched by mail, else by student ID (a personal mail on the sheet)."""
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or e < now() or not _same(_sig(key, f"csv.{sid}.{e}"), k):
        raise ApiError("forbidden", "screen")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["status", "name", "email", "student_id", "school", "course", "phone", "telegram", "checked_in", "tier"])
    xs = rows(con, "SELECT * FROM qr_expected WHERE session_id = ? ORDER BY full_name", sid)
    by_mail, by_sid = {x["email"]: x for x in xs}, {x["student_id"]: x for x in xs if x["student_id"]}
    seen = set()
    for r in rows(con, """SELECT m.done_at, m.scanned_at, st.first_name, st.last_name, st.email, st.student_id, st.school, st.course,
            st.verified_at, u.tg_first_name, u.tg_last_name, u.tg_username FROM qr_marks m JOIN users u ON u.id = m.user_id
            LEFT JOIN students st ON st.user_id = m.user_id WHERE m.session_id = ?
            ORDER BY m.done_at IS NULL, COALESCE(m.done_at, m.scanned_at)""", sid):
        x = by_mail.get((r["email"] or "").lower()) or by_sid.get(r["student_id"])
        if x:
            seen.add(x["email"])
        done = r["done_at"] is not None
        name = " ".join(n for n in (r["last_name"], r["first_name"]) if n) or " ".join(n for n in (r["tg_last_name"], r["tg_first_name"]) if n)
        w.writerow(map(_cell, ["scanned, not signed in" if not done else "came" if x else "came (not on the list)",
                    x["full_name"] if x else name, r["email"], r["student_id"], r["school"], r["course"], x and x["phone"],
                    (x and x["tg"]) or r["tg_username"], time.strftime("%H:%M:%S", time.gmtime((r["done_at"] or r["scanned_at"]) + 5 * 3600)),
                    ("A" if r["verified_at"] <= s["started_at"] else "B") if done else ""]))
    for x in xs:
        if x["email"] not in seen:
            w.writerow(map(_cell, ["absent", x["full_name"], x["email"], x["student_id"], x["school"], x["course"], x["phone"], x["tg"], "", ""]))
    return "\ufeff" + out.getvalue()


# ------------------------------------------------------------ the student's scan

def mark(con, key: bytes, uid: int, student: bool, p: str) -> dict:
    try:
        _, sid, slot, sig = str(p).split("_")
        sid, slot = int(sid), int(slot)
    except ValueError:
        raise ApiError("bad_input", "qr") from None
    if not _same(_sig(key, f"ci.{sid}.{slot}"), sig):
        raise ApiError("bad_input", "qr")
    # the same scan again after the sign-up (the app repeats it): its age doesn't matter, it was taken in time
    had = one(con, "SELECT 1 FROM qr_marks WHERE session_id = ? AND user_id = ?", sid, uid)
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    # finished: only someone who scanned before Finish may still complete it, for GRACE (said before "old": a photo
    # scanned after Finish is "closed")
    if not s or s["started_at"] is None or s["ended_at"] is not None and not (had and s["ended_at"] > now() - GRACE):
        raise ApiError("closed", "qr")
    if not had and not 0 <= time.time() - slot * SLOT <= SCAN_OK + SLOT:
        raise ApiError("bad_input", "qr_old")
    t = now()
    with tx(con):
        con.execute("INSERT OR IGNORE INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, ?)", (sid, uid, t))
        if student:
            con.execute("UPDATE qr_marks SET done_at = ? WHERE session_id = ? AND user_id = ? AND done_at IS NULL", (t, sid, uid))
            if s["event_id"]:  # an event's own session: that event's check-in too
                logic.screen_came(con, s["event_id"], uid, t)
    return {"title": s["title"], "done": student}


def became_student(con, uid: int) -> None:
    """Just signed up: the scans waiting for it count now (sessions open or finished under GRACE ago)."""
    t = now()
    with tx(con):
        due = rows(con, """SELECT s.event_id FROM qr_marks m JOIN qr_sessions s ON s.id = m.session_id WHERE m.user_id = ?
            AND m.done_at IS NULL AND (s.ended_at IS NULL OR s.ended_at > ?)""", uid, t - GRACE)
        con.execute("""UPDATE qr_marks SET done_at = ? WHERE user_id = ? AND done_at IS NULL
            AND session_id IN (SELECT id FROM qr_sessions WHERE ended_at IS NULL OR ended_at > ?)""", (t, uid, t - GRACE))
        for r in due:
            if r["event_id"]:
                logic.screen_came(con, r["event_id"], uid, t)


def prefill(con, email: str | None) -> dict | None:
    """The student ID the organizers' list has for this KBTU mail (open sessions only)"""
    if not email:
        return None
    r = one(con, """SELECT x.student_id FROM qr_expected x JOIN qr_sessions s ON s.id = x.session_id
        WHERE x.email = ? AND x.student_id IS NOT NULL AND s.ended_at IS NULL ORDER BY s.id DESC""", email.strip().lower())
    return {"studentId": r[0]} if r else None
