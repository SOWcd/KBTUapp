"""The forum channel's discussion group (FORUM_GROUP), the bot's side of logic/tgcomments.py: who may comment,
/report, edits, and the bot round's deletions. The bot is the group's admin with "delete messages" and "ban users"
only. Each batch's comments here are handled before anything else the batch holds (bot.hear), and the slow parts
(the AI's look) run as tasks beside the ears, so a stranger's comment never waits behind a receipt's OCR."""
from __future__ import annotations

import asyncio
import html
import logging
import re

import httpx

from . import ai, db, logic, texts
from .config import Config
from .logic import now, one
from .logic import tgcomments as rules

log = logging.getLogger("kbtu.tgc")

WARN_FOR = 60       # seconds the bot's warning stays in the thread
# what a person writes; joins, pins, title changes are Telegram's own lines and stay
CONTENT = ("text", "caption", "photo", "sticker", "animation", "video", "voice", "video_note", "audio", "document", "poll",
           "contact", "location", "venue", "dice", "story")

_tasks: set[asyncio.Task] = set()
_last: dict[str, asyncio.Task] = {}


def spawn(coro, chain: str = "tgc") -> None:
    """A slow job beside the ears, one after another on its chain: two event-post copies in a batch must not both
    comment ("events"), and the comments' AI looks ("tgc") never hold up an event post's first comment."""
    prev = _last.get(chain)
    prev = prev if prev and not prev.done() else None

    async def run():
        if prev:
            await asyncio.gather(prev, return_exceptions=True)
        await coro
    _last[chain] = t = asyncio.get_running_loop().create_task(run())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def settle() -> None:
    """Every job spawned so far, done (tests; a job's own failure is logged, not raised)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def ours(cfg: Config, upd: dict) -> bool:
    m = upd.get("message") or upd.get("edited_message") or {}
    return bool(cfg.tgc_chat) and (m.get("chat") or {}).get("id") == cfg.tgc_chat


def _text(m: dict) -> str:
    return str(m.get("text") or m.get("caption") or "")


def _link(con, root: int | None, mid: int) -> str | None:
    """The way back to a comment's thread: the channel post, its comments open at that comment (or near it, if gone)."""
    p = rules.post_of(con, root) if root else None
    return f"https://t.me/{p[0]}/{p[1]}?comment={mid}" if p else None


def _is_report(cfg: Config, text: str) -> bool:
    m = re.match(r"/report(?:@(\w+))?(?:\s|$)", text)
    return bool(m) and (not m[1] or m[1].lower() == cfg.bot_username.lower())


async def _call(cfg: Config, http: httpx.AsyncClient, method: str, body: dict) -> dict:
    try:
        r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{method}", json=body)).json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("tgc %s: %s", method, type(exc).__name__)
        return {"ok": False}
    if not r.get("ok"):
        log.warning("tgc %s: %s", method, str(r.get("description"))[:200])
    return r


async def gate(cfg: Config, http: httpx.AsyncClient, con, upds: list[dict]) -> None:
    """One batch's messages in the group: a stranger's comment deleted (all in one call), warned once in its thread or
    banned; posting as another channel deleted and that channel banned; a student's /report taken (the command
    deleted); a reported comment's edit judged again. One message that breaks (a locked database) is logged and
    skipped; what was decided for the rest still goes out."""
    doomed: list[int] = []
    bans: set[int] = set()
    chans: set[int] = set()
    warns: list[tuple[int, str, bool]] = []  # (thread root, language, text kept)
    try:
        for upd in upds:
            try:
                _one(cfg, http, con, upd, doomed, bans, chans, warns)
            except Exception as exc:  # noqa: BLE001
                log.warning("tgc gate: %s", type(exc).__name__)
    finally:
        await _act(cfg, http, con, doomed, bans, chans, warns)


