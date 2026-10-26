"""Running an event: creating, editing, publishing, the door, attendees, ratings, the album."""
from __future__ import annotations

import json
import re
import sqlite3

from ..db import tx

from .core import (ApiError, DOOR_EARLY, DOOR_LATE, PERSON, PERSON_COLS, PROFILE_QR, RANK, TWO_GIS, Viewer, _door_ref,
    _may, _org, _qs, at_least, can, card, cards, friend_ids, full, log_action, media_shape, need_student, one, org_ref,
    person_ref, role_in, rows, taken)


# ---------------------------------------------------------------- Studio (own org)

def _staff_event(con, v: Viewer, eid: int, right: str) -> sqlite3.Row:
    """The event, if I have this right in its club: "events" to run it, "door" to check people in."""
    e = one(con, "SELECT * FROM events WHERE id = ?", eid)
    if not e:
        raise ApiError("not_found")
    _may(con, v, e["org_id"], right)
    return e


def org_events(con, v: Viewer, oid: int) -> list[dict]:
    """Studio's list; for the club's Head+ each event also says how many questions wait for them (`_asking`) and how
    many receipts to check, so they show on top of Studio."""
    role = role_in(con, v, oid)
    if not at_least(role, "member"):
        raise ApiError("forbidden")
    head = can(con, v, oid, "events")
    found = rows(con, "SELECT * FROM events WHERE org_id = ? AND memo_only = 0 ORDER BY starts_at", oid)  # Oct 15's requests without an event: left, hidden
    # receipts that look wrong and nobody looked at yet (§4.3; a registration's last receipt counts), on top of Studio too
    check = dict(rows(con, """SELECT r.event_id, COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id)
        WHERE e.org_id = ? AND r.status = 'going' AND c.status = 'accepted' AND c.flags != '' AND c.reviewed_at IS NULL GROUP BY r.event_id""", oid)) if head else {}
    saved = dict(rows(con, f"SELECT event_id, COUNT(*) FROM saved_events WHERE event_id IN ({_qs([e['id'] for e in found])}) GROUP BY event_id",
                      *[e["id"] for e in found])) if head and found else {}
    asked = dict(rows(con, """SELECT x.event_id, COUNT(*) FROM volunteers x JOIN events e ON e.id = x.event_id
        WHERE e.org_id = ? AND x.status = 'asked' GROUP BY x.event_id""", oid)) if head else {}  # volunteers waiting for an answer
    return [{**c, "questions": len(_asking(con, e["id"], v.id)) if head else 0, "toCheck": check.get(e["id"], 0), "savedBy": saved.get(e["id"], 0),
             "volunteersAsked": asked.get(e["id"], 0)}
            for e, c in zip(found, cards(con, v, found))]


