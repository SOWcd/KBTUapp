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

from . import ai, casting, db, download, llm, logic, media, mirror, mtbot, offsite, portal, push, receipt, swear, texts, tgc, tiktok, userbot, video
from .config import Config
from .logic import notifications, now, one, rows
from .logic.account import _Taken
from .logic.core import ApiError

log = logging.getLogger("kbtu.bot")

POLL = 2                    # seconds between outbox checks
GAP = 0.05                  # ≤ 20 messages a second (Telegram allows about 30)
AI_GAP = 10                 # seconds between translations (ai.py): a backlog drains without a burst
LEASE = 60                  # a taken message is free again after this, if its postman died or the network was down
PEEK = 2                    # seconds between looks for Stars' pre-checkouts while a batch of updates runs (_checkout_watch)
CHECKOUT_HTTP = 3          # one answerPreCheckoutQuery at most: answers go in turn, so a hung one eats its neighbours' 10 s
CHECKOUT_RETRY = 1         # seconds between rounds of retries of the answers that failed
CHECKOUT_WINDOW = 8        # stop retrying after this: Telegram allows 10 s, and a try started later would land too late
_checked: deque[str] = deque(maxlen=256)  # pre-checkouts already answered: the look and the next round see the same ones
WAIT = 25                   # getUpdates: Telegram holds the request this long while nobody writes
FRESH = 300                 # an older message isn't answered: what piled up while nobody listened
SYNC_GAP = 0.25             # a chat sync's getChatMember calls: about 4 a second, beside the postman (logic/chatsync.py)
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


def _appeal_kind(n: int) -> str:
    """The appeals message by Russian plural: 1 alone, 21/31…, 2–4/22…, the rest (kk, en: one text past 1)."""
    if n == 1:
        return "fch_appeal"
    if n % 10 == 1 and n % 100 != 11:
        return "fch_appeal_one"
    return "fch_appeal_few" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "fch_appeal_many"


