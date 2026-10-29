"""The student forum (Oct 30, the owner: one place instead of a dozen chats). Anyone signed in with KBTU posts a
thread: a charger to lend or borrow, "who's going to KFC", a question, "two people needed now", anything else.
Replies go under it, "I'm in" gathers people on the ones that call for them. A thread or a reply can be anonymous:
nobody sees who wrote it, not the moderators either; the admin alone can reveal the author, and every reveal is in
the audit log. The AI reads every text first: an anonymous one goes live only on its yes, a named one unless it says
no; the rest waits for a moderator. Three reports from accounts older than two weeks hide a thing until a moderator
looks. A thread leaves the feed after its topic's days and is deleted 30 days later (the privacy policy)."""
from __future__ import annotations

from ..db import tx

from .core import ApiError, PERSON, Viewer, log_action, need_student, one, person_ref, rows

TOPICS = ("thing", "go", "help", "vol", "talk")
GATHER = ("go", "vol")                    # "I'm in" counts people here
LIFE = {"thing": 7, "go": 1, "help": 7, "vol": 1, "talk": 30}   # days in the feed
BODY_MAX, REPLY_MAX = 1000, 500
THREADS_A_DAY, REPLIES_AN_HOUR = 5, 30
HIDE_AT, REPORTER_AGE = 3, 14 * 86400
KEEP = 30 * 86400
PAGE = 40
JOINERS = 6                               # faces shown on a gathering thread
# blocks hide named things both ways, never anonymous ones: hiding those would tell whoever blocked someone that the
# anonymous thread is theirs (block, look, unblock: an oracle the adversarial review found)
_SHOWN = """(t.anon = 1 OR NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.user_id = :me AND b.blocked_id = t.user_id)
    OR (b.user_id = t.user_id AND b.blocked_id = :me)))"""


def _blocked(con, me: int) -> set[int]:
    """Who I blocked and who blocked me."""
    return {r[0] for r in rows(con, "SELECT blocked_id FROM blocks WHERE user_id = ? UNION SELECT user_id FROM blocks WHERE blocked_id = ?", me, me)}


def _verdict_status(verdict: bool | None, anon: bool) -> tuple[str, str | None]:
    """The AI's look decides where a text goes: anonymous ones need its yes, named ones only its not-no."""
    if verdict is True or (verdict is None and not anon):
        return "live", None
    return "held", "ai" if verdict is False else "check"


def _text(raw: object, most: int, least: int = 1) -> str:
    s = "\n".join(line.rstrip() for line in str(raw or "").strip().splitlines())
    if not least <= len(s) <= most:
        raise ApiError("bad_input")
    return s


def _people(con, ids: set[int]) -> dict[int, dict]:
    if not ids:
        return {}
    return {p["id"]: person_ref(p) for p in rows(con, f"{PERSON} WHERE u.id IN ({','.join('?' * len(ids))})", *ids)}


def _shapes(con, v: Viewer, found: list) -> list[dict]:
    """Threads for a list, each fact read once for all of them (a card per thread was the old slowness)."""
    if not found:
        return []
    ids = [t["id"] for t in found]
    qs = ",".join("?" * len(ids))
    replies = dict(rows(con, f"SELECT thread_id, COUNT(*) FROM thread_replies WHERE status = 'live' AND thread_id IN ({qs}) GROUP BY thread_id", *ids))
    joins: dict[int, list[int]] = {}
    for j in rows(con, f"SELECT thread_id, user_id FROM thread_joins WHERE thread_id IN ({qs}) ORDER BY at", *ids):
        joins.setdefault(j["thread_id"], []).append(j["user_id"])
    shut = _blocked(con, v.id)
    joins = {k: [u for u in js if u not in shut] for k, js in joins.items()}
    people = _people(con, {t["user_id"] for t in found if not t["anon"]} | {u for js in joins.values() for u in js[:JOINERS]})
    out = []
    for t in found:
        js = joins.get(t["id"], [])
        x = {"id": t["id"], "topic": t["topic"], "body": t["body"], "anon": bool(t["anon"]), "mine": t["user_id"] == v.id,
             "author": None if t["anon"] else people.get(t["user_id"]), "createdAt": t["created_at"], "bumpedAt": t["bumped_at"],
             "expiresAt": t["expires_at"], "replies": replies.get(t["id"], 0)}
        if t["topic"] in GATHER:
            x |= {"joins": len(js), "joined": v.id in js, "joiners": [people[u] for u in js[:JOINERS] if u in people]}
        if t["user_id"] == v.id or v.role in ("admin", "moderator"):
            x |= {"status": t["status"], "why": t["why"]}
        out.append(x)
    return out


