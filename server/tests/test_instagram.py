"""A club's Instagram posts in its news by themselves (instagram.py): its handle asked through Business Discovery in
batches, each new post one of the club's posts (caption, picture, link), first reads capped, nothing twice, the
hour's allowance kept (calls capped, pauses on a limit, a busy header or a refused token), a handle with no business
account asked again a day later, a club that may not post stories gets none, a handle taken off takes its posts down.
Recorded (made-up) Graph answers (instagram_batch.json), no network."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

from kbtu import db, download, instagram, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

REC = json.loads((Path(__file__).parent / "instagram_batch.json").read_text())
ME = "17841400000000000"


def _dated(hours: list[int]) -> dict:
    """The recorded account, its posts dated `hours` ago (newest first), so the first read's 30 days hold."""
    a = copy.deepcopy(REC["account"])
    now = int(time.time())
    for m, h in zip(a["business_discovery"]["media"]["data"], hours):
        m["timestamp"] = datetime.fromtimestamp(now - h * 3600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return a


class _Meta:
    """graph.facebook.com as the batch endpoint answers: answer(handle) -> (code, body) or None (that call timed out);
    or `top` (status, body): the whole request refused."""

    def __init__(self, answer, headers: dict | None = None, top: tuple[int, dict] | None = None):
        self.answer, self.headers, self.top, self.batches = answer, headers or {"x-app-usage": REC["app_usage"]}, top, []

    async def post(self, url, data, timeout, follow_redirects):
        assert url == instagram.GRAPH and data["access_token"] == "tok" and "tok" not in json.dumps(data["batch"])
        batch = json.loads(data["batch"])
        self.batches.append([re.search(r"username\(([\w.]+)\)", b["relative_url"]).group(1) for b in batch])
        assert all(b["method"] == "GET" and b["relative_url"].startswith(f"{ME}?fields=business_discovery.") for b in batch)
        if self.top:
            return httpx.Response(self.top[0], json=self.top[1], headers=self.headers)
        out = []
        for h in self.batches[-1]:
            r = self.answer(h)
            out.append(None if r is None else {"code": r[0], "body": json.dumps(r[1])})
        return httpx.Response(200, json=out, headers=self.headers)


def _pics(monkeypatch, ok: bool = True):
    async def fetch(http, url, hosts, cap, **kw):
        assert download.allowed(url, hosts) and hosts == instagram.CDN, url
        out = io.BytesIO()
        Image.new("RGB", (640, 640), (40, 90, 200)).save(out, "JPEG")
        return out.getvalue() if ok else None
    monkeypatch.setattr(download, "fetch", fetch)


def _club(env, name: str, links: list[str], official: bool = True):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, name, name[:2].upper(), "trophy_3d", official)
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps(links), oid))
    return c, dataclasses.replace(cfg, ig_user_id=ME, ig_token="tok"), con, oid


def _sweep(cfg, http, con) -> int:
    return asyncio.run(instagram.sweep(cfg, http, con))


def _posts(c, oid: int) -> list[dict]:
    return c.get(f"/api/posts?scope=org:{oid}", headers=tma(1)).json()


def test_handles_media_and_text():
    assert instagram.handle("https://instagram.com/kbtu.chess") == "kbtu.chess"
    assert instagram.handle("https://www.instagram.com/KBTU_Chess/?igsh=abc") == "kbtu_chess"
    for no in ("https://www.instagram.com/p/C0aaaaaaaa4/", "https://www.instagram.com/reel/x", "https://instagram.com/explore",
               "http://instagram.com/kbtu", "https://instagram.com.evil.kz/kbtu", "https://instagram.com/kbtu/../x",
               "https://instagram.com/a..b", "https://www.youtube.com/@kbtu", None):
        assert instagram.handle(no) is None, no
    items = _dated([1, 2, 3, 4])["business_discovery"]["media"]["data"]
    bad = [{**items[0], "id": "x1"}, {**items[0], "id": "9", "permalink": "https://evil.kz/p/C0aaaaaaaa9/"},
           {**items[0], "id": "8", "timestamp": "yesterday"}, "junk",
           {**items[0], "id": "7", "media_url": "https://evil.kz/a.jpg", "timestamp": items[3]["timestamp"]}]
    got = instagram.parse_media(items + bad)
    assert [m["id"] for m in got] == ["18000000000000004", "18000000000000003", "18000000000000002", "18000000000000001", "7"]
    assert got[1]["picture"].startswith("https://scontent-fra3-1.cdninstagram.com/v/") and ".mp4" not in got[1]["picture"]  # a reel: its cover
    assert got[3]["caption"] == "" and got[4]["picture"] is None  # no caption; a picture off Instagram's CDN never fetched
    assert instagram.parse_media(None) == [] and instagram.parse_media({"data": []}) == []
    link = "https://www.instagram.com/p/C0aaaaaaaa4/"
    assert instagram.text(items[0]["caption"], "Chess", link) == ("Chess night this Friday!", f"Room 305, 18:00. Bring a friend ♟️ #kbtu\n\n{link}")
    assert instagram.text("", "Chess", link) == ("Chess", link)


