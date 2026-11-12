"""Telegram chats: KBTU's directory and an org's own chats."""
from __future__ import annotations

import json
import re
import sqlite3

from ..db import tx

from .core import (ApiError, Viewer, _org, _qs, can, card, log_action, need_student, one, org_ref, photo, rows)


# ---------------------------------------------------------------- the chats directory (§4.11)

TG_LINK = re.compile(r"https://t\.me/[A-Za-z0-9_+\-/]{3,80}")


def _chat(c: sqlite3.Row, opened: set[int], orgs: dict | None = None) -> dict:
    """orgs: org id -> its ref, for the catalog's chip of whose chat it is (PLAN 86)."""
    return {"id": c["id"], "title": c["title"], "kind": "forum" if c["forum"] else c["kind"], "url": c["url"], "members": c["members"],
            "photo": f"media/{c['photo']}.t.webp" if c["photo"] else None, "school": c["school"], "course": c["course"], "opened": c["id"] in opened,
            "org": (orgs or {}).get(c["org_id"]), "section": c["section"], "sectionAi": bool(c["section_ai"])}


def chats(con, v: Viewer) -> dict:
    """Curated Telegram chats (§4.11), the biggest first (A8); "for you" are the ones aimed at my school and
    course plus those for everyone (my school and course first, by size within); a club's or school's chat says whose
    (PLAN 86; the app no longer ticks the ones I opened; the owner didn't understand it)."""
    st = one(con, "SELECT school, course FROM students WHERE user_id = ?", v.id) if v.student else None
    opened = {r[0] for r in rows(con, "SELECT chat_id FROM chat_opens WHERE user_id = ?", v.id)} if v.student else set()
    # a closed chat's invite link (t.me/+…) only to signed-in students: it lets anyone in (any chat)
    live = rows(con, "SELECT * FROM chats WHERE status = 'live' ORDER BY COALESCE(members, -1) DESC, title")
    orgs = _org_refs(con, {c["org_id"] for c in live if c["org_id"]})
    everything = [_chat(c, opened, orgs) for c in live if v.student or "/+" not in c["url"]]
    fits = lambda c: (c["school"] in (None, st["school"])) and (c["course"] in (None, st["course"]))  # noqa: E731
    aim = lambda c: (c["school"] is not None) * 2 + (c["course"] is not None)  # noqa: E731  — my school and course first, everyone's last
    mine = sorted((c for c in everything if st and fits(c)), key=lambda c: -aim(c))
    out = {"forYou": mine if st else [c for c in everything if c["school"] is None and c["course"] is None], "all": everything}
    if v.role in ("admin", "moderator"):
        out["pending"] = pending_chats(con)
    return out


def pending_chats(con) -> list[dict]:
    """The suggestions waiting for a look, newest first, with whose each is (for the moderator)."""
    waiting = rows(con, "SELECT * FROM chats WHERE status = 'pending' ORDER BY id DESC")
    whose = _org_refs(con, {c["org_id"] for c in waiting if c["org_id"]})
    return [{**_chat(c, set(), whose), "at": c["created_at"]} for c in waiting]


def _org_refs(con, ids: set[int]) -> dict[int, dict]:
    """The chats' clubs as org_ref shows them, their logos in one read (one per club ran on every app start)."""
    found = rows(con, f"SELECT * FROM orgs WHERE id IN ({_qs(ids)})", *ids) if ids else []
    logos = core._by_id(con, "files", (o["logo_file_id"] for o in found))
    return {o["id"]: org_ref(con, o, logos) for o in found}


def chat_opened(con, v: Viewer, cid: int) -> None:
    need_student(v)
    if not one(con, "SELECT 1 FROM chats WHERE id = ? AND status = 'live'", cid):
        raise ApiError("not_found")
    con.execute("INSERT OR IGNORE INTO chat_opens (user_id, chat_id, opened_at) VALUES (?, ?, ?)", (v.id, cid, core.now()))


