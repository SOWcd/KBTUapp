"""Running an event: creating, editing, publishing, the door, attendees, ratings, the album."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from .. import media, pdfpages
from ..db import tx

from .core import (FULL_TOOLS, ApiError, DOOR_EARLY, DOOR_LATE, door_shut, PERSON, PERSON_COLS, PROFILE_QR, RANK, TWO_GIS, Viewer, _door_ref,
    _by_id, _may, _org, _qs, at_least, can, card, cards, deleting, evdel, friend_ids, full, log_action, media_shape, need_student, one, org_ref,
    overseer, person_ref, role_in, rows, short_name, taken)


# ---------------------------------------------------------------- Studio (own org)

def _staff_event(con, v: Viewer, eid: int, right: str, cohost: bool = False, helper: tuple[str, ...] = ()) -> sqlite3.Row:
    """The event, if I have this right in its club: "events" to run it, "door" to check people in. cohost: the door and
    the attendee list, which the co-host's event team has too (cohosts.py); every other right stays the host's.
    helper: the kinds of the event's temporary door helper let in too (crew.py)."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or e["hidden_at"] and deleting(con, eid):  # the admin's delete: gone from Studio at once (Admin has its Undo)
        raise ApiError("not_found")
    if not (cohost and co_runs(con, v, eid)) and not (helper and crew_kind(con, v, e) in helper):
        _may(con, v, e["org_id"], right)
    if right == "door" and e["guest_host"]:
        raise ApiError("closed")  # a partner's event has no door: people sign up on the host's site
    return e