def _asking(con, eid: int, reader: int = 0) -> list:
    """Students' comments under an event that wait for the club: after its last answer (as the club, or by any of its
    Head+ as themselves; their own words are never questions) and, for a `reader`, after they last read the thread
    (Studio's count stayed after he had read and answered). By ids, so the same second never hides one.
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
            VALUES (?, ?, 'cancelled', 'self', ?, ?, ?)""", (eid, v.id, _ticket_code(con), core.now(), core.now()))
    con.execute("UPDATE registrations SET note = ? WHERE event_id = ? AND user_id = ?", (why or None, eid, v.id))
    return card(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _team_door(e: sqlite3.Row) -> bool:
    """A club meeting, or a free team-only event: no tickets, so the door has the whole team (a meeting's
    tag) to mark, and someone who came without signing up is let in by name."""
    return bool(e["meeting"]) or (e["visibility"] == "members" and not e["price"])


def _expected(con, e: sqlite3.Row) -> list[int]:
    """Who a club meeting expects (§2b): the club's students, or only those with its tag."""
    tag = e["meeting_tag"]
    return [r[0] for r in rows(con, "SELECT m.user_id FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ?"
                                    + (" AND m.user_id IN (SELECT user_id FROM member_tags WHERE tag_id = ?)" if tag else ""), e["org_id"], *([tag] if tag else []))]


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
    out = []
    for p in found:
        answer = "yes" if p["status"] in ("going", "hold") else "no" if p["status"] == "cancelled" else "none"
        came = p["checked_in_at"] is not None
        out.append({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "role": p["role"],
                    "answer": answer, "note": p["note"] if answer == "no" else None, "came": came, "probation": bool(p["probation"])})
    return sorted(out, key=lambda x: (-RANK[x["role"]], x["fullName"]))


def leaders_answers(con, v: Viewer, eid: int) -> list[dict]:
    """DMP's view of a leaders meeting (§4.10): per club, who said yes, who no, who hasn't answered."""
    e = _staff_event(con, v, eid, "events")
    if e["visibility"] != "leaders":
        raise ApiError("bad_input")
    roles = LEAD_ROLES[e["leaders_from"] or "president"]
    out = []
    for o in rows(con, "SELECT * FROM orgs WHERE kind IN ('club', 'school', 'council') AND status = 'active' ORDER BY official DESC, name"):
        people = rows(con, f"""SELECT {PERSON_COLS}, m.role, r.status AS answer FROM org_members m JOIN users u ON u.id = m.user_id
            JOIN students s ON s.user_id = u.id LEFT JOIN registrations r ON r.event_id = ? AND r.user_id = u.id
            WHERE m.org_id = ? AND m.role IN ({','.join('?' * len(roles))})""", eid, o["id"], *roles)
        if not people:
            continue
        said = lambda p: "yes" if p["answer"] in ("going", "hold") else "no" if p["answer"] == "cancelled" else "none"  # noqa: E731
        out.append({"org": org_ref(con, o), "people": sorted(({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(),
                                                          "role": p["role"], "answer": said(p)} for p in people), key=lambda x: -RANK[x["role"]])})
    return out


def clean_event(i: dict, oversee: bool = False) -> dict:
    """The editor's input, checked. A leaders meeting (§4.10) only from an oversight org
    (DMP), with the lowest role invited."""
    try:
        title, place = str(i["title"]).strip(), str(i["place"]).strip()
        description = str(i.get("description") or "").strip()
        url = (str(i.get("placeUrl") or "")).strip() or None
        starts, ends = int(i["startsAt"]), (int(i["endsAt"]) if i.get("endsAt") is not None else None)
        seats = int(i["seats"]) if i.get("seats") is not None else None
        reg_until = int(i["regUntil"]) if i.get("regUntil") is not None else None
        emoji, color = str(i["emoji"]), str(i["color"])
        visibility = None if i.get("visibility") is None else str(i["visibility"])  # left out: kept as it is
        leaders = str(i.get("leadersFrom") or "president") if visibility == "leaders" else None
        meeting = i.get("meeting") is True  # a club meeting (§2b): team-only, someone's tag or the whole club expected
        tag = int(i["meetingTag"]) if meeting and i.get("meetingTag") is not None else None
        vol = int(i["volunteers"]) if i.get("volunteers") else None  # how many volunteers it needs; none: off
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    ok = (0 < len(title) <= 80 and len(place) <= 80 and len(description) <= 2000  # no place: to be confirmed (a room asked of DMP) and (ends is None or ends > starts)
          and (seats is None or 0 < seats <= 5000) and (url is None or TWO_GIS.match(url)) and (reg_until is None or reg_until <= starts)
          and re.fullmatch(r"#[0-9a-fA-F]{6}", color) and re.fullmatch(r"[a-z0-9_]{1,40}", emoji) and visibility in (None, "public", "members", *(("leaders",) if oversee else ()))
          and leaders in (None, "president", "vice", "head") and (not meeting or visibility == "members" and seats is None)
          and (vol is None or 1 <= vol <= 500 and not meeting))
    if not ok:
        raise ApiError("bad_input")
    return {"title": title, "description": description, "starts_at": starts, "ends_at": ends, "place": place, "place_url": url,
            "emoji": emoji, "color": color, "seats": seats, "reg_until": reg_until, "first_year": int(bool(i.get("firstYear"))),
            "needs_phone": int(i.get("needsPhone") is True),  # sign-up asks for the phone once, kept for next time (PLAN 71)
            "album_open": int(i.get("albumOpen") is not False),  # "Photos from participants" (off: the team's only)
            "meeting": int(meeting), "meeting_tag": tag, "volunteers": vol, "volunteers_senior": int(bool(vol and i.get("volunteersSenior"))),
            **({"visibility": visibility, "leaders_from": leaders} if visibility else {})}


def _meeting_ok(con, v: Viewer, oid: int, f: dict, priced: bool, was: tuple | None = None) -> None:
    """A meeting's tag is one of the club's own, and a meeting has no price. A Head with a department calls only that
    department (PLAN item 35); `was` (meeting, tag) before an edit: what someone else set stays as it is."""
    if f["meeting"] and (priced or f["meeting_tag"] and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ?", f["meeting_tag"], oid)):
        raise ApiError("bad_input")
    if f["meeting"] and (f["meeting"], f["meeting_tag"]) != was and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
        own = dept_of(con, oid, v.id)
        if own is not None and f["meeting_tag"] != own:
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


def kz_phone(raw: object) -> str | None:
    """A Kazakhstan number as typed (8 701..., +7 701..., 701...) kept as +7XXXXXXXXXX; None if it isn't one."""
    t = str(raw or "")
    d = re.sub(r"[^0-9]", "", t)  # ASCII only: \d takes any script's digits
    # ten digits are the number without its +7, unless it came with a "+": "+7 701 234 56 7" is one digit short
    d = "7" + d[1:] if len(d) == 11 and d[0] == "8" else "7" + d if len(d) == 10 and not t.lstrip().startswith("+") else d
    return "+" + d if re.fullmatch(r"7[0-9]{10}", d) else None


def _pay(con, v: Viewer, body: dict, org: sqlite3.Row, e: sqlite3.Row | None = None) -> dict:
    """The price and where students send it (§4.3): only an official club's Vice+ set them, and they are fixed once the
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
    if not org["official"] or not can(con, v, org["id"], "money"):
        raise ApiError("forbidden", "price")
    if e and any(new[k] != old[k] for k in ("price", "pay_to_name", "pay_phone")) \
            and one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", e["id"]):
        raise ApiError("conflict", "paid")  # someone has paid by these details already
    return new


def create_event(con, v: Viewer, oid: int, body: dict) -> dict:
    _may(con, v, oid, "events")
    org = _org(con, oid)
    f = {**clean_event(body, bool(org["can_oversee"])), **_pay(con, v, body, org)}
    _meeting_ok(con, v, oid, f, bool(f.get("price")))
    f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, None), _focus(body, None), _memo(body, None)
    f["video_id"], f["wide_video_id"] = _video(con, v, body, None), _video(con, v, body, None, "wideVideoId")
    with tx(con):  # bad slides leave no draft behind
        cur = con.execute(f"""INSERT INTO events (org_id, status, {', '.join(f)}, tint, created_by, created_at, updated_at)
            VALUES (?, 'draft', {', '.join('?' * len(f))}, ?, ?, ?, ?)""", (oid, *f.values(), shade(f["color"]), v.id, core.now(), core.now()))
        e = one(con, "SELECT * FROM events WHERE id = ?", cur.lastrowid)
        _slides(con, v, body, e, f["cover_file_id"])
    return full(con, v, e)


SLIDES = 9   # photos after the cover (PLAN 33): ten in all, as an Instagram or TikTok photo post


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


def update_event(con, v: Viewer, eid: int, body: dict) -> dict:
    org = one(con, "SELECT o.* FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ?", eid)
    f = clean_event(body, bool(org and org["can_oversee"]))
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] == "cancelled":
            raise ApiError("closed")
        f |= _pay(con, v, body, org, e)
        _meeting_ok(con, v, e["org_id"], f, bool(f["price"] if "price" in f else e["price"]), (e["meeting"], e["meeting_tag"]))
        if f["seats"] is not None and f["seats"] < taken(con, eid):
            raise ApiError("conflict")  # seats can't drop below who is already in
        f["cover_file_id"], f["cover_focus"], f["memo"] = _cover(con, v, body, e["cover_file_id"]), _focus(body, e["cover_focus"]), _memo(body, e["memo"])
        f["video_id"], f["wide_video_id"] = _video(con, v, body, e["video_id"]), _video(con, v, body, e["wide_video_id"], "wideVideoId")
        _slides(con, v, body, e, f["cover_file_id"])
        if (f["memo"], f["starts_at"], f["ends_at"]) != (e["memo"], e["starts_at"], e["ends_at"]):
            f["memo_sent_at"] = f["memo_sent_by"] = None  # changed requests go to DMP again
        if (f["title"], f["description"]) != (e["title"], e["description"]):
            f["i18n"], f["lang"], f["ai_tries"] = None, None, 0  # translated again (ai.py)
        con.execute(f"UPDATE events SET {', '.join(k + ' = ?' for k in f)}, tint = ?, updated_at = ? WHERE id = ?",
                    (*f.values(), shade(f["color"]), core.now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if e["price"] and not after["price"]:  # free now: whoever was about to pay is simply in
            for (uid,) in rows(con, "SELECT user_id FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
                con.execute("UPDATE registrations SET status = 'going', hold_until = NULL, updated_at = ? WHERE event_id = ? AND user_id = ?", (core.now(), eid, uid))
                _remind(con, uid, after)
        _changed(con, v, e, after)
        promote(con, after)
    return full(con, v, after)


def _changed(con, v: Viewer, e: sqlite3.Row, after: sqlite3.Row) -> None:
    """Who hears that a published event moved (PLAN "Place and time", §4.9): the room DMP gave for a place to be confirmed,
    or one KBTU room for another, tells nobody now (the 2-hour reminder shows it; at once for those with reminders off);
    another venue or a new time tells them, edits within 10 minutes in one message (the bot reads the event when it
    sends); within 2 hours of the start or during it, at once and only to those not checked in. A new place also gets a
    line in the event's Updates."""
    eid, moved = e["id"], e["starts_at"] != after["starts_at"]
    placed = (e["place"], e["place_url"]) != (after["place"], after["place_url"])
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
        con.execute("UPDATE events SET place = ?, place_url = NULL, updated_at = ? WHERE id = ?", (text, core.now(), eid))
        after = one(con, "SELECT * FROM events WHERE id = ?", eid)
        _changed(con, v, e, after)
    return full(con, v, after)


def publish_event(con, v: Viewer, eid: int) -> dict:
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "draft":
            raise ApiError("conflict")
        if e["starts_at"] <= core.now():
            raise ApiError("closed")
        con.execute("UPDATE events SET status = 'published', published_at = ?, updated_at = ? WHERE id = ?", (core.now(), core.now(), eid))
        if e["visibility"] == "leaders":  # §4.10: every invited leader hears at once (always on)
            for (uid,) in _invited_leaders(con, e, exclude=v.id):
                notify(con, uid, "leaders_invite", f"li:{eid}")
        if e["meeting"]:  # §2b: everyone expected hears at once (always on)
            for uid in _expected(con, e):
                if uid != v.id:
                    notify(con, uid, "meeting_invite", f"mi:{eid}")
        if e["visibility"] == "public":  # subscribers hear about it (§7, can be turned off)
            for r in rows(con, """SELECT s.user_id FROM subscriptions s JOIN users u ON u.id = s.user_id
                WHERE s.org_id = ? AND u.n_new_events = 1 AND s.user_id != ?""", e["org_id"], v.id):
                notify(con, r[0], "new_event", f"event:{eid}")
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def cancel_event(con, v: Viewer, eid: int) -> dict:
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if e["status"] != "published":
            raise ApiError("conflict")
        con.execute("UPDATE events SET status = 'cancelled', cancelled_at = ?, updated_at = ? WHERE id = ?", (core.now(), core.now(), eid))
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
        e = _staff_event(con, v, eid, "events")
        if e["status"] not in ("draft", "cancelled"):
            raise ApiError("conflict")
        if one(con, "SELECT 1 FROM receipts c JOIN registrations r ON r.id = c.registration_id WHERE r.event_id = ?", eid):
            raise ApiError("conflict", "paid")
    with tx(con):
        paid = [r[0] for r in rows(con, """SELECT c.file_id FROM receipts c JOIN registrations r ON r.id = c.registration_id
            WHERE r.event_id = ?""", eid)]
        pics = [r[0] for r in rows(con, """SELECT file_id FROM event_photos WHERE event_id = ?
            UNION SELECT cover_file_id FROM events WHERE id = ? AND cover_file_id IS NOT NULL
            UNION SELECT file_id FROM event_slides WHERE event_id = ?""", eid, eid, eid)]
        post = one(con, "SELECT channel_msg FROM events WHERE id = ?", eid)
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
        photos = [p for f in pics for p in _drop_unused(con, f)]
    return receipts, photos


def attendees(con, v: Viewer, eid: int) -> list[dict]:
    _staff_event(con, v, eid, "events")
    order = {"going": 0, "hold": 1, "waitlist": 2}
    found = rows(con, f"""SELECT {PERSON_COLS}, r.status, r.checked_in_at, r.walk_in, r.checkin_manual, r.created_at AS at, r.free,
            c.id AS rid, c.flags, c.reviewed_at, c.created_at AS sent_at, c.amount, c.receipt_no, c.sender_name, c.recipient_name, c.paid_at
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        LEFT JOIN receipts c ON c.id = (SELECT MAX(id) FROM receipts WHERE registration_id = r.id AND status = 'accepted')
        WHERE r.event_id = ? AND r.status != 'cancelled'""", eid)
    out = [{"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "status": p["status"],
            "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"]), "at": p["at"], "free": bool(p["free"]),
            "receipt": {"id": p["rid"], "flags": [x for x in p["flags"].split(",") if x], "reviewed": p["reviewed_at"] is not None, "at": p["sent_at"],
                        "amount": p["amount"], "no": p["receipt_no"], "sender": p["sender_name"], "recipient": p["recipient_name"], "paidAt": p["paid_at"]}
            if p["rid"] else None} for p in found]
    flagged = lambda a: bool(a["receipt"] and a["receipt"]["flags"] and not a["receipt"]["reviewed"])  # noqa: E731
    return sorted(out, key=lambda a: (not flagged(a), order[a["status"]], a["fullName"]))  # §4.3: flagged receipts first


