"""An event's team marked from Studio (checkin.crew): a club session tied to the event, one per event, apart from its
guests' session; the attacks of its review, each failing."""
from __future__ import annotations

import threading

from kbtu import checkin, db
from kbtu.logic import now
from test_checkin_door import _ev
from test_club_checkin import _join, _mail
from test_core import _club_runs, env, login, tma  # noqa: F401


def _crew(c, tg, eid, who="club"):
    return c.post(f"/api/events/{eid}/crew-screen", headers=tma(tg), json={"who": who, "title": "Party · team"})


def _setup(c, con):
    oid = _club_runs(c, con, 9, "dana", "chess")
    _mail(con, 9, "dana@kbtu.kz")
    _join(c, con, oid, 1, "ann", "member")
    _mail(con, 1, "ann@kbtu.kz")
    return oid, _ev(con, oid, now() + 600)


def test_one_per_event_and_its_rights(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, eid = _setup(c, con)
    other = _club_runs(c, con, 8, "eve", "go")
    assert c.get(f"/api/events/{eid}/crew-screen", headers=tma(9)).json() is None       # none yet
    assert _crew(c, 1, eid).status_code == 403                                           # a plain member
    assert _crew(c, 8, eid).status_code == 403                                           # another club's head
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (eid, other))
    assert _crew(c, 8, eid).status_code == 403                                           # a co-host: its own club only
    assert c.get(f"/api/events/{eid}/crew-screen", headers=tma(8)).status_code == 403
    s = _crew(c, 9, eid).json()
    assert (s["crew"], s["event"], s["title"], s["expected"]) == (eid, None, "Party · team", 2)
    assert _crew(c, 9, eid).json()["session"] == s["session"]                           # tapped again: the same one
    assert c.get(f"/api/events/{eid}/crew-screen", headers=tma(9)).json()["session"] == s["session"]
    guests = c.post(f"/api/events/{eid}/screen", headers=tma(9)).json()                  # the guests' session: another one
    assert guests["session"] != s["session"] and guests["event"] == eid and guests["crew"] is None
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = ?", (oid,))
    assert c.get(f"/api/events/{eid}/crew-screen", headers=tma(9)).status_code == 403   # an archived club
    con.close()


def test_two_taps_at_once_make_one(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, eid = _setup(c, con)
    out = []
    ts = [threading.Thread(target=lambda: out.append(_crew(c, 9, eid).json()["session"])) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(set(out)) == 1 and con.execute("SELECT COUNT(*) FROM qr_sessions WHERE crew_event_id = ?", (eid,)).fetchone()[0] == 1
    con.close()


def test_outsiders_counted_apart_and_guests_never_mix(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, eid = _setup(c, con)
    login(c, 3, "cat")                                                                   # a guest with a ticket, not in the club
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) SELECT ?, id, 'going', 'x-1', 0, 0 FROM users WHERE tg_id = 3", (eid,))
    sid = _crew(c, 9, eid).json()["session"]
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(3), json={"p": p}).json()["done"]          # anyone's scan counts: the usual answer
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]          # the team member
    # the team's marks are no event check-in: the guest's ticket stays unused
    assert con.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ? AND checked_in_at IS NOT NULL", (eid,)).fetchone()[0] == 0
    row = [x for x in c.get("/api/screens", headers=tma(9)).json() if x["session"] == sid][0]
    assert (row["came"], row["done"], row["expected"]) == (1, 2, 2)                     # came 1 of 2 members, one more apart
    assert c.get(f"/api/screens/{sid}/people", headers=tma(9)).json() == {"came": ["Testov Ann"], "other": ["Testov Cat"], "absent": ["Testov Dana"]}
    for tg in (1, 3):
        assert c.get(f"/api/screens/{sid}/people", headers=tma(tg)).status_code == 403
    csv = c.get(c.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]).text.splitlines()
    assert [x.split(",")[0] for x in csv[1:]] == ["came", "came (not on the list)", "absent"]
    # the guests' session: the member's and the guest's scans there never reach the team's
    g = c.post(f"/api/events/{eid}/screen", headers=tma(9)).json()["session"]
    assert g != sid and con.execute("SELECT crew_event_id FROM qr_sessions WHERE id = ?", (g,)).fetchone()[0] is None
    con.close()


def test_lists_and_csv_stay_the_organizers(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, eid = _setup(c, con)
    _club_runs(c, con, 8, "eve", "go")
    sid = _crew(c, 9, eid).json()["session"]
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    for tg in (1, 8):
        assert c.get(f"/api/screens/{sid}/absent", headers=tma(tg)).status_code == 403
        assert c.post(f"/api/screens/{sid}/csv", headers=tma(tg)).status_code == 403
        assert c.post(f"/api/screens/{sid}/finish", headers=tma(tg)).status_code == 403
        assert sid not in [x["session"] for x in c.get("/api/screens", headers=tma(tg)).json()]
    assert c.get(f"/api/screens/{sid}/absent", headers=tma(9)).json() == ["Testov Ann", "Testov Dana"]
    con.close()


def test_caps_cancelled_and_deleted(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, eid = _setup(c, con)
    for _ in range(checkin.CLUB_OPEN - 1):
        c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={})
    sid = _crew(c, 9, eid).json()["session"]                                             # the fifth open one
    assert c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={}).status_code == 429  # counted as a club session
    assert _crew(c, 9, _ev(con, oid, now())).status_code == 429
    late = _ev(con, oid, now())
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (late,))
    assert _crew(c, 9, late).status_code == 409                                          # a cancelled event: none made
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    con.execute("DELETE FROM events WHERE id = ?", (eid,))                               # the event deleted: the attendance stays
    assert tuple(con.execute("SELECT crew_event_id, org_id FROM qr_sessions WHERE id = ?", (sid,)).fetchone()) == (None, oid)
    assert _crew(c, 9, eid).status_code == 403
    assert c.get(f"/api/screens/{sid}/absent", headers=tma(9)).status_code == 200
    con.close()


def test_finishes_after_12h_and_its_event(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, eid = _setup(c, con)
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (now() - 3600, now() + 3600, eid))
    sid = _crew(c, 9, eid).json()["session"]
    c.post(f"/api/screens/{sid}/start", headers=tma(9))
    con.execute("UPDATE qr_sessions SET started_at = started_at - ? WHERE id = ?", (checkin.STALE + 60, sid))
    checkin.sweep(con)
    assert con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0] is None   # 12 h on, its event still on
    con.execute("UPDATE events SET ends_at = ? WHERE id = ?", (now() - 1, eid))
    checkin.sweep(con)
    assert con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]          # both over
    con.close()


def test_no_volunteer_hours(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, eid = _setup(c, con)
    checkin.logic.vol.ORG = "chess"                                                      # this club is the ledger's
    try:
        sid = _crew(c, 9, eid).json()["session"]
        p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
        assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
        assert con.execute("SELECT COUNT(*) FROM vol_meets WHERE session_id = ?", (sid,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM vol_shifts WHERE session_id = ?", (sid,)).fetchone()[0] == 0
    finally:
        checkin.logic.vol.ORG = ""
    con.close()