def test_new_posts_become_the_club_posts(env, monkeypatch):
    c, cfg, con, oid = _club(env, "Chess Club", ["https://www.youtube.com/@kbtuchess", "https://www.instagram.com/kbtu.chess/"])
    login(c, 1, "ann")
    _pics(monkeypatch)
    account = _dated([1, 2, 3, 24 * 40])  # the oldest past the first read's 30 days
    meta = _Meta(lambda h: (200, account))
    assert _sweep(cfg, meta, con) == 3 and meta.batches == [["kbtu.chess"]]
    posts = _posts(c, oid)
    assert [p["title"] for p in posts] == ["Chess night this Friday!", "Blitz finals in 60 seconds", "Tournament photos \U0001F4F8"]
    assert posts[0]["body"].endswith("\n\nhttps://www.instagram.com/p/C0aaaaaaaa4/") and posts[1]["body"] == "https://www.instagram.com/reel/C0aaaaaaaa3/"
    assert all(p["photo"] for p in posts) and not any(p["tg"] for p in posts)
    assert not con.execute("SELECT 1 FROM bot_outbox").fetchone()  # nobody notified
    assert con.execute("SELECT ig_id FROM ig_accounts WHERE org_id = ?", (oid,)).fetchone()[0] == "17841400000000001"
    # nothing about people: the rows hold the club's handle and its media ids alone
    assert {r[0] for r in con.execute("SELECT handle FROM ig_media")} == {"kbtu.chess"}
    # the next round: nothing new, nothing twice
    assert _sweep(cfg, meta, con) == 0 and len(_posts(c, oid)) == 3
    # a new post (and one whose picture fails: it goes without one)
    fresh = _dated([0, 1, 2, 3])
    fresh["business_discovery"]["media"]["data"][0].update(id="18000000000000005", permalink="https://www.instagram.com/p/C0aaaaaaaa5/", caption="")
    meta.answer = lambda h: (200, fresh)
    _pics(monkeypatch, ok=False)
    assert _sweep(cfg, meta, con) == 1
    top = _posts(c, oid)[0]
    assert top["title"] == "Chess Club" and top["body"] == "https://www.instagram.com/p/C0aaaaaaaa5/" and not top["photo"]


def test_no_business_account_waits_a_day_and_fails_nothing_else(env, monkeypatch):
    c, cfg, con, oid = _club(env, "Chess Club", ["https://instagram.com/kbtu.chess"])
    other = logic.create_org(con, None, "Go Club", "GO", "trophy_3d", True)
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps(["https://instagram.com/kbtu.someone", "https://instagram.com/kbtu.slow"]), other))
    _pics(monkeypatch)
    answers = {"kbtu.chess": (200, _dated([1, 2, 3, 4])), "kbtu.someone": (400, REC["not_business"]), "kbtu.slow": None}
    meta = _Meta(answers.get)
    assert _sweep(cfg, meta, con) == 4
    known = dict(con.execute("SELECT handle, ig_id FROM ig_accounts").fetchall())
    assert known == {"kbtu.chess": "17841400000000001", "kbtu.someone": None}  # a timed-out call: nothing marked, asked again
    assert _sweep(cfg, meta, con) == 0 and sorted(meta.batches[-1]) == ["kbtu.chess", "kbtu.slow"]  # no account: a day later
    assert not con.execute("SELECT 1 FROM meta WHERE key = 'ig_pause'").fetchone()


def test_the_hour_allowance_is_kept(env, monkeypatch):
    c, cfg, con, oid = _club(env, "Chess Club", [f"https://instagram.com/club.{n}" for n in range(5)])
    _pics(monkeypatch)
    monkeypatch.setattr(instagram, "CALLS", 3)
    monkeypatch.setattr(instagram, "BATCH", 2)
    meta = _Meta(lambda h: (200, {"business_discovery": {"id": "1" + h[-1], "media": {"data": []}}, "id": ME}))
    assert _sweep(cfg, meta, con) == 0 and meta.batches == [["club.0", "club.1"], ["club.2"]]
    _sweep(cfg, meta, con)
    assert meta.batches[2:] == [["club.3", "club.4"], ["club.0"]]  # the least recently read first
    # a usage header past BUSY: the round stops there, an hour off
    meta.batches, meta.headers = [], {"x-app-usage": REC["app_usage_busy"]}
    _sweep(cfg, meta, con)
    assert len(meta.batches) == 1 and _sweep(cfg, meta, con) == 0 and len(meta.batches) == 1
    until = int(con.execute("SELECT value FROM meta WHERE key = 'ig_pause'").fetchone()[0].split(":")[0])
    assert 3500 < until - time.time() <= 3600


