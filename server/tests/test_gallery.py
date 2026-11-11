"""The Afisha's Gallery (logic.organizing.gallery): students only, only what is open to every student, never what a report
or a moderator took away, no more about the author than the event's album says, one query for all rows."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

ADMIN, HEAD, AL, BO, CY = 80, 81, 82, 83, 84
NOW = logic.core.now()


def _setup(env):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}))))
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, HEAD, AL, BO, CY)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, ids[HEAD], oid, "president", "test")
    c.ids = ids
    return c, con, oid


def _event(con, c, oid, title="Open", **cols):
    base = {"org_id": oid, "status": "published", "title": title, "place": "Hall", "starts_at": NOW - 7200, "ends_at": NOW - 3600, "emoji": "crown_3d",
            "color": "#123456", "tint": "#123456", "created_by": c.ids[HEAD], "created_at": NOW - 9000, "updated_at": NOW - 9000, **cols}
    return con.execute(f"INSERT INTO events ({', '.join(base)}) VALUES ({', '.join('?' * len(base))})", tuple(base.values())).lastrowid


def _photo(con, eid, by, sha=None):
    n = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'event_photo', 'image/webp', 1, 10, 10, ?, ?, ?, '#000000')""", (sha or f"s{n}", f"p{n}", by, NOW)).lastrowid
    return _pin(con, eid, fid, by)


def _pin(con, eid, fid, by):
    con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (?, ?, 1, ?)", (eid, fid, by))
    return fid


def _ids(c, who=AL):
    return [p["id"] for p in c.get("/api/gallery", headers=tma(who)).json()["photos"]]


def test_students_only_and_says_no_more_than_the_album(env):
    c, con, oid = _setup(env)
    eid = _event(con, c, oid)
    fid = _photo(con, eid, c.ids[BO])
    assert c.get("/api/gallery", headers=tma(999)).json() == {"photos": [], "more": False}  # a guest: faces
    page = c.get("/api/gallery", headers=tma(AL)).json()
    album = c.get(f"/api/events/{eid}", headers=tma(AL)).json()["photos"][0]
    p = page["photos"][0]
    assert page["more"] is False and p["id"] == fid and p["event"] == {"id": eid, "title": "Open"}
    assert p["by"] == album["by"] and {k for k in p if k != "event"} == set(album)  # the author: the album's line, nothing more
    assert p["mine"] is False and _ids(c, BO) == [fid] and c.get("/api/gallery", headers=tma(BO)).json()["photos"][0]["mine"] is True


def test_only_events_open_to_every_student(env):
    c, con, oid = _setup(env)
    ok = _photo(con, _event(con, c, oid), c.ids[BO])
    secret = [_event(con, c, oid, status="draft"), _event(con, c, oid, status="cancelled"), _event(con, c, oid, hidden_at=NOW),
              _event(con, c, oid, visibility="members"), _event(con, c, oid, visibility="leaders", leaders_from="president"), _event(con, c, oid, meeting=1)]
    for e in secret:
        _photo(con, e, c.ids[BO])
    # a club the admin hid
    gone = logic.create_org(con, None, "Hidden", "HI", "crown_3d", True)
    _photo(con, _event(con, c, gone), c.ids[BO])
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (gone,))
    # the president and the app's admin see what any student sees here, though _visible would let them into the drafts
    assert _ids(c, AL) == _ids(c, HEAD) == _ids(c, ADMIN) == [ok]
    # the event itself deleted: its album goes with it
    con.execute("DELETE FROM events WHERE id = (SELECT event_id FROM event_photos WHERE file_id = ?)", (ok,))
    assert _ids(c) == []


def test_an_initiative_off_the_afisha_only_for_those_it_is_theirs(env):
    c, con, oid = _setup(env)
    club = logic.create_org(con, None, "Small", "SM", "crown_3d", False)  # no check mark: not on the general afisha
    eid = _event(con, c, club)
    fid = _photo(con, eid, c.ids[BO])
    assert _ids(c) == []
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', 'G-1', 0, 0)", (eid, c.ids[AL]))
    assert _ids(c) == [fid] and _ids(c, CY) == []


def test_hide_first_year_is_kept(env):
    c, con, oid = _setup(env)
    fid = _photo(con, _event(con, c, oid, first_year=1), c.ids[BO])
    assert _ids(c) == [fid]
    con.execute("UPDATE users SET hide_first_year = 1 WHERE id = ?", (c.ids[AL],))
    assert _ids(c) == [] and _ids(c, CY) == [fid]


def _report(c, who, fid):
    return c.post("/api/reports", headers=tma(who), json={"target": "photo", "id": fid, "reason": "spam"})


def test_reports_and_take_downs(env):
    c, con, oid = _setup(env)
    eid = _event(con, c, oid)
    fid, other = _photo(con, eid, c.ids[BO]), _photo(con, eid, c.ids[BO])
    assert _report(c, AL, fid).status_code == 204
    assert _ids(c, AL) == [other] and _ids(c, CY) == [other, fid]  # one report: gone for me alone
    assert _report(c, CY, fid).status_code == 204
    assert _ids(c, HEAD) == [other, fid]  # two: not yet
    assert _report(c, ADMIN, fid).status_code == 204
    assert _ids(c, HEAD) == [other]  # three: for everyone
    assert c.post(f"/api/admin/reports/photo/{fid}", headers=tma(ADMIN), json={"remove": False}).status_code == 204  # kept by a moderator
    assert fid in _ids(c, HEAD)
    assert _report(c, CY, other).status_code == 204
    assert c.post(f"/api/admin/reports/photo/{other}", headers=tma(ADMIN), json={"remove": True}).status_code == 204  # taken down
    assert other not in _ids(c, HEAD) and other not in _ids(c, CY)


def test_newest_first_pages_once_each_and_one_query(env):
    c, con, oid = _setup(env)
    eid, later = _event(con, c, oid), _event(con, c, oid, title="Later")
    ids = [_photo(con, eid, c.ids[BO]) for _ in range(3)]
    _pin(con, later, ids[0], c.ids[BO])  # one file in two albums: once, under the newer event
    h = tma(AL)
    a = c.get("/api/gallery", params={"limit": 2}, headers=h).json()
    b = c.get("/api/gallery", params={"limit": 2, "before": a["photos"][-1]["id"]}, headers=h).json()
    assert [p["id"] for p in a["photos"]] == ids[:0:-1] and a["more"] is True
    assert [p["id"] for p in b["photos"]] == [ids[0]] and b["more"] is False and b["photos"][0]["event"]["id"] == later
    assert c.get("/api/gallery", params={"before": 1 << 70}, headers=h).status_code == 400  # never an integer SQLite can't bind

    v = logic.core.Viewer(c.ids[AL], "user", True)
    def count() -> int:
        seen: list[str] = []
        con.set_trace_callback(seen.append)
        logic.gallery.feed(con, v)
        con.set_trace_callback(None)
        return len(seen)
    before = count()
    for _ in range(10):
        _photo(con, eid, c.ids[BO])
    assert count() == before == 2  # the feed and the albums (the first page), one query each


def test_photo_in_a_closed_album_too_can_still_be_reported(env):
    c, con, oid = _setup(env)
    fid = _photo(con, _event(con, c, oid, 'Team', visibility='members'), c.ids[HEAD])  # the closed album comes first
    _pin(con, _event(con, c, oid), fid, c.ids[HEAD])
    assert c.post('/api/reports', headers=tma(AL), json={'target': 'photo', 'id': fid, 'reason': 'spam'}).status_code == 204
