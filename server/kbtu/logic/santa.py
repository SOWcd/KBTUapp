"""Secret Santa on an event (owner, Nov 17): the editor's switch; signing up asks a wishlist (its line under the field
is the feature's own consent: name and wishlist go to one participant); the organizer draws once, from three people
going: one random cycle, so nobody gives to themselves and everyone gives and receives once; sign-up closes with it.
Secrecy is the point: a pair and a wishlist are read in one place, view(), by the giver alone. No list, export, log or
audit row has them (the wishlist lives here, not in registrations.answers, which the organizers read)."""
from __future__ import annotations

import secrets
import sqlite3

from ..db import tx

from .core import PERSON, ApiError, Viewer, full, now, one, person_ref, rows

WISH_MAX = 300
MIN = 3

_GOING = """SELECT p.user_id FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
    AND r.status = 'going' WHERE p.event_id = ?"""


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
        ids = [r[0] for r in rows(con, _GOING, eid)]
        if len(ids) < MIN:
            raise ApiError("conflict", "few")
        # who isn't going (cancelled, the waitlist) is out for good: every row left is someone in the cycle
        con.execute(f"DELETE FROM santa_people WHERE event_id = ? AND user_id NOT IN ({','.join('?' * len(ids))})", (eid, *ids))
        secrets.SystemRandom().shuffle(ids)  # a shuffled ring: a uniformly random single cycle
        for a, b in zip(ids, ids[1:] + ids[:1]):
            con.execute("UPDATE santa_people SET gives_to = ? WHERE event_id = ? AND user_id = ?", (b, eid, a))
            notify(con, a, "santa_drawn", f"event:{eid}")
        con.execute("UPDATE santa_events SET drawn_at = ? WHERE event_id = ?", (now(), eid))
        # the app shows "Registration closed" (wish() refuses whatever the deadline says later); updated_at: lists' cached cards see the draw at once
        shut = e["reg_until"] if e["reg_until"] and e["reg_until"] <= now() else min(now(), e["starts_at"])
        con.execute("UPDATE events SET reg_until = ?, updated_at = ? WHERE id = ?", (shut, now(), eid))
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _to(con, eid: int, uid: int) -> dict | None:
    """Whom I give to: my person, or, if they stepped out since (any way a seat is lost), theirs, and so on round the
    ring, so nobody still in is left without a Santa. None: nobody is left but me."""
    ring = {r["user_id"]: r for r in rows(con, """SELECT p.user_id, p.gives_to, p.wish, r.status IS 'going' AS here FROM santa_people p
        LEFT JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id WHERE p.event_id = ?""", eid)}
    nxt, seen = ring[uid]["gives_to"], {uid}
    while nxt in ring and nxt not in seen:
        if ring[nxt]["here"]:
            return {"person": person_ref(one(con, PERSON + " WHERE u.id = ?", nxt)), "wish": ring[nxt]["wish"]}
        seen.add(nxt)
        nxt = ring[nxt]["gives_to"]
    return None


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
    """An account being deleted (account.delete_me, before its rows go): their Santa gives to their person instead."""
    con.execute("""UPDATE santa_people SET gives_to = (SELECT x.gives_to FROM santa_people x WHERE x.event_id = santa_people.event_id AND x.user_id = ?)
        WHERE gives_to = ?""", (uid, uid))


from .organizing import _staff_event  # noqa: E402  (they import core, core imports this)
from .seats import notify  # noqa: E402
