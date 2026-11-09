"""A bare /start@bot in a group: one answer a minute, saying whether the chat is linked to the app."""
from __future__ import annotations

import asyncio
import time

from kbtu import bot, db
from test_core import env  # noqa: F401  (env: the fixture)


def test_group_start_answers(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    sent = []

    async def send(_cfg, _http, body):
        sent.append(body)
    monkeypatch.setattr(bot, "_send", send)
    bot._hello.clear()
    msg = {"chat": {"id": -5}, "text": f"/start@{cfg.bot_username}", "date": int(time.time()), "from": {"id": 1, "language_code": "en"}}
    run = lambda m: asyncio.run(bot._group(cfg, None, con, m))  # noqa: E731
    run(msg); run(msg)
    assert len(sent) == 1 and sent[0]["text"].startswith("\U0001F44B Hi") and sent[0]["chat_id"] == -5
    bot._hello.clear()
    run({**msg, "text": "/start@SomeOtherBot"})
    run({**msg, "date": int(time.time()) - bot.FRESH - 5})
    assert len(sent) == 1