def _one(cfg: Config, http: httpx.AsyncClient, con, upd: dict, doomed: list, bans: set, chans: set, warns: list) -> None:
    """One message of the group: what to delete, ban and warn (gate sends it all at once)."""
    edit = "edited_message" in upd
    msg = upd.get("message") or upd["edited_message"]
    sender = msg.get("sender_chat") or {}
    if msg.get("is_automatic_forward"):  # the channel's post, copied in: the root of its comments
        if sender.get("username") and (post := (msg.get("forward_origin") or {}).get("message_id")):
            rules.post_of(con, msg["message_id"], sender["username"], int(post))
            if sender.get("id") == cfg.forum_channel:  # one of ours whose send's answer was lost: found
                logic.fchannel.found(con, int(post), _text(msg))
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('tgc_channel', ?)", (str(sender["id"]),))
        return
    if not any(k in msg for k in CONTENT):
        return
    root = msg.get("message_thread_id") or (msg.get("reply_to_message") or {}).get("message_id")
    if sender:  # as a channel, or an anonymous admin: nobody to check. The forum channel's own admins may
        linked = (one(con, "SELECT value FROM meta WHERE key = 'tgc_channel'") or [""])[0]
        if str(sender.get("id")) != linked:
            doomed.append(msg["message_id"])
            # a ban only once the forum channel is known (its first post's copy): it mustn't ban itself in its own group
            if linked and sender.get("id") != cfg.tgc_chat:
                chans.add(sender["id"])
        return
    tg = int((msg.get("from") or {}).get("id") or 0)
    who = rules.commenter(con, tg)
    if who == "student":
        if not edit and _is_report(cfg, _text(msg)):
            doomed.append(msg["message_id"])
            _report(cfg, http, con, msg)
        elif edit and (cid := rules.edited(con, cfg.tgc_chat, msg["message_id"], _text(msg))):
            spawn(_judge(cfg, http, cid, rules.fresh_edit(con, tg)))
        return
    doomed.append(msg["message_id"])
    if edit:  # a stranger's edit isn't a second comment (it came with the first, after a restart): it just goes
        return
    if who == "banned" or not tg:
        if tg:
            rules.banned(con, tg)  # on record: an unban in the app lifts it here too (unban_due)
        bans.add(tg)
        return
    act, raid = rules.stranger(con, tg, _text(msg), _link(con, root, msg["message_id"]))
    if act == "ban":
        bans.add(tg)
    elif not raid:
        warns.append((root, str((msg.get("from") or {}).get("language_code") or "")[:2], bool(_text(msg))))


async def _act(cfg: Config, http: httpx.AsyncClient, con, doomed: list, bans: set, chans: set, warns: list) -> None:
    for i in range(0, len(doomed), 100):
        await _call(cfg, http, "deleteMessages", {"chat_id": cfg.tgc_chat, "message_ids": doomed[i:i + 100]})
    for tg in bans - {0}:  # as long as the record (the policy's 90 days): Telegram lifts it by itself then
        await _call(cfg, http, "banChatMember", {"chat_id": cfg.tgc_chat, "user_id": tg, "until_date": now() + rules.STRANGER_KEEP})
    for ch in chans:
        await _call(cfg, http, "banChatSenderChat", {"chat_id": cfg.tgc_chat, "sender_chat_id": ch})
    for root, lang, kept in warns:
        text, button = texts.bot_message(lang, "tgc_warn" if kept else "tgc_warn_plain")
        body = {"chat_id": cfg.tgc_chat, "text": text, "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp=cm"}]]}}
        if root:  # in the thread the stranger was writing in (a reply to the post's copy), else the group's main chat
            body["reply_parameters"] = {"message_id": root, "allow_sending_without_reply": True}
        r = await _call(cfg, http, "sendMessage", body)
        if r.get("ok"):
            rules.later_delete(con, r["result"]["message_id"], now() + WARN_FOR)


