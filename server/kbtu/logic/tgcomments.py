"""The forum channel's comments in Telegram (TG_COMMENTS_CHAT; owner, Nov 1; .claude/reports/tg-comments-review.md,
tg-comments-final-review.md, tg-comments-mod-review.md). The channel is public and its discussion group open:
"Comments" goes straight into the field. Only students confirmed by Microsoft write there; the bot (tgc.py) deletes
anyone else's comment, says so once as a reply in the thread (gone after a minute) with a button into the app, and
bans a second try. The stranger's text waits an hour for him alone: the app shows it to the same Telegram account
(the signed initData), never to whoever opens a link.
Reports: a student replies /report; the bot deletes the command and answers in DM. A comment goes at once only when two
reporters verified more than two weeks ago reported it AND the AI says it breaks the rules; its author gets his words
in DM ("removed after reports, under review") and a moderator has the last word: confirm or restore (owner, Nov 1: the
AI never decides). Anything else reported waits in the same queue, still up (an hourly digest; 3+ reports at once).
Reporters' accuracy changes only on a moderator's decision; /report is closed only by a moderator, and only for someone
with two wrong reports or more. Here the rules; the Telegram calls are in tgc.py."""
from __future__ import annotations

import hashlib

from ..db import tx

from .core import ApiError, PERSON, Viewer, log_action, one, person_ref, rows

SAVE_FOR = 3600            # a stranger's deleted text, for him alone (the policy, the bot's template: 1 hour)
STRANGER_KEEP = 90 * 86400  # a warning or a ban on record
KEEP = 30 * 86400          # reported comments' copies and their reports; the owner's undo
RAID_AT = 5                # strangers within a minute: a raid; no warnings (each is a send), the first comment bans
DELETE_AT = 2              # distinct reporters verified over REPORTER_AGE ago, with the AI's "violation"
ALERT_AT = 3               # reports on one comment still up: the moderators hear at once, not in the hourly digest
CLOSE_AT = 2               # wrong reports (kept or restored by a moderator) within KEEP before a moderator may close /report
PAIR_AT = 2                # a reporter's wrong reports on one author: his reports on that author never delete again
AI_LOOKS = 30              # a reporter's reports a day that may each bring a fresh AI look (reports themselves: no cap, owner)
GOOD_AT = 10              # confirmed reports on as many different authors, none wrong: the owner hears (never a promotion)
LIVE = ("open", "queued")  # in the moderators' queue, still up
WRONG = ("overturned", "abuse")


def commenter(con, tg_id: int | None) -> str | None:
    """'student' may comment; 'banned' (banned in the app) is banned in the group too; None: a stranger. Students
    confirmed by Microsoft only (a typed-in ID could be anyone's), staff rows out until the owner decides (review 2)."""
    u = one(con, """SELECT u.banned_at, EXISTS (SELECT 1 FROM students s WHERE s.user_id = u.id AND s.manual = 0
        AND s.consent_version != 'staff') AS st FROM users u WHERE u.tg_id = ?""", tg_id)
    return None if not u else "banned" if u["banned_at"] else "student" if u["st"] else None


def stranger(con, tg_id: int, body: str, link: str | None) -> tuple[str, bool]:
    """A stranger's comment (already on its way out): ('warn', raid) the first time, his text kept SAVE_FOR for the
    app; ('ban', raid) the second time, or at once during a raid (the owner hears once an hour)."""
    t = now()
    with tx(con):
        raid = one(con, """SELECT COUNT(*) FROM tgc_strangers WHERE seen_at > ? AND tg_id != ?
            AND tg_id NOT IN (SELECT tg_id FROM users)""", t - 60, tg_id)[0] >= RAID_AT  # a raid's accounts never opened the app
        was = one(con, "SELECT warned_at FROM tgc_strangers WHERE tg_id = ?", tg_id)
        ban = raid or bool(was and was["warned_at"])
        con.execute("""INSERT INTO tgc_strangers (tg_id, seen_at, warned_at, banned_at) VALUES (?, ?, ?, ?) ON CONFLICT (tg_id)
            DO UPDATE SET seen_at = excluded.seen_at, warned_at = COALESCE(warned_at, excluded.warned_at),
            banned_at = COALESCE(excluded.banned_at, banned_at)""", (tg_id, t, None if ban else t, t if ban else None))
        if not ban and body:  # one row per person: a newer comment replaces the older
            con.execute("INSERT OR REPLACE INTO tgc_saved (tg_id, body, link, at) VALUES (?, ?, ?, ?)", (tg_id, body[:4096], link, t))
        if raid:
            for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
                notify(con, uid, "tgc_raid", f"rd:{t // 3600}")
    return ("ban" if ban else "warn"), raid


