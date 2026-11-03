"""Admin → Inbox (review Nov 3): everything that waits for the app's staff in one typed list, one request, filtered by
role (a moderator never gets club applications, roster claims or the map's flaws); its count is the Admin shield's
badge. And "Done": what the staff decided lately, who and when, with the Undo where there is one."""
from __future__ import annotations

import json

from .core import ApiError, PERSON, Viewer, now, one, rows, shown_name

DONE_DAYS = 30  # the take-downs' own undo window (moderation.TAKEDOWN_KEEP)
DONE_MAX = 100
HARM = ("danger",)  # a report's reasons that hurt a person go first among the ones still up


def inbox(con, v: Viewer) -> dict:
    """The waiting items, those already hidden first (a person waits for the verdict), then harm, then the oldest;
    each {kind, key, at, hidden, data} with data in the shape the old lists had. And the Done list."""
    _mod(v)
    admin = v.role == "admin"
    items = []
    for r in report_queue(con, v):
        harm = any(k in HARM for k in r["reasons"]) or r.get("rule") in ("abuse", "pdata")
        items.append(_item("report", f"{r['target']}:{r['id']}", r["at"], bool(r.get("removed")), r, harm))
    m = fchannel.mod_queue(con, v)
    for p in m["held"]:
        items.append(_item("fpost", p["id"], p["at"], True, p))
    for r in m["replies"]["held"]:
        items.append(_item("freply", r["id"], r["at"], True, r))
    for r in m["replies"]["live"]:
        if r["reports"]:
            items.append(_item("freply", r["id"], r["at"], False, r))
    for c in pending_chats(con):
        items.append(_item("chat", c["id"], c["at"], False, c))
    if admin:
        for a in club_applications(con, v):
            if a["status"] == "pending":
                items.append(_item("capp", a["id"], a["createdAt"], False, a))
        for r in roster_requests(con, v):
            items.append(_item("claim", r["id"], 0, False, r))
        f = one(con, "SELECT COUNT(*), MIN(created_at) FROM map_flaws WHERE done_at IS NULL")
        if f[0]:
            items.append(_item("flaws", "all", f[1], False, {"count": f[0]}))
    items.sort(key=lambda x: (not x["hidden"], not x.pop("harm"), x["at"]))
    return {"items": items, "done": done(con, v)}


def _item(kind: str, key, at: int, hidden: bool, data: dict, harm: bool = False) -> dict:
    return {"kind": kind, "key": f"{kind}:{key}", "at": at, "hidden": hidden, "harm": harm, "data": data}


def count(con, v: Viewer) -> int:
    """The shield's number on /api/me: the inbox's length, counted (no report_queue's per-row reads on every /me)."""
    if v.role not in ("admin", "moderator"):
        return 0
    # the report queue's rule in one query: not those about me (moderation._about); a thing gone meanwhile counts till the bot's round closes its reports
    n = one(con, """SELECT COUNT(*) FROM (SELECT DISTINCT target, target_id FROM reports WHERE status = 'open') r WHERE NOT (
        r.target = 'user' AND r.target_id = :me
        OR r.target = 'comment' AND EXISTS (SELECT 1 FROM comments WHERE id = r.target_id AND user_id = :me)
        OR r.target = 'photo' AND EXISTS (SELECT 1 FROM event_photos WHERE file_id = r.target_id AND added_by = :me)
        OR r.target = 'ask' AND EXISTS (SELECT 1 FROM asks WHERE id = r.target_id AND user_id = :me)
        OR r.target = 'fpost' AND EXISTS (SELECT 1 FROM fchan_posts WHERE id = r.target_id AND user_id = :me))""".replace(":me", "?"),
            *[v.id] * 5)[0]
    n += one(con, """SELECT COUNT(*) FROM tgc_comments c WHERE (c.status IN ('open', 'queued') OR c.review = 1)
        AND c.author_id IS NOT ? AND NOT EXISTS (SELECT 1 FROM tgc_reports r WHERE r.comment_id = c.id AND r.reporter_id = ?)
        AND EXISTS (SELECT 1 FROM tgc_reports r WHERE r.comment_id = c.id)""", v.id, v.id)[0]  # tgcomments.queue_items' rule
    n += one(con, "SELECT COUNT(*) FROM fchan_posts WHERE status = 'held' AND (why != 'check' OR created_at < ?)", now() - 60)[0]
    n += one(con, """SELECT COUNT(*) FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id WHERE r.status = 'held' AND (r.why != 'check' OR r.created_at < ?)
        OR r.status = 'live' AND p.status = 'live' AND EXISTS (SELECT 1 FROM fchan_reply_reports x WHERE x.reply_id = r.id)""", now() - 60)[0]
    n += one(con, "SELECT COUNT(*) FROM chats WHERE status = 'pending'")[0]
    if v.role == "admin":
        from .. import roster  # it imports kbtu.logic itself
        n += one(con, "SELECT COUNT(*) FROM club_applications WHERE status = 'pending'")[0]
        n += len(roster.requests(con, v))
        n += one(con, "SELECT EXISTS (SELECT 1 FROM map_flaws WHERE done_at IS NULL)")[0]
    return n


