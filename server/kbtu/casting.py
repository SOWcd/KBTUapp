"""Casting (PLAN "Casting", designed Oct 11 from the owner's club's process): a club's recruitment round. The club opens
it with departments (its own tags, each with a line about it and maybe places) and at most six questions of its own;
a student applies in a minute (name, year, school, KBTU email and Telegram are their profile already), picking up to
`picks` departments in order (no departments: a round for the whole club; one: nothing to pick); the casting team (the "casting" right: HR, heads) screens the applications one by one
(no / maybe / next, stars, a note: the team's only), takes the shortlisted into a department or says no, and sends the
results in one tap: the accepted are members at once with their department's tag, the rest get the club's own words.
The results go in parts while the round stays open (each applicant is told once, when the team has decided on them);
finishing the round tells the undecided "no" and ends it.
Interviews: the team adds time slots (one by one, or groups), invites the shortlisted, who pick a time in the app (the
bot: the invitation, a nudge after 48 hours, reminders the evening before and an hour before); the team marks who came.
The board counts each department's taken against its places and shows the funnel. Sixty days after the results the
answers and the team's notes go (keep the least data); who applied and how it ended stay, for "applied before"."""
from __future__ import annotations

import calendar
import json
import re
import unicodedata

from .db import tx
from .logic.teams import may_dept
from .logic import PERSON_COLS, ApiError, Viewer, _may, _once, _qs, banned, can, joined, log_action, need_student, notify, now, one, person_ref, role_in, rows

KINDS = ("short", "long", "one", "many", "link")
VERDICTS = ("no", "maybe", "next")
SOURCES = ("club", "join", "link", "qr", "channel", "friend", "bot")
LIMIT = {"short": 200, "long": 2000, "link": 300}
GROUP = re.compile(r"https://t\.me/[\w+/-]{2,120}")  # a Telegram group's invite or @name: nothing else goes to the accepted
DAY, ASTANA = 86400, 5 * 3600


def _live(con, oid: int):
    """The club's round that isn't over (open, or closed for new applications while the team decides)."""
    return one(con, "SELECT * FROM rounds WHERE org_id = ? AND status != 'done'", oid)


def _get(con, rid: int):
    r = one(con, "SELECT * FROM rounds WHERE id = ?", rid)
    if not r:
        raise ApiError("not_found")
    return r


def _accepting(r) -> bool:
    return r["status"] == "open" and r["closes_at"] > now()


def view(con, v: Viewer, oid: int) -> dict | None:
    """The club's live round: what a student needs to apply (and their own application), plus the counts for the team."""
    r = _live(con, oid)
    team = can(con, v, oid, "casting")
    if not r and not team and v.student:  # the results went out: my "no" with the club's own words, here (the bot never quotes them)
        r = one(con, """SELECT r.* FROM rounds r JOIN round_apps a ON a.round_id = r.id AND a.user_id = ? WHERE r.org_id = ? AND r.status = 'done'
            AND a.stage = 'no' AND r.decline_text != '' AND r.sent_at > ? ORDER BY r.sent_at DESC""", v.id, oid, now() - 60 * DAY)
    mine = one(con, "SELECT * FROM round_apps WHERE round_id = ? AND user_id = ?", r["id"], v.id) if r and v.student else None
    told = bool(mine and (mine["sent_at"] or r["status"] == "done"))  # my result went out (a round goes on taking others)
    # invited to an interview with no result yet: the round stays theirs after the intake closes (their time, a call to come)
    called = bool(mine and mine["stage"] == "next" and mine["invited_at"] and not told)
    if not r or not (team or _accepting(r) or r["status"] == "done" or told or called):
        return None
    deps = rows(con, """SELECT d.tag_id, d.about, d.places, t.name, t.color FROM round_departments d JOIN org_tags t ON t.id = d.tag_id
        WHERE d.round_id = ? ORDER BY d.pos""", r["id"])
    qs = rows(con, "SELECT * FROM round_questions WHERE round_id = ? ORDER BY pos", r["id"])
    # the club's own "what's next" (in-person auditions, dates, place): shown in the app like its description, never by the bot
    out = {"id": r["id"], "title": r["title"], "picks": r["picks"], "closesAt": r["closes_at"], "resultsBy": r["results_by"],
           "open": _accepting(r), "status": r["status"], "nextText": r["next_text"],
           "interviews": bool(r["next_text"] or one(con, "SELECT 1 FROM round_slots WHERE round_id = ?", r["id"])),
           "departments": [{"tagId": d["tag_id"], "name": d["name"], "color": d["color"], "about": d["about"], "places": d["places"]} for d in deps],
           "questions": [{"id": q["id"], "kind": q["kind"], "text": q["text"], "options": json.loads(q["options"]) if q["options"] else None,
                          "required": bool(q["required"]), "tagId": q["tag_id"]} for q in qs],
           "mine": {"departments": json.loads(mine["departments"]), "answers": json.loads(mine["answers"]), "stage": _seen(mine, r),
                    "invited": bool(mine["invited_at"]) and not told, "slot": _slot(con, mine["slot_id"])}
           if mine and mine["stage"] != "withdrawn" else None}
    if told and mine["stage"] == "no":
        out["declineText"] = r["decline_text"]
    if told and mine["stage"] == "yes" and role_in(con, v, oid) and not banned(con, oid, v.id) or team:  # the group's invite: the accepted still in the club only, in the app
        out["groupLink"] = r["group_link"]
    if team:
        counts = dict(rows(con, "SELECT stage, COUNT(*) FROM round_apps WHERE round_id = ? GROUP BY stage", r["id"]))
        out |= {"counts": counts, "declineText": r["decline_text"], "team": True}
    return out


