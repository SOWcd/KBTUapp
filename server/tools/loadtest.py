"""Load test: a big seeded database, the real server under uvicorn, many students opening the app at once.

    cd server && .venv/bin/python tools/loadtest.py [--students 5000] [--users 300] [--seconds 30] [--workers 1]

Seeds a fresh database in a temp directory (5000 students, 80 clubs, 400 events, ~30k registrations, ~20k
friendships, 75k classes, posts, comments, reads), starts `uvicorn kbtu.app:create --factory` on it with the postman
off, then runs `--users` students in parallel for `--seconds`: each one opens the app (the same calls as the web app's
start: me, events, orgs, schedule, posts, friends, my card, tickets), opens events and a club, and sometimes signs up,
leaves, comments, reacts or marks posts read. Prints requests per second and p50/p95/p99 per route. Nothing leaves
this machine: the Telegram initData is signed with a made-up bot token.

    --rush N    instead: N students tap "Going" on one new event with N/3 seats at the same moment; then the database
                must hold exactly N/3 tickets and the rest on the waitlist, in the order they came, nobody twice."""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kbtu import auth, db  # noqa: E402

BOT = "1:loadtest"
SERVER = Path(__file__).resolve().parents[1]
SCHOOLS = ["SITE", "BS", "ISE", "SAM", "SMSGT", "KMA", "SEOGI", "SCE"]


