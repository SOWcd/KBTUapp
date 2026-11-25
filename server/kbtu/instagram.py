"""A club's Instagram posts in its news, by themselves (owner, Nov 25): no club signs in anywhere. The app's own
Instagram professional account (IG_USER_ID, IG_TOKEN) asks Meta's Graph API for each club's public business or
creator account by its handle (Business Discovery), every half hour (outbox.send_due); each new post becomes one of the
club's posts, as the Telegram mirror (mirror.py) does with a channel's: the caption as the club's own public text (its
first line the title), the picture copied (a video's cover), the post's link last (News draws it as an Instagram
button). Nobody is notified; the club's rules for stories hold (clubs.stories_open). A handle taken off the club takes
its posts down. Only the club's media is asked for: no follower, liker or commenter, nothing about people is stored.

Meta's limit for the app is 200 calls an hour per user (we are one): a round makes at most CALLS (one per account,
sent BATCH to an HTTP request), the accounts least recently read first; a usage header past BUSY %, a rate-limit error
or a failed request pauses every round (doubling up to PAUSE_MAX); a refused token pauses PAUSE_MAX and says so in the
log. Here the database and the parsing; sweep() does the network."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import download, media, mirror
from .logic import now, one, photo_free, rows, tx, wipe_post
from .logic.clubs import stories_open

GRAPH = "https://graph.facebook.com/v24.0/"  # a Graph API version lives two years: move it on when Meta retires it
CDN = ("cdninstagram.com", "fbcdn.net")      # where Instagram's pictures are (media_url, thumbnail_url)
FIRST_TAKE, FIRST_DAYS = 5, 30               # an account linked anew: at most its last 5 posts of the last 30 days
PER_ROUND = 5                                # an account's new posts in one round at most (the rest next round)
ASK = 12                                     # an account's latest posts asked for each round
RETRY = 86400                                # a handle with no business/creator account behind it: asked again a day later
CALLS, BATCH = 90, 50                        # calls a round (two rounds an hour: 180 < 200), calls in one HTTP request
BUSY = 80                                    # % of a usage header at which the rounds pause
PAUSE, PAUSE_MAX = 1800, 12 * 3600           # the first pause, doubled each failure in a row, at most
RATE = {4, 17, 32, 613, 80002}               # Meta's "too many calls" codes (app, user, page, custom, Instagram)
TOKEN = 190                                  # the token expired or was revoked: the owner makes a new one (README)
TRANSIENT = {1, 2}                           # Meta's own trouble ("unknown", "service unavailable"): asked again next round
TIMEOUT = 30                                 # seconds for one batch request
PIC_TIMEOUT = 10                             # seconds for one picture
BUDGET = 60                                  # seconds a round may start new pictures in: the postman's round waits on it
JSON_BYTES = 2 * 1024 * 1024                 # a batch's answer at most

# a club link that is an Instagram account: instagram.com/<handle> (not a post, a reel or Instagram's own pages)
_LINK = re.compile(r"https://(?:www\.|m\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?(?:[?#].*)?")
_NOT_HANDLE = {"p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct", "about", "developer", "legal"}
_MEDIA_ID = re.compile(r"\d{1,30}")
_PERMALINK = re.compile(r"https://www\.instagram\.com/(?:p|reel|tv)/[\w-]{5,40}/?")
log = logging.getLogger("kbtu.instagram")


def handle(url: str) -> str | None:
    """A club link that is an Instagram account: its handle, lowercase; else None."""
    m = _LINK.fullmatch(url.strip()) if isinstance(url, str) else None
    h = m.group(1).lower() if m else None
    return h if h and h not in _NOT_HANDLE and not h.startswith(".") and ".." not in h else None


def wanted(con) -> list[dict]:
    """The clubs' Instagram handles, each with what is known of it (its account id, how far it was taken)."""
    links = []
    # every club's, hidden ones too: hiding a club hides its posts already, only a link taken off takes them down
    # (forget); fresh() posts for active clubs alone
    for o in rows(con, "SELECT id, links FROM orgs WHERE links IS NOT NULL"):
        try:
            urls = json.loads(o["links"] or "[]")
        except ValueError:
            continue
        for url in urls if isinstance(urls, list) else []:
            if h := handle(url):
                links.append((o["id"], h))
    known = {(r["org_id"], r["handle"]): r for r in rows(con, "SELECT * FROM ig_accounts")}
    return [{"org": oid, "handle": h, **({"account": k["ig_id"], "seen": k["seen_until"], "checked": k["checked_at"]}
                                         if (k := known.get((oid, h))) else {"account": None, "seen": None, "checked": None})}
            for oid, h in dict.fromkeys(links)]


