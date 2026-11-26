"""Group chats with the bot (bot.py's ears hand each message here): an event's or a club's group (its card, the bare
/start@bot), the swear filter, /all, the replies to TikTok, YouTube Shorts and Instagram links with the video, and the
channel's discussion group (the rules under each new post)."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import random
import re
import time

import httpx

from . import bot, db, logic, media, mtbot, swear, texts, tgc, tiktok
from .bot import FRESH, _call, _nap, _send, _tg, _video_seen, premium
from .chores import chat_card
from .config import Config
from .logic import one

log = logging.getLogger("kbtu.bot")

TAG_GAP = 3.0               # /all's messages: a group takes about 20 a minute
TAG_FAST, TAG_BURST = 0.4, 18  # its first messages go quickly (90 people in a few seconds), the rest at TAG_GAP
TAG_SAY = 200               # the caller's words repeated over each five, at most this long
TAG_MARKS = tuple("\U0001F525 \u2B50 \u26A1 \U0001F3AF \U0001F680 \U0001F48E \U0001F389 \U0001F44B \U0001F4E3 \U0001F514 \u2728 \U0001F4A5 \U0001F31F \U0001F3C6 \U0001F388 \u2764 \U0001F499 \U0001F49A \U0001F49B \U0001F49C \U0001F9E1".split())  # the link text, one per person (no names): five different ones a message, the pack's animated ones when it has them
SWEAR_CAP = 1               # a person's swear warnings a minute in a chat; past it (a flood) their messages only go
SWEAR_CHAT_CAP = 10         # a chat's warnings a minute: a group takes about 20 messages a minute, the bot keeps its voice
WARN_FOR = 60               # a swear warning stays this long, then the bot removes it
# ponytail: per worker (the bot polls in one) and its keys never pruned (a few bytes a swearer); a table if that changes
_swore: dict[tuple[int, int], list[float]] = {}  # (chat, person; 0: the chat) -> this minute's warnings
_tagging: set[int] = set()  # ponytail: chats with an /all running, per worker (the bot runs in one: its lock); a table if that changes
_tagged: dict[int, float] = {}  # a chat's last /all finished then (ALL_AGAIN); per worker as _tagging, a few bytes a group
ALL_AGAIN = 300             # a chat's next /all no sooner than this after the last ended: no calling everyone in a loop
EMPTY_WAIT = 60             # after an /all that called nobody: no rescan of the chat's roster on every message
_moved: dict[int, int] = {}  # a group turned supergroup: old id -> new (a run that spans it records its wait under the new)
TAG_MAX = 300               # people one /all calls at most: 60 messages, about 3 minutes at TAG_GAP


async def _member(cfg: Config, http: httpx.AsyncClient, con, upd: dict) -> None:
    """Our bot added to a chat or taken out of it (my_chat_member). Made admin by someone who may edit a club's chats:
    his Studio pick, or a chat on the club's page, links it; else it's remembered for him to link from Studio."""
    chat, status = upd.get("chat") or {}, (upd.get("new_chat_member") or {}).get("status")
    logic.chatsync.bot_status(con, chat.get("id"), status)  # a linked chat where the bot isn't an admin any more: paused
    if chat.get("id"):  # the swear filter pauses without its rights and goes on when they're back
        logic.chatmod.rights(con, chat["id"], logic.chatmod.missing(upd.get("new_chat_member") or {}))
    if chat.get("id") and status != "administrator":
        logic.bot_unwait(con, chat["id"])  # a remembered chat needs our bot an admin there
    if status in ("left", "kicked"):
        logic.bot_left(con, chat["id"])
        return
    # every link needs our bot made an admin: only a chat's admin can do that, a plain member adding us proves nothing
    # (else someone else's open group can be claimed); a later promotion comes as another update.
    # A plain member's group links only by its admin's /start oc_<id> (_group)
    if status != "administrator" or chat.get("type") not in ("channel", "group", "supergroup"):
        return
    invite = None
    try:  # an admin bot is told the chat's primary invite link
        r = (await _tg(cfg, http, "getChat", {"chat_id": chat["id"]})).json()
        invite = (r.get("result") or {}).get("invite_link") if r.get("ok") else None
    except (httpx.HTTPError, ValueError) as exc:  # matched by its @name then
        log.warning("bot added: %s", type(exc).__name__)
    who = int((upd.get("from") or {}).get("id") or 0)  # the action's performer (Telegram's `from`)
    if cid := logic.pick_claim(con, who, chat, invite) or logic.bot_added(con, who, chat, invite):  # Studio's picker first
        await chat_card(cfg, http, con, cid, chat["id"])
    else:  # no club's yet: his to link from Studio → Chats for ten minutes
        logic.bot_admin(con, who, chat, invite)


HELLO_EVERY = 60            # a group's bare /start@bot gets one answer a minute
ALL_NO_TTL = 15             # "/all: wait" or "nobody to call" and the command it answers live this long; one such answer a chat in that time
_denied: dict[int, float] = {}  # ponytail: as _hello below
_hello: dict[int, float] = {}  # ponytail: per worker and never pruned (a few bytes a group); a table if it's ever abused


def _seen(con, msg: dict) -> None:
    """/all's memory of who is in a club's chat: a person who writes or joins (never an anonymous admin or a channel),
    forgotten on leaving. Before the swear filter: a message it deletes still shows its sender is in the chat."""
    chat = msg["chat"]["id"]
    if not msg.get("sender_chat"):
        logic.chatlist.seen(con, chat, msg.get("from"))
    for u in msg.get("new_chat_members") or []:
        logic.chatlist.seen(con, chat, u)
    if gone := (msg.get("left_chat_member") or {}).get("id"):
        logic.chatlist.unseen(con, chat, int(gone))


async def _group(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> None:
    """In a group: "/start ec_<token>" (sent by Telegram when the organizer added the bot by the app's "Create chat")
    links it to the event and makes its join-request link; a group turned supergroup keeps its event."""
    chat = msg["chat"]
    if new := msg.get("migrate_to_chat_id"):
        with db.tx(con):
            logic.chatlist.seen_moved(con, chat["id"], new)  # first; the links then in the holder's order (chatlist._holder)
            con.execute("UPDATE chat_sync SET chat_id = ? WHERE chat_id = ?", (new, chat["id"]))
            con.execute("UPDATE chats SET tg_chat_id = ? WHERE tg_chat_id = ?", (new, chat["id"]))
            con.execute("UPDATE events SET chat_id = ? WHERE chat_id = ?", (new, chat["id"]))
        logic.chatmod.stale()  # its swear filter goes on under the new id at once
        if chat["id"] in _tagged:  # /all's wait goes on under the new id too
            _tagged[new] = _tagged[chat["id"]]
        _moved[chat["id"]] = new  # a few bytes, once in a group's life
        return
    words = str(msg.get("text") or "").split()
    # "@all": ours alone where another bot answers /all too; the plain words people really type: "\u043a\u0430\u043b\u043b",
    # "\u043a\u043e\u043b\u043b" first in a message, "call" only as the whole message (it starts ordinary English sentences)
    cmd = rf"/(all|tag)(@{re.escape(cfg.bot_username)})?|@all|\u043a[\u0430\u043e]\u043b\u043b[!.]*"
    # ... or last, after their own words (as in "meeting at 6, \u043a\u0430\u043b\u043b"); never in the middle of a sentence
    last = len(words) > 1 and not re.fullmatch(cmd, words[0], re.I) and bool(re.fullmatch(cmd, words[-1], re.I))
    if words and (re.fullmatch(cmd, words[0], re.I) or last or len(words) == 1 and re.fullmatch(r"call[!.]*", words[0], re.I)):
        sender = msg.get("from") or {}
        # the sender of this very message, a person: never a forward, an anonymous admin or a channel (sender_chat), an old one
        if sender.get("is_bot") or msg.get("sender_chat") or msg.get("forward_origin") or msg.get("forward_date") \
                or msg.get("is_automatic_forward") or time.time() - int(msg.get("date") or 0) > FRESH:
            return
        # a channel's discussion group: anyone may comment there without joining, so a message proves nothing: no /all
        # at all. Known by the forum's group (FORUM_GROUP) or a comment under a channel post (a reply to its automatic forward)
        if chat["id"] == cfg.tgc_chat or (msg.get("reply_to_message") or {}).get("is_automatic_forward"):
            return
        who = int(sender.get("id") or 0)
        # _tag_all also verifies the caller's Telegram membership and authority before reading the roster.
        if logic.chatlist.banned(con, who):
            return
        if not logic.chatlist.student(con, who):  # no account in the app: told so, nobody is called
            _refuse(cfg, http, chat["id"], msg["message_id"], sender.get("language_code"), "all_app")
            return
        if chat["id"] in _tagging or time.time() - _tagged.get(chat["id"], 0) < ALL_AGAIN:  # one run, then ALL_AGAIN: say so, then both go
            _refuse(cfg, http, chat["id"], msg["message_id"], sender.get("language_code"), "all_soon")
            return
        r = msg.get("reply_to_message")  # under the message they answered (a topic's own start isn't one), else their command
        to = r["message_id"] if r and not r.get("forum_topic_created") else msg["message_id"]
        _tagging.add(chat["id"])  # before any await: a second /all in the same batch is refused
        say = " ".join(words[:-1] if last else words[1:]).rstrip(",")[:TAG_SAY]  # their own words beside the command, in this very chat
        tgc.spawn(_tag_all(cfg, http, chat["id"], to, who, say, msg["message_id"], sender.get("language_code")), f"all:{chat['id']}")
        return
    if len(words) == 2 and re.fullmatch(r"/start(@\w+)?", words[0]) and re.fullmatch(r"oc_\d+", words[1]):  # Studio's "Add our bot" deep link identifies the club.
        sender = int((msg.get("from") or {}).get("id") or 0)
        # only the group's own admin links it (whoever added the bot as an admin is one), as for an event's chat
        me = (await _tg(cfg, http, "getChatMember", {"chat_id": chat["id"], "user_id": sender})).json()
        if not (me.get("ok") and (me.get("result") or {}).get("status") in ("creator", "administrator")):
            return
        if cid := logic.bot_added(con, sender, chat, cid=int(words[1][3:])):
            await chat_card(cfg, http, con, cid, chat["id"])
        return
    if len(words) == 1 and words[0].lower() == f"/start@{cfg.bot_username}".lower():  # someone just asks: am I on duty here?
        t = time.time()
        if t - int(msg.get("date") or 0) <= FRESH and t - _hello.get(chat["id"], 0) > HELLO_EVERY:
            _hello[chat["id"]] = t
            lang = (msg.get("from") or {}).get("language_code")
            on = one(con, "SELECT 1 FROM chats WHERE tg_chat_id = ? AND status IN ('live', 'org')", chat["id"])
            text, button = texts.bot_message(lang if lang in ("kk", "en") else "ru", "group_on" if on else "group_off")
            await _send(cfg, http, {"chat_id": chat["id"], "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": [[
                {"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp"}]]}})
        return
    if len(words) != 2 or not re.fullmatch(r"/start(@\w+)?", words[0]) or not words[1].startswith("ec_"):
        return
    sender = int((msg.get("from") or {}).get("id") or 0)
    # only the group's own admin links it (whoever added the bot as an admin is one): a member can't hand it to an event
    me = (await _tg(cfg, http, "getChatMember", {"chat_id": chat["id"], "user_id": sender})).json()
    admin = me.get("ok") and (me.get("result") or {}).get("status") in ("creator", "administrator")
    e = logic.chat_claim(con, words[1][3:], sender, chat["id"]) if admin else None
    if not e:
        await _send(cfg, http, {"chat_id": chat["id"], "text": texts.CHAT_BAD, "parse_mode": "HTML"})
        return
    r = (await _tg(cfg, http, "createChatInviteLink", {"chat_id": chat["id"], "name": e["title"][:32], "creates_join_request": True})).json()
    if not r.get("ok"):  # the bot isn't an admin that may invite: say what to fix
        log.warning("chat link: %s", str(r.get("description"))[:200])
        await _send(cfg, http, {"chat_id": chat["id"], "text": texts.CHAT_NO_RIGHTS, "parse_mode": "HTML"})
        return
    con.execute("UPDATE events SET chat_link = ? WHERE id = ?", (r["result"]["invite_link"], e["id"]))
    await _send(cfg, http, {"chat_id": chat["id"], "text": texts.CHAT_LINKED.format(title=html.escape(e["title"])), "parse_mode": "HTML"})


def _refuse(cfg: Config, http: httpx.AsyncClient, chat: int, mid: int, lang: str | None, key: str) -> None:
    """/all answered without calling (all_soon, all_none, all_app): one such answer a chat each ALL_NO_TTL, one pending."""
    pending = tgc._last.get(f"allno:{chat}")
    if time.time() - _denied.get(chat, 0) > ALL_NO_TTL and not (pending and not pending.done()):  # one waiting a chat at most
        _denied[chat] = time.time()
        tgc.spawn(_all_no(cfg, http, chat, mid, lang, key), f"allno:{chat}")


async def _all_no(cfg: Config, http: httpx.AsyncClient, chat: int, mid: int, lang: str | None, key: str) -> None:
    """/all not run: a template under the command, then both are deleted (theirs: if the bot may)."""
    text, _ = texts.bot_message(lang if lang in ("kk", "en") else "ru", key)
    sent = await _call(cfg, http, "sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML", "reply_parameters": {"message_id": mid, "allow_sending_without_reply": True}}, 0)
    await _nap(ALL_NO_TTL)  # a stop deletes them early: no process would be left to do it later
    for m in (mid, ((sent or {}).get("result") or {}).get("message_id")):
        if m:
            await _call(cfg, http, "deleteMessage", {"chat_id": chat, "message_id": m}, 0)


def _swear_hit(con, msg: dict) -> tuple[int, str] | None:
    """Shared by moderation and early video dispatch so a filtered link gets no reply."""
    chat, sender = msg.get("chat") or {}, msg.get("from") or {}
    if chat.get("type") not in ("group", "supergroup") or not sender.get("id") or sender.get("is_bot") or msg.get("sender_chat") \
            or time.time() - int(msg.get("edit_date") or msg.get("date") or 0) > FRESH or not logic.chatmod.chat_on(con, chat["id"]):
        return None
    poll = msg.get("poll") or {}
    text = _own_words(msg.get("text") or "", msg.get("entities")) + "\n" + _own_words(msg.get("caption") or "", msg.get("caption_entities")) \
        + "\n" + "\n".join([poll.get("question") or "", *((o.get("text") or "") for o in poll.get("options") or ())])
    # the cached list may be 30 s behind a switch turned off in another worker: a hit asks the database itself
    if (stem := swear.find(text)) and (cid := logic.chatmod.on_now(con, chat["id"])):
        return cid, stem
    return None


async def _swear(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> bool:
    if not (hit := _swear_hit(con, msg)):
        return False
    cid, stem = hit
    chat, sender = msg["chat"], msg["from"]
    lang = sender.get("language_code")
    topic = msg.get("message_thread_id") if msg.get("is_topic_message") else None  # a forum's topic (General: none; a reply's thread isn't one)
    tgc.spawn(_swear_act(cfg, http, chat["id"], cid, msg["message_id"], sender["id"], stem, lang if lang in ("kk", "en") else "ru", topic),
              f"swear:{chat['id']}")
    return True


def _own_words(text: str, entities: list | None) -> str:
    """The text without its mentions, links and emails: someone named "a swear word" (a first name, a username) must not
    get whoever mentions them deleted and muted. Entities count UTF-16 units."""
    b = text.encode("utf-16-le")
    for e in sorted(entities or (), key=lambda e: -int(e.get("offset", 0))):
        if e.get("type") in ("mention", "text_mention", "url", "email"):
            o, n = 2 * int(e.get("offset", 0)), 2 * int(e.get("length", 0))
            b = b[:o] + " ".encode("utf-16-le") + b[o + n:]
    return b.decode("utf-16-le", "ignore")


async def swear_rights(cfg: Config, http: httpx.AsyncClient, chat: int) -> list[str] | None:
    """The rights our bot lacks in a chat for the swear filter ("delete", "ban"); None: Telegram didn't answer."""
    r = await _call(cfg, http, "getChatMember", {"chat_id": chat, "user_id": int(cfg.bot_token.split(":")[0])}, 0)
    return logic.chatmod.missing(r["result"] or {}) if r and r.get("ok") else None


async def _swear_act(cfg: Config, http: httpx.AsyncClient, chat: int, cid: int, mid: int, tg: int, stem: str, lang: str,
                     topic: int | None = None) -> None:
    """A chat's admin: nothing (never deleted, never muted). Else delete; then, once a minute a person (SWEAR_CAP, and
    SWEAR_CHAT_CAP for the chat) the hit is recorded and a template warning naming nobody is said (in the message's
    topic), the third muted for an hour (not one already restricted: our hour's end would lift their restriction too);
    the warning goes after a minute. A refused delete or mute: the bot's rights are asked, a lacking one pauses the filter there (Studio
    says which). Logs Telegram's word only."""
    m = await _call(cfg, http, "getChatMember", {"chat_id": chat, "user_id": tg})
    if not (m and m.get("ok")) or (status := (m.get("result") or {}).get("status")) in ("creator", "administrator"):
        return
    con = db.connect(cfg.db_path)
    try:
        r = await _call(cfg, http, "deleteMessage", {"chat_id": chat, "message_id": mid})
        if not (r and r.get("ok")):  # gone already (another admin was faster), or our rights
            log.warning("swear: %s", str((r or {}).get("description"))[:120])
            if (miss := await swear_rights(cfg, http, chat)) is not None:
                logic.chatmod.rights(con, chat, miss)
            return
        t = time.monotonic()
        mine, room = (_swore.setdefault(k, []) for k in ((chat, tg), (chat, 0)))
        mine[:], room[:] = [x for x in mine if t - x < 60], [x for x in room if t - x < 60]
        if len(mine) >= SWEAR_CAP or len(room) >= SWEAR_CHAT_CAP:  # a flood: only deleted, nothing counted or said
            return
        mine.append(t)
        room.append(t)
        rid, n = logic.chatmod.hit(con, cid, tg, stem)
        kind = "warn"
        if n >= logic.chatmod.WARNS and status != "restricted":
            no = dict.fromkeys(("can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos",
                                "can_send_video_notes", "can_send_voice_notes", "can_send_polls", "can_send_other_messages",
                                "can_add_web_page_previews"), False)
            x = await _call(cfg, http, "restrictChatMember", {"chat_id": chat, "user_id": tg, "permissions": no,
                                                               "until_date": int(time.time()) + logic.chatmod.MUTE})
            if x and x.get("ok"):
                logic.chatmod.muted(con, rid)
                kind = "mute"
            else:
                log.warning("swear mute: %s", str((x or {}).get("description"))[:120])
                if (miss := await swear_rights(cfg, http, chat)) is not None:
                    logic.chatmod.rights(con, chat, miss)
        sent = await _call(cfg, http, "sendMessage", {"chat_id": chat, "text": texts.swear(lang, kind),
                                                      "parse_mode": "HTML", **({"message_thread_id": topic} if topic else {})})
        if sent and sent.get("ok"):
            u = asyncio.get_running_loop().create_task(_unsay(cfg, http, chat, sent["result"]["message_id"]))
            tgc._tasks.add(u)
            u.add_done_callback(tgc._tasks.discard)
    finally:
        con.close()


async def _unsay(cfg: Config, http: httpx.AsyncClient, chat: int, mid: int) -> None:
    await _nap(WARN_FOR)  # a stop deletes it early: no process would be left to do it later
    await _call(cfg, http, "deleteMessage", {"chat_id": chat, "message_id": mid})


def _inert(say: str) -> str:
    """The caller's words, repeated: never a mention, a link, a command, a hashtag (a word joiner after the sign)."""
    return re.sub(r"([@#$/.:])", "\\1\u2060", say)


async def _tag_all(cfg: Config, http: httpx.AsyncClient, chat: int, to: int, who: int, say: str = "", mid: int = 0, lang: str | None = None) -> None:
    """/all by `who`: everyone in the chat, five a message (Telegram notifies only the first five mentions), each an emoji
    linked by id (no username needed), as replies under `to`; stops at the first refusal. Whom: the app's list, the seen
    ones, then the chat's participants Telegram lists to our bot right now (mtbot.members; none if it can't: the first two
    alone); logic.tag_all. Those Telegram just listed are in the chat; each of the others is asked (getChatMember, ten at a
    time) and one not there forgotten. `say`: the caller's own words after the command, repeated over each five (a
    push then shows why one is called, as every tag bot does): plain text, escaped, short. Fast at first
    (TAG_BURST messages TAG_FAST apart: a group takes about 20 a minute), then TAG_GAP.
    At most TAG_MAX people: past it the rest aren't called this run, and the chat waits ALL_AGAIN like after any run.
    Nobody to call (alone there, or nobody known): a template under the command (`mid`), and no wait after."""
    gone: list[int] = []
    called = sent_n = 0
    failed = False
    head = f"{html.escape(_inert(say))}\n\n" if say else ""
    body = {"chat_id": chat, "parse_mode": "HTML", "reply_parameters": {"message_id": to, "allow_sending_without_reply": True},
            "link_preview_options": {"is_disabled": True}}
    quiet = False

    async def send(batch: list[int]) -> bool:
        nonlocal called, sent_n, failed
        marks = random.sample(TAG_MARKS, len(batch))
        gap = 0 if not sent_n else TAG_FAST if sent_n < TAG_BURST else TAG_GAP  # the first one at once
        sent = await _call(cfg, http, "sendMessage", {**body, "text": head + "".join(f'<a href="tg://user?id={t}">{premium(m)}</a>' for m, t in zip(marks, batch))}, gap)
        if sent and not sent.get("ok") and bot._custom_re:  # the pack's emoji refused inside a mention: the plain ones
            sent = await _call(cfg, http, "sendMessage", {**body, "text": head + "".join(f'<a href="tg://user?id={t}">{m}</a>' for m, t in zip(marks, batch))}, gap)
        if not (sent and sent.get("ok")):  # the network, no rights, the chat gone: no more of it
            log.warning("tag all: %s", str((sent or {}).get("description"))[:120])
            failed = True
            return False
        called, sent_n = called + len(batch), sent_n + 1
        return True

    try:
        # the caller is in the chat now, by Telegram (one call per run; a guest in a channel's comments isn't)
        t0 = time.monotonic()
        me = await _call(cfg, http, "getChatMember", {"chat_id": chat, "user_id": who}, 0)
        st = (me or {}).get("result") or {} if me and me.get("ok") else {}
        status = st.get("status")
        if not (status in ("creator", "administrator", "member") or status == "restricted" and st.get("is_member")):
            quiet = True
            return
        admin = status in ("creator", "administrator")
        con = db.connect(cfg.db_path)
        try:
            if not logic.chatlist.may_call(con, chat, who, admin):
                quiet = True
                return
            t1 = time.monotonic()
            roster = await mtbot.members(cfg, chat, TAG_MAX)  # read no further than the cap: a 10 000 group costs 300 ids
            # where a slow /all spends its time: durations only, no chat and no person
            log.warning("tag all: caller %.1f s, members %.1f s (%s)", t1 - t0, time.monotonic() - t1, "list" if roster else "no list")
            # members hidden in the chat: the bot never shows a roster the caller couldn't see (its admins can)
            live = roster.ids if roster and (not roster.hidden or admin) else []
            people = [t for t in logic.tag_all(con, chat, who, live) if not roster or t not in roster.skip]  # deleted, bots
        finally:
            con.close()
        sure = set(live)
        batch: list[int] = []
        for i in range(0, len(people), 10):
            some = people[i:i + 10]
            ask = [tg for tg in some if tg not in sure]
            told = dict(zip(ask, await asyncio.gather(*(_call(cfg, http, "getChatMember", {"chat_id": chat, "user_id": tg}, 0) for tg in ask))))
            for tg in some:
                m = told.get(tg)
                if tg in sure or m and m.get("ok") and logic.chatsync.in_chat(m["result"]) and not (m["result"].get("user") or {}).get("is_bot"):
                    batch.append(tg)
                elif m and m.get("ok"):  # Telegram says not in the chat: forgotten if the bot remembered them
                    gone.append(tg)
            while len(batch) >= 5 and called < TAG_MAX:
                n = min(5, TAG_MAX - called)
                if not await send(batch[:n]):
                    return
                batch = batch[n:]
            if called >= TAG_MAX:
                return
        if batch and called < TAG_MAX:
            await send(batch[:TAG_MAX - called])
    finally:
        _tagging.discard(chat)
        now_id = _moved.get(chat, chat)  # turned supergroup meanwhile: the wait goes on under its new id
        if quiet:
            pass
        elif called or failed:
            _tagged[now_id] = time.time()
        else:  # nobody called: a short wait only; never silence for a call on purpose (the bot unable to send stays silent)
            _tagged[now_id] = time.time() - max(0, ALL_AGAIN - EMPTY_WAIT)
            if mid:
                _refuse(cfg, http, chat, mid, lang, "all_none")
        if gone:
            con = db.connect(cfg.db_path)
            try:
                for tg in gone:
                    logic.chatlist.unseen(con, chat, tg)
            finally:
                con.close()


def _event_copy(cfg: Config, msg: dict) -> bool:
    """Telegram's copy of an events channel post in its discussion group."""
    channel = cfg.events_channel.lstrip("@").lower()
    return bool(channel) and bool(msg.get("is_automatic_forward")) and str((msg.get("sender_chat") or {}).get("username") or "").lower() == channel


async def _discussion_bg(cfg: Config, http: httpx.AsyncClient, msg: dict) -> None:
    """_discussion beside the ears (tgc.spawn): its wait for the post's id never holds up the batch."""
    con = db.connect(cfg.db_path)
    try:
        await _discussion(cfg, http, con, msg)
    except Exception:  # noqa: BLE001
        log.exception("discussion")
    finally:
        con.close()


_video_uploads = asyncio.Semaphore(2)  # only full transfers hold a slot; cached and URL replies can always start
_video_log = logging.getLogger("uvicorn.error")  # the runtime's INFO handler


def _video_updates(cfg: Config, http: httpx.AsyncClient, updates: list[dict]) -> None:
    if not cfg.tiktok:
        return
    for upd in updates:
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        try:
            if chat.get("type") not in ("group", "supergroup") or tgc.ours(cfg, upd) or upd["update_id"] in _video_seen:
                continue
            if time.time() - int(msg.get("date") or 0) > FRESH or not (url := tiktok.link(msg)):
                continue
            _video_seen.add(upd["update_id"])
            tgc.spawn(_group_video(cfg, http, msg, url, time.monotonic()), chain=None)
        except Exception as exc:  # one bad update must not delay the others
            log.warning("group video: %s", type(exc).__name__)


async def _group_video(cfg: Config, http: httpx.AsyncClient, msg: dict, url: str, started: float) -> None:
    # The poller's connection may be in use by a receipt or already closed when this task starts.
    try:
        con = db.connect(cfg.db_path)
        try:
            if _swear_hit(con, msg) or logic.chatlist.banned(con, int((msg.get("from") or {}).get("id") or 0)):
                return
        finally:
            con.close()
        if tiktok.room(msg["chat"]["id"], user=int((msg.get("from") or {}).get("id") or 0), video=tiktok.key(url)):
            await _tiktok(cfg, http, msg, url, started)
    except Exception as exc:
        log.warning("group video: %s", type(exc).__name__)


async def _tiktok(cfg: Config, http: httpx.AsyncClient, msg: dict, url: str, started: float | None = None) -> None:
    started = time.monotonic() if started is None else started
    # whose link it is: the Instagram session's own caps per chat and per person (tiktok._session_take)
    asker = tiktok.asker.set((msg["chat"]["id"], int((msg.get("from") or {}).get("id") or 0)))
    chat = {"chat_id": msg["chat"]["id"]}
    if msg.get("is_topic_message") and msg.get("message_thread_id"):
        chat["message_thread_id"] = msg["message_thread_id"]
    api = f"https://api.telegram.org/bot{cfg.bot_token}/"

    async def action():
        try:
            await http.post(api + "sendChatAction", json={**chat, "action": "upload_video"}, timeout=4)
        except httpx.HTTPError:
            pass

    async def reply():
        try:
            async with asyncio.timeout(tiktok.REPLY_SECONDS):
                route = await _video_reply(http, api, chat, msg["message_id"], url)
        except Exception as exc:  # the network or the source failed, or took too long: leave the link alone
            route = type(exc).__name__
        _video_log.info("group video %s %.3fs", route, time.monotonic() - started)

    try:
        await asyncio.gather(action(), reply())  # its tasks copy the context: they see the asker
    finally:
        tiktok.asker.reset(asker)


async def _video_reply(http: httpx.AsyncClient, api: str, chat: dict, mid: int, url: str) -> str:
    reply = {"message_id": mid, "allow_sending_without_reply": True}
    body = {**chat, "reply_parameters": reply, "supports_streaming": True}
    form = {**chat, "reply_parameters": json.dumps(reply)}
    alias = tiktok.key(url)
    short_host = bool(tiktok.LINK.match(url)["short_host"])

    async def reuse(k: str) -> str | None:
        entry = tiktok.cached(k)
        if not entry:
            return None
        file_id, duration = entry
        if isinstance(file_id, tuple):  # an album's items: a slideshow's photos, a post's photos and videos
            if len(file_id) == 1:
                (one,) = file_id
                kind, media = one["type"], one["media"]
                extra = {k: v for k, v in one.items() if k not in ("type", "media")}
                r = await http.post(api + ("sendPhoto" if kind == "photo" else "sendVideo"),
                                    json={**chat, "reply_parameters": reply, **extra, kind: media}, timeout=60)
            else:
                r = await http.post(api + "sendMediaGroup",
                                    json={**chat, "reply_parameters": reply, "media": [dict(m) for m in file_id]}, timeout=60)
        elif short_host and duration >= 180:
            return "unavailable"  # youtu.be has a stricter duration limit than /shorts/
        else:
            r = await http.post(api + "sendVideo", json={**body, "video": file_id}, timeout=60)
        answer = r.json()
        if answer.get("error_code", r.status_code) == 400:
            if tiktok.cached(k) == entry:
                tiktok.forget(k)
            return None
        if not answer.get("ok"):
            return "refused"
        tiktok.remember(alias, file_id, duration)
        return "cache"

    if route := await reuse(alias):
        return route
    # The same video asked for at once (several chats, or twice in one) is fetched once: the others wait for the first
    # and send its file id. A youtu.be link flies apart from /shorts/ ones: its source answer can differ (shorter cap).
    lane = alias + ":be" if short_host else alias
    async with tiktok.flight(lane) as shared:
        if shared.runs:
            if route := await reuse(alias):
                return route
            if shared.gone:
                return "unavailable"
        got = await tiktok.fetch(http, url)
        if not got:
            shared.gone = True
            return "unavailable"
        if isinstance(got, (list, tiktok.Album)):  # an Album's key is its link's (ig:<code>): this flight's
            async with _video_uploads:
                route = await _video_album(http, api, form, got, alias)
            shared.gone = route == "unavailable"
            return route
        if got.key == lane:
            route = await _video_send(http, api, body, form, alias, got)
            shared.gone = route == "unavailable"
            return route
        async with tiktok.flight(got.key) as same:  # another link to this same video may be on its way
            if same.gone:
                return "unavailable"
            if route := await reuse(got.key):
                return route
            route = await _video_send(http, api, body, form, alias, got)
            shared.gone = same.gone = route == "unavailable"  # the source had nothing sendable
            return route


async def _video_send(http: httpx.AsyncClient, api: str, body: dict, form: dict, alias: str, got: tiktok.Clip) -> str:
    for version in await tiktok.versions(http, got):
        f = version.video
        duration = got.duration or f.get("duration") or 0
        meta = {k: int(v) for k, v in (("duration", duration), ("width", f.get("width")), ("height", f.get("height"))) if v}
        route = "url"
        answer = {}
        if version.direct:
            # Telegram accepts a remote cover by URL. Custom thumbnails accompany multipart uploads.
            cover = {"cover": got.cover} if got.cover.startswith("https://") else {}
            r = await http.post(api + "sendVideo", json={**body, **meta, **cover, "video": f["url"]}, timeout=60)
            answer = r.json()
            if not answer.get("ok") and answer.get("error_code", r.status_code) not in (400, 413):
                return "refused"
        if not answer.get("ok"):
            async with _video_uploads:
                try:
                    upload = await tiktok.prepare_upload(http, got, version)
                except tiktok.Paused:  # the source rests: a later version may still go by URL
                    upload = None
                if not upload:
                    continue  # e.g. the real size exceeds the estimate: try the next resolution
                meta, files = _video_files(tiktok.Part(*upload), "video", "thumbnail")
                r = await http.post(api + "sendVideo", data={**form, **meta, "supports_streaming": "true"}, files=files, timeout=120)
                answer = r.json()
                route = "upload"
        if not answer.get("ok"):
            return "refused"
        if file_id := (answer.get("result", {}).get("video") or {}).get("file_id"):
            for k in (got.key, alias):
                tiktok.remember(k, file_id, duration)
        return route
    return "unavailable"


def _video_files(part: tiktok.Part, name: str, thumb: str) -> tuple[dict, dict]:
    """A video upload's InputMedia fields (its real duration and size, the thumbnail as an attachment) and its files."""
    meta = {k: int(part.tracks[k]) for k in ("duration", "width", "height") if part.tracks.get(k)}
    files = {name: (f"{name}.mp4", part.data, "video/mp4")}
    if part.thumb:
        files[thumb] = (f"{thumb}.jpg", part.thumb, "image/jpeg")
        meta["thumbnail"] = f"attach://{thumb}"
    return meta, files


async def _video_album(http: httpx.AsyncClient, api: str, form: dict, got: list[str] | tiktok.Album, alias: str) -> str:
    """A slideshow's photos, or an Instagram post's photos and videos: one alone as itself, more as one album, no
    caption. The items that failed are left out; none left: nothing at all."""
    if isinstance(got, tiktok.Album):
        parts = await tiktok.gather(http, got)
    else:
        parts = [tiktok.Part(p) for p in await tiktok.photos(http, got)]
    answer: dict = {}
    for attempt in range(2):
        if not parts:
            return "unavailable"
        answer = await _album_send(http, api, form, parts)
        if answer.get("ok") or attempt:
            break
        # Telegram refuses an album whole for one item it can't take, naming it ("message #3"): once, the rest go
        bad = re.search(r"message #(\d+) ", str(answer.get("description") or ""))
        if answer.get("error_code") != 400 or not bad or len(parts) < 2 or not 1 <= int(bad[1]) <= len(parts):
            break
        del parts[int(bad[1]) - 1]
    if not answer.get("ok"):
        return "refused"
    sent = answer.get("result")
    sent = sent if isinstance(sent, list) else [sent]
    # each item's file id (a photo's largest size): another chat gets them by id, without a second download
    media = tuple(_sent_media(m, p) for m, p in zip(sent, parts))
    if len(sent) == len(parts) and all(media):
        tiktok.remember(alias, media, 0)
    return "photos" if all(p.tracks is None for p in parts) else "album"


async def _album_send(http: httpx.AsyncClient, api: str, form: dict, parts: list[tiktok.Part]) -> dict:
    if len(parts) == 1 and parts[0].tracks is None:
        method, data, files = "sendPhoto", form, {"photo": ("tiktok.jpg", parts[0].data, "image/jpeg")}
    elif len(parts) == 1:
        meta, files = _video_files(parts[0], "video", "thumbnail")
        method, data = "sendVideo", {**form, **meta, "supports_streaming": "true"}
    else:
        files, media = {}, []
        for i, p in enumerate(parts):  # each file its own part; a video's thumbnail beside it
            if p.tracks is None:
                files[f"p{i}"] = (f"{i}.jpg", p.data, "image/jpeg")
                media.append({"type": "photo", "media": f"attach://p{i}"})
            else:
                meta, more = _video_files(p, f"v{i}", f"t{i}")
                files.update(more)
                media.append({"type": "video", "media": f"attach://v{i}", **meta, "supports_streaming": True})
        method, data = "sendMediaGroup", {**form, "media": json.dumps(media)}
    r = await http.post(api + method, data=data, files=files, timeout=120)
    answer = r.json()
    return answer if answer.get("ok") else {**answer, "error_code": answer.get("error_code", r.status_code)}


def _sent_media(m, part: tiktok.Part) -> dict | None:
    """The InputMedia that sends this item again by its file id."""
    if not isinstance(m, dict):
        return None
    if part.tracks is None:
        file_id = ((m.get("photo") or [{}])[-1] or {}).get("file_id")
        return {"type": "photo", "media": file_id} if isinstance(file_id, str) else None
    file_id = (m.get("video") or {}).get("file_id")
    meta = {k: int(part.tracks[k]) for k in ("duration", "width", "height") if part.tracks.get(k)}
    return {"type": "video", "media": file_id, **meta, "supports_streaming": True} if isinstance(file_id, str) else None


async def _discussion(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> bool:
    """The channel's discussion group: Telegram forwards each post there by itself, and the comments are replies to that
    copy. Under an event's post the bot writes the first comment, the rules and "Sign up", and keeps its link for the
    app's "Discuss". True: the message was such a copy. Needs the bot in that group, as an admin
    (a bot that isn't one doesn't see the group's messages)."""
    channel = cfg.events_channel.lstrip("@").lower()
    if not _event_copy(cfg, msg):
        return False
    post = int((msg.get("forward_origin") or {}).get("message_id") or msg.get("forward_from_message_id") or 0)
    # the copy can come before post_channel, running beside us, has stored the post's id: give it a moment
    # ponytail: a channel post that is no event's waits these 3 s too; a few a week
    for wait in (0, 1, 2):
        await asyncio.sleep(wait)
        if e := logic.channel_discussion(con, post):
            break
        if one(con, "SELECT 1 FROM events WHERE channel_msg = ?", post):
            return True  # commented already
    else:
        return True
    keys = {"inline_keyboard": [[{"text": texts.CHANNEL_BUTTON, "url": f"https://t.me/{cfg.bot_username}?startapp=ev_{e['id']}"}]]}
    r = (await _send(cfg, http, {
        "chat_id": msg["chat"]["id"], "text": texts.CHANNEL_RULES, "parse_mode": "HTML", "reply_markup": keys,
        "reply_parameters": {"message_id": msg["message_id"]}})).json()
    if not r.get("ok"):
        log.warning("discussion %d: %s", e["id"], str(r.get("description"))[:200])
        return True
    con.execute("UPDATE events SET channel_link = ? WHERE id = ?", (f"https://t.me/{channel}/{e['channel_msg']}?comment={r['result']['message_id']}", e["id"]))
    # where the post's copy sits in the group: deleting the event deletes it too (logic.delete_event)
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"thread:{e['id']}", f"{msg['chat']['id']} {msg['message_id']}"))
    return True
