"""A club of one person is off the Clubs registry (clubs.orgs) for everyone but that person; its page still opens."""
from __future__ import annotations

import time

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

PRES, FAN, SECOND = 20, 30, 40


def test_solo_club_hidden(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(logic.clubs, "CLUB_MIN", 5)
    for t, n in ((PRES, "pres"), (FAN, "fan"), (SECOND, "second")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    uid = lambda t: con.execute("SELECT id FROM users WHERE tg_id = ?", (t,)).fetchone()[0]  # noqa: E731
    org = logic.create_org(con, None, "Lonely", "LO", "crown_3d", True)
    logic.set_role(con, None, uid(PRES), org, "president", "test")
    ids = lambda t: [o["id"] for o in c.get("/api/orgs", headers=tma(t)).json()]  # noqa: E731
    assert org not in ids(FAN) and org in ids(PRES)  # only its one member sees it
    assert c.get(f"/api/orgs/{org}", headers=tma(FAN)).status_code == 200  # a direct link works
    logic.set_role(con, None, uid(SECOND), org, "member", "test")
    logic.core._SHARED.clear()
    assert org not in ids(FAN)  # two: still under CLUB_MIN
    for t in range(50, 50 + logic.clubs.CLUB_MIN - 2):
        login(c, t, f"m{t}")
        logic.set_role(con, None, uid(t), org, "member", "test")
    logic.core._SHARED.clear()
    assert org in ids(FAN)  # CLUB_MIN people: a club


def test_quiet_initiative_hidden(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(logic.clubs, "CLUB_QUIET", 60 * 86400)
    for t, n in ((PRES, "pres"), (FAN, "fan")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    pres = con.execute("SELECT id FROM users WHERE tg_id = ?", (PRES,)).fetchone()[0]
    org = logic.create_org(con, None, "Quiet", "QU", "crown_3d", False)
    logic.set_role(con, None, pres, org, "president", "test")
    con.execute("UPDATE orgs SET created_at = 0 WHERE id = ?", (org,))
    ids = lambda t: [o["id"] for o in c.get("/api/orgs", headers=tma(t)).json()]  # noqa: E731
    logic.core._SHARED.clear()
    assert org not in ids(FAN) and org in ids(PRES)        # quiet: gone, but not for its own
    con.execute("INSERT INTO posts (org_id, title, created_at) VALUES (?, 'hi', ?)", (org, int(time.time())))
    logic.core._SHARED.clear()
    assert org in ids(FAN)                                 # a post brings it back
    con.execute("UPDATE posts SET created_at = 0 WHERE org_id = ?", (org,))
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (org,))
    logic.core._SHARED.clear()
    assert org in ids(FAN)                                 # an official club stays, quiet or not
    con.close()


def test_one_official_presidency_on_handover(env):
    c, cfg = env
    for t, n in ((PRES, "pres"), (SECOND, "second")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    uid = lambda t: con.execute("SELECT id FROM users WHERE tg_id = ?", (t,)).fetchone()[0]  # noqa: E731
    a = logic.create_org(con, None, "Official A", "OA", "crown_3d", True)
    b = logic.create_org(con, None, "Official B", "OB", "crown_3d", True)
    logic.set_role(con, None, uid(PRES), a, "president", "test")
    logic.set_role(con, None, uid(SECOND), a, "member", "test")
    logic.set_role(con, None, uid(SECOND), b, "president", "test")     # the admin's way stays free
    r = c.post(f"/api/orgs/{a}/transfer", headers=tma(PRES), json={"userId": uid(SECOND)})
    assert r.status_code == 409 and r.json()["message"] == "president_elsewhere"
    con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (a,))     # an initiative has no such limit
    assert c.post(f"/api/orgs/{a}/transfer", headers=tma(PRES), json={"userId": uid(SECOND)}).status_code == 200
    # now SECOND leads the initiative and official B: the ask for the initiative's check mark waits until one post goes
    con.execute("UPDATE orgs SET top_at = 1 WHERE id = ?", (a,))
    r = c.post(f"/api/orgs/{a}/official-path", headers=tma(SECOND))
    assert r.status_code == 409 and r.json()["message"] == "president_elsewhere"
    con.close()