# ---- the app's card: my own words, to me alone

_REMOVED = """SELECT c.id, c.body, c.status, c.review, c.rule FROM tgc_comments c JOIN users u ON u.id = c.author_id WHERE c.author_id = ?
    AND u.can_dm = 0 AND c.status IN ('deleting', 'deleted', 'restored') AND c.shown = 0 ORDER BY c.id"""
RULES = ("spam", "insult", "danger", "other")  # the report reasons (moderation.report): the rule a removed comment broke


def saved(con, v: Viewer) -> bool:
    """A card waits for this Telegram account (GET /api/me says so; the app then asks for it): a stranger's text under
    the hour, or what became of a comment of mine the reports removed, while the bot may not write to me."""
    return one(con, "SELECT 1 FROM tgc_saved s JOIN users u ON u.tg_id = s.tg_id WHERE u.id = ? AND s.at > ?", v.id, now() - SAVE_FOR) is not None \
        or one(con, _REMOVED, v.id) is not None


def take_saved(con, v: Viewer) -> dict | None:
    """My own deleted comment, to me alone (the signed initData's Telegram id is the key, nothing in the link). A
    stranger's text under the hour: a student gets it once, with the way back to the thread; anyone else sees it
    without that way (it would walk him into the second-comment ban) until the hour runs out. Else a comment of mine
    the reports removed, once per news (the bot couldn't tell me in DM): "pending" under review, "confirmed" with the
    rule it broke, "restored" (post it again)."""
    tg = one(con, "SELECT tg_id FROM users WHERE id = ?", v.id)[0]
    r = one(con, "SELECT body, link FROM tgc_saved WHERE tg_id = ? AND at > ?", tg, now() - SAVE_FOR)
    if r:
        student = commenter(con, tg) == "student"
        if student:
            con.execute("DELETE FROM tgc_saved WHERE tg_id = ?", (tg,))
        return {"body": r["body"], "link": r["link"] if student else None, "student": student}
    c = one(con, _REMOVED, v.id)
    if not c:
        return None
    con.execute("UPDATE tgc_comments SET shown = 1 WHERE id = ?", (c["id"],))
    verdict = "restored" if c["status"] == "restored" else "pending" if c["review"] else "confirmed"
    return {"body": c["body"], "link": None, "student": True, "removed": True, "verdict": verdict,
            "rule": c["rule"] or "other" if verdict == "confirmed" else None}


# ---- reports

