"""The forum UI rework's server side (Nov 10, Codex's ranked list): the feed's time is when the post went out, never when
it was written; no commenters' faces under an anonymous post; my held post's why survives a reload (to me alone); the
pace says when I may post again; a refusal gives the photos back for Edit or the appeal."""
from __future__ import annotations

import pytest

from kbtu import db
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import setup, tick
from test_fchannel_photos import TG, upload


def test_public_time_and_no_faces_on_anonymous(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, verdict="flag")
    login(c, 1, "ann"), login(c, 2, "bob"), login(c, 4, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 4")
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "A quiet confession here", "anon": True}).json()
    con.execute("UPDATE fchan_posts SET created_at = 1000 WHERE id = ?", (p["id"],))       # written long ago, held since
    assert c.post(f"/api/forum-posts/{p['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    tick(cfg, TG(), con)
    row = next(x for x in c.get("/api/forum-posts/feed", headers=tma(2)).json() if x["id"] == p["id"])
    out = con.execute("SELECT posted_at FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0]
    assert out > 1000 and row["at"] == out                                                        # when it went out
    # a comment by an app student under it: still no faces (its author's, or its absence, would tell)
    con.execute("UPDATE fchan_posts SET comments = 1 WHERE id = ?", (p["id"],))
    con.execute("INSERT INTO fchan_comments (msg_id, post_id, user_id, at) VALUES (5, ?, 2, 0)", (p["id"],))
    con.execute("UPDATE students SET consent_version = 'staff'")
    row = next(x for x in c.get("/api/forum-posts/feed", headers=tma(4)).json() if x["id"] == p["id"])
    assert row["comments"] == 1 and row["faces"] == []
    con.close()


def test_held_why_kept_and_pace(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, verdict="flag")
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    said["why"] = {"quote": "physics teacher", "reason": "It points at one teacher.", "fix": "Say what happened, not who."}
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Our physics teacher is unfair to us"}).json()
    assert c.post(f"/api/forum-posts/{p['id']}/why", headers=tma(1), json={}).json()["explain"]["fix"]
    # a reload: the feed brings it back, to me alone
    mine = next(x for x in c.get("/api/forum-posts/feed", headers=tma(1)).json() if x["id"] == p["id"])
    assert mine["review"] == {"kind": "ai", "explain": said["why"]}
    assert all("review" not in x for x in c.get("/api/forum-posts/feed", headers=tma(2)).json())
    # an anonymous one with photos: the kind says so
    ph = upload(c, 2)
    said["word"] = "ok"
    q = c.post("/api/forum-posts", headers=tma(2), json={"body": "Look at the new hall here", "anon": True, "photos": [ph["id"]]}).json()
    assert next(x for x in c.get("/api/forum-posts/feed", headers=tma(2)).json() if x["id"] == q["id"])["review"] == {"kind": "photo", "explain": None}
    # the pace: two in ten minutes, then when
    c.post("/api/forum-posts", headers=tma(1), json={"body": "Second post of the evening"})
    assert c.get("/api/forum-posts/revealed", headers=tma(1)).json()["next"] is not None
    r = c.post("/api/forum-posts", headers=tma(1), json={"body": "Third post of the evening"})
    first = con.execute("SELECT MIN(created_at) FROM fchan_posts WHERE user_id = 1").fetchone()[0]
    assert r.status_code == 429 and r.json()["retry"] == first + 600
    con.close()


def test_refusal_gives_photos_back(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, verdict="ad")
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    ph = upload(c, 1)
    r = c.post("/api/forum-posts", headers=tma(1), json={"body": "Selling my old calculator cheap", "photos": [ph["id"]]})
    assert r.status_code == 400
    pid = r.json()["post"]
    assert con.execute("SELECT user_id, post_id FROM fchan_photos WHERE id = ?", (ph["id"],)).fetchone()[:] == (1, None)  # mine again
    # the appeal names it again
    p = c.post(f"/api/forum-posts/{pid}/appeal", headers=tma(1), json={"body": "Selling my old calculator cheap", "photos": [ph["id"]]}).json()
    assert p["status"] == "held" and con.execute("SELECT post_id FROM fchan_photos WHERE id = ?", (ph["id"],)).fetchone()[0] == pid
    con.close()


@pytest.mark.parametrize("anon", [False, True])
def test_hearts_are_private_and_erased(env, monkeypatch, anon):
    c, cfg, _, _ = setup(env, monkeypatch)
    a, b, guest, staff = tma(1), tma(2), tma(3), tma(4)
    login(c, 1, "ann")
    bob = login(c, 2, "bob")
    moderator = login(c, 4, "moderator")
    pid = c.post("/api/forum-posts", headers=a, json={"body": "Studying in the library", "anon": anon}).json()["id"]
    url = f"/api/forum-posts/{pid}/heart"

    def heart(headers, picked):
        return c.put(url, headers=headers, json={"hearted": picked})

    def card(headers):
        return c.get("/api/forum-posts/feed", headers=headers).json()[0]

    con = db.connect(cfg.db_path)
    assert heart(b, True).status_code == 404  # approved, still waiting for the bot
    con.execute("""UPDATE fchan_posts SET tg_msg = 50, reactions = '{"x":7}' WHERE id = ?""", (pid,))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (moderator["id"],))
    outbox = con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0]
    assert heart(guest, True).status_code == 401
    assert heart(b, "false").status_code == 400
    viewers = (a, b, guest, staff)
    before = [card(viewer) for viewer in viewers]
    for _ in range(2):
        assert heart(b, True).json() == {"hearts": 1, "hearted": True}
    for viewer, original in zip(viewers, before):
        assert original["reactions"] == [{"emoji": "x", "n": 7}]
        assert card(viewer) == original | {"hearts": 1, "hearted": viewer == b, "picks": [{"emoji": "❤️", "n": 1}],
                                           "pick": "❤️" if viewer == b else None}
    assert heart(a, True).json() == {"hearts": 2, "hearted": True}
    for _ in range(2):
        assert heart(a, False).json() == {"hearts": 1, "hearted": False}
    con.execute("UPDATE fchan_posts SET status = 'hidden' WHERE id = ?", (pid,))
    assert heart(b, False).status_code == 404
    con.execute("UPDATE fchan_posts SET status = 'live' WHERE id = ?", (pid,))
    assert c.put("/api/forum-posts/visit", headers=b, json={"msg": 50}).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == outbox
    delete_now(c, cfg, b)
    assert con.execute("SELECT forum_seen_msg FROM users WHERE id = ?", (bob["id"],)).fetchone()[0] == 0
    assert card(a)["hearts"] == 0
    assert heart(a, True).status_code == 200
    assert c.delete(f"/api/forum-posts/{pid}", headers=a).status_code == 204
    assert not con.execute("SELECT 1 FROM fchan_hearts").fetchone()
    con.close()


def test_visit_uses_publication_order_and_only_advances_for_me(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    a, b = tma(1), tma(2)
    uid = login(c, 1, "ann")["id"]
    con = db.connect(cfg.db_path)
    con.executemany("""INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at)
        VALUES (?, 'A synthetic post', 0, ?, ?, 1)""", [(uid, "held", None), (uid, "live", 80), (uid, "hidden", 90)])
    url = "/api/forum-posts/visit"
    def visit(headers):
        return c.get(url, headers=headers).json()
    def seen(msg):
        return c.put(url, headers=b, json={"msg": msg}).status_code
    c.get("/api/forum-posts/feed", headers=b)  # a prefetch is not a visit
    assert visit(b) == {"latest": 80, "seen": 0}
    assert seen(90) == 404 and seen(True) == 400
    assert seen(80) == 204
    con.execute("UPDATE fchan_posts SET status = 'live', tg_msg = 100 WHERE status = 'held'")
    assert visit(b) == {"latest": 100, "seen": 80}
    assert seen(100) == seen(80) == 204  # an older tab finishes later
    assert visit(b)["seen"] == 100 and visit(a)["seen"] == 0
    con.close()
