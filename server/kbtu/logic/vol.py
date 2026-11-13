"""The volunteers ledger of one club (VOLUNTEERS=<slug>; Zhyly Zhurek first, owner Nov 9-10): its spreadsheet as an app.

A volunteer is a record of the club, apart from any account (people never in the app are on it too); the President
links one to an account and back. Hours come only from scans (the club's President with the owner, Nov 11: nobody types
hours): real check-in and check-out at the club's sessions (checkin.mark), never a teambuilding's; the shifts once entered
by hand stay as recorded. A check-in never checked out counts 0 minutes, the attendance stays; after Finish whoever ran
the door answers for each such shift (resolve: "until the end", or the time they left, between the check-in and Finish),
and the volunteer's "left without checking out" counter grows; no minutes are taken off. Who runs the door (a President,
a Vice, the holder of the hand-over link), if they started the session or paired its screen themselves (started, paired),
is on shift from the first volunteer they mark in until their own check-out or Finish. No shift counts more than 12 hours,
nor past 12 hours after its session's Start (SHIFT_CAP). The door of one session can be handed to a club member by a one-time link (hand, take). Misses: a session the
President marks as a teambuilding; its expected list (the whole roster) is frozen when the session is made. A miss
counts only once that session really ran: Finished, GRACE after it, and at least max(3, ceil(expected / 4)) of the
expected people marked. Readers: the club's President and whom she grants (club members); each volunteer sees only
their own hours and misses. "The President" here is the President or a Vice-president (_president), the same in
everything. Only they edit (misses, links, a shift taken out), with a reason, every edit in vol_edits (numbers
and times, never a contact). The import's columns are kept as they were (`raw`); the monthly "deposit" columns are
shown raw, nothing is computed from them until the club explains them. Nothing here is deleted by itself."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets

from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, log_action, now, one, person_ref, rows, _qs

# ponytail: v1 shortcuts, each with its upgrade: grants survive a new President (have her re-confirm them); a scan that
# waits for a sign-in (checkin.became_student) opens no shift (hook it there); only the club's own sessions count, not
# other clubs' events it helps at (the request flow); a teambuilding's validity is frozen only when an account is deleted
# (freeze_held), live until then so the President's corrections still count; the hand-over link's holder gets no capsule
# (checkin.running): the link itself is the way back; nobody answers for their own unmarked shift, so a club with one
# President and no Vice needs her to check out herself (upgrade: the app's admin answers from Admin); the 12 h caps
# (SHIFT_CAP) are applied when hours are read (_end), the rows keep the scans' own times, and no job finishes a session
# left open: its unmarked shifts wait for Finish (upgrade: a nightly Finish at Start + 12 h).
KEY = b""                # keys the hashes of deleted people's import keys (app.create, admin: from TOKEN_KEY)
ORG = ""                 # the club's slug (config VOLUNTEERS, set by app.create); empty: all of this is off
GRACE = 30 * 60          # as checkin.GRACE: a late sign-in may still complete a scan this long after Finish
REASON_MAX = 200
SHIFT_CAP = 12 * 3600    # one shift counts this long at most, and a session of the club gives hours for this long after its Start
RESOLVE_FOR = 7 * 86400  # an unmarked shift is answered for within this long after Finish; later it stays 0
FROM = "vol_resolve_from"  # meta: when answering for the unmarked began (migration 157); sessions finished before it stay as they were
HAND_MAX = 14 * 86400    # a hand-over link dies this long after it was made, opened or not (a session never finished)
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
    """The President or a Vice-president: one and the same for the whole ledger (Nov 11); decided here alone."""
    return v.student and bool(one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ? AND role IN ('president', 'vice')", org, v.id))


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

def _tie(con, vid: int, uid: int) -> None:
    """Every account a record was ever linked to: deleting that account deletes the record, unlinked since or not."""
    con.execute("INSERT OR IGNORE INTO vol_ties (vol_id, user_id) VALUES (?, ?)", (vid, uid))


def _attach(con, by: int | None, org: int, vid: int, uid: int) -> None:
    """Record vid to the account uid (by: who, None the app itself). The member's own record, if any (made by a check-in
    or another row of the import), merges into this one: its shifts, misses and columns move here."""
    y = one(con, "SELECT * FROM vol_people WHERE org_id = ? AND user_id = ? AND id != ?", org, uid, vid)
    if y:
        p = one(con, "SELECT raw FROM vol_people WHERE id = ?", vid)
        raw = json.loads(p["raw"])
        for k, x in json.loads(y["raw"]).items():
            raw[k if k not in raw else f"{k} ({y['id']})"] = x
        con.execute("UPDATE vol_shifts SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
        con.execute("UPDATE vol_misses SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
        con.execute("UPDATE vol_edits SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))
        con.execute("UPDATE vol_keys SET vol_id = ? WHERE vol_id = ?", (vid, y["id"]))  # its import keys stay as aliases
        con.execute("UPDATE vol_ties SET vol_id = ? WHERE vol_id = ? AND user_id NOT IN (SELECT user_id FROM vol_ties WHERE vol_id = ?)", (vid, y["id"], vid))
        con.execute("INSERT OR IGNORE INTO vol_expected (session_id, vol_id) SELECT session_id, ? FROM vol_expected WHERE vol_id = ?", (vid, y["id"]))
        con.execute("UPDATE vol_people SET raw = ?, balance = balance + ?, name = CASE WHEN name = '' THEN ? ELSE name END, tg = COALESCE(tg, ?) WHERE id = ?",
                    (json.dumps(raw, ensure_ascii=False), y["balance"], y["name"], y["tg"], vid))
        con.execute("DELETE FROM vol_people WHERE id = ?", (y["id"],))
        con.execute("INSERT INTO vol_edits (vol_id, what, ref, old, new, reason, by, at) VALUES (?, 'merge', ?, NULL, ?, '', ?, ?)",
                    (vid, y["id"], json.dumps({"balance": y["balance"]}), by, now()))
    con.execute("UPDATE vol_people SET user_id = ? WHERE id = ?", (uid, vid))
    _tie(con, vid, uid)
    log_action(con, by, "vol_link", f"user:{uid}", json.dumps({"vol": vid, **({} if by else {"auto": "tg"})}))


def _by_tg(con, org: int, uid: int) -> int | None:
    """The one unlinked record of the import whose Telegram username is this member's current one (none, or two: None).
    ponytail: a username is trusted as Telegram holds it now; a swapped username links the wrong record (the President
    unlinks it); upgrade: ask the member to confirm."""
    r = rows(con, """SELECT p.id FROM vol_people p JOIN users u ON u.id = ? AND lower(u.tg_username) = p.tg
        WHERE p.org_id = ? AND p.user_id IS NULL AND p.tg IS NOT NULL""", uid, org)
    return r[0][0] if len(r) == 1 else None


def autolink(con, org: int) -> int:
    """Every member of the club, a verified student with no record yet, and an unlinked import record by their Telegram
    username: linked. The admin's command, run by hand (an unlink by the President stays: nothing links again by itself);
    never a merge (a member with a record of their own is the President's to link). The count.
    ponytail: a wrong link the President undoes keeps its vol_ties row (deleting that account still takes the record);
    upgrade: drop the tie on an unlink of an auto link with nothing done under it."""
    n = 0
    with tx(con):
        for (uid,) in rows(con, """SELECT m.user_id FROM org_members m JOIN students s ON s.user_id = m.user_id AND s.manual = 0
                WHERE m.org_id = ?""", org):
            vid = _by_tg(con, org, uid)
            if vid and not one(con, "SELECT 1 FROM vol_people WHERE org_id = ? AND user_id = ?", org, uid):
                _attach(con, None, org, vid, uid)
                n += 1
    return n


def _record(con, org: int, uid: int) -> int | None:
    """My record in the club; a member without one gets an empty one (people who joined in the app after the import)."""
    r = one(con, "SELECT id FROM vol_people WHERE org_id = ? AND user_id = ?", org, uid)
    if r:
        return r[0]
    if not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", org, uid):
        return None
    vid = con.execute("INSERT INTO vol_people (org_id, user_id, created_at) VALUES (?, ?, ?)", (org, uid, now())).lastrowid
    _tie(con, vid, uid)
    return vid


def concerned(con, v: Viewer) -> bool:
    """The ledger holds this account's data or shows it others' (linked, granted, the President): its policy section
    must be agreed to (app.py: consent +vol1). Nobody else is asked."""
    org = org_id(con)
    return bool(org and v.student and (_president(con, v, org) or one(con, """SELECT 1 FROM vol_people WHERE org_id = ? AND user_id = ?
        UNION ALL SELECT 1 FROM vol_access WHERE org_id = ? AND user_id = ?""", org, v.id, org, v.id)))


def _khash(org: int, key: str) -> str:
    return hmac.new(KEY, f"vol-gone {org} {key}".encode(), hashlib.sha256).hexdigest()


def gone(con, uid: int) -> None:
    """An account being deleted (account.delete_me, before its rows go): every record ever tied to it goes with its
    shifts and misses, its import keys kept only as keyed hashes so a later list can't bring the person back; the club's
    teambuildings that already ran keep their validity (freeze_held)."""
    vids = [r[0] for r in rows(con, "SELECT vol_id FROM vol_ties WHERE user_id = ? UNION SELECT id FROM vol_people WHERE user_id = ?", uid, uid)]
    if not vids:
        return
    freeze_held(con)
    for org, key in rows(con, f"SELECT org_id, ikey FROM vol_keys WHERE vol_id IN ({_qs(vids)})", *vids):
        con.execute("INSERT OR IGNORE INTO vol_gone (org_id, khash) VALUES (?, ?)", (org, _khash(org, key)))
    con.execute(f"DELETE FROM vol_people WHERE id IN ({_qs(vids)})", vids)


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
    if not _mine(con, s) or s["ended_at"] is not None:  # a sign-in completed after Finish (GRACE) is attendance, never a shift
        return
    vid = _record(con, org, uid)
    if not vid:
        return  # a guest at the club's public event isn't a volunteer
    last = one(con, "SELECT * FROM vol_shifts WHERE vol_id = ? AND session_id = ? AND gone_at IS NULL ORDER BY in_at DESC, id DESC", vid, s["id"])
    if not out:
        if not last or last["out_at"] is not None:
            con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, in_by) VALUES (?, ?, ?, ?)", (vid, s["id"], t, uid))
            for r in _runners(con, s):  # whoever runs the door is here from the first volunteer they mark in
                rv = r != uid and _record(con, org, r)
                if rv and not one(con, "SELECT 1 FROM vol_shifts WHERE vol_id = ? AND session_id = ? AND gone_at IS NULL", rv, s["id"]):
                    con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, in_by) VALUES (?, ?, ?, ?)", (rv, s["id"], t, r))
    elif last:
        con.execute("UPDATE vol_shifts SET out_at = ?, out_by = ? WHERE id = ?", (t, uid, last["id"]))


# ------------------------------------------------------------ who runs a session's door (checkin calls these)

def _held(con, uid: int, s) -> bool:
    """The hand-over link's holder, while it lasts: not taken back, still a member and a student, until GRACE after Finish."""
    t = now()
    return (s["ended_at"] is None or s["ended_at"] > t - GRACE) and bool(one(con, """SELECT 1 FROM vol_hands h
        JOIN vol_meets m ON m.session_id = h.session_id JOIN org_members x ON x.org_id = m.org_id AND x.user_id = h.user_id
        JOIN students st ON st.user_id = h.user_id AND st.manual = 0
        WHERE h.session_id = ? AND h.user_id = ? AND h.revoked_at IS NULL AND h.created_at > ?""", s["id"], uid, t - HAND_MAX))


def holds(con, v: Viewer, s) -> bool:
    """This session's door was handed to me (take): I may start it, show its QR, switch to leaving, finish, and answer
    for the unmarked. Nothing else of it (the CSV, the helpers, another session) is mine."""
    return bool(ORG and v.student and _held(con, v.id, s))


def _mine(con, s) -> bool:
    """The ledger's club's session; never its team marked at an event (checkin.crew: no shifts, no hours)"""
    return bool(s["org_id"] and s["org_id"] == org_id(con) and not s["crew_event_id"])


def _runs(con, s, v: Viewer) -> None:
    """A President, a Vice or the link's holder is noted as running this door (the same meta mark as a member showing an
    event's QR, checkin.control): only for what they did themselves, Start or pairing the screen, never a later tap."""
    if _president(con, v, s["org_id"]) or holds(con, v, s):
        con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"qrshow:{s['id']}:{v.id}",))