def report(con, reporter_tg: int, chat: int, msg_id: int, author_tg: int, body: str, link: str | None) -> tuple[str, int | None]:
    """A student's /report on a comment (its text as he saw it). ('ok', id): counted, the AI looks next (tgc.py), the
    reporter hears in DM; 'dup': his again; 'kept': a moderator kept it (counted, not judged again until an edit);
    'gone': deleted already; 'closed': his /report is closed (he hears so); 'self': his own."""
    u = one(con, "SELECT id FROM users WHERE tg_id = ?", reporter_tg)
    if not u:
        return "self", None
    if one(con, "SELECT 1 FROM tgc_closed WHERE user_id = ?", u["id"]):
        notify(con, u["id"], "tgc_closed", f"rc:{now() // 86400}")
        return "closed", None
    if author_tg == reporter_tg:
        return "self", None
    author = one(con, "SELECT id FROM users WHERE tg_id = ?", author_tg)
    with tx(con):
        c = one(con, """INSERT INTO tgc_comments (chat_id, msg_id, author_id, author_tg, body, link, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (chat_id, msg_id) DO UPDATE SET body = CASE WHEN status IN ('open', 'queued') THEN excluded.body ELSE body END
            RETURNING id, status""", chat, msg_id, author["id"] if author else None, author_tg, body[:4096], link, now())
        if c["status"] not in (*LIVE, "kept"):
            return "gone", c["id"]
        new = con.execute("INSERT OR IGNORE INTO tgc_reports (comment_id, reporter_id, body, at) VALUES (?, ?, ?, ?)",
                          (c["id"], u["id"], body[:4096], now())).rowcount
        notify(con, u["id"], "tgc_report_ok", f"ro:{c['id']}")
    return ("kept" if c["status"] == "kept" else "ok" if new else "dup"), c["id"]


def _hash(body: str) -> str:
    return hashlib.sha256(" ".join(body.split()).casefold().encode()).hexdigest()[:32]


def fresh_look(con, reporter_tg: int) -> bool:
    """May this reporter's new report bring about a fresh AI look? AI_LOOKS a day; past them the report still counts,
    it reuses a look at the same text or waits for a moderator (review: the AI's cost, without capping /report)."""
    return one(con, """SELECT COUNT(*) FROM tgc_reports r JOIN users u ON u.id = r.reporter_id WHERE u.tg_id = ? AND r.at > ?""",
               reporter_tg, now() - 86400)[0] <= AI_LOOKS


def looked(con, cid: int) -> tuple[bool | None, str | None] | None:
    """The AI's verdict on this comment's text as it is now, if it looked at this very text before; else None."""
    c = one(con, "SELECT body, ai, ai_hash, rule FROM tgc_comments WHERE id = ?", cid)
    if not c or c["ai"] not in ("ok", "flag") or c["ai_hash"] != _hash(c["body"]):
        return None
    return (True, None) if c["ai"] == "ok" else (False, c["rule"])


def look(con, cid: int, body: str, verdict: bool | None) -> None:
    """The AI looked at this text (an answer only: no answer is asked again next time)."""
    if verdict is not None:
        con.execute("UPDATE tgc_comments SET ai_hash = ? WHERE id = ?", (_hash(body), cid))


def banned(con, tg_id: int) -> None:
    """Banned in the app, so banned in the group: on record, so the app's unban lifts it here too (unban_due)."""
    con.execute("""INSERT INTO tgc_strangers (tg_id, seen_at, banned_at) VALUES (?, ?, ?)
        ON CONFLICT (tg_id) DO UPDATE SET seen_at = excluded.seen_at, banned_at = excluded.banned_at""", (tg_id, now(), now()))