def chat_input(v: Viewer, body: dict) -> str:
    """Checks a new chat before the app looks it up on t.me; returns its link."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    title, url, kind = str(body.get("title") or "").strip(), str(body.get("url") or "").strip(), body.get("kind")
    school = str(body.get("school") or "").strip() or None
    course = body.get("course")
    if not len(title) <= 80 or not TG_LINK.fullmatch(url) or kind not in ("channel", "group", "forum") or (school and len(school) > 40) \
            or not (course is None or (isinstance(course, int) and not isinstance(course, bool) and 1 <= course <= 6)):
        raise ApiError("bad_input")
    return url


def add_chat(con, v: Viewer, body: dict, peek: dict) -> dict:
    """A chat for the directory (moderators and the admin): a t.me link, a channel, a group or a topics group, for
    everyone or a school and/or a course. The title may be left empty: then the chat's own; peek (its t.me page) brings
    the avatar (a saved photo's path) and the members."""
    chat_input(v, body)
    title = str(body.get("title") or "").strip() or " ".join(str(peek.get("title") or "").split())[:80]
    if len(title) < 2:
        raise ApiError("bad_input")
    kind = body["kind"]
    if c := one(con, f"SELECT id, url FROM chats WHERE status = 'org' AND ({SAME_CHAT})", body["url"].strip(), body["url"].strip(), None):
        if "/+" in c["url"]:
            raise ApiError("conflict", "org")  # a club's closed chat stays off the catalog
        # a club's own channel joins the catalog as that row: still the club's
        con.execute("UPDATE chats SET title = ?, kind = ?, forum = ?, school = ?, course = ?, status = 'live' WHERE id = ?",
                    (title, "channel" if kind == "channel" else "group", int(kind == "forum"), str(body.get("school") or "").strip() or None, body.get("course"), c["id"]))
        return _owned(con, c["id"])
    cid = con.execute("""INSERT INTO chats (title, kind, forum, url, photo, members, school, course, added_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (title, "channel" if kind == "channel" else "group", int(kind == "forum"), body["url"].strip(),
                                                  peek.get("photo"), peek.get("members"), str(body.get("school") or "").strip() or None,
                                                  body.get("course"), v.id, core.now())).lastrowid
    return _owned(con, cid)


def _owned(con, cid: int) -> dict:
    """A catalog chat with the chip of whose it is."""
    c = one(con, "SELECT * FROM chats WHERE id = ?", cid)
    return _chat(c, set(), {c["org_id"]: org_ref(con, _org(con, c["org_id"]))} if c["org_id"] else {})


def chat_refreshed(con, cid: int, peek: dict) -> str | None:
    """The daily look at a chat's t.me page: a new avatar and members count; returns the old photo's path to remove."""
    c = one(con, "SELECT photo FROM chats WHERE id = ?", cid)
    if not c:
        return None
    photo = peek.get("photo") or c["photo"]
    con.execute("UPDATE chats SET photo = ?, members = COALESCE(?, members), about = COALESCE(?, about) WHERE id = ?", (photo, peek.get("members"), peek.get("about"), cid))
    return c["photo"] if c["photo"] and c["photo"] != photo else None


# A chat any student suggests (PLAN item 45): picked in the bot's own
# chat picker, sent to it, or typed in the app's sheet; any chat since Oct 21: a closed
# one by its invite link, which only signed-in students then see (chats()) and the admin sees marked before approving.
HANDLE = re.compile(r"(?:@|(?:https?://)?(?:t|telegram)\.me/(?:s/)?)([A-Za-z][A-Za-z0-9_]{3,31})/?", re.I)


# one chat, whatever the link's case (a public name; an invite hash is case-sensitive) or its Telegram id: url, url, tg_chat_id
SAME_CHAT = "(rtrim(lower(url), '/') = lower(?) AND url NOT LIKE '%/+%') OR rtrim(url, '/') = ? OR (tg_chat_id IS NOT NULL AND tg_chat_id = ?)"


def chat_handle(text: str) -> str | None:
    """A public chat's @name from "@name" or a t.me link, lowercased; None for anything else (an invite link too)."""
    m = HANDLE.fullmatch(text.strip())
    return m.group(1).lower() if m else None


INVITE = re.compile(r"(?:https?://)?(?:t|telegram)\.me/(?:\+|joinchat/)([A-Za-z0-9_-]{8,64})/?", re.I)


def chat_link(text: str) -> str | None:
    """Any chat a student can name: a public one by @name or its t.me link,
    a closed one by its invite link (t.me/+…, t.me/joinchat/…); its t.me address, or None."""
    if name := chat_handle(text):
        return f"https://t.me/{name}"
    m = INVITE.fullmatch(text.strip())
    return f"https://t.me/+{m.group(1)}" if m else None


# t.me paths that are Telegram's own pages, never a chat
TG_PAGES = {"addstickers", "addemoji", "addlist", "addtheme", "bg", "boost", "confirmphone", "contact", "iv", "joinchat",
            "login", "proxy", "setlanguage", "share", "socks", "invoice", "giftcode", "c", "s"}
ANY_LINK = re.compile(r"(?<![\w.-])(?:https?://)?(?:www\.)?(?:t|telegram)\.me/([^\s?#<>\"'«»()]+)", re.I)


def chat_links(msg: dict, at_most: int = 10) -> list[str]:
    """The chats a message (typed or forwarded) links to, in order, each once: their t.me addresses (chat_link). From
    its text or caption and their hidden links (text_link); a whole message "@name" too. Not a post (t.me/name/123,
    t.me/c/...), Telegram's own pages, or a bot (its name ends in "bot")."""
    text = str(msg.get("text") or msg.get("caption") or "")
    if (whole := chat_link(text)) and not whole.lower().endswith("bot"):
        return [whole]
    found = [text] + [str(e.get("url") or "") for e in (msg.get("entities") or msg.get("caption_entities") or []) if e.get("type") == "text_link"]
    out: list[str] = []
    for m in (m for x in found for m in ANY_LINK.finditer(x)):
        parts = m.group(1).rstrip("/.,;:!").split("/")
        if len(parts) == 2 and parts[0].lower() in ("s", "joinchat"):  # a channel's web view; an old invite link
            parts = [parts[1] if parts[0].lower() == "s" else f"+{parts[1]}"]
        if len(parts) != 1 or parts[0].lower() in TG_PAGES or parts[0].lower().endswith("bot"):
            continue  # a post, a topic, Telegram's own page, a bot
        if (url := chat_link(f"t.me/{parts[0]}")) and url not in out:
            out.append(url)
    return out[:at_most]


def known_chat(con, url: str, tg_chat: int | None = None) -> sqlite3.Row | None:
    """The directory's row for this chat, if it has one (live, waiting, or a club's own)."""
    return one(con, f"SELECT * FROM chats WHERE {SAME_CHAT}", url, url, tg_chat)


def suggest_check(con, uid: int, url: str, tg_chat: int | None) -> None:
    """Before the server looks the chat up on t.me: 10 suggestions a day (a club head with several chats
    mustn't hit it), nothing twice: "already in the catalog" or "already waiting"."""
    # a public name in any case; an invite hash is case-sensitive
    if c := one(con, f"SELECT status, url FROM chats WHERE {SAME_CHAT}", url, url, tg_chat):
        if c["status"] != "org":
            raise ApiError("conflict", c["status"])  # live | pending
        if "/+" in c["url"]:
            raise ApiError("conflict", "org")  # a club's closed chat: on its page already, never in the catalog (its invite link)
    if one(con, "SELECT COUNT(*) FROM chats WHERE added_by = ? AND created_at > ? AND status != 'org'", uid, core.now() - 86400)[0] >= 10:
        raise ApiError("rate_limited")


def suggest_chat(con, uid: int, url: str, kind: str, tg_chat: int | None, peek: dict) -> str:
    """The suggestion, waiting (kind: channel, group or forum); the admins and moderators hear of it once a day at most.
    The AI sorts it into a section soon after (sort_next). Its title."""
    title = " ".join(str(peek.get("title") or "").split())[:80] or url.replace("https://t.me/", "@")
    about = " ".join(str(peek.get("about") or "").split())[:300] or None
    with tx(con):
        suggest_check(con, uid, url, tg_chat)  # again inside the write: two taps at once
        if c := one(con, f"SELECT id FROM chats WHERE status = 'org' AND ({SAME_CHAT})", url, url, tg_chat):  # a club's own: it stays theirs
            con.execute("UPDATE chats SET status = 'pending', added_by = ?, created_at = ? WHERE id = ?", (uid, core.now(), c["id"]))
            cid = c["id"]
        else:
            cid = con.execute("""INSERT INTO chats (title, kind, forum, url, tg_chat_id, photo, members, about, added_by, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""", (title, "channel" if kind == "channel" else "group", int(kind == "forum"),
                                                                       url, tg_chat, peek.get("photo"), peek.get("members"), about, uid, core.now())).lastrowid
        con.execute("INSERT OR IGNORE INTO chat_asks (chat_id, user_id) VALUES (?, ?)", (cid, uid))
        notify_staff(con, [r[0] for r in rows(con, "SELECT id FROM users WHERE role IN ('admin', 'moderator')")], "chat_suggested",
                     f"cs:{(core.now() + 5 * 3600) // 86400}")
    return title


def chat_asked_too(con, uid: int, url: str, tg_chat: int | None) -> None:
    """Another student suggested a chat already waiting: they hear too when it's approved (chat_asks)."""
    if c := one(con, f"SELECT id FROM chats WHERE status = 'pending' AND ({SAME_CHAT})", url, url, tg_chat):
        con.execute("INSERT OR IGNORE INTO chat_asks (chat_id, user_id) VALUES (?, ?)", (c["id"], uid))


def approve_chat(con, v: Viewer, cid: int) -> dict:
    """A suggested chat goes into the catalog; each who suggested it hears so once (if they let the bot write)."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    with tx(con):
        c = one(con, "SELECT * FROM chats WHERE id = ? AND status = 'pending'", cid)
        if not c:
            raise core.decided(con, f"chat:{cid}")
        con.execute("UPDATE chats SET status = 'live' WHERE id = ?", (cid,))
        log_action(con, v.id, "chat_approve", f"chat:{cid}", json.dumps({"title": c["title"]}))
        asked = {r[0] for r in rows(con, "SELECT user_id FROM chat_asks WHERE chat_id = ?", cid)} | ({c["added_by"]} if c["added_by"] else set())
        for uid in asked:
            notify(con, uid, "chat_approved", f"ca:{cid}")
        con.execute("DELETE FROM chat_asks WHERE chat_id = ?", (cid,))
    return _owned(con, cid)


# ---------------------------------------------------------------- sections: what a chat is for (Nov 2)
SECTIONS = ("study", "reviews", "admission", "schools", "clubs", "fun")
SORT_AGAIN = 3600  # an AI that didn't answer is asked about the chat again an hour later


def sort_next(con) -> sqlite3.Row | None:
    """The next directory chat (live or waiting) with no section the AI wasn't asked about within the hour, the newest
    suggestion first; marked as asked now (a failed ask waits, the next chat goes)."""
    with tx(con):
        c = one(con, """SELECT id, title, about FROM chats WHERE section IS NULL AND status IN ('live', 'pending')
            AND COALESCE(section_try, 0) < ? ORDER BY status = 'pending' DESC, id DESC LIMIT 1""", core.now() - SORT_AGAIN)
        if c:
            con.execute("UPDATE chats SET section_try = ? WHERE id = ?", (core.now(), c["id"]))
    return c


def sort_save(con, cid: int, section: str) -> None:
    """The AI's section, applied at once and marked unchecked; never over one staff chose meanwhile."""
    if section in SECTIONS:
        con.execute("UPDATE chats SET section = ?, section_ai = 1 WHERE id = ? AND section IS NULL", (section, cid))


def set_chat_section(con, v: Viewer, cid: int, section: object) -> dict:
    """Admin: a chat's section by staff, checked from now on (the AI's mark goes)."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    if section not in SECTIONS:
        raise ApiError("bad_input")
    with tx(con):
        if not one(con, "SELECT 1 FROM chats WHERE id = ?", cid):
            raise ApiError("not_found")
        con.execute("UPDATE chats SET section = ?, section_ai = 0 WHERE id = ?", (section, cid))
        log_action(con, v.id, "chat_section", f"chat:{cid}", str(section))
    return _owned(con, cid)


def delete_chat(con, v: Viewer, cid: int) -> None:
    """A chat out of the catalog, or a suggestion declined, with an Undo for CHAT_UNDO (Admin → Done): the row is kept
    in meta (`chatdel:<id>`), its avatar stays on disk till then (chats_gone). Who suggested or asked for it isn't kept: declined,
    nobody is told (quietly). A second decline of the same suggestion is a conflict."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    with tx(con):
        c = one(con, "SELECT * FROM chats WHERE id = ? AND status IN ('live', 'pending')", cid)
        if not c:
            raise core.decided(con, f"chat:{cid}") if one(con, "SELECT 1 FROM chats WHERE id = ?", cid) or one(con, "SELECT 1 FROM meta WHERE key = ?", f"chatdel:{cid}") else ApiError("not_found")
        con.execute("DELETE FROM chat_asks WHERE chat_id = ?", (cid,))
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"chatdel:{cid}", json.dumps({"at": core.now(), "row": {**dict(c), "added_by": None}})))
        if c["org_id"]:  # a club's chat leaves the catalog, not the club's page
            con.execute("UPDATE chats SET status = 'org' WHERE id = ?", (cid,))
        else:
            con.execute("DELETE FROM chats WHERE id = ?", (cid,))
        log_action(con, v.id, "chat_decline" if c["status"] == "pending" else "chat_remove", f"chat:{cid}", json.dumps({"title": c["title"]}))