def _draft_event(con, v: Viewer, eid: int) -> sqlite3.Row:
    """The event to edit: the "events" right's; or a member's own draft, theirs until the club approves it (published:
    the organizers' alone)."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if e and e["status"] == "draft" and e["created_by"] == v.id and not e["hidden_at"] and at_least(role_in(con, v, e["org_id"]), "member"):
        return e
    return _staff_event(con, v, eid, "events")


def org_events(con, v: Viewer, oid: int) -> list[dict]:
    """Studio's list; for the club's Head+ each event also says how many questions wait for them (`_asking`) and how
    many receipts to check, so they show on top of Studio."""
    role = role_in(con, v, oid)
    if not at_least(role, "member"):
        raise ApiError("forbidden")
    head = can(con, v, oid, "events")
    # requests without an event: left, hidden; the events we co-host, out already, for the whole team as our
    # own (cohosts.py; their counters below stay the host's, their door and list our event team's)
    # never a taken-down or deleted one, nor a hidden host's: the event's own page refuses those too
    found = rows(con, f"""SELECT * FROM events WHERE (org_id = ? OR status != 'draft' AND hidden_at IS NULL
        AND org_id NOT IN (SELECT id FROM orgs WHERE status = 'hidden') AND id IN (SELECT x.event_id FROM event_cohosts x
        JOIN orgs c ON c.id = x.org_id AND c.status = 'active' WHERE x.org_id = ? AND x.status = 'accepted')) AND memo_only = 0 AND NOT {evdel('events')} ORDER BY starts_at""", oid, oid)
    found = [e for e in found if e["visibility"] != "members" or e["org_id"] != oid or for_me(con, v, e, role)]  # a department's: its own
    # receipts that look wrong and nobody looked at yet (§4.3; a registration's last receipt counts), on top of Studio too
    check = dict(rows(con, """SELECT r.event_id, COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id)
        WHERE e.org_id = ? AND r.status = 'going' AND c.status = 'accepted' AND c.flags != '' AND c.reviewed_at IS NULL AND c.created_at >= r.created_at
        GROUP BY r.event_id""", oid)) if head else {}
    own = [e["id"] for e in found if e["org_id"] == oid]  # a co-hosted event's counts are its host's
    saved = dict(rows(con, f"SELECT event_id, COUNT(*) FROM saved_events WHERE event_id IN ({_qs(own)}) GROUP BY event_id", *own)) if head and own else {}
    asked = dict(rows(con, """SELECT x.event_id, COUNT(*) FROM volunteers x JOIN events e ON e.id = x.event_id
        WHERE e.org_id = ? AND x.status = 'asked' GROUP BY x.event_id""", oid)) if head else {}  # volunteers waiting for an answer
    # the club's own people asking to come as guests (seats.team_ask): its President's and Vices' to answer
    guests = dict(rows(con, """SELECT a.event_id, COUNT(*) FROM team_asks a JOIN events e ON e.id = a.event_id
        JOIN org_members m ON m.org_id = e.org_id AND m.user_id = a.user_id WHERE e.org_id = ? AND a.status = 'pending' GROUP BY a.event_id""", oid)) \
        if role in ("president", "vice") else {}
    # The same cutoffs as _asking, counted once for the whole list; co-hosted events keep their host's questions.
    questions = dict(rows(con, f"""WITH leads AS (SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice', 'head')),
        live AS (SELECT id, event_id, user_id, as_org FROM comments WHERE event_id IN ({_qs(own)}) AND deleted_at IS NULL),
        answered AS (SELECT event_id, MAX(id) AS last_id FROM live WHERE as_org = 1 OR user_id IN leads GROUP BY event_id)
        SELECT c.event_id, COUNT(*) FROM live c LEFT JOIN answered a ON a.event_id = c.event_id
        LEFT JOIN comment_reads r ON r.event_id = c.event_id AND r.user_id = ?
        WHERE c.as_org = 0 AND c.user_id NOT IN leads AND c.id > COALESCE(a.last_id, 0) AND c.id > COALESCE(r.last_id, 0)
        GROUP BY c.event_id""", oid, *own, v.id)) if head and own else {}
    # drafts found in the club's channel (autoev.py): Studio's To do asks to check and publish them
    posts = autoev.from_posts(con, [e["id"] for e in found if e["org_id"] == oid and e["status"] == "draft"]) if head else {}
    # members' drafts and where each stands (submit_event): the author's own, and the President's and Vices' to answer
    asks = {r["event_id"]: r for r in rows(con, "SELECT r.* FROM event_reviews r JOIN events e ON e.id = r.event_id WHERE e.org_id = ? AND e.status = 'draft'", oid)}
    review = {e["id"]: {"mine": e["created_by"] == v.id, "askedAt": a["asked_at"] if a else None, "reason": a["reason"] if a else None}
              for e in found if e["org_id"] == oid and e["status"] == "draft" and ((a := asks.get(e["id"])) or e["created_by"] == v.id)}
    return [{**c, **({"review": review[e["id"]]} if e["id"] in review else {}), "questions": questions.get(e["id"], 0), "toCheck": check.get(e["id"], 0), "savedBy": saved.get(e["id"], 0),
             "volunteersAsked": asked.get(e["id"], 0), "teamAsks": guests.get(e["id"], 0), **({"fromPost": posts[e["id"]]} if e["id"] in posts else {})}
            for e, c in zip(found, cards(con, v, found))]


def _asking(con, eid: int, reader: int = 0) -> list:
    """Students' comments under an event that wait for the club: after its last answer (as the club, or by any of its
    Head+ as themselves; their own words are never questions) and, for a `reader`, after they last read the thread
    (else Studio's count stays after he has read and answered). By ids, so the same second never hides one.
    ponytail: an id freed by a deleted account's last comment can come back; a reader may then miss one question."""
    return rows(con, """WITH leads AS (SELECT m.user_id FROM org_members m JOIN events e ON e.org_id = m.org_id
            WHERE e.id = ? AND m.role IN ('president', 'vice', 'head')),
          live AS (SELECT * FROM comments WHERE event_id = ? AND deleted_at IS NULL)
        SELECT user_id FROM live WHERE as_org = 0 AND user_id NOT IN leads
          AND id > COALESCE((SELECT MAX(id) FROM live WHERE as_org = 1 OR user_id IN leads), 0)
          AND id > COALESCE((SELECT last_id FROM comment_reads WHERE event_id = ? AND user_id = ?), 0)""", eid, eid, eid, reader)


def shade(color: str) -> str:
    """Sheet tint from the event's colour (with a cover the editor sends the photo's own, §4.8b): the same hue, a quarter darker."""
    n = int(color[1:], 16)
    return "#" + "".join(f"{round(((n >> s) & 255) * 0.75):02x}" for s in (16, 8, 0))


LEAD_ROLES = {"president": ("president",), "vice": ("president", "vice"), "head": ("president", "vice", "head")}


def _invited_leaders(con, e: sqlite3.Row, exclude: int | None = None) -> list[sqlite3.Row]:
    """Who a leaders meeting invites: every club's people from its lowest invited role up (each person once)."""
    roles = LEAD_ROLES[e["leaders_from"] or "president"]
    return rows(con, f"""SELECT DISTINCT m.user_id FROM org_members m JOIN orgs o ON o.id = m.org_id JOIN students s ON s.user_id = m.user_id
        WHERE o.kind IN ('club', 'school', 'council') AND o.status = 'active' AND m.role IN ({','.join('?' * len(roles))}) AND m.user_id != ?""",
                *roles, exclude or 0)


def decline(con, v: Viewer, eid: int, note: object = None) -> dict:
    """"Can't make it" (a leaders meeting, §4.10; a club meeting, §2b, says why, which its Head+ read): the answer is
    kept, a seat or a ticket given back."""
    need_student(v)
    e = _event(con, v, eid)
    if e["status"] != "published" or e["starts_at"] <= core.now():
        raise ApiError("closed")
    why = " ".join(str(note or "").split())
    if len(why) > 140 or (e["meeting"] and len(why) < 2):
        raise ApiError("bad_input", "note")
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, v.id)
    if r and r["status"] in ("going", "hold", "waitlist"):
        unregister(con, v, eid)
    elif not r:
        con.execute("""INSERT INTO registrations (event_id, user_id, status, cancel_reason, ticket_code, created_at, updated_at)
            VALUES (?, ?, 'cancelled', 'self', ?, ?, ?)""", (eid, v.id, _ticket_code(con, eid), core.now(), core.now()))
    con.execute("UPDATE registrations SET note = ? WHERE event_id = ? AND user_id = ?", (why or None, eid, v.id))
    return card(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _team_door(e: sqlite3.Row) -> bool:
    """A club meeting, or a free team-only event: no tickets, so the door has the whole team (a meeting's
    tag) to mark, and someone who came without signing up is let in by name."""
    return not e["guest_list"] and (bool(e["meeting"]) or (e["visibility"] == "members" and not e["price"]))


def _expected(con, e: sqlite3.Row) -> list[int]:
    """Who a team-only event is for (§2b; a meeting expects them): the club's students, only those with its tag, or
    its board (Head+, by their roles now)."""
    tag = e["meeting_tag"]
    return [r[0] for r in rows(con, "SELECT m.user_id FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ?"
                                    + (" AND m.user_id IN (SELECT user_id FROM member_tags WHERE tag_id = ?)" if tag else "")
                                    + (" AND m.role IN ('head', 'vice', 'president')" if e["for_board"] else ""), e["org_id"], *([tag] if tag else []))]


def meeting_answers(con, v: Viewer, eid: int) -> list[dict]:
    """A club meeting's people for its Head+ (§2b): each one's answer (yes, no with the reason, none) and whether they
    came, and whether they are on probation."""
    e = _staff_event(con, v, eid, "events")
    if not e["meeting"]:
        raise ApiError("bad_input")
    expected = _expected(con, e)
    found = rows(con, f"""SELECT {PERSON_COLS}, m.role, m.probation, r.status, r.note, r.checked_in_at
        FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id
        LEFT JOIN registrations r ON r.event_id = ? AND r.user_id = u.id
        WHERE m.org_id = ? AND u.id IN ({_qs(expected)})""", eid, e["org_id"], *expected) if expected else []
    mine, people = role_in(con, v, e["org_id"]), can(con, v, e["org_id"], "people")
    out = []
    for p in found:
        answer = "yes" if p["status"] in ("going", "hold") else "no" if p["status"] == "cancelled" else "none"
        came = p["checked_in_at"] is not None
        out.append({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "role": p["role"],
                    "answer": answer, "note": p["note"], "came": came, **probation_field(v, mine, people, p)})
    return sorted(out, key=lambda x: (-RANK[x["role"]], x["fullName"]))


def leaders_answers(con, v: Viewer, eid: int) -> list[dict]:
    """DMP's view of a leaders meeting (§4.10): per club, who said yes, who no, who hasn't answered."""
    e = _staff_event(con, v, eid, "events")
    if e["visibility"] != "leaders":
        raise ApiError("bad_input")
    roles = LEAD_ROLES[e["leaders_from"] or "president"]
    out = []
    orgs = rows(con, "SELECT * FROM orgs WHERE kind IN ('club', 'school', 'council') AND status = 'active' ORDER BY official DESC, name")
    by_org: dict[int, list] = {}  # every club's leaders in one read, not one per club
    for p in rows(con, f"""SELECT {PERSON_COLS}, m.org_id, m.role, r.status AS answer FROM org_members m JOIN users u ON u.id = m.user_id
            JOIN students s ON s.user_id = u.id LEFT JOIN registrations r ON r.event_id = ? AND r.user_id = u.id
            WHERE m.role IN ({','.join('?' * len(roles))}) ORDER BY m.org_id, m.user_id""", eid, *roles):
        by_org.setdefault(p["org_id"], []).append(p)
    logos = _by_id(con, "files", (o["logo_file_id"] for o in orgs if o["id"] in by_org))
    for o in orgs:
        people = by_org.get(o["id"])
        if not people:
            continue
        said = lambda p: "yes" if p["answer"] in ("going", "hold") else "no" if p["answer"] == "cancelled" else "none"  # noqa: E731
        out.append({"org": org_ref(con, o, logos), "people": sorted(({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(),
                                                          "role": p["role"], "answer": said(p)} for p in people), key=lambda x: -RANK[x["role"]])})
    return out


QUESTIONS_MAX, QUESTION_MAX, OPTION_MAX = 5, 80, 40


def clean_questions(raw: object) -> str | None:
    """The editor's questions at sign-up, checked: up to 5, each its words (2-80), text or a choice of 2-8 options
    (1-40 each, no repeats), required or not. None: no questions. Kept as JSON."""
    if raw is None or raw == []:
        return None
    if not isinstance(raw, list) or len(raw) > QUESTIONS_MAX:
        raise ApiError("bad_input", "questions")
    out = []
    for q in raw:
        if not isinstance(q, dict):
            raise ApiError("bad_input", "questions")
        label, kind = " ".join(str(q.get("label") or "").split()), q.get("kind")
        opts = [" ".join(str(o).split()) for o in q.get("options") or []] if kind == "choice" else []
        if not 2 <= len(label) <= QUESTION_MAX or kind not in ("text", "choice") or not isinstance(q.get("required", False), bool) \
                or kind == "choice" and not (2 <= len(opts) <= 8 and len(set(opts)) == len(opts) and all(1 <= len(o) <= OPTION_MAX for o in opts)):
            raise ApiError("bad_input", "questions")
        out.append({"label": label, "kind": kind, **({"options": opts} if opts else {}), "required": bool(q.get("required"))})
    if len({q["label"].lower() for q in out}) != len(out):  # one column each in the table: no two the same
        raise ApiError("bad_input", "questions")
    return json.dumps(out, ensure_ascii=False)


def clean_event(i: dict, oversee: bool = False) -> dict:
    """The editor's input, checked. A leaders meeting (§4.10) only from an oversight org
    (DMP), with the lowest role invited."""
    try:
        title, place = str(i["title"]).strip(), str(i["place"]).strip()
        description = str(i.get("description") or "").strip()
        url = (str(i.get("placeUrl") or "")).strip() or None
        starts, ends = int(i["startsAt"]), (int(i["endsAt"]) if i.get("endsAt") is not None else None)
        # capacity is chosen, never a default: a number, or null for no limit; left out is refused (an editor that
        # forgot the field would publish an unlimited event by accident)
        if "seats" not in i:
            raise ApiError("bad_input", "seats")
        seats = i["seats"]
        if not (seats is None or isinstance(seats, int) and not isinstance(seats, bool)):
            raise ApiError("bad_input", "seats")
        reg_until = int(i["regUntil"]) if i.get("regUntil") is not None else None
        emoji, color = str(i["emoji"]), str(i["color"])
        visibility = None if i.get("visibility") is None else str(i["visibility"])  # left out: kept as it is
        leaders = str(i.get("leadersFrom") or "president") if visibility == "leaders" else None
        meeting = i.get("meeting") is True  # a club meeting (§2b): team-only, someone's tag or the whole club expected
        # "For whom": one of the club's tags on any team-only event, required or not (_meeting_ok checks it)
        tag = int(i["meetingTag"]) if i.get("meetingTag") is not None else None
        board = i.get("forBoard") is True  # "For whom": the board (Head+), a built-in choice beside the tags
        vol = int(i["volunteers"]) if i.get("volunteers") else None  # how many volunteers it needs; none: off
        late = i.get("lateSignup") is True  # sign-up stays open until the end; no deadline then (_partner_ok checks the rest)
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    ok = (0 < len(title) <= 80 and len(place) <= 80 and len(description) <= 2000  # no place: to be confirmed (a room asked of DMP)
          and (ends is None or starts < ends <= starts + 31 * 86400)  # Cap the span in days because the door stays open for the whole event.
          and (seats is None or 0 < seats <= 5000) and (url is None or TWO_GIS.match(url)) and (reg_until is None or reg_until <= starts)
          and re.fullmatch(r"#[0-9a-fA-F]{6}", color) and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and visibility in (None, "public", "members", *(("leaders",) if oversee else ()))
          and leaders in (None, "president", "vice", "head") and (not meeting or visibility == "members" and seats is None)
          and (vol is None or 1 <= vol <= 500 and not meeting) and not (board and tag))
    if not ok:
        raise ApiError("bad_input")
    return {"title": title, "description": description, "starts_at": starts, "ends_at": ends, "place": place, "place_url": url,
            "emoji": emoji, "color": color, "seats": seats, "reg_until": None if late else reg_until, "late_signup": int(late), "first_year": int(bool(i.get("firstYear"))),
            "needs_phone": int(i.get("needsPhone") is True),  # Keep the phone number so the next event can use it at sign-up.
            **({"questions": clean_questions(i["form"])} if "form" in i else {}),  # the questions at sign-up; left out: kept as they are
            "meeting": int(meeting), "meeting_tag": tag, "for_board": int(board), "volunteers": vol, "volunteers_senior": int(bool(vol and i.get("volunteersSenior"))),
            **({"visibility": visibility, "leaders_from": leaders} if visibility else {})}


def online_fields(i: dict, was: str | None) -> dict:
    """An online event, resolved against the saved one (`was`: events.online; None for a new event):
    - `online` left out: kept as it is (`onlineUrl` alone is refused: which way it was meant is unclear);
    - `online: true`: online; `onlineUrl` a link typed by the organizer (any https host, core.online_url), null or ''
      for none yet, left out to keep the saved link;
    - `online: false` (or anything but true): not online, the link gone.
    Online has no place: place and its 2GIS link are cleared whenever the event stays online."""
    if "online" not in i:
        if "onlineUrl" in i:
            raise ApiError("bad_input", "online")
        online = was
    elif i["online"] is not True:
        online = None
    elif "onlineUrl" not in i:
        online = was or ""
    else:
        raw = i["onlineUrl"]
        if raw is not None and not isinstance(raw, str):
            raise ApiError("bad_input", "online")
        link = core.online_url(raw, typed=True)
        if (raw or "").strip() and not link:
            raise ApiError("bad_input", "online")
        online = link or ""
    return {"online": online, **({"place": "", "place_url": None} if online is not None else {})}


def _meeting_ok(con, v: Viewer, oid: int, f: dict, priced: bool, was: tuple | None = None, vis: str = "public") -> None:
    """A meeting has no price. "For whom" (the tag) is one of the club's own, on a team-only event only (a meeting or
    not: a department's get-together today, its required meeting tomorrow). A Head with a department calls only that
    department (PLAN item 35); `was` (meeting, tag, board) before an edit: what someone else set stays as it is. `vis`: the
    event's visibility after the edit."""
    if f["meeting"] and priced or (f["meeting_tag"] or f["for_board"]) and f.get("visibility", vis) != "members" \
            or f["meeting_tag"] and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ?", f["meeting_tag"], oid):
        raise ApiError("bad_input")
    if (f["meeting"] or f["meeting_tag"] or f["for_board"]) and (f["meeting"], f["meeting_tag"], f["for_board"]) != was \
            and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
        own = depts_scope(con, oid, v.id)
        if own is not None and f["meeting_tag"] not in own:
            raise ApiError("forbidden", "dept")


def _cover(con, v: Viewer, body: dict, keep: int | None) -> int | None:
    """The editor's coverId: absent keeps the current photo, null removes it, an id must be the caller's upload."""
    if "coverId" not in body:
        return keep
    if body["coverId"] is None:
        return None
    try:
        f = one(con, "SELECT id FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?", int(body["coverId"]), v.id)
    except (TypeError, ValueError):
        f = None
    if not f:
        raise ApiError("bad_input")
    return f["id"]


def _focus(body: dict, keep: str | None) -> str | None:
    """The editor's coverFocus: the point of the photo every frame keeps in view, [x, y] from 0 to 1; absent keeps it."""
    if "coverFocus" not in body:
        return keep
    if body["coverFocus"] is None:
        return None
    try:
        x, y = (float(c) for c in body["coverFocus"])
    except (TypeError, ValueError):
        raise ApiError("bad_input")
    if not (0 <= x <= 1 and 0 <= y <= 1):  # NaN fails here too
        raise ApiError("bad_input")
    return f"{x:.3f},{y:.3f}"


FORMATS = ("feed", "card", "list")


def _cover_by(con, v: Viewer, body: dict, eid: int, cover: int | None, was: int | None) -> None:
    """The editor's coverBy: {format: {focus} | {id, focus} | null}, a format's own crop or its own photo over the one
    cover (the Feed's tall slide, the event's card, a list's thumbnail). Absent keeps them, a format's null goes back to
    the cover; a photo must be on that format already (a co-organizer's) or the caller's upload. No cover: none; another
    cover and nothing said: the crops made for the old one go."""
    if cover is None:
        con.execute("DELETE FROM event_covers WHERE event_id = ?", (eid,))
    elif body.get("coverBy") is None:
        if cover != was:
            con.execute("DELETE FROM event_covers WHERE event_id = ? AND file_id IS NULL", (eid,))
    else:
        by = body["coverBy"]
        if not isinstance(by, dict) or set(by) - set(FORMATS):
            raise ApiError("bad_input")
        for k, x in by.items():
            if x is not None and not isinstance(x, dict):
                raise ApiError("bad_input")
            fid, focus = (x.get("id"), _focus({"coverFocus": x.get("focus")}, None)) if x else (None, None)
            if fid is not None and (not isinstance(fid, int) or isinstance(fid, bool) or fid == cover or not one(
                    con, """SELECT 1 FROM event_covers WHERE event_id = ? AND format = ? AND file_id = ?
                    UNION ALL SELECT 1 FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?""", eid, k, fid, fid, v.id)):
                raise ApiError("bad_input")
            if fid is None and focus is None:
                con.execute("DELETE FROM event_covers WHERE event_id = ? AND format = ?", (eid, k))
            else:
                con.execute("INSERT OR REPLACE INTO event_covers (event_id, format, file_id, focus) VALUES (?, ?, ?, ?)", (eid, k, fid, focus))
    core._SHARED.pop(("event", eid), None)  # the Afisha's card shows them


def kz_phone(raw: object) -> str | None:
    """A Kazakhstan number as typed (8 701..., +7 701..., 701...) kept as +7XXXXXXXXXX; None if it isn't one."""
    t = str(raw or "")
    d = re.sub(r"[^0-9]", "", t)  # ASCII only: \d takes any script's digits
    # ten digits are the number without its +7, unless it came with a "+": "+7 701 234 56 7" is one digit short
    d = "7" + d[1:] if len(d) == 11 and d[0] == "8" else "7" + d if len(d) == 10 and not t.lstrip().startswith("+") else d
    return "+" + d if re.fullmatch(r"7[0-9]{10}", d) else None


def _pay(con, v: Viewer, body: dict, org: sqlite3.Row, e: sqlite3.Row | None = None) -> dict:
    """The price and where students send it (§4.3): only an official club's Vice+ set them (the creator from Admin too, logged) (any club's Vice+ makes it free), and they are fixed once the
    first receipt is in. Absent keeps them; a null price makes the event free. The phone is kept as +7XXXXXXXXXX.
    freeFirst: how many 1st-year students come free (the first ones to register); it can change any time.
    ponytail: a raised freeFirst doesn't turn 1st-years already holding a seat free; they pay or let it go."""
    if not any(k in body for k in ("price", "payToName", "payPhone", "freeFirst")):
        return {}
    price, name, phone, first = body.get("price"), None, None, None
    if price is not None:
        name = " ".join(str(body.get("payToName") or "").split())
        phone = kz_phone(body.get("payPhone"))
        first = body.get("freeFirst") or None
        if (not isinstance(price, int) or isinstance(price, bool) or not 1 <= price <= 1_000_000
                or not 2 <= len(name) <= 80 or not phone
                or not (first is None or (isinstance(first, int) and not isinstance(first, bool) and 1 <= first <= 5000))):
            raise ApiError("bad_input")
    new = {"price": price, "pay_to_name": name, "pay_phone": phone, "free_first": first}
    old = {k: e[k] for k in new} if e else dict.fromkeys(new)
    if new == old:
        return {}
    if not (org["official"] or org["top_at"] or price is None) or not can(con, v, org["id"], "money"):  # a club that lost the ✓ may still go free
        raise ApiError("forbidden", "price")
    if e and any(new[k] != old[k] for k in ("price", "pay_to_name", "pay_phone")) \
            and one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", e["id"]):
        raise ApiError("conflict", "paid")  # someone has paid by these details already
    if v.lent_full and v.staff_org == org["id"] and price is not None and (new["pay_to_name"], new["pay_phone"]) != (old["pay_to_name"], old["pay_phone"]):
        # the creator from Admin sets or changes the club's payee as its President would: the owner's log
        # keeps what it was and what it became, so a payment sent elsewhere can be traced
        log_action(con, v.id, "staff_kaspi", f"org:{org['id']}", json.dumps({"event": e["id"] if e else None, "was": {"name": old["pay_to_name"], "phone": old["pay_phone"]},
                                                                            "now": {"name": name, "phone": phone}}, ensure_ascii=False))
    return new


# a partner's name must not pass for KBTU's own: KBTU, DMP, a council, a school (en, ru)
GUEST_BANNED = re.compile(r"kbtu|\u043a\u0431\u0442\u0443|dmp|\u0434\u043c\u043f|council|\u0441\u043e\u0432\u0435\u0442|school", re.I)
HTTPS = re.compile(r"https://[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?")


def _partner(con, v: Viewer, body: dict, org: sqlite3.Row, e: sqlite3.Row | None = None) -> dict:
    """A partner's event (such as the Incubator's Halloween party): guestHost names the outside host, shown as
    "With <host>" (the club stays the one accountable), externalUrl is where people sign up. Only an official club's
    organizers or DMP set it, and not once people have signed up here. Absent keeps both."""
    if "guestHost" not in body:
        return {}
    host = " ".join(str(body.get("guestHost") or "").split()) or None
    url = str(body.get("externalUrl") or "").strip() or None
    if host and not (len(host) <= 60 and not GUEST_BANNED.search(host) and url and len(url) <= 500 and HTTPS.fullmatch(url)):
        raise ApiError("bad_input", "partner")
    # off again: its link goes with it; an older event's own external_url stays
    new = {"guest_host": host, "external_url": url if host else None if e is None or e["guest_host"] else e["external_url"]}
    old = {k: e[k] for k in new} if e else dict.fromkeys(new)
    if new == old:
        return {}
    if not (org["official"] or org["top_at"] or overseer(con, v) or host is None):  # off again needs no ✓ (a club that lost it)
        raise ApiError("forbidden", "partner")
    if host and e and one(con, "SELECT 1 FROM registrations WHERE event_id = ?", e["id"]):
        raise ApiError("conflict", "taken")
    return new


def _partner_ok(f: dict, e: sqlite3.Row | None = None) -> None:
    """A partner's event has no tickets: no price, public, not a meeting (the link out is the only way in). Late sign-up
    likewise: free, uncapped, public, ours (no receipt judged at the door, no waitlist nobody leaves)."""
    get = lambda k: f[k] if k in f else e[k] if e else None  # noqa: E731
    if get("guest_host") and (get("price") or get("meeting") or (get("visibility") or "public") != "public"):
        raise ApiError("bad_input", "partner")
    if get("late_signup") and (get("price") or get("seats") is not None or get("meeting") or (get("visibility") or "public") != "public"
                               or get("guest_host") or get("external_url")):
        raise ApiError("bad_input", "late")


def _school_only(org: sqlite3.Row, on: object) -> str | None:
    """"Only for <school>": a school's own org alone, and only its own school (its slug, account.school_slug's);
    off (None) is always allowed, so it can be switched off later."""
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    if not on:
        return None
    if org["kind"] != "school" or org["slug"] not in {s["slug"] for s in SCHOOLS}:
        raise ApiError("forbidden", "school")
    return org["slug"]


def _own_tr(body: dict, f: dict) -> dict:
    """The announcement came in all three languages (the fill's `tr`, assistant.filled): the club's own texts are kept
    as the event's translations, so the AI never translates it. Only all three and only for the very text being saved
    (the editor drops `tr` once the title or description is retyped); anything else: nothing, the AI's turn as ever."""
    tr, langs = body.get("tr"), ("ru", "kk", "en")
    if not isinstance(tr, dict) or tr.get("lang") not in langs:
        return {}
    out = {}
    for k in langs:
        if k == tr["lang"]:
            continue
        x = tr.get(k)
        title, desc = (x.get("title"), x.get("description")) if isinstance(x, dict) else (None, None)
        if not isinstance(title, str) or not isinstance(desc, str) or not title.strip():
            return {}
        out[k] = {"title": " ".join(title.split())[:80], "description": desc.strip()[:2000] if f["description"] else ""}
    return {"i18n": json.dumps(out, ensure_ascii=False), "lang": tr["lang"]}


DRAFTS_A_DAY = 5  # a member's own (without the "events" right): each one is the President's and the Vices' to read


def create_event(con, v: Viewer, oid: int, body: dict, *, guest_list: bool = False) -> dict:
    """A draft. The "events" right publishes it; any other member of the club sends theirs to its President and Vices
    (submit_event), and it stays theirs to edit until one of them approves it."""
    member = not can(con, v, oid, "events")
    if member and not at_least(role_in(con, v, oid), "member"):
        raise ApiError("forbidden")
    org = _org(con, oid)
    f = {**clean_event(body, bool(org["can_oversee"])), **_pay(con, v, body, org), **_partner(con, v, body, org), **evteams.settings(body)}
    f |= online_fields(body, None)
    if body.get("schoolOnly"):
        f["school"] = _school_only(org, True)
    _partner_ok(f)
    evteams.settings_ok(con, f)
    _meeting_ok(con, v, oid, f, bool(f.get("price")))
    f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, None), _focus(body, None), _memo(body, None) if org["official"] or org["top_at"] else None
    f["video_id"], f["wide_video_id"] = _video(con, v, body, None), _video(con, v, body, None, "wideVideoId")
    f.update(_own_tr(body, f))
    if guest_list:
        f.update(guest_list=1, age_check=1)
    with tx(con):  # bad slides leave no draft behind
        if member and one(con, "SELECT COUNT(*) FROM events WHERE org_id = ? AND created_by = ? AND created_at > ?", oid, v.id, core.now() - 86400)[0] >= DRAFTS_A_DAY:
            raise ApiError("rate_limited", "drafts")
        cur = con.execute(f"""INSERT INTO events (org_id, status, {', '.join(f)}, tint, created_by, created_at, updated_at)
            VALUES (?, 'draft', {', '.join('?' * len(f))}, ?, ?, ?, ?)""", (oid, *f.values(), shade(f["color"]), v.id, core.now(), core.now()))
        e = one(con, "SELECT * FROM events WHERE id = ?", cur.lastrowid)
        _slides(con, v, body, e, f["cover_file_id"])
        _cover_by(con, v, body, e["id"], f["cover_file_id"], None)
        if "santa" in body:
            santa.set_on(con, e["id"], body["santa"])
        santa.check_event(con, e["id"], f)
    return full(con, v, e)


