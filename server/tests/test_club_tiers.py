"""Official clubs get the full app, student initiatives a limited one: the events channel, the followers' message,
News for everyone, the name rules and losing the check mark. Each test fails while its rule is gone."""
from __future__ import annotations

import dataclasses
import time

from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, logic
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)

EV = {"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}


def _club(c, cfg, official: bool, name="Chess", pres=20):
    """A club (tg <pres> its President) and its follower tg 30; returns (con, org id)."""
    login(c, pres, "pres"); login(c, 30, "fan"); login(c, 31, "other")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, name, "CH", "crown_3d", official)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = ?", (pres,)).fetchone()[0], oid, "president", "test")
    assert c.put(f"/api/orgs/{oid}/subscription", headers=tma(30)).status_code == 200
    return con, oid


def _body(title, **kw):
    return {**EV, "title": title, "startsAt": logic.core.now() + 7 * 86400, **kw}


def _publish(c, oid, title, pres=20, **kw):
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(pres), json=_body(title, **kw)).json()
    return c.post(f"/api/events/{e['id']}/publish", headers=tma(pres)).json()


def test_channel_is_official_clubs(env):
    """Rule 1: an initiative's event stays off @KBTUevents; one posted before the check mark went keeps its edits; the
    check mark sends its unposted future events out."""
    c, cfg = env
    con, oid = _club(c, cfg, False)
    e = _publish(c, oid, "Open day")
    assert logic.channel_due(con) == []
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    (row, _, _, sig), = logic.channel_due(con)
    assert row["id"] == e["id"]
    con.execute("UPDATE events SET channel_msg = 7, channel_sig = ? WHERE id = ?", (sig, e["id"]))
    con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (oid,))
    assert logic.channel_due(con) == []
    c.post(f"/api/events/{e['id']}/cancel", headers=tma(20))
    assert [r[0]["id"] for r in logic.channel_due(con)] == [e["id"]]  # its post still says "cancelled"


def test_followers_told_weekly(env, monkeypatch):
    """Rule 2: an initiative tells its followers of one event a rolling week; the others still show in the app; deleting
    a cancelled event buys no extra message; an official club tells of each."""
    c, cfg = env
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    con, oid = _club(c, cfg, False)
    told = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event'").fetchone()[0]  # noqa: E731
    a = _publish(c, oid, "One")
    assert a["told"] is True and a["tellAfter"] is None and told() == 1
    clock[0] += 3600
    b = _publish(c, oid, "Two")
    assert b["told"] is False and b["tellAfter"] == t0 + 7 * 86400 and told() == 1
    assert {x["id"] for x in c.get("/api/events", headers=tma(31), params={"org": oid}).json()} >= {a["id"], b["id"]}  # its page (not the afisha: test_afisha)
    for x in (a, b):  # cancelled and deleted: the week still counts
        c.post(f"/api/events/{x['id']}/cancel", headers=tma(20)); c.delete(f"/api/events/{x['id']}", headers=tma(20))
    assert _publish(c, oid, "Three")["told"] is False and told() == 1
    clock[0] = t0 + 7 * 86400 + 1
    assert _publish(c, oid, "Four")["told"] is True and told() == 2
    assert "told" not in _publish(c, oid, "Team", visibility="members")  # nobody outside the team is told of it
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    assert _publish(c, oid, "Five")["told"] is True and _publish(c, oid, "Six")["told"] is True and told() == 4


def test_news_for_everyone_is_official(env):
    """Rule 3: News 'all' shows an initiative's posts to its members and followers alone; an official club's to all."""
    c, cfg = env
    con, oid = _club(c, cfg, False)
    _, off = con, logic.create_org(con, None, "Debate", "DB", "crown_3d", True)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], off, "president", "test")
    # an initiative's own posts open at the Ascent's collab (test_official_path): one from before, as the app had them
    con.execute("INSERT INTO posts (org_id, author_id, audience, title, body, created_at) VALUES (?, NULL, 'public', 'Initiative news', 'x', 0)", (oid,))
    assert c.post(f"/api/orgs/{off}/posts", headers=tma(20), json={"title": "Official news", "body": "x"}).status_code == 200
    seen = lambda uid: {p["title"] for p in c.get("/api/posts", headers=tma(uid), params={"scope": "all"}).json()}  # noqa: E731
    assert seen(31) == {"Official news"}
    assert seen(30) == seen(20) == {"Initiative news", "Official news"}  # a follower; a member
    assert {p["title"] for p in c.get("/api/posts", headers=tma(31), params={"scope": f"org:{oid}"}).json()} == {"Initiative news"}  # its own page


