"""The subjects' cards: a card per university subject (tools/subjects.py writes SUBJECTS_FILE, never the repo;
no file: off) and "looking for people to study it with". Being listed is a find-people request (forum.py) on that
subject: one per person and subject, until the term's end (a date set when listed, checked when read), its note checked
by the AI and moderated as any request (held, reports, Admin's queue), reached only by forum.contact's offer that the
other side accepts in the bot. Nobody sees who takes a subject: only who listed themselves.
The privacy policy's section 3 "Skills and finding people" covers it (a request's type, title, text, expiry, status;
offers and decisions), so listing oneself takes the policy in force (app.py: else the in-place gate)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, log_action, need_student, one, person_ref, short_name

NOTE_MAX = 140
LISTED_MAX = 12          # subjects one person is listed on at once (a term has 6-8)
WRITES_AN_HOUR = 30      # each with a note is an AI call
LINK = re.compile(r"https?://|www\.|t\.me/|@\w|\w\.(?:com|ru|kz|me|org|net|io)\b", re.I)  # plain words only
# where each term ends (Almaty), after its retakes: fall's Jan 9, spring's Jun 5, summer's Jul 23 (the 2026-27 calendar,
# web/src/lib/academic.ts). ponytail: fixed month and day; a calendar that moves them: change them here
TERM_ENDS = ((1, 9), (6, 5), (7, 23))
ALMATY = timezone(timedelta(hours=5))

_cat: tuple[str, float, dict] | None = None


def catalogue(path: str) -> dict[str, dict]:
    """The cards by id, read again only when the file changes. No file: the feature is off (404)."""
    global _cat
    try:
        m = Path(path).stat().st_mtime if path else None
    except OSError:
        m = None
    if m is None or not Path(path).is_file():
        raise ApiError("not_found", "no subjects")
    if not _cat or _cat[:2] != (path, m):
        _cat = (path, m, {s["id"]: s for s in json.loads(Path(path).read_text(encoding="utf-8"))["subjects"]})
    return _cat[2]


def on(path: str) -> bool:
    try:
        catalogue(path)
        return True
    except ApiError:
        return False


def term_end(t: int) -> int:
    """The end of the term a listing made at `t` is for: the first of TERM_ENDS after it."""
    y = datetime.fromtimestamp(t, ALMATY).year
    return min(e for yy in (y, y + 1) for m, d in TERM_ENDS if (e := int(datetime(yy, m, d, tzinfo=ALMATY).timestamp())) > t)


def may_read(con, uid: int) -> bool:
    """The subject listings are find-people data (the policy's section 3): a student Microsoft confirmed, on the policy
    in force (staff and admins' own rows are exempt), as app.subj_reader asks. For the routes that only reach them
    through a report (forum.may_touch_ask) and for a write the AI made wait (join)."""
    s = one(con, "SELECT manual, consent_version FROM students WHERE user_id = ?", uid)
    return bool(s) and not s["manual"] and (on_policy(s["consent_version"], CONSENT) or s["consent_version"] in ("staff", "admin"))


_SEEN = """a.subject IS NOT NULL AND a.status = 'live' AND a.expires_at > :now AND a.user_id != :me
    AND NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.user_id = :me AND b.blocked_id = a.user_id) OR (b.user_id = a.user_id AND b.blocked_id = :me))
    AND a.id NOT IN (SELECT target_id FROM reports WHERE target = 'ask' AND reporter_id = :me AND status = 'open')
    AND NOT EXISTS (SELECT 1 FROM subject_holds h WHERE h.user_id = a.user_id AND h.subject = a.subject AND h.until > :now)"""


def subjects(con, v: Viewer, path: str) -> dict:
    """Every card, how many others are looking on each (one read for all), and the ones I'm listed on."""
    need_student(v)
    cat = catalogue(path)
    counts = {r[0]: r[1] for r in con.execute(f"SELECT a.subject, COUNT(*) FROM asks a WHERE {_SEEN} GROUP BY a.subject",
                                              {"now": _now(), "me": v.id}) if r[0] in cat}
    mine = [r[0] for r in con.execute("SELECT subject FROM asks WHERE user_id = ? AND subject IS NOT NULL AND expires_at > ?", (v.id, _now()))]
    return {"subjects": list(cat.values()), "counts": counts, "mine": [s for s in mine if s in cat]}


