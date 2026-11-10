"""Codex's security review of forum photos (Nov 10): each finding, fixed at its root."""
from __future__ import annotations

import io
from pathlib import Path

import httpx
from PIL import Image

from kbtu import db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)
from test_fchannel import CH, setup, tick
from test_fchannel_photos import TG, media_root, upload


def jpeg(w: int, h: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(out, "JPEG")
    return out.getvalue()


def files(cfg) -> set[str]:
    root = media_root(cfg)
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} if root.exists() else set()


def test_copy_deletion_does_not_break_photo_sending(env, monkeypatch):
    """5: the copies' loop named its group message `root` and the photo send read files under it."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    con.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", [("fchgone:77", "0"), ("fchcopy:77", "88")])  # a copy to delete this round
    ph = upload(c, 1)
    c.post("/api/forum-posts", headers=tma(1), json={"body": "A photo while a copy leaves", "photos": [ph["id"]]})
    tg = TG()
    tick(cfg, tg, con)
    assert len(tg.of("sendPhoto")) == 1
    con.close()


def test_album_found_after_lost_send_leaves_whole(env, monkeypatch):
    """1: a send whose answer was lost, found by its caption: every photo's message goes with the post."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    a, b = upload(c, 1), upload(c, 1)
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Two photos from the fair", "photos": [a["id"], b["id"]]}).json()
    assert logic.fchannel.sending(con, p["id"])
    logic.fchannel.lost(con)                                                                      # no answer came
    logic.fchannel.found(con, 500, "Two photos from the fair\n\n— Ann T")                    # its copy reached the group
    assert [r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ? ORDER BY n", (p["id"],))] == [500, 501]
    assert c.delete(f"/api/forum-posts/{p['id']}", headers=tma(1)).status_code == 204
    assert sorted(tuple(r) for r in con.execute("SELECT msg_id, photo FROM tg_unpost")) == [(500, 1), (501, 1)]
    con.close()


def test_thin_photo_refused_and_telegram_refusal_does_not_block(env, monkeypatch):
    """2: a strip Telegram never accepts is refused at upload (no files left); and a post Telegram refuses for good
    goes to a moderator while the next ones still go out."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    before = files(cfg)
    r = c.post("/api/forum-posts/photos", headers=tma(1), content=jpeg(30, 900))
    assert r.status_code == 400 and r.json()["message"] == "photo_shape"
    assert files(cfg) == before and not con.execute("SELECT 1 FROM fchan_photos").fetchone()

    class No(TG):
        def __call__(self, request):
            if request.url.path.endswith("/sendPhoto"):
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: PHOTO_INVALID_DIMENSIONS"})
            return super().__call__(request)
    ph = upload(c, 1)
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "A photo Telegram refuses", "photos": [ph["id"]]}).json()
    q = c.post("/api/forum-posts", headers=tma(2), json={"body": "Words after it still go out"}).json()
    tg = No()
    tick(cfg, tg, con)
    assert tuple(con.execute("SELECT status, why, tg_msg FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()) == ("held", "tgno", None)
    assert con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (q["id"],)).fetchone()[0] > 0
    assert [x["chat_id"] for x in tg.of("sendMessage")] == [CH]
    con.close()


def test_upload_quota_not_refunded(env, monkeypatch):
    """3, 4: the hour's uploads are counted on their own: putting photos on a post gives none back; the slot is taken
    before the decode; the count leaves with the account."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    monkeypatch.setattr(logic.fchannel, "PHOTO_UPLOADS", 3)
    ids = [upload(c, 1)["id"] for _ in range(3)]
    c.post("/api/forum-posts", headers=tma(1), json={"body": "Three photos from today", "photos": ids})
    before = files(cfg)
    r = c.post("/api/forum-posts/photos", headers=tma(1), content=jpeg(400, 300))
    assert r.status_code == 429 and files(cfg) == before                                          # refused before any file
    assert con.execute("SELECT 1 FROM meta WHERE key LIKE 'fchup:%'").fetchone()
    delete_now(c, cfg, tma(1))
    assert not con.execute("SELECT 1 FROM meta WHERE key LIKE 'fchup:%'").fetchone()
    con.close()


def test_failed_registration_drops_files(env, monkeypatch):
    """4: the files are written before the row; any failure of the row drops them."""
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    before = files(cfg)

    def boom(*a):
        raise logic.ApiError("conflict")
    monkeypatch.setattr(logic.fchannel, "add_photo", boom)
    assert c.post("/api/forum-posts/photos", headers=tma(1), content=jpeg(400, 300)).status_code == 409
    assert files(cfg) == before
    assert Path(cfg.db_path).exists()
