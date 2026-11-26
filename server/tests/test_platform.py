"""The device kind from /api/me (account.seen_platform): kept at most once a day per kind, swept after 90 days, gone
with the account."""
import time

from kbtu import db, logic
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def kinds(con, uid: int) -> dict:
    return dict(con.execute("SELECT kind, seen_at FROM user_platforms WHERE user_id = ?", (uid,)).fetchall())


def test_platform_kept_once_a_day(env, monkeypatch):
    c, cfg = env
    login(c, 90, "stu")
    con = db.connect(cfg.db_path)
    uid = con.execute("SELECT id FROM users WHERE tg_id = 90").fetchone()[0]
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    assert kinds(con, uid) == {}                                                  # no kind said: nothing kept
    for other in ("tdesktop", "unknown", "ANDROID", "x" * 300, ""):              # only the four coarse kinds, the page still opens
        assert c.get("/api/me", params={"platform": other}, headers=tma(90)).status_code == 200
    assert kinds(con, uid) == {}
    first = clock[0]
    assert c.get("/api/me?platform=android&reportLog=false", headers=tma(90)).status_code == 200
    assert kinds(con, uid) == {"android": first}
    clock[0] += 3600
    c.get("/api/me?platform=android", headers=tma(90))                           # the same day: no write
    c.get("/api/me?platform=desktop", headers=tma(90))                           # another kind: its own row
    assert kinds(con, uid) == {"android": first, "desktop": first + 3600}
    clock[0] = first + 86400
    c.get("/api/me?platform=android", headers=tma(90))
    assert kinds(con, uid) == {"android": first + 86400, "desktop": first + 3600}


def test_platform_swept_and_deleted(env, monkeypatch):
    c, cfg = env
    login(c, 90, "stu")
    login(c, 91, "bob")
    con = db.connect(cfg.db_path)
    stu, bob = (con.execute("SELECT id FROM users WHERE tg_id = ?", (t,)).fetchone()[0] for t in (90, 91))
    night = ((int(time.time()) + 5 * 3600) // 86400 + 2) * 86400 - 4 * 3600        # two days on, 01:00 Almaty
    set_clock(monkeypatch, lambda: night)
    con.executemany("INSERT INTO user_platforms (user_id, kind, seen_at) VALUES (?, ?, ?)",
                    [(stu, "android", night - 91 * 86400), (stu, "ios", night - 89 * 86400), (bob, "android", night)])
    logic.stats_day(con)                                                          # the night's sweep: 90 days, as the policy says
    assert kinds(con, stu) == {"ios": night - 89 * 86400}
    logic.account.delete_me(con, logic.Viewer(stu, "user", True))
    assert kinds(con, stu) == {} and kinds(con, bob) == {"android": night}
    assert ("user_platforms", "user_id") in logic.account._DEL_GONE
