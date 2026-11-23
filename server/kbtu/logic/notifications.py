"""Optional bot notifications, their Settings switches, and anonymous delivery totals."""
from __future__ import annotations

from ..db import tx
from . import core
from .core import one, rows

# An allowlist of private outbox templates. Tickets, door alerts, changes to bookings, and
# account, payment and moderation messages never enter this list.
CATEGORIES = {
    "nRemind": ("n_remind", ("remind_2h", "saved_tomorrow", "rate", "comment_question", "comment_answer",
                            "comment_reply", "photo_report", "photo_call", "round_iv_nudge", "round_iv_remind",
                            "santa_soon", "santa_nudge", "santa_eve")),
    "nNewEvents": ("n_new_events", ("new_event", "casting_open", "round_open")),
    "nForumComments": ("n_forum_comments", ("fch_comments",)),
    "nBroadcasts": ("n_broadcasts", ("broadcast", "santa_news", "santa_open")),
    "nDigests": ("n_digests", ("memo_ready", "place_tba")),
    "nFriends": ("n_friends", ("friend_request", "friend_new")),
    "nProjectPings": ("ask_pings", ("ask_match",)),
}
CATEGORY_OF = {kind: key for key, (_, kinds) in CATEGORIES.items() for kind in kinds}
WINDOW = 30


def allowed(con, key: str, uid: int, tg: int) -> bool:
    col, _ = CATEGORIES[key]
    return one(con, f"""SELECT 1 FROM users WHERE id = ? AND tg_id = ? AND tg_id > 0
        AND can_dm = 1 AND banned_at IS NULL AND {col} = 1""", uid, tg) is not None


def set_preference(con, uid: int, key: str, on: bool, undo: str | None = None) -> None:
    """Inside the caller's write transaction. Only the card that changed the switch can undo it."""
    col, _ = CATEGORIES[key]
    path = f"$.{key}"
    # Retain only the last card's signature so a queued tap cannot mute again after the switch changes.
    con.execute(f"""UPDATE users SET {col} = ?, notification_undo =
        CASE WHEN ? IS NULL THEN json_replace(notification_undo, ?, 0)
             ELSE json_set(notification_undo, ?, json_object('card', ?, 'active', 1)) END
        WHERE id = ?""", (int(on), undo, f"{path}.active", path, undo, uid))
    if key == "nForumComments" and not on:
        con.execute("""UPDATE bot_outbox SET error = 'muted' WHERE user_id = ? AND kind = 'fch_comments'
            AND sent_at IS NULL AND error IS NULL""", (uid,))
    if key == "nRemind":
        from .seats import _remind
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND sent_at IS NULL", (uid,))
        if on:
            for e in rows(con, "SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id WHERE r.user_id = ? AND r.status = 'going'", uid):
                _remind(con, uid, e)


def switch_from_chat(con, tg: int, key: str, turn_on: bool, undo: str, sent_at: int) -> tuple[str, bool, bool] | None:
    """Return language, current setting, and whether this card can undo the mute."""
    col, _ = CATEGORIES[key]
    with tx(con):
        path = f"$.{key}"
        u = one(con, f"""SELECT id, lang, {col} AS enabled,
                json_extract(notification_undo, ?) = ? AS same_card, json_extract(notification_undo, ?) AS active
            FROM users WHERE tg_id = ? AND banned_at IS NULL""", f"{path}.card", undo, f"{path}.active", tg)
        if not u:
            return None
        enabled = bool(u["enabled"])
        can_undo = bool(u["same_card"] and u["active"])
        if turn_on:
            if can_undo and not enabled:
                set_preference(con, u["id"], key, True)
            return u["lang"], enabled or can_undo, False
        if enabled and not u["same_card"]:
            set_preference(con, u["id"], key, False, undo)
            feedback(con, key, sent_at, "off")
            return u["lang"], False, True
        return u["lang"], enabled, can_undo


def can_mark_useful(con, tg: int, key: str, undo: str) -> bool:
    # An older Useful snapshot must never replace a successful mute or its Undo.
    return one(con, """SELECT 1 FROM users WHERE tg_id = ? AND banned_at IS NULL
        AND json_extract(notification_undo, ?) IS NOT ?""", tg, f"$.{key}.card", undo) is not None


def _day(at: int) -> int:
    from .daily import day_of
    return day_of(at)


def delivered(con, key: str, at: int) -> None:
    con.execute("""INSERT INTO notification_days (day, category, sent) VALUES (?, ?, 1)
        ON CONFLICT (day, category) DO UPDATE SET sent = sent + 1""", (_day(at), key))


def feedback(con, key: str, sent_at: int, action: str) -> None:
    # Put feedback on the delivery day so the numerator and denominator describe the same messages.
    col = {"useful": "useful", "off": "turned_off"}[action]
    day, today = _day(sent_at), _day(core.now())
    if today - WINDOW < day <= today:
        # A tap can arrive while the postman is still waiting for the send response.
        con.execute(f"""INSERT INTO notification_days (day, category, {col}) VALUES (?, ?, 1)
            ON CONFLICT (day, category) DO UPDATE SET {col} = {col} + 1""", (day, key))


def summary(con, at: int) -> list[dict]:
    today = _day(at)
    totals = {r[0]: tuple(r)[1:] for r in rows(con, """SELECT category, SUM(sent), SUM(useful), SUM(turned_off)
        FROM notification_days WHERE day BETWEEN ? AND ? GROUP BY category""", today - WINDOW + 1, today)}
    out = []
    for key in CATEGORIES:
        sent, useful, off = totals.get(key, (0, 0, 0))
        out.append({"category": key, "sent": sent, "useful": useful, "turnedOff": off})
    return out


def forget(con) -> None:
    con.execute("DELETE FROM notification_days WHERE day < ?", (_day(core.now()) - WINDOW + 1,))
