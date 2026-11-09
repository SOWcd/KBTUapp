"""Check-in helpers let in by an organizer's QR (checkin.py hand/helper): what they get, what they never get, when it ends."""
from __future__ import annotations

import time

from kbtu import checkin, db
from test_core import delete_now, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)
from test_review_checkin import _phone_event as _head_event, _scan

H = 9  # the organizer (test_review_checkin._phone_event, made Vice below)


def _phone_event(c, con, *args):
    """The organizer as the club's Vice: the policy's door helper is let in by a President or Vice."""
    out = _head_event(c, con, *args)
    con.execute("UPDATE org_members SET role = 'vice' WHERE role = 'head'")
    return out


def _hand(c, sid):
    return c.post(f"/api/screens/{sid}/helpers", headers=tma(H)).json()


def _ask(c, tg, p, join=False):
    return c.post("/api/screens/helper", headers=tma(tg), json={"p": p, "join": join})


def _in(c, con, tg=2, name="bob"):
    """A running event's session with student `tg` let in as a helper: (event, session, its check-in QR)."""
    eid, sid, ci = _phone_event(c, con, "vol")
    login(c, tg, name)
    assert _ask(c, tg, _hand(c, sid)["param"], True).status_code == 200
    return eid, sid, ci


def _show(c, sid, tg=2):
    return c.post(f"/api/screens/{sid}/show", headers=tma(tg))


