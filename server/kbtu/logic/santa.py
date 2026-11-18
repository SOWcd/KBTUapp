"""Secret Santa on an event (owner, Nov 17): the editor's switch; signing up asks a wishlist (its line under the field
is the feature's own consent: name and wishlist go to one participant); the organizer draws once, from three people
going: one random cycle, so nobody gives to themselves and everyone gives and receives once; sign-up closes with it
(no promotion from the waitlist either). Who loses their seat is out for good: db.py's triggers splice them from the ring.
Secrecy is the point: a pair and a wishlist are read in one place, view(), by the giver alone. No list, export, log or
audit row has them (the wishlist lives here, not in registrations.answers, which the organizers read).
Round 2 (Nov 18): a gift budget and the wishlists' deadline (the event's reg_until) set at the start; at the deadline the
bot's round draws by itself through the same _draw (tick()); reminders before the deadline and on the eve of the
gifts day, each once per person (notify's unique refs); the organizer's "remind those not in yet", once a day."""
from __future__ import annotations

import secrets
import sqlite3

from ..db import tx

from .core import PERSON, ApiError, Viewer, _may, full, now, one, person_ref, rights_of, rows

WISH_MAX = 300
MIN = 3
BUDGET = (100, 1_000_000)  # tenge: a gift's sane bounds
DAY = 86400

_GOING = """SELECT p.user_id FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
    AND r.status = 'going' WHERE p.event_id = ?"""
# who the draw takes: going with a wishlist, not banned and, on a team-only game, still in the club (after the draw the
# ring is fixed: a ban or leaving the club changes nobody's person, only a lost seat does)
_IN = _GOING + """ AND p.user_id IN (SELECT u.id FROM users u WHERE u.banned_at IS NULL)
    AND ((SELECT visibility FROM events WHERE id = p.event_id) = 'public' OR p.user_id IN (SELECT m.user_id FROM org_members m
      WHERE m.org_id = (SELECT org_id FROM events WHERE id = p.event_id)))"""
# the club's people not in yet (the reminders' and the organizer's list), the bot able to write to them for `reach`
_NOT_IN = """SELECT m.user_id FROM org_members m JOIN users u ON u.id = m.user_id AND u.banned_at IS NULL
    WHERE m.org_id = ? AND m.user_id NOT IN (""" + _IN + ")"
_REACH = " AND u.can_dm = 1 AND u.tg_id > 0"


def default_until(starts: int) -> int:
    """Wishlists until: a week before the gifts day; a game closer than that, halfway there."""
    return starts - 7 * DAY if starts - 7 * DAY > now() else now() + (starts - now()) // 2


def _budget(raw: object) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool) or not BUDGET[0] <= raw <= BUDGET[1]:
        raise ApiError("bad_input", "budget")
    return raw


def _until(raw: object, starts: int) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or not now() < raw <= starts:
        raise ApiError("bad_input", "until")
    return raw


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
        starts = body.get("startsAt")
        if not isinstance(starts, int) or isinstance(starts, bool):
            raise ApiError("bad_input")
        budget = _budget(body.get("budget"))
        until = _until(body["regUntil"], starts) if body.get("regUntil") is not None else default_until(starts) if starts > now() else None
        made = create_event(con, v, oid, {"title": body.get("title"), "place": "", "startsAt": starts, "regUntil": until, "emoji": "sparkles_3d",
                                          "color": "#D7263D", "visibility": "members", "santa": True})
        con.execute("UPDATE santa_games SET budget = ? WHERE event_id = ?", (budget, made["id"]))
        out = publish_event(con, v, made["id"])
        # a team-only event tells nobody by itself (owner, Nov 17: "how do I learn my club started it?"): the team hears once
        for r in rows(con, """SELECT m.user_id FROM org_members m JOIN users u ON u.id = m.user_id AND u.can_dm = 1 AND u.banned_at IS NULL
                WHERE m.org_id = ? AND m.user_id != ?""", oid, v.id):
            notify(con, r[0], "santa_open", f"event:{made['id']}")
        return out


