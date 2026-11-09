"""A club of one person is off the Clubs registry (clubs.orgs) for everyone but that person; its page still opens."""
from __future__ import annotations

import asyncio
import time

from kbtu import ai, db, logic
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
    ids = lambda t: [o["id"] for o in c.get("/api/orgs", headers=tma(t)).json() if not o["small"]]  # noqa: E731
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


def test_president_hears_the_club_is_hidden_once(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(logic.clubs, "CLUB_MIN", 5)
    login(c, PRES, "pres")
    con = db.connect(cfg.db_path)
    uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (PRES,)).fetchone()[0]
    org = logic.create_org(con, None, "Lonely", "LO", "crown_3d", True)
    logic.set_role(con, None, uid, org, "president", "test")
    day = 86400 * 20000 + 7 * 3600  # 12:00 in Almaty, past the job's hour
    sent = lambda: con.execute("SELECT user_id, ref FROM bot_outbox WHERE kind = 'club_hidden'").fetchall()  # noqa: E731
    monkeypatch.setattr(logic.core, "now", lambda: day)
    con.execute("UPDATE orgs SET created_at = ? WHERE id = ?", (day - 86400, org))
    logic.clubs.hidden_day(con)
    assert not sent()  # a new club has two days
    con.execute("UPDATE orgs SET created_at = ? WHERE id = ?", (day - 3 * 86400, org))
    monkeypatch.setattr(logic.core, "now", lambda: day + 86400)
    for _ in range(2):
        logic.clubs.hidden_day(con)
    monkeypatch.setattr(logic.core, "now", lambda: day + 2 * 86400)
    logic.clubs.hidden_day(con)
    assert [tuple(r) for r in sent()] == [(uid, f"chid:{org}")]


def test_quiet_flag(env, monkeypatch):
    """Quiet clubs stay listed and carry the flag; new, active and official ones don't."""
    c, cfg = env
    monkeypatch.setattr(logic.clubs, "CLUB_QUIET", 30 * 86400)
    for t, n in ((PRES, "pres"), (FAN, "fan")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    pres = con.execute("SELECT id FROM users WHERE tg_id = ?", (PRES,)).fetchone()[0]
    org = logic.create_org(con, None, "Quiet", "QU", "crown_3d", False)
    logic.set_role(con, None, pres, org, "president", "test")

    def quiet():
        logic.core._SHARED.clear()
        return next(o for o in c.get("/api/orgs", headers=tma(FAN)).json() if o["id"] == org)["quiet"]

    assert quiet() is False                                # a new club has its 30 days
    con.execute("UPDATE orgs SET created_at = 0 WHERE id = ?", (org,))
    assert quiet() is True                                 # still listed, and marked
    con.execute("INSERT INTO posts (org_id, title, created_at) VALUES (?, 'hi', ?)", (org, int(time.time())))
    assert quiet() is False                                # a post wakes it
    con.execute("UPDATE posts SET created_at = 0 WHERE org_id = ?", (org,))
    assert quiet() is True
    now = int(time.time())
    con.execute("""INSERT INTO events (org_id, status, title, starts_at, created_at, updated_at) VALUES (?, 'published', 'e', ?, 0, 0)""", (org, now - 86400))
    assert quiet() is False                                # an event in the 30 days wakes it
    con.execute("UPDATE events SET starts_at = 0 WHERE org_id = ?", (org,))
    assert quiet() is True
    con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_at) VALUES (?, 'r', ?, 'done', 0)", (org, now - 86400))
    assert quiet() is False                                # so does a round closed in the 30 days, not only an open one
    con.execute("UPDATE rounds SET closes_at = 0 WHERE org_id = ?", (org,))
    assert quiet() is True
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (org,))
    assert quiet() is False                                # an official club is never quiet
    con.close()


def test_category_set_by_lead_and_filled_by_ai(env):
    c, cfg = env
    for t, n in ((PRES, "pres"), (FAN, "fan")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    pres = con.execute("SELECT id FROM users WHERE tg_id = ?", (PRES,)).fetchone()[0]
    mine = logic.create_org(con, None, "Mine", "MI", "crown_3d", False)
    other = logic.create_org(con, None, "Other", "OT", "crown_3d", False)
    logic.set_role(con, None, pres, mine, "president", "test")
    assert c.patch(f"/api/orgs/{mine}", json={"category": "nonsense"}, headers=tma(PRES)).status_code >= 400
    assert c.patch(f"/api/orgs/{mine}", json={"category": "art"}, headers=tma(FAN)).status_code >= 400  # not its lead
    assert c.patch(f"/api/orgs/{mine}", json={"category": "art"}, headers=tma(PRES)).json()["category"] == "art"

    async def said(cfg, http, msgs, **kw):
        assert kw["check"]("it") and not kw["check"]("anything else")
        return "IT\n", "qa"
    original, logic_chat = ai.llm.chat, said
    ai.llm.chat = logic_chat
    try:
        filled, left = asyncio.run(ai.fill_categories(con, cfg, None))
    finally:
        ai.llm.chat = original
    assert (filled, left) == (con.execute("SELECT COUNT(*) FROM orgs WHERE category = 'it'").fetchone()[0], 0)
    get = lambda i: con.execute("SELECT category FROM orgs WHERE id = ?", (i,)).fetchone()[0]  # noqa: E731
    assert get(mine) == "art" and get(other) == "it"       # a club's own choice stays
    con.close()


def test_friends_in_a_club(env):
    """Only my friends, read for the list; a club hiding its members or a friend hiding where they go shows nobody."""
    c, cfg = env
    for t, n in ((PRES, "pres"), (FAN, "fan"), (SECOND, "second")):
        login(c, t, n)
    con = db.connect(cfg.db_path)
    uid = lambda t: con.execute("SELECT id FROM users WHERE tg_id = ?", (t,)).fetchone()[0]  # noqa: E731
    org = logic.create_org(con, None, "Pals", "PA", "crown_3d", False)
    logic.set_role(con, None, uid(PRES), org, "president", "test")
    logic.set_role(con, None, uid(SECOND), org, "member", "test")
    a, b = sorted((uid(FAN), uid(PRES)))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (a, b))

    def seen(t):
        logic.core._SHARED.clear()
        o = next(x for x in c.get("/api/orgs", headers=tma(t)).json() if x["id"] == org)
        return [p["id"] for p in o["friends"]], o["friendsN"]

    assert seen(FAN) == ([uid(PRES)], 1)                   # my friend, and not the stranger beside them
    assert seen(SECOND) == ([], 0)                         # not friends with anyone there
    con.execute("UPDATE users SET show_going = 0 WHERE id = ?", (uid(PRES),))
    assert seen(FAN) == ([], 0)                            # hides where they go
    con.execute("UPDATE users SET show_going = 1 WHERE id = ?", (uid(PRES),))
    con.execute("UPDATE orgs SET members_hidden = 1 WHERE id = ?", (org,))
    assert seen(FAN) == ([], 0)                            # the club hides its members
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
