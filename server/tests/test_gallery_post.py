"""Posting to the Gallery (logic/gallery.py, GALLERY): KBTU's own photos beside the albums, under the author's name, at
once; an event only one I went to; 30 a day; three people's reports hide a photo, the reporter's at once; a moderator's
Delete and my own erase the files; my account's deletion takes my photos and their reports."""
from __future__ import annotations

import dataclasses
import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_gallery import ADMIN, AL, BO, CY, HEAD, NOW, _event, _ids


def _app(env, mode="all"):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}), gallery=mode)))
    c.ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, HEAD, AL, BO, CY)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, c.ids[HEAD], oid, "president", "test")
    c.media = Path(cfg.db_path).resolve().parent / "media"
    return c, con, oid


def _jpeg(seed=0, taken=None):
    raw, ex = io.BytesIO(), Image.Exif()
    if taken:
        ex.get_ifd(0x8769)[36867] = taken
    Image.new("RGB", (64, 48), (seed % 256, 90, 160)).save(raw, "JPEG", exif=ex.tobytes())
    return raw.getvalue()


def _post(c, who, seed=0, taken=None, **params):
    return c.post("/api/gallery", headers=tma(who), content=_jpeg(seed, taken), params=params)


def _going(con, c, eid, who, code):
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, 0, 0)",
                (eid, c.ids[who], code))


def test_flag_off_staff_everyone(env):
    for mode, ok in (("", ()), ("staff", (ADMIN,)), ("all", (ADMIN, AL))):
        c, con, _ = _app(env, mode)
        for who in (ADMIN, AL):
            assert (_post(c, who, seed=who).status_code == 200) == (who in ok), (mode, who)
            assert ("post" in c.get("/api/gallery", headers=tma(who)).json()) == (who in ok)
        assert _post(c, 999).status_code == 404  # a guest never
        if mode == "staff":  # a staff post: in the staff's feed alone
            assert len(_ids(c, ADMIN)) == 1 and _ids(c, AL) == []
        con.execute("DELETE FROM gallery_photos")


def test_shows_at_once_under_my_name_newest_taken_first(env):
    c, con, _ = _app(env)
    old = _post(c, AL, 1, taken="2024:09:01 10:00:00").json()
    new = _post(c, BO, 2).json()  # no EXIF: the upload's time
    assert old["by"] == "P82 T" and old["uid"] == c.ids[AL] and old["mine"] and old["canDelete"] and "event" not in old
    assert old["at"] == 1725166800  # 10:00 in Almaty
    feed = c.get("/api/gallery", headers=tma(CY)).json()["photos"]
    assert [p["id"] for p in feed] == [new["id"], old["id"]] and not feed[0]["mine"] and not feed[0]["canDelete"]
    page = c.get("/api/gallery", params={"limit": 1, "before": new["id"]}, headers=tma(CY)).json()
    assert [p["id"] for p in page["photos"]] == [old["id"]] and page["more"] is False
    assert _post(c, AL, 1, taken="2024:09:01 10:00:00").json()["id"] == old["id"] and len(_ids(c)) == 2  # the same photo again
    assert _post(c, AL, 3, taken="1970:01:01 00:00:00").json()["at"] > 1725166800  # a camera's unset clock: now


def test_attach_only_to_events_i_went_to(env):
    c, con, oid = _app(env)
    went, other = _event(con, c, oid, "Went"), _event(con, c, oid, "Other")
    ahead = _event(con, c, oid, "Ahead", starts_at=NOW + 86400, ends_at=NOW + 90000)
    _going(con, c, went, AL, "G-1")
    _going(con, c, ahead, AL, "G-2")
    assert c.get("/api/gallery", headers=tma(AL)).json()["post"] == {"events": [{"id": went, "title": "Went"}]}  # begun ones only
    assert _post(c, AL, 1, event=other).status_code == 403 and _post(c, AL, 1, event=ahead).status_code == 403
    assert _post(c, BO, 1, event=went).status_code == 403  # not signed up
    p = _post(c, AL, 1, event=went).json()
    assert p["event"] == {"id": went, "title": "Went"}
    album = c.get(f"/api/events/{went}", headers=tma(CY)).json()["photos"]
    assert [(x["id"], x["uid"]) for x in album] == [(p["id"], c.ids[AL])]  # in its album too
    assert _ids(c, CY) == [p["id"]]  # once in the feed
    # out of the album by the club's Head: out of the Gallery too (never left as a general photo)
    assert c.delete(f"/api/events/{went}/photos/{p['id']}", headers=tma(HEAD)).status_code == 200
    assert _ids(c, CY) == [] and not con.execute("SELECT 1 FROM gallery_photos").fetchone()


