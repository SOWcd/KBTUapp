"""The weekly memo to DMP and its sign-off."""
from __future__ import annotations

import json
import re

from .. import receipt, texts

from .core import ApiError, PERSON, Viewer, _once, one, rows


MEMO_ASKS = ("room", "guests", "provide", "promo", "gear", "print", "film")


def _memo(body: dict, keep: str | None) -> str | None:
    """The editor's "For the memo" block (what DMP is asked for, texts.memo_asks): absent keeps it, null clears it.
    Free-form inside each request, bounded: plain values, or a short list of them (printing, a promo's days, more times)."""
    if "memo" not in body:
        return keep
    m = body["memo"]
    if m is None or m == {}:
        return None
    plain = lambda x: x is None or isinstance(x, (bool, int)) or isinstance(x, str) and len(x) <= 1500  # noqa: E731
    ok = isinstance(m, dict) and set(m) <= set(MEMO_ASKS) and all(
        isinstance(a, dict) and all(plain(x) or isinstance(x, list) and len(x) <= 31 and all(plain(y) or isinstance(y, dict) and all(plain(z) for z in y.values()) for y in x)
                                    for x in a.values()) for a in m.values())
    out = json.dumps(m, ensure_ascii=False) if ok else ""
    if not ok or len(out) > 8000:
        raise ApiError("bad_input")
    return out


def _next_week(t: int | None = None) -> int:
    """Monday 00:00 (Almaty) of the week the coming Wednesday's memo covers: DMP takes next week's memos on Wednesdays,
    so from Thursday on it's the week after next (1970-01-01 was a Thursday: Monday = 0)."""
    day = ((t or core.now()) + 5 * 3600) // 86400
    return (day + (2 - (day + 3) % 7) % 7 + 5) * 86400 - 5 * 3600


def _room_no(place: str, url: str | None) -> str | None:
    """The room number in a campus place ("Aud. 305", "332b"), as the memo names it; none off campus."""
    m = None if url else re.search(r"(?<!\d)(\d{2,3}[a-z\u0430-\u044f\u0451]?)(?!\d)", place.lower())
    return m[1] if m else None


def _memo_sender(con, v: Viewer, oid: int) -> dict:
    """Who signs the memo: the sender's "First Last" (kk, ru), in Latin for en (passport style; fixed once by hand), the
    position in three languages from the club role (texts.memo_pos), the portal's phone; `memo_sign` keeps the fixes."""
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    m = one(con, "SELECT m.role, m.memo_sign, r.name FROM org_members m LEFT JOIN org_roles r ON r.id = m.role_id WHERE m.org_id = ? AND m.user_id = ?", oid, v.id)
    fixed = json.loads(m["memo_sign"]) if m and m["memo_sign"] else {}
    name = f"{s['first_name']} {s['last_name']}" if s else ""
    lat = " ".join(w.capitalize() for w in "".join(receipt._LAT.get(c, c) for c in name.lower()).split())
    pos = texts.memo_pos(m["role"] if m else "member", m["name"] if m else None)
    return {"name": name, "nameEn": fixed.get("nameEn") or lat, "phone": texts.phone_line(s["phone"]) if s else None,
            **{k: fixed.get(k) or pos[k] for k in ("kk", "ru", "en")}, "fixed": bool(fixed)}


def memo(con, v: Viewer, oid: int, later: bool = False) -> dict:
    """The week's memo for DMP (PLAN stage 2): one memo of next week's events that ask DMP for something (drafts too:
    rooms are booked before the poster), with `later` the later ones too, signed once by the caller; events already
    sent are left out (listed in `sent`). The app opens it in Outlook to youth_policy@kbtu.kz or copies it. `without`: next
    week's events that ask for nothing, to check."""
    _may(con, v, oid, "memo")
    o = _org(con, oid)
    monday = _next_week()
    evs = rows(con, "SELECT * FROM events WHERE org_id = ? AND status IN ('draft', 'published') AND memo_only = 0 AND starts_at >= ? ORDER BY starts_at", oid, monday)
    week = [e for e in evs if e["starts_at"] < monday + 7 * 86400]
    todo = [e for e in evs if e["memo"] and not e["memo_sent_at"]]
    asked = [e for e in todo if later or e["starts_at"] < monday + 7 * 86400]
    me = _memo_sender(con, v, oid)
    sign = texts.memo_sign(o["name"], me, me["name"], me["nameEn"], me["phone"])
    shape = lambda e: {"title": e["title"], "starts_at": e["starts_at"], "ends_at": e["ends_at"], "place": e["place"], "meeting": e["meeting"],  # noqa: E731
                       "room": _room_no(e["place"], e["place_url"]), "off": bool(e["place_url"]), "seats": e["seats"]}
    asks = [(shape(e), json.loads(e["memo"])) for e in asked]
    dmp = [(e, m) for e, m in asks if set(m) - {"print"}]  # an event asking only for printing has nothing for DMP
    text = texts.memo_text(o["name"], dmp, sign)
    prints = [(e, m) for e, m in asks if m.get("print")]
    pr = texts.print_letter(o["name"], prints, me["ru"], me["name"], me["phone"]) if prints else None
    who = lambda uid: (lambda p: shown_name(p) if p else None)(one(con, PERSON + " WHERE u.id = ?", uid)) if uid else None  # noqa: E731
    brief = lambda e: {"id": e["id"], "title": e["title"], "startsAt": e["starts_at"], "draft": e["status"] == "draft"}  # noqa: E731
    return {"to": texts.MEMO_TO, "subject": texts.memo_subject(o["name"], monday), "text": text, "from": monday, "until": monday + 7 * 86400,
            "print": {"to": texts.PRINT_TO, "subject": pr[0], "text": pr[1]} if pr else None, "guests": any("guests" in json.loads(e["memo"]) for e in asked),
            "events": [brief(e) for e in asked], "later": [brief(e) for e in todo if e["starts_at"] >= monday + 7 * 86400],
            "sent": [{**brief(e), "sentAt": e["memo_sent_at"], "sentBy": who(e["memo_sent_by"])} for e in evs if e["memo"] and e["memo_sent_at"]],
            "without": [brief(e) for e in week if not e["memo"]], "canEdit": can(con, v, oid, "events"),
            "opened": {"at": o["memo_opened_at"], "by": who(o["memo_opened_by"])} if o["memo_opened_at"] else None,
            "sign": {k: me[k] for k in ("name", "nameEn", "kk", "ru", "en", "fixed")},
            "signFrom": texts.MEMO2_SIGN["kk"][0]}  # the sheet's items go in before the signature


