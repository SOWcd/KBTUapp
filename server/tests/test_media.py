"""Media: photos, videos, albums, chat avatars and userpics on disk."""
from __future__ import annotations

import asyncio
import dataclasses
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import auth, bot_dm, chores, config, db, logic, media, outbox, app as server, texts, video
from test_core import BOT, delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def test_photos(env):
    """An organizer's photo is re-encoded (EXIF with GPS gone), served by hash and put on an event; nobody else uploads."""
    import io
    from PIL import Image
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    exif = Image.Exif()
    exif[0x8825] = {2: (43.0, 14.0, 0.0), 4: (76.0, 55.0, 0.0)}   # GPSInfo: where the photo was taken
    raw = io.BytesIO()
    Image.new("RGB", (3000, 2000), (200, 40, 40)).save(raw, "JPEG", exif=exif)
    assert c.post("/api/photos", headers=tma(30), content=raw.getvalue()).status_code == 403          # not an organizer
    assert c.post("/api/photos", headers=tma(20), content=b"not an image").json()["message"] == "not_an_image"
    up = c.post("/api/photos", headers=tma(20), content=raw.getvalue()).json()
    assert (up["w"], up["h"]) == (1600, 1067) and up["url"].endswith(".webp")
    clear = io.BytesIO()
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(clear, "PNG")
    assert c.post("/api/photos", headers=tma(20), content=clear.getvalue()).json()["color"] == "#ffffff"  # a logo's transparency: white
    bomb = io.BytesIO()
    Image.new("1", (8000, 5000)).save(bomb, "PNG")                     # ~100 KB that would unpack into hundreds of MB
    assert c.post("/api/photos", headers=tma(20), content=bomb.getvalue()).json()["message"] == "not_an_image"
    tiff = io.BytesIO()
    Image.new("RGB", (40, 30)).save(tiff, "TIFF")                      # only the five formats are ever parsed
    assert c.post("/api/photos", headers=tma(20), content=tiff.getvalue()).json()["message"] == "not_an_image"
    for size in ((8064, 6048), (6000, 4000), (4284, 5712), (6001, 4001)):   # 48 MP, a 24 MP camera, a 24 MP iPhone portrait, a crop: read smaller, not refused
        huge = io.BytesIO()
        Image.new("RGB", size, (10, 90, 200)).save(huge, "JPEG")
        r = c.post("/api/photos", headers=tma(20), content=huge.getvalue()).json()
        assert max(r["w"], r["h"]) == 1600
    served = c.get("/" + up["url"])
    assert served.headers["content-type"] == "image/webp" and "immutable" in served.headers["cache-control"]
    assert not Image.open(io.BytesIO(served.content)).getexif()                                        # no EXIF, no GPS
    start = int(time.time()) + 86400
    body = {"seats": None, "title": "Poster", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "coverId": up["id"]}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert ev["cover"]["thumb"] == up["thumb"] and ev["tint"] == "#2c50bf"                            # the colour sent: the editor picks the photo's
    assert ev["cover"]["focus"] is None                                                                # the middle until marked
    framed = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverFocus": [0.25, 0.8]}).json()
    assert framed["cover"]["focus"] == [0.25, 0.8]
    for bad in ([2, 0], [0.5], "0.5,0.5", ["x", 0], [-0.1, 0.5]):
        assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverFocus": bad}).status_code == 400
    kept = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={k: v for k, v in body.items() if k != "coverId"}).json()
    assert kept["cover"] is not None and kept["cover"]["focus"] == [0.25, 0.8]                         # absent keeps both
    gone = c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "coverId": None}).json()
    assert gone["cover"] is None
    # PLAN 33: photos after the cover, swiped sideways; a co-organizer keeps the others' when saving
    login(c, 21, "vic")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'vice', 0 FROM users WHERE tg_id = 21")
    def pic(tg, rgb):
        b = io.BytesIO(); Image.new("RGB", (40, 30), rgb).save(b, "PNG")
        return c.post("/api/photos", headers=tma(tg), content=b.getvalue()).json()["id"]
    a, b2, mine = pic(20, (1, 2, 3)), pic(20, (4, 5, 6)), pic(21, (7, 8, 9))
    plain = {k: v for k, v in body.items() if k != "coverId"}   # the editor sends coverId only when it changes
    put = lambda tg, ids: c.patch(f"/api/events/{ev['id']}", headers=tma(tg), json={**plain, "slideIds": ids})  # noqa: E731
    assert [x["id"] for x in put(20, [b2, a]).json()["slides"]] == [b2, a]                              # in the order picked
    for bad in ([a, a], [True], "1", [a] * 10, [mine]):                                                 # the last: someone else's upload
        assert put(20, bad).status_code == 400
    assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json={**body, "slideIds": [up["id"]]}).status_code == 400  # not the cover again
    assert [x["id"] for x in put(21, [a, mine]).json()["slides"]] == [a, mine]                          # the Vice keeps the President's
    c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
    assert [x["id"] for x in c.get("/api/events", headers=tma(30)).json()[0]["slides"]] == [a, mine]
    assert c.patch(f"/api/events/{ev['id']}", headers=tma(20), json=body).json()["slides"] != []        # absent keeps
    assert put(20, []).json()["slides"] == []
    put(20, [a, b2])
    other = c.post("/api/orgs/1/events", headers=tma(20), json={**body, "slideIds": [a]}).json()       # the same photo on two events
    c.post(f"/api/events/{ev['id']}/cancel", headers=tma(20), json={"reason": "x"})
    assert c.delete(f"/api/events/{ev['id']}", headers=tma(20)).status_code == 204
    assert con.execute("SELECT 1 FROM files WHERE id = ?", (a,)).fetchone() and not con.execute("SELECT 1 FROM files WHERE id = ?", (b2,)).fetchone()
    assert [x["id"] for x in c.get(f"/api/events/{other['id']}", headers=tma(20)).json()["slides"]] == [a]
    assert c.get("/media/..%2Ft.db").status_code == 404 and "SQLite" not in c.get("/media/../t.db").text   # never leaves media/


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_videos(env, tmp_path):
    """An organizer's video comes in pieces (a repeated piece isn't added twice), is compressed without its metadata, and
    plays on the event once ready; a non-video fails; nobody else uploads."""
    import subprocess
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    src = tmp_path / "in.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=60:d=2", "-f", "lavfi", "-i", "sine=d=2",
                    "-metadata", "location=+43.2+076.9/", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src)], check=True)
    raw = src.read_bytes()
    P = tma(20)
    assert c.post("/api/videos", headers=tma(30), json={"size": len(raw)}).status_code == 403          # not an organizer
    assert c.post("/api/videos", headers=P, json={"size": video.MAX_BYTES + 1}).status_code == 400
    vid = c.post("/api/videos", headers=P, json={"size": len(raw)}).json()["id"]
    half = len(raw) // 2
    assert c.post(f"/api/videos/{vid}/done", headers=P).status_code == 409                             # not all of it yet
    assert c.put(f"/api/videos/{vid}?at=0", headers=P, content=raw[:half]).json() == {"at": half}
    assert c.put(f"/api/videos/{vid}?at=0", headers=P, content=raw[:half]).json() == {"at": half}       # sent again: where it stands
    assert c.put(f"/api/videos/{vid}?at={half}", headers=tma(30), content=raw[half:]).status_code == 404  # someone else's
    assert c.put(f"/api/videos/{vid}?at={half}", headers=P, content=raw[half:]).json() == {"at": len(raw)}
    assert c.post(f"/api/videos/{vid}/done", headers=P).json()["status"] == "queued"
    start = int(time.time()) + 86400
    body = {"seats": None, "title": "Reel", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "videoId": vid}
    ev = c.post("/api/orgs/1/events", headers=P, json=body).json()
    assert ev["video"]["status"] == "queued"                                                           # the editor sees it coming
    c.post(f"/api/events/{ev['id']}/publish", headers=P)
    assert c.get("/api/events", headers=tma(30)).json()[0]["video"] is None                           # students: only once ready

    async def work():  # the postman's loop, one round
        x = logic.next_video(con)
        logic.video_done(con, x["id"], await video.compress(Path(cfg.db_path).parent / "uploads" / str(x["id"]), Path(cfg.db_path).parent / "media"))
    asyncio.run(work())
    shown = c.get("/api/events", headers=tma(30)).json()[0]["video"]
    assert shown["status"] == "ready" and shown["duration"] == 2.0 and shown["poster"]["w"] == 720
    played = c.get("/" + shown["url"], headers={"Range": "bytes=0-99"})
    assert played.status_code == 206 and len(played.content) == 100                                    # iOS plays only with ranges
    out = Path(cfg.db_path).parent / shown["url"]
    meta = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream=width,height,r_frame_rate", "-of", "json", str(out)],
                          capture_output=True, text=True).stdout
    assert "location" not in meta and '"width": 720' in meta and '"30/1"' in meta
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None}).json()["video"] is None

    bad = c.post("/api/videos", headers=P, json={"size": 5}).json()["id"]
    c.put(f"/api/videos/{bad}?at=0", headers=P, content=b"hello")
    c.post(f"/api/videos/{bad}/done", headers=P)
    x = logic.next_video(con)
    with pytest.raises(video.BadVideo):
        asyncio.run(video.compress(Path(cfg.db_path).parent / "uploads" / str(x["id"]), Path(cfg.db_path).parent / "media"))
    # PLAN 32: a horizontal clip behind the sheet: 720 on the short side, muted, 20 s at most; only in its own slot
    wsrc = tmp_path / "wide.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=2", "-f", "lavfi", "-i", "sine=d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(wsrc)], check=True)
    wraw = wsrc.read_bytes()
    wid = c.post("/api/videos", headers=P, json={"size": len(wraw), "wide": True}).json()["id"]
    c.put(f"/api/videos/{wid}?at=0", headers=P, content=wraw)
    c.post(f"/api/videos/{wid}/done", headers=P)
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": wid}).status_code == 400   # not the Feed's slot
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None, "wideVideoId": vid}).status_code == 400
    assert c.patch(f"/api/events/{ev['id']}", headers=P, json={**body, "videoId": None, "wideVideoId": wid}).json()["wideVideo"]["status"] == "queued"
    assert c.get(f"/api/events/{ev['id']}", headers=tma(30)).json()["wideVideo"] is None                # students: only once ready
    wx = logic.next_video(con)
    assert wx["id"] == wid
    logic.video_done(con, wid, asyncio.run(video.compress(Path(cfg.db_path).parent / "uploads" / str(wid), Path(cfg.db_path).parent / "media", True)))
    wide = c.get(f"/api/events/{ev['id']}", headers=tma(30)).json()["wideVideo"]
    assert wide["poster"]["w"] == 1280 and wide["poster"]["h"] == 720
    wmeta = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(Path(cfg.db_path).parent / wide["url"])],
                           capture_output=True, text=True).stdout.split()
    assert wmeta == ["video"]                                                                            # no sound track
    con.execute("UPDATE videos SET created_at = 0")
    assert sorted(i for i, _ in logic.stale_videos(con)) == [vid] and not con.execute("SELECT 1 FROM videos WHERE id = ?", (vid,)).fetchone()
    assert c.post("/api/videos", headers=P, json={"size": 5}).status_code == 200                       # `bad` still working: a second
    assert c.post("/api/videos", headers=P, json={"size": 5}).status_code == 429                       # a third unfinished: no


