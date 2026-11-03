"""Co-hosted events (Nov 3, "Crystal & JCC do an Anime Quiz together"): the host club (the event's org) invites one
other club of the app; its Vice+ accepts or declines. Until accepted nothing shows. Accepted, both clubs show on the
event, it is on both clubs' pages and both clubs' followers hear of it once; the co-host's people with the "events"
right work the door (the scanner, by name, /show) and see the attendee list without receipts. Everything else
(editing, price, seats, receipts, cancelling, deleting) stays the host's; the money goes to the host. Either side ends
it: the host removes, the co-host's Vice+ leaves. Not a partner's event (guest_host: an outside host, a link out).
The review: .claude/reports/cohost-review.md."""
from __future__ import annotations

import json
import sqlite3

from ..db import tx

from .core import ApiError, Viewer, at_least, can, full, one, org_ref, role_in, rows


COHOST_INVITES_A_DAY = 10  # a host club's invites (each one messages the other club's leaders)
# the co-host's accepted row, its club still shown (hidden or archived later: gone from the card and the door)
ACCEPTED = """SELECT x.*, o.name FROM event_cohosts x JOIN orgs o ON o.id = x.org_id
    WHERE x.event_id = ? AND x.status = 'accepted' AND o.status = 'active'"""


def co_runs(con, v: Viewer, eid: int) -> bool:
    """I run this event as its co-host: the "events" right in its accepted co-host club."""
    x = v.student and one(con, ACCEPTED, eid)
    return bool(x and can(con, v, x["org_id"], "events"))


def runs(con, v: Viewer, e: sqlite3.Row) -> bool:
    """Whoever runs the event: the host's events right or the co-host's (the door's self check-in, full names)."""
    return can(con, v, e["org_id"], "events") or co_runs(con, v, e["id"])


def cohosts_of(con, ids: list[int]) -> dict[int, sqlite3.Row]:
    """The accepted, shown co-host club of each event, in one query (a list of cards)."""
    if not ids:
        return {}
    return {r["event_id"]: r for r in rows(con, f"""SELECT x.event_id, o.* FROM event_cohosts x JOIN orgs o ON o.id = x.org_id
        WHERE x.event_id IN ({','.join('?' * len(ids))}) AND x.status = 'accepted' AND o.status = 'active'""", *ids)}


def cohost_view(con, e: sqlite3.Row) -> dict | None:
    """The host team's view in the editor: the invited club and where it stands (pending, accepted, declined)."""
    x = one(con, """SELECT x.status, o.* FROM event_cohosts x JOIN orgs o ON o.id = x.org_id WHERE x.event_id = ?
        ORDER BY x.status = 'declined', x.created_at DESC LIMIT 1""", e["id"])
    return {"org": org_ref(con, x), "status": x["status"]} if x else None


def _fits(e: sqlite3.Row) -> bool:
    """A co-host only on a public event that is no meeting and no partner's (review 1)."""
    return e["visibility"] == "public" and not e["meeting"] and not e["guest_host"]


def _over(e: sqlite3.Row) -> bool:
    return e["status"] == "cancelled" or end_of(e) <= core.now()


def _leaders(con, oid: int) -> list[int]:
    return [r[0] for r in rows(con, """SELECT m.user_id FROM org_members m JOIN students s ON s.user_id = m.user_id
        WHERE m.org_id = ? AND m.role IN ('president', 'vice')""", oid)]


def _touch(con, eid: int) -> None:
    """The card changed: Afisha's shared cache is keyed by the events row (review 10), so every worker rebuilds it."""
    con.execute("UPDATE events SET updated_at = ? WHERE id = ?", (core.now(), eid))
    core._SHARED.pop(("event", eid), None)


