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
from test_paid_teams import _pay, _receipt, _team
from test_team_guests import PAID, _club, _uid

CS2 = {**PAID, "teamMin": 2, "teamMax": 5, "seats": 6}


def _out(c, eid, tg, who=20):
    return c.delete(f"/api/events/{eid}/people/{tg}", headers=tma(who))


def _out_team(c, eid, tid, people, who=20):
    return c.request("DELETE", f"/api/events/{eid}/teams/{tid}", headers=tma(who), json={"people": people})


def _age(con):
    """The receipts so far a minute older: a new sign-up after them is a later second, as it always is off the tests."""
    con.execute("UPDATE receipts SET created_at = created_at - 60")


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
    assert _out_team(c, eid, tid, [_uid(con, cap), _uid(con, a)]).json()["message"] == "changed"  # not the roster confirmed
    assert _status(con, eid, cap) == ("going", None)
    assert c.delete(f"/api/events/{eid}/teams/{tid}", headers=tma(20)).status_code == 400  # no roster: refused
    assert _out_team(c, eid, tid, [_uid(con, t) for t in (cap, a, b)]).status_code == 204
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
    att = {x["person"]["id"]: x["status"] for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert att[_uid(con, cap)] == "cancelled"  # removed, kept at the end for the refund
    _age(con)
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
    assert _out_team(c, eid, tid, [_uid(con, cap), _uid(con, mate)]).json()["message"] == "checked_in"
    assert _status(con, eid, cap) == ("going", None)  # all or nothing
    # a team of another event, or a missing one
    other = _event(c, teamMin=2, teamMax=3)
    assert _out_team(c, other, tid, [_uid(con, cap), _uid(con, mate)]).status_code == 404
    # a single member's removal: the captain hears a player left
    con.execute("UPDATE registrations SET checked_in_at = NULL WHERE event_id = ?", (eid,))
    assert _out(c, eid, _uid(con, mate)).status_code == 204
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'team_left'", (_uid(con, cap),)).fetchone()
    assert len(_mine(c, eid, cap)["members"]) == 1


def test_admin_from_admin_removes_on_free_events_only(env):
    """The app's admin acting from Admin (X-Staff-Event, STAFF_RIGHTS: never money) may remove on a free event, not
    on a paid one; the club's own President may on both."""
    import dataclasses
    from fastapi.testclient import TestClient
    from kbtu import app as server
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    con = _club(c, cfg)
    login(c, 60, "boss")
    free, paid = _event(c), _event(c, **PAID)
    assert _go(c, free, 10).json()["my"]["status"] == "going"
    (p, q) = _people(c, 2)
    _pay(c, paid, p)
    _pay(c, paid, q)
    staff = lambda eid: {**tma(60), "X-Staff-Event": str(eid)}  # noqa: E731
    r = c.delete(f"/api/events/{paid}/people/{_uid(con, p)}", headers=staff(paid))
    assert (r.status_code, r.json()["message"]) == (403, "staff") and _status(con, paid, p) == ("going", None)
    assert c.delete(f"/api/events/{free}/people/{_uid(con, 10)}", headers=staff(free)).status_code == 204
    assert _out(c, paid, _uid(con, q)).status_code == 204  # the club's own President


def test_old_flagged_receipt_never_blocks_a_repaid_seat(env):
    """Removed with a flagged receipt, back with a new one the organizer accepted: the door and the list look only at
    this seat's receipts (since its created_at, which a new sign-up restarts)."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **PAID)
    (p,) = _people(c, 1)
    _pay(c, eid, p)
    rid = con.execute("SELECT id FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, p))).fetchone()[0]
    con.execute("UPDATE receipts SET flags = 'duplicate', reviewed_at = NULL, created_at = created_at - 60 WHERE registration_id = ?", (rid,))
    con.execute("UPDATE registrations SET created_at = created_at - 60 WHERE id = ?", (rid,))
    assert logic.organizing.flagged(con, rid)
    assert _out(c, eid, _uid(con, p)).status_code == 204
    assert _go(c, eid, p).json()["my"]["status"] == "hold"
    assert not logic.organizing.flagged(con, rid)  # the old seat's warning isn't this seat's
    _receipt(c, eid, p)
    new = con.execute("SELECT MAX(id) FROM receipts WHERE registration_id = ?", (rid,)).fetchone()[0]
    assert c.post(f"/api/receipts/{new}/review", headers=tma(20), json={"reject": False}).status_code == 204
    assert not logic.organizing.flagged(con, rid)
    row = next(x for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json() if x["person"]["id"] == _uid(con, p))
    assert row["receipt"]["id"] == new and row["receipt"]["reviewed"]
    assert _sheet(c, eid, p)["my"]["receiptFlags"] == []
    assert con.execute("SELECT COUNT(*) FROM receipts WHERE registration_id = ?", (rid,)).fetchone()[0] == 2  # the old one kept


def test_removed_paid_person_stays_in_attendees_for_the_refund(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **PAID)
    (p, q) = _people(c, 2)
    _pay(c, eid, p)
    assert _go(c, eid, q).json()["my"]["status"] == "hold"
    assert _out(c, eid, _uid(con, p)).status_code == 204
    assert _out(c, eid, _uid(con, q)).status_code == 204  # no receipt: simply gone
    att = {x["person"]["id"]: x for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()}
    assert _uid(con, q) not in att
    assert att[_uid(con, p)]["status"] == "cancelled" and att[_uid(con, p)]["receipt"]
    _age(con)
    assert _go(c, eid, p).json()["my"]["status"] == "hold"  # back: an ordinary hold, the old receipt not shown
    row = next(x for x in c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json() if x["person"]["id"] == _uid(con, p))
    assert row["status"] == "hold" and row["receipt"] is None


def test_removed_person_isnt_walked_back_in(env):
    """A free event: a badge at the door or the big screen brings back someone who cancelled themselves, never someone
    the organizers removed (they sign up again first)."""
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c)
    for tg in (10, 11):
        assert _go(c, eid, tg).json()["my"]["status"] == "going"
    assert _out(c, eid, _uid(con, 10)).status_code == 204
    assert c.delete(f"/api/events/{eid}/registration", headers=tma(11)).status_code == 200
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    code = lambda tg: con.execute("SELECT qr_code FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    assert logic.organizing._walk_in(con, e, _uid(con, 10), code(10), e["starts_at"]) == "cancelled"
    assert not logic.organizing.screen_came(con, eid, _uid(con, 10), e["starts_at"])["done"]
    assert _status(con, eid, 10) == ("cancelled", "removed")
    assert logic.organizing._walk_in(con, e, _uid(con, 11), code(11), e["starts_at"])["status"] == "going"  # as before


def test_each_promotion_rings(env, monkeypatch):
    """Promoted, removed, back on the waitlist, promoted again: the second payment prompt goes too."""
    from test_core import set_clock
    c, cfg = env
    con = _club(c, cfg)
    t = [int(time.time())]
    set_clock(monkeypatch, lambda: t[0])
    eid = _event(c, **PAID, seats=1)
    (a, b) = _people(c, 2)
    _pay(c, eid, a)
    assert _go(c, eid, b).json()["my"]["status"] == "waitlist"
    t[0] += 5
    assert _out(c, eid, _uid(con, a)).status_code == 204
    assert _status(con, eid, b)[0] == "hold"
    t[0] += 5
    assert _out(c, eid, _uid(con, b)).status_code == 204
    _pay(c, eid, a)
    t[0] += 5
    assert _go(c, eid, b).json()["my"]["status"] == "waitlist"
    t[0] += 5
    assert _out(c, eid, _uid(con, a)).status_code == 204
    assert _status(con, eid, b)[0] == "hold"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'seat_hold'", (_uid(con, b),)).fetchone()[0] == 2
