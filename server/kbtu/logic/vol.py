"""The volunteers ledger of one club (VOLUNTEERS=<slug>; Zhyly Zhurek first, owner Nov 9-10): its spreadsheet as an app.

A volunteer is a record of the club, apart from any account (people never in the app are on it too); the President
links one to an account and back. Hours: real check-in and check-out at the club's sessions (checkin.mark), never a teambuilding's, or shifts
the President enters; a check-in never checked out counts 0 minutes, the attendance stays. Misses: a session the
President marks as a teambuilding; its expected list (the whole roster) is frozen when the session is made. A miss
counts only once that session really ran: Finished, GRACE after it, and at least max(3, ceil(expected / 4)) of the
expected people marked. Readers: the club's President and whom she grants (club members); each volunteer sees only
their own hours and misses. Only the President edits (her own too), with a reason, every edit in vol_edits (numbers
and times, never a contact). The import's columns are kept as they were (`raw`); the monthly "deposit" columns are
shown raw, nothing is computed from them until the club explains them. Nothing here is deleted by itself."""
from __future__ import annotations

import hashlib
import json
import re

from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, log_action, now, one, person_ref, rows, _qs

# ponytail: v1 shortcuts, each with its upgrade: overlapping shifts aren't refused (check on add/edit if hand edits pile up);
# a teambuilding's "held" is computed live, so a deleted account's mark can un-hold it later (freeze it once GRACE passes);
# grants survive a new President (have her re-confirm them); a scan that waits for a sign-in (checkin.became_student)
# opens no shift (hook it there); a record deleted with its account comes back if a later, different file lists it
# (keep a keyed hash of deleted keys); only the club's own sessions count, not other clubs' events it helps at (the request flow).
ORG = ""                 # the club's slug (config VOLUNTEERS, set by app.create); empty: all of this is off
GRACE = 30 * 60          # as checkin.GRACE: a late sign-in may still complete a scan this long after Finish
REASON_MAX = 200
SHIFT_MAX = 24 * 3600    # one shift by hand: a day at most
MEMBERS, HOURS = "ZhZh \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438", "\u0427\u0430\u0441\u044b 26-27"   # the club's sheets (plan, Nov 6), matched loosely below


def org_id(con) -> int | None:
    r = ORG and one(con, "SELECT id FROM orgs WHERE slug = ?", ORG)
    return r[0] if r else None


def _org(con) -> int:
    o = org_id(con)
    if not o:
        raise ApiError("not_found")
    return o


