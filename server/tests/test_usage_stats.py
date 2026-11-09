"""Anonymous usage counters (logic/stats.py): an allowlist, clamped, daily totals with no person in them."""
from __future__ import annotations

import re
from pathlib import Path

from kbtu import bot, db, logic, texts
from kbtu.logic import stats
from test_core import DB, env, login, set_clock, tma  # noqa: F401  (env: the fixture)

MONDAY = 20003  # an Almaty day number that is a Monday
at = lambda day, hour=10: day * 86400 - 5 * 3600 + hour * 3600  # noqa: E731


def totals(con) -> dict:
    return {r[0]: r[1] for r in con.execute("SELECT key, SUM(n) FROM usage_days GROUP BY key")}


def post(c, uid, body):
    r = c.post("/api/stats", headers=tma(uid), json=body)
    assert r.status_code == 204, r.text


def test_needs_a_signed_user(env):
    c, _ = env
    assert c.post("/api/stats", json={"tab.afisha": 1}).status_code == 403


def test_allowlist_clamp_and_upsert(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    post(c, 1, {"tab.afisha": 2, "nope": 5, "err.nope": 1, "ev_12": 1, "from.event": 1.5, "do.qr": True, "do.follow": -3, "sheet.map": "9"})
    assert totals(con) == {"tab.afisha": 2}                                # everything else is ignored
    post(c, 2, {"tab.afisha": 3, "do.signup": 10_000, "open.ios.2": 7})
    assert totals(con) == {"tab.afisha": 5, "do.signup": stats.MAX_IN_BATCH, "open.ios.2": 1}  # adds up, clamped; a launch is one sample
    assert con.execute("SELECT COUNT(*) FROM usage_days").fetchone()[0] == 3  # one row a key a day


def test_one_client_runs_out_of_budget(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    for _ in range(100):
        post(c, 3, {"sheet.news": 10_000})
    assert totals(con)["sheet.news"] <= stats.DAY_BUDGET
    post(c, 4, {"sheet.news": 1})                                          # someone else still counts
    before = totals(con)["sheet.news"]
    post(c, 5, {"sheet.news": 1})
    assert totals(con)["sheet.news"] == before + 1


def test_no_person_is_stored(env):
    _, cfg = env
    con = db.connect(cfg.db_path)
    assert [r[1] for r in con.execute("PRAGMA table_info(usage_days)")] == ["day", "key", "n"]
    assert not con.execute("PRAGMA foreign_key_list(usage_days)").fetchall()
    assert all(re.fullmatch(r"[a-z]+(\.[a-z_0-9]+)+", k) for k in stats.KEYS)  # names, no room for a value


def test_web_names_match_the_allowlist():
    src = (Path(__file__).parents[2] / "web/src/lib/stats.ts").read_text(encoding="utf-8")
    assert set(re.findall(r"'((?:tab|sheet|do|from)\.[a-z]+)'", src)) == {*stats.SCREENS, *stats.ACTIONS, *stats.SOURCES}
    edges = lambda name: len(re.search(rf"{name} = \[(.*?)\]", src).group(1).split(","))  # noqa: E731  (one bucket more than edges)
    assert edges("SESS_EDGES") + 1 == len(stats.SESSIONS) and edges("DAY_EDGES") + 1 == len(stats.DAY_TIMES)
    assert {"uniq.do.qr", "uniq.tab.club", "sess.6", "time.6"} <= stats.KEYS and "uniq.from.qr" not in stats.KEYS and "sess.7" not in stats.KEYS


def _people(c, con):
    owner, other = login(c, 11, "own")["id"], login(c, 12, "oth")["id"]
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE id = ?", (owner,))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (other,))  # an admin who is not the creator hears nothing
    con.execute("UPDATE users SET can_dm = 1")
    return owner


def _digests(con):
    return con.execute("SELECT user_id, ref FROM bot_outbox WHERE kind = 'usage_week'").fetchall()


def test_digest_only_to_the_creator_once_a_week(env, monkeypatch):
    c, _ = env
    con = db.connect(DB[0])
    owner = _people(c, con)
    for t in (at(MONDAY - 1), at(MONDAY, 8), at(MONDAY + 1)):              # Sunday, Monday before 9, Tuesday
        set_clock(monkeypatch, lambda t=t: t)
        logic.stats.week(con)
    assert _digests(con) == []
    set_clock(monkeypatch, lambda: at(MONDAY))
    logic.stats.week(con)
    logic.stats.week(con)
    set_clock(monkeypatch, lambda: at(MONDAY, 15))
    logic.stats.week(con)
    assert [tuple(r) for r in _digests(con)] == [(owner, f"uw:{MONDAY}")]
    set_clock(monkeypatch, lambda: at(MONDAY + 7))
    logic.stats.week(con)
    assert [tuple(r) for r in _digests(con)] == [(owner, f"uw:{MONDAY}"), (owner, f"uw:{MONDAY + 7}")]


def test_digest_numbers(env, monkeypatch):
    c, _ = env
    con = db.connect(DB[0])
    _people(c, con)
    set_clock(monkeypatch, lambda: at(MONDAY))
    con.execute("UPDATE users SET seen_at = ?", (at(MONDAY - 1),))
    last = MONDAY - 1
    con.executemany("INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)", [
        (last, "sheet.event", 40), (last - 1, "sheet.event", 2), (last, "tab.afisha", 30), (last, "from.qr", 9), (last, "err.sheet.map", 4),
        (last, "open.ios.0", 5), (last, "open.ios.1", 3), (last, "open.ios.5", 2),
        (MONDAY, "sheet.event", 1000), (MONDAY - 8, "sheet.event", 1000)])   # today and the week before aren't this week
    f = logic.stats.fields(con, 7, MONDAY)
    assert f["active"] == 2 and f["top"].split("\n")[:2] == ["sheet.event 42", "tab.afisha 30"]
    assert len(f["top"].split("\n")) == len(f["bottom"].split("\n")) == 10
    assert f["bottom"].split("\n")[0].endswith(" 0")                       # what nobody opens is there, at zero
    assert f["sources"].split("\n")[0] == "qr 9" and f["errors"] == "sheet.map 4"
    assert f["opens"] == "ios: ≤1 / ≤2 (10)"                               # 5 of 10 under a second, 8 of 10 under two
    con.execute("UPDATE users SET lang = 'en' WHERE is_founder = 1")
    logic.stats.week(con)
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'usage_week'").fetchone()
    assert bot._render(con, row) == (*texts.bot_message("en", "usage_week", **f), "")
    assert "sheet.event 42" in bot._render(con, row)[0] and "ios: ≤1 / ≤2 (10)" in bot._render(con, row)[0]


def test_retention(env, monkeypatch):
    _, cfg = env
    con = db.connect(cfg.db_path)
    set_clock(monkeypatch, lambda: at(MONDAY, 1))                          # just after midnight: the nightly round
    con.executemany("INSERT INTO usage_days (day, key, n) VALUES (?, 'tab.club', 1)", [(MONDAY - 181,), (MONDAY - 180,), (MONDAY,)])
    logic.stats_day(con)
    assert [r[0] for r in con.execute("SELECT day FROM usage_days ORDER BY day")] == [MONDAY - 180, MONDAY]


def test_samples_are_one_a_batch(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    post(c, 6, {"sess.1": 9, "time.3": 9, "uniq.sheet.map": 9})
    assert totals(con) == {"sess.1": 1, "time.3": 1, "uniq.sheet.map": 1}


def test_retention_and_people_from_visits(env, monkeypatch):
    c, _ = env
    con = db.connect(DB[0])
    set_clock(monkeypatch, lambda: at(MONDAY))
    a, b, d = (login(c, i, n)["id"] for i, n in ((31, "ana"), (32, "ben"), (33, "dan")))
    con.execute("DELETE FROM visits")
    con.execute("UPDATE users SET created_at = ? WHERE id IN (?, ?)", (at(MONDAY - 8), a, b))  # both joined 8 days ago
    con.execute("UPDATE users SET created_at = ? WHERE id = ?", (at(MONDAY - 200), d))
    day = MONDAY - 8
    con.executemany("INSERT INTO visits (day, user_id) VALUES (?, ?)", [(day, a), (day, b), (day + 1, a), (day + 7, b), (MONDAY - 1, a), *((MONDAY - 1 - i, d) for i in range(16))])
    f = stats.fields(con, 7, MONDAY)
    assert (f["dau"], f["wau"], f["mau"]) == (3, 3, 3)
    assert f["retention"].split("\n") == ["D1: 50% (1/2)", "D7: 100% (2/2)", "D30: —"]    # D30: nobody joined 30 days before the window's days
    assert f["spread"].split("\n") == ["1: 0%", "2-3: 67%", "4-7: 0%", "8-15: 0%", "16+: 33%"]  # ben 2, ana 3, dan 16


def test_digest_shows_length_time_and_uses(env, monkeypatch):
    c, _ = env
    con = db.connect(DB[0])
    ids = [login(c, 41 + i, f"eva{i}")["id"] for i in range(4)]
    set_clock(monkeypatch, lambda: at(MONDAY))
    last = MONDAY - 1
    con.execute("DELETE FROM visits")
    con.executemany("INSERT INTO visits (day, user_id) VALUES (?, ?)", [(last, i) for i in ids])
    con.executemany("INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)", [(last, "sess.2", 3), (last, "sess.6", 1), (last, "time.4", 2), (last, "uniq.sheet.event", 1), (last, "uniq.do.qr", 3)])
    f = stats.fields(con, 7, MONDAY)
    assert f["sessions"] == "≤30s 0 · ≤1m 0 · ≤3m 3 · ≤5m 0 · ≤10m 0 · ≤20m 0 · 20m+ 1\np50 ≤3m, p75 ≤3m"
    assert f["day_times"].endswith("p50 ≤40m, p75 ≤40m")
    assert f["uses"].split("\n")[:2] == ["do.qr 75%", "sheet.event 25%"]
    assert all(("{%s}" % k) in texts.BOT[lang]["usage_week"][0] for lang in ("ru", "kk", "en") for k in f)
