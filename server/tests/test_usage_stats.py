"""Anonymous usage counters (logic/stats.py): an allowlist, clamped, daily totals with no person in them."""
from __future__ import annotations

import re
from pathlib import Path

from kbtu import db, logic, texts
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


def test_android_page_counts_signed_out(env, monkeypatch):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    for k in ("page", "join", "join", "nope", "andr.go"):
        assert c.post(f"/api/stats/andr?k={k}").status_code == 204
    got = totals(con)
    assert got.get("andr.page") == 1 and got.get("andr.join") == 2 and not any(k.endswith(("nope", "andr.go")) for k in got)
    monkeypatch.setattr(stats, "PAGE_CAP", 3)
    for _ in range(5):
        c.post("/api/stats/andr?k=optin")
    assert totals(con)["andr.optin"] == 3  # the day's ceiling
    post(c, 11, {"andr.sheet": 1, "andr.go": 1, "andr.join": 9})  # the app sends only its own two; the page's need the page
    got = totals(con)
    assert got["andr.sheet"] == 1 and got["andr.go"] == 1 and got["andr.join"] == 2
    assert "sheet 1 → go 1 → page 1 → join 2 → optin 3 → play 0" in stats.fields(con, 7)["android"]


def test_android_page_flood_writes_nothing_past_the_cap(env, monkeypatch):
    """A loop on the signed-out page: at the day's cap it returns before the database, so it takes no write lock."""
    c, _ = env
    con = db.connect(DB[0])
    writes = []
    real = stats.maybe
    monkeypatch.setattr(stats, "maybe", lambda *a, **kw: (writes.append(a), real(*a, **kw))[1])
    monkeypatch.setattr(stats, "PAGE_CAP", 3)
    for i in range(10):
        assert c.post("/api/stats/andr?k=play", headers={"cf-connecting-ip": f"10.0.0.{i}"}).status_code == 204
    assert len(writes) == 3 and totals(con)["andr.play"] == 3


def test_android_page_throttled_per_address(env, monkeypatch):
    c, _ = env
    con = db.connect(DB[0])
    monkeypatch.setattr(stats, "PAGE_PER_IP", 2)
    for _ in range(5):
        c.post("/api/stats/andr?k=page", headers={"cf-connecting-ip": "10.0.0.7"})
    assert totals(con)["andr.page"] == 2                                   # this address, this minute
    c.post("/api/stats/andr?k=page", headers={"cf-connecting-ip": "10.0.0.8"})
    assert totals(con)["andr.page"] == 3                                   # another address still counts
    later = logic.core.now() + 60
    set_clock(monkeypatch, lambda: later)
    c.post("/api/stats/andr?k=page", headers={"cf-connecting-ip": "10.0.0.7"})
    assert totals(con)["andr.page"] == 4                                   # and the next minute


def test_one_person_caps_each_key_a_day(env):
    """MAX_IN_BATCH is per batch: batch after batch, one account still can't run a rare key or a funnel's step up."""
    c, _ = env
    con = db.connect(DB[0])
    for _ in range(5):
        post(c, 6, {"signup.done": 20, "do.share": 1})
    got = totals(con)
    assert got["signup.done"] == stats.KEY_DAY_CAP and got["do.share"] == 5
    post(c, 7, {"signup.done": 2})                                         # someone else still counts
    assert totals(con)["signup.done"] == stats.KEY_DAY_CAP + 2


def test_staff_screens_have_no_platform_timings(env):
    """A screen only a club's organizers open, timed by platform, could name one club head: no tti.* for those."""
    c, _ = env
    con = db.connect(DB[0])
    assert set(stats.STAFF_SCREENS) <= set(stats.SCREENS)
    assert not [k for k in stats.KEYS if k.startswith(tuple(f"tti.{s}." for s in stats.STAFF_SCREENS))]
    post(c, 8, {**{f"tti.{s}.ios.1": 1 for s in stats.STAFF_SCREENS}, "sheet.scanner": 1, "tti.sheet.event.ios.1": 1})
    assert totals(con) == {"sheet.scanner": 1, "tti.sheet.event.ios.1": 1}


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


