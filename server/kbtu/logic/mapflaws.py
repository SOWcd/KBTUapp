"""The map's flaws, marked in the app (owner, Oct 29: endless small mistakes, and screenshots bloat the work): a long
press on the plan, a line of text, and the spot lands in the admin's list with its floor and plan units. The app's staff
mark (ten a day each); students not until the privacy policy covers it. Fixed ones go 30 days after."""
from __future__ import annotations

from .core import ApiError, Viewer, need_student, now, one, rows

A_DAY = 10
KEEP = 30 * 86400


def report(con, v: Viewer, body: dict) -> None:
    need_student(v)
    if v.role not in ("admin", "moderator"):  # the owner and the team mark the map (students only once the policy says so)
        raise ApiError("forbidden")
    ver, floor, text = body.get("ver"), body.get("floor"), " ".join(str(body.get("body") or "").split())
    try:
        u, w = float(body["u"]), float(body["v"])
        px, py = (float(body["px"]), float(body["py"])) if body.get("px") is not None else (None, None)
    except (KeyError, TypeError, ValueError):
        raise ApiError("bad_input") from None
    if ver not in ("main", "old", "kbtu") or not isinstance(floor, int) or isinstance(floor, bool) or not 0 <= floor <= 5 \
            or not (0 <= u <= 1 and 0 <= w <= 1) or not 2 <= len(text) <= 300:
        raise ApiError("bad_input")
    if one(con, "SELECT COUNT(*) FROM map_flaws WHERE user_id = ? AND created_at > ?", v.id, now() - 86400)[0] >= A_DAY:
        raise ApiError("rate_limited")
    con.execute("INSERT INTO map_flaws (user_id, ver, floor, u, v, px, py, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (v.id, ver, floor, u, w, px, py, text, now()))


def listing(con, v: Viewer) -> list[dict]:
    """The admin's list: open ones first, oldest first, then the last fixed ones."""
    if v.role != "admin":
        raise ApiError("forbidden")
    return [{"id": r["id"], "ver": r["ver"], "floor": r["floor"], "u": r["u"], "v": r["v"], "px": r["px"], "py": r["py"], "body": r["body"],
             "at": r["created_at"], "done": r["done_at"]} for r in rows(con, """SELECT * FROM map_flaws
        ORDER BY done_at IS NOT NULL, CASE WHEN done_at IS NULL THEN created_at ELSE -done_at END LIMIT 200""")]


def done(con, v: Viewer, fid: int, on: object = True) -> None:
    if v.role != "admin":
        raise ApiError("forbidden")
    if not con.execute("UPDATE map_flaws SET done_at = ? WHERE id = ?", (now() if on is not False else None, fid)).rowcount:
        raise ApiError("not_found")


def sweep(con) -> None:
    con.execute("DELETE FROM map_flaws WHERE done_at < ?", (now() - KEEP,))