def due(con, at: int) -> list[dict]:
    """This round's accounts: the least recently read first, CALLS at most; a handle with no account waits RETRY."""
    ws = [w for w in wanted(con) if not (w["checked"] is not None and w["account"] is None and at - w["checked"] < RETRY)]
    return sorted(ws, key=lambda w: w["checked"] or 0)[:CALLS]


def forget(con, root: Path | None = None) -> list[int]:
    """Handles their club no longer links: their posts taken down and wiped like a deleted channel post (mirror.gone),
    the rows gone. The posts taken down."""
    linked = {(w["org"], w["handle"]) for w in wanted(con)}
    down, paths = [], []
    with tx(con):
        for a in rows(con, "SELECT org_id, handle FROM ig_accounts"):
            if (a["org_id"], a["handle"]) in linked:
                continue
            con.execute("DELETE FROM ig_accounts WHERE org_id = ? AND handle = ?", (a["org_id"], a["handle"]))
            for m in rows(con, "SELECT post_id FROM ig_media WHERE org_id = ? AND handle = ? AND post_id IS NOT NULL", a["org_id"], a["handle"]):
                con.execute("UPDATE posts SET hidden_at = COALESCE(hidden_at, ?) WHERE id = ?", (now(), m["post_id"]))
                paths += wipe_post(con, m["post_id"])
                down.append(m["post_id"])
            con.execute("DELETE FROM ig_media WHERE org_id = ? AND handle = ?", (a["org_id"], a["handle"]))
    if root:
        media.drop(root, [p for p in paths if photo_free(con, p)])
    return down


def read(con, oid: int, h: str, account: str | None) -> None:
    """A handle asked about: its account id, or None (no business/creator account there: asked again after RETRY)."""
    con.execute("""INSERT INTO ig_accounts (org_id, handle, ig_id, checked_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (org_id, handle) DO UPDATE SET ig_id = excluded.ig_id, checked_at = excluded.checked_at""",
                (oid, h, account, now()))


def parse_media(items) -> list[dict]:
    """An account's posts as Business Discovery lists them, newest first: {id, caption, picture, link, at}. Anything
    malformed is skipped, never raised. A video's picture is its cover; a post with none goes without one."""
    out = []
    for m in items if isinstance(items, list) else []:
        if not isinstance(m, dict):
            continue
        mid, link, caption = str(m.get("id", "")), m.get("permalink"), m.get("caption")
        try:
            at = int(datetime.strptime(str(m.get("timestamp", "")), "%Y-%m-%dT%H:%M:%S%z").timestamp())
        except ValueError:
            continue
        if not _MEDIA_ID.fullmatch(mid) or not isinstance(link, str) or not _PERMALINK.fullmatch(link):
            continue
        pic = m.get("thumbnail_url") if m.get("media_type") == "VIDEO" else m.get("media_url")
        out.append({"id": mid, "caption": caption if isinstance(caption, str) else "", "at": at, "link": link,
                    "picture": pic if isinstance(pic, str) and download.allowed(pic, CDN) else None})
    return sorted(out, key=lambda x: -x["at"])


def fresh(con, w: dict, posts: list[dict]) -> list[dict]:
    """The posts to bring now, oldest first: newer than what was taken (on a first read: the last FIRST_DAYS, at most
    FIRST_TAKE), not seen before, PER_ROUND at most; none for a club that may not post stories."""
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND status = 'active'", w["org"])
    if not o or not stories_open(con, o):
        return []
    since = w["seen"] if w["seen"] is not None else now() - FIRST_DAYS * 86400
    new = [p for p in posts if p["at"] > since and not one(con, "SELECT 1 FROM ig_media WHERE media_id = ?", p["id"])]
    # first read: the newest few; after that the oldest first, so a backlog's rest comes next round (seen_until moves up)
    return list(reversed(new[:FIRST_TAKE])) if w["seen"] is None else list(reversed(new))[:PER_ROUND]


