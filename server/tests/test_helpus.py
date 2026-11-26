"""To the creator from inside the app (logic/helpus.py): an anonymous line keeps no author (schema, rows, outbox), its caps,
the signed offer with its own consent, the admin-only list with its unread count, the bot's templates, retention, deletion."""
from __future__ import annotations

import time

import pytest

from kbtu import db, logic, outbox
from kbtu.logic import helpus
from kbtu.logic.core import ApiError, Viewer
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env is a fixture)

A, B, BOSS = 1, 2, 3


def _setup(env):
    c, cfg = env
    ids = {u: login(c, u, n)["id"] for u, n in ((A, "ali"), (B, "bota"), (BOSS, "boss"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE id = ?", (ids[BOSS],))
    return c, cfg, con, ids


def test_anonymous_line_keeps_no_author(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    anon = lambda u, text: c.post("/api/helpus/anon", headers=tma(u), json={"body": text})  # noqa: E731
    assert anon(9, "a guest").status_code == 401
    for bad in ("", " x ", "y" * 1001, None, 5):
        assert c.post("/api/helpus/anon", headers=tma(A), json={"body": bad}).status_code == 400
    assert anon(A, "  the map is slow  ").status_code == 204
    # the schema holds nothing that points at a person or a minute
    assert [r[1] for r in con.execute("PRAGMA table_info(anon_feedback)")] == ["id", "body", "day"]
    assert ("anon_feedback" not in {t for t, _, _ in logic.account._user_fks(con)})
    row = con.execute("SELECT * FROM anon_feedback").fetchone()
    assert (row["body"], row["day"]) == ("the map is slow", (t0 + 5 * 3600) // 86400)
    # the creator's push: the template alone, tomorrow 09:00 Almaty, one for the day, nothing of the author in it
    assert anon(B, "second").status_code == 204
    told = [dict(r) for r in con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'anon_feedback'")]
    assert len(told) == 1 and told[0]["user_id"] == ids[BOSS] and told[0]["payload"] == "{}"
    assert told[0]["ref"] == f"afb:{row['day']}" and str(ids[A]) not in told[0]["ref"].split(":")
    assert told[0]["send_after"] == (row["day"] + 1) * 86400 + 4 * 3600 > t0
    text, button, start = outbox._render(con, told[0])
    assert text.startswith("\U0001f4dd") and "map" not in text and button and start == "voices"
    # nobody's audit line either
    assert not con.execute("SELECT 1 FROM audit_log WHERE actor_id = ? OR data LIKE '%map is slow%'", (ids[A],)).fetchone()
    # no per-person cap (it would have to know the person); the whole day's bound by the table's own rows
    assert [anon(A, f"more {i}").status_code for i in range(3)] == [204] * 3
    monkeypatch.setattr(helpus, "ANON_ALL", 5)
    assert anon(B, "the day is full").status_code == 429
    set_clock(monkeypatch, lambda: t0 + 86400)
    assert anon(A, "a new day").status_code == 204
    # the body is capped before it is parsed, and must be an object
    assert c.post("/api/helpus/anon", headers=tma(A), content=b'{"body": "' + b"x" * 9000 + b'"}').status_code == 400
    assert c.post("/api/helpus/anon", headers=tma(A), json=["x"]).status_code == 400


def test_anon_released_daily(env, monkeypatch):
    """Admin sees a day's lines once it is over, without ids, and marks read only what it was shown."""
    c, cfg, con, ids = _setup(env)
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    for text in ("one", "two"):
        assert c.post("/api/helpus/anon", headers=tma(A), json={"body": text}).status_code == 204
    get = lambda: c.get("/api/helpus", headers=tma(BOSS))  # noqa: E731
    assert get().json()["anon"] == [] and c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 0  # today: not yet
    assert "no-store" in get().headers["cache-control"]
    set_clock(monkeypatch, lambda: t0 + 86400)
    day = (t0 + 5 * 3600) // 86400
    got = get().json()["anon"]
    assert sorted(a["body"] for a in got) == ["one", "two"] and all(set(a) == {"body", "day", "new"} and a["new"] and a["day"] == day for a in got)
    assert c.post("/api/helpus/anon", headers=tma(B), json={"body": "today's"}).status_code == 204
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 2
    # read up to what it showed; a mark past the released days is clamped, today's line stays new tomorrow
    assert c.post("/api/helpus/seen", headers=tma(BOSS), json={"day": day + 5, "offer": 0}).status_code == 204
    assert c.post("/api/helpus/seen", headers=tma(BOSS), json={"day": "x", "offer": 0}).status_code == 400
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 0
    set_clock(monkeypatch, lambda: t0 + 2 * 86400)
    assert [(a["body"], a["new"]) for a in get().json()["anon"]][0] == ("today's", True)


def test_offer_list_and_unread(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    ok = {"kinds": ["design", "code"], "note": " I have a subscription ", "consent": helpus.CONSENT}
    offer = lambda u, **kw: c.post("/api/helpus/offer", headers=tma(u), json={**ok, **kw})  # noqa: E731
    assert offer(9).status_code == 401
    for bad in ({"kinds": []}, {"kinds": ["money"]}, {"kinds": "code"}, {"note": "n" * 501}, {"consent": "old"}, {"consent": None}):
        assert offer(A, **bad).status_code == 400, bad
    assert offer(A).status_code == 204
    assert c.post("/api/helpus/anon", headers=tma(B), json={"body": "too many taps"}).status_code == 204
    set_clock(monkeypatch, lambda: int(time.time()) + 86400)  # the anonymous line is released the next day
    # staff only: a student and a moderator get nothing
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (ids[B],))
    for u in (A, B):
        assert c.get("/api/helpus", headers=tma(u)).status_code == 403
        assert c.post("/api/helpus/seen", headers=tma(u), json={"day": 0, "offer": 0}).status_code == 403
        assert not c.get("/api/admin/inbox", headers=tma(u)).json().get("voices") if u == B else True
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 2
    con.execute("UPDATE users SET tg_username = 'ali_tg' WHERE id = ?", (ids[A],))  # Telegram's, as his launch brings it
    got = c.get("/api/helpus", headers=tma(BOSS)).json()
    o = got["offers"][0]
    assert (o["person"]["id"], o["username"], o["kinds"], o["note"], o["new"]) == (ids[A], "ali_tg", ["code", "design"], "I have a subscription", True)
    assert [(a["body"], a["new"]) for a in got["anon"]] == [("too many taps", True)] and "person" not in got["anon"][0]
    # another admin: the anonymous lines only, never the signed offers (they are the creator's)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ids[B],))
    other = c.get("/api/helpus", headers=tma(B)).json()
    assert other["offers"] == [] and len(other["anon"]) == 1 and c.get("/api/admin/inbox", headers=tma(B)).json()["voices"] == 1
    assert c.post("/api/helpus/seen", headers=tma(B), json={"day": got["anon"][0]["day"], "offer": o["id"]}).status_code == 204
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 1  # his offer mark is untouched
    con.execute("UPDATE users SET role = 'user' WHERE id = ?", (ids[B],))
    assert c.post("/api/helpus/seen", headers=tma(BOSS), json={"day": got["anon"][0]["day"], "offer": o["id"]}).status_code == 204
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 0
    assert offer(A, note="").status_code == 204
    got = c.get("/api/helpus", headers=tma(BOSS)).json()
    assert [(x["note"], x["new"]) for x in got["offers"]] == [(None, True), ("I have a subscription", False)]  # newest first
    assert c.get("/api/admin/inbox", headers=tma(BOSS)).json()["voices"] == 1
    # the bot: one push a day, a template with a button into Admin, never the words; none once he is not the creator
    told = [dict(r) for r in con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'helper_offer' ORDER BY id")]
    day = (int(time.time()) + 5 * 3600) // 86400  # the two offers came on two days (the clock moved one)
    assert [r["ref"] for r in told] == [f"ho:{day}", f"ho:{day + 1}"] and {r["user_id"] for r in told} == {ids[BOSS]} and told[0]["payload"] == "{}"
    text, button, start = outbox._render(con, told[0])
    assert text.startswith("\U0001f91d") and "subscription" not in text and button and start == "voices"
    con.execute("UPDATE users SET is_founder = 0 WHERE id = ?", (ids[BOSS],))
    assert outbox._render(con, told[0]) is None
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids[BOSS],))
    assert offer(A, kinds=["code"] * 7).status_code == 400
    # three a day
    assert [offer(A).status_code for _ in range(3)] == [204, 204, 429]
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'helper_offer'").fetchone()[0] == 2  # still one a day
    # gone with the account
    delete_now(c, cfg, tma(A))
    assert not con.execute("SELECT 1 FROM helper_offers").fetchone()
    # an offer racing the erasure: the student row is gone by the time it writes
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (ids[B],))
    with pytest.raises(ApiError):
        helpus.offer(con, Viewer(ids[B], "user", True), ok)
    assert con.execute("SELECT COUNT(*) FROM anon_feedback").fetchone()[0] == 1  # nobody's: it stays its 90 days


def test_retention(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    assert c.post("/api/helpus/anon", headers=tma(A), json={"body": "old words"}).status_code == 204
    assert c.post("/api/helpus/offer", headers=tma(A), json={"kinds": ["test"], "consent": helpus.CONSENT}).status_code == 204
    left = lambda: tuple(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("anon_feedback", "helper_offers"))  # noqa: E731
    seen = lambda: tuple(len(x) for x in c.get("/api/helpus", headers=tma(BOSS)).json().values())  # noqa: E731
    for days, want in ((89, (1, 1)), (90, (0, 1)), (180, (0, 1)), (181, (0, 0))):
        set_clock(monkeypatch, lambda: t0 + days * 86400)  # noqa: B023
        assert seen() == want, days  # the reads cut off before the sweep runs
        with db.tx(con):
            helpus.sweep(con)
        assert left() == want, days