def invite(con, v: Viewer, eid: int, oid: object) -> dict:
    """The host's "Invite a club" (the events right): one active club, not ours, on a public event still ahead."""
    if not isinstance(oid, int) or isinstance(oid, bool):
        raise ApiError("bad_input")
    with tx(con):
        e = _staff_event(con, v, eid, "events")
        if _over(e):
            raise ApiError("closed")
        if not _fits(e):
            raise ApiError("bad_input", "cohost")
        if oid == e["org_id"] or not one(con, "SELECT 1 FROM orgs WHERE id = ? AND kind = 'club' AND status = 'active'", oid):
            raise ApiError("bad_input")
        if one(con, "SELECT 1 FROM event_cohosts WHERE event_id = ? AND status != 'declined'", eid):
            raise ApiError("conflict", "cohost")  # ponytail: one co-host per event; more later
        if one(con, "SELECT 1 FROM event_cohosts WHERE event_id = ? AND org_id = ?", eid, oid):
            raise ApiError("conflict", "declined")  # they said no to this one: not asked again
        # counted apart from the rows, which a withdrawal deletes (second review): per host club and Almaty day
        day = f"cohost_inv:{e['org_id']}:{(core.now() + 5 * 3600) // 86400}"
        sent = one(con, "SELECT value FROM meta WHERE key = ?", day)
        if sent and int(sent[0]) >= COHOST_INVITES_A_DAY:
            raise ApiError("rate_limited")
        con.execute("DELETE FROM meta WHERE key LIKE 'cohost_inv:' || ? || ':%' AND key != ?", (e["org_id"], day))  # yesterday's
        con.execute("INSERT INTO meta (key, value) VALUES (?, '1') ON CONFLICT (key) DO UPDATE SET value = CAST(value AS INTEGER) + 1", (day,))
        con.execute("INSERT INTO event_cohosts (event_id, org_id, invited_by, created_at) VALUES (?, ?, ?, ?)", (eid, oid, v.id, core.now()))
        for uid in _leaders(con, oid):
            notify(con, uid, "cohost_invite", f"ch:{eid}:{oid}")  # once per event and club (the outbox key)
    return full(con, v, e)


def invites(con, v: Viewer, oid: int) -> list[dict]:
    """The invites waiting for this club's answer (its Vice+, Studio's To do): the event, its host, when and where.
    A host's draft is shown here so far, to decide on: its title, time and place only."""
    if not at_least(role_in(con, v, oid), "vice"):
        raise ApiError("forbidden")
    found = rows(con, """SELECT e.*, x.created_at AS asked FROM event_cohosts x JOIN events e ON e.id = x.event_id
        JOIN orgs h ON h.id = e.org_id JOIN orgs c ON c.id = x.org_id AND c.status = 'active'
        WHERE x.org_id = ? AND x.status = 'pending' AND e.status != 'cancelled'
        AND COALESCE(e.ends_at, e.starts_at + ?) > ? AND h.status = 'active' ORDER BY e.starts_at""", oid, core.NO_END, core.now())
    hosts = core._by_id(con, "orgs", (e["org_id"] for e in found))
    return [{"event": {"id": e["id"], "title": e["title"], "startsAt": e["starts_at"], "place": e["place"], "status": e["status"]},
             "host": org_ref(con, hosts[e["org_id"]]), "at": e["asked"]} for e in found]


def answer(con, v: Viewer, eid: int, yes: object) -> list[dict]:
    """The co-host's Vice+ says yes or no. Yes: the card shows both clubs, and if it's out already, our followers hear."""
    if not isinstance(yes, bool):
        raise ApiError("bad_input")
    with tx(con):
        x = one(con, """SELECT x.* FROM event_cohosts x JOIN orgs c ON c.id = x.org_id AND c.status = 'active'
            WHERE x.event_id = ? AND x.status != 'declined'""", eid)
        if not x or not at_least(role_in(con, v, x["org_id"]), "vice"):
            raise ApiError("not_found")  # someone else's invite says nothing; a hidden or archived club answers nothing
        if x["status"] != "pending":
            raise ApiError("conflict")  # another Vice answered first
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        if yes and (_over(e) or not _fits(e)):
            raise ApiError("closed")
        con.execute("UPDATE event_cohosts SET status = ?, decided_by = ?, decided_at = ? WHERE event_id = ? AND org_id = ?",
                    ("accepted" if yes else "declined", v.id, core.now(), eid, x["org_id"]))
        if yes:
            _touch(con, eid)
            tell(con, one(con, "SELECT * FROM events WHERE id = ?", eid), v.id)
        if x["invited_by"]:
            notify(con, x["invited_by"], "cohost_yes" if yes else "cohost_no", f"chd:{eid}:{x['org_id']}")
    return invites(con, v, x["org_id"])