OPEN_CAP = 500  # an open window's room: everyone who applied
def _mins(s) -> int: return s["wide"] or s["minutes"]  # an open window's real span (table round_wide)
def _cap(s) -> int: return OPEN_CAP if s["wide"] else s["capacity"]


def _slot(con, sid: int | None) -> dict | None:
    s = one(con, "SELECT s.*, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide FROM round_slots s WHERE s.id = ?", sid) if sid else None
    return {"id": s["id"], "startsAt": s["starts_at"], "minutes": _mins(s), "place": s["place"]} if s else None


def _seen(a, r) -> str:
    """What the applicant sees: 'sent' until their result goes out, then 'yes' or 'no' (the team's steps stay theirs)."""
    return a["stage"] if (a["sent_at"] or r["status"] == "done") and a["stage"] in ("yes", "no") else "sent"


def group_link(con, v: Viewer, oid: int) -> str | None:
    """The club's group invite for a member it took through a round (the latest round that has one)."""
    if not (v.student and role_in(con, v, oid)):
        return None
    r = one(con, """SELECT r.group_link FROM rounds r JOIN round_apps a ON a.round_id = r.id WHERE r.org_id = ? AND a.user_id = ?
        AND a.stage = 'yes' AND a.sent_at IS NOT NULL AND r.group_link IS NOT NULL ORDER BY r.id DESC LIMIT 1""", oid, v.id)
    return r[0] if r else None


def _clean(con, oid: int, body: dict) -> dict:
    """A round's settings from the setup screen, checked; departments are the club's own tags."""
    try:
        title = " ".join(str(body["title"]).split())
        picks, closes = int(body.get("picks") or 2), int(body["closesAt"])
        results = int(body["resultsBy"]) if body.get("resultsBy") is not None else None
        decline, nxt = str(body.get("declineText") or "").strip(), str(body.get("nextText") or "").strip()
        group = str(body.get("groupLink") or "").strip() or None
        deps = [(int(d["tagId"]), str(d.get("about") or "").strip(), int(d["places"]) if d.get("places") else None) for d in body["departments"]]
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    ids = [d[0] for d in deps]
    qs = clean_questions(body.get("questions"), ids)
    tags = {r[0] for r in rows(con, "SELECT id FROM org_tags WHERE org_id = ?", oid)}
    picks = max(1, min(picks, 3, len(deps) or 1))  # never more than there are departments
    ok = (0 < len(title) <= 80 and now() < closes <= now() + 120 * 86400 and (results is None or results >= closes)
          and (group is None or GROUP.fullmatch(group)) and len(decline) <= 500 and len(nxt) <= 300 and len(deps) <= 12 and len(set(ids)) == len(ids) and set(ids) <= tags
          and all(len(a) <= 200 and (p is None or 0 < p <= 500) for _, a, p in deps))
    if not ok:
        raise ApiError("bad_input")
    return {"title": title, "picks": picks, "closes": closes, "results": results, "decline": decline, "next": nxt, "group": group, "deps": deps, "qs": qs}


def clean_questions(raw, deps: list[int]) -> list[tuple]:
    """At most six questions of the club's own, checked: (kind, text, options, required, department or None). Also the
    always-open join questions (clubs.py: no departments)."""
    try:
        qs = [(str(q["kind"]), " ".join(str(q["text"]).split()), [" ".join(str(o).split()) for o in q.get("options") or []],
               bool(q.get("required", True)), int(q["tagId"]) if q.get("tagId") is not None else None) for q in raw or []]
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ApiError("bad_input")
    if not (len(qs) <= 6 and all(k in KINDS and 0 < len(t) <= 200 and (k not in ("one", "many") or 2 <= len(o) <= 8 and all(0 < len(x) <= 60 for x in o))
                                 and (g is None or g in deps) for k, t, o, _, g in qs)):
        raise ApiError("bad_input")
    return qs


def check_answers(qs: list[dict], answers: dict, picked: list[int]) -> dict:
    """A student's answers to the questions ({id, kind, options, required, tag}), cleaned: a department's question only
    if it was picked, no empty ones; bad_input names a missing required one (q<id>)."""
    clean = {}
    for q in qs:
        if q["tag"] is not None and q["tag"] not in picked:
            continue
        a, opts = answers.get(str(q["id"])), q["options"] or []
        if q["kind"] in LIMIT:
            a = " ".join(str(a or "").split()) if q["kind"] != "long" else str(a or "").strip()
            if len(a) > LIMIT[q["kind"]] or q["kind"] == "link" and a and not re.match(r"(https?://)?[\w-]+(\.[\w-]+)+\S*$", a):
                raise ApiError("bad_input")
        elif q["kind"] == "one":
            if a not in (None, "", *opts):
                raise ApiError("bad_input")
        else:
            a = [x for x in a or [] if isinstance(x, str)] if isinstance(a, list) else []
            if not set(a) <= set(opts):
                raise ApiError("bad_input")
        if q["required"] and not a:
            raise ApiError("bad_input", f"q{q['id']}")
        if a:
            clean[str(q["id"])] = a
    return clean