CHAT_UNDO = 7 * 86400


def undo_chat(con, v: Viewer, cid: int) -> None:
    """A declined suggestion back in the waiting list, a removed chat back in the catalog, as they were (the opens and
    the askers aside). Not when the same chat came back meanwhile."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    with tx(con):
        by = one(con, "SELECT actor_id FROM audit_log WHERE target = ? AND action IN ('chat_decline', 'chat_remove') ORDER BY id DESC LIMIT 1", f"chat:{cid}")
        if by and by[0] != v.id and v.role != "admin":  # a moderator takes back his own; the admin anyone's
            raise ApiError("forbidden")
        k = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"chatdel:{cid}")
        if not k:
            raise ApiError("not_found")
        row = json.loads(k[0])["row"]
        now = one(con, "SELECT * FROM chats WHERE id = ?", cid)
        if now and now["status"] == "org":  # a club's: only its catalog status comes back
            con.execute("UPDATE chats SET status = ? WHERE id = ?", (row["status"], cid))
        elif now or one(con, f"SELECT 1 FROM chats WHERE {SAME_CHAT}", row["url"], row["url"], row["tg_chat_id"]):
            raise ApiError("conflict", "again")
        else:
            if row["org_id"] and not one(con, "SELECT 1 FROM orgs WHERE id = ?", row["org_id"]):
                row["org_id"] = None
            con.execute(f"INSERT INTO chats ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
        log_action(con, v.id, "chat_undo", f"chat:{cid}")


def chats_gone(con) -> list[str]:
    """The bot's round: removed chats past their Undo; their avatars when nothing else shows them (to delete)."""
    out = []
    with tx(con):
        for k, val in rows(con, "SELECT key, value FROM meta WHERE key LIKE 'chatdel:%'"):
            d = json.loads(val)
            if d["at"] + CHAT_UNDO <= core.now():
                con.execute("DELETE FROM meta WHERE key = ?", (k,))
                if d["row"]["photo"]:
                    out.append(d["row"]["photo"])
    return [p for p in out if photo_free(con, p)]


