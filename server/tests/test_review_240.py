"""Inkar's server review (issue #240): each test is a failing case from the review, fixed."""
from __future__ import annotations

import contextlib
import json
import time

import pytest

from kbtu import casting, db, logic, roster
from kbtu.logic import ApiError, Viewer, organizing
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def _con(cfg):
    return db.connect(cfg.db_path)


def _club(con, pres: int) -> None:
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres,))


def _event(con, eid: int, starts: int, ends: int | None = None) -> None:
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_at, updated_at)
        VALUES (?, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (eid, starts, ends))


def _racing(monkeypatch, module, sneak) -> None:
    """Two taps at once: the other request's write lands a moment before this one takes the write lock."""
    real, done = module.tx, []

    @contextlib.contextmanager
    def tx(con, **k):
        if not done:
            done.append(1)
            sneak(con)
        with real(con, **k) as c:
            yield c
    monkeypatch.setattr(module, "tx", tx)


def _code(fn, *args) -> str:
    with pytest.raises(ApiError) as e:
        fn(*args)
    return e.value.code


# ------------------------------------------------------------ roster

def _pending(con, oid: int, key: str, **fields) -> None:
    values = {"key": key, "org_id": oid, "sheet": "S", "role": "member", "created_at": 0, **fields}
    con.execute(f"INSERT INTO roster_pending ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})", tuple(values.values()))


def test_roster_open_takes_the_write_lock_only_for_a_row_that_joins(env, monkeypatch):
    """A banned club's row, or a row waiting for a claim, made every /api/me run roster.match (a write lock, no join)."""
    c, cfg = env
    pres, ann = login(c, 20, "pres"), login(c, 21, "ann")
    con = _con(cfg)
    _club(con, pres["id"])
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'laptop_3d', 0)")
    con.execute("UPDATE students SET email = 'ann@kbtu.kz', ms_oid = 'ann', ms_profile = ? WHERE user_id = ?",
                (json.dumps({"givenName": "Ann", "surname": "Testov"}), ann["id"]))
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (1, ?, 0)", (ann["id"],))
    _pending(con, 1, "banned", full_name="Testov Ann", email="ann@kbtu.kz")        # verified, but the club banned her
    _pending(con, 2, "claim", full_name="Someone Else", email="ann@kbtu.kz")       # her e-mail, another name: a claim
    calls = []
    monkeypatch.setattr(roster, "match", lambda *a: calls.append(a) or [])
    assert c.get("/api/me", headers=tma(21)).status_code == 200
    assert calls == [] and not roster.due(con, ann["id"])
    assert [r["org_id"] for r in roster.asks(con, ann["id"])] == [2]                # the banned club's row isn't hers to claim
    _pending(con, 2, "mine", full_name="Testov Ann", email="ann@kbtu.kz")          # a verified row: the match runs
    assert roster.due(con, ann["id"])
    c.get("/api/me", headers=tma(21))
    assert len(calls) == 1


# ------------------------------------------------------------ organizing: per-day caps under the write lock

def test_post_update_cap_counted_under_the_lock(env, monkeypatch):
    c, cfg = env
    pres = login(c, 20, "pres")
    con = _con(cfg)
    _club(con, pres["id"])
    _event(con, 1, int(time.time()) + 86400)
    v = Viewer(pres["id"], "user", True)
    for _ in range(organizing.UPDATES_A_DAY - 1):
        con.execute("INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (1, ?, 'news', ?)", (pres["id"], logic.now()))
    _racing(monkeypatch, organizing, lambda con: con.execute(
        "INSERT INTO event_updates (event_id, author_id, body, created_at) VALUES (1, ?, 'other tap', ?)", (pres["id"], logic.now())))
    assert _code(logic.post_update, con, v, 1, "Room changed") == "rate_limited"
    assert con.execute("SELECT COUNT(*) FROM event_updates").fetchone()[0] == organizing.UPDATES_A_DAY


def test_invite_friend_cap_counted_under_the_lock(env, monkeypatch):
    c, cfg = env
    pres, ali, f1, f2 = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "fff"), login(c, 23, "ggg")
    con = _con(cfg)
    _club(con, pres["id"])
    _event(con, 1, int(time.time()) + 86400)
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", tuple(sorted((ali["id"], f1["id"]))))
    monkeypatch.setattr(organizing, "INVITES_A_DAY", 1)
    _racing(monkeypatch, organizing, lambda con: con.execute(
        "INSERT INTO friend_invites (from_id, to_id, event_id, created_at) VALUES (?, ?, 1, ?)", (ali["id"], f2["id"], logic.now())))
    assert _code(logic.invite_friend, con, Viewer(ali["id"], "user", True), 1, f1["id"]) == "rate_limited"
    assert con.execute("SELECT COUNT(*) FROM friend_invites").fetchone()[0] == 1


