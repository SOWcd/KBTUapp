"""The postman (SPEC §7), inside the web app's event loop (app.py lifespan).

- Postman: sends what logic.notify() queued in bot_outbox, as server templates (texts.py) in the user's
  language with a button into the app; only to users who let the bot write (can_dm). A user who blocked
  the bot loses can_dm until Telegram says otherwise.
- Ears: whatever someone writes to the bot (/start first of all) is answered with what the app is and a button
  into it; a receipt (Kaspi's PDF or a picture) goes to the sender's seat on hold.
No KBTU session outlives a request (SPEC §4.1), so the bot keeps none to refresh schedules with."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import html
import json
import fcntl
import logging
import os
import random
import re
import secrets
import sqlite3
import time
from collections import OrderedDict, deque
from pathlib import Path

import anyio.to_thread
import httpx

from . import ai, casting, checkin, db, download, instagram, llm, logic, media, mirror, mtbot, offsite, portal, receipt, swear, texts, tgc, tiktok, userbot, video, youtube
from .config import Config
from .logic import notifications, now, one, rows
from .logic.account import _Taken
from .logic.core import ApiError

log = logging.getLogger("kbtu.bot")

POLL = 2                    # seconds between outbox checks
AI_GAP = 10                 # seconds between translations (ai.py): a backlog drains without a burst
PEEK = 2                    # seconds between looks for Stars' pre-checkouts while a batch of updates runs (_checkout_watch)
CHECKOUT_HTTP = 3          # one answerPreCheckoutQuery at most: answers go in turn, so a hung one eats its neighbours' 10 s
CHECKOUT_RETRY = 1         # seconds between rounds of retries of the answers that failed
CHECKOUT_WINDOW = 8        # stop retrying after this: Telegram allows 10 s, and a try started later would land too late
_checked: deque[str] = deque(maxlen=256)  # pre-checkouts already answered: the look and the next round see the same ones
WAIT = 25                   # getUpdates: Telegram holds the request this long while nobody writes
FRESH = 300                 # an older message isn't answered: what piled up while nobody listened
SYNC_GAP = 0.25             # a chat sync's getChatMember calls: about 4 a second, beside the postman (logic/chatsync.py)
_sync_live = False          # a chat sync link exists (CHAT_SYNC): chat_member updates are asked for; _chat_sync keeps it
# A deploy stops the container (SIGTERM; Docker's grace is 10 s, then SIGKILL): stop() ends the long poll at once, a batch
# at its next update, the postman at its next message; jobs spawned beside the ears get the rest of DRAIN, then go.
# It starts only after uvicorn has closed its connections, and the lifespan waits DRAIN + 2 s before it cancels.
# ponytail: 6 s fits Docker's default grace; a longer stop_grace_period on the host can buy a longer DRAIN
DRAIN = 6
OFFSET_KEEP = 86400         # a stored offset older than this isn't trusted: Telegram keeps updates a day (and picks random ids after a week of silence)
_stop: asyncio.Event | None = None  # run()'s, while it runs; set by stop()
_stop_by = float("inf")     # time.monotonic() when the drain ends
_replay: int | None = None  # the update the last process died in the middle of (stored busy): handled again only where that is safe


# A bot whose owner has Telegram Premium can use custom emoji. If Telegram rejects them but accepts
# the plain version, disable the pack so subsequent messages send on the first try.
# Use the bot pack first and the others to fill gaps.
EMOJI_PACKS = ("NewsEmoji", "AnimatedAsianEmoji", "RestrictedEmoji")
_custom: dict[str, str] = {}   # plain emoji (no variation selector) -> custom_emoji_id
_custom_re: re.Pattern | None = None


async def load_pack(cfg: Config, http: httpx.AsyncClient) -> None:
    global _custom_re
    for pack in EMOJI_PACKS:
        try:
            answer = (await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getStickerSet", params={"name": pack})).json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("emoji pack %s: %s", pack, type(exc).__name__)
            continue
        stickers = (answer.get("result") or {}).get("stickers") or []
        for st in stickers:  # the first sticker for an emoji wins
            if st.get("custom_emoji_id") and st.get("emoji"):
                _custom.setdefault(st["emoji"].replace("\ufe0f", ""), st["custom_emoji_id"])
        log.warning("emoji pack %s: %d in all so far%s", pack, len(_custom), "" if answer.get("ok") else f" ({answer.get('description')})")
    _custom_re = re.compile("|".join(re.escape(e) + "\ufe0f?" for e in sorted(_custom, key=len, reverse=True))) if _custom else None


def premium(text: str) -> str:
    """Our plain emoji as the pack's, in HTML (parse_mode HTML everywhere the bot writes)."""
    if not _custom_re:
        return text
    if "<tg-emoji" in text:  # already the pack's (a mention's mark): wrapped once, never inside itself
        return re.sub(r"(<tg-emoji[^>]*>.*?</tg-emoji>)|([^<]+)", lambda m: m.group(1) or premium(m.group(2)), text, flags=re.S)
    return _custom_re.sub(lambda m: f'<tg-emoji emoji-id="{_custom[m.group(0).replace(chr(0xFE0F), "")]}">{m.group(0)}</tg-emoji>', text)


def fancy(body: dict) -> dict:
    """The pack's emoji in an HTML text or caption (premium emoji everywhere the bot writes); the same
    dict back when nothing changes."""
    key = "caption" if "caption" in body else "text"
    if not body.get(key) or body.get("parse_mode") != "HTML" or (t := premium(body[key])) == body[key]:
        return body
    return {**body, key: t}


async def _tg(cfg: Config, http: httpx.AsyncClient, method: str, body: dict, files: dict | None = None) -> httpx.Response:
    """A Telegram call whose text or caption (HTML) gets the pack's emoji (everywhere the bot writes, the
    channel and groups too); refused for them (400), once more plain, and the pack is off until a restart."""
    global _custom_re
    url, key = f"https://api.telegram.org/bot{cfg.bot_token}/{method}", "caption" if "caption" in body else "text"
    fancy = {**body, key: premium(body[key])} if body.get(key) and body.get("parse_mode") == "HTML" else body

    async def post(b: dict) -> httpx.Response:
        return await (http.post(url, data=b, files=files) if files else http.post(url, json=b))
    r = await post(fancy)
    if fancy is not body and fancy[key] != body[key] and r.status_code == 400 and re.search(r"emoji|entit", str(r.json().get("description")), re.I):
        why = str(r.json().get("description"))[:200]
        r = await post(body)
        if r.status_code == 200:  # it was the emoji: the pack goes off (broken HTML fails plain too and leaves it on)
            log.warning("emoji pack refused: %s", why)
            _custom_re = None
    return r


async def _send(cfg: Config, http: httpx.AsyncClient, body: dict) -> httpx.Response:
    return await _tg(cfg, http, "sendMessage", body)


def purge(cfg: Config, con) -> None:
    """The accounts whose week ran out (logic.delete_due), and their files on disk (app.py keeps them in the same places)."""
    home = Path(cfg.db_path).resolve().parent
    logic.delete_due(con)
    logic.drain_deleted_files(con)  # first: retry even when SQL erasure committed in an earlier round
    photos = logic.purge_takedowns(con)  # and what a moderator took down 30 days ago
    gone, pics = logic.events_gone(con)  # the admin's event deletes past their Undo's day
    media.drop(home / "receipts", gone)
    photos = photos + pics + logic.chats_gone(con)  # and chats removed from the catalog a week ago
    media.drop(home / "media", photos)
    media.drop(home / "media", [p for p in logic.wipe_hidden_posts(con) if logic.photo_free(con, p)])  # and the posts hidden 30 days ago


