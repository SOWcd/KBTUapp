"""Posting to the Gallery (logic/gallery.py, GALLERY): KBTU's own photos beside the albums, under the author's name, at
once; an event's album only on the album's own rules; 30 uploads a day (attempts); three people's reports hide a photo,
the reporter's at once; a moderator's Delete is kept 30 days for an undo; my own Delete and my account's deletion erase."""
from __future__ import annotations

import dataclasses
import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_gallery import ADMIN, AL, BO, CY, HEAD, NOW, _event, _ids, _photo


def _app(env, mode="all"):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}), gallery=mode)))
    c.ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, HEAD, AL, BO, CY)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, c.ids[HEAD], oid, "president", "test")
    c.media = Path(cfg.db_path).resolve().parent / "media"
    return c, con, oid


def _jpeg(seed=0):
    raw = io.BytesIO()
    Image.new("RGB", (64, 48), (seed * 23 % 256, seed * 7 % 256, 160)).save(raw, "JPEG")  # far apart: near colours encode alike
    return raw.getvalue()


def _post(c, who, seed=0, **params):
    if "event" not in params:
        params.setdefault("topic", "other")  # a photo of no event says its topic; topic=None: none said
    return c.post("/api/gallery", headers=tma(who), content=_jpeg(seed), params={k: x for k, x in params.items() if x is not None})


