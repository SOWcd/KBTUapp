"""A club's YouTube channel in its news by itself (youtube.py): its link resolved once, the public feed read, each new
video one of the club's posts (title, link, thumbnail), first reads capped, a backlog taken oldest first, nothing twice,
a club that may not post stories gets none, a link taken off takes its posts down. A recorded (made-up) feed, no network."""
from __future__ import annotations

import asyncio
import io
import json
import time
from datetime import datetime, timezone

from PIL import Image

from kbtu import db, download, logic, youtube
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

CHANNEL = "UC" + "a" * 22
DAY = 86400


def _feed(videos: list[tuple[str, str, int]]) -> bytes:
    """A channel's Atom feed as YouTube serves it: (video id, title, published) each."""
    entries = "".join(f"""<entry><id>yt:video:{v}</id><yt:videoId>{v}</yt:videoId><yt:channelId>{CHANNEL}</yt:channelId>
      <title>{t}</title><link rel="alternate" href="https://www.youtube.com/watch?v={v}"/>
      <published>{datetime.fromtimestamp(at, timezone.utc).isoformat()}</published>
      <media:group><media:title>{t}</media:title><media:thumbnail url="https://i1.ytimg.com/vi/{v}/hqdefault.jpg" width="480" height="360"/></media:group>
    </entry>""" for v, t, at in videos)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <link rel="self" href="http://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"/><id>yt:channel:{CHANNEL[2:]}</id>
 <yt:channelId>{CHANNEL}</yt:channelId><title>Chess Club</title>{entries}</feed>""".encode()


def _thumb() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (480, 360), (200, 40, 40)).save(out, "JPEG")
    return out.getvalue()


def _club(env, links: list[str], official: bool = True):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "trophy_3d", official)
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps(links), oid))
    return c, cfg, con, oid


def _web(monkeypatch, pages: dict[str, bytes | None], asked: list[str] | None = None):
    """download.fetch answering from `pages` (a URL's start -> bytes; None: the fetch failed), its hosts checked."""
    async def fetch(http, url, hosts, cap, **kw):
        assert download.allowed(url, hosts), url
        if asked is not None:
            asked.append(url)
        for start, body in pages.items():
            if url.startswith(start):
                if isinstance(body, Exception):
                    raise body
                return body
        return None
    monkeypatch.setattr(download, "fetch", fetch)


def _sweep(cfg, con) -> int:
    return asyncio.run(youtube.sweep(cfg, None, con))


def _posts(c, oid: int, who: int = 1) -> list[dict]:
    return c.get(f"/api/posts?scope=org:{oid}", headers=tma(who)).json()


def test_channel_links_and_the_feed():
    assert youtube.channel_path(f"https://www.youtube.com/channel/{CHANNEL}") == f"channel/{CHANNEL}"
    assert youtube.channel_path("https://youtube.com/@kbtu.chess?si=x") == "@kbtu.chess"
    assert youtube.channel_path("https://m.youtube.com/c/KbtuChess/") == "c/KbtuChess"
    assert youtube.channel_path("https://www.youtube.com/user/kbtuchess") == "user/kbtuchess"
    for no in ("https://www.youtube.com/watch?v=abcdefghijk", "https://youtu.be/abcdefghijk", "https://www.youtube.com/@kbtu/../evil",
               "http://www.youtube.com/@kbtuchess", "https://youtube.com.evil.kz/@kbtuchess", "https://www.instagram.com/kbtuchess"):
        assert youtube.channel_path(no) is None, no
    now = int(time.time())
    feed = youtube.parse_feed(_feed([("abcdefghij1", "Older  one", now - 2 * DAY), ("abcdefghij2", "Newest &amp; best", now - DAY),
                                     ("bad id", "No id", now), ("abcdefghij3", "", now)]))
    assert [(v["id"], v["title"]) for v in feed] == [("abcdefghij2", "Newest & best"), ("abcdefghij1", "Older one")]
    assert youtube.parse_feed(b"<not xml") == [] and youtube.parse_feed(b"<feed/>") == []


def test_new_videos_become_the_club_posts(env, monkeypatch):
    c, cfg, con, oid = _club(env, ["https://www.instagram.com/kbtuchess", "https://www.youtube.com/@kbtuchess"])
    login(c, 1, "ann")
    now = int(time.time())
    old = [(f"oldvideo{n:03d}", f"Old {n}", now - (40 + n) * DAY) for n in range(3)]  # past the first read's 30 days
    recent = [(f"newvideo{n:03d}", f"Game {n}", now - (n + 1) * 3600) for n in range(7)]
    canonical = f'<html><link rel="canonical" href="https://www.youtube.com/channel/{CHANNEL}"></html>'.encode()
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"
    asked: list[str] = []
    _web(monkeypatch, {"https://www.youtube.com/@kbtuchess": canonical, feed_url: _feed(recent + old), "https://i.ytimg.com/": _thumb()}, asked)
    # a first read: the last 5 of the last 30 days, oldest first, each with its link and thumbnail; nobody notified
    assert _sweep(cfg, con) == 5
    posts = _posts(c, oid)
    assert [p["title"] for p in posts] == [f"Game {n}" for n in range(5)]  # newest first, as News lists them
    assert posts[0]["body"] == "https://www.youtube.com/watch?v=newvideo000" and posts[0]["photo"] and not posts[0]["tg"]
    assert not con.execute("SELECT 1 FROM bot_outbox").fetchone()
    assert con.execute("SELECT channel_id FROM yt_channels WHERE org_id = ?", (oid,)).fetchone()[0] == CHANNEL
    # the handle resolved once: the next hour reads the feed alone; nothing new, nothing posted (the 6th and 7th were before)
    asked.clear()
    assert _sweep(cfg, con) == 0 and not any("@kbtuchess" in u for u in asked) and feed_url in asked
    # a backlog of 7 new ones: the oldest 5 now, the other 2 next round, none twice
    more = [(f"latest{n:05d}", f"Latest {n}", now + n * 60) for n in range(7)]
    _web(monkeypatch, {feed_url: _feed(more[::-1] + recent + old), "https://i.ytimg.com/": None})
    assert _sweep(cfg, con) == 5 and _sweep(cfg, con) == 2 and _sweep(cfg, con) == 0
    titles = [p["title"] for p in _posts(c, oid)]
    assert titles[:7] == [f"Latest {n}" for n in reversed(range(7))] and len(titles) == len(set(titles)) == 12
    assert not _posts(c, oid)[0]["photo"]  # a thumbnail that failed: the post goes without one


def test_a_bad_feed_fails_nothing_else(env, monkeypatch):
    c, cfg, con, oid = _club(env, [f"https://www.youtube.com/channel/{CHANNEL}"])
    other = logic.create_org(con, None, "Go Club", "GO", "trophy_3d", True)
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps(["https://www.youtube.com/@nochannel", "https://www.youtube.com/channel/UC" + "b" * 22]), other))
    now = int(time.time())
    _web(monkeypatch, {f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}": _feed([("abcdefghijk", "Ours", now - 60)]),
                       "https://www.youtube.com/feeds/videos.xml?channel_id=UC" + "b" * 22: RuntimeError("boom"),
                       "https://www.youtube.com/@nochannel": b"<html>no canonical here</html>"})
    assert _sweep(cfg, con) == 1
    known = dict(con.execute("SELECT path, channel_id FROM yt_channels WHERE org_id = ?", (other,)).fetchall())
    assert known == {"@nochannel": None, "channel/UC" + "b" * 22: "UC" + "b" * 22}  # no channel: tried again a day later


