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
import ipaddress
import json
import secrets
import time

from . import logic
from .logic import ApiError, Viewer, can, log_action, now, one, rows, tx
from .texts import _cell

SLOT = 10           # the QR on the screen changes this often (s)
SCAN_OK = 90        # a scan is taken this long after its QR was shown: 5 min let a photo relay too long, 60 s was tight for
                    # a cold Telegram start on crowded wifi (owner, Oct 29)
GRACE = 30 * 60     # after Finish, someone who scanned in time may still finish signing in this long
PAIR_TTL = 120      # a screen's pairing QR turns this often while nobody has bound it (a photo of it goes stale)
PAIR_MAX = 5000     # unpaired screens at once, all together: junk requests can't fill the table
PAIR_PER_IP = 10    # ... and from one address (its hash): one machine can't take them all and lock every screen out
CSV_TTL = 300       # the CSV link the app hands Telegram's download works this long
LEASE = logic.profiles.QR_LEASE  # each poll of a screen showing the QR renews this: nothing showing it, its code stops this soon after
HAND_OK = 45        # how old the helper's QR may be: it gives a whole session's QR, so a forwarded photo dies sooner than SCAN_OK's
HAND_GRACE = 30     # the helper's QR, once its sheet closed: time to read "help run this?" and say yes
SCREEN_SEEN = 60    # a paired screen counts as connected this long after its last poll (a closed tab says nothing: it just stops)
SCREEN_IDLE = 86400 # a paired screen silent this long has lost its pairing
NO_EVENT_LIVE = 86400  # a running session without an event leaves the capsule this long after its Start


