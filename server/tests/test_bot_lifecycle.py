"""The bot's leadership and its nightly copy: a failing child takes its siblings down under the lock; a failed copy retries."""
from __future__ import annotations

import asyncio
import dataclasses
import fcntl
import sqlite3
from pathlib import Path

from kbtu import bot, db
from test_core import env  # noqa: F401  (env: the fixture)


def test_failing_child_cancels_siblings_under_lock(env, monkeypatch):
    _, cfg = env
    lock_path = f"{cfg.db_path}.bot.lock"
    seen = {}

    def held() -> bool:
        with open(lock_path, "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(f, fcntl.LOCK_UN)
            return False

    async def nothing(*_a):
        return None

    async def boom(*_a):
        await asyncio.sleep(0.05)
        raise RuntimeError("postman broke")

    def forever(name):
        async def child(*_a):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                seen[name] = held()
                raise
        return child

    monkeypatch.setattr(bot, "load_pack", nothing)
    monkeypatch.setattr(bot, "_commands", nothing)
    monkeypatch.setattr(bot.receipt, "ready", lambda: True)
    monkeypatch.setattr(bot, "_postman", boom)
    for name in ("_ears", "_videos", "_translator", "_userbot"):
        monkeypatch.setattr(bot, name, forever(name))
    cfg = dataclasses.replace(cfg, chat_sync=False)

    async def main():
        task = asyncio.create_task(bot.run(cfg))
        while len(seen) < 4:
            await asyncio.sleep(0.01)
        task.cancel()  # the shutdown, as the lifespan does it
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(asyncio.wait_for(main(), 10))
    assert seen == {"_ears": True, "_videos": True, "_translator": True, "_userbot": True}  # all cancelled before the lock went
    assert not held()


def test_failed_backup_leaves_no_daily_marker(env, monkeypatch):
    _, cfg = env
    con = db.connect(cfg.db_path)
    monkeypatch.setattr(bot.time, "time", lambda: 20000 * 86400 - 5 * 3600 + 5 * 3600)  # 05:00 Almaty
    monkeypatch.setattr(bot, "_backup_retry", 0.0)

    class Full:  # the disk is full: VACUUM INTO fails, everything else goes through
        def execute(self, sql, *a):
            if sql.startswith("VACUUM"):
                raise sqlite3.OperationalError("database or disk is full")
            return con.execute(sql, *a)
    bot.backup_day(cfg, Full())
    marker = lambda: con.execute("SELECT 1 FROM meta WHERE key = 'backup_day'").fetchone()  # noqa: E731
    assert not marker()
    bot._backup_retry = 0.0  # the hour is over
    bot.backup_day(cfg, con)
    assert marker() and list((Path(cfg.db_path).resolve().parent / "backups").glob("kbtu-*.db"))


def test_offsite_unset_tells_the_creator_once(env, monkeypatch):
    _, cfg = env
    con = db.connect(cfg.db_path)
    monkeypatch.setattr(bot.time, "time", lambda: 20000 * 86400)  # 05:00 Almaty
    monkeypatch.setattr(bot, "_backup_retry", 0.0)
    monkeypatch.setattr(bot.offsite, "ready", lambda: False)
    monkeypatch.setenv("DB_MUST_EXIST", "1")
    con.execute("INSERT INTO users (tg_id, role, is_founder, created_at, seen_at) VALUES (9002, 'admin', 1, 0, 0)")
    bot.backup_day(cfg, con)
    for _ in range(3):
        bot.offsite_round(cfg, con)
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'backup_failed'").fetchone()[0] == 1