def test_web_flows_errors_and_timings_match_the_allowlist():
    web = Path(__file__).parents[2] / "web/src"
    src = (web / "lib/stats.ts").read_text(encoding="utf-8")
    names = set(re.findall(r"'((?:signup|paid|post|edit|join|streak)\.[a-z0-9]+)'", src))
    assert names == {k for k in (*stats.FLOW_KEYS, *stats.STREAK) if k.startswith(("signup.", "paid.", "post.", "edit.", "join.", "streak."))}
    union = lambda name: re.findall(r"'([a-z_]+)'", re.search(rf"type {name} = (.*?);", src, re.S).group(1))  # noqa: E731
    assert tuple(union("JsKind")) == stats.JS_KINDS and tuple(union("ApiKind")) == stats.API_KINDS
    codes = re.search(r"interface ApiError \{ error: (.*?);", (web / "lib/api/types.ts").read_text(encoding="utf-8")).group(1)
    assert set(re.findall(r"'([a-z_]+)'", codes)) == set(stats.API_KINDS) - {"network", "server", *stats.EXPECTED}  # the server's codes, all of them
    client = (web / "lib/api/client.ts").read_text(encoding="utf-8")  # a 403's reason only (a 400 may say 'consent' too)
    assert "r.status === 403 ? (data as ApiError | null)?.message" in client and "why === 'consent' ? 'consent' : why === 'init_data' ? 'expired'" in client
    assert len(re.search(r"TTI_EDGES = \[(.*?)\]", src).group(1).split(",")) + 1 == len(stats.TTI)
    for steps, ends in stats.FUNNELS.values():                              # every step is a key someone can count
        assert all(k in stats.KEYS or k.startswith("andr.") for k in (*steps, *ends))


