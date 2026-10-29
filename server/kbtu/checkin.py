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
SCAN_OK = 90        # a scan is taken this long after its QR was shown: 5 min let a photo relay too long, 60 s was tight for
                    # a cold Telegram start on crowded wifi (owner, Oct 29)
PIN_TRIES = 200     # wrong PINs a minute, all together (a right one always opens): ~3.5 days to try all 10^6
GRACE = 30 * 60     # after Finish, someone who scanned in time may still finish signing in this long
# ponytail: _fails is per process (one uvicorn worker today); a table in SQLite if it ever runs several
_fails: list[float] = []


def _sig(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()[:16]


def _same(sig: str, given: object) -> bool:
    """compare_digest on bytes: a non-ASCII str would raise TypeError (a 500)"""
    return hmac.compare_digest(sig.encode(), str(given or "").encode())


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
    # the PIN first: junk POSTs can't lock the organizer out, only the guessers
    s = one(con, "SELECT id FROM qr_sessions WHERE pin_hash = ?", _pin_hash(str(pin or "").strip()))
    if not s:
        t = time.monotonic()
        _fails[:] = [f for f in _fails if f > t - 60]
        if len(_fails) >= PIN_TRIES:
            raise ApiError("rate_limited")
        _fails.append(t)
        raise ApiError("not_found", "pin")
    return {"session": s["id"], "key": _sig(key, f"screen.{s['id']}")}


def _screen(con, key: bytes, sid: int, k: str):
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or not _same(_sig(key, f"screen.{sid}"), k):
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
    # once: a finished session stays finished (reopened, its CSV and tiers would mix two meetings)
    con.execute("UPDATE qr_sessions SET started_at = ? WHERE id = ? AND started_at IS NULL", (now(), sid))
    return state(con, key, sid, k)


def finish(con, key: bytes, sid: int, k: str) -> dict:
    _screen(con, key, sid, k)
    con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (now(), sid))
    return state(con, key, sid, k)


def _cell(v) -> str:
    """No formulas in Excel: a cell starting = + - @ or a tab/CR gets a ' (phones "+7 ..." show it; harmless)"""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def export(con, key: bytes, sid: int, k: str) -> str:
    """Who came (tier, time), who scanned but never signed in, then who of the expected list didn't; a BOM so Excel
    reads the Cyrillic. The list is matched by mail, else by student ID (a personal mail on the sheet)."""
    s = _screen(con, key, sid, k)
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
    con.execute("INSERT OR IGNORE INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, ?)", (sid, uid, t))
    if student:
        con.execute("UPDATE qr_marks SET done_at = ? WHERE session_id = ? AND user_id = ? AND done_at IS NULL", (t, sid, uid))
    return {"title": s["title"], "done": student}


def became_student(con, uid: int) -> None:
    """Just signed up: the scans waiting for it count now (sessions open or finished under GRACE ago)."""
    t = now()
    con.execute("""UPDATE qr_marks SET done_at = ? WHERE user_id = ? AND done_at IS NULL
        AND session_id IN (SELECT id FROM qr_sessions WHERE ended_at IS NULL OR ended_at > ?)""", (t, uid, t - GRACE))


def prefill(con, email: str | None) -> dict | None:
    """The student ID the organizers' list has for this KBTU mail (open sessions only)"""
    if not email:
        return None
    r = one(con, """SELECT x.student_id FROM qr_expected x JOIN qr_sessions s ON s.id = x.session_id
        WHERE x.email = ? AND x.student_id IS NOT NULL AND s.ended_at IS NULL ORDER BY s.id DESC""", email.strip().lower())
    return {"studentId": r[0]} if r else None
