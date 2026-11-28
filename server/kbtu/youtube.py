"""A club's YouTube channel in its news, by itself (#280): a channel among the club's links (orgs.links) is resolved
once to its channel id, and its public feed (youtube.com/feeds/videos.xml, no key, no login) is read hourly; each new
video becomes one of the club's posts, as the Telegram mirror (mirror.py) does with a channel's posts: its title, its
link (News draws it as a YouTube button, the tap opens YouTube), its thumbnail as the photo. Nobody is notified; the
club's own rules for stories hold (clubs.stories_open). A link taken off the club takes its videos' posts down.
Here the database and the parsing; sweep() does the network, each feed on its own (one bad feed fails nothing)."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx

from . import download
from .feeds import Feed
from .logic import now

PAGES = ("youtube.com",)              # a channel's page (an @handle resolved) and its feed
THUMBS = ("i.ytimg.com",)
RETRY = 86400                         # a link that resolved to no channel is tried again a day later
TITLE = 120                           # what an app post's title holds (logic.create_post)
PAGE_BYTES, FEED_BYTES = 3 * 1024 * 1024, 1024 * 1024
TIMEOUT = 10                          # seconds for a whole page, feed or thumbnail (the postman's round waits on it)
BUDGET = 60                           # seconds a pass may start new channels in: a slow YouTube must not hold the bot's
                                      # messages for minutes; the rest wait an hour (shuffled, so none always comes last)

_LINK = re.compile(r"https://(?:www\.|m\.)?youtube\.com/(channel/UC[\w-]{22}|@[\w.-]{3,30}|c/[\w.-]{1,100}|user/[\w.-]{1,100})/?(?:[?#].*)?")
_ID = re.compile(r"UC[\w-]{22}")
# the page's own canonical address names its channel (an @handle's page, a /c/ or /user/ one)
_CANONICAL = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"')
_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
_VIDEO = re.compile(r"[\w-]{11}")
log = logging.getLogger("kbtu.youtube")


def channel_path(url: str) -> str | None:
    """A club link that is a YouTube channel: its path (channel/UC..., @handle, c/name, user/name), else None."""
    m = _LINK.fullmatch(url.strip())
    return m.group(1) if m else None


def _links(raw: str):
    return (path for url in json.loads(raw or "[]") if isinstance(url, str) and (path := channel_path(url)))


def parse_feed(xml: bytes) -> list[dict]:
    """A channel feed's videos, newest first: {id, title, at}. Anything malformed is skipped, never raised."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for e in root.findall("a:entry", _NS):
        vid, title, at = e.findtext("yt:videoId", "", _NS).strip(), " ".join(e.findtext("a:title", "", _NS).split()), e.findtext("a:published", "", _NS)
        try:
            ts = int(datetime.fromisoformat(at).timestamp())
        except ValueError:
            continue
        if _VIDEO.fullmatch(vid) and title:
            out.append({"id": vid, "title": title[:TITLE], "at": ts})
    return sorted(out, key=lambda x: -x["at"])


def watch_url(video: str) -> str:
    return f"https://www.youtube.com/watch?v={video}"


feed = Feed("yt_channels", "yt_videos", "path", "channel_id", "video_id", _links,
            lambda v, name: (v["title"], watch_url(v["id"])), lambda v: f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg",
            THUMBS, TIMEOUT, channel_posts=True)


async def _resolve(http: httpx.AsyncClient, path: str) -> str | None:
    if m := _ID.fullmatch(path.removeprefix("channel/")):
        return m.group(0)
    page = await download.fetch(http, f"https://www.youtube.com/{path}", PAGES, PAGE_BYTES, types=("text/html",), seconds=TIMEOUT)
    m = _CANONICAL.search(page.decode("utf-8", "replace")) if page else None
    return m.group(1) if m else None


async def sweep(cfg, http: httpx.AsyncClient, con) -> int:
    """One pass over every linked channel (outbox.send_due, hourly): resolve what is new, read each feed, post what is new.
    A feed that fails is skipped till the next hour. The posts made."""
    root = Path(cfg.db_path).resolve().parent / "media"
    await asyncio.to_thread(feed.forget, con, root)
    made, end = 0, time.monotonic() + BUDGET
    ws = await asyncio.to_thread(feed.wanted, con)
    random.shuffle(ws)
    for w in ws:
        if time.monotonic() >= end:
            break
        try:
            if w["checked"] is None or (w["account"] is None and now() - w["checked"] > RETRY):
                w["account"] = await _resolve(http, w["path"])
                await asyncio.to_thread(feed.read, con, w["org"], w["path"], w["account"])
            if not w["account"]:
                continue
            xml = await download.fetch(http, f"https://www.youtube.com/feeds/videos.xml?channel_id={w['account']}", PAGES, FEED_BYTES,
                                       seconds=TIMEOUT)
            if not xml:
                continue  # no feed this hour (nothing marked read: a first read stays a first read)
            made += await feed.post(con, http, root, w, parse_feed(xml))
        except Exception as exc:  # noqa: BLE001  one channel's trouble never stops the others or the round
            log.warning("youtube %s: %s", w["path"], type(exc).__name__)
    return made