def card(con, v: Viewer, path: str, sid: str) -> dict:
    """A subject: who else is looking (their card and note, my offer to each), and my own listing."""
    need_student(v)
    s = catalogue(path).get(sid)
    if not s:
        raise ApiError("not_found")
    people = []
    for p in con.execute(f"""SELECT {PERSON_COLS}, s.course, s.school, u.tg_id, u.tg_username, a.id AS ask, a.body, c.status AS offered
            FROM asks a JOIN users u ON u.id = a.user_id LEFT JOIN students s ON s.user_id = u.id
            LEFT JOIN contacts c ON c.ask_id = a.id AND c.from_id = :me AND c.to_id = a.user_id
            WHERE a.subject = :sid AND {_SEEN} ORDER BY a.id DESC LIMIT 200""", {"now": _now(), "me": v.id, "sid": sid}).fetchall():
        people.append({"ask": p["ask"], "person": person_ref(p), "name": short_name(p), "course": p["course"], "school": p["school"],
                       "note": p["body"] or None, "offered": p["offered"],
                       **({"telegram": _link(p)} if p["offered"] == "accepted" else {})})
    a = one(con, "SELECT * FROM asks WHERE subject = ? AND user_id = ? AND expires_at > ?", sid, v.id, _now())
    held = _held(con, v.id, sid)
    mine = {"note": a["body"], "status": "hidden" if held else a["status"], "why": a["why"], "until": a["expires_at"]} if a else None
    return {**s, "people": people, "mine": mine, "restricted": held}


def note_of(body: object) -> str:
    """My note as it would be kept: plain words, one line, no links or handles; too long or a link: refused."""
    note = " ".join(str((body or {}).get("note") or "").split()) if isinstance(body, dict) else ""
    if len(note) > NOTE_MAX:
        raise ApiError("bad_input")
    if LINK.search(note):
        raise ApiError("bad_input", "link")
    return note


def reserve(con, v: Viewer, path: str, sid: str) -> dict:
    """Before the AI is asked about my note: the subject is real, I'm under the cap, and this write is counted (one
    transaction), so neither a made-up subject nor a spent hour reaches the AI. The card."""
    need_student(v)
    s = catalogue(path).get(sid)
    if not s:
        raise ApiError("not_found")
    hour = _now() // 3600
    with tx(con):
        n = int((one(con, "SELECT value FROM meta WHERE key = ?", f"subj:{v.id}:{hour}") or [0])[0])
        if n >= WRITES_AN_HOUR:
            raise ApiError("rate_limited")
        _may_list(con, v.id, sid)
        con.execute("DELETE FROM meta WHERE key GLOB ? AND key != ?", (f"subj:{v.id}:*", f"subj:{v.id}:{hour}"))  # my past hours
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"subj:{v.id}:{hour}", str(n + 1)))
    return s


def _may_list(con, uid: int, sid: str) -> None:
    """Room for one more listing (the cap, but changing one I have is fine) and no take-down standing on this subject."""
    if one(con, "SELECT COUNT(*) FROM asks WHERE user_id = ? AND subject IS NOT NULL AND subject != ? AND expires_at > ?",
           uid, sid, _now())[0] >= LISTED_MAX:
        raise ApiError("rate_limited", "subjects")
    if _held(con, uid, sid):
        raise ApiError("conflict", "restricted")


def _held(con, uid: int, sid: str) -> int | None:
    """Until when a moderator's take-down keeps me off this subject (None: it doesn't)."""
    h = one(con, "SELECT until FROM subject_holds WHERE user_id = ? AND subject = ? AND until > ?", uid, sid, _now())
    return h[0] if h else None


def join(con, v: Viewer, path: str, s: dict, note: str, verdict: bool | None) -> dict:
    """List me on a subject (reserve() first) or change my note: live at once without a note or with the AI's yes, else
    held for a moderator (as create_ask). Until the term's end. The cap and a take-down are checked again here, inside
    the write: two lists at once at the cap end with one."""
    sid = s["id"]
    with tx(con):
        if not may_read(con, v.id):  # the AI took its time: the account may be gone, or no longer on the policy
            raise ApiError("forbidden", "consent")
        _may_list(con, v.id, sid)
        status, why = ("live", None) if not note or verdict else ("held", "ai" if verdict is False else "check")
        con.execute("""INSERT INTO asks (id, user_id, kind, title, body, status, why, created_at, expires_at, subject)
            VALUES (?, ?, 'help', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (subject, user_id) WHERE subject IS NOT NULL DO UPDATE SET title = excluded.title, body = excluded.body,
                status = excluded.status, why = excluded.why, expires_at = excluded.expires_at, found = NULL""",
                    (core.next_id(con, "asks"), v.id, s["names"]["ru"], note, status, why, _now(), term_end(_now()), sid))
    return card(con, v, path, sid)