def _came(con, c, eid, who, code):
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
        VALUES (?, ?, 'going', ?, 0, 0, ?)""", (eid, c.ids[who], code, NOW - 3600))


def _path(con, fid):
    return con.execute("SELECT path FROM files WHERE id = ?", (fid,)).fetchone()[0]


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


def test_off_nothing_new(env):
    """GALLERY unset: production as before, but for the third reporter."""
    c, con, oid = _app(env, "")
    eid = _event(con, c, oid)
    fid = _photo(con, eid, c.ids[AL])
    assert c.delete(f"/api/gallery/{fid}", headers=tma(AL)).status_code == 404  # my album photo stays
    rep = lambda reason: c.post("/api/reports", headers=tma(BO), json={"target": "photo", "id": fid, "reason": reason}).status_code  # noqa: E731
    assert rep("me") == rep("rules") == 400 and rep("spam") == 204
    p = c.get("/api/gallery", headers=tma(AL)).json()["photos"][0]
    assert p["canDelete"] is False and "at" not in p and "uid" not in p and "post" not in c.get("/api/gallery", headers=tma(AL)).json()


def test_shows_at_once_under_my_name_newest_first(env):
    c, con, _ = _app(env)
    old = _post(c, AL, 1).json()
    new = _post(c, BO, 2).json()
    assert old["by"] == "P82 T" and old["uid"] == c.ids[AL] and old["mine"] and old["canDelete"] and "event" not in old and old["at"] >= NOW
    feed = c.get("/api/gallery", headers=tma(CY)).json()["photos"]
    assert [p["id"] for p in feed] == [new["id"], old["id"]] and not feed[0]["mine"] and not feed[0]["canDelete"]
    page = c.get("/api/gallery", params={"limit": 1, "before": new["id"]}, headers=tma(CY)).json()
    assert [p["id"] for p in page["photos"]] == [old["id"]] and page["more"] is False
    assert _post(c, AL, 1).json()["id"] == old["id"] and len(_ids(c)) == 2  # the same photo again: the one there


def test_attach_on_the_albums_rules(env):
    c, con, oid = _app(env)
    went, other = _event(con, c, oid, "Went"), _event(con, c, oid, "Other")
    ahead = _event(con, c, oid, "Ahead", starts_at=NOW + 86400, ends_at=NOW + 90000)
    old = _event(con, c, oid, "Old", starts_at=NOW - 30 * 86400, ends_at=NOW - 29 * 86400)
    _came(con, c, went, AL, "G-1")
    _came(con, c, old, AL, "G-3")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', 'G-2', 0, 0)",
                (ahead, c.ids[AL]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', 'G-4', 0, 0)",
                (went, c.ids[BO]))  # signed up, never came
    assert c.get("/api/gallery", headers=tma(AL)).json()["post"] == {"events": [{"id": went, "title": "Went"}]}  # its album open now
    for eid in (other, ahead, old):
        assert _post(c, AL, 1, event=eid).status_code == 403
    assert _post(c, BO, 1, event=went).status_code == 403  # a no-show
    p = _post(c, AL, 1, event=went).json()
    assert p["event"] == {"id": went, "title": "Went"}
    album = c.get(f"/api/events/{went}", headers=tma(CY)).json()["photos"]
    assert [(x["id"], x["uid"]) for x in album] == [(p["id"], c.ids[AL])]  # in its album too
    assert _ids(c, CY) == [p["id"]]  # once in the feed
    # the guest's album share (10) counts these too
    con.execute("UPDATE meta SET value = '0' WHERE key LIKE 'gal:%'")
    for n in range(2, 11):
        assert _post(c, AL, n, event=went).status_code == 200
    assert _post(c, AL, 11, event=went).status_code == 403
    # out of the album by the club's Head: still the student's, a plain KBTU photo
    assert c.delete(f"/api/events/{went}/photos/{p['id']}", headers=tma(HEAD)).status_code == 200
    assert p["id"] in _ids(c, CY) and con.execute("SELECT event_id FROM gallery_photos WHERE file_id = ?", (p["id"],)).fetchone()[0] is None
    # the event deleted (it was open to everyone): the posts stay, plain
    logic.organizing._delete_event(con, went)
    assert len(_ids(c, CY)) == 10 and not con.execute("SELECT 1 FROM gallery_photos WHERE event_id IS NOT NULL").fetchone()


def test_a_closed_events_posts_never_turn_public(env):
    """Posted to an album not every student sees (members, leaders, a meeting, an initiative off the afisha): the event
    deleted, or the photo out of its album, or a take-down undone after the event went: never a plain photo for all."""
    c, con, oid = _app(env)
    small = logic.create_org(con, None, "Small", "SM", "crown_3d", False)
    logic.set_role(con, None, c.ids[HEAD], small, "president", "test")
    files = lambda: sorted(p.name for p in c.media.rglob("*.webp"))  # noqa: E731
    seed = 0
    for n, (org, kw) in enumerate(((oid, {"visibility": "members"}), (oid, {"visibility": "leaders", "leaders_from": "president"}),
                                   (oid, {"meeting": 1}), (small, {}))):
        eid = _event(con, c, org, f"Closed {n}", **kw)
        fids = [_post(c, HEAD, seed := seed + 1, event=eid) for _ in range(3)]
        assert [r.status_code for r in fids] == [200] * 3, (kw, fids[0].text)
        gone, down, kept = (r.json()["id"] for r in fids)
        assert len(files()) == 6  # each with its thumbnail
        # out of the album by the team: gone, not plain
        assert c.delete(f"/api/events/{eid}/photos/{gone}", headers=tma(HEAD)).status_code == 200
        assert not con.execute("SELECT 1 FROM gallery_photos WHERE file_id = ?", (gone,)).fetchone() and len(files()) == 4
        # taken down by a moderator, then the event deleted: the undo brings nothing back
        con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'photo', ?, 'rules', ?)", (c.ids[AL], down, NOW))
        assert c.post(f"/api/admin/reports/photo/{down}", headers=tma(ADMIN), json={"remove": True}).status_code == 204
        _, photos = logic.organizing._delete_event(con, eid)
        assert len(photos) == 1 and not con.execute("SELECT 1 FROM gallery_photos").fetchone()
        for who in (CY, HEAD, ADMIN):
            assert _feed(c, who) == [] and _feed(c, who, topic="other") == [], (kw, who)
        assert c.post(f"/api/admin/taken-down/photo/{down}/restore", headers=tma(ADMIN)).status_code == 204
        assert not con.execute("SELECT 1 FROM gallery_photos").fetchone() and _feed(c, CY) == []
        assert not con.execute("SELECT 1 FROM files WHERE id IN (?, ?, ?)", (gone, down, kept)).fetchone()
        for f in list(c.media.rglob("*.webp")):
            f.unlink()  # _delete_event returns the kept one's path for the caller; the test is the caller
        con.execute("DELETE FROM meta WHERE key LIKE 'gal:%'")


def test_an_open_events_take_down_undone_after_it_went_is_plain(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid)
    fid = _post(c, HEAD, 1, event=eid).json()["id"]
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) VALUES (?, 'photo', ?, 'rules', ?)", (c.ids[AL], fid, NOW))
    assert c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": True}).status_code == 204
    logic.organizing._delete_event(con, eid)
    assert c.post(f"/api/admin/taken-down/photo/{fid}/restore", headers=tma(ADMIN)).status_code == 204
    assert _feed(c, CY) == [fid] and _feed(c, CY, topic="other") == [fid]
    # one taken down before this fix (no "open" on its row): stays gone
    fid = _post(c, HEAD, 2, event=(eid := _event(con, c, oid))).json()["id"]
    logic.gallery.take_down(con, fid)
    con.execute("UPDATE takedowns SET data = json_remove(data, '$.gallery.open') WHERE target_id = ?", (fid,))
    logic.organizing._delete_event(con, eid)
    assert c.post(f"/api/admin/taken-down/photo/{fid}/restore", headers=tma(ADMIN)).status_code == 204
    assert fid not in _feed(c, CY)


def test_the_admins_delete_takes_a_closed_events_posts(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid, "Secret", visibility="members", meeting=1)
    fid = _post(c, HEAD, 1, event=eid).json()["id"]
    assert fid not in _feed(c, CY)
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(ADMIN)).status_code in (200, 204)
    assert _feed(c, CY) == []  # hidden for its Undo day
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = ?", (f"evdel:{eid}",))
    _, photos = logic.events_gone(con)
    assert len(photos) == 1 and _feed(c, CY) == [] and _feed(c, CY, topic="other") == [] and not con.execute("SELECT 1 FROM gallery_photos").fetchone()


def test_albums_only_of_events_open_to_every_student(env):
    """The shelf says no more than the feed: a draft, a cancelled or hidden event, members' or leaders' own, a meeting,
    a first-year one for who hides them, an initiative off the afisha: no album, for the staff and the club's own too;
    a photo three people reported isn't counted."""
    c, con, oid = _app(env)
    ok = _event(con, c, oid)
    a, b = _photo(con, ok, c.ids[BO]), _photo(con, ok, c.ids[BO])
    for kw in ({"status": "draft"}, {"status": "cancelled"}, {"hidden_at": NOW}, {"visibility": "members"},
               {"visibility": "leaders", "leaders_from": "president"}, {"meeting": 1}, {"first_year": 1}):
        _photo(con, _event(con, c, oid, **kw), c.ids[BO])
    con.execute("UPDATE users SET hide_first_year = 1")
    small = logic.create_org(con, None, "Small", "SM", "crown_3d", False)
    _photo(con, _event(con, c, small), c.ids[BO])
    albums = lambda who: [(x["id"], x["n"]) for x in c.get("/api/gallery", headers=tma(who)).json()["albums"]]  # noqa: E731
    for who in (AL, HEAD, ADMIN):
        assert albums(who) == [(ok, 2)], who
    for n, who in enumerate((AL, CY, HEAD)):
        assert c.post("/api/reports", headers=tma(who), json={"target": "photo", "id": b, "reason": "rules"}).status_code == 204
        assert albums(ADMIN) == [(ok, 1 if n == 2 else 2)] and albums(who) == [(ok, 1)]  # mine at once, everyone's at three
    assert c.post("/api/reports", headers=tma(AL), json={"target": "photo", "id": a, "reason": "rules"}).status_code == 204
    assert albums(AL) == [] and albums(BO) == [(ok, 1)]  # nothing of it left for me: no album


