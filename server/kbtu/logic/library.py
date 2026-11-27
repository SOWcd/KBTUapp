"""Library seats (LIBRARY, owner Nov 27; the privacy policy's section 16). A QR sticker per table: a bare code only the
app's scanner takes (useless as a link). No booking: a student finds a free seat, scans the table, taps the seat and has
it for HOLD; scanning again and tapping it extends it. Someone who sees things on a seat but nobody there taps "nobody
here": the holder gets the bot's template and CONFIRM to answer (a rescan, or "I'm here" in the app); no answer frees
the seat. One answer per report, never a second round: after it the reporter, still at the table (its code again), may
say "still not here", which frees the seat at once. The holder back on that seat within FALSE_FOR marks that report
false; STRIKES false ones in a week and that person can't report until the oldest is a week old.
Nobody ever sees who sits where: a seat is free, taken or reported (and mine). What happens to the things on a seat is
not the app's business. Sits and reports go after KEEP, and with the account."""
from __future__ import annotations

import base64
import binascii
import io
import secrets

from ..db import tx
from . import core  # core.now: the tests' clock
from .core import ApiError, Viewer, need_current_student, need_student, one, rows

CONSENT = "lib1"            # the feature's own consent (the policy's section 16), asked on the first seat or report
HOLD = 3 * 3600             # a seat is held this long after the scan (owner, Nov 12: three hours, then rescan)
SOON = 600                  # the bot's "your seat frees in 10 minutes" goes this long before the end
CONFIRM = 600               # the holder's time to answer a report
STILL_FOR = 900             # after the holder's answer, the reporter may say "still not here" this long
FALSE_FOR = 900             # the holder back on the seat this soon after "still not here": that report was false
STRIKES, WEEK = 3, 7 * 86400  # this many false reports in a week: no reporting until the oldest is a week old
A_DAY = 10                  # reports a person files a day
AGAIN = 3600                # a sit reported once can be reported again only this long after
KEEP = 7 * 86400            # sits and reports are kept a week (the policy's section 16)
GONE_KEEP = 30 * 86400      # a removed room or table can be brought back this long
PREFIX = "KBTU-LIB-"        # the sticker's code: this, then 16 of base32's letters (QR's alphanumeric mode: a small code)
MAX_SEATS, MAX_TABLES = 12, 300
MODE = ""                   # LIBRARY as app.create set it: the bot's messages go only while it is on

# a sit is live while it hasn't ended, its time hasn't run out and no report on it went unanswered past CONFIRM
# (the two run-outs are settled into ended_at by the next write, _settle; reads never wait for one)
_OPEN = "r.answered_at IS NULL AND r.still_at IS NULL"
LIVE = f"""s.ended_at IS NULL AND s.until > ? AND NOT EXISTS (SELECT 1 FROM lib_reports r WHERE r.sit_id = s.id
    AND {_OPEN} AND r.created_at + {CONFIRM} <= ?)"""


def on(mode: str, v: Viewer) -> bool:
    """LIBRARY=1: everyone; staff: the app's admins and moderators (to try it, the pitch's demo)."""
    return mode == "all" or mode == "staff" and v.role in ("admin", "moderator")


def summary(con, v: Viewer) -> dict:
    """/api/me's part: agreed to the section yet."""
    return {"consent": _agreed(con, v.id)}


def _agreed(con, uid: int) -> bool:
    return one(con, "SELECT 1 FROM lib_consents WHERE user_id = ? AND version = ?", uid, CONSENT) is not None