def leave(con, v: Viewer, sid: str) -> None:
    """Off the list at once and for real: the row goes, its offers with it (a take-down stands apart: subject_holds)."""
    con.execute("DELETE FROM asks WHERE subject = ? AND user_id = ?", (sid, v.id))


# ---- a moderator's take-down: its own record, one per author and subject (forum.hide_ask writes it), until the
# listing's own end. While it stands the listing is out of every read (_SEEN) and listing again is refused

def hold(con, uid: int, sid: str, by: int | None, why: str, until: int) -> None:
    title = one(con, "SELECT title FROM asks WHERE user_id = ? AND subject = ?", uid, sid)
    con.execute("DELETE FROM subject_holds WHERE user_id = ? AND subject = ? AND until <= ?", (uid, sid, _now()))  # a past term's
    con.execute("INSERT OR IGNORE INTO subject_holds (user_id, subject, title, by_id, why, at, until) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, sid, title[0] if title else sid, by, why, _now(), until))


def holds(con) -> list[dict]:
    """The take-downs standing, for Admin to lift, newest first."""
    return [{"id": h["hid"], "title": h["title"], "person": person_ref(h), "name": short_name(h), "why": h["why"], "at": h["at"], "until": h["until"]}
            for h in con.execute(f"""SELECT h.id AS hid, h.title, h.why, h.at, h.until, {PERSON_COLS} FROM subject_holds h JOIN users u ON u.id = h.user_id
                LEFT JOIN students s ON s.user_id = u.id WHERE h.until > ? ORDER BY h.id DESC LIMIT 100""", (_now(),)).fetchall()]


def lift(con, v: Viewer, hid: int) -> None:
    """A moderator lifts a take-down (asked first in Admin): the record goes and the listing, if its author kept it, is
    up again. Done's Undo makes the record again (unlift), from what this line keeps."""
    _mod(v)
    with tx(con):
        h = one(con, "SELECT * FROM subject_holds WHERE id = ? AND until > ?", hid, _now())
        if not h:
            raise ApiError("not_found")
        con.execute("DELETE FROM subject_holds WHERE id = ?", (hid,))
        con.execute("UPDATE asks SET status = 'live', why = NULL WHERE user_id = ? AND subject = ? AND status = 'hidden'", (h["user_id"], h["subject"]))
        log_action(con, v.id, "subject_lift", f"subject_hold:{hid}", json.dumps({k: h[k] for k in ("user_id", "subject", "title", "by_id", "why", "at", "until")}))


def unlift(con, v: Viewer, target: str, data: dict) -> None:
    """Done's Undo of a lift: the same take-down again, its deadline as it was (gone by now, or its author no longer a
    student: nothing to undo). Logged on the lift's own target, so that lift counts as decided."""
    with tx(con):
        if data.get("until", 0) <= _now() or not con.execute("""INSERT OR IGNORE INTO subject_holds (user_id, subject, title, by_id, why, at, until)
                SELECT ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM students WHERE user_id = ?)""",
                (data["user_id"], data["subject"], data["title"], data["by_id"], data["why"], data["at"], data["until"], data["user_id"])).rowcount:
            raise ApiError("not_found")
        log_action(con, v.id, "subject_unlift", target)


def sweep_counters(con) -> None:
    """The hourly write counters past their hour (forum_sweep, nightly): nothing of who wrote when outlives the hour."""
    hour = _now() // 3600
    for (k,) in con.execute("SELECT key FROM meta WHERE key LIKE 'subj:%' OR key LIKE 'fsearch:%'").fetchall():
        if not k.split(":")[-1].isdigit() or int(k.split(":")[-1]) < hour:
            con.execute("DELETE FROM meta WHERE key = ?", (k,))


def offer(con, v: Viewer, aid: object) -> dict:
    """"Study together": the find-people offer to whoever listed themselves (forum.contact), only on a subject's listing."""
    if not isinstance(aid, int) or isinstance(aid, bool) or not one(con, "SELECT 1 FROM asks WHERE id = ? AND subject IS NOT NULL", aid):
        raise ApiError("not_found")
    return contact(con, v, aid=aid)


def _now() -> int:
    return core.now()


from . import core  # noqa: E402
from .forum import _link, contact  # noqa: E402
from .oversight import _mod  # noqa: E402
from .account import CONSENT, on_policy  # noqa: E402
