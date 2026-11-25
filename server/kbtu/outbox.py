"""The postman (SPEC §7): sends what logic.notify() queued in bot_outbox, as server templates (texts.py) in the user's
language with a button into the app; only to users who let the bot write (can_dm). A user who blocked the bot loses
can_dm until Telegram says otherwise. bot.py's _postman runs send_due every POLL seconds, in the worker that leads."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time

import anyio.to_thread
import httpx

from . import casting, checkin, db, instagram, logic, mirror, texts, tgc, youtube
from .bot import _chores, _send, _stopping, _tg, _userpics, offsite_round, post_channel, refresh_chats
from .bot_dm import MUTE_ROW, _feedback_buttons
from .config import Config
from .logic import notifications, now, one, rows

log = logging.getLogger("kbtu.bot")

GAP = 0.04                  # the postman's sends start this far apart: ≤ 25 a second overall (Telegram allows about 30)
SENDERS = 25                # chats the postman writes to at once (one message per chat at a time): its answers take a while
BATCH = 200                 # queued messages read at once; a full batch is followed by the next in the same round
LEASE = 60                  # a taken message is free again after this, if its postman died or the network was down


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
        return (*texts.bot_message(lang, kind), f"fa_{a['id']}")
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
        kind = ("contact_subj" if a["subject"] else "contact_ask") if a else "contact_ask_plain"  # a subject's: its catalogue name
        text = texts.bot_message(lang, kind, name=logic.short_name(p), title=a["title"] if a else "")[0]
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
    if kind == "event_review":  # er:<event>:<day>, to the club's President and Vices: a member's draft waits for their yes; quiet once answered or gone
        e = one(con, """SELECT e.org_id, o.name FROM events e JOIN orgs o ON o.id = e.org_id AND o.status = 'active'
            JOIN event_reviews r ON r.event_id = e.id AND r.asked_at IS NOT NULL
            JOIN org_members m ON m.org_id = o.id AND m.user_id = ? AND m.role IN ('president', 'vice')
            WHERE e.id = ? AND e.status = 'draft' AND e.hidden_at IS NULL""", m["user_id"], int(ref[1]))
        return (*texts.bot_message(lang, kind, org=e["name"]), f"st_{e['org_id']}") if e else None
    if kind in ("event_approved", "event_returned"):  # ea:<event>, eb:<event>:<day>, to the member who made it; quiet if it changed since
        back = "" if kind == "event_approved" else "AND EXISTS (SELECT 1 FROM event_reviews r WHERE r.event_id = e.id AND r.asked_at IS NULL AND r.reason IS NOT NULL)"
        e = one(con, f"""SELECT e.id, e.org_id, o.name FROM events e JOIN orgs o ON o.id = e.org_id AND o.status = 'active'
            WHERE e.id = ? AND e.created_by = ? AND e.hidden_at IS NULL AND e.status = ? {back}""", int(ref[1]), m["user_id"], "draft" if back else "published")
        return (*texts.bot_message(lang, kind, org=e["name"]), f"st_{e['org_id']}" if back else f"ev_{e['id']}") if e else None
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
        return (*texts.bot_message(lang, kind), f"ev_{e['id']}") if e and not logic.door_shut(e, now()) else None
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
    if kind == "meetup_review":
        notice = checkin.meetup_notice(con, int(ref[1]), m["user_id"])
        return (*texts.bot_message(lang, notice["kind"], dept=notice["dept"]), f"meet_{ref[1]}") if notice else None
    if kind in SANTA_KINDS:
        return _santa(con, m, lang)
    if kind in ("donation_confirmed", "donation_rejected"):
        d = one(con, "SELECT status, revision FROM donations WHERE id = ? AND user_id = ?", int(ref[1]), m["user_id"])
        if not d or d["status"] != kind.removeprefix("donation_") or d["revision"] != int(ref[2]):
            return None
        return (*texts.bot_message(lang, kind), "donate")
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
    if kind == "remind_2h" and not one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", e["id"], m["user_id"]):
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


def _due(con) -> list:
    # the partial index outbox_todo (migration 109), named: else the planner picks outbox_due, which walks every failed row
    return rows(con, """SELECT b.*, u.tg_id, u.lang, u.can_dm, u.banned_at FROM bot_outbox b INDEXED BY outbox_todo JOIN users u ON u.id = b.user_id
        WHERE b.sent_at IS NULL AND b.error IS NULL AND b.send_after <= ? ORDER BY b.send_after, b.id LIMIT ?""", now(), BATCH)


def _mark(con, m, sent: bool, error: str | None = None) -> None:
    # Deleting a post or account can retire this row while Telegram answers. SQLite can reuse its numeric id.
    con.execute("UPDATE bot_outbox SET sent_at = ?, error = ? WHERE id = ? AND user_id = ? AND kind = ? AND ref = ?",
                (now() if sent else None, error, m["id"], m["user_id"], m["kind"], m["ref"]))


def _take(con, m, forum_channel: bool):
    """One queued message taken and rendered, or None (the other postman has it, or it can't go: marked why)."""
    # take it first: during a deploy the old and the new container run side by side for a few seconds, and
    # both postmen see the same queue; whoever moves send_after on gets the message (back after LEASE if lost)
    lease = logic.fchannel.COMMENT_GAP if m["kind"] == "fch_comments" else LEASE  # Telegram may receive a send whose answer is lost
    if not con.execute("""UPDATE bot_outbox SET send_after = ? WHERE id = ? AND user_id = ? AND kind = ? AND ref = ?
                       AND send_after = ? AND sent_at IS NULL AND error IS NULL""",
                       (now() + lease, m["id"], m["user_id"], m["kind"], m["ref"], m["send_after"])).rowcount:
        return None
    if not m["can_dm"]:
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


def _answered(con, m, status: int, answer: dict) -> None:
    if answer.get("ok"):
        if m["kind"] == "contact_ask" and (mid := (answer.get("result") or {}).get("message_id")):
            logic.subjects.offer_delivered(con, int(m["ref"].split(":")[1]), m["user_id"], m["tg_id"], mid)
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


async def _withdrawn_offers(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """Replace a withdrawn study offer's Telegram card and remove its buttons."""
    for c in rows(con, """SELECT c.id, c.offer_message, u.tg_id, u.lang FROM contacts c JOIN users u ON u.id = c.to_id
            WHERE c.withdrawn_at IS NOT NULL AND c.offer_message IS NOT NULL ORDER BY c.id LIMIT 50"""):
        target = json.loads(c["offer_message"])
        if target["chat_id"] == c["tg_id"]:
            try:
                r = await _tg(cfg, http, "editMessageText", {**target, "parse_mode": "HTML",
                              "text": texts.bot_message(c["lang"], "contact_withdrawn")[0], "reply_markup": {"inline_keyboard": []}})
                if r.status_code == 429 or r.status_code >= 500:
                    return  # try again next round
            except (httpx.HTTPError, ValueError):
                return
        con.execute("UPDATE contacts SET offer_message = NULL WHERE id = ? AND offer_message = ?", (c["id"], c["offer_message"]))


async def send_due(cfg: Config, http: httpx.AsyncClient) -> None:
    con = db.connect(cfg.db_path)  # one connection, used by one thread at a time (check_same_thread=False)
    try:
        await anyio.to_thread.run_sync(_chores, cfg, con)
        offsite_round(cfg, con)  # and that copy, encrypted, to R2 (Sundays the media too); reads, a write an hour at most
        await post_channel(cfg, http, con)  # public events to @KBTUevents, edits and cancels too
        await tgc.tick(cfg, http, con)  # the forum channel's comments: strangers' texts after the hour, deletions, unbans
        await tgc.post_tick(cfg, http, con)  # the forum channel's posts: taken down, then the new ones published
        await _withdrawn_offers(cfg, http, con)
        await _userpics(cfg, http, con)  # Telegram photos copied to /media: t.me takes ~1 s on every open
        if await anyio.to_thread.run_sync(logic._once, con, "yt_hour", str(now() // 3600)):
            await youtube.sweep(cfg, http, con)  # hourly: the clubs' YouTube channels' new videos as their posts
        if cfg.ig_user_id and cfg.ig_token and await anyio.to_thread.run_sync(logic._once, con, "ig_half", str(now() // 1800)):
            await instagram.sweep(cfg, http, con)  # every half hour: the clubs' Instagram posts as their posts
        if await anyio.to_thread.run_sync(logic._once, con, "chats_day", str(now() // 86400)):
            await refresh_chats(cfg, http, con)  # daily: the chats' avatars and members from their t.me pages
        while True:  # batch after batch while the queue stays full (a broadcast); the chores above wait for it
            due = await anyio.to_thread.run_sync(_due, con)
            if not await _batch(cfg, http, con, due) or len(due) < BATCH:
                return
    finally:
        con.close()


async def _batch(cfg: Config, http: httpx.AsyncClient, con, due: list) -> bool:
    """One batch side by side: up to SENDERS chats at once, one message per chat at a time and in the queue's order,
    the sends started GAP apart overall. False: stop the round (stop(), the network or a 429)."""
    lock, gate, halt = asyncio.Lock(), asyncio.Semaphore(SENDERS), asyncio.Event()
    nxt = time.monotonic()

    async def turn() -> bool:  # this send's slot, GAP after the one before; False: the round is over
        nonlocal nxt
        at = max(nxt, time.monotonic())
        nxt = at + GAP
        await asyncio.sleep(at - time.monotonic())
        return not (halt.is_set() or _stopping())  # between messages: one cut mid-send would go again after its LEASE, maybe twice

    async def chat(ms: list) -> None:
        async with gate:
            for m in ms:
                if not await turn():
                    return
                await _deliver(cfg, http, con, m, lock, halt)

    chats: dict[int, list] = {}
    for m in due:
        chats.setdefault(m["tg_id"], []).append(m)
    async with asyncio.TaskGroup() as tg:  # a bug in one cancels the rest: none outlives the connection
        for ms in chats.values():
            tg.create_task(chat(ms))
    return not (halt.is_set() or _stopping())


async def _deliver(cfg: Config, http: httpx.AsyncClient, con, m, lock: asyncio.Lock, halt: asyncio.Event) -> None:
    """One queued message taken, sent and marked. The connection serves one thread at a time (lock), the sends run
    side by side; the network down or a 429 sets halt."""
    async with lock:
        if halt.is_set():  # while this one waited its turn at the database
            return
        msg = await anyio.to_thread.run_sync(_take, con, m, bool(cfg.forum_channel))
        if msg is None:
            return
        text, button, start = msg
        to = m["tg_id"]
        if m["kind"] == "credit_ask":  # the account may have moved since the queue was read: to its Telegram of now, or not at all
            to = logic.credits.asking(con, m["user_id"])
            if to is None:
                _mark(con, m, False, "gone")
                return
        if m["kind"] in tgc.AUTHOR and not one(con, "SELECT 1 FROM users WHERE id = ? AND tg_id = ?", m["user_id"], to):
            return  # the account moved after the batch was read; the retry will use the new chat
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
                return
            if m["kind"] in MUTE_ROW:
                body.setdefault("reply_markup", {"inline_keyboard": []})["inline_keyboard"].append(
                    _feedback_buttons(cfg, to, m["lang"], category))
    try:
        async with lock:  # it reads the connection first (and returns at once for any other kind)
            r = await tgc.edit_first(cfg, http, con, m, body)  # a comment's verdict: its first message edited
        if r is None:
            r = await _send(cfg, http, body)
        answer = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("postman: %s", type(exc).__name__)
        halt.set()  # the network is down: the rest stays queued for the next round
        return
    if not answer.get("ok") and r.status_code == 429:  # too fast: everyone waits as told; this one goes again after its LEASE
        halt.set()
        await asyncio.sleep(float(answer.get("parameters", {}).get("retry_after", 5)))
        return
    async with lock:
        await anyio.to_thread.run_sync(_answered, con, m, r.status_code, answer)
