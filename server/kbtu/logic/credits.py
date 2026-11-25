"""The people of the app: the creator, the idea's author, the Team, and everyone whose idea, find (a bug) or code is in it.

The honor medal also qualifies a holder for the consent sheet. Only a current yes adds their medal to this list.
The inscription stays on the profile. Revoking the medal leaves any shipped lines and their consent intact.

A contribution (`credits`, written by the team with `kbtu.admin credit ...`) is a Telegram id (an account or not yet)
or a GitHub login (`gh`: a pull request's author; such a line is never tied to an account, so publishing it ties no
login to a profile here), a kind and one line in ru, kk, en: OUR words about what shipped, never the person's message, gender-neutral and with
no name, handle, link or identifying detail (it is shown under "Student"). It is listed once shipped, newest first by
the day it shipped: no order by amount, nothing to argue about.

The feature's own consent (CONSENT, as evteams'): a name and a face stand next to the lines ONLY after that person's
yes to the text in force, and only while they could give it now (`_CAN`: a signed-in student, not banned). Otherwise
(no answer, a no, a withdrawal, a ban, no account, a deleted or unlinked account) every line stays, each as its own
"Student" row: no name, face, id or link, and nothing that says two nameless lines are one person's. The one exception:
a line with a GitHub login stands under that login (any case), its lines together (the login is public on GitHub). A yes covers the
lines shown and those added later (the sheet says so). Every answer is a row of `credit_consents` (who, when, yes or
no, to which text), never replaced: the latest one counts. A yes names the latest row the app saw (`rev`) and is
refused if a newer answer exists: a late or repeated yes never undoes a withdrawal. Asked by the bot's template once
per person and text version (`ask`), answered in the app, changed in Settings.

The Team (`credit_team`, `kbtu.admin team add|del`, audited): the core developers the creator picked, first added first,
each a card with their lines under it (not again below). Being on it is something to say yes to, as a line is; without
that yes a member is not in the block at all, their lines stay below as anyone's.

The creator alone is named without a consent row: on purpose, he is public as the creator everywhere already
(`person.founder`, /api/me's support), and nothing else of his is shown here. The idea's author follows the rule.

Deleting an account: its consents go (`_DEL_GONE`) and its lines lose the Telegram id (`gone`): what the app got stays
in the list as nameless "Student" rows, and nothing left behind points at the person. An account moved to another
Telegram (`kbtu.admin move`) takes its lines along and its yes ends (`moved`): the new profile is previewed afresh.
"""
from __future__ import annotations

import hashlib
import re
import time

from . import core
from ..db import tx
from .core import PERSON_COLS, ApiError, Viewer, one, person_ref, rows

KINDS = ("idea", "find", "code")
LINE_MAX = 90     # a line is a few words; the CLI refuses more
CONSENT = "cr1"   # the consent sheet's text (web: cr.ask*); a reworded sheet is a new version, and old yeses ask again
REMIND = "lines are OUR words: gender-neutral, no name, handle, link or identifying detail (shown under \"Student\")"

# the one rule of who may be named, answer and be asked: a signed-in student (not a typed-in row), not banned.
# Over `users u LEFT JOIN students s`
_CAN = "(u.tg_id > 0 AND u.banned_at IS NULL AND s.user_id IS NOT NULL AND s.manual = 0)"
# the latest answer, joined as k
_LAST = "LEFT JOIN credit_consents k ON k.id = (SELECT x.id FROM credit_consents x WHERE x.user_id = u.id ORDER BY x.id DESC LIMIT 1)"
_HONOR = "EXISTS (SELECT 1 FROM achievement_grants g WHERE g.user_id = u.id AND g.code = 'honor')"
_TEAM = "EXISTS (SELECT 1 FROM credit_team t WHERE t.user_id = u.id)"
_HAS = f"((u.is_founder = 0 AND ({_HONOR} OR {_TEAM})) OR u.mark = 'idea' OR EXISTS (SELECT 1 FROM credits c WHERE c.tg_id = u.tg_id AND c.shipped_on IS NOT NULL))"
_COLS = f"{PERSON_COLS}, u.tg_id, u.banned_at, {_CAN} AS can, k.id AS rev, k.show, k.version"