def test_album(env, monkeypatch):
    """The guests' album: who came adds up to 10 photos from the start until a week after the end, the team too;
    the one who added it or the club's Head+ take one out; guests see none; deleting my data takes mine out."""
    import io
    from PIL import Image
    c, cfg = env
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 7200
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', ?, 0, 0)", (ali["id"], start))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T92ABC', 0, 0)", (zhan["id"],))
    dana = login(c, 96, "dana")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', 'T96ABC', ?, 0, 0)", (dana["id"], start))
    P, A, Z = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan")

    def jpeg(n: int) -> bytes:
        raw = io.BytesIO()
        Image.new("RGB", (64, 48), (n * 20 % 256, 90, 160)).save(raw, "JPEG")
        return raw.getvalue()

    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is True
    assert c.get("/api/events/1", headers=Z).json()["canAddPhotos"] is True                # going, not let in: any student may add (owner)
    e = c.post("/api/events/1/photos", headers=A, content=jpeg(0)).json()
    assert len(e["photos"]) == 1 and e["photos"][0]["canDelete"] is True
    first = e["photos"][0]["id"]
    assert c.get("/api/events/1", headers=Z).json()["photos"][0]["canDelete"] is False
    assert c.get("/api/events/1", headers=tma(93, "Guest")).json()["photos"] == []           # people's faces: students only
    for n in range(1, 10):
        e = c.post("/api/events/1/photos", headers=A, content=jpeg(n)).json()
    assert len(e["photos"]) == 10 and e["canAddPhotos"] is False                            # ten each
    report = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'photo_report'").fetchall()
    assert [r["user_id"] for r in report] == [dana["id"]] and outbox._render(con, report[0])[2] == "ph_1"  # once, to who else came
    assert c.post("/api/events/1/photos", headers=A, content=jpeg(11)).status_code == 403
    assert c.get("/api/events/1", headers=P).json()["canAddPhotos"] is True                 # the team brings its own
    assert c.delete(f"/api/events/1/photos/{first}", headers=Z).status_code == 403
    assert len(c.delete(f"/api/events/1/photos/{first}", headers=P).json()["photos"]) == 9  # the club's Head+
    # Afisha's "Past": mine (signed up or came), ended; the admin's photo call to who came, once each
    assert [e["id"] for e in c.get("/api/events/past?mine=1", headers=Z).json()] == [1]
    assert c.get("/api/events/past?mine=1", headers=tma(93, "Guest")).json() == []
    from kbtu import admin
    monkeypatch.setattr(config, "load", lambda: cfg)
    con.execute("UPDATE users SET can_dm = 1")
    admin.main(["photo-call", "1", "--send"])
    admin.main(["photo-call", "1", "--send"])
    call = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'photo_call'").fetchall()
    assert sorted(r["user_id"] for r in call) == sorted([ali["id"], dana["id"]]) and outbox._render(con, call[0])[2] == "ph_1"
    con.execute("UPDATE events SET ends_at = ? WHERE id = 1", (int(time.time()) - 8 * 86400,))
    assert outbox._render(con, call[0]) is None                                                 # a week on: no adding, quiet
    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is False               # a week after the end: closed
    assert delete_now(c, cfg, A) is None
    left = c.get("/api/events/1", headers=P).json()["photos"]
    assert len(left) == 9 and {p["by"] for p in left} == {None}                              # my photos stay, without my name (H2)


