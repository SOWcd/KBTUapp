"""One QR at the door (checkin._team): at a public event, its own club's member without a guest seat scanning the guests'
QR is marked in the team's session (made and started as its organizer opened the QR on the day), never as a guest; the
attacks of its review, each failing."""
from __future__ import annotations

import time

import pytest

from kbtu import checkin, db
from test_checkin_door import _ev, _mem, _qr, _reg
from test_club_checkin import _mail
from test_core import _club_runs, env, login, tma  # noqa: F401
from test_review_checkin import _scan, _signed


def _setup(c, con, t0=None):
    oid = _club_runs(c, con, 9, "dana", "chess")
    _mail(con, 9, "dana@kbtu.kz")
    ann = _mem(c, con, oid, 1, "ann")
    _mail(con, 1, "ann@kbtu.kz")
    return oid, ann, _ev(con, oid, int(time.time()) - 60 if t0 is None else t0)


def _crew(con, eid):
    return con.execute("SELECT * FROM qr_sessions WHERE crew_event_id = ?", (eid,)).fetchone()


def _marks(con, sid, done=True):
    return con.execute(f"SELECT COUNT(*) FROM qr_marks WHERE session_id = ? {'AND done_at IS NOT NULL' if done else ''}", (sid,)).fetchone()[0]


def test_member_to_the_team_guests_as_before(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    g, q = _qr(c, 9, eid)
    crew = _crew(con, eid)                                                                 # made and started as its organizer opened the QR
    assert crew["started_at"] and crew["event_id"] is None and crew["org_id"] == oid
    assert con.execute("SELECT u.tg_id FROM audit_log a JOIN users u ON u.id = a.actor_id WHERE a.action = 'checkin_new' AND a.target = ?",
                       (f"qr:{crew['id']}",)).fetchone()[0] == 9                           # under the organizer
    r = _scan(c, 1, q["param"]).json()
    assert r["done"] and r["team"] and not r["again"] and r["event"] == eid
    assert _marks(con, crew["id"]) == 1 and _marks(con, g, False) == 0                     # never a guest
    assert c.get(f"/api/screens/{crew['id']}/people", headers=tma(9)).json()["came"] == ["Testov Ann"]
    last = c.post(f"/api/screens/{g}/show", headers=tma(9)).json()
    assert last["done"] == 0 and last["last"]["team"]                                      # the door: said as the team's, not counted
    again = _scan(c, 1, q["param"]).json()                                                 # a double scan: once
    assert again["team"] and again["again"] and _marks(con, crew["id"]) == 1
    login(c, 3, "cat")                                                                     # a guest: as before
    r = _scan(c, 3, q["param"]).json()
    assert r["done"] and "team" not in r and _marks(con, g) == 1 and _marks(con, crew["id"]) == 1
    assert not c.post(f"/api/screens/{g}/show", headers=tma(9)).json()["last"]["team"]
    assert _qr(c, 9, eid)[0] == g and _crew(con, eid)["id"] == crew["id"]                  # opened again: the same two
    assert c.post(f"/api/screens/{g}/finish", headers=tma(9)).status_code == 200
    csv = c.get(c.post(f"/api/screens/{g}/csv", headers=tma(9)).json()["url"]).text
    assert "Testov Cat" in csv and "Testov Ann" not in csv
    con.close()


def test_a_guest_seat_means_a_guest(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _reg(con, eid, ann["id"], "AAAA")                                                      # let in as a guest (team_ask) or a President's seat
    con.execute("INSERT INTO team_asks (event_id, user_id, status, created_at) VALUES (?, ?, 'yes', 0)", (eid, ann["id"]))
    bob = _mem(c, con, oid, 2, "bob")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'cancelled', ?, 0, 0)",
                (eid, bob["id"], f"{eid}-BBBB"))                                           # a seat given back: no seat
    g, q = _qr(c, 9, eid)
    r = _scan(c, 1, q["param"]).json()
    assert r["done"] and "team" not in r and _marks(con, g) == 1
    assert con.execute("SELECT checked_in_at FROM registrations WHERE event_id = ? AND user_id = ?", (eid, ann["id"])).fetchone()[0]
    assert _scan(c, 2, q["param"]).json()["team"] and _marks(con, _crew(con, eid)["id"]) == 1
    con.close()