def test_album_room_counted_under_the_lock(env, monkeypatch):
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = _con(cfg)
    _club(con, pres["id"])
    t = int(time.time())
    _event(con, 1, t - 3600, t + 3600)
    other = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at)
        VALUES ('a', 'event_photo', 'image/webp', 1, 'ab/a', ?, 0)""", (ali["id"],)).lastrowid
    monkeypatch.setattr(organizing, "ALBUM_EACH", 1)
    _racing(monkeypatch, organizing, lambda con: con.execute(
        "INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (1, ?, 1, ?)", (other, ali["id"])))
    saved = {"sha256": "b", "bytes": 1, "width": 1, "height": 1, "path": "ab/b", "color": "#000000"}
    assert _code(logic.add_album_photo, con, Viewer(ali["id"], "user", True), 1, saved) == "forbidden"
    assert con.execute("SELECT COUNT(*) FROM event_photos").fetchone()[0] == 1


# ------------------------------------------------------------ account

def test_new_photo_while_a_takedown_holds_the_old_one(env):
    """The old avatar is held by a take-down's undo: replacing or dropping it was a FOREIGN KEY 500."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = _con(cfg)
    v = Viewer(ali["id"], "user", True)

    def avatar(sha: str) -> int:
        return con.execute("""INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at)
            VALUES (?, 'avatar', 'image/webp', 1, ?, ?, 0)""", (sha, f"ab/{sha}", ali["id"])).lastrowid
    a = avatar("a")
    con.execute("UPDATE users SET avatar_file_id = ?, avatar_tg = 0 WHERE id = ?", (a, ali["id"]))
    con.execute("INSERT INTO takedowns (target, target_id, user_id, data, file_id, at) VALUES ('user', ?, ?, '{}', ?, ?)",
                (ali["id"], ali["id"], a, logic.now()))
    assert logic.set_photo(con, v, {"sha256": "b", "bytes": 1, "width": 1, "height": 1, "path": "ab/b", "color": "#000000"}) == []
    assert con.execute("SELECT 1 FROM files WHERE id = ?", (a,)).fetchone()   # kept for the undo
    con.execute("UPDATE users SET avatar_file_id = ? WHERE id = ?", (a, ali["id"]))
    assert logic.drop_my_photo(con, v) == []
    assert con.execute("SELECT avatar_file_id FROM users WHERE id = ?", (ali["id"],)).fetchone()[0] is None


# ------------------------------------------------------------ seats

def test_guard_read_non_ascii_is_forbidden():
    assert _code(logic.guard_read, b"k" * 32, "abc.ééé") == "forbidden"


def test_cal_token_first_two_taps_keep_one(env, monkeypatch):
    """Both see none; the other tap's token is written first: this one answers with it, never overwrites it."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = _con(cfg)

    def other_tap_first(n):
        con.execute("UPDATE users SET cal_token = 'first' WHERE id = ?", (ali["id"],))
        return "second"
    monkeypatch.setattr(logic.seats.secrets, "token_urlsafe", other_tap_first)
    assert logic.cal_token(con, Viewer(ali["id"], "user", True)) == "first"
    assert con.execute("SELECT cal_token FROM users WHERE id = ?", (ali["id"],)).fetchone()[0] == "first"


# ------------------------------------------------------------ moderation

def test_undo_brings_an_album_photo_back_to_every_album(env):
    c, cfg = env
    pres, ali, rep, mod = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "rep"), login(c, 23, "mod")
    con = _con(cfg)
    _club(con, pres["id"])
    t = int(time.time())
    _event(con, 1, t - 7200)
    _event(con, 2, t - 3600)
    f = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at)
        VALUES ('p', 'event_photo', 'image/webp', 1, 'ab/p', ?, 0)""", (ali["id"],)).lastrowid
    con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (1, ?, 1, ?), (2, ?, 1, ?)", (f, ali["id"], f, ali["id"]))
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'photo', ?, 'spam', 0)", (rep["id"], f))
    m = Viewer(mod["id"], "moderator", True)
    logic.resolve_report(con, m, "photo", f, True)
    assert not con.execute("SELECT 1 FROM event_photos").fetchone()
    logic.restore(con, m, "photo", f)
    assert [r[0] for r in con.execute("SELECT event_id FROM event_photos WHERE file_id = ? ORDER BY event_id", (f,))] == [1, 2]
    assert not con.execute("SELECT 1 FROM takedowns").fetchone()


# ------------------------------------------------------------ clubs

def test_subscribe_checks_the_club_before_the_row(env):
    c, cfg = env
    pres = login(c, 20, "pres")
    login(c, 21, "ali")
    con = _con(cfg)
    _club(con, pres["id"])
    assert c.put("/api/orgs/999/subscription", headers=tma(21)).status_code == 404   # gone: was a FOREIGN KEY 500
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert c.put("/api/orgs/1/subscription", headers=tma(21)).status_code == 404
    assert not con.execute("SELECT 1 FROM subscriptions").fetchone()                  # a refusal keeps no row


# ------------------------------------------------------------ casting

def test_drop_slot_keeps_a_slot_booked_a_moment_ago(env, monkeypatch):
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = _con(cfg)
    _club(con, pres["id"])
    con.execute("INSERT INTO rounds (id, org_id, title, closes_at, created_at) VALUES (1, 1, 'r', 9999999999, 0)")
    con.execute("INSERT INTO round_slots (id, round_id, starts_at, minutes) VALUES (5, 1, 9999999000, 15)")
    app_id = con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, stage, created_at, updated_at)
        VALUES (1, ?, 'dev', '{}', 'next', 0, 0)""", (ali["id"],)).lastrowid
    _racing(monkeypatch, casting, lambda con: con.execute("UPDATE round_apps SET slot_id = 5 WHERE id = ?", (app_id,)))
    assert _code(casting.drop_slot, con, Viewer(pres["id"], "user", True), 5) == "conflict"
    assert con.execute("SELECT slot_id FROM round_apps WHERE id = ?", (app_id,)).fetchone()[0] == 5
