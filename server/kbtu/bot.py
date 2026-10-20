"""The postman (SPEC §7), inside the web app's event loop (app.py lifespan).

- Postman: sends what logic.notify() queued in bot_outbox, as server templates (texts.py) in the user's
  language with a button into the app; only to users who let the bot write (can_dm). A user who blocked
  the bot loses can_dm until Telegram says otherwise.
- Ears: whatever someone writes to the bot (/start first of all) is answered with what the app is and a button
  into it (owner, Oct 7: /start said nothing); a receipt (Kaspi's PDF or a picture) goes to the sender's seat on hold.
Until Oct 7 it also refreshed schedules with each student's stored KBTU session; no session outlives a request
now (SPEC §4.1), the stored ones were ended, and migration 18 dropped their table."""
from __future__ import annotations

import asyncio
import html
import json
import fcntl
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import httpx

from . import casting, db, logic, media, offsite, receipt, texts, video
from .config import Config
from .logic import now, one, rows

log = logging.getLogger("kbtu.bot")

POLL = 2                    # seconds between outbox checks
GAP = 0.05                  # ≤ 20 messages a second (Telegram allows about 30)
LEASE = 60                  # a taken message is free again after this, if its postman died or the network was down
WAIT = 25                   # getUpdates: Telegram holds the request this long while nobody writes
FRESH = 300                 # an older message isn't answered: what piled up while nobody listened (before Oct 7)


