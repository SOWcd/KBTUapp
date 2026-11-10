"""The forum UI rework's server side (Nov 10, Codex's ranked list): the feed's time is when the post went out, never when
it was written; no commenters' faces under an anonymous post; my held post's why survives a reload (to me alone); the
pace says when I may post again; a refusal gives the photos back for Edit or the appeal."""
from __future__ import annotations

from kbtu import db
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)
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
