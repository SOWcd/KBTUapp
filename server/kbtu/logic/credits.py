"""The people of the app: the creator, the idea's author, and everyone whose idea, find (a bug) or code is in it.

A contribution (`credits`, written by the team with `kbtu.admin credit ...`) is a Telegram id (an account or not yet),
a kind and one line in ru, kk, en: OUR words about what shipped, never the person's message. It is listed once shipped,
newest first by the day it shipped: no order by amount, nothing to argue about.

The feature's own consent (CONSENT, as evteams'): a name and a face stand next to the lines ONLY after that person's
yes. No answer, a no, a withdrawal, a ban, no account, a deleted account: the lines stay, signed "Student" by the app,
with no name, face, id or link. The creator alone is named without it (public as the creator already); the idea's
author follows the rule. Every answer is a row of `credit_consents` (who, when, which text version), never replaced:
the latest one counts. Asked by the bot's template once per person (`ask`), answered in the app, changed in Settings.

Deleting an account: its consents go (`_DEL_GONE`) and its lines lose the Telegram id (`gone`): what the app got stays
in the list as a nameless "Student", and nothing left behind points at the person.
"""
from __future__ import annotations

import time

from . import core
from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, need_student, one, person_ref, rows

KINDS = ("idea", "find", "code")
LINE_MAX = 90     # a line is a few words; the CLI refuses more
CONSENT = "cr1"   # the consent sheet's text (web: cr.ask*); a reworded sheet is a new version, and old yeses ask again
OFF = "off"       # a no or a withdrawal: remembered, so the bot never asks again (a later yes is a new row)

_SAID = "(SELECT x.version FROM credit_consents x WHERE x.user_id = u.id ORDER BY x.id DESC LIMIT 1)"


# ------------------------------------------------------------ the list

def _item(r) -> dict:
    return {"kind": r["kind"], "text": {"ru": r["ru"], "kk": r["kk"], "en": r["en"]}, "on": r["shipped_on"]}


def _named(r) -> bool:
    """Shown with a name and a face: an account of a student, not banned, whose latest answer is this text's yes."""
    return r["id"] is not None and r["said"] == CONSENT and r["banned_at"] is None and r["first_name"] is not None


def listing(con, v: Viewer) -> dict:
    """GET /api/credits: the whole screen in two reads. Nobody's Telegram id, row id or consent leaves here, and a
    person without a yes is `person: null` (their lines stay)."""
    top = rows(con, f"""SELECT {PERSON_COLS}, u.banned_at, u.tg_id, {_SAID} AS said FROM users u LEFT JOIN students s ON s.user_id = u.id
        WHERE (u.is_founder = 1 OR u.mark = 'idea') AND u.tg_id > 0""")
    founder = next((p for p in top if p["is_founder"]), None)
    idea = next((p for p in top if p["mark"] == "idea" and not p["is_founder"]), None)
    mine_tg = one(con, "SELECT tg_id FROM users WHERE id = ?", v.id)[0]
    # shipped lines, the newest first; each person stands where their newest line does, their lines together
    got = rows(con, f"""SELECT c.id AS cid, c.tg_id AS whose, c.kind, c.ru, c.kk, c.en, c.shipped_on, {PERSON_COLS}, u.banned_at, {_SAID} AS said
        FROM credits c LEFT JOIN users u ON u.tg_id = c.tg_id AND u.tg_id > 0 LEFT JOIN students s ON s.user_id = u.id
        WHERE c.shipped_on IS NOT NULL ORDER BY c.shipped_on DESC, c.id DESC""")
    people: dict[object, dict] = {}
    idea_items, my_items = [], []
    for r in got:
        if r["whose"] is not None and r["whose"] == mine_tg:
            my_items.append(_item(r))
        if founder and r["whose"] == founder["tg_id"]:
            continue  # the creator's own work is the app itself
        if idea and r["whose"] == idea["tg_id"]:
            idea_items.append(_item(r))
            continue
        key = r["whose"] if r["whose"] is not None else ("gone", r["cid"])  # a deleted account's lines: each alone
        people.setdefault(key, {"person": person_ref(r) if _named(r) else None, "items": []})["items"].append(_item(r))
    is_idea = bool(idea and idea["id"] == v.id)
    said = one(con, f"SELECT {_SAID} FROM users u WHERE u.id = ?", v.id)[0]
    return {
        "founder": person_ref(founder) if founder and founder["banned_at"] is None else None,
        "idea": {"person": person_ref(idea) if _named(idea) else None, "items": idea_items} if idea else None,
        "people": list(people.values()),
        # what is mine here, for the consent sheet and Settings' switch; nothing of mine: null, and neither is offered
        "mine": {"consent": None if said not in (CONSENT, OFF) else said == CONSENT, "idea": is_idea, "items": my_items}
        if v.student and (my_items or is_idea) else None,
        "version": CONSENT,
    }


