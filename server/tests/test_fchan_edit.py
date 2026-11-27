"""Editing my own forum channel post (fchannel.edit_*, tgc.post_tick): the same gates and AI look as a new post; its
yes edits the channel message in place (comments and hearts stay); a refusal leaves the live post as it was; a doubt
or an anonymous post with photos waits for a moderator; the pace counts an edit as a post; nobody else edits it; a
take-down drops a waiting edit; an anonymous post stays anonymous all the way."""
from __future__ import annotations

import json
import time

import httpx

from kbtu import db
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import CH, setup, tick
from test_fchannel_photos import TG, mods, upload
from test_tgcomments import Telegram


def _live(c, cfg, con, tg, uid: int, body: str, **extra) -> int:
    p = c.post("/api/forum-posts", headers=tma(uid), json={"body": body, **extra}).json()
    assert p["status"] == "live", p
    tick(cfg, tg, con)
    return p["id"]


def _card(c, uid: int, pid: int) -> dict:
    return c.get(f"/api/forum-posts/feed/post/{pid}", headers=tma(uid)).json()


def test_edit_in_place_keeps_comments_and_hearts(env, monkeypatch):
    c, cfg, said, seen = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    tg = Telegram()
    pid = _live(c, cfg, con, tg, 1, "Lost a black umbrella in the library")
    msg = con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0]
    assert c.put(f"/api/forum-posts/{pid}/heart", headers=tma(2), json={"hearted": True}).status_code == 200
    con.execute("UPDATE fchan_posts SET comments = 3 WHERE id = ?", (pid,))
    # nobody else's, and not the same words, nor the rules a new post has
    assert c.post(f"/api/forum-posts/{pid}/edit", headers=tma(2), json={"body": "Hijacked words of someone else"}).status_code == 404
    assert c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Lost a black umbrella in the library"}).json()["message"] == "same"
    assert c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "see kbtu.kz now"}).json()["message"] == "links"
    n = len(seen)
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Lost a black umbrella in the library, room 301"})
    assert r.status_code == 200 and r.json()["state"] == "done", r.text
    assert seen[n:] == ["Lost a black umbrella in the library, room 301"]                     # the same AI look
    card = _card(c, 2, pid)
    assert card["body"].endswith("room 301") and card["edited"] and card["hearts"] == 1 and card["comments"] == 3
    assert "edit" not in card
    tick(cfg, tg, con)
    ed = tg.of("editMessageText")
    assert len(ed) == 1 and ed[0]["message_id"] == msg and ed[0]["chat_id"] == CH
    assert ed[0]["text"] == "Lost a black umbrella in the library, room 301\n\n<i>— Ann T</i>"
    assert not tg.of("sendMessage")[1:] and not tg.of("deleteMessage")                         # the same message, never anew
    assert tuple(con.execute("SELECT tg_msg, edit_sync FROM fchan_posts WHERE id = ?", (pid,)).fetchone()) == (msg, None)
    tick(cfg, tg, con)
    assert len(tg.of("editMessageText")) == 1                                                  # once
    con.close()