def test_rate_limits_and_a_refused_token_pause_the_rounds(env, monkeypatch, caplog):
    c, cfg, con, oid = _club(env, "Chess Club", ["https://instagram.com/kbtu.chess"])
    pause = lambda: [int(x) for x in con.execute("SELECT value FROM meta WHERE key = 'ig_pause'").fetchone()[0].split(":")]
    meta = _Meta(lambda h: (403, REC["rate_limited"]))
    assert _sweep(cfg, meta, con) == 0 and len(meta.batches) == 1
    until, fails = pause()
    assert fails == 1 and abs(until - time.time() - instagram.PAUSE) < 5
    assert _sweep(cfg, meta, con) == 0 and len(meta.batches) == 1  # paused: no call at all
    assert not con.execute("SELECT 1 FROM ig_accounts WHERE ig_id IS NULL").fetchone()  # a limit is no "no account"
    # the next failure in a row doubles it; a failed request counts too
    con.execute("UPDATE meta SET value = ? WHERE key = 'ig_pause'", (f"{int(time.time()) - 1}:1",))
    meta.top = (500, {})
    _sweep(cfg, meta, con)
    until, fails = pause()
    assert fails == 2 and abs(until - time.time() - 2 * instagram.PAUSE) < 5
    # a refused token: the longest pause, and the log says what to do (never the token)
    con.execute("UPDATE meta SET value = ? WHERE key = 'ig_pause'", (f"{int(time.time()) - 1}:2",))
    meta.top = (400, REC["token_expired"])
    _sweep(cfg, meta, con)
    assert abs(pause()[0] - time.time() - instagram.PAUSE_MAX) < 5
    assert "IG_TOKEN was refused" in caplog.text and "tok" not in caplog.text.replace("token", "")
    # a round that goes through: the failures in a row start again
    con.execute("UPDATE meta SET value = ? WHERE key = 'ig_pause'", (f"{int(time.time()) - 1}:3",))
    meta.top, meta.answer = None, lambda h: (200, {"business_discovery": {"id": "1", "media": {"data": []}}, "id": ME})
    _sweep(cfg, meta, con)
    assert not con.execute("SELECT 1 FROM meta WHERE key = 'ig_pause'").fetchone()


def test_off_without_the_settings(env):
    c, cfg, con, oid = _club(env, "Chess Club", ["https://instagram.com/kbtu.chess"])
    meta = _Meta(lambda h: (200, _dated([1, 2, 3, 4])))
    for off in (dataclasses.replace(cfg, ig_token=""), dataclasses.replace(cfg, ig_user_id="")):
        assert _sweep(off, meta, con) == 0
    assert meta.batches == [] and not con.execute("SELECT 1 FROM ig_accounts").fetchone()


def test_only_a_club_that_may_post_stories(env, monkeypatch):
    # a student initiative before the Ascent's collab step posts no stories (clubs.stories_open), brought ones neither
    c, cfg, con, oid = _club(env, "Chess Club", ["https://instagram.com/kbtu.chess"], official=False)
    _pics(monkeypatch)
    assert _sweep(cfg, _Meta(lambda h: (200, _dated([1, 2, 3, 4]))), con) == 0 and not con.execute("SELECT 1 FROM posts").fetchone()


def test_a_handle_taken_off_takes_its_posts_down(env, monkeypatch):
    c, cfg, con, oid = _club(env, "Chess Club", ["https://instagram.com/kbtu.chess"])
    login(c, 1, "ann")
    _pics(monkeypatch)
    meta = _Meta(lambda h: (200, _dated([1, 2, 3, 4])))
    assert _sweep(cfg, meta, con) == 4
    # hidden, the club keeps them; shown again, nothing is brought twice
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (oid,))
    assert _sweep(cfg, meta, con) == 0 and con.execute("SELECT COUNT(*) FROM ig_media").fetchone()[0] == 4
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (oid,))
    assert _sweep(cfg, meta, con) == 0 and len(_posts(c, oid)) == 4
    # the link edited away: the posts taken down and wiped, the rows gone
    con.execute("UPDATE orgs SET links = '[]' WHERE id = ?", (oid,))
    assert _sweep(cfg, meta, con) == 0 and _posts(c, oid) == []
    assert con.execute("SELECT COUNT(*) FROM posts WHERE title = '' AND body = '' AND photo_file_id IS NULL AND hidden_at IS NOT NULL").fetchone()[0] == 4
    assert not con.execute("SELECT 1 FROM ig_media UNION ALL SELECT 1 FROM ig_accounts").fetchone()
    # and a club deleted takes its rows with it
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps(["https://instagram.com/kbtu.chess"]), oid))
    fresh = _dated([1, 2, 3, 4])
    for n, m in enumerate(fresh["business_discovery"]["media"]["data"]):
        m["id"] = f"1900000000000000{n}"
    meta.answer = lambda h: (200, fresh)
    assert _sweep(cfg, meta, con) == 4
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("DELETE FROM posts WHERE org_id = ?", (oid,))
    con.execute("DELETE FROM orgs WHERE id = ?", (oid,))
    assert not con.execute("SELECT 1 FROM ig_media UNION ALL SELECT 1 FROM ig_accounts").fetchone()
