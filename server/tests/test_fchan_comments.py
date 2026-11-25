"""A signed comment written in the app under a channel post (logic/fchannel.py comment_*, thread): the same AI look,
bot and moderators as an anonymous author's reply, signed with the commenter's short name, shown in the app's thread."""
from __future__ import annotations

from test_core import env, tma  # noqa: F401  (env: the fixture)
from test_fchan_replies import clock, group_sends, tick, world  # noqa: F401


def test_signed_comment_flow(env, monkeypatch):
    w = world(env, monkeypatch)
    clock(monkeypatch)
    r = w.c.post(f"/api/forum-posts/{w.pid}/comments", headers=tma(2), json={"body": "The soup was fine today"}).json()
    assert r.get("state") == "soon", r
    row = w.con.execute("SELECT s.user_id, r.comment_msg FROM fchan_replies r JOIN fchan_signed s ON s.reply_id = r.id WHERE r.id = ?", (r["id"],)).fetchone()
    assert row[0] is not None and row[1] is None                                    # signed: names its commenter, answers the thread
    tick(w.cfg, w.tg, w.con)
    s = group_sends(w.tg)
    assert len(s) == 1 and s[0]["reply_parameters"] == {"message_id": 55} and s[0]["text"].startswith("The soup was fine today\n\n<i>— ")
    assert "\U0001f3ad" not in s[0]["text"]                                         # not the anonymous author's mark
    mine = w.c.get(f"/api/forum-posts/{w.pid}/thread", headers=tma(2)).json()
    assert [(c["body"], c["mine"], c["anon"], c["state"]) for c in mine] == [("The soup was fine today", True, False, "sent")]
    other = w.c.get(f"/api/forum-posts/{w.pid}/thread", headers=tma(1)).json()      # the post's author sees it, not as theirs
    assert other[0]["mine"] is False and other[0]["name"]
    assert w.con.execute("SELECT comments FROM fchan_posts WHERE id = ?", (w.pid,)).fetchone()[0] >= 1


def test_signed_comment_rules(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    post = lambda body, h=tma(2): w.c.post(f"/api/forum-posts/{w.pid}/comments", headers=h, json={"body": body})  # noqa: E731
    assert post("The soup was fine today").status_code == 200
    assert post("Right after, too soon").status_code == 429                         # REPLY_GAP
    t[0] += 61
    for bad in ("see kbtu.kz", "ask @someone", "x"):
        assert post(bad).status_code == 400
    assert post("My own anonymous post", tma(1)).status_code == 409                 # its author answers as the mask


def test_signed_comment_held_and_deleted(env, monkeypatch):
    w = world(env, monkeypatch, word="person")
    clock(monkeypatch)
    r = w.c.post(f"/api/forum-posts/{w.pid}/comments", headers=tma(2), json={"body": "Ask the teacher about it"}).json()
    assert r.get("state") == "held", r
    assert w.c.get(f"/api/forum-posts/{w.pid}/thread", headers=tma(1)).json() == []  # held: only its author sees it
    assert w.c.get(f"/api/forum-posts/{w.pid}/thread", headers=tma(2)).json()[0]["state"] == "held"
    assert w.c.delete(f"/api/forum-replies/{r['id']}", headers=tma(1)).status_code == 404  # not the post's author's to delete
    assert w.c.delete(f"/api/forum-replies/{r['id']}", headers=tma(2)).status_code == 204
    assert w.c.get(f"/api/forum-posts/{w.pid}/thread", headers=tma(2)).json() == []