def _int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def threads(con, v: Viewer, topic: object = None, before: object = None, bid: object = None) -> list[dict]:
    """The feed: live threads newest-bumped first (mine also while held), a topic to filter by, the next page after the
    last one shown (its bumpedAt and id: threads bumped in the same second aren't lost at the edge). Not what I
    reported, not named people I blocked or who blocked me."""
    need_student(v)
    if topic is not None and topic not in TOPICS or before is not None and not (_int(before) and _int(bid)):
        raise ApiError("bad_input")
    found = con.execute(f"""SELECT t.* FROM threads t WHERE t.expires_at > :now
            AND (t.user_id = :me AND t.status IN ('live', 'held') OR t.status = 'live' AND {_SHOWN}
                AND t.id NOT IN (SELECT target_id FROM reports WHERE target = 'thread' AND reporter_id = :me AND status = 'open'))
            {"AND t.topic = :topic" if topic else ""} {"AND (t.bumped_at < :before OR t.bumped_at = :before AND t.id < :bid)" if before else ""}
        ORDER BY t.bumped_at DESC, t.id DESC LIMIT {PAGE}""", {"now": _now(), "me": v.id, "topic": topic, "before": before, "bid": bid}).fetchall()
    return _shapes(con, v, found)


def _open(con, v: Viewer, tid: object):
    """A thread one may answer or join: live, not run out, not a blocked named person's."""
    t = con.execute(f"SELECT t.* FROM threads t WHERE t.id = :id AND t.status = 'live' AND t.expires_at > :now AND {_SHOWN}",
                    {"id": tid, "now": _now(), "me": v.id}).fetchone() if _int(tid) else None
    if not t:
        raise ApiError("not_found")
    return t


def _seen(con, v: Viewer, tid: int):
    """A thread I may open: live, not run out and not a blocked named person's; or mine; or a moderator's look."""
    t = one(con, "SELECT * FROM threads WHERE id = ? AND status != 'gone'", tid)
    if not t or not (t["user_id"] == v.id or v.role in ("admin", "moderator")
                     or t["status"] == "live" and t["expires_at"] > _now() and (t["anon"] or t["user_id"] not in _blocked(con, v.id))):
        raise ApiError("not_found")
    return t


def thread(con, v: Viewer, tid: int) -> dict:
    """One thread with its replies, oldest first. An anonymous writer is "the author" (the thread's own, anonymous) or
    "Anonymous N", numbered in the order they first wrote, the same number all through the thread."""
    need_student(v)
    t = _seen(con, v, tid)
    shut = _blocked(con, v.id)
    reps = [r for r in rows(con, """SELECT * FROM thread_replies WHERE thread_id = ? AND (status = 'live' OR user_id = ? AND status = 'held')
        ORDER BY id""", tid, v.id) if r["anon"] or r["user_id"] not in shut]  # anonymous ones stay (else an oracle, as above)
    people = _people(con, {r["user_id"] for r in reps if not r["anon"]})
    numbers: dict[int, int] = {}
    out = []
    for r in reps:
        if r["anon"]:
            who = {"op": True} if r["user_id"] == t["user_id"] and t["anon"] else {"n": numbers.setdefault(r["user_id"], len(numbers) + 1)}
        else:
            who = {"person": people.get(r["user_id"]), "op": r["user_id"] == t["user_id"] and not t["anon"]}
        x = {"id": r["id"], "body": r["body"], "anon": bool(r["anon"]), "mine": r["user_id"] == v.id, "at": r["created_at"], **who}
        if r["user_id"] == v.id or v.role in ("admin", "moderator"):
            x |= {"status": r["status"], "why": r["why"]}
        out.append(x)
    return {**_shapes(con, v, [t])[0], "thread": out}