def _sig(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()[:16]


def _same(sig: str, given: object) -> bool:
    """compare_digest on bytes: a non-ASCII str would raise TypeError (a 500)"""
    return hmac.compare_digest(sig.encode(), str(given or "").encode("utf-8", "replace"))  # replace: a lone surrogate in JSON


def new(con, title: str, people: list[dict], org_id: int | None = None) -> int:
    """A session with its expected people, run by the club's organizers (none: the admin only)."""
    with tx(con):
        # pin_hash: the PIN went (pairing replaced it); the column is NOT NULL UNIQUE, so a random one
        sid = con.execute("INSERT INTO qr_sessions (title, pin_hash, org_id, created_at) VALUES (?, ?, ?, ?)",
                          (title, secrets.token_hex(32), org_id, now())).lastrowid
        logic.vol.meet(con, sid, org_id)  # the volunteers ledger's club: its roster frozen as this session's expected list
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

# The secret lives in that browser tab alone (Screen.svelte: sessionStorage), so closing the tab ends the pairing: nothing
# holds the secret any more. A reload or a dead network keeps it: nothing here expires a pairing for going quiet under a day.
# ponytail: qr_screens.created_at of a paired row is its last poll, to spare a migration; a column of its own if anything else needs it

def _hash(secret: str) -> str:
    return hashlib.sha256(f"kbtu-screen:{secret}".encode()).hexdigest()


def _where(key: bytes, ip: str) -> str:
    """The address the per-IP limit counts, keyed (a plain hash of an IPv4 is reversed in minutes): an IPv6 by its /64,
    the block one machine gets"""
    if ":" in ip:
        try:
            ip = str(ipaddress.ip_network(ip + "/64", strict=False))
        except ValueError:
            pass
    return hmac.new(key, f"screen-ip {ip}".encode(), hashlib.sha256).hexdigest()[:16]


def pair(con, key: bytes, ip: str = "") -> dict:
    """A new screen: its pairing code (public, in the QR) and its secret (stays in that browser, only its hash here)."""
    where = _where(key, ip)
    t = now()
    # unpaired ones rotate every PAIR_TTL; a paired one goes a day after its session ended or its tab's last poll
    con.execute("""DELETE FROM qr_screens WHERE session_id IS NULL AND created_at < ? OR session_id IS NOT NULL AND created_at < ? OR session_id IN
        (SELECT id FROM qr_sessions WHERE ended_at < ?)""", (t - PAIR_TTL, t - SCREEN_IDLE, t - 86400))
    if one(con, "SELECT COUNT(*) FROM qr_screens WHERE session_id IS NULL")[0] >= PAIR_MAX \
            or one(con, "SELECT COUNT(*) FROM qr_screens WHERE session_id IS NULL AND ip = ?", where)[0] >= PAIR_PER_IP:
        raise ApiError("rate_limited")
    code, secret = secrets.token_hex(8), secrets.token_urlsafe(24)
    con.execute("INSERT INTO qr_screens (code, secret, ip, created_at) VALUES (?, ?, ?, ?)", (code, _hash(secret), where, t))
    return {"code": code, "secret": secret, "ttl": PAIR_TTL}


def screen(con, key: bytes, secret: str) -> dict:
    """What the screen shows: its pairing code until an organizer binds it, then the session (no controls)."""
    r = one(con, "SELECT * FROM qr_screens WHERE secret = ?", _hash(str(secret or "")))
    if not r:
        raise ApiError("forbidden", "screen")
    if r["session_id"] is None:
        return {"code": r["code"], "left": max(0, r["created_at"] + PAIR_TTL - now())}
    t = now()
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", r["session_id"])
    # ponytail: the right is read with the last-poll write, once per 10 s of 2 s polls: a removed organizer's screen lasts up to 10 s more
    due = r["created_at"] < t - 10
    if r["created_at"] < t - SCREEN_IDLE or due and not _paired_by_runs(con, r["paired_by"], s):  # idle first: the write below would revive it
        con.execute("DELETE FROM qr_screens WHERE code = ?", (r["code"],))
        raise ApiError("forbidden", "screen")
    if due:
        con.execute("UPDATE qr_screens SET created_at = ? WHERE code = ?", (t, r["code"]))
    _lease(con, s["id"])
    return {"code": r["code"], **_state(con, key, s)}


def _paired_by_runs(con, uid: int | None, s) -> bool:
    """Who paired the screen may still bind it (bind: _mine), as app.viewer would see them; a deleted account (NULL) can't."""
    u = uid and one(con, """SELECT u.id, u.role, EXISTS (SELECT 1 FROM students WHERE user_id = u.id AND manual = 0) AS student
        FROM users u WHERE u.id = ? AND u.banned_at IS NULL""", uid)
    return bool(u) and _doors(con, Viewer(u["id"], u["role"], bool(u["student"])), s)


def _lease(con, sid: int) -> None:
    con.execute("UPDATE qr_sessions SET lease_until = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (now() + LEASE, sid))


def _state(con, key: bytes | None, s) -> dict:
    sid = s["id"]
    running = s["started_at"] is not None and s["ended_at"] is None
    slot = int(time.time()) // SLOT
    c = one(con, """SELECT COUNT(*) FILTER (WHERE done_at IS NOT NULL), COUNT(*) FILTER (WHERE done_at IS NULL),
        COUNT(*) FILTER (WHERE left_at IS NOT NULL) FROM qr_marks WHERE session_id = ?""", sid)
    return {"session": sid, "event": s["event_id"], "title": s["title"], "started": s["started_at"], "ended": s["ended_at"], "done": c[0], "pending": c[1],
            "phase": s["phase"], "departed": c[2],
            "expected": one(con, "SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", sid)[0],
            "param": f"ci_{sid}_{slot}_{_sig(key, f'ci.{sid}.{slot}')}" if running and key else None, "next": SLOT - int(time.time()) % SLOT}


def _runs(con, v: Viewer, s, cohost: bool = True) -> bool:
    """A session's organizers: the admin, or who runs events in its club (an admin-made session without a club: the admin);
    an event's session, its co-host's event team too, except for the CSV (cohost-review.md 3)."""
    return v.role == "admin" or bool(s["org_id"] and can(con, v, s["org_id"], "events")) \
        or bool(cohost and s["event_id"] and logic.co_runs(con, v, s["event_id"]))


def _doors(con, v: Viewer, s) -> bool:
    """Who works this session's door: its organizers, or whom the volunteers ledger's link handed it to (logic/vol.py
    holds): Start, the QR (a phone or a paired screen), leaving, Finish. The CSV, the helpers and unpairing stay _runs'."""
    return _runs(con, v, s) or logic.vol.holds(con, v, s)


def _guests(con, e, sid: int | None) -> bool:
    """An ordinary public event's door, the one a member may show the QR at: never a team-only one, a meeting, a
    partner's, or the volunteers ledger's club (its scans count hours and misses: its organizers' alone)."""
    return e["visibility"] == "public" and not e["meeting"] and not e["guest_host"] and e["org_id"] != logic.vol.org_id(con) \
        and not (sid and one(con, "SELECT 1 FROM vol_meets WHERE session_id = ?", sid))


def _door(con, v: Viewer, e, sid: int | None, start: bool = False) -> None:
    """An event's session: every member who works its door (the ticket scanner) may also start and show its QR, for a
    guest who can't open a ticket (owner, Nov 10), at an ordinary public event while its door is open; Start from T-30
    only (a President's early opening doesn't move the tier line). Finishing, the CSV and the screens stay the
    organizers'. Raises why not: forbidden (an organizers' session), closed (with when it opens)."""
    if not e or not can(con, v, e["org_id"], "door"):
        raise ApiError("forbidden", "screen")
    if not _guests(con, e, sid):
        raise ApiError("forbidden", "door_staff")
    at = max(logic.door_at(e), e["starts_at"] - logic.DOOR_AUTO) if start else logic.door_at(e)
    if now() < at and e["status"] == "published" and not e["hidden_at"]:
        raise ApiError("closed", "not_open", {"at": at})
    if e["status"] != "published" or e["hidden_at"] or logic.door_shut(e, now()):
        raise ApiError("closed", "closed")


def _mine(con, v: Viewer, sid: int, cohost: bool = True, door: bool = False):
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or not (_runs(con, v, s, cohost) or door and logic.vol.holds(con, v, s)):
        raise ApiError("forbidden", "screen")
    return s


def _row(con, key: bytes | None, s) -> dict:
    c = one(con, "SELECT COUNT(*) FILTER (WHERE created_at > ?), COUNT(*) FILTER (WHERE created_at >= ?) FROM qr_screens WHERE session_id = ?",
            now() - SCREEN_SEEN, now() - SCREEN_IDLE, s["id"])
    # screens: polling now; paired: "disconnect" still has something to cut; vol: the volunteers ledger's session (its door: GET /api/vol/meets/<id>/door)
    return {**_state(con, key, s), "screens": c[0], "paired": c[1], "vol": bool(one(con, "SELECT 1 FROM vol_meets WHERE session_id = ?", s["id"]))}


def sessions(con, key: bytes, v: Viewer) -> list[dict]:
    """The sessions I run: open ones and those finished in the last day (for the list), newest first."""
    run = [o for o, r in logic._rights(con, v).items() if "events" in r]  # my rights read once, not a query per session
    # and the events we co-host (cohosts.py), and a door of the volunteers ledger handed to me (checked row by row: holds)
    mine = "" if v.role == "admin" else f"""AND (org_id IN ({logic._qs(run)}) OR event_id IN (SELECT x.event_id FROM event_cohosts x
        JOIN orgs o ON o.id = x.org_id WHERE x.status = 'accepted' AND o.status = 'active' AND x.org_id IN ({logic._qs(run)}))
        OR id IN (SELECT session_id FROM vol_hands WHERE user_id = ? AND revoked_at IS NULL))"""
    return [_row(con, key, s) for s in rows(con, f"SELECT * FROM qr_sessions WHERE (ended_at IS NULL OR ended_at > ?) {mine} ORDER BY id DESC",
                                              now() - 86400, *([] if v.role == "admin" else [*run * 2, v.id]))
            if v.role == "admin" or s["org_id"] in run or _doors(con, v, s)]


def running(con, v: Viewer) -> dict | None:
    """The check-in the capsule shows (/api/me, read once): the newest running one I run in my clubs, else one I help at.
    Not every club's for the app's admin: that's Admin. Gone when it's finished or its event is over (`until`)."""
    if not v.student:
        return None
    run = [o for o, r in logic._rights(con, v).items() if "events" in r]
    end = f"COALESCE(e.ends_at, e.starts_at + {logic.DOOR_LATE}, s.started_at + {NO_EVENT_LIVE})"
    # my clubs only, never _runs: its admin exception would turn an admin who helps into an organizer (one interface for everyone)
    ran = f"""(s.org_id IN ({logic._qs(run)}) OR s.event_id IN (SELECT x.event_id FROM event_cohosts x JOIN orgs o ON o.id = x.org_id
        WHERE x.status = 'accepted' AND o.status = 'active' AND x.org_id IN ({logic._qs(run)})))"""
    s = one(con, f"""SELECT s.*, {end} AS until, {ran} AS ran FROM qr_sessions s LEFT JOIN events e ON e.id = s.event_id
        WHERE s.started_at IS NOT NULL AND s.ended_at IS NULL AND COALESCE(e.status, '') != 'cancelled' AND {end} > ?
        AND ({ran} OR {logic.crew.QR_HELPING}) ORDER BY ran DESC, s.id DESC LIMIT 1""", *run, *run, now(), *run, *run, v.id, v.id)
    if not s:
        return None
    if s["ran"]:
        return {**_row(con, None, s), "helper": False, "until": s["until"]}
    e = s["event_id"] and one(con, "SELECT * FROM events WHERE id = ?", s["event_id"])
    return {"session": s["id"], "event": s["event_id"], "title": _title_for(con, s, v.id, True)[0], "helper": True,
            "scanner": bool(e) and logic.crew.kind(con, v, e) is not None, "until": s["until"]}


def bind(con, key: bytes, v: Viewer, code: str, sid: int | None) -> dict:
    """An organizer's scan of the screen's QR. Unpaired: bound to the session picked (or my only one). Already
    paired: its session's controls, never moved to another session (another club's organizer can't take it)."""
    r = one(con, "SELECT * FROM qr_screens WHERE code = ?", str(code or ""))
    if not r or r["session_id"] is None and r["created_at"] < now() - PAIR_TTL:
        raise ApiError("not_found", "pair")  # rotated away: scan the screen again
    if r["session_id"] is not None:
        return _row(con, key, _mine(con, v, r["session_id"], door=True))
    if sid is None:
        mine = sessions(con, key, v)
        live = [x for x in mine if x["ended"] is None]
        if not mine:
            raise ApiError("forbidden", "screen")
        if len(live) != 1:
            raise ApiError("conflict", "pick")  # none open or several: the app asks which
        sid = live[0]["session"]
    s = _mine(con, v, sid, door=True)
    if not con.execute("UPDATE qr_screens SET session_id = ?, paired_by = ?, created_at = ? WHERE code = ? AND session_id IS NULL", (sid, v.id, now(), r["code"])).rowcount:
        return bind(con, key, v, code, sid)  # another scan bound it first: the session it really got, if mine (or gone: rotated)
    logic.vol.paired(con, s, v)  # the ledger's club: who paired its screen runs this door
    return _row(con, key, s)


def control(con, key: bytes, v: Viewer, sid: int, act: str) -> dict:
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    door = act in ("start", "show")
    work = act in ("start", "show", "out", "in", "finish")  # the door's work: the volunteers ledger's link hands these over (vol.holds)
    if not (act == "show" and s and logic.crew.qr_helping(con, v, s)):  # a helper only keeps the QR showing (hand, below)
        if not door or not s or _runs(con, v, s) or logic.vol.holds(con, v, s):  # a co-host starts and shows it; finishing and unpairing (for good) stay the host's
            s = _mine(con, v, sid, cohost=door, door=work)
        else:  # a member at the event's door; who showed this code can't check themselves in with it (mark)
            _door(con, v, s["event_id"] and one(con, "SELECT * FROM events WHERE id = ?", s["event_id"]), sid, act == "start")
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"qrshow:{sid}:{v.id}",))
    if act == "start":  # once: a finished session stays finished (reopened, its CSV and tiers would mix two meetings)
        with tx(con):
            if con.execute("UPDATE qr_sessions SET started_at = ?, lease_until = ? WHERE id = ? AND started_at IS NULL", (now(), now() + LEASE, sid)).rowcount:
                logic.vol.started(con, s, v)  # the ledger's club: who started it runs this door
    elif act == "show":  # an organizer's phone showing the QR itself (EventQr.svelte polls this): the same lease as a /show screen's
        _lease(con, sid)
    elif act == "finish":
        with tx(con):
            t = now()
            if con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (t, sid)).rowcount:
                logic.vol.finished(con, s, v.id, t)  # who ran the door: there to the end; every other open shift waits for an answer
            con.execute("DELETE FROM qr_helpers WHERE session_id = ?", (sid,))
    elif act == "unpair":  # every screen of it goes back to its pairing QR
        con.execute("DELETE FROM qr_screens WHERE session_id = ?", (sid,))
    elif act in ("out", "in"):  # the same QR marks leaving now (a running session), or arriving again
        con.execute("UPDATE qr_sessions SET phase = ? WHERE id = ? AND started_at IS NOT NULL AND ended_at IS NULL", (act, sid))
    else:
        raise ApiError("not_found")
    out = _row(con, key, one(con, "SELECT * FROM qr_sessions WHERE id = ?", s["id"]))
    if act == "show":  # who the last counted scan was: the phone at the door sees a guest's own name, not a screenshot of a toast
        m = one(con, "SELECT user_id, done_at FROM qr_marks WHERE session_id = ? AND done_at IS NOT NULL ORDER BY done_at DESC LIMIT 1", sid)
        out["last"] = m and {"name": logic.short_name(one(con, logic.PERSON + " WHERE u.id = ?", m[0])), "at": m[1]}
    return {**out, "title": _title_for(con, s, v.id, True)[0]} if act == "show" and not _runs(con, v, s) else out  # a helper: the title as helper() showed it


