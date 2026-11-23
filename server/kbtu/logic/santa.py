"""Secret Santa on an event: the editor's switch; signing up asks a wishlist (its line under the field
is the feature's own consent: name and wishlist go to one participant); the organizer draws once, from three people
going: one random cycle, so nobody gives to themselves and everyone gives and receives once; sign-up closes with it
(no promotion from the waitlist either). Who loses their seat is out for good: db.py's triggers splice them from the ring.
Secrecy is the point: a pair and a wishlist are read in one place, view(), by the giver alone. No list, export, log or
audit row has them (the wishlist lives here, not in registrations.answers, which the organizers read).
A gift budget and the wishlists' deadline (the event's reg_until) set at the start; at the deadline the
bot's round draws by itself through the same _draw (tick()); reminders before the deadline and on the eve of the
gifts day, each once per person (notify's unique refs); the organizer's "remind those not in yet", once a day.
After the draw the two of a pair may write to each other (chat, write, report): one thread per pair, the receiver never
told who their Santa is; no list, export, log or audit row has a message; gone 3 days after the gifts day. A report by
either closes the thread and shows it, with its two people, to the app's staff alone (Admin: reports, report_done)."""
from __future__ import annotations

import secrets
import sqlite3

from ..db import tx

from .core import PERSON, ApiError, Viewer, _may, full, log_action, now, one, person_ref, rights_of, rows

WISH_MAX = 300
MIN = 3
BUDGET = (100, 1_000_000)  # tenge: a gift's sane bounds
DAY = 86400
MSG_MAX, MSG_DAY, MSG_KEEP = 500, 50, 3 * DAY  # the chat: a message's length, mine a day, how long after the gifts day it lives
REPORT_KEEP = 30 * DAY  # a reported thread: that long after the gifts day, and until the staff handled it
LEAD = 3600  # the wishlists close an hour before the gifts day at the latest: the round needs the moment to draw

_GOING = """SELECT p.user_id FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
    AND r.status = 'going' WHERE p.event_id = ?"""
# who the draw takes: going with a wishlist, not banned and, on a team-only game, still in the club (after the draw the
# ring is fixed: a ban or leaving the club changes nobody's person, only a lost seat does)
_IN = _GOING + """ AND p.user_id IN (SELECT u.id FROM users u WHERE u.banned_at IS NULL)
    AND ((SELECT visibility FROM events WHERE id = p.event_id) = 'public' OR p.user_id IN (SELECT m.user_id FROM org_members m
      WHERE m.org_id = (SELECT org_id FROM events WHERE id = p.event_id)))"""
# the club's people not in yet (the reminders' and the organizer's list); _not_in() keeps whom the game is for
_NOT_IN = """SELECT m.user_id FROM org_members m JOIN users u ON u.id = m.user_id AND u.banned_at IS NULL
    WHERE m.org_id = ? AND m.user_id NOT IN (""" + _IN + ")"
_REACH = " AND u.can_dm = 1 AND u.tg_id > 0"