def staff_create_event(con, v: Viewer, oid: int, body: dict, via: str = "admin", *, guest_list: bool = False) -> dict:
    """A club's draft made for it by the app's admin (Admin, X-Staff-Org) or the operator (kbtu.admin, via "server"):
    v carries staff_org = oid. Every rule is create_event's; never the money (the club sets its price and Kaspi details
    itself in Studio), whatever v's own role in the club. The owner's log names who, the club and the event."""
    if v.role != "admin" or v.staff_org != oid:
        raise ApiError("forbidden", "staff")
    # the creator (lent_full) has every option its President has; anyone else makes a plain public free event alone: the
    # money, the team's meetings, its volunteers, a leaders' call and the DMP memo are the club's own
    if not v.lent_full and any(body.get(k) is not None for k in ("price", "payToName", "payPhone", "freeFirst")):
        raise ApiError("forbidden", "price")
    if not v.lent_full and (body.get("visibility") not in (None, "public") or any(body.get(k) for k in ("meeting", "forBoard", "meetingTag", "leadersFrom", "volunteers"))):
        raise ApiError("forbidden", "plain")
    org = _org(con, oid)
    partner = bool(body.get("guestHost"))
    if org["status"] != "active" or partner and not (org["official"] or org["top_at"]):  # a partner's link out: a recognised club's alone here
        raise ApiError("forbidden", "partner" if org["status"] == "active" else "staff")
    with tx(con):
        e = create_event(con, v, oid, body if v.lent_full else {k: x for k, x in body.items() if k != "memo"}, guest_list=guest_list)
        log_action(con, v.id, "staff_create", f"event:{e['id']}", json.dumps({"org": oid, "via": via, **({"partner": True} if partner else {})}))
        _log_full(con, v, oid, e["id"], body)
    return e


# what the creator's lent_full adds to staff's plain event: each one set names him and the club in the owner's log
FULL_ONLY = ("price", "freeFirst", "volunteers", "guestHost", "memo", "videoId", "wideVideoId", "meeting", "forBoard", "meetingTag", "leadersFrom")


def _log_full(con, v: Viewer, oid: int, eid: int, body: dict) -> None:
    got = {k: body[k] for k in FULL_ONLY if body.get(k)} | ({"visibility": body["visibility"]} if body.get("visibility") not in (None, "public") else {})
    if v.lent_full and got:
        log_action(con, v.id, "staff_full", f"org:{oid}", json.dumps({"event": eid, **got}, ensure_ascii=False))


SLIDES = 9   # Limit the carousel to ten photos including the cover.


def _slides(con, v: Viewer, body: dict, e: sqlite3.Row, cover: int | None) -> None:
    """The editor's slideIds: absent keeps, [] clears; each one already on this event (a co-organizer's) or my own upload."""
    if "slideIds" not in body:
        return
    ids = body["slideIds"]
    if not isinstance(ids, list) or len(ids) > SLIDES or len(set(ids)) != len(ids) \
            or any(not isinstance(i, int) or isinstance(i, bool) for i in ids) or (cover is not None and cover in ids):
        raise ApiError("bad_input")
    for i in ids:
        if not one(con, """SELECT 1 FROM event_slides WHERE event_id = ? AND file_id = ?
                UNION ALL SELECT 1 FROM files WHERE id = ? AND kind = 'event_cover' AND owner_id = ?""", e["id"], i, i, v.id):
            raise ApiError("bad_input")
    con.execute("DELETE FROM event_slides WHERE event_id = ?", (e["id"],))
    con.executemany("INSERT INTO event_slides (event_id, pos, file_id) VALUES (?, ?, ?)", [(e["id"], n, i) for n, i in enumerate(ids)])
    core._SHARED.pop(("event", e["id"]), None)  # the Afisha's card shows them (other workers: core.SHARED_TTL)