async def refresh_chats(cfg: Config, http: httpx.AsyncClient, con) -> None:
    root = Path(cfg.db_path).resolve().parent / "media"
    for c in rows(con, "SELECT id, url, org_id, tg_chat_id FROM chats"):
        if c["org_id"] and c["tg_chat_id"] and await chat_card(cfg, http, con, c["id"], c["tg_chat_id"]):
            continue  # our bot sits in it: Telegram's own card
        peek = await media.chat_peek(http, c["url"])
        if peek["image"]:
            try:
                peek["photo"] = (await asyncio.to_thread(media.save, peek["image"], root))["path"]
            except media.BadImage:
                pass
        if old := logic.chat_refreshed(con, c["id"], peek):
            if not one(con, "SELECT 1 FROM files WHERE path = ?", old):  # never a file something else still shows
                media.drop(root, [old])


async def chat_card(cfg: Config, http: httpx.AsyncClient, con, cid: int, tg_chat: int) -> bool:
    """An org's chat our bot sits in (PLAN 86): its card from Telegram (getChat: title, about, avatar; getChatMemberCount),
    never a message. False when Telegram won't say (the bot was removed: the t.me page again)."""
    api = f"https://api.telegram.org/bot{cfg.bot_token}"
    try:
        r = (await http.post(f"{api}/getChat", json={"chat_id": tg_chat})).json()
        if not r.get("ok"):
            if r.get("error_code") in (400, 403):  # no such chat for us any more
                logic.bot_left(con, tg_chat)
            return False
        ch, card = r["result"], {"title": r["result"].get("title"), "about": r["result"].get("description") or ""}
        n = (await http.post(f"{api}/getChatMemberCount", json={"chat_id": tg_chat})).json()
        card["members"] = n.get("result") if n.get("ok") else None
        if fid := (ch.get("photo") or {}).get("big_file_id"):
            f = (await http.post(f"{api}/getFile", json={"file_id": fid})).json()
            if f.get("ok") and f["result"].get("file_path") and int(f["result"].get("file_size") or 0) <= media.MAX_BYTES:
                img = await http.get(f"https://api.telegram.org/file/bot{cfg.bot_token}/{f['result']['file_path']}")
                if img.status_code == 200:
                    root = Path(cfg.db_path).resolve().parent / "media"
                    try:
                        card["photo"] = (await asyncio.to_thread(media.save, img.content, root))["path"]
                    except media.BadImage:
                        pass
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("chat card: %s", type(exc).__name__)
        return False
    root = Path(cfg.db_path).resolve().parent / "media"
    old = logic.chat_card(con, cid, card)
    _drop_free(con, root, old, card.get("photo"))  # the one replaced, or the new one when the chat was gone meanwhile
    return True


async def _userpics(cfg: Config, http: httpx.AsyncClient, con, n: int = 5) -> None:
    """Copy new Telegram photos first, then refresh stale copies for recently seen users."""
    root = Path(cfg.db_path).resolve().parent / "media"
    t = now()
    for u in logic.rows(con, """SELECT id, tg_photo_url, tg_photo_path, tg_photo_src FROM users WHERE tg_photo_url IS NOT NULL
            AND (tg_photo_src IS NOT tg_photo_url OR (seen_at >= ? AND (tg_photo_at IS NULL OR tg_photo_at < ?)))
            ORDER BY tg_photo_src IS NOT tg_photo_url DESC LIMIT ?""", t - 86400, t - 3 * 86400, n):
        old_path = u["tg_photo_path"]
        path = None
        try:
            data = await download.fetch(http, u["tg_photo_url"], download.TELEGRAM_PAGE + download.TELEGRAM_FILES, media.MAX_BYTES)
            if data:
                if old_path and Path(old_path).name == hashlib.sha256(data).hexdigest() and (root / f"{old_path}.t.webp").is_file():
                    path = old_path  # keep unchanged copies on disk without rewriting them
                else:
                    path = (await asyncio.to_thread(media.save, data, root))["path"]
        except (httpx.HTTPError, media.BadImage, OSError) as exc:
            log.warning("userpic: %s", type(exc).__name__)
        if path is None and u["tg_photo_src"] == u["tg_photo_url"]:
            path = old_path
        # only if the URL is still the one fetched: a newer photo meanwhile is the next round's
        if con.execute("UPDATE users SET tg_photo_path = ?, tg_photo_src = ?, tg_photo_at = ? WHERE id = ? AND tg_photo_url = ?",
                       (path, u["tg_photo_url"], now(), u["id"], u["tg_photo_url"])).rowcount:
            _drop_free(con, root, old_path if old_path != path else None)
        else:
            _drop_free(con, root, path)


def _drop_free(con, root: Path, *paths: str | None) -> None:
    """Saved pictures nothing shows (no files row names them) gone from disk."""
    media.drop(root, [p for p in paths if p and logic.photo_free(con, p)])


async def _avatar(peek: dict, root: Path) -> None:
    """A chat's t.me picture saved as its avatar (peek["photo"]); a broken picture or a full disk: none."""
    if peek.get("image"):
        try:
            peek["photo"] = (await asyncio.to_thread(media.save, peek["image"], root))["path"]
        except (media.BadImage, OSError):
            pass


def _refused(r: dict) -> bool:
    """Telegram refused this message for what it is (a caption too long, bad HTML), not for the channel (no rights, no
    such chat) or the moment (flood wait): sending it again won't help, and it mustn't hold up the posts after it."""
    return r.get("error_code") == 400 and not re.search(r"rights|chat not found|not a member|admin", str(r.get("description")), re.I)