def _report(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> None:
    """/report as a reply to a comment: not the post's copy, not the bot's, not a channel's, not one's own. Counted,
    the reporter hears in DM (the outbox: only if he lets the bot write), the AI's look runs beside."""
    t = msg.get("reply_to_message") or {}
    author = t.get("from") or {}
    if not t or t.get("is_automatic_forward") or t.get("sender_chat") or author.get("is_bot") or not author.get("id"):
        return
    root = msg.get("message_thread_id") or t.get("message_thread_id")
    res, cid = rules.report(con, msg["from"]["id"], cfg.tgc_chat, t["message_id"], author["id"], _text(t), _link(con, root, t["message_id"]))
    if res == "ok":  # no cap on reports (owner); a cap on the fresh AI looks one reporter brings about in a day
        spawn(_judge(cfg, http, cid, rules.fresh_look(con, msg["from"]["id"])))


async def _judge(cfg: Config, http: httpx.AsyncClient, cid: int, fresh: bool = True) -> None:
    """The AI's look at a reported comment's text, then the rule (rules.judge); a deletion goes in the bot's next round.
    The same text looked at before: its verdict again, no AI call. fresh=False (the reporter's day of looks is used up):
    no new look, the rule decides without it (a moderator then)."""
    con = db.connect(cfg.db_path)
    try:
        body = (one(con, "SELECT body FROM tgc_comments WHERE id = ?", cid) or [""])[0]
        if (seen := rules.looked(con, cid)) is not None:
            verdict, rule = seen
        elif fresh and body.strip():  # a sticker: a moderator looks
            # commenter() doesn't ask for the policy in force: an author not yet on it (+ai1) gets the EU host alone
            s = one(con, """SELECT s.consent_version FROM tgc_comments c JOIN students s ON s.user_id = c.author_id
                WHERE c.id = ?""", cid)
            only = ai.PUBLIC_PROVIDERS if logic.agreed(s, cfg) else ai.EU_ONLY
            verdict, rule = await ai.screen_comment(cfg, http, body, con, only=only)
            rules.look(con, cid, body, verdict)
        else:
            verdict, rule = None, None
        rules.judge(con, cid, verdict, rule)
    except Exception:  # noqa: BLE001 - one comment's look must not stop the next
        log.exception("tgc judge")
    finally:
        con.close()


async def tick(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """The bot's round, with the group set: the bot's warnings past their minute, comments a moderator or the reports
    deleted, and new students unbanned. The old records are wiped by send_due (rules.sweep), on or off."""
    if not cfg.tgc_chat:
        return
    if gone := rules.due_deletes(con):
        await _call(cfg, http, "deleteMessages", {"chat_id": cfg.tgc_chat, "message_ids": gone})
    for cid, chat, mid in rules.to_delete(con):
        r = await _call(cfg, http, "deleteMessage", {"chat_id": chat, "message_id": mid})
        if r.get("ok") or r.get("error_code") == 400:  # gone, or never to be (its author deleted it first; too old)
            rules.deleted(con, cid, chat, mid)
        else:
            break  # the network, a flood wait, lost rights: next round (the unbans below still go)
    for tg in rules.unban_due(con):
        await _call(cfg, http, "unbanChatMember", {"chat_id": cfg.tgc_chat, "user_id": tg, "only_if_banned": True})


def _gone(r: dict) -> bool:
    """Telegram says the message isn't there (deleted already): nothing left to take down."""
    return r.get("error_code") == 400 and "not found" in str(r.get("description")).lower()


async def post_tick(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """The forum channel's posts (logic/fchannel.py), in the bot's round: first what must leave (deleted by the author,
    taken down, a deleted account's), then their copies in the discussion group, then what the AI or a moderator let
    out. Plain text, no parse_mode, no preview: the words go as they are, never as markup. The bot needs in the
    channel: post, edit and delete others' messages."""
    if not cfg.forum_channel:
        return
    F = logic.fchannel
    F.lost(con)  # a send cut off last round (a timeout, a crash): to a moderator, never sent twice by itself
    for u in F.unposts(con):
        r = await _call(cfg, http, "deleteMessage", {"chat_id": cfg.forum_channel, "message_id": u["msg_id"]})
        if r.get("ok") or _gone(r):
            F.copy_gone(con, u["msg_id"])  # its copy in the group goes next (below), whenever its mapping is known
        elif r.get("error_code") == 400:  # too old to delete (48 h), or rights lost: its words edited away (edits sync to the copy)
            text = texts.bot_message("ru", "fch_gone" if u["why"] == "author" else "fch_removed")[0]
            e = await _call(cfg, http, "editMessageText", {"chat_id": cfg.forum_channel, "message_id": u["msg_id"], "text": text})
            if not (e.get("ok") or _gone(e) or "not modified" in str(e.get("description"))):
                F.unpost_later(con, u["msg_id"])  # still public: tried again in 10 minutes (the warning is in the log)
                continue
        else:
            break  # the network, a flood wait: next round
        F.unposted(con, u["msg_id"])
    for key, root in F.copies(con):
        if not cfg.tgc_chat:
            break
        if root is not None:
            r = await _call(cfg, http, "deleteMessage", {"chat_id": cfg.tgc_chat, "message_id": root})
            if not (r.get("ok") or _gone(r)):
                break
        F.copy_done(con, key, root)
    anon, button = texts.bot_message("ru", "fch_anon")  # the channel speaks Russian, as the events' one does
    for pid, body, name in F.to_send(con):
        if not F.sending(con, pid):  # marked "sending" (tg_msg 0, committed) before it goes; deleted meanwhile: skipped
            continue
        r = await _call(cfg, http, "sendMessage", {
            "chat_id": cfg.forum_channel, "text": f"{body}\n\n— {name or anon}", "link_preview_options": {"is_disabled": True},
            "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp=fp"}]]}})
        if r.get("ok"):
            F.sent(con, pid, r["result"]["message_id"])
        elif r.get("error_code"):  # Telegram said no: it isn't in the channel, the next round tries again
            F.unsend(con, pid)
            break
        else:  # no answer: it may be in the channel or not; F.lost hands it to a moderator next round
            break