def news(con, dry: bool = False, only: int | None = None) -> int:
    """`python -m kbtu.admin santa-news`: the tool's announcement, a template with a button into their Studio, queued
    once per person to every President and Vice of an active organization the bot can write to (their first one's
    Studio). Run by hand, never by a deploy; a second run queues only who became one since."""
    to = rows(con, """SELECT m.user_id, MIN(m.org_id) AS org FROM org_members m JOIN orgs o ON o.id = m.org_id AND o.status = 'active' AND o.kind != 'office'
        JOIN users u ON u.id = m.user_id AND u.can_dm = 1 AND u.banned_at IS NULL AND u.tg_id > 0
        WHERE m.role IN ('president', 'vice') AND (? IS NOT NULL OR NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = m.user_id AND b.kind = 'santa_news'))
          AND (? IS NULL OR m.user_id = ?)
        GROUP BY m.user_id ORDER BY m.user_id""", only, only, only)  # only: one person first, to read it as they will, again after each rewording
    if not dry:
        with tx(con):
            for r in to:
                notify(con, r["user_id"], "santa_news", f"sn:{r['org']}" + (f":{now()}" if only else ""))
    return len(to)


def parts(con, ids: list[int]) -> dict[int, dict]:
    """The card's part, the same for everyone: the game is on, the draw is done, the gift's budget (the deadline is regUntil)."""
    return {r[0]: {"drawn": bool(r[1]), **({"budget": r[2]} if r[2] else {})} for r in rows(con, f"""SELECT s.event_id, s.drawn_at, g.budget
        FROM santa_events s LEFT JOIN santa_games g ON g.event_id = s.event_id WHERE s.event_id IN ({','.join('?' * len(ids))})""", *ids)}


def settings(con, v: Viewer, eid: int, body: dict) -> dict:
    """The game's budget and deadline, by who runs the event, until the draw; a key left out is kept."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
        if not s or e["status"] != "published":
            raise ApiError("not_found")
        if s["drawn_at"]:
            raise ApiError("conflict", "drawn")
        if "budget" in body:
            con.execute("INSERT INTO santa_games (event_id, budget) VALUES (?, ?) ON CONFLICT (event_id) DO UPDATE SET budget = excluded.budget",
                        (eid, _budget(body["budget"])))
        if "regUntil" in body:
            con.execute("UPDATE events SET reg_until = ?, updated_at = ? WHERE id = ?", (_until(body["regUntil"], e["starts_at"]), now(), eid))
        con.execute("UPDATE events SET updated_at = ? WHERE id = ?", (now(), eid))  # lists' cached cards see the budget
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


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
        con.execute("INSERT OR IGNORE INTO santa_games (event_id) VALUES (?)", (eid,))


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
        why = _draw(con, _staff_event(con, v, eid, "events"))
        if why:
            raise ApiError("not_found") if why == "not_found" else ApiError("conflict", why)
    return full(con, v, one(con, "SELECT * FROM events WHERE id = ?", eid))


def _draw(con, e: sqlite3.Row) -> str | None:
    """The one draw, inside the caller's write transaction (draw by hand, tick() at the deadline): None when drawn,
    else why not. BEGIN IMMEDIATE serialises it: a second worker's attempt finds drawn_at set."""
    eid = e["id"]
    s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
    if not s or e["status"] != "published":
        return "not_found"
    if s["drawn_at"]:
        return "drawn"
    if one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
        return "holds"  # a seat being paid for would land in a drawn game with no Santa
    ids = [r[0] for r in rows(con, _IN, eid)]
    if len(ids) < MIN:
        return "few"
    # who isn't in (cancelled, the waitlist, banned, out of the club) is out for good: every row left is someone in the cycle
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
    return None


