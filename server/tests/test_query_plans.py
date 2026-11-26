"""Speed (issue #363): what every app open reads uses an index. The first screen (and an event's and a club's page)
runs on a small database while every statement is recorded, and EXPLAIN QUERY PLAN of each must not walk a whole table
that grows with use: a SCAN of it, or a SEARCH with no index (MAX(id) walking the rowids). There is no ANALYZE here, so
the planner takes an index whenever one fits: a walk in these plans is one no index serves, a dropped index or a new
query without one. The timings are the PR's, on a seeded copy of ~20k students."""
import re
import sqlite3
import sys

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

# tables that grow with users or with use; a full walk of one gets slower every term
GROWS = {"users", "students", "events", "registrations", "bot_outbox", "posts", "comments", "post_reads", "post_reactions",
         "org_members", "subscriptions", "friendships", "friend_requests", "event_ratings", "receipts", "achievement_levels",
         "saved_events", "schedule_classes", "visits", "files", "rounds", "event_photos", "chat_opens", "fchan_posts", "fchan_comments"}
# whole-table reads that are meant: (module, function) -> the tables it may walk
MEANT = {("logic/profiles.py", "_rarity"): {"students", "achievement_levels"}}  # how rare each badge is: every student's levels, once a minute per worker
HOT = ["/api/me?platform=tg", "/api/events", "/api/events/past", "/api/events/past?attended=1", "/api/orgs", "/api/me/schedule",
       "/api/posts?scope=all", "/api/posts?scope=subs", "/api/posts?scope=clubs", "/api/castings", "/api/chats", "/api/friends"]
NAMES = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_]\w*)(?:\s+(?:AS\s+)?(?!ON\b|WHERE\b|JOIN\b|LEFT\b|INNER\b|CROSS\b|GROUP\b"
                   r"|ORDER\b|LIMIT\b|USING\b|INDEXED\b|NOT\b|SET\b|VALUES\b|SELECT\b|DEFAULT\b)([A-Za-z_]\w*))?", re.I)
SKIP = ("kbtu/db.py",)
HELPERS = {"rows", "one", "tx", "maybe"}


def _caller() -> tuple[str, str]:
    """The kbtu function that ran the statement (not db.py, not the rows()/one() helpers)."""
    f = sys._getframe(2)
    while f:
        path = f.f_code.co_filename.replace("\\", "/")
        if "/kbtu/" in path and not path.endswith(SKIP) and f.f_code.co_name not in HELPERS:
            return path.split("/kbtu/")[1], f.f_code.co_name
        f = f.f_back
    return "", ""


def _seed(con, me: int, pal: int) -> tuple[int, int]:
    """A club I'm in and a friend's, with an event ahead, one past, a post and an open round: the paths a real app open takes."""
    t = logic.now()
    oid = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('plans', 'club', 'Plans', 'P', 'trophy_3d', 0)").lastrowid
    for uid, role in ((me, "head"), (pal, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", (oid, uid, role))
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, ?, 0)", (me, oid))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(me, pal), max(me, pal)))
    eids = []
    for start in (t + 86400, t - 7 * 86400):
        eids.append(con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, created_by, created_at, updated_at, published_at)
            VALUES (?, 'published', 'Plans night', 'Hall', ?, ?, ?, 0, 0, 0)""", (oid, start, start + 7200, me)).lastrowid)
    for eid in eids:
        for uid in (me, pal):
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
                VALUES (?, ?, 'going', ?, 0, 0, ?)""", (eid, uid, f"P{eid}-{uid}", t - 7 * 86400 + 600 if eid == eids[1] else None))
    con.execute("INSERT INTO posts (org_id, author_id, title, body, created_at) VALUES (?, ?, 'News', 'Words.', ?)", (oid, me, t))
    con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_by, created_at) VALUES (?, 'Autumn', ?, 'open', ?, 0)", (oid, t + 86400, me))
    return oid, eids[0]


def test_the_first_screen_walks_no_growing_table(env, monkeypatch):  # noqa: F811
    c, cfg = env
    me, pal = login(c, 1, "plans")["id"], login(c, 2, "pal")["id"]
    con = db.connect(cfg.db_path)
    oid, eid = _seed(con, me, pal)
    con.close()

    seen: dict[str, tuple[str, str]] = {}
    real = db.connect

    def traced(path: str):
        x = real(path)
        x.set_trace_callback(lambda sql: seen.setdefault(sql.strip(), _caller()))
        return x

    monkeypatch.setattr(db, "connect", traced)  # a fresh app below: its pool opens every connection through here
    app = TestClient(server.create(cfg))
    seen.clear()  # the start's own catch-up steps are not an app open
    for path in HOT + [f"/api/events/{eid}", f"/api/orgs/{oid}", f"/api/users/{me}"]:
        for uid in (1, 2):
            r = app.get(path, headers=tma(uid))
            assert r.status_code == 200, (path, r.text)
    assert len(seen) > 100  # it did record the screen

    plan = sqlite3.connect(cfg.db_path)
    tables = {r[0] for r in plan.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert GROWS <= tables, GROWS - tables  # a renamed table: this test would guard nothing
    walks = []
    for sql, (module, fn) in seen.items():
        if not sql.upper().startswith(("SELECT", "WITH", "UPDATE", "DELETE", "INSERT")) or "IN ()" in sql:
            continue  # an empty IN () reads nothing, whatever its plan says
        alias = {}
        for t, a in NAMES.findall(sql):
            if t in tables:
                alias[t] = alias.get(t, t)
                if a:
                    alias[a] = t
        for step in (r[3] for r in plan.execute("EXPLAIN QUERY PLAN " + sql)):
            m = re.match(r"(SCAN|SEARCH) (\w+)( USING)?", step)
            if not m or (m.group(1) == "SEARCH" and m.group(3)):
                continue
            t = alias.get(m.group(2))
            if t in GROWS and t not in MEANT.get((module, fn), ()):
                walks.append(f"{module}:{fn} walks {t} ({step}): {' '.join(sql.split())[:200]}")
    assert not walks, "\n".join(walks)
