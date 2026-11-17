"""Secret Santa on an event (owner, Nov 17): the editor's switch; signing up asks a wishlist (its line under the field
is the feature's own consent: name and wishlist go to one participant); the organizer draws once, from three people
going: one random cycle, so nobody gives to themselves and everyone gives and receives once; sign-up closes with it
(no promotion from the waitlist either). Who loses their seat is out for good: db.py's triggers splice them from the ring.
Secrecy is the point: a pair and a wishlist are read in one place, view(), by the giver alone. No list, export, log or
audit row has them (the wishlist lives here, not in registrations.answers, which the organizers read)."""
from __future__ import annotations

import secrets
import sqlite3

from ..db import tx

from .core import PERSON, ApiError, Viewer, _may, full, now, one, person_ref, rows

WISH_MAX = 300
MIN = 3

_GOING = """SELECT p.user_id FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
    AND r.status = 'going' WHERE p.event_id = ?"""


def start(con, v: Viewer, oid: int, body: dict) -> dict:
    """Studio's one button (owner, Nov 17: "a person presses it and the game is there, no event form"): a published
    team-only Santa event. title: "Secret Santa" in the starter's language; startsAt: the gifts day the app proposed
    (a published event needs a start; the editor changes it later). One game at a time: a running one is returned."""
    _may(con, v, oid, "events")
    with tx(con):
        e = one(con, """SELECT e.* FROM events e JOIN santa_events s ON s.event_id = e.id WHERE e.org_id = ? AND e.status = 'published'
            AND COALESCE(e.ends_at, e.starts_at) > ? ORDER BY e.id LIMIT 1""", oid, now())
        if e:
            return full(con, v, e)
        made = create_event(con, v, oid, {"title": body.get("title"), "place": "", "startsAt": body.get("startsAt"), "emoji": "sparkles_3d",
                                          "color": "#D7263D", "visibility": "members", "santa": True})
        return publish_event(con, v, made["id"])


def news(con, dry: bool = False) -> int:
    """`python -m kbtu.admin santa-news`: the tool's announcement, a template with a button into their Studio, queued
    once per person to every President and Vice of an active organization the bot can write to (their first one's
    Studio). Run by hand, never by a deploy; a second run queues only who became one since."""
    to = rows(con, """SELECT m.user_id, MIN(m.org_id) AS org FROM org_members m JOIN orgs o ON o.id = m.org_id AND o.status = 'active'
        JOIN users u ON u.id = m.user_id AND u.can_dm = 1 AND u.banned_at IS NULL AND u.tg_id > 0
        WHERE m.role IN ('president', 'vice') AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = m.user_id AND b.kind = 'santa_news')
        GROUP BY m.user_id ORDER BY m.user_id""")
    if not dry:
        with tx(con):
            for r in to:
                notify(con, r["user_id"], "santa_news", f"sn:{r['org']}")
    return len(to)


def parts(con, ids: list[int]) -> dict[int, dict]:
    """The card's part, the same for everyone: the game is on, the draw is done."""
    return {r[0]: {"drawn": bool(r[1])} for r in rows(con, f"SELECT event_id, drawn_at FROM santa_events WHERE event_id IN ({','.join('?' * len(ids))})", *ids)}


def set_on(con, eid: int, on: object) -> None:
    """The editor's switch, inside its transaction. Off before the draw forgets the wishlists; after it nothing changes."""
    s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
    if bool(s) == (on is True):
        return
    if s and s["drawn_at"]:
        raise ApiError("conflict", "santa")
    if s:
        con.execute("DELETE FROM santa_events WHERE event_id = ?", (eid,))  # its people cascade
    elif one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND status != 'cancelled'", eid):
        raise ApiError("conflict", "santa_signed")  # those in wrote no wishlist and can't any more (as needs_phone)
    else:
        con.execute("INSERT INTO santa_events (event_id) VALUES (?)", (eid,))