def attendees_export(con, v: Viewer, eid: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    """The event and its people for the CSV (Head+, §3: an organizer sees contacts for their own event). Every export
    of personal data goes to the audit log."""
    e = _staff_event(con, v, eid, "events")
    # the phone only where this event asked for it (one club's ask reached every club's list)
    found = rows(con, """SELECT s.last_name, s.first_name, u.tg_username, s.student_id, s.course, s.school, s.email,
            CASE WHEN ? THEN s.phone END AS phone,
            r.status, r.created_at, r.checked_in_at, r.walk_in, r.checkin_manual
        FROM registrations r JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id
        WHERE r.event_id = ? AND r.status != 'cancelled' ORDER BY s.last_name, s.first_name""", e["needs_phone"], eid)
    log_action(con, v.id, "attendees_export", f"event:{eid}", json.dumps({"rows": len(found)}))
    return e, found


def _walk_in(con, e: sqlite3.Row, uid: int, code: str, t: int) -> sqlite3.Row | str:
    """A badge QR at the door: someone who forgot to register, or was just passing by, comes in.
    A ticket they hold is checked in as usual; a free event registers them on the spot (walk_in); a paid one
    needs a ticket."""
    if e["status"] != "published":
        return "closed"
    if not one(con, "SELECT 1 FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ? AND u.qr_code = ?", uid, code):
        return "not_found"
    r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)
    if r and r["status"] == "going":
        return r
    if e["price"]:
        return "paid"
    if r:  # waitlisted or cancelled earlier, at the door now
        con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, hold_until = NULL, waitlisted_at = NULL, walk_in = 1, updated_at = ? WHERE id = ?",
                    (t, r["id"]))
    else:
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                    (e["id"], uid, _ticket_code(con), t, t))
    return one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], uid)


