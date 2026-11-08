"""A club of one person is off the Clubs registry (clubs.orgs) for everyone but that person; its page still opens."""
from __future__ import annotations

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