def _president(con, v: Viewer, org: int) -> bool:
    return v.student and bool(one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ? AND role = 'president'", org, v.id))


def _reader(con, v: Viewer, org: int) -> bool:
    """The President, or a member she granted (leaving the club ends it)."""
    return _president(con, v, org) or v.student and bool(one(con, """SELECT 1 FROM vol_access a JOIN org_members m ON m.org_id = a.org_id
        AND m.user_id = a.user_id WHERE a.org_id = ? AND a.user_id = ?""", org, v.id))


def _need_pres(con, v: Viewer) -> int:
    org = _org(con)
    if not _president(con, v, org):
        raise ApiError("forbidden")
    return org


def _reason(body: dict) -> str:
    r = " ".join(str(body.get("reason") or "").split())
    if not 2 <= len(r) <= REASON_MAX:
        raise ApiError("bad_input", "reason")
    return r


def _person(con, org: int, vid: object):
    p = isinstance(vid, int) and one(con, "SELECT * FROM vol_people WHERE id = ? AND org_id = ?", vid, org)
    if not p:
        raise ApiError("not_found")
    return p


def _edit(con, v: Viewer, vid: int, what: str, ref: int | None, old, new, reason: str) -> None:
    con.execute("INSERT INTO vol_edits (vol_id, what, ref, old, new, reason, by, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vid, what, ref, None if old is None else json.dumps(old), None if new is None else json.dumps(new), reason, v.id, now()))


# ------------------------------------------------------------ the roster and its sessions

def _record(con, org: int, uid: int) -> int | None:
    """My record in the club; a member without one gets an empty one (people who joined in the app after the import)."""
    r = one(con, "SELECT id FROM vol_people WHERE org_id = ? AND user_id = ?", org, uid)
    if r:
        return r[0]
    if not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", org, uid):
        return None
    return con.execute("INSERT INTO vol_people (org_id, user_id, created_at) VALUES (?, ?, ?)", (org, uid, now())).lastrowid


def meet(con, sid: int, org: int | None) -> None:
    """A check-in session just made (checkin.new, checkin.for_event): the club's roster frozen as its expected list."""
    if not org or org != org_id(con):
        return
    with tx(con):
        for (uid,) in rows(con, """SELECT user_id FROM org_members m WHERE org_id = ? AND NOT EXISTS
                (SELECT 1 FROM vol_people p WHERE p.org_id = m.org_id AND p.user_id = m.user_id)""", org):
            _record(con, org, uid)
        con.execute("INSERT OR IGNORE INTO vol_meets (session_id, org_id, created_at) VALUES (?, ?, ?)", (sid, org, now()))
        n = con.execute("INSERT OR IGNORE INTO vol_expected (session_id, vol_id) SELECT ?, id FROM vol_people WHERE org_id = ?", (sid, org)).rowcount
        con.execute("UPDATE vol_meets SET expected_n = ? WHERE session_id = ?", (n, sid))


def on_scan(con, s, uid: int, t: int, out: bool) -> None:
    """A student's check-in scan at the club's session (inside checkin.mark's transaction): arriving opens a shift unless
    one is open; leaving closes the open one, else moves the last one's end (the last leaving counts, as qr_marks.left_at)."""
    org = s["org_id"]
    if not org or org != org_id(con):
        return
    vid = _record(con, org, uid)
    if not vid:
        return  # a guest at the club's public event isn't a volunteer
    last = one(con, "SELECT * FROM vol_shifts WHERE vol_id = ? AND session_id = ? AND gone_at IS NULL ORDER BY in_at DESC, id DESC", vid, s["id"])
    if not out:
        if not last or last["out_at"] is not None:
            con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, in_by) VALUES (?, ?, ?, ?)", (vid, s["id"], t, uid))
    elif last:
        con.execute("UPDATE vol_shifts SET out_at = ?, out_by = ? WHERE id = ?", (t, uid, last["id"]))


# ------------------------------------------------------------ the numbers, each read once for all rows

def _minutes(con, org: int, vid: int | None = None) -> dict[int, tuple[int, int]]:
    """{volunteer: (minutes of closed shifts, open shifts)}; an open shift (never checked out) counts 0. A teambuilding's
    shifts give no hours (owner, Nov 10: hours are for volunteering at events; a teambuilding only counts for misses)."""
    return {r[0]: (r[1] // 60, r[2]) for r in rows(con, f"""SELECT h.vol_id, COALESCE(SUM(CASE WHEN h.out_at > h.in_at THEN h.out_at - h.in_at END), 0),
        COUNT(*) FILTER (WHERE h.out_at IS NULL) FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
        WHERE p.org_id = ? AND h.gone_at IS NULL AND NOT EXISTS (SELECT 1 FROM vol_meets m WHERE m.session_id = h.session_id AND m.team = 1) {'AND h.vol_id = ?' if vid else ''} GROUP BY h.vol_id""", org, *([vid] if vid else []))}


# a teambuilding that really ran: Finished, GRACE ago, at least max(3, ceil(expected / 4)) of its expected people marked
_HELD = """m.team = 1 AND s.ended_at IS NOT NULL AND s.ended_at <= ? AND (SELECT COUNT(DISTINCT y.vol_id) FROM vol_expected y
    JOIN vol_shifts h ON h.vol_id = y.vol_id AND h.session_id = y.session_id AND h.gone_at IS NULL WHERE y.session_id = m.session_id)
    >= MAX(3, (m.expected_n + 3) / 4)"""


def _missed(con, org: int, vid: int | None = None) -> list:
    """(volunteer, session, title, ended) of every miss: expected at a held teambuilding, never marked there."""
    return rows(con, f"""SELECT x.vol_id, s.id, s.title, s.ended_at FROM vol_expected x JOIN vol_meets m ON m.session_id = x.session_id
        JOIN qr_sessions s ON s.id = m.session_id WHERE m.org_id = ? AND {_HELD} {'AND x.vol_id = ?' if vid else ''}
        AND NOT EXISTS (SELECT 1 FROM vol_shifts h WHERE h.vol_id = x.vol_id AND h.session_id = x.session_id AND h.gone_at IS NULL)
        ORDER BY s.ended_at DESC""", org, now() - GRACE, *([vid] if vid else []))


def _misses(con, org: int, vid: int | None = None) -> dict[int, int]:
    n: dict[int, int] = {}
    for r in _missed(con, org, vid):
        n[r[0]] = n.get(r[0], 0) + 1
    for r in rows(con, f"""SELECT x.vol_id, SUM(x.n) FROM vol_misses x JOIN vol_people p ON p.id = x.vol_id WHERE p.org_id = ? AND x.gone_at IS NULL
            {'AND x.vol_id = ?' if vid else ''} GROUP BY x.vol_id""", org, *([vid] if vid else [])):
        n[r[0]] = n.get(r[0], 0) + r[1]
    return {k: max(0, x) for k, x in n.items()}


def _names(con, ps) -> dict[int, dict]:
    ids = [p["user_id"] for p in ps if p["user_id"]]
    return {r["id"]: person_ref(r) for r in rows(con, f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.id IN ({_qs(ids)})", *ids)}


def _row(p, who: dict | None, mins: tuple[int, int], misses: int) -> dict:
    return {"id": p["id"], "name": p["name"] or (who or {}).get("realName") or (who or {}).get("name") or "", "tg": p["tg"], "person": who,
            "minutes": p["balance"] + mins[0], "open": mins[1], "misses": misses}


def summary(con, v: Viewer) -> dict | None:
    """/api/me's part: may I read the ledger, edit it, and my own numbers (when I'm on it)."""
    org = org_id(con)
    if not org or not v.student:
        return None
    me = one(con, "SELECT * FROM vol_people WHERE org_id = ? AND user_id = ?", org, v.id)
    pres = _president(con, v, org)
    ledger = pres or _reader(con, v, org)
    if not me and not ledger:
        return None
    mine = None
    if me:
        mins = _minutes(con, org, me["id"]).get(me["id"], (0, 0))
        mine = {"id": me["id"], "minutes": me["balance"] + mins[0], "open": mins[1], "misses": _misses(con, org, me["id"]).get(me["id"], 0)}
    return {"org": org, "ledger": ledger, "edit": pres, "mine": mine}


def ledger(con, v: Viewer) -> dict:
    org = _org(con)
    if not _reader(con, v, org):
        raise ApiError("forbidden")
    ps = rows(con, "SELECT * FROM vol_people WHERE org_id = ?", org)
    who, mins, miss = _names(con, ps), _minutes(con, org), _misses(con, org)
    people = sorted((_row(p, who.get(p["user_id"]), mins.get(p["id"], (0, 0)), miss.get(p["id"], 0)) for p in ps), key=lambda x: x["name"].lower())
    t = now()
    held = {r[0] for r in rows(con, f"SELECT m.session_id FROM vol_meets m JOIN qr_sessions s ON s.id = m.session_id WHERE m.org_id = ? AND {_HELD}", org, t - GRACE)}
    meets = [{"session": r["session_id"], "title": r["title"], "at": r["started_at"] or r["created_at"], "ended": r["ended_at"], "team": bool(r["team"]),
              "expected": r["expected_n"], "marked": r["marked"], "held": r["session_id"] in held}
             for r in rows(con, """SELECT m.*, s.title, s.started_at, s.ended_at, (SELECT COUNT(DISTINCT h.vol_id) FROM vol_shifts h
                JOIN vol_expected y ON y.vol_id = h.vol_id AND y.session_id = h.session_id WHERE h.session_id = m.session_id AND h.gone_at IS NULL) AS marked
                FROM vol_meets m JOIN qr_sessions s ON s.id = m.session_id WHERE m.org_id = ? ORDER BY m.session_id DESC LIMIT 40""", org)]
    access = []
    if _president(con, v, org):
        access = [person_ref(r) for r in rows(con, f"""SELECT {PERSON_COLS} FROM vol_access a JOIN users u ON u.id = a.user_id
            LEFT JOIN students s ON s.user_id = u.id WHERE a.org_id = ? ORDER BY a.at""", org)]
    return {"edit": _president(con, v, org), "people": people, "meets": meets, "access": access}


def person(con, v: Viewer, vid: int | None) -> dict:
    """One volunteer: shifts, misses; for the readers also the imported columns and the edits. None: my own."""
    org = _org(con)
    reader = _reader(con, v, org)
    if vid is None:
        r = v.student and one(con, "SELECT id FROM vol_people WHERE org_id = ? AND user_id = ?", org, v.id)
        if not r:
            raise ApiError("not_found")
        vid = r[0]
    p = _person(con, org, vid)
    if not reader and not (v.student and p["user_id"] == v.id):
        raise ApiError("forbidden")
    who = _names(con, [p]).get(p["user_id"])
    out = _row(p, who, _minutes(con, org, vid).get(vid, (0, 0)), _misses(con, org, vid).get(vid, 0))
    out["balance"] = p["balance"]
    out["shifts"] = [{"id": h["id"], "session": h["session_id"], "title": h["title"], "inAt": h["in_at"], "outAt": h["out_at"],
                      "byHand": h["in_by"] != p["user_id"] or h["session_id"] is None, "gone": h["gone_at"] is not None}
                     for h in rows(con, """SELECT h.*, s.title FROM vol_shifts h LEFT JOIN qr_sessions s ON s.id = h.session_id
                        WHERE h.vol_id = ? AND (h.gone_at IS NULL OR ?) ORDER BY h.in_at DESC""", vid, reader)]
    out["missed"] = [{"session": r[1], "title": r[2], "at": r[3]} for r in _missed(con, org, vid)]
    out["manual"] = [{"id": r["id"], "n": r["n"], "session": r["session_id"], "at": r["at"]}
                     for r in rows(con, "SELECT * FROM vol_misses WHERE vol_id = ? AND gone_at IS NULL ORDER BY at DESC", vid)]
    if reader:
        out["raw"] = json.loads(p["raw"])
        out["edits"] = [{"what": r["what"], "ref": r["ref"], "old": r["old"] and json.loads(r["old"]), "new": r["new"] and json.loads(r["new"]),
                         "reason": r["reason"], "at": r["at"], "by": r["by"]} for r in rows(con, "SELECT * FROM vol_edits WHERE vol_id = ? ORDER BY id DESC LIMIT 100", vid)]
    return out


# ------------------------------------------------------------ the President's edits (each with a reason, in vol_edits)

def _when(x: object, field: str) -> int:
    if not isinstance(x, int) or isinstance(x, bool) or not 1577836800 <= x <= now() + 600:  # 2020 .. now: never ahead
        raise ApiError("bad_input", field)
    return x


def _span(i: int, o: int | None) -> None:
    if o is not None and not i < o <= i + SHIFT_MAX:
        raise ApiError("bad_input", "out")


def set_balance(con, v: Viewer, vid: int, body: dict) -> dict:
    org = _need_pres(con, v)
    reason, p = _reason(body), _person(con, org, vid)
    b = body.get("minutes")
    if not isinstance(b, int) or isinstance(b, bool) or not 0 <= b <= 100000 * 60:
        raise ApiError("bad_input", "minutes")
    with tx(con):
        con.execute("UPDATE vol_people SET balance = ? WHERE id = ?", (b, vid))
        _edit(con, v, vid, "balance", None, p["balance"], b, reason)
    return person(con, v, vid)


def add_shift(con, v: Viewer, vid: int, body: dict) -> dict:
    """A shift by hand (a camera that didn't work, a mark forgotten): its times as the President gives them."""
    org = _need_pres(con, v)
    reason, _ = _reason(body), _person(con, org, vid)
    i = _when(body.get("inAt"), "in")
    o = None if body.get("outAt") is None else _when(body.get("outAt"), "out")
    _span(i, o)
    sid = body.get("session")
    if sid is not None and not (isinstance(sid, int) and one(con, "SELECT 1 FROM vol_meets WHERE session_id = ? AND org_id = ?", sid, org)):
        raise ApiError("bad_input", "session")
    with tx(con):
        hid = con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at, in_by, out_by) VALUES (?, ?, ?, ?, ?, ?)",
                          (vid, sid, i, o, v.id, v.id if o else None)).lastrowid
        _edit(con, v, vid, "shift_add", hid, None, {"in": i, "out": o, "session": sid}, reason)
    return person(con, v, vid)


def edit_shift(con, v: Viewer, hid: int, body: dict) -> dict:
    """Its times changed, or taken out (gone) and back; the old values stay in vol_edits."""
    org = _need_pres(con, v)
    reason = _reason(body)
    h = one(con, "SELECT h.* FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id WHERE h.id = ? AND p.org_id = ?", hid, org)
    if not h:
        raise ApiError("not_found")
    i = _when(body["inAt"], "in") if "inAt" in body else h["in_at"]
    o = (None if body["outAt"] is None else _when(body["outAt"], "out")) if "outAt" in body else h["out_at"]
    _span(i, o)
    gone = h["gone_at"] if "gone" not in body else (h["gone_at"] or now()) if body["gone"] is True else None
    with tx(con):
        con.execute("UPDATE vol_shifts SET in_at = ?, out_at = ?, gone_at = ?, in_by = CASE WHEN ? THEN ? ELSE in_by END, out_by = CASE WHEN ? THEN ? ELSE out_by END WHERE id = ?",
                    (i, o, gone, i != h["in_at"], v.id, o != h["out_at"], v.id, hid))
        _edit(con, v, h["vol_id"], "shift", hid, {"in": h["in_at"], "out": h["out_at"], "gone": h["gone_at"] is not None},
              {"in": i, "out": o, "gone": gone is not None}, reason)
    return person(con, v, h["vol_id"])


def add_miss(con, v: Viewer, vid: int, body: dict) -> dict:
    """+1 a miss the app didn't see (a meeting without check-in), -1 one excused."""
    org = _need_pres(con, v)
    reason, _ = _reason(body), _person(con, org, vid)
    n, sid = body.get("n"), body.get("session")
    if n not in (1, -1) or isinstance(n, bool) or sid is not None and not (isinstance(sid, int) and one(con, "SELECT 1 FROM vol_meets WHERE session_id = ? AND org_id = ?", sid, org)):
        raise ApiError("bad_input")
    with tx(con):
        mid = con.execute("INSERT INTO vol_misses (vol_id, session_id, n, by, at) VALUES (?, ?, ?, ?, ?)", (vid, sid, n, v.id, now())).lastrowid
        _edit(con, v, vid, "miss", mid, None, {"n": n, "session": sid}, reason)
    return person(con, v, vid)


def drop_miss(con, v: Viewer, mid: int, body: dict) -> dict:
    org = _need_pres(con, v)
    reason = _reason(body)
    m = one(con, "SELECT x.* FROM vol_misses x JOIN vol_people p ON p.id = x.vol_id WHERE x.id = ? AND p.org_id = ? AND x.gone_at IS NULL", mid, org)
    if not m:
        raise ApiError("not_found")
    with tx(con):
        con.execute("UPDATE vol_misses SET gone_at = ? WHERE id = ?", (now(), mid))
        _edit(con, v, m["vol_id"], "miss_gone", mid, {"n": m["n"]}, None, reason)
    return person(con, v, m["vol_id"])


def link(con, v: Viewer, vid: int, body: dict) -> dict:
    """The record to a member's account, or off it (user null). The member's own record, if any (made by a check-in or
    another row of the import), merges into this one: its shifts, misses and columns move here. ponytail: a merge isn't
    split back by unlinking; the edits log keeps what moved."""
    org = _need_pres(con, v)
    p = _person(con, org, vid)
    uid = body.get("user")
    with tx(con):
        if uid is None:
            if p["user_id"]:
                con.execute("UPDATE vol_people SET user_id = NULL WHERE id = ?", (vid,))
                log_action(con, v.id, "vol_unlink", f"user:{p['user_id']}", json.dumps({"vol": vid}))
            return person(con, v, vid)
        if not isinstance(uid, int) or not one(con, """SELECT 1 FROM org_members m JOIN students s ON s.user_id = m.user_id
                WHERE m.org_id = ? AND m.user_id = ?""", org, uid):
            raise ApiError("bad_input", "user")
        if p["user_id"] not in (None, uid):
            raise ApiError("conflict", "linked")
        y = one(con, "SELECT * FROM vol_people WHERE org_id = ? AND user_id = ? AND id != ?", org, uid, vid)
        if y:
            raw = json.loads(p["raw"])
            for k, x in json.loads(y["raw"]).items():
                raw[k if k not in raw else f"{k} ({y['id']})"] = x
            con.execute("UPDATE vol_shifts SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
            con.execute("UPDATE vol_misses SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
            con.execute("UPDATE vol_edits SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
            con.execute("INSERT OR IGNORE INTO vol_expected (session_id, vol_id) SELECT session_id, ? FROM vol_expected WHERE vol_id = ?", (vid, y["id"]))
            con.execute("UPDATE vol_people SET raw = ?, balance = balance + ?, name = CASE WHEN name = '' THEN ? ELSE name END, tg = COALESCE(tg, ?) WHERE id = ?",
                        (json.dumps(raw, ensure_ascii=False), y["balance"], y["name"], y["tg"], vid))
            con.execute("DELETE FROM vol_people WHERE id = ?", (y["id"],))
            _edit(con, v, vid, "merge", y["id"], None, {"balance": y["balance"]}, "")
        con.execute("UPDATE vol_people SET user_id = ? WHERE id = ?", (uid, vid))
        log_action(con, v.id, "vol_link", f"user:{uid}", json.dumps({"vol": vid}))
    return person(con, v, vid)


def set_team(con, v: Viewer, sid: int, body: dict) -> dict:
    """A session of the club is a teambuilding (its frozen list may get misses) or not."""
    org = _need_pres(con, v)
    on = body.get("team")
    if not isinstance(on, bool) or not con.execute("UPDATE vol_meets SET team = ? WHERE session_id = ? AND org_id = ?", (int(on), sid, org)).rowcount:
        raise ApiError("bad_input" if not isinstance(on, bool) else "not_found")
    log_action(con, v.id, "vol_team", f"qr:{sid}", json.dumps({"on": on}))
    return ledger(con, v)


def set_access(con, v: Viewer, body: dict) -> dict:
    """The President lets a member read the ledger, or stops it."""
    org = _need_pres(con, v)
    uid, on = body.get("user"), body.get("on")
    if not isinstance(uid, int) or not isinstance(on, bool) or uid == v.id:
        raise ApiError("bad_input")
    with tx(con):
        if on:
            if not one(con, "SELECT 1 FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ? AND m.user_id = ?", org, uid):
                raise ApiError("bad_input", "user")
            con.execute("INSERT OR IGNORE INTO vol_access (org_id, user_id, granted_by, at) VALUES (?, ?, ?, ?)", (org, uid, v.id, now()))
        else:
            con.execute("DELETE FROM vol_access WHERE org_id = ? AND user_id = ?", (org, uid))
        log_action(con, v.id, "vol_access", f"user:{uid}", json.dumps({"on": on}))
    return ledger(con, v)


# ------------------------------------------------------------ the import (admin vol import), from the club's xlsx

def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w@]+", " ", str(s).lower()).split())


def _tg(s: str) -> str | None:
    t = re.sub(r"^(https?://)?(t\.me/|telegram\.me/)", "", str(s).strip().lower()).lstrip("@")
    return t if re.fullmatch(r"[a-z0-9_]{4,32}", t) else None


def _role(head: str) -> str | None:
    """The header's meaning, tolerant of spelling: name, tg, or None (kept raw only)."""
    words = _norm(head).split()
    if any(w == "\u0444\u0438\u043e" or w.startswith(("name", "\u0438\u043c\u044f")) for w in words):
        return "name"
    if any(w.startswith(("\u0442\u0435\u043b\u0435\u0433\u0440\u0430\u043c", "telegram")) or w in ("\u0442\u0433", "tg", "\u043d\u0438\u043a", "nick", "username") for w in words):
        return "tg"
    return None


def _sheet(book: dict, want: str, hint: str):
    for name in book:
        if _norm(name) == _norm(want):
            return name
    return next((n for n in book if hint in _norm(n)), None)


def _table(grid: list[list[str]]):
    """(header row index, headers) — the first row with two cells or more, within the first ten."""
    for i, r in enumerate(grid[:10]):
        if sum(1 for c in r if c) >= 2:
            return i, r
    return None, []


def plan(data: bytes, balance: str | None = None) -> dict:
    """The dry run: what the file holds and what an import would make; never a name or a contact, only counts,
    headers and row numbers. Raises xlsx.Bad for a file it won't read."""
    from .. import xlsx
    book, formulas = xlsx.read(data)
    out = {"sha": hashlib.sha256(data).hexdigest(), "formulas": formulas, "sheets": {}, "problems": [], "people": []}
    recs: dict[str, dict] = {}
    for want, hint in ((MEMBERS, "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a"), (HOURS, "\u0447\u0430\u0441")):
        name = _sheet(book, want, hint)
        if name is None:
            out["problems"].append(f"no sheet like {want!r}")
            continue
        hi, heads = _table(book[name])
        heads = [h or f"column {j + 1}" for j, h in enumerate(heads)]
        roles = {j: _role(h) for j, h in enumerate(heads)}
        col = {k: next((j for j, r in roles.items() if r == k), None) for k in ("name", "tg")}
        info = {"rows": 0, "headers": [[h, roles[j]] for j, h in enumerate(heads)], "matched": 0, "new": 0}
        out["sheets"][name] = info
        if hi is None or col["name"] is None and col["tg"] is None:
            out["problems"].append(f"{name}: no name or Telegram column")
            continue
        if balance and want == HOURS and balance not in heads:
            out["problems"].append(f"{name}: no column {balance!r} for the starting balance")
        for r, cells in enumerate(book[name][hi + 1:], hi + 2):
            cells = cells + [""] * (len(heads) - len(cells))
            if not any(cells):
                continue
            info["rows"] += 1
            if len(cells) > len(heads) and any(cells[len(heads):]):
                out["problems"].append(f"{name} row {r}: cells past the last header (kept as column N)")
            row = {(heads[j] if j < len(heads) else f"column {j + 1}"): c for j, c in enumerate(cells) if c}
            nm = cells[col["name"]] if col["name"] is not None else ""
            tg = _tg(cells[col["tg"]]) if col["tg"] is not None else None
            if col["tg"] is not None and cells[col["tg"]] and not tg:
                out["problems"].append(f"{name} row {r}: Telegram not a username (kept raw)")
            keys = [k for k in (tg and f"tg:{tg}", _norm(nm) and f"n:{_norm(nm)}") if k]
            if not keys:
                out["problems"].append(f"{name} row {r}: no name and no Telegram (kept, unkeyed)")
            rec = next((recs[k] for k in keys if k in recs), None)
            if rec and want in rec["sheets"]:
                out["problems"].append(f"{name} row {r}: repeats row {rec['sheets'][want]} (kept apart)")
                rec = None
                keys = []
            if rec is None:
                rec = {"name": nm, "tg": tg, "key": keys[0] if keys else None, "raw": {}, "sheets": {}, "balance": 0}
                out["people"].append(rec)
                info["new"] += 1
                if want == HOURS and out["sheets"].get(_sheet(book, MEMBERS, "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a") or "", {}).get("rows"):
                    out["problems"].append(f"{name} row {r}: on no row of the members sheet (a person of its own; the President may link both to one account)")
            else:
                info["matched"] += 1
            for k in keys:
                recs.setdefault(k, rec)
            rec["sheets"][want] = r
            rec["raw"][name] = row
            rec["name"] = rec["name"] or nm
            rec["tg"] = rec["tg"] or tg
            if balance and want == HOURS and row.get(balance):
                try:
                    rec["balance"] = round(float(row[balance].replace(",", ".").replace(" ", "")) * 60)
                    if not 0 <= rec["balance"] <= 100000 * 60:
                        raise ValueError
                except ValueError:
                    rec["balance"] = 0
                    out["problems"].append(f"{name} row {r}: {balance!r} isn't a number of hours (no balance)")
    return out


def counts(p: dict) -> dict:
    return {"people": len(p["people"]), "sheets": {k: {x: y for x, y in v.items() if x != "headers"} for k, v in p["sheets"].items()},
            "withBalance": sum(1 for r in p["people"] if r["balance"]), "formulas": p["formulas"], "problems": len(p["problems"])}


def apply(con, org: int, p: dict, source: str) -> dict:
    """One transaction: the batch (where the list came from, as given) and every record whose key isn't in the club yet.
    The same file twice is the same batch."""
    with tx(con):
        old = one(con, "SELECT id FROM vol_batches WHERE org_id = ? AND sha = ? AND undone_at IS NULL", org, p["sha"])
        if old:
            return {"batch": old[0], "again": True, "added": 0, "there": len(p["people"])}
        bid = con.execute("INSERT INTO vol_batches (org_id, source, sha, counts, created_at) VALUES (?, ?, ?, ?, ?)",
                          (org, source, p["sha"], json.dumps(counts(p)), now())).lastrowid
        added = there = 0
        for r in p["people"]:
            if r["key"] and one(con, "SELECT 1 FROM vol_people WHERE org_id = ? AND ikey = ?", org, r["key"]):
                there += 1
                continue
            con.execute("INSERT INTO vol_people (org_id, name, tg, ikey, raw, balance, batch_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (org, r["name"], r["tg"], r["key"], json.dumps(r["raw"], ensure_ascii=False), r["balance"], bid, now()))
            added += 1
        log_action(con, None, "vol_import", f"org:{org}", json.dumps({"batch": bid, "added": added, "there": there}))
    return {"batch": bid, "again": False, "added": added, "there": there}


def undo(con, org: int, bid: int) -> dict:
    """The batch's records go, except those used since (linked, shifts, misses or edits): those stay and are counted."""
    with tx(con):
        if not one(con, "SELECT 1 FROM vol_batches WHERE id = ? AND org_id = ? AND undone_at IS NULL", bid, org):
            raise ApiError("not_found")
        used = """user_id IS NOT NULL OR EXISTS (SELECT 1 FROM vol_shifts WHERE vol_id = p.id) OR EXISTS (SELECT 1 FROM vol_misses WHERE vol_id = p.id)
            OR EXISTS (SELECT 1 FROM vol_edits WHERE vol_id = p.id)"""
        kept = one(con, f"SELECT COUNT(*) FROM vol_people p WHERE batch_id = ? AND ({used})", bid)[0]
        gone = con.execute(f"DELETE FROM vol_people AS p WHERE batch_id = ? AND NOT ({used})", (bid,)).rowcount
        con.execute("UPDATE vol_batches SET undone_at = ? WHERE id = ?", (now(), bid))
        log_action(con, None, "vol_import_undo", f"org:{org}", json.dumps({"batch": bid, "gone": gone, "kept": kept}))
    return {"gone": gone, "kept": kept}
