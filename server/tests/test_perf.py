"""The performance review's fixes (Nov 2): each one's guard, as small as it can be."""
from __future__ import annotations

import sqlite3
import threading
import time

from kbtu import bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


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
    assert r.headers["cache-control"] == "public, max-age=300, stale-while-revalidate=86400"
    assert c.get("/emoji/party_popper_3d.webp", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    assert c.get("/", headers={"If-None-Match": r.headers["etag"]}).headers["cache-control"] == "no-cache"
    assert c.get("/assets/a.js").headers["cache-control"].endswith("immutable")
    me = c.get("/api/me", headers={**tma(8), "Accept-Encoding": "gzip"})
    assert me.status_code == 200 and (me.headers.get("content-encoding") == "gzip") == (len(me.content) >= 1024)


def test_assets_go_precompressed(env):
    """The build's .br / .gz are sent as they are (no gzip on the loop per client); without them, the file itself."""
    import gzip
    from pathlib import Path
    c, cfg = env
    js = Path(cfg.web_dist) / "assets" / "b.js"
    body = b"export const x = 1;\n" * 200
    js.write_bytes(body)
    js.with_name("b.js.gz").write_bytes(gzip.compress(body))
    js.with_name("b.js.br").write_bytes(b"not-really-brotli")  # its bytes, untouched, tell it apart
    br = c.get("/assets/b.js", headers={"Accept-Encoding": "br"})
    assert br.headers["content-encoding"] == "br" and br.headers["vary"] == "Accept-Encoding"
    assert br.headers["content-type"].startswith("text/javascript") and br.headers["cache-control"].endswith("immutable")
    gz = c.get("/assets/b.js", headers={"Accept-Encoding": "gzip"})
    assert gz.headers["content-encoding"] == "gzip" and gz.content == body  # the client inflates the ready .gz
    plain = c.get("/assets/b.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.content == body
    assert c.get("/assets/b.js", headers={"Accept-Encoding": "br", "If-None-Match": br.headers["etag"]}).status_code == 304


def test_optimize_runs_once_a_night(env, monkeypatch):
    _, cfg = env
    con = db.connect(cfg.db_path)
    assert con.execute("PRAGMA mmap_size").fetchone()[0] > 0
    monkeypatch.setattr(time, "time", lambda: 86400 * 100 + 3600)  # 06:00 Almaty
    q: list[str] = []
    con.set_trace_callback(q.append)
    bot.optimize_day(con)
    bot.optimize_day(con)
    assert sum(s.startswith("PRAGMA optimize") for s in q) == 1


def _plans(con, fn) -> list[tuple[str, str]]:
    q: list[str] = []
    con.set_trace_callback(q.append)
    fn()
    con.set_trace_callback(None)
    return [(s, " | ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + s))) for s in q if s.lstrip().upper().startswith("SELECT")]


def test_hot_reads_use_indexes(env):
    """12: the Afisha, the news feed, a club list's join requests and a check-in's achievement scan search an index:
    no SCAN of the table, no TEMP B-TREE for the order."""
    c, cfg = env
    login(c, 7, "Ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('oo', 'club', 'O', 'O', 'x', 0)")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 7").fetchone()[0]
    v = logic.Viewer(uid, "user", True)
    plans = _plans(con, lambda: (logic.events(con, v), logic.posts(con, v, "all"), logic.orgs(con, v), logic.profiles._counts(con, uid)))
    for table, sql in [("events", "FROM events WHERE starts_at >"), ("posts", "FROM posts WHERE"), ("join_requests", "FROM join_requests WHERE user_id")]:
        found = [p for s, p in plans if sql in s]
        assert found, sql
        assert f"SCAN {table}" not in found[-1] and f"SEARCH {table} USING" in found[-1] and "TEMP B-TREE" not in found[-1], found[-1]


def test_streak_scans_only_my_weeks(env, monkeypatch):
    """7: the streak reads public events from my first check-in's week on (an index range), and counts the same as
    reading every event ever: a busy week before my first check-in changes nothing, one after it breaks the run."""
    c, cfg = env
    login(c, 7, "Ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (900, 'oo', 'club', 'O', 'O', 'x', 0)")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 7").fetchone()[0]
    week = 7 * 86400
    base = (logic.profiles._week(int(time.time())) - 20) * week - 3 * 86400 - 5 * 3600 + 86400  # a Tuesday, 20 weeks ago
    starts = [base - 30 * week, base - week, base, base + week, base + 3 * week, base + 4 * week, base + 6 * week, base + 7 * week, base + 8 * week]
    mine = {base, base + week, base + 4 * week, base + 7 * week, base + 8 * week}
    for i, s in enumerate(starts):
        e = con.execute("INSERT INTO events (org_id, status, title, starts_at, created_at, updated_at) VALUES (900, 'published', 't', ?, 0, 0)", (s,)).lastrowid
        if s in mine:
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at)
                VALUES (?, ?, 'going', ?, ?, 0, 0)""", (e, uid, f"tk{i}", s + 3600))
    every = {logic.profiles._week(r[0]) for r in con.execute("SELECT starts_at FROM events WHERE status = 'published' AND visibility = 'public' AND guest_host IS NULL")}
    want = logic.profiles._streak({logic.profiles._week(t) for t in logic.profiles.attended(con, uid)}, every, logic.profiles._week(logic.core.now()))
    plans = _plans(con, lambda: logic.profiles._counts(con, uid))
    got = logic.profiles._counts(con, uid)
    assert (got["streak"], got["streak_now"]) == want == (2, 2)  # weeks 3 and 6 broke it; the empty weeks since break nothing
    busy = [p for s, p in plans if "SELECT starts_at FROM events" in s]
    assert busy and "SEARCH events USING INDEX" in busy[0] and "starts_at>?" in busy[0], busy


def test_expired_holds_promote_once(env, monkeypatch):
    """11: a GET that saw an expired hold but finds it swept once it holds the lock moves no waitlist again."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    calls = []
    monkeypatch.setattr(logic.seats, "promote", lambda con, e: calls.append(e))
    monkeypatch.setattr(logic.seats, "one", lambda *a: (1,))  # the lock-free look saw an expiry another request swept since
    logic.seats.sweep_holds(con)
    assert not calls and not con.in_transaction


def test_forum_feed_pages_use_message_index(env):
    """Bound both halves before merging: the old visibility, deduplication and cursor order must stay exact."""
    c, cfg = env
    users = [c.get("/api/me", headers=tma(i)).json()["id"] for i in (7, 8)]
    con = db.connect(cfg.db_path)
    with db.tx(con):
        con.executemany("""INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at)
            VALUES (?, 'Synthetic post', 1, ?, ?, 0)""",
            [(users[i % 2], ("live", "held", "hidden", "gone")[i % 4],
              (None, 0, -2, (1 << 62) + 1, (600 - i) // 2)[i % 5]) for i in range(500)])
    for uid in users:
        v = logic.Viewer(uid, "user", False)
        for before in (None, 0, -1, True, 100, 200, 300, 1 << 62, (1 << 62) + 2):
            cursor = before if isinstance(before, int) and before > 0 else (1 << 63) - 1
            want = [r[0] for r in con.execute("""SELECT id FROM fchan_posts
                WHERE (status = 'live' AND tg_msg > 0 OR user_id = ? AND status != 'gone')
                AND COALESCE(NULLIF(tg_msg, 0), 1 << 62) < ?
                ORDER BY COALESCE(NULLIF(tg_msg, 0), 1 << 62) DESC, id DESC LIMIT 50""", (uid, cursor))]
            got = logic.fchannel.feed(con, v, before)
            assert [p["id"] for p in got] == want
            assert all(p["person"] is None for p in got)
    plans = _plans(con, lambda: logic.fchannel.feed(con, v))
    plan = next(p for s, p in plans if "WHERE id IN" in s)
    assert "fchan_posts_by_message (status=? AND tg_msg>? AND tg_msg<?)" in plan, plan
    con.close()


def test_studio_questions_are_counted_once_for_the_list(env):
    """Batch counts preserve lead/club answers, deleted comments, per-reader cutoffs and the host's ownership."""
    c, cfg = env
    users = [login(c, i, name)["id"] for i, name in ((7, "Lead"), (8, "Member"), (9, "Other"))]
    con = db.connect(cfg.db_path)
    with db.tx(con):
        con.executemany("""INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at)
            VALUES (?, ?, 'club', 'Synthetic club', 'S', 'x', 0)""", [(901, "perf1"), (902, "perf2")])
        con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                        [(901, users[0], "head"), (901, users[1], "member"), (902, users[2], "president")])
        for i in range(21):
            eid = con.execute("""INSERT INTO events (org_id, status, title, starts_at, created_at, updated_at)
                VALUES (?, 'published', 'Synthetic event', 1, 0, 0)""", (901 if i < 20 else 902,)).lastrowid
            comments = []
            for uid, as_org, deleted in [(users[1], 0, False), (users[2], 0, False), (users[0], 0, i % 2 == 0),
                                         (users[1], int(i % 3 == 0), i % 5 == 0), (users[2], 0, False),
                                         (users[0] if i % 4 == 0 else users[1], 0, i % 7 == 0)]:
                comments.append(con.execute("""INSERT INTO comments (event_id, user_id, body, as_org, deleted_at, created_at)
                    VALUES (?, ?, 'Synthetic comment', ?, ?, 0)""", (eid, uid, as_org, 1 if deleted else None)).lastrowid)
            if i % 3:
                con.execute("INSERT INTO comment_reads (event_id, user_id, last_id) VALUES (?, ?, ?)",
                            (eid, users[0], comments[1 if i % 2 else 4]))
            if i == 20:
                cohost = eid
                con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, 901, 'accepted', 0)", (eid,))
    v = logic.Viewer(users[0], "user", True)
    want = {r[0]: len(logic.organizing._asking(con, r[0], v.id)) for r in con.execute("SELECT id FROM events WHERE org_id = 901")}
    want[cohost] = 0
    queries = []
    con.set_trace_callback(queries.append)
    got = logic.org_events(con, v, 901)
    con.set_trace_callback(None)
    assert {e["id"]: e["questions"] for e in got} == want
    assert any(want.values())
    assert sum(s.startswith("WITH leads AS") for s in queries) == 1
    assert all(e["questions"] == 0 for e in logic.org_events(con, logic.Viewer(users[1], "user", True), 901))
    con.close()
