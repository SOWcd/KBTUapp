"""A club's latest events in the Clubs list (clubs._org_parts "last", one query for all) and on its page (Recent)."""
from __future__ import annotations

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

PRES, FAN = 20, 30


def test_last_and_recent(env):
    c, cfg = env
    login(c, PRES, "pres")
    login(c, FAN, "fan")
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Crystal", "CR", "crown_3d", True)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = ?", (PRES,)).fetchone()[0], org, "president", "test")
    now = logic.core.now()

    def ev(title, ago, **kw):
        e = c.post(f"/api/orgs/{org}/events", headers=tma(PRES), json={"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF",
                   "title": title, "startsAt": now + 86400, **kw}).json()
        assert c.post(f"/api/events/{e['id']}/publish", headers=tma(PRES)).status_code == 200
        con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (now - ago * 86400, e["id"]))
        con.commit()
        logic.core._SHARED.clear()  # the shared part is kept a few seconds
        return e["id"]

    last = lambda: next(o for o in c.get("/api/orgs", headers=tma(FAN)).json() if o["id"] == org)["last"]  # noqa: E731
    assert last() is None
    ev("Old", 40)  # past the 30 days
    assert last() is None
    a = ev("Case Night", 5)
    ev("Earlier", 9)
    ev("Team only", 2, visibility="members")
    assert last()["id"] == a and last()["title"] == "Case Night"  # the latest public one, not the team's
    # the club's page: newest first, the team's own only to the team
    assert [e["title"] for e in c.get(f"/api/events/past?org={org}", headers=tma(FAN)).json()] == ["Case Night", "Earlier", "Old"]
    assert c.get(f"/api/events/past?org={org}", headers=tma(PRES)).json()[0]["title"] == "Team only"