def default_until(starts: int) -> int:
    """Wishlists until: a week before the gifts day; a game closer than that, halfway there; an hour before it at the latest."""
    return min(starts - LEAD, starts - 7 * DAY if starts - 7 * DAY > now() else now() + (starts - now()) // 2)


def _for(con, e: sqlite3.Row, uid: int) -> bool:
    """The game is for this member: seats.for_me's "For whom" (the editor refuses the board or a tag on a Santa game,
    check_event; this keeps the reminders and the list right whatever audience rule comes next)."""
    m = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", e["org_id"], uid)
    return bool(m) and for_me(con, Viewer(uid, "user", True), e, m["role"])


def _not_in(con, e: sqlite3.Row, reach: bool = False) -> list[int]:
    """The club's people the game is for who are not in yet (`reach`: the bot can write to them)."""
    ids = [r[0] for r in rows(con, _NOT_IN + (_REACH if reach else "") + " ORDER BY m.user_id", e["org_id"], e["id"])]
    return ids if not e["meeting_tag"] and not e["for_board"] else [u for u in ids if _for(con, e, u)]


def check_event(con, eid: int, f: dict) -> None:
    """The editor's save on a Santa game, inside its transaction: it is for the whole team (no board, tag or meeting:
    the reminders and the list go to the club), and its wishlists close an hour before the gifts day at the latest."""
    s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
    if not s:
        return
    if f.get("for_board") or f.get("meeting_tag") or f.get("meeting"):
        raise ApiError("bad_input", "santa_audience")
    if not s["drawn_at"] and f.get("reg_until") is not None and f["reg_until"] > f["starts_at"] - LEAD:
        raise ApiError("bad_input", "santa_until")


def _budget(raw: object) -> int:
    # required, at least a rough sum; a game started without one keeps its empty one
    if not isinstance(raw, int) or isinstance(raw, bool) or not BUDGET[0] <= raw <= BUDGET[1]:
        raise ApiError("bad_input", "budget")
    return raw


def _until(raw: object, starts: int) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool) or not now() < raw <= starts - LEAD:
        raise ApiError("bad_input", "until")
    return raw


def start(con, v: Viewer, oid: int, body: dict) -> dict:
    """Studio's one button (a person presses it and the game is there, no event form): a published
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
        until = _until(body["regUntil"], starts) if body.get("regUntil") is not None else default_until(starts) if starts > now() + LEAD else None
        made = create_event(con, v, oid, {"title": body.get("title"), "place": "", "startsAt": starts, "regUntil": until, "emoji": "sparkles_3d",
                                          "color": "#D7263D", "visibility": "members", "santa": True, "seats": None})
        # a deadline within a day: the invite is the reminder (no "closes tomorrow" seconds after it)
        con.execute("UPDATE santa_games SET budget = ?, soon = ? WHERE event_id = ?", (budget, now() if until and until - DAY <= now() else None, made["id"]))
        out = publish_event(con, v, made["id"])
        # a team-only event tells nobody by itself (the club wouldn't learn the game started): the team hears
        # once, and once a day per club at most, whatever game it is (one stopped and started again is no new news)
        e = one(con, "SELECT * FROM events WHERE id = ?", made["id"])
        told = [u for u in _not_in(con, e, reach=True) if u != v.id and not one(con, """SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'santa_open'
            AND ref LIKE ? AND send_after > ?""", u, f"so:{oid}:%", now() - DAY)]
        for uid in told:
            notify(con, uid, "santa_open", f"so:{oid}:{made['id']}")
        return {**out, "santaTold": len(told)}


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
    """The game's budget and deadline, by who runs the event, until the draw; a key left out is kept (a budget sent is a sum)."""
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
            until = _until(body["regUntil"], e["starts_at"])
            con.execute("UPDATE events SET reg_until = ?, updated_at = ? WHERE id = ?", (until, now(), eid))
            if until - DAY <= now():  # within a day: no "closes tomorrow" on top of whatever the club just heard
                con.execute("UPDATE santa_games SET soon = COALESCE(soon, ?) WHERE event_id = ?", (now(), eid))
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
    con.execute("INSERT OR REPLACE INTO santa_people (event_id, user_id, wish) VALUES (?, ?, ?)", (eid, uid, _clean(raw)))


def _clean(raw: object) -> str:
    """A wishlist as kept: one line of words, 2 to WISH_MAX characters (at sign-up and when changed)."""
    w = " ".join(raw.split()) if isinstance(raw, str) else ""
    if not 2 <= len(w) <= WISH_MAX:
        raise ApiError("bad_input", "wish")
    return w