def test_join_happy_path(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _phone_event(c, con, "vol")
    login(c, 2, "bob")
    p = _hand(c, sid)["param"]
    seen = _ask(c, 2, p).json()
    assert seen["title"] == "Meet" and seen["session"] == sid and seen["event"] == eid and not seen["joined"]  # asking changes nothing
    assert con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 0 and _show(c, sid).status_code == 403
    got = _ask(c, 2, p, True).json()
    assert got["joined"] and got["scanner"]
    assert _ask(c, 2, p, True).json()["joined"] and _hand(c, sid)["helpers"] == 1                         # idempotent
    shown = _show(c, sid).json()
    assert shown["param"].startswith("ci_") and _scan(c, 3, shown["param"]).status_code in (200, 401, 403)
    assert con.execute("SELECT added_by FROM qr_helpers").fetchone()[0] == con.execute("SELECT id FROM users WHERE tg_id = ?", (H,)).fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_helper'").fetchone()[0] == 1   # once, for the repeat too
    con.close()


def test_several_helpers(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _in(c, con)
    login(c, 3, "cat")
    assert _ask(c, 3, _hand(c, sid)["param"], True).json()["joined"]
    assert _hand(c, sid)["helpers"] == 2 and _show(c, sid, 3).status_code == 200
    con.close()


def test_forged_old_and_crossed_codes_refused(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, ci = _phone_event(c, con, "vol")
    login(c, 2, "bob")
    good = _hand(c, sid)["param"]
    _, s, slot, by, sig = good.split("_")
    bad = lambda p: _ask(c, 2, p, True).json()  # noqa: E731
    assert bad(f"hq_{s}_{slot}_{by}_{'0' * 16}")["message"] == "qr"
    assert bad(f"hq_{s}_{slot}_{int(by) + 1}_{sig}")["message"] == "qr"                                   # the issuer is signed
    assert bad(ci)["message"] == "qr"                                                                     # a check-in QR isn't a helper's
    assert bad(ci.replace("ci_", "hq_"))["message"] == "qr"
    assert bad("hq_x")["message"] == "qr"
    assert _scan(c, 2, good).json()["message"] == "qr"                                                    # nor a helper's a check-in QR
    assert _scan(c, 2, f"ci_{s}_{slot}_{sig}").json()["message"] == "qr"
    old = int(time.time()) // checkin.SLOT - (checkin.SCAN_OK + 3 * checkin.SLOT) // checkin.SLOT
    assert bad(f"hq_{s}_{old}_{by}_{checkin._sig(cfg.token_key, f'qh.{s}.{old}.{by}.0')}")["message"] == "qr_old"
    con.execute("UPDATE qr_sessions SET help_until = ? WHERE id = ?", (int(time.time()) - checkin.HAND_GRACE - 1, sid))  # the sheet is closed
    assert bad(good)["message"] == "qr_old"
    assert con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 0
    con.close()


def test_helper_refused_the_rest(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)
    h = tma(2)
    for act in ("finish", "unpair", "out", "in", "start", "helpers", "csv"):
        assert c.post(f"/api/screens/{sid}/{act}", headers=h).status_code == 403, act
    assert c.delete(f"/api/screens/{sid}/helpers", headers=h).status_code == 403                          # can't hand on or clear
    assert c.get("/api/screens", headers=h).json() == []                                                  # no session list
    assert c.get(f"/api/events/{eid}/door", headers=h).status_code == 403                                 # no list by name
    assert c.post(f"/api/events/{eid}/screen", headers=h).status_code == 403
    con.close()


def test_helper_scans_as_a_scanner_only(env):
    """Tickets of those going; no walk-in by a badge, no list, no flag: crew.py's "scan"."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)
    assert c.get(f"/api/events/{eid}", headers=tma(2)).json()["myCrew"] == "scan"
    ann = login(c, 1, "ann")
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at)
        VALUES (?, ?, 'going', ?, 0, 0)""", (eid, ann["id"], f"{eid}-K7M2"))  # signed up before it began
    r = c.post(f"/api/events/{eid}/checkin", headers=tma(2), json={"code": "K7M2"}).json()
    assert r["result"] == "ok" and r["flagged"] is False and r["person"]["id"] == ann["id"]
    con.close()


def test_access_ends_on_removal(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)
    assert _hand(c, sid)["helpers"] == 1
    assert c.delete(f"/api/screens/{sid}/helpers", headers=tma(H)).json()["helpers"] == 0
    assert _show(c, sid).status_code == 403 and c.get(f"/api/events/{eid}", headers=tma(2)).json()["myCrew"] is None
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(2), json={"code": "X"}).status_code == 403
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'checkin_helpers_off'").fetchone()[0] == 1
    con.close()


def test_access_ends_on_finish(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    eid, sid, _ = _in(c, con)
    p = _hand(c, sid)["param"]
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(H)).status_code == 200
    assert _show(c, sid).status_code == 403 and c.get(f"/api/events/{eid}", headers=tma(2)).json()["myCrew"] is None
    assert _ask(c, 2, p, True).json()["error"] == "closed"
    assert con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 0
    con.close()


def test_club_ban_and_lost_student_end_it(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _in(c, con)
    uid = con.execute("SELECT id FROM users WHERE tg_id = 2").fetchone()[0]
    p = _hand(c, sid)["param"]
    org = con.execute("SELECT org_id FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (org, uid))
    assert _show(c, sid).status_code == 403 and _ask(c, 2, p, True).status_code == 403
    con.execute("DELETE FROM org_bans")
    assert _show(c, sid).status_code == 200
    con.execute("DELETE FROM students WHERE user_id = ?", (uid,))
    assert _show(c, sid).status_code == 403
    con.close()


def test_non_student_refused(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _phone_event(c, con, "vol")
    c.get("/api/me", headers=tma(5))
    r = _ask(c, 5, _hand(c, sid)["param"], True)
    assert r.json()["error"] == "need_student" and con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 0
    con.close()


def test_deleted_account_leaves_no_row(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    _in(c, con)
    assert con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 1
    delete_now(c, cfg, tma(2))
    assert con.execute("SELECT COUNT(*) FROM qr_helpers").fetchone()[0] == 0
    con.close()


def test_remove_all_kills_the_codes_shown(env):
    """The one just removed can't scan the same code again; a fresh code works; a lone surrogate is a refusal, not a crash."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _phone_event(c, con, "vol")
    login(c, 2, "bob")
    old = _hand(c, sid)["param"]
    assert _ask(c, 2, old, True).status_code == 200
    c.delete(f"/api/screens/{sid}/helpers", headers=tma(H))
    assert _ask(c, 2, old, True).status_code == 400 and _show(c, sid).status_code == 403
    assert checkin._same("a", "\ud800") is False
    assert _ask(c, 2, _hand(c, sid)["param"], True).status_code == 200 and _show(c, sid).status_code == 200
    con.close()


def test_a_head_cannot_hand_it_over(env):
    """A Head runs the session but doesn't let helpers in (the policy says President or Vice)."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    _, sid, _ = _head_event(c, con, "vol")
    assert c.post(f"/api/screens/{sid}/helpers", headers=tma(H)).status_code == 403