# ---------------------------------------------------------------- an org's own chats (PLAN 86)
# A club's or school's Telegram chats on its page: channels, groups, topics groups, open and closed. chats.org_id says
# whose a chat is (a catalog row shows on the page too; one linked only from Studio waits as status 'org', out of the
# catalog); one public channel is the MAIN one, with the big Subscribe button (and later the userbot mirror's source).
# A closed chat shows with a lock, its title, photo and members, and no way in: its invite link never leaves Studio.
# The cards come from the chat's t.me page, and once its President adds our bot, from Telegram itself (bot.py
# refresh_chats: getChat, getChatMemberCount); the bot never reads or keeps a message.

ORG_CHATS = 12  # a club's chats on its page at most


def _closed(c: sqlite3.Row) -> bool:
    return "/+" in c["url"]


def org_chats(con, oid: int, editor: bool = False) -> list[dict]:
    """The org's chats, the main channel first, then by size. editor (Studio): the invite links too and whether our bot
    keeps the card."""
    out = []
    for c in rows(con, "SELECT * FROM chats WHERE org_id = ? ORDER BY main DESC, COALESCE(members, -1) DESC, title", oid):
        x = {"id": c["id"], "title": c["title"], "kind": "forum" if c["forum"] else c["kind"], "members": c["members"], "about": c["about"],
             "photo": f"media/{c['photo']}.t.webp" if c["photo"] else None, "closed": _closed(c), "main": bool(c["main"]),
             "url": c["url"] if editor or not _closed(c) else None}
        out.append({**x, "bot": c["tg_chat_id"] is not None, "mirror": bool(c["mirror"])} if editor else x)
    return out