def rewish(con, v: Viewer, eid: int, raw: object) -> dict:
    """My own wishlist changed, while I'm going in a published game, before and after the draw until the gifts day
    starts: my Santa simply reads the newest. After the draw they hear it (a template, no words of mine) at most once a
    day per game; their row is found through mine, and the answer says nothing of who they are."""
    w = _clean(raw)
    with tx(con):
        e = one(con, """SELECT e.starts_at, s.drawn_at FROM events e JOIN santa_events s ON s.event_id = e.id
            WHERE e.id = ? AND e.status = 'published' AND e.hidden_at IS NULL""", eid)
        if not e:
            raise ApiError("not_found")
        if e["starts_at"] <= now():
            raise ApiError("closed")
        me = one(con, _GOING + " AND p.user_id = ?", eid, v.id)
        if not me:
            raise ApiError("forbidden")
        if con.execute("UPDATE santa_people SET wish = ? WHERE event_id = ? AND user_id = ? AND wish != ?", (w, eid, v.id, w)).rowcount and e["drawn_at"]:
            g = one(con, "SELECT user_id FROM santa_people WHERE event_id = ? AND gives_to = ? AND user_id != ?", eid, v.id, v.id)
            if g and not one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'santa_wish' AND ref LIKE ? AND send_after > ?",
                             g[0], f"event:{eid}:%", now() - DAY):
                notify(con, g[0], "santa_wish", f"event:{eid}:{now()}")
    return {"wish": w}


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
    hasn't joined, once per person per game (the ref), the button once a day per club (a game started again included)."""
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        s = one(con, "SELECT drawn_at FROM santa_events WHERE event_id = ?", eid)
        if not s or e["status"] != "published" or s["drawn_at"] or e["reg_until"] and e["reg_until"] <= now():
            raise ApiError("closed")
        if _remind_at(con, e):
            raise ApiError("conflict", "soon")
        to = _nudgeable(con, e, v.id)
        for uid in to:
            notify(con, uid, "santa_nudge", f"sr:{e['org_id']}:{eid}")
        if to:
            con.execute("INSERT INTO santa_games (event_id, nudged_at) VALUES (?, ?) ON CONFLICT (event_id) DO UPDATE SET nudged_at = excluded.nudged_at",
                        (eid, now()))
    return {"n": len(to), "nudgeAt": now() + DAY if to else None}