# the author's messages about one comment, each said only while it's still true: "under review" while a moderator hasn't
# decided, then the verdict; the verdict edits the first message in place (owner, Nov 1), so the chat holds one
AUTHOR = {"tgc_removed": "status IN ('deleting', 'deleted') AND review = 1",
          "tgc_confirmed": "status IN ('deleting', 'deleted') AND review = 0",
          "tgc_back": "status = 'restored'"}


async def edit_first(cfg: Config, http: httpx.AsyncClient, con, m, body: dict) -> httpx.Response | None:
    """A verdict on a comment: the "under review" message edited into it. None when there's none to edit or Telegram
    won't (too old, deleted by him, blocked): the postman sends it new then (a block: the app's card, take_saved)."""
    if m["kind"] not in ("tgc_confirmed", "tgc_back"):
        return None
    mid = (one(con, "SELECT dm_id FROM tgc_comments WHERE id = ?", int(m["ref"].split(":")[1])) or [None])[0]
    if not mid:
        return None
    r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/editMessageText",
                        json={k: x for k, x in body.items() if k != "link_preview_options"} | {"message_id": mid})
    return r if r.status_code == 200 and r.json().get("ok") else None


def sent(con, m, answer: dict) -> None:
    """The message to the author went out: its id, for the verdict to edit; he knows, so the app's card doesn't repeat it."""
    if m["kind"] in AUTHOR and isinstance(answer.get("result"), dict) and answer["result"].get("message_id"):
        con.execute("UPDATE tgc_comments SET dm_id = ?, shown = 1 WHERE id = ?", (answer["result"]["message_id"], int(m["ref"].split(":")[1])))


def render(con, m, lang: str) -> tuple[str, str | None, str] | None:
    """The postman's text for this feature's messages (bot._render)."""
    kind, ref = m["kind"], m["ref"].split(":")
    if kind == "tgc_queue":  # to admins and moderators (hourly, or at once for 3+ reports): comments waiting, the backlog
        q = "SELECT COUNT(*) FROM tgc_comments WHERE (status = 'queued' OR review = 1)"
        n, old = one(con, q)[0], one(con, q + " AND decided_at < ?", now() - 86400)[0]
        return (*texts.bot_message(lang, kind, n=n, old=old), "capps") if n else None
    if kind in AUTHOR:  # to the author: removed after reports (under review), then the verdict; his own words only with
        # "restored" (to post them again), to him alone (AGENTS.md's one exception for a user's own text)
        c = one(con, "SELECT body, clause FROM tgc_comments WHERE id = ? AND " + AUTHOR[kind], int(ref[1]))
        rule = texts.pick(texts.TGC_RULES, lang).get(c["clause"] or "other") if c else ""
        words = "\n\n" + html.escape(c["body"]) if c and kind == "tgc_back" else ""
        return (texts.bot_message(lang, kind, rule=rule)[0] + words, None, "") if c else None
    if kind == "tgc_good":  # to the owner: an accurate reporter, for him to decide about the moderator status
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=logic.short_name(p)), f"u_{p['id']}") if p else None
    return (*texts.bot_message(lang, kind), "")
