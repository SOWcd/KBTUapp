"""Ask for help (fchannel.HELP_HOURS): a signed channel post with an "I'm coming" button; who's coming goes to its
author alone; it leaves the feed at its time and the channel with the next round; the list goes with the post and
with a comer's account."""
from __future__ import annotations

from kbtu import db, logic
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import setup


def _card(c, headers, pid):
    return next((x for x in c.get("/api/forum-posts/feed", headers=headers).json() if x["id"] == pid), None)


def test_help_ask_coming_and_expiry(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    a, b, d, guest = tma(1), tma(2), tma(5), tma(3)
    login(c, 1, "ann")
    bob = login(c, 2, "bob")
    login(c, 5, "dan")
    con = db.connect(cfg.db_path)
    body = "Need two people now to cut forms in room 404"
    # signed only; the time is one of the offered
    assert c.post("/api/forum-posts", headers=a, json={"body": body, "anon": True, "help": 3}).status_code == 400
    assert c.post("/api/forum-posts", headers=a, json={"body": body, "help": 2}).status_code == 400
    assert c.post("/api/forum-posts", headers=a, json={"body": body, "help": True}).status_code == 400
    p = c.post("/api/forum-posts", headers=a, json={"body": body, "help": 3}).json()
    pid = p["id"]
    until = con.execute("SELECT help_until - created_at FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0]
    assert until == 3 * 3600
    url = f"/api/forum-posts/{pid}/coming"
    assert c.put(url, headers=b, json={"coming": True}).status_code == 404  # not in the channel yet
    con.execute("UPDATE fchan_posts SET tg_msg = 70 WHERE id = ?", (pid,))
    assert c.put(url, headers=guest, json={"coming": True}).status_code == 401
    assert c.put(url, headers=a, json={"coming": True}).status_code == 400  # not to my own
    assert c.put(url, headers=b, json={"coming": "yes"}).status_code == 400
    for _ in range(2):
        assert c.put(url, headers=b, json={"coming": True}).json() == {"coming": 1, "me": True}
    assert c.put(url, headers=d, json={"coming": True}).json() == {"coming": 2, "me": True}
    # the author sees who, the others how many and their own
    mine = _card(c, a, pid)["help"]
    assert mine["coming"] == 2 and not mine["me"] and {x["id"] for x in mine["who"]} == {bob["id"], con.execute("SELECT id FROM users WHERE tg_id = 5").fetchone()[0]}
    theirs = _card(c, b, pid)["help"]
    assert theirs["coming"] == 2 and theirs["me"] and "who" not in theirs and theirs["until"] == mine["until"]
    assert c.put(url, headers=d, json={"coming": False}).json() == {"coming": 1, "me": False}
    # a comer's account goes: off the list
    delete_now(c, cfg, b)
    assert _card(c, a, pid)["help"]["coming"] == 0
    assert c.put(url, headers=d, json={"coming": True}).status_code == 200
    # time's up: out of everyone's feed at once, and down with the next sweep (out of the channel, the list gone)
    later = logic.core.now() + 3 * 3600 + 1
    set_clock(monkeypatch, lambda: later)
    assert _card(c, a, pid) is None and _card(c, d, pid) is None
    assert c.put(url, headers=d, json={"coming": False}).status_code == 404
    logic.fchannel.expire_help(con)
    assert con.execute("SELECT status, body FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[:] == ("gone", "")
    assert con.execute("SELECT 1 FROM tg_unpost WHERE msg_id = 70").fetchone()
    assert not con.execute("SELECT 1 FROM fchan_coming").fetchone()
    con.close()


def test_expired_ask_not_released_and_author_gone_ends_it(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, verdict="flag")  # held for a moderator
    login(c, 1, "ann"), login(c, 4, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 4")
    pid = c.post("/api/forum-posts", headers=tma(1), json={"body": "Need hands to carry chairs to hall B", "help": 1}).json()["id"]
    con.execute("UPDATE fchan_posts SET help_until = ? WHERE id = ?", (logic.core.now() - 1, pid))
    r = c.post(f"/api/forum-posts/{pid}/mod", headers=tma(4), json={"ok": True})
    assert r.status_code == 409 and con.execute("SELECT status FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0] == "held"
    # a lost send past its time stays for the moderator (it may be in the channel, unmatched)
    con.execute("UPDATE fchan_posts SET why = 'lost' WHERE id = ?", (pid,))
    logic.fchannel.expire_help(con)
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0] == "held"
    # the author's account goes: their live ask ends at once
    said["word"] = "ok"
    live = c.post("/api/forum-posts", headers=tma(1), json={"body": "Anyone free to help sort the books now", "help": 6}).json()["id"]
    con.execute("UPDATE fchan_posts SET tg_msg = 72 WHERE id = ?", (live,))
    delete_now(c, cfg, tma(1))
    assert con.execute("SELECT help_until <= ? FROM fchan_posts WHERE id = ?", (logic.core.now(), live)).fetchone()[0] == 1
    con.close()


def test_block_keeps_the_two_apart(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    a, b, d = tma(1), tma(2), tma(5)
    login(c, 1, "ann")
    bob, dan = login(c, 2, "bob"), login(c, 5, "dan")
    con = db.connect(cfg.db_path)
    pid = c.post("/api/forum-posts", headers=a, json={"body": "Need two people now to cut forms in room 404", "help": 3}).json()["id"]
    con.execute("UPDATE fchan_posts SET tg_msg = 73 WHERE id = ?", (pid,))
    url = f"/api/forum-posts/{pid}/coming"
    assert c.put(url, headers=b, json={"coming": True}).status_code == 200
    # bob blocks ann after coming: off her list of faces (the count stays), and dan is still there
    assert c.post("/api/forum/blocks", headers=b, json={"user": con.execute("SELECT id FROM users WHERE tg_id = 1").fetchone()[0]}).status_code == 204
    assert c.put(url, headers=d, json={"coming": True}).status_code == 200
    mine = _card(c, a, pid)["help"]
    assert mine["coming"] == 2 and [x["id"] for x in mine["who"]] == [dan["id"]]
    # across a block nobody comes anew; taking it back still works
    assert c.put(url, headers=b, json={"coming": False}).json() == {"coming": 1, "me": False}
    assert c.put(url, headers=b, json={"coming": True}).status_code == 404
    assert bob["id"] not in {x["id"] for x in _card(c, a, pid)["help"]["who"]}
    con.close()


def test_expired_ask_not_appealed(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch, "noise")  # refused by the AI
    login(c, 1, "ann")
    body = "zzz test please read this"
    r = c.post("/api/forum-posts", headers=tma(1), json={"body": body, "help": 1})
    assert r.status_code == 400 and r.json()["appeal"] is True
    con = db.connect(cfg.db_path)
    con.execute("UPDATE fchan_posts SET help_until = ? WHERE id = ?", (logic.core.now() - 1, r.json()["post"]))
    # its time is up: no appeal spent on it (the next round would wipe it)
    assert c.post(f"/api/forum-posts/{r.json()['post']}/appeal", headers=tma(1), json={"body": body}).status_code == 409
    assert logic.fchannel.appeals_left(con, con.execute("SELECT id FROM users WHERE tg_id = 1").fetchone()[0]) == logic.fchannel.APPEALS_A_DAY
    con.close()


def test_plain_post_has_no_help(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    pid = c.post("/api/forum-posts", headers=tma(1), json={"body": "Studying in the library tonight"}).json()["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE fchan_posts SET tg_msg = 71 WHERE id = ?", (pid,))
    assert "help" not in _card(c, tma(2), pid)
    assert c.put(f"/api/forum-posts/{pid}/coming", headers=tma(2), json={"coming": True}).status_code == 404
    con.close()