def _nudgeable(con, e: sqlite3.Row, me: int) -> list[int]:
    """Whom the reminder would reach: not in, the bot can write to them, not reminded in this game; never who presses it."""
    return [u for u in _not_in(con, e, reach=True) if u != me and not one(
        con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'santa_nudge' AND ref = ?", u, f"sr:{e['org_id']}:{e['id']}")]


def _remind_at(con, e: sqlite3.Row) -> int | None:
    """When the club's reminder button works again (None: now): a day after its last use in any of the club's games."""
    last = one(con, "SELECT MAX(g.nudged_at) FROM santa_games g JOIN events x ON x.id = g.event_id WHERE x.org_id = ?", e["org_id"])[0]
    return last + DAY if last and last + DAY > now() else None


def tick(con) -> None:
    """The postman's round (bot._chores), the game's clock: one read of the running games whose next step is due (a
    handful of rows; a step done is marked in santa_games, so a game is read again only when its next step comes, and
    a round with nothing due writes nothing). At the deadline: the draw; too few: the President and Vices hear it once
    per deadline (a moved deadline re-arms it); a seat being paid for: the next round looks again, read-only (a hold
    lasts 30 minutes). A day before the deadline: those not in yet; a day before the gifts day: those playing (again if
    the day moves); the gifts day come undrawn (no deadline, late sign-up): the President and Vices, once."""
    t = now()
    for g in rows(con, """SELECT e.*, s.drawn_at FROM santa_events s JOIN santa_games g ON g.event_id = s.event_id
            JOIN events e ON e.id = s.event_id WHERE e.status = 'published' AND e.hidden_at IS NULL
            AND (s.drawn_at IS NULL AND e.starts_at > ? AND e.reg_until <= ? AND COALESCE(g.checked, 0) != e.reg_until
              OR s.drawn_at IS NULL AND e.reg_until > ? AND e.reg_until - ? <= ? AND g.soon IS NULL
              OR s.drawn_at IS NOT NULL AND e.starts_at > ? AND e.starts_at - ? <= ? AND COALESCE(g.eve, 0) != e.starts_at
              OR s.drawn_at IS NULL AND e.starts_at <= ? AND e.starts_at > ? AND COALESCE(g.late, 0) != e.starts_at)""",
            t, t, t, DAY, t, t, DAY, t, t, t - DAY):
        if g["drawn_at"]:
            _eve(con, g)
        elif g["starts_at"] <= t:
            with tx(con):
                for uid in _heads(con, g):
                    notify(con, uid, "santa_late", f"sl:{g['id']}:{g['starts_at']}")
                con.execute("UPDATE santa_games SET late = ? WHERE event_id = ?", (g["starts_at"], g["id"]))
        elif g["reg_until"] <= t:
            _deadline(con, g["id"])
        else:
            with tx(con):  # never to who started the game: they set that deadline
                for uid in _not_in(con, g, reach=True):
                    if uid != g["created_by"]:
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
    """A day before the gifts day, each one playing with a person to give to hears it, once per gifts day (a moved day
    is a new eve); a game drawn on its eve already heard of the draw."""
    with tx(con):
        if g["drawn_at"] < g["starts_at"] - DAY:
            for (uid,) in rows(con, _GOING + " AND p.gives_to != p.user_id ORDER BY p.user_id", g["id"]):  # by user id, never the ring's order
                notify(con, uid, "santa_eve", f"se:{g['id']}:{g['starts_at']}")
        con.execute("UPDATE santa_games SET eve = ? WHERE event_id = ?", (g["starts_at"], g["id"]))


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
        outs = _not_in(con, e)
        people = {p["id"]: person_ref(p) for p in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(ins + outs))})", *ins, *outs)} if ins + outs else {}
        names = lambda ids: sorted((people[i] for i in ids if i in people), key=lambda p: p["name"].lower())  # noqa: E731
        at = _remind_at(con, e)
        out |= {"santaN": len(ins), "santaTeam": {"in": names(ins), "out": names(outs), "remind": len(_nudgeable(con, e, v.id)), "remindAt": at}}
    me = one(con, """SELECT p.wish FROM santa_people p JOIN registrations r ON r.event_id = p.event_id AND r.user_id = p.user_id
        AND r.status = 'going' WHERE p.event_id = ? AND p.user_id = ?""", e["id"], v.id)
    if me:
        out["mySanta"] = {"wish": me["wish"], **({"to": _to(con, e["id"], v.id)} if s["drawn_at"] else {})}
    return out


def _thread(con, eid: int, uid: int, mine: bool) -> tuple[int, int] | None:
    """A thread's two people (giver, receiver), read off the ring by my own row alone, never from the client. mine: the
    one where I am the Santa; else the one with my Santa. None: no such pair, or no game to talk in (not drawn, not
    published, MSG_KEEP past the gifts day, or I'm not playing): the same answer to an organizer and a stranger."""
    r = one(con, f"""SELECT p.user_id, p.gives_to FROM santa_people p JOIN santa_events s ON s.event_id = p.event_id AND s.drawn_at IS NOT NULL
        JOIN events e ON e.id = p.event_id AND e.status = 'published' AND e.hidden_at IS NULL AND COALESCE(e.ends_at, e.starts_at) + ? > ?
        WHERE p.event_id = ? AND p.{'user_id' if mine else 'gives_to'} = ? AND p.gives_to != p.user_id""", MSG_KEEP, now(), eid, uid)
    return (r[0], r[1]) if r and one(con, _GOING + " AND p.user_id = ?", eid, uid) else None


_MSGS = "FROM santa_msgs WHERE event_id = ? AND giver_id = ? AND to_id = ?"


