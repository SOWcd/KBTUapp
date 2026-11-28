"""The Forum's next step (server side): reactions (one emoji per student per post), polls (a moderator's yes, a final
vote stored apart from the voter, bars once POLL_SHOWN voted or it closed) and the Friday digest (counts only, off
until the owner's yes). Telegram and the AI are mocked."""
from __future__ import annotations

import json

from kbtu import db, logic, outbox, texts
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_fchannel import CH, setup, tick
from test_tgcomments import Telegram

F = logic.fchannel
HEART, LAUGH, FIRE = "❤️", "\U0001f602", "\U0001f525"
POLL = {"body": "Which exam week works best?", "poll": {"options": ["The first", "The second", "Either"], "days": 3}}


def test_reactions_one_per_student_counts_only(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    for i, name in [(1, "ann"), (2, "bob"), (3, "cat")]:
        login(c, i, name)
    con = db.connect(cfg.db_path)
    pid = c.post("/api/forum-posts", headers=tma(1), json={"body": "Studying in the library", "anon": True}).json()["id"]
    con.execute("UPDATE fchan_posts SET tg_msg = 50 WHERE id = ?", (pid,))
    react = lambda who, e: c.put(f"/api/forum-posts/{pid}/react", headers=tma(who), json={"emoji": e})  # noqa: E731
    assert react(2, "\U0001f44d").status_code == 400                                     # not in the set
    assert react(2, LAUGH).json() == {"picks": [{"emoji": LAUGH, "n": 1}], "pick": LAUGH, "hearts": 1, "hearted": True}
    assert react(2, FIRE).json()["picks"] == [{"emoji": FIRE, "n": 1}]                   # another replaces mine
    assert react(1, "❤").json()["pick"] == HEART                                     # the author too (anonymous: no tell); the bare heart is the heart
    got = react(3, FIRE).json()
    assert got["picks"] == [{"emoji": HEART, "n": 1}, {"emoji": FIRE, "n": 2}] and got["pick"] == FIRE  # the set's order
    card = c.get("/api/forum-posts/feed", headers=tma(2)).json()[0]
    assert card["picks"] == got["picks"] and card["pick"] == FIRE and card["hearts"] == 3 and "who" not in json.dumps(card)
    # a build before reactions: its heart keeps my pick, off takes it back
    assert c.put(f"/api/forum-posts/{pid}/heart", headers=tma(3), json={"hearted": True}).json() == {"hearts": 3, "hearted": True}
    assert con.execute("SELECT emoji FROM fchan_hearts WHERE post_id = ? AND user_id = (SELECT id FROM users WHERE tg_id = 3)", (pid,)).fetchone()[0] == FIRE
    assert c.put(f"/api/forum-posts/{pid}/heart", headers=tma(3), json={"hearted": False}).json() == {"hearts": 2, "hearted": False}
    assert react(2, None).json()["pick"] is None
    delete_now(c, cfg, tma(1))                                                             # the author's account goes: so do their reactions
    assert con.execute("SELECT COUNT(*) FROM fchan_hearts").fetchone()[0] == 0
    con.close()


def test_poll_waits_for_a_moderator_then_votes_stay_apart_from_voters(env, monkeypatch):
    c, cfg, said, seen = setup(env, monkeypatch)
    ids = {i: login(c, i, f"s{i}")["id"] for i in range(1, 9)}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (ids[8],))
    for bad in ({"options": ["Only one"], "days": 3}, {"options": ["A", "a"], "days": 3}, {"options": ["A", "B"], "days": 2},
                {"options": ["A", "see kbtu.kz"], "days": 1}, {"options": ["A", "B" * 81], "days": 1}):
        assert c.post("/api/forum-posts", headers=tma(1), json={"body": "Which one is it?", "poll": bad}).status_code == 400, bad
    assert not seen
    p = c.post("/api/forum-posts", headers=tma(1), json=POLL | {"anon": True}).json()
    assert p["status"] == "held"                                                          # the AI's yes: still a moderator's
    assert seen[-1] == "Which exam week works best?\n\n▫️ The first\n▫️ The second\n▫️ Either"
    r = c.post("/api/forum-posts", headers=tma(1), json=POLL | {"body": "Another question here?"})
    assert r.status_code == 429 and r.json()["message"] == "polls"                        # one a day
    q = c.get("/api/forum-posts/mod", headers=tma(8)).json()["held"]
    assert q[0]["poll"] == {"options": ["The first", "The second", "Either"], "days": 3} and q[0]["author"] is None
    assert c.post(f"/api/forum-posts/{p['id']}/mod", headers=tma(8), json={"ok": True}).status_code == 204
    tg = Telegram()
    tick(cfg, tg, con)
    r = c.post(f"/api/forum-posts/{p['id']}/edit", headers=tma(1), json={"body": "Which exam week works for you?"})
    assert r.status_code == 400 and r.json()["message"] == "poll"                         # the votes were given to these words
    nick = texts.nick(*con.execute("SELECT nick_a, nick_n FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone())
    assert tg.of("sendMessage")[0]["chat_id"] == CH
    assert tg.of("sendMessage")[0]["text"] == f"{seen[-1]}\n\n<i>— {nick}</i>"
    closes = con.execute("SELECT closes_at FROM fchan_polls WHERE post_id = ?", (p["id"],)).fetchone()[0]
    assert closes == con.execute("SELECT posted_at FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0] + 3 * 86400
    vote = lambda who, n: c.put(f"/api/forum-posts/{p['id']}/vote", headers=tma(who), json={"choice": n})  # noqa: E731
    assert vote(2, 3).status_code == 400                                                  # no fourth option
    first = vote(2, 1).json()
    assert first["voted"] and first["total"] == 1 and first["counts"] is None             # fewer than POLL_SHOWN: the total only
    assert vote(2, 0).status_code == 409                                                  # final
    for who in (3, 4, 5):
        vote(who, 0)
    assert vote(1, 2).json()["counts"] == [3, 1, 1]                                       # the fifth vote: the bars (the author voted like anyone)
    card = lambda who: next(x for x in c.get("/api/forum-posts/feed", headers=tma(who)).json() if x["id"] == p["id"])["poll"]  # noqa: E731
    assert card(6) == {"options": ["The first", "The second", "Either"], "days": 3, "closes": closes, "closed": False,
                       "voted": False, "total": 5, "counts": None}                        # not voted: no bars
    # nothing ties a choice to a voter: who voted, and the counts, in two tables
    assert {r[0] for r in con.execute("SELECT user_id FROM fchan_voted")} == {ids[i] for i in (1, 2, 3, 4, 5)}
    assert [tuple(r) for r in con.execute("SELECT choice, n FROM fchan_tally ORDER BY choice")] == [(0, 3), (1, 1), (2, 1)]
    delete_now(c, cfg, tma(2))                                                             # a voter goes: the count stays, the mark goes
    assert con.execute("SELECT COUNT(*) FROM fchan_voted").fetchone()[0] == 4
    set_clock(monkeypatch, lambda: closes)
    assert vote(6, 0).status_code == 409                                                  # closed
    assert card(6)["counts"] == [3, 1, 1] and card(6)["closed"]                           # everyone sees the end
    # reported: the moderators read the options too
    assert c.post("/api/reports", headers=tma(6), json={"target": "fpost", "id": p["id"], "reason": "spam"}).status_code == 204
    rep = [x for x in c.get("/api/admin/reports", headers=tma(8)).json() if x["target"] == "fpost"]
    assert len(rep) == 1 and rep[0]["text"] == seen[-1]
    # the author deletes it: options, votes and counts go with the words
    assert c.delete(f"/api/forum-posts/{p['id']}", headers=tma(1)).status_code == 204
    assert con.execute("SELECT options FROM fchan_polls").fetchone()[0] == "[]"
    assert not con.execute("SELECT 1 FROM fchan_voted UNION ALL SELECT 1 FROM fchan_tally").fetchone()
    con.close()


def test_refused_poll_is_not_appealed_and_restore_keeps_its_close(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch, verdict="ad")
    ann = login(c, 1, "ann")["id"]
    con = db.connect(cfg.db_path)
    r = c.post("/api/forum-posts", headers=tma(1), json=POLL)
    assert r.status_code == 400 and r.json()["message"] == "ad" and r.json()["appeal"] is False
    pid = r.json()["post"]
    assert con.execute("SELECT options FROM fchan_polls WHERE post_id = ?", (pid,)).fetchone()[0] == "[]"  # wiped with the words
    assert c.post(f"/api/forum-posts/{pid}/appeal", headers=tma(1), json={"body": POLL["body"]}).status_code == 404
    # closes_at is written once: sent again later (a restore, a republish), the poll doesn't reopen
    con.execute("INSERT INTO fchan_posts (id, user_id, body, status, tg_msg, created_at) VALUES (900, ?, 'Old poll here?', 'live', 0, 0)", (ann,))
    con.execute("INSERT INTO fchan_polls (post_id, options, days, closes_at) VALUES (900, '[\"A\", \"B\"]', 1, 1000)")
    F.sent(con, 900, 77)
    assert con.execute("SELECT closes_at FROM fchan_polls WHERE post_id = 900").fetchone()[0] == 1000
    con.close()


def test_digest_counts_only_once_on_friday_after_the_owners_yes(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    a, b, mute = (login(c, i, n)["id"] for i, n in [(1, "ann"), (2, "bob"), (3, "cat")])
    con = db.connect(cfg.db_path)
    friday = 2_000_000_000 - (2_000_000_000 + logic.core.TZ) % (7 * 86400) + 1 * 86400 + 18 * 3600  # a Friday 18:00 Almaty
    assert (friday + logic.core.TZ) // 86400 % 7 == 1 and (friday + logic.core.TZ) % 86400 == 18 * 3600
    set_clock(monkeypatch, lambda: friday)
    con.execute("INSERT INTO fchan_posts (id, user_id, body, status, tg_msg, created_at, posted_at) VALUES (1, ?, 'A post', 'live', 40, ?, ?)", (a, friday, friday))
    con.execute("UPDATE users SET forum_seen_msg = 40 WHERE id = ?", (b,))                # bob read everything: nothing for him
    con.execute("UPDATE users SET n_forum_digest = 0 WHERE id = ?", (mute,))
    con.execute("UPDATE users SET can_dm = 1")
    F.digest_week(con)
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'forum_week'").fetchone()  # off until the owner's yes
    con.execute("INSERT INTO meta (key, value) VALUES (?, 'on')", (F.DIGEST,))
    F.digest_week(con)
    F.digest_week(con)                                                                    # once a week
    got = [tuple(r) for r in con.execute("SELECT user_id, ref, payload FROM bot_outbox WHERE kind = 'forum_week'")]
    day = (friday + logic.core.TZ) // 86400
    assert got == [(a, f"fw:{day}", json.dumps({"posts": 1, "polls": 0}))]
    row = {"kind": "forum_week", "ref": f"fw:{day}", "lang": "en", "payload": got[0][2], "user_id": a}
    text, button, start = outbox._render(con, row)
    assert text == texts.bot_message("en", "forum_week", posts=1, polls=0)[0] and start == "fp" and text.startswith("\U0001f5de")
    set_clock(monkeypatch, lambda: friday + 2 * 86400)
    assert outbox._render(con, row) is None                                               # missed its Saturday: never late
    con.close()