def test_album_reports(env):
    """A photo can be reported: gone for the reporter at once, for everyone after two people, the admin's queue
    shows its thumb and "take down" deletes it; who added it shows."""
    import dataclasses
    import io
    from PIL import Image
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 96, "dana")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 7200
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    for u, code in ((ali, "T91ABC"), (zhan, "T92ABC"), (dana, "T96ABC")):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (1, ?, 'going', ?, ?, 0, 0)",
                    (u["id"], code, start))
    P, A, Z, D, B = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(96, "Dana"), tma(94, "Boss")
    raw = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 90, 160)).save(raw, "JPEG")
    ph = c.post("/api/events/1/photos", headers=A, content=raw.getvalue()).json()["photos"][0]
    assert ph["by"] == "Ali T" and ph["mine"] is True
    assert c.get("/api/events/1", headers=Z).json()["photos"][0]["mine"] is False
    rep = lambda h: c.post("/api/reports", headers=h, json={"target": "photo", "id": ph["id"], "reason": "insult"}).status_code  # noqa: E731
    assert rep(A) == 404                                                                    # not my own
    assert rep(Z) == 204
    assert c.get("/api/events/1", headers=Z).json()["photos"] == []                         # gone for me at once
    assert len(c.get("/api/events/1", headers=P).json()["photos"]) == 1                     # not yet for the rest
    assert rep(D) == 204 and len(c.get("/api/events/1", headers=P).json()["photos"]) == 1  # two: not yet
    assert rep(B) == 204
    assert c.get("/api/events/1", headers=P).json()["photos"] == []                         # three people: hidden until the admin looks
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(r["target"], r["id"], r["where"]) for r in q] == [("photo", ph["id"], {"kind": "event", "id": 1})] and q[0]["text"].endswith(".t.webp")
    # a moderator never judges their own photo: not in their queue, and refused
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 91")
    assert c.get("/api/me", headers=A).json()["counters"]["inbox"] == 0
    assert c.get("/api/admin/reports", headers=A).json() == [] and c.post(f"/api/admin/reports/photo/{ph['id']}", headers=A, json={"remove": False}).status_code == 403
    con.execute("UPDATE users SET role = 'user' WHERE tg_id = 91")
    # kept: back for everyone, and two new reports hide it only for those two (a moderator's call holds)
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": False}).status_code == 204
    assert rep(Z) == 204 and rep(D) == 204
    assert len(c.get("/api/events/1", headers=P).json()["photos"]) == 1 and c.get("/api/events/1", headers=Z).json()["photos"] == []
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": True}).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM event_photos").fetchone()[0] == 0 and c.get("/api/admin/reports", headers=B).json() == []
    # kept 30 days for an undo: the file stays, "taken down" lists it, Restore puts it back in the album
    path = con.execute("SELECT path FROM files WHERE id = ?", (ph["id"],)).fetchone()[0]
    on_disk = lambda: (Path(cfg.db_path).parent / "media" / f"{path}.webp").exists()  # noqa: E731
    assert on_disk()
    assert c.post(f"/api/admin/taken-down/photo/{ph['id']}/restore", headers=B).status_code == 204
    assert [(p["id"], p["by"]) for p in c.get("/api/events/1", headers=P).json()["photos"]] == [(ph["id"], "Ali T")]
    assert c.post("/api/reports", headers=P, json={"target": "photo", "id": ph["id"], "reason": "insult"}).status_code == 204
    assert c.post(f"/api/admin/reports/photo/{ph['id']}", headers=B, json={"remove": True}).status_code == 204
    con.execute("UPDATE takedowns SET at = at - 29 * 86400")
    chores.purge(cfg, con)
    assert on_disk()                                                                         # 29 days: still there
    con.execute("UPDATE takedowns SET at = at - 2 * 86400")
    chores.purge(cfg, con)                                                                      # 31: gone, from disk too
    assert not on_disk() and not con.execute("SELECT 1 FROM files WHERE id = ?", (ph["id"],)).fetchone()
    assert c.post(f"/api/admin/taken-down/photo/{ph['id']}/restore", headers=B).status_code == 404
    e = c.get("/api/events/1", headers=P).json()
    body = {k: e[k] for k in ("title", "description", "startsAt", "endsAt", "place", "placeUrl", "emoji", "color", "seats", "firstYear")}
    was = c.get("/api/events/1", headers=A).json()["canAddPhotos"]
    assert c.patch("/api/events/1", headers=P, json={**body, "albumOpen": False}).status_code == 200  # the old switch: ignored
    assert c.get("/api/events/1", headers=A).json()["canAddPhotos"] is was                  # guests' photos are always on
    assert "albumOpen" not in c.get("/api/events/1", headers=P).json()