def checkin(con, v: Viewer, eid: int, raw: str) -> dict:
    """The door scanner: a ticket (KBTU<code>) or a badge QR (§4.4). Says how late they are, for the organizer."""
    with tx(con):
        e = _staff_event(con, v, eid, "door")
        t = core.now()
        if t < e["starts_at"] - DOOR_EARLY or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            return {"result": "closed"}
        badge = PROFILE_QR.search(str(raw))
        if badge:
            r = _walk_in(con, e, int(badge[1]), badge[2], t)
            if isinstance(r, str):
                return {"result": r}
        else:
            c = re.sub(r"[\s-]+", "", str(raw)).upper()  # typed as "7k4 m2p", or the QR's KBTU<code> (KBTU-<code> before Oct 5)
            r = one(con, "SELECT * FROM registrations WHERE ticket_code IN (?, ?)", c, c.removeprefix("KBTU"))
            if not r:
                return {"result": "not_found"}
            if r["event_id"] != eid:
                return {"result": "other_event"}
            if r["status"] != "going":
                return {"result": "cancelled"}
        if not r["checked_in_at"]:
            _came(con, e, r["user_id"], lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, updated_at = ? WHERE id = ?",
                                                           (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"])),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": one(con, "SELECT 1 FROM receipts WHERE registration_id = ? AND status = 'accepted' AND flags != '' AND reviewed_at IS NULL", r["id"]) is not None}


RATE_FOR = 7 * 86400   # a rating is taken from the end of the event this long
RATE_SHOW = 3          # the club sees the ratings from this many on, so a small club can't tell who wrote what


def _rating_view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict:
    """What the event sheet shows about ratings: mine (and whether I may still give one: checked in, ended, within 7
    days), and for the club's Head+ the anonymous summary — average, the five counts, the comments, no names; under
    RATE_SHOW of them, only how many."""
    mine = one(con, "SELECT score FROM event_ratings WHERE event_id = ? AND user_id = ?", e["id"], v.id) if v.student else None
    came = v.student and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", e["id"], v.id)
    out = {"myRating": mine["score"] if mine else None, "canRate": bool(came) and end_of(e) <= core.now() <= end_of(e) + RATE_FOR, "ratings": None}
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
    """One tap after the event (from the Luma review): only those checked in, from the end until 7 days later;
    changing one's mind is fine. Anonymous to the club."""
    need_student(v)
    e = _event(con, v, eid)
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
        raise ApiError("bad_input")
    text = str(comment or "").strip()[:300]
    if not _rating_view(con, v, e, False)["canRate"]:
        raise ApiError("forbidden")
    con.execute("""INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (event_id, user_id) DO UPDATE SET score = excluded.score, comment = excluded.comment, created_at = excluded.created_at""",
                (eid, v.id, score, text, core.now()))
    return full(con, v, e)


def _ask_rating(con, uid: int, e: sqlite3.Row) -> None:
    """Checked in: an hour after the end the bot asks how it was (follows the reminders switch)."""
    notify(con, uid, "rate", f"rate:{e['id']}", after=end_of(e) + 3600)


INVITES_A_DAY = 30


def event_invites(con, v: Viewer, eid: int) -> list[dict]:
    """"Bring a friend" (§4.7): my friends and where each one stands with this event — to invite, invited by me, or
    going (only for those who show where they go, §3; the rest look invitable and the bot simply stays quiet)."""
    need_student(v)
    _event(con, v, eid)
    out = []
    for p in rows(con, PERSON + " WHERE u.id IN (SELECT b FROM friendships WHERE a = ? UNION SELECT a FROM friendships WHERE b = ?)", v.id, v.id):
        going = p["show_going"] and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')", eid, p["id"])
        asked = one(con, "SELECT 1 FROM friend_invites WHERE from_id = ? AND to_id = ? AND event_id = ?", v.id, p["id"], eid)
        out.append({"person": person_ref(p), "state": "going" if going else "invited" if asked else "none"})
    rank = {"none": 0, "invited": 1, "going": 2}
    return sorted(out, key=lambda x: (rank[x["state"]], x["person"]["name"]))


def invite_friend(con, v: Viewer, eid: int, uid: object) -> list[dict]:
    """The bot brings my friend our card: "<name> invites you to <title>" + Open. Once per friend and event; public
    events that haven't started; 30 invites a day."""
    need_student(v)
    e = _event(con, v, eid)
    if not isinstance(uid, int) or isinstance(uid, bool) or uid not in friend_ids(con, v.id):
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


def _album_view(con, v: Viewer, e: sqlite3.Row) -> dict:
    """The guests' album (from the Luma review). Students see it (guests don't: people's faces); who came adds
    photos, and so does the team; the one who added a photo or the club's Head+ take it out."""
    if not v.student:
        return {"photos": [], "canAddPhotos": False}
    head = can(con, v, e["org_id"], "events")
    ps = rows(con, f"""SELECT f.*, p.added_by, s.first_name, s.last_name, u.nick FROM event_photos p JOIN files f ON f.id = p.file_id
        LEFT JOIN users u ON u.id = p.added_by LEFT JOIN students s ON s.user_id = p.added_by WHERE p.event_id = ?
        AND f.id NOT IN (SELECT r.target_id FROM reports r WHERE r.target = 'photo' AND r.status = 'open' GROUP BY r.target_id
                         HAVING (COUNT(DISTINCT r.reporter_id) >= 2  -- for everyone, unless a moderator already kept it
                                 AND NOT EXISTS (SELECT 1 FROM reports k WHERE k.target = 'photo' AND k.target_id = r.target_id AND k.status = 'dismissed'))
                             OR SUM(r.reporter_id = ?) > 0)
        ORDER BY p.sort""", e["id"], v.id)
    by = lambda f: f["nick"] or (f"{f['first_name']} {f['last_name'][:1]}." if f["first_name"] else None)  # noqa: E731
    return {"photos": [{**media_shape(f), "canDelete": head or f["added_by"] == v.id, "by": by(f), "mine": f["added_by"] == v.id} for f in ps],
            "canAddPhotos": _album_room(con, v, e) > 0, "albumOpen": bool(e["album_open"])}


def _album_room(con, v: Viewer, e: sqlite3.Row) -> int:
    """How many more photos I may add to this event's album now."""
    if not v.student or e["status"] != "published" or not e["starts_at"] <= core.now() <= end_of(e) + ALBUM_FOR:
        return 0
    team = at_least(role_in(con, v, e["org_id"]), "member") or bool(e["co_org_id"] and at_least(role_in(con, v, e["co_org_id"]), "member"))
    if not team and (not e["album_open"] or not one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND checked_in_at IS NOT NULL", e["id"], v.id)):
        return 0
    mine = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ? AND added_by = ?", e["id"], v.id)["n"]
    total = one(con, "SELECT COUNT(*) AS n FROM event_photos WHERE event_id = ?", e["id"])["n"]
    return max(0, min((ALBUM_TEAM if team else ALBUM_EACH) - mine, ALBUM_MAX - total))


def can_add_album_photo(con, v: Viewer, eid: int) -> bool:
    return _album_room(con, v, _event(con, v, eid)) > 0


def add_album_photo(con, v: Viewer, eid: int, saved: dict) -> dict:
    e = _event(con, v, eid)
    if _album_room(con, v, e) <= 0:
        raise ApiError("forbidden")
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'event_photo' AND owner_id = ?", saved["sha256"], v.id)
    fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                     saved["path"], v.id, core.now(), saved["color"])).lastrowid
    con.execute("""INSERT OR IGNORE INTO event_photos (event_id, file_id, sort, added_by)
        VALUES (?, ?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM event_photos WHERE event_id = ?), ?)""", (eid, fid, eid, v.id))
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