def may_chats(con, v: Viewer, oid: int) -> sqlite3.Row:
    """Who links an org's chats: its Vice+ (the profile right; the owner said "the president", Studio's profile is Vice+
    since Oct 5), and the admin (AdminChats links any chat; here: a school with no President yet). The org."""
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND status != 'archived'", oid)
    if not o:
        raise ApiError("not_found")
    if not can(con, v, oid, "profile") and v.role != "admin":
        raise ApiError("forbidden")
    return o


def add_org_chat(con, v: Viewer, oid: int, url: str, peek: dict) -> tuple[list[dict], list[str]]:
    """A chat for the org by its link (chat_link: @name, a t.me link or an invite link), looked up on its t.me page
    (peek). A chat in the catalog becomes the org's (another org's stays theirs); a new one waits out of the catalog.
    The first public channel is the main one. Studio's list, and the avatar to remove when the catalog's is kept."""
    if not peek.get("ok"):
        raise ApiError("unavailable", "telegram")
    if peek.get("members") is None:
        raise ApiError("bad_input", "notchat")  # a person, a bot, a dead link
    with tx(con):
        may_chats(con, v, oid)
        c = one(con, f"SELECT * FROM chats WHERE {SAME_CHAT}", url, url, None)
        if c and c["org_id"] not in (None, oid):
            raise ApiError("conflict", "taken")  # the app's team sorts it out (the admin edits both clubs' lists)
        if c and c["org_id"] is None and v.role != "admin":
            raise ApiError("conflict", "catalog")  # a catalog chat is the admin's to give to a club
        if (not c or c["org_id"] != oid) and one(con, "SELECT COUNT(*) FROM chats WHERE org_id = ?", oid)[0] >= ORG_CHATS:
            raise ApiError("conflict", "limit")
        if c:  # the catalog's row keeps its avatar (the daily look renews it)
            con.execute("UPDATE chats SET org_id = ? WHERE id = ?", (oid, c["id"]))
            cid, gone = c["id"], [peek.get("photo")]
        else:
            title = " ".join(str(peek.get("title") or "").split())[:80] or url.replace("https://t.me/", "@")
            about = " ".join(str(peek.get("about") or "").split())[:300] or None
            cid, gone = con.execute("""INSERT INTO chats (title, kind, forum, url, photo, members, about, added_by, created_at, status, org_id)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 'org', ?)""", (title, "channel" if peek.get("channel") else "group", url, peek.get("photo"),
                                                                  peek["members"], about, v.id, core.now(), oid)).lastrowid, []
        ch = one(con, "SELECT * FROM chats WHERE id = ?", cid)
        if ch["kind"] == "channel" and not _closed(ch) and not one(con, "SELECT 1 FROM chats WHERE org_id = ? AND main = 1", oid):
            con.execute("UPDATE chats SET main = 1 WHERE id = ?", (cid,))
        _chats_audit(con, v, oid, f"add {url}")
    return org_chats(con, oid, True), [p for p in gone if p and photo_free(con, p)]