async def post_channel(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """The events channel (logic.channel_due): a new post with the cover (or text without one), or the old one edited."""
    if not cfg.events_channel:
        return
    api = f"https://api.telegram.org/bot{cfg.bot_token}"
    root = Path(cfg.db_path).resolve().parent / "media"
    for post, thread in logic.channel_gone(con):  # deleted events: their posts go (one Telegram refuses, e.g. too old,
        for chat, mid in ((cfg.events_channel, post), *([thread.split()] if thread else [])):  # stays and is logged)
            r = (await http.post(f"{api}/deleteMessage", json={"chat_id": chat, "message_id": int(mid)})).json()
            if not r.get("ok"):
                log.warning("channel delete %s/%s: %s", chat, mid, str(r.get("description"))[:200])
                if r.get("error_code") != 400:  # a flood wait, Telegram down, no right yet: the next round tries again
                    return
        con.execute("DELETE FROM meta WHERE key = ?", (f"channel_gone:{post}",))
    # no button under the post: Telegram hides the comments then; an edit without one takes the old one off
    for e, text, cover, sig in logic.channel_due(con, cfg.bot_username):
        jpg = root / f"{cover}.jpg" if cover else None
        if e["channel_msg"]:  # the post is there: its words (and the cover, when it was posted with one) change
            how = "editMessageCaption" if e["channel_photo"] else "editMessageText"
            body = {"chat_id": cfg.events_channel, "message_id": e["channel_msg"], "parse_mode": "HTML",
                    **({"caption": text} if e["channel_photo"] else {"text": text, "link_preview_options": {"is_disabled": True}})}
            r = (await _tg(cfg, http, how, body)).json()
            if not r.get("ok") and "not modified" not in str(r.get("description")):
                log.warning("channel edit %d: %s", e["id"], str(r.get("description"))[:200])
                if "not found" not in str(r.get("description")) and not _refused(r):
                    return  # try again next round
            con.execute("UPDATE events SET channel_sig = ? WHERE id = ?", (sig, e["id"]))
            continue
        if jpg and jpg.exists():
            r = (await _tg(cfg, http, "sendPhoto", {"chat_id": cfg.events_channel, "caption": text, "parse_mode": "HTML"},
                           files={"photo": jpg.read_bytes()})).json()
        else:
            r = (await _tg(cfg, http, "sendMessage", {"chat_id": cfg.events_channel, "text": text, "parse_mode": "HTML",
                                                      "link_preview_options": {"is_disabled": True}})).json()
        if not r.get("ok"):  # the bot isn't the channel's admin, or a flood wait: next round
            log.warning("channel post %d: %s", e["id"], str(r.get("description"))[:200])
            if _refused(r):  # this post itself can't go (too long...): skipped until the event changes, the rest go on
                con.execute("UPDATE events SET channel_sig = ? WHERE id = ?", (sig, e["id"]))
                continue
            return
        con.execute("UPDATE events SET channel_msg = ?, channel_photo = ?, channel_sig = ? WHERE id = ?",
                    (r["result"]["message_id"], int(bool(jpg and jpg.exists())), sig, e["id"]))


def optimize_day(con) -> None:
    """After 04:00 Almaty, once a day: the planner's statistics (sqlite_stat1) brought up to date. Without them it picks
    indexes blind; 0x10002 looks at every table, analysis_limit keeps it to milliseconds on a big one."""
    local = int(time.time()) + 5 * 3600
    if local % 86400 < 4 * 3600 or not logic._once(con, "optimize_day", str(local // 86400)):
        return
    try:
        con.execute("PRAGMA analysis_limit = 1000")
        con.execute("PRAGMA optimize = 0x10002")
    except sqlite3.Error as exc:  # busy: tomorrow again, nothing depends on it
        log.warning("optimize failed: %s", exc)


def backup_day(cfg: Config, con) -> None:
    """After 04:00 Almaty, once a day: a full copy of the database into backups/ beside it, the last 14 kept. It guards against a bad deploy or a wrong delete, not a lost disk: that needs a copy elsewhere."""
    db_path = Path(cfg.db_path).resolve()
    # the copies db.py makes before a migration: two weeks, as the nightly ones (deleted accounts must not outlive them)
    for bak in db_path.parent.glob(f"{db_path.name}.v*.bak"):
        if bak.stat().st_mtime < time.time() - 14 * 86400:
            bak.unlink(missing_ok=True)
    root = db_path.parent / "backups"
    for old in root.glob("kbtu-*.db"):  # retention also runs when today's copy fails or is not due
        if old.stat().st_mtime < time.time() - 15 * 86400:
            old.unlink()
    global _backup_retry
    local = int(time.time()) + 5 * 3600
    day = str(local // 86400)
    if local % 86400 < 4 * 3600 or time.time() < _backup_retry or one(con, "SELECT 1 FROM meta WHERE key = 'backup_day' AND value = ?", day):
        return
    root.mkdir(exist_ok=True)
    out = root / f"kbtu-{time.strftime('%Y-%m-%d', time.gmtime(local))}.db"
    tmp = out.with_suffix(".tmp")  # a copy cut short (a full disk) never counts among the 14
    tmp.unlink(missing_ok=True)  # VACUUM INTO won't overwrite
    try:
        con.execute("VACUUM INTO ?", (str(tmp),))
    except sqlite3.Error as exc:
        log.warning("backup failed: %s", exc)
        tmp.unlink(missing_ok=True)
        _backup_retry = time.time() + 3600  # the day isn't marked: tried again in an hour, not every round
        return
    tmp.replace(out)
    con.execute("INSERT INTO meta (key, value) VALUES ('backup_day', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (day,))
    for old in sorted(root.glob("kbtu-*.db"))[:-14]:
        old.unlink()
    log.warning("backup: %s, %d KB", out.name, out.stat().st_size // 1024)


_backup_retry = 0.0  # a failed nightly copy waits until this (time.time()) before the next try
_offsite: asyncio.Task | None = None  # the upload running in its thread; one at a time


USERBOT_QUIET = 2 * 3600  # no sweep finished for this long (they run every half hour): the userbot is down


def userbot_round(con) -> None:
    """The owner hears once per outage that the userbot went quiet (meta userbot_ok: its heartbeat, mirror.alive;
    userbot_alert: raised), and once when it's back. No heartbeat at all (qa, tests, never set up): nothing."""
    beat, alert = one(con, "SELECT value FROM meta WHERE key = 'userbot_ok'"), one(con, "SELECT value FROM meta WHERE key = 'userbot_alert'")
    if not beat or bool(alert) == (now() - int(beat[0]) > USERBOT_QUIET):
        return
    for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
        logic.notify(con, uid, "userbot_ok" if alert else "userbot_off", f"ub:{alert[0]}" if alert else f"uo:{beat[0]}")
    if alert:
        con.execute("DELETE FROM meta WHERE key = 'userbot_alert'")
    else:
        con.execute("INSERT INTO meta (key, value) VALUES ('userbot_alert', ?)", (beat[0],))


def offsite_round(cfg: Config, con) -> None:
    """After the nightly copy (backup_day): it and the receipts to R2, on Sundays the media too (offsite.py). In a thread,
    so the postman isn't held; a day counts only after R2's 200, tried again hourly until then. Each object is named
    with its time: the bucket's lock refuses to overwrite one that a lost answer left behind."""
    global _offsite
    if _offsite and not _offsite.done():
        return
    local = int(time.time()) + 5 * 3600
    if local % 86400 < 4 * 3600:
        return
    date, home = time.strftime("%Y-%m-%d", time.gmtime(local)), Path(cfg.db_path).resolve().parent
    stamp, done = time.strftime("%Y-%m-%d-%H%M", time.gmtime(local)), lambda key: one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, date)
    copy = home / "backups" / f"kbtu-{date}.db"
    if not offsite.ready():  # no R2 keys or no age: nothing leaves the server; the creator hears it once (meta offsite_unset),
        # on the image only (DB_MUST_EXIST=1): development and tests run without R2 on purpose
        if os.environ.get("DB_MUST_EXIST") == "1" and copy.exists() and logic._once(con, "offsite_unset", "1"):
            log.warning("offsite: not configured, the nightly copy stays on this server")
            for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
                logic.notify(con, uid, "backup_failed", f"bf:{date}")
        return
    yday = time.strftime("%Y-%m-%d", time.gmtime(local - 86400))
    # two nights without a copy off the server (six tries tonight already): the admins hear it once per outage
    # (meta offsite_alert: the day it was raised), and once more when a copy gets through again
    alert = one(con, "SELECT value FROM meta WHERE key = 'offsite_alert'")
    admins = lambda: rows(con, "SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL")  # noqa: E731
    if alert and done("offsite_db"):
        logic.notify_staff(con, [r[0] for r in admins()], "backup_ok", f"bo:{date}")
        con.execute("DELETE FROM meta WHERE key = 'offsite_alert'")
    elif not alert and local % 86400 >= 10 * 3600 and not done("offsite_db") and not one(con, "SELECT 1 FROM meta WHERE key = 'offsite_db' AND value = ?", yday):
        logic.notify_staff(con, [r[0] for r in admins()], "backup_failed", f"bf:{date}")
        con.execute("INSERT INTO meta (key, value) VALUES ('offsite_alert', ?)", (date,))
    # deletions.log and its salt ride along: a copy restored from R2 alone must still re-run the deletions since (redelete)
    jobs = ([("offsite_db", [copy, home / "receipts", home / "deletions.log", home / "deletions.salt"], f"db/{stamp}.tar.age")]
            if copy.exists() and not done("offsite_db") else [])
    if time.gmtime(local).tm_wday == 6 and not done("offsite_media"):
        jobs.append(("offsite_media", [home / "media"], f"media/{stamp}.tar.age"))
    last = one(con, "SELECT value FROM meta WHERE key = 'offsite_try'")
    if not jobs or (last and now() - int(last["value"]) < 3600):
        return
    con.execute("INSERT INTO meta (key, value) VALUES ('offsite_try', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (str(now()),))
    _offsite = asyncio.get_running_loop().create_task(asyncio.to_thread(_offsite_run, cfg.db_path, home, date, jobs))


def _offsite_run(db_path: str, home: Path, date: str, jobs: list) -> None:
    for key, paths, name in jobs:
        try:
            size = offsite.upload(paths, name, home)
        except Exception as exc:  # a failed night is tried again in an hour; the log shows why
            log.warning("offsite %s failed: %s", name, exc)
            return
        con = db.connect(db_path)
        try:
            con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, date))
        finally:
            con.close()
        log.warning("offsite: %s, %d KB", name, size // 1024)


def _chores(cfg: Config, con) -> None:
    """The round's own database work, in a thread (send_due): with 15 s of busy_timeout a write burst would otherwise
    hold the API worker's event loop, /healthz included."""
    logic.strip_emoji_names(con)  # Normalize stored names once so the displayed names follow the club naming rules.
    logic.memo_week(con)  # Wednesday morning: next week's memo for DMP is ready (each runs once, by its meta key)
    logic.tba_day(con)    # 10:00: events still without a place, to their organizers
    logic.saved_day(con)  # 12:00: saved events tomorrow, to those not going
    logic.clubs.hidden_day(con)  # 11:00: a club too small for the registry, to its president, once
    logic.door_round(con)  # the door is open (early, or at T-30): each guest going hears it once
    logic.daily.guest_age_round(con)  # guest-list data and age marks expire a day after the event
    logic.santa.tick(con)  # Secret Santa's clock: the draw at the deadline, the reminders (one read of the games due)
    logic.stats_day(con)  # after midnight: yesterday's row for the admin's stats
    logic.course_day(con)  # September 1: every student's year of study a year on
    logic.pymk.night(con)  # People you may know: everyone's suggestions afresh, once a day
    casting.forget(con)   # daily: answers and notes of rounds whose results went out 60 days ago
    purge(cfg, con)       # accounts whose week to change their mind ran out
    logic.ms_sweep(con)   # unfinished Microsoft sign-ins after a week, used-link marks after a day
    backup_day(cfg, con)  # a nightly copy of the database, 14 kept
    optimize_day(con)     # the query planner's statistics, once a night
    userbot_round(con)    # the owner hears when the channels' userbot goes quiet, and when it's back
    logic.close_gone(con)  # reports of what went by itself (the queue, a GET, never writes)
    logic.tgcomments.sweep(con)  # the policy's retention even with the forum switched off (its old rows still go)
    logic.fchannel.sweep(con)


def _student(con, tg_id: int | None) -> sqlite3.Row | None:
    """Who writes to the bot, if a student signed in with KBTU (a typed-in row waiting for Microsoft is nobody yet)."""
    return one(con, """SELECT u.id, u.role, u.lang, s.first_name, s.last_name, s.first_lat, s.last_lat FROM users u
        JOIN students s ON s.user_id = u.id AND s.manual = 0 WHERE u.tg_id = ?""", tg_id)


_video_seen: set[int] = set()  # unconfirmed update IDs can appear both in a peek and in the next poll


def guard_key(cfg: Config) -> bytes:
    return hmac.new(cfg.token_key, b"kbtu-guard", hashlib.sha256).digest()


async def _join(cfg: Config, http: httpx.AsyncClient, con, req: dict) -> None:
    """A join request to an event's group: those signed up (and volunteers, the team) in, the rest declined. A club's
    chat linked in the app (the bot an admin that may add members): a confirmed student in, a banned person out, anyone
    else left to the chat's admins. In a chat
    whose guard bot we are (a query_id, answered within 10 s): a student in at once, a stranger gets the app to sign up
    (POST /api/guard lets them in after), a banned person out."""
    if qid := req.get("query_id"):
        chat, who = req["chat"]["id"], req["from"]["id"]
        d = logic.guard_join(con, chat, who)
        url = f"https://{cfg.domain}/?startapp=gq_{logic.guard_token(guard_key(cfg), chat, who, qid)}"
        r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/" + ("sendChatJoinRequestWebApp" if d == "app" else "answerChatJoinRequestQuery"),
                            json={"chat_join_request_query_id": qid, **({"web_app_url": url} if d == "app" else {"result": d})})
        if not r.json().get("ok"):
            log.warning("guard: %s", str(r.json().get("description"))[:200])
        return
    ok = logic.chat_join(con, req["chat"]["id"], req["from"]["id"])
    if ok is None:  # not an event's chat: a chat linked in the app lets a confirmed student in (owner, Nov 24)
        d = logic.guard_join(con, req["chat"]["id"], req["from"]["id"])
        if d not in ("approve", "decline"):  # someone we don't know, or a chat we don't know: its admins decide
            return
        ok = d == "approve"
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{'approve' if ok else 'decline'}ChatJoinRequest",
                    json={"chat_id": req["chat"]["id"], "user_id": req["from"]["id"]})


INLINE_EVENTS = 5  # the empty query's upcoming events; a typed one shows up to 20 matches
INLINE_POSTS = 3  # the empty query's own forum posts, newest first


def inline_answer(cfg: Config, con, q: dict) -> dict:
    """answerInlineQuery's body for "@KBTUappBot <words>" in any chat: only our templates, each with a button into the
    app. A student: my friend link, each club whose team link is live and that I may share (the "team" right; a typing
    pop-up never makes one), my recent signed forum posts live in the channel, and the afisha's upcoming events as an anonymous student sees them. Anyone else: one button."""
    tg = (q.get("from") or {}).get("id")
    me = _student(con, tg)
    lang = me["lang"] if me else str((q.get("from") or {}).get("language_code") or "")[:2]
    body: dict = {"inline_query_id": q["id"], "results": [], "is_personal": True, "cache_time": 10}
    if not me:
        body["button"] = {"text": texts.bot_message(lang, "welcome")[1], "web_app": {"url": f"https://{cfg.domain}/"}}
        return body
    app = f"https://t.me/{cfg.bot_username}?startapp="

    def article(rid: str, title: str, text: str, button: str, start: str, **more) -> dict:
        return {"type": "article", "id": rid, "title": title, **more,
                "input_message_content": {"message_text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
                "reply_markup": {"inline_keyboard": [[{"text": button, "url": app + start}]]}}

    words = str(q.get("query") or "").strip()[:64]
    out = body["results"]
    if not words:
        v = logic.Viewer(me["id"], me["role"], True)
        name = logic.shown_name(one(con, logic.PERSON + " WHERE u.id = ?", me["id"]))
        out.append(article("rf", *texts.share_invite("rf", lang, name=name), f"r_{logic._qr_code(con, me['id'], 'link_code')}"))
        mine = [oid for oid, r in logic._rights(con, v).items() if "team" in r]
        for o in rows(con, f"""SELECT o.id, o.name, i.token, i.expires_at FROM orgs o JOIN org_invites i ON i.org_id = o.id AND i.multi = 1
                AND i.revoked_at IS NULL AND i.expires_at > ? WHERE o.status = 'active' AND o.id IN ({','.join('?' * len(mine)) or 'NULL'})
                ORDER BY o.name""", now(), *mine):
            title, text, button = texts.share_invite("jm", lang, club=o["name"], until=texts.when(o["expires_at"], lang).split(",")[0])
            out.append(article(f"jm-{o['id']}", title, text, button, f"join_{o['id']}_{o['token']}"))
        # my own live forum posts, signed ones only: the one who sends an inline card shows in the chat, so an anonymous
        # post here would tell whose it is
        for p in rows(con, """SELECT id, body FROM fchan_posts WHERE user_id = ? AND anon = 0 AND status = 'live' AND tg_msg > 0
                ORDER BY id DESC LIMIT ?""", me["id"], INLINE_POSTS):
            title, text, button, words = texts.share_post(lang, p["body"])
            out.append(article(f"fp-{p['id']}", title, text, button, f"fp_{p['id']}", **({"description": words} if words else {})))
    # the afisha as a nobody sees it: published, public, on the general afisha (never drafts, hidden or members-only)
    evs = [e for e in logic.seats.events(con, logic.Viewer(0, "user", False)) if e["status"] == "published"
           and (not words or logic.search.hit(words, [e["title"], *((x or {}).get("title") for x in (e.get("i18n") or {}).values())]))]
    for e in evs[:20 if words else INLINE_EVENTS]:
        org = " × ".join([e["org"]["name"], *([e["coHost"]["name"]] if e["coHost"] else [])])
        place = texts.where(e["place"], e["online"], lang)
        caption, button = texts.share_event(lang, e["title"], e["startsAt"], place, org, e["price"], e["taken"])
        poster = f"https://{cfg.domain}/og/poster.jpg?c={(e['color'] or e['tint'] or '#3B6BFF').lstrip('#')}&e={e['emoji'] or 'sparkles_3d'}"
        out.append(article(f"ev-{e['id']}", e["title"], caption, button, f"ev_{e['id']}", thumbnail_url=poster,
                           description=" · ".join([texts.when(e["startsAt"], lang), *([place] if place else [])])))
    return body


def _wanted(cfg: Config) -> str:
    # edits: the forum's group, and a club's group with its swear filter on (an edit mustn't smuggle a word in)
    return json.dumps(["message", "edited_message", "callback_query", "inline_query", "chat_join_request", "my_chat_member", "pre_checkout_query",
                       # the forum channel's reactions (sent only where the bot is the channel's admin, and only when asked for)
                       *(["message_reaction_count"] if cfg.forum_channel else []),
                       # someone joining or leaving a club's linked chat (logic/chatsync.py; sent only where the bot is an admin)
                       *(["chat_member"] if _sync_live else [])])


async def _answer_checkout(cfg: Config, http: httpx.AsyncClient, q: dict) -> bool:
    """One try. True when there is no use in another: answered, or refused for good (a query too old, 400)."""
    good = logic.stars.checkout_ok(cfg.bot_token, q, (q.get("from") or {}).get("id"))
    why = {} if good else {"error_message": texts.pick(texts.STARS_REFUSED, str((q.get("from") or {}).get("language_code") or ""))}
    try:
        r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/answerPreCheckoutQuery", timeout=CHECKOUT_HTTP,
                            json={"pre_checkout_query_id": q["id"], "ok": good, **why})
        answered = r.status_code == 200 and r.json().get("ok") is True
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        log.warning("checkouts: %s", type(exc).__name__)  # the type only: the URL holds the token
        return False
    if not answered:
        log.warning("checkouts: %s", r.status_code)
    if answered or (400 <= r.status_code < 500 and r.status_code != 429):
        _checked.append(q["id"])
        return True
    return False


async def _checkouts(cfg: Config, http: httpx.AsyncClient, updates: list[dict]) -> None:
    """Stars' pre-checkouts, answered once each: no database, nothing slow. Everyone's first try comes before anyone's
    retry, so one failing answer doesn't spend its neighbours' 10 s."""
    todo = [q for u in updates if (q := u.get("pre_checkout_query")) and q["id"] not in _checked]
    end = time.monotonic() + CHECKOUT_WINDOW
    while todo := [q for q in todo if not await _answer_checkout(cfg, http, q)]:
        if time.monotonic() + CHECKOUT_RETRY >= end:
            return  # not marked answered: the next look tries again, and a query gone stale ends with its 400
        await asyncio.sleep(CHECKOUT_RETRY)


def stop() -> None:
    """The lifespan's shutdown (SIGTERM, a deploy): what is under way finishes, within DRAIN; nothing new starts."""
    global _stop, _stop_by
    if _stop is None:  # before run() got going: it sees this and doesn't start
        _stop = asyncio.Event()
    if not _stop.is_set():
        _stop_by = time.monotonic() + DRAIN
        _stop.set()


def _stopping() -> bool:
    return _stop is not None and _stop.is_set()


async def _nap(seconds: float) -> None:
    """asyncio.sleep, cut short by stop()."""
    if _stop is None:
        await asyncio.sleep(seconds)
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_stop.wait(), seconds)


async def _or_stop(aw):
    """aw's result, or None when stop() comes first (aw is cancelled)."""
    task = asyncio.ensure_future(aw)
    if _stop is None:
        return await task
    waiter = asyncio.ensure_future(_stop.wait())
    try:
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        waiter.cancel()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return None if task.cancelled() else task.result()


def _save(cfg: Config, con, offset: int, busy: bool, reply: dict | None = None, ms: int = 1000) -> None:
    """Where the ears are (meta bot_offset), after each update: the next process resumes there (_resume), so nothing
    handled before a stop or a crash is handled again. busy: the update at `offset` has started (a crash may leave it
    half done); reply: its answer, the work behind it done, which the next process sends if this one dies sending it.
    Best effort, a second at most: a skipped write costs only this (Telegram's own confirmation at the next poll holds)."""
    state = {"bot": cfg.bot_token.split(":")[0], "next": offset, "at": int(time.time()),
             **({"busy": 1} if busy else {}), **({"reply": reply} if reply else {})}
    try:
        db.maybe(con, con.execute, "INSERT INTO meta (key, value) VALUES ('bot_offset', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                 (json.dumps(state),), ms=ms)
    except sqlite3.Error as exc:
        log.warning("offset: %s", type(exc).__name__)


def _keep_videos(cfg: Config, before: set[int]) -> None:
    """The group videos started (_video_seen), kept beside the offset: a batch the next process gets again doesn't send
    them twice."""
    if _video_seen <= before:
        return
    try:
        con = db.connect(cfg.db_path)  # its own: the batch's may be inside a thread's transaction right now
        try:
            db.maybe(con, con.execute, "INSERT INTO meta (key, value) VALUES ('bot_videos', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                     (json.dumps(sorted(_video_seen)),), ms=1000)
        finally:
            con.close()
    except sqlite3.Error as exc:
        log.warning("offset: %s", type(exc).__name__)


def _resume(cfg: Config, con) -> tuple[int, dict | None]:
    """At start: the stored offset, and the answer the last process died sending (handed out once, and only while
    FRESH). 0 when none is stored, or it is another bot's, or too old (or from the future: the clock jumped) to trust;
    Telegram's own confirmation then decides, which lags by at most a batch. Also what the last process had started:
    its group videos, and the update it died in the middle of (_replay)."""
    global _replay
    _replay = None
    try:
        got = one(con, "SELECT value FROM meta WHERE key = 'bot_offset'")
        s = json.loads(got[0]) if got else {}
        vids = one(con, "SELECT value FROM meta WHERE key = 'bot_videos'")
        vids = json.loads(vids[0]) if vids else []
    except (sqlite3.Error, ValueError) as exc:
        log.warning("offset: %s", type(exc).__name__)
        return 0, None
    if isinstance(s, dict) and s.get("reply"):  # once: dying while sending it again doesn't send it a third time
        try:
            con.execute("UPDATE meta SET value = ? WHERE key = 'bot_offset'", (json.dumps({k: v for k, v in s.items() if k != "reply"}),))
        except sqlite3.Error as exc:  # not forgotten: then not sent either
            log.warning("offset: %s", type(exc).__name__)
            s.pop("reply")
    if not isinstance(s, dict) or type(s.get("next")) is not int or type(s.get("at")) is not int:
        return 0, None
    age = time.time() - s["at"]
    if s.get("bot") != cfg.bot_token.split(":")[0] or not -300 <= age <= OFFSET_KEEP:
        return 0, None
    if isinstance(vids, list):
        _video_seen.update(i for i in vids if type(i) is int)
    _replay = s["next"] if s.get("busy") else None
    return s["next"], s["reply"] if age <= FRESH and isinstance(s.get("reply"), dict) else None


async def _drain() -> None:
    """After stop(): jobs spawned beside the ears (tgc.spawn: /all, swear warnings, group videos, the AI's looks) finish
    until the deadline; the rest are cancelled. None runs again: their updates are done (an /all cut short calls nobody
    twice, a group video isn't sent twice)."""
    while pending := [t for t in tgc._tasks if not t.done()]:
        if (left := _stop_by - time.monotonic()) <= 0:
            break
        await asyncio.wait(pending, timeout=left)
    if pending := [t for t in tgc._tasks if not t.done()]:
        log.warning("stop: %d jobs cut", len(pending))
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def _wind_down(calm: list[asyncio.Task], rest: list[asyncio.Task]) -> None:
    """A child of run()'s group: at stop(), the ears and the postman end their update or message by themselves (until the
    deadline); the loops that start over anyway (videos, translations, the mirror, the chat sync) are cancelled."""
    await _stop.wait()
    for t in rest:
        t.cancel()
    _, late = await asyncio.wait(calm, timeout=max(0.0, _stop_by - time.monotonic()))
    for t in late:
        log.warning("stop: cut %s", t.get_coro().__name__)
        t.cancel()


async def _checkout_watch(cfg: Config, http: httpx.AsyncClient, offset: int, done: asyncio.Event) -> None:
    """Telegram allows 10 s for a pre-checkout and a batch can spend longer on one receipt's OCR, so while a batch runs
    this looks for new ones. getUpdates at the batch's own offset confirms nothing (they all come again to the next
    round, which only skips the answered ones), and it never overlaps the long poll: hear waits for this to end."""
    from .bot_groups import _video_updates  # here: it imports bot.py
    while True:
        try:
            await asyncio.wait_for(done.wait(), PEEK)
            return
        except asyncio.TimeoutError:
            pass
        try:
            # ponytail: getUpdates hands out the first 100 pending updates, so a pre-checkout behind a backlog of 100+ can
            # miss its 10 s and the donor taps again; upgrade: a webhook (a look past the batch would confirm what it hasn't run)
            r = await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getUpdates", params={"offset": offset, "timeout": 0, "allowed_updates": _wanted(cfg)})
            updates = r.json().get("result") or []
            if not _stopping():  # a video started now would be cut by the drain and then skipped as seen; the next process starts it
                before = set(_video_seen)
                _video_updates(cfg, http, updates)
                _keep_videos(cfg, before)
            await _checkouts(cfg, http, updates)
        except Exception as exc:  # noqa: BLE001 - hear awaits this: nothing here may cost the batch its offset
            log.warning("checkouts: %s", type(exc).__name__)


async def hear(cfg: Config, http: httpx.AsyncClient, offset: int) -> int:
    """One long poll: answers what came and returns the next offset (the same one when the round failed). Each update
    handled is stored (_save) before the next starts; after stop() the poll ends at once and a batch at its next update."""
    from .bot_dm import _file, _lang, _receipt, _reply, _sched_file, _schedule, _suggest, _tapped, _welcome  # here: they import bot.py
    from .bot_groups import _discussion_bg, _event_copy, _group, _member, _seen, _swear, _video_updates
    global _replay
    try:
        r = await _or_stop(http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getUpdates",
                                    params={"offset": offset, "timeout": WAIT, "allowed_updates": _wanted(cfg)}, timeout=WAIT + 10))
        if r is None:  # stopped while waiting: nothing of this poll is confirmed, the next process gets it all
            return offset
        answer = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("ears: %s", type(exc).__name__)
        await _nap(5)
        return offset
    if not answer.get("ok"):  # 409: a webhook is set elsewhere, so this bot's messages go there; say so, now and then
        log.warning("ears: %s", str(answer.get("description", r.status_code))[:200])
        await _nap(60)
        return offset
    batch = answer["result"]
    if _stopping():  # it came as the stop did: left for the next process, unconfirmed (pre-checkouts can't wait for it)
        await _checkouts(cfg, http, batch)
        return offset
    if cfg.tiktok:
        _video_seen.intersection_update(u["update_id"] for u in batch)
        before = set(_video_seen)
        _video_updates(cfg, http, batch)
        _keep_videos(cfg, before)
    await _checkouts(cfg, http, batch)  # Stars' pre-checkouts need no database and have 10 s to answer
    con = db.connect(cfg.db_path)
    done = asyncio.Event()
    watch = None
    try:  # the watcher only once connected: finally is what ends it, and a look alive past this round would clash with the next long poll (409)
        watch = asyncio.create_task(_checkout_watch(cfg, http, offset, done)) if batch else None
        # the forum channel's comments first: a stranger's comment is gone before anything slow in the batch runs
        if mine := [u for u in answer["result"] if tgc.ours(cfg, u)]:
            try:
                await tgc.gate(cfg, http, con, mine)
            except Exception as exc:  # noqa: BLE001 - the rest of the batch still goes
                log.warning("tgc: %s", type(exc).__name__)
        # guarded join requests next, before anything slow (10 s to answer) and before the ban skip (guard_join declines)
        for upd in answer["result"]:
            if (upd.get("chat_join_request") or {}).get("query_id"):
                try:
                    await _join(cfg, http, con, upd["chat_join_request"])
                except Exception as exc:  # noqa: BLE001 - the rest of the batch still goes
                    log.warning("guard: %s", type(exc).__name__)
        for upd in answer["result"]:
            if _stopping():  # the rest of the batch goes to the next process, from here
                offset = upd["update_id"]
                break
            _save(cfg, con, upd["update_id"], True)  # the ones before it done, this one started
            cut = upd["update_id"] == _replay  # the last process died in the middle of this one
            msg = {}
            try:  # all of it: a locked database even in the ban check would replay the whole batch
                offset = upd["update_id"] + 1
                if not tgc.ours(cfg, upd) and ((upd.get("message") or {}).get("chat") or {}).get("type") in ("group", "supergroup"):
                    _seen(con, upd["message"])  # cheap, never blocks: first, so a message the swear filter deletes still counts
                if not tgc.ours(cfg, upd) and await _swear(cfg, http, con, upd.get("message") or upd.get("edited_message") or {}):
                    continue  # a club's group: a swear word, deleted (before the ban skip: the chat is everyone's)
                if "edited_message" in upd or "pre_checkout_query" in upd or tgc.ours(cfg, upd):  # edits matter only there; pre-checkouts are answered (above)
                    continue
                if cm := upd.get("chat_member"):  # a linked chat's join or leave; recorded before the offset moves on
                    try:
                        new, where = cm.get("new_chat_member") or {}, (cm.get("chat") or {}).get("id")
                        if where and logic.chatsync.in_chat(new):  # /all's memory of who is in a club's chat (logic/chatlist.py)
                            logic.chatlist.seen(con, where, new.get("user"))
                        elif where:  # left, banned, or restricted out of it
                            logic.chatlist.unseen(con, where, int((new.get("user") or {}).get("id") or 0))
                        logic.chatsync.member_update(con, cm, upd["update_id"])
                    except sqlite3.Error as exc:
                        log.warning("chat sync: %s", type(exc).__name__)
                        await asyncio.sleep(1)
                        return upd["update_id"]
                    continue
                if rc := upd.get("message_reaction_count"):
                    if (rc.get("chat") or {}).get("id") == cfg.forum_channel:
                        logic.fchannel.reacted(con, rc)
                    continue
                msg = upd.get("message") or {}
                if payment := msg.get("successful_payment"):  # before the ban skip: the Stars have arrived; no answer but Telegram's own receipt
                    try:
                        await asyncio.to_thread(logic.stars.paid, con, payment, (msg.get("from") or {}).get("id"), cfg.bot_token)
                    except sqlite3.Error as exc:  # paid but unrecorded: this update again next round (paid is idempotent by the charge id)
                        log.warning("stars paid: %s", type(exc).__name__)
                        await asyncio.sleep(1)
                        return upd["update_id"]
                    continue
                if (msg.get("chat") or {}).get("type") == "private" and str(msg.get("text") or "").split("@")[0].split()[:1] == ["/paysupport"]:  # before the ban skip: Telegram's rules want it for every payer
                    await _send(cfg, http, _reply(msg["chat"]["id"], *texts.bot_message(_lang(con, msg), "paysupport", tg_id=msg["chat"]["id"])))
                    continue
                sender = ((upd.get("callback_query") or upd.get("inline_query") or upd.get("chat_join_request") or msg).get("from") or {}).get("id")
                group = (msg.get("chat") or {}).get("type") in ("group", "supergroup")  # a group's housekeeping serves everyone in it
                if sender and not group and one(con, "SELECT 1 FROM users WHERE tg_id = ? AND banned_at IS NOT NULL", sender):
                    continue  # banned: the bot neither answers nor acts for him
                if "callback_query" in upd:
                    # cut in the middle: an offer decided, a mute's "useful" counted may have run (once is safer: a
                    # button left untouched is tapped again); a receipt's pick runs again (losing it costs a seat)
                    if cut and not str(upd["callback_query"].get("data") or "").startswith("rc:"):
                        log.warning("ears: a tap cut by the last stop, skipped")
                        continue
                    await _tapped(cfg, http, con, upd["callback_query"], cut)
                    continue
                if "inline_query" in upd:  # "@KBTUappBot ..." typed in any chat (inline mode, BotFather /setinline)
                    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/answerInlineQuery", json=inline_answer(cfg, con, upd["inline_query"]))
                    continue
                if "chat_join_request" in upd:
                    if not upd["chat_join_request"].get("query_id"):  # a guarded one was answered above
                        await _join(cfg, http, con, upd["chat_join_request"])
                    continue
                if "my_chat_member" in upd:
                    await _member(cfg, http, con, upd["my_chat_member"])
                    continue
                if (msg.get("chat") or {}).get("type") in ("group", "supergroup"):  # an event's group: only its linking matters
                    if cut and not msg.get("migrate_to_chat_id"):  # /all or a chat's linking may have run: never twice
                        log.warning("ears: a group command cut by the last stop, skipped")
                        continue
                    if _event_copy(cfg, msg):
                        tgc.spawn(_discussion_bg(cfg, http, msg), "events")
                    else:
                        await _group(cfg, http, con, msg)
                    continue
                # a receipt is taken even if it waited (the hold decides); a stale hello isn't answered (FRESH)
                # chats a message links to (typed or forwarded; a photo or a file is a receipt unless forwarded)
                if msg.get("chat_shared") or (msg.get("forward_origin") or not _file(msg)) and not _sched_file(msg) and logic.chat_links(msg):
                    try:
                        body = await _suggest(cfg, http, con, msg)
                    except Exception:  # a full disk, a broken picture: answer nothing, but never get stuck on this update
                        log.exception("suggest")
                        body = None
                elif not _sched_file(msg) and _file(msg):
                    # a receipt behind a burst of sign-ups: "database is locked" in the catch-all below would lose the update
                    # with no answer and the hold would run out (paid, no seat); so this update again next round, as a
                    # Stars payment does (the same picture is the same file, add_receipt one transaction)
                    try:
                        body = await _receipt(cfg, http, con, msg, again=cut)
                    except sqlite3.OperationalError as exc:
                        if "locked" not in str(exc) and "busy" not in str(exc):
                            raise
                        log.warning("receipt: %s", type(exc).__name__)
                        await asyncio.sleep(1)
                        return upd["update_id"]
                else:
                    body = await _schedule(cfg, http, con, msg) if _sched_file(msg) else _welcome(con, cfg, msg)
                if body:
                    con.execute("UPDATE users SET can_dm = 1 WHERE tg_id = ?", (body["chat_id"],))  # writing to the bot unblocks it
                    _save(cfg, con, offset, False, body)  # the work is done: a stop now costs at most the answer, which the next process sends
                    await _send(cfg, http, body)
            except Exception as exc:  # one update that breaks (a page the parser chokes on) never stops the bot for everyone
                log.warning("ears: %s", type(exc).__name__)  # the type only: never a page's words
                if not isinstance(exc, httpx.HTTPError) and _sched_file(msg) and (msg.get("chat") or {}).get("type") == "private":
                    try:
                        await _send(cfg, http, _reply(msg["chat"]["id"], *texts.bot_message(_lang(con, msg), "sched_bad")))
                    except Exception as again:
                        log.warning("ears: %s", type(again).__name__)
        if batch:
            _save(cfg, con, offset, False)
        if _replay is not None and _replay < offset:
            _replay = None
    finally:
        done.set()
        if watch:
            await watch
        con.close()
    return offset


async def _ears(cfg: Config, http: httpx.AsyncClient) -> None:
    """Until stop(): from where the last process stopped (_resume), the answer it died sending first."""
    con = db.connect(cfg.db_path)
    try:
        offset, reply = _resume(cfg, con)
    finally:
        con.close()
    if reply:
        try:
            await _send(cfg, http, reply)
        except httpx.HTTPError as exc:
            log.warning("ears: %s", type(exc).__name__)
    while not _stopping():
        try:
            offset = await hear(cfg, http, offset)
        except Exception:  # a bug in one round must not stop the ears
            log.exception("ears round")
            await _nap(5)
    # stopped between updates: once more, waiting longer (the drain has time), so a write the batch skipped on a busy
    # database doesn't leave an answer to send again or a finished update marked started (an update a retry path left
    # unfinished runs again either way)
    con = db.connect(cfg.db_path)
    try:
        _save(cfg, con, offset, False, ms=3000)
    finally:
        con.close()


async def _postman(cfg: Config, http: httpx.AsyncClient) -> None:
    from .outbox import send_due  # here, not at the top: outbox imports bot.py's plumbing
    while not _stopping():
        try:
            await send_due(cfg, http)
        except Exception:  # a bug in one round must not stop the postman
            log.exception("bot round")
        await _nap(POLL)


async def _call(cfg: Config, http: httpx.AsyncClient, method: str, params: dict, gap: float = SYNC_GAP) -> dict | None:
    """A paced call beside the ears (the chat sync, /all): a 429 waits as told; None: the network, or still too fast."""
    for _ in range(5):
        await asyncio.sleep(gap)
        try:
            f = fancy(params)
            r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{method}", json=f)
            answer = r.json()
            if r.status_code == 400 and f is not params and re.search(r"emoji|entit", str(answer.get("description")), re.I):
                r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{method}", json=params)  # the pack refused: plain
                answer = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("%s: %s", method, type(exc).__name__)  # the type only: the URL holds the token
            await asyncio.sleep(10)  # the network: again in a while, not in a tight loop
            return None
        if r.status_code != 429:
            return answer
        await asyncio.sleep(float((answer.get("parameters") or {}).get("retry_after", 5)))
    return None


async def _chat_sync(cfg: Config, http: httpx.AsyncClient) -> None:
    """Clubs mirrored from their chats (CHAT_SYNC, logic/chatsync.py): whether to ask Telegram for chat_member updates, and
    the sweeps, a step at a time at about 4 calls a second; a 429 waits as told. Never inside a request or the postman."""
    global _sync_live
    bot_id = int(cfg.bot_token.split(":")[0])

    async def call(method: str, params: dict) -> dict | None:
        return await _call(cfg, http, method, params)
    con = db.connect(cfg.db_path)
    while True:
        try:
            _sync_live = logic.chatsync.live(con)
            if not await logic.chatsync.ask_step(con, call) and not await logic.chatsync.step(con, call, bot_id):
                await asyncio.sleep(30)
        except Exception:  # noqa: BLE001 - the loop must outlive one bad round
            log.exception("chat sync")
            await asyncio.sleep(30)


async def _videos(cfg: Config) -> None:
    """Event videos (video.py), one at a time in this one process: whatever was being compressed when the last postman
    died starts over. Videos no event holds leave the disk a day after their upload."""
    con = db.connect(cfg.db_path)  # one thread at a time uses it (check_same_thread=False), as in send_due
    root = Path(cfg.db_path).resolve().parent
    swept, reset = 0.0, False
    while True:
        try:
            if not reset:  # inside the guard: a busy database at start is tried again, not the loop's end
                await anyio.to_thread.run_sync(con.execute, "UPDATE videos SET status = 'queued' WHERE status = 'working'")
                reset = True
            if time.monotonic() - swept > 3600:
                swept = time.monotonic()
                for vid, path in await anyio.to_thread.run_sync(logic.stale_videos, con):
                    (root / "uploads" / str(vid)).unlink(missing_ok=True)
                    for ext in (".mp4", ".webp", ".t.webp", ".jpg") if path else ():
                        (root / "media" / f"{path}{ext}").unlink(missing_ok=True)
            x = await anyio.to_thread.run_sync(logic.next_video, con)
            if not x:
                await asyncio.sleep(3)
                continue
            src = root / "uploads" / str(x["id"])
            try:
                done = await video.compress(src, root / "media", bool(x["wide"]))
                await anyio.to_thread.run_sync(logic.video_done, con, x["id"], done)
            except (video.BadVideo, OSError) as exc:
                log.warning("video %d: %s", x["id"], str(exc)[-200:])
                await anyio.to_thread.run_sync(logic.video_done, con, x["id"], None, "too_long" if str(exc) == "too_long" else "not_a_video")
            src.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - the loop must outlive one bad video
            log.exception("videos")
            await asyncio.sleep(30)


async def _translator(cfg: Config) -> None:
    """Event and club texts into the other two languages (ai.py), one every few seconds, on the AI chain (llm.py); off
    without any of its keys. Every link resting: back in a few minutes."""
    on = llm.available(cfg)
    log.warning("ai translation: %s", "on" if on else "off (no AI keys)")
    try:  # never let the translator take the postman down with it (asyncio.gather)
        con = db.connect(cfg.db_path)
        logic.ai_note(con, on=on)
    except Exception:  # noqa: BLE001
        log.exception("translator start")
        return
    if not on:
        return
    async with httpx.AsyncClient(timeout=120) as http:
        while True:
            try:
                job = logic.ai_next(con)
                if not job:
                    await sort_chat(cfg, http, con)  # nothing to translate: a directory chat into its section
                else:
                    kind, rid, was = job
                    try:
                        src, tr = await ai.translate(cfg, http, was, logic.AI_LIMIT[kind], con)
                        logic.ai_save(con, kind, rid, was, src, tr)
                    except ai.Busy as exc:
                        logic.ai_note(con, error=f"busy: {exc}")
                        await asyncio.sleep(300)
                    except ai.Failed as exc:
                        log.warning("ai %s %d: %s", kind, rid, exc)
                        logic.ai_failed(con, kind, rid, str(exc))
                    except Exception as exc:  # noqa: BLE001 - a surprise counts a try, so one row never blocks the rest
                        log.exception("ai %s %d", kind, rid)
                        logic.ai_failed(con, kind, rid, type(exc).__name__)
                await asyncio.sleep(AI_GAP)
            except Exception:  # noqa: BLE001 - the loop must outlive one bad answer
                log.exception("translator")
                await asyncio.sleep(30)


async def sort_chat(cfg: Config, http: httpx.AsyncClient, con) -> bool:
    """One directory chat into its section by the AI (ai.chat_section: its public title and description), applied at
    once; no answer: it stays unsorted and is asked about again in an hour (logic.sort_next). False: none waiting."""
    c = logic.sort_next(con)
    if not c:
        return False
    if section := await ai.chat_section(cfg, http, c["title"], c["about"], con):
        logic.sort_save(con, c["id"], section)
    return True


async def _userbot(cfg: Config) -> None:
    """The channel mirror (userbot.py); never takes the postman down with it (asyncio.gather)."""
    try:
        await userbot.run(cfg)
    except Exception:  # noqa: BLE001
        log.exception("userbot")


async def _commands(cfg: Config, http: httpx.AsyncClient) -> None:
    """Telegram's "/" menu, set at each start (cheap, idempotent): English is the default, ru and kk by the user's language."""
    for scope, by_lang in texts.COMMANDS.items():
        for lang, cmds in by_lang.items():
            try:
                await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/setMyCommands", json={
                    "scope": {"type": scope}, **({} if lang == "en" else {"language_code": lang}),
                    "commands": [{"command": c, "description": d} for c, d in cmds]})
            except httpx.HTTPError:
                log.warning("setMyCommands failed")  # the menu waits for the next start; the bot works without it
    # "add to group as admin" opens with every right on: a link's admin= can't turn on tags or join requests on iOS
    rights = {f"can_{r}": True for r in ("manage_chat", "delete_messages", "manage_video_chats", "restrict_members",
              "promote_members", "change_info", "invite_users", "post_stories", "edit_stories", "delete_stories",
              "pin_messages", "manage_topics", "manage_tags")}
    try:
        res = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/setMyDefaultAdministratorRights",
                              json={"rights": {"is_anonymous": False, **rights}})
        log.warning("default admin rights: %s", res.text[:200])
    except httpx.HTTPError:
        log.warning("setMyDefaultAdministratorRights failed")


