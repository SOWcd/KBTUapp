"""A transient database lock retries one update; a permanent failure must not block everyone after it."""
import json
import sqlite3

import pytest

from kbtu import bot_dm, db, logic
from helpers import env  # noqa: F401
from test_stars import Telegram, hear, payment, tap


@pytest.mark.parametrize("handler", ["appchats", "chatsync", "stars"])
@pytest.mark.parametrize("error, retry", [
    (sqlite3.OperationalError("database is locked"), True),
    (sqlite3.OperationalError("database is busy"), True),
    (sqlite3.OperationalError("database or disk is full"), False),
    (sqlite3.OperationalError("no such table: busy"), False),
    (sqlite3.IntegrityError("constraint failed: busy"), False),
])
def test_database_error_does_not_replay_forever(env, monkeypatch, caplog, handler, error, retry):
    _, cfg = env
    con = db.connect(cfg.db_path)
    tapped = []

    async def on_tap(_cfg, _http, _con, q, *_):
        tapped.append(q["id"])

    def broken(*_):
        raise error

    monkeypatch.setattr(bot_dm, "_tapped", on_tap)
    module, name = {"appchats": (logic.appchats, "heard"), "chatsync": (logic.chatsync, "member_update"),
                    "stars": (logic.stars, "paid")}[handler]
    real = getattr(module, name)
    monkeypatch.setattr(module, name, broken)
    update = payment(6) if handler == "stars" else {
        "update_id": 6, "chat_member": {"chat": {"id": -100500}, "date": 1,
                                       "new_chat_member": {"status": "member", "user": {"id": 900}}}}
    batch = [tap(5), update, tap(7)]
    assert hear(cfg, Telegram(batch, [])) == (6 if retry else 8)
    assert tapped == (["5"] if retry else ["5", "7"])
    state = json.loads(con.execute("SELECT value FROM meta WHERE key = 'bot_offset'").fetchone()[0])
    assert state["next"] == (6 if retry else 8) and bool(state.get("busy")) == retry
    assert f"{'stars paid' if handler == 'stars' else 'chat sync'}: {type(error).__name__}" in caplog.text
    if handler == "stars":
        assert con.execute("SELECT count(*) FROM star_gifts").fetchone()[0] == 0

    if retry:
        monkeypatch.setattr(module, name, real)
        assert hear(cfg, Telegram(batch[1:], [])) == 8
        assert tapped == ["5", "7"]
        if handler == "stars":
            assert hear(cfg, Telegram([update], [])) == 7
            assert con.execute("SELECT count(*) FROM star_gifts WHERE charge_id = 'c1'").fetchone()[0] == 1
    con.close()