def test_errors_timings_and_flows_counted_by_class_only(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    post(c, 9, {"tti.sheet.event.ios.2": 1, "tti.tab.forum.android.5": 3, "js.tab.forum.type": 1, "api.sheet.pay.network": 2,
                "signup.tap": 1, "post.drop": 1, "streak.t2": 1, "do.share": 1,
                "js.tab.forum.Cannot read properties": 1, "api.sheet.admin.network": 1, "tti.sheet.event.ios.9": 1, "andr.play": 1})
    assert totals(con) == {"tti.sheet.event.ios.2": 1, "tti.tab.forum.android.5": 3, "js.tab.forum.type": 1, "api.sheet.pay.network": 2,
                           "signup.tap": 1, "post.drop": 1, "streak.t2": 1, "do.share": 1}  # a message, the admin sheet, a page step: dropped


def test_week_digest(env):
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("DELETE FROM usage_days")
    last = MONDAY - 1
    con.executemany("INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)", [
        (last, "sheet.event", 200), (last, "signup.tap", 50), (last, "signup.done", 40), (last, "signup.fail", 3),
        (last - 7, "sheet.event", 100), (last - 7, "signup.tap", 40), (last - 7, "signup.done", 36),  # the week before
        (last, "sheet.map", 12), (last - 7, "sheet.map", 60),
        (last, "tti.sheet.studio.android.4", 8), (last, "tti.sheet.studio.android.0", 1), (last - 7, "tti.sheet.studio.android.2", 6),
        (last, "tti.sheet.event.ios.0", 30), (last, "tti.sheet.news.ios.5", 2),   # under 5 samples: not ranked
        (last, "api.tab.forum.network", 7), (last - 7, "api.tab.forum.network", 2), (last, "do.share", 4),
        (last, "api.tab.afisha.consent", 30), (last, "api.sheet.event.consent", 4), (last, "api.tab.afisha.expired", 9),
        (MONDAY, "sheet.event", 999)])                                      # today isn't a whole day yet
    w = stats.week(con, MONDAY).split("\n")
    assert w[0].startswith("📊 ") and all(line[:1] in "📊📈🪜🐢💥🆕 " for line in w)
    assert "  ▼ sheet.map 12 (−80%)" in w and "  ▲ sheet.event 200 (+100%)" in w
    assert "  🎟 signup: event 200 → tap 50 (25%) → done 40 (80%) · fail 3 · 🔻event→tap 25%, −15 pts" in w
    assert "  📮 appeal: —" in w
    slow = w.index("🐢 Slowest (p75, tap → first frame)")
    assert w[slow + 1:slow + 3] == ["  sheet.studio android ≤2s (9, was ≤500ms)", "  sheet.event ios ≤100ms (30)"]
    assert "  api.tab.forum.network 7 (+250%)" in w and w[-1].startswith("🆕 Since Nov 20: share 4 · ")
    assert "  not errors: consent asked 34 · sign-in expired 9" in w and not any(".consent " in x or ".expired " in x for x in w)


def test_usage_numbers(env):
    c, _ = env
    con = db.connect(DB[0])
    a, b = (login(c, uid, name)["id"] for uid, name in ((11, "ann"), (12, "ben")))
    con.execute("DELETE FROM visits")
    con.executemany("INSERT INTO visits (day, user_id) VALUES (?, ?)", [(MONDAY - 1, a), (MONDAY - 1, b), (MONDAY - 2, a), (MONDAY - 2, b), (MONDAY, a)])
    last = MONDAY - 1
    con.executemany("INSERT INTO usage_days (day, key, n) VALUES (?, ?, ?)", [
        (last, "sheet.event", 40), (last - 1, "sheet.event", 2), (last, "tab.afisha", 30), (last, "from.qr", 9), (last, "err.sheet.map", 4),
        (last, "open.ios.0", 5), (last, "open.ios.1", 3), (last, "open.ios.5", 2),
        (MONDAY, "sheet.event", 1000), (MONDAY - 8, "sheet.event", 1000)])   # today and the week before aren't this week
    f = stats.fields(con, 7, MONDAY)
    assert f["active"] == 2 and f["top"].split("\n")[:2] == ["sheet.event 42", "tab.afisha 30"]
    assert len(f["top"].split("\n")) == len(f["bottom"].split("\n")) == 10
    assert f["bottom"].split("\n")[0].endswith(" 0")                       # what nobody opens is there, at zero
    assert f["sources"].split("\n")[0] == "qr 9" and f["errors"] == "sheet.map 4"
    assert f["opens"] == "ios: ≤1 / ≤2 (10)"                               # 5 of 10 under a second, 8 of 10 under two


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


def test_usage_shows_length_time_and_uses(env, monkeypatch):
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
    con.execute("INSERT INTO usage_days (day, key, n) VALUES (?, 'uniq.sheet.event', 50)", (last - stats.WINDOW,))
    assert stats.fields(con, stats.WINDOW + 1, MONDAY)["uses"] == f["uses"]
    assert all(("{%s}" % k) in texts.BOT[lang]["usage_week"][0] for lang in ("ru", "kk", "en") for k in f)


def test_drops_repeated_uniques_and_admin_counters(env):
    c, _ = env
    stats._spent.clear()
    stats._uniq.clear()
    con = db.connect(DB[0])
    post(c, 7, {"uniq.sheet.map": 1, "sheet.admin": 3, "err.sheet.admin": 1, "uniq.sheet.admin": 1})
    for _ in range(5):
        post(c, 7, {"uniq.sheet.map": 1})
    assert totals(con) == {"uniq.sheet.map": 1}                            # a repeat is dropped; the admin sheet isn't counted at all


def test_layout_buckets_by_platform(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    con.execute("DELETE FROM usage_days")
    post(c, 13, {"lay.android.8.safe_b.6": 3, "lay.android.8.gap.6": 1, "lay.android.8.full.1": 1, "lay.ios.9.env_b.5": 1,
                 "lay.android.8.safe_b.8": 1, "lay.android.8.safe_b.48": 1, "lay.android.13.gap.0": 1})
    post(c, 14, {"lay.android.8.safe_b.0": 1, "lay.android.8.full.0": 1})
    assert totals(con) == {"lay.android.8.safe_b.6": 1, "lay.android.8.gap.6": 1, "lay.android.8.full.1": 1, "lay.ios.9.env_b.5": 1,
                           "lay.android.8.safe_b.0": 1, "lay.android.8.full.0": 1}  # one a launch; a bucket or version off the list: dropped
    out = stats.layout(con, 1).split("\n")
    assert out == ["ios tg 9: fullscreen 0/0", "  env(safe-area-inset-bottom): 33-48 1",
                   "android tg 8: fullscreen 1/2", "  tg safeAreaInset.bottom: 0 1 · 49-64 1", "  nav bottom gap (10 by design): 49-64 1"]
    web = Path(__file__).parents[2] / "web/src/lib"
    src, lay = ((web / f).read_text(encoding="utf-8") for f in ("stats.ts", "layoutStats.ts"))
    assert len(re.search(r"LAY_EDGES = \[(.*?)\]", lay).group(1).split(",")) + 1 == len(stats.LAY)
    assert tuple(re.findall(r"'([a-z_]+)'", re.search(r"type LayMetric = (.*?);", src).group(1))) == tuple(stats.LAY_VALUES)
    assert (*re.findall(r"'(\d+)'", re.search(r"TG_MAJORS = \[(.*?)\]", lay).group(1)), "x") == stats.TG_MAJORS


def test_hero_kinds_counted_without_an_item(env):
    c, _ = env
    stats._spent.clear()
    con = db.connect(DB[0])
    src = (Path(__file__).parents[2] / "web/src/lib/hero.ts").read_text(encoding="utf-8")
    kinds = re.search(r"KINDS = \[(.*?)\]", src).group(1)
    assert tuple(re.findall(r"'([a-z]+)'", kinds)) == stats.HERO_KINDS    # the app's names are the allowlist's
    post(c, 8, {"hero.show.news": 3, "hero.tap.news": 1, "hero.tap.e12": 1, "hero.show.news.p7": 1})
    assert totals(con) == {"hero.show.news": 3, "hero.tap.news": 1}       # a kind, never an item or a person
    assert "news 1/3" in stats.fields(con, 1)["hero"].split("\n")