def test_only_a_club_that_may_post_stories(env, monkeypatch):
    # a student initiative before the Ascent's collab step posts no stories (clubs.stories_open), mirrored ones neither
    c, cfg, con, oid = _club(env, [f"https://www.youtube.com/channel/{CHANNEL}"], official=False)
    _web(monkeypatch, {"https://www.youtube.com/feeds/": _feed([("abcdefghijk", "Ours", int(time.time()) - 60)])})
    assert _sweep(cfg, con) == 0 and not con.execute("SELECT 1 FROM posts").fetchone()


def test_a_link_taken_off_takes_its_videos_down(env, monkeypatch):
    c, cfg, con, oid = _club(env, [f"https://www.youtube.com/channel/{CHANNEL}"])
    login(c, 1, "ann")
    _web(monkeypatch, {"https://www.youtube.com/feeds/": _feed([("abcdefghijk", "Ours", int(time.time()) - 60)]), "https://i.ytimg.com/": _thumb()})
    assert _sweep(cfg, con) == 1
    # hidden, the club keeps them (its posts are out of sight anyway); shown again, nothing is posted twice
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (oid,))
    assert _sweep(cfg, con) == 0 and con.execute("SELECT COUNT(*) FROM yt_videos").fetchone()[0] == 1
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (oid,))
    assert _sweep(cfg, con) == 0 and [p["title"] for p in _posts(c, oid)] == ["Ours"]
    # the link edited away: the post taken down and wiped, its picture gone, the rows too
    con.execute("UPDATE orgs SET links = '[]' WHERE id = ?", (oid,))
    assert _sweep(cfg, con) == 0
    assert _posts(c, oid) == [] and con.execute("SELECT title, photo_file_id, hidden_at IS NOT NULL FROM posts").fetchone()[:] == ("", None, 1)
    assert not con.execute("SELECT 1 FROM yt_videos UNION ALL SELECT 1 FROM yt_channels").fetchone()
    # and a club deleted takes its rows with it
    con.execute("UPDATE orgs SET links = ? WHERE id = ?", (json.dumps([f"https://www.youtube.com/channel/{CHANNEL}"]), oid))
    _web(monkeypatch, {"https://www.youtube.com/feeds/": _feed([("abcdefghij2", "Again", int(time.time()) - 30)])})
    assert _sweep(cfg, con) == 1
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("DELETE FROM posts WHERE org_id = ?", (oid,))
    con.execute("DELETE FROM orgs WHERE id = ?", (oid,))
    assert not con.execute("SELECT 1 FROM yt_videos UNION ALL SELECT 1 FROM yt_channels").fetchone()