def judge(con, cid: int, verdict: bool | None, rule: str | None = None) -> str | None:
    """The AI's look at a reported comment (True clean, False a violation of `rule`, None no answer), then the rule:
    'delete' with DELETE_AT reporters verified over two weeks ago and a violation (the bot deletes it, its author gets
    his words, a moderator confirms or restores); 'queue' with that many but no violation found (or no answer), or a
    violation with fewer; 'open' otherwise. Never 'delete' for a text a moderator cleared before (reposted), nor on
    reporters a moderator found wrong about this author before (a pair hunting one person). The AI reads only the
    author's text, so two people must agree with it."""
    with tx(con):
        c = one(con, "SELECT * FROM tgc_comments WHERE id = ?", cid)
        if not c or c["status"] not in LIVE:
            return None
        n = one(con, """SELECT COUNT(*) FROM tgc_reports r JOIN students s ON s.user_id = r.reporter_id AND s.manual = 0
            WHERE r.comment_id = ? AND s.verified_at < ? AND (SELECT COUNT(*) FROM tgc_reports w JOIN tgc_comments x ON x.id = w.comment_id
                WHERE w.reporter_id = r.reporter_id AND x.author_tg = ? AND w.outcome IN ('overturned', 'abuse')) < ?""",
                cid, now() - threads.REPORTER_AGE, c["author_tg"], PAIR_AT)[0]
        reports = one(con, "SELECT COUNT(*) FROM tgc_reports WHERE comment_id = ?", cid)[0]
        cleared = one(con, "SELECT 1 FROM meta WHERE key = ?", f"tgcok:{_hash(c['body'])}") is not None
        ai = {True: "ok", False: "flag", None: "none"}[verdict]
        if verdict is False and rule in RULES:  # the AI's guess at the rule, the moderator's default
            con.execute("UPDATE tgc_comments SET rule = ? WHERE id = ?", (rule, cid))
        if verdict is False and n >= DELETE_AT and not cleared:
            con.execute("UPDATE tgc_comments SET status = 'deleting', review = 1, ai = ?, decided_at = ? WHERE id = ?", (ai, now(), cid))
            log_action(con, None, "tg_auto_remove", f"tgc:{cid}")
            if c["author_id"]:  # his own words back at once, while the thread is still about them (review 3)
                notify(con, c["author_id"], "tgc_removed", f"tr:{cid}")
            return "delete"
        if reports >= ALERT_AT:  # many at once: the moderators now, not in the hour's digest
            for uid in _mods(con):
                notify(con, uid, "tgc_queue", f"ta:{cid}")
        if n >= DELETE_AT or verdict is False or reports >= ALERT_AT:
            con.execute("UPDATE tgc_comments SET status = 'queued', ai = ?, decided_at = ? WHERE id = ?", (ai, now(), cid))
            return "queue"
        con.execute("UPDATE tgc_comments SET ai = ? WHERE id = ?", (ai, cid))
        return "open"


def edited(con, chat: int, msg_id: int, body: str) -> int | None:
    """A reported comment edited (edit-to-abuse after a check, or edit-to-clean before the second report): the new text
    is the one judged again; one a moderator kept goes back to the checks."""
    c = one(con, "SELECT id, body FROM tgc_comments WHERE chat_id = ? AND msg_id = ? AND status IN ('open', 'queued', 'kept')", chat, msg_id)
    if not c or c["body"] == body[:4096]:  # the same words (only a formatting change): nothing new to judge
        return None
    con.execute("UPDATE tgc_comments SET body = ?, status = CASE WHEN status = 'kept' THEN 'open' ELSE status END WHERE id = ?",
                (body[:4096], c["id"]))
    return c["id"]


def to_delete(con) -> list[tuple[int, int, int]]:
    """(id, chat, message) the bot takes out of Telegram now."""
    return [tuple(r) for r in rows(con, "SELECT id, chat_id, msg_id FROM tgc_comments WHERE status = 'deleting'")]


def deleted(con, cid: int) -> None:
    """Out of Telegram (or Telegram refused: its author deleted it first, mostly; a 48 h limit if there is one)."""
    con.execute("UPDATE tgc_comments SET status = 'deleted' WHERE id = ? AND status = 'deleting'", (cid,))


# ---- the moderators' side (moderation.report_queue / taken_down / restore, app.py's resolve route)

def _mods(con) -> list[int]:
    return [r[0] for r in rows(con, "SELECT id FROM users WHERE role IN ('admin', 'moderator') AND banned_at IS NULL AND tg_id > 0")]


def _involved(con, v: Viewer, c) -> bool:
    """A moderator who wrote or reported it doesn't decide it (another moderator, or the owner, does)."""
    return c["author_id"] == v.id or one(con, "SELECT 1 FROM tgc_reports WHERE comment_id = ? AND reporter_id = ?", c["id"], v.id) is not None