def update_event(con, v: Viewer, eid: int, body: dict) -> dict:
    org = one(con, "SELECT o.* FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ?", eid)
    f = clean_event(body, bool(org and org["can_oversee"]))
    with tx(con):
        e = _draft_event(con, v, eid)
        if e["status"] == "cancelled":
            raise ApiError("closed")
        f |= _pay(con, v, body, org, e) | _partner(con, v, body, org, e) | evteams.settings(body) | online_fields(body, e["online"])
        if "schoolOnly" in body:
            f["school"] = _school_only(org, body["schoolOnly"])
        _partner_ok(f, e)
        evteams.settings_ok(con, f, e)
        get = lambda k: f[k] if k in f else e[k]  # noqa: E731
        if (get("visibility") != "public" or get("meeting") or get("guest_host")) \
                and one(con, "SELECT 1 FROM event_cohosts WHERE event_id = ? AND status != 'declined'", eid):
            raise ApiError("bad_input", "cohost")  # a co-host only on a public event (cohosts.py): remove it first
        _meeting_ok(con, v, e["org_id"], f, bool(f["price"] if "price" in f else e["price"]), (e["meeting"], e["meeting_tag"], e["for_board"]), e["visibility"])
        if f["seats"] is not None and f["seats"] < taken(con, eid):
            raise ApiError("conflict")  # seats can't drop below who is already in
        if f["needs_phone"] and not e["needs_phone"] and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND status != 'cancelled'", eid):
            raise ApiError("conflict", "needs_phone")  # those in never agreed to give it here (the export sends it)
        f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, e["cover_file_id"]), _focus(body, e["cover_focus"]), _memo(body, e["memo"]) if org and (org["official"] or org["top_at"]) and (v.lent_full or not v.staff_org) else e["memo"]  # the admin from Admin never touches the club's memo (the creator as its President)
        f["video_id"], f["wide_video_id"] = _video(con, v, body, e["video_id"]), _video(con, v, body, e["wide_video_id"], "wideVideoId")
        _slides(con, v, body, e, f["cover_file_id"])
        _cover_by(con, v, body, eid, f["cover_file_id"], e["cover_file_id"])
        if "santa" in body:  # Secret Santa's switch (santa.py); left out: kept
            santa.set_on(con, eid, body["santa"])
        santa.check_event(con, eid, f)
        if (f["memo"], f["starts_at"], f["ends_at"]) != (e["memo"], e["starts_at"], e["ends_at"]):
            f["memo_sent_at"] = f["memo_sent_by"] = None  # changed requests go to DMP again
        if (f["title"], f["description"]) != (e["title"], e["description"]):
            f["i18n"], f["lang"], f["ai_tries"] = None, None, 0  # translated again (ai.py)
        f.update(_own_tr(body, f))
        con.execute(f"UPDATE events SET {', '.join(k + ' = ?' for k in f)}, tint = ?, updated_at = ? WHERE id = ?",
                    (*f.values(), shade(f["color"]), core.now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if not after["guest_list"] and e["price"] and not after["price"]:  # free now: whoever was about to pay is simply in
            for (uid,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
                con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE event_id = ? AND user_id = ?", (core.now(), eid, uid))
                evteams.paid(con, one(con, "SELECT id FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)[0])
                _remind(con, uid, after)
        _changed(con, v, e, after)
        _log_full(con, v, e["org_id"], eid, body)
        cohost_changed(con, e, after)
        promote(con, after)
    return full(con, v, after)


def _changed(con, v: Viewer, e: sqlite3.Row, after: sqlite3.Row) -> None:
    """Who hears that a published event moved (PLAN "Place and time", §4.9): the room DMP gave for a place to be confirmed,
    or one KBTU room for another, tells nobody (the 2-hour reminder shows it; at once for those with reminders off);
    another venue or a new time tells them, edits within 10 minutes in one message (the bot reads the event when it
    sends); within 2 hours of the start or during it, at once and only to those not checked in. A new place also gets a
    line in the event's Updates."""
    eid, moved = e["id"], e["starts_at"] != after["starts_at"]
    placed = (e["place"], e["place_url"], e["online"]) != (after["place"], after["place_url"], after["online"])
    if e["status"] != "published" or not (moved or placed):
        return
    soon = core.now() >= after["starts_at"] - 2 * 3600
    quiet = not moved and not e["place_url"] and not after["place_url"] and after["place"]  # a room on campus: TBA -> room, room -> room
    for r in rows(con, """SELECT r.user_id, r.checked_in_at, u.n_remind FROM registrations r JOIN users u ON u.id = r.user_id
            WHERE r.event_id = ? AND r.status IN ('going','hold','waitlist')""", eid):
        if moved:
            con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (r[0], f"event:{eid}:%"))
            _remind(con, r[0], after)
        if soon and r["checked_in_at"] or quiet and not soon and r["n_remind"]:
            continue
        if not one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'event_changed' AND ref LIKE ? AND sent_at IS NULL", r[0], f"event:{eid}:%"):
            notify(con, r[0], "event_changed", f"event:{eid}:{after['updated_at']}", after=core.now() if soon or moved else core.now() + 600)  # always on (§4.9)
    if placed and after["place"]:
        con.execute("INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (?, ?, ?, ?)", (eid, v.id, f"📍 → {after['place']}", core.now()))


def change_place(con, v: Viewer, eid: int, place: object) -> dict:
    """Studio's "Change room" during an event (rooms change on the spot): a KBTU room in one tap, the rules above."""
    text = " ".join(str(place or "").split())
    if not 0 < len(text) <= 80:
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published" or end_of(e) < core.now():
            raise ApiError("closed")
        con.execute("UPDATE events SET place = ?, place_url = NULL, online = NULL, updated_at = ? WHERE id = ?", (text, core.now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        _changed(con, v, e, after)
        cohost_changed(con, e, after)
    return full(con, v, after)


REVIEW_REASONS = ("details", "when", "cover", "repeat", "later")  # why a member's draft comes back: a list, never typed words


def submit_event(con, v: Viewer, eid: int) -> dict:
    """A member's own draft goes to the club's President and Vices: the bot tells each, Studio shows it on top."""
    with tx(con):
        e = _draft_event(con, v, eid)
        if e["status"] != "draft" or e["created_by"] != v.id or can(con, v, e["org_id"], "events"):
            raise ApiError("conflict")  # an organizer publishes theirs
        if e["starts_at"] <= core.now():
            raise ApiError("closed")
        con.execute("""INSERT INTO event_reviews (event_id, asked_at) VALUES (?, ?)
            ON CONFLICT (event_id) DO UPDATE SET asked_at = excluded.asked_at, reason = NULL, returned_at = NULL""", (eid, core.now()))
        for (uid,) in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice') AND user_id != ?", e["org_id"], v.id):
            notify(con, uid, "event_review", f"er:{eid}:{core.now() // 86400}")  # sent again after a return: one ping a day
    return full(con, v, e)


def review_event(con, v: Viewer, eid: int, ok: object, reason: object = None) -> dict:
    """The club's President or a Vice answers a member's draft: yes publishes it as their own Publish would, no sends it
    back with a reason from the list."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if not e or e["hidden_at"]:
            raise ApiError("not_found")
        if role_in(con, v, e["org_id"]) not in ("president", "vice"):
            raise ApiError("forbidden")
        if e["status"] != "draft" or not one(con, "SELECT 1 FROM event_reviews WHERE event_id = ? AND asked_at IS NOT NULL", eid):
            raise ApiError("conflict")
        if ok is True:
            out = _publish(con, v, e, True)
            con.execute("DELETE FROM event_reviews WHERE event_id = ?", (eid,))
            if e["created_by"] and e["created_by"] != v.id:
                notify(con, e["created_by"], "event_approved", f"ea:{eid}")
            return out
        if ok is not False or reason not in REVIEW_REASONS:
            raise ApiError("bad_input")
        con.execute("UPDATE event_reviews SET asked_at = NULL, reason = ?, returned_at = ? WHERE event_id = ?", (reason, core.now(), eid))
        if e["created_by"] and e["created_by"] != v.id:
            notify(con, e["created_by"], "event_returned", f"eb:{eid}:{core.now() // 86400}")
    return full(con, v, e)


def publish_event(con, v: Viewer, eid: int, *, announce: bool = True) -> dict:
    with tx(con):
        return _publish(con, v, _staff_event(con, v, eid, "events"), announce)


def _publish(con, v: Viewer, e: sqlite3.Row, announce: bool) -> dict:
    """A draft goes out (inside the caller's transaction): who hears it, and whether the club's followers did."""
    eid = e["id"]
    if e["status"] != "draft":
        raise ApiError("conflict")
    if e["starts_at"] <= core.now():
        raise ApiError("closed")
    con.execute("""UPDATE events SET status = 'published', published_at = ?, updated_at = ?, silent_publish = ?
        WHERE id = ?""", (core.now(), core.now(), int(not announce), eid))
    told = None
    if announce:
        if e["visibility"] == "leaders":  # §4.10: every invited leader hears at once (always on)
            for (uid,) in _invited_leaders(con, e, exclude=v.id):
                notify(con, uid, "leaders_invite", f"li:{eid}")
        if e["meeting"]:  # §2b: everyone expected hears at once (always on)
            for uid in _expected(con, e):
                if uid != v.id:
                    notify(con, uid, "meeting_invite", f"mi:{eid}")
        if e["visibility"] == "public" and not e["guest_host"]:  # subscribers hear about it (§7, can be turned off); a partner's: the feed only
            after = _tell_after(con, e)
            told = after is None
            if told:
                tell_followers(con, e, e["org_id"], v.id)
        cohost_tell(con, one(con, "SELECT * FROM events WHERE id = ?", eid), v.id)  # an accepted co-host's followers, by its own week
    out = full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))
    # Studio's toast says whether the followers heard, and if not, from when a next event may tell them
    return out if told is None else {**out, "told": told, "tellAfter": after}


TELL_EVERY = 7 * 86400  # a student initiative's followers hear of a new event once a week at most; an official club's of each


def tell_followers(con, e, oid: int, actor: int, payload: str = "{}") -> None:
    subscribers = rows(con, """SELECT s.user_id FROM subscriptions s JOIN users u ON u.id = s.user_id
        WHERE s.org_id = ? AND u.n_new_events = 1 AND s.user_id != ?""", oid, actor)
    for (uid,) in subscribers:
        if sees_school(con, uid, e):
            notify(con, uid, "new_event", f"event:{e['id']}", payload)
    # The cooldown depends on the subscriber list before school filtering. Zero overrides the historical fallback.
    if subscribers:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"told:{oid}", str(core.now())))
    else:
        con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '0')", (f"told:{oid}",))


def _tell_after(con, e: sqlite3.Row) -> int | None:
    """None: an event published now may tell the club's followers; else when the next one may. A club without the ✓:
    once per rolling week, from the last time they were told (meta told:<org>, so deleting a cancelled event buys no
    other), or before that was kept, its last public event published (cancelled ones too)."""
    if one(con, f"SELECT {FULL_TOOLS} FROM orgs WHERE id = ?", e["org_id"])[0]:  # a club at the top too; an office (DMP, the app's) is KBTU's own
        return None
    t = one(con, """SELECT COALESCE((SELECT CAST(value AS INTEGER) FROM meta WHERE key = ?), (SELECT MAX(published_at) FROM events
        WHERE org_id = ? AND id != ? AND visibility = 'public' AND guest_host IS NULL AND status != 'draft' AND silent_publish = 0))""",
            f"told:{e['org_id']}", e["org_id"], e["id"])[0]
    return t + TELL_EVERY if t and t + TELL_EVERY > core.now() else None


def cancel_event(con, v: Viewer, eid: int) -> dict:
    """The club's Head+, or the admin (before deleting someone's event: Admin → Clubs; audited)."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid) if v.role == "admin" else None
        if e and not can(con, v, e["org_id"], "events"):
            log_action(con, v.id, "event_cancel", f"event:{eid}")
        e = e or _staff_event(con, v, eid, "events")
        if e["status"] != "published":
            raise ApiError("conflict")
        con.execute("UPDATE events SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?", (core.now(), core.now(), eid))
        evteams.cancelled(con, eid)
        for r in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status IN ('going','hold','waitlist')", eid):
            notify(con, r[0], "event_cancelled", f"event:{eid}")
        con.execute("DELETE FROM bot_outbox WHERE kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (f"event:{eid}:%",))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def delete_event(con, v: Viewer, eid: int) -> tuple[list[str], list[str]]:
    """A draft, or a cancelled event (a test or a mistake shouldn't hang in Studio forever). Not one
    with payments: deleting it would take the receipts with it, the only record of money that changed hands.
    The admin may delete any event, paid and photographed too: a club asks him to remove a test (the
    button is in Admin only, its confirm names what goes). Returns the receipt images and photos to delete from disk:
    a receipt is personal and nobody could open it any more."""
    if v.role != "admin":
        e = _draft_event(con, v, eid)  # a member's own draft too
        if e["status"] not in ("draft", "cancelled"):
            raise ApiError("conflict")
        if one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", eid):
            raise ApiError("conflict", "paid")
    return _delete_event(con, eid)


def _delete_event(con, eid: int) -> tuple[list[str], list[str]]:
    with tx(con):
        con.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"evdel:{eid}", f"u18:{eid}"))
        con.execute("DELETE FROM bot_outbox WHERE kind = 'u18_leave' AND ref LIKE ?", (f"u18:{eid}:%",))
        paid = [r[0] for r in rows(con, """SELECT c.file_id FROM receipts c JOIN registrations r ON r.id = c.registration_id
            WHERE r.event_id = ?""", eid)]
        pics = [r[0] for r in rows(con, """SELECT file_id FROM event_photos WHERE event_id = ?
            UNION SELECT cover_file_id FROM events WHERE id = ? AND cover_file_id IS NOT NULL
            UNION SELECT file_id FROM event_slides WHERE event_id = ?
            UNION SELECT file_id FROM event_covers WHERE event_id = ? AND file_id IS NOT NULL""", eid, eid, eid, eid)]
        pics += [f for f in gallery.album_gone(con, eid) if f not in pics]  # a closed event's Gallery posts never turn public
        post = one(con, "SELECT channel_msg FROM events WHERE id = ?", eid)
        doc = _doc_paths(con, eid)
        for sl in rows(con, "SELECT slug, org_id FROM short_links WHERE event_id = ?", eid):  # they go with it (cascade)
            _keep_name(con, sl["slug"], sl["org_id"])
        if not con.execute("DELETE FROM events WHERE id = ?", (eid,)).rowcount:
            raise ApiError("not_found")
        # its channel post goes too (it stayed), with the copy in the discussion group: the bot's next
        # round deletes them (bot.post_channel), the event's row is gone by then
        thread = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"thread:{eid}")
        if post and post[0]:
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"channel_gone:{post[0]}", thread[0] if thread else ""))
        receipts = [p for f in paid for p in _drop_photo(con, f)]
        photos = [p for f in pics for p in _drop_unused(con, f)] + doc  # the rules' pages: the cascade took their row
    return receipts, photos


# ---------------------------------------------------------------- the event's document (its rules, a PDF)
# The PDF itself is never kept nor served: its pages are rendered to pictures once, in a child process with hard limits
# (pdfpages.py), and stored as photos are (media.store) under media/doc/ (served with a short cache: a removed
# document's pages must not live on in caches for a year), named by a random key so no hash ties them to the file.
DOC_BYTES = 5 * 1024 * 1024
DOC_PAGES = 30
DOC_SIDE = 1600              # media.store's longest side: a phone's full width, pinch to zoom
DOC_TITLE = 40
DOC_SECONDS = 20             # the whole document's rendering, wall time and CPU (30 plain pages: ~6 s on a laptop)
DOC_MEMORY = 1 << 30         # the child's address space


def doc_check(con, v: Viewer, eid: int) -> None:
    """Who may put or remove the event's document: who may edit the event; asked before the upload is read."""
    if _staff_event(con, v, eid, "events")["status"] == "cancelled":
        raise ApiError("closed")


def render_doc(data: bytes, root: Path) -> list[dict]:
    """The PDF's pages as stored pictures under root/doc/ (in the picture threads); a refusal or a failure leaves no
    file behind. BadImage: too_big | not_a_pdf | too_many_pages."""
    if len(data) > DOC_BYTES:
        raise media.BadImage("too_big")
    kept: list[str] = []
    try:
        # next to the database, not /tmp (as SQLite's temp files in the image); always removed
        with tempfile.TemporaryDirectory(dir=root.parent, prefix=".doc-") as tmp:
            try:
                files = pdfpages.run(data, Path(tmp), DOC_PAGES, DOC_SIDE, DOC_SECONDS, DOC_MEMORY)
            except ValueError as exc:
                raise media.BadImage(str(exc)) from None
            out = []
            for f in files:
                im = media.decode(f.read_bytes())  # the child's PNG through the photos' own checks
                key = secrets.token_bytes(32)
                sha = hashlib.sha256(key).hexdigest()
                kept.append(f"doc/{sha[:2]}/{sha}")  # before the files: a store that fails halfway is dropped too
                s = media.store(im, key, root / "doc")
                out.append({"path": f"doc/{s['path']}", "w": s["width"], "h": s["height"], "color": s["color"]})
            return out
    except BaseException:
        media.drop(root, kept)
        raise


def _doc_paths(con, eid: int) -> list[str]:
    r = one(con, "SELECT pages FROM event_docs WHERE event_id = ?", eid)
    return [p["path"] for p in json.loads(r[0])] if r else []


def put_doc(con, v: Viewer, eid: int, title: object, pages: list[dict]) -> tuple[dict, list[str]]:
    """The event's one document, new or replacing the old; returns the event and the old pages' files to delete."""
    # no control or format characters (direction marks, zero-width ones); none left: the app's own word ("Rules")
    title = " ".join("".join(c for c in str(title or "") if unicodedata.category(c) not in ("Cc", "Cf")).split())[:DOC_TITLE] or None
    with tx(con):
        doc_check(con, v, eid)
        gone = _doc_paths(con, eid)
        con.execute("INSERT OR REPLACE INTO event_docs (event_id, title, pages, created_at) VALUES (?, ?, ?, ?)",
                    (eid, title, json.dumps(pages), core.now()))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid)), gone