def test_before_the_door_team_only(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    t0 = int(time.time()) + 2400                                                           # the door opens in 10 min (T-30)
    if (t0 + 5 * 3600) // 86400 != (int(time.time()) + 5 * 3600) // 86400:
        pytest.skip("Almaty's midnight in between")
    _, ann, eid = _setup(c, con, t0)
    g, q = _qr(c, 9, eid)                                                                  # its organizer opens early
    assert _scan(c, 1, q["param"]).json()["team"]                                          # the team comes early: counted
    login(c, 3, "cat")
    r = _scan(c, 3, q["param"])                                                            # a guest: refused, nothing kept
    assert r.status_code == 409 and r.json()["message"] == "not_open" and r.json()["at"] == t0 - 1800
    assert _marks(con, g, False) == 0
    con.close()


def test_scans_never_make_or_reopen_the_team_session(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    _mem(c, con, oid, 7, "mia")
    s = c.post(f"/api/events/{eid}/screen", headers=tma(7)).json()                         # a plain member at the door: no team session
    p = c.post(f"/api/screens/{s['session']}/start", headers=tma(7)).json()["param"]
    assert _crew(con, eid) is None
    r = _scan(c, 1, p).json()                                                              # none: the guest's way, no error
    assert r["done"] and "team" not in r and _crew(con, eid) is None
    e2 = _ev(con, oid, int(time.time()) - 60)
    g2, q2 = _qr(c, 9, e2)
    c.post(f"/api/screens/{_crew(con, e2)['id']}/finish", headers=tma(9))                  # the team's finished: not reopened
    assert "team" not in _scan(c, 1, q2["param"]).json() and _marks(con, g2) == 1
    later = _ev(con, oid, int(time.time()) + 3 * 86400)                                    # another day: none made yet
    _qr(c, 9, later)                                                                       # its organizer starts it days early
    assert _crew(con, later) is None
    con.close()


def test_leaving_goes_where_the_arrival_went(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    g, q = _qr(c, 9, eid)
    login(c, 3, "cat")
    assert _scan(c, 1, q["param"]).json()["team"] and _scan(c, 3, q["param"]).json()["done"]
    c.post(f"/api/screens/{g}/out", headers=tma(9))
    q = c.post(f"/api/screens/{g}/show", headers=tma(9)).json()
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ann["id"]))  # left the club since: still leaves the team's
    r = _scan(c, 1, q["param"]).json()
    assert r["left"] and r["team"]
    crew = _crew(con, eid)["id"]
    assert con.execute("SELECT left_at FROM qr_marks WHERE session_id = ? AND user_id = ?", (crew, ann["id"])).fetchone()[0]
    assert _marks(con, g, False) == 1                                                      # no guest mark made for her
    r = _scan(c, 3, q["param"]).json()                                                     # a guest leaving: as before
    assert r["left"] and "team" not in r
    login(c, 4, "kim")
    assert _scan(c, 4, q["param"]).json()["message"] == "qr_not_in"                        # never came: as before
    con.close()


def test_who_never_gets_into_the_team(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    other = _club_runs(c, con, 8, "eve", "go")
    _mem(c, con, other, 5, "max")                                                          # a co-host's member: a guest
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (eid, other))
    lea = _mem(c, con, oid, 6, "lea")
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, lea["id"]))  # left the club
    g, q = _qr(c, 9, eid)
    crew = _crew(con, eid)["id"]
    for tg in (5, 6):
        r = _scan(c, tg, q["param"]).json()
        assert r["done"] and "team" not in r
    assert _marks(con, crew, False) == 0 and _marks(con, g) == 2
    e2 = _ev(con, other, int(time.time()) - 60)                                            # this club's member at another club's event
    _qr(c, 8, e2)
    assert "team" not in _scan(c, 1, _qr(c, 8, e2)[1]["param"]).json() and _marks(con, _crew(con, e2)["id"], False) == 0
    sid, slot, sig = q["param"].split("_")[1:]                                             # a forged or stale code: refused before anything
    assert _scan(c, 1, f"ci_{sid}_{slot}_{'0' * 16}").status_code == 400
    assert _scan(c, 1, f"ci_{crew}_{slot}_{sig}").status_code == 400                       # the guests' signature on the team's session
    assert _scan(c, 1, _signed(cfg, sid, int(slot) - 100)).json()["message"] == "qr_old"   # an old photo: never reaches the team
    assert _marks(con, crew, False) == 0
    for col, val in (("meeting", 1), ("visibility", "'members'")):                         # a meeting, a team-only one: no team routing
        e3 = _ev(con, oid, int(time.time()) - 60)
        con.execute(f"UPDATE events SET {col} = {val} WHERE id = ?", (e3,))
        _, q3 = _qr(c, 9, e3)
        assert "team" not in _scan(c, 1, q3["param"]).json() and _crew(con, e3) is None
    con.close()


def test_a_held_offer_means_a_guest_and_rights_read_with_the_mark(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, created_at, updated_at) VALUES (?, ?, 'hold', ?, ?, 0, 0)",
                (eid, ann["id"], f"{eid}-HHHH", int(time.time()) + 600))                  # a waitlist offer held
    g, q = _qr(c, 9, eid)
    assert "team" not in _scan(c, 1, q["param"]).json() and _marks(con, _crew(con, eid)["id"], False) == 0
    # removed from the club just before the scan's write: read inside its transaction, so a guest
    bob = _mem(c, con, oid, 2, "bob")
    real = checkin.tx
    def removed_first(con2):  # the removal lands as the scan's transaction opens
        con2.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, bob["id"]))
        return real(con2)
    checkin.tx = removed_first
    try:
        r = _scan(c, 2, q["param"]).json()
    finally:
        checkin.tx = real
    assert "team" not in r and _marks(con, _crew(con, eid)["id"], False) == 0
    con.close()


def test_team_leaving_keeps_the_guests_window(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, ann, eid = _setup(c, con)
    g, q = _qr(c, 9, eid)
    assert _scan(c, 1, q["param"]).json()["team"]
    c.post(f"/api/screens/{g}/out", headers=tma(9))
    q = c.post(f"/api/screens/{g}/show", headers=tma(9)).json()
    con.execute("UPDATE events SET ends_at = ? WHERE id = ?", (int(time.time()) - checkin.GRACE - 60, eid))  # over, past its grace
    r = _scan(c, 1, q["param"])
    assert r.status_code == 409
    assert not con.execute("SELECT left_at FROM qr_marks WHERE session_id = ? AND user_id = ?", (_crew(con, eid)["id"], ann["id"])).fetchone()[0]
    con.close()