def _said(r) -> bool | None:
    """Their answer as it stands: a yes to this text, a no (to any text: never asked again), or none (an old yes too)."""
    return None if r["rev"] is None or (r["show"] and r["version"] != CONSENT) else bool(r["show"])


def _state(con, uid: int):
    return one(con, f"SELECT {_COLS}, {_HONOR} AS honor, {_TEAM} AS team, {_HAS} AS has FROM users u LEFT JOIN students s ON s.user_id = u.id {_LAST} WHERE u.id = ?", uid)


# ------------------------------------------------------------ the list

def _item(r) -> dict:
    return {"kind": r["kind"], "text": {"ru": r["ru"], "kk": r["kk"], "en": r["en"]}, "on": r["shipped_on"]}


def _named(r) -> bool:
    return bool(r) and r["id"] is not None and bool(r["can"]) and _said(r) is True


def _tie(cid: int) -> str:
    """Same-day lines in an order that says nothing of when they were entered or whose they are."""
    return hashlib.sha256(f"credit:{cid}".encode()).hexdigest()


def listing(con, v: Viewer) -> dict:
    """GET /api/credits: the whole screen in four reads. Nobody's Telegram id, row id or answer leaves here; a line
    without its person's yes is a row of its own with `person: null`."""
    if not con.in_transaction:  # one snapshot for all the reads: an answer landing between them can't pair an old
        con.execute("BEGIN")    # yes with a newer line
        try:
            return listing(con, v)
        finally:
            con.execute("COMMIT")
    top = rows(con, f"""SELECT {_COLS}, g.created_at AS honored FROM users u LEFT JOIN students s ON s.user_id = u.id {_LAST}
        LEFT JOIN achievement_grants g ON g.user_id = u.id AND g.code = 'honor'
        WHERE (u.is_founder = 1 OR u.mark = 'idea' OR g.id IS NOT NULL) AND u.tg_id > 0""")
    founder = next((p for p in top if p["is_founder"]), None)
    idea = next((p for p in top if p["mark"] == "idea" and not p["is_founder"]), None)
    # the Team: only who said yes; the creator and the idea's author have their own cards
    team = [r for r in rows(con, f"""SELECT {_COLS}, {_HONOR} AS honored FROM credit_team t JOIN users u ON u.id = t.user_id
        LEFT JOIN students s ON s.user_id = u.id {_LAST}
        WHERE u.is_founder = 0 AND u.mark IS NOT 'idea' ORDER BY t.added_at, t.user_id""") if _named(r)]
    team_items: dict[int, list] = {r["tg_id"]: [] for r in team}
    me = _state(con, v.id)
    got = rows(con, f"""SELECT c.id AS cid, c.tg_id AS whose, c.gh, c.kind, c.ru, c.kk, c.en, c.shipped_on, {_COLS}
        FROM credits c LEFT JOIN users u ON u.tg_id = c.tg_id AND u.tg_id > 0 LEFT JOIN students s ON s.user_id = u.id {_LAST}
        WHERE c.shipped_on IS NOT NULL ORDER BY c.shipped_on DESC, c.id DESC""")
    people: dict[object, dict] = {}
    idea_items, my_items = [], []
    for r in got:
        if r["whose"] is not None and r["whose"] == me["tg_id"]:
            my_items.append(_item(r))
        if founder and r["whose"] == founder["tg_id"]:
            continue  # the creator's own work is the app itself
        if _named(idea) and r["whose"] == idea["tg_id"]:
            idea_items.append(_item(r))
            continue
        if r["whose"] in team_items:
            team_items[r["whose"]].append(_item(r))
            continue
        named = _named(r)
        # a named person's lines together, where their newest stands; a GitHub login's too; a nameless line alone
        gh = None if named else r["gh"]  # newest first: the row shows its newest line's spelling
        row = people.setdefault(r["whose"] if named else ("gh", gh.lower()) if gh else ("line", r["cid"]),
                                {"person": person_ref(r) if named else None, "gh": gh, "items": [], "at": (r["shipped_on"], _tie(r["cid"]))})
        row["items"].append(_item(r))
    # Only a named holder gets a medal entry. A shipped credit keeps its own anonymity and sort order.
    for r in top:
        if r["honored"] is None or not _named(r) or r["is_founder"] or r["mark"] == "idea" or r["tg_id"] in team_items:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(r["honored"] + 5 * 3600))
        row = people.setdefault(r["tg_id"], {"person": person_ref(r), "gh": None, "items": [], "at": (day, _tie(r["id"]))})
        row["honor"] = True
    is_idea = bool(idea and idea["id"] == v.id)
    is_team = bool(me["team"]) and not is_idea and not me["is_founder"]
    said = _said(me)
    return {
        "founder": person_ref(founder) if founder and founder["banned_at"] is None else None,
        "idea": {"person": person_ref(idea) if _named(idea) else None, "items": idea_items,
                 **({"honor": True} if _named(idea) and idea["honored"] is not None else {})} if idea else None,
        "team": [{"person": person_ref(r), "items": team_items[r["tg_id"]], **({"honor": True} if r["honored"] else {})} for r in team],
        "people": [{"person": p["person"], "items": p["items"], **({"honor": True} if p.get("honor") else {})} | ({"gh": p["gh"]} if p["gh"] else {}) for p in sorted(people.values(), key=lambda p: p["at"], reverse=True)],
        # what is mine here, for the consent sheet and Settings' switch (kept while a yes stands, to take it back);
        # rev: my latest answer, which a yes must name. Nothing of mine: null, and nothing is offered
        "mine": {"consent": said, "rev": me["rev"], "idea": is_idea, "items": my_items, **({"honor": True} if me["honor"] and not me["is_founder"] else {}),
                 **({"team": True} if is_team else {})}
        if me["can"] and (my_items or is_idea or is_team or said or (me["honor"] and not me["is_founder"])) else None,
        "version": CONSENT,
    }