def test_share_poster(env):
    """A coverless event's share card gets its own poster, not the app picture; no place, no dangling dot."""
    c, _ = env
    r = c.get("/og/poster.jpg?c=3B6BFF&e=party_popper_3d")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert c.get("/og/poster.jpg?c=zz&e=party_popper_3d").status_code == 404
    assert c.get("/og/poster.jpg?c=3B6BFF&e=../index").status_code == 404
    assert "📍" not in texts.share_event("ru", "T", 0, "")[0] and "📍 Hall" in texts.share_event("en", "T", 0, "Hall")[0]
    assert "📍" not in texts.share_event("ru", "T", 0, "\u041c\u0435\u0441\u0442\u043e \u0443\u0442\u043e\u0447\u043d\u044f\u0435\u0442\u0441\u044f")[0]
    full = texts.share_event("ru", "A<b>", 0, "222", "StudEx × Genius", 1500, 89)[0]
    assert full.split("\n") == ["<b>A&lt;b&gt;</b>", "StudEx × Genius", "📅 1 \u044f\u043d\u0432\u0430\u0440\u044f, 05:00 · 📍 222", "🎟 1\u00a0500\u00a0₸ · \u0438\u0434\u0443\u0442 89", "\u041f\u043e\u0439\u0434\u0451\u0448\u044c \u0441\u043e \u043c\u043d\u043e\u0439? 👀"]
    assert texts.share_event("en", "T", 0, "", "", None, 9)[0].split("\n")[1:] == ["📅 Jan 1, 05:00", "🎟 Free", "Coming with me? 👀"]