def test_a_day_counts_attempts(env, monkeypatch):
    c, con, _ = _app(env)
    monkeypatch.setattr(logic.gallery, "A_DAY", 2)
    first = _post(c, AL, 1).json()["id"]
    assert _post(c, AL, 2).status_code == 200
    assert c.delete(f"/api/gallery/{first}", headers=tma(AL)).status_code == 204
    r = _post(c, AL, 3)
    assert r.status_code == 429 and r.json()["message"] == "gallery"  # a deleted one gives nothing back
    con.execute("UPDATE meta SET key = 'gal:0:0' WHERE key LIKE 'gal:%'")  # the next day
    assert _post(c, AL, 3).status_code == 200


def test_a_refused_upload_leaves_no_file(env, monkeypatch):
    c, con, _ = _app(env)
    files = lambda: sorted(p.name for p in c.media.rglob("*.webp")) if c.media.exists() else []  # noqa: E731
    before = files()
    monkeypatch.setattr(logic.gallery, "post", lambda *a: (_ for _ in ()).throw(logic.ApiError("forbidden")))
    assert _post(c, AL, 1).status_code == 403 and files() == before


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
    # Delete: out, its files kept 30 days for the undo
    assert rep(CY) == 204 and c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": True}).status_code == 204
    assert _ids(c, ADMIN) == [] and (c.media / f"{_path(con, fid)}.webp").exists()
    assert c.post(f"/api/admin/taken-down/photo/{fid}/restore", headers=tma(ADMIN)).status_code == 204
    assert _ids(c, CY) == [fid] and c.get("/api/gallery", headers=tma(CY)).json()["photos"][0]["uid"] == c.ids[BO]