# ------------------------------------------------------------ the consent

def answer(con, v: Viewer, body: dict) -> dict:
    """PUT /api/credits/consent {show, consent, rev}: my yes or my no, said again any time; each a new row.
    A yes: to the text in force (`consent`), with something of mine to name me for, by one who may be named, and on
    top of the latest answer the app saw (`rev`, null: none): a yes from an older sheet, or sent twice, is `conflict`
    and changes nothing. A no is never refused for being late: it only ever hides."""
    if not isinstance(body, dict) or type(body.get("show")) is not bool:
        raise ApiError("bad_input")
    show, version, rev = body["show"], body.get("consent"), body.get("rev")
    if show and (version != CONSENT or not (rev is None or type(rev) is int)):
        raise ApiError("bad_input")
    if not show and not (isinstance(version, str) and re.fullmatch(r"cr\d{1,4}", version)):
        version = CONSENT  # an old app's no: recorded against the text in force
    with tx(con):
        me = _state(con, v.id)  # read again under the write lock: banned, unlinked or moved since the request began
        if not me["can"]:
            raise ApiError("need_student")
        if show and not me["has"]:
            raise ApiError("conflict", "nothing")  # a yes is to lines the sheet showed
        if show and me["rev"] != rev:
            raise ApiError("conflict", "stale")
        con.execute("INSERT INTO credit_consents (user_id, show, version, at) VALUES (?, ?, ?, ?)", (v.id, int(show), version, core.now()))
    return listing(con, v)


_ASKABLE = f"""{_CAN} AND u.is_founder = 0 AND {_HAS} AND (k.id IS NULL OR (k.show = 1 AND k.version != '{CONSENT}'))"""


def ask(con, dry: bool = False) -> int:
    """`kbtu.admin credit ask`: the bot's "shall we name you?" once per person and text version: those with a shipped
    line (or the idea's author, or on the Team) who can answer (`_CAN`, and the bot can write to them) and have not: never answered,
    or said yes to an older text. An explicit no is never asked again. The number of messages actually queued."""
    ref = f"cra:{CONSENT}"
    to = rows(con, f"""SELECT u.id FROM users u LEFT JOIN students s ON s.user_id = u.id {_LAST}
        WHERE {_ASKABLE} AND u.can_dm = 1
          AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = u.id AND b.kind = 'credit_ask' AND b.ref = ?)
        ORDER BY u.id""", ref)
    if dry:
        return len(to)
    with tx(con):
        return sum(con.execute("INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after) VALUES (?, 'credit_ask', ?, '{}', ?)",
                               (r["id"], ref, core.now())).rowcount for r in to)