def reserve_thread(con, v: Viewer, body: dict) -> int:
    """A new thread, made at once and held ('check') before the AI is asked: the day's allowance is counted in the same
    transaction, so posts sent at the same moment can't all pass it, nor all cost the AI a look. settle_thread puts the
    verdict on it; with no verdict it stays held for a moderator."""
    need_student(v)
    topic, anon = body.get("topic"), body.get("anon", False)
    if topic not in TOPICS or not isinstance(anon, bool):
        raise ApiError("bad_input")
    text = _text(body.get("body"), BODY_MAX, 2)
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM threads WHERE user_id = ? AND created_at > ?", v.id, _now() - 86400)[0] >= THREADS_A_DAY:
            raise ApiError("rate_limited", "threads")
        return con.execute("""INSERT INTO threads (user_id, topic, body, anon, status, why, created_at, bumped_at, expires_at)
            VALUES (?, ?, ?, ?, 'held', 'check', ?, ?, ?)""", (v.id, topic, text, int(anon), _now(), _now(), _now() + LIFE[topic] * 86400)).lastrowid


def settle_thread(con, v: Viewer, tid: int, verdict: bool | None) -> dict:
    """The AI's verdict on a reserved thread (untouched meanwhile: not deleted, not decided by a moderator)."""
    t = one(con, "SELECT anon FROM threads WHERE id = ?", tid)
    if t:
        status, why = _verdict_status(verdict, bool(t["anon"]))
        con.execute("UPDATE threads SET status = ?, why = ? WHERE id = ? AND status = 'held' AND why = 'check'", (status, why, tid))
    return thread(con, v, tid)


def delete_thread(con, v: Viewer, tid: int) -> None:
    """The author takes it down: the words and the replies go at once; a wordless tombstone stays until the sweep, so
    the day's allowance still counts it (deleting can't buy more posts, nor more of the AI's looks)."""
    with tx(con):
        if not con.execute("UPDATE threads SET status = 'gone', body = '', why = NULL WHERE id = ? AND user_id = ? AND status != 'gone'", (tid, v.id)).rowcount:
            raise ApiError("not_found")
        con.execute("UPDATE thread_replies SET status = 'gone', body = '', why = NULL WHERE thread_id = ?", (tid,))
        con.execute("DELETE FROM thread_joins WHERE thread_id = ?", (tid,))


def reserve_reply(con, v: Viewer, tid: int, body: dict) -> int:
    """A reply under a live thread open to me, made at once and held before the AI is asked (as reserve_thread)."""
    need_student(v)
    anon = body.get("anon", False)
    if not isinstance(anon, bool):
        raise ApiError("bad_input")
    text = _text(body.get("body"), REPLY_MAX)
    with tx(con):
        _open(con, v, tid)
        if one(con, "SELECT COUNT(*) FROM thread_replies WHERE user_id = ? AND created_at > ?", v.id, _now() - 3600)[0] >= REPLIES_AN_HOUR:
            raise ApiError("rate_limited", "replies")
        return con.execute("INSERT INTO thread_replies (thread_id, user_id, body, anon, status, why, created_at) VALUES (?, ?, ?, ?, 'held', 'check', ?)",
                           (tid, v.id, text, int(anon), _now())).lastrowid


def settle_reply(con, v: Viewer, rid: int, verdict: bool | None) -> dict:
    """The AI's verdict on a reserved reply; up: the thread rises and its author hears (never the words)."""
    r = one(con, "SELECT * FROM thread_replies WHERE id = ?", rid)
    if not r:
        raise ApiError("not_found")
    status, why = _verdict_status(verdict, bool(r["anon"]))
    with tx(con):
        if con.execute("UPDATE thread_replies SET status = ?, why = ? WHERE id = ? AND status = 'held' AND why = 'check'", (status, why, rid)).rowcount \
                and status == "live" and (t := one(con, "SELECT * FROM threads WHERE id = ? AND status = 'live'", r["thread_id"])):
            _went_live(con, t, v.id)
    return thread(con, v, r["thread_id"])


