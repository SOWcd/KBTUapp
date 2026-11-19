"""The tree of a club's Telegram groups (for DMP): organisation -> its main group -> its departments' groups,
then its other groups. Seen by the club's Vice+ in Studio -> Chats and by DMP (Head+) and the admin for every club.

A group's place comes from what the server already knows: a chat sync link (chatsync.py, the creator's: main or a
department) wins; else the club's own label (chat_place), one tap in Studio. A label is only a label: it never links the
sync and never adds or removes anyone (only the creator's `admin chatsync link` does that). Counts only: a group's member
count is the one the bot's daily card look already keeps (chats.members); no Telegram call here, no names or ids of
people. Telegram gives a bot no list of its chats: a group shows once it is the club's in our catalog or sync."""
from __future__ import annotations

import json
import sqlite3

from ..db import tx
from . import core
from .core import ApiError, Viewer, _by_id, log_action, one, org_ref, overseer, rows
from .chatlist import may_chats

PLACES = ("main", "dept", "other")


def _node(c: sqlite3.Row | None, s: sqlite3.Row | None) -> dict:
    """One group: its card (c) and its sync link (s), either may be missing."""
    return {"id": c["id"] if c else None, "title": c["title"] if c else None, "members": c["members"] if c else None,
            "forum": bool(c and c["forum"]), "bot": bool(s or (c and c["tg_chat_id"] is not None)),
            "sync": ("paused" if s["paused"] else "on") if s else "off",
            "at": (s["last_date"] or s["created_at"]) if s else None}  # a roster change is known only where the sync hears it


def _guess(node: dict, depts: list[dict], has_main: bool) -> dict | None:
    """A loose group's likely place, offered first (never applied): a department's name in its title, else a topics
    group where the club has no main one."""
    title = (node["title"] or "").casefold()
    hits = [d for d in depts if len(d["name"]) >= 3 and d["name"].casefold() in title]
    if len(hits) == 1:
        return {"place": "dept", "tag": hits[0]["id"]}
    return {"place": "main"} if node["forum"] and not has_main else None


def trees(con, oid: int | None = None) -> list[dict]:
    """Every organisation's tree (oid: that one alone). Each fact is read once for all of them, never club by club."""
    by = "AND o.id = ?" if oid else "AND (o.kind IN ('club', 'school', 'council') OR o.can_oversee = 1)"
    orgs = rows(con, f"SELECT o.* FROM orgs o WHERE o.status != 'archived' {by} ORDER BY o.official DESC, o.name", *([oid] if oid else []))
    ids = {o["id"] for o in orgs}
    depts: dict[int, list[dict]] = {}
    for t in rows(con, "SELECT id, org_id, name, color FROM org_tags WHERE department = 1 ORDER BY name"):
        if t["org_id"] in ids:
            depts.setdefault(t["org_id"], []).append({"id": t["id"], "name": t["name"], "color": t["color"]})
    syncs = {s["chat_id"]: s for s in rows(con, "SELECT * FROM chat_sync") if s["org_id"] in ids}
    cards: dict[int, list[sqlite3.Row]] = {}
    for c in rows(con, "SELECT id, org_id, title, members, forum, tg_chat_id FROM chats WHERE kind = 'group' AND org_id IS NOT NULL "
                       "ORDER BY COALESCE(members, -1) DESC, title"):
        if c["org_id"] in ids:
            cards.setdefault(c["org_id"], []).append(c)
    # a label counts only while the group is still that club's (given to another club, it is loose there)
    places = {p["chat_id"]: p for p in rows(con, "SELECT p.* FROM chat_place p JOIN chats c ON c.id = p.chat_id AND c.org_id = p.org_id")}
    logos = _by_id(con, "files", (o["logo_file_id"] for o in orgs))
    out = []
    for o in orgs:
        ds = depts.get(o["id"], [])
        main, other, loose = None, [], []
        under: dict[int, list[dict]] = {d["id"]: [] for d in ds}
        seen: set[int] = set()

        def put(n: dict, kind: str, tag: int | None, how: str) -> None:
            nonlocal main
            n["by"] = how
            if kind == "main" and main is None:
                main, n["place"], n["tag"] = n, "main", None
            elif kind == "dept" and tag in under:
                under[tag].append(n)
                n["place"], n["tag"] = "dept", tag
            else:
                other.append(n)
                n["place"], n["tag"] = "other", None

        hand = []
        for c in cards.get(o["id"], []):
            s = syncs.get(c["tg_chat_id"]) if c["tg_chat_id"] is not None else None
            if s and s["org_id"] == o["id"]:
                seen.add(s["chat_id"])
                put(_node(c, s), s["kind"], s["tag_id"], "sync")
            elif p := places.get(c["id"]):
                hand.append((c, p))
            else:
                loose.append(_node(c, None))
        for s in syncs.values():  # linked by the creator, no card in our catalog
            if s["org_id"] == o["id"] and s["chat_id"] not in seen:
                put(_node(None, s), s["kind"], s["tag_id"], "sync")
        for c, p in hand:  # after the sync's: a synced main group holds the top
            put(_node(c, None), p["place"], p["tag_id"], "hand")
        for n in loose:
            n["by"], n["place"], n["tag"], n["guess"] = None, None, None, _guess(n, ds, main is not None)
        nodes = [*([main] if main else []), *(n for d in under.values() for n in d), *other, *loose]
        out.append({"org": org_ref(con, o, logos), "groups": len(nodes), "kept": sum(n["sync"] == "on" for n in nodes),
                    "last": max((n["at"] for n in nodes if n["at"]), default=None), "main": main,
                    "depts": [{**d, "chats": under[d["id"]]} for d in ds], "other": other, "loose": loose})
    return out


