"""The schedule page's student ID (bot._page_sid) against Settings, and the admin's correction of a club role's title."""
from __future__ import annotations

import sqlite3

import pytest

from kbtu import admin, bot, config, db, logic
from kbtu.logic import account, queues
from test_core import env, login  # noqa: F401  (env: the fixture)


def _ali(env):
    c, cfg = env
    uid = login(c, 70, "ali")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET student_id = '26B000009' WHERE user_id = ?", (uid,))
    return cfg, con, uid, lambda: tuple(con.execute("SELECT student_id, course, fixed FROM students WHERE user_id = ?", (uid,)).fetchone())


def test_page_holds_the_lock_from_read_to_write(env, monkeypatch):
    """The ID moved by a PATCH between the year check and the write would make a 2nd-year a 1st-year: it has to wait."""
    cfg, con, uid, got = _ali(env)
    other = sqlite3.connect(cfg.db_path, isolation_level=None, timeout=0)
    real, parallel = bot.one, []

    def one(*a):
        row = real(*a)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            other.execute("UPDATE students SET student_id = '25B000009' WHERE user_id = ?", (uid,))
        parallel.append(1)
        return row
    monkeypatch.setattr(bot, "one", one)
    bot._page_sid(con, uid, "26B000001")
    assert parallel == [1] and got() == ("26B000001", 2, "student_id")


def test_page_writes_only_as_the_one_correction(env):
    cfg, con, uid, got = _ali(env)
    bot._page_sid(con, uid, "26B000001")                                 # the honest first fix: written, and it is the once
    assert got() == ("26B000001", 2, "student_id")
    bot._page_sid(con, uid, "26B000002")                                 # an edited page after it: left, a line for support
    assert got()[0] == "26B000001"
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'sid_page_fixed'").fetchone()[0] == 1


def test_one_counter_for_settings_and_page(env, monkeypatch):
    cfg, con, uid, got = _ali(env)
    bek = login(env[0], 71, "bek")["id"]
    con.execute("UPDATE students SET student_id = '26B000002' WHERE user_id = ?", (bek,))
    locked = []
    monkeypatch.setattr(account, "id_clash", lambda c, *a: locked.append(c.in_transaction))
    v = logic.Viewer(uid, "user", True)
    for _ in range(4):                                                   # 4 from Settings, all taken: counted under the lock
        with pytest.raises(logic.ApiError):
            logic.update_me(con, v, {"studentId": "26B000002"})
    assert locked == [True] * 4
    bot._page_sid(con, uid, "25B000001")                                 # the page's: the 5th
    assert logic.sid_tries(con, uid) == 5
    with pytest.raises(logic.ApiError) as e:                             # Settings is out of tries too
        logic.update_me(con, v, {"studentId": "26B000002"})
    assert e.value.message == "sid_tries"
    bot._page_sid(con, uid, "26B000001")                                 # and so is the page
    assert got()[0] == "26B000009" and logic.sid_tries(con, uid) == 5


def test_a_free_id_found_then_refused_still_counts(env):
    """A free ID written, then a bad field undoing it: without the count, an unlimited probe of which IDs are free."""
    cfg, con, uid, got = _ali(env)
    with pytest.raises(logic.ApiError) as e:
        logic.update_me(con, logic.Viewer(uid, "user", True), {"studentId": "26B000001", "city": "!"})
    assert e.value.message != "sid_taken" and got() == ("26B000009", 2, "") and logic.sid_tries(con, uid) == 1


def test_clash_alert_goes_with_the_account(env):
    c, cfg = env
    fon = login(c, 72, "fon")["id"]
    _, con, uid, _got = _ali(env)
    other = login(c, 73, "oth")["id"]
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE id = ?", (fon,))
    con.execute("UPDATE students SET student_id = '26B000002' WHERE user_id = ?", (other,))
    bot._page_sid(con, uid, "26B000002")
    alerts = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'sid_page_clash'").fetchone()[0]  # noqa: E731
    assert alerts() == 1
    logic.delete_me(con, logic.Viewer(uid, "user", True))
    assert alerts() == 0


def test_org_role_title(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    logic.create_org(con, None, "Chem", "C", "laptop_3d", False, "chem", "club")
    org = con.execute("SELECT id FROM orgs WHERE slug = 'chem'").fetchone()[0]
    add = "INSERT INTO org_roles (org_id, name, name_kk, name_en, src, ai_wait, color, level, rights, fixed, created_at) VALUES (?, ?, ?, ?, ?, ?, '#000000', 'member', 'memo', ?, 1)"
    rid = con.execute(add, (org, "syn", "kk-syn", "Mentor", "en", 1, 0)).lastrowid
    con.execute(add, (org, "taken", None, None, "ru", 0, 0))
    vice = con.execute("SELECT id FROM org_roles WHERE org_id = ? AND fixed = 1", (org,)).fetchone()[0]
    row = lambda: tuple(con.execute("SELECT name, name_kk, name_en, level, rights, hand FROM org_roles WHERE id = ?", (rid,)).fetchone())  # noqa: E731

    admin.main(["org-role", str(rid), "loan"])                           # Russian alone: the Kazakh stays the AI's
    assert row() == ("loan", "kk-syn", "Mentor", "member", "memo", "ru")
    queues.ai_save(con, "role", rid, {"title": "Mentor"}, "en", {"ru": {"title": "ai"}, "kk": {"title": "ai-kk"}})
    assert row()[:2] == ("loan", "ai-kk")
    admin.main(["org-role", str(rid), "loan", "kaz"])
    assert row() == ("loan", "kaz", "Mentor", "member", "memo", "kk,ru")
    con.execute("UPDATE org_roles SET ai_wait = 1 WHERE id = ?", (rid,))
    queues.ai_save(con, "role", rid, {"title": "Mentor"}, "en", {"ru": {"title": "ai"}, "kk": {"title": "ai-kk"}})
    assert row()[:2] == ("loan", "kaz")

    for bad, word in (([str(vice), "x"], "Vice"), (["99999", "x"], "no such"), ([str(rid), "taken"], "another role")):
        with pytest.raises(SystemExit) as e:
            admin.main(["org-role", *bad])
        assert word in str(e.value)
    assert row()[0] == "loan" and not con.in_transaction
