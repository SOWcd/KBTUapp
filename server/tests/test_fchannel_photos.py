"""Photos on forum channel posts (fchannel.add_photo, tgc.post_tick): re-encoded with no EXIF under a random name; a
named post goes out at once (a photo with a caption, or an album), an anonymous one waits for a moderator; two people's
reports take a post with photos out; the author's delete takes its messages and files; account deletion covers them."""
from __future__ import annotations

import email
import io
import json
from pathlib import Path

import httpx
from PIL import Image

from kbtu import db, logic, texts
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)
from test_fchannel import CH, setup, tick
from test_tgcomments import Telegram


class TG(Telegram):
    """The mock Bot API, reading multipart calls too (files under "_files"); an album answers with a message each."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        ct = request.headers.get("content-type", "")
        if not ct.startswith("multipart"):
            return super().__call__(request)
        method = request.url.path.rsplit("/", 1)[1]
        msg = email.message_from_bytes(b"Content-Type: " + ct.encode() + b"\r\n\r\n" + request.content)
        body: dict = {"_files": {}}
        for part in msg.get_payload():
            name = part.get_param("name", header="content-disposition")
            if part.get_filename():
                body["_files"][name] = part.get_payload(decode=True)
            else:
                body[name] = part.get_payload(decode=True).decode()
        self.calls.append((method, body))
        if method == "sendMediaGroup":
            return httpx.Response(200, json={"ok": True, "result": [{"message_id": 2000 + 10 * len(self.calls) + i} for i in range(len(json.loads(body["media"])))]})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": int(body.get("message_id") or 900 + len(self.calls))}})


def jpeg_with_gps() -> bytes:
    """A phone photo: EXIF with a GPS spot in it."""
    im = Image.new("RGB", (800, 600), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[0x8825] = {1: "N", 2: (43.0, 14.0, 0.0), 3: "E", 4: (76.0, 56.0, 0.0)}  # GPSInfo: KBTU
    out = io.BytesIO()
    im.save(out, "JPEG", exif=exif)
    assert Image.open(io.BytesIO(out.getvalue())).getexif().get_ifd(0x8825)  # it really has a location
    return out.getvalue()


def upload(c, uid: int) -> dict:
    r = c.post("/api/forum-posts/photos", headers=tma(uid), content=jpeg_with_gps())
    assert r.status_code == 200, r.text
    return r.json()


def media_root(cfg) -> Path:
    return Path(cfg.db_path).resolve().parent / "media"


def mods(c, con, uid: int = 4):
    login(c, uid, "mod")
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = ?", (uid,))


def test_named_photos_go_at_once_without_exif(env, monkeypatch):
    c, cfg, said, seen = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    tg = TG()
    raw = jpeg_with_gps()
    ph = upload(c, 1)
    assert set(ph) >= {"id", "url", "thumb", "w", "h"}
    path = con.execute("SELECT path FROM fchan_photos WHERE id = ?", (ph["id"],)).fetchone()[0]
    import hashlib
    assert hashlib.sha256(raw).hexdigest() not in path                                          # a random name, never the content hash
    for ext in (".webp", ".t.webp", ".jpg"):
        data = (media_root(cfg) / f"{path}{ext}").read_bytes()
        assert b"Exif" not in data and b"PhoneMaker" not in data and not dict(Image.open(io.BytesIO(data)).getexif())
    # someone else's photo, too many, the same twice, a caption too long, a bad id: refused
    other = upload(c, 2)
    A = tma(1)
    for bad in ({"photos": [other["id"]]}, {"photos": [ph["id"]] * 2}, {"photos": [ph["id"], 1, 2, 3, 4]}, {"photos": [True]}, {"photos": "1"}):
        assert c.post("/api/forum-posts", headers=A, json={"body": "My lost umbrella, look", **bad}).status_code == 400, bad
    assert c.post("/api/forum-posts", headers=A, json={"body": "word " * 190, "photos": [ph["id"]]}).json()["message"] == "long"
    # a named post with one photo: live at once (the AI read the words), sent as a photo with the caption
    p = c.post("/api/forum-posts", headers=A, json={"body": "Found this umbrella in the library", "photos": [ph["id"]]}).json()
    assert p["status"] == "live" and seen[-1] == "Found this umbrella in the library"
    assert c.post("/api/forum-posts", headers=tma(1), json={"body": "Again the same photo here", "photos": [ph["id"]]}).status_code == 400  # on a post already
    tick(cfg, tg, con)
    sent = tg.of("sendPhoto")
    assert len(sent) == 1 and sent[0]["chat_id"] == str(CH) and sent[0]["caption"] == "Found this umbrella in the library\n\n<i>— Ann T</i>"
    assert sent[0]["_files"]["photo"] == (media_root(cfg) / f"{path}.jpg").read_bytes()
    assert not tg.of("sendMessage")
    mid = con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0]
    assert con.execute("SELECT msg FROM fchan_photos WHERE id = ?", (ph["id"],)).fetchone()[0] == mid
    feed = {x["id"]: x for x in c.get("/api/forum-posts/feed", headers=tma(2)).json()}
    assert feed[p["id"]]["photos"][0]["thumb"] == f"media/{path}.t.webp"
    # two photos: an album, the caption on its first, each message kept
    a, b = upload(c, 2), upload(c, 2)
    q = c.post("/api/forum-posts", headers=tma(2), json={"body": "Two views of the new atrium", "photos": [a["id"], b["id"]]}).json()
    tick(cfg, tg, con)
    album = tg.of("sendMediaGroup")
    media = json.loads(album[0]["media"])
    assert [m["media"] for m in media] == ["attach://p0", "attach://p1"] and media[0]["caption"].startswith("Two views") and "caption" not in media[1]
    msgs = [r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ? ORDER BY n", (q["id"],))]
    assert len(set(msgs)) == 2 and con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (q["id"],)).fetchone()[0] == msgs[0]
    con.close()


def test_anonymous_photos_wait_for_a_moderator(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = TG()
    ph = upload(c, 1)
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Guess where this is on campus", "anon": True, "photos": [ph["id"]]}).json()
    assert p["status"] == "held"                                                                 # the AI said ok: still a person first
    assert con.execute("SELECT why FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0] == "photo"
    mine = [x for x in c.get("/api/forum-posts/feed", headers=tma(1)).json() if x["id"] == p["id"]][0]
    assert mine["human"] and mine["photos"]                                                      # "on review"
    tick(cfg, tg, con)
    assert not tg.calls                                                                          # nothing out
    held = c.get("/api/forum-posts/mod", headers=tma(4)).json()["held"]
    assert [x["id"] for x in held] == [p["id"]] and held[0]["author"] is None and held[0]["photos"]
    assert c.post(f"/api/forum-posts/{p['id']}/mod", headers=tma(4), json={"ok": True}).status_code == 204
    tick(cfg, tg, con)
    assert len(tg.of("sendPhoto")) == 1
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'fch_posted' AND ref = ?", (f"fp:{p['id']}",)).fetchone()  # told
    # rejected: told after the undo minute, nothing out
    ph2 = upload(c, 1)
    r = c.post("/api/forum-posts", headers=tma(1), json={"body": "Another place on campus here", "anon": True, "photos": [ph2["id"]]}).json()
    assert c.post(f"/api/forum-posts/{r['id']}/mod", headers=tma(4), json={"ok": False}).status_code == 204
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'fch_declined' AND ref = ?", (f"fd:{r['id']}",)).fetchone()
    tick(cfg, tg, con)
    assert len(tg.of("sendPhoto")) == 1
    # an anonymous post with no photos goes as before
    login(c, 2, "bob")
    assert c.post("/api/forum-posts", headers=tma(2), json={"body": "Just words this time around", "anon": True}).json()["status"] == "live"
    con.close()


def test_reports_take_a_photo_post_out_at_two(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    for i, n in enumerate(("ann", "bob", "cat"), 1):
        login(c, i, n)
    con = db.connect(cfg.db_path)
    mods(c, con)
    tg = TG()
    a, b = upload(c, 1), upload(c, 1)
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Pictures from the fair today", "photos": [a["id"], b["id"]]}).json()
    words = c.post("/api/forum-posts", headers=tma(1), json={"body": "Only words in this one here"}).json()
    tick(cfg, tg, con)
    msgs = [r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ? ORDER BY n", (p["id"],))]
    rep = lambda who, pid: c.post("/api/reports", headers=tma(who), json={"target": "fpost", "id": pid, "reason": "insult"})  # noqa: E731
    assert rep(2, p["id"]).status_code == 204 and rep(2, p["id"]).status_code == 204              # the same person twice: one
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0] == "live"
    assert rep(3, p["id"]).status_code == 204
    assert tuple(con.execute("SELECT status, why FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()) == ("hidden", "reports")
    assert sorted(r[0] for r in con.execute("SELECT msg_id FROM tg_unpost WHERE photo = 1")) == sorted(msgs)
    rep(2, words["id"]), rep(3, words["id"])
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (words["id"],)).fetchone()[0] == "live"  # words alone wait
    tick(cfg, tg, con)
    assert {d["message_id"] for d in tg.of("deleteMessage") if d["chat_id"] == CH} == set(msgs)
    # in the moderator's queue with its photos; kept: back in the channel as a new album
    q = [x for x in c.get("/api/admin/reports", headers=tma(4)).json() if x["target"] == "fpost" and x["id"] == p["id"]]
    assert len(q) == 1 and len(q[0]["photos"]) == 2
    assert c.post(f"/api/admin/reports/fpost/{p['id']}", headers=tma(4), json={"remove": False}).status_code == 204
    assert con.execute("SELECT status, tg_msg FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[:] == ("live", None)
    tick(cfg, tg, con)
    assert len(tg.of("sendMediaGroup")) == 2
    # kept once: new reports don't take it out by themselves again
    login(c, 5, "dan")
    rep(5, p["id"]), rep(3, p["id"])
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (p["id"],)).fetchone()[0] == "live"
    # another one out by reports, then removed by the moderator: stays down, its Undo in the removed list
    d = upload(c, 2)
    r = c.post("/api/forum-posts", headers=tma(2), json={"body": "A photo of a stranger, sorry", "photos": [d["id"]]}).json()
    tick(cfg, tg, con)
    rep(1, r["id"]), rep(3, r["id"])
    assert c.post(f"/api/admin/reports/fpost/{r['id']}", headers=tma(4), json={"remove": True}).status_code == 204
    assert tuple(con.execute("SELECT status, why FROM fchan_posts WHERE id = ?", (r["id"],)).fetchone()) == ("hidden", "moderator")
    assert r["id"] in [x["id"] for x in c.get("/api/forum-posts/mod", headers=tma(4)).json()["removed"]]
    con.close()


def test_delete_takes_photo_messages_and_files(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    tg = TG()
    a, b = upload(c, 1), upload(c, 1)
    paths = [r[0] for r in con.execute("SELECT path FROM fchan_photos ORDER BY id")]
    p = c.post("/api/forum-posts", headers=tma(1), json={"body": "Our team photos from today", "photos": [a["id"], b["id"]]}).json()
    tick(cfg, tg, con)
    msgs = [r[0] for r in con.execute("SELECT msg FROM fchan_photos WHERE post_id = ? ORDER BY n", (p["id"],))]
    assert c.delete(f"/api/forum-posts/{p['id']}", headers=tma(1)).status_code == 204
    assert not con.execute("SELECT 1 FROM fchan_photos").fetchone()
    tick(cfg, tg, con)
    assert {d["message_id"] for d in tg.of("deleteMessage") if d["chat_id"] == CH} == set(msgs)
    assert not any((media_root(cfg) / f"{x}{ext}").exists() for x in paths for ext in (".webp", ".t.webp", ".jpg"))
    # past 48 h Telegram won't delete: each photo becomes a blank one with the template under it
    class Old(TG):
        def __call__(self, request):
            if request.url.path.endswith("/deleteMessage"):
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "message can't be deleted"})
            return super().__call__(request)
    old = Old()
    c2 = upload(c, 1)
    q = c.post("/api/forum-posts", headers=tma(1), json={"body": "One more photo from the hall", "photos": [c2["id"]]}).json()
    tick(cfg, old, con)
    mid = con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (q["id"],)).fetchone()[0]
    c.delete(f"/api/forum-posts/{q['id']}", headers=tma(1))
    tick(cfg, old, con)
    edit = old.of("editMessageMedia")
    assert len(edit) == 1 and edit[0]["message_id"] == str(mid) and json.loads(edit[0]["media"])["caption"] == texts.bot_message("ru", "fch_gone")[0]
    assert not old.of("editMessageText") and not con.execute("SELECT 1 FROM tg_unpost").fetchone()
    con.close()


def test_account_deletion_covers_photos(env, monkeypatch):
    c, cfg, said, _ = setup(env, monkeypatch)
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    tg = TG()
    loose = upload(c, 1)                                                                         # picked, never posted
    held = upload(c, 1)
    c.post("/api/forum-posts", headers=tma(1), json={"body": "Never got out of the queue", "anon": True, "photos": [held["id"]]})
    paths = [r[0] for r in con.execute("SELECT path FROM fchan_photos")]
    delete_now(c, cfg, tma(1))
    assert not con.execute("SELECT 1 FROM fchan_photos").fetchone()
    tick(cfg, tg, con)
    assert not any((media_root(cfg) / f"{x}.jpg").exists() for x in paths)
    # an upload never posted is swept after the hour
    login(c, 2, "bob")
    up = upload(c, 2)
    con.execute("UPDATE fchan_photos SET created_at = 0 WHERE id = ?", (up["id"],))
    con.execute("DELETE FROM meta WHERE key = 'fch_sweep'")
    logic.fchannel.sweep(con)
    assert not con.execute("SELECT 1 FROM fchan_photos").fetchone()
    con.close()