def chat(con, v: Viewer, eid: int) -> dict:
    """My two threads in a drawn game: `to`, where I write as the Santa of my person (named on the event's page), and
    `from`, with my own Santa. A message says only whether it is mine: never an id or a name, so my Santa stays secret."""
    out = {}
    for side in ("to", "from"):
        p = _thread(con, eid, v.id, side == "to")
        ms = rows(con, f"SELECT id, from_giver, text, created_at {_MSGS} ORDER BY id", eid, *p) if p else []
        closed = any(m["text"] is None for m in ms)  # reported: shut for both, its words now the staff's to read
        out[side] = {"closed": closed, "msgs": [] if closed else [
            {"id": m["id"], "mine": bool(m["from_giver"]) == (side == "to"), "text": m["text"], "at": m["created_at"]} for m in ms]} if p else None
    if not any(out.values()):
        raise ApiError("not_found")
    return out


def _side(body: dict) -> bool:
    if body.get("side") not in ("to", "from"):
        raise ApiError("bad_input")
    return body["side"] == "to"


def write(con, v: Viewer, eid: int, body: dict) -> dict:
    """A message into one of my two threads: plain words, one line, up to MSG_MAX; MSG_DAY a day per person. The other
    one hears it from the bot: a template with no words of mine, once an hour per thread at most."""
    mine = _side(body)
    text = " ".join(body["text"].split()) if isinstance(body.get("text"), str) else ""
    if not 1 <= len(text) <= MSG_MAX:
        raise ApiError("bad_input", "text")
    with tx(con):  # the count and the insert as one: parallel taps can't pass the day's limit
        p = _thread(con, eid, v.id, mine)
        if not p:
            raise ApiError("not_found")
        if one(con, f"SELECT 1 {_MSGS} AND text IS NULL", eid, *p):
            raise ApiError("closed")
        # ponytail: the day's count reads my threads through two indexes (giver, receiver); a sender column if it shows up slow
        if one(con, """SELECT COUNT(*) FROM santa_msgs WHERE created_at > ? AND text IS NOT NULL
                AND (giver_id = ? AND from_giver = 1 OR to_id = ? AND from_giver = 0)""", now() - DAY, v.id, v.id)[0] >= MSG_DAY:
            raise ApiError("rate_limited", "santa_msgs")
        mid = con.execute("INSERT INTO santa_msgs (event_id, giver_id, to_id, from_giver, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (eid, *p, int(mine), text, now())).lastrowid
        other, kind = (p[1], "santa_msg") if mine else (p[0], "santa_reply")
        if not one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = ? AND ref LIKE ? AND send_after > ?", other, kind, f"event:{eid}:%", now() - 3600):
            notify(con, other, kind, f"event:{eid}:{now()}")
    return {"id": mid, "mine": True, "text": text, "at": now()}


def report(con, v: Viewer, eid: int, body: dict) -> None:
    """Report on a thread, by either of its two: nobody writes in it again, and it goes to the app's staff (Admin),
    the only ones who then read it and see both its people. The staff hear it from the bot, a template."""
    mine = _side(body)
    with tx(con):
        p = _thread(con, eid, v.id, mine)
        if not p:
            raise ApiError("not_found")
        if one(con, f"SELECT 1 {_MSGS} AND text IS NULL", eid, *p):
            return
        rid = con.execute("INSERT INTO santa_msgs (event_id, giver_id, to_id, from_giver, created_at) VALUES (?, ?, ?, ?, ?)",
                          (eid, *p, int(mine), now())).lastrowid
        notify_staff(con, _mods(con), "santa_reported", f"srp:{rid}")


_OPEN = "FROM santa_msgs WHERE text IS NULL AND done_at IS NULL"


def reports(con, v: Viewer) -> list[dict]:
    """Admin → Santa reports, the app's staff alone (never a club's organizer): each open report with the whole thread
    and both its people, oldest first."""
    _mod(v)
    out = []
    for r in rows(con, f"SELECT id, event_id, giver_id, to_id, from_giver, created_at {_OPEN} ORDER BY id"):
        who = {p["id"]: person_ref(p) for p in rows(con, PERSON + " WHERE u.id IN (?, ?)", r["giver_id"], r["to_id"])}
        e = one(con, "SELECT title FROM events WHERE id = ?", r["event_id"])
        out.append({"id": r["id"], "at": r["created_at"], "title": e["title"], "giver": who.get(r["giver_id"]), "to": who.get(r["to_id"]),
                    "byGiver": bool(r["from_giver"]),
                    "msgs": [{"id": m["id"], "fromGiver": bool(m["from_giver"]), "text": m["text"], "at": m["created_at"]} for m in rows(
                        con, f"SELECT id, from_giver, text, created_at {_MSGS} AND text IS NOT NULL ORDER BY id", r["event_id"], r["giver_id"], r["to_id"])]})
    return out


def report_done(con, v: Viewer, rid: int) -> None:
    """The staff handled a report (whatever they did about it, with their own tools): it leaves the list; the audit
    log keeps who and which report, never the pair or a word."""
    _mod(v)
    with tx(con):
        if not con.execute("UPDATE santa_msgs SET done_at = ? WHERE id = ? AND text IS NULL AND done_at IS NULL", (now(), rid)).rowcount:
            raise ApiError("not_found")
        log_action(con, v.id, "santa_report_done", f"santa_report:{rid}")


def forget(con) -> None:
    """The nightly sweep (daily.stats_day): a thread goes MSG_KEEP after the gifts day; a reported one REPORT_KEEP after
    it, and not before the staff handled it."""
    con.execute("""DELETE FROM santa_msgs WHERE id IN (SELECT m.id FROM santa_msgs m JOIN events e ON e.id = m.event_id
        LEFT JOIN santa_msgs r ON r.event_id = m.event_id AND r.giver_id = m.giver_id AND r.to_id = m.to_id AND r.text IS NULL
        WHERE CASE WHEN r.id IS NULL THEN COALESCE(e.ends_at, e.starts_at) + ? <= ?
                   ELSE r.done_at IS NOT NULL AND COALESCE(e.ends_at, e.starts_at) + ? <= ? END)""", (MSG_KEEP, now(), REPORT_KEEP, now()))


def gone(con, uid: int) -> None:
    """An account being deleted (account.delete_me, before its rows go): out of every drawn game as a lost seat is
    (migration 184's triggers relink the ring and tell who is affected); whatever row is left is relinked here."""
    con.execute("""UPDATE registrations SET status = 'cancelled', cancel_reason = 'removed', updated_at = ? WHERE user_id = ? AND status = 'going'
        AND event_id IN (SELECT event_id FROM santa_events WHERE drawn_at IS NOT NULL)""", (now(), uid))
    con.execute("""UPDATE santa_people SET gives_to = (SELECT x.gives_to FROM santa_people x WHERE x.event_id = santa_people.event_id AND x.user_id = ?)
        WHERE gives_to = ?""", (uid, uid))


def drop(con, uid: int, oid: int | None = None) -> None:
    """Out of the club `oid` (left, removed) or banned (None), inside the caller's transaction: their seat in that club's
    upcoming team-only Santa games (all upcoming ones when banned: they can't open their person any more) goes the way
    seats.joined takes a seat, the waitlist moving into it; the triggers relink a drawn ring and tell their Santa.
    Lifting a ban gives nothing back."""
    for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id JOIN santa_events s ON s.event_id = e.id
            WHERE r.user_id = ? AND r.status IN ('going', 'waitlist') AND e.status = 'published' AND e.starts_at > ?
            AND (? IS NULL OR e.org_id = ? AND e.visibility = 'members')""", uid, now(), oid, oid):
        con.execute("""UPDATE registrations SET status = 'cancelled', cancel_reason = 'removed', hold_until = NULL, waitlisted_at = NULL, updated_at = ?
            WHERE event_id = ? AND user_id = ?""", (now(), e["id"], uid))
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND ref LIKE ? AND sent_at IS NULL", (uid, f"event:{e['id']}:%"))
        promote(con, e)


from .organizing import _staff_event, create_event, publish_event  # noqa: E402  (they import core, core imports this)
from .tgcomments import _mods  # noqa: E402
from .oversight import _mod  # noqa: E402
from .seats import for_me, notify, notify_staff, promote  # noqa: E402