def for_event(con, key: bytes, v: Viewer, eid: int) -> dict:
    """An event's own session (its organizer's "Check-in screen" in the app), made on first use: its title, its club. A
    paid event keeps its tickets at the door, a partner's has no door (Oct 29)."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or not can(con, v, e["org_id"], "door") and not logic.co_runs(con, v, eid) and v.role != "admin":
        raise ApiError("forbidden", "screen")
    if e["status"] != "published" or e["guest_host"]:  # a paid one too: a ticket held is checked in by the scan (organizing.screen_came)
        raise ApiError("closed", "screen")
    x = one(con, "SELECT * FROM qr_sessions WHERE event_id = ?", eid)
    if x and logic.vol.holds(con, v, x):  # the volunteers ledger's door, handed to me: its session as it is
        return _row(con, key, x)
    if not (v.role == "admin" or can(con, v, e["org_id"], "events") or logic.co_runs(con, v, eid)):  # not its organizer (_runs): a member at its door
        _door(con, v, e, x and x["id"])
    with tx(con):
        if not one(con, "SELECT 1 FROM qr_sessions WHERE event_id = ?", eid):
            con.execute("INSERT INTO qr_sessions (title, pin_hash, org_id, event_id, created_at) VALUES (?, ?, ?, ?, ?)",
                        (e["title"], secrets.token_hex(32), e["org_id"], eid, now()))
            logic.vol.meet(con, one(con, "SELECT id FROM qr_sessions WHERE event_id = ?", eid)[0], e["org_id"])
        if not (v.role == "admin" or can(con, v, e["org_id"], "events") or logic.co_runs(con, v, eid)):  # the code goes to this member: mark's "own"
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"qrshow:{one(con, 'SELECT id FROM qr_sessions WHERE event_id = ?', eid)[0]}:{v.id}",))
        return _row(con, key, one(con, "SELECT * FROM qr_sessions WHERE event_id = ?", eid))


def handed(con, key: bytes, v: Viewer, token: object) -> dict:
    """The volunteers ledger's hand-over link opened (logic/vol.py take): that session, mine to run."""
    return _row(con, key, one(con, "SELECT * FROM qr_sessions WHERE id = ?", logic.vol.take(con, v, token)))