def queue_items(con, v: Viewer) -> list[dict]:
    """Reported comments in the report queue's shape: those the reports and the AI removed first, oldest first (a person
    waits for his verdict), then the ones still up, most reported first. The text judged and, as notes, what reporters
    saw when it differed (an edit since); the reporters as their accuracy and how long ago Microsoft verified them,
    never their names."""
    out = []
    for c in rows(con, f"SELECT * FROM tgc_comments WHERE status IN {LIVE} OR review = 1 ORDER BY review DESC, created_at"):
        if _involved(con, v, c):
            continue
        reps = rows(con, """SELECT r.body, r.at, s.verified_at, (SELECT SUM(w.outcome = 'confirmed') FROM tgc_reports w WHERE w.reporter_id = r.reporter_id) AS ok,
            (SELECT SUM(w.outcome IN ('overturned', 'abuse')) FROM tgc_reports w WHERE w.reporter_id = r.reporter_id) AS bad
            FROM tgc_reports r LEFT JOIN students s ON s.user_id = r.reporter_id WHERE r.comment_id = ? ORDER BY r.at DESC""", c["id"])
        if not reps:
            continue
        seen = {r["body"]: r["at"] for r in reps if r["body"] != c["body"]}
        out.append({"target": "tgc", "id": c["id"], "text": c["body"], "where": {"kind": "tgc", "id": c["id"], "link": c["link"]},
                    "count": len(reps), "reasons": {"other": len(reps)}, "ai": c["ai"], "rule": c["rule"], "removed": bool(c["review"]),
                    "reporters": [{"right": r["ok"] or 0, "wrong": r["bad"] or 0,
                                   "days": (now() - r["verified_at"]) // 86400 if r["verified_at"] else None} for r in reps],
                    "notes": [{"reason": "other", "note": b, "at": a} for b, a in list(seen.items())[:5]], "at": reps[-1]["at"]})
    removed = [x for x in out if x["removed"]]
    return removed + sorted((x for x in out if not x["removed"]), key=lambda x: -x["count"])


def resolve(con, v: Viewer, cid: int, action: str, rule: object = None) -> None:
    """A moderator's verdict, audited: 'remove' (still up: the bot deletes it; removed: confirmed) with the rule it
    broke (RULES; the AI's guess by default), 'keep' (still up: the reports were wrong; removed: restored), 'abuse'
    (as keep, and the reports were abuse: each reporter with CLOSE_AT wrong reports in KEEP loses /report; a person's
    call, never the AI's). Only now does accuracy change. Its author hears the verdict (the bot edits its first
    message into it: tgc.edit_first)."""
    _mod(v)
    if action not in ("remove", "keep", "abuse") or rule is not None and rule not in RULES:
        raise ApiError("bad_input")
    with tx(con):
        c = one(con, f"SELECT * FROM tgc_comments WHERE id = ? AND (status IN {LIVE} OR review = 1)", cid)
        if not c:
            raise ApiError("not_found")
        if _involved(con, v, c):
            raise ApiError("forbidden")
        if action == "remove":
            con.execute("""UPDATE tgc_comments SET status = CASE WHEN status = 'deleted' THEN 'deleted' ELSE 'deleting' END, review = 0,
                rule = ?, shown = 0, decided_at = ? WHERE id = ?""", (rule or c["rule"] or "other", now(), cid))
            con.execute("UPDATE tgc_reports SET outcome = 'confirmed' WHERE comment_id = ?", (cid,))
            if c["author_id"]:  # the verdict, with his words: the "under review" message edited, or a new one
                notify(con, c["author_id"], "tgc_confirmed", f"tc:{cid}")
            log_action(con, v.id, "tg_confirm", f"tgc:{cid}")
            for (uid,) in rows(con, "SELECT reporter_id FROM tgc_reports WHERE comment_id = ?", cid):
                _good(con, uid)
            return
        if c["review"]:
            _restore(con, cid)
        else:
            con.execute("UPDATE tgc_comments SET status = 'kept', decided_at = ? WHERE id = ?", (now(), cid))
            _clear(con, c["body"])
        con.execute("UPDATE tgc_reports SET outcome = ? WHERE comment_id = ?", ("abuse" if action == "abuse" else "overturned", cid))
        log_action(con, v.id, "tg_restore" if c["review"] else "tg_keep", f"tgc:{cid}", '{"abuse": true}' if action == "abuse" else "{}")
        if action == "abuse":
            for (uid,) in rows(con, """SELECT r.reporter_id FROM tgc_reports r WHERE r.comment_id = ? AND (SELECT COUNT(*) FROM tgc_reports w
                    WHERE w.reporter_id = r.reporter_id AND w.outcome IN ('overturned', 'abuse') AND w.at > ?) >= ?""", cid, now() - KEEP, CLOSE_AT):
                if con.execute("INSERT OR IGNORE INTO tgc_closed (user_id, at, by_id) VALUES (?, ?, ?)", (uid, now(), v.id)).rowcount:
                    log_action(con, v.id, "tg_report_close", f"user:{uid}", f'{{"tgc": {cid}}}')


def _clear(con, body: str) -> None:
    """A text a moderator let stand: posted again, reports on it go to the queue, never to an automatic deletion."""
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"tgcok:{_hash(body)}", str(now())))