def test_club_names(env):
    """Rule 4: an application's name, short name and abbr pass the rename check at application and at approval;
    a Vice can't set KBTU or a check mark as the abbr or short name; an official club is renamed by DMP alone."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    good = {"name": "Go Club", "short": "GO", "description": "We play go every week.", "emoji": "trophy_3d", "cover": 2, "links": []}
    for bad in ({"name": "КВТU Go"}, {"name": "Go ✓"}, {"short": "✓"},
                {"name": "Kazakh British Technical University"}):  # look-alike KBTU, a tick, a tick, KBTU as the initials
        assert c.post("/api/club-applications", headers=A, json={**good, **bad}).status_code == 400, bad
    con = db.connect(cfg.db_path)
    logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    assert c.post("/api/club-applications", headers=A, json={**good, "name": "Сhess"}).status_code == 409  # a Cyrillic C
    aid = c.post("/api/club-applications", headers=A, json=good).json()["id"]
    logic.create_org(con, None, "Gо Club", "GC", "crown_3d", False)  # named meanwhile, with a Cyrillic o
    assert c.post(f"/api/admin/club-applications/{aid}", headers=B, json={"approve": True}).status_code == 409
    # renames: abbr and short checked; an official club's name is DMP's
    con2, oid = _club(c, cfg, False, "Robots", pres=62)
    P = tma(62)
    for bad in ({"abbr": "KBTU"}, {"abbr": "✓RB"}, {"short": "✓"}, {"abbr": "JCC_KBTU"}, {"abbr": "JC_C"}, {"abbr": "J.C"}):
        assert c.patch(f"/api/orgs/{oid}", headers=P, json=bad).status_code == 400, bad
    assert c.patch(f"/api/orgs/{oid}", headers=P, json={"name": "Robotics"}).status_code == 200
    con2.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    assert c.patch(f"/api/orgs/{oid}", headers=P, json={"name": "Robots Lab"}).status_code == 403
    assert c.patch(f"/api/orgs/{oid}", headers=P, json={"description": "We build robots."}).status_code == 200
    assert c.patch(f"/api/orgs/{oid}", headers=B, json={"name": "Robots Lab"}).status_code == 200


def test_losing_the_tick(env):
    """Rule 5: a club that lost the check mark may make its paid event free and drop its partner host, not set new
    ones; its President hears it from the bot."""
    c, cfg = env
    con, oid = _club(c, cfg, True)
    paid = _body("Gala", price=2000, payToName="Arman A.", payPhone="87071234567")
    party = _body("Party", seats=None, guestHost="Nomad Hub", externalUrl="https://example.com/x")
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=paid).json()
    p = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=party).json()
    D = tma(70)
    login(c, 70, "dmp")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 70")
    assert c.post(f"/api/registry/orgs/{oid}/official", headers=D, json={"on": False}).json()["official"] is False
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'club_unofficial'").fetchall()
    assert len(told) == 1 and bot._render(con, told[0])[2] == f"cl_{oid}"
    assert c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**paid, "price": 3000}).status_code == 403
    assert c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**paid, "price": None}).json()["price"] is None
    assert c.patch(f"/api/events/{p['id']}", headers=tma(20), json={**party, "guestHost": "Other Hub"}).status_code == 403
    assert c.patch(f"/api/events/{p['id']}", headers=tma(20), json={**party, "guestHost": None}).status_code == 200
    c.post(f"/api/registry/orgs/{oid}/official", headers=D, json={"on": True})
    assert bot._render(con, told[0]) is None  # the ✓ is back before it went out: nothing to say


def test_review_fixes(env):
    """The review's: KBTU's own office (official 0, not a club) is as official; a featured post is for everyone; a
    publish nobody heard keeps the week; the President's message on losing the check mark waits the Undo's minute."""
    c, cfg = env
    con, oid = _club(c, cfg, False)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, can_broadcast) VALUES (90, 'dmp', 'office', 'DMP', 'D', 'crown_3d', 0, 1)")
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], 90, "president", "test")
    e = _publish(c, 90, "DMP day")
    assert e["told"] is True and [r[0]["id"] for r in logic.channel_due(con)] == [e["id"]]
    _publish(c, 90, "DMP day 2")
    assert c.post("/api/orgs/90/posts", headers=tma(20), json={"title": "DMP news", "body": "x"}).status_code == 200
    pid = con.execute("INSERT INTO posts (org_id, author_id, audience, title, body, created_at) VALUES (?, NULL, 'public', 'Featured', 'x', 0)", (oid,)).lastrowid
    seen = lambda: {x["title"] for x in c.get("/api/posts", headers=tma(31), params={"scope": "all"}).json()}  # noqa: E731
    assert seen() == {"DMP news"}
    con.execute("UPDATE posts SET featured_until = ? WHERE id = ?", (logic.core.now() + 3600, pid))
    assert seen() == {"DMP news", "Featured"}
    # nobody to tell: the week isn't spent
    lone = logic.create_org(con, None, "Lonely", "LO", "crown_3d", False)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], lone, "president", "test")
    assert _publish(c, lone, "A")["told"] is True and _publish(c, lone, "B")["told"] is True
    # a club told before the meta key existed (the deploy): its last public event still counts, every time
    old = logic.create_org(con, None, "Older", "OL", "crown_3d", False)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], old, "president", "test")
    c.put(f"/api/orgs/{old}/subscription", headers=tma(30))
    _publish(c, old, "Then")
    con.execute("DELETE FROM meta WHERE key = ?", (f"told:{old}",))
    assert _publish(c, old, "Now")["told"] is False and _publish(c, old, "Again")["told"] is False
    off = logic.create_org(con, None, "Ticked", "TI", "crown_3d", True)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], off, "president", "test")
    login(c, 70, "dmp"); con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 70")
    c.post(f"/api/registry/orgs/{off}/official", headers=tma(70), json={"on": False})
    assert con.execute("SELECT send_after FROM bot_outbox WHERE kind = 'club_unofficial'").fetchone()[0] >= logic.core.now() + 50


def test_old_abbr_cleaned_at_start(env):
    """A short form typed before the rule ("JCC_KBTU") is cut to what the rule allows when the app starts; a good one stays."""
    from kbtu import db, logic
    c, cfg = env
    con = db.connect(cfg.db_path)
    a = logic.create_org(con, None, "Japanese Culture", "JC", "crown_3d", False)
    b = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    con.execute("UPDATE orgs SET abbr = 'JCC_KBTU' WHERE id = ?", (a,))
    con.execute("UPDATE orgs SET abbr = 'CHS' WHERE id = ?", (b,))
    logic.clubs.fill_abbrs(con)
    assert [r[0] for r in con.execute("SELECT abbr FROM orgs WHERE id IN (?, ?) ORDER BY id", (a, b))] == ["JCC", "CHS"]
