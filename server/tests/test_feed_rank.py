"""Forum order and Chief activist through their HTTP entry points."""
from kbtu import db, logic
from test_core import env, login, set_clock, tma  # noqa: F401
from test_fchannel import setup


def test_rank_uses_freshness_hearts_distinct_commenters_and_signed_friends(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    viewer, friend, other = (login(c, i, name)["id"] for i, name in [(1, "ann"), (2, "bob"), (3, "cat")])
    now = 2_000_000_000
    set_clock(monkeypatch, lambda: now)
    con = db.connect(cfg.db_path)
    fixtures = [
        (1, friend, 0, now), (2, other, 0, now), (3, friend, 1, now), (4, other, 1, now),
        (5, other, 0, now - 120 * 3600), (6, other, 0, now), (7, other, 0, now),
    ]
    con.executemany("""INSERT INTO fchan_posts (id, user_id, anon, status, body, tg_msg, created_at, posted_at)
        VALUES (?, ?, ?, 'live', 'Seeded post', 100 + ?, 0, ?)""",
                    [(pid, uid, anon, pid, at) for pid, uid, anon, at in fixtures])
    con.executemany("INSERT INTO fchan_hearts (post_id, user_id) VALUES (?, ?)", [(2, viewer), (2, friend), (5, viewer), (5, friend), (5, other)])
    con.executemany("INSERT INTO fchan_comments VALUES (?, ?, ?, ?, ?)",
                    [(i, 6, friend, now, 0) for i in range(1, 15)] +
                    [(15, 7, friend, now, 0), (16, 7, viewer, now, 0), (17, 6, viewer, now, 1)])
    path = "/api/forum-posts/feed/page"
    first = c.get(path, headers=tma(1)).json()["posts"]
    assert [p["id"] for p in first] == [7, 6, 2, 4, 3, 1, 5]
    con.execute("INSERT INTO friendships VALUES (?, ?, ?)", (viewer, friend, now))
    ranked = c.get(path, headers=tma(1)).json()["posts"]
    assert [p["id"] for p in ranked] == [7, 1, 6, 2, 4, 3, 5]
    assert [p for p in ranked if p["anon"]] == [p for p in first if p["anon"]]
    assert all(p["person"] is None and p["faces"] == [] for p in ranked if p["anon"])
    assert [p["id"] for p in c.get(path, headers=tma(1), params={"order": "new"}).json()["posts"]] == list(range(7, 0, -1))
    con.close()


def test_coordinated_hearts_do_not_hold_the_top_for_a_day(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    author = login(c, 1, "ann")["id"]
    now = 2_000_000_000
    set_clock(monkeypatch, lambda: now)
    con = db.connect(cfg.db_path)
    con.executemany("INSERT INTO users (id, tg_id, created_at, seen_at) VALUES (?, ?, 0, 0)", [(1000 + i, 9_000_000 + i) for i in range(100)])
    con.executemany("""INSERT INTO fchan_posts (id, user_id, anon, status, body, tg_msg, created_at, posted_at)
        VALUES (?, ?, 0, 'live', 'Seeded post', ?, 0, ?)""", [(1, author, 1, now - 24 * 3600), (2, author, 2, now)])
    con.executemany("INSERT INTO fchan_hearts (post_id, user_id) VALUES (1, ?)", [(1000 + i,) for i in range(100)])
    assert [p["id"] for p in c.get("/api/forum-posts/feed/page", headers=tma(1)).json()["posts"]] == [2, 1]
    con.close()


def test_feed_snapshot_survives_changes_and_rechecks_visibility(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    reader, author, stranger = (login(c, i, name)["id"] for i, name in [(1, "ann"), (2, "bob"), (3, "cat")])
    now = 2_000_000_000
    set_clock(monkeypatch, lambda: now)
    monkeypatch.setattr(logic.fchannel, "FEED_MAX", 2)
    con = db.connect(cfg.db_path)
    con.executemany("""INSERT INTO fchan_posts (id, user_id, anon, status, body, tg_msg, created_at, posted_at)
        VALUES (?, ?, 1, 'live', 'Seeded post', ?, ?, ?)""",
                    [(pid, author, pid, now, now) for pid in range(1, 8)])
    path = "/api/forum-posts/feed/page"
    first = c.get(path, headers=tma(1)).json()
    cursor = first["cursor"]
    assert [p["id"] for p in first["posts"]] == [7, 6]
    assert c.get(path, headers=tma(3), params={"cursor": cursor}).status_code == 404
    assert c.get(path, headers=tma(1), params={"cursor": cursor, "order": "new"}).status_code == 404
    con.execute("INSERT INTO fchan_hearts (post_id, user_id) VALUES (1, ?), (1, ?)", (reader, stranger))
    con.execute("UPDATE fchan_posts SET status = 'hidden' WHERE id = 5")
    con.execute("INSERT INTO fchan_posts (id, user_id, status, body, tg_msg, created_at) VALUES (8, ?, 'live', 'New post', 8, ?)", (author, now))
    page = c.get(path, headers=tma(1), params={"cursor": cursor}).json()
    assert [p["id"] for p in page["posts"]] == [4, 3]
    tail = c.get(path, headers=tma(1), params={"cursor": page["cursor"]}).json()
    assert [p["id"] for p in tail["posts"]] == [2, 1] and tail["cursor"] is None
    assert tail["posts"][1]["hearts"] == 2 and tail["posts"][1]["hearted"]
    assert c.get("/api/forum-posts/feed/post/5", headers=tma(1)).status_code == 404
    assert c.get("/api/forum-posts/feed/post/1", headers=tma(1)).json()["person"] is None
    fresh = c.get(path, headers=tma(1)).json()
    assert [p["id"] for p in fresh["posts"]] == [1, 8]
    now += logic.fchannel.FEED_AGE
    assert c.get(path, headers=tma(1), params={"cursor": cursor}).status_code == 404
    con.close()


def test_activist_counts_live_days_and_checkins_and_keeps_progress_private(env, monkeypatch):
    c, cfg, _, _ = setup(env, monkeypatch)
    author, friend = (login(c, i, name)["id"] for i, name in [(1, "ann"), (2, "bob")])
    day = 86400
    published = 23_000 * day - 5 * 3600
    now = published + day - 1
    set_clock(monkeypatch, lambda: now)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO friendships VALUES (?, ?, ?)", (author, friend, now))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("""INSERT INTO events (id, org_id, status, title, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (?, 1, ?, 'Event', 0, 'laptop_3d', '#3B6BFF', ?, 0, 0)""",
                    [(i, "published" if i < 32 else "draft", author) for i in range(1, 33)])
    con.executemany("""INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at)
        VALUES (?, ?, 'going', ?, ?, 0, 0)""",
                    [(i, author, f"T{i}", now if i in (1, 32) else None) for i in range(1, 33)])
    con.executemany("""INSERT INTO fchan_posts (id, user_id, anon, status, body, tg_msg, created_at, posted_at)
        VALUES (?, ?, 1, ?, 'Seeded post', ?, 0, ?)""", [
            (1, author, "live", 1, published), (2, author, "live", 2, published + 300),
            (3, author, "hidden", 3, published - day), (4, author, "live", None, published - day),
            (5, author, "held", None, published - day), (6, author, "live", 6, None),
        ])
    con.execute("INSERT INTO fchan_comments VALUES (20, 1, ?, ?, 0)", (author, now))

    def medal(who=1):
        profile = c.get(f"/api/users/{author}", headers=tma(who)).json()
        assert all(a["code"] != "critic" for a in profile["awards"]["achievements"])
        assert all(a["code"] != "activist" for a in profile["showcase"])
        return next((a for a in profile["awards"]["achievements"] if a["code"] == "activist"), None)

    assert medal(2) is None
    assert medal()["parts"] == {"posts": 0, "events": 1}
    now += 1
    assert medal()["parts"] == {"posts": 1, "events": 1}
    assert medal()["level"] == 0
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = 2", (now,))
    logic.sync_levels(con)
    assert medal()["level"] == 1
    assert {"code": "activist", "level": 1} in c.get("/api/me", headers=tma(1)).json()["unlocked"]
    assert medal(2) is None  # a new tier could link a timed anonymous publication to this profile
    now += day
    assert medal()["parts"] == {"posts": 1, "events": 2}  # both publications on the same Almaty day
    con.execute("UPDATE fchan_posts SET status = 'hidden' WHERE id IN (1, 2)")
    assert medal()["level"] == 0
    assert medal(2) is None
    assert {"code": "activist", "level": 1} not in c.get("/api/me", headers=tma(1)).json()["unlocked"]

    con.executemany("""INSERT INTO fchan_posts (id, user_id, status, body, tg_msg, created_at, posted_at)
        VALUES (?, ?, 'live', 'Seeded post', ?, 0, ?)""",
                    [(i + 10, author, i + 10, published - i * day) for i in range(1, 16)])
    for level, events in [(2, 6), (3, 15), (4, 30)]:
        con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id <= ?", (now, events))
        got = medal()
        assert got["level"] == level and got["parts"] == {"posts": 15, "events": events}
    con.close()
