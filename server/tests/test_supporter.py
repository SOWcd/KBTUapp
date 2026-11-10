"""Fuel (a new Stars gift's award) and Club founder (by hand, for a club that earned it): who gives them, who sees them."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_stars import Telegram, hear, payment


def staff(env):
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60, 63}))))
    login(c, 60, "boss"); login(c, 63, "adm")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    return c, cfg, con


def test_a_new_stars_gift_gives_fuel_once_and_quietly(env):
    c, cfg = env
    ali = login(c, 7, "ali")  # the payer of test_stars.payment()
    con = db.connect(cfg.db_path)
    hear(cfg, Telegram([payment()], []))
    hear(cfg, Telegram([payment(2)], []))                # the same charge replayed
    hear(cfg, Telegram([payment(3, charge="c2")], []))   # a second gift: held already, nothing more
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'supporter'", (ali["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ?", (ali["id"],)).fetchone()[0] == 0  # no push
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'grant'").fetchone()[0] == 0
    assert {r[1] for r in con.execute("PRAGMA table_info(star_gifts)")} == {"charge_id", "amount", "created_at"}  # still payer-less
    assert c.get("/api/me", headers=tma(7, "Ali")).json()["unlocked"] == [{"code": "supporter", "level": 1}]


def test_only_the_creator_gives_fuel_by_hand_and_never_by_link(env):
    c, cfg, con = staff(env)
    ali = login(c, 61, "ali")
    give = lambda code, h, **kw: c.post("/api/admin/grants", headers=h, json={"userId": ali["id"], "code": code, **kw})  # noqa: E731
    assert give("supporter", tma(63)).status_code == 403
    assert c.post("/api/admin/grants/take-back", headers=tma(63), json={"userId": ali["id"], "code": "supporter"}).status_code == 403
    assert c.get("/api/admin/awards/supporter/people", headers=tma(63)).status_code == 403
    assert "supporter" not in c.get("/api/admin/awards", headers=tma(63)).json()
    assert give("supporter", tma(60)).status_code == 200
    assert "supporter" not in c.get(f"/api/admin/grants/of/{ali['id']}", headers=tma(63)).json()["has"]
    assert c.get(f"/api/admin/grants/of/{ali['id']}", headers=tma(60)).json()["has"] == ["supporter"]
    boss = logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = 60").fetchone()[0], "admin", True)
    for bulk in (lambda: logic.grant_link(con, boss, "supporter"), lambda: logic.open_qr(con, boss, "club_founder")):
        try:
            bulk()
            raise AssertionError("given in bulk")
        except logic.ApiError as e:
            assert e.code == "bad_input"


def test_club_founder_only_for_a_club_that_earned_it(env):
    c, cfg, con = staff(env)
    ali = login(c, 61, "ali")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    give = lambda **kw: c.post("/api/admin/grants", headers=tma(63), json={"userId": ali["id"], "code": "club_founder", **kw})  # noqa: E731
    assert give().status_code == 400 and give(orgId=1).status_code == 400  # no club; a student initiative
    con.execute("UPDATE orgs SET top_at = 1 WHERE id = 1")
    assert give(orgId=1).status_code == 200
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")  # stays whatever the club does later
    mine = next(a for a in c.get(f"/api/users/{ali['id']}", headers=tma(61)).json()["awards"]["achievements"] if a["code"] == "club_founder")
    assert mine["level"] == 1 and mine["org"]["id"] == 1


def test_fuel_shows_to_others_only_on_the_showcase(env):
    c, cfg = env
    ali, bob = login(c, 61, "ali"), login(c, 62, "bob")
    codes = lambda h: [a["code"] for a in c.get(f"/api/users/{ali['id']}", headers=h).json()["awards"]["achievements"]]  # noqa: E731
    assert "supporter" not in codes(tma(61))                     # not even locked on my own: no nudge to pay
    con = db.connect(cfg.db_path)
    with db.tx(con):
        logic._grant(con, None, ali["id"], "supporter", log=False)
    assert "supporter" in codes(tma(61)) and "supporter" not in codes(tma(62))
    c.patch("/api/me", headers=tma(61), json={"showcase": ["supporter"]})
    p = c.get(f"/api/users/{ali['id']}", headers=tma(62)).json()
    assert "supporter" in [a["code"] for a in p["awards"]["achievements"]] and p["shelf"] == ["supporter"]
    assert next(a for a in p["awards"]["achievements"] if a["code"] == "supporter")["rarity"] == 0  # no count of givers