def drop_doc(con, v: Viewer, eid: int) -> list[str]:
    """Removes the event's document; its pages' files to delete."""
    with tx(con):
        doc_check(con, v, eid)
        gone = _doc_paths(con, eid)
        con.execute("DELETE FROM event_docs WHERE event_id = ?", (eid,))
    return gone


EVENT_UNDO = 86400  # Admin's delete: hidden at once, gone for good a day later (Admin → Done has the Undo till then)


def set_reg_until(con, v: Viewer, eid: int, until: object) -> dict:
    """Registration closes now ("now"), at a time up to the start, or stays open to the start (null): Admin's "Close
    registration" and its Undo (the editor's "Sign-up until" sets the same column)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] == "cancelled":
            raise ApiError("closed")
        at = core.now() if until == "now" else until
        # a late sign-up event takes sign-ups until its end: "now" closes it while it runs too
        last = end_of(e) if until == "now" and e["late_signup"] else e["starts_at"]
        if not (at is None or isinstance(at, int) and not isinstance(at, bool) and 0 < at <= last):
            raise ApiError("bad_input")
        if until != "now":  # a Santa game's deadline: an hour before its gifts day at the latest
            santa.check_event(con, eid, {"reg_until": at, "starts_at": e["starts_at"]})
        con.execute("UPDATE events SET reg_until = ?, updated_at = ? WHERE id = ?", (at, core.now(), eid))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def admin_delete_event(con, v: Viewer, eid: int) -> None:
    """The admin deletes a club's event (a test, a mistake; paid and photographed too): hidden from everyone at once
    (hidden_at), deleted with its receipts and photos by the bot's round after EVENT_UNDO (events_gone)."""
    if v.role != "admin":
        raise ApiError("forbidden")
    with tx(con):
        e = one(con, "SELECT id, title, status, hidden_at, COALESCE(ends_at, starts_at, 0) > ? AS ahead FROM events WHERE id = ?", core.now(), eid)
        if not e:
            raise ApiError("not_found")
        if deleting(con, eid):
            raise core.decided(con, f"event:{eid}")
        # people hold seats or paid for one still ahead: it's cancelled first (they hear it, seats and receipts stay); then deleted
        if e["status"] == "published" and e["ahead"] and one(con, """SELECT 1 FROM registrations WHERE event_id = ? AND status IN ('going', 'hold', 'waitlist')
                UNION ALL SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?""", eid, eid):
            raise ApiError("conflict", "cancel_first")
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"evdel:{eid}", json.dumps({"due": core.now() + EVENT_UNDO, "hidden": e["hidden_at"]})))
        con.execute("UPDATE events SET hidden_at = COALESCE(hidden_at, ?) WHERE id = ?", (core.now(), eid))
        log_action(con, v.id, "event_delete", f"event:{eid}", json.dumps({"title": e["title"]}))


def undo_delete_event(con, v: Viewer, eid: int) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")
    with tx(con):
        k = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"evdel:{eid}")
        if not k:
            raise ApiError("not_found")
        con.execute("UPDATE events SET hidden_at = ? WHERE id = ?", (json.loads(k[0])["hidden"], eid))
        log_action(con, v.id, "event_undo", f"event:{eid}")


def events_gone(con) -> tuple[list[str], list[str]]:
    """The bot's round: the admin's deletes past their Undo, gone for good; their receipts and photos (to delete)."""
    receipts: list[str] = []
    photos: list[str] = []
    for k, val in rows(con, "SELECT key, value FROM meta WHERE key LIKE 'evdel:%'"):
        if json.loads(val)["due"] <= core.now():
            con.execute("UPDATE events SET hidden_at = COALESCE(hidden_at, ?) WHERE id = ?", (core.now(), int(k[6:])))  # whatever undid the hide meanwhile
            try:
                r, p = _delete_event(con, int(k[6:]))
            except ApiError:  # gone meanwhile (its club's own delete)
                con.execute("DELETE FROM meta WHERE key = ?", (k,))
                continue
            receipts += r
            photos += p
    return receipts, photos


def attendees(con, v: Viewer, eid: int) -> list[dict]:
    """The host's event team; the co-host's sees short names only, no receipts or answers. Someone
    the organizers removed who had paid stays at the end ('cancelled'), their receipt a tap away for the refund, until
    they sign up again; a receipt counts only for the seat it was sent for (since the seat's created_at)."""
    e = _staff_event(con, v, eid, "events", cohost=True)
    paid = can(con, v, e["org_id"], "events")
    order = {"going": 0, "hold": 1, "waitlist": 2, "cancelled": 3}
    found = rows(con, f"""SELECT {PERSON_COLS}, r.status, r.checked_in_at, r.walk_in, r.checkin_manual, r.created_at AS at, r.free, r.invited_by, r.checked_in_by, r.answers,
            c.id AS rid, c.flags, c.reviewed_at, c.reviewed_by, ac.receipt_id IS NOT NULL AS auto,
            c.created_at AS sent_at, c.amount, c.receipt_no, c.sender_name, c.recipient_name, c.paid_at
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        LEFT JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id AND status = 'accepted' AND created_at >= r.created_at)
        LEFT JOIN receipt_auto_checks ac ON ac.receipt_id = c.id
        WHERE r.event_id = ? AND (r.status != 'cancelled' OR r.cancel_reason = 'removed' AND c.id IS NOT NULL)""", eid)
    ids = list({p["invited_by"] for p in found if p["invited_by"]})  # who brought them: "My link" or "Bring a friend" (EventManage's "Who brought")
    # the club's members only: a friend's invite between two outsiders isn't the club's business
    by = {p["id"]: person_ref(p) for p in rows(con, f"{PERSON} JOIN org_members m ON m.user_id = u.id AND m.org_id = ? WHERE u.id IN ({_qs(ids)})",
                                               one(con, "SELECT org_id FROM events WHERE id = ?", eid)[0], *ids)} if ids else {}
    # "came" for whoever brought them only when someone else checked them in: a member can mark their own friends at the door
    out = [{"person": person_ref(p), "by": by.get(p["invited_by"]), "byCame": bool(p["checked_in_at"] and p["checked_in_by"] != p["invited_by"]), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "status": p["status"],
            "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"]), "at": p["at"], "free": bool(p["free"]),
            "receipt": {"id": p["rid"], "flags": [x for x in p["flags"].split(",") if x], "reviewed": p["reviewed_at"] is not None, "at": p["sent_at"],
                        "auto": bool(p["auto"]) and p["reviewed_at"] is not None and p["reviewed_by"] is None,
                        "amount": p["amount"], "no": p["receipt_no"], "sender": p["sender_name"], "recipient": p["recipient_name"], "paidAt": p["paid_at"]}
            if p["rid"] and paid and not v.staff_org else None, "answers": json.loads(p["answers"]) if p["answers"] else None} for p in found]
    if not paid:  # the co-host: short names as at the door; no full names, answers or who brought them (the policy's organizer is the host)
        out = [{**a, "person": _door_ref(p), "fullName": short_name(p), "by": None, "byCame": False, "answers": None} for a, p in zip(out, found)]
    flagged = lambda a: bool(a["receipt"] and a["receipt"]["flags"] and not a["receipt"]["reviewed"])  # noqa: E731
    return sorted(out, key=lambda a: (not flagged(a), order[a["status"]], a["fullName"]))  # §4.3: flagged receipts first