# ---- Done: the decisions of the last DONE_DAYS, newest first; an Undo where the action has one and nothing came after

UNDOABLE = ("report_remove", "tg_confirm", "post_hide", "fchan_hide", "fchan_reply_hide", "capp_no", "chat_decline", "chat_remove",
            "event_delete", "tg_report_close")
NO_UNDO_KINDS = ("ask",)  # a forum request a moderator hid has no way back here


def _undoable(action: str, target: str) -> bool:
    kind, _, ref = target.partition(":")
    return action in UNDOABLE and ref.isdigit() and kind not in NO_UNDO_KINDS


def done(con, v: Viewer) -> list[dict]:
    _mod(v)
    acts = MOD_DONE + (ADMIN_DONE if v.role == "admin" else ())
    found = rows(con, f"""SELECT * FROM audit_log WHERE at > ? AND action IN ({','.join('?' * len(DECISIONS))})
        ORDER BY id DESC LIMIT 400""", now() - DONE_DAYS * 86400, *DECISIONS)
    later: dict[str, str] = {}  # a thing's newest line, read newest first: was a decision undone, or decided again?
    out = []
    for a in found:
        key = same_targets(a["target"])[-1]
        first = key not in later
        later.setdefault(key, a["action"])
        if a["action"] not in acts:
            continue  # an undo's own line, or another role's decision
        out.append({"id": a["id"], "action": a["action"], "target": a["target"], "actor": a["actor_id"], "at": a["at"],
                    "data": json.loads(a["data"] or "{}"), "undone": not first and later[key] in UNDOES,
                    "undo": first and _undoable(a["action"], a["target"]) and (a["actor_id"] == v.id or v.role == "admin")})
        if len(out) >= DONE_MAX:
            break
    texts = _texts(con, [x["target"] for x in out])
    ids = {x["actor"] for x in out if x["actor"]}
    names = {p["id"]: shown_name(p) for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)} if ids else {}
    return [{"id": x["id"], "action": x["action"], "target": x["target"], "kind": x["target"].partition(":")[0], "text": x["data"].get("title") or texts.get(x["target"]) or "",
             "by": names.get(x["actor"]), "mine": x["actor"] == v.id, "at": x["at"], "undone": x["undone"], "undo": x["undo"]} for x in out]


