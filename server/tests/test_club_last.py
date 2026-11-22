"""A club's latest events in the Clubs list (clubs._org_parts "last", one query for all) and on its page (Recent)."""
from __future__ import annotations

import pytest

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
    login(c, 40, "mate")
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 40").fetchone()[0], org, "member", "test")  # two: a listed club
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


@pytest.mark.parametrize("kind", ["club", "school"])
def test_org_event_rating(env, kind):
    c, cfg = env
    voters = [login(c, uid, name)["id"] for uid, name in [(20, "pres"), (30, "fan"), (40, "mate"), (50, "guest")]]
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Crystal", "CR", "crown_3d", True, kind=kind)
    logic.set_role(con, None, voters[0], org, "president", "test")
    now = logic.core.now()

    def event(scores, *, days=10, visibility="public", school=None, status="published", hidden=None):
        start = now - days * 86400
        eid = con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, emoji, visibility, school, hidden_at,
            created_by, created_at, updated_at) VALUES (?, ?, 'Rating', 'Atrium', ?, 'crown_3d', ?, ?, ?, ?, 0, 0)""",
                          (org, status, start, visibility, school, hidden, voters[0])).lastrowid
        public_after = start + logic.core.NO_END + logic.organizing.RATE_FOR if visibility == "public" and school is None else None
        con.executemany("""INSERT INTO event_ratings (event_id, user_id, score, comment, created_at, public_after)
            VALUES (?, ?, ?, 'Private', 0, ?)""", [(eid, uid, score, public_after) for uid, score in zip(voters, scores)])
        return eid

    event([1, 1])
    event([1, 1, 1], days=1)  # still open, even with three votes
    restricted = event([1, 1, 1], visibility="members")
    con.execute("UPDATE events SET visibility = 'public' WHERE id = ?", (restricted,))
    event([1, 1, 1], school="site")
    event([1, 1, 1], status="cancelled")
    event([1, 1, 1], hidden=now)
    page = f"/api/orgs/{org}"
    assert c.get(page, headers=tma(FAN)).json()["eventRating"] is None
    event([3, 4, 5])
    event([5, 5, 5, 5])
    for headers in (tma(PRES), tma(FAN), tma(60)):
        result = c.get(page, headers=headers).json()
        assert result["eventRating"] == 4.6  # weight each vote equally across qualifying events
        assert "Private" not in str(result)
    assert next(o for o in c.get("/api/orgs", headers=tma(FAN)).json() if o["id"] == org)["eventRating"] == 4.6