def test_off_a_general_photo_cannot_be_reported(env):
    c, con, _ = _app(env)
    fid = _post(c, BO, 1).json()["id"]
    logic.gallery.MODE = ""
    assert c.post("/api/reports", headers=tma(AL), json={"target": "photo", "id": fid, "reason": "spam"}).status_code == 404
    assert _ids(c, AL) == []


def test_delete_mine_erases_files_and_reports(env):
    c, con, _ = _app(env)
    fid = _post(c, AL, 1).json()["id"]
    path = _path(con, fid)
    assert c.post("/api/reports", headers=tma(BO), json={"target": "photo", "id": fid, "reason": "me"}).status_code == 204
    assert c.delete(f"/api/gallery/{fid}", headers=tma(BO)).status_code == 404  # not another's
    assert c.delete(f"/api/gallery/{fid}", headers=tma(AL)).status_code == 204
    assert _ids(c) == [] and not (c.media / f"{path}.webp").exists()
    # the next file may take its id: it inherits no reports
    assert not con.execute("SELECT 1 FROM reports WHERE target = 'photo' AND target_id = ?", (fid,)).fetchone()


def test_account_deletion_takes_my_photos_and_their_reports(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid)
    _came(con, c, eid, AL, "G-1")
    general, attached = _post(c, AL, 1).json()["id"], _post(c, AL, 2, event=eid).json()["id"]
    assert c.post("/api/reports", headers=tma(BO), json={"target": "photo", "id": general, "reason": "me"}).status_code == 204
    paths = [_path(con, general), _path(con, attached)]
    _, photos = logic.delete_me(con, logic.Viewer(c.ids[AL], "user", True))
    assert sorted(photos) == sorted(paths)
    assert _ids(c, BO) == [] and not con.execute("SELECT 1 FROM gallery_photos UNION ALL SELECT 1 FROM event_photos").fetchone()
    assert not con.execute("SELECT 1 FROM reports WHERE target = 'photo'").fetchone()
    assert not con.execute("SELECT 1 FROM meta WHERE key LIKE 'gal:%'").fetchone()
    assert ("gallery_photos", "user_id") in logic._DEL_GONE


# ---- photos of no event: a topic each (gallery.TOPICS), the feed's filter