def main_org_chat(con, v: Viewer, oid: int, cid: int) -> list[dict]:
    """This public channel is the org's main one (the Subscribe button); the one before stays on the page."""
    with tx(con):
        may_chats(con, v, oid)
        c = one(con, "SELECT * FROM chats WHERE id = ? AND org_id = ?", cid, oid)
        if not c:
            raise ApiError("not_found")
        if c["kind"] != "channel" or _closed(c):
            raise ApiError("bad_input", "notchannel")  # nobody can subscribe to a group or a closed channel from the page
        con.execute("UPDATE chats SET main = 0 WHERE org_id = ? AND main = 1", (oid,))
        con.execute("UPDATE chats SET main = 1 WHERE id = ?", (cid,))
        _chats_audit(con, v, oid, f"main {c['url']}")
    return org_chats(con, oid, True)


def mirror_org_chat(con, v: Viewer, oid: int, cid: int, on: object) -> list[dict]:
    """Studio's switch under the main channel (PLAN 86 part 2): its posts in the club's news, or not. The posts already
    mirrored stay the club's news; off, the userbot leaves the channel."""
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    with tx(con):
        may_chats(con, v, oid)
        c = one(con, "SELECT * FROM chats WHERE id = ? AND org_id = ?", cid, oid)
        if not c:
            raise ApiError("not_found")
        con.execute("UPDATE chats SET mirror = ? WHERE id = ?", (int(on), cid))
        _chats_audit(con, v, oid, f"mirror {'on' if on else 'off'} {c['url']}")
    return org_chats(con, oid, True)


def drop_org_chat(con, v: Viewer, oid: int, cid: int) -> tuple[list[dict], list[str]]:
    """The chat off the org's page: one of its own goes, a catalog row stays in the catalog, nobody's. Studio's list and
    the avatar to remove."""
    with tx(con):
        may_chats(con, v, oid)
        c = one(con, "SELECT * FROM chats WHERE id = ? AND org_id = ?", cid, oid)
        if not c:
            raise ApiError("not_found")
        gone = _unlink(con, c)
        _chats_audit(con, v, oid, f"drop {c['url']}")
    return org_chats(con, oid, True), [gone] if gone and photo_free(con, gone) else []


