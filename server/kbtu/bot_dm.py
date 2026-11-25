"""Private chats with the bot (bot.py's ears hand each message here): /start's welcome and the chat picker, a chat link
suggested, the class timetable sent as a saved page, a Kaspi receipt (a PDF or a picture) to the sender's seat on hold,
and the taps on the buttons under the bot's messages ("Don't send these" among them)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from collections import OrderedDict
from pathlib import Path

import anyio.to_thread
import httpx

from . import db, logic, media, portal, receipt, texts
from .bot import FRESH, _avatar, _drop_free, _student, _tg
from .config import Config
from .logic import notifications, now, one, rows
from .logic.account import _Taken
from .logic.core import ApiError

log = logging.getLogger("kbtu.bot")


def _welcome(con, cfg: Config, msg: dict) -> dict | None:
    """The answer to a private message: what the app is and a button into it, in the person's language (the app's if
    they have used it, else Telegram's). /start's parameter (t.me/KBTUappBot?start=ev_5) is handed on to the app."""
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or now() - int(msg.get("date") or 0) > FRESH:
        return None
    u = one(con, "SELECT lang FROM users WHERE tg_id = ?", chat["id"])
    words = str(msg.get("text") or "").split()
    arg = words[1] if len(words) == 2 and words[0] == "/start" and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", words[1]) else ""
    if words[:1] == ["/exit"]:
        arg = "exit"
    if [w.split("@")[0] for w in words[:1]] == ["/chat"] or arg == "chat":  # "Suggest a chat" uses Telegram's own chat picker.
        return _chat_picker(con, cfg, msg)
    # /exit or ?start=exit: "help me get out" as a message with its button, to forward to any chat
    text, button = texts.bot_message(u["lang"] if u else str((msg.get("from") or {}).get("language_code") or "")[:2], "exit" if arg == "exit" else "welcome")
    return {"chat_id": chat["id"], "text": text, "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp{'=' + arg if arg else ''}"}]]}}


def _lang(con, msg: dict) -> str:
    u = one(con, "SELECT lang FROM users WHERE tg_id = ?", (msg.get("chat") or {}).get("id"))
    return u["lang"] if u else str((msg.get("from") or {}).get("language_code") or "")[:2]


def _chat_picker(con, cfg: Config, msg: dict) -> dict:
    """Two buttons that open Telegram's own list of the student's chats: channels, groups. Any of them; a closed one then needs its invite link, since we can't make one. A student only."""
    chat, lang = msg["chat"], _lang(con, msg)
    if not _student(con, chat["id"]):
        return _reply(chat["id"], *texts.bot_message(lang, "chat_signin"), "", cfg)
    channel, group = texts.bot_message(lang, "chat_buttons")
    pick = lambda rid, label: [{"text": label, "request_chat": {"request_id": rid, "chat_is_channel": rid == 1,  # noqa: E731
                                                              "request_title": True, "request_username": True}}]
    return {"chat_id": chat["id"], "text": texts.bot_message(lang, "chat_pick")[0], "parse_mode": "HTML",
            "reply_markup": {"keyboard": [pick(1, channel), pick(2, group)], "resize_keyboard": True, "one_time_keyboard": True}}


async def _tg_chat(cfg: Config, http: httpx.AsyncClient | None, url: str) -> dict | None:
    """A public chat as Telegram itself sees it (getChat by its @name): type, title, description, topics. None for an
    invite link (Telegram won't say), a person or a typo, or no answer."""
    if "/+" in url or http is None:
        return None
    try:
        r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/getChat", json={"chat_id": "@" + url.rsplit("/", 1)[1]})).json()
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    c = r.get("result") if isinstance(r, dict) and r.get("ok") else None
    return c if isinstance(c, dict) and c.get("type") in ("channel", "group", "supergroup") else None