def grant_all(con, v: Viewer, sid: int, code: object) -> dict:
    """The owner gives a manual award (e.g. "init26") to everyone counted in a session, once each: how many got it and
    the batch that undoes them all at once (logic.undo_batch)."""
    if not logic._owner(con, v):
        raise ApiError("forbidden")
    if code not in logic.GRANTABLE or code in ("bugs", "dmp", *logic.ONE_BY_ONE) or not one(con, "SELECT 1 FROM qr_sessions WHERE id = ?", sid):
        raise ApiError("bad_input")
    n, batch = 0, f"q{sid}_{now()}"
    with tx(con):
        for (uid,) in rows(con, """SELECT m.user_id FROM qr_marks m JOIN students s ON s.user_id = m.user_id WHERE m.session_id = ?
                AND m.done_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM achievement_grants g WHERE g.user_id = m.user_id AND g.code = ?)""", sid, code):
            logic._grant(con, v.id, uid, str(code), batch)
            n += 1
    return {"granted": n, "batch": batch}


def csv_link(con, key: bytes, v: Viewer, sid: int) -> dict:
    """A link Telegram's downloadFile can open without our headers: signed, for CSV_TTL."""
    _mine(con, v, sid, cohost=False)  # names, mails, phones: the host's
    log_action(con, v.id, "checkin_csv", f"qr:{sid}")  # names, mails, phones: who took the list is on record
    e = now() + CSV_TTL
    return {"url": f"/api/screen/{sid}/csv?e={e}&k={_sig(key, f'csv.{sid}.{e}')}", "name": f"checkin-{sid}.csv"}