def set_chat_org(con, v: Viewer, cid: int, oid: int | None) -> dict:
    """AdminChats: whose a catalog chat is (t.me/kbtusite is SITE's), or nobody's."""
    if v.role != "admin":
        raise ApiError("forbidden")
    if oid is not None and (not isinstance(oid, int) or isinstance(oid, bool) or not one(con, "SELECT 1 FROM orgs WHERE id = ? AND status != 'archived'", oid)):
        raise ApiError("bad_input")
    with tx(con):
        c = one(con, "SELECT * FROM chats WHERE id = ?", cid)
        if not c:
            raise ApiError("not_found")
        if c["status"] == "org" and oid is None:
            raise ApiError("bad_input")  # out of the catalog and nobody's: removed from the club's list instead
        if c["org_id"] != oid:
            con.execute("UPDATE chats SET org_id = ?, main = 0 WHERE id = ?", (oid, cid))
            if c["main"] and (nxt := one(con, """SELECT id FROM chats WHERE org_id = ? AND kind = 'channel' AND url NOT LIKE '%/+%'
                    ORDER BY COALESCE(members, -1) DESC LIMIT 1""", c["org_id"])):  # the old org's next public channel
                con.execute("UPDATE chats SET main = 1 WHERE id = ?", (nxt["id"],))
            if oid and c["kind"] == "channel" and not _closed(c) and not one(con, "SELECT 1 FROM chats WHERE org_id = ? AND main = 1", oid):
                con.execute("UPDATE chats SET main = 1 WHERE id = ?", (cid,))
            log_action(con, v.id, "chat_org", f"chat:{cid}", str(oid or ""))
    c = one(con, "SELECT * FROM chats WHERE id = ?", cid)
    return _chat(c, set(), {oid: org_ref(con, _org(con, oid))} if oid else {})


def _unlink(con, c: sqlite3.Row) -> str | None:
    """A chat off its org: its own row goes, a catalog row stays in the catalog, nobody's. A closed one waiting for the
    catalog only through its club goes too: nobody's, its invite link must not end up there. Its avatar, to remove if free."""
    if c["status"] == "org" or (c["status"] == "pending" and _closed(c)):
        con.execute("DELETE FROM chats WHERE id = ?", (c["id"],))
        return c["photo"]
    con.execute("UPDATE chats SET org_id = NULL, main = 0 WHERE id = ?", (c["id"],))
    return None


def _chats_audit(con, v: Viewer, oid: int, what: str) -> None:
    log_action(con, v.id, "org_chats", f"org:{oid}", what)


PICK_TTL = 600  # "Link a group / channel": Telegram's own picker, then our bot added there, within ten minutes


def chat_pick(con, v: Viewer, oid: int) -> None:
    """Studio's "Link a group / channel" (owner, Nov 5: no typing @names): Telegram's add-the-bot picker opens next; the
    chat our bot lands in from me in the next ten minutes becomes this org's (pick_claim). One pending pick a person."""
    may_chats(con, v, oid)
    tg = one(con, "SELECT tg_id FROM users WHERE id = ?", v.id)["tg_id"]
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"chpick:{tg}", f"{oid}:{core.now() + PICK_TTL}"))


def pick_claim(con, tg_from: int, chat: dict, invite: str | None) -> int | None:
    """Our bot just landed in a chat, added by someone with a fresh chat_pick: the chat is that org's now (the same rules
    as add_org_chat: another org's stays theirs, a catalog chat is the admin's to give, the page's limit). Its id."""
    key = f"chpick:{tg_from}"
    m = one(con, "SELECT value FROM meta WHERE key = ?", key)
    if not m:
        return None
    oid, until = map(int, m["value"].split(":"))
    u = one(con, "SELECT id, role FROM users WHERE tg_id = ? AND banned_at IS NULL", tg_from)
    url = f"https://t.me/{chat['username']}" if chat.get("username") else invite
    if until < core.now() or not u:
        con.execute("DELETE FROM meta WHERE key = ?", (key,))
        return None
    if not url:  # a plain member of a closed group, or a basic group before Telegram upgrades it: the pick waits for the admin rights
        return None
    v = Viewer(u["id"], u["role"], bool(one(con, "SELECT 1 FROM students WHERE user_id = ?", u["id"])))
    with tx(con):
        try:
            may_chats(con, v, oid)
        except ApiError:
            return None
        c = one(con, f"SELECT * FROM chats WHERE {SAME_CHAT}", url, url, chat["id"])
        held = one(con, "SELECT * FROM chats WHERE tg_chat_id = ?", chat["id"])  # the bot's chat id is the proof (a closed chat's links differ)
        if held and (not c or held["id"] != c["id"]):
            c = held
        if c and (c["org_id"] not in (None, oid) or c["org_id"] is None and v.role != "admin"):
            return None
        if (not c or c["org_id"] != oid) and one(con, "SELECT COUNT(*) FROM chats WHERE org_id = ?", oid)[0] >= ORG_CHATS:
            return None
        kind = "channel" if chat.get("type") == "channel" else "group"
        if c:
            con.execute("UPDATE chats SET org_id = ?, tg_chat_id = ? WHERE id = ?", (oid, chat["id"], c["id"]))
            cid = c["id"]
        else:
            title = " ".join(str(chat.get("title") or "").split())[:80] or "Telegram"
            cid = con.execute("""INSERT INTO chats (title, kind, forum, url, tg_chat_id, added_by, created_at, status, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'org', ?)""", (title, kind, int(bool(chat.get("is_forum"))), url, chat["id"], v.id, core.now(), oid)).lastrowid
        ch = one(con, "SELECT * FROM chats WHERE id = ?", cid)
        if ch["kind"] == "channel" and not _closed(ch) and not one(con, "SELECT 1 FROM chats WHERE org_id = ? AND main = 1", oid):
            con.execute("UPDATE chats SET main = 1 WHERE id = ?", (cid,))
        _chats_audit(con, v, oid, f"pick {url}")
        con.execute("DELETE FROM meta WHERE key = ?", (key,))  # spent only once it worked
    return cid


