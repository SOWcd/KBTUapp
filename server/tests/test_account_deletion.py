"""Account erasure includes indirect identifiers and retries filesystem cleanup after a restart."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kbtu import app, bot, db, logic, media
from test_core import delete_now, env, login, tma  # noqa: F401


def _file(con, cfg, uid, path, kind="event_cover"):
    root = Path(cfg.db_path).parent / ("receipts" if kind == "receipt" else "media")
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    for ext in (".webp", ".t.webp", ".jpg"):
        (root / f"{path}{ext}").write_bytes(b"synthetic image")
    return con.execute("""INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at)
        VALUES (?, ?, 'image/webp', 15, ?, ?, 0)""", (path, kind, path, uid)).lastrowid


@pytest.mark.parametrize("photos", [False, True])
def test_deletion_removes_unused_uploads_but_keeps_live_pictures(env, photos):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    other = login(c, 22, "zhan")["id"]
    con = db.connect(cfg.db_path)
    unused = _file(con, cfg, uid, "aa/unused")
    logo = _file(con, cfg, uid, "aa/logo")
    _file(con, cfg, uid, "aa/shared")
    _file(con, cfg, other, "aa/shared")
    _file(con, cfg, uid, "aa/telegram")
    con.execute("UPDATE users SET tg_photo_path = 'aa/telegram' WHERE id = ?", (other,))
    con.execute("""INSERT INTO orgs (slug, kind, name, short, emoji, logo_file_id, created_at)
        VALUES ('club', 'club', 'Club', 'C', 'laptop_3d', ?, 0)""", (logo,))
    assert c.get("/media/aa/unused.webp").status_code == 200
    assert c.post("/api/me/delete", headers=tma(21), json={"photos": photos}).status_code == 200
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (uid,))
    bot.purge(cfg, con)
    assert not con.execute("SELECT 1 FROM files WHERE id = ?", (unused,)).fetchone()
    for ext in (".webp", ".t.webp", ".jpg"):
        assert c.get(f"/media/aa/unused{ext}").status_code == 404
        for kept in ("logo", "shared", "telegram"):
            assert c.get(f"/media/aa/{kept}{ext}").status_code == 200


def test_deletion_scrubs_attendance_identifiers_written_by_others(env):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    other = login(c, 22, "zhan")["id"]
    con = db.connect(cfg.db_path)
    actions = ("checkin_hand", "checkin_unhand", "seat_remove", "came_by_hand", "unseat_by_hand")
    untouched = []
    for action in actions:
        for who in (uid, other):
            data = {"who": f"u{who}"} if action.startswith("checkin_") else {"user": who, "event": 1}
            logic.log_action(con, other, action, "qr:1" if action.startswith("checkin_") else "registration:1", json.dumps(data))
            if who == other:
                untouched.append(data)
    delete_now(c, cfg, tma(21))
    saved = [json.loads(r[0]) for r in con.execute("SELECT data FROM audit_log WHERE action IN (?, ?, ?, ?, ?) ORDER BY id", actions)]
    assert saved[::2] == [{}] * len(actions)
    assert saved[1::2] == untouched


@pytest.mark.parametrize("sent", [None, 1])
def test_deletion_erases_organizer_requests_in_other_peoples_queues(env, sent):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    other = login(c, 22, "zhan")["id"]
    con = db.connect(cfg.db_path)
    refs = [f"oa:1:{uid}", f"oa:2:{uid}", f"oa:{uid}:{other}", f"oa:1:{uid}0"]
    for ref in refs:
        con.execute("""INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after, sent_at)
            VALUES (?, 'org_ask', ?, '{"nick":"example_organizer"}', 0, ?)""", (other, ref, sent))
    delete_now(c, cfg, tma(21))
    assert {r[0] for r in con.execute("SELECT ref FROM bot_outbox WHERE kind = 'org_ask'")} == set(refs[2:])


@pytest.mark.parametrize("resume", ["startup", "round"])
def test_committed_deletion_retries_file_cleanup_after_restart(env, monkeypatch, resume):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    other = login(c, 22, "zhan")["id"]
    con = db.connect(cfg.db_path)
    avatar = _file(con, cfg, uid, "aa/avatar", "avatar")
    _file(con, cfg, uid, "aa/receipt", "receipt")
    _file(con, cfg, uid, "aa/reused")
    con.execute("UPDATE users SET avatar_file_id = ?, delete_at = 0 WHERE id = ?", (avatar, uid))
    logic.delete_due(con)  # commit, then lose the returned paths as a stopped process would
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    con.close()
    con = db.connect(cfg.db_path)
    _file(con, cfg, other, "aa/reused")  # a live reference added before the retry must win
    _file(con, cfg, other, "aa/receipt")  # the same hash in public media cannot retain a private receipt
    home = Path(cfg.db_path).parent
    drop = media.drop

    def interrupted(root, paths):
        if "aa/avatar" in paths:
            (root / "aa/avatar.webp").unlink(missing_ok=True)
            raise OSError("interrupted unlink")
        drop(root, paths)

    with monkeypatch.context() as patch:
        patch.setattr(media, "drop", interrupted)
        with pytest.raises(OSError, match="interrupted unlink"):
            bot.purge(cfg, con)
    assert con.execute("SELECT 1 FROM meta WHERE key GLOB 'del-file:*'").fetchone()
    if resume == "startup":
        app.create(cfg)  # the replay checkpoint is already committed: only pending files remain
    else:
        bot.purge(cfg, con)
    for ext in (".webp", ".t.webp", ".jpg"):
        assert not (home / "media" / f"aa/avatar{ext}").exists()
        assert not (home / "receipts" / f"aa/receipt{ext}").exists()
        assert (home / "media" / f"aa/receipt{ext}").exists()
        assert (home / "media" / f"aa/reused{ext}").exists()
    assert not con.execute("SELECT 1 FROM meta WHERE key GLOB 'del-file:*'").fetchone()