def door(con, v: Viewer, eid: int) -> list[dict]:
    """The door list for check-in by name (Member+, like the scanner; §3: a Member sees short names only): who is going,
    the ones still to come first."""
    e = _staff_event(con, v, eid, "door")
    found = rows(con, f"""SELECT {PERSON_COLS}, r.checked_in_at, r.walk_in, r.checkin_manual FROM registrations r
        JOIN users u ON u.id = r.user_id JOIN students s ON s.user_id = u.id WHERE r.event_id = ? AND r.status = 'going'""", eid)
    out = [{"person": _door_ref(p), "checkedInAt": p["checked_in_at"], "walkIn": bool(p["walk_in"]), "manual": bool(p["checkin_manual"])} for p in found]
    if _team_door(e):  # §2b: everyone expected is on the list, answered or not
        rest = [u for u in _expected(con, e) if u not in {p["id"] for p in found}]
        out += [{"person": _door_ref(p), "checkedInAt": None, "walkIn": False, "manual": False}
                for p in (rows(con, PERSON + f" WHERE u.id IN ({_qs(rest)})", *rest) if rest else [])]
    return sorted(out, key=lambda a: (a["checkedInAt"] is not None, -(a["checkedInAt"] or 0), a["person"]["name"]))


def checkin_by_name(con, v: Viewer, eid: int, uid: int) -> dict:
    """No QR (a dead phone): a person going to the event is checked in by hand from the door list (§4.4). The same answer
    as the scanner; marked "by hand" for the organizer and the CSV."""
    with tx(con):
        e = _staff_event(con, v, eid, "door")
        t = core.now()
        if t < e["starts_at"] - DOOR_EARLY or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            return {"result": "closed"}
        r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if _team_door(e) and (not r or r["status"] != "going") and uid in _expected(con, e):  # §2b: came anyway
            if r:
                con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL, walk_in = 1, updated_at = ? WHERE id = ?", (t, r["id"]))
            else:
                con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at) VALUES (?, ?, 'going', ?, 1, ?, ?)",
                            (eid, uid, _ticket_code(con), t, t))
            r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?", eid, uid)
        if not r:
            return {"result": "not_found"}
        if r["status"] != "going":
            return {"result": "cancelled"}
        if not r["checked_in_at"]:
            _came(con, e, uid, lambda: con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, checkin_manual = 1, updated_at = ? WHERE id = ?",
                                                  (t, v.id, t, r["id"])))
        at = r["checked_in_at"] or t
        came = one(con, "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", eid)[0]
        return {"result": "already" if r["checked_in_at"] else "ok", "person": _door_ref(one(con, PERSON + " WHERE u.id = ?", uid)),
                "at": at, "came": came, "going": taken(con, eid), "walkIn": bool(r["walk_in"]), "late": max(0, at - e["starts_at"]) // 60,
                "flagged": one(con, "SELECT 1 FROM receipts WHERE registration_id = ? AND status = 'accepted' AND flags != '' AND reviewed_at IS NULL", r["id"]) is not None}