def _render(con, m) -> tuple[str, str | None, str | list] | None:
    """(text, button, startapp) for one outbox row, or None when what it was about is gone. A list in place of startapp
    is the whole keyboard (rows of buttons: "start" opens the app there, "url" a link, "callback_data" a tap)."""
    kind, ref, lang = m["kind"], m["ref"].split(":"), m["lang"]
    if kind == "app_broadcast":  # the creator's CLI announcement, with a Telegram URL button
        msg = texts.broadcast_message(lang, m["ref"])
        url = json.loads(m["payload"]).get("url")
        votes = [{"text": texts.bot_message(lang, f"vote_{v}")[0], "callback_data": f"bv:{v}:{m['ref']}"} for v in (1, 0)]
        return (msg[0], None, [[{"text": msg[1], "url": url}], votes]) if msg and url else None
    ev = lambda e: {"title": logic.title_in(e, lang), "when": texts.when(e["starts_at"], lang), "place": texts.place_or_tba(e["place"], lang, "online" in e.keys() and e["online"] is not None)}  # noqa: E731
    reminders = lambda: one(con, "SELECT n_remind FROM users WHERE id = ?", m["user_id"])[0]  # noqa: E731  (the switch for cards about events)

    def listed(evs):  # a line per event, the first one opened
        text, button = texts.bot_message(lang, kind, list="\n".join(f"• {logic.title_in(e, lang)}, {texts.when(e['starts_at'], lang)}" for e in evs))
        return text, button, f"ev_{evs[0]['id']}"
    if kind.startswith("tgc_"):  # the forum channel's comments (tgc.py)
        return tgc.render(con, m, lang)
    if kind == "fch_comments":
        post = one(con, """SELECT p.id FROM fchan_posts p JOIN users u ON u.id = p.user_id
            WHERE p.id = ? AND p.user_id = ? AND p.status = 'live' AND p.tg_msg > 0
              AND u.tg_id = ? AND u.tg_id > 0 AND u.can_dm = 1 AND u.banned_at IS NULL AND u.n_forum_comments = 1""",
            int(ref[1]), m["user_id"], m["tg_id"])
        template = "fch_reply_answer" if json.loads(m["payload"]).get("answer") else kind
        return (*texts.bot_message(lang, template), f"fp_{post['id']}") if post else None
    if kind == "fch_reply_answer":  # a retiring bot queued this after migration 203 folded pending answers into fch_comments
        return None
    if kind == "fch_reply_gone":  # fg:<reply>, to the post's author (through the post): its card
        r = one(con, "SELECT p.id FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.id = ? AND p.user_id = ? AND p.status = 'live'",
                int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, kind), f"fp_{r['id']}") if r else None
    if kind in ("fch_posted", "fch_declined"):  # fp:<post> / fd:<post>, to its author: still out, still declined (an undo, a delete: nothing)
        r = one(con, "SELECT id FROM fchan_posts WHERE id = ? AND user_id = ? AND " + ("status = 'live' AND tg_msg > 0" if kind == "fch_posted"
                # declined: never once it went out (an undo published it, then a take-down)
                else "status = 'hidden' AND why = 'moderator' AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = fchan_posts.user_id AND b.kind = 'fch_posted' AND b.ref = 'fp:' || fchan_posts.id)"),
                int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, kind), f"fp_{r['id']}") if r else None
    if kind == "fch_reply_queue":  # rq:<reply>, to moderators: anonymous authors' replies reported or held, in Admin
        n = one(con, """SELECT COUNT(*) FROM fchan_replies r WHERE r.status = 'held' AND r.why != 'check'
            OR r.status = 'live' AND EXISTS (SELECT 1 FROM fchan_reply_reports x WHERE x.reply_id = r.id)""")[0]
        return (*texts.bot_message(lang, kind, n=n), "capps") if n else None
    if kind == "fch_appeal":  # fq:<hour>, to moderators: refused posts their authors sent for a look, waiting in Admin
        n = one(con, "SELECT COUNT(*) FROM fchan_posts WHERE status = 'held' AND appealed_at IS NOT NULL")[0]
        return (*texts.bot_message(lang, _appeal_kind(n), n=n), "capps") if n else None
    if kind == "appeal_answer":  # apl:<appeal>, to its author: SG answered (a template, never the words); gone: nothing
        mine = one(con, "SELECT 1 FROM appeal_authors WHERE appeal_id = ? AND user_id = ?", int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, kind), f"apl_{int(ref[1])}") if mine else None  # that appeal's own view
    if kind == "ask_answer":  # apl:<question>, to its author: a person answered the question KRI couldn't (a template)
        mine = one(con, "SELECT 1 FROM appeal_authors WHERE appeal_id = ? AND user_id = ?", int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, kind), f"ask_{int(ref[1])}") if mine and logic.appeals.ask_open(con, m["user_id"]) else None  # that question's own view; ASK off for me: its button would open nothing
    if kind == "sid_check":  # sc:<student id>, to its holder: someone else typed it; quiet once they changed theirs
        held = one(con, "SELECT 1 FROM students WHERE user_id = ? AND student_id = ?", m["user_id"], ref[1])
        return (*texts.bot_message(lang, kind, sid=ref[1]), "me") if held else None
    if kind == "sid_free":  # sf:<student id>, parked for the one turned away; woken when it's freed (migration 127)
        free = not one(con, "SELECT 1 FROM students WHERE student_id = ?", ref[1])
        return (*texts.bot_message(lang, kind, sid=ref[1]), "me") if free else None
    if kind == "id_clash":  # Render queued clash alerts until they expire so pending notices can still reach admins.
        who = [one(con, """SELECT u.tg_id, u.tg_username, u.tg_first_name, s.first_name, s.last_name, s.email
            FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.id = ?""", int(x)) for x in ref[2:4]]
        if not all(who):
            return None
        f, held = {}, json.loads(m["payload"] or "{}")  # the holder as they were when it happened
        for k, p in zip("ab", who):
            f[k + "name"] = (k == "b" and held.get("name")) or " ".join(x for x in (p["first_name"], p["last_name"]) if x) or p["tg_first_name"]
            f[k + "mail"] = (k == "b" and held.get("email")) or p["email"] or "—"
            f[k + "tg"] = "@" + p["tg_username"] if p["tg_username"] else p["tg_first_name"]
            f[k + "id"] = p["tg_id"]
        return (*texts.bot_message(lang, kind, sid=ref[1], **f), "")
    if kind == "ask_match":  # am:<request>: a project request for my skills; quiet once it's gone or my pings are off
        a = one(con, "SELECT * FROM asks WHERE id = ? AND status = 'live' AND expires_at > ?", int(ref[1]), logic.now())
        if not a or not one(con, "SELECT ask_pings FROM users WHERE id = ?", m["user_id"])[0]:
            return None
        sk = one(con, """SELECT s.name FROM ask_skills k JOIN skills s ON s.id = k.skill_id WHERE k.ask_id = ?
            ORDER BY EXISTS (SELECT 1 FROM user_skills u WHERE u.user_id = ? AND u.skill_id = s.id) DESC, s.name""", a["id"], m["user_id"])
        return (*texts.bot_message(lang, kind, skill=sk["name"] if sk else ""), f"fa_{a['id']}")
    if kind == "org_ask":  # oa:<event>:<organizer>, payload nick: write to the event's organizer (no username of mine to give
        # him). The ask's own rules (organizing._reach) again: quiet once my seat or the event is gone (cancelled, a
        # week after the end), he lost the club's right or is banned, either of us blocked the other, or his username
        # isn't the one he asked with (a handle he gave up may be someone else's now)
        e = one(con, """SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id JOIN registrations r ON r.event_id = e.id
            AND r.user_id = ? AND (r.status = 'going' OR r.status = 'hold' AND r.hold_until >= ?)
            WHERE e.id = ? AND e.status = 'published' AND e.hidden_at IS NULL""", m["user_id"], logic.now(), int(ref[1]))
        o, me, nick = int(ref[2]), m["user_id"], json.loads(m["payload"] or "{}").get("nick")
        if not e or logic.seats.end_of(e) + logic.organizing.REVEAL_AFTER < logic.now() or "events" not in logic.rights_of(con, o, e["org_id"]) \
                or not one(con, "SELECT 1 FROM users WHERE id = ? AND banned_at IS NULL AND tg_username = ?", o, nick) \
                or one(con, "SELECT 1 FROM blocks WHERE (user_id = ? AND blocked_id = ?) OR (user_id = ? AND blocked_id = ?)", o, me, me, o):
            return None
        text, button = texts.bot_message(lang, kind, title=logic.title_in(e, lang), org=e["org_name"])
        return text, None, [[{"text": button, "url": f"https://t.me/{nick}"}]]
    if kind == "contact_ask":  # ct:<contact>[:<token>]: someone offers help or wants to get in touch; Accept shares both contacts
        tok = ref[2] if len(ref) > 2 else None  # the offer's own: a reused id never shows (or answers) another's
        if not tok and (old := one(con, "SELECT id FROM contacts WHERE id = ? AND to_id = ? AND status = 'pending' AND token IS NULL", int(ref[1]), m["user_id"])):
            tok = secrets.token_hex(4)  # Give tokenless offers a token so the card can identify the exact offer.
            con.execute("UPDATE contacts SET token = ? WHERE id = ?", (tok, old["id"]))
        c = tok and one(con, "SELECT * FROM contacts WHERE id = ? AND to_id = ? AND status = 'pending' AND token = ?", int(ref[1]), m["user_id"], tok)
        p = c and one(con, logic.PERSON + " WHERE u.id = ?", c["from_id"])
        if not p:
            return None
        a = one(con, "SELECT title, subject FROM asks WHERE id = ?", c["ask_id"]) if c["ask_id"] else None
        skills = ", ".join(s["name"] for s in rows(con, "SELECT s.name FROM user_skills k JOIN skills s ON s.id = k.skill_id WHERE k.user_id = ? ORDER BY s.name", p["id"]))
        kind = ("contact_subj" if a["subject"] else "contact_ask") if a else "contact_ask_plain"  # a subject's: its catalogue name
        text = texts.bot_message(lang, kind, name=logic.short_name(p), title=a["title"] if a else "", skills=skills or "\u2014")[0]
        yes, no = texts.bot_message(lang, "contact_buttons")
        k = f"ct:{c['id']}:{tok}"
        return text, None, [[{"text": yes, "callback_data": f"{k}:y"}, {"text": no, "callback_data": f"{k}:n"}]]
    if kind == "contact_ok":  # co:<contact>:to|from:<token>: accepted; each side gets the other's Telegram, never a stranger's
        c = len(ref) > 3 and one(con, "SELECT * FROM contacts WHERE id = ? AND status = 'accepted' AND token = ?", int(ref[1]), ref[3])
        if c and m["user_id"] != (c["from_id"] if ref[2] == "to" else c["to_id"]):  # rendered for its own recipient only
            c = None
        other = c and (c["to_id"] if ref[2] == "to" else c["from_id"])
        p = other and one(con, logic.PERSON + " WHERE u.id = ?", other)
        if not p:
            return None
        text, button = texts.bot_message(lang, kind, name=logic.short_name(p))
        return text, None, [[{"text": button, "url": logic.telegram_of(con, other)}]]
    if kind == "ask_hidden":  # ah:<request>, to its author: why it's gone from the lists
        a = one(con, "SELECT title, why, subject FROM asks WHERE id = ? AND status = 'hidden'", int(ref[1]))
        why = texts.pick(texts.ASK_WHY, lang).get(a["why"] or "") if a else None
        return (*texts.bot_message(lang, kind, title=a["title"], why=why), f"sj_{a['subject']}" if a["subject"] else f"fa_{ref[1]}") if why else None
    if kind in ("backup_failed", "backup_ok", "userbot_off", "userbot_ok"):  # bf/bo:<day> to the admins; uo/ub:<since> to the owner
        return (*texts.bot_message(lang, kind), "")
    if kind in ("prefill_no_match", "prefill_other_id", "prefill_id_held"):  # pn/pf:<user>, ph:<user>:<holder>, to the owner (account.ms_link)
        return (*texts.bot_message(lang, kind, user=ref[1], holder=ref[-1]), "")
    if kind == "channel_ask":  # ca:<org>, to the club's President (admin channel-ask): gone once the club has its channel
        o = one(con, """SELECT o.name FROM orgs o JOIN org_members m ON m.org_id = o.id AND m.user_id = ? AND m.role = 'president'
            WHERE o.id = ? AND o.status = 'active'""", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"ce_{ref[1]}") if o and not mirror.has_channel(con, int(ref[1])) else None
    if kind == "auto_event":  # ae:<event>, to its club's President, once: a draft found in the club's channel; quiet once published, deleted or dismissed
        e = one(con, """SELECT e.org_id, o.name FROM events e JOIN orgs o ON o.id = e.org_id AND o.status = 'active'
            JOIN org_members m ON m.org_id = o.id AND m.user_id = ? AND m.role = 'president'
            WHERE e.id = ? AND e.status = 'draft' AND e.hidden_at IS NULL""", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, org=e["name"]), f"st_{e['org_id']}") if e else None
    if kind == "delete_soon":  # del:<when>, to me; gone if I changed my mind
        at = one(con, "SELECT delete_at FROM users WHERE id = ?", m["user_id"])["delete_at"]
        return (*texts.bot_message(lang, kind, when=texts.when(at, lang).split(",")[0]), "me") if at else None
    if kind == "join_request":  # jr:<org>:<applicant>:<day>, to the club's Vice+; gone once withdrawn or answered
        o, p = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1])), one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not o or not p or not one(con, "SELECT 1 FROM join_requests WHERE org_id = ? AND user_id = ? AND status = 'pending'", int(ref[1]), int(ref[2])):
            return None
        return (*texts.bot_message(lang, kind, org=o["name"], name=logic.short_name(p)), f"jr_{ref[1]}")
    if kind == "team_ask":  # ta:<event>:<member>:<day>, to the club's President and Vices; gone once answered, withdrawn or too late
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[1]))
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not e or not p or not logic.signup_open(e) or not one(con, "SELECT 1 FROM team_asks WHERE event_id = ? AND user_id = ? AND status = 'pending'", e["id"], p["id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.short_name(p), title=logic.title_in(e, lang)), f"mg_{e['id']}")
    if kind in ("team_ask_yes", "team_ask_no"):  # tad:<event>:<day>, to the member; quiet if it changed since or sign-up is over
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[1]))
        if not e or not logic.signup_open(e) or not one(con, "SELECT 1 FROM team_asks WHERE event_id = ? AND user_id = ? AND status = ?",
                                                        e["id"], m["user_id"], kind.rsplit("_", 1)[1]):
            return None
        return (*texts.bot_message(lang, kind, **ev(e)), f"ev_{e['id']}")
    if kind == "roster_claim":  # rq:<row>:<student>, to the club's President (or DMP): it's them under another name?
        r = one(con, "SELECT r.title, o.name FROM roster_pending r JOIN orgs o ON o.id = r.org_id WHERE r.id = ? AND r.claimed_by = ?", int(ref[1]), int(ref[2]))
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not r or not p:
            return None
        return (*texts.bot_message(lang, kind, org=r["name"], name=logic.short_name(p)), "rq")
    if kind == "join_decided":  # jr:<request>:yes|no, to the applicant
        r = one(con, "SELECT j.org_id, o.name FROM join_requests j JOIN orgs o ON o.id = j.org_id WHERE j.id = ?", int(ref[1]))
        if not r:
            return None
        return (*texts.bot_message(lang, "join_yes" if ref[2] == "yes" else "join_no", org=r["name"]), f"cl_{r['org_id']}")
    if kind == "rate":  # rate:<event>, an hour after the end, to those checked in; not if rated already or reminders are off
        e = one(con, "SELECT title, i18n FROM events WHERE id = ? AND status = 'published'", int(ref[1]))
        if not e or not reminders() or one(con, "SELECT 1 FROM event_ratings WHERE event_id = ? AND user_id = ?", int(ref[1]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, title=logic.title_in(e, lang)), f"ev_{ref[1]}")
    if kind == "event_update":  # upd:<id>; gone if the organizer deleted it or the event is no longer on
        u = one(con, """SELECT e.id, e.title, e.i18n, o.name FROM event_updates x JOIN events e ON e.id = x.event_id JOIN orgs o ON o.id = e.org_id
            WHERE x.id = ? AND e.status = 'published' AND e.hidden_at IS NULL AND o.status != 'hidden'""", int(ref[1]))
        return (*texts.bot_message(lang, kind, title=logic.title_in(u, lang), org=u["name"]), f"ev_{u['id']}") if u else None
    if kind in ("broadcast", "important"):  # post:<id>, to every club member / to its club's members; gone if taken down
        post = one(con, "SELECT p.title, p.i18n, o.name FROM posts p JOIN orgs o ON o.id = p.org_id WHERE p.id = ? AND p.hidden_at IS NULL", int(ref[1]))
        return (*texts.bot_message(lang, kind, org=post["name"], title=logic.title_in(post, lang)), "news") if post else None
    if kind == "casting_open":  # cst:<post>, to a club's followers who aren't in it; gone once it's over, cancelled or deleted
        p = one(con, """SELECT p.casting_from, o.name FROM posts p JOIN orgs o ON o.id = p.org_id
            WHERE p.id = ? AND p.hidden_at IS NULL AND p.casting_cancelled_at IS NULL AND p.casting_to > ?""", int(ref[1]), logic.now())
        return (*texts.bot_message(lang, kind, org=p["name"], when=texts.when(p["casting_from"], lang)), "news") if p else None
    if kind == "club_hidden":  # chid:<org>, to its president, once; gone if the club has gathered its people meanwhile
        c = one(con, """SELECT o.id, o.name, (SELECT COUNT(*) FROM org_members m WHERE m.org_id = o.id) AS n FROM orgs o WHERE o.id = ? AND o.status = 'active'""", int(ref[1]))
        return (*texts.bot_message(lang, kind, org=c["name"], n=c["n"], need=logic.clubs.CLUB_MIN), f"cl_{c['id']}") if c and c["n"] < logic.clubs.CLUB_MIN else None
    if kind == "friend_request":  # fq:<asker>:<day>; gone once answered or taken back
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[1]))
        if not p or not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", int(ref[1]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p)), "friends")
    if kind == "event_reported":  # er:<event>:<its oldest open report>, to moderators: 3 people reported it; quiet once decided or taken down
        r = one(con, "SELECT 1 FROM reports r JOIN events e ON e.id = r.target_id AND e.hidden_at IS NULL WHERE r.id = ? AND r.status = 'open'", int(ref[2]))
        return (*texts.bot_message(lang, kind), "capps") if r else None
    if kind == "santa_reported":  # srp:<report>, to moderators: a Santa chat was reported; quiet once handled
        r = one(con, "SELECT 1 FROM santa_msgs WHERE id = ? AND text IS NULL AND done_at IS NULL", int(ref[1]))
        return (*texts.bot_message(lang, kind), "capps") if r else None
    if kind == "chat_suggested":  # cs:<day>, to admins and moderators: once a day at most, while some still wait
        n = one(con, "SELECT COUNT(*) FROM chats WHERE status = 'pending'")[0]
        return (*texts.bot_message(lang, kind, n=n), "achats") if n else None
    if kind == "chat_approved":  # ca:<chat>, to each who suggested it, while it is still in the catalog: the Chats screen
        c = one(con, "SELECT title, kind, forum FROM chats WHERE id = ? AND status = 'live'", int(ref[1]))
        return (*texts.chat_approved(lang, "forum" if c["forum"] else c["kind"], c["title"]), "chats") if c else None
    if kind in ("anon_feedback", "helper_offer"):  # afb:<day> | ho:<id>, to the creator: the template only, the words are read in Admin
        boss = one(con, "SELECT 1 FROM users WHERE id = ? AND is_founder = 1 AND role = 'admin'", m["user_id"])  # still the creator
        return (*texts.bot_message(lang, kind), "voices") if boss else None
    if kind == "club_application":  # capp:<id>, to moderators and the admin while it waits
        a = one(con, "SELECT name, status FROM club_applications WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=a["name"]), "capps") if a and a["status"] == "pending" else None
    if kind == "club_path":  # opath:<id>, to the admins while it waits
        r = one(con, "SELECT o.name FROM official_requests r JOIN orgs o ON o.id = r.org_id WHERE r.id = ? AND r.status = 'pending' AND o.official = 0", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=r["name"]), "capps") if r else None
    if kind == "sid_page_clash":  # sp:<user>:<day>, to the founder: a schedule page's student ID is another account's; the audit log has who
        return (*texts.bot_message(lang, kind), "") if one(con, "SELECT 1 FROM students WHERE user_id = ?", int(ref[1])) else None
    if kind == "club_top":  # top:<org>, to the founder: a student initiative reached the Ascent's top (its lanyard is made by hand)
        o = one(con, "SELECT name FROM orgs WHERE id = ? AND top_at IS NOT NULL AND official = 0", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"cl_{ref[1]}") if o else None
    if kind == "club_application_decided":  # cad:<id>:yes|no, to the applicant; a no's reason is read in the app (our words only here)
        a = one(con, "SELECT name, org_id, status FROM club_applications WHERE id = ?", int(ref[1]))
        if not a or a["status"] != ("approved" if ref[2] == "yes" else "rejected"):  # an Undo since: nothing to say
            return None
        return (*texts.bot_message(lang, "club_yes" if ref[2] == "yes" else "club_no", name=a["name"]), f"cl_{a['org_id']}" if ref[2] == "yes" and a["org_id"] else "newclub")
    if kind == "club_handover":  # ho:<org>, to the new President: the old one deleted the account (logic._hand_over)
        o = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"cl_{ref[1]}") if o else None
    if kind == "club_emoji":  # emo:<org>, to the President: the name lost its emoji (logic.strip_emoji_names)
        o = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"cl_{ref[1]}") if o else None
    if kind in ("club_official", "club_unofficial"):  # off:<org>, to the club's President: DMP gave the ✓ or took it (said only while still so)
        o = one(con, "SELECT name, official FROM orgs WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"cl_{ref[1]}") if o and bool(o["official"]) == (kind == "club_official") else None
    if kind == "achievement":  # ach:<code>:<level>: a new level, once (→ aw_<code>: the card, Share there)
        code, level = ref[1], int(ref[2])
        a = next((x for x in logic.ACHIEVEMENTS if x[0] == code), None)
        # gone with an Undo or a take-back before it went out: nothing to say
        if not a or not one(con, "SELECT 1 FROM achievement_levels WHERE user_id = ? AND code = ? AND level >= ?", m["user_id"], code, level):
            return None
        tier = f" · {texts.tier_name(lang, level, len(a[2]))}" if len(a[2]) > 1 else ""
        return (*texts.bot_message(lang, kind, name=texts.pick(texts.ACH_NAMES, lang)[code], tier=tier), f"aw_{logic.BADGE_OF.get(code, code)}")  # a variant opens its badge
    if kind == "photo_report":  # ph:<event>, to those who came, once: the guests' album filled up
        e = one(con, "SELECT id, title, i18n FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[1]))
        n = one(con, "SELECT COUNT(*) FROM event_photos WHERE event_id = ?", int(ref[1]))[0]
        return (*texts.bot_message(lang, kind, title=logic.title_in(e, lang), n=n), f"ph_{e['id']}") if e and n else None
    if kind == "photo_call":  # ph2:<event>, admin photo-call: those who came, once; quiet once guests can't add (closed, a week on)
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[1]))
        return (*texts.bot_message(lang, kind, title=logic.title_in(e, lang)), f"ph_{e['id']}") if e and logic.now() <= logic.end_of(e) + logic.ALBUM_FOR else None
    if kind == "u18_leave":  # u18:<event>:<round>; a corrected age or undone check-in makes it stale
        e = one(con, """SELECT e.* FROM events e JOIN registrations r ON r.event_id = e.id
            JOIN reg_age a ON a.registration_id = r.id WHERE e.id = ? AND e.age_check = 1 AND e.status = 'published'
            AND e.hidden_at IS NULL AND r.user_id = ? AND r.status = 'going' AND r.checked_in_at IS NOT NULL AND a.adult = 0""",
                int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, kind), f"ev_{e['id']}") if e and now() < logic.end_of(e) and not logic.door_shut(e, now()) else None
    if kind in ("comment_question", "comment_answer"):  # cq:<event>:<hour> to the club's Head+ · ca:<event>:<answer> to askers
        e = one(con, "SELECT e.id, e.title, e.i18n, o.name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.hidden_at IS NULL",
                int(ref[1]))
        if not e or not reminders():
            return None
        if kind == "comment_question" and not logic._asking(con, e["id"], m["user_id"]):  # answered or read before the card went out
            return None
        if kind == "comment_answer" and not one(con, "SELECT 1 FROM comments WHERE id = ? AND deleted_at IS NULL", int(ref[2])):
            return None
        return (*texts.bot_message(lang, kind, title=logic.title_in(e, lang), org=e["name"]), f"cm_{e['id']}")
    if kind == "comment_reply":  # cr:<post|event>:<id>:<hour>, to whoever was answered; follows the reminders switch
        if ref[1] == "event":
            x = one(con, "SELECT title, i18n FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[2]))
        else:
            x = one(con, "SELECT title, i18n FROM posts WHERE id = ? AND hidden_at IS NULL", int(ref[2]))
        if not x or not reminders():
            return None
        return (*texts.bot_message(lang, kind, title=logic.title_in(x, lang)), f"{'cm' if ref[1] == 'event' else 'cp'}_{ref[2]}")
    if kind in ("volunteer_yes", "volunteer_no"):  # vo:<event>:<when>; quiet if the decision changed since or the event is over
        e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.starts_at > ?",
                int(ref[1]), logic.now())
        x = e and one(con, "SELECT status FROM volunteers WHERE event_id = ? AND user_id = ?", e["id"], m["user_id"])
        if not x or x["status"] != kind.split("_")[1]:
            return None
        return (*texts.bot_message(lang, kind, org=e["org_name"], **ev(e)), f"ev_{e['id']}")
    if kind == "team_left":  # tl:<event>:<team>:<when>, evteams.left: to its captain while the team stands and the event hasn't started
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL AND starts_at > ?", int(ref[1]), logic.now())
        if not e or not one(con, "SELECT 1 FROM event_team_members WHERE team_id = ? AND user_id = ?", int(ref[2]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, **ev(e)), f"ev_{e['id']}")
    if kind == "team_consent":  # tc:<event>[:<when>], evteams.consent_ask / remind; quiet once agreed, out of the event, or it started
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL AND starts_at > ? AND team_max IS NOT NULL", int(ref[1]), logic.now())
        if not e or one(con, "SELECT 1 FROM team_consents WHERE user_id = ?", m["user_id"]) or not one(  # agreed, or withdrew it: never asked
                con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')", e["id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, **ev(e)), f"tc_{e['id']}")
    if kind in ("team_placed", "team_removed", "team_missed"):  # tp:<event>:<team> / tr: / tm:<event>:<when>, evteams.py; quiet once it started or changed since
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL AND starts_at > ?", int(ref[1]), logic.now())
        x = e and one(con, "SELECT team_id FROM event_team_members WHERE event_id = ? AND user_id = ?", e["id"], m["user_id"])
        if kind == "team_missed" and not (e and e["team_max"] is not None and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", e["id"], m["user_id"])):
            return None  # "your ticket is yours" only while it is
        if not e or kind == "team_placed" and not (x and x[0] == int(ref[2])) or kind != "team_placed" and x:
            return None
        return (*texts.bot_message(lang, kind, **ev(e)), f"ev_{e['id']}")
    if kind in ("leaders_invite", "meeting_invite"):  # li: / mi:<event>, to everyone invited; quiet once they've answered or it's over
        e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.starts_at > ?",
                int(ref[1]), logic.now())
        if not e or one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, org=e["org_name"], **ev(e)), f"ev_{e['id']}")
    if kind == "friend_invite":  # fi:<event>:<inviter>; gone if the event is off or has started, or they're in already
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND starts_at > ?", int(ref[1]), logic.now())
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not e or not p or one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')",
                                 e["id"], m["user_id"]) or not logic.seats.sees_school(con, m["user_id"], e):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p), **ev(e)), f"ev_{e['id']}")
    if kind == "round_open":  # ro:<round>, to a club's followers who aren't in it; gone once it stops taking applications
        r = one(con, "SELECT r.*, o.name FROM rounds r JOIN orgs o ON o.id = r.org_id AND o.status = 'active' WHERE r.id = ? AND r.status = 'open' AND r.closes_at > ?", int(ref[1]), logic.now())
        if not r or one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", r["org_id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, org=r["name"], until=texts.when(r["closes_at"], lang)), f"rc_{r['org_id']}")
    if kind in ("round_interview", "round_iv_nudge", "round_iv_remind"):  # iv: / ivn: / ivr:<application>[:<slot>:<when>]
        a = one(con, """SELECT a.*, r.org_id, r.status AS rstatus, o.name FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id AND o.status = 'active' WHERE a.id = ?""", int(ref[1]))
        if not a or a["stage"] == "withdrawn" or a["rstatus"] == "done" or a["sent_at"]:  # their result went out
            return None
        if kind == "round_iv_nudge" and a["slot_id"]:  # picked a time already
            return None
        if kind == "round_iv_remind":
            s = one(con, "SELECT * FROM round_slots WHERE id = ?", a["slot_id"]) if a["slot_id"] == int(ref[2]) else None
            if not s:
                return None
            return (*texts.bot_message(lang, kind, org=a["name"], when=texts.when(s["starts_at"], lang), place=texts.place_or_tba(s["place"], lang)),
                    f"iv_{a['org_id']}")
        return (*texts.bot_message(lang, kind, org=a["name"]), f"iv_{a['org_id']}")
    if kind == "round_place":  # ivp:<application>:<slot>:<n>, casting.set_place: that slot as it is now; quiet once decided, over, booked elsewhere, full or edited back
        a = one(con, """SELECT a.*, r.org_id, r.status AS rstatus, o.name FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id AND o.status = 'active' WHERE a.id = ?""", int(ref[1]))
        s = a and a["stage"] == "next" and a["rstatus"] != "done" and not a["sent_at"] and casting.place_slot(con, a, int(ref[2]))
        if not s or s["place"] == json.loads(m["payload"] or "{}").get("was"):
            return None
        return (*texts.bot_message(lang, kind, org=a["name"], when=texts.when_span(s["starts_at"], s["ends"], lang),
                                   place=texts.place_or_tba(s["place"], lang)), f"iv_{a['org_id']}")
    if kind == "round_call":  # ivc:<application>:<slot>:<start>, casting.call_slot: "come over" while the window is on; quiet once decided, came or over
        a = one(con, """SELECT a.*, r.org_id, r.status AS rstatus, o.name FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id AND o.status = 'active' WHERE a.id = ?""", int(ref[1]))
        s = a and a["rstatus"] != "done" and one(con, f"""SELECT s.*, {casting._ENDS} AS ends, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide
            FROM round_slots s WHERE s.id = ? AND s.round_id = ? AND s.starts_at = ?""", int(ref[2]), a["round_id"], int(ref[3]))
        if not casting.call_holds(a, s):
            return None
        return (*texts.bot_message(lang, kind, org=a["name"], when=texts.when_span(s["starts_at"], s["ends"], lang),
                                   place=texts.place_or_tba(s["place"], lang)), f"iv_{a['org_id']}")
    if kind in ("round_yes", "round_no"):  # ry: / rn:<application>, the results, to each applicant
        a = one(con, """SELECT a.*, r.org_id, r.decline_text, r.group_link, o.name, t.name AS dept FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id AND o.status = 'active' LEFT JOIN org_tags t ON t.id = a.taken_tag WHERE a.id = ?""", int(ref[1]))
        if not a:
            return None
        if kind == "round_yes":
            # the club's group: its invite waits in the app (the club's sheet), the bot only says so (AGENTS.md: templates only)
            key = kind + ("_dept" if a["dept"] else "") + ("_group" if a["group_link"] else "")
            return (*texts.bot_message(lang, key, org=a["name"], dept=a["dept"] or ""), f"cl_{a['org_id']}")
        if a["decline_text"]:  # the club's own words are in the app, never in the bot's message (AGENTS.md: templates only)
            return (*texts.bot_message(lang, "round_no_why", org=a["name"]), f"iv_{a['org_id']}")
        return (*texts.bot_message(lang, kind, org=a["name"]), "clubs")
    if kind == "usage_week":  # retired (owner, Nov 23): a row still queued from before goes nowhere
        return None
    if kind == "memo_ready":  # memo:<org>:<monday>, to whoever has "memo"; gone if nothing asks DMP any more or it's sent
        o = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1]))
        n = one(con, """SELECT COUNT(*) FROM events WHERE org_id = ? AND status IN ('draft', 'published') AND memo IS NOT NULL
            AND memo_sent_at IS NULL AND starts_at >= ? AND starts_at < ?""", int(ref[1]), int(ref[2]), int(ref[2]) + 7 * 86400)[0]
        return (*texts.bot_message(lang, kind, org=o["name"], n=n), f"memo_{ref[1]}") if o and n else None
    if kind == "saved_tomorrow":  # sv:<day>: my saved events tomorrow I'm not going to (gone if I signed up meanwhile)
        day = int(ref[1])
        evs = rows(con, """SELECT e.id, e.title, e.i18n, e.starts_at FROM saved_events s JOIN events e ON e.id = s.event_id WHERE s.user_id = ?
            AND e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ? AND NOT EXISTS (SELECT 1 FROM registrations r
            WHERE r.event_id = e.id AND r.user_id = s.user_id AND r.status IN ('going', 'hold', 'waitlist')) ORDER BY e.starts_at""",
                   m["user_id"], (day + 1) * 86400 - 5 * 3600, (day + 2) * 86400 - 5 * 3600)
        return listed(evs) if evs else None
    if kind == "place_tba":  # tba:<day>, to an event's maker: all their coming events still without a place
        evs = rows(con, "SELECT id, title, i18n, starts_at FROM events WHERE created_by = ? AND status = 'published' AND place = '' AND starts_at > ? ORDER BY starts_at",
                   m["user_id"], logic.now())
        return listed(evs) if evs else None
    if kind == "friend_new":  # fn:<the other one>:<day>; gone if they're no longer friends by then
        other = int(ref[1])
        p = one(con, logic.PERSON + " WHERE u.id = ?", other)
        if not p or not one(con, "SELECT 1 FROM friendships WHERE a = ? AND b = ?", min(other, m["user_id"]), max(other, m["user_id"])):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p)), f"u_{other}")
    if kind == "probation_passed":  # pp:<org>:<day>, to the person, while they're still in the club
        o = one(con, "SELECT o.name FROM orgs o JOIN org_members mm ON mm.org_id = o.id AND mm.user_id = ? WHERE o.id = ?", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, org=o["name"]), f"cl_{ref[1]}") if o else None
    if kind == "removal_ask":  # rm:<request>, to each President/Vice who outranks the person; gone once decided
        q = one(con, "SELECT q.*, o.name AS org FROM removal_requests q JOIN orgs o ON o.id = q.org_id WHERE q.id = ? AND q.status = 'pending'", int(ref[1]))
        if not q or m["user_id"] not in logic.teams.removal_leaders(con, q["org_id"], q["user_id"], q["by_id"]):
            return None
        p = one(con, logic.PERSON + " WHERE u.id = ?", q["user_id"])
        if not p:
            return None
        b = one(con, logic.PERSON + " WHERE u.id = ?", q["by_id"])
        return (*texts.bot_message(lang, kind, by=logic.short_name(b) if b else "?", name=logic.short_name(p), org=q["org"],
                                   ban=texts.pick(texts.BAN, lang) if q["ban"] else ""), f"tm_{q['org_id']}")
    if kind in SANTA_KINDS:
        return _santa(con, m, lang)
    if kind == "credit_ask":  # cra, kbtu.admin credit ask: "shall we name you?", once; quiet once answered or nothing shipped is theirs
        return (*texts.bot_message(lang, kind), "people") if logic.credits.asking(con, m["user_id"]) else None  # (send_due reads where to again)
    if kind == "santa_news":  # sn:<org>, to its President or Vice (kbtu.admin santa-news), opens the Santa welcome over Studio: quiet once they aren't
        o = one(con, """SELECT o.name FROM orgs o JOIN org_members mm ON mm.org_id = o.id AND mm.user_id = ? AND mm.role IN ('president', 'vice')
            WHERE o.id = ? AND o.status = 'active'""", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, org=o["name"]), f"sn_{ref[1]}") if o else None
    if kind == "crew_added":  # cw:<event>, to the helper (logic/crew.py): quiet once the right is gone or the event over
        e = one(con, """SELECT e.*, o.name AS org FROM event_crew c JOIN events e ON e.id = c.event_id JOIN orgs o ON o.id = c.org_id
            WHERE c.event_id = ? AND c.user_id = ? AND e.status = 'published' AND e.hidden_at IS NULL AND e.visibility = 'public'
            AND COALESCE(e.ends_at, e.starts_at + ?) > ? AND o.status = 'active' AND (c.org_id = e.org_id OR EXISTS (SELECT 1 FROM event_cohosts x
            WHERE x.event_id = e.id AND x.org_id = c.org_id AND x.status = 'accepted'))""", int(ref[1]), m["user_id"], logic.NO_END, logic.now())
        return (*texts.bot_message(lang, kind, org=e["org"], **ev(e)), f"ev_{e['id']}") if e else None
    if kind.startswith("cohost_"):  # ch: / chd: / che:<event>:<club> (logic/cohosts.py): quiet once what it says is no longer so
        e = one(con, """SELECT e.*, h.name AS host, c.name AS org, x.status AS co FROM events e JOIN orgs h ON h.id = e.org_id JOIN orgs c ON c.id = ?
            LEFT JOIN event_cohosts x ON x.event_id = e.id AND x.org_id = c.id WHERE e.id = ? AND e.status != 'cancelled' AND e.hidden_at IS NULL
            AND h.status = 'active' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""", int(ref[2]), int(ref[1]), logic.NO_END, logic.now())
        want = {"cohost_invite": "pending", "cohost_yes": "accepted", "cohost_no": "declined", "cohost_changed": "accepted"}.get(kind)
        if not e or (e["co"] != want if want else e["co"] == "accepted"):
            return None
        # the invite opens our Studio (its To do answers it); the rest open the event
        return (*texts.bot_message(lang, kind, host=e["host"], org=e["org"], **ev(e)), f"st_{ref[2]}" if kind == "cohost_invite" else f"ev_{e['id']}")
    e = one(con, "SELECT e.*, o.name AS org_name, o.status AS org_status FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ?", int(ref[1]))
    # a moderator's take-down (hidden_at) or the admin's hidden club: nobody can open it, so nobody hears of it (a cancel still goes)
    if not e or (kind != "event_cancelled" and (e["status"] != "published" or e["hidden_at"] or e["org_status"] == "hidden")):
        return None
    if not logic.seats.sees_school(con, m["user_id"], e):  # a school's own event: only to whom it shows (its signed-up keep theirs)
        return None
    if e["visibility"] != "public" and kind in ("remind_2h", "seat_free", "going_ok", "door_open"):  # a club's own event has no ticket
        kind += "_team"
    if kind.startswith("door_open") and (not one(con, "SELECT n_door FROM users WHERE id = ?", m["user_id"])[0] or not one(
            con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going' AND checked_in_at IS NULL", e["id"], m["user_id"])):
        return None
    co = one(con, "SELECT o.name FROM event_cohosts x JOIN orgs o ON o.id = x.org_id WHERE x.event_id = ? AND x.status = 'accepted' AND o.status = 'active'",
             e["id"]) if kind == "new_event" else None  # a co-hosted event names both clubs
    # queued for a co-host's follower (payload co): quiet once that club no longer co-hosts it
    via = json.loads(m["payload"] or "{}").get("co") if kind == "new_event" else None
    if via and not one(con, """SELECT 1 FROM event_cohosts x JOIN orgs o ON o.id = x.org_id
            WHERE x.event_id = ? AND x.org_id = ? AND x.status = 'accepted' AND o.status = 'active'""", e["id"], via):
        return None
    # Use the generic template if the payload has no recognized rejection reason.
    why = texts.pick(texts.REJECT_WHY, lang).get(json.loads(m["payload"] or "{}").get("why")) if kind == "receipt_rejected" else None
    if why:
        kind = "receipt_rejected_why"
    text, button = texts.bot_message(lang, kind, org=e["org_name"] + (f" × {co[0]}" if co else ""), why=why or "", **ev(e))
    return text, button, f"{'tk' if kind in ('remind_2h', 'seat_free', 'going_ok', 'door_open') else 'ev'}_{e['id']}"


SANTA_KINDS = frozenset({"santa_open", "santa_soon", "santa_nudge", "santa_drawn", "santa_changed", "santa_wish", "santa_two", "santa_alone", "santa_eve",
                         "santa_few", "santa_wait", "santa_late", "santa_msg", "santa_reply"})


def _santa(con, m, lang: str) -> tuple[str, str | None, str] | None:
    """Secret Santa's templates (logic/santa.py): each read when it goes, quiet once it no longer holds (joined since,
    left the club or the game, drawn, the deadline or the ring moved). Never a name, a wishlist or a pair. Refs:
    so:/sr:<org>:<event> (the invite, the organizer's reminder), else <prefix>:<event>[:...]."""
    kind, ref, uid, t = m["kind"], m["ref"].split(":"), m["user_id"], logic.now()
    eid = int(ref[2]) if ref[0] in ("so", "sr") else int(ref[1])
    e = one(con, """SELECT e.*, o.name AS org, s.drawn_at, g.budget FROM events e JOIN orgs o ON o.id = e.org_id AND o.status = 'active'
        JOIN santa_events s ON s.event_id = e.id LEFT JOIN santa_games g ON g.event_id = e.id
        WHERE e.id = ? AND e.status = 'published' AND e.hidden_at IS NULL""", eid)
    chat = kind in ("santa_msg", "santa_reply")  # the chat outlives the gifts day
    if not e or not chat and (e["starts_at"] <= t) != (kind == "santa_late"):  # only "the gifts day came undrawn" speaks of a day begun
        return None
    playing = one(con, logic.santa._GOING + " AND p.user_id = ?", e["id"], uid)
    title, go = logic.title_in(e, lang), f"ev_{e['id']}"
    if kind in ("santa_open", "santa_soon", "santa_nudge"):  # to the club's people the game is for, not in yet, while wishlists are taken
        if e["drawn_at"] or playing or (e["reg_until"] or t + 1) <= t or not logic.santa._for(con, e, uid):
            return None
        soon = kind == "santa_soon"
        return (*texts.bot_message(lang, kind, org=e["org"], until=texts.when(e["reg_until"], lang) if e["reg_until"] else "",
                                   terms=texts.santa_terms(lang, e["budget"], None if soon else e["reg_until"])), go)
    if kind in ("santa_few", "santa_wait", "santa_late"):  # to its President and Vices: the game waits for them
        if e["drawn_at"] or uid not in logic.santa._heads(con, e) or kind == "santa_few" and e["reg_until"] != int(ref[2]):
            return None
        return (*texts.bot_message(lang, kind, title=title, n=len(rows(con, logic.santa._IN, e["id"]))), f"mg_{e['id']}")
    if not e["drawn_at"] or not playing:  # the rest go to those playing a drawn game
        return None
    ring = one(con, "SELECT COUNT(*) FROM santa_people WHERE event_id = ?", e["id"])[0]
    if kind == "santa_two" and ring != 2 or kind == "santa_alone" and ring != 1:
        return None  # the ring changed again since: a newer message says how it stands
    if kind in ("santa_changed", "santa_eve", "santa_wish") and not one(con, "SELECT 1 FROM santa_people WHERE event_id = ? AND user_id = ? AND gives_to != user_id", e["id"], uid):
        return None  # everyone else left: no person to give to (santa_alone says so)
    if kind == "santa_eve" and len(ref) > 2 and int(ref[2]) != e["starts_at"]:
        return None  # the gifts day moved since: the new eve has its own message
    if chat and not logic.santa.pushable(con, e["id"], uid, kind):
        return None  # no chat for them any more (retired, over, out of the club) or the thread shut; never its words, only that there are some
    where = f"\n📍 {e['place']}" if e["place"] else ""  # a Santa game: never online
    return (*texts.bot_message(lang, kind, title=title, when=texts.when(e["starts_at"], lang), where=where), go)


def purge(cfg: Config, con) -> None:
    """The accounts whose week ran out (logic.delete_due), and their files on disk (app.py keeps them in the same places)."""
    home = Path(cfg.db_path).resolve().parent
    receipts, photos = logic.delete_due(con)
    media.drop(home / "receipts", receipts)  # first: a failing step below mustn't leave the deleted accounts' receipts on disk
    photos = photos + logic.purge_takedowns(con)  # and what a moderator took down 30 days ago
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
        r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/getChat", json={"chat_id": chat["id"]})).json()
        invite = (r.get("result") or {}).get("invite_link") if r.get("ok") else None
    except (httpx.HTTPError, ValueError) as exc:  # matched by its @name then
        log.warning("bot added: %s", type(exc).__name__)
    who = int((upd.get("from") or {}).get("id") or 0)  # the action's performer (Telegram's `from`)
    if cid := logic.pick_claim(con, who, chat, invite) or logic.bot_added(con, who, chat, invite):  # Studio's picker first
        await chat_card(cfg, http, con, cid, chat["id"])
    else:  # no club's yet: his to link from Studio → Chats for ten minutes
        logic.bot_admin(con, who, chat, invite)


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
    global _backup_retry
    local = int(time.time()) + 5 * 3600
    day = str(local // 86400)
    if local % 86400 < 4 * 3600 or time.time() < _backup_retry or one(con, "SELECT 1 FROM meta WHERE key = 'backup_day' AND value = ?", day):
        return
    root = db_path.parent / "backups"
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
    for old in root.glob("kbtu-*.db"):  # by age too: skipped nights mustn't stretch a deleted account's life past 30 days
        if old.stat().st_mtime < time.time() - 15 * 86400:
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
    casting.forget(con)   # daily: answers and notes of rounds whose results went out 60 days ago
    purge(cfg, con)       # accounts whose week to change their mind ran out
    logic.ms_sweep(con)   # unfinished Microsoft sign-ins after a week, used-link marks after a day
    backup_day(cfg, con)  # a nightly copy of the database, 14 kept
    optimize_day(con)     # the query planner's statistics, once a night
    userbot_round(con)    # the owner hears when the channels' userbot goes quiet, and when it's back
    logic.close_gone(con)  # reports of what went by itself (the queue, a GET, never writes)
    logic.tgcomments.sweep(con)  # the policy's retention even with the forum switched off (its old rows still go)
    logic.fchannel.sweep(con)


def _due(con) -> list:
    # the partial index outbox_todo (migration 109), named: else the planner picks outbox_due, which walks every failed row
    # pushable: this person's notifications go to the app (push.py): a live token, and the app picked in Settings (or
    # no Telegram to write to)
    t = now()
    return rows(con, f"""SELECT b.*, u.tg_id, u.lang, u.can_dm, u.banned_at,
        {push.LIVE.format("b.user_id")} AND (u.notify_via = 'app' OR u.can_dm = 0) AS pushable
        FROM bot_outbox b INDEXED BY outbox_todo JOIN users u ON u.id = b.user_id
        WHERE b.sent_at IS NULL AND b.error IS NULL AND b.send_after <= ? ORDER BY b.send_after, b.id LIMIT 50""",
                *push.bounds(t), t)


def _pushes(cfg: Config, m, start) -> bool:
    """This message goes to the app instead of Telegram (push.py): a template with one way into the app (never a
    keyboard of votes or links, a forum comment's edits, or the credits' ask, which follow Telegram's own account)."""
    return push.on(cfg) and bool(m["pushable"]) and isinstance(start, str) and not m["kind"].startswith("tgc_") \
        and m["kind"] not in ("fch_comments", "credit_ask")


def _mark(con, m, sent: bool, error: str | None = None) -> None:
    # Deleting a post or account can retire this row while Telegram answers. SQLite can reuse its numeric id.
    con.execute("UPDATE bot_outbox SET sent_at = ?, error = ? WHERE id = ? AND user_id = ? AND kind = ? AND ref = ?",
                (now() if sent else None, error, m["id"], m["user_id"], m["kind"], m["ref"]))


def _take(con, m, forum_channel: bool, pushable: bool = False):
    """One queued message taken and rendered, or None (the other postman has it, or it can't go: marked why).
    pushable: the app may get it (push.on and a live device), so no Telegram is no reason to drop it yet."""
    # take it first: during a deploy the old and the new container run side by side for a few seconds, and
    # both postmen see the same queue; whoever moves send_after on gets the message (back after LEASE if lost)
    lease = logic.fchannel.COMMENT_GAP if m["kind"] == "fch_comments" else LEASE  # Telegram may receive a send whose answer is lost
    if not con.execute("""UPDATE bot_outbox SET send_after = ? WHERE id = ? AND user_id = ? AND kind = ? AND ref = ?
                       AND send_after = ? AND sent_at IS NULL AND error IS NULL""",
                       (now() + lease, m["id"], m["user_id"], m["kind"], m["ref"], m["send_after"])).rowcount:
        return None
    if not m["can_dm"] and not pushable:
        return _mark(con, m, False, "no_dm")
    if m["banned_at"]:  # banned: the bot stops writing
        return _mark(con, m, False, "banned")
    if (category := notifications.CATEGORY_OF.get(m["kind"])) and not notifications.allowed(con, category, m["user_id"], m["tg_id"]):
        return _mark(con, m, False, "gone")
    if m["kind"] == "fch_comments" and not forum_channel:
        return _mark(con, m, False, "gone")
    msg = _render(con, m)
    if msg is None:
        _mark(con, m, False, "gone")
    return msg


def _pushed(con, m) -> None:
    """Delivered to the iPhone app: sent, as a Telegram message would be."""
    with db.tx(con):
        _mark(con, m, True)
        if category := notifications.CATEGORY_OF.get(m["kind"]):
            notifications.delivered(con, category, now())


def _answered(con, m, status: int, answer: dict) -> None:
    if answer.get("ok"):
        if category := notifications.CATEGORY_OF.get(m["kind"]):
            with db.tx(con):
                _mark(con, m, True)
                result = answer.get("result")
                sent_at = (result.get("date") if isinstance(result, dict) else None) or now()
                notifications.delivered(con, category, sent_at)
        else:
            _mark(con, m, True)
        tgc.sent(con, m, answer)
    elif status == 403:  # blocked the bot or never started it
        con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (m["user_id"],))
        _mark(con, m, False, "blocked")
    else:
        _mark(con, m, False, str(answer.get("description", status))[:200])




async def send_due(cfg: Config, http: httpx.AsyncClient) -> None:
    con = db.connect(cfg.db_path)  # one connection, used by one thread at a time (check_same_thread=False)
    try:
        await anyio.to_thread.run_sync(_chores, cfg, con)
        offsite_round(cfg, con)  # and that copy, encrypted, to R2 (Sundays the media too); reads, a write an hour at most
        await post_channel(cfg, http, con)  # public events to @KBTUevents, edits and cancels too
        await tgc.tick(cfg, http, con)  # the forum channel's comments: strangers' texts after the hour, deletions, unbans
        await tgc.post_tick(cfg, http, con)  # the forum channel's posts: taken down, then the new ones published
        await _userpics(cfg, http, con)  # Telegram photos copied to /media: t.me takes ~1 s on every open
        if await anyio.to_thread.run_sync(logic._once, con, "chats_day", str(now() // 86400)):
            await refresh_chats(cfg, http, con)  # daily: the chats' avatars and members from their t.me pages
        for m in await anyio.to_thread.run_sync(_due, con):
            if _stopping():  # between messages: one taken and cut mid-send would go again after its LEASE, maybe twice
                return
            msg = await anyio.to_thread.run_sync(_take, con, m, bool(cfg.forum_channel), push.on(cfg) and bool(m["pushable"]))
            if msg is None:
                continue
            text, button, start = msg
            # one channel per person (push.py): the app's push when it took it, else at once Telegram's (if the bot may write)
            if _pushes(cfg, m, start) and await push.deliver(cfg, con, m["user_id"], text, start, now()):
                await anyio.to_thread.run_sync(_pushed, con, m)
                continue
            if not m["can_dm"]:
                await anyio.to_thread.run_sync(_mark, con, m, False, "no_dm")
                continue
            to = m["tg_id"]
            if m["kind"] == "credit_ask":  # the account may have moved since the queue was read: to its Telegram of now, or not at all
                to = logic.credits.asking(con, m["user_id"])
                if to is None:
                    _mark(con, m, False, "gone")
                    continue
            body = {"chat_id": to, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
            if isinstance(start, list):  # the whole keyboard; "start" buttons open the app there
                body["reply_markup"] = {"inline_keyboard": [[{"text": b["text"], "url": f"https://t.me/{cfg.bot_username}?startapp={b['start']}"}
                                                             if "start" in b else b for b in row] for row in start]}
            elif button:
                body["reply_markup"] = {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}
            if category := notifications.CATEGORY_OF.get(m["kind"]):
                # The settings may have changed while the worker rendered the card.
                if not notifications.allowed(con, category, m["user_id"], to):
                    _mark(con, m, False, "gone")
                    continue
                if m["kind"] in MUTE_ROW:
                    body.setdefault("reply_markup", {"inline_keyboard": []})["inline_keyboard"].append(
                        _feedback_buttons(cfg, to, m["lang"], category))
            try:
                r = await tgc.edit_first(cfg, http, con, m, body)  # a comment's verdict: its first message edited
                if r is None:
                    r = await _send(cfg, http, body)
                answer = r.json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("postman: %s", type(exc).__name__)
                return  # the network is down: everything stays queued for the next round
            if not answer.get("ok") and r.status_code == 429:  # too fast: wait as told, this one goes again next round
                await asyncio.sleep(float(answer.get("parameters", {}).get("retry_after", 5)))
                return
            await anyio.to_thread.run_sync(_answered, con, m, r.status_code, answer)
            await asyncio.sleep(GAP)
    finally:
        con.close()


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


def _student(con, tg_id: int | None) -> sqlite3.Row | None:
    """Who writes to the bot, if a student signed in with KBTU (a typed-in row waiting for Microsoft is nobody yet)."""
    return one(con, """SELECT u.id, u.role, u.lang, s.first_name, s.last_name, s.first_lat, s.last_lat FROM users u
        JOIN students s ON s.user_id = u.id AND s.manual = 0 WHERE u.tg_id = ?""", tg_id)


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
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/answerCallbackQuery", json={"callback_query_id": cq["id"]})
    msg, data = cq.get("message") or {}, str(cq.get("data") or "")
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
    if f := re.fullmatch(r"(ct|ps):(\d+)(?::([0-9a-f]{8}))?(?::([yn]))?|an:([yn])", data):
        u = one(con, "SELECT id, lang FROM users WHERE tg_id = ?", (cq.get("from") or {}).get("id"))
        if not u or not msg:
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
        me = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/getChatMember", json={"chat_id": chat["id"], "user_id": sender})).json()
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
    api, sender = f"https://api.telegram.org/bot{cfg.bot_token}", int((msg.get("from") or {}).get("id") or 0)
    # only the group's own admin links it (whoever added the bot as an admin is one): a member can't hand it to an event
    me = (await http.post(f"{api}/getChatMember", json={"chat_id": chat["id"], "user_id": sender})).json()
    admin = me.get("ok") and (me.get("result") or {}).get("status") in ("creator", "administrator")
    e = logic.chat_claim(con, words[1][3:], sender, chat["id"]) if admin else None
    if not e:
        await _send(cfg, http, {"chat_id": chat["id"], "text": texts.CHAT_BAD, "parse_mode": "HTML"})
        return
    r = (await http.post(f"{api}/createChatInviteLink", json={"chat_id": chat["id"], "name": e["title"][:32], "creates_join_request": True})).json()
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
        if sent and not sent.get("ok") and _custom_re:  # the pack's emoji refused inside a mention: the plain ones
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


_video_seen: set[int] = set()  # unconfirmed update IDs can appear both in a peek and in the next poll
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
    good = logic.stars.checkout_ok(q)
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
                        await asyncio.to_thread(logic.stars.paid, con, payment, (msg.get("from") or {}).get("id"))
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