def test_chat_avatars_on_disk(env, monkeypatch):
    """A chat's avatar from its t.me page: saved with a suggestion (a broken picture: none), replaced by the daily look
    and by the bot's own card for a chat it sits in, the old file then off the disk."""
    import io
    from PIL import Image
    from kbtu import media
    c, cfg = env
    login(c, 63, "ali")
    con = db.connect(cfg.db_path)
    root = Path(cfg.db_path).resolve().parent / "media"
    def png(color):
        b = io.BytesIO()
        Image.new("RGB", (64, 64), color).save(b, "PNG")
        return b.getvalue()
    image = {"https://t.me/jam_news": png((200, 40, 40)), "https://t.me/broken_pic": b"not a picture"}
    async def peek(http, url):
        return {"ok": True, "title": url.rsplit("/", 1)[1], "image": image.get(url), "members": 50, "about": None, "channel": True}
    monkeypatch.setattr(media, "chat_peek", peek)
    def suggest(handle):
        con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
        return asyncio.run(bot_dm._suggest(cfg, None, con, {"chat": {"id": 63, "type": "private"}, "date": logic.now(), "text": handle}))["text"]
    on_disk = lambda p: (root / f"{p}.webp").exists()  # noqa: E731
    assert suggest("@jam_news").startswith("✅") and suggest("@broken_pic").startswith("✅")
    first = con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    assert first and on_disk(first)
    assert con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/broken_pic'").fetchone()[0] is None
    image["https://t.me/jam_news"] = png((40, 200, 40))                                 # a new avatar on t.me
    asyncio.run(chores.refresh_chats(cfg, None, con))
    second = con.execute("SELECT photo FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    assert second != first and on_disk(second) and not on_disk(first)
    # once our bot sits in the chat, Telegram's own card: title, about, members, avatar
    cid = con.execute("SELECT id FROM chats WHERE url = 'https://t.me/jam_news'").fetchone()[0]
    class Resp:
        def __init__(self, body=None, content=b""):
            self.body, self.content, self.status_code = body, content, 200
        def json(self):
            return self.body
    class Http:
        async def post(self, url, json=None):
            method = url.rsplit("/", 1)[1]
            return Resp({"getChat": {"ok": True, "result": {"title": "Jam  News", "description": "Every Friday", "photo": {"big_file_id": "F"}}},
                         "getChatMemberCount": {"ok": True, "result": 77}, "getFile": {"ok": True, "result": {"file_path": "p/1.jpg", "file_size": 999}}}[method])
        async def get(self, url):
            return Resp(content=png((40, 40, 200)))
    assert asyncio.run(chores.chat_card(cfg, Http(), con, cid, -100123)) is True
    row = con.execute("SELECT title, about, members, photo FROM chats WHERE id = ?", (cid,)).fetchone()
    assert tuple(row)[:3] == ("Jam News", "Every Friday", 77) and row[3] not in (first, second) and on_disk(row[3]) and not on_disk(second)


def test_paths_no_test_ran(env, media_dns):
    """What a trace of the whole suite showed no test running: a round's settings changed while it's live and an
    application taken back; a friend request taken back; a volunteer leaving; past events (a hidden club's left out);
    a club tag deleted; the roster's e-mails; a chat's t.me page read."""
    import httpx
    from kbtu import media, roster
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ann"), (22, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)  # official: its events on the afisha
    logic.set_role(con, None, ids[20], oid, "president", "test")
    P, A, B = tma(20), tma(21), tma(22)

    # a live round: its settings change, its questions stay once someone applied; an applicant withdraws; then it closes
    hr = c.post(f"/api/orgs/{oid}/tags", headers=P, json={"name": "HR", "color": "#2FBF71", "department": True}).json()["tags"][0]["id"]
    body = {"title": "Recruitment", "picks": 1, "closesAt": int(time.time()) + 7 * 86400, "departments": [{"tagId": hr}],
            "questions": [{"kind": "long", "text": "Why us?"}]}
    r = c.post(f"/api/orgs/{oid}/round", headers=P, json=body).json()
    q = str(r["questions"][0]["id"])
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=A, json={"departments": [hr], "answers": {q: "I play"}}).status_code == 200
    changed = c.patch(f"/api/rounds/{r['id']}", headers=P, json={**body, "title": "Recruitment 2026", "questions": [{"kind": "long", "text": "Other"}]}).json()
    assert changed["title"] == "Recruitment 2026" and [x["text"] for x in changed["questions"]] == ["Why us?"]  # answers still match
    assert c.patch(f"/api/rounds/{r['id']}", headers=A, json={"close": True}).status_code == 403
    assert c.delete(f"/api/rounds/{r['id']}/apply", headers=A).json()["mine"] is None                  # taken back: not mine any more
    assert con.execute("SELECT stage FROM round_apps WHERE user_id = ?", (ids[21],)).fetchone()[0] == "withdrawn"
    assert c.patch(f"/api/rounds/{r['id']}", headers=P, json={"close": True}).json()["open"] is False
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=B, json={"departments": [hr], "answers": {q: "x"}}).status_code == 409  # closed

    # a friend request taken back: nothing pending, and it can be asked again
    assert c.post("/api/friends/requests", headers=A, json={"userId": ids[22]}).json()["friendship"] == "requested"
    assert c.delete(f"/api/friends/requests/{ids[22]}", headers=A).status_code in (200, 204)
    assert not con.execute("SELECT 1 FROM friend_requests WHERE from_id = ? AND status = 'pending'", (ids[21],)).fetchone()

    # a volunteer leaves before anyone decided
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50, "volunteers": 2}
    e = c.post(f"/api/orgs/{oid}/events", headers=P, json=ev).json()
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=A, json={"note": "I can"}).status_code == 200
    c.delete(f"/api/events/{e['id']}/volunteer", headers=A)
    assert not con.execute("SELECT 1 FROM volunteers WHERE event_id = ? AND user_id = ?", (e["id"], ids[21])).fetchone()

    # past events: an ended one shows; a hidden club's doesn't
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, e["id"]))
    assert [x["id"] for x in c.get("/api/events/past", headers=B).json()] == [e["id"]]
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (oid,))
    assert c.get("/api/events/past", headers=B).json() == []
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (oid,))

    # a club tag deleted: gone from the team's setup and from whoever wore it
    tags = c.post(f"/api/orgs/{oid}/tags", headers=P, json={"name": "SMM", "color": "#18A9DB"}).json()["tags"]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, ids[22]))
    smm = next(t["id"] for t in tags if t["name"] == "SMM")
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (smm, ids[22]))
    assert c.delete(f"/api/orgs/{oid}/tags/{smm}", headers=A).status_code == 403
    assert [t["name"] for t in c.delete(f"/api/orgs/{oid}/tags/{smm}", headers=P).json()["tags"]] == ["HR"]
    assert not con.execute("SELECT 1 FROM member_tags WHERE user_id = ?", (ids[22],)).fetchone()

    # the roster's e-mails: lowercased, the obviously broken ones dropped
    assert [roster.email_of(x) for x in (" Ann@KBTU.kz ", "no-at.kz", "a@b", None, "x y@kbtu.kz")] == ["ann@kbtu.kz", None, None, None, None]

    # a chat's t.me page: title, about, members, channel or group, the avatar only from Telegram's file host
    page = ('<meta property="og:title" content="Chess &amp; Co"><meta property="og:description" content="Fridays at 6">'
            '<meta property="og:image" content="https://cdn4.telesco.pe/file/abc.jpg"><div class="tgme_page_extra">1 204 subscribers</div>')
    def handler(r):
        return httpx.Response(200, content=b"IMG") if "telesco.pe" in r.headers["Host"] else httpx.Response(200, text=page)
    async def peek(text=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler if text is None else (lambda r: httpx.Response(200, text=text)))) as http:
            return await media.chat_peek(http, "https://t.me/chess_co")
    got = asyncio.run(peek())
    assert (got["ok"], got["title"], got["about"], got["members"], got["channel"], got["image"]) == (True, "Chess & Co", "Fridays at 6", 1204, True, b"IMG")
    stock = asyncio.run(peek('<meta property="og:title" content="Group"><meta property="og:description" content="You can view and join @g right away.">'
                             '<meta property="og:image" content="https://telegram.org/img/t_logo.png"><div class="tgme_page_extra">35 members</div>'))
    assert (stock["about"], stock["image"], stock["members"], stock["channel"]) == (None, None, 35, False)  # Telegram's stock line and logo