def wish(con, eid: int, uid: int, raw: object) -> None:
    """A sign-up on a Santa event, inside register's transaction: the wishlist is required; after the draw nobody new."""
    s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
    if not s:
        return
    if s["drawn_at"]:
        raise ApiError("closed", "deadline")
    w = " ".join(raw.split()) if isinstance(raw, str) else ""
    if not 2 <= len(w) <= WISH_MAX:
        raise ApiError("bad_input", "wish")
    con.execute("INSERT OR REPLACE INTO santa_people (event_id, user_id, wish) VALUES (?, ?, ?)", (eid, uid, w))


def draw(con, v: Viewer, eid: int) -> dict:
    """Once, by who runs the event, from MIN people going. Each hears it from the bot (a template, no name in it)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
        if not s or e["status"] != "published":
            raise ApiError("not_found")
        if s["drawn_at"]:
            raise ApiError("conflict", "drawn")
        if one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
            raise ApiError("conflict", "holds")  # a seat being paid for would land in a drawn game with no Santa
        ids = [r[0] for r in rows(con, _GOING, eid)]
        if len(ids) < MIN:
            raise ApiError("conflict", "few")
        # who isn't going (cancelled, the waitlist) is out for good: every row left is someone in the cycle
        con.execute(f"DELETE FROM santa_people WHERE event_id = ? AND user_id NOT IN ({','.join('?' * len(ids))})", (eid, *ids))
        secrets.SystemRandom().shuffle(ids)  # a shuffled ring: a uniformly random single cycle
        for a, b in zip(ids, ids[1:] + ids[:1]):
            con.execute("UPDATE santa_people SET gives_to = ? WHERE event_id = ? AND user_id = ?", (b, eid, a))
        for uid in sorted(ids):  # by user id, never in the ring's order: the outbox's ids would spell out every pair
            notify(con, uid, "santa_drawn", f"event:{eid}")
        con.execute("UPDATE santa_events SET drawn_at = ? WHERE event_id = ?", (now(), eid))
        # the app shows "Registration closed" (wish() refuses whatever the deadline says later); updated_at: lists' cached cards see the draw at once
        shut = e["reg_until"] if e["reg_until"] and e["reg_until"] <= now() else min(now(), e["starts_at"])
        con.execute("UPDATE events SET reg_until = ?, updated_at = ? WHERE id = ?", (shut, now(), eid))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _to(con, eid: int, uid: int) -> dict | None:
    """Whom I give to. None: everyone else left (the ring closed on me)."""
    r = one(con, "SELECT p.user_id, p.wish FROM santa_people me JOIN santa_people p ON p.event_id = me.event_id AND p.user_id = me.gives_to"
                 " WHERE me.event_id = ? AND me.user_id = ? AND me.gives_to != me.user_id", eid, uid)
    return {"person": person_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"])), "wish": r["wish"]} if r else None


def view(con, v: Viewer, e: sqlite3.Row, head: bool) -> dict:
    """The event's page. Organizers: how many play, nothing else. A participant still going: their own wishlist and,
    after the draw, their person with that person's wishlist. The only reader of a pair there is."""
    s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", e["id"])
    if not s:
        return {}
    out: dict = {"santaN": len(rows(con, _GOING, e["id"]))} if head else {}
    me = one(con, """SELECT p.wish FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
        AND r.status = 'going' WHERE p.event_id = ? AND p.user_id = ?""", e["id"], v.id)
    if me:
        out["mySanta"] = {"wish": me["wish"], **({"to": _to(con, e["id"], v.id)} if s["drawn_at"] else {})}
    return out


def gone(con, uid: int) -> None:
    """An account being deleted (account.delete_me, before its rows go): their Santa gives to their person instead
    (a seat already lost did this through the triggers; this covers whatever row is left)."""
    con.execute("""UPDATE santa_people SET gives_to = (SELECT x.gives_to FROM santa_people x WHERE x.event_id = santa_people.event_id AND x.user_id = ?)
        WHERE gives_to = ?""", (uid, uid))


from .organizing import _staff_event, create_event, publish_event  # noqa: E402  (they import core, core imports this)
from .seats import notify  # noqa: E402