async def suggest(cfg: Config, http: httpx.AsyncClient | None, con, uid: int, url: str, tg_chat: int | None = None,
                  channel: bool | None = None, gate: bool = True) -> tuple[str, str, str]:
    """A chat suggested by a student (the bot's picker, a message to the bot, or the app's sheet): checked, looked up
    (Telegram's getChat for a public one, its t.me page for the avatar and members; a person or a bot is neither), then
    waiting for the admins. (outcome, title, kind): outcome sent, waiting, exists, org (a club's: on its page), limit,
    later (Telegram didn't answer), slow (within 10 s of the last; gate=False: the caller checked), notchat; kind
    channel, group, forum or invite (a closed chat), with the title, for sent and the known ones."""
    root, peek = Path(cfg.db_path).resolve().parent / "media", {}
    try:
        logic.suggest_check(con, uid, url, tg_chat)
        if gate and not await asyncio.to_thread(logic._once, con, f"suggest_at:{uid}", str(now() // 10)):  # one look at t.me per 10 s per student
            return "slow", "", ""
        peek = await media.chat_peek(http, url)
        if not peek["ok"]:
            return "later", "", ""
        tg = await _tg_chat(cfg, http, url)
        if peek["members"] is None and not tg:
            return "notchat", "", ""
        await _avatar(peek, root)
        if tg:
            peek |= {"title": tg.get("title") or peek.get("title"), "about": tg.get("description") or peek.get("about")}
            kind = "channel" if tg["type"] == "channel" else "forum" if tg.get("is_forum") else "group"
        else:
            kind = "channel" if (channel if channel is not None else peek.get("channel")) else "group"
        title = await asyncio.to_thread(logic.suggest_chat, con, uid, url, kind, tg_chat, peek)  # writes: lock waits off the loop
        _drop_free(con, root, peek.get("photo"))  # a club's row took the suggestion: it keeps its own avatar
        return "sent", title, "invite" if "/+" in url else kind
    except logic.ApiError as exc:  # caught again inside the write (two at once): the saved avatar goes if nothing shows it
        _drop_free(con, root, peek.get("photo"))
        if exc.code != "conflict":
            return "limit", "", ""
        if exc.message == "pending":
            await asyncio.to_thread(logic.chat_asked_too, con, uid, url, tg_chat)  # told too when it's approved
        c = logic.known_chat(con, url, tg_chat)
        return ({"pending": "waiting", "org": "org"}.get(exc.message, "exists"), c["title"] if c else "",
                ("invite" if "/+" in c["url"] else "forum" if c["forum"] else c["kind"]) if c else "")


async def _suggest(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> dict | None:
    """The chats a private message names, straight into the moderation queue: picked in the picker (chat_shared), or
    linked in a message typed or forwarded (logic.chat_links, 10 at most). One template answer naming each chat as
    Telegram calls it, never the sender's own words. Nothing joins the catalog before staff approve it, whoever sent
    it; a club's own channel is linked in Studio, not here."""
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or now() - int(msg.get("date") or 0) > FRESH:
        return None
    lang, shared = _lang(con, msg), msg.get("chat_shared") or {}
    done = lambda text: {"chat_id": chat["id"], "text": text, "parse_mode": "HTML", "reply_markup": {"remove_keyboard": True}}  # noqa: E731
    u = _student(con, chat["id"])
    if not u:
        return _reply(chat["id"], *texts.bot_message(lang, "chat_signin"), "", cfg)
    if shared and not shared.get("username"):
        return done(texts.bot_message(lang, "chat_invite")[0])  # a closed chat from the picker: its invite link, please
    urls = [f"https://t.me/{str(shared['username']).lower()}"] if shared else logic.chat_links(msg)
    if not urls:
        return done(texts.bot_message(lang, "chat_private")[0])
    if not logic._once(con, f"suggest_at:{u['id']}", str(now() // 10)):  # one message's look at t.me per 10 s per student
        return done(texts.bot_message(lang, "chat_later")[0])
    got = [await suggest(cfg, http, con, u["id"], url, shared.get("chat_id") if shared else None,
                         shared.get("request_id") == 1 if shared else None, gate=False) for url in urls]
    return done(texts.chat_reply(lang, got))


def _file(msg: dict) -> dict | None:
    """A receipt in a message: Kaspi's PDF (Share → Telegram sends it as a file), a picture sent as a file, or a photo."""
    d = msg.get("document") or {}
    if d.get("mime_type") == "application/pdf" or str(d.get("mime_type") or "").startswith("image/"):
        return d
    return (msg.get("photo") or [None])[-1]  # the biggest size comes last


SCHED_FILES = (".webarchive", ".mht", ".mhtml", ".html", ".htm")
SCHED_MIMES = {"application/x-webarchive", "multipart/related", "message/rfc822", "text/html"}
SCHED_MAX = 20 * 1024 * 1024  # what a bot may download (getFile); a saved schedule page is ~0.4-7 MB


def _sched_file(msg: dict) -> dict | None:
    """The portal's schedule page saved on the phone: Safari's Web Archive, Chrome's .mht (or the page itself)."""
    d = msg.get("document") or {}
    name, mime = str(d.get("file_name") or "").lower(), str(d.get("mime_type") or "").lower()
    # iOS sometimes sends "..._webarchive" (the dot turned into "_"), so the type and that spelling count too
    if name.endswith(SCHED_FILES) or name.endswith(tuple("_" + e[1:] for e in SCHED_FILES)) or mime in SCHED_MIMES:
        return d
    # Telegram may show a saved page as just "file" (no extension, octet-stream or no mime): a candidate whose content
    # decides (portal.page_html sniffs it), in a private chat only; a receipt (pdf, image) never is
    return d if (d and not _file(msg) and (msg.get("chat") or {}).get("type") == "private"
                 and (mime in ("", "application/octet-stream") or "." not in name)) else None


def _sched_named(msg: dict) -> bool:
    d = msg.get("document") or {}
    name, mime = str(d.get("file_name") or "").lower(), str(d.get("mime_type") or "").lower()
    return name.endswith(SCHED_FILES) or name.endswith(tuple("_" + e[1:] for e in SCHED_FILES)) or mime in SCHED_MIMES


async def _schedule(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> dict | None:
    """A student's week from the portal's schedule page (portal.py; PLAN 26; Share -> Web Archive ->
    Telegram -> the bot): it replaces their classes when the page's name is theirs (the Microsoft one), each class
    keeping its names in the languages sent before (the portal switched to another language, the page sent again).
    The answer has counts and language names only. The file is read in memory and never kept; nothing of the page
    goes to the log. The student ID on it, once the name matched, may correct the account's (_page_sid)."""
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return None
    u = _student(con, chat["id"])
    lang = u["lang"] if u else str((msg.get("from") or {}).get("language_code") or "")[:2]
    say = lambda kind, start="", **f: _reply(chat["id"], *texts.bot_message(lang, kind, **f), start, cfg)  # noqa: E731
    if not u:  # a file that only might be a page isn't the student's to be told off for: the welcome
        return say("sched_signin") if _sched_named(msg) else _welcome(con, cfg, msg)
    d = _sched_file(msg) or {}
    if int(d.get("file_size") or 0) > SCHED_MAX:
        return say("sched_big")
    try:
        r = await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getFile", params={"file_id": d.get("file_id")})
        data = (await http.get(f"https://api.telegram.org/file/bot{cfg.bot_token}/{r.json()['result']['file_path']}")).content
        week = await asyncio.to_thread(lambda: portal.parse(portal.page_html(data)))
    except portal.NotSchedule as exc:
        log.info("schedule: not a schedule page (%s)", exc)
        return say("sched_not")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("schedule: %s", type(exc).__name__)
        return say("sched_bad")
    # the Cyrillic names or the Latin ones (the portal may write either, transliterated its own way)
    if not any(portal.same_person(week.name, f or "", l or "") for f, l in ((u["first_name"], u["last_name"]), (u["first_lat"], u["last_lat"]))):
        return say("sched_other")
    got = await asyncio.to_thread(logic.save_schedule, con, u["id"], week.lessons, week.lang)
    if got is None:  # the account deleted while the page was read: its week doesn't come back
        return say("sched_signin")
    await asyncio.to_thread(_page_sid, con, u["id"], week.sid)
    page, words = got["lang"], texts.pick(texts.SCHED_LANG, lang)
    same, changes = page in got["had"], got["added"] + got["removed"] + got["moved"]
    if not got["was"] or not page or not same and len(got["has"]) < 2:
        return say("sched_ok", "sched", n=len(week.lessons))  # the first week, or a new language with nothing of the old left
    said = (texts.bot_message(lang, "sched_same", language=words[page]) if same else
            texts.bot_message(lang, "sched_added", language=words[page], languages=", ".join(words[x] for x in got["has"])))[0]
    if changes or same:
        said += " " + texts.bot_message(lang, "sched_changed" if changes else "sched_nochange", n=changes)[0]
    return _reply(chat["id"], said, texts.bot_message(lang, "sched_ok", n=len(week.lessons))[1], "sched", cfg)


def _page_sid(con, uid: int, sid: str | None) -> None:
    """The student ID on a page whose name matched, written over the account's when it differs, silently, with the
    audit line `kbtu.admin fix sid` leaves (old and new). A saved page is plain HTML anyone can edit, so it is trusted
    no further than a typo: the same year and degree letter only (those decide the perks: a 1st-year bachelor's free
    seats), and only as the account's one correction (My data's `fixed`, which this spends: after it a page is a
    suggestion for support, an audit line, or an edited one could take a classmate's unclaimed ID). One held by another
    account is left and the founder hears (no ID in the notice or the log). Tries count with Settings' (sid_tries). All
    under one write lock: a parallel PATCH /api/me can't change the ID between the year check and the write."""
    if not sid:
        return
    with db.tx(con):
        s = one(con, "SELECT student_id, consent_version, manual, fixed FROM students WHERE user_id = ?", uid)
        if not s or s["manual"] or logic.core.is_staff(s) or s["student_id"] == sid:
            return  # unconfirmed: its name is self-typed, so a page "matching" it proves nothing; staff: a placeholder ID
        if logic.sid_tries(con, uid) >= 5:
            return
        fixed = list(filter(None, s["fixed"].split(",")))
        left = ("sid_page_year" if re.sub(r"\d+$", "", s["student_id"]) != re.sub(r"\d+$", "", sid)
                else "sid_page_fixed" if "student_id" in fixed else None)
        if left:
            logic.log_action(con, None, left, f"user:{uid}")
            return
        try:
            logic.fix_identity(con, uid, "student_id", sid, admin=True)
            con.execute("UPDATE students SET fixed = ? WHERE user_id = ?", (",".join([*fixed, "student_id"]), uid))
        except _Taken:
            logic.log_action(con, None, "sid_page_taken", f"user:{uid}")
            for (f,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
                logic.notify(con, f, "sid_page_clash", f"sp:{uid}:{now() // 86400}")
        except ApiError:  # an ID the app doesn't take (a course out of range): left
            pass


def _reply(chat: int, text: str, button: str | None = None, start: str = "", cfg: Config | None = None, keys: list | None = None) -> dict:
    body: dict = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if keys or button:
        body["reply_markup"] = {"inline_keyboard": keys or [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp{'=' + start if start else ''}"}]]}
    return body


async def _receipt(cfg: Config, http: httpx.AsyncClient, con, msg: dict, eid: int | None = None, again: bool = False) -> dict | None:
    """A receipt sent to the bot (§4.3; Kaspi → Share → Telegram → the bot): it goes to the sender's seat on hold, the
    only one, or the one they pick (the buttons answer the receipt's own message, so the pick finds the file in
    reply_to_message: nothing to keep in between). The answer to send, or None for a group chat."""
    chat = msg.get("chat") or {}
    if chat.get("type") != "private":
        return None
    u = _student(con, chat["id"])
    lang = u["lang"] if u else str((msg.get("from") or {}).get("language_code") or "")[:2]
    say = lambda kind, start="", **f: _reply(chat["id"], *texts.bot_message(lang, kind, **f), start, cfg)  # noqa: E731
    if not u:
        return say("receipt_signin")

    def taken(eid: int, title: str, c: dict) -> dict:
        if flags := (c["my"] or {}).get("receiptFlags"):  # looks wrong: the ticket stays, the app's ticket takes another file
            return say("receipt_check", f"tk_{eid}", title=title, why=texts.receipt_why(lang, flags))
        if one(con, "SELECT 1 FROM events WHERE id = ? AND team_max IS NOT NULL", eid):  # a team event: the team is the next step, on the event's page
            return say("receipt_ok_team", f"ev_{eid}", title=title)
        return say("receipt_ok", f"tk_{eid}", title=title)
    viewer = logic.Viewer(u["id"], u["role"], True)
    # again: the last process died in the middle of this very receipt (bot.hear). Taken already: the same answer, never
    # "no seat on hold" (its seat isn't on hold any more), and never a second seat that went on hold meanwhile
    if again and (e := one(con, """SELECT e.* FROM receipts c JOIN registrations r ON r.id = c.registration_id
            JOIN events e ON e.id = r.event_id WHERE r.user_id = ? AND r.status = 'going' AND c.via = 'bot'
            AND c.created_at >= ? AND (? IS NULL OR e.id = ?) ORDER BY c.id DESC""", u["id"], int(msg.get("date") or 0) - 60, eid, eid)):
        return taken(e["id"], e["title"], logic.card(con, viewer, e))
    logic.sweep_holds(con)
    holds = rows(con, """SELECT e.id, e.title FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status = 'hold' ORDER BY r.hold_until""", u["id"])
    if eid is None and len(holds) > 1:
        body = _reply(chat["id"], texts.bot_message(lang, "receipt_which")[0], keys=[[{"text": h["title"][:60], "callback_data": f"rc:{h['id']}"}] for h in holds])
        return {**body, "reply_parameters": {"message_id": msg["message_id"]}}
    if eid is None and holds:
        eid = holds[0]["id"]
    if eid not in {h["id"] for h in holds}:  # none on hold: just expired (paid too late), or never tapped "Going"
        late = one(con, """SELECT e.id, e.title FROM registrations r JOIN events e ON e.id = r.event_id WHERE r.user_id = ?
            AND r.cancel_reason = 'hold_expired' AND r.updated_at > ? ORDER BY r.updated_at DESC""", u["id"], now() - 7200)
        return say("receipt_late", f"ev_{late['id']}", title=late["title"]) if late else say("receipt_none")
    f = _file(msg) or {}
    if int(f.get("file_size") or 0) > media.MAX_BYTES:
        return say("receipt_bad")
    try:
        logic.receipt_open(con, viewer, eid)
    except logic.ApiError as exc:
        return say("receipt_wait" if exc.code == "rate_limited" else "receipt_none")
    try:
        r = await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getFile", params={"file_id": f.get("file_id")})
        path = r.json()["result"]["file_path"]
        data = (await http.get(f"https://api.telegram.org/file/bot{cfg.bot_token}/{path}")).content
        saved, read = await asyncio.to_thread(receipt.take, data, Path(cfg.db_path).resolve().parent / "receipts")  # as app.py
    except receipt.NotReceipt:
        return say("receipt_not")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, media.BadImage) as exc:
        log.warning("receipt: %s", type(exc).__name__)
        return say("receipt_bad")
    root = Path(cfg.db_path).resolve().parent / "receipts"
    try:
        c, gone = logic.add_receipt(con, viewer, eid, saved, read, via="bot")
    except logic.ApiError:  # the hold ran out while the file was read: the picture goes, unless a row has the same one
        media.drop(root, [] if one(con, "SELECT 1 FROM files WHERE path = ?", saved["path"]) else [saved["path"]])
        return say("receipt_none")
    media.drop(root, gone)  # the one it replaced
    return taken(eid, next(h["title"] for h in holds if h["id"] == eid), c)


# Only announcements a student can browse or ignore get "Don't send these" (Codex review, owner Nov 23); a ticket, a
# reply or a reminder keeps the whole keyboard for its own action. Settings still mutes every category.
MUTE_ROW = {"new_event", "casting_open", "round_open", "broadcast"}


def _feedback_token(cfg: Config, chat: int, action: str, category: str, nonce: str, mid: int = 0) -> str:
    key = f"nf:{action}:{category}:{nonce}"
    mac = hmac.new(cfg.token_key, f"{key}:{chat}:{mid}".encode(), hashlib.sha256).hexdigest()[:20]
    return f"{key}:{mac}"


def _feedback_buttons(cfg: Config, chat: int, lang: str, category: str) -> list[dict]:
    nonce = secrets.token_hex(8)
    return [{"text": texts.bot_message(lang, f"feedback_{action}")[0],
             "callback_data": _feedback_token(cfg, chat, action, category, nonce)} for action in ("off",)]


# Telegram holds the button state. ponytail: keep the last 512 edits in memory for taps already in
# Telegram's queue with an older snapshot. Increase the buffer if that backlog ever outgrows it.
_feedback_edits: OrderedDict[str, set[str]] = OrderedDict()


async def _feedback_tap(cfg: Config, http: httpx.AsyncClient, con, cq: dict, msg: dict, data: str) -> None:
    match = re.fullmatch(r"nf:(off|undo):([A-Za-z]+):([0-9a-f]{16}):[0-9a-f]{20}", data)
    chat = msg.get("chat") or {}
    tg, mid, sent_at = chat.get("id"), msg.get("message_id"), msg.get("date")
    if not match or chat.get("type") != "private" or tg != (cq.get("from") or {}).get("id") or not tg or not mid or not sent_at:
        return
    action, category, nonce = match.groups()
    if category not in notifications.CATEGORIES or not hmac.compare_digest(
            data, _feedback_token(cfg, tg, action, category, nonce, mid if action == "undo" else 0)):
        return
    keyboard = (msg.get("reply_markup") or {}).get("inline_keyboard") or []
    if not keyboard or not any(b.get("callback_data") == data for b in keyboard[-1]):
        return
    edits = _feedback_edits.get(nonce, set())
    if action in edits:
        return
    ids = {"chat_id": tg, "message_id": mid}
    links = keyboard[:-1]
    undo = _feedback_token(cfg, tg, "undo", category, nonce, mid)
    card = undo.rsplit(":", 1)[1]
    state = await anyio.to_thread.run_sync(notifications.switch_from_chat, con, tg, category, action == "undo", card, sent_at)
    if state is None:
        return
    lang, on, can_undo = state
    original = msg.get("text") or ""
    if action == "undo":
        for locale in texts.BOT:
            off = texts.bot_message(locale, "feedback_disabled")[0]
            original = "" if original == off else original.removesuffix(f"\n\n{off}")
    status, button = texts.bot_message(lang, "feedback_enabled" if on else "feedback_disabled")
    edited = f"{original}\n\n{status}" if original else status
    entities = msg.get("entities") or []
    if len(edited) > 4096:
        edited, entities = status, []
    keys = [*links, [{"text": button, "callback_data": undo}]] if can_undo else links
    r = await _tg(cfg, http, "editMessageText", {**ids, "text": edited, "entities": entities,
        "link_preview_options": {"is_disabled": True}, "reply_markup": {"inline_keyboard": keys}})
    if r.json().get("ok"):
        _feedback_edits[nonce] = edits | {action}
        _feedback_edits.move_to_end(nonce)
        if len(_feedback_edits) > 512:
            _feedback_edits.popitem(last=False)


async def _tapped(cfg: Config, http: httpx.AsyncClient, con, cq: dict, again: bool = False) -> None:
    """A tap on the bot's buttons under a message they answer: "which event" for a receipt (rc:); and on the forum's
    cards (ct:, ps:). The question turns into the answer; someone else's tap does nothing."""
    msg, data = cq.get("message") or {}, str(cq.get("data") or "")
    f = re.fullmatch(r"(ct|ps):(\d+)(?::([0-9a-f]{8}))?(?::([yn]))?|an:([yn])", data)
    callback = f"https://api.telegram.org/bot{cfg.bot_token}/answerCallbackQuery"
    ack = {"callback_query_id": cq["id"]}
    if not f or f[1] != "ct":
        await http.post(callback, json=ack)
    if data.startswith("nf:"):
        await _feedback_tap(cfg, http, con, cq, msg, data)
        return
    if v := re.fullmatch(r"bv:([01]):([a-z0-9_]{1,40})", data):  # a broadcast's Interesting / Not interesting: the tapper's own vote, changeable
        u = one(con, "SELECT id FROM users WHERE tg_id = ?", (cq.get("from") or {}).get("id"))
        if u:
            con.execute("INSERT OR REPLACE INTO broadcast_votes (name, user_id, vote, at) VALUES (?, ?, ?, ?)", (v[2], u["id"], int(v[1]), int(time.time())))
            con.execute("UPDATE users SET n_broadcasts = ? WHERE id = ?", (int(v[1]), u["id"]))  # "don't send these" turns broadcasts off (Settings turns them back on)
        if msg.get("message_id") and (kb := (msg.get("reply_markup") or {}).get("inline_keyboard")):  # the vote row says thanks, the link stays
            await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/editMessageReplyMarkup", json={
                "chat_id": (msg.get("chat") or {}).get("id"), "message_id": msg["message_id"], "reply_markup": {"inline_keyboard": kb[:1]}})
        return
    # the forum's cards: Accept/Decline an offer, stop the pings; an: more messages like the elective's? (the tapper's own row)
    if f:
        u = one(con, "SELECT id, lang FROM users WHERE tg_id = ?", (cq.get("from") or {}).get("id"))
        if not u or not msg:
            if f[1] == "ct":
                await http.post(callback, json=ack)
            return
        if f[5]:
            con.execute("UPDATE users SET announce_ok = ? WHERE id = ?", (int(f[5] == "y"), u["id"]))
            said = "announce_yes" if f[5] == "y" else "announce_no"
        elif f[1] == "ps":
            with db.tx(con):
                notifications.set_preference(con, u["id"], "nProjectPings", False)
            said = "ask_stopped"
        else:
            st = logic.decide_contact(con, u["id"], int(f[2]), f[4] == "y", f[3])  # f[3]: the offer's token
            if not st and one(con, "SELECT 1 FROM contacts WHERE id = ? AND to_id = ? AND token = ? AND withdrawn_at IS NOT NULL",
                              int(f[2]), u["id"], f[3]):
                await http.post(callback, json={**ack, "text": texts.bot_message(u["lang"], "contact_withdrawn")[0]})
                return
            await http.post(callback, json=ack)
            said = {"accepted": "contact_yes", "declined": "contact_no"}.get(st or "", "contact_gone")
        chat, thanks = (msg.get("chat") or {}).get("id"), texts.bot_message(u["lang"], said)[0]
        if f[5]:  # the post stays with its link; the question's buttons give way to the thanks
            await _tg(cfg, http, "editMessageText", {"chat_id": chat, "message_id": msg["message_id"], "text": f"{msg.get('text', '')}\n\n{thanks}",
                                                     "entities": msg.get("entities") or [], "reply_markup": {"inline_keyboard": [
                                                         r for r in (msg.get("reply_markup") or {}).get("inline_keyboard", []) if all("url" in b for b in r)]}})
            return
        await _tg(cfg, http, "editMessageText", {"chat_id": chat, "message_id": msg["message_id"], "parse_mode": "HTML",
                                                 "text": thanks, "reply_markup": {"inline_keyboard": []}})
        return
    orig = msg.get("reply_to_message") or {}
    m = re.fullmatch(r"rc:(\d+)", data)
    if not m or (orig.get("from") or {}).get("id") != (cq.get("from") or {}).get("id"):
        return
    body = await _receipt(cfg, http, con, orig, int(m[1]), again) if _file(orig) else None
    if body:
        await _tg(cfg, http, "editMessageText", {**body, "message_id": msg["message_id"], "reply_markup": body.get("reply_markup", {"inline_keyboard": []})})