def _heads(con, e: sqlite3.Row) -> list[int]:
    """Its club's President and the Vices who may run events: whom the round tells what the game is missing."""
    return [r[0] for r in rows(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role IN ('president', 'vice') ORDER BY user_id", e["org_id"])
            if "events" in rights_of(con, r[0], e["org_id"])]


def remind(con, v: Viewer, eid: int) -> dict:
    """The organizer's "Remind those not in yet": a template to each of the club's people the bot can write to and who
    hasn't joined, once per person per game (the ref), the button once a day per game."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        s = one(con, "SELECT s.drawn_at, g.nudged_at FROM santa_events s LEFT JOIN santa_games g ON g.event_id = s.event_id WHERE s.event_id = ?", eid)
        if not s or e["status"] != "published" or s["drawn_at"] or e["reg_until"] and e["reg_until"] <= now():
            raise ApiError("closed")
        if s["nudged_at"] and s["nudged_at"] + DAY > now():
            raise ApiError("conflict", "soon")
        to = _nudgeable(con, e, v.id)
        for uid in to:
            notify(con, uid, "santa_nudge", f"sr:{eid}")
        if to:
            con.execute("INSERT INTO santa_games (event_id, nudged_at) VALUES (?, ?) ON CONFLICT (event_id) DO UPDATE SET nudged_at = excluded.nudged_at",
                        (eid, now()))
    return {"n": len(to), "nudgeAt": now() + DAY if to else None}


def _nudgeable(con, e: sqlite3.Row, me: int) -> list[int]:
    """Whom the reminder would reach: not in, the bot can write to them, not reminded before; never who presses it."""
    return [r[0] for r in rows(con, _NOT_IN + _REACH + f" AND m.user_id != {int(me)}" + """ AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = m.user_id
        AND b.kind = 'santa_nudge' AND b.ref = ?) ORDER BY m.user_id""", e["org_id"], e["id"], f"sr:{e['id']}")]


def tick(con) -> None:
    """The postman's round (bot._chores), the game's clock: one read of the running games whose next step is due (a
    handful of rows; a step done is marked in santa_games, so a game is read again only when its next step comes).
    At the deadline: the draw; too few: the President and Vices hear it once per deadline (a moved deadline re-arms
    it); a seat being paid for: the next round tries again (a hold lasts 30 minutes). A day before the deadline: those
    not in yet; a day before the gifts day: those playing."""
    t = now()
    for g in rows(con, """SELECT e.*, s.drawn_at, g.checked, g.soon, g.eve FROM santa_events s JOIN santa_games g ON g.event_id = s.event_id
            JOIN events e ON e.id = s.event_id WHERE e.status = 'published' AND e.hidden_at IS NULL AND e.starts_at > ?
            AND (s.drawn_at IS NULL AND e.reg_until IS NOT NULL AND (e.reg_until <= ? AND COALESCE(g.checked, 0) != e.reg_until
                                                                     OR e.reg_until - ? <= ? AND g.soon IS NULL)
                 OR s.drawn_at IS NOT NULL AND g.eve IS NULL AND e.starts_at - ? <= ?)""", t, t, DAY, t, DAY, t):
        if g["drawn_at"]:
            _eve(con, g)
        elif g["reg_until"] <= t:
            _deadline(con, g["id"])
        else:
            with tx(con):
                for (uid,) in rows(con, _NOT_IN + _REACH + " ORDER BY m.user_id", g["org_id"], g["id"]):
                    notify(con, uid, "santa_soon", f"sw:{g['id']}")
                con.execute("UPDATE santa_games SET soon = ? WHERE event_id = ?", (t, g["id"]))


def _deadline(con, eid: int) -> str | None:
    """The wishlists' deadline came: the draw, as by hand. Returns what _draw said ("busy": already done elsewhere)."""
    if one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND status = 'hold'", eid):
        return "holds"  # read before taking the write lock: a hold resolves itself within 30 minutes
    with tx(con):
        e = one(con, """SELECT e.* FROM events e JOIN santa_events s ON s.event_id = e.id JOIN santa_games g ON g.event_id = e.id
            WHERE e.id = ? AND s.drawn_at IS NULL AND e.reg_until <= ? AND COALESCE(g.checked, 0) != e.reg_until""", eid, now())
        if not e:
            return "busy"  # another worker's round took it first
        why = _draw(con, e)
        if why == "holds":
            return why
        if why == "few":
            for uid in _heads(con, e):
                notify(con, uid, "santa_few", f"sk:{eid}:{e['reg_until']}")
        con.execute("UPDATE santa_games SET checked = ? WHERE event_id = ?", (e["reg_until"], eid))
        return why