def attendees_export(con, v: Viewer, eid: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    """The event and its people for the CSV (Head+, §3: an organizer sees contacts for their own event). Every export
    of personal data goes to the audit log."""
    need_student(v)
    e = _staff_event(con, v, eid, "events")
    # the phone only where this event asked for it (else one club's ask reaches every club's list)
    found = rows(con, """SELECT s.last_name, s.first_name, s.middle_name, s.last_lat, s.first_lat, s.middle_lat, u.tg_username, s.student_id, s.course, s.school, s.email,
            CASE WHEN e.needs_phone AND r.phone_shared THEN s.phone END AS phone,
            r.status, r.created_at, r.checked_in_at, r.walk_in, r.checkin_manual, r.answers
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        JOIN events e ON e.id = r.event_id
        WHERE r.event_id = ? AND r.status != 'cancelled' ORDER BY s.last_name, s.first_name""", eid)
    log_action(con, v.id, "attendees_export", f"event:{eid}", json.dumps({"rows": len(found)}))
    return e, found


REVEALS_A_DAY, REVEAL_AFTER = 40, 7 * 86400
ASK_DELAY = 90  # Delay delivery so bot workers have time to pick up the notification template during a deploy.
_REACH = ("attendee_contact", "attendee_ask")  # the audit log's lines for both, counted together against the cap


def _reach(con, v: Viewer, eid: int, uid: int) -> tuple[sqlite3.Row, bool, str, str]:
    """An organizer reaching one attendee (inside the caller's tx): the host club's own organizer (the receipts' right;
    not a co-host, not staff from Admin), the person holds a seat on this event (a ticket, or a hold waiting on its
    receipt), the event published (not a draft, not cancelled), up to a week after the end. (the attendee's users row,
    blocked either way, the audit target and data)."""
    if not v.student or v.staff_org:
        raise ApiError("forbidden")
    e = _staff_event(con, v, eid, "events")
    t = core.now()
    if e["status"] != "published" or e["hidden_at"] is not None or end_of(e) + REVEAL_AFTER < t:  # hidden by moderation: as the bot's check
        raise ApiError("closed")
    u = one(con, """SELECT u.id, u.tg_username FROM registrations r JOIN users u ON u.id = r.user_id WHERE r.event_id = ? AND r.user_id = ?
        AND (r.status = 'going' OR r.status = 'hold' AND r.hold_until >= ?)""", eid, uid, t)
    if uid == v.id or not u:
        raise ApiError("not_found")
    blocked = bool(one(con, "SELECT 1 FROM blocks WHERE (user_id = ? AND blocked_id = ?) OR (user_id = ? AND blocked_id = ?)", uid, v.id, v.id, uid))
    return u, blocked, f"user:{uid}", json.dumps({"event": eid})


def _asked(con, target: str, data: str) -> bool:
    """Any of the event's organizers already asked this person to write (one ask per person and event, whoever asks)."""
    return bool(one(con, "SELECT 1 FROM audit_log WHERE action = 'attendee_ask' AND target = ? AND data = ?", target, data))


def _count(con, v: Viewer, action: str, target: str, data: str) -> None:
    """One line of the audit log, within the 40 a day (both kinds together)."""
    if one(con, f"SELECT COUNT(*) FROM audit_log WHERE action IN {_REACH} AND actor_id = ? AND at > ?", v.id, core.now() - 86400)[0] >= REVEALS_A_DAY:
        raise ApiError("rate_limited")
    log_action(con, v.id, action, target, data)


def attendee_contact(con, v: Viewer, eid: int, uid: int) -> dict:
    """"Write in Telegram" on an attendee's row: one person's @username, asked for one at a time (never in the list).
    Each reveal is in the audit log, 40 a day per organizer (the same person and event again that day isn't counted
    twice). No username, or a block either way (never told apart): null, unlogged; asked: someone of the event's
    organizers already asked them to write."""
    with tx(con):  # the count and the new line in one write: two taps at once never pass the cap together
        u, blocked, target, data = _reach(con, v, eid, uid)
        if not u["tg_username"] or blocked:
            return {"username": None, "asked": _asked(con, target, data)}
        if not one(con, "SELECT 1 FROM audit_log WHERE action = 'attendee_contact' AND actor_id = ? AND target = ? AND data = ? AND at > ?",
                   v.id, target, data, core.now() - 86400):
            _count(con, v, "attendee_contact", target, data)
    return {"username": u["tg_username"]}


def attendee_ask(con, v: Viewer, eid: int, uid: int, nick: str | None) -> dict:
    """"Ask them to write to me", for someone the reveal gave no username: the bot sends them a template naming the
    event and the club, its button the organizer's own Telegram (he shows himself; nothing of theirs is shown). nick:
    his username as his signed session says now, kept with the message (the bot drops it if his changes). Once per
    person and event for the whole club, within the same 40 a day. A block either way goes exactly like a real ask on
    his side (the cap, the audit line, asked) and only the message stays unsent: a block never shows."""
    with tx(con):
        u, blocked, target, data = _reach(con, v, eid, uid)
        if not nick:
            raise ApiError("bad_input", "own_username")  # his button would have nowhere to go
        if u["tg_username"] and not blocked:
            raise ApiError("bad_input")  # they can be written to: no bot message in their chat for it
        if not _asked(con, target, data):
            _count(con, v, "attendee_ask", target, data)
            if not blocked:
                notify(con, uid, "org_ask", f"oa:{eid}:{v.id}", json.dumps({"nick": nick}), after=core.now() + ASK_DELAY)
    return {"asked": True}


def _walk_in(con, e: sqlite3.Row, uid: int, code: str, t: int, walk: bool = True) -> sqlite3.Row | str:
    """A badge QR at the door: someone who forgot to register, or was just passing by, comes in.
    A ticket they hold is checked in as usual; a free event registers them on the spot (walk_in); a paid one
    needs a ticket."""
    if e["status"] != "published":
        return "closed"
    if not one(con, "SELECT 1 FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ? AND u.qr_code = ? AND s.manual = 0 AND u.banned_at IS NULL", uid, code):
        return "not_found"
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)
    if r and r["status"] == "going":
        return r
    if e["guest_list"]:
        raise ApiError("guest_list")
    if not _visible(con, Viewer(uid, "user", True), e):
        return "not_found"
    if not walk:
        return "cancelled" if r else "not_found"
    if e["price"]:
        return "paid"
    if r and r["cancel_reason"] == "removed" and r["status"] == "cancelled":
        return "cancelled"  # the organizers took them off: back only by signing up again
    if r:  # waitlisted or cancelled earlier, at the door now
        renew_cancelled_ticket(con, e["id"], r)
        con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, hold_until = NULL, waitlisted_at = NULL, walk_in = 1, updated_at = ? WHERE id = ?",
                    (t, r["id"]))
    else:
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                    (e["id"], uid, _ticket_code(con, e["id"]), t, t))
    return one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)


def _admission_shut(con, e: sqlite3.Row, t: int) -> str | None:
    if e["status"] != "published" or e["hidden_at"] is not None or e["guest_host"] or one(
            con, "SELECT 1 FROM orgs WHERE id = ? AND status = 'hidden'", e["org_id"]):
        return "closed"
    return door_shut(e, t)