# Premium emoji (Bot API 9.4: a bot whose owner has Telegram Premium may send custom emoji): the pack the owner picked
# (Oct 14), loaded once a postman starts; each plain emoji our texts use that the pack also has goes out animated, the
# rest stay plain. If Telegram ever refuses them (Premium ended), the message goes again plain and the pack is dropped.
# the packs, first wins (owner, Oct 18: NewsEmoji, made for bots; the older pack fills what it lacks)
EMOJI_PACKS = ("NewsEmoji", "AnimatedAsianEmoji")
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
    """A Telegram call whose text or caption (HTML) gets the pack's emoji (owner, Oct 18: everywhere the bot writes, the
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


def _render(con, m) -> tuple[str, str | None, str] | None:
    """(text, button, startapp) for one outbox row, or None when what it was about is gone."""
    kind, ref, lang = m["kind"], m["ref"].split(":"), m["lang"]
    if kind == "link_attempt":
        return (*texts.bot_message(lang, kind), "")
    if kind == "backup_failed":  # bf:<day>, to the admins: no copy reached R2 last night nor the night before
        return (*texts.bot_message(lang, kind), "")
    if kind == "delete_soon":  # del:<when>, to me; gone if I changed my mind
        at = one(con, "SELECT delete_at FROM users WHERE id = ?", m["user_id"])["delete_at"]
        return (*texts.bot_message(lang, kind, when=texts.when(at, lang).split(",")[0]), "me") if at else None
    if kind == "join_request":  # jr:<org>:<applicant>:<day>, to the club's Vice+; gone once withdrawn or answered
        o, p = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1])), one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not o or not p or not one(con, "SELECT 1 FROM join_requests WHERE org_id = ? AND user_id = ? AND status = 'pending'", int(ref[1]), int(ref[2])):
            return None
        return (*texts.bot_message(lang, kind, org=o["name"], name=logic.short_name(p)), f"jr_{ref[1]}")
    if kind == "join_decided":  # jr:<request>:yes|no, to the applicant
        r = one(con, "SELECT j.org_id, o.name FROM join_requests j JOIN orgs o ON o.id = j.org_id WHERE j.id = ?", int(ref[1]))
        if not r:
            return None
        return (*texts.bot_message(lang, "join_yes" if ref[2] == "yes" else "join_no", org=r["name"]), f"cl_{r['org_id']}")
    if kind == "rate":  # rate:<event>, an hour after the end, to those checked in; not if rated already or reminders are off
        e = one(con, "SELECT title FROM events WHERE id = ? AND status = 'published'", int(ref[1]))
        if not e or not one(con, "SELECT n_remind FROM users WHERE id = ?", m["user_id"])[0] \
                or one(con, "SELECT 1 FROM event_ratings WHERE event_id = ? AND user_id = ?", int(ref[1]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, title=e["title"]), f"ev_{ref[1]}")
    if kind == "event_update":  # upd:<id>; gone if the organizer deleted it or the event is no longer on
        u = one(con, """SELECT e.id, e.title, o.name FROM event_updates x JOIN events e ON e.id = x.event_id JOIN orgs o ON o.id = e.org_id
            WHERE x.id = ? AND e.status = 'published'""", int(ref[1]))
        return (*texts.bot_message(lang, kind, title=u["title"], org=u["name"]), f"ev_{u['id']}") if u else None
    if kind in ("broadcast", "important"):  # post:<id>, to every club member / to its club's members; gone if taken down
        post = one(con, "SELECT p.title, o.name FROM posts p JOIN orgs o ON o.id = p.org_id WHERE p.id = ? AND p.hidden_at IS NULL", int(ref[1]))
        return (*texts.bot_message(lang, kind, org=post["name"], title=post["title"]), "news") if post else None
    if kind == "friend_request":  # fq:<asker>:<day>; gone once answered or taken back
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[1]))
        if not p or not one(con, "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND status = 'pending'", int(ref[1]), m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p)), "friends")
    if kind == "club_application":  # capp:<id>, to moderators and the admin while it waits
        a = one(con, "SELECT name, status FROM club_applications WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=a["name"]), "capps") if a and a["status"] == "pending" else None
    if kind == "club_application_decided":  # cad:<id>:yes|no, to the applicant; a no's reason is read in the app (our words only here)
        a = one(con, "SELECT name, org_id FROM club_applications WHERE id = ?", int(ref[1]))
        if not a:
            return None
        return (*texts.bot_message(lang, "club_yes" if ref[2] == "yes" else "club_no", name=a["name"]), f"cl_{a['org_id']}" if ref[2] == "yes" and a["org_id"] else "newclub")
    if kind == "club_official":  # off:<org>, to the club's President: DMP gave the ✓ (said only while it still has it)
        o = one(con, "SELECT name, official FROM orgs WHERE id = ?", int(ref[1]))
        return (*texts.bot_message(lang, kind, name=o["name"]), f"cl_{ref[1]}") if o and o["official"] else None
    if kind == "achievement":  # ach:<code>:<level>: a new level, once (→ aw_<code>: the card, Share there)
        code, level = ref[1], int(ref[2])
        a = next((x for x in logic.ACHIEVEMENTS if x[0] == code), None)
        if not a:
            return None
        tier = f" · {texts.TIERS[lang if lang in texts.TIERS else 'ru'][level - 1]}" if len(a[2]) > 1 else ""
        return (*texts.bot_message(lang, kind, name=texts.ACH_NAMES[lang if lang in texts.ACH_NAMES else "ru"][code], tier=tier), f"aw_{code}")
    if kind == "photo_report":  # ph:<event>, to those who came, once: the guests' album filled up
        e = one(con, "SELECT id, title FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[1]))
        n = one(con, "SELECT COUNT(*) FROM event_photos WHERE event_id = ?", int(ref[1]))[0]
        return (*texts.bot_message(lang, kind, title=e["title"], n=n), f"ph_{e['id']}") if e and n else None
    if kind in ("comment_question", "comment_answer"):  # cq:<event>:<hour> to the club's Head+ · ca:<event>:<answer> to askers
        e = one(con, "SELECT e.id, e.title, o.name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.hidden_at IS NULL",
                int(ref[1]))
        if not e or not one(con, "SELECT n_remind FROM users WHERE id = ?", m["user_id"])[0]:  # follows the reminders switch
            return None
        if kind == "comment_question" and not logic._asking(con, e["id"], m["user_id"]):  # answered or read before the card went out
            return None
        if kind == "comment_answer" and not one(con, "SELECT 1 FROM comments WHERE id = ? AND deleted_at IS NULL", int(ref[2])):
            return None
        return (*texts.bot_message(lang, kind, title=e["title"], org=e["name"]), f"cm_{e['id']}")
    if kind == "comment_reply":  # cr:<post|event>:<id>:<hour>, to whoever was answered; follows the reminders switch
        if ref[1] == "event":
            x = one(con, "SELECT title FROM events WHERE id = ? AND status = 'published' AND hidden_at IS NULL", int(ref[2]))
        else:
            x = one(con, "SELECT title FROM posts WHERE id = ? AND hidden_at IS NULL", int(ref[2]))
        if not x or not one(con, "SELECT n_remind FROM users WHERE id = ?", m["user_id"])[0]:
            return None
        return (*texts.bot_message(lang, kind, title=x["title"]), f"{'cm' if ref[1] == 'event' else 'cp'}_{ref[2]}")
    if kind in ("volunteer_yes", "volunteer_no"):  # vo:<event>:<when>; quiet if the decision changed since or the event is over
        e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.starts_at > ?",
                int(ref[1]), logic.now())
        x = e and one(con, "SELECT status FROM volunteers WHERE event_id = ? AND user_id = ?", e["id"], m["user_id"])
        if not x or x["status"] != kind.split("_")[1]:
            return None
        return (*texts.bot_message(lang, kind, org=e["org_name"], title=e["title"], when=texts.when(e["starts_at"], lang), place=texts.place_or_tba(e["place"], lang)), f"ev_{e['id']}")
    if kind in ("leaders_invite", "meeting_invite"):  # li: / mi:<event>, to everyone invited; quiet once they've answered or it's over
        e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ? AND e.status = 'published' AND e.starts_at > ?",
                int(ref[1]), logic.now())
        if not e or one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ?", e["id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, org=e["org_name"], title=e["title"], when=texts.when(e["starts_at"], lang), place=texts.place_or_tba(e["place"], lang)), f"ev_{e['id']}")
    if kind == "friend_invite":  # fi:<event>:<inviter>; gone if the event is off or has started, or they're in already
        e = one(con, "SELECT * FROM events WHERE id = ? AND status = 'published' AND starts_at > ?", int(ref[1]), logic.now())
        p = one(con, logic.PERSON + " WHERE u.id = ?", int(ref[2]))
        if not e or not p or one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status IN ('going', 'hold', 'waitlist')",
                                 e["id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p), title=e["title"], when=texts.when(e["starts_at"], lang), place=texts.place_or_tba(e["place"], lang)),
                f"ev_{e['id']}")
    if kind == "round_open":  # ro:<round>, to a club's followers who aren't in it; gone once it stops taking applications
        r = one(con, "SELECT r.*, o.name FROM rounds r JOIN orgs o ON o.id = r.org_id WHERE r.id = ? AND r.status = 'open' AND r.closes_at > ?", int(ref[1]), logic.now())
        if not r or one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", r["org_id"], m["user_id"]):
            return None
        return (*texts.bot_message(lang, kind, org=r["name"], until=texts.when(r["closes_at"], lang)), f"rc_{r['org_id']}")
    if kind in ("round_interview", "round_iv_nudge", "round_iv_remind"):  # iv: / ivn: / ivr:<application>[:<slot>:<when>]
        a = one(con, """SELECT a.*, r.org_id, r.status AS rstatus, o.name FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id WHERE a.id = ?""", int(ref[1]))
        if not a or a["stage"] == "withdrawn" or a["rstatus"] == "done":
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
        a = one(con, """SELECT a.*, r.org_id, r.decline_text, o.name, t.name AS dept FROM round_apps a JOIN rounds r ON r.id = a.round_id
            JOIN orgs o ON o.id = r.org_id LEFT JOIN org_tags t ON t.id = a.taken_tag WHERE a.id = ?""", int(ref[1]))
        if not a:
            return None
        if kind == "round_yes":
            return (*texts.bot_message(lang, kind + ("_dept" if a["dept"] else ""), org=a["name"], dept=a["dept"] or ""), f"cl_{a['org_id']}")
        text, button = texts.bot_message(lang, kind, org=a["name"])
        return (text + ("\n\n" + html.escape(a["decline_text"]) if a["decline_text"] else ""), button, "clubs")
    if kind == "memo_ready":  # memo:<org>:<monday>, to whoever has "memo"; gone if nothing asks DMP any more or it's sent
        o = one(con, "SELECT name FROM orgs WHERE id = ?", int(ref[1]))
        n = one(con, """SELECT COUNT(*) FROM events WHERE org_id = ? AND status IN ('draft', 'published') AND memo IS NOT NULL
            AND memo_sent_at IS NULL AND starts_at >= ? AND starts_at < ?""", int(ref[1]), int(ref[2]), int(ref[2]) + 7 * 86400)[0]
        return (*texts.bot_message(lang, kind, org=o["name"], n=n), f"memo_{ref[1]}") if o and n else None
    if kind == "saved_tomorrow":  # sv:<day>: my saved events tomorrow I'm not going to (gone if I signed up meanwhile)
        day = int(ref[1])
        evs = rows(con, """SELECT e.id, e.title, e.starts_at FROM saved_events s JOIN events e ON e.id = s.event_id WHERE s.user_id = ?
            AND e.status = 'published' AND e.starts_at >= ? AND e.starts_at < ? AND NOT EXISTS (SELECT 1 FROM registrations r
            WHERE r.event_id = e.id AND r.user_id = s.user_id AND r.status IN ('going', 'hold', 'waitlist')) ORDER BY e.starts_at""",
                   m["user_id"], (day + 1) * 86400 - 5 * 3600, (day + 2) * 86400 - 5 * 3600)
        if not evs:
            return None
        text, button = texts.bot_message(lang, kind, list="\n".join(f"• {e['title']}, {texts.when(e['starts_at'], lang)}" for e in evs))
        return text, button, f"ev_{evs[0]['id']}"
    if kind == "place_tba":  # tba:<day>, to an event's maker: all their coming events still without a place
        evs = rows(con, "SELECT id, title, starts_at FROM events WHERE created_by = ? AND status = 'published' AND place = '' AND starts_at > ? ORDER BY starts_at",
                   m["user_id"], logic.now())
        if not evs:
            return None
        text, button = texts.bot_message(lang, kind, list="\n".join(f"• {e['title']}, {texts.when(e['starts_at'], lang)}" for e in evs))
        return text, button, f"ev_{evs[0]['id']}"
    if kind == "friend_new":  # fn:<the other one>:<day>; gone if they're no longer friends by then
        other = int(ref[1])
        p = one(con, logic.PERSON + " WHERE u.id = ?", other)
        if not p or not one(con, "SELECT 1 FROM friendships WHERE a = ? AND b = ?", min(other, m["user_id"]), max(other, m["user_id"])):
            return None
        return (*texts.bot_message(lang, kind, name=logic.shown_name(p)), f"u_{other}")
    if kind == "strike":  # st:<strike>, to the person (→ tm_<org>: their Team); gone if cleared or they've left the club
        x = one(con, """SELECT x.*, o.name FROM strikes x JOIN orgs o ON o.id = x.org_id JOIN org_members mm ON mm.org_id = x.org_id AND mm.user_id = x.user_id
            WHERE x.id = ? AND x.cleared_at IS NULL""", int(ref[1]))
        if not x:
            return None
        n = one(con, "SELECT COUNT(*) FROM strikes WHERE org_id = ? AND user_id = ? AND cleared_at IS NULL AND id <= ?", x["org_id"], x["user_id"], x["id"])[0]
        said = texts.STRIKE_REASON[lang if lang in texts.STRIKE_REASON else "ru"]
        reason = x["note"] if x["reason"] == "other" else said[x["reason"]] + (f" ({x['note']})" if x["note"] else "")
        return (*texts.bot_message(lang, kind, org=x["name"], reason=reason, n=n), f"tm_{x['org_id']}")
    if kind == "probation_passed":  # pp:<org>:<day>, to the person, while they're still in the club
        o = one(con, "SELECT o.name FROM orgs o JOIN org_members mm ON mm.org_id = o.id AND mm.user_id = ? WHERE o.id = ?", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, org=o["name"]), f"cl_{ref[1]}") if o else None
    if kind == "removal_ask":  # rm:<request>, to each President/Vice who outranks the person; gone once decided
        q = one(con, "SELECT q.*, o.name AS org FROM removal_requests q JOIN orgs o ON o.id = q.org_id WHERE q.id = ? AND q.status = 'pending'", int(ref[1]))
        p = one(con, logic.PERSON + " WHERE u.id = ?", q["user_id"]) if q else None
        if not q or not p:
            return None
        if q["by_id"] is None:  # the third strike
            return (*texts.bot_message(lang, "removal_strikes", name=logic.short_name(p), org=q["org"]), f"tm_{q['org_id']}")
        b = one(con, logic.PERSON + " WHERE u.id = ?", q["by_id"])
        return (*texts.bot_message(lang, kind, by=logic.short_name(b) if b else "?", name=logic.short_name(p), org=q["org"],
                                   ban=texts.BAN[lang if lang in texts.BAN else "ru"] if q["ban"] else ""), f"tm_{q['org_id']}")
    e = one(con, "SELECT e.*, o.name AS org_name FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.id = ?", int(ref[1]))
    if not e or (kind != "event_cancelled" and e["status"] != "published"):
        return None
    if e["visibility"] != "public" and kind in ("remind_2h", "seat_free"):  # a club's own event has no ticket (owner, Oct 6)
        kind += "_team"
    text, button = texts.bot_message(lang, kind, title=e["title"], when=texts.when(e["starts_at"], lang), place=texts.place_or_tba(e["place"], lang), org=e["org_name"])
    return text, button, f"{'tk' if kind in ('remind_2h', 'seat_free') else 'ev'}_{e['id']}"


def purge(cfg: Config, con) -> None:
    """The accounts whose week ran out (logic.delete_due), and their files on disk (app.py keeps them in the same places)."""
    home = Path(cfg.db_path).resolve().parent
    receipts, photos = logic.delete_due(con)
    for root, rels in ((home / "receipts", receipts), (home / "media", photos)):
        for rel in rels:
            for ext in (".webp", ".t.webp", ".jpg"):
                (root / f"{rel}{ext}").unlink(missing_ok=True)


async def refresh_chats(cfg: Config, http: httpx.AsyncClient, con) -> None:
    root = Path(cfg.db_path).resolve().parent / "media"
    for c in rows(con, "SELECT id, url FROM chats"):
        peek = await media.chat_peek(http, c["url"])
        if peek["image"]:
            try:
                peek["photo"] = (await asyncio.to_thread(media.save, peek["image"], root))["path"]
            except media.BadImage:
                pass
        if old := logic.chat_refreshed(con, c["id"], peek):
            if not one(con, "SELECT 1 FROM files WHERE path = ?", old):  # never a file something else still shows
                for ext in (".webp", ".t.webp", ".jpg"):
                    (root / f"{old}{ext}").unlink(missing_ok=True)


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
    # no button under the post: Telegram hides the comments then (owner, Oct 17); an edit without one takes the old one off
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


def backup_day(cfg: Config, con) -> None:
    """After 04:00 Almaty, once a day: a full copy of the database into backups/ beside it, the last 14 kept (owner, Oct 18:
    there were none). It guards against a bad deploy or a wrong delete, not a lost disk: that needs a copy elsewhere."""
    local = int(time.time()) + 5 * 3600
    if local % 86400 < 4 * 3600 or not logic._once(con, "backup_day", str(local // 86400)):
        return
    root = Path(cfg.db_path).resolve().parent / "backups"
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
    log.warning("backup: %s, %d KB", out.name, out.stat().st_size // 1024)


_offsite: asyncio.Task | None = None  # the upload running in its thread; one at a time


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
    if local % 86400 >= 10 * 3600 and not done("offsite_db") and not one(con, "SELECT 1 FROM meta WHERE key = 'offsite_db' AND value = ?", yday):
        # two nights without a copy off the server (six tries tonight already): the admins hear it once a day
        for (uid,) in rows(con, "SELECT id FROM users WHERE role = 'admin'"):
            logic.notify(con, uid, "backup_failed", f"bf:{date}")
    jobs = [("offsite_db", [copy, home / "receipts"], f"db/{stamp}.tar.age")] if copy.exists() and not done("offsite_db") else []
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


async def send_due(cfg: Config, http: httpx.AsyncClient) -> None:
    con = db.connect(cfg.db_path)
    try:
        logic.memo_week(con)  # Wednesday morning: next week's memo for DMP is ready (each runs once, by its meta key)
        logic.tba_day(con)    # 10:00: events still without a place, to their organizers
        logic.saved_day(con)  # 12:00: saved events tomorrow, to those not going
        logic.stats_day(con)  # after midnight: yesterday's row for the admin's stats
        casting.forget(con)   # daily: answers and notes of rounds whose results went out 60 days ago
        purge(cfg, con)       # accounts whose week to change their mind ran out
        backup_day(cfg, con)  # a nightly copy of the database, 14 kept
        offsite_round(cfg, con)  # and that copy, encrypted, to R2 (Sundays the media too)
        await post_channel(cfg, http, con)  # public events to @KBTUevents, edits and cancels too
        if logic._once(con, "chats_day", str(now() // 86400)):
            await refresh_chats(cfg, http, con)  # daily: the chats' avatars and members from their t.me pages
        due = rows(con, """SELECT b.*, u.tg_id, u.lang, u.can_dm FROM bot_outbox b JOIN users u ON u.id = b.user_id
            WHERE b.sent_at IS NULL AND b.error IS NULL AND b.send_after <= ? ORDER BY b.send_after, b.id LIMIT 50""", now())
        for m in due:
            # take it first: during a deploy the old and the new container run side by side for a few seconds, and
            # both postmen see the same queue; whoever moves send_after on gets the message (back after LEASE if lost)
            if not con.execute("UPDATE bot_outbox SET send_after = ? WHERE id = ? AND send_after = ? AND sent_at IS NULL AND error IS NULL",
                               (now() + LEASE, m["id"], m["send_after"])).rowcount:
                continue
            mark = lambda sent, error=None: con.execute("UPDATE bot_outbox SET sent_at = ?, error = ? WHERE id = ?", (now() if sent else None, error, m["id"]))
            if not m["can_dm"]:
                mark(False, "no_dm")
                continue
            msg = _render(con, m)
            if msg is None:
                mark(False, "gone")
                continue
            text, button, start = msg
            body = {"chat_id": m["tg_id"], "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
            if button:
                body["reply_markup"] = {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}
            try:
                r = await _send(cfg, http, body)
                answer = r.json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("postman: %s", type(exc).__name__)
                return  # the network is down: everything stays queued for the next round
            if answer.get("ok"):
                mark(True)
            elif r.status_code == 429:  # too fast: wait as told, this one goes again next round
                await asyncio.sleep(float(answer.get("parameters", {}).get("retry_after", 5)))
                return
            elif r.status_code == 403:  # blocked the bot or never started it
                con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (m["user_id"],))
                mark(False, "blocked")
            else:
                mark(False, str(answer.get("description", r.status_code))[:200])
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
    # /exit or ?start=exit: "help me get out" as a message with its button, to forward to any chat (owner, Oct 15)
    text, button = texts.bot_message(u["lang"] if u else str((msg.get("from") or {}).get("language_code") or "")[:2], "exit" if arg == "exit" else "welcome")
    return {"chat_id": chat["id"], "text": text, "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp{'=' + arg if arg else ''}"}]]}}


def _file(msg: dict) -> dict | None:
    """A receipt in a message: Kaspi's PDF (Share → Telegram sends it as a file), a picture sent as a file, or a photo."""
    d = msg.get("document") or {}
    if d.get("mime_type") == "application/pdf" or str(d.get("mime_type") or "").startswith("image/"):
        return d
    return (msg.get("photo") or [None])[-1]  # the biggest size comes last


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
    u = one(con, "SELECT u.id, u.role, u.lang FROM users u JOIN students s ON s.user_id = u.id WHERE u.tg_id = ?", chat["id"])
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
    try:
        c = logic.add_receipt(con, logic.Viewer(u["id"], u["role"], True), eid, saved, read, via="bot")
    except logic.ApiError:  # the hold ran out while the file was read
        return say("receipt_none")
    title = next(h["title"] for h in holds if h["id"] == eid)
    if flags := (c["my"] or {}).get("receiptFlags"):  # looks wrong: the ticket stays, the app's ticket takes another file
        return say("receipt_check", f"tk_{eid}", title=title, why=texts.receipt_why(lang, flags))
    return say("receipt_ok", f"tk_{eid}", title=title)