# ------------------------------------------------------------ the consent

def answer(con, v: Viewer, body: dict) -> dict:
    """PUT /api/credits/consent {show, consent}: my yes (with the version of the text the app showed) or my no; said
    again any time. Kept as a new row each time: who, when, which text."""
    need_student(v)
    if not isinstance(body, dict) or type(body.get("show")) is not bool or (body["show"] and body.get("consent") != CONSENT):
        raise ApiError("bad_input")
    with tx(con):
        if body["show"] and not _has(con, v.id):
            raise ApiError("conflict")  # a yes is to lines the sheet showed: nothing of mine there, nothing to agree to
        con.execute("INSERT INTO credit_consents (user_id, version, at) VALUES (?, ?, ?)", (v.id, CONSENT if body["show"] else OFF, core.now()))
    return listing(con, v)


def ask(con, dry: bool = False) -> int:
    """`kbtu.admin credit ask`: the bot's "shall we name you?" once per person who has a shipped line (or is the
    idea's author), can answer (a student the bot can write to, not banned) and never has. The count."""
    from .seats import notify
    to = rows(con, f"""SELECT u.id FROM users u JOIN students s ON s.user_id = u.id
        WHERE u.tg_id > 0 AND u.banned_at IS NULL AND u.can_dm = 1 AND u.is_founder = 0 AND {_SAID} IS NULL
          AND (u.mark = 'idea' OR EXISTS (SELECT 1 FROM credits c WHERE c.tg_id = u.tg_id AND c.shipped_on IS NOT NULL))
          AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = u.id AND b.kind = 'credit_ask')
        ORDER BY u.id""")
    if not dry:
        with tx(con):
            for r in to:
                notify(con, r["id"], "credit_ask", "cra")
    return len(to)


def _has(con, uid: int) -> bool:
    """Something to name them for: a shipped line, or the idea itself."""
    return one(con, """SELECT 1 FROM users u WHERE u.id = ?
        AND (u.mark = 'idea' OR EXISTS (SELECT 1 FROM credits c WHERE c.tg_id = u.tg_id AND c.shipped_on IS NOT NULL))""", uid) is not None


def asking(con, uid: int) -> bool:
    """The bot, before it sends: still unanswered, still something to name them for."""
    return _has(con, uid) and one(con, f"SELECT {_SAID} FROM users u WHERE u.id = ?", uid)[0] is None


def gone(con, tg_id: int) -> None:
    """A deleted account: its lines stay, nameless for good (no Telegram id left on them)."""
    con.execute("UPDATE credits SET tg_id = NULL WHERE tg_id = ?", (tg_id,))


# ------------------------------------------------------------ the team's CLI (kbtu.admin credit ...)

def add(con, tg_id: int, kind: str, ru: str, kk: str, en: str) -> int:
    lines = [" ".join(x.split()) for x in (ru, kk, en)]
    if tg_id <= 0 or kind not in KINDS or not all(0 < len(x) <= LINE_MAX for x in lines):
        raise ValueError(f"a Telegram id, one of {KINDS}, three lines of 1..{LINE_MAX} characters")
    with tx(con):
        return con.execute("INSERT INTO credits (tg_id, kind, ru, kk, en, created_at) VALUES (?, ?, ?, ?, ?, ?)", (tg_id, kind, *lines, core.now())).lastrowid


def ship(con, cid: int, day: str | None = None) -> str:
    day = day or time.strftime("%Y-%m-%d", time.gmtime(core.now() + 5 * 3600))  # today in Almaty
    try:
        time.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise ValueError("the day as YYYY-MM-DD") from None
    if len(day) != 10:
        raise ValueError("the day as YYYY-MM-DD")
    with tx(con):
        if not con.execute("UPDATE credits SET shipped_on = ? WHERE id = ?", (day, cid)).rowcount:
            raise ValueError(f"no credit {cid}")
    return day


def delete(con, cid: int) -> None:
    with tx(con):
        if not con.execute("DELETE FROM credits WHERE id = ?", (cid,)).rowcount:
            raise ValueError(f"no credit {cid}")