def test_a_day_limit(env, monkeypatch):
    c, con, _ = _app(env)
    monkeypatch.setattr(logic.gallery, "A_DAY", 2)
    assert _post(c, AL, 1).status_code == _post(c, AL, 2).status_code == 200
    r = _post(c, AL, 3)
    assert r.status_code == 429 and r.json()["message"] == "gallery"
    con.execute("UPDATE gallery_photos SET created_at = created_at - 86401")
    assert _post(c, AL, 3).status_code == 200


def test_three_reports_hide_reporter_at_once_moderator_decides(env):
    c, con, _ = _app(env)
    fid = _post(c, BO, 1).json()["id"]
    rep = lambda who, reason="rules": c.post("/api/reports", headers=tma(who), json={"target": "photo", "id": fid, "reason": reason}).status_code  # noqa: E731
    assert rep(BO) == 404 and rep(AL, "spam") == 204  # never my own
    assert rep(AL, "me") == 204 and _ids(c, AL) == [] and _ids(c, CY) == [fid]  # gone for me at once
    assert rep(CY) == 204 and _ids(c, HEAD) == [fid]
    assert rep(HEAD, "me") == 204 and _ids(c, ADMIN) == []  # three people: for everyone
    assert c.post("/api/reports", headers=tma(AL), json={"target": "user", "id": c.ids[BO], "reason": "me"}).status_code == 400  # a photo's own
    q = c.get("/api/admin/reports", headers=tma(ADMIN)).json()
    assert [(r["id"], r["where"], r["reasons"]) for r in q] == [(fid, {"kind": "gallery", "id": fid}, {"me": 2, "rules": 1})]
    assert c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": False}).status_code == 204  # Return
    assert _ids(c, ADMIN) == [fid] and _ids(c, AL) == [fid]
    # Delete: erased, its files from disk too
    path = con.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()[0]
    assert (c.media / f"{path}.webp").exists()
    assert rep(CY) == 204 and c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": True}).status_code == 204
    assert _ids(c, ADMIN) == [] and not (c.media / f"{path}.webp").exists() and not (c.media / f"{path}.t.webp").exists()
    assert not con.execute("SELECT 1 FROM files WHERE id = ?", (fid,)).fetchone()


def test_off_a_general_photo_cannot_be_reported(env):
    c, con, _ = _app(env)
    fid = _post(c, BO, 1).json()["id"]
    logic.gallery.MODE = ""
    assert c.post("/api/reports", headers=tma(AL), json={"target": "photo", "id": fid, "reason": "rules"}).status_code == 404
    assert _ids(c, AL) == []


def test_delete_mine_erases_files(env):
    c, con, _ = _app(env)
    fid = _post(c, AL, 1).json()["id"]
    path = con.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()[0]
    assert c.delete(f"/api/gallery/{fid}", headers=tma(BO)).status_code == 404  # not another's
    assert c.delete(f"/api/gallery/{fid}", headers=tma(AL)).status_code == 204
    assert _ids(c) == [] and not (c.media / f"{path}.webp").exists()


def test_account_deletion_takes_my_photos_and_their_reports(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid)
    _going(con, c, eid, AL, "G-1")
    general, attached = _post(c, AL, 1).json()["id"], _post(c, AL, 2, event=eid).json()["id"]
    assert c.post("/api/reports", headers=tma(BO), json={"target": "photo", "id": general, "reason": "me"}).status_code == 204
    paths = [r[0] for r in con.execute("SELECT path FROM files WHERE id IN (?, ?)", (general, attached))]
    _, photos = logic.delete_me(con, logic.Viewer(c.ids[AL], "user", True))
    assert sorted(photos) == sorted(paths)
    assert _ids(c, BO) == [] and not con.execute("SELECT 1 FROM gallery_photos UNION ALL SELECT 1 FROM event_photos").fetchone()
    assert not con.execute("SELECT 1 FROM reports WHERE target = 'photo'").fetchone()
    assert ("gallery_photos", "user_id") in logic._DEL_GONE