def club(con, v: Viewer, oid: int) -> dict:
    """Studio -> Chats: the club's own tree, for whoever edits its chats (its Vice+, the admin)."""
    may_chats(con, v, oid)
    return trees(con, oid)[0]


def all_clubs(con, v: Viewer) -> list[dict]:
    """DMP's panel: every organisation's tree (DMP Head+ and the admin)."""
    if not overseer(con, v):
        raise ApiError("forbidden")
    return trees(con)


def place(con, v: Viewer, oid: int, cid: int, where: object, tag: object = None) -> dict:
    """Where a group of the club goes in its tree: 'main', 'dept' (tag: the club's department), 'other', or None (loose
    again). Only a label: the sync stays the creator's (admin chatsync link), so no member is added or removed here; a
    synced group's place is its link's (conflict synced)."""
    if where is not None and where not in PLACES or (where == "dept") != (isinstance(tag, int) and not isinstance(tag, bool)):
        raise ApiError("bad_input")
    with tx(con):
        may_chats(con, v, oid)
        c = one(con, "SELECT id, tg_chat_id FROM chats WHERE id = ? AND org_id = ? AND kind = 'group'", cid, oid)
        if not c:
            raise ApiError("not_found")
        if c["tg_chat_id"] is not None and one(con, "SELECT 1 FROM chat_sync WHERE chat_id = ?", c["tg_chat_id"]):
            raise ApiError("conflict", "synced")
        if where == "dept" and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", tag, oid):
            raise ApiError("bad_input")
        if where == "main":
            if one(con, "SELECT 1 FROM chat_sync WHERE org_id = ? AND kind = 'main'", oid):
                raise ApiError("conflict", "main")
            con.execute("DELETE FROM chat_place WHERE org_id = ? AND place = 'main' AND chat_id != ?", (oid, cid))  # one main: the old one is loose again
        con.execute("DELETE FROM chat_place WHERE chat_id = ?", (cid,))
        if where:
            con.execute("INSERT INTO chat_place (chat_id, org_id, place, tag_id, at) VALUES (?, ?, ?, ?, ?)",
                        (cid, oid, where, tag if where == "dept" else None, core.now()))
        log_action(con, v.id, "org_chats", f"org:{oid}", json.dumps({"place": where, "chat": cid, "tag": tag}))
    return trees(con, oid)[0]