def end(con, v: Viewer, eid: int) -> None:
    """Either side ends it: the host's events right removes (or takes back an invite), the co-host's Vice+ leaves.
    People keep their tickets; the other side hears once. The row goes, so the club may be invited again."""
    with tx(con):
        e = one(con, "SELECT * FROM events WHERE id = ?", eid)
        x = e and one(con, "SELECT * FROM event_cohosts WHERE event_id = ? AND status != 'declined'", eid)
        if not x:
            raise ApiError("not_found")
        host = can(con, v, e["org_id"], "events")
        if not host and not (x["status"] == "accepted" and at_least(role_in(con, v, x["org_id"]), "vice")):
            raise ApiError("forbidden")
        con.execute("DELETE FROM event_cohosts WHERE event_id = ? AND org_id = ?", (eid, x["org_id"]))
        if x["status"] != "accepted":
            return  # an invite taken back: its message renders to nothing now (bot._render)
        _touch(con, eid)
        for uid in _leaders(con, x["org_id"] if host else e["org_id"]):  # the other side's leaders now (the inviter may have left)
            if uid != v.id:
                notify(con, uid, "cohost_removed" if host else "cohost_left", f"che:{eid}:{x['org_id']}")


def changed(con, e: sqlite3.Row, after: sqlite3.Row) -> None:
    """The host moved, re-priced or renamed an event we co-host: our leaders hear it once (a template, no words of the
    host's), edits within 10 minutes in one message, as event_changed (organizing._changed)."""
    x = one(con, ACCEPTED, e["id"])
    if not x or all(e[k] == after[k] for k in ("starts_at", "ends_at", "price", "title")):
        return
    for uid in _leaders(con, x["org_id"]):
        if not one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'cohost_changed' AND ref LIKE ? AND sent_at IS NULL",
                   uid, f"chc:{e['id']}:%"):
            notify(con, uid, "cohost_changed", f"chc:{e['id']}:{x['org_id']}:{core.now()}", after=core.now() + 600)


def tell(con, e: sqlite3.Row, actor: int) -> None:
    """The co-host's followers hear of a public event once it is out and accepted, under the co-host's own weekly limit
    (review 7: an initiative can't reach its followers twice a week through co-hosting). Someone following both clubs
    hears once: the outbox key (user, new_event, event:<id>) is the host's message's."""
    x = one(con, ACCEPTED, e["id"])
    if not x or e["status"] != "published" or e["hidden_at"] or not _fits(e) or e["starts_at"] <= core.now():
        return
    if _tell_after(con, {"org_id": x["org_id"], "id": e["id"]}) is not None:
        return
    told = rows(con, """SELECT s.user_id FROM subscriptions s JOIN users u ON u.id = s.user_id
            WHERE s.org_id = ? AND u.n_new_events = 1 AND s.user_id != ?""", x["org_id"], actor)
    for (uid,) in told:
        notify(con, uid, "new_event", f"event:{e['id']}", json.dumps({"co": x["org_id"]}))  # the co-host's: checked again at send time (bot._render)
    # as the host's (publish_event): the week starts when someone heard
    con.execute(f"INSERT OR {'REPLACE' if told else 'IGNORE'} INTO meta (key, value) VALUES (?, ?)", (f"told:{x['org_id']}", str(core.now()) if told else "0"))


# the other domains', imported last: they import this one too
from . import core  # noqa: E402
from .organizing import _staff_event, _tell_after  # noqa: E402
from .seats import end_of, notify  # noqa: E402