async def run(cfg: Config) -> None:
    """Forever, in one process: every worker (and, during a deploy, the other container) waits on a lock file next to
    the database, and whoever holds it is the postman, since Telegram's rate limit is the bot's, not a worker's; if
    that process dies, the lock goes with it and another takes over within seconds. Then the outbox, every few
    seconds, and the ears (one poller at a time: Telegram refuses a second). Until stop(): what is under way finishes
    (DRAIN), and only then is the lock let go, so the next leader starts where this one stopped (_resume)."""
    global _stop, _stop_by
    if not _stopping():
        _stop, _stop_by = asyncio.Event(), float("inf")
    try:
        await _lead(cfg)
    finally:
        _stop = None


async def _lead(cfg: Config) -> None:
    global _sync_live
    with open(f"{cfg.db_path}.bot.lock", "w") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if _stopping():
                    return
                await _nap(5)
        log.warning("postman in process %d", os.getpid())  # one line per start (warning: the level the container's log keeps)
        log.warning("receipts ocr: %s", await asyncio.to_thread(receipt.ready))
        if cfg.chat_sync:  # before the first poll: a join in that window would never come again
            _sync_live = logic.chatsync.live(db.connect(cfg.db_path))
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                await load_pack(cfg, http)
                await _commands(cfg, http)
                # a failing child takes its siblings down, all awaited, then they start again under the same lock: no
                # poller outlives leadership (a plain gather leaves them running after the lock is let go)
                while not _stopping():
                    try:
                        async with asyncio.TaskGroup() as tg:
                            calm = [tg.create_task(_postman(cfg, http)), tg.create_task(_ears(cfg, http))]
                            rest = [tg.create_task(job) for job in (_videos(cfg), _translator(cfg), _userbot(cfg),
                                                                    *([_chat_sync(cfg, http)] if cfg.chat_sync else []))]
                            tg.create_task(_wind_down(calm, rest))
                    except Exception:  # noqa: BLE001 - restarted under the same lock; a cancel (shutdown) goes through
                        log.exception("bot children")
                        await _nap(5)
                await _drain()  # inside: the jobs still use this client
        finally:
            await mtbot.close()  # the bot's MTProto session goes before the lock does
