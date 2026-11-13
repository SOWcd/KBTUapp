"""A club's group moderated for swearing (owner, Nov 13), as the popular group bots do, but ours and reported in Studio.

Off by default. A linked group's switch (chats.swear) is its club's President's or Vice's; on only when our bot may delete
and restrict there (app.py asks Telegram). Then the bot (bot._swear) reads each new or edited message's text and caption
for a word of swear.py's lists: the message goes, its author gets a warning by a link to their id (never their words),
and the third within 7 days mutes them for an hour; the count starts over. A chat's admins are never muted. A hit is one
row: chat, Telegram id (and app id when known), the matched stem, when, its warning number, whether it muted. Nothing for
clean messages, nothing at all where it's off; 90 days (daily). The club's President, Vice and Heads see 30 days."""
from __future__ import annotations

from ..db import tx
from . import core
from .core import PERSON_COLS, ApiError, log_action, one, person_ref, rows

WARNS = 3                # the warning that mutes
WINDOW = 7 * 86400       # warnings older than this don't count
MUTE = 3600
KEEP = 90 * 86400
REPORT = 30 * 86400
SWITCH = ("president", "vice")
READ = ("president", "vice", "head")


def _lead(con, v: core.Viewer, oid: int, roles: tuple) -> None:
    if not (v.student and one(con, f"""SELECT 1 FROM org_members m JOIN orgs o ON o.id = m.org_id JOIN users u ON u.id = m.user_id
            WHERE m.org_id = ? AND m.user_id = ? AND o.status != 'archived' AND u.banned_at IS NULL
            AND m.role IN ({",".join("?" * len(roles))})""", oid, v.id, *roles)):
        raise ApiError("forbidden")


def target(con, v: core.Viewer, oid: int, cid: int) -> int:
    """The Telegram id of this club's linked group, whose switch this President or Vice may flip."""
    _lead(con, v, oid, SWITCH)
    c = one(con, "SELECT tg_chat_id FROM chats WHERE id = ? AND org_id = ? AND kind = 'group' AND tg_chat_id IS NOT NULL", cid, oid)
    if not c:
        raise ApiError("not_found")
    return c[0]


def switch(con, v: core.Viewer, oid: int, cid: int, on: bool) -> bool:
    """On or off (the caller checked the bot's rights for on); True: it changed, so the bot tells the chat."""
    with tx(con):
        target(con, v, oid, cid)
        if bool(one(con, "SELECT swear FROM chats WHERE id = ?", cid)[0]) == on:
            return False
        con.execute("UPDATE chats SET swear = ? WHERE id = ?", (int(on), cid))
        log_action(con, v.id, "org_chats", f"org:{oid}", f"swear {'on' if on else 'off'} {cid}")
    return True


def forget(con, cid: int) -> None:
    """The chat left its club (unlinked, given to another, the bot out): off, and its hits go."""
    con.execute("DELETE FROM swear_hits WHERE chat_id = ?", (cid,))
    con.execute("UPDATE chats SET swear = 0 WHERE id = ? AND swear = 1", (cid,))


def chat_on(con, tg_chat: int) -> int | None:
    """Our card of a club's group whose switch is on, by its Telegram id."""
    r = one(con, "SELECT id FROM chats WHERE tg_chat_id = ? AND swear = 1 AND org_id IS NOT NULL", tg_chat)
    return r[0] if r else None


def hit(con, cid: int, tg: int, stem: str) -> tuple[int, int]:
    """A hit recorded: its row and its warning number, 1 + those since the last mute-warning within 7 days."""
    t = core.now()
    with tx(con):
        last = one(con, "SELECT MAX(id) FROM swear_hits WHERE chat_id = ? AND tg_id = ? AND warn = ?", cid, tg, WARNS)[0] or 0
        n = one(con, "SELECT COUNT(*) FROM swear_hits WHERE chat_id = ? AND tg_id = ? AND id > ? AND at > ?", cid, tg, last, t - WINDOW)[0] + 1
        u = one(con, "SELECT id FROM users WHERE tg_id = ?", tg)
        rid = con.execute("INSERT INTO swear_hits (chat_id, tg_id, user_id, stem, at, warn) VALUES (?, ?, ?, ?, ?, ?)",
                          (cid, tg, u[0] if u else None, stem, t, n)).lastrowid
    return rid, n


def muted(con, rid: int) -> None:
    con.execute("UPDATE swear_hits SET muted = 1 WHERE id = ?", (rid,))


def undo(con, rid: int) -> None:
    """The bot couldn't delete the message (its rights taken away): no hit, no warning."""
    con.execute("DELETE FROM swear_hits WHERE id = ?", (rid,))


def sweep(con) -> None:
    con.execute("DELETE FROM swear_hits WHERE at < ?", (core.now() - KEEP,))


def report(con, v: core.Viewer, oid: int) -> list[dict]:
    """The club's groups, last 30 days, a row a person (the most warned first): the club's own people by name, anyone
    else "a chat member" (no Telegram id leaves the server); warnings, the stems, mutes."""
    _lead(con, v, oid, READ)
    by: dict[int, dict] = {}
    for h in rows(con, """SELECT h.tg_id, h.stem, h.muted FROM swear_hits h JOIN chats c ON c.id = h.chat_id
            WHERE c.org_id = ? AND h.at >= ? ORDER BY h.id""", oid, core.now() - REPORT):
        x = by.setdefault(h["tg_id"], {"warns": 0, "stems": {}, "mutes": 0})
        x["warns"] += 1
        x["mutes"] += h["muted"]
        x["stems"][h["stem"]] = x["stems"].get(h["stem"], 0) + 1
    ours = {p["tg_id"]: person_ref(p) for p in rows(con, f"""SELECT u.tg_id, {PERSON_COLS} FROM org_members m JOIN users u ON u.id = m.user_id
        LEFT JOIN students s ON s.user_id = u.id WHERE m.org_id = ? AND u.tg_id IN ({",".join("?" * len(by))})""", oid, *by)} if by else {}
    out = [{"person": ours.get(tg), "warns": x["warns"], "mutes": x["mutes"], "stems": sorted(x["stems"], key=lambda s: -x["stems"][s])}
           for tg, x in by.items()]
    return sorted(out, key=lambda r: (-r["warns"], -r["mutes"]))