def text(caption: str, name: str, link: str) -> tuple[str, str]:
    """A post's title and body: the caption split as a channel post's (mirror._split), the post's link last."""
    p = mirror._split(caption, name)
    return p["title"], f"{p['body']}\n\n{link}" if p["body"] else link


def take(con, w: dict, posts: list[dict], photos: dict[str, dict]) -> list[int]:
    """The new posts as the club's (photos: media.save's answer per media id), and how far the account was read.
    The posts made."""
    made = []
    with tx(con):
        name = one(con, "SELECT name FROM orgs WHERE id = ?", w["org"])["name"]
        for p in posts:
            if one(con, "SELECT 1 FROM ig_media WHERE media_id = ?", p["id"]):
                continue
            fid = mirror._photo(con, photos[p["id"]]) if p["id"] in photos else None
            title, body = text(p["caption"], name, p["link"])
            pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, photo_file_id, comments_on, created_at)
                VALUES (?, NULL, 'public', ?, ?, ?, 1, ?)""", (w["org"], title, body, fid, p["at"])).lastrowid
            con.execute("INSERT INTO ig_media (media_id, org_id, handle, post_id, published_at) VALUES (?, ?, ?, ?, ?)",
                        (p["id"], w["org"], w["handle"], pid, p["at"]))
            made.append(pid)
        base = w["seen"] if w["seen"] is not None else now() - FIRST_DAYS * 86400
        con.execute("UPDATE ig_accounts SET seen_until = ? WHERE org_id = ? AND handle = ?",
                    (max([base, *(p["at"] for p in posts)]), w["org"], w["handle"]))
    return made


def query(cfg, h: str) -> str:
    """One account's Business Discovery call (h is a checked handle: letters, digits, dots, underscores)."""
    fields = f"media.limit({ASK}){{id,caption,media_type,media_url,thumbnail_url,permalink,timestamp}}"
    return f"{cfg.ig_user_id}?fields=business_discovery.username({h}){{id,{fields}}}"


def _error(body) -> int | None:
    """A Graph error's code (None: not an error answer)."""
    try:
        e = (json.loads(body) if isinstance(body, (str, bytes)) else body or {}).get("error")
        return int(e.get("code")) if isinstance(e, dict) else None
    except (ValueError, TypeError, AttributeError):
        return None


def busy(headers) -> bool:
    """Meta's usage headers (percent of the hour's allowance) say to stop: any figure past BUSY."""
    worst = 0.0
    for name in ("x-app-usage", "x-business-use-case-usage"):
        try:
            v = json.loads(headers.get(name) or "{}")
        except ValueError:
            continue
        found = [v] if name == "x-app-usage" else [x for lst in v.values() if isinstance(lst, list) for x in lst]
        for d in found:
            if isinstance(d, dict):
                worst = max([worst, *(float(d[k]) for k in ("call_count", "total_cputime", "total_time")
                                      if isinstance(d.get(k), (int, float)))])
    return worst >= BUSY


async def _batch(http: httpx.AsyncClient, cfg, urls: list[str]) -> tuple[list | None, int | None, httpx.Headers]:
    """One batch request: each call's answer in order ({code, body}, or None when that call timed out at Meta), or None
    for the whole with its error code; and the usage headers. The token goes in the body, never in a URL or a log."""
    try:
        r = await http.post(GRAPH, data={"access_token": cfg.ig_token, "include_headers": "false",
                                         "batch": json.dumps([{"method": "GET", "relative_url": u} for u in urls])},
                            timeout=TIMEOUT, follow_redirects=False)
        if len(r.content) > JSON_BYTES:
            return None, None, r.headers
        if r.status_code != 200:
            return None, _error(r.content), r.headers
        answers = r.json()
        return (answers, None, r.headers) if isinstance(answers, list) and len(answers) == len(urls) else (None, None, r.headers)
    except (httpx.HTTPError, ValueError):
        return None, None, httpx.Headers()