def _went_live(con, t, by: int) -> None:
    """A reply is up: the thread rises in the feed and its author hears (not of their own)."""
    con.execute("UPDATE threads SET bumped_at = ? WHERE id = ?", (_now(), t["id"]))
    if t["user_id"] != by:
        notify(con, t["user_id"], "thread_reply", f"tr:{t['id']}:{_now() // 3600}")


def delete_reply(con, v: Viewer, rid: int) -> None:
    """Mine goes: the words wiped, a tombstone for the hour's allowance."""
    if not con.execute("UPDATE thread_replies SET status = 'gone', body = '', why = NULL WHERE id = ? AND user_id = ? AND status != 'gone'", (rid, v.id)).rowcount:
        raise ApiError("not_found")


def join(con, v: Viewer, tid: int, on: object) -> dict:
    """"I'm in" on a thread that gathers people (or not any more); the author hears, like a reply."""
    need_student(v)
    if not isinstance(on, bool):
        raise ApiError("bad_input")
    with tx(con):
        t = _open(con, v, tid)
        if t["topic"] not in GATHER or t["user_id"] == v.id:
            raise ApiError("not_found")
        if on:
            if con.execute("INSERT OR IGNORE INTO thread_joins (thread_id, user_id, at) VALUES (?, ?, ?)", (tid, v.id, _now())).rowcount:
                notify(con, t["user_id"], "thread_reply", f"tr:{tid}:{_now() // 3600}")
        else:
            con.execute("DELETE FROM thread_joins WHERE thread_id = ? AND user_id = ?", (tid, v.id))
    return _shapes(con, v, [one(con, "SELECT * FROM threads WHERE id = ?", tid)])[0]


def joiners(con, v: Viewer, tid: int) -> list[dict]:
    """Who said "I'm in", for the author: their faces and a way to write to them (they offered by joining)."""
    t = one(con, "SELECT * FROM threads WHERE id = ? AND user_id = ?", tid, v.id)
    if not t:
        raise ApiError("not_found")
    found = rows(con, f"""{PERSON.replace('SELECT ', 'SELECT u.tg_username, ', 1)} JOIN thread_joins j ON j.user_id = u.id
        WHERE j.thread_id = ? ORDER BY j.at""", tid)
    shut = _blocked(con, v.id)  # joined, then blocked me: no way to write to them
    return [person_ref(p) | {"telegram": f"https://t.me/{p['tg_username']}" if p["tg_username"] else None} for p in found if p["id"] not in shut]


def reveal(con, v: Viewer, kind: str, xid: int) -> dict:
    """The app's owner alone (the founder admin, as the app promises: not every admin) learns who wrote an anonymous
    thread or reply; the audit log, which only the owner reads, keeps every look."""
    if not _owner(con, v):
        raise ApiError("forbidden")
    r = one(con, f"SELECT user_id, anon FROM {'threads' if kind == 'thread' else 'thread_replies'} WHERE id = ?", xid) if kind in ("thread", "reply") else None
    if not r or not r["anon"]:
        raise ApiError("not_found")
    log_action(con, v.id, "reveal_anon", f"{kind}:{xid}")
    return person_ref(one(con, PERSON + " WHERE u.id = ?", r["user_id"]))


# ---- moderation: held texts (the AI didn't pass or didn't answer), reports, take-downs

def mod_queue(con, v: Viewer) -> dict:
    """What waits for a moderator, oldest first: held threads and held replies (with their thread's words)."""
    _mod(v)
    held = _shapes(con, v, rows(con, "SELECT * FROM threads WHERE status = 'held' AND expires_at > ? ORDER BY id", _now()))
    reps = [{"id": r["id"], "body": r["body"], "anon": bool(r["anon"]), "why": r["why"], "at": r["created_at"], "thread": r["thread_id"], "threadBody": r["tb"][:200]}
            for r in rows(con, """SELECT r.*, t.body AS tb FROM thread_replies r JOIN threads t ON t.id = r.thread_id
                WHERE r.status = 'held' AND t.status = 'live' ORDER BY r.id""")]
    return {"threads": held, "replies": reps}