def test_userpic_copy(env, media_dns):
    """The Telegram photo is served from /media once the bot copied it; a new t.me photo goes back to t.me until its
    own copy, and the old copy leaves the disk."""
    import asyncio
    import io
    import httpx
    from PIL import Image
    from kbtu import chores
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    pic = lambda k: {"Authorization": "tma " + auth.sign_init_data({"id": 10, "first_name": "Ali", "photo_url": f"https://t.me/i/userpic/320/{k}.jpg"}, BOT)}
    url = "a"
    pics = {}
    for k, rgb in (("a", (200, 40, 40)), ("b", (40, 200, 40))):
        buf = io.BytesIO()
        Image.new("RGB", (320, 320), rgb).save(buf, "JPEG")
        pics[k] = buf.getvalue()

    async def round_():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, content=pics[r.url.path[-5]]))) as http:
            await chores._userpics(cfg, http, con)

    me = lambda: c.get("/api/me", headers=pic(url)).json()["avatar"]
    me()
    asyncio.run(round_())
    first = me()
    assert first.startswith("media/") and first.endswith(".t.webp")
    root = Path(cfg.db_path).resolve().parent
    assert (root / first).is_file()
    url = "b"
    assert me() == "https://t.me/i/userpic/320/b.jpg"
    asyncio.run(round_())
    assert me() not in (first, "https://t.me/i/userpic/320/b.jpg") and not (root / first).exists()