def paused(con, at: int) -> bool:
    p = one(con, "SELECT value FROM meta WHERE key = 'ig_pause'")
    return bool(p) and int(p["value"].split(":")[0]) > at


def pause(con, seconds: int | None = None) -> None:
    """Every round waits: `seconds`, or PAUSE doubled for each failure in a row (PAUSE_MAX at most)."""
    p = one(con, "SELECT value FROM meta WHERE key = 'ig_pause'")
    fails = int(p["value"].split(":")[1]) + 1 if p else 1
    wait = seconds or min(PAUSE_MAX, PAUSE * 2 ** (fails - 1))
    con.execute("INSERT INTO meta (key, value) VALUES ('ig_pause', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (f"{now() + wait}:{fails}",))


def calm(con) -> None:
    """A round that went through: the failures in a row start again from none."""
    con.execute("DELETE FROM meta WHERE key = 'ig_pause'")


async def sweep(cfg, http: httpx.AsyncClient, con) -> int:
    """One round (outbox.send_due, every half hour): handles taken off forgotten, then the due accounts asked in batches,
    their new posts brought in. Off without IG_USER_ID and IG_TOKEN. The posts made."""
    if not (cfg.ig_user_id and cfg.ig_token):
        return 0
    root = Path(cfg.db_path).resolve().parent / "media"
    await asyncio.to_thread(forget, con, root)
    if await asyncio.to_thread(paused, con, now()):
        return 0
    ws = await asyncio.to_thread(due, con, now())
    made, end, trouble = 0, time.monotonic() + BUDGET, None
    for i in range(0, len(ws), BATCH):
        chunk = ws[i:i + BATCH]
        answers, code, headers = await _batch(http, cfg, [query(cfg, w["handle"]) for w in chunk])
        if answers is None:
            trouble = code if code is not None else "request"
            break
        for w, a in zip(chunk, answers):
            try:
                if not isinstance(a, dict):
                    continue  # this call timed out at Meta: asked again next round
                if a.get("code") != 200:
                    code = _error(a.get("body"))
                    if code in RATE or code == TOKEN:
                        trouble = code
                    elif code not in TRANSIENT:  # not a business or creator account, renamed, gone: asked again a day later
                        await asyncio.to_thread(read, con, w["org"], w["handle"], None)
                    continue
                found = json.loads(a.get("body") or "{}").get("business_discovery") or {}
                w["account"] = str(found.get("id") or "") or None
                await asyncio.to_thread(read, con, w["org"], w["handle"], w["account"])
                if not w["account"]:
                    continue
                new = await asyncio.to_thread(fresh, con, w, parse_media((found.get("media") or {}).get("data")))
                photos = {}
                for p in new:
                    if not p["picture"] or time.monotonic() >= end:
                        continue
                    data = await download.fetch(http, p["picture"], CDN, media.MAX_BYTES, types=("image/",), seconds=PIC_TIMEOUT)
                    try:
                        if data:
                            photos[p["id"]] = await asyncio.to_thread(media.save, data, root)
                    except media.BadImage:
                        pass  # no picture: the post goes without one
                if new or w["seen"] is None:
                    made += len(await asyncio.to_thread(take, con, w, new, photos))
            except Exception as exc:  # noqa: BLE001  one account's trouble never stops the others or the round
                log.warning("instagram %s: %s", w["handle"], type(exc).__name__)
        if trouble is not None or busy(headers):
            break
    if trouble == TOKEN:
        log.warning("instagram: IG_TOKEN was refused (expired or revoked): make a new one (README), rounds wait %d h", PAUSE_MAX // 3600)
        await asyncio.to_thread(pause, con, PAUSE_MAX)
    elif trouble is not None:
        log.warning("instagram: %s, rounds pause", f"Graph error {trouble}" if isinstance(trouble, int) else "the request failed")
        await asyncio.to_thread(pause, con)
    elif ws and busy(headers):
        await asyncio.to_thread(pause, con, 3600)  # near the hour's allowance: one hour off, not a failure
    elif ws:
        await asyncio.to_thread(calm, con)
    return made
