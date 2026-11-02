"""The performance review's fixes (Nov 2): each one's guard, as small as it can be."""
from __future__ import annotations

import sqlite3
import threading

from kbtu import bot, db, logic
from test_core import env, tma  # noqa: F401  (env: the fixture)


def test_outbox_due_uses_its_index(env):
    """5: the postman's due query walks only waiting rows (the partial index), never the failed ones."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    q = []
    con.set_trace_callback(q.append)
    bot._due(con)  # the postman's own query (INDEXED BY fails loudly if it ever stops fitting the index)
    con.set_trace_callback(None)
    plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + q[-1]))
    assert "outbox_todo" in plan and "TEMP B-TREE" not in plan, plan


def test_meta_ranges_use_the_key(env):
    """12: a prefix as a key range searches meta's primary key; LIKE would scan (and `_` would match any letter)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    plan = " ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN SELECT key FROM meta WHERE key >= 'tgcdel:' AND key < 'tgcdel;'"))
    assert "SEARCH" in plan, plan
    con.execute("INSERT INTO meta (key, value) VALUES ('channel_gone:5', 'x'), ('channel_gonf:6', 'y'), ('channel_gone;', 'z')")
    assert logic.channel_gone(con) == [(5, "x")]


def test_best_effort_write_skips_a_busy_lock(env):
    """11: a GET's own write waits 200 ms for the lock, not 15 s; skipped meanwhile, and the GET still answers."""
    c, cfg = env
    assert c.get("/api/me", headers=tma(7)).status_code == 200
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET seen_at = 0")  # the next seen_at check is due
    holder = sqlite3.connect(cfg.db_path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")  # a burst holding the write lock
    ran = []
    assert db.maybe(con, lambda: (con.execute("UPDATE users SET seen_at = 1"), ran.append(1))) is None
    assert not ran and con.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_MS
    t = threading.Thread(target=lambda: c.get("/api/me", headers=tma(7)))
    t.start()
    t.join(5)
    alive = t.is_alive()
    holder.execute("ROLLBACK")
    t.join()
    assert not alive  # answered with the lock still held
    assert db.maybe(con, lambda: 5) == 5


def test_public_files_cache_and_304(env):
    """4 and 9: emoji are kept a day and revalidate to a 304; the page is never cached; big JSON goes gzipped."""
    c, _ = env
    r = c.get("/emoji/party_popper_3d.webp")
    assert r.headers["cache-control"] == "public, max-age=86400, stale-while-revalidate=604800"
    assert c.get("/emoji/party_popper_3d.webp", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert c.get("/", headers={"If-None-Match": r.headers["etag"]}).headers["cache-control"] == "no-cache"
    assert c.get("/assets/a.js").headers["cache-control"].endswith("immutable")
    me = c.get("/api/me", headers={**tma(8), "Accept-Encoding": "gzip"})
    assert me.status_code == 200 and (me.headers.get("content-encoding") == "gzip") == (len(me.content) >= 1024)
