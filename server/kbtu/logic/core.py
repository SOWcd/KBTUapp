"""The ground every rule stands on: the caller (Viewer), errors, the clock, queries, rights and levels."""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from dataclasses import dataclass


HOLD = 30 * 60          # an unpaid seat waits 30 min for the receipt (§4.3)
log = logging.getLogger("kbtu.logic")
NO_END = 3 * 3600       # an event without an end counts as 3 h long
DOOR_EARLY = 3 * 3600   # check-in opens 3 h before the start (§4.4) …
DOOR_LATE = 6 * 3600    # … and, without an end, closes 6 h after the start
RANK = {"member": 1, "head": 2, "vice": 3, "president": 4}
# A club role's rights (SPEC §2): the toggles of its editor (owner, Oct 7: "as in Telegram"). Each needs a level; the
# highest one a role has is its level, which ranks it for the rank rule (whom it acts on). A level without a club role,
# and a role made before the toggles, has its level's rights; the President has them all.
RIGHTS = {"door": "member", "events": "head", "posts": "head", "people": "head", "casting": "head", "team": "vice", "money": "vice", "memo": "vice", "profile": "vice"}
LEVEL_RIGHTS = {lv: frozenset(r for r, need in RIGHTS.items() if RANK[need] <= RANK[lv]) for lv in RANK}
PROFILE_QR = re.compile(r"\bu_(\d+)_([A-Z2-7]{10})\b")  # a badge QR: …?startapp=u_<id>_<code> (§4.4)
TWO_GIS = re.compile(r"^https://(?:[a-z]+\.)?2gis\.(?:kz|ru|com)/", re.I)
SEASON_MONTHS = (2, 8)  # a season starts in February and in August (§4.11)


class ApiError(Exception):
    STATUS = {"need_student": 401, "forbidden": 403, "not_found": 404, "full": 409, "closed": 409,
              "conflict": 409, "rate_limited": 429, "bad_input": 400, "unavailable": 503}

    def __init__(self, code: str, message: str = "", extra: dict | None = None):
        super().__init__(code)
        self.code, self.message, self.extra = code, message, extra or {}

    @property
    def status(self) -> int:
        return self.STATUS[self.code]


@dataclass(frozen=True)
class Viewer:
    id: int
    role: str                   # platform role: user / moderator / admin
    student: bool               # signed in with KBTU (only students act, §2)


def now() -> int:
    return int(time.time())


def one(con: sqlite3.Connection, sql: str, *args) -> sqlite3.Row | None:
    return con.execute(sql, args).fetchone()


def rows(con: sqlite3.Connection, sql: str, *args) -> list[sqlite3.Row]:
    return con.execute(sql, args).fetchall()


def log_action(con, actor: int | None, action: str, target: str, data: str = "{}") -> None:
    """A line of the audit log, now: who (None: the app itself), what, on what ('user:5'), the details as JSON."""
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, ?, ?, ?, ?)", (actor, action, target, data, now()))


def need_student(v: Viewer) -> None:
    if not v.student:
        raise ApiError("need_student")


def role_in(con, v: Viewer, org: int) -> str | None:
    """My role in an org. Only students can be members (a guest's old rows don't count)."""
    if not v.student:
        return None
    r = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", org, v.id)
    return r["role"] if r else None


def at_least(role: str | None, least: str) -> bool:
    return role is not None and RANK[role] >= RANK[least]


def overseer(con, v: Viewer) -> bool:
    """DMP Head+ (an org with can_oversee) or the admin."""
    return v.role == "admin" or (v.student and one(con, """SELECT 1 FROM org_members m JOIN orgs o ON o.id = m.org_id
        WHERE m.user_id = ? AND o.can_oversee = 1 AND m.role != 'member'""", v.id) is not None)


PERSON_COLS = ("u.id, u.tg_first_name, u.tg_last_name, u.tg_photo_url, u.is_founder, u.mark, u.show_going, s.first_name, s.last_name, u.nick,"
               " u.role AS platform_role,"  # aliased: lists join a club role as `role`
               " CASE WHEN u.avatar_tg = 0 THEN (SELECT path FROM files WHERE id = u.avatar_file_id) END AS own_photo")
PERSON = f"SELECT {PERSON_COLS} FROM users u LEFT JOIN students s ON s.user_id = u.id"


def _once(con, key: str, value: str) -> bool:
    """True the first time a periodic job runs for `value` (a week, a day): the bot's rounds come every few seconds."""
    if one(con, "SELECT 1 FROM meta WHERE key = ? AND value = ?", key, value):
        return False
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))
    return True


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from .clubs import org  # noqa: E402
