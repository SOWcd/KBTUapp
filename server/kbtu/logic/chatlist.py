"""Telegram chats: KBTU's directory and an org's own chats."""
from __future__ import annotations

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
            "org": (orgs or {}).get(c["org_id"])}


def chats(con, v: Viewer) -> dict:
    """Curated Telegram chats (§4.11), the biggest first (A8, owner Oct 23); "for you" are the ones aimed at my school and
    course plus those for everyone (my school and course first, by size within); a club's or school's chat says whose
    (PLAN 86; the app no longer ticks the ones I opened: the owner didn't understand it, Oct 22)."""
    st = one(con, "SELECT school, course FROM students WHERE user_id = ?", v.id) if v.student else None
    opened = {r[0] for r in rows(con, "SELECT chat_id FROM chat_opens WHERE user_id = ?", v.id)} if v.student else set()
    # a closed chat's invite link (t.me/+…) only to signed-in students: it lets anyone in (owner, Oct 21: any chat)
    live = rows(con, "SELECT * FROM chats WHERE status = 'live' ORDER BY COALESCE(members, -1) DESC, title")
    found = {c["org_id"] for c in live if c["org_id"]}
    orgs = {o["id"]: org_ref(con, o) for o in rows(con, f"SELECT * FROM orgs WHERE id IN ({_qs(found)})", *found)} if found else {}
    everything = [_chat(c, opened, orgs) for c in live if v.student or "/+" not in c["url"]]
    fits = lambda c: (c["school"] in (None, st["school"])) and (c["course"] in (None, st["course"]))  # noqa: E731
    aim = lambda c: (c["school"] is not None) * 2 + (c["course"] is not None)  # noqa: E731  — my school and course first, everyone's last
    mine = sorted((c for c in everything if st and fits(c)), key=lambda c: -aim(c))
    out = {"forYou": mine if st else [c for c in everything if c["school"] is None and c["course"] is None], "all": everything}
    if v.role in ("admin", "moderator"):  # the suggestions waiting for a look, newest first
        waiting = rows(con, "SELECT * FROM chats WHERE status = 'pending' ORDER BY id DESC")
        found = {c["org_id"] for c in waiting if c["org_id"]}
        whose = {o["id"]: org_ref(con, o) for o in rows(con, f"SELECT * FROM orgs WHERE id IN ({_qs(found)})", *found)} if found else {}
        out["pending"] = [{**_chat(c, set(), whose), "at": c["created_at"]} for c in waiting]  # whose it is, for the moderator
    return out


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


# A chat any student suggests (PLAN item 45, owner Oct 20: "as Telegram-native as possible"): picked in the bot's own
# chat picker, sent to it, or typed in the app's sheet; any chat since Oct 21 (owner: "any group, any channel"): a closed
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
    """Any chat a student can name (owner, Oct 21: "any group, any channel"): a public one by @name or its t.me link,
    a closed one by its invite link (t.me/+…, t.me/joinchat/…); its t.me address, or None."""
    if name := chat_handle(text):
        return f"https://t.me/{name}"
    m = INVITE.fullmatch(text.strip())
    return f"https://t.me/+{m.group(1)}" if m else None


def suggest_check(con, uid: int, url: str, tg_chat: int | None) -> None:
    """Before the server looks the chat up on t.me: 10 suggestions a day (owner, Oct 20: a club head with several chats
    mustn't hit it), nothing twice: "already in the catalog" or "already waiting" (owner, Oct 20)."""
    # a public name in any case; an invite hash is case-sensitive
    if c := one(con, f"SELECT status, url FROM chats WHERE {SAME_CHAT}", url, url, tg_chat):
        if c["status"] != "org":
            raise ApiError("conflict", c["status"])  # live | pending
        if "/+" in c["url"]:
            raise ApiError("conflict", "org")  # a club's closed chat: on its page already, never in the catalog (its invite link)
    if one(con, "SELECT COUNT(*) FROM chats WHERE added_by = ? AND created_at > ? AND status != 'org'", uid, core.now() - 86400)[0] >= 10:
        raise ApiError("rate_limited")


def suggest_chat(con, uid: int, url: str, kind: str, tg_chat: int | None, peek: dict) -> str:
    """The suggestion, waiting; the admins and moderators hear of it once a day at most. Its title."""
    title = " ".join(str(peek.get("title") or "").split())[:80] or url.replace("https://t.me/", "@")
    with tx(con):
        suggest_check(con, uid, url, tg_chat)  # again inside the write: two taps at once
        if c := one(con, f"SELECT id FROM chats WHERE status = 'org' AND ({SAME_CHAT})", url, url, tg_chat):  # a club's own: it stays theirs
            con.execute("UPDATE chats SET status = 'pending', added_by = ?, created_at = ? WHERE id = ?", (uid, core.now(), c["id"]))
        else:
            con.execute("""INSERT INTO chats (title, kind, forum, url, tg_chat_id, photo, members, added_by, created_at, status)
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 'pending')""", (title, kind, url, tg_chat, peek.get("photo"), peek.get("members"), uid, core.now()))
        for (aid,) in rows(con, "SELECT id FROM users WHERE role IN ('admin', 'moderator')"):
            notify(con, aid, "chat_suggested", f"cs:{(core.now() + 5 * 3600) // 86400}")
    return title


def approve_chat(con, v: Viewer, cid: int) -> dict:
    """A suggested chat goes into the catalog; whoever suggested it hears so."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    with tx(con):
        c = one(con, "SELECT * FROM chats WHERE id = ? AND status = 'pending'", cid)
        if not c:
            raise ApiError("not_found")
        con.execute("UPDATE chats SET status = 'live' WHERE id = ?", (cid,))
        if c["added_by"]:
            notify(con, c["added_by"], "chat_approved", f"ca:{cid}")
    return _owned(con, cid)


def delete_chat(con, v: Viewer, cid: int) -> str | None:
    """A chat out of the catalog, or a suggestion declined; its avatar's path when nothing else shows it (to remove)."""
    if v.role not in ("admin", "moderator"):
        raise ApiError("forbidden")
    c = one(con, "SELECT photo, org_id FROM chats WHERE id = ?", cid)
    if c and c["org_id"]:  # a club's chat leaves the catalog, not the club's page
        con.execute("UPDATE chats SET status = 'org' WHERE id = ?", (cid,))
        return None
    con.execute("DELETE FROM chats WHERE id = ?", (cid,))
    return c["photo"] if c and c["photo"] and photo_free(con, c["photo"]) else None


# ---------------------------------------------------------------- an org's own chats (PLAN 86, owner Oct 22 and 26)
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


def chat_orgs(con, v: Viewer) -> list[sqlite3.Row]:
    """The orgs whose chats I link (may_chats: Vice+), for the bot's "is this your club's channel?" (owner, Oct 25)."""
    return [o for o in rows(con, """SELECT o.* FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ?
        AND o.status != 'archived' ORDER BY o.name""", v.id) if can(con, v, o["id"], "profile")]


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
    """AdminChats: whose a catalog chat is (owner, Oct 22: t.me/kbtusite is SITE's), or nobody's."""
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
    """No chat and no file record shows this picture any more (pictures are named by their content: shared)."""
    return not one(con, "SELECT 1 FROM chats WHERE photo = ?", path) and not one(con, "SELECT 1 FROM files WHERE path = ?", path)


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core  # noqa: E402
from .clubs import orgs  # noqa: E402
from .seats import notify  # noqa: E402
from .teams import invite  # noqa: E402