_TEXT = {  # target kind -> (the text, read for all rows at once)
    "comment": "SELECT id, body FROM comments WHERE id IN ({})",
    "post": "SELECT id, title FROM posts WHERE id IN ({})",
    "event": "SELECT id, title FROM events WHERE id IN ({})",
    "photo": "SELECT id, 'media/' || path || '.t.webp' FROM files WHERE id IN ({})",
    "user": f"SELECT id, COALESCE(nick, (SELECT first_name || ' ' || last_name FROM students WHERE user_id = users.id), tg_first_name) FROM users WHERE id IN ({{}})",
    "tgc": "SELECT id, body FROM tgc_comments WHERE id IN ({})",
    "fpost": "SELECT id, body FROM fchan_posts WHERE id IN ({})",
    "fchan": "SELECT id, body FROM fchan_posts WHERE id IN ({})",
    "fchanr": "SELECT id, body FROM fchan_replies WHERE id IN ({})",
    "ask": "SELECT id, title FROM asks WHERE id IN ({})",
    "roster": "SELECT id, full_name FROM roster_pending WHERE id IN ({})",  # while the row is there (never kept in the log)
    "tgreport": f"SELECT id, COALESCE(nick, (SELECT first_name || ' ' || last_name FROM students WHERE user_id = users.id), tg_first_name) FROM users WHERE id IN ({{}})",
}


def _texts(con, targets: list[str]) -> dict[str, str]:
    by: dict[str, set[int]] = {}
    for t in targets:
        k, _, i = t.partition(":")
        if k in _TEXT and i.isdigit():
            by.setdefault(k, set()).add(int(i))
    return {f"{k}:{i}": x for k, ids in by.items() for i, x in rows(con, _TEXT[k].format(",".join("?" * len(ids))), *ids)}


def undo(con, v: Viewer, aid: int) -> list[str]:
    """One Done row's Undo, by the action it took back: only the newest decision on its thing, of the last DONE_DAYS,
    by me (an admin: anyone's). Each undo then keeps its own rules (how long, not one's own). Returns files to remove
    from disk (a restore's leftovers)."""
    _mod(v)
    a = one(con, "SELECT * FROM audit_log WHERE id = ? AND at > ?", aid, now() - DONE_DAYS * 86400)
    if not a or not _undoable(a["action"], a["target"]):
        raise ApiError("not_found")
    if a["actor_id"] != v.id and v.role != "admin":
        raise ApiError("forbidden")
    ts = same_targets(a["target"])
    last = one(con, f"""SELECT MAX(id) FROM audit_log WHERE target IN ({','.join('?' * len(ts))})
        AND action IN ({','.join('?' * len(DECISIONS))})""", *ts, *DECISIONS)[0]
    if last != aid:
        raise decided(con, a["target"])  # undone already, or decided again since
    kind, _, ref = a["target"].partition(":")
    tid = int(ref)
    act = a["action"]
    if act == "fchan_hide" or act == "report_remove" and kind == "fpost":
        fchannel.mod_restore(con, v, tid)
    elif act == "fchan_reply_hide":
        fchannel.reply_mod_restore(con, v, tid)
    elif act in ("report_remove", "tg_confirm", "post_hide"):
        return restore(con, v, kind, tid)
    elif act == "capp_no":
        undo_club_refusal(con, v, tid)
    elif act in ("chat_decline", "chat_remove"):
        undo_chat(con, v, tid)
    elif act == "event_delete":
        undo_delete_event(con, v, tid)
    elif act == "tg_report_close" and kind == "tgreport":
        tgcomments.reopen(con, v, tid)
    else:
        raise ApiError("not_found")  # an old line's shape (user:<id>)
    return []


# the other domains', imported last: they import this one too
from . import fchannel, tgcomments  # noqa: E402
from .account import roster_requests  # noqa: E402
from .chatlist import pending_chats, undo_chat  # noqa: E402
from .clubs import club_applications, undo_club_refusal  # noqa: E402
from .core import ADMIN_DONE, DECISIONS, MOD_DONE, UNDOES, decided, same_targets  # noqa: E402
from .moderation import report_queue, restore  # noqa: E402
from .organizing import undo_delete_event  # noqa: E402
from .oversight import _mod  # noqa: E402
