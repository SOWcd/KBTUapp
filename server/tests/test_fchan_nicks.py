"""An anonymous forum post's random nick (fchannel.pick_nick, Nov 3; .claude/reports/anon-nicks-review.md): drawn with
secrets for anonymous posts alone, fresh across recent posts (one author's too), stable for its post, the channel's
signature and the author's replies' in Russian; posts from before keep "Anon"."""
from __future__ import annotations

import pathlib
import re

from kbtu import logic, texts
from test_core import env, tma  # noqa: F401  (env: the fixture)
from test_fchan_replies import clock, group_sends, world
from test_fchannel import tick

F = logic.fchannel


def nick_of(con, pid: int):
    return tuple(con.execute("SELECT nick_a, nick_n FROM fchan_posts WHERE id = ?", (pid,)).fetchone())


def test_nick_lists_and_app_parity():
    assert len(texts.NICK_ADJ) == len(texts.NICK_NOUN) == 40
    assert all(len(a) == 3 for a in texts.NICK_ADJ) and {g for _, g in texts.NICK_NOUN} == {0, 1, 2}
    assert len({w for w, _ in texts.NICK_NOUN}) == 40 and len({a[0] for a in texts.NICK_ADJ}) == 40
    assert texts.nick(1, 0) == "\u0412\u0435\u0441\u0451\u043b\u0430\u044f \u041b\u0438\u0441\u0430"      # agrees with the noun
    assert texts.nick(0, 39) == "\u0422\u0438\u0445\u043e\u0435 \u042d\u0445\u043e"
    # the app's Russian words are the server's, in the same order (the indexes are the stored nick)
    ts = (pathlib.Path(__file__).parents[2] / "web/src/lib/i18n/nicks.ts").read_text()
    assert [tuple(m) for m in re.findall(r"\[\['([^']+)', '([^']+)', '([^']+)'\]", ts)] == texts.NICK_ADJ
    assert [(w, int(g)) for w, g in re.findall(r"\['([^']+)', ([012]), '", ts)] == texts.NICK_NOUN


def test_nick_anon_only_fresh_and_stable(env, monkeypatch):
    w = world(env, monkeypatch)                                       # Ann's anonymous post, live in the channel
    t = clock(monkeypatch)
    a = nick_of(w.con, w.pid)
    assert a[0] is not None and a[1] is not None
    t[0] += 3600
    named = w.c.post("/api/forum-posts", headers=tma(1), json={"body": "Lost my blue scarf near the library"}).json()
    assert named["nick"] is None and nick_of(w.con, named["id"]) == (None, None)
    t[0] += 3600
    anon = w.c.post("/api/forum-posts", headers=tma(1), json={"body": "Does anyone else hate the new schedule?", "anon": True}).json()
    assert anon["nick"] == list(nick_of(w.con, anon["id"])) != list(a)  # mine: shown to me as it'll be signed
    # many of one author's: never the same nick while recent, whatever the draw (the last NICK_FRESH excluded)
    seen = {tuple(a), tuple(anon["nick"])}
    for _ in range(300):
        n = F.pick_nick(w.con)
        assert n not in seen
        seen.add(n)
        w.con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, created_at, nick_a, nick_n) VALUES (?, 'x x', 1, 'held', 0, ?, ?)", (w.ann["id"], *n))
    # stable: the feed, a second look, the channel send all say the same
    feed = lambda: next(p for p in w.c.get("/api/forum-posts/feed", headers=tma(2)).json() if p["id"] == w.pid)  # noqa: E731
    assert feed()["nick"] == list(a) == feed()["nick"] and feed()["sign"] == texts.nick(*a)
    assert any(b["text"].endswith(f"<i>— {texts.nick(*a)}</i>") for b in w.tg.of("sendMessage"))


def test_nick_reply_signature(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    nick = texts.nick(*nick_of(w.con, w.pid))
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Thanks, all of you"})
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert group_sends(w.tg)[-1]["text"] == f"Thanks, all of you\n\n<i>— \U0001f3ad {nick}</i>"


def test_nick_old_posts_fall_back(env, monkeypatch):
    w = world(env, monkeypatch)
    t = clock(monkeypatch)
    w.con.execute("UPDATE fchan_posts SET nick_a = NULL, nick_n = NULL WHERE id = ?", (w.pid,))  # as one from before nicks
    row = next(p for p in w.c.get("/api/forum-posts/feed", headers=tma(2)).json() if p["id"] == w.pid)
    assert row["nick"] is None and row["sign"] == F.anon_sign(row["body"])
    w.c.post(f"/api/forum-posts/{w.pid}/replies", headers=tma(1), json={"body": "Thanks, all of you"})
    t[0] += 21
    tick(w.cfg, w.tg, w.con)
    assert group_sends(w.tg)[-1]["text"] == f"Thanks, all of you\n\n<i>— {texts.FCH_REPLY_SIGN}</i>"
