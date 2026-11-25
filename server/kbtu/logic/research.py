"""Forum research: verified, once-only surveys and signed proposals reviewed in Admin.
Approval records the owner's decision only; the form is still made by hand with `admin form new`.
"""
from __future__ import annotations

import json
import re
import secrets

from ..db import tx
from . import core, forms
from .core import PERSON, ApiError, Viewer, need_student, one, person_ref, rows

CONSENT = "2026-11-24"  # web research.consent; separate from the account's consent
ANSWER_CONSENT = "2026-11-24"  # web research.signedConsent / anonymousConsent
A_DAY, KEEP = 3, 180 * 86400
ANSWER_KEEP = 365 * 86400
BODY_MOST = 40000  # the bounded fields fit even when JSON escapes every character
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\ud800-\udfff]")
LIMITS = {"title": 120, "goal": 1200, "questions": 4000, "organizer": 200}


def surveys(con, v: Viewer) -> list[dict]:
    # The spec is prefetched with the list: opening a survey never waits for another request.
    return [{"slug": r["slug"], "title": (spec := json.loads(r["spec"]))["title"], "spec": spec,
             "about": r["about"], "answers": r["n"], "answered": bool(r["answered"])}
            for r in rows(con, """SELECT f.slug, f.spec, r.about,
                (SELECT COUNT(*) FROM form_answers a WHERE a.form_id = f.id)
                  + (SELECT COUNT(*) FROM research_answers a WHERE a.form_id = f.id) n,
                EXISTS(SELECT 1 FROM research_participants p WHERE p.form_id = f.id AND p.user_id = ?) answered
                FROM research_forms r JOIN forms f ON f.id = r.form_id
                WHERE f.closed_at IS NULL ORDER BY f.id DESC""", v.id)]


def _student(con, v: Viewer) -> None:
    # Inside the write lock: verification, a ban or account deletion may have changed since authentication.
    if not one(con, f"""SELECT 1 FROM students s JOIN users u ON u.id = s.user_id
        WHERE s.user_id = ? AND s.manual = 0 AND NOT {core.staff_sql()} AND u.banned_at IS NULL""", v.id):
        raise ApiError("need_student")


def answer(con, v: Viewer, slug: str, body: object) -> None:
    need_student(v)
    if not isinstance(body, dict) or body.get("consent") != ANSWER_CONSENT:
        raise ApiError("bad_input", "consent")
    anonymous = body.get("anonymous", False)
    if type(anonymous) is not bool:
        raise ApiError("bad_input", "anonymous")
    with tx(con):
        _student(con, v)
        f = one(con, """SELECT f.id, f.spec, f.closed_at FROM forms f
            JOIN research_forms r ON r.form_id = f.id WHERE f.slug = ?""", slug)
        if not f:
            raise ApiError("not_found")
        if f["closed_at"] is not None:
            raise ApiError("closed")
        if one(con, "SELECT 1 FROM research_participants WHERE form_id = ? AND user_id = ?", f["id"], v.id):
            raise ApiError("conflict", "answered")
        out = forms.answers(json.loads(f["spec"]), body.get("answers"))
        con.execute("INSERT INTO research_participants (form_id, user_id) VALUES (?, ?)", (f["id"], v.id))
        # Random keys and no submission time on anonymous rows keep ordering and timing out of the export.
        con.execute("""INSERT INTO research_answers (id, form_id, user_id, answers, consent, day)
            VALUES (?, ?, ?, ?, ?, ?)""", (secrets.token_hex(16), f["id"], None if anonymous else v.id,
                json.dumps(out, ensure_ascii=False), ANSWER_CONSENT, None if anonymous else core.now() // 86400 * 86400))


def propose(con, v: Viewer, body: object) -> None:
    need_student(v)
    if not isinstance(body, dict) or body.get("consent") != CONSENT:
        raise ApiError("bad_input", "consent")
    fields = {}
    for key, cap in LIMITS.items():
        value = body.get(key)
        if isinstance(value, str):
            value = value.replace("\r\n", "\n").replace("\r", "\n")
        if not isinstance(value, str) or _CTRL.search(value) or not 1 <= len(value.strip()) <= cap:
            raise ApiError("bad_input", key)
        fields[key] = value.strip()
    questions = [q.strip() for q in fields["questions"].splitlines() if q.strip()]
    if not 1 <= len(questions) <= 10:
        raise ApiError("bad_input", "questions")
    fields["questions"] = "\n".join(questions)
    with tx(con):
        # Recheck inside the write lock: deletion or loss of verification may have raced the request.
        _student(con, v)
        if one(con, "SELECT COUNT(*) FROM research_requests WHERE user_id = ? AND created_at > ?",
               v.id, core.now() - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "research_day")
        con.execute("""INSERT INTO research_requests (id, user_id, title, goal, questions, organizer, consent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (core.next_id(con, "research_requests"), v.id, *(fields[k] for k in LIMITS), CONSENT, core.now()))


def requests(con, v: Viewer) -> list[dict]:
    with tx(con, write=False):
        if not one(con, "SELECT 1 FROM users WHERE id = ? AND role IN ('admin', 'moderator') AND banned_at IS NULL", v.id):
            raise ApiError("forbidden")
        items = rows(con, f"""SELECT p.*, u.tg_username, r.id rid, r.title, r.goal, r.questions, r.organizer,
            r.created_at requested_at, r.approved_at FROM research_requests r
            JOIN users u ON u.id = r.user_id JOIN ({PERSON}) p ON p.id = r.user_id
            WHERE r.created_at >= ? ORDER BY r.approved_at IS NOT NULL, r.id DESC""", core.now() - KEEP)
    return [{"id": r["rid"], "person": person_ref(r), "username": r["tg_username"],
             **{k: r[k] for k in LIMITS}, "at": r["requested_at"], "approved": r["approved_at"] is not None} for r in items]


def approve(con, v: Viewer, rid: int, body: object) -> None:
    if not isinstance(body, dict) or type(body.get("approved")) is not bool:
        raise ApiError("bad_input")
    with tx(con):
        # Owner only, checked from today's row; a stale viewer role is not enough.
        if not one(con, "SELECT 1 FROM users WHERE id = ? AND role = 'admin' AND is_founder = 1 AND banned_at IS NULL", v.id):
            raise ApiError("forbidden")
        if not con.execute("UPDATE research_requests SET approved_at = ? WHERE id = ? AND created_at >= ?",
                           (core.now() if body["approved"] else None, rid, core.now() - KEEP)).rowcount:
            raise ApiError("not_found")


def sweep(con) -> None:
    with tx(con):
        now = core.now()
        con.execute("DELETE FROM research_requests WHERE created_at < ?", (now - KEEP,))
        # The deadline also applies to the earlier public answers for the library survey.
        for table in ("form_answers", "research_answers", "research_participants"):
            con.execute(f"""DELETE FROM {table} WHERE form_id IN (
                SELECT r.form_id FROM research_forms r JOIN forms f ON f.id = r.form_id WHERE f.closed_at < ?
                )""", (now - ANSWER_KEEP,))