def started(con, s, v: Viewer) -> None:
    """checkin.control: this person's Start began the session (ids only in the log)."""
    if _mine(con, s):
        _runs(con, s, v)
        log_action(con, v.id, "vol_session_start", f"qr:{s['id']}")


def paired(con, s, v: Viewer) -> None:
    """checkin.bind: this person's scan paired a screen to the session."""
    if _mine(con, s):
        _runs(con, s, v)


def on_shift(con, s, uid: int) -> bool:
    """An open shift of mine at this session of the club (checkin.mark: who ran the door has no scan of their own to leave by)."""
    return bool(s["org_id"] and s["org_id"] == org_id(con) and one(con, """SELECT 1 FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
        WHERE p.user_id = ? AND h.session_id = ? AND h.out_at IS NULL AND h.gone_at IS NULL""", uid, s["id"]))


def _runners(con, s) -> list[int]:
    """Who ran this door (started, paired) and still may: a role or a link lost since doesn't count."""
    k = f"qrshow:{s['id']}:"
    return [u for u in (int(r[0][len(k):]) for r in rows(con, "SELECT key FROM meta WHERE key >= ? AND key < ?", k, k[:-1] + ";"))
            if _held(con, u, s) or one(con, """SELECT 1 FROM org_members m JOIN students st ON st.user_id = m.user_id AND st.manual = 0
                WHERE m.org_id = ? AND m.user_id = ? AND m.role IN ('president', 'vice')""", s["org_id"], u)]


