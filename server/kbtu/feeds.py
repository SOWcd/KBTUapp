"""The clubs' public feeds: linked sources, first reads, posts and pictures. Providers own fetching and item shapes."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from . import download, media, mirror
from .logic import now, one, photo_free, rows, tx, wipe_post
from .logic.clubs import stories_open

FIRST_TAKE, FIRST_DAYS, PER_ROUND = 5, 30, 5


@dataclass(frozen=True)
class Feed:
    accounts: str
    items: str
    link: str
    account: str
    item: str
    links: Callable[[str], Iterable[str]]
    text: Callable[[dict, str], tuple[str, str]]
    picture: Callable[[dict], str | None]
    hosts: tuple[str, ...]
    timeout: int
    channel_posts: bool = False  # YouTube posts belong to a resolved channel; Instagram's belong to a handle.

    def wanted(self, con) -> list[dict]:
        """All linked sources, including hidden clubs: only removing a link takes its posts down."""
        links = [(o["id"], link) for o in rows(con, "SELECT id, links FROM orgs WHERE links IS NOT NULL")
                 for link in self.links(o["links"])]
        known = {(r["org_id"], r[self.link]): r for r in rows(con, f"SELECT * FROM {self.accounts}")}
        return [{"org": oid, self.link: link, **({"account": k[self.account], "seen": k["seen_until"], "checked": k["checked_at"]}
                                                if (k := known.get((oid, link))) else {"account": None, "seen": None, "checked": None})}
                for oid, link in dict.fromkeys(links)]

    def forget(self, con, root: Path | None = None) -> list[int]:
        """Unlinked sources: wipe their posts and rows, keeping a channel still linked another way."""
        linked = {(w["org"], w[self.link]) for w in self.wanted(con)}
        source = self.account if self.channel_posts else self.link
        down, paths = [], []
        with tx(con):
            for a in rows(con, f"SELECT * FROM {self.accounts}"):
                if (a["org_id"], a[self.link]) in linked:
                    continue
                con.execute(f"DELETE FROM {self.accounts} WHERE org_id = ? AND {self.link} = ?", (a["org_id"], a[self.link]))
                if self.channel_posts and a[source] and one(con, f"SELECT 1 FROM {self.accounts} WHERE org_id = ? AND {source} = ?", a["org_id"], a[source]):
                    continue
                for p in rows(con, f"SELECT post_id FROM {self.items} WHERE org_id = ? AND {source} = ? AND post_id IS NOT NULL", a["org_id"], a[source]):
                    con.execute("UPDATE posts SET hidden_at = COALESCE(hidden_at, ?) WHERE id = ?", (now(), p["post_id"]))
                    paths += wipe_post(con, p["post_id"])
                    down.append(p["post_id"])
                con.execute(f"DELETE FROM {self.items} WHERE org_id = ? AND {source} = ?", (a["org_id"], a[source]))
        if root:
            media.drop(root, [p for p in paths if photo_free(con, p)])
        return down

    def read(self, con, oid: int, link: str, account: str | None) -> None:
        """Record a lookup, including a missing account, without advancing the feed's first read."""
        con.execute(f"""INSERT INTO {self.accounts} (org_id, {self.link}, {self.account}, checked_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (org_id, {self.link}) DO UPDATE SET {self.account} = excluded.{self.account}, checked_at = excluded.checked_at""",
                    (oid, link, account, now()))

    def fresh(self, con, w: dict, items: list[dict]) -> list[dict]:
        """New items, oldest first; a first read takes the newest few from the last FIRST_DAYS."""
        o = one(con, "SELECT * FROM orgs WHERE id = ? AND status = 'active'", w["org"])
        if not o or not stories_open(con, o):
            return []
        since = w["seen"] if w["seen"] is not None else now() - FIRST_DAYS * 86400
        new = [p for p in items if p["at"] > since and not one(con, f"SELECT 1 FROM {self.items} WHERE {self.item} = ?", p["id"])]
        # Later rounds take the oldest first, so the rest of a backlog comes next round as seen_until moves up.
        return list(reversed(new[:FIRST_TAKE])) if w["seen"] is None else list(reversed(new))[:PER_ROUND]

    def take(self, con, w: dict, items: list[dict], photos: dict[str, dict]) -> list[int]:
        """Insert the club's posts and advance the source's cursor together."""
        made = []
        with tx(con):
            name = "" if self.channel_posts else one(con, "SELECT name FROM orgs WHERE id = ?", w["org"])["name"]
            for p in items:
                if one(con, f"SELECT 1 FROM {self.items} WHERE {self.item} = ?", p["id"]):
                    continue
                fid = mirror._photo(con, photos[p["id"]]) if p["id"] in photos else None
                title, body = self.text(p, name)
                pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, photo_file_id, comments_on, created_at)
                    VALUES (?, NULL, 'public', ?, ?, ?, 1, ?)""", (w["org"], title, body, fid, p["at"])).lastrowid
                if self.channel_posts:
                    con.execute("INSERT INTO yt_videos (video_id, org_id, channel_id, post_id, title, published_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (p["id"], w["org"], w["account"], pid, title, p["at"]))
                else:
                    con.execute("INSERT INTO ig_media (media_id, org_id, handle, post_id, published_at) VALUES (?, ?, ?, ?, ?)",
                                (p["id"], w["org"], w["handle"], pid, p["at"]))
                made.append(pid)
            base = w["seen"] if w["seen"] is not None else now() - FIRST_DAYS * 86400
            con.execute(f"UPDATE {self.accounts} SET seen_until = ? WHERE org_id = ? AND {self.link} = ?",
                        (max([base, *(p["at"] for p in items)]), w["org"], w[self.link]))
        return made

    async def post(self, con, http, root: Path, w: dict, items: list[dict], end: float | None = None) -> int:
        """One fetched feed: select new items, copy their pictures, then post even when a picture is unavailable."""
        new = await asyncio.to_thread(self.fresh, con, w, items)
        photos = {}
        for p in new:
            picture = self.picture(p)
            if not picture or (end is not None and time.monotonic() >= end):
                continue
            data = await download.fetch(http, picture, self.hosts, media.MAX_BYTES, types=("image/",), seconds=self.timeout)
            try:
                if data:
                    photos[p["id"]] = await asyncio.to_thread(media.save, data, root)
            except media.BadImage:
                pass  # no picture: the post goes without one
        return len(await asyncio.to_thread(self.take, con, w, new, photos)) if new or w["seen"] is None else 0
