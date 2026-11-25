"""The global search's server half (logic/search.more): people only when they made themselves findable, forum channel
posts as the feed shows them, a cap an hour."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_search_more(env, monkeypatch):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True, forum_channel=True)))
    con = db.connect(cfg.db_path)
    ann, bob, cat, mod = (login(c, 140 + i, n)["id"] for i, n in enumerate(("ann", "bob", "cat", "mod")))
    con.execute("UPDATE users SET open_projects = 1 WHERE id IN (?, ?)", (bob, mod))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod,))
    con.execute("UPDATE users SET tg_username = 'cat_tg' WHERE id = ?", (cat,))
    A, M = tma(140), tma(143)
    people = lambda h, q: [x["person"]["id"] for x in c.get("/api/search/more", headers=h, params={"q": q}).json()["people"]]  # noqa: E731

    # a student (the find-people forum isn't open to students yet): nobody by name, open to projects or not
    assert people(A, "Bob") == [] and people(A, "Cat") == []
    # an exact @username finds a student who may be added as a friend, and nobody once they turned that off
    assert people(A, "@cat_tg") == [cat]
    # ... never across a block (either way) or once banned, and not counted as a profile opened then
    for blocker, blocked in ((cat, ann), (ann, cat)):
        con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (blocker, blocked))
        con.execute("DELETE FROM profile_views")
        assert people(A, "@cat_tg") == [] and not con.execute("SELECT 1 FROM profile_views").fetchone()
        con.execute("DELETE FROM blocks")
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (cat,))
    assert people(A, "@cat_tg") == []
    con.execute("UPDATE users SET banned_at = NULL, can_friend = 0 WHERE id = ?", (cat,))
    assert people(A, "@cat_tg") == []
    # the forum open to me (a moderator with FORUM=1): those open to projects by name, never the others, never me
    assert people(M, "Bob") == [bob] and people(M, "Cat") == [] and people(M, "Mod") == []
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (bob, mod))
    assert people(M, "Bob") == []                                                                    # a block hides both ways

    # posts: live ones by their words, an anonymous one without its author; held ones and typos don't come
    for body, status, msg, anon in (("Looking for a calculus tutor", "live", 7, 1), ("Calculus notes anyone", "held", None, 0)):
        con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at) VALUES (?, ?, ?, ?, ?, 0)", (bob, body, anon, status, msg))
    posts = c.get("/api/search/more", headers=A, params={"q": "calculus"}).json()["posts"]
    assert [(p["body"], p["person"]) for p in posts] == [("Looking for a calculus tutor", None)]
    assert c.get("/api/search/more", headers=A, params={"q": "calculsu"}).json()["posts"] == []
    # the channel off: no posts; one letter: nothing asked
    assert TestClient(server.create(cfg)).get("/api/search/more", headers=A, params={"q": "calculus"}).json()["posts"] == []
    assert c.get("/api/search/more", headers=A, params={"q": "c"}).json() == {"people": [], "posts": []}

    # the cap an hour: one counter per person, the past hours' gone
    con.execute("INSERT INTO meta (key, value) VALUES (?, '5')", (f"gsearch:{ann}:1",))
    c.get("/api/search/more", headers=A, params={"q": "calculus"})
    assert not con.execute("SELECT 1 FROM meta WHERE key = ?", (f"gsearch:{ann}:1",)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM meta WHERE key LIKE ?", (f"gsearch:{ann}:%",)).fetchone()[0] == 1
    monkeypatch.setattr(logic.search, "MORE_AN_HOUR", 0)
    assert c.get("/api/search/more", headers=A, params={"q": "calculus"}).status_code == 429
