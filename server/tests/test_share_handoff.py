"""Sharing outside the Mini App (a browser, the phone apps): /api/share with handoff holds the server's own card for the
bot (core.share_hold) and answers with the bot's start link; /start sh_<secret> sends that card to the Telegram account
that made it, once, with a button that offers it in inline mode to that account alone; an hour, then gone."""
from __future__ import annotations

from kbtu import bot, db, logic
from test_afisha import OFF, _event, _setup
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)


def _start(con, cfg, tg, arg, lang="en"):
    return bot._welcome(con, cfg, {"chat": {"id": tg, "type": "private"}, "date": logic.now(), "text": f"/start {arg}",
                                   "from": {"id": tg, "language_code": lang}})


def _inline(con, cfg, tg, query):
    return bot.inline_answer(cfg, con, {"id": "q", "from": {"id": tg, "language_code": "en"}, "query": query})


def test_share_handoff(env, monkeypatch):
    c, cfg = env
    ali = login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO achievement_grants (user_id, code, created_at) VALUES (?, 'bugs', 0)", (ali["id"],))
    A = tma(61, "Ali")

    r = c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs", "handoff": True}).json()
    assert set(r) == {"open"} and r["open"].startswith(f"https://t.me/{cfg.bot_username}?start=sh_")
    secret = r["open"].split("start=sh_")[1]
    assert len(secret) == 22 and len("sh_" + secret) <= 64  # Telegram's start parameter: 64 characters at most
    held = con.execute("SELECT value FROM meta WHERE key = ?", (f"share:{secret}",)).fetchone()
    assert held and '"tg": 61' in held[0]

    # someone else's Telegram (a forwarded link): nothing, and the link still works for its maker
    out = _start(con, cfg, 62, "sh_" + secret)
    assert out["text"].startswith("⏳") and "sh_" not in str(out)
    assert _inline(con, cfg, 62, "sh_" + secret)["results"] == []

    # the maker: the card as it will look, one button into Telegram's chat picker carrying the secret
    out = _start(con, cfg, 61, "sh_" + secret)
    assert "\U0001f3c5" in out["text"] and "photo" not in out
    [[button]] = out["reply_markup"]["inline_keyboard"]
    assert button["text"] == "\U0001f4e4 Send to a chat" and button["switch_inline_query_chosen_chat"]["query"] == "sh_" + secret
    assert "url" not in button  # not the card's own button: the giver never claims it by mistake
    # once: the same start again is refused
    assert _start(con, cfg, 61, "sh_" + secret)["text"].startswith("⏳")

    # the Share button's inline query: exactly the card the Mini App would have sent, for the maker alone, never cached
    body = _inline(con, cfg, 61, "sh_" + secret)
    [card] = body["results"]
    assert card["type"] == "article" and card["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=aw_bugs")
    assert body["cache_time"] == 0 and body["is_personal"]
    assert _inline(con, cfg, 61, "sh_" + "x" * 22)["results"] == []          # a made-up secret
    assert _inline(con, cfg, 61, "sh_../" + secret)["results"] == []          # not a secret's shape

    # an event: its photo card, sent as a photo
    _, _, off = _setup(c, cfg)
    ev = _event(c, off, OFF, "Hack night")
    r = c.post("/api/share", headers=A, json={"kind": "ev", "id": ev, "handoff": True}).json()
    out = _start(con, cfg, 61, r["open"].split("start=")[1])
    assert out["photo"].startswith("https://") and "Hack night" in out["caption"]
    assert out["reply_markup"]["inline_keyboard"][0][0]["switch_inline_query_chosen_chat"]["query"].startswith("sh_")

    # an hour later: gone, and the sweep removes it
    later = logic.now() + logic.core.SHARE_TTL + 1
    set_clock(monkeypatch, lambda: later)
    assert _inline(con, cfg, 61, "sh_" + secret)["results"] == []
    logic.ms_sweep(con)
    assert not con.execute("SELECT 1 FROM meta WHERE key = ?", (f"share:{secret}",)).fetchone()

    # a cap an hour: each card may mint a link
    monkeypatch.setattr(logic.core, "SHARE_AN_HOUR", 2)
    for _ in range(2):
        assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs", "handoff": True}).status_code == 200
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs", "handoff": True}).json()["error"] == "rate_limited"

    # the Mini App's own way is unchanged: no handoff, no held card
    n = con.execute("SELECT COUNT(*) FROM meta WHERE key >= 'share:' AND key < 'share;'").fetchone()[0]
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs", "link": True}).json() == {"link": f"https://t.me/{cfg.bot_username}?startapp=aw_bugs"}
    assert con.execute("SELECT COUNT(*) FROM meta WHERE key >= 'share:' AND key < 'share;'").fetchone()[0] == n

    # deleting the account takes the held cards with it
    logic.delete_me(con, logic.Viewer(ali["id"], "user", True))
    assert not con.execute("SELECT 1 FROM meta WHERE key >= 'share:' AND key < 'share;'").fetchone()