def test_refusal_leaves_the_post_and_doubt_waits(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = Telegram()
    pid = _live(c, cfg, con, tg, 1, "Selling nothing, just saying hello")
    # an ad: refused, said, the live post as it was, nothing to the channel
    said["word"] = "ad"
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Buy my course, cheap and fast"})
    assert r.status_code == 400 and r.json()["message"] == "ad"
    assert _card(c, 1, pid)["body"] == "Selling nothing, just saying hello" and not _card(c, 1, pid)["edited"]
    tick(cfg, tg, con)
    assert not tg.of("editMessageText")
    # harmless first, then aimed at a person: a moderator first, the channel keeps the old words meanwhile
    said["word"] = "person"
    set_clock(monkeypatch, lambda: int(time.time()) + 700)                                      # past the pace
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Dana from 3rd year is a thief"})
    assert r.status_code == 200 and r.json()["state"] == "held"
    mine = _card(c, 1, pid)
    assert mine["body"] == "Selling nothing, just saying hello" and mine["edit"] == "held"
    assert "edit" not in _card(c, 4, pid)                                                       # to me alone
    tick(cfg, tg, con)
    assert not tg.of("editMessageText")
    q = c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"]
    assert len(q) == 1 and q[0]["id"] == pid and q[0]["body"].startswith("Dana") and q[0]["edit"]["was"].startswith("Selling")
    assert any(x["key"] == f"fpost:e{q[0]['edit']['id']}" for x in c.get("/api/admin/inbox", headers=tma(4)).json()["items"])
    # never by its author; declined: the post as it was
    assert c.post(f"/api/forum-edits/{q[0]['edit']['id']}/mod", headers=tma(1), json={"ok": True}).status_code == 403
    assert c.post(f"/api/forum-edits/{q[0]['edit']['id']}/mod", headers=tma(4), json={"ok": False}).status_code == 204
    assert _card(c, 1, pid)["edit"] == "declined" and _card(c, 1, pid)["body"].startswith("Selling")
    assert c.post(f"/api/forum-edits/{q[0]['edit']['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 409   # decided
    tick(cfg, tg, con)
    assert not tg.of("editMessageText")
    con.close()


def test_pace_counts_edits(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    tg = Telegram()
    pid = _live(c, cfg, con, tg, 1, "First words of a quiet morning")
    assert c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Second words of a quiet morning"}).json()["state"] == "done"
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Third words of a quiet morning"})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"                          # a post and an edit: two in ten minutes
    assert c.post("/api/forum-posts", headers=tma(1), json={"body": "Another post right away here"}).status_code == 429
    con.close()


def test_anonymous_edit_with_photos_waits_and_stays_anonymous(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = TG()
    a, b = upload(c, 1), upload(c, 1)
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Guess where this is on campus", "anon": True, "photos": [a["id"], b["id"]]}).json()
    assert c.post(f"/api/forum-posts/{p['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    tick(cfg, tg, con)
    msgs = [r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ? ORDER BY n", (p["id"],))]
    sign = json.loads(tg.of("sendMediaGroup")[0]["media"])[0]["caption"].rsplit("— ", 1)[1]
    mine = _card(c, 1, p["id"])
    assert [x["id"] for x in mine["photos"]] == [a["id"], b["id"]]                              # ids on my own card alone
    assert all("id" not in x for x in _card(c, 4, p["id"])["photos"])
    set_clock(monkeypatch, lambda: int(time.time()) + 700)
    new = upload(c, 1)
    # the album's size stays (one for one); someone else's upload never
    assert c.post(f"/api/forum-posts/{p['id']}/edit", headers=tma(1), json={"body": "Guess again", "photos": [a["id"]]}).json()["message"] == "photos"
    r = c.post(f"/api/forum-posts/{p['id']}/edit", headers=tma(1), json={"body": "Guess where this is, a hint: near the atrium", "photos": [a["id"], new["id"]]})
    assert r.status_code == 200 and r.json()["state"] == "held"                                 # the AI can't judge pictures
    row = con.execute("SELECT user_id, edit_id, post_id FROM fchan_photos WHERE id = ?", (new["id"],)).fetchone()
    assert row[0] is None and row[1] and row[2] is None                                         # no user id on it while it waits
    assert "user_id" not in [d[1] for d in con.execute("PRAGMA table_info(fchan_edits)")]
    q = c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"]
    assert q[0]["author"] is None and q[0]["anon"] and len(q[0]["photos"]) == 2
    assert c.post(f"/api/forum-edits/{q[0]['edit']['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    tick(cfg, tg, con)
    media = tg.of("editMessageMedia")
    assert [m["message_id"] for m in media] == [str(msgs[1])]                                   # only the changed slot
    cap = tg.of("editMessageCaption")
    assert len(cap) == 1 and cap[0]["message_id"] == msgs[0] and cap[0]["caption"].endswith("— " + sign)  # the same mask
    assert [r[0] for r in con.execute("SELECT id FROM fchan_photos WHERE post_id = ? ORDER BY n", (p["id"],))] == [a["id"], new["id"]]
    assert not con.execute("SELECT 1 FROM fchan_photos WHERE id = ?", (b["id"],)).fetchone()   # the replaced one gone
    con.close()


def test_take_down_drops_a_waiting_edit(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = Telegram()
    pid = _live(c, cfg, con, tg, 1, "A calm post about the library")
    said["word"] = "flag"
    assert c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Something the AI is unsure of"}).json()["state"] == "held"
    eid = c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"][0]["edit"]["id"]
    assert c.post(f"/api/forum-posts/{pid}/mod", headers=tma(4), json={"ok": False}).status_code == 204
    assert not c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"]
    assert c.post(f"/api/forum-edits/{eid}/mod", headers=tma(4), json={"ok": True}).status_code in (404, 409)
    assert tuple(con.execute("SELECT status, body FROM fchan_edits WHERE id = ?", (eid,)).fetchone()) == ("gone", "")
    con.close()


def test_photo_swap_on_a_reported_post_waits(env, monkeypatch):
    """A named post's new photo goes on the AI's yes to the words, unless someone reported the post: then a moderator
    looks (a swap under a report, then back after a keep, would pass nobody); a keep from before an edit no longer
    shields the post from the reports' auto-hide."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob"), login(c, 3, "cat")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = TG()
    ph = upload(c, 1)
    pid = _live(c, cfg, con, tg, 1, "Found this umbrella in the library", photos=[ph["id"]])
    assert c.post("/api/reports", headers=tma(2), json={"target": "fpost", "id": pid, "reason": "spam"}).status_code in (200, 204)
    con.execute("UPDATE reports SET status = 'dismissed', resolved_at = ? WHERE target = 'fpost' AND target_id = ?", (int(time.time()) - 5, pid))
    set_clock(monkeypatch, lambda: int(time.time()) + 700)
    new = upload(c, 1)
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Found this umbrella in the library", "photos": [new["id"]]})
    assert r.status_code == 200 and r.json()["state"] == "held"
    eid = c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"][0]["edit"]["id"]
    assert c.post(f"/api/forum-edits/{eid}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    # the keep was before this edit: two reports now take it out again
    for uid in (2, 3):
        c.post("/api/reports", headers=tma(uid), json={"target": "fpost", "id": pid, "reason": "spam"})
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0] == "hidden"
    con.close()


def test_word_swap_on_a_reported_post_waits_and_the_reported_words_stay(env, monkeypatch):
    """Under a report any edit goes to a moderator, words alone too (swapped to harmless words before the decision and
    back after, it would pass nobody); the report keeps the words it was made on for the moderator, until its decision."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = Telegram()
    pid = _live(c, cfg, con, tg, 1, "Something rude about the dean office")
    assert c.post("/api/reports", headers=tma(2), json={"target": "fpost", "id": pid, "reason": "insult"}).status_code in (200, 204)
    set_clock(monkeypatch, lambda: int(time.time()) + 700)
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "A kind word about the library"})
    assert r.status_code == 200 and r.json()["state"] == "held"
    q = c.get("/api/forum-posts/mod", headers=tma(4)).json()["edits"]
    assert q[0]["why"] == "reported" and q[0]["edit"]["was"].startswith("Something rude")
    rep = next(x for x in c.get("/api/admin/reports", headers=tma(4)).json() if x["target"] == "fpost")
    assert rep["was"] is None                                                                   # not edited yet
    assert c.post(f"/api/forum-edits/{q[0]['edit']['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    rep = next(x for x in c.get("/api/admin/reports", headers=tma(4)).json() if x["target"] == "fpost")
    assert rep["text"] == "A kind word about the library" and rep["was"] == "Something rude about the dean office"
    assert c.post(f"/api/admin/reports/fpost/{pid}", headers=tma(4), json={"remove": False}).status_code == 204
    assert con.execute("SELECT body FROM reports WHERE target = 'fpost' AND target_id = ?", (pid,)).fetchone()[0] is None  # gone at the decision
    con.close()


def test_refused_photo_edit_goes_to_a_moderator(env, monkeypatch):
    """Telegram refuses an edited photo for good (400): the channel would keep a picture the post no longer has, so the
    post leaves the channel and waits as a refused send; a release sends it anew."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    mods(c, con)

    class No(TG):
        def __call__(self, request):
            if request.url.path.endswith("/editMessageMedia"):
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "wrong file"})
            return super().__call__(request)
    tg = No()
    ph = upload(c, 1)
    pid = _live(c, cfg, con, tg, 1, "Found this umbrella in the library", photos=[ph["id"]])
    msgs = {con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0]} | {
        r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ?", (pid,))}
    set_clock(monkeypatch, lambda: int(time.time()) + 700)
    new = upload(c, 1)
    r = c.post(f"/api/forum-posts/{pid}/edit", headers=tma(1), json={"body": "Found this umbrella in the library", "photos": [new["id"]]})
    assert r.status_code == 200 and r.json()["state"] == "done", r.text
    tick(cfg, tg, con)
    assert tuple(con.execute("SELECT status, why, tg_msg, edit_sync FROM fchan_posts WHERE id = ?", (pid,)).fetchone()) == ("held", "tgno", None, None)
    tick(cfg, tg, con)
    assert {d["message_id"] for d in tg.of("deleteMessage") if d["chat_id"] == CH} >= msgs          # out of the channel
    held = c.get("/api/forum-posts/mod", headers=tma(4)).json()["held"]
    assert [p["why"] for p in held if p["id"] == pid] == ["tgno"]
    assert c.post(f"/api/forum-posts/{pid}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    tick(cfg, tg, con)
    assert con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[0] not in (None, 0, *msgs)  # sent anew
    con.close()