def _agree(con, v: Viewer, body: dict) -> None:
    """Inside a write: the consent sent with this first action is recorded with it; without either, no action."""
    if body.get("consent") == CONSENT:
        con.execute("INSERT OR REPLACE INTO lib_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT, core.now()))
    elif not _agreed(con, v.id):
        raise ApiError("forbidden", "lib_consent")  # never "consent": the app reads that as the policy's own gate


def withdraw(con, v: Viewer) -> None:
    """The consent taken back: my seat freed, my sits and reports gone; false reports of mine stay their week (a strike
    must not wash off by withdrawing and agreeing again: the policy's "kept for protection")."""
    with tx(con):
        con.execute("DELETE FROM lib_consents WHERE user_id = ?", (v.id,))
        con.execute("DELETE FROM lib_reports WHERE reporter_id = ? AND (false_at IS NULL OR false_at < ?)", (v.id, core.now() - WEEK))
        con.execute("DELETE FROM lib_sits WHERE user_id = ?", (v.id,))


def _settle(con, t: int) -> None:
    """Inside a write, first: sits whose report went unanswered or whose time ran out end at that moment."""
    con.execute(f"""UPDATE lib_sits SET why = 'report', ended_at = (SELECT MIN(r.created_at) + {CONFIRM} FROM lib_reports r
        WHERE r.sit_id = lib_sits.id AND {_OPEN}) WHERE ended_at IS NULL AND EXISTS (SELECT 1 FROM lib_reports r
        WHERE r.sit_id = lib_sits.id AND {_OPEN} AND r.created_at + {CONFIRM} <= ? AND r.created_at + {CONFIRM} < lib_sits.until)""", (t,))
    con.execute("UPDATE lib_sits SET ended_at = until, why = 'time' WHERE ended_at IS NULL AND until <= ?", (t,))


def _code(body: dict) -> str:
    c = body.get("code")
    if not isinstance(c, str) or not c.strip().upper().startswith(PREFIX) or len(c.strip()) > 40:
        raise ApiError("not_found", "table")  # someone else's QR, a link, a typo: not a table of ours
    return c.strip().upper()


def _table(con, code: str):
    t = one(con, """SELECT t.*, r.name AS room FROM lib_tables t JOIN lib_rooms r ON r.id = t.room_id
        WHERE t.code = ? AND t.gone_at IS NULL AND r.gone_at IS NULL""", code)
    if not t:
        raise ApiError("not_found", "table")
    return t


def _seat(body: dict, t) -> int:
    s = body.get("seat")
    if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= t["seats"]:
        raise ApiError("bad_input")
    return s


def _live_at(con, table_id: int, seat: int, t: int):
    return one(con, f"SELECT s.* FROM lib_sits s WHERE s.table_id = ? AND s.seat = ? AND {LIVE}", table_id, seat, t, t)


def _states(con, t: int, table_ids: list[int], uid: int = 0) -> dict[tuple[int, int], str]:
    """(table, seat) -> taken | reported | mine | asked (my own report waits on it), for every live sit at once."""
    if not table_ids:
        return {}
    got = rows(con, f"""SELECT s.table_id, s.seat, s.user_id,
            EXISTS (SELECT 1 FROM lib_reports r WHERE r.sit_id = s.id AND {_OPEN}) AS open,
            EXISTS (SELECT 1 FROM lib_reports r WHERE r.sit_id = s.id AND r.reporter_id = ? AND r.still_at IS NULL) AS asked
        FROM lib_sits s WHERE s.table_id IN ({",".join("?" * len(table_ids))}) AND {LIVE}""", uid, *table_ids, t, t)
    return {(r["table_id"], r["seat"]): "mine" if uid and r["user_id"] == uid else "asked" if uid and r["asked"]
            else "reported" if r["open"] else "taken" for r in got}


def _seats(states: dict, tab) -> list[str]:
    return [states.get((tab["id"], n), "free") for n in range(1, tab["seats"] + 1)]


def _rooms(con, t: int, uid: int = 0, codes: bool = False) -> list[dict]:
    """Every room with its tables and their seats' states, in two reads for all of them."""
    rooms = rows(con, "SELECT * FROM lib_rooms WHERE gone_at IS NULL ORDER BY id")
    tables = rows(con, "SELECT * FROM lib_tables WHERE gone_at IS NULL AND room_id IN (SELECT id FROM lib_rooms WHERE gone_at IS NULL) ORDER BY id")
    states = _states(con, t, [x["id"] for x in tables], uid)
    out = []
    for r in rooms:
        mine = [{"id": x["id"], "label": x["label"], "seats": _seats(states, x), **({"code": x["code"]} if codes else {})}
                for x in tables if x["room_id"] == r["id"]]
        out.append({"id": r["id"], "name": r["name"], "tables": mine, **({"screen": r["screen"]} if codes else {}),
                    "free": sum(s.count("free") for s in (x["seats"] for x in mine)), "total": sum(len(x["seats"]) for x in mine)})
    return out


def _mine(con, v: Viewer, t: int) -> dict | None:
    s = one(con, f"""SELECT s.*, tb.label, tb.room_id, rm.name AS room FROM lib_sits s JOIN lib_tables tb ON tb.id = s.table_id
        JOIN lib_rooms rm ON rm.id = tb.room_id WHERE s.user_id = ? AND {LIVE}""", v.id, t, t)
    if not s:
        return None
    r = one(con, f"SELECT r.created_at FROM lib_reports r WHERE r.sit_id = ? AND {_OPEN}", s["id"])
    return {"table": s["label"], "room": s["room"], "seat": s["seat"], "since": s["started_at"], "until": s["until"],
            "asked": r["created_at"] + CONFIRM if r else None}  # a report waits on my answer until then


def _my_report(con, v: Viewer, t: int) -> dict | None:
    """My latest report while it still says something: waiting for the holder (until), the holder answered (still not
    here? until), or the seat freed (by no answer or by my "still not here": scan to sit)."""
    r = one(con, """SELECT r.*, s.seat, s.ended_at, s.why, s.until, s.table_id, tb.label FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id
        JOIN lib_tables tb ON tb.id = s.table_id WHERE r.reporter_id = ? AND r.created_at > ? ORDER BY r.id DESC LIMIT 1""",
             v.id, t - CONFIRM - STILL_FOR - FALSE_FOR)
    if not r or r["false_at"]:
        return None
    base = {"id": r["id"], "table": r["label"], "tableId": r["table_id"], "seat": r["seat"]}
    deadline = r["created_at"] + CONFIRM
    if r["still_at"]:
        return {**base, "state": "freed"} if t < r["still_at"] + FALSE_FOR else None
    live = r["ended_at"] is None and r["until"] > t
    if r["answered_at"]:
        return {**base, "state": "here", "until": r["answered_at"] + STILL_FOR} if live and t < r["answered_at"] + STILL_FOR else None
    if live and deadline > t:
        return {**base, "state": "wait", "until": deadline}
    # no answer in time, or the holder left first: the seat is free now (scan to sit)
    ended = r["ended_at"] or min(deadline, r["until"])
    return {**base, "state": "freed"} if r["why"] != "gone" and t < ended + FALSE_FOR else None


def _strikes(con, uid: int, t: int) -> int | None:
    """When I may report again, or None: STRIKES false reports in the last week."""
    got = rows(con, "SELECT false_at FROM lib_reports WHERE reporter_id = ? AND false_at > ? ORDER BY false_at DESC", uid, t - WEEK)
    return got[STRIKES - 1]["false_at"] + WEEK if len(got) >= STRIKES else None


def state(con, v: Viewer) -> dict:
    """The library sheet: the rooms' free seats, my seat, my report, and whether I may report."""
    need_student(v)
    t = core.now()
    with tx(con, write=False):
        rooms = _rooms(con, t)
        return {"consent": _agreed(con, v.id), "hold": HOLD, "confirm": CONFIRM,
                "rooms": [{"id": r["id"], "name": r["name"], "free": r["free"], "total": r["total"]} for r in rooms],
                "mine": _mine(con, v, t), "report": _my_report(con, v, t), "blockedUntil": _strikes(con, v.id, t)}


def _view(con, v: Viewer, tab, t: int) -> dict:
    return {"id": tab["id"], "label": tab["label"], "room": tab["room"], "seats": _seats(_states(con, t, [tab["id"]], v.id), tab)}


def table(con, v: Viewer, body: dict) -> dict:
    """A scanned sticker: its table's seats (no names; mine and the one I reported marked as such)."""
    need_student(v)
    code, t = _code(body), core.now()
    with tx(con, write=False):
        return _view(con, v, _table(con, code), t)


def _answer(con, sit_id: int, t: int) -> None:
    con.execute(f"UPDATE lib_reports SET answered_at = ? WHERE sit_id = ? AND {_OPEN.replace('r.', '')}", (t, sit_id))


def _soon(con, uid: int, sit_id: int, until: int) -> None:
    from .seats import notify
    notify(con, uid, "lib_soon", f"ls:{sit_id}:{until}", after=until - SOON)  # an extend leaves this one stale (render)


def sit(con, v: Viewer, body: dict) -> dict:
    """A tap on a seat at the table just scanned: a free one is mine for HOLD (any other seat of mine freed); mine again
    extends it and answers a report on it; another's is taken, except mine back from the very person whose "still not
    here" freed it a moment ago (that report false)."""
    need_student(v)
    code, t = _code(body), core.now()
    with tx(con):
        need_current_student(con, v)
        _agree(con, v, body)
        _settle(con, t)
        tab = _table(con, code)
        seat = _seat(body, tab)
        cur = _live_at(con, tab["id"], seat, t)
        if cur and cur["user_id"] == v.id:
            con.execute("UPDATE lib_sits SET until = ? WHERE id = ?", (t + HOLD, cur["id"]))
            _answer(con, cur["id"], t)
            _soon(con, v.id, cur["id"], t + HOLD)
            return {"table": _view(con, v, tab, t), "state": state(con, v)}
        # my seat freed by a "still not here" a moment ago: I'm here after all, so that report was false
        back = one(con, """SELECT r.id, r.reporter_id FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id
            WHERE s.table_id = ? AND s.seat = ? AND s.user_id = ? AND r.still_at > ? AND r.false_at IS NULL
            ORDER BY r.id DESC LIMIT 1""", tab["id"], seat, v.id, t - FALSE_FOR)
        if cur:
            if not back or cur["user_id"] != back["reporter_id"]:
                raise ApiError("conflict", "taken")
            con.execute("UPDATE lib_sits SET ended_at = ?, why = 'back' WHERE id = ?", (t, cur["id"]))
        if back:
            con.execute("UPDATE lib_reports SET false_at = ? WHERE id = ?", (t, back["id"]))
        con.execute("UPDATE lib_sits SET ended_at = ?, why = 'moved' WHERE user_id = ? AND ended_at IS NULL", (t, v.id))
        sid = con.execute("INSERT INTO lib_sits (table_id, seat, user_id, started_at, until) VALUES (?, ?, ?, ?, ?)",
                          (tab["id"], seat, v.id, t, t + HOLD)).lastrowid
        _soon(con, v.id, sid, t + HOLD)
        return {"table": _view(con, v, tab, t), "state": state(con, v)}


def leave(con, v: Viewer) -> dict:
    need_student(v)
    t = core.now()
    with tx(con):
        _settle(con, t)
        con.execute("UPDATE lib_sits SET ended_at = ?, why = 'left' WHERE user_id = ? AND ended_at IS NULL", (t, v.id))
        return state(con, v)


def here(con, v: Viewer) -> dict:
    """"I'm here" from the app (the bot's button opens it): answers the report on my seat, without the table's code.
    A photo of the sticker would answer as well, so the reporter keeps "still not here"."""
    need_student(v)
    t = core.now()
    with tx(con):
        _settle(con, t)
        s = one(con, f"""SELECT s.id FROM lib_sits s WHERE s.user_id = ? AND {LIVE}
            AND EXISTS (SELECT 1 FROM lib_reports r WHERE r.sit_id = s.id AND {_OPEN})""", v.id, t, t)
        if not s:
            raise ApiError("not_found")
        _answer(con, s["id"], t)
        return state(con, v)


def report(con, v: Viewer, body: dict) -> dict:
    """"Nobody here" on a taken seat at the table just scanned: the holder has CONFIRM to answer, else the seat frees
    (and I hear of it). One waiting report of mine at a time; A_DAY a day; none while my false ones are STRIKES."""
    from .seats import notify
    need_student(v)
    code, t = _code(body), core.now()
    with tx(con):
        need_current_student(con, v)
        _agree(con, v, body)
        _settle(con, t)
        tab = _table(con, code)
        seat = _seat(body, tab)
        cur = _live_at(con, tab["id"], seat, t)
        if not cur:
            raise ApiError("conflict", "free")
        if cur["user_id"] == v.id:
            raise ApiError("bad_input", "mine")
        if (until := _strikes(con, v.id, t)) is not None:
            raise ApiError("forbidden", "strikes", {"until": until})
        if one(con, "SELECT COUNT(*) FROM lib_reports WHERE reporter_id = ? AND created_at > ?", v.id, t - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "reports")
        if one(con, f"SELECT 1 FROM lib_reports r WHERE r.reporter_id = ? AND {_OPEN} AND r.created_at + {CONFIRM} > ?", v.id, t):
            raise ApiError("conflict", "waiting")
        if one(con, "SELECT 1 FROM lib_reports WHERE sit_id = ? AND created_at > ?", cur["id"], t - AGAIN):
            raise ApiError("conflict", "reported")
        rid = con.execute("INSERT INTO lib_reports (sit_id, reporter_id, created_at) VALUES (?, ?, ?)", (cur["id"], v.id, t)).lastrowid
        notify(con, cur["user_id"], "lib_report", f"lr:{rid}")
        notify(con, v.id, "lib_freed", f"lf:{rid}", after=t + CONFIRM)  # quiet if answered meanwhile (render)
        return {"table": _view(con, v, tab, t), "state": state(con, v)}


def still(con, v: Viewer, body: dict) -> dict:
    """"Still not here" after the holder's answer, with the table's code again (I'm at the table): the seat frees at
    once, no second round; the holder hears of it and gets it back with a rescan (and then my report counts as false)."""
    from .seats import notify
    need_student(v)
    code, t = _code(body), core.now()
    rid = body.get("report")
    if not isinstance(rid, int) or isinstance(rid, bool):
        raise ApiError("bad_input")
    with tx(con):
        need_current_student(con, v)
        _settle(con, t)
        tab = _table(con, code)
        r = one(con, f"""SELECT r.*, s.user_id AS holder FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id
            WHERE r.id = ? AND r.reporter_id = ? AND s.table_id = ? AND r.answered_at IS NOT NULL AND r.still_at IS NULL
            AND r.answered_at + {STILL_FOR} > ? AND {LIVE}""", rid, v.id, tab["id"], t, t, t)
        if not r:
            raise ApiError("conflict", "gone")
        con.execute("UPDATE lib_reports SET still_at = ? WHERE id = ?", (t, rid))
        con.execute("UPDATE lib_sits SET ended_at = ?, why = 'still' WHERE id = ?", (t, r["sit_id"]))
        notify(con, r["holder"], "lib_still", f"lst:{rid}")
        return {"table": _view(con, v, tab, t), "state": state(con, v)}


def render(con, m, lang: str):
    """The bot's library templates (outbox._render), each read when it goes and quiet once it no longer holds. Only the
    table's label and the seat's number, never a name."""
    from .. import texts
    kind, ref, uid, t = m["kind"], m["ref"].split(":"), m["user_id"], core.now()
    if not MODE:
        return None
    if kind == "lib_soon":  # ls:<sit>:<until>, to its holder SOON before the end; stale once extended, left or ended
        s = one(con, f"""SELECT s.seat, tb.label FROM lib_sits s JOIN lib_tables tb ON tb.id = s.table_id
            WHERE s.id = ? AND s.user_id = ? AND s.until = ? AND {LIVE}""", int(ref[1]), uid, int(ref[2]), t, t)
    elif kind == "lib_report":  # lr:<report>, to the holder: while it waits for an answer
        s = one(con, f"""SELECT s.seat, tb.label FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id JOIN lib_tables tb ON tb.id = s.table_id
            WHERE r.id = ? AND s.user_id = ? AND {_OPEN} AND r.created_at + {CONFIRM} > ? AND {LIVE}""", int(ref[1]), uid, t, t, t)
    elif kind == "lib_freed":  # lf:<report>, to the reporter at its deadline: only if no answer freed it
        s = one(con, f"""SELECT s.seat, tb.label FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id JOIN lib_tables tb ON tb.id = s.table_id
            WHERE r.id = ? AND r.reporter_id = ? AND {_OPEN} AND r.created_at + {CONFIRM} <= ? AND r.created_at + {CONFIRM} < s.until
            AND (s.ended_at IS NULL OR s.why = 'report') AND tb.gone_at IS NULL""", int(ref[1]), uid, t)
    elif kind == "lib_still":  # lst:<report>, to the holder: freed by "still not here"; quiet once they're back or it's late
        s = one(con, f"""SELECT s.seat, tb.label FROM lib_reports r JOIN lib_sits s ON s.id = r.sit_id JOIN lib_tables tb ON tb.id = s.table_id
            WHERE r.id = ? AND s.user_id = ? AND r.still_at > ? AND r.false_at IS NULL""", int(ref[1]), uid, t - FALSE_FOR)
    else:
        return None
    return (*texts.bot_message(lang, kind, seat=s["seat"], table=s["label"]), "lib") if s else None


def screen(con, key: str) -> dict:
    """The room's big screen (/show?lib=<key>): its tables' seats as free or taken, nothing else (the key is all it needs)."""
    t = core.now()
    with tx(con, write=False):
        r = one(con, "SELECT id FROM lib_rooms WHERE screen = ? AND gone_at IS NULL", key) if isinstance(key, str) and 8 <= len(key) <= 64 else None
        room = next((x for x in _rooms(con, t) if r and x["id"] == r["id"]), None)
        if not room:
            raise ApiError("not_found")
        # reported counts as taken on a wall: a reported seat is someone's until they don't answer
        return {"name": room["name"], "free": room["free"], "total": room["total"],
                "tables": [{"label": x["label"], "seats": ["free" if s == "free" else "taken" for s in x["seats"]]} for x in room["tables"]]}


def sweep(con) -> None:
    """Nightly (daily.stats_day): a week of sits and reports, as the policy says; removed rooms and tables after a month."""
    t = core.now()
    con.execute("DELETE FROM lib_reports WHERE created_at < ?", (t - KEEP,))
    con.execute("DELETE FROM lib_sits WHERE COALESCE(ended_at, until) < ?", (t - KEEP,))
    con.execute("DELETE FROM lib_tables WHERE gone_at < ?", (t - GONE_KEEP,))
    con.execute("DELETE FROM lib_rooms WHERE gone_at < ?", (t - GONE_KEEP,))


# ---- the admin's: rooms, tables, stickers, the live view

def _admin(v: Viewer) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")


def _name(x: object, most: int) -> str:
    s = " ".join(str(x or "").split())
    if not 1 <= len(s) <= most:
        raise ApiError("bad_input")
    return s


def admin_list(con, v: Viewer) -> list[dict]:
    """Every room with its tables, their codes (the stickers), the seats' live states and the big screen's key."""
    _admin(v)
    with tx(con, write=False):
        return _rooms(con, core.now(), codes=True)


def add_room(con, v: Viewer, body: dict) -> list[dict]:
    _admin(v)
    name = _name(body.get("name"), 60)
    with tx(con):
        con.execute("INSERT INTO lib_rooms (name, screen, created_at) VALUES (?, ?, ?)", (name, secrets.token_urlsafe(18), core.now()))
        return admin_list(con, v)


def edit_room(con, v: Viewer, rid: int, body: dict) -> list[dict]:
    """{name} renames; {gone: true} removes it with its tables (live seats freed), {gone: false} brings it back."""
    _admin(v)
    with tx(con):
        if not one(con, "SELECT 1 FROM lib_rooms WHERE id = ?", rid):
            raise ApiError("not_found")
        if "name" in body:
            con.execute("UPDATE lib_rooms SET name = ? WHERE id = ?", (_name(body["name"], 60), rid))
        if body.get("gone") is True:
            t = core.now()
            con.execute("UPDATE lib_rooms SET gone_at = ? WHERE id = ? AND gone_at IS NULL", (t, rid))
            con.execute("UPDATE lib_sits SET ended_at = ?, why = 'gone' WHERE ended_at IS NULL AND table_id IN (SELECT id FROM lib_tables WHERE room_id = ?)", (t, rid))
        elif body.get("gone") is False:
            con.execute("UPDATE lib_rooms SET gone_at = NULL WHERE id = ?", (rid,))
        return admin_list(con, v)


def _new_code(con) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    while True:
        c = PREFIX + "".join(secrets.choice(alphabet) for _ in range(16))  # 80 bits: not guessed, not walked
        if not one(con, "SELECT 1 FROM lib_tables WHERE code = ?", c):
            return c


def add_tables(con, v: Viewer, rid: int, body: dict) -> list[dict]:
    """{seats, n}: n tables of that many seats, numbered on from the room's highest number; {seats, label}: one, named."""
    _admin(v)
    seats, n = body.get("seats"), body.get("n", 1)
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (seats, n)) or not 1 <= seats <= MAX_SEATS or not 1 <= n <= 50:
        raise ApiError("bad_input")
    with tx(con):
        if not one(con, "SELECT 1 FROM lib_rooms WHERE id = ? AND gone_at IS NULL", rid):
            raise ApiError("not_found")
        have = [r["label"] for r in rows(con, "SELECT label FROM lib_tables WHERE room_id = ? AND gone_at IS NULL", rid)]
        if len(have) + n > MAX_TABLES:
            raise ApiError("bad_input", "too_many")
        if body.get("label") is not None and n == 1:
            labels = [_name(body["label"], 12)]
        else:
            top = max((int(x) for x in have if x.isdigit()), default=0)
            labels = [str(top + i) for i in range(1, n + 1)]
        for label in labels:
            con.execute("INSERT INTO lib_tables (room_id, label, seats, code, created_at) VALUES (?, ?, ?, ?, ?)",
                        (rid, label, seats, _new_code(con), core.now()))
        return admin_list(con, v)