def _feed(c, who=CY, **params):
    r = c.get("/api/gallery", headers=tma(who), params=params)
    return [p["id"] for p in r.json()["photos"]] if r.status_code == 200 else r.status_code


def test_topic_of_a_photo_of_no_event(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid)
    _came(con, c, eid, AL, "G-1")
    files = lambda: sorted(p.name for p in c.media.rglob("*.webp")) if c.media.exists() else []  # noqa: E731
    for bad in ("events", "CAMPUS", "x", ""):
        assert _post(c, AL, 1, topic=bad).status_code == 400, bad
    assert _post(c, AL, 1, event=eid, topic="campus").status_code == 400  # an event's photo has no topic
    assert files() == [] and not con.execute("SELECT 1 FROM meta WHERE key LIKE 'gal:%'").fetchone()  # refused before the work
    for n, topic in enumerate(logic.gallery.TOPICS):
        assert _post(c, AL, n, topic=topic).json()["topic"] == topic
    old = _post(c, AL, 8, topic=None)  # an old web bundle: neither said, taken as other until 2026-11-25
    assert old.status_code == 200 and old.json()["topic"] == "other" and old.json()["id"] in _feed(c, topic="other")
    assert con.execute("SELECT topic FROM gallery_photos WHERE file_id = ?", (old.json()["id"],)).fetchone()[0] is None
    ev = _post(c, AL, 9, event=eid).json()
    assert "topic" not in ev and ev["event"]["id"] == eid  # the event flow as before
    assert con.execute("SELECT topic FROM gallery_photos WHERE file_id = ?", (ev["id"],)).fetchone()[0] is None
    assert _post(c, 999, 1, topic="campus").status_code == 404  # not a student
    logic.gallery.MODE = "staff"
    assert _post(c, AL, 10, topic="campus").status_code == 404