def export(con, key: bytes, sid: int, e: int, k: str) -> str:
    """Who came (tier, time), who scanned but never signed in, then who of the expected list didn't; a BOM so Excel
    reads the Cyrillic. The list is matched by mail, else by student ID (a personal mail on the sheet)."""
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if not s or e < now() or not _same(_sig(key, f"csv.{sid}.{e}"), k):
        raise ApiError("forbidden", "screen")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["status", "name", "middle_name", "last_name_latin", "first_name_latin", "middle_name_latin", "email", "student_id", "school", "course", "phone", "telegram", "checked_in", "tier", "left", "hours"])
    hm = lambda ts: time.strftime("%H:%M:%S", time.gmtime(ts + 5 * 3600)) if ts else ""  # noqa: E731
    xs = rows(con, "SELECT * FROM qr_expected WHERE session_id = ? ORDER BY full_name", sid)
    by_mail, by_sid = {x["email"]: x for x in xs}, {x["student_id"]: x for x in xs if x["student_id"]}
    seen = set()
    for r in rows(con, """SELECT m.done_at, m.scanned_at, m.left_at, st.first_name, st.last_name, st.middle_name, st.last_lat, st.first_lat, st.middle_lat, st.email, st.student_id, st.school, st.course,
            st.verified_at, u.tg_first_name, u.tg_last_name, u.tg_username FROM qr_marks m JOIN users u ON u.id = m.user_id
            LEFT JOIN students st ON st.user_id = m.user_id WHERE m.session_id = ?
            ORDER BY m.done_at IS NULL, COALESCE(m.done_at, m.scanned_at)""", sid):
        x = by_mail.get((r["email"] or "").lower()) or by_sid.get(r["student_id"])
        if x:
            seen.add(x["email"])
        done = r["done_at"] is not None
        name = " ".join(n for n in (r["last_name"], r["first_name"]) if n) or " ".join(n for n in (r["tg_last_name"], r["tg_first_name"]) if n)
        w.writerow(map(_cell, ["scanned, not signed in" if not done else "came" if x else "came (not on the list)",
                    x["full_name"] if x else name, r["middle_name"], r["last_lat"], r["first_lat"], r["middle_lat"], r["email"], r["student_id"], r["school"], r["course"], x and x["phone"],
                    (x and x["tg"]) or r["tg_username"], time.strftime("%H:%M:%S", time.gmtime((r["done_at"] or r["scanned_at"]) + 5 * 3600)),
                    ("A" if r["verified_at"] <= s["started_at"] else "B") if done and r["verified_at"] is not None else "", hm(r["left_at"]),  # unlinked since: no tier
                    f"{(r['left_at'] - r['done_at']) / 3600:.1f}" if done and r["left_at"] and r["left_at"] > r["done_at"] else ""]))
    for x in xs:
        if x["email"] not in seen:
            w.writerow(map(_cell, ["absent", x["full_name"], "", "", "", "", x["email"], x["student_id"], x["school"], x["course"], x["phone"], x["tg"], "", "", "", ""]))
    return "\ufeff" + out.getvalue()


