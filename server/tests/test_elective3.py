"""The owner's one-off (Nov 7): the incubator's elective post to the 3rd years (admin announce3), "more like it?" Yes/No."""
from __future__ import annotations

import asyncio
import json

import httpx

from kbtu import admin, bot, config, db, texts
from test_core import env, login  # noqa: F401  (env: the fixture)


def test_announce3(env, monkeypatch, capsys):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    ids = {n: login(c, tg, n)["id"] for tg, n in ((30, "ann"), (31, "ben"), (32, "cat"), (33, "dan"))}
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("UPDATE students SET course = 3 WHERE user_id != ?", (ids["dan"],))   # dan: 2nd year
    con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (ids["ben"],))           # ben: the bot can't write
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids["cat"],))        # cat: banned
    queued = lambda: [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'elective3'")]  # noqa: E731
    admin.main(["announce3"])                                                        # dry run: counts, queues nothing
    assert "1 (dry run" in capsys.readouterr().out and queued() == []
    admin.main(["announce3", "--send"])
    admin.main(["announce3", "--send"])                                              # a rerun: nobody again
    assert queued() == [ids["ann"]] and ": 0 (queued)" in capsys.readouterr().out

    calls = []

    def tg(request: httpx.Request) -> httpx.Response:
        method, body = request.url.path.rsplit("/", 1)[1], json.loads(request.content or b"{}")
        calls.append((method, body))
        if method == "forwardMessage":  # a channel the bot isn't in: refused, our gist goes instead
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(tg)) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())
    sent = [(m, b) for m, b in calls if m in ("forwardMessage", "sendMessage") and b.get("chat_id") == 30]
    assert [m for m, _ in sent] == ["forwardMessage", "sendMessage", "sendMessage"]
    assert sent[1][1]["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://t.me/KBTUstartup/2016"
    assert [k["callback_data"] for k in sent[2][1]["reply_markup"]["inline_keyboard"][0]] == ["an:y", "an:n"]
    assert con.execute("SELECT sent_at FROM bot_outbox WHERE kind = 'elective3'").fetchone()[0]

    edits = []

    async def edit(cfg, http, method, body, files=None):
        edits.append(body)
    monkeypatch.setattr(bot, "_tg", edit)

    class Http:
        async def post(self, *a, **k):
            return None
    tap = lambda who, data: asyncio.run(bot._tapped(cfg, Http(), con, {"id": "q", "from": {"id": who}, "data": data,  # noqa: E731
                                                                    "message": {"message_id": 5, "chat": {"id": 30}}}))
    ok = lambda: {r[0]: r[1] for r in con.execute("SELECT id, announce_ok FROM users")}  # noqa: E731
    tap(30, "an:y")
    tap(30, "an:y")                                                                  # idempotent
    assert ok()[ids["ann"]] == 1 and edits[-1]["text"] == texts.bot_message("ru", "announce_yes")[0]
    tap(31, "an:n")      # a forged tap on ann's message: only ben's own answer changes
    assert ok()[ids["ann"]] == 1 and ok()[ids["ben"]] == 0
    tap(30, "an:n")
    assert ok()[ids["ann"]] == 0 and ok()[ids["dan"]] is None