def test_albums_on_the_first_page(env):
    """The shelf: each open event's album once, the one with the newest photo first, its count as I see it and its cover
    (the event's own, else its newest photo); closed events and reported photos stay out; in one query."""
    c, con, oid = _app(env)
    a, b, closed = _event(con, c, oid, "A"), _event(con, c, oid, "B"), _event(con, c, oid, "Closed", visibility="members")
    a1, a2 = _photo(con, a, c.ids[AL]), _photo(con, a, c.ids[AL])
    b1 = _photo(con, b, c.ids[BO])
    _photo(con, closed, c.ids[BO])
    cover = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES ('cv', 'event_cover', 'image/webp', 1, 10, 10, 'cv', ?, ?, '#000000')""", (c.ids[HEAD], NOW)).lastrowid
    con.execute("UPDATE events SET cover_file_id = ?, cover_focus = '0.5,0.2' WHERE id = ?", (cover, a))
    _post(c, AL, 1, topic="campus")  # of no event: no album
    got = c.get("/api/gallery", headers=tma(CY)).json()["albums"]
    assert [(x["id"], x["title"], x["n"], x["cover"]["id"], x["cover"]["focus"]) for x in got] == [(b, "B", 1, b1, None), (a, "A", 2, cover, [0.5, 0.2])]
    assert got[0]["at"] == NOW - 7200  # the event's day
    assert c.post("/api/reports", headers=tma(CY), json={"target": "photo", "id": a2, "reason": "rules"}).status_code == 204
    assert [(x["id"], x["n"]) for x in c.get("/api/gallery", headers=tma(CY)).json()["albums"]] == [(b, 1), (a, 1)]  # gone for the reporter
    for params in ({"topic": "events"}, {"before": 1 << 40}):
        assert "albums" not in c.get("/api/gallery", headers=tma(CY), params=params).json()  # the first page of everything alone
    assert "albums" not in c.get("/api/gallery", headers=tma(999)).json()  # a guest: nothing
    seen = []
    con.set_trace_callback(seen.append)
    logic.gallery.albums(con, logic.core.Viewer(c.ids[CY], "user", True))
    con.set_trace_callback(None)
    assert len([q for q in seen if q.lstrip().upper().startswith(("SELECT", "WITH"))]) == 1


def test_feed_mixes_both_newest_first_and_filters(env):
    c, con, oid = _app(env)
    eid = _event(con, c, oid)
    _came(con, c, eid, AL, "G-1")
    campus = _post(c, AL, 1, topic="campus").json()["id"]
    album = _photo(con, eid, c.ids[BO])  # added in the album itself
    life = _post(c, BO, 2, topic="life").json()["id"]
    attached = _post(c, AL, 3, event=eid).json()["id"]
    old = _post(c, BO, 4).json()["id"]
    con.execute("UPDATE gallery_photos SET topic = NULL WHERE file_id = ?", (old,))  # posted before topics
    assert _feed(c) == [old, attached, life, album, campus]
    shown = {p["id"]: p for p in c.get("/api/gallery", headers=tma(CY)).json()["photos"]}
    assert shown[album]["at"] == NOW and "uid" not in shown[album]  # an album's photo: when it was uploaded, for the feed's days
    assert _feed(c, topic="events") == [attached, album]
    assert _feed(c, topic="campus") == [campus] and _feed(c, topic="life") == [life] and _feed(c, topic="study") == []
    assert _feed(c, topic="other") == [old]
    assert _feed(c, topic="x") == 400
    page = c.get("/api/gallery", headers=tma(CY), params={"topic": "events", "limit": 1}).json()
    assert [p["id"] for p in page["photos"]] == [attached] and page["more"] is True
    assert _feed(c, topic="events", before=attached) == [album]
    logic.gallery.MODE = ""  # off: the albums alone, whatever is asked
    assert _feed(c, topic="campus") == [] and _feed(c) == [attached, album]


def test_a_topic_photo_is_as_safe_as_any(env, monkeypatch):
    c, con, _ = _app(env)
    monkeypatch.setattr(logic.gallery, "A_DAY", 3)
    fid = _post(c, BO, 1, topic="study").json()["id"]
    rep = lambda who: c.post("/api/reports", headers=tma(who), json={"target": "photo", "id": fid, "reason": "me"}).status_code  # noqa: E731
    assert rep(AL) == 204 and _feed(c, AL, topic="study") == [] and _feed(c, CY, topic="study") == [fid]
    assert rep(CY) == rep(HEAD) == 204 and _feed(c, ADMIN, topic="study") == []  # three people: for everyone
    # a moderator's Delete and its undo keep the topic
    assert c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": True}).status_code == 204
    assert not con.execute("SELECT 1 FROM gallery_photos").fetchone()
    assert c.post(f"/api/admin/taken-down/photo/{fid}/restore", headers=tma(ADMIN)).status_code == 204
    assert c.get("/api/gallery", headers=tma(CY), params={"topic": "study"}).json()["photos"][0]["topic"] == "study"
    # the author's Delete: the row and the file
    path = _path(con, fid)
    assert c.delete(f"/api/gallery/{fid}", headers=tma(AL)).status_code == 404
    assert c.delete(f"/api/gallery/{fid}", headers=tma(BO)).status_code == 204
    assert _feed(c) == [] and not (c.media / f"{path}.webp").exists()
    # the day's share is one for every kind
    assert _post(c, BO, 2, topic="life").status_code == _post(c, BO, 3).status_code == 200
    r = _post(c, BO, 4, topic="campus")
    assert r.status_code == 429 and r.json()["message"] == "gallery"


def test_account_deletion_leaves_no_topic_photo(env):
    c, con, _ = _app(env)
    fid = _post(c, AL, 1, topic="campus").json()["id"]
    path = _path(con, fid)
    _, photos = logic.delete_me(con, logic.Viewer(c.ids[AL], "user", True))
    server.media.drop(c.media, photos)
    assert photos == [path] and not (c.media / f"{path}.webp").exists()
    assert not con.execute("SELECT 1 FROM gallery_photos UNION ALL SELECT 1 FROM files WHERE id = ?", (fid,)).fetchone()
    assert _feed(c, topic="campus") == []