def _restore(con, cid: int) -> None:
    """Telegram can't bring a message back: still there (not yet deleted), it simply stays; gone, its author hears it
    was a mistake and may post it again (his own words once more, in DM). Nothing in the thread (review 3)."""
    c = one(con, "SELECT * FROM tgc_comments WHERE id = ?", cid)
    con.execute("UPDATE tgc_comments SET status = ?, review = 0, shown = 0, decided_at = ? WHERE id = ?",
                ("kept" if c["status"] == "deleting" else "restored", now(), cid))
    _clear(con, c["body"])
    if c["status"] == "deleted" and c["author_id"]:
        notify(con, c["author_id"], "tgc_back", f"tb:{cid}")


def _good(con, uid: int) -> None:
    """An active reporter right every time, on GOOD_AT different authors (a pair feeding each other violations gets no
    credit): the owner is told once, to offer the moderator status himself (review 2, 3: a person decides)."""
    c = one(con, """SELECT COUNT(DISTINCT CASE WHEN r.outcome = 'confirmed' THEN x.author_tg END) AS ok,
        SUM(r.outcome IN ('overturned', 'abuse')) AS bad FROM tgc_reports r JOIN tgc_comments x ON x.id = r.comment_id
        WHERE r.reporter_id = ? AND r.at > ?""", uid, now() - KEEP)
    if (c["ok"] or 0) >= GOOD_AT and not c["bad"] and one(con, "SELECT 1 FROM users WHERE id = ? AND role = 'user'", uid):
        for (owner,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0"):
            notify(con, owner, "tgc_good", f"gr:{uid}")


def taken(con, cid: int) -> str | None:
    """A deleted comment's text, for the undo list (KEEP days)."""
    r = one(con, "SELECT body FROM tgc_comments WHERE id = ? AND status IN ('deleting', 'deleted') AND review = 0", cid)
    return r[0] if r else None


def restore(con, v: Viewer, cid: int) -> int:
    """The undo list: a confirmed deletion reversed (the owner's 30 days); the reporters were wrong after all."""
    c = one(con, "SELECT * FROM tgc_comments WHERE id = ? AND status IN ('deleting', 'deleted')", cid)
    if not c:
        return 0
    if _involved(con, v, c):
        raise ApiError("forbidden")
    _restore(con, cid)
    con.execute("UPDATE tgc_reports SET outcome = 'overturned' WHERE comment_id = ?", (cid,))
    return 1


def closed(con, v: Viewer) -> list[dict]:
    """Whose /report is closed, for the admin's switch."""
    _admin(v)
    return [{"person": person_ref(p), "at": p["at"]} for p in rows(con, PERSON.replace("SELECT ", "SELECT k.at, ", 1)
                                                                   + " JOIN tgc_closed k ON k.user_id = u.id ORDER BY k.at DESC")]


def reopen(con, v: Viewer, uid: int) -> None:
    """The admin gives /report back (the template says "write to support"); the old wrong marks stop counting."""
    _admin(v)
    with tx(con):
        if not con.execute("DELETE FROM tgc_closed WHERE user_id = ?", (uid,)).rowcount:
            raise ApiError("not_found")
        con.execute("UPDATE tgc_reports SET outcome = NULL WHERE reporter_id = ? AND outcome IN ('overturned', 'abuse')", (uid,))
        log_action(con, v.id, "tg_report_open", f"user:{uid}")


# ---- the bot's rounds

def later_delete(con, msg_id: int, at: int) -> None:
    """The bot's own warning in the thread goes after a minute; kept here so a restart doesn't leave it up."""
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"tgcdel:{msg_id}", str(at)))