def _eve(con, g: sqlite3.Row) -> None:
    """A day before the gifts day, each one playing hears it once; a game drawn on its eve already heard of the draw."""
    with tx(con):
        if g["drawn_at"] < g["starts_at"] - DAY:
            for (uid,) in rows(con, _GOING + " ORDER BY p.user_id", g["id"]):  # by user id, never the ring's order
                notify(con, uid, "santa_eve", f"se:{g['id']}")
        con.execute("UPDATE santa_games SET eve = ? WHERE event_id = ?", (now(), g["id"]))


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
    out: dict = {}
    if head and s["drawn_at"]:
        out["santaN"] = len(rows(con, _GOING, e["id"]))
    elif head:  # the organizer's list before the draw: who is in, who of the club not yet; names only, never a wishlist
        ins = [r[0] for r in rows(con, _IN, e["id"])]
        outs = [r[0] for r in rows(con, _NOT_IN, e["org_id"], e["id"])]
        people = {p["id"]: person_ref(p) for p in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(ins + outs))})", *ins, *outs)} if ins + outs else {}
        names = lambda ids: sorted((people[i] for i in ids if i in people), key=lambda p: p["name"].lower())  # noqa: E731
        g = one(con, "SELECT nudged_at FROM santa_games WHERE event_id = ?", e["id"])
        at = g["nudged_at"] + DAY if g and g["nudged_at"] and g["nudged_at"] + DAY > now() else None
        out |= {"santaN": len(ins), "santaTeam": {"in": names(ins), "out": names(outs), "remind": len(_nudgeable(con, e, v.id)), "remindAt": at}}
    me = one(con, """SELECT p.wish FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
        AND r.status = 'going' WHERE p.event_id = ? AND p.user_id = ?""", e["id"], v.id)
    if me:
        out["mySanta"] = {"wish": me["wish"], **({"to": _to(con, e["id"], v.id)} if s["drawn_at"] else {})}
    return out


def gone(con, uid: int) -> None:
    """An account being deleted (account.delete_me, before its rows go): their Santa gives to their person instead
    (a seat already lost did this through the triggers; this covers whatever row is left). That Santa hears their
    person changed, as after a cancelled seat (migration 184's trigger)."""
    for r in rows(con, """SELECT g.event_id, g.user_id FROM santa_people g JOIN santa_people l ON l.event_id = g.event_id AND l.user_id = g.gives_to
            JOIN santa_events s ON s.event_id = g.event_id AND s.drawn_at IS NOT NULL WHERE g.gives_to = ? AND l.gives_to != g.user_id""", uid):
        notify(con, r["user_id"], "santa_changed", f"event:{r['event_id']}:{secrets.token_hex(6)}")
    con.execute("""UPDATE santa_people SET gives_to = (SELECT x.gives_to FROM santa_people x WHERE x.event_id = santa_people.event_id AND x.user_id = ?)
        WHERE gives_to = ?""", (uid, uid))


from .organizing import _staff_event, create_event, publish_event  # noqa: E402  (they import core, core imports this)
from .seats import notify  # noqa: E402