def finished(con, s, by: int, t: int) -> None:
    """Finish (inside checkin.control's transaction): who ran the door was there to the end, their own open shift closes
    now. Every other open shift, the one who pressed Finish too, stays open, 0 minutes, until someone answers for it (resolve)."""
    if not _mine(con, s):
        return
    for u in _runners(con, s):
        con.execute("""UPDATE vol_shifts SET out_at = ?, out_by = ? WHERE session_id = ? AND out_at IS NULL AND gone_at IS NULL AND in_at < ?
            AND vol_id IN (SELECT id FROM vol_people WHERE org_id = ? AND user_id = ?)""", (t, u, s["id"], t, s["org_id"], u))
    log_action(con, by, "vol_session_finish", f"qr:{s['id']}", json.dumps({"duration": t - s["started_at"]}))


def _end(in_at: int, out_at: int, sid: int | None, started: int | None) -> int:
    """Where a shift's hours stop: its check-out, 12 h after its check-in, 12 h after its session's Start, whichever is
    first. A shift once entered by hand (no session) stays as recorded."""
    if sid is None:
        return out_at
    return max(in_at, min(out_at, in_at + SHIFT_CAP, *([started + SHIFT_CAP] if started else [])))


def _open(con, s) -> bool:
    """This finished session's unmarked may still be answered for: finished since the feature came, RESOLVE_FOR ago at most."""
    f = one(con, "SELECT value FROM meta WHERE key = ?", FROM)
    return s["ended_at"] is not None and bool(f) and int(f[0]) <= s["ended_at"] > now() - RESOLVE_FOR


