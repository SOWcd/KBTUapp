"""The organizer takes a person, or a whole team, off an event (seats.remove_seats): only the event's own organizers;
each seat ends as a self-cancel does ('removed'), the waitlist moves in, a paid one's receipt row stays, the bot's
template once per person, the audit log; a checked-in person is refused; a removed one may sign up again.
The case: a paid CS2 5x5, a team of five paid players withdrew."""
from __future__ import annotations

import io
import json
import time

from PIL import Image

from kbtu import bot, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)
from test_event_teams import _event, _go, _list, _mine, _people, _sheet
from test_paid_teams import _pay, _team
from test_team_guests import PAID, _club, _uid

CS2 = {**PAID, "teamMin": 2, "teamMax": 5, "seats": 6}


def _out(c, eid, tg, who=20):
    return c.delete(f"/api/events/{eid}/people/{tg}", headers=tma(who))


def _status(con, eid, tg):
    return tuple(con.execute("SELECT status, cancel_reason FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, tg))).fetchone())


def _removed_msgs(con, tg):
    return con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'seat_removed'", (_uid(con, tg),)).fetchone()[0]


def test_only_the_events_organizers_remove(env):
    c, cfg = env
    con = _club(c, cfg)
    login(c, 21, "other")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'art', 'club', 'Art', 'A', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 2, id, 'president', 0 FROM users WHERE tg_id = 21")
    eid = _event(c)
    for tg in (10, 11):
        assert _go(c, eid, tg).json()["my"]["status"] == "going"
    victim = _uid(con, 10)
    for who in (11, 12, 21):  # a participant, a stranger, another club's president
        assert c.delete(f"/api/events/{eid}/people/{victim}", headers=tma(who)).status_code in (403, 404), who
    assert _status(con, eid, 10) == ("going", None)
    # a plain member of the host club without the "events" right neither
    logic.set_role(con, None, _uid(con, 12), 1, "member", "test")
    assert c.delete(f"/api/events/{eid}/people/{victim}", headers=tma(12)).status_code in (403, 404)
    assert c.delete(f"/api/events/{eid}/teams/1", headers=tma(11)).status_code in (403, 404)
    assert _status(con, eid, 10) == ("going", None) and not _removed_msgs(con, 10)


def test_single_removal_frees_the_seat_and_can_sign_up_again(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, seats=1)
    assert _go(c, eid, 10).json()["my"]["status"] == "going"
    assert _go(c, eid, 11).json()["my"]["status"] == "waitlist"
    assert c.delete(f"/api/events/{eid}/people/{_uid(con, 10)}", headers=tma(20)).status_code == 204
    assert _status(con, eid, 10) == ("cancelled", "removed")
    assert _status(con, eid, 11)[0] == "going"  # the waitlist moved in
    assert _removed_msgs(con, 10) == 1
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'seat_removed'").fetchone()
    text, _, to = bot._render(con, {**dict(m), "lang": "en"})
    assert "Case" in text and "IT Club" in text and to == f"ev_{eid}"  # the template, a button into the event
    a = con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'seat_remove'").fetchone()
    assert a[0] == _uid(con, 20) and json.loads(a[2])["user"] == _uid(con, 10)
    # twice: nothing to remove
    assert c.delete(f"/api/events/{eid}/people/{_uid(con, 10)}", headers=tma(20)).status_code == 404
    # signs up again normally: the waitlist now (the seat went on)
    assert _go(c, eid, 10).json()["my"]["status"] == "waitlist"


def test_whole_team_paid_keeps_receipts_and_old_receipt_is_flagged(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **CS2)
    cap, a, b, solo, wait = _people(c, 5)
    _pay(c, eid, cap)
    assert _team(c, eid, cap, "Vision").status_code == 200
    token = _mine(c, eid, cap)["token"]
    for tg in (a, b):
        _pay(c, eid, tg, {"join": token})
    _pay(c, eid, solo)
    for tg in _people(c, 2, first=200):
        _pay(c, eid, tg)
    assert _go(c, eid, wait).json()["my"]["status"] == "waitlist"
    receipts = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    tid = _list(c, eid)["teams"][0]["id"]
    assert c.delete(f"/api/events/{eid}/teams/{tid}", headers=tma(20)).status_code == 204
    for tg in (cap, a, b):
        assert _status(con, eid, tg) == ("cancelled", "removed")
        assert _removed_msgs(con, tg) == 1
    assert _list(c, eid)["teams"] == []  # the empty team went (migration 161's trigger)
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'team_left'").fetchone()  # no "a player left" to the leaving team
    assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == receipts  # every receipt row kept
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'seat_remove'").fetchone()[0] == 3
    assert _status(con, eid, wait)[0] == "hold"  # a freed seat: the waitlist's, to pay for
    assert _status(con, eid, solo) == ("going", None)
    # out of the attendee list; signed up again, the old receipt isn't shown as paid while on hold
    att = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    assert _uid(con, cap) not in [x["person"]["id"] for x in att]
    assert _go(c, eid, cap).json()["my"]["status"] == "hold"
    row = next(x for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json() if x["person"]["id"] == _uid(con, cap))
    assert row["status"] == "hold" and row["receipt"] is None
    assert _sheet(c, eid, cap)["my"]["status"] == "hold"


def test_reused_receipt_after_removal_is_a_duplicate(env):
    """The old receipt sent again after a removal: a ticket by the usual rules, but flagged a duplicate for the
    organizer and the door, never passed by the app."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **PAID)
    (p,) = _people(c, 1)
    buf = io.BytesIO()
    Image.new("RGB", (600, 1200), (7, 77, 177)).save(buf, "PNG")
    send = lambda: c.post(f"/api/events/{eid}/receipt", headers=tma(p), content=buf.getvalue()).json()  # noqa: E731
    assert _go(c, eid, p).json()["my"]["status"] == "hold" and send()["my"]["status"] == "going"
    assert _out(c, eid, _uid(con, p)).status_code == 204
    assert _status(con, eid, p) == ("cancelled", "removed")
    assert _go(c, eid, p).json()["my"]["status"] == "hold"
    assert send()["my"]["status"] == "going"
    old, new = con.execute("SELECT flags, reviewed_at FROM receipts ORDER BY id").fetchall()
    assert "duplicate" in new[0].split(",") and new[1] is None
    assert any(x["receipt"] and "duplicate" in x["receipt"]["flags"] for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json())


def test_checked_in_is_refused_and_after_start_closed(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c)
    assert _go(c, eid, 10).json()["my"]["status"] == "going"
    assert _go(c, eid, 11).json()["my"]["status"] == "going"
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ? AND user_id = ?", (int(time.time()), eid, _uid(con, 10)))
    r = _out(c, eid, _uid(con, 10))
    assert (r.status_code, r.json()["message"]) == (409, "checked_in")
    assert _status(con, eid, 10) == ("going", None) and not _removed_msgs(con, 10)
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (int(time.time()) - 60, eid))
    assert _out(c, eid, _uid(con, 11)).json()["error"] == "closed"


def test_checked_in_member_blocks_the_whole_team(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, teamMin=2, teamMax=3)
    cap, mate = _people(c, 2)
    assert _go(c, eid, cap, {"create": "Owls"}).status_code == 200
    assert _go(c, eid, mate, {"join": _mine(c, eid, cap)["token"]}).status_code == 200
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ? AND user_id = ?", (int(time.time()), eid, _uid(con, mate)))
    tid = _list(c, eid)["teams"][0]["id"]
    assert c.delete(f"/api/events/{eid}/teams/{tid}", headers=tma(20)).status_code == 409
    assert _status(con, eid, cap) == ("going", None)  # all or nothing
    # a team of another event, or a missing one
    other = _event(c, teamMin=2, teamMax=3)
    assert c.delete(f"/api/events/{other}/teams/{tid}", headers=tma(20)).status_code == 404
    # a single member's removal: the captain hears a player left
    con.execute("UPDATE registrations SET checked_in_at = NULL WHERE event_id = ?", (eid,))
    assert _out(c, eid, _uid(con, mate)).status_code == 204
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'team_left'", (_uid(con, cap),)).fetchone()
    assert len(_mine(c, eid, cap)["members"]) == 1