# ------------------------------------------------------------ helpers, let in by a QR
# (owner, Nov 9, a live event) Whoever fully runs a session shows a rotating QR (hq_<session>_<slot>_<by>_<sig>, signed
# apart from ci_) to someone beside them. That student then shows the session's QR and works the event's scanner as a
# scanner-only door helper (logic/crew.py), until Finish or "remove all"; nothing else of the session is theirs.

def _hands_over(con, v: Viewer, sid: int):
    """Who may let a helper in: the club's President or Vice, as the privacy policy says of door helpers, or the app's admin."""
    s = _mine(con, v, sid, cohost=False)
    if v.role != "admin" and not (s["org_id"] and one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ? AND role IN ('president', 'vice')", s["org_id"], v.id)):
        raise ApiError("forbidden", "screen")
    return s


def hand(con, key: bytes, v: Viewer, sid: int) -> dict:
    """The helper's QR, for the sheet showing it: each poll renews its lease."""
    s = _hands_over(con, v, sid)
    live = s["started_at"] is not None and s["ended_at"] is None
    if live:
        con.execute("UPDATE qr_sessions SET help_until = ? WHERE id = ?", (now() + LEASE, sid))
    slot = int(time.time()) // SLOT
    return {**_row(con, key, s), "param": f"hq_{sid}_{slot}_{v.id}_{_sig(key, f"qh.{sid}.{slot}.{v.id}.{s['help_gen']}")}" if live else None,
            "helpers": one(con, "SELECT COUNT(*) FROM qr_helpers WHERE session_id = ?", sid)[0]}


def hands_off(con, key: bytes, v: Viewer, sid: int) -> dict:
    _hands_over(con, v, sid)
    with tx(con):  # help_gen: every code shown so far stops working too, or the one just removed scans it again
        con.execute("UPDATE qr_sessions SET help_gen = help_gen + 1 WHERE id = ?", (sid,))
        n = con.execute("DELETE FROM qr_helpers WHERE session_id = ?", (sid,)).rowcount
        if n:
            log_action(con, v.id, "checkin_helpers_off", f"qr:{sid}", json.dumps({"n": n}))
    return hand(con, key, v, sid)


def helper(con, key: bytes, v: Viewer, p: str, join: bool) -> dict:
    """A scan of the helper's QR: what it's for (the app asks first), or, with join, I'm in. Scanned again: in already."""
    logic.need_student(v)
    try:
        kind, sid, slot, by, sig = str(p).split("_")
        sid, slot, by = int(sid), int(slot), int(by)
    except ValueError:
        raise ApiError("bad_input", "qr") from None
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    if kind != "hq" or not s or not _same(_sig(key, f"qh.{sid}.{slot}.{by}.{s['help_gen']}"), sig):
        raise ApiError("bad_input", "qr")
    if s["started_at"] is None or s["ended_at"] is not None:
        raise ApiError("closed", "qr")
    if not 0 <= time.time() - slot * SLOT <= HAND_OK + SLOT or (s["help_until"] or 0) + HAND_GRACE < now():
        raise ApiError("bad_input", "qr_old")
    if logic.crew.barred(con, v.id, s):
        raise ApiError("forbidden", "banned")
    runs = _runs(con, v, s)  # an organizer scanning it: theirs already, no row
    if join and not runs:
        with tx(con):
            # re-checked under the lock: a Finish or "remove all" that landed after the checks above wins
            if con.execute("""INSERT OR IGNORE INTO qr_helpers (session_id, user_id, added_by, created_at) SELECT ?, ?, ?, ?
                    WHERE EXISTS (SELECT 1 FROM qr_sessions WHERE id = ? AND ended_at IS NULL AND help_gen = ?)""",
                           (sid, v.id, by, now(), sid, s["help_gen"])).rowcount:
                log_action(con, by, "checkin_helper", f"user:{v.id}", json.dumps({"session": sid}))
    e = s["event_id"] and one(con, "SELECT * FROM events WHERE id = ?", s["event_id"])
    return {"session": sid, "event": s["event_id"], "title": _title_for(con, s, v.id, True)[0], "joined": runs or logic.crew.qr_helping(con, v, s),
            "scanner": bool(e) and logic.crew.kind(con, v, e) is not None}


# ------------------------------------------------------------ the student's scan

def mark(con, key: bytes, v: Viewer, p: str) -> dict:
    uid, student = v.id, v.student
    try:
        _, sid, slot, sig = str(p).split("_")
        sid, slot = int(sid), int(slot)
    except ValueError:
        raise ApiError("bad_input", "qr") from None
    if not _same(_sig(key, f"ci.{sid}.{slot}"), sig):
        raise ApiError("bad_input", "qr")
    had = one(con, "SELECT done_at FROM qr_marks WHERE session_id = ? AND user_id = ?", sid, uid)
    s = one(con, "SELECT * FROM qr_sessions WHERE id = ?", sid)
    # finished: only someone who scanned before Finish may still complete it, for GRACE (said before "old": a photo
    # scanned after Finish is "closed")
    if not s or s["started_at"] is None or s["ended_at"] is not None and not (had and s["ended_at"] > now() - GRACE):
        raise ApiError("closed", "qr")
    out = s["phase"] == "out" and s["ended_at"] is None
    # the same scan again after the sign-up (the app repeats it): its age doesn't matter, it was taken in time. Leaving
    # always looks at it: an old link in Telegram's history must not mark someone gone home as leaving at the end
    fresh = 0 <= time.time() - slot * SLOT <= SCAN_OK + SLOT and (s["lease_until"] is None or s["lease_until"] >= now())
    if (out or not had) and not fresh:
        raise ApiError("bad_input", "qr_old")
    if out and not had and not logic.vol.on_shift(con, s, uid):  # (who runs the ledger's door came by marking others in: their check-out counts)
        # leaving without having come: no mark, or a "leaving" scan alone would count as there (and earn the badge)
        raise ApiError("bad_input", "qr_not_in")
    t = now()
    e = s["event_id"] and one(con, "SELECT * FROM events WHERE id = ?", s["event_id"])
    if e and out and _guests(con, e, sid) and (logic.door_shut(e, t) == "not_open" or logic.door_shut(e, t - GRACE) == "closed"):
        raise ApiError("closed", "qr")  # leaving an event too: within its door's window (GRACE for the crowd leaving at the end)
    if e and not out and _guests(con, e, sid):
        if one(con, "SELECT 1 FROM meta WHERE key = ?", f"qrshow:{sid}:{uid}") and not logic.cohosts.runs(con, v, e):  # as the scanner: who works the door doesn't check themselves in (a plain member who came as a guest does)
            raise ApiError("forbidden", "own")
        r = e["price"] and one(con, "SELECT id, checked_in_at FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", e["id"], uid)
        if r and r["checked_in_at"] and not had:  # this ticket came in already (a screenshot at the scanner): the door must see it
            return {"title": s["title"], "done": False, "left": False, "already": r["checked_in_at"]}
        if r and not r["checked_in_at"] and logic.organizing.flagged(con, r["id"]):  # the scanner shows the flag: that's where it goes
            return {"title": s["title"], "done": False, "left": False, "flagged": True}
    with tx(con):
        con.execute("INSERT OR IGNORE INTO qr_marks (session_id, user_id, scanned_at) VALUES (?, ?, ?)", (sid, uid, t))
        if out:  # leaving: the last time counts (out and back in, out again)
            con.execute("UPDATE qr_marks SET left_at = ? WHERE session_id = ? AND user_id = ?", (t, sid, uid))
        came = student
        if student:
            con.execute("UPDATE qr_marks SET done_at = ? WHERE session_id = ? AND user_id = ? AND done_at IS NULL", (t, sid, uid))
            if s["event_id"] and not out:  # an event's own session: that event's check-in too; "done" only if it counted there
                came = logic.screen_came(con, s["event_id"], uid, t)
                if came and fresh:  # never by that old link repeated on a later day (the "had" pass above)
                    _attendance(con, s, uid, t)
            if came and fresh:  # the volunteers ledger's club: a shift opens or closes, only by a scan that counted, of a QR just shown
                logic.vol.on_scan(con, s, uid, t, out)
    title, event = _title_for(con, s, uid, student)
    # event: the confirmation's cover and the sheet it settles into; again: counted by an earlier scan already
    return {"title": title, "done": came, "left": out, "event": event, "again": bool(came and not out and had and had["done_at"])}


def _title_for(con, s, uid: int, student: bool) -> tuple[str, int | None]:
    """What the scan's confirmation names, and its event: a leaders' meeting keeps its title (and its id) from who isn't
    invited (only the club's name)."""
    e = s["event_id"] and one(con, "SELECT * FROM events WHERE id = ?", s["event_id"])
    if e and e["visibility"] == "leaders" and not logic._visible(con, Viewer(uid, "user", student), e):
        return one(con, "SELECT name FROM orgs WHERE id = ?", e["org_id"])[0], None
    return s["title"], s["event_id"] or None


def _attendance(con, s, uid: int, t: int) -> None:
    """A DMP office event's scan is that day's Attendance award; the batch (one session, one Almaty day) undoes it."""
    e = logic.profiles.DMP_ON and one(con, "SELECT e.created_by FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND o.slug = 'dmp'", s["event_id"])
    if e:
        try:
            logic._grant(con, e[0], uid, "dmp", f"q{s['id']}_{(t + 5 * 3600) // 86400}", log=False)
        except ApiError as x:
            if x.code != "conflict":  # already got one today
                raise


def became_student(con, uid: int) -> None:
    """Just signed up: the scans waiting for it count now (sessions open or finished under GRACE ago)."""
    t = now()
    with tx(con):
        due = rows(con, """SELECT s.id, s.event_id, m.scanned_at FROM qr_marks m JOIN qr_sessions s ON s.id = m.session_id WHERE m.user_id = ?
            AND m.done_at IS NULL AND (s.ended_at IS NULL OR s.ended_at > ?)""", uid, t - GRACE)
        con.execute("""UPDATE qr_marks SET done_at = ? WHERE user_id = ? AND done_at IS NULL
            AND session_id IN (SELECT id FROM qr_sessions WHERE ended_at IS NULL OR ended_at > ?)""", (t, uid, t - GRACE))
        for r in due:
            # judged at the scan's moment: a sign-in may outlast the QR or the door, and an early scan isn't saved by signing in during the event
            if r["event_id"] and logic.screen_came(con, r["event_id"], uid, r["scanned_at"]):
                _attendance(con, r, uid, r["scanned_at"])


def prefill(con, email: str | None, ms: dict | None = None) -> dict | None:
    """The student ID an organizers' list has for this KBTU mail (open sessions only), else the freshmen list's
    (admin prefill-import) when its name is the Microsoft account's (`ms`: account.prefill_mine). Never an ID another
    student holds: a typo in a list would hand it over."""
    if not email:
        return None
    free = "NOT EXISTS (SELECT 1 FROM students t WHERE t.student_id = x.student_id)"
    e = email.strip().lower()
    r = one(con, f"""SELECT x.student_id FROM qr_expected x JOIN qr_sessions s ON s.id = x.session_id
        WHERE x.email = ? AND x.student_id IS NOT NULL AND s.ended_at IS NULL AND {free} ORDER BY s.id DESC""", e)
    if r:
        return {"studentId": r[0]}
    r = one(con, f"SELECT x.* FROM prefill x WHERE x.email = ? AND {free}", e)
    return {"studentId": r["student_id"]} if r and ms and logic.account.prefill_mine(r, ms.get("first"), ms.get("last")) else None