def _thash(token: object) -> str:
    return hashlib.sha256(f"kbtu-vol-hand:{token}".encode("utf-8", "replace")).hexdigest()


def _door(con, v: Viewer, sid: object):
    """(session, am I the President or a Vice) of a session of the club whose door is mine; raises otherwise."""
    org = _org(con)
    s = isinstance(sid, int) and one(con, "SELECT s.* FROM qr_sessions s JOIN vol_meets m ON m.session_id = s.id WHERE s.id = ? AND m.org_id = ?", sid, org)
    if not s:
        raise ApiError("not_found")
    lead = _president(con, v, org)
    if not lead and not holds(con, v, s):
        raise ApiError("forbidden")
    return s, lead


def _door_view(con, s, lead: bool) -> dict:
    """After Finish: every shift nobody checked out of, answered for or not yet. For the President and Vice: the link."""
    hs = [] if not _open(con, s) else rows(con, """SELECT h.id AS hid, h.in_at, h.out_at, p.* FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
        WHERE h.session_id = ? AND h.gone_at IS NULL AND (h.out_at IS NULL OR EXISTS (SELECT 1 FROM vol_edits e WHERE e.vol_id = h.vol_id
        AND e.what = 'resolve' AND e.ref = h.id)) ORDER BY h.out_at IS NOT NULL, h.in_at, h.id""", s["id"])
    who = _names(con, hs)
    hand = None
    if lead:
        r = one(con, "SELECT user_id FROM vol_hands WHERE session_id = ? AND revoked_at IS NULL AND created_at > ?", s["id"], now() - HAND_MAX)
        hand = r and {"holder": r[0] and _names(con, [r]).get(r[0])}
    # the link's holder: who handed the door to them
    by = None if lead else one(con, "SELECT made_by AS user_id FROM vol_hands WHERE session_id = ? AND revoked_at IS NULL", s["id"])
    return {"session": s["id"], "lead": lead, "ended": s["ended_at"], "hand": hand, "by": by and by[0] and _names(con, [by]).get(by[0]),
            "unmarked": [{"id": h["hid"], "name": _name(h, who.get(h["user_id"])), "person": who.get(h["user_id"]), "inAt": h["in_at"], "outAt": h["out_at"],
                          "end": _end(h["in_at"], s["ended_at"], s["id"], s["started_at"])} for h in hs]}


def door(con, v: Viewer, sid: int) -> dict:
    return _door_view(con, *_door(con, v, sid))