def test_userpic_refetch(env, monkeypatch, media_dns):
    import io
    import httpx
    from PIL import Image

    c, cfg = env
    url = "https://t.me/i/userpic/320/same.svg"
    headers = {"Authorization": "tma " + auth.sign_init_data({"id": 10, "first_name": "Ali", "photo_url": url}, BOT)}
    assert c.get("/api/me", headers=headers).json()["avatar"] == url
    con = db.connect(cfg.db_path)
    root = Path(cfg.db_path).parent / "media"
    t = logic.now()
    monkeypatch.setattr(chores, "now", lambda: t)

    async def fetch(status, color):
        buf = io.BytesIO()
        if color:
            Image.new("RGB", (32, 32), color).save(buf, "PNG")
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(status, content=buf.getvalue()))) as http:
            await chores._userpics(cfg, http, con)
        path, at = con.execute("SELECT tg_photo_path, tg_photo_at FROM users WHERE tg_id = 10").fetchone()
        assert at == t
        return root / f"{path}.t.webp"

    first = asyncio.run(fetch(200, "red"))
    assert first.is_file()
    con.execute("UPDATE users SET tg_photo_at = ? WHERE tg_id = 10", (t - 4 * 86400,))
    second = asyncio.run(fetch(200, "green"))
    assert second != first and second.is_file() and not first.exists()
    os.utime(second, (1, 1))
    con.execute("UPDATE users SET tg_photo_at = ? WHERE tg_id = 10", (t - 4 * 86400,))
    assert asyncio.run(fetch(200, "green")) == second and second.stat().st_mtime == 1
    con.execute("UPDATE users SET tg_photo_at = ? WHERE tg_id = 10", (t - 4 * 86400,))
    assert asyncio.run(fetch(503, None)) == second and second.is_file()
    con.close()