def mod_decide(con, v: Viewer, kind: str, xid: int, ok: object) -> None:
    """A moderator lets a held thread or reply go live, or takes it down (hidden; the queue's restore can undo)."""
    _mod(v)
    if kind not in ("thread", "reply") or not isinstance(ok, bool):
        raise ApiError("bad_input")
    table = "threads" if kind == "thread" else "thread_replies"
    with tx(con):
        x = one(con, f"SELECT * FROM {table} WHERE id = ? AND status = 'held'", xid)
        if not x:
            raise ApiError("not_found")
        if x["user_id"] == v.id:  # their own: another moderator decides
            raise ApiError("forbidden")
        con.execute(f"UPDATE {table} SET status = ?, why = ? WHERE id = ?", ("live" if ok else "hidden", None if ok else "moderator", xid))
        t = ok and kind == "reply" and one(con, "SELECT * FROM threads WHERE id = ? AND status = 'live'", x["thread_id"])
        if t:  # the thread itself still up: it rises and its author hears
            _went_live(con, t, x["user_id"])
        log_action(con, v.id, "thread_release" if ok else "thread_hide", f"{kind}:{xid}")


def owner_of(con, kind: str, xid: int) -> int | None:
    r = one(con, f"SELECT user_id FROM {'threads' if kind == 'thread' else 'thread_replies'} WHERE id = ?", xid)
    return r[0] if r else None


def reportable(con, v: Viewer, kind: str, xid: int) -> bool:
    """Up and not mine: what a report may be about."""
    if kind == "thread":
        return one(con, "SELECT 1 FROM threads WHERE id = ? AND status = 'live' AND user_id != ?", xid, v.id) is not None
    return one(con, """SELECT 1 FROM thread_replies r JOIN threads t ON t.id = r.thread_id WHERE r.id = ? AND r.status = 'live'
        AND r.user_id != ? AND t.status = 'live' AND t.expires_at > ?""", xid, v.id, _now()) is not None


def after_report(con, kind: str, xid: int) -> None:
    """Three reports from accounts older than two weeks: down until a moderator looks (the queue shows it)."""
    n = one(con, """SELECT COUNT(*) FROM reports r JOIN users u ON u.id = r.reporter_id WHERE r.target = ? AND r.target_id = ?
        AND r.status = 'open' AND u.created_at < ?""", kind, xid, _now() - REPORTER_AGE)[0]
    if n >= HIDE_AT:
        con.execute(f"UPDATE {'threads' if kind == 'thread' else 'thread_replies'} SET status = 'hidden', why = 'reports' WHERE id = ? AND status = 'live'", (xid,))


def words(con, kind: str, xid: int, hidden: bool = False) -> tuple[str, int] | None:
    """The text a moderator judges and the thread it's in; None once it's gone (or, hidden=True, not down)."""
    want = "status = 'hidden'" if hidden else "status IN ('live', 'hidden')"
    if kind == "thread":
        r = one(con, f"SELECT body, id FROM threads WHERE id = ? AND {want}", xid)
    else:
        r = one(con, f"SELECT body, thread_id FROM thread_replies WHERE id = ? AND {want}", xid)
    return (r[0], r[1]) if r else None


def take_down(con, kind: str, xid: int) -> None:
    con.execute(f"UPDATE {'threads' if kind == 'thread' else 'thread_replies'} SET status = 'hidden', why = 'moderator' WHERE id = ? AND status != 'gone'", (xid,))


def put_back(con, kind: str, xid: int, reported_only: bool = False) -> int:
    """Live again: a moderator's restore, or (reported_only) a report queue's "leave it" on what three reports hid."""
    return con.execute(f"""UPDATE {'threads' if kind == 'thread' else 'thread_replies'} SET status = 'live', why = NULL
        WHERE id = ? AND status = 'hidden' {"AND why = 'reports'" if reported_only else ""}""", (xid,)).rowcount


def threads_sweep(con) -> None:
    """What the privacy policy promises: a thread goes 30 days after it left the feed, its replies and joins with it."""
    con.execute("DELETE FROM threads WHERE expires_at < ?", (_now() - KEEP,))


def _now() -> int:
    return core.now()


# the other domains', imported last: they import this one too
from . import core  # noqa: E402
from .oversight import _mod, _owner  # noqa: E402
from .seats import notify  # noqa: E402