def resolve(con, v: Viewer, hid: int, body: dict) -> dict:
    """Someone left without checking out: who ran the door says "until the end" (left: null) or when they left (a time
    from their check-in to Finish, to the minute; _end's 12 h at most); the app counts the minutes. Never the shift of a
    record ever tied to one's own account (an unlink doesn't make it someone else's). Only a session finished since this
    came, within RESOLVE_FOR. Logged in vol_edits (left_unmarked), which is also the volunteer's counter. Answered wrongly:
    the President or a Vice answers again, inside the same window."""
    org = _org(con)
    with tx(con):
        h = one(con, """SELECT h.*, p.user_id FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
            WHERE h.id = ? AND p.org_id = ? AND h.gone_at IS NULL AND h.session_id IS NOT NULL""", hid, org)
        if not h:
            raise ApiError("not_found")
        s, lead = _door(con, v, h["session_id"])
        if not _open(con, s):
            raise ApiError("closed")
        if h["user_id"] == v.id or one(con, "SELECT 1 FROM vol_ties WHERE vol_id = ? AND user_id = ?", h["vol_id"], v.id):
            raise ApiError("forbidden", "own")
        if h["out_at"] is not None and not (lead and one(con, "SELECT 1 FROM vol_edits WHERE vol_id = ? AND what = 'resolve' AND ref = ?", h["vol_id"], hid)):
            raise ApiError("conflict")  # checked out by a scan: nothing to answer for; answered already: the President's or Vice's to change
        end = _end(h["in_at"], s["ended_at"], s["id"], s["started_at"])
        left = body.get("left")
        if left is not None and (not isinstance(left, int) or isinstance(left, bool) or not h["in_at"] // 60 * 60 <= left <= end):
            raise ApiError("bad_input", "left")
        out = end if left is None else max(left, h["in_at"])  # the check-in's own minute: from the check-in
        con.execute("UPDATE vol_shifts SET out_at = ?, out_by = ? WHERE id = ?", (out, v.id, hid))
        _edit(con, v, h["vol_id"], "resolve", hid, {"out": h["out_at"]}, {"out": out, "left_unmarked": True, "until_end": left is None}, "")
    return _door_view(con, s, lead)


def hand(con, v: Viewer, sid: int) -> dict:
    """The President or a Vice makes the one-time link to this session's door (a new one ends the last). The token is
    given once, here; only its hash is kept, and it is never logged."""
    s, lead = _door(con, v, sid)
    if not lead:
        raise ApiError("forbidden")
    if s["ended_at"] is not None:
        raise ApiError("closed")
    token = secrets.token_hex(16)
    with tx(con):
        con.execute("UPDATE vol_hands SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL", (now(), s["id"]))
        con.execute("INSERT INTO vol_hands (session_id, token, made_by, created_at) VALUES (?, ?, ?, ?)", (s["id"], _thash(token), v.id, now()))
        log_action(con, v.id, "vol_hand", f"qr:{s['id']}")
    return {**_door_view(con, s, True), "token": token}


def unhand(con, v: Viewer, sid: int) -> dict:
    """Taken back: the link and its holder's right end at once."""
    s, lead = _door(con, v, sid)
    if not lead:
        raise ApiError("forbidden")
    with tx(con):
        if con.execute("UPDATE vol_hands SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL", (now(), s["id"])).rowcount:
            log_action(con, v.id, "vol_hand_off", f"qr:{s['id']}")
    return _door_view(con, s, True)


def take(con, v: Viewer, token: object) -> int:
    """The link opened: the first verified student of the club to open it holds the session's door (its id); the same
    person again: still theirs; anyone after: refused. A President or a Vice opening it takes nothing (theirs already)."""
    org = _org(con)
    if not v.student:  # a verified student (app.viewer: never a manual one), refused before the link is touched
        raise ApiError("forbidden", "student")
    t = now()
    h = one(con, """SELECT h.id, h.session_id, h.user_id, s.ended_at FROM vol_hands h JOIN vol_meets m ON m.session_id = h.session_id
        JOIN qr_sessions s ON s.id = h.session_id WHERE h.token = ? AND m.org_id = ? AND h.revoked_at IS NULL AND h.created_at > ?""", _thash(token), org, t - HAND_MAX)
    if not h or h["ended_at"] is not None and h["ended_at"] <= t - GRACE:
        raise ApiError("not_found", "hand")
    if _president(con, v, org):
        return h["session_id"]
    if not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", org, v.id):
        raise ApiError("forbidden", "member")
    with tx(con):
        if con.execute("UPDATE vol_hands SET user_id = ?, taken_at = ? WHERE id = ? AND user_id IS NULL AND revoked_at IS NULL", (v.id, t, h["id"])).rowcount:
            log_action(con, v.id, "vol_hand_taken", f"qr:{h['session_id']}")
        elif not one(con, "SELECT 1 FROM vol_hands WHERE id = ? AND user_id = ? AND revoked_at IS NULL", h["id"], v.id):
            raise ApiError("conflict", "taken")
    return h["session_id"]


# ------------------------------------------------------------ the numbers, each read once for all rows

def _minutes(con, org: int, vid: int | None = None) -> dict[int, tuple[int, int]]:
    """{volunteer: (minutes of closed shifts, open shifts)}; an open shift (never checked out) counts 0, and time in two
    shifts at once counts once (the union). A teambuilding's shifts give no hours (owner, Nov 10: hours are for
    volunteering at events; a teambuilding only counts for misses)."""
    out: dict[int, list] = {}
    end: dict[int, int] = {}
    for r in rows(con, f"""SELECT h.vol_id, h.in_at, h.out_at, h.session_id, (SELECT started_at FROM qr_sessions WHERE id = h.session_id)
            FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
            WHERE p.org_id = ? AND h.gone_at IS NULL AND NOT EXISTS (SELECT 1 FROM vol_meets m WHERE m.session_id = h.session_id AND m.team = 1)
            {'AND h.vol_id = ?' if vid else ''} ORDER BY h.vol_id, h.in_at""", org, *([vid] if vid else [])):
        x = out.setdefault(r[0], [0, 0])
        if r[2] is None:
            x[1] += 1
        elif r[2] > r[1]:
            o = _end(r[1], r[2], r[3], r[4])
            a = max(r[1], end.get(r[0], 0))
            x[0] += max(0, o - a)
            end[r[0]] = max(end.get(r[0], 0), o)
    return {k: (s // 60, n) for k, (s, n) in out.items()}


# a teambuilding that really ran: Finished, GRACE ago, at least max(3, ceil(expected / 4)) of its expected people marked
# (frozen in vol_meets.held once an account is deleted: its marks going can't flip a past result, freeze_held)
_LIVE = """(SELECT COUNT(DISTINCT y.vol_id) FROM vol_expected y JOIN vol_shifts h ON h.vol_id = y.vol_id AND h.session_id = y.session_id
    AND h.gone_at IS NULL WHERE y.session_id = m.session_id) >= MAX(3, (m.expected_n + 3) / 4)"""
_HELD = f"""m.team = 1 AND s.ended_at IS NOT NULL AND s.ended_at <= ? AND COALESCE(m.held, {_LIVE})"""


def freeze_held(con) -> None:
    """Every teambuilding past GRACE keeps its validity as it is now (counts only, no person)."""
    con.execute(f"""UPDATE vol_meets AS m SET held = {_LIVE} WHERE held IS NULL AND team = 1 AND session_id IN
        (SELECT id FROM qr_sessions WHERE ended_at IS NOT NULL AND ended_at <= ?)""", (now() - GRACE,))


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


def _unmarked(con, org: int, vid: int | None = None) -> dict[int, int]:
    """{volunteer: shifts they left without checking out of}: the ones someone had to answer for (resolve)."""
    return {r[0]: r[1] for r in rows(con, f"""SELECT h.vol_id, COUNT(*) FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id
        WHERE p.org_id = ? AND h.gone_at IS NULL AND EXISTS (SELECT 1 FROM vol_edits e WHERE e.vol_id = h.vol_id AND e.what = 'resolve' AND e.ref = h.id)
        {'AND h.vol_id = ?' if vid else ''} GROUP BY h.vol_id""", org, *([vid] if vid else []))}


def _names(con, ps) -> dict[int, dict]:
    ids = [p["user_id"] for p in ps if p["user_id"]]
    return {r["id"]: person_ref(r) for r in rows(con, f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.id IN ({_qs(ids)})", *ids)}


def _name(p, who: dict | None) -> str:
    return p["name"] or (who or {}).get("realName") or (who or {}).get("name") or ""


def _row(p, who: dict | None, mins: tuple[int, int], misses: int, unmarked: int) -> dict:
    return {"id": p["id"], "name": _name(p, who), "tg": p["tg"], "person": who,
            "minutes": p["balance"] + mins[0], "open": mins[1], "misses": misses, "unmarked": unmarked}


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
        mine = {"id": me["id"], "minutes": me["balance"] + mins[0], "open": mins[1], "misses": _misses(con, org, me["id"]).get(me["id"], 0),
                "unmarked": _unmarked(con, org, me["id"]).get(me["id"], 0)}
    return {"org": org, "ledger": ledger, "edit": pres, "mine": mine}


def ledger(con, v: Viewer) -> dict:
    org = _org(con)
    if not _reader(con, v, org):
        raise ApiError("forbidden")
    ps = rows(con, "SELECT * FROM vol_people WHERE org_id = ?", org)
    who, mins, miss, unm = _names(con, ps), _minutes(con, org), _misses(con, org), _unmarked(con, org)
    people = sorted((_row(p, who.get(p["user_id"]), mins.get(p["id"], (0, 0)), miss.get(p["id"], 0), unm.get(p["id"], 0)) for p in ps), key=lambda x: x["name"].lower())
    t = now()
    held = {r[0] for r in rows(con, f"SELECT m.session_id FROM vol_meets m JOIN qr_sessions s ON s.id = m.session_id WHERE m.org_id = ? AND {_HELD}", org, t - GRACE)}
    meets = [{"session": r["session_id"], "title": r["title"], "at": r["started_at"] or r["created_at"], "ended": r["ended_at"], "team": bool(r["team"]),
              "expected": r["expected_n"], "marked": r["marked"], "held": r["session_id"] in held,
              "unresolved": r["unresolved"] if _open(con, r) else 0}
             for r in rows(con, """SELECT m.*, s.title, s.started_at, s.ended_at, (SELECT COUNT(DISTINCT h.vol_id) FROM vol_shifts h
                JOIN vol_expected y ON y.vol_id = h.vol_id AND y.session_id = h.session_id WHERE h.session_id = m.session_id AND h.gone_at IS NULL) AS marked,
                (SELECT COUNT(*) FROM vol_shifts h WHERE h.session_id = m.session_id AND h.gone_at IS NULL AND h.out_at IS NULL) AS unresolved
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
    out = _row(p, who, _minutes(con, org, vid).get(vid, (0, 0)), _misses(con, org, vid).get(vid, 0), _unmarked(con, org, vid).get(vid, 0))
    out["balance"] = p["balance"]
    unm = {r[0] for r in rows(con, "SELECT ref FROM vol_edits WHERE vol_id = ? AND what = 'resolve'", vid)}
    # a shift taken out stays on its volunteer's own page, with why: they see that hours were removed
    why = {r[0]: r[1] for r in rows(con, "SELECT ref, reason FROM vol_edits WHERE vol_id = ? AND what = 'shift' AND json_extract(new, '$.gone') ORDER BY id", vid)}
    out["shifts"] = [{"id": h["id"], "session": h["session_id"], "title": h["title"], "inAt": h["in_at"],
                      "outAt": h["out_at"] and _end(h["in_at"], h["out_at"], h["session_id"], h["started_at"]),
                      "byHand": h["in_by"] != p["user_id"] or h["session_id"] is None, "gone": h["gone_at"] is not None, "unmarked": h["id"] in unm, "team": bool(h["team"]),
                      **({"goneReason": why.get(h["id"], "")} if h["gone_at"] is not None else {})}
                     for h in rows(con, """SELECT h.*, s.title, s.started_at, EXISTS (SELECT 1 FROM vol_meets m WHERE m.session_id = h.session_id AND m.team = 1) AS team
                        FROM vol_shifts h LEFT JOIN qr_sessions s ON s.id = h.session_id
                        WHERE h.vol_id = ? ORDER BY h.in_at DESC""", vid)]
    out["missed"] = [{"session": r[1], "title": r[2], "at": r[3]} for r in _missed(con, org, vid)]
    out["manual"] = [{"id": r["id"], "n": r["n"], "session": r["session_id"], "at": r["at"]}
                     for r in rows(con, "SELECT * FROM vol_misses WHERE vol_id = ? AND gone_at IS NULL ORDER BY at DESC", vid)]
    if reader:
        out["raw"] = json.loads(p["raw"])
        out["edits"] = [{"what": r["what"], "ref": r["ref"], "old": r["old"] and json.loads(r["old"]), "new": r["new"] and json.loads(r["new"]),
                         "reason": r["reason"], "at": r["at"], "by": r["by"]} for r in rows(con, "SELECT * FROM vol_edits WHERE vol_id = ? ORDER BY id DESC LIMIT 100", vid)]
    return out


# ------------------------------------------------------------ the President's and Vice's edits (each with a reason, in vol_edits)

def edit_shift(con, v: Viewer, hid: int, body: dict) -> dict:
    """A shift taken out (gone) or put back, never its times: hours come from scans alone (Nov 11). The shifts once made
    or changed by hand stay as recorded; the old values are in vol_edits."""
    org = _need_pres(con, v)
    reason = _reason(body)
    h = one(con, "SELECT h.* FROM vol_shifts h JOIN vol_people p ON p.id = h.vol_id WHERE h.id = ? AND p.org_id = ?", hid, org)
    if not h:
        raise ApiError("not_found")
    if not isinstance(body.get("gone"), bool):
        raise ApiError("bad_input", "gone")
    gone = (h["gone_at"] or now()) if body["gone"] else None
    with tx(con):
        con.execute("UPDATE vol_shifts SET gone_at = ? WHERE id = ?", (gone, hid))
        _edit(con, v, h["vol_id"], "shift", hid, {"gone": h["gone_at"] is not None}, {"gone": gone is not None}, reason)
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
        _attach(con, v.id, org, vid, uid)
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
    used: set[str] = set()       # the records' keys
    ambiguous: set[str] = set()  # names two people have
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
            tgk, nk = tg and f"tg:{tg}", _norm(nm) and f"n:{_norm(nm)}"
            if not tgk and not nk:
                out["problems"].append(f"{name} row {r}: no name and no Telegram (kept, keyed by its cells)")
            rec = recs.get(tgk) if tgk else None
            if rec is None and nk and nk not in ambiguous:  # by the name only while one person has it
                byname = recs.get(nk)
                rec = byname if byname is not None and not (tg and byname["tg"] and byname["tg"] != tg) else None
            if rec and want in rec["sheets"]:
                out["problems"].append(f"{name} row {r}: repeats row {rec['sheets'][want]} (kept apart)")
                rec = None
            if rec is None:
                if nk in recs:
                    ambiguous.add(nk)  # a namesake: from now on that name matches nobody
                # every record keyed, a repeat too (its n-th time), so a deletion's marker covers it on any later list
                base = tgk if tgk and tgk not in used else nk if nk and nk not in used else tgk or nk or \
                    "raw:" + hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
                key, n = base, 2
                while key in used:
                    key, n = f"{base}#{n}", n + 1
                used.add(key)
                rec = {"name": nm, "tg": tg, "key": key, "raw": {}, "sheets": {}, "balance": 0}
                out["people"].append(rec)
                info["new"] += 1
                if want == HOURS and out["sheets"].get(_sheet(book, MEMBERS, "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a") or "", {}).get("rows"):
                    out["problems"].append(f"{name} row {r}: on no row of the members sheet (a person of its own; the President may link both to one account)")
            else:
                info["matched"] += 1
            for k in (tgk, nk):
                if k:
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
        added = there = deleted = 0
        for r in p["people"]:
            if r["key"] and one(con, "SELECT 1 FROM vol_keys WHERE org_id = ? AND ikey = ?", org, r["key"]):
                there += 1
                continue
            if r["key"] and one(con, "SELECT 1 FROM vol_gone WHERE org_id = ? AND khash = ?", org, _khash(org, r["key"])):
                deleted += 1  # deleted on their request: never back from a list
                continue
            vid = con.execute("INSERT INTO vol_people (org_id, name, tg, raw, balance, batch_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (org, r["name"], r["tg"], json.dumps(r["raw"], ensure_ascii=False), r["balance"], bid, now())).lastrowid
            if r["key"]:
                con.execute("INSERT INTO vol_keys (org_id, ikey, vol_id) VALUES (?, ?, ?)", (org, r["key"], vid))
            added += 1
        log_action(con, None, "vol_import", f"org:{org}", json.dumps({"batch": bid, "added": added, "there": there, "deleted": deleted}))
    return {"batch": bid, "again": False, "added": added, "there": there, "deleted": deleted}


def undo(con, org: int, bid: int) -> dict:
    """The batch's records go, except those used since (linked, shifts, misses or edits): those stay and are counted."""
    with tx(con):
        if not one(con, "SELECT 1 FROM vol_batches WHERE id = ? AND org_id = ? AND undone_at IS NULL", bid, org):
            raise ApiError("not_found")
        used = """user_id IS NOT NULL OR EXISTS (SELECT 1 FROM vol_ties WHERE vol_id = p.id) OR EXISTS (SELECT 1 FROM vol_shifts WHERE vol_id = p.id) OR EXISTS (SELECT 1 FROM vol_misses WHERE vol_id = p.id)
            OR EXISTS (SELECT 1 FROM vol_edits WHERE vol_id = p.id)"""
        kept = one(con, f"SELECT COUNT(*) FROM vol_people p WHERE batch_id = ? AND ({used})", bid)[0]
        gone = con.execute(f"DELETE FROM vol_people AS p WHERE batch_id = ? AND NOT ({used})", (bid,)).rowcount
        con.execute("UPDATE vol_batches SET undone_at = ? WHERE id = ?", (now(), bid))
        log_action(con, None, "vol_import_undo", f"org:{org}", json.dumps({"batch": bid, "gone": gone, "kept": kept}))
    return {"gone": gone, "kept": kept}