def edit_table(con, v: Viewer, tid: int, body: dict) -> list[dict]:
    """{label}, {seats} (fewer: those past the new count are freed), {gone: true|false} removes it or brings it back."""
    _admin(v)
    t = core.now()
    with tx(con):
        if not one(con, "SELECT 1 FROM lib_tables WHERE id = ?", tid):
            raise ApiError("not_found")
        if "label" in body:
            con.execute("UPDATE lib_tables SET label = ? WHERE id = ?", (_name(body["label"], 12), tid))
        if "seats" in body:
            s = body["seats"]
            if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= MAX_SEATS:
                raise ApiError("bad_input")
            con.execute("UPDATE lib_tables SET seats = ? WHERE id = ?", (s, tid))
            con.execute("UPDATE lib_sits SET ended_at = ?, why = 'gone' WHERE table_id = ? AND seat > ? AND ended_at IS NULL", (t, tid, s))
        if body.get("gone") is True:
            con.execute("UPDATE lib_tables SET gone_at = ? WHERE id = ? AND gone_at IS NULL", (t, tid))
            con.execute("UPDATE lib_sits SET ended_at = ?, why = 'gone' WHERE table_id = ? AND ended_at IS NULL", (t, tid))
        elif body.get("gone") is False:
            con.execute("UPDATE lib_tables SET gone_at = NULL WHERE id = ?", (tid,))
        return admin_list(con, v)


