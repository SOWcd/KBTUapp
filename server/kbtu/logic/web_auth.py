"""Opaque browser sessions and single-use Telegram Login proofs."""
from __future__ import annotations

import hashlib
import re
import secrets

from .. import auth, db
from . import core
from .core import ApiError, one
from .daily import day_of, visit

COOKIE = "__Host-kb-session"
IDLE = 60 * 86400
MAX_AGE = 90 * 86400
STAFF_MAX_AGE = 14 * 86400

_SESSION_USER = "web_sessions s JOIN users u ON u.id = s.user_id LEFT JOIN students st ON st.user_id = u.id"
_AGE_LIMIT = f"""CASE WHEN u.role IN ('moderator', 'admin') OR u.is_founder OR {core.staff_sql('st')}
                 THEN {STAFF_MAX_AGE} ELSE {MAX_AGE} END"""


def _digest(token: str) -> bytes | None:
    if re.fullmatch(r"[0-9a-f]{64}", token):
        return hashlib.sha256(bytes.fromhex(token)).digest()
    return None


def consume(con, data: dict, t: int) -> None:
    # A proof must stay spent even if its session is signed out or the account erased.
    proof = hashlib.sha256(bytes.fromhex(data["hash"])).digest()
    if not con.execute("INSERT OR IGNORE INTO web_login_used VALUES (?, ?)",
                       (proof, data["auth_date"] + auth.WIDGET_MAX_AGE)).rowcount:
        raise ApiError("forbidden", "web_login")
    forget(con, t)


def issue(con, uid: int, old_token: str, t: int) -> str:
    revoke(con, old_token)
    token = secrets.token_hex(32)
    con.execute("INSERT INTO web_sessions VALUES (?, ?, ?, ?)", (_digest(token), uid, t, t))
    return token


def revoke(con, token: str) -> None:
    if digest := _digest(token):
        con.execute("DELETE FROM web_sessions WHERE digest = ?", (digest,))


def revoke_all(con, uid: int) -> None:
    con.execute("DELETE FROM web_sessions WHERE user_id = ?", (uid,))


def forget(con, t: int) -> None:
    con.execute("DELETE FROM web_sessions WHERE last_used_at <= ?", (t - IDLE,))
    con.execute(f"""DELETE FROM web_sessions WHERE digest IN (
        SELECT s.digest FROM {_SESSION_USER} WHERE s.created_at <= ? - ({_AGE_LIMIT})
    )""", (t,))
    con.execute("DELETE FROM web_login_used WHERE expires_at <= ?", (t,))


def lookup(con, token: str, admins: frozenset[int]):
    digest = _digest(token)
    t = core.now()
    u = one(con, f"""SELECT u.*, s.last_used_at, s.created_at AS session_created_at, ({_AGE_LIMIT}) AS session_max_age
        FROM {_SESSION_USER} WHERE s.digest = ? AND s.last_used_at > ? AND u.banned_at IS NULL AND u.tg_id > 0""",
            digest, t - IDLE) if digest else None
    if u is None:
        raise ApiError("unauthorized", "web_session")
    # An environment admin may still have the old role in the database until touch() runs.
    max_age = STAFF_MAX_AGE if u["tg_id"] in admins else u["session_max_age"]
    if u["session_created_at"] <= t - max_age:
        # A rejected session should stay expired if the account's role changes again.
        db.maybe(con, revoke, con, token)
        raise ApiError("unauthorized", "web_session")
    return u


def touch(con, token: str, u, admins: frozenset[int], seen_every: int) -> bool:
    t = core.now()
    promote = u["tg_id"] in admins and u["role"] != "admin"
    seen = t - u["seen_at"] > seen_every or day_of(t) != day_of(u["seen_at"])
    if t <= u["last_used_at"] and not (seen or promote):
        return False

    def update() -> bool:
        digest = _digest(token)
        changed = con.execute("""UPDATE web_sessions SET last_used_at = ?
            WHERE digest = ? AND last_used_at < ?""", (t, digest, t)).rowcount
        if seen or promote:
            if con.execute("""UPDATE users SET seen_at = ?, role = CASE WHEN ? THEN 'admin' ELSE role END
                WHERE id = ? AND seen_at = ? AND banned_at IS NULL
                AND EXISTS (SELECT 1 FROM web_sessions WHERE digest = ? AND user_id = users.id)""",
                           (t, int(promote), u["id"], u["seen_at"], digest)).rowcount:
                visit(con, u["id"], t)
        return bool(changed)

    return bool(db.maybe(con, update))
