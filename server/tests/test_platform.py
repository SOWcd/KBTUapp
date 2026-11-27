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


def test_android_app_reported(env, monkeypatch):
    """The installed Android app (the Google Play TWA) says app=play: /api/me answers androidApp from then on (Profile's
    Google Play row and the tester sheet stop); only with platform=android, swept after 90 days, gone with the account."""
    c, cfg = env
    login(c, 90, "stu")
    con = db.connect(cfg.db_path)
    uid = con.execute("SELECT id FROM users WHERE tg_id = 90").fetchone()[0]
    now = ((int(time.time()) + 5 * 3600) // 86400 + 2) * 86400 - 4 * 3600       # two days on, 01:00 Almaty: the sweep runs
    set_clock(monkeypatch, lambda: now)
    assert c.get("/api/me?platform=android", headers=tma(90)).json()["androidApp"] is False
    for bad in ("?platform=ios&app=play", "?platform=android&app=other", "?app=play"):  # another kind or word: nothing kept
        c.get("/api/me" + bad, headers=tma(90))
    assert c.get("/api/me?platform=android", headers=tma(90)).json()["androidApp"] is False
    c.get("/api/me?platform=android&app=play", headers=tma(90))
    assert c.get("/api/me", headers=tma(90)).json()["androidApp"] is True      # Telegram too: the account knows
    con.execute("UPDATE android_app SET seen_at = ?", (now - 91 * 86400,))
    logic.stats_day(con)
    assert con.execute("SELECT COUNT(*) FROM android_app").fetchone()[0] == 0
    c.get("/api/me?platform=android&app=play", headers=tma(90))
    logic.account.delete_me(con, logic.Viewer(uid, "user", True))
    assert con.execute("SELECT COUNT(*) FROM android_app").fetchone()[0] == 0
    assert ("android_app", "user_id") in logic.account._DEL_GONE


def test_android_welcome_once_after_the_yes(env, monkeypatch, capsys):
    """The installed app's first launch queues the bot's one thanks, but only once the creator turned it on (admin
    android-welcome on, which also thanks whoever opened it before); off stops new ones; a preview goes to one person."""
    from kbtu import admin, outbox
    c, cfg = env
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    login(c, 90, "stu")
    login(c, 91, "two")
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (90, 91)}

    def thanks():
        return [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'android_welcome' AND ref = '' ORDER BY user_id")]
    c.get("/api/me?platform=android&app=play", headers=tma(90))
    assert thanks() == []                                                    # not before the yes
    admin.main(["android-welcome", "on", "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 1"
    admin.main(["android-welcome", "on"])
    assert capsys.readouterr().out.strip() == "on, queued 1"
    assert thanks() == [uid[90]]
    c.get("/api/me?platform=android&app=play", headers=tma(91))
    con.execute("UPDATE android_app SET seen_at = 0")                         # a later day: no second thanks
    c.get("/api/me?platform=android&app=play", headers=tma(91))
    c.get("/api/me?platform=android&app=play", headers=tma(90))
    admin.main(["android-welcome", "on"])
    assert thanks() == [uid[90], uid[91]]
    row = con.execute("SELECT * FROM bot_outbox WHERE kind = 'android_welcome' AND user_id = ?", (uid[91],)).fetchone()
    text, button, start = outbox._render(con, {**dict(row), "lang": "en", "tg_id": 91})
    assert text.startswith("\U0001f389") and button and start == ""
    admin.main(["android-welcome", "off"])
    con.execute("DELETE FROM android_app")
    con.execute("DELETE FROM bot_outbox")
    c.get("/api/me?platform=android&app=play", headers=tma(90))
    assert thanks() == []                                                    # off: no new ones
    con.execute("UPDATE users SET tg_username = 'owner90' WHERE tg_id = 90")
    admin.main(["android-welcome", "@owner90"])
    assert [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'android_welcome' AND ref != ''")] == [uid[90]]