async def _picked(cfg: Config, http: httpx.AsyncClient, con, cq: dict) -> None:
    """A tap on one of the "which event" buttons: the receipt is the message those buttons answer."""
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/answerCallbackQuery", json={"callback_query_id": cq["id"]})
    msg, data = cq.get("message") or {}, str(cq.get("data") or "")
    orig = msg.get("reply_to_message") or {}
    if not re.fullmatch(r"rc:\d+", data) or not _file(orig) or (orig.get("from") or {}).get("id") != (cq.get("from") or {}).get("id"):
        return
    body = await _receipt(cfg, http, con, orig, int(data[3:]))
    if body:  # the question turns into the answer
        await _tg(cfg, http, "editMessageText", {**body, "message_id": msg["message_id"], "reply_markup": body.get("reply_markup", {"inline_keyboard": []})})


async def _group(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> None:
    """In a group: "/start ec_<token>" (sent by Telegram when the organizer added the bot by the app's "Create chat")
    links it to the event and makes its join-request link; a group turned supergroup keeps its event."""
    chat = msg["chat"]
    if new := msg.get("migrate_to_chat_id"):
        con.execute("UPDATE events SET chat_id = ? WHERE chat_id = ?", (new, chat["id"]))
        return
    words = str(msg.get("text") or "").split()
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


async def _discussion(cfg: Config, http: httpx.AsyncClient, con, msg: dict) -> bool:
    """The channel's discussion group: Telegram forwards each post there by itself, and the comments are replies to that
    copy. Under an event's post the bot writes the first comment, the rules and "Sign up", and keeps its link for the
    app's "Discuss" (owner, Oct 17). True: the message was such a copy. Needs the bot in that group, as an admin
    (a bot that isn't one doesn't see the group's messages)."""
    channel = cfg.events_channel.lstrip("@").lower()
    if not channel or not msg.get("is_automatic_forward") or str((msg.get("sender_chat") or {}).get("username") or "").lower() != channel:
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


async def _join(cfg: Config, http: httpx.AsyncClient, con, req: dict) -> None:
    """A join request to an event's group: those signed up (and volunteers, the team) in, the rest declined."""
    ok = logic.chat_join(con, req["chat"]["id"], req["from"]["id"])
    if ok is None:
        return
    await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/{'approve' if ok else 'decline'}ChatJoinRequest",
                    json={"chat_id": req["chat"]["id"], "user_id": req["from"]["id"]})


