"""The postman (SPEC §7), inside the web app's event loop (app.py lifespan).

- Postman: sends what logic.notify() queued in bot_outbox, as server templates (texts.py) in the user's
  language with a button into the app; only to users who let the bot write (can_dm). A user who blocked
  the bot loses can_dm until Telegram says otherwise.
- Ears: whatever someone writes to the bot (/start first of all) is answered with what the app is and a button
  into it (/start said nothing); a receipt (Kaspi's PDF or a picture) goes to the sender's seat on hold.
Until Oct 7 it also refreshed schedules with each student's stored KBTU session; no session outlives a request
now (SPEC §4.1), the stored ones were ended, and migration 18 dropped their table."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import fcntl
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import anyio.to_thread
import httpx

from . import ai, casting, db, llm, logic, media, mirror, offsite, portal, receipt, texts, tgc, userbot, video
from .config import Config
from .logic import now, one, rows
from .logic.account import _Taken
from .logic.core import ApiError

log = logging.getLogger("kbtu.bot")

POLL = 2                    # seconds between outbox checks
GAP = 0.05                  # ≤ 20 messages a second (Telegram allows about 30)
AI_GAP = 10                 # seconds between translations (ai.py): a backlog drains without a burst
LEASE = 60                  # a taken message is free again after this, if its postman died or the network was down
WAIT = 25                   # getUpdates: Telegram holds the request this long while nobody writes
FRESH = 300                 # an older message isn't answered: what piled up while nobody listened (before Oct 7)


# Premium emoji (Bot API 9.4: a bot whose owner has Telegram Premium may send custom emoji): the pack the owner picked
# loaded once a postman starts; each plain emoji our texts use that the pack also has goes out animated, the
# rest stay plain. If Telegram ever refuses them (Premium ended), the message goes again plain and the pack is dropped.
# the packs, first wins (owner, Oct 18: NewsEmoji, made for bots; the older pack fills what it lacks; Oct 25: Telegram's own
# RestrictedEmoji, ~1000, last, only for what the others lack)
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
    return _custom_re.sub(lambda m: f'<tg-emoji emoji-id="{_custom[m.group(0).replace(chr(0xFE0F), "")]}">{m.group(0)}</tg-emoji>', text)


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
    ev = lambda e: {"title": logic.title_in(e, lang), "when": texts.when(e["starts_at"], lang), "place": texts.place_or_tba(e["place"], lang)}  # noqa: E731
    reminders = lambda: one(con, "SELECT n_remind FROM users WHERE id = ?", m["user_id"])[0]  # noqa: E731  (the switch for cards about events)

    def listed(evs):  # a line per event, the first one opened
        text, button = texts.bot_message(lang, kind, list="\n".join(f"• {logic.title_in(e, lang)}, {texts.when(e['starts_at'], lang)}" for e in evs))
        return text, button, f"ev_{evs[0]['id']}"
    if kind.startswith("tgc_"):  # the forum channel's comments (tgc.py)
        return tgc.render(con, m, lang)
    if kind in ("fch_reply_answer", "fch_reply_gone"):  # fa:<reply>:<hour> / fg:<reply>, to the post's author (through the post): its card
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
    if kind == "sid_check":  # sc:<student id>, to its holder: someone else typed it; quiet once they changed theirs
        held = one(con, "SELECT 1 FROM students WHERE user_id = ? AND student_id = ?", m["user_id"], ref[1])
        return (*texts.bot_message(lang, kind, sid=ref[1]), "me") if held else None
    if kind == "sid_free":  # sf:<student id>, parked for the one turned away; woken when it's freed (migration 127)
        free = not one(con, "SELECT 1 FROM students WHERE student_id = ?", ref[1])
        return (*texts.bot_message(lang, kind, sid=ref[1]), "me") if free else None
    if kind == "id_clash":  # old rows only (Nov 4: the holder is asked now; they expire in 30 days)  # ic:<student id>:<new>:<holder>, to the admins: both people's names, emails and Telegram
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
        text, button = texts.bot_message(lang, kind, skill=sk["name"] if sk else "")  # another's words: behind the button only
        return text, None, [[{"text": button, "start": f"fa_{a['id']}"}], [{"text": texts.bot_message(lang, "ask_stop")[0], "callback_data": "ps:0"}]]
    if kind == "contact_ask":  # ct:<contact>: someone offers help or wants to get in touch; Accept shares both contacts
        c = one(con, "SELECT * FROM contacts WHERE id = ? AND status = 'pending'", int(ref[1]))
        p = c and one(con, logic.PERSON + " WHERE u.id = ?", c["from_id"])
        if not p:
            return None
        a = one(con, "SELECT title FROM asks WHERE id = ?", c["ask_id"]) if c["ask_id"] else None
        skills = ", ".join(s["name"] for s in rows(con, "SELECT s.name FROM user_skills k JOIN skills s ON s.id = k.skill_id WHERE k.user_id = ? ORDER BY s.name", p["id"]))
        text = texts.bot_message(lang, "contact_ask" if a else "contact_ask_plain", name=logic.short_name(p), title=a["title"] if a else "", skills=skills or "\u2014")[0]
        yes, no = texts.bot_message(lang, "contact_buttons")
        return text, None, [[{"text": yes, "callback_data": f"ct:{c['id']}:y"}, {"text": no, "callback_data": f"ct:{c['id']}:n"}]]
    if kind == "elective3":  # elective3:2016: the incubator's post in short, its link, and more like it? Yes/No (_tapped, an:)
        (text, post), (yes, no) = texts.bot_message(lang, "elective3_gist"), texts.bot_message(lang, "announce_buttons")
        return text, None, [[{"text": post, "url": f"https://t.me/{ELECTIVE[0][1:]}/{ELECTIVE[1]}"}],
                            [{"text": yes, "callback_data": "an:y"}, {"text": no, "callback_data": "an:n"}]]
    if kind == "contact_ok":  # co:<contact>:to|from: accepted; each side gets the other's Telegram
        c = one(con, "SELECT * FROM contacts WHERE id = ? AND status = 'accepted'", int(ref[1]))
        other = c and (c["to_id"] if ref[2] == "to" else c["from_id"])
        p = other and one(con, logic.PERSON + " WHERE u.id = ?", other)
        if not p:
            return None
        text, button = texts.bot_message(lang, kind, name=logic.short_name(p))
        return text, None, [[{"text": button, "url": logic.telegram_of(con, other)}]]
    if kind == "ask_hidden":  # ah:<request>, to its author: why it's gone from the lists
        a = one(con, "SELECT title, why FROM asks WHERE id = ? AND status = 'hidden'", int(ref[1]))
        why = texts.pick(texts.ASK_WHY, lang).get(a["why"] or "") if a else None
        return (*texts.bot_message(lang, kind, title=a["title"], why=why), f"fa_{ref[1]}") if why else None
    if kind in ("backup_failed", "backup_ok", "userbot_off", "userbot_ok"):  # bf/bo:<day> to the admins; uo/ub:<since> to the owner
        return (*texts.bot_message(lang, kind), "")
    if kind in ("prefill_no_match", "prefill_other_id", "prefill_id_held"):  # pn/pf:<user>, ph:<user>:<holder>, to the owner (account.ms_link)
        return (*texts.bot_message(lang, kind, user=ref[1], holder=ref[-1]), "")
    if kind == "channel_ask":  # ca:<org>, to the club's President (admin channel-ask): gone once the club has its channel
        o = one(con, """SELECT o.name FROM orgs o JOIN org_members m ON m.org_id = o.id AND m.user_id = ? AND m.role = 'president'
            WHERE o.id = ? AND o.status = 'active'""", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"ce_{ref[1]}") if o and not mirror.has_channel(con, int(ref[1])) else None
    if kind == "delete_soon":  # del:<when>, to me; gone if I changed my mind
        at = one(con, "SELECT delete_at FROM users WHERE id = ?", m["user_id"])["delete_at"]
        return (*texts.bot_message(lang, kind, when=texts.when(at, lang).split(",")[0]), "me") if at else None
    if kind == "join_request":  # jr:<org>:<applicant>:<day>, to the club's Vice+; gone once withdrawn or answered
        o, p = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1])), one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not o or not p or not one(con, "SELECT 1 FROM join_requests WHERE org_id = ? AND user_id = ? AND status = 'pending'", int(ref[1]), int(ref[2])):
            return None
        return (*texts.bot_message(lang, kind, org=o["name"], name=logic.short_name(p)), f"jr_{ref[1]}")
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
    if kind == "friend_request":  # fq:<asker>:<day>; gone once answered or taken back
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[1]))
        if not p or not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", int(ref[1]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p)), "friends")
    if kind == "event_reported":  # er:<event>:<its oldest open report>, to moderators: 3 people reported it; quiet once decided or taken down
        r = one(con, "SELECT 1 FROM reports r JOIN events e ON e.id = r.target_id AND e.hidden_at IS NULL WHERE r.id = ? AND r.status = 'open'", int(ref[2]))
        return (*texts.bot_message(lang, kind), "capps") if r else None
    if kind == "chat_suggested":  # cs:<day>, to admins and moderators: once a day at most, while some still wait
        n = one(con, "SELECT COUNT(*) FROM chats WHERE status = 'pending'")[0]
        return (*texts.bot_message(lang, kind, n=n), "achats") if n else None
    if kind == "chat_approved":  # ca:<chat>, to each who suggested it, while it is still in the catalog: the Chats screen
        c = one(con, "SELECT title, kind, forum FROM chats WHERE id = ? AND status = 'live'", int(ref[1]))
        return (*texts.chat_approved(lang, "forum" if c["forum"] else c["kind"], c["title"]), "chats") if c else None
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
                                 e["id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p), **ev(e)), f"ev_{e['id']}")
    if kind == "round_open":  # ro:<round>, to a club's followers who aren't in it; gone once it stops taking applications
        r = one(con, "SELECT r.*, o.name FROM rounds r JOIN orgs o ON o.id = r.org_id WHERE r.id = ? AND r.status = 'open' AND r.closes_at > ?", int(ref[1]), logic.now())
        if not r or one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", r["org_id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, org=r["name"], until=texts.when(r["closes_at"], lang)), f"rc_{r['org_id']}")
    if kind in ("round_interview", "round_iv_nudge", "round_iv_remind"):  # iv: / ivn: / ivr:<application>[:<slot>:<when>]
        a = one(con, """SELECT a.*, r.org_id, r.status AS rstatus, o.name FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id WHERE a.id = ?""", int(ref[1]))
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
    if kind in ("round_yes", "round_no"):  # ry: / rn:<application>, the results, to each applicant
        a = one(con, """SELECT a.*, r.org_id, r.decline_text, r.group_link, o.name, t.name AS dept FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id LEFT JOIN org_tags t ON t.id = a.taken_tag WHERE a.id = ?""", int(ref[1]))
        if not a:
            return None
        if kind == "round_yes":
            # the club's group: its invite waits in the app (the club's sheet), the bot only says so (AGENTS.md: templates only)
            key = kind + ("_dept" if a["dept"] else "") + ("_group" if a["group_link"] else "")
            return (*texts.bot_message(lang, key, org=a["name"], dept=a["dept"] or ""), f"cl_{a['org_id']}")
        if a["decline_text"]:  # the club's own words are in the app, never in the bot's message (AGENTS.md: templates only)
            return (*texts.bot_message(lang, "round_no_why", org=a["name"]), f"iv_{a['org_id']}")
        return (*texts.bot_message(lang, kind, org=a["name"]), "clubs")
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
        p = one(con, logic.PERSON + " WHERE u.id = ?", q["user_id"]) if q else None
        if not q or not p:
            return None
        b = one(con, logic.PERSON + " WHERE u.id = ?", q["by_id"])
        return (*texts.bot_message(lang, kind, by=logic.short_name(b) if b else "?", name=logic.short_name(p), org=q["org"],
                                   ban=texts.pick(texts.BAN, lang) if q["ban"] else ""), f"tm_{q['org_id']}")
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
    if e["visibility"] != "public" and kind in ("remind_2h", "seat_free", "going_ok", "door_open"):  # a club's own event has no ticket
        kind += "_team"
    if kind.startswith("door_open") and (not reminders() or not one(  # reminders off, or cancelled or in since it was queued
            con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going' AND checked_in_at IS NULL", e["id"], m["user_id"])):
        return None
    co = one(con, "SELECT o.name FROM event_cohosts x JOIN orgs o ON o.id = x.org_id WHERE x.event_id = ? AND x.status = 'accepted' AND o.status = 'active'",
             e["id"]) if kind == "new_event" else None  # a co-hosted event names both clubs
    # queued for a co-host's follower (payload co): quiet once that club no longer co-hosts it
    via = json.loads(m["payload"] or "{}").get("co") if kind == "new_event" else None
    if via and not one(con, """SELECT 1 FROM event_cohosts x JOIN orgs o ON o.id = x.org_id
            WHERE x.event_id = ? AND x.org_id = ? AND x.status = 'accepted' AND o.status = 'active'""", e["id"], via):
        return None
    text, button = texts.bot_message(lang, kind, org=e["org_name"] + (f" × {co[0]}" if co else ""), **ev(e))
    return text, button, f"{'tk' if kind in ('remind_2h', 'seat_free', 'going_ok', 'door_open') else 'ev'}_{e['id']}"


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
    """A few users whose Telegram photo is new to us: saved under /media (tg_photo_path), the old copy dropped. A photo
    that fails is marked done all the same (tg_photo_src) and stays on t.me until Telegram gives a new URL."""
    root = Path(cfg.db_path).resolve().parent / "media"
    for u in logic.rows(con, """SELECT id, tg_photo_url, tg_photo_path FROM users WHERE tg_photo_url IS NOT NULL
            AND tg_photo_src IS NOT tg_photo_url LIMIT ?""", n):
        path = None
        try:
            r = await http.get(u["tg_photo_url"], follow_redirects=True, timeout=15)
            if r.status_code == 200:
                path = (await asyncio.to_thread(media.save, r.content, root))["path"]
        except (httpx.HTTPError, media.BadImage, OSError) as exc:
            log.warning("userpic: %s", type(exc).__name__)
        # only if the URL is still the one fetched: a newer photo meanwhile is the next round's
        if con.execute("UPDATE users SET tg_photo_path = ?, tg_photo_src = ? WHERE id = ? AND tg_photo_url = ?",
                       (path, u["tg_photo_url"], u["id"], u["tg_photo_url"])).rowcount:
            _drop_free(con, root, u["tg_photo_path"] if u["tg_photo_path"] != path else None)
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
    """Our bot added to a chat or taken out of it (my_chat_member). Added by someone who may edit a club's chats, to a
    chat on its page: the bot keeps that card from now on (a group added by Studio's link says which: its /start)."""
    chat, status = upd.get("chat") or {}, (upd.get("new_chat_member") or {}).get("status")
    if status in ("left", "kicked"):
        logic.bot_left(con, chat["id"])
        return
    if status not in ("member", "administrator") or chat.get("type") not in ("channel", "group", "supergroup"):
        return
    invite = None
    if status == "administrator":  # an admin bot is told the chat's primary invite link
        try:
            r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/getChat", json={"chat_id": chat["id"]})).json()
            invite = (r.get("result") or {}).get("invite_link") if r.get("ok") else None
        except (httpx.HTTPError, ValueError) as exc:  # matched by its name or title then
            log.warning("bot added: %s", type(exc).__name__)
    who = int((upd.get("from") or {}).get("id") or 0)
    # the picker only for a bot made admin: only a chat's admin can do that, a plain member adding us proves nothing
    # (Codex review, Nov 5: someone else's open group claimed); a later promotion comes as another update
    picked = status == "administrator" and logic.pick_claim(con, who, chat, invite)
    if cid := picked or logic.bot_added(con, who, chat, invite):  # Studio's picker first
        await chat_card(cfg, http, con, cid, chat["id"])


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
    """After 04:00 Almaty, once a day: a full copy of the database into backups/ beside it, the last 14 kept (there were none). It guards against a bad deploy or a wrong delete, not a lost disk: that needs a copy elsewhere."""
    db_path = Path(cfg.db_path).resolve()
    # the copies db.py makes before a migration: two weeks, as the nightly ones (H2: deleted accounts must not outlive them)
    for bak in db_path.parent.glob(f"{db_path.name}.v*.bak"):
        if bak.stat().st_mtime < time.time() - 14 * 86400:
            bak.unlink(missing_ok=True)
    local = int(time.time()) + 5 * 3600
    if local % 86400 < 4 * 3600 or not logic._once(con, "backup_day", str(local // 86400)):
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
        return
    tmp.replace(out)
    for old in sorted(root.glob("kbtu-*.db"))[:-14]:
        old.unlink()
    for old in root.glob("kbtu-*.db"):  # by age too: skipped nights mustn't stretch a deleted account's life past 30 days
        if old.stat().st_mtime < time.time() - 15 * 86400:
            old.unlink()
    log.warning("backup: %s, %d KB", out.name, out.stat().st_size // 1024)


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
    if not offsite.ready() or (_offsite and not _offsite.done()):
        return
    local = int(time.time()) + 5 * 3600
    if local % 86400 < 4 * 3600:
        return
    date, home = time.strftime("%Y-%m-%d", time.gmtime(local)), Path(cfg.db_path).resolve().parent
    stamp, done = time.strftime("%Y-%m-%d-%H%M", time.gmtime(local)), lambda key: one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, date)
    copy = home / "backups" / f"kbtu-{date}.db"
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
    logic.strip_emoji_names(con)  # once (meta): org names from before the no-emoji rule
    logic.memo_week(con)  # Wednesday morning: next week's memo for DMP is ready (each runs once, by its meta key)
    logic.tba_day(con)    # 10:00: events still without a place, to their organizers
    logic.saved_day(con)  # 12:00: saved events tomorrow, to those not going
    logic.door_round(con)  # the door is open (early, or at T-30): each guest going hears it once
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
    # the partial index outbox_todo (migration 109), named: the planner liked outbox_due, which walks every failed row
    return rows(con, """SELECT b.*, u.tg_id, u.lang, u.can_dm, u.banned_at FROM bot_outbox b INDEXED BY outbox_todo JOIN users u ON u.id = b.user_id
        WHERE b.sent_at IS NULL AND b.error IS NULL AND b.send_after <= ? ORDER BY b.send_after, b.id LIMIT 50""", now())


def _mark(con, m, sent: bool, error: str | None = None) -> None:
    con.execute("UPDATE bot_outbox SET sent_at = ?, error = ? WHERE id = ?", (now() if sent else None, error, m["id"]))


def _take(con, m):
    """One queued message taken and rendered, or None (the other postman has it, or it can't go: marked why)."""
    # take it first: during a deploy the old and the new container run side by side for a few seconds, and
    # both postmen see the same queue; whoever moves send_after on gets the message (back after LEASE if lost)
    if not con.execute("UPDATE bot_outbox SET send_after = ? WHERE id = ? AND send_after = ? AND sent_at IS NULL AND error IS NULL",
                       (now() + LEASE, m["id"], m["send_after"])).rowcount:
        return None
    if not m["can_dm"]:
        return _mark(con, m, False, "no_dm")
    if m["banned_at"]:  # banned: the bot stops writing
        return _mark(con, m, False, "banned")
    msg = _render(con, m)
    if msg is None:
        _mark(con, m, False, "gone")
    return msg


def _answered(con, m, status: int, answer: dict) -> None:
    if answer.get("ok"):
        _mark(con, m, True)
        tgc.sent(con, m, answer)
    elif status == 403:  # blocked the bot or never started it
        con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (m["user_id"],))
        _mark(con, m, False, "blocked")
    else:
        _mark(con, m, False, str(answer.get("description", status))[:200])


ELECTIVE = ("@KBTUstartup", 2016)  # owner's one-off exception (Nov 7): the incubator's post to the 3rd years, in short with its link


async def send_due(cfg: Config, http: httpx.AsyncClient) -> None:
    con = db.connect(cfg.db_path)  # one connection, used by one thread at a time (check_same_thread=False)
    try:
        await anyio.to_thread.run_sync(_chores, cfg, con)
        offsite_round(cfg, con)  # and that copy, encrypted, to R2 (Sundays the media too); reads, a write an hour at most
        await post_channel(cfg, http, con)  # public events to @KBTUevents, edits and cancels too
        await tgc.tick(cfg, http, con)  # the forum channel's comments: strangers' texts after the hour, deletions, unbans
        await tgc.post_tick(cfg, http, con)  # the forum channel's posts: taken down, then the new ones published
        await _userpics(cfg, http, con)  # Telegram photos copied to /media: t.me took ~1 s on every open
        if await anyio.to_thread.run_sync(logic._once, con, "chats_day", str(now() // 86400)):
            await refresh_chats(cfg, http, con)  # daily: the chats' avatars and members from their t.me pages
        for m in await anyio.to_thread.run_sync(_due, con):
            msg = await anyio.to_thread.run_sync(_take, con, m)
            if msg is None:
                continue
            text, button, start = msg
            body = {"chat_id": m["tg_id"], "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
            if isinstance(start, list):  # the whole keyboard; "start" buttons open the app there
                body["reply_markup"] = {"inline_keyboard": [[{"text": b["text"], "url": f"https://t.me/{cfg.bot_username}?startapp={b['start']}"}
                                                             if "start" in b else b for b in row] for row in start]}
            elif button:
                body["reply_markup"] = {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}
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
    if [w.split("@")[0] for w in words[:1]] == ["/chat"] or arg == "chat":  # "suggest a chat": Telegram's own chat picker (PLAN item 45)
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
    keeping its names in the languages sent before (the portal switched to another language, the page sent again: Oct
    30). The answer has counts and language names only. The file is read in memory and never kept; nothing of the page
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
    seats); another year is left, an audit line says so. One held by another account is left and the founder hears
    (no ID in the notice or the log). Five a day, like Settings: the profile would tell which IDs are registered."""
    s = one(con, "SELECT student_id, consent_version, manual FROM students WHERE user_id = ?", uid)
    if not sid or not s or s["manual"] or s["consent_version"] == "staff" or s["student_id"] == sid:
        return  # unconfirmed: its name is self-typed, so a page "matching" it proves nothing; staff: a placeholder ID
    tries = one(con, """SELECT COUNT(*) FROM audit_log WHERE target = ? AND at > ? AND (action IN ('sid_page_taken', 'sid_page_year')
        OR action = 'identity_fix' AND actor_id IS NULL AND json_extract(data, '$.field') = 'student_id')""", f"user:{uid}", now() - 86400)[0]
    if tries >= 5:
        return
    if re.sub(r"\d+$", "", s["student_id"]) != re.sub(r"\d+$", "", sid):
        with db.tx(con):
            logic.log_action(con, None, "sid_page_year", f"user:{uid}")
        return
    try:
        logic.fix_identity(con, uid, "student_id", sid, admin=True)
    except _Taken:
        with db.tx(con):
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


async def _receipt(cfg: Config, http: httpx.AsyncClient, con, msg: dict, eid: int | None = None) -> dict | None:
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
        c, gone = logic.add_receipt(con, logic.Viewer(u["id"], u["role"], True), eid, saved, read, via="bot")
    except logic.ApiError:  # the hold ran out while the file was read: the picture goes, unless a row has the same one
        media.drop(root, [] if one(con, "SELECT 1 FROM files WHERE path = ?", saved["path"]) else [saved["path"]])
        return say("receipt_none")
    media.drop(root, gone)  # the one it replaced
    title = next(h["title"] for h in holds if h["id"] == eid)
    if flags := (c["my"] or {}).get("receiptFlags"):  # looks wrong: the ticket stays, the app's ticket takes another file
        return say("receipt_check", f"tk_{eid}", title=title, why=texts.receipt_why(lang, flags))
    return say("receipt_ok", f"tk_{eid}", title=title)


async def _tapped(cfg: Config, http: httpx.AsyncClient, con, cq: dict) -> None:
    """A tap on the bot's buttons under a message they answer: "which event" for a receipt (rc:); and on the forum's
    cards (ct:, ps:). The question turns into the answer; someone else's tap does nothing."""
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/answerCallbackQuery", json={"callback_query_id": cq["id"]})
    msg, data = cq.get("message") or {}, str(cq.get("data") or "")
    # the forum's cards: Accept/Decline an offer, stop the pings; an: more messages like the elective's? (the tapper's own row)
    if f := re.fullmatch(r"(ct|ps):(\d+)(?::([yn]))?|an:([yn])", data):
        u = one(con, "SELECT id, lang FROM users WHERE tg_id = ?", (cq.get("from") or {}).get("id"))
        if not u or not msg:
            return
        if f[4]:
            con.execute("UPDATE users SET announce_ok = ? WHERE id = ?", (int(f[4] == "y"), u["id"]))
            said = "announce_yes" if f[4] == "y" else "announce_no"
        elif f[1] == "ps":
            con.execute("UPDATE users SET ask_pings = 0 WHERE id = ?", (u["id"],))
            said = "ask_stopped"
        else:
            st = logic.decide_contact(con, u["id"], int(f[2]), f[3] == "y")
            said = {"accepted": "contact_yes", "declined": "contact_no"}.get(st or "", "contact_gone")
        chat, thanks = (msg.get("chat") or {}).get("id"), texts.bot_message(u["lang"], said)[0]
        if f[4]:  # the post stays with its link; the question's buttons give way to the thanks
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
    body = await _receipt(cfg, http, con, orig, int(m[1])) if _file(orig) else None
    if body:
        await _tg(cfg, http, "editMessageText", {**body, "message_id": msg["message_id"], "reply_markup": body.get("reply_markup", {"inline_keyboard": []})})


async def _group(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> None:
    """In a group: "/start ec_<token>" (sent by Telegram when the organizer added the bot by the app's "Create chat")
    links it to the event and makes its join-request link; a group turned supergroup keeps its event."""
    chat = msg["chat"]
    if new := msg.get("migrate_to_chat_id"):
        con.execute("UPDATE events SET chat_id = ? WHERE chat_id = ?", (new, chat["id"]))
        con.execute("UPDATE chats SET tg_chat_id = ? WHERE tg_chat_id = ?", (new, chat["id"]))
        return
    words = str(msg.get("text") or "").split()
    if len(words) == 2 and re.fullmatch(r"/start(@\w+)?", words[0]) and re.fullmatch(r"oc_\d+", words[1]):  # Studio's "Add our bot" (PLAN 86)
        if cid := logic.bot_added(con, int((msg.get("from") or {}).get("id") or 0), chat, cid=int(words[1][3:])):
            await chat_card(cfg, http, con, cid, chat["id"])
        return
    if len(words) != 2 or not re.fullmatch(r"/start(@\w+)?", words[0]) or not words[1].startswith("ec_"):
        return
    e = logic.chat_claim(con, words[1][3:], int((msg.get("from") or {}).get("id") or 0), chat["id"])
    api = f"https://api.telegram.org/bot{cfg.bot_token}"
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


def _event_copy(cfg: Config, msg: dict) -> bool:
    """Telegram's copy of an events channel post in its discussion group."""
    channel = cfg.events_channel.lstrip("@").lower()
    return bool(channel) and bool(msg.get("is_automatic_forward")) and str((msg.get("sender_chat") or {}).get("username") or "").lower() == channel


async def _discussion_bg(cfg: Config, http: httpx.AsyncClient, msg: dict) -> None:
    """_discussion beside the ears (tgc.spawn): its wait for the post's id never holds up the batch (review 2)."""
    con = db.connect(cfg.db_path)
    try:
        await _discussion(cfg, http, con, msg)
    except Exception:  # noqa: BLE001
        log.exception("discussion")
    finally:
        con.close()


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
    """A join request to an event's group: those signed up (and volunteers, the team) in, the rest declined. In a chat
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
    if ok is None:
        return
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{'approve' if ok else 'decline'}ChatJoinRequest",
                    json={"chat_id": req["chat"]["id"], "user_id": req["from"]["id"]})


async def hear(cfg: Config, http: httpx.AsyncClient, offset: int) -> int:
    """One long poll: answers what came and returns the next offset (the same one when the round failed)."""
    try:
        r = await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getUpdates",
                           params={"offset": offset, "timeout": WAIT, "allowed_updates": json.dumps(
                               ["message", *(["edited_message"] if cfg.tgc_chat else []), "callback_query", "chat_join_request", "my_chat_member",
                                # the forum channel's reactions (sent only where the bot is the channel's admin, and only when asked for)
                                *(["message_reaction_count"] if cfg.forum_channel else [])])}, timeout=WAIT + 10)
        answer = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("ears: %s", type(exc).__name__)
        await asyncio.sleep(5)
        return offset
    if not answer.get("ok"):  # 409: a webhook is set elsewhere, so this bot's messages go there; say so, now and then
        log.warning("ears: %s", str(answer.get("description", r.status_code))[:200])
        await asyncio.sleep(60)
        return offset
    con = db.connect(cfg.db_path)
    try:
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
            msg = {}
            try:  # all of it: a locked database even in the ban check replayed the whole batch
                offset = upd["update_id"] + 1
                if "edited_message" in upd or tgc.ours(cfg, upd):  # edits matter only in the forum's group (above)
                    continue
                if rc := upd.get("message_reaction_count"):
                    if (rc.get("chat") or {}).get("id") == cfg.forum_channel:
                        logic.fchannel.reacted(con, rc)
                    continue
                msg = upd.get("message") or {}
                sender = ((upd.get("callback_query") or upd.get("chat_join_request") or msg).get("from") or {}).get("id")
                group = (msg.get("chat") or {}).get("type") in ("group", "supergroup")  # a group's housekeeping serves everyone in it
                if sender and not group and one(con, "SELECT 1 FROM users WHERE tg_id = ? AND banned_at IS NOT NULL", sender):
                    continue  # banned: the bot neither answers nor acts for him
                if "callback_query" in upd:
                    await _tapped(cfg, http, con, upd["callback_query"])
                    continue
                if "chat_join_request" in upd:
                    if not upd["chat_join_request"].get("query_id"):  # a guarded one was answered above
                        await _join(cfg, http, con, upd["chat_join_request"])
                    continue
                if "my_chat_member" in upd:
                    await _member(cfg, http, con, upd["my_chat_member"])
                    continue
                if (msg.get("chat") or {}).get("type") in ("group", "supergroup"):  # an event's group: only its linking matters
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
                else:
                    body = await _schedule(cfg, http, con, msg) if _sched_file(msg) else await _receipt(cfg, http, con, msg) if _file(msg) else _welcome(con, cfg, msg)
                if body:
                    con.execute("UPDATE users SET can_dm = 1 WHERE tg_id = ?", (body["chat_id"],))  # writing to the bot unblocks it
                    await _send(cfg, http, body)
            except Exception as exc:  # one update that breaks (a page the parser chokes on) never stops the bot for everyone
                log.warning("ears: %s", type(exc).__name__)  # the type only: never a page's words
                if not isinstance(exc, httpx.HTTPError) and _sched_file(msg) and (msg.get("chat") or {}).get("type") == "private":
                    try:
                        await _send(cfg, http, _reply(msg["chat"]["id"], *texts.bot_message(_lang(con, msg), "sched_bad")))
                    except Exception as again:
                        log.warning("ears: %s", type(again).__name__)
    finally:
        con.close()
    return offset


async def _ears(cfg: Config, http: httpx.AsyncClient) -> None:
    offset = 0
    while True:
        try:
            offset = await hear(cfg, http, offset)
        except Exception:  # a bug in one round must not stop the ears
            log.exception("ears round")
            await asyncio.sleep(5)


async def _postman(cfg: Config, http: httpx.AsyncClient) -> None:
    while True:
        try:
            await send_due(cfg, http)
        except Exception:  # a bug in one round must not stop the postman
            log.exception("bot round")
        await asyncio.sleep(POLL)


async def _videos(cfg: Config) -> None:
    """Event videos (video.py), one at a time in this one process: whatever was being compressed when the last postman
    died starts over. Videos no event holds leave the disk a day after their upload."""
    con = db.connect(cfg.db_path)
    root = Path(cfg.db_path).resolve().parent
    con.execute("UPDATE videos SET status = 'queued' WHERE status = 'working'")
    swept = 0.0
    while True:
        try:
            if time.monotonic() - swept > 3600:
                swept = time.monotonic()
                for vid, path in logic.stale_videos(con):
                    (root / "uploads" / str(vid)).unlink(missing_ok=True)
                    for ext in (".mp4", ".webp", ".t.webp", ".jpg") if path else ():
                        (root / "media" / f"{path}{ext}").unlink(missing_ok=True)
            x = logic.next_video(con)
            if not x:
                await asyncio.sleep(3)
                continue
            src = root / "uploads" / str(x["id"])
            try:
                logic.video_done(con, x["id"], await video.compress(src, root / "media", bool(x["wide"])))
            except (video.BadVideo, OSError) as exc:
                log.warning("video %d: %s", x["id"], str(exc)[-200:])
                logic.video_done(con, x["id"], None, "too_long" if str(exc) == "too_long" else "not_a_video")
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


async def run(cfg: Config) -> None:
    """Forever, in one process: every worker (and, during a deploy, the other container) waits on a lock file next to
    the database, and whoever holds it is the postman, since Telegram's rate limit is the bot's, not a worker's; if
    that process dies, the lock goes with it and another takes over within seconds. Then the outbox, every few
    seconds, and the ears (one poller at a time: Telegram refuses a second)."""
    with open(f"{cfg.db_path}.bot.lock", "w") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(5)
        log.warning("postman in process %d", os.getpid())  # one line per start (warning: the level the container's log keeps)
        log.warning("receipts ocr: %s", await asyncio.to_thread(receipt.ready))
        async with httpx.AsyncClient(timeout=15) as http:
            await load_pack(cfg, http)
            await asyncio.gather(_postman(cfg, http), _ears(cfg, http), _videos(cfg), _translator(cfg), _userbot(cfg))