def asking(con, uid: int) -> int | None:
    """The bot, as it takes the message to send: the Telegram id to write to, read now (the account may have moved),
    while it is still theirs to answer (not banned, unlinked or answered meanwhile); else None."""
    r = one(con, f"SELECT u.tg_id FROM users u LEFT JOIN students s ON s.user_id = u.id {_LAST} WHERE u.id = ? AND {_ASKABLE}", uid)
    return r[0] if r else None


def gone(con, tg_id: int) -> None:
    """A deleted account: its lines stay, nameless for good (no Telegram id left on them)."""
    con.execute("UPDATE credits SET tg_id = NULL WHERE tg_id = ?", (tg_id,))


def moved(con, uid: int, old_tg: int, new_tg: int, merge: bool = False) -> None:
    """`kbtu.admin move`, inside its transaction: the account's lines follow it to its new Telegram, and its yes ends
    (another name and face may stand there now: asked afresh; a merged move is not undone by moving back). Lines already written for the new Telegram id would
    come under this account too: refused unless the team says they are the same person's (`--merge-credits`)."""
    if not merge and one(con, "SELECT 1 FROM credits WHERE tg_id = ?", new_tg):
        raise ValueError("the target Telegram has its own lines in People of the app: --merge-credits if they are this person's too")
    con.execute("UPDATE credits SET tg_id = ? WHERE tg_id = ?", (new_tg, old_tg))
    # always a new "no" row where there is anything to answer about: a yes still on its way from the old Telegram names
    # an older answer (or none) and is refused, whatever the last answer was
    if (one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'honor'", uid) or one(con, "SELECT 1 FROM credit_team WHERE user_id = ?", uid)
            or one(con, "SELECT 1 FROM credits WHERE tg_id = ?", new_tg) or one(con, "SELECT 1 FROM credit_consents WHERE user_id = ?", uid)):
        con.execute("INSERT INTO credit_consents (user_id, show, version, at) VALUES (?, 0, ?, ?)", (uid, CONSENT, core.now()))


# ------------------------------------------------------------ the team's CLI (kbtu.admin credit ...)

GH = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")  # GitHub's own login rule, near enough


def add(con, who: int | str, kind: str, ru: str, kk: str, en: str) -> int:
    """who: a Telegram id, or "gh:<login>" (never tied to an account: no binding, so no login is linked to a profile)."""
    lines = [" ".join(x.split()) for x in (ru, kk, en)]
    gh = who[3:] if isinstance(who, str) and who.startswith("gh:") else None
    if gh is not None and not GH.fullmatch(gh):
        raise ValueError("gh:<a GitHub login>")
    tg_id = None if gh is not None else int(who)
    if (tg_id is not None and tg_id <= 0) or kind not in KINDS or not all(0 < len(x) <= LINE_MAX for x in lines):
        raise ValueError(f"a Telegram id, one of {KINDS}, three lines of 1..{LINE_MAX} characters")
    if any(re.search(r"@\w|https?://|t\.me/|www\.|\d{5,}", x, re.I) for x in lines):
        raise ValueError(f"no handle, link or id in a line: {REMIND}")
    with tx(con):
        return con.execute("INSERT INTO credits (tg_id, gh, kind, ru, kk, en, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (tg_id, gh, kind, *lines, core.now())).lastrowid


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


def team(con, uid: int, on: bool) -> bool:
    """`kbtu.admin team add|del`: the creator puts a person on the Team or takes them off, in the audit log. Whether
    anything changed."""
    with tx(con):
        n = (con.execute("INSERT OR IGNORE INTO credit_team (user_id, added_at) VALUES (?, ?)", (uid, core.now())) if on
             else con.execute("DELETE FROM credit_team WHERE user_id = ?", (uid,))).rowcount
        if n:
            core.log_action(con, None, "team_add" if on else "team_del", f"user:{uid}")
    return bool(n)


def delete(con, cid: int) -> None:
    with tx(con):
        if not con.execute("DELETE FROM credits WHERE id = ?", (cid,)).rowcount:
            raise ValueError(f"no credit {cid}")