def memo_item(con, v: Viewer, oid: int, body: dict) -> str:
    """One item of the memo, written from the sheet's small form (owner, Oct 15: a request needs no event): `kind` and its
    fields as the editor's memo block has them, the day and hours, the place. The sheet shows it and puts it in the text."""
    _may(con, v, oid, "memo")
    kind, place = body.get("kind"), " ".join(str(body.get("place") or "").split())[:80]
    try:
        starts, ends = int(body["startsAt"]), int(body["endsAt"]) if body.get("endsAt") else None
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    if kind not in MEMO_ASKS or kind == "print" or (ends is not None and ends <= starts):
        raise ApiError("bad_input")
    memo = json.loads(_memo({"memo": {kind: body.get("fields") or {}}}, None) or "{}")
    e = {"title": "", "starts_at": starts, "ends_at": ends, "place": place, "room": _room_no(place, None), "off": False, "seats": None, "meeting": 0}
    return (texts.memo_asks(e, memo) or [""])[0]


def memo_opened(con, v: Viewer, oid: int) -> None:
    """"Open in Outlook" or "Copy": the sheet shows it to the others, so nobody sends the week twice."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE orgs SET memo_opened_at = ?, memo_opened_by = ? WHERE id = ?", (core.now(), v.id, oid))


def memo_sent(con, v: Viewer, oid: int, ids: object) -> None:
    """"Sent it to DMP?" -> Yes: these events leave the next memos (an edit of their requests brings them back)."""
    _may(con, v, oid, "memo")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids) or len(ids) > 100:
        raise ApiError("bad_input")
    for i in ids:
        con.execute("UPDATE events SET memo_sent_at = ?, memo_sent_by = ? WHERE id = ? AND org_id = ? AND memo IS NOT NULL", (core.now(), v.id, i, oid))


def memo_again(con, v: Viewer, oid: int, eid: int) -> None:
    """"Include again": a sent event goes back into the memo."""
    _may(con, v, oid, "memo")
    con.execute("UPDATE events SET memo_sent_at = NULL, memo_sent_by = NULL WHERE id = ? AND org_id = ?", (eid, oid))


def memo_sign(con, v: Viewer, oid: int, body: dict) -> dict:
    """The sender fixes the Latin name and the three positions once; an empty field goes back to the computed one."""
    _may(con, v, oid, "memo")
    keep = {k: " ".join(str(body.get(k) or "").split()) for k in ("nameEn", "kk", "ru", "en")}
    if any(len(x) > 120 for x in keep.values()):
        raise ApiError("bad_input")
    keep = {k: x for k, x in keep.items() if x}
    con.execute("UPDATE org_members SET memo_sign = ? WHERE org_id = ? AND user_id = ?", (json.dumps(keep, ensure_ascii=False) if keep else None, oid, v.id))
    return memo(con, v, oid)


def memo_week(con) -> None:
    """Wednesday 9:00-18:00 (Almaty), once a week: everyone with the club's "memo" right, where next week has events
    asking DMP for something not sent yet, hears the memo is ready (DMP takes them until 18:00 that day; later there's no
    point). The sheet shows who opened it already."""
    local = core.now() + 5 * 3600
    if (local // 86400 + 3) % 7 != 2 or not 9 * 3600 <= local % 86400 < 18 * 3600:
        return
    monday = _next_week()
    if not _once(con, "memo_week", str(monday)):
        return
    for (oid,) in rows(con, """SELECT DISTINCT org_id FROM events WHERE status IN ('draft', 'published') AND memo IS NOT NULL
            AND memo_sent_at IS NULL AND starts_at >= ? AND starts_at < ?""", monday, monday + 7 * 86400):
        for m in rows(con, "SELECT m.user_id, m.role, t.rights FROM org_members m LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.org_id = ?", oid):
            if "memo" in _rights_from(m["role"], m["rights"]):
                notify(con, m["user_id"], "memo_ready", f"memo:{oid}:{monday}")


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .account import me  # noqa: E402
from .seats import notify  # noqa: E402
from .shapes import _may, _org, _rights_from, can, shown_name  # noqa: E402
