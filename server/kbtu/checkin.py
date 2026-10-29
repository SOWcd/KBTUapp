"""Check-in by a QR on a big screen (owner, Oct 29: the volunteers' meetings were marked by hand in a 220-row sheet).
The organizer opens /screen on a laptop, types the session's PIN and presses Start: a QR rotating every 10 s
(t.me/KBTUappBot?startapp=ci_<session>_<slot>_<sig>). A scan posts at once, signed in or not, and waits as "pending";
it counts once that person is a KBTU student (signed in now or before), until Finish. Tier A: a student before Start,
B: became one during it (a forwarded sign-in link could do that for someone absent: the CSV says which).
The session's expected list (the organizers' sheet, never in the repo) prefills the student ID at sign-up by KBTU mail.
A session is made by `admin checkin new` (the PIN printed once, only its hash kept)."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
import time

from .logic import ApiError, now, one, rows, tx

SLOT = 10           # the QR on the screen changes this often (s)
SCAN_OK = 5 * 60    # a scan is taken this long after its QR was shown: a slow phone on crowded wifi
PIN_TRIES = 20      # wrong PINs a minute, all together: 10^6 PINs stay out of reach
_fails: list[float] = []


def _sig(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()[:16]


def _pin_hash(pin: str) -> str:
    return hashlib.sha256(f"kbtu-screen:{pin}".encode()).hexdigest()


def new(con, title: str, people: list[dict]) -> tuple[int, str]:
    """A session with its expected people; returns (id, PIN)."""
    with tx(con):
        while True:
            pin = f"{secrets.randbelow(10**6):06d}"
            if not one(con, "SELECT 1 FROM qr_sessions WHERE pin_hash = ?", _pin_hash(pin)):
                break
        sid = con.execute("INSERT INTO qr_sessions (title, pin_hash, created_at) VALUES (?, ?, ?)",
                          (title, _pin_hash(pin), now())).lastrowid
        for p in people:
            if p.get("email"):
                con.execute("""INSERT OR IGNORE INTO qr_expected (session_id, email, full_name, student_id, school, course, phone, tg, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (sid, p["email"].strip().lower(), p.get("name") or "", p.get("studentId"),
                     p.get("school"), p.get("course"), p.get("phone"), p.get("tg"), json.dumps(p.get("extra") or {}, ensure_ascii=False)))
    return sid, pin


# ------------------------------------------------------------ the screen (no Telegram: a PIN, then a key per session)

def open_screen(con, key: bytes, pin: str) -> dict:
    t = time.monotonic()
    _fails[:] = [f for f in _fails if f > t - 60]
    if len(_fails) >= PIN_TRIES:
        raise ApiError("rate_limited")
    s = one(con, "SELECT id FROM qr_sessions WHERE pin_hash = ?", _pin_hash(str(pin or "").strip()))
    if not s:
        _fails.append(t)
        raise ApiError("not_found", "pin")
    return {"session": s["id"], "key": _sig(key, f"screen.{s['id']}")}


def _screen(con, key: bytes, sid: int, k: str):
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or not hmac.compare_digest(_sig(key, f"screen.{sid}"), str(k or "")):
        raise ApiError("forbidden", "screen")
    return s


def state(con, key: bytes, sid: int, k: str) -> dict:
    s = _screen(con, key, sid, k)
    running = s["started_at"] is not None and s["ended_at"] is None
    slot = int(time.time()) // SLOT
    c = one(con, """SELECT COUNT(*) FILTER (WHERE done_at IS NOT NULL), COUNT(*) FILTER (WHERE done_at IS NULL)
        FROM qr_marks WHERE session_id = ?""", sid)
    return {"title": s["title"], "started": s["started_at"], "ended": s["ended_at"], "done": c[0], "pending": c[1],
            "expected": one(con, "SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", sid)[0],
            "param": f"ci_{sid}_{slot}_{_sig(key, f'ci.{sid}.{slot}')}" if running else None, "next": SLOT - int(time.time()) % SLOT}