def open_round(con, v: Viewer, oid: int, body: dict) -> dict:
    """The club opens recruiting (the casting team); its followers who aren't in it hear it once."""
    _may(con, v, oid, "casting")
    f = _clean(con, oid, body)
    with tx(con):
        if _live(con, oid):
            raise ApiError("conflict")  # one round at a time
        rid = con.execute("""INSERT INTO rounds (org_id, title, picks, closes_at, results_by, decline_text, next_text, group_link, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (oid, f["title"], f["picks"], f["closes"], f["results"], f["decline"], f["next"], f["group"], v.id, now())).lastrowid
        _save_parts(con, rid, f)
        for (uid,) in rows(con, """SELECT s.user_id FROM subscriptions s WHERE s.org_id = ?
                AND s.user_id NOT IN (SELECT user_id FROM org_members WHERE org_id = ?)""", oid, oid):
            notify(con, uid, "round_open", f"ro:{rid}")
    return view(con, v, oid)


def _save_parts(con, rid: int, f: dict) -> None:
    con.execute("DELETE FROM round_departments WHERE round_id = ?", (rid,))
    for i, (tag, about, places) in enumerate(f["deps"]):
        con.execute("INSERT INTO round_departments (round_id, tag_id, pos, about, places) VALUES (?, ?, ?, ?, ?)", (rid, tag, i, about, places))
    con.execute("DELETE FROM round_questions WHERE round_id = ?", (rid,))
    for i, (kind, text, options, required, tag) in enumerate(f["qs"]):
        con.execute("INSERT INTO round_questions (round_id, pos, kind, text, options, required, tag_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rid, i, kind, text, json.dumps(options, ensure_ascii=False) if kind in ("one", "many") else None, int(required), tag))


def update_round(con, v: Viewer, rid: int, body: dict) -> dict:
    """Settings change while the round is live; once someone has applied the questions stay as they are (answers would
    stop matching them), the rest may change. {close: true} stops new applications at once."""
    r = _get(con, rid)
    _may(con, v, r["org_id"], "casting")
    if r["status"] == "done":
        raise ApiError("closed")
    with tx(con):
        if body.get("close") is True:
            con.execute("UPDATE rounds SET status = 'closed', closes_at = MIN(closes_at, ?) WHERE id = ?", (now(), rid))
        else:
            f = _clean(con, r["org_id"], {**body, "closesAt": body.get("closesAt", max(r["closes_at"], now() + 60))})
            applied = one(con, "SELECT 1 FROM round_apps WHERE round_id = ?", rid)
            if applied:
                f["qs"] = [(q["kind"], q["text"], json.loads(q["options"]) if q["options"] else [], bool(q["required"]), q["tag_id"])
                           for q in rows(con, "SELECT * FROM round_questions WHERE round_id = ? ORDER BY pos", rid)]
            con.execute("""UPDATE rounds SET title = ?, picks = ?, closes_at = ?, results_by = ?, decline_text = ?, next_text = ?, group_link = ?,
                status = 'open' WHERE id = ?""", (f["title"], f["picks"], f["closes"], f["results"], f["decline"], f["next"], f["group"], rid))
            _save_parts(con, rid, f)
    return view(con, v, r["org_id"])


def apply(con, v: Viewer, rid: int, body: dict) -> dict:
    """A student's application (again: it changes theirs while the round takes them). Departments in order of wish; an
    answer for every required question that applies (a department's own question only if it was picked)."""
    need_student(v)
    r = _get(con, rid)
    if not _accepting(r):
        raise ApiError("closed")
    if role_in(con, v, r["org_id"]):
        raise ApiError("conflict", "member")
    if banned(con, r["org_id"], v.id):
        raise ApiError("forbidden", "banned")
    if one(con, "SELECT 1 FROM round_apps WHERE round_id = ? AND user_id = ? AND sent_at IS NOT NULL", rid, v.id):
        raise ApiError("closed")  # told already: their result stands
    deps = {row[0] for row in rows(con, "SELECT tag_id FROM round_departments WHERE round_id = ?", rid)}
    try:
        picked = [int(x) for x in body["departments"]]
        answers = {str(k): val for k, val in dict(body.get("answers") or {}).items()}
        source = str(body.get("source") or "club")
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    if len(deps) == 1 and not picked:  # one department: nothing to pick
        picked = list(deps)
    if not ((1 if deps else 0) <= len(picked) <= (r["picks"] if deps else 0) and len(set(picked)) == len(picked) and set(picked) <= deps) or source not in SOURCES:
        raise ApiError("bad_input")
    clean = check_answers([{"id": q["id"], "kind": q["kind"], "options": json.loads(q["options"]) if q["options"] else [], "required": q["required"],
                            "tag": q["tag_id"]} for q in rows(con, "SELECT * FROM round_questions WHERE round_id = ? ORDER BY pos", rid)], answers, picked)
    con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (round_id, user_id) DO UPDATE SET departments = excluded.departments, answers = excluded.answers, updated_at = excluded.updated_at,
            stage = CASE WHEN stage = 'withdrawn' THEN 'new' ELSE stage END""",
                (rid, v.id, json.dumps(picked), json.dumps(clean, ensure_ascii=False), source, now(), now()))
    return view(con, v, r["org_id"])


def withdraw(con, v: Viewer, rid: int) -> dict | None:
    need_student(v)
    r = _get(con, rid)
    if r["status"] == "done":
        raise ApiError("closed")
    con.execute("UPDATE round_apps SET stage = 'withdrawn', updated_at = ? WHERE round_id = ? AND user_id = ? AND sent_at IS NULL", (now(), rid, v.id))
    return view(con, v, r["org_id"])


def apps(con, v: Viewer, rid: int) -> list[dict]:
    """Every application for the casting team, oldest first: the profile, the picks and answers, the team's votes (with
    who), and what only the app knows: the club's events they came to, their friends in the club, an earlier try."""
    r = _get(con, rid)
    _may(con, v, r["org_id"], "casting")
    oid = r["org_id"]
    found = rows(con, f"""SELECT a.*, {PERSON_COLS}, s.course, s.school, s.email, u.tg_username, u.created_at AS since
        FROM round_apps a JOIN users u ON u.id = a.user_id JOIN students s ON s.user_id = u.id
        WHERE a.round_id = ? AND a.stage != 'withdrawn' ORDER BY a.id""", rid)
    if not found:
        return []
    ids, uids = [a["id"] for a in found], [a["user_id"] for a in found]
    votes: dict[int, list] = {}
    for x in rows(con, f"""SELECT x.*, s.first_name, s.last_name FROM round_votes x JOIN students s ON s.user_id = x.user_id
            WHERE x.app_id IN ({_qs(ids)}) ORDER BY x.at""", *ids):
        votes.setdefault(x["app_id"], []).append({"by": f"{x['first_name']} {x['last_name'][:1]}".strip(), "mine": x["user_id"] == v.id,
                                                  "verdict": x["verdict"], "stars": x["stars"], "note": x["note"]})
    came = {x[0]: (x[1], x[2]) for x in rows(con, f"""SELECT g.user_id, COUNT(*), MAX(e.title) FROM registrations g JOIN events e ON e.id = g.event_id
        WHERE e.org_id = ? AND g.checked_in_at IS NOT NULL AND g.user_id IN ({_qs(uids)}) GROUP BY g.user_id""", oid, *uids)}
    members = {x[0] for x in rows(con, "SELECT user_id FROM org_members WHERE org_id = ?", oid)}
    friends = {}
    for a, b in rows(con, f"SELECT a, b FROM friendships WHERE a IN ({_qs(uids)}) OR b IN ({_qs(uids)})", *uids, *uids):
        for me, other in ((a, b), (b, a)):
            if me in uids and other in members:
                friends[me] = friends.get(me, 0) + 1
    before = {x[0] for x in rows(con, f"""SELECT a.user_id FROM round_apps a JOIN rounds r ON r.id = a.round_id WHERE r.org_id = ? AND r.id != ?
        AND a.user_id IN ({_qs(uids)}) UNION SELECT user_id FROM join_requests WHERE org_id = ? AND user_id IN ({_qs(uids)})""", oid, rid, *uids, oid, *uids)}
    # person_ref by the user's id: a.* comes first, so a row's "id" is the application's (a tap opened another student)
    return [{"id": a["id"], "person": {**person_ref(a), "id": a["user_id"]}, "fullName": f"{a['last_name']} {a['first_name']}".strip(), "course": a["course"], "school": a["school"],
             "email": a["email"], "username": a["tg_username"], "departments": json.loads(a["departments"]), "answers": json.loads(a["answers"]),
             "stage": a["stage"], "takenTag": a["taken_tag"], "at": a["created_at"], "source": a["source"], "votes": votes.get(a["id"], []),
             "came": came.get(a["user_id"], (0, None))[0], "lastEvent": came.get(a["user_id"], (0, None))[1], "friends": friends.get(a["user_id"], 0),
             "before": a["user_id"] in before, "since": a["since"], "invited": bool(a["invited_at"]), "slot": _slot(con, a["slot_id"]), "sent": bool(a["sent_at"]),
             "showed": None if a["came"] is None else bool(a["came"])} for a in found]


def _app(con, v: Viewer, app_id: int):
    a = one(con, "SELECT a.*, r.org_id, r.status AS rstatus FROM round_apps a JOIN rounds r ON r.id = a.round_id WHERE a.id = ?", app_id)
    if not a:
        raise ApiError("not_found")
    _may(con, v, a["org_id"], "casting")
    if a["rstatus"] == "done" or a["stage"] == "withdrawn" or a["sent_at"]:
        raise ApiError("closed")  # a result that went out stands
    return a


def vote(con, v: Viewer, app_id: int, body: dict) -> dict:
    """A teammate's verdict on an application (no / maybe / next), stars and a note; the latest verdict is its stage
    until someone decides (yes into a department, or no)."""
    with tx(con):  # read and written under the lock: results sent meanwhile stand
        a = _app(con, v, app_id)
        verdict, stars, note = body.get("verdict"), body.get("stars"), " ".join(str(body.get("note") or "").split())
        if verdict not in VERDICTS or not (stars is None or isinstance(stars, int) and not isinstance(stars, bool) and 1 <= stars <= 5) or len(note) > 500:
            raise ApiError("bad_input")
        con.execute("""INSERT INTO round_votes (app_id, user_id, verdict, stars, note, at) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (app_id, user_id) DO UPDATE SET verdict = excluded.verdict, stars = excluded.stars, note = excluded.note, at = excluded.at""",
                    (app_id, v.id, verdict, stars, note, now()))
        if a["stage"] not in ("yes",):
            con.execute("UPDATE round_apps SET stage = ?, updated_at = ? WHERE id = ?", (verdict, now(), app_id))
    return {"stage": verdict if a["stage"] != "yes" else "yes"}


def decide(con, v: Viewer, app_id: int, body: dict) -> dict:
    """Taken into a department (any of the round's: the board may move someone to their second wish or elsewhere), or no."""
    with tx(con):  # read and written under the lock: a "no" sent meanwhile never turns into a "yes" with no membership
        a = _app(con, v, app_id)
        stage, tag = body.get("stage"), body.get("tagId")
        deps = {row[0] for row in rows(con, "SELECT tag_id FROM round_departments WHERE round_id = ?", a["round_id"])}
        if stage == "yes" and (tag in deps or tag is None and not deps):  # no departments: into the club, no tag
            con.execute("UPDATE round_apps SET stage = 'yes', taken_tag = ?, updated_at = ? WHERE id = ?", (tag, now(), app_id))
        elif stage in ("no", "next", "maybe", "new"):
            con.execute("UPDATE round_apps SET stage = ?, taken_tag = NULL, updated_at = ? WHERE id = ?", (stage, now(), app_id))
        else:
            raise ApiError("bad_input")
    return {"stage": stage, "takenTag": tag if stage == "yes" else None}


def is_dept(con, oid: int, tag: int) -> bool:
    return bool(one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", tag, oid))


def send(con, v: Viewer, rid: int, final: bool = True) -> dict:
    """The results decided so far, in one tap: the accepted are members at once with their department's tag, the
    declined hear the club's own words (or the app's); each applicant is told once, the undecided wait for a later send
    and the round goes on. final (the old one-tap results, a cached client's too): the undecided hear "no" and the round
    is over. The bot sends at its own pace."""
    r = _get(con, rid)
    _may(con, v, r["org_id"], "casting")
    oid = r["org_id"]
    with tx(con):
        live = """UPDATE rounds SET sent_at = ?, status = CASE WHEN ? THEN 'done' ELSE status END,
            closes_at = CASE WHEN ? THEN MIN(closes_at, ?) ELSE closes_at END WHERE id = ? AND status != 'done'"""
        if not con.execute(live, (now(), final, final, now(), rid)).rowcount:
            raise ApiError("conflict")
        yes = no = 0
        decided = "" if final else "AND stage IN ('yes', 'no')"
        # told now: an interview still ahead is off and its seat free (one already past stays: who came); the bot's reminders check sent_at
        con.execute(f"""UPDATE round_apps SET slot_id = NULL WHERE round_id = ? AND stage != 'withdrawn' AND sent_at IS NULL {decided}
            AND slot_id IN (SELECT id FROM round_slots WHERE starts_at > ?)""", (rid, now()))
        for a in rows(con, f"SELECT * FROM round_apps WHERE round_id = ? AND stage != 'withdrawn' AND sent_at IS NULL {decided}", rid):
            if a["stage"] == "yes" and not banned(con, oid, a["user_id"]):
                new = con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (oid, a["user_id"], now())).rowcount
                joined(con, oid, a["user_id"])
                # departments are a set: a newcomer lands in it; one in the club already gets it only as Team would give
                # it by the sender's hand (a Head can't approve their own way into another department's powers)
                if a["taken_tag"] and (new or not is_dept(con, oid, a["taken_tag"]) or may_dept(con, v, oid, a["user_id"], a["taken_tag"])):
                    con.execute("INSERT OR IGNORE INTO member_tags (tag_id, user_id) VALUES (?, ?)", (a["taken_tag"], a["user_id"]))
                con.execute("UPDATE round_apps SET sent_at = ? WHERE id = ?", (now(), a["id"]))
                notify(con, a["user_id"], "round_yes", f"ry:{a['id']}")
                yes += 1
            else:
                con.execute("UPDATE round_apps SET stage = 'no', taken_tag = NULL, sent_at = ? WHERE id = ?", (now(), a["id"]))
                notify(con, a["user_id"], "round_no", f"rn:{a['id']}")
                no += 1
    return {"accepted": yes, "declined": no}


# ---- interviews

def _at(date: str, hm: str) -> int:
    """A form's 'YYYY-MM-DD' and 'HH:MM' in Almaty as a timestamp."""
    y, m, d = (int(x) for x in date.split("-"))
    h, mi = (int(x) for x in hm.split(":"))
    return calendar.timegm((y, m, d, h, mi, 0)) - ASTANA


def add_slots(con, v: Viewer, rid: int, body: dict) -> list[dict]:
    """A day's slots: from..to every `minutes`, each for `capacity` people (1: one by one, more: a group), at `place`.
    An open window (a club lead, Nov 17: "just come between 2 and 6"): minutes = the whole from..to, one slot for up to 500."""
    r = _get(con, rid)
    _may(con, v, r["org_id"], "casting")
    if r["status"] == "done":
        raise ApiError("closed")
    try:
        start, end = _at(str(body["date"]), str(body["from"])), _at(str(body["date"]), str(body["to"]))
        minutes, cap, place = int(body["minutes"]), int(body.get("capacity") or 1), " ".join(str(body.get("place") or "").split())
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input")
    # an open window: the whole from..to as one slot, longer than an interview or for more than a group
    wide = minutes if start + minutes * 60 == end and (minutes > 180 or cap > 50) else None
    if not ((wide or 5 <= minutes <= 180 and 1 <= cap <= 50) and len(place) <= 120 and now() < start < end <= start + 14 * 3600):
        raise ApiError("bad_input")
    with tx(con):
        t = start
        while t + minutes * 60 <= end:
            con.execute("INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, ?, ?, ?)", (rid, t, min(minutes, 180), 50 if wide else cap, place))
            if wide:
                con.execute("INSERT INTO round_wide (slot_id, minutes) VALUES (last_insert_rowid(), ?)", (wide,))
            t += minutes * 60
    return slots(con, v, rid)


def drop_slot(con, v: Viewer, sid: int) -> list[dict]:
    """A slot nobody booked goes (a booked one stays: the person would lose their time silently)."""
    s = one(con, "SELECT s.*, r.org_id FROM round_slots s JOIN rounds r ON r.id = s.round_id WHERE s.id = ?", sid)
    if not s:
        raise ApiError("not_found")
    _may(con, v, s["org_id"], "casting")
    if one(con, "SELECT 1 FROM round_apps WHERE slot_id = ? AND stage != 'withdrawn'", sid):
        raise ApiError("conflict")
    with tx(con):  # its waiting place notices go with it: SQLite may hand the id to the next slot made
        con.execute("DELETE FROM round_slots WHERE id = ?", (sid,))
        con.execute("DELETE FROM bot_outbox WHERE kind = 'round_place' AND sent_at IS NULL AND ref LIKE ?", (f"ivp:%:{sid}:%",))
        con.execute("DELETE FROM bot_outbox WHERE kind = 'round_call' AND sent_at IS NULL AND ref LIKE ?", (f"ivc:%:{sid}:%",))
    return slots(con, v, s["round_id"])


NO_LINK = re.compile(r"http|www\.|t\.me|@|://", re.I)  # a slot's new place goes into the bot's message: no link, no ping
# "example.com", "a.kz" by their ending; never a room like "aud. 305", "b.2", "1.5 floor", "Eng.Lab 305"
DOMAIN = re.compile(r"\b[a-z0-9-]+\.(?:com|kz|ru|org|net|me|io|app|link|gg|ly|cc|co|info|xyz|site|online|su|by|uz|dev|edu)\b", re.I)
PLACE_NOTICES = 3  # place changes a round may tell the shortlisted about per Almaty day; more still save, quietly
PLACE_EDITS = 8    # place changes a round may save per Almaty day at all


def _plain_place(raw) -> str:
    """A slot's place as the bot may quote it: one line, no invisible or direction characters, no link, no mention."""
    if not isinstance(raw, str) or any(unicodedata.category(c) in ("Cc", "Cf") for c in raw):
        raise ApiError("bad_input")
    place = unicodedata.normalize("NFKC", " ".join(raw.split()))  # kept as checked: fullwidth "305" is the same room
    if not 0 < len(place) <= 120 or NO_LINK.search(place) or DOMAIN.search(place):
        raise ApiError("bad_input")
    return place


_ENDS = "s.starts_at + COALESCE((SELECT minutes FROM round_wide w WHERE w.slot_id = s.id), s.minutes) * 60"


def _full(con, s) -> bool:
    taken = one(con, "SELECT COUNT(*) FROM round_apps WHERE slot_id = ? AND stage != 'withdrawn'", s["id"])[0]
    return taken >= (OPEN_CAP if one(con, "SELECT 1 FROM round_wide WHERE slot_id = ?", s["id"]) else s["capacity"])


def place_slot(con, a, sid: int):
    """The edited slot a place notice names, as it is now, if the notice still holds for this application: the slot
    hasn't ended, and it is theirs, or they are invited with no time and it has room. None: nothing to tell."""
    s = one(con, f"SELECT s.*, {_ENDS} AS ends FROM round_slots s WHERE s.id = ? AND s.round_id = ? AND {_ENDS} > ?", sid, a["round_id"], now())
    if not s or a["slot_id"] and a["slot_id"] != sid or not a["slot_id"] and (not a["invited_at"] or _full(con, s)):
        return None
    return s


def set_place(con, v: Viewer, sid: int, body: dict) -> dict:
    """The venue moved (a club lead, Nov 19): a slot's place changes; the shortlisted it concerns (booked on it, or
    invited with no time while it has room) hear it once from the bot, a couple of minutes later from what is current
    then, so a few quick edits are one message per slot. notice: 'sent', 'limit' (the day's notices are used up: saved,
    nobody told) or 'none'. Checked and written under the write lock (tx is BEGIN IMMEDIATE): a removed organizer, a
    round finished or a slot ended meanwhile never slips through."""
    place = _plain_place(body.get("place"))
    with tx(con):
        s = one(con, """SELECT s.*, r.org_id, r.status AS rstatus, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide
            FROM round_slots s JOIN rounds r ON r.id = s.round_id WHERE s.id = ?""", sid)
        if not s:
            raise ApiError("not_found")
        _may(con, v, s["org_id"], "casting")
        if s["rstatus"] == "done" or s["starts_at"] + _mins(s) * 60 <= now():
            raise ApiError("closed")
        rid = s["round_id"]
        if place == s["place"]:
            return {"slots": slots(con, v, rid), "notice": "none"}
        day = (now() + ASTANA) // DAY * DAY - ASTANA
        edits, used = one(con, """SELECT COUNT(*), COALESCE(SUM(json_extract(data, '$.told') = 1), 0) FROM audit_log
            WHERE target = ? AND action = 'round_place' AND at >= ?""", f"round:{rid}", day)
        if edits >= PLACE_EDITS:
            raise ApiError("rate_limited")
        con.execute("UPDATE round_slots SET place = ? WHERE id = ?", (place, sid))
        room = not _full(con, s)
        told = covered = limited = False
        for a in rows(con, """SELECT id, user_id FROM round_apps WHERE round_id = ? AND stage = 'next' AND sent_at IS NULL
                AND (slot_id = ? OR slot_id IS NULL AND invited_at IS NOT NULL AND ?)""", rid, sid, room):
            mine = f"ivp:{a['id']}:{sid}:%"
            # one message waiting per applicant and slot: it renders the slot as it is when it goes, so it carries this edit too
            if one(con, "SELECT 1 FROM bot_outbox WHERE kind = 'round_place' AND ref LIKE ? AND sent_at IS NULL AND error IS NULL", mine):
                covered = True
            elif used >= PLACE_NOTICES:
                limited = True
            else:
                n = one(con, "SELECT COUNT(*) FROM bot_outbox WHERE kind = 'round_place' AND ref LIKE ?", mine)[0]
                # the place before it: edited back to that before it goes, the row says nothing (bot._render)
                notify(con, a["user_id"], "round_place", f"ivp:{a['id']}:{sid}:{n}", json.dumps({"was": s["place"]}, ensure_ascii=False), after=now() + 120)
                told = True
        log_action(con, v.id, "round_place", f"round:{rid}", json.dumps({"slot": sid, "old": s["place"], "new": place, "told": int(told)}, ensure_ascii=False))
        return {"slots": slots(con, v, rid), "notice": "limit" if limited else "sent" if told or covered else "none"}


CALL_AHEAD = 2 * 3600  # "come over" from two hours before a window until it ends
# whom a "come over" reaches: shortlisted, invited, no result yet, not marked as came; booked on any window or none
_CALLED = "stage = 'next' AND sent_at IS NULL AND invited_at IS NOT NULL AND came IS NOT 1"


def _callable(s) -> bool:
    return s["starts_at"] - CALL_AHEAD <= now() < s["starts_at"] + _mins(s) * 60


def call_ref(a_id: int, s) -> str:
    """ivc:<application>:<slot>:<start>: the start too, so a new slot that gets a dropped one's id is a new window."""
    return f"ivc:{a_id}:{s['id']}:{s['starts_at']}"


def call_holds(a, s) -> bool:
    """The bot's check when it sends: still someone to call, the window not over."""
    return bool(s and a["stage"] == "next" and not a["sent_at"] and a["invited_at"] and a["came"] != 1 and _callable(s))


def call_slot(con, v: Viewer, sid: int) -> dict:
    """The team is at the window now (a club lead, Nov 19: "I'm here, come over"): every shortlisted without a result
    hears it from the bot once per window, a fixed template (the club, the window, its place). queued: how many now."""
    with tx(con):
        s = one(con, """SELECT s.*, r.org_id, r.status AS rstatus, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide
            FROM round_slots s JOIN rounds r ON r.id = s.round_id WHERE s.id = ?""", sid)
        if not s:
            raise ApiError("not_found")
        _may(con, v, s["org_id"], "casting")
        if s["rstatus"] == "done" or not _callable(s):
            raise ApiError("closed")
        queued = 0
        for a in rows(con, f"SELECT id, user_id FROM round_apps WHERE round_id = ? AND {_CALLED}", s["round_id"]):
            queued += con.execute("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'round_call', ?, ?)",
                                (a["user_id"], call_ref(a["id"], s), now())).rowcount
        log_action(con, v.id, "round_call", f"round:{s['round_id']}", json.dumps({"slot": sid, "queued": queued}))
        return {"queued": queued, "slots": slots(con, v, s["round_id"])}


def slots(con, v: Viewer, rid: int) -> list[dict]:
    """The round's slots in time order: the team sees who booked each (and whether they came); an invited applicant the
    coming ones with room left, and their own."""
    r = _get(con, rid)
    team = can(con, v, r["org_id"], "casting")
    mine = None if team else one(con, "SELECT * FROM round_apps WHERE round_id = ? AND user_id = ? AND stage != 'withdrawn'", rid, v.id)
    if not team and not (mine and mine["invited_at"]):
        raise ApiError("forbidden")
    booked: dict[int, list] = {}
    for a in rows(con, f"""SELECT a.id AS app, a.slot_id, a.came, {PERSON_COLS} FROM round_apps a JOIN users u ON u.id = a.user_id
            JOIN students s ON s.user_id = u.id WHERE a.round_id = ? AND a.slot_id IS NOT NULL AND a.stage != 'withdrawn'""", rid):
        booked.setdefault(a["slot_id"], []).append(a)
    calls: dict[tuple, dict] = {}  # a window's "come over": whom it went to and how it went; read once for all rows
    reach: set = set()
    if team:
        for ref, aid, sent, error in rows(con, """SELECT b.ref, a.id, b.sent_at, b.error FROM bot_outbox b
                JOIN round_apps a ON a.user_id = b.user_id AND a.round_id = ? WHERE b.kind = 'round_call'""", rid):
            app, sid, at = (int(x) for x in ref.split(":")[1:4])
            if app == aid:  # this round's application, not the same person's in another round
                # told: what Telegram took; waiting: still in the queue; a failed one (no DMs, blocked) is neither
                calls.setdefault((sid, at), {})[app] = "told" if sent else None if error else "waiting"
        reach = {a[0] for a in rows(con, f"SELECT id FROM round_apps WHERE round_id = ? AND {_CALLED}", rid)}
    out = []
    for s in rows(con, "SELECT s.*, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide FROM round_slots s WHERE s.round_id = ? ORDER BY s.starts_at", rid):
        people = booked.get(s["id"], [])
        x = {"id": s["id"], "startsAt": s["starts_at"], "minutes": _mins(s), "capacity": _cap(s), "place": s["place"],
             "left": _cap(s) - len(people)}
        if team:
            x["people"] = [{"appId": a["app"], "person": person_ref(a), "fullName": f"{a['last_name']} {a['first_name']}".strip(),
                            "showed": None if a["came"] is None else bool(a["came"])} for a in people]
            # a coming window shows the button dim with its opening time, so the team knows it's there
            if now() < s["starts_at"] + _mins(s) * 60 and r["status"] != "done":
                went = calls.get((s["id"], s["starts_at"]), {})
                x["call"] = {"told": sum(w == "told" for w in went.values()), "waiting": sum(w == "waiting" for w in went.values()),
                             "tried": len(went), "left": len(reach - went.keys())}
                if not _callable(s):
                    x["call"]["opensAt"] = s["starts_at"] - CALL_AHEAD
        elif s["id"] == mine["slot_id"]:
            x["mine"] = True
        elif x["left"] <= 0 or s["starts_at"] <= now():
            continue
        out.append(x)
    return out


def invite(con, v: Viewer, rid: int) -> dict:
    """The shortlisted (next) not invited yet hear from the bot: pick an interview time; a nudge in 48 hours if they haven't."""
    r = _get(con, rid)
    _may(con, v, r["org_id"], "casting")
    if r["status"] == "done":
        raise ApiError("closed")
    if not one(con, "SELECT 1 FROM round_slots WHERE round_id = ? AND starts_at > ?", rid, now()):
        raise ApiError("conflict", "no_slots")
    n = 0
    with tx(con):
        for a in rows(con, "SELECT id, user_id FROM round_apps WHERE round_id = ? AND stage = 'next' AND invited_at IS NULL", rid):
            con.execute("UPDATE round_apps SET invited_at = ? WHERE id = ?", (now(), a["id"]))
            notify(con, a["user_id"], "round_interview", f"iv:{a['id']}")
            notify(con, a["user_id"], "round_iv_nudge", f"ivn:{a['id']}", after=now() + 48 * 3600)
            n += 1
    return {"invited": n}


def nudge_now(con, rid: int, dry: bool = False) -> int:
    """By hand (admin round-nudge): the 48-hour "pick a time" nudge of a round goes now to the invited who haven't
    picked one, e.g. when the first time is sooner than the nudge. Once each: it is the same outbox row."""
    q = """FROM bot_outbox WHERE kind = 'round_iv_nudge' AND sent_at IS NULL AND error IS NULL AND send_after > ?
        AND CAST(substr(ref, 5) AS INTEGER) IN (SELECT id FROM round_apps WHERE round_id = ? AND stage = 'next' AND slot_id IS NULL)"""
    if dry:
        return one(con, "SELECT COUNT(*) " + q, now(), rid)[0]
    with tx(con):
        return con.execute("UPDATE bot_outbox SET send_after = ? WHERE id IN (SELECT id " + q + ")", (now(), now(), rid)).rowcount


def book(con, v: Viewer, rid: int, body: dict) -> list[dict]:
    """An invited applicant takes a time (or gives it up: null) while it has room and hasn't started. The bot reminds
    them the evening before (19:00) and an hour before."""
    need_student(v)
    r = _get(con, rid)
    if r["status"] == "done":
        raise ApiError("closed")
    sid = body.get("slotId")
    with tx(con):
        a = one(con, "SELECT * FROM round_apps WHERE round_id = ? AND user_id = ? AND stage != 'withdrawn'", rid, v.id)
        if not a or not a["invited_at"]:
            raise ApiError("forbidden")
        if a["sent_at"]:  # told: their result stands, the time is for those still waiting
            raise ApiError("closed")
        con.execute("DELETE FROM bot_outbox WHERE kind = 'round_iv_remind' AND ref LIKE ? AND sent_at IS NULL", (f"ivr:{a['id']}:%",))
        if sid is None:
            con.execute("UPDATE round_apps SET slot_id = NULL WHERE id = ?", (a["id"],))
        else:
            s = one(con, "SELECT s.*, (SELECT minutes FROM round_wide w WHERE w.slot_id = s.id) AS wide FROM round_slots s WHERE s.id = ? AND s.round_id = ? AND s.starts_at > ?", sid, rid, now())
            taken = one(con, "SELECT COUNT(*) FROM round_apps WHERE slot_id = ? AND id != ? AND stage != 'withdrawn'", sid, a["id"])[0] if s else 0
            if not s or taken >= _cap(s):
                raise ApiError("full")
            con.execute("UPDATE round_apps SET slot_id = ? WHERE id = ?", (sid, a["id"]))
            eve = (s["starts_at"] + ASTANA) // DAY * DAY - ASTANA - 5 * 3600  # 19:00 the day before, Almaty
            for at, tag in ((eve, "eve"), (s["starts_at"] - 3600, "hour")):
                if at > now():
                    notify(con, v.id, "round_iv_remind", f"ivr:{a['id']}:{sid}:{tag}", after=at)
    return slots(con, v, rid)


def showed(con, v: Viewer, app_id: int, body: dict) -> dict:
    """The team marks whether they came to the interview (null: not yet known)."""
    a = _app(con, v, app_id)
    came = body.get("came")
    if came not in (True, False, None):
        raise ApiError("bad_input")
    con.execute("UPDATE round_apps SET came = ? WHERE id = ?", (None if came is None else int(came), a["id"]))
    return {"showed": came}


def forget(con) -> None:
    """Once a day (the bot's round): sixty days after a round's results, its answers, votes and notes go."""
    day = (now() + ASTANA) // DAY
    if not _once(con, "cast_forget", str(day)):
        return
    old = [r[0] for r in rows(con, "SELECT id FROM rounds WHERE status = 'done' AND sent_at < ?", now() - 60 * DAY)]
    if old:
        con.execute(f"UPDATE round_apps SET answers = '{{}}' WHERE round_id IN ({_qs(old)}) AND answers != '{{}}'", old)
        con.execute(f"DELETE FROM round_votes WHERE app_id IN (SELECT id FROM round_apps WHERE round_id IN ({_qs(old)}))", old)
    # an any-time join request's answers: sixty days after the club's answer, the same
    con.execute("UPDATE join_requests SET answers = NULL WHERE answers IS NOT NULL AND status != 'pending' AND decided_at < ?", (now() - 60 * DAY,))