PAGE_BYTES, PAGES = 3_000_000, 60
PAGE_PX = (2600, 3700)  # A4 at up to ~300 dpi


def stickers(con, v: Viewer, rid: int, body: object) -> tuple[str, bytes]:
    """The room's sticker sheet as a PDF: the app drew its pages (the QR codes, the labels, the words in the app's
    font) and sends them as JPEG or PNG images; here they're checked and put together. (room name, the PDF)"""
    from PIL import Image
    _admin(v)
    r = one(con, "SELECT name FROM lib_rooms WHERE id = ? AND gone_at IS NULL", rid)
    if not r:
        raise ApiError("not_found")
    pages = body.get("pages") if isinstance(body, dict) else None
    if not isinstance(pages, list) or not 1 <= len(pages) <= PAGES or not all(isinstance(p, str) for p in pages):
        raise ApiError("bad_input")
    images = []
    for p in pages:
        try:
            raw = base64.b64decode(p.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            raise ApiError("bad_input") from None
        if len(raw) > PAGE_BYTES:
            raise ApiError("bad_input", "too_big")
        try:
            im = Image.open(io.BytesIO(raw))
            if im.format not in ("JPEG", "PNG") or im.width > PAGE_PX[0] or im.height > PAGE_PX[1]:
                raise ApiError("bad_input")
            images.append(im.convert("RGB"))
        except (OSError, Image.DecompressionBombError, ValueError):
            raise ApiError("bad_input") from None
    out = io.BytesIO()
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    return r["name"], out.getvalue()