def start(con, key: bytes, sid: int, k: str) -> dict:
    _screen(con, key, sid, k)
    con.execute("UPDATE qr_sessions SET started_at = COALESCE(started_at, ?), ended_at = NULL WHERE id = ?", (now(), sid))
    return state(con, key, sid, k)


def finish(con, key: bytes, sid: int, k: str) -> dict:
    _screen(con, key, sid, k)
    con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (now(), sid))
    return state(con, key, sid, k)


def export(con, key: bytes, sid: int, k: str) -> str:
    """Who came (tier, time), then who of the expected list didn't; a BOM so Excel reads the Cyrillic."""
    s = _screen(con, key, sid, k)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["status", "name", "email", "student_id", "school", "course", "phone", "telegram", "checked_in", "tier"])
    seen = set()
    for r in rows(con, """SELECT m.done_at, st.first_name, st.last_name, st.email, st.student_id, st.school, st.course, st.verified_at,
            u.tg_username, x.full_name, x.phone, x.tg FROM qr_marks m JOIN users u ON u.id = m.user_id
            JOIN students st ON st.user_id = m.user_id LEFT JOIN qr_expected x ON x.session_id = m.session_id AND x.email = lower(st.email)
            WHERE m.session_id = ? AND m.done_at IS NOT NULL ORDER BY m.done_at""", sid):
        seen.add((r["email"] or "").lower())
        w.writerow(["came" if r["full_name"] is not None else "came (not on the list)", r["full_name"] or f"{r['last_name']} {r['first_name']}",
                    r["email"], r["student_id"], r["school"], r["course"], r["phone"], r["tg"] or r["tg_username"],
                    time.strftime("%H:%M:%S", time.gmtime(r["done_at"] + 5 * 3600)), "A" if r["verified_at"] <= s["started_at"] else "B"])
    for x in rows(con, "SELECT * FROM qr_expected WHERE session_id = ? ORDER BY full_name", sid):
        if x["email"] not in seen:
            w.writerow(["absent", x["full_name"], x["email"], x["student_id"], x["school"], x["course"], x["phone"], x["tg"], "", ""])
    return "﻿" + out.getvalue()


# ------------------------------------------------------------ the student's scan

def mark(con, key: bytes, uid: int, student: bool, p: str) -> dict:
    try:
        _, sid, slot, sig = str(p).split("_")
        sid, slot = int(sid), int(slot)
    except ValueError:
        raise ApiError("bad_input", "qr") from None
    if not hmac.compare_digest(_sig(key, f"ci.{sid}.{slot}"), sig):
        raise ApiError("bad_input", "qr")
    # the same scan again after the sign-up (the app repeats it): its age doesn't matter, it was taken in time
    had = one(con, "SELECT 1 FROM qr_marks WHERE session_id = ? AND user_id = ?", sid, uid)
    if not had and not 0 <= time.time() - slot * SLOT <= SCAN_OK + SLOT:
        raise ApiError("bad_input", "qr_old")
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or s["started_at"] is None or s["ended_at"] is not None:
        raise ApiError("closed", "qr")
    t = now()
    con.execute("INSERT OR IGNORE INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, ?)", (sid, uid, t))
    if student:
        con.execute("UPDATE qr_marks SET done_at = ? WHERE session_id = ? AND user_id = ? AND done_at IS NULL", (t, sid, uid))
    return {"title": s["title"], "done": student}


def became_student(con, uid: int) -> None:
    """Just signed up: the scans waiting for it count now (sessions still open)."""
    con.execute("""UPDATE qr_marks SET done_at = ? WHERE user_id = ? AND done_at IS NULL
        AND session_id IN (SELECT id FROM qr_sessions WHERE ended_at IS NULL)""", (now(), uid))


def prefill(con, email: str | None) -> dict | None:
    """The student ID the organizers' list has for this KBTU mail (open sessions only)"""
    if not email:
        return None
    r = one(con, """SELECT x.student_id FROM qr_expected x JOIN qr_sessions s ON s.id = x.session_id
        WHERE x.email = ? AND x.student_id IS NOT NULL AND s.ended_at IS NULL ORDER BY s.id DESC""", email.strip().lower())
    return {"studentId": r[0]} if r else None
