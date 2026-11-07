"""The host club's own people are never its guests (owner, Nov 7): no sign-up to its public events, joining gives the seat
back to the waitlist, migration 135 did the same once; a paid seat stays; the door still counts a member who came."""
from __future__ import annotations

import time

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

PAID = {"price": 2000, "payToName": "Arman A.", "payPhone": "87071234567"}


def _club(c, cfg):
    """IT Club (tg 20 its president); tg 10, 11, 12 students."""
    for tg, name in ((20, "pres"), (10, "ali"), (11, "bob"), (12, "cat")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    return con


def _event(c, start=None, **extra):
    start = start or int(time.time()) + 5 * 3600
    body = {"title": "Case", "place": "Hall", "startsAt": start, "endsAt": start + 7200, "emoji": "laptop_3d", "color": "#3B6BFF", **extra}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert c.post(f"/api/events/{ev['id']}/publish", headers=tma(20)).status_code == 200, ev
    return ev["id"]


def _go(c, eid, tg):
    return c.post(f"/api/events/{eid}/registration", headers=tma(tg), json={}).json()


def _uid(con, tg):
    return con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]


def _reg(con, eid, tg):
    return con.execute("SELECT status, cancel_reason FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, tg))).fetchone()


def test_member_cant_sign_up(env):
    c, cfg = env
    con = _club(c, cfg)
    free, paid, team = _event(c), _event(c, **PAID), _event(c, visibility="members")
    for eid in (free, paid):
        r = _go(c, eid, 20)
        assert r.get("error") == "forbidden" and r.get("message") == "team", r
    assert _go(c, team, 20)["my"]["status"] == "going"  # a team-only event is the team's own
    assert _go(c, free, 10)["my"]["status"] == "going"
    # one who left the club to sign up is a guest; rejoining hands the seat back
    logic.set_role(con, None, _uid(con, 20), 1, "none", "test")
    assert _go(c, free, 20)["my"]["status"] == "going"
    logic.set_role(con, None, _uid(con, 20), 1, "member", "test")
    assert tuple(_reg(con, free, 20)) == ("cancelled", "removed")


def test_joining_frees_the_seat_for_the_waitlist(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, seats=1)
    assert _go(c, eid, 10)["my"]["status"] == "going"
    assert _go(c, eid, 11)["my"]["status"] == "waitlist"
    assert _go(c, eid, 12)["my"]["status"] == "waitlist"
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'remind_2h' AND user_id = ?", (_uid(con, 10),)).fetchone()
    # tg 10 is taken into the club: his join request accepted
    con.execute("INSERT INTO join_requests (org_id, user_id, status, created_at) VALUES (1, ?, 'pending', 0)", (_uid(con, 10),))
    rid = con.execute("SELECT id FROM join_requests WHERE user_id = ?", (_uid(con, 10),)).fetchone()[0]
    assert c.post(f"/api/join-requests/{rid}/accept", headers=tma(20)).status_code == 204
    assert con.execute("SELECT 1 FROM org_members WHERE org_id = 1 AND user_id = ?", (_uid(con, 10),)).fetchone()
    assert tuple(_reg(con, eid, 10)) == ("cancelled", "removed")
    assert _reg(con, eid, 11)["status"] == "going" and _reg(con, eid, 12)["status"] == "waitlist"  # first in line first
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'remind_2h' AND user_id = ?", (_uid(con, 10),)).fetchone()
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'seat_free' AND user_id = ?", (_uid(con, 11),)).fetchone()
    # nothing about the seat goes to the new member (only the club's own answer)
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref LIKE ?", (_uid(con, 10), f"event:{eid}%")).fetchone()


def test_paid_seat_stays(env):
    c, cfg = env
    con = _club(c, cfg)
    eid = _event(c, **PAID)
    assert _go(c, eid, 10)["my"]["status"] == "hold"
    logic.set_role(con, None, _uid(con, 10), 1, "member", "test")
    assert _reg(con, eid, 10)["status"] == "hold"  # money: theirs to pay or give back


def test_migration_135(env):
    c, cfg = env
    con = _club(c, cfg)
    free, paid, team, past = _event(c, seats=2), _event(c, **PAID), _event(c, visibility="members"), _event(c)
    for tg in (10, 11):
        assert _go(c, free, tg)["my"]["status"] == "going"
    assert _go(c, free, 12)["my"]["status"] == "waitlist"
    assert _go(c, paid, 10)["my"]["status"] == "hold"
    assert _go(c, past, 10)["my"]["status"] == "going"
    # tg 10 became a member before the rule (written directly: no joined()), his club's team event too
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (_uid(con, 10),))
    assert _go(c, team, 10)["my"]["status"] == "going"
    con.execute("UPDATE events SET starts_at = starts_at - 86400, ends_at = ends_at - 86400 WHERE id = ?", (past,))
    sql = dict(db.MIGRATIONS)[135]
    con.executescript(f"BEGIN;\n{sql}\nCOMMIT;")
    assert tuple(_reg(con, free, 10)) == ("cancelled", "removed")
    assert _reg(con, free, 11)["status"] == "going"  # not a member
    assert _reg(con, paid, 10)["status"] == "hold" and _reg(con, team, 10)["status"] == "going" and _reg(con, past, 10)["status"] == "going"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'remind_2h' AND user_id = ? AND ref LIKE ?", (_uid(con, 10), f"event:{free}:%")).fetchone()
    logic.refill(con)
    assert _reg(con, free, 12)["status"] == "going"
    logic.refill(con)  # again: nothing left to move
    assert con.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = 'going'", (free,)).fetchone()[0] == 2


def test_member_at_the_door_still_counts(env):
    c, cfg = env
    con = _club(c, cfg)
    start = int(time.time()) + 600
    eid = _event(c, start=start)
    logic.screen_came(con, eid, _uid(con, 20), start)  # the big screen's QR, scanned by the president himself
    r = con.execute("SELECT status, walk_in, checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, 20))).fetchone()
    assert r["status"] == "going" and r["walk_in"] == 1 and r["checked_in_at"] == start
    team = c.get("/api/orgs/1/team", headers=tma(20))
    assert team.status_code == 200