def screen_came(con, eid: int, uid: int, t: int) -> dict:
    """A counted scan of an event's big-screen QR (checkin.py): that person came, as the door scanner would say. A ticket
    they hold is checked in; a free public event registers them on the spot (walk_in); a paid one needs a ticket and a
    team-only one counts its members only, a leaders' meeting only those already on its list, except the DMP office's: whoever is invited comes in, and someone in the hall who isn't
    counts by the scan alone (no registration: it would hand them the event). Only within the door's window (as the scanner): a session started days off counts no one,
    nor does a hidden or a partner's event. Duplicate and flagged tickets are reported to the door."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e or _admission_shut(con, e, t):
        return {"done": False}
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
    if not r or r["status"] != "going":
        if e["guest_list"]:
            return {"done": False}
        dmp = e["visibility"] == "leaders" and one(con, "SELECT 1 FROM orgs WHERE id = ? AND slug = 'dmp'", e["org_id"])
        if not _visible(con, Viewer(uid, "user", True), e):
            return {"done": bool(dmp)}  # DMP may count the scan alone, without granting a seat or revealing the event
        if r and r["status"] == "cancelled" and r["cancel_reason"] == "removed":
            return {"done": False}  # the organizers took them off: back only by signing up again
        if e["price"] or e["visibility"] == "leaders" and not dmp:
            return {"done": False}
        if r:
            renew_cancelled_ticket(con, eid, r)
            con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, hold_until = NULL, waitlisted_at = NULL, walk_in = 1, updated_at = ? WHERE id = ?",
                        (t, r["id"]))
        else:
            con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                        (eid, uid, _ticket_code(con, eid), t, t))
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
    if r["checked_in_at"] is not None:
        return {"done": False, "already": r["checked_in_at"]}
    if not e["guest_list"] and e["price"] and flagged(con, r["id"]):
        return {"done": False, "flagged": True}
    _came(con, e, uid, lambda: con.execute("UPDATE registrations SET checked_in_at = ?, updated_at = ? WHERE id = ?", (t, t, r["id"])))
    return {"done": True}


def checkin(con, v: Viewer, eid: int, raw: str, admit: bool = False) -> dict:
    """The door scanner: a ticket (KBTU<code>) or a badge QR (§4.4). Says how late they are, for the organizer. A
    flagged receipt stops before anything is recorded (_held); `admit`: the organizer looked and lets them in."""
    with tx(con):
        e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("scan", "door")))
        t = core.now()
        if shut := _admission_shut(con, e, t):
            return {"result": shut}
        badge = PROFILE_QR.search(str(raw))
        if badge:  # a scanner-only helper lets in who is going, never registers anyone
            r = _walk_in(con, e, int(badge[1]), badge[2], t, walk=can(con, v, e["org_id"], "door") or co_runs(con, v, eid) or crew_kind(con, v, e) != "scan")
            if isinstance(r, str):
                return {"result": r}
        else:
            misses = one(con, "SELECT misses, last_at FROM door_misses WHERE event_id = ? AND user_id = ?", eid, v.id)
            recent = misses and misses["last_at"] > t - 60
            if recent and misses["misses"] >= 5:
                raise ApiError("rate_limited")
            c = re.sub(r"[\s-]+", "", str(raw)).upper()  # typed as "k7 m2", or the QR's KBTU<code> (KBTU-<code> on older tickets)
            # a code means something only within its event (seats._ticket_code): another event's is simply not found
            r = one(con, "SELECT * FROM registrations WHERE ticket_code IN (?, ?)", f"{eid}-{c}", f"{eid}-{c.removeprefix('KBTU')}")
            if not r or r["status"] != "going":
                con.execute("INSERT OR REPLACE INTO door_misses (event_id, user_id, misses, last_at) VALUES (?, ?, ?, ?)",
                            (eid, v.id, misses["misses"] + 1 if recent else 1, t))
                return {"result": "cancelled" if r else "not_found"}
        if r["user_id"] == v.id and not runs(con, v, e):  # as checkin_by_name (a walk-in rolls back)
            raise ApiError("forbidden")
        if (held := _held(con, v, e, r, admit)) is not None:
            return held
        if not r["checked_in_at"]:
            if not badge and misses:  # repeating a known ticket cannot clear the counter
                con.execute("DELETE FROM door_misses WHERE event_id = ? AND user_id = ?", (eid, v.id))
            _came(con, e, r["user_id"], lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, updated_at = ? WHERE id = ?",
                                                           (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"])),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": not e["guest_list"] and (can(con, v, e["org_id"], "door") or co_runs(con, v, eid)) and flagged(con, r["id"]),
                **_checkin_age(con, e, r["id"])}


def _checkin_age(con, e: sqlite3.Row, rid: int) -> dict:
    if not e["age_check"]:
        return {}
    mark = one(con, "SELECT adult FROM reg_age WHERE registration_id = ?", rid)
    return {"adult": bool(mark[0]) if mark else None}


def _held(con, v: Viewer, e: sqlite3.Row, r: sqlite3.Row, admit: bool) -> dict | None:
    """A paid seat whose receipt nobody reviewed, not in yet: the door hears it before anything is recorded. Its
    organizers (the events right, a co-host's team) may let them in after a look (`admit`);
    anyone else at the door (a member, a helper) is only told to call one, never that the receipt is flagged."""
    if r["checked_in_at"] or e["guest_list"] or not e["price"] or not flagged(con, r["id"]):
        return None
    org = can(con, v, e["org_id"], "events") or co_runs(con, v, e["id"])
    if admit and org:
        return None
    return {"result": "flagged" if org else "ask_org", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"])), "at": core.now(),
            "came": one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", e["id"])[0],
            "going": taken(con, e["id"]), "walkIn": False, "late": 0,
            **({"flagged": True} if org else {}), **_checkin_age(con, e, r["id"])}


def flagged(con, rid: int) -> bool:
    """The seat's receipt has warnings nobody reviewed (a duplicate, a short amount): the door looks at it first.
    A spot check or a receipt read in part ('spot', 'partial') isn't a warning: nothing wrong was found, the student walks in."""
    # only this seat's receipts: one from before a removal or a cancel (the seat's created_at restarts on a new sign-up) is the old seat's
    return one(con, """SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE c.registration_id = ? AND c.status = 'accepted'
        AND c.flags NOT IN ('', 'spot', 'partial') AND c.reviewed_at IS NULL AND c.created_at >= r.created_at""", rid) is not None


RATE_FOR = 7 * 86400   # a rating is taken from the end of the event this long
RATE_SHOW = 3          # the club sees the ratings from this many on, so a small club can't tell who wrote what


def _rating_open(e: sqlite3.Row) -> bool:
    end = end_of(e)
    return end <= core.now() <= end + RATE_FOR


def _rating_view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict:
    """What the event sheet shows about ratings: mine (and whether I may still give one: checked in, ended, within 7
    days), and for the club's Head+ the anonymous summary — average, the five counts, the comments, no names; under
    RATE_SHOW of them, only how many."""
    mine = one(con, "SELECT score FROM event_ratings WHERE event_id = ? AND user_id = ?", e["id"], v.id) if v.student else None
    came = v.student and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", e["id"], v.id)
    out = {"myRating": mine["score"] if mine else None, "canRate": bool(came) and _rating_open(e), "ratings": None}
    if head:
        rs = rows(con, "SELECT score, comment, created_at FROM event_ratings WHERE event_id = ? ORDER BY created_at DESC", e["id"])
        if 0 < len(rs) < RATE_SHOW:  # so few the club could tell who wrote what: the count alone
            out["ratings"] = {"avg": None, "count": len(rs), "dist": [], "comments": []}
        elif rs:
            out["ratings"] = {"avg": round(sum(r["score"] for r in rs) / len(rs), 1), "count": len(rs),
                              "dist": [sum(1 for r in rs if r["score"] == s) for s in range(1, 6)],
                              "comments": [{"score": r["score"], "body": r["comment"], "at": r["created_at"]} for r in rs if r["comment"]][:50]}
    return out


def rate_event(con, v: Viewer, eid: int, score: object, comment: object) -> dict:
    """One tap after the event: only those checked in, from the end until 7 days later;
    changing one's mind is fine. Anonymous to the club."""
    need_student(v)
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        raise ApiError("bad_input")
    text = str(comment or "").strip()[:300]
    with tx(con):
        e = _event(con, v, eid)
        if not _rating_view(con, v, e, False)["canRate"]:
            raise ApiError("forbidden")
        public_after = end_of(e) + RATE_FOR if e["status"] == "published" and not e["hidden_at"] and e["visibility"] == "public" and not e["school"] else None
        # MAX keeps NULL for a private vote and never moves a vote's original publication deadline earlier.
        con.execute("""INSERT INTO event_ratings (event_id, user_id, score, comment, created_at, public_after) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (event_id, user_id) DO UPDATE SET score = excluded.score, comment = excluded.comment,
            created_at = excluded.created_at, public_after = MAX(event_ratings.public_after, excluded.public_after)""",
                    (eid, v.id, score, text, core.now(), public_after))
    return full(con, v, e)


def dismiss_rating(con, v: Viewer, eid: int) -> None:
    """Quiet the in-app prompt across devices. The event's rating form still works."""
    need_student(v)
    with tx(con):
        e = _event(con, v, eid)
        if e["status"] != "published" or e["hidden_at"] or not _rating_open(e):
            raise ApiError("forbidden")
        if not con.execute("""UPDATE registrations SET rating_dismissed = 1
            WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL""", (eid, v.id)).rowcount:
            raise ApiError("forbidden")


def _ask_rating(con, uid: int, e: sqlite3.Row) -> None:
    """Checked in: an hour after the end the bot asks how it was (follows the reminders switch)."""
    notify(con, uid, "rate", f"rate:{e['id']}", after=end_of(e) + 3600)


INVITES_A_DAY = 30


def event_invites(con, v: Viewer, eid: int) -> list[dict]:
    """"Bring a friend" (§4.7): my friends and where each one stands with this event — to invite, invited by me, or
    going (only for those who show where they go, §3; the rest look invitable and the bot simply stays quiet)."""
    need_student(v)
    e = _event(con, v, eid)
    out = []
    # who's coming and whom I asked: read once for the list, not per friend
    signed = {r[0] for r in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status IN ('going', 'hold', 'waitlist')", eid)}
    invited = {r[0] for r in rows(con, "SELECT to_id FROM friend_invites WHERE from_id = ? AND event_id = ?", v.id, eid)}
    for p in rows(con, PERSON + " WHERE u.id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)", v.id, v.id):
        if not sees_school(con, p["id"], e):  # a school's own event: friends of another school aren't offered (no query for any other event)
            continue
        going, asked = p["show_going"] and p["id"] in signed, p["id"] in invited
        out.append({"person": person_ref(p), "state": "going" if going else "invited" if asked else "none"})
    rank = {"none": 0, "invited": 1, "going": 2}
    return sorted(out, key=lambda x: (rank[x["state"]], x["person"]["name"]))


def invite_friend(con, v: Viewer, eid: int, uid: object) -> list[dict]:
    """The bot brings my friend our card: "<name> invites you to <title>" + Open. Once per friend and event; public
    events that haven't started; 30 invites a day."""
    need_student(v)
    e = _event(con, v, eid)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid not in friend_ids(con, v.id) or not sees_school(con, uid, e):
        raise ApiError("forbidden")
    if e["status"] != "published" or e["starts_at"] <= core.now() or e["visibility"] != "public":
        raise ApiError("closed")
    if one(con, "SELECT COUNT(*) FROM friend_invites WHERE from_id = ? AND created_at > ?", v.id, core.now() - 86400)[0] >= INVITES_A_DAY:
        raise ApiError("rate_limited")
    if con.execute("INSERT OR IGNORE INTO friend_invites (from_id, to_id, event_id, created_at) VALUES (?, ?, ?, ?)", (v.id, uid, eid, core.now())).rowcount:
        notify(con, uid, "friend_invite", f"fi:{eid}:{v.id}")  # the bot skips it if they're already in by then
    return event_invites(con, v, eid)


ALBUM_EACH, ALBUM_TEAM, ALBUM_MAX = 10, 40, 300  # a guest's photos, the organizing team's (the photographer's set), all
ALBUM_FOR = 7 * 86400                            # photos are added from the start until a week after the end
PHOTO_REPORT_AT = 3                              # the third photo tells everyone who came (an hour after the end at the earliest)


# A photo a viewer may see, an album's or the Gallery's (its one ?: the viewer; `f` is the file): reported by me, or by
# PHOTO_HIDE people and not kept by a moderator, it's out. A photo taken down is out of event_photos altogether.
PHOTO_HIDE = 3  # three different people
PHOTO_SHOWN = f"""f.id NOT IN (SELECT r.target_id FROM reports r WHERE r.target = 'photo' AND r.status = 'open' GROUP BY r.target_id
                         HAVING (COUNT(DISTINCT r.reporter_id) >= {PHOTO_HIDE}  -- for everyone, unless a moderator already kept it
                                 AND NOT EXISTS (SELECT 1 FROM reports k WHERE k.target = 'photo' AND k.target_id = r.target_id AND k.status = 'dismissed'))
                             OR SUM(r.reporter_id = ?) > 0)"""


def _photo_by(f: sqlite3.Row) -> str | None:
    """Who added an album photo, all anyone is told: the nick or "First L."; nothing once their account is gone."""
    return f["nick"] or (f"{f['first_name']} {f['last_name'][:1]}" if f["first_name"] else None)


def _album_view(con, v: Viewer, e: sqlite3.Row) -> dict:
    """The guests' album. Students see it (guests don't: people's faces); who came adds
    photos, and so does the team; the one who added a photo or the club's Head+ take it out."""
    if not v.student:
        return {"photos": [], "canAddPhotos": False}
    head = can(con, v, e["org_id"], "events")
    # a Gallery post: its author (posted under their name, gallery.py) and when it was posted
    ps = rows(con, f"""SELECT f.*, p.added_by, g.user_id AS poster, g.created_at AS posted, s.first_name, s.last_name, u.nick
        FROM event_photos p JOIN files f ON f.id = p.file_id LEFT JOIN gallery_photos g ON g.file_id = p.file_id
        LEFT JOIN users u ON u.id = p.added_by LEFT JOIN students s ON s.user_id = p.added_by WHERE p.event_id = ?
        AND {PHOTO_SHOWN}
        ORDER BY COALESCE(f.taken_at, f.created_at), f.id""", e["id"], v.id)  # when each was taken, whoever added it when
    return {"photos": [{**media_shape(f), "canDelete": head or f["added_by"] == v.id, "by": _photo_by(f), "mine": f["added_by"] == v.id,
                        **({"uid": f["poster"], "at": f["posted"]} if f["poster"] else {})} for f in ps],
            "canAddPhotos": _album_room(con, v, e) > 0}


def _album_room(con, v: Viewer, e: sqlite3.Row) -> int:
    """How many more photos I may add to this event's album now."""
    if not v.student or e["status"] != "published" or not e["starts_at"] <= core.now() <= end_of(e) + ALBUM_FOR:
        return 0
    co = one(con, ACCEPTED, e["id"])
    team = at_least(role_in(con, v, e["org_id"]), "member") or bool(co and at_least(role_in(con, v, co["org_id"]), "member"))
    # any student, not only the checked-in: whoever dropped by adds theirs (owner: a gallery with few limits lives)
    mine = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ? AND added_by = ?", e["id"], v.id)["n"]
    total = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ?", e["id"])["n"]
    return max(0, min((ALBUM_TEAM if team else ALBUM_EACH) - mine, ALBUM_MAX - total))


def can_add_album_photo(con, v: Viewer, eid: int) -> bool:
    return _album_room(con, v, _event(con, v, eid)) > 0


def event_photo_file(con, uid: int, saved: dict) -> int:
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'event_photo' AND owner_id = ?", saved["sha256"], uid)
    if f:
        return f["id"]
    return con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color, taken_at)
        VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
            saved["path"], uid, core.now(), saved["color"], saved.get("taken"))).lastrowid


def attach_album_photo(con, eid: int, fid: int, uid: int) -> None:
    con.execute("""INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by)
        VALUES (?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM event_photos WHERE event_id = ?), ?)""", (eid, fid, eid, uid))


def add_album_photo(con, v: Viewer, eid: int, saved: dict) -> dict:
    e = _event(con, v, eid)
    if _album_room(con, v, e) <= 0:
        raise ApiError("forbidden")
    attach_album_photo(con, eid, event_photo_file(con, v.id, saved), v.id)
    if one(con, "SELECT COUNT(*) FROM event_photos WHERE event_id = ?", eid)[0] == PHOTO_REPORT_AT:  # the album has a story now
        for (uid,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL AND user_id != ?", eid, v.id):
            notify(con, uid, "photo_report", f"ph:{eid}", after=max(core.now(), end_of(e) + 3600))  # once per event (§7)
    return full(con, v, e)


def remove_album_photo(con, v: Viewer, eid: int, fid: int) -> tuple[dict, list[str]]:
    """Out of the album, by whoever added it or the club's team; its file goes from the disk when nothing else shows it
    (returned)."""
    e = _event(con, v, eid)
    p = one(con, "SELECT added_by FROM event_photos WHERE event_id = ? AND file_id = ?", eid, fid)
    if not p:
        raise ApiError("not_found")
    if p["added_by"] != v.id and v.role != "admin" and not can(con, v, e["org_id"], "events"):
        raise ApiError("forbidden")
    con.execute("DELETE FROM event_photos WHERE event_id = ? AND file_id = ?", (eid, fid))
    # a student's Gallery post of this event stays theirs, a plain KBTU photo now; of a closed event: gone with it
    gallery.album_gone(con, eid, fid)
    return full(con, v, e), _drop_unused(con, fid)


UPDATES_A_DAY = 3


def post_update(con, v: Viewer, eid: int, body: str) -> list[dict]:
    """An organizer's update (Head+): pinned under the event's title for everyone,
    and the bot tells the people going, holding a seat or waiting — with our template, never the organizer's words (§9).
    Three a day per event at most, so it stays news and never spam."""
    e = _staff_event(con, v, eid, "events")
    text = str(body or "").strip()
    if e["status"] != "published" or not 2 <= len(text) <= 300:
        raise ApiError("bad_input")
    if one(con, "SELECT COUNT(*) FROM event_updates WHERE event_id = ? AND created_at > ?", eid, core.now() - 86400)[0] >= UPDATES_A_DAY:
        raise ApiError("rate_limited")
    with tx(con):
        uid = con.execute("INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (?, ?, ?, ?)", (eid, v.id, text, core.now())).lastrowid
        for (who,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status IN ('going','hold','waitlist') AND user_id != ?", eid, v.id):
            notify(con, who, "event_update", f"upd:{uid}")
    return full(con, v, e)["updates"]


def delete_update(con, v: Viewer, eid: int, uid: int) -> None:
    _staff_event(con, v, eid, "events")
    if not con.execute("DELETE FROM event_updates WHERE id = ? AND event_id = ?", (uid, eid)).rowcount:
        raise ApiError("not_found")


UNDO = 600  # a check-in by name can be taken back this long (a wrong tap at the door)


def _door_ok(con, v: Viewer, e: sqlite3.Row) -> sqlite3.Row:
    """A department's (or the board's) team-only event: its door is for those it is for, and who runs the events."""
    if e["visibility"] == "members" and not for_me(con, v, e, role_in(con, v, e["org_id"])):
        raise ApiError("forbidden")
    return e


def _age_event(con, v: Viewer, eid: int, helper: tuple[str, ...]) -> sqlite3.Row:
    e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=helper))
    if not e["age_check"] or e["hidden_at"]:
        raise ApiError("not_found")
    if e["status"] != "published" or end_of(e) <= core.now():
        raise ApiError("closed")
    return e


def door_extra(con, v: Viewer, eid: int, step: object = None) -> dict:
    """Guests let in without the app (outsiders, their ID checked by eye): one anonymous count per event, +1 or -1 at
    the door; nobody is named or stored, so it asks no consent. Read by anyone at the door, changed while it is open."""
    if step is not None and step not in (1, -1):
        raise ApiError("bad_input")
    with tx(con):
        e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("scan", "door")))
        if step is not None:
            if e["status"] != "published" or e["hidden_at"] or door_shut(e, core.now()):
                raise ApiError("closed")
            con.execute("UPDATE events SET door_extra = max(0, door_extra + ?) WHERE id = ?", (step, eid))
        return {"extra": one(con, "SELECT door_extra FROM events WHERE id = ?", eid)[0]}