async def hear(cfg: Config, http: httpx.AsyncClient, offset: int) -> int:
    """One long poll: answers what came and returns the next offset (the same one when the round failed)."""
    try:
        r = await http.get(f"https://api.telegram.org/bot{cfg.bot_token}/getUpdates",
                           params={"offset": offset, "timeout": WAIT, "allowed_updates": '["message","callback_query","chat_join_request"]'}, timeout=WAIT + 10)
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
        for upd in answer["result"]:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            try:
                if "callback_query" in upd:
                    await _picked(cfg, http, con, upd["callback_query"])
                    continue
                if "chat_join_request" in upd:
                    await _join(cfg, http, con, upd["chat_join_request"])
                    continue
                if (msg.get("chat") or {}).get("type") in ("group", "supergroup"):  # an event's group: only its linking matters
                    if not await _discussion(cfg, http, con, msg):
                        await _group(cfg, http, con, msg)
                    continue
                # a receipt is taken even if it waited (the hold decides); a stale hello isn't answered (FRESH)
                body = await _receipt(cfg, http, con, msg) if _file(msg) else _welcome(con, cfg, msg)
                if body:
                    con.execute("UPDATE users SET can_dm = 1 WHERE tg_id = ?", (body["chat_id"],))  # writing to the bot unblocks it
                    await _send(cfg, http, body)
            except httpx.HTTPError as exc:
                log.warning("ears: %s", type(exc).__name__)
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
                logic.video_done(con, x["id"], await video.compress(src, root / "media"))
            except (video.BadVideo, OSError) as exc:
                log.warning("video %d: %s", x["id"], str(exc)[-200:])
                logic.video_done(con, x["id"], None, "too_long" if str(exc) == "too_long" else "not_a_video")
            src.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - the loop must outlive one bad video
            log.exception("videos")
            await asyncio.sleep(30)


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
            await asyncio.gather(_postman(cfg, http), _ears(cfg, http), _videos(cfg))