def bot_added(con, tg_from: int, chat: dict, invite: str | None = None, cid: int | None = None) -> int | None:
    """Our bot is in a chat now: which org chat it is, among those of the orgs the one who added it may edit (the admin:
    any) and not yet kept by the bot. A group by Studio's link says (its /start oc_<id>); a channel can't carry one, so
    by its @name, its invite link (getChat gives one to an admin bot), or its exact title (a closed channel's link on
    the page may not be its primary one; not for the admin, who may edit every club: a title is no proof which). The chat's id."""
    u = one(con, "SELECT id, role FROM users WHERE tg_id = ? AND banned_at IS NULL", tg_from)
    if not u:
        return None
    v = Viewer(u["id"], u["role"], bool(one(con, "SELECT 1 FROM students WHERE user_id = ?", u["id"])))
    name = str(chat.get("username") or "").lower()
    for c in rows(con, "SELECT * FROM chats WHERE org_id IS NOT NULL AND tg_chat_id IS NULL AND (? IS NULL OR id = ?) ORDER BY id", cid, cid):
        if v.role != "admin" and not can(con, v, c["org_id"], "profile"):
            continue
        if cid or (name and c["url"].rstrip("/").lower() == f"https://t.me/{name}") or (invite and c["url"].rstrip("/") == invite.rstrip("/")) \
                or (v.role != "admin" and chat.get("type") == "channel" and c["kind"] == "channel" and c["title"] == chat.get("title")):
            con.execute("UPDATE chats SET tg_chat_id = ? WHERE id = ?", (chat["id"], c["id"]))
            return c["id"]
    return None


def bot_left(con, tg_chat: int) -> None:
    """Our bot is out of a chat: its card comes from the t.me page again."""
    con.execute("UPDATE chats SET tg_chat_id = NULL WHERE tg_chat_id = ? AND org_id IS NOT NULL", (tg_chat,))


def chat_card(con, cid: int, card: dict) -> str | None:
    """The bot's look at a chat it sits in: title, about, members, avatar (a saved photo's path); the old avatar to remove."""
    c = one(con, "SELECT title, about, photo FROM chats WHERE id = ?", cid)
    if not c:
        return None
    title = " ".join(str(card.get("title") or "").split())[:80] or c["title"]
    about = " ".join(str(card.get("about") or "").split())[:300] if card.get("about") is not None else c["about"]
    photo = card.get("photo") or c["photo"]
    con.execute("UPDATE chats SET title = ?, about = ?, photo = ?, members = COALESCE(?, members) WHERE id = ?", (title, about or None, photo, card.get("members"), cid))
    return c["photo"] if c["photo"] and c["photo"] != photo else None


def photo_free(con, path: str) -> bool:
    """No chat, file record or Telegram photo copy shows this picture any more (pictures are named by their content: shared)."""
    return not con.execute("""SELECT 1 FROM chats WHERE photo = :p UNION ALL SELECT 1 FROM files WHERE path = :p
        UNION ALL SELECT 1 FROM users WHERE tg_photo_path = :p""", {"p": path}).fetchone()


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .clubs import orgs  # noqa: E402
from .seats import notify, notify_staff  # noqa: E402
from .teams import invite  # noqa: E402
