"""The postman's chores (outbox.send_due runs them before each round's messages): the nightly retention sweep and
backup with its offsite copy, the database's upkeep, the userbot's heartbeat, the chats' cards and the Telegram
userpics copied to /media, and the public events posted to the channel."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import httpx

from . import casting, db, download, logic, media, offsite
from .bot import _tg
from .config import Config
from .logic import now, one, rows

log = logging.getLogger("kbtu.bot")


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
    """An org's chat our bot sits in: its card from Telegram (getChat: title, about, avatar; getChatMemberCount),
    never a message. False when Telegram won't say (the bot was removed: the t.me page again)."""
    try:
        r = (await _tg(cfg, http, "getChat", {"chat_id": tg_chat})).json()
        if not r.get("ok"):
            if r.get("error_code") in (400, 403):  # no such chat for us any more
                logic.bot_left(con, tg_chat)
            return False
        ch, card = r["result"], {"title": r["result"].get("title"), "about": r["result"].get("description") or ""}
        n = (await _tg(cfg, http, "getChatMemberCount", {"chat_id": tg_chat})).json()
        card["members"] = n.get("result") if n.get("ok") else None
        if fid := (ch.get("photo") or {}).get("big_file_id"):
            f = (await _tg(cfg, http, "getFile", {"file_id": fid})).json()
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


USERPICS = 5  # photos copied per postman round


async def _userpics(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """Copy new Telegram photos first, then refresh stale copies for recently seen users."""
    root = Path(cfg.db_path).resolve().parent / "media"
    t = now()
    for u in logic.rows(con, """SELECT id, tg_photo_url, tg_photo_path, tg_photo_src FROM users WHERE tg_photo_url IS NOT NULL
            AND (tg_photo_src IS NOT tg_photo_url OR (seen_at >= ? AND (tg_photo_at IS NULL OR tg_photo_at < ?)))
            ORDER BY tg_photo_src IS NOT tg_photo_url DESC LIMIT ?""", t - 86400, t - 3 * 86400, USERPICS):
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
    root = Path(cfg.db_path).resolve().parent / "media"
    for post, thread in logic.channel_gone(con):  # deleted events: their posts go (one Telegram refuses, e.g. too old,
        for chat, mid in ((cfg.events_channel, post), *([thread.split()] if thread else [])):  # stays and is logged)
            r = (await _tg(cfg, http, "deleteMessage", {"chat_id": chat, "message_id": int(mid)})).json()
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
    logic.rooms.purge_round(con)  # game rooms 3 hours after their last change
    logic.santa.tick(con)  # Secret Santa's clock: the draw at the deadline, the reminders (one read of the games due)
    logic.stats_day(con)  # after midnight: yesterday's row for the admin's stats
    logic.course_day(con)  # September 1: every student's year of study a year on
    logic.pymk.night(con)  # People you may know: everyone's suggestions afresh, once a day
    casting.forget(con)   # daily: answers and notes of rounds whose results went out 60 days ago
    purge(cfg, con)       # accounts whose week to change their mind ran out
    logic.ms_sweep(con)   # unfinished Microsoft sign-ins after a week, used-link marks after a day, held share cards after an hour
    backup_day(cfg, con)  # a nightly copy of the database, 14 kept
    optimize_day(con)     # the query planner's statistics, once a night
    userbot_round(con)    # the owner hears when the channels' userbot goes quiet, and when it's back
    logic.close_gone(con)  # reports of what went by itself (the queue, a GET, never writes)
    logic.tgcomments.sweep(con)  # the policy's retention even with the forum switched off (its old rows still go)
    logic.fchannel.sweep(con)
