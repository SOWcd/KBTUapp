"""The door (owner, Nov 7): shut until the club's President or a Vice opens it early (from 4 h before the start) or it
opens by itself at T-30; then every guest going hears it once from the bot. The scanner, the list by name, the big
screen and walk-ins by name all follow it. The app's admin (X-Staff-Event) never opens it."""
from __future__ import annotations

import time

from kbtu import bot, db, logic
from test_admin_events import _as, _setup
from test_core import env, login, tma  # noqa: F401  (env is a fixture)
from test_team_guests import _club, _event, _go, _uid


def _team(c, cfg):
    """IT Club: tg 20 President, 21 Vice, 22 a Head, 23 a Member; 10, 11 guests."""
    con = _club(c, cfg)
    for tg, role in ((21, "vice"), (22, "head"), (23, "member")):
        login(c, tg, f"t{tg}")
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", (_uid(con, tg), role))
    return con


def _start(con, eid, in_s):
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) + in_s, int(time.time()) + in_s + 7200, eid))


def _scan(c, eid, con, tg):
    code = con.execute("SELECT ticket_code FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, tg))).fetchone()[0]
    return c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": "KBTU" + code}).json()["result"]


def _sent(con, eid):
    return sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'door_open' AND ref = ?", (f"door:{eid}",)))


def test_shut_until_opened_by_president_or_vice(env):
    c, cfg = env
    con = _team(c, cfg)
    eid = _event(c)
    for tg in (10, 11):
        assert _go(c, eid, tg)["my"]["status"] == "going"
    _start(con, eid, 2 * 3600)
    assert _scan(c, eid, con, 10) == "not_open"          # 2 h before: shut, a plate of its own
    logic.door_round(con)
    assert _sent(con, eid) == []
    open_ = lambda tg: c.post(f"/api/events/{eid}/door-open", headers=tma(tg))  # noqa: E731
    for tg in (22, 23, 10):  # a Head, a Member, a guest: no
        assert open_(tg).status_code == 403
    _start(con, eid, 5 * 3600)
    assert open_(20).status_code == 409                   # more than 4 h before: not yet
    _start(con, eid, 2 * 3600)
    r = open_(21)                                         # a Vice opens it
    assert r.status_code == 200 and r.json()["doorAt"] <= int(time.time())
    assert con.execute("SELECT actor_id FROM audit_log WHERE action = 'door_open' AND target = ?", (f"event:{eid}",)).fetchone()[0] == _uid(con, 21)
    was = con.execute("SELECT door_open_at FROM events WHERE id = ?", (eid,)).fetchone()[0]
    assert open_(20).status_code == 200 and con.execute("SELECT door_open_at FROM events WHERE id = ?", (eid,)).fetchone()[0] == was  # once
    assert _scan(c, eid, con, 10) == "ok"
    logic.door_round(con)
    logic.door_round(con)
    assert _sent(con, eid) == [_uid(con, 11)]             # who is in already doesn't hear it; once each
    # the event moved 6 h later: the early opening no longer counts, the door is shut again
    _start(con, eid, 6 * 3600)
    assert _scan(c, eid, con, 11) == "not_open"


def test_opens_by_itself_at_t30(env):
    c, cfg = env
    con = _team(c, cfg)
    eid = _event(c)
    assert _go(c, eid, 10)["my"]["status"] == "going"
    _start(con, eid, 31 * 60)
    assert _scan(c, eid, con, 10) == "not_open"
    walk = lambda: c.post(f"/api/events/{eid}/door/guests", headers=tma(20), json={"name": "Aruzhan Serikova"})  # noqa: E731
    assert walk().status_code == 409                       # a walk-in by name: not yet
    logic.screen_came(con, eid, _uid(con, 11), int(time.time()))  # the big screen: not yet
    assert not con.execute("SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, 11))).fetchone()
    logic.door_round(con)
    assert _sent(con, eid) == []
    _start(con, eid, 29 * 60)
    logic.door_round(con)
    logic.door_round(con)
    assert _sent(con, eid) == [_uid(con, 10)]
    m = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'door_open'").fetchone()
    text, _, start = bot._render(con, m)
    assert "Case" in text and start == f"tk_{eid}"         # a template with a button to the ticket
    con.execute("UPDATE users SET n_remind = 0 WHERE id = ?", (_uid(con, 10),))
    assert bot._render(con, m) is None                     # reminders off: quiet
    con.execute("UPDATE users SET n_remind = 1 WHERE id = ?", (_uid(con, 10),))
    logic.screen_came(con, eid, _uid(con, 11), int(time.time()))
    assert con.execute("SELECT checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, 11))).fetchone()[0]
    assert walk().status_code == 200
    assert _scan(c, eid, con, 10) == "ok"
    assert bot._render(con, m) is None                     # in already by the time it goes
    # moved: event_changed tells, not a second door message
    _start(con, eid, 20 * 60)
    logic.door_round(con)
    assert _sent(con, eid) == [_uid(con, 10)]


def test_deploy_keeps_a_door_already_in_use(env):
    """Migration 137: an event the old 3-hour rule already let people into keeps its door open, and nobody is told."""
    c, cfg = env
    con = _team(c, cfg)
    busy, idle = _event(c), _event(c)
    for eid in (busy, idle):
        assert _go(c, eid, 10)["my"]["status"] == "going"
        assert _go(c, eid, 11)["my"]["status"] == "going"
        _start(con, eid, 2 * 3600)
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ? AND user_id = ?", (int(time.time()) - 60, busy, _uid(con, 10)))
    con.executescript(f"BEGIN;\n{dict(db.MIGRATIONS)[137].split(';', 1)[1]}\nCOMMIT;")  # its UPDATE (the column is there)
    assert _scan(c, busy, con, 11) == "ok"
    assert _scan(c, idle, con, 11) == "not_open"
    logic.door_round(con)
    assert _sent(con, busy) == [] and _sent(con, idle) == []


def test_admin_never_opens_the_door(env):
    c, con, ids = _setup(env)
    con.execute("UPDATE events SET starts_at = ? WHERE id = 1", (int(time.time()) + 3600,))
    assert c.post("/api/events/1/door-open", headers=_as(60)).status_code == 403   # the staff path lends "events", not this
    assert c.post("/api/events/1/door-open", headers=tma(64)).status_code == 403   # another club's President
    assert c.post("/api/events/1/door-open", headers=tma(62)).status_code == 200   # the club's own
    assert con.execute("SELECT door_open_at FROM events WHERE id = 1").fetchone()[0]