def due_deletes(con) -> list[int]:
    found = [int(r[0][7:]) for r in rows(con, "SELECT key FROM meta WHERE key LIKE 'tgcdel:%' AND CAST(value AS INTEGER) <= ?", now())]
    con.executemany("DELETE FROM meta WHERE key = ?", [(f"tgcdel:{m}",) for m in found])
    return found


def post_of(con, root: int, username: str | None = None, post: int | None = None) -> tuple[str, int] | None:
    """The channel post a comment thread hangs under (its copy in the group is the thread's root): remembered when the
    copy arrives, read for the link back to the comments. ponytail: a meta row per channel post, never pruned (a few a day)."""
    if username and post:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"tgcpost:{root}", f"{username} {post}"))
        return username, post
    r = one(con, "SELECT value FROM meta WHERE key = ?", f"tgcpost:{root}")
    return (r[0].split()[0], int(r[0].split()[1])) if r else None


def unban_due(con) -> list[int]:
    """Strangers banned in the group who are students now (signed in with Microsoft, or unbanned in the app): their
    Telegram ids, to unban; their rows go."""
    out = [r[0] for r in rows(con, """SELECT g.tg_id FROM tgc_strangers g JOIN users u ON u.tg_id = g.tg_id AND u.banned_at IS NULL
        JOIN students s ON s.user_id = u.id AND s.manual = 0 AND s.consent_version != 'staff' WHERE g.banned_at IS NOT NULL""")]  # commenter()'s rule, in one read
    con.executemany("DELETE FROM tgc_strangers WHERE tg_id = ?", [(t,) for t in out])
    return out


def sweep(con) -> None:
    """Each bot round: strangers' texts after the hour (every read checks the hour too); every few minutes the old
    records (the policy's 30 and 90 days) and the moderators' hourly digest when something new waits."""
    con.execute("DELETE FROM tgc_saved WHERE at <= ?", (now() - SAVE_FOR,))
    if not _once(con, "tgc_sweep", str(now() // 300)):
        return
    con.execute("DELETE FROM tgc_strangers WHERE seen_at < ?", (now() - STRANGER_KEEP,))
    con.execute("DELETE FROM tgc_comments WHERE created_at < ? AND status != 'deleting'", (now() - KEEP,))
    con.execute("DELETE FROM meta WHERE key LIKE 'tgcok:%' AND CAST(value AS INTEGER) < ?", (now() - KEEP,))
    if one(con, "SELECT 1 FROM tgc_comments WHERE (status = 'queued' OR review = 1) AND decided_at > ?", now() - 3600):
        for uid in _mods(con):
            notify(con, uid, "tgc_queue", f"tq:{now() // 3600}")


def now() -> int:
    return core.now()


# the other domains', imported last: they import this one too
from . import core, threads  # noqa: E402
from .core import _once  # noqa: E402
from .oversight import _admin, _mod  # noqa: E402
from .seats import notify  # noqa: E402