def undo_checkin(con, v: Viewer, eid: int, uid: int) -> None:
    """Take back a check-in by name made in the last 10 minutes (a scanned ticket stays: it proves the person came). One
    that came from a walk-in's typed name (link_door_guests) takes that name with it: it wasn't them, and a name left
    linked would keep saying they came (PLAN A19 "left")."""
    _staff_event(con, v, eid, "door")
    with tx(con):
        cur = con.execute("""UPDATE registrations SET checked_in_at = NULL, checked_in_by = NULL, checkin_manual = 0, updated_at = ?
            WHERE event_id = ? AND user_id = ? AND checkin_manual = 1 AND checked_in_at > ?""", (core.now(), eid, uid, core.now() - UNDO))
        if not cur.rowcount:
            raise ApiError("conflict")
        con.execute("DELETE FROM door_guests WHERE event_id = ? AND user_id = ?", (eid, uid))


# A19 (Oct 23 night): someone at the door without the app, or not on the list, types their own first and last
# name on the organiser's phone. When a student with that name confirms with Microsoft later, they count as came.
GUEST_NAME = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*(?: [^\W\d_]+(?:[-'’][^\W\d_]+)*){1,3}")
GUESTS_MAX = 500  # an event's walk-ins by name (a typo loop must not fill the table)


def _norm_name(s: str) -> str:
    """"Ivanov  Ivan" and "ivan ivanov" are one person; Cyrillic yo is e."""
    return " ".join(sorted(s.lower().replace("\u0451", "\u0435").split()))


def _guest(g: sqlite3.Row, full: bool, me: int) -> dict:
    first, *rest = g["full_name"].split(" ")
    return {"id": g["id"], "name": g["full_name"] if full else f"{first} {rest[-1][:1]}.", "at": g["created_at"],
            "linked": g["user_id"] is not None, "undo": g["added_by"] == me and g["user_id"] is None and g["created_at"] > core.now() - UNDO}


def door_guests(con, v: Viewer, eid: int) -> list[dict]:
    """The walk-ins by name, newest first: full names for Head+ (like the attendees), short ones for the door (§3)."""
    e = _staff_event(con, v, eid, "door")
    full = can(con, v, e["org_id"], "events")
    return [_guest(g, full, v.id) for g in rows(con, "SELECT * FROM door_guests WHERE event_id = ? ORDER BY created_at DESC, id DESC", eid)]


def add_door_guest(con, v: Viewer, eid: int, name: object) -> dict:
    """A walk-in by name (Member+, the door's right): while the door is open, a free event only (a paid one needs a
    ticket). The same name twice at one event is one person."""
    full = " ".join(str(name or "").split())
    if not (3 <= len(full) <= 80 and GUEST_NAME.fullmatch(full)):
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "door")
        t = core.now()
        if e["status"] != "published" or t < e["starts_at"] - DOOR_EARLY or t > (e["ends_at"] or e["starts_at"] + DOOR_LATE):
            raise ApiError("conflict", "closed")
        if e["price"]:
            raise ApiError("conflict", "paid")
        if e["visibility"] != "public":  # a team meeting is marked from its expected list (§2b), not by typed names
            raise ApiError("conflict", "team")
        con.execute("DELETE FROM door_guests WHERE user_id IS NULL AND created_at < ?", (t - GUEST_DAYS,))  # nobody came for them
        norm = _norm_name(full)
        if one(con, "SELECT 1 FROM door_guests WHERE event_id = ? AND norm = ?", eid, norm):
            raise ApiError("conflict", "already")
        if one(con, "SELECT COUNT(*) FROM door_guests WHERE event_id = ?", eid)[0] >= GUESTS_MAX:
            raise ApiError("rate_limited")
        gid = con.execute("INSERT INTO door_guests (event_id, full_name, norm, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
                          (eid, full, norm, v.id, t)).lastrowid
        return _guest(one(con, "SELECT * FROM door_guests WHERE id = ?", gid), can(con, v, e["org_id"], "events"), v.id)


def undo_door_guest(con, v: Viewer, eid: int, gid: int) -> None:
    """A wrong name taken back by whoever typed it, in the first 10 minutes, while nobody is linked to it."""
    _staff_event(con, v, eid, "door")
    if not con.execute("DELETE FROM door_guests WHERE id = ? AND event_id = ? AND added_by = ? AND user_id IS NULL AND created_at > ?",
                       (gid, eid, v.id, core.now() - UNDO)).rowcount:
        raise ApiError("conflict")


GUEST_DAYS = 30 * 86400  # a walk-in's name waits this long for its student, then goes


def link_door_guests(con, uid: int) -> None:
    """A student confirmed by Microsoft (their names are KBTU's): a walk-in of the last 30 days with their full name was
    them, only if no other student has that name (owner's rule with the review's guard: two Aruzhan Serikovas and
    nobody can tell). Only where the door rules still hold: a public free event, not banned from the club; a
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
        for g in rows(con, """SELECT g.* FROM door_guests g JOIN events e ON e.id = g.event_id WHERE g.norm = ? AND g.user_id IS NULL
                AND g.created_at > ? AND e.status = 'published' AND e.price IS NULL AND e.visibility = 'public'
                AND NOT EXISTS (SELECT 1 FROM org_bans b WHERE b.org_id = e.org_id AND b.user_id = ?)
                AND NOT EXISTS (SELECT 1 FROM door_guests y WHERE y.event_id = g.event_id AND y.user_id = ?)""", norm, core.now() - GUEST_DAYS, uid, uid):
            r = one(con, "SELECT id, status, checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", g["event_id"], uid)
            if r and (r["status"] != "going" or r["checked_in_at"]):
                continue
            con.execute("UPDATE door_guests SET user_id = ? WHERE id = ?", (uid, g["id"]))
            if not r:
                con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, walk_in, created_at, updated_at)
                    VALUES (?, ?, 'going', ?, 1, ?, ?)""", (g["event_id"], uid, _ticket_code(con), core.now(), core.now()))
            # as a check-in at the door: the rating ask and the levels it brings (written directly, they were lost)
            _came(con, one(con, "SELECT * FROM events WHERE id = ?", g["event_id"]), uid, lambda g=g: con.execute(
                """UPDATE registrations SET checked_in_at = ?, checked_in_by = ?, checkin_manual = 1, updated_at = ? WHERE event_id = ? AND user_id = ?""",
                (g["created_at"], g["added_by"], core.now(), g["event_id"], uid)))


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import _drop_photo, _drop_unused, me  # noqa: E402
from .clubs import _keep_name, org, people  # noqa: E402
from .daily import _memo  # noqa: E402
from .profiles import _came  # noqa: E402
from .queues import _video  # noqa: E402
from .seats import _event, _remind, _ticket_code, end_of, notify, promote, unregister  # noqa: E402
from .teams import dept_of, team  # noqa: E402