def let_in_pending(con, v: Viewer, eid: int, sid: object, surname: object, adult: object = None) -> dict:
    """The door lets in a ticket buyer from the organizers' list who isn't in the app (guests.let_in); with `adult`,
    the 18+ the door saw on their ID. Their ticket comes checked in when they sign in later."""
    if adult is not None and not isinstance(adult, bool):
        raise ApiError("bad_input")
    with tx(con):
        e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
        if not e["guest_list"]:
            raise ApiError("not_found")
        t = core.now()
        if door_shut(e, t):
            raise ApiError("closed")
        out = guests.let_in(con, eid, sid, surname, t)
        if adult is not None and e["age_check"]:
            guests.set_pending_age(con, eid, str(sid), adult)
            out["adult"] = adult
        return out


def pending_count(con, v: Viewer, eid: int) -> dict:
    _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
    return {**guests.pending_count(con, eid), "list": guests.door_list(con, eid)}


def tick_pending(con, v: Viewer, eid: int, key: object, adult: object = None, came: object = True) -> dict:
    """The door taps a name on the organizers' list (guests.tick), within the door's window."""
    with tx(con):
        e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
        if door_shut(e, core.now()):
            raise ApiError("closed")
        return guests.tick(con, eid, key, core.now(), adult if e["age_check"] else None, came is not False)


def mark_age(con, v: Viewer, eid: int, uid: object, adult: object) -> dict:
    if type(uid) is not int or not 0 < uid < 2**63 or not isinstance(adult, bool):
        raise ApiError("bad_input")
    with tx(con):
        e = _age_event(con, v, eid, ("scan", "door"))
        if uid == v.id and not runs(con, v, e):
            raise ApiError("forbidden")
        r = one(con, """SELECT id FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'
            AND checked_in_at IS NOT NULL""", eid, uid)
        if not r:
            raise ApiError("not_found")
        guests.set_age(con, r[0], adult, v.id)
    return {"adult": adult}


def notify_minors(con, v: Viewer, eid: int) -> dict:
    with tx(con):
        e = _age_event(con, v, eid, ("door",))
        if door_shut(e, core.now()):
            raise ApiError("closed")
        t, key = core.now(), f"u18:{eid}"
        last = one(con, "SELECT value FROM meta WHERE key = ?", key)
        if last and t - int(last[0]) < 600:
            raise ApiError("rate_limited")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(t)))
        recipients = rows(con, """SELECT r.user_id FROM registrations r JOIN reg_age a ON a.registration_id = r.id
            WHERE r.event_id = ? AND r.status = 'going' AND r.checked_in_at IS NOT NULL AND a.adult = 0""", eid)
        for (uid,) in recipients:
            notify(con, uid, "u18_leave", f"u18:{eid}:{t}")
    return {"count": len(recipients)}


def door(con, v: Viewer, eid: int) -> list[dict]:
    """The door list for check-in by name (Member+, like the scanner; §3: a Member sees short names only): who is going,
    the ones still to come first."""
    e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
    found = rows(con, f"""SELECT {PERSON_COLS}, r.checked_in_at, r.walk_in, r.checkin_manual, r.door_team, a.adult FROM registrations r
        JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id LEFT JOIN reg_age a ON a.registration_id = r.id
        WHERE r.event_id = ? AND r.status = 'going'""", eid)
    out = [{"person": _door_ref(p), "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"]), "team": p["door_team"],
            **({"adult": None if p["adult"] is None else bool(p["adult"])} if e["age_check"] else {})} for p in found]
    if _team_door(e):  # §2b: everyone expected is on the list, answered or not
        rest = [u for u in _expected(con, e) if u not in {p["id"] for p in found}]
        out += [{"person": _door_ref(p), "checkedInAt": None, "walkIn": False, "manual": False,
                 **({"adult": None} if e["age_check"] else {})}
                for p in (rows(con, PERSON + f" WHERE u.id IN ({_qs(rest)})", *rest) if rest else [])]
    return sorted(out, key=lambda a: (a["checkedInAt"] is not None, -(a["checkedInAt"] or 0), a["person"]["name"]))


def checkin_by_name(con, v: Viewer, eid: int, uid: int, admit: bool = False) -> dict:
    """No QR (a dead phone): a person going to the event is checked in by hand from the door list (§4.4). The same answer
    as the scanner; marked "by hand" for the organizer and the CSV."""
    with tx(con):
        e = _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
        if uid == v.id and not runs(con, v, e):
            raise ApiError("forbidden")  # the door is every member's: marking myself as came is for whoever runs the event
        t = core.now()
        if shut := _admission_shut(con, e, t):
            return {"result": shut}
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if e["guest_list"] and (not r or r["status"] != "going"):
            raise ApiError("guest_list")
        if _team_door(e) and (not r or r["status"] != "going") and (uid in _expected(con, e) or (e["meeting_tag"] or e["for_board"]) and one(  # §2b: came anyway
                con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ? AND role IN ('president', 'vice')", e["org_id"], uid)):  # a department's: its Vice+ too
            if r:
                renew_cancelled_ticket(con, eid, r)
                con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, walk_in = 1, updated_at = ? WHERE id = ?", (t, r["id"]))
            else:
                con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                            (eid, uid, _ticket_code(con, eid), t, t))
            r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if not r:
            return {"result": "not_found"}
        if r["status"] != "going":
            return {"result": "cancelled"}
        if (held := _held(con, v, e, r, admit)) is not None:
            return held
        if not r["checked_in_at"]:
            _came(con, e, uid, lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, checkin_manual = 1, updated_at = ? WHERE id = ?",
                                                  (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", uid)),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": not e["guest_list"] and (can(con, v, e["org_id"], "door") or co_runs(con, v, eid)) and flagged(con, r["id"]),
                **_checkin_age(con, e, r["id"])}


def undo_checkin(con, v: Viewer, eid: int, uid: int) -> None:
    """Take back a check-in by name made in the last 10 minutes (a scanned ticket stays: it proves the person came). One
    that came from a walk-in's typed name (link_door_guests) takes that name with it: it wasn't them, and a name left
    linked would keep saying they came (PLAN A19 "left")."""
    _door_ok(con, v, _staff_event(con, v, eid, "door", cohost=True, helper=("door",)))
    with tx(con):
        cur = con.execute("""UPDATE registrations SET checked_in_at = NULL, checked_in_by = NULL, checkin_manual = 0, updated_at = ?
            WHERE event_id = ? AND user_id = ? AND checkin_manual = 1 AND checked_in_at > ?""", (core.now(), eid, uid, core.now() - UNDO))
        if not cur.rowcount:
            raise ApiError("conflict")
        con.execute("DELETE FROM door_guests WHERE event_id = ? AND user_id = ?", (eid, uid))


# Match a stored walk-in to an account only after Microsoft verifies the student's name.


def _norm_name(s: str) -> str:
    """"Ivanov  Ivan" and "ivan ivanov" are one person; Cyrillic yo is e."""
    return " ".join(sorted(s.lower().replace("\u0451", "\u0435").split()))


GUEST_DAYS = 30 * 86400  # a walk-in's name waits this long for its student, then goes


# ponytail: remove link_door_guests, GUEST_DAYS and _norm_name once all pending walk-ins pass the 30-day limit.
def link_door_guests(con, uid: int) -> None:
    """A student confirmed by Microsoft (their names are KBTU's): a walk-in of the last 30 days with their full name was
    them, only if no other student has that name (two Aruzhan Serikovas and nobody can
    tell). Only where the door rules still hold: a public free event, not banned from the club; a
    registration they had stays theirs (cancelled or waitlisted: they said no, the name is left alone)."""
    s = one(con, "SELECT first_name, last_name FROM students WHERE user_id = ?", uid)
    if not s or not s["first_name"] or not s["last_name"]:
        return
    norm = _norm_name(f"{s['first_name']} {s['last_name']}")
    twins = sum(_norm_name(f"{r[0]} {r[1]}") == norm for r in rows(con, """SELECT first_name, last_name FROM students
        WHERE user_id != ? AND first_name IS NOT NULL AND last_name IS NOT NULL""", uid))  # ponytail: a scan per confirmation, a norm column if it grows
    if twins:
        return
    with tx(con):
        me = Viewer(uid, one(con, "SELECT role FROM users WHERE id = ?", uid)[0], True)
        for g in rows(con, """SELECT g.*, e.org_id FROM door_guests g JOIN events e ON e.id = g.event_id WHERE g.norm = ? AND g.user_id IS NULL
                AND g.created_at > ? AND e.status = 'published' AND e.price IS NULL AND e.visibility = 'public' AND e.guest_list = 0
                AND NOT EXISTS (SELECT 1 FROM org_bans b WHERE b.org_id = e.org_id AND b.user_id = ?)
                AND NOT EXISTS (SELECT 1 FROM door_guests y WHERE y.event_id = g.event_id AND y.user_id = ?)""", norm, core.now() - GUEST_DAYS, uid, uid):
            if g["added_by"] == uid and not can(con, me, g["org_id"], "events"):
                continue  # my own name typed at the door: no self check-in (as checkin_by_name), whoever runs the event may
            r = one(con, "SELECT id, status, checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", g["event_id"], uid)
            if r and (r["status"] != "going" or r["checked_in_at"]):
                continue
            con.execute("UPDATE door_guests SET user_id = ? WHERE id = ?", (uid, g["id"]))
            if not r:
                con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at)
                    VALUES (?, ?, 'going', ?, 1, ?, ?)""", (g["event_id"], uid, _ticket_code(con, g["event_id"]), core.now(), core.now()))
            # as a check-in at the door: the rating ask and the levels it brings (written directly, they would be lost)
            _came(con, one(con, "SELECT * FROM events WHERE id = ?", g["event_id"]), uid, lambda g=g: con.execute(
                """UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, checkin_manual = 1, updated_at = ? WHERE event_id = ? AND user_id = ?""",
                (g["created_at"], g["added_by"], core.now(), g["event_id"], uid)))


# ---------------------------------------------------------------- the door's opening

def open_door(con, v: Viewer, eid: int) -> dict:
    """The host club's President or a Vice opens the door early, from 4 h before the start (it opens by itself at T-30,
    core.door_at). Their role, not a right: the app's admin (X-Staff-Event lends "events") never opens it; the creator
    from Admin does, as its President (core.role_in). Every guest
    hears of it (door_round); once open it stays open."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if not e or role_in(con, v, e["org_id"]) not in ("president", "vice"):
            raise ApiError("forbidden")
        t = core.now()
        if e["status"] != "published" or e["hidden_at"] or e["guest_host"] or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            raise ApiError("closed")
        if t < e["starts_at"] - DOOR_EARLY:
            raise ApiError("closed", "early")
        if door_shut(e, t) == "not_open":
            con.execute("UPDATE events SET door_open_at = ?, updated_at = ? WHERE id = ?", (t, t, eid))
            log_action(con, v.id, "door_open", f"event:{eid}", json.dumps({"before": e["starts_at"] - t}))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def door_round(con) -> None:
    """The postman's round (bot._chores): once the open door has let its first person in (a scan, by name, the big
    screen, a walk-in: the organizers are at the door), each guest going and not yet in hears it once,
    until the start (a moved event: event_changed tells). Only events starting within DOOR_EARLY are read."""
    t = core.now()
    for e in rows(con, """SELECT * FROM events e WHERE status = 'published' AND hidden_at IS NULL AND COALESCE(guest_host, '') = ''
            AND starts_at > ? AND starts_at <= ?
            AND COALESCE(door_audience, 'both') != 'team'  -- a team-only door: no guest is told
            AND EXISTS (SELECT 1 FROM registrations r WHERE r.event_id = e.id AND r.checked_in_at IS NOT NULL)""", t, t + DOOR_EARLY):
        if door_shut(e, t):
            continue
        ref = f"door:{e['id']}"
        guests = rows(con, """SELECT r.user_id FROM registrations r WHERE r.event_id = ? AND r.status = 'going' AND r.checked_in_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = r.user_id AND b.kind = 'door_open' AND b.ref = ?)""", e["id"], ref)
        if guests:
            with tx(con):  # one commit for a hall of guests
                for (uid,) in guests:
                    notify(con, uid, "door_open", ref)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import autoev, core, evteams, gallery, guests, santa  # noqa: E402
from .account import _drop_photo, _drop_unused, me  # noqa: E402
from .clubs import SCHOOLS, _keep_name, org, people  # noqa: E402
from .cohosts import ACCEPTED, changed as cohost_changed, co_runs, runs, tell as cohost_tell  # noqa: E402
from .crew import kind as crew_kind  # noqa: E402
from .seats import _visible, for_me, sees_school  # noqa: E402
from .daily import _memo  # noqa: E402
from .profiles import _came  # noqa: E402
from .queues import _video  # noqa: E402
from .seats import _event, _remind, _ticket_code, end_of, notify, promote, renew_cancelled_ticket, unregister  # noqa: E402
from .teams import depts_scope, probation_field, team  # noqa: E402