def seed(path: str, students: int, rnd: random.Random) -> tuple[list[int], list[int], list[int], list[int]]:
    """(user ids, upcoming event ids, org ids, post ids)."""
    db.init(path)
    con = db.connect(path)
    now, day = int(time.time()), 86400
    con.execute("BEGIN")
    users = list(range(1, students + 1))
    con.executemany("""INSERT INTO users (id, tg_id, tg_username, tg_first_name, tg_last_name, lang, can_dm, created_at, seen_at, qr_code, card_no)
        VALUES (?, ?, ?, ?, ?, 'ru', 1, ?, ?, ?, ?)""",
                    [(u, 10_000_000 + u, f"user{u}", f"Name{u}", f"Surname{u}", now - 30 * day, now, f"QR{u:08d}", u) for u in users])
    con.executemany("""INSERT INTO students (user_id, student_id, first_name, last_name, email, course, school, consent_version, consent_at, verified_at, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-v1', ?, ?, ?)""",
                    [(u, f"24B{100000 + u}", f"Name{u}", f"Surname{u}", f"u{u}@kbtu.kz", rnd.randint(1, 4), rnd.choice(SCHOOLS), now, now, now) for u in users])
    classes = [(u, wd, f"{h:02d}:00", f"{h:02d}:50", f"Subject {rnd.randint(1, 300)}", f"CSCI{rnd.randint(1000, 4999)}", "lecture", str(rnd.randint(100, 500)), "Teacher")
               for u in users for wd in range(1, 6) for h in rnd.sample(range(8, 19), 3)]
    con.executemany("INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, code, kind, room, teacher) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", classes)
    orgs = list(range(1, 81))
    con.executemany("INSERT INTO orgs (id, slug, kind, name, short, description, emoji, official, created_at) VALUES (?, ?, 'club', ?, ?, ?, 'laptop_3d', ?, ?)",
                    [(o, f"club{o}", f"Club {o}", "C", "A club for load testing. " * 5, int(o % 3 == 0), now - 60 * day) for o in orgs])
    members, seen = [], set()
    for o in orgs:
        team = rnd.sample(users, 36)
        for i, u in enumerate(team):
            members.append((o, u, "president" if i == 0 else "vice" if i == 1 else "head" if i < 4 else "member", now - 30 * day))
            seen.add((o, u))
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)", members)
    con.executemany("INSERT OR IGNORE INTO subscriptions (user_id, org_id, created_at) VALUES (?, ?, ?)",
                    [(u, o, now) for u in users for o in rnd.sample(orgs, 3)])
    events, upcoming = [], []
    for e in range(1, 401):
        starts = now + rnd.randint(1, 30) * day + rnd.randint(9, 20) * 3600 if e % 2 else now - rnd.randint(1, 60) * day
        events.append((e, rnd.choice(orgs), f"Event {e}", "What happens there. " * 10, starts, starts + 7200, str(rnd.randint(100, 500)),
                       "laptop_3d", "#3B6BFF", rnd.choice([None, 50, 100, 300]), now - 40 * day, now - 40 * day, now - 40 * day))
        if starts > now:
            upcoming.append(e)
    con.executemany("""INSERT INTO events (id, org_id, status, title, description, starts_at, ends_at, place, emoji, color, seats, created_at, updated_at, published_at)
        VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", events)
    regs, n = set(), 0
    while len(regs) < 30_000:
        regs.add((rnd.randint(1, 400), rnd.choice(users)))
    rows = []
    for ev, u in regs:
        n += 1
        rows.append((ev, u, f"T{n:09d}", now - 10 * day, now - 10 * day, now - day if ev % 2 == 0 and rnd.random() < 0.6 else None))
    con.executemany("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at) VALUES (?, ?, 'going', ?, ?, ?, ?)", rows)
    pairs = set()
    while len(pairs) < 20_000:
        a, b = rnd.sample(users, 2)
        pairs.add((min(a, b), max(a, b)))
    con.executemany("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, ?)", [(a, b, now) for a, b in pairs])
    posts = list(range(1, 2001))
    con.executemany("INSERT INTO posts (id, org_id, author_id, audience, title, body, created_at) VALUES (?, ?, NULL, ?, ?, ?, ?)",
                    [(p, rnd.choice(orgs), "clubs" if p % 10 == 0 else "public", f"Post {p}", "News from the club. " * 8, now - rnd.randint(0, 60) * day) for p in posts])
    con.executemany("INSERT INTO comments (post_id, event_id, user_id, body, created_at) VALUES (?, ?, ?, ?, ?)",
                    [(rnd.choice(posts), None, rnd.choice(users), "Nice!", now - rnd.randint(0, 30) * day) for _ in range(5000)]
                    + [(None, rnd.randint(1, 400), rnd.choice(users), "When does it start?", now - rnd.randint(0, 30) * day) for _ in range(5000)])
    con.executemany("INSERT OR IGNORE INTO post_reads (post_id, user_id, read_at) VALUES (?, ?, ?)", [(rnd.choice(posts), rnd.choice(users), now) for _ in range(60_000)])
    con.executemany("INSERT OR IGNORE INTO post_reactions (post_id, user_id, kind) VALUES (?, ?, 'fire')", [(rnd.choice(posts), rnd.choice(users)) for _ in range(20_000)])
    con.executemany("INSERT OR IGNORE INTO saved_events (user_id, event_id, created_at) VALUES (?, ?, ?)", [(rnd.choice(users), rnd.randint(1, 400), now) for _ in range(10_000)])
    con.executemany("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, send_after, sent_at) VALUES (?, 'remind_2h', ?, ?, ?)",
                    [(rnd.choice(users), f"event:{i}", now - day, now - day) for i in range(50_000)])
    con.execute("COMMIT")
    con.execute("ANALYZE")
    con.close()
    return users, upcoming, orgs, posts


def route(method: str, url: str) -> str:
    return method + " " + re.sub(r"/\d+", "/{id}", url.split("?")[0]) + ("?" + url.split("?")[1].split("=")[0] if "?" in url else "")


async def student(http: httpx.AsyncClient, uid: int, upcoming: list[int], orgs: list[int], posts: list[int], until: float, out: list, rnd: random.Random):
    head = {"Authorization": "tma " + auth.sign_init_data({"id": 10_000_000 + uid, "first_name": f"Name{uid}"}, BOT)}

    async def go(method: str, url: str, body: dict | None = None):
        t = time.perf_counter()
        try:
            r = await http.request(method, url, headers=head, json=body)
            ok = r.status_code < 500 and not (r.status_code >= 400 and r.json().get("error") in (None, "unavailable"))
        except httpx.HTTPError:
            ok = False
        out.append((route(method, url), time.perf_counter() - t, ok))

    while time.monotonic() < until:
        await go("GET", "/api/me")  # the app's start: me, then these together, then friends and my card
        await asyncio.gather(go("GET", "/api/events"), go("GET", "/api/orgs"), go("GET", "/api/me/schedule"), go("GET", "/api/posts?scope=all"))
        await asyncio.gather(go("GET", "/api/friends"), go("GET", f"/api/users/{uid}"), go("GET", "/api/me/tickets"))
        for e in rnd.sample(upcoming, 3):  # looking around
            await go("GET", f"/api/events/{e}")
        e = rnd.choice(upcoming)
        if rnd.random() < 0.3:
            await go("POST", f"/api/events/{e}/registration", {})
            await go("DELETE", f"/api/events/{e}/registration")
        if rnd.random() < 0.2:
            await go("GET", f"/api/events/{e}/comments")
            await go("POST", f"/api/events/{e}/comments", {"body": "Is there food?", "asOrg": False})
        o = rnd.choice(orgs)
        await asyncio.gather(go("GET", f"/api/orgs/{o}"), go("GET", f"/api/posts?scope=org:{o}"))
        if rnd.random() < 0.3:
            await go("PUT", f"/api/posts/{rnd.choice(posts)}/reactions/fire")
            await go("POST", "/api/posts/read", {"ids": rnd.sample(posts, 5)})


async def rush(http: httpx.AsyncClient, uids: list[int], out: list) -> None:
    heads = [{"Authorization": "tma " + auth.sign_init_data({"id": 10_000_000 + u, "first_name": f"Name{u}"}, BOT)} for u in uids]

    async def go(head: dict) -> None:
        t = time.perf_counter()
        try:
            r = await http.post("/api/events/9999/registration", headers=head, json={})
            ok = r.status_code == 200 and r.json()["my"]["status"] in ("going", "waitlist")
            if not ok:
                print("failed:", r.status_code, r.text[:200])
        except httpx.HTTPError as exc:
            print("failed:", type(exc).__name__)
            ok = False
        out.append(("rush", time.perf_counter() - t, ok))
    await asyncio.gather(*(go(h) for h in heads))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=5000)
    ap.add_argument("--users", type=int, default=300, help="students using the app at the same moment")
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--keep", action="store_true", help="keep the temp directory (the seeded database)")
    ap.add_argument("--rush", type=int, default=0, help="N students sign up for one event at once (see above)")
    a = ap.parse_args()
    rnd = random.Random(7)
    tmp = Path(tempfile.mkdtemp(prefix="kbtu-load-"))
    path = str(tmp / "kbtu.db")
    t = time.monotonic()
    users, upcoming, orgs, posts = seed(path, a.students, rnd)
    print(f"seeded {a.students} students in {time.monotonic() - t:.1f}s: {os.path.getsize(path) / 1e6:.0f} MB")
    seats = a.rush // 3
    if a.rush:
        con = db.connect(path)
        con.execute("""INSERT INTO events (id, org_id, status, title, starts_at, ends_at, seats, created_at, updated_at, published_at)
            VALUES (9999, 1, 'published', 'Rush', ?, ?, ?, 0, 0, 0)""", (int(time.time()) + 86400, int(time.time()) + 90000, seats))
        con.close()
    port = free_port()
    env = {**os.environ, "DB_PATH": path, "BOT_TOKEN": BOT, "TOKEN_KEY": base64.b64encode(os.urandom(32)).decode(), "BACKGROUND": "0",
           "ADMIN_TG_IDS": "", "WEB_DIST": str(SERVER.parent / "web" / "dist")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "kbtu.app:create", "--factory", "--port", str(port), "--workers", str(a.workers),
                             "--log-level", "warning", "--no-access-log"], cwd=SERVER, env=env)
    try:
        # ponytail: one client process; past a few hundred sockets at once the test measures this machine's TCP accept
        # queue, not the app (in production Cloudflare's tunnel reuses a handful of connections)
        conns = min(200, max(a.users, a.rush))
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60,
                                     limits=httpx.Limits(max_connections=conns, max_keepalive_connections=conns)) as http:
            for _ in range(100):
                try:
                    if (await http.get("/healthz")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
            out: list = []
            if a.rush:
                await rush(http, users[:a.rush], out)
                proc.terminate()
                proc.wait()
                con = db.connect(path)
                got = dict(con.execute("SELECT status, COUNT(*) FROM registrations WHERE event_id = 9999 GROUP BY status").fetchall())
                twice = con.execute("SELECT COUNT(*) - COUNT(DISTINCT user_id) FROM registrations WHERE event_id = 9999").fetchone()[0]
                order = [r[0] for r in con.execute("SELECT waitlisted_at FROM registrations WHERE event_id = 9999 AND status = 'waitlist' ORDER BY id")]
                lat = sorted(sec for _, sec, _ in out)
                print(f"rush: {a.rush} students at once on {a.workers} worker(s), {seats} seats: {got}, twice: {twice}, failed: "
                      f"{sum(not ok for *_, ok in out)}; p50 {lat[len(lat) // 2] * 1000:.0f} ms, max {lat[-1] * 1000:.0f} ms")
                assert got.get("going") == seats and got.get("waitlist") == a.rush - seats and not twice and order == sorted(order), "seats went wrong"
                return
            until = time.monotonic() + a.seconds
            t = time.monotonic()
            await asyncio.gather(*(student(http, rnd.choice(users), upcoming, orgs, posts, until, out, random.Random(i)) for i in range(a.users)))
            took = time.monotonic() - t
    finally:
        proc.terminate()
        proc.wait()
        if not a.keep:
            shutil.rmtree(tmp)
    by: dict[str, list] = {}
    for name, sec, ok in out:
        by.setdefault(name, []).append((sec, ok))
    print(f"\n{a.users} students, {a.workers} worker(s), {took:.0f}s: {len(out)} requests, {len(out) / took:.0f} req/s, "
          f"{sum(not ok for _, _, ok in out)} failed" + (f"; database kept in {tmp}" if a.keep else ""))
    print(f"{'route':44} {'n':>6} {'fail':>5} {'p50 ms':>7} {'p95 ms':>7} {'p99 ms':>7} {'max ms':>7}")
    for name, xs in sorted(by.items(), key=lambda kv: -sorted(s for s, _ in kv[1])[int(len(kv[1]) * 0.95)]):
        s = sorted(x for x, _ in xs)
        q = lambda p: s[min(len(s) - 1, int(len(s) * p))] * 1000  # noqa: E731
        print(f"{name:44} {len(s):>6} {sum(not ok for _, ok in xs):>5} {q(0.5):>7.0f} {q(0.95):>7.0f} {q(0.99):>7.0f} {s[-1] * 1000:>7.0f}")


if __name__ == "__main__":
    asyncio.run(main())
