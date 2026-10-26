"""A club's team: ranks, roles, departments, invite links."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from pathlib import Path

from ..db import tx

from .core import (ApiError, LEVEL_RIGHTS, PERSON, PERSON_COLS, RANK, RIGHTS, Viewer, _may, _org, _rights_from, can,
    log_action, need_student, one, person_ref, rights_of, role_in, rows, short_name)


# ---------------------------------------------------------------- the club's own team (SPEC §2: the rank rule)

def team(con, v: Viewer, oid: int) -> list[dict]:
    """The full roster for the club's own team (§3): full names and @usernames, highest role first, with the club's own
    role name and the tags (§2b). Probation: for the club's Head+ and the person. Vice+ also see who
    hasn't been checked in at the club's events for 60 days, to keep the roster real (§4.13)."""
    mine = role_in(con, v, oid)
    if not mine:
        raise ApiError("forbidden")
    r = rights_of(con, v.id, oid)
    vice, head = "team" in r, "people" in r
    found = rows(con, f"""SELECT {PERSON_COLS}, u.tg_username, m.role, m.joined_at, m.role_id, m.probation, t.name AS title, t.color AS title_color,
        (SELECT MAX(r.checked_in_at) FROM registrations r JOIN events e ON e.id = r.event_id WHERE e.org_id = m.org_id AND r.user_id = u.id) AS seen,
        (SELECT group_concat(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id WHERE g.org_id = m.org_id AND mt.user_id = u.id) AS tags,
        (SELECT MIN(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id WHERE g.org_id = m.org_id AND mt.user_id = u.id AND g.department) AS dept
        FROM org_members m JOIN users u ON u.id = m.user_id JOIN students s ON s.user_id = u.id LEFT JOIN org_roles t ON t.id = m.role_id
        WHERE m.org_id = ?""", oid)
    return sorted(({"person": person_ref(p), "fullName": f"{p['last_name']} {p['first_name']}".strip(), "username": p["tg_username"],
                    "role": p["role"], "roleId": p["role_id"], "title": p["title"], "titleColor": p["title_color"],
                    "tags": sorted(int(x) for x in (p["tags"] or "").split(",") if x), "dept": p["dept"], "joinedAt": p["joined_at"],
                    "quiet": vice and (p["seen"] or p["joined_at"]) < core.now() - QUIET_FOR,
                    # theirs, and Head+ strictly above them (the rank rule; audit L10: a Head saw the Vice's)
                    **({"probation": bool(p["probation"])} if (head and RANK[mine] > RANK[p["role"]]) or p["id"] == v.id else {})}
                   for p in found), key=lambda m: (-RANK[m["role"]], m["fullName"]))


def _below(con, v: Viewer, oid: int, uid: int, right: str) -> str:
    """My role, if I may act on them: the right, and strictly above them by the rank rule (§2)."""
    mine = role_in(con, v, oid)
    theirs = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)
    if not theirs:
        raise ApiError("not_found")
    if not can(con, v, oid, right) or RANK[mine] <= RANK[theirs["role"]]:
        raise ApiError("forbidden")
    return mine


def dept_of(con, oid: int, uid: int) -> int | None:
    """Their department in the club: a tag marked department (one per person; several from before: the first)"""
    r = one(con, """SELECT MIN(g.id) FROM member_tags mt JOIN org_tags g ON g.id = mt.tag_id
        WHERE g.org_id = ? AND mt.user_id = ? AND g.department = 1""", oid, uid)
    return r[0] if r else None


def _manage(con, v: Viewer, oid: int, uid: int) -> str:
    """My role, if the rank rule lets me manage them: Vice+, and strictly above them."""
    return _below(con, v, oid, uid, "team")


def _remove(con, actor: int, oid: int, uid: int, ban: bool, by: str) -> None:
    """Someone is out of the club: their tags and open removal requests there go too; banned, they can't come
    back by an application or the link until a Vice+ lifts it (§2b)."""
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (oid, uid))
    con.execute("DELETE FROM member_tags WHERE user_id = ? AND tag_id IN (SELECT id FROM org_tags WHERE org_id = ?)", (uid, oid))
    con.execute("UPDATE removal_requests SET status = 'done', decided_by = ?, decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'",
                (actor, core.now(), oid, uid))
    if ban:
        con.execute("INSERT OR REPLACE INTO org_bans (org_id, user_id, by_id, created_at) VALUES (?, ?, ?, ?)", (oid, uid, actor, core.now()))
        con.execute("UPDATE join_requests SET status = 'rejected', decided_by = ?, decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'",
                    (actor, core.now(), oid, uid))
    log_action(con, actor, "role_change", f"user:{uid}", json.dumps({"org": oid, "role": "none", "by": by, **({"ban": True} if ban else {})}))


def remove_member(con, v: Viewer, oid: int, uid: int) -> None:
    """Vice+ remove someone below them; anyone leaves by themselves, except the President, who hands the club over first."""
    if uid == v.id:
        r = role_in(con, v, oid)
        if not r:
            raise ApiError("not_found")
        if r == "president":
            raise ApiError("conflict", "president")
    else:
        _manage(con, v, oid, uid)
    with tx(con):
        _remove(con, v.id, oid, uid, False, "self" if uid == v.id else "team")


def transfer(con, v: Viewer, oid: int, uid: int) -> list[dict]:
    """Only the President hands the club over, to someone already in it; they become Vice (§2)."""
    if role_in(con, v, oid) != "president":
        raise ApiError("forbidden")
    if uid == v.id or not one(con, "SELECT 1 FROM org_members m JOIN students s ON s.user_id = m.user_id WHERE m.org_id = ? AND m.user_id = ?", oid, uid):
        raise ApiError("not_found")
    with tx(con):  # the club's own role names stay below the President: both start plain
        con.execute("UPDATE org_members SET role = 'vice', role_id = ? WHERE org_id = ? AND user_id = ?", (_official(con, oid, "vice"), oid, v.id))
        con.execute("UPDATE org_members SET role = 'president', role_id = NULL, probation = 0 WHERE org_id = ? AND user_id = ?", (oid, uid))
        log_action(con, v.id, "presidency_transfer", f"org:{oid}", json.dumps({"to": uid}))
    return team(con, v, oid)


# ---------------------------------------------------------------- Team 2.0 (SPEC §2b)
# A club's own roles are a name and colour on one of the levels, so every rights check stays on the level. Tags are
# groups of people. Probation: Head+ put someone below them on it, a label until the President or Vice take it off
# (the strikes that came with it went on Oct 22; never used). A Head asks to remove someone; a Vice+ removes at once; either may ban from coming back.

HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _named(body: dict) -> tuple[str, str]:
    name, color = " ".join(str(body.get("name") or "").split()), str(body.get("color") or "")
    if not (1 <= len(name) <= 24 and HEX.fullmatch(color)):
        raise ApiError("bad_input")
    return name, color


def team_setup(con, v: Viewer, oid: int) -> dict:
    """What Team needs besides the roster: the club's roles and tags (the whole team sees them), and for Vice+ the open
    removal requests (each says whether I outrank the person and so may decide) and the bans."""
    mine = role_in(con, v, oid)
    if not mine:
        raise ApiError("forbidden")
    out: dict = {
        "roles": [{"id": r["id"], "name": r["name"], "color": r["color"], "level": r["level"], "rights": _ordered(_rights_from(r["level"], r["rights"])),
                   "count": r["n"], "fixed": bool(r["fixed"])} for r in rows(con, """SELECT r.*,
            (SELECT COUNT(*) FROM org_members m WHERE m.role_id = r.id) AS n FROM org_roles r WHERE r.org_id = ?
            ORDER BY r.fixed DESC, r.fixed AND r.level = 'head', r.id""", oid)],
        "tags": [{"id": g["id"], "name": g["name"], "color": g["color"], "count": g["n"], "department": bool(g["department"])} for g in rows(con, """SELECT g.*,
            (SELECT COUNT(*) FROM member_tags mt JOIN org_members m ON m.user_id = mt.user_id AND m.org_id = g.org_id WHERE mt.tag_id = g.id) AS n
            FROM org_tags g WHERE g.org_id = ? ORDER BY g.id""", oid)],
        "myDept": dept_of(con, oid, v.id),
    }
    if can(con, v, oid, "team"):
        asks = rows(con, f"""SELECT q.*, m.role, {PERSON_COLS} FROM removal_requests q JOIN org_members m ON m.org_id = q.org_id AND m.user_id = q.user_id
            JOIN users u ON u.id = q.user_id JOIN students s ON s.user_id = u.id WHERE q.org_id = ? AND q.status = 'pending' ORDER BY q.id""", oid)
        by = {b["id"]: b for b in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(asks))})", *[a["by_id"] for a in asks])} if asks else {}
        out["removals"] = [{"id": a["id"], "person": person_ref(a), "fullName": f"{a['last_name']} {a['first_name']}".strip(),
                            "by": person_ref(by[a["by_id"]]) if a["by_id"] in by else None, "ban": bool(a["ban"]), "note": a["note"],
                            "at": a["created_at"], "canDecide": RANK[mine] > RANK[a["role"]]} for a in asks]
        out["bans"] = [{"person": person_ref(b), "fullName": f"{b['last_name'] or ''} {b['first_name'] or ''}".strip() or short_name(b), "at": b["created_at"]}
                       for b in rows(con, f"""SELECT {PERSON_COLS}, x.created_at FROM org_bans x JOIN users u ON u.id = x.user_id
                           LEFT JOIN students s ON s.user_id = u.id WHERE x.org_id = ? ORDER BY x.created_at DESC""", oid)]
    return out


def _ordered(rights) -> list[str]:
    return [r for r in RIGHTS if r in rights]


def save_role(con, v: Viewer, oid: int, body: dict, rid: int | None = None) -> dict:
    """Whoever runs the team ("team") makes the club's own roles: a name, a colour and toggles of rights (SPEC §2), only
    rights they have themselves and below their own level (the rights' highest level is the role's); a changed level
    moves everyone holding the role (they are all below the editor). A `level` alone (an older app) means its rights.
    The official Vice and Head (`fixed`) keep their name and level."""
    mine = role_in(con, v, oid)
    if not can(con, v, oid, "team"):
        raise ApiError("forbidden")
    name, color = _named(body)
    rights = body["rights"] if "rights" in body else list(LEVEL_RIGHTS[body["level"]]) if body.get("level") in ("member", "head", "vice") else None
    if not isinstance(rights, list) or any(r not in RIGHTS for r in rights):
        raise ApiError("bad_input")
    rights = _ordered(rights)
    level = max((RIGHTS[r] for r in rights), key=RANK.__getitem__, default="member")
    if RANK[level] >= RANK[mine] or not set(rights) <= rights_of(con, v.id, oid):
        raise ApiError("forbidden")
    with tx(con):
        if rid is None:
            if one(con, "SELECT COUNT(*) FROM org_roles WHERE org_id = ?", oid)[0] >= 20:
                raise ApiError("conflict", "many")
        else:
            r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid)
            if not r:
                raise ApiError("not_found")
            if RANK[r["level"]] >= RANK[mine] or r["fixed"] and RANK[level] > RANK[r["level"]]:
                raise ApiError("forbidden")
            if r["fixed"]:  # an official role keeps its name and level; its rights below the level may be tuned
                name, level = r["name"], r["level"]
        try:
            if rid is None:
                con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (oid, name, color, level, ",".join(rights), core.now()))
            else:
                con.execute("UPDATE org_roles SET name = ?, color = ?, level = ?, rights = ? WHERE id = ?", (name, color, level, ",".join(rights), rid))
                con.execute("UPDATE org_members SET role = ? WHERE org_id = ? AND role_id = ?", (level, oid, rid))
        except sqlite3.IntegrityError:
            raise ApiError("conflict", "taken") from None
    return team_setup(con, v, oid)


def delete_role(con, v: Viewer, oid: int, rid: int) -> dict:
    """A role goes; whoever held it keeps the level and its rights, without the name."""
    mine = role_in(con, v, oid)
    r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid)
    if not can(con, v, oid, "team"):
        raise ApiError("forbidden")
    if not r:
        raise ApiError("not_found")
    if RANK[r["level"]] >= RANK[mine] or r["fixed"]:
        raise ApiError("forbidden")
    con.execute("DELETE FROM org_roles WHERE id = ?", (rid,))
    return team_setup(con, v, oid)


def save_tag(con, v: Viewer, oid: int, body: dict, tid: int | None = None) -> dict:
    """Head+ make the club's tags (SMM, Design, ...): a name and a colour; `department` marks it a department (PLAN 47:
    one per person, Team groups by it). Unmarking leaves the people tagged."""
    _may(con, v, oid, "people")
    name, color = _named(body)
    dept = body.get("department")
    if dept is not None and not isinstance(dept, bool):
        raise ApiError("bad_input")
    was = one(con, "SELECT department FROM org_tags WHERE id = ? AND org_id = ?", tid, oid) if tid is not None else None
    if dept is not None and bool(dept) != bool(was and was[0]) and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
        raise ApiError("forbidden")  # a Head unmarking a department would sidestep its rules: Vice+ only
    with tx(con):
        if tid is None and one(con, "SELECT COUNT(*) FROM org_tags WHERE org_id = ?", oid)[0] >= 30:
            raise ApiError("conflict", "many")
        if tid is not None and not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ?", tid, oid):
            raise ApiError("not_found")
        try:
            if tid is None:
                con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, ?, ?, ?, ?)", (oid, name, color, int(bool(dept)), core.now()))
            else:
                con.execute("UPDATE org_tags SET name = ?, color = ?, department = COALESCE(?, department) WHERE id = ?",
                            (name, color, None if dept is None else int(dept), tid))
        except sqlite3.IntegrityError:
            raise ApiError("conflict", "taken") from None
    return team_setup(con, v, oid)


def delete_tag(con, v: Viewer, oid: int, tid: int) -> dict:
    _may(con, v, oid, "people")
    if not con.execute("DELETE FROM org_tags WHERE id = ? AND org_id = ?", (tid, oid)).rowcount:
        raise ApiError("not_found")
    return team_setup(con, v, oid)


def update_member(con, v: Viewer, oid: int, uid: int, body: dict) -> list[dict]:
    """One person in Team (§2b), only what is sent: `role` (a level) or `roleId` (one of the club's roles; null: just the
    level) — Vice+ by the rank rule, and on myself one of the club's roles at my own level (a name, no more rights);
    `tags` — Head+ on themselves or anyone below them, Vice+ on anyone (labels, no power, the
    President and the Vice tag each other; departments in it are left as they are); `dept` — the department (a tag
    marked so) or null for none (PLAN 47): Vice+ on anyone; a Head on those below them, only into or out of the Head's
    own department, never their own; `probation` — Head+ put someone
    below them on it, only the President or Vice take it off (passed: the bot congratulates)."""
    if not body or not set(body) <= {"role", "roleId", "tags", "dept", "probation"}:
        raise ApiError("bad_input")
    with tx(con):
        if "role" in body or "roleId" in body:
            rid = body.get("roleId")
            mine = role_in(con, v, oid) if uid == v.id and rid is not None else _manage(con, v, oid, uid)
            if not mine:
                raise ApiError("forbidden")
            if rid is not None:
                r = one(con, "SELECT * FROM org_roles WHERE id = ? AND org_id = ?", rid, oid) if isinstance(rid, int) and not isinstance(rid, bool) else None
                if not r:
                    raise ApiError("bad_input")
                role, given = r["level"], _rights_from(r["level"], r["rights"])
            else:
                role = str(body.get("role") or "")
                if role not in RANK:
                    raise ApiError("bad_input")
                given = LEVEL_RIGHTS[role]
                rid = _official(con, oid, role)  # a Vice or Head level is its official role
                if rid:
                    given = _rights_from(role, one(con, "SELECT rights FROM org_roles WHERE id = ?", rid)[0])
            if (RANK[role] != RANK[mine] if uid == v.id else RANK[role] >= RANK[mine]) or not given <= rights_of(con, v.id, oid):  # only rights I have myself (as in Telegram)
                raise ApiError("forbidden")
            con.execute("UPDATE org_members SET role = ?, role_id = ? WHERE org_id = ? AND user_id = ?", (role, rid, oid, uid))
            log_action(con, v.id, "role_change", f"user:{uid}", json.dumps({"org": oid, "role": role, "roleId": rid, "by": "team"}))
        if "tags" in body:
            tags = body["tags"]
            if uid != v.id and RANK[role_in(con, v, oid) or "member"] < RANK["vice"]:
                _below(con, v, oid, uid, "people")
            elif not can(con, v, oid, "people") or not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
                raise ApiError("forbidden")
            if not isinstance(tags, list) or len(tags) > 10 or any(not isinstance(x, int) or isinstance(x, bool) for x in tags):
                raise ApiError("bad_input")
            if len(set(tags)) != one(con, f"SELECT COUNT(*) FROM org_tags WHERE org_id = ? AND id IN ({','.join('?' * len(set(tags))) or 'NULL'})", oid, *set(tags))[0]:
                raise ApiError("bad_input")
            depts = {r[0] for r in rows(con, "SELECT id FROM org_tags WHERE org_id = ? AND department = 1", oid)}
            con.execute("DELETE FROM member_tags WHERE user_id = ? AND tag_id IN (SELECT id FROM org_tags WHERE org_id = ? AND department = 0)", (uid, oid))
            con.executemany("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", [(t, uid) for t in set(tags) - depts])
        if "dept" in body:
            d = body["dept"]
            depts = {r[0] for r in rows(con, "SELECT id FROM org_tags WHERE org_id = ? AND department = 1", oid)}
            if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d not in depts):
                raise ApiError("bad_input")
            if RANK[role_in(con, v, oid) or "member"] >= RANK["vice"]:
                if not can(con, v, oid, "people") or not one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid):
                    raise ApiError("forbidden")
            else:  # a Head: their own department's people only, and not themselves
                if uid == v.id:
                    raise ApiError("forbidden")
                _below(con, v, oid, uid, "people")
                own = dept_of(con, oid, v.id)
                if own is None or dept_of(con, oid, uid) not in (None, own) or d not in (None, own):
                    raise ApiError("forbidden")
            gone = depts if RANK[role_in(con, v, oid) or "member"] >= RANK["vice"] else {own}  # a Head touches their own only
            con.execute(f"DELETE FROM member_tags WHERE user_id = ? AND tag_id IN ({','.join('?' * len(gone)) or 'NULL'})", (uid, *gone))
            if d is not None:
                con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (d, uid))
        if "probation" in body:
            on = body["probation"]
            if not isinstance(on, bool):
                raise ApiError("bad_input")
            _below(con, v, oid, uid, "people" if on else "team")
            was = one(con, "SELECT probation FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["probation"]
            con.execute("UPDATE org_members SET probation = ? WHERE org_id = ? AND user_id = ?", (int(on), oid, uid))
            if was and not on:
                notify(con, uid, "probation_passed", f"pp:{oid}:{core.now() // 86400}")
    return team(con, v, oid)


def _ask_removal(con, oid: int, uid: int, by: int | None, ban: bool, note: str) -> None:
    """A removal request (one open per person; a second ask joins it, a ban asked for sticks), and a bot message to
    every President and Vice who outranks the person."""
    con.execute("""INSERT INTO removal_requests (org_id, user_id, by_id, ban, note, created_at) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (org_id, user_id) WHERE status = 'pending' DO UPDATE SET ban = max(ban, excluded.ban)""", (oid, uid, by, int(ban), note, core.now()))
    rid = one(con, "SELECT id FROM removal_requests WHERE org_id = ? AND user_id = ? AND status = 'pending'", oid, uid)["id"]
    theirs = one(con, "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", oid, uid)["role"]
    for m in rows(con, "SELECT user_id, role FROM org_members WHERE org_id = ? AND role IN ('vice', 'president') AND user_id != ?", oid, by or 0):
        if RANK[m["role"]] > RANK[theirs]:
            notify(con, m["user_id"], "removal_ask", f"rm:{rid}")


def remove(con, v: Viewer, oid: int, uid: int, body: dict) -> dict:
    """Removing someone below me (§2b): a Vice+ does it at once, banned too if asked; a Head's tap is a request the
    President or Vice decide. {done}: whether they are out already."""
    ban, note = body.get("ban", False), " ".join(str(body.get("note") or "").split())
    if not isinstance(ban, bool) or len(note) > 140:
        raise ApiError("bad_input")
    with tx(con):
        _below(con, v, oid, uid, "people")
        if can(con, v, oid, "team"):
            _remove(con, v.id, oid, uid, ban, "team")
            return {"done": True}
        _ask_removal(con, oid, uid, v.id, ban, note)
    return {"done": False}


def decide_removal(con, v: Viewer, rid: int, approve: object) -> None:
    """The President or a Vice who outranks the person answers a removal request."""
    if not isinstance(approve, bool):
        raise ApiError("bad_input")
    q = one(con, "SELECT * FROM removal_requests WHERE id = ?", rid)
    if not q:
        raise ApiError("not_found")
    with tx(con):
        if one(con, "SELECT status FROM removal_requests WHERE id = ?", rid)["status"] != "pending":
            raise ApiError("conflict")  # another Vice answered first
        _below(con, v, q["org_id"], q["user_id"], "team")
        if approve:
            _remove(con, v.id, q["org_id"], q["user_id"], bool(q["ban"]), "request")
        else:
            con.execute("UPDATE removal_requests SET status = 'declined', decided_by = ?, decided_at = ? WHERE id = ?", (v.id, core.now(), rid))


def unban(con, v: Viewer, oid: int, uid: int) -> None:
    _may(con, v, oid, "team")
    if not con.execute("DELETE FROM org_bans WHERE org_id = ? AND user_id = ?", (oid, uid)).rowcount:
        raise ApiError("not_found")


def banned(con, oid: int, uid: int) -> bool:
    return one(con, "SELECT 1 FROM org_bans WHERE org_id = ? AND user_id = ?", oid, uid) is not None


# ---------------------------------------------------------------- invite links (§4.5: Vice+, one person, 48 h → instant Member)

INVITE_TTL = 2 * 86400


def invite(con, v: Viewer, oid: int, dept: object = None) -> dict:
    """A fresh member link for one person (sent in a DM, so it needn't live long; one that went
    somewhere it shouldn't lets in one person at most). 96 random bits. `dept`: the department the newcomer lands in;
    below Vice, only one's own."""
    _may(con, v, oid, "team")
    if dept is not None:
        if not isinstance(dept, int) or isinstance(dept, bool) or not one(con, "SELECT 1 FROM org_tags WHERE id = ? AND org_id = ? AND department = 1", dept, oid):
            raise ApiError("bad_input")
        if RANK[role_in(con, v, oid) or "member"] < RANK["vice"] and dept != dept_of(con, oid, v.id):
            raise ApiError("forbidden", "dept")
    token = secrets.token_hex(12)
    con.execute("INSERT INTO org_invites (token, org_id, role, created_by, created_at, expires_at, dept_id) VALUES (?, ?, 'member', ?, ?, ?, ?)",
                (token, oid, v.id, core.now(), core.now() + INVITE_TTL, dept))
    return {"token": token}


PRESIDENT_LINK_TTL = 7 * 86400


def president_link(con, v: Viewer, oid: int) -> dict:
    """The admin makes a new club's President with a link (§2): one person, once, within 7 days — no need for them to
    have opened the app before. A new link ends the unused old one."""
    _admin(v)
    o = one(con, "SELECT * FROM orgs WHERE id = ? AND kind IN ('club', 'school', 'council') AND status = 'active'", oid)
    if not o:
        raise ApiError("not_found")
    token = secrets.token_hex(12)
    with tx(con):
        con.execute("UPDATE org_invites SET revoked_at = ? WHERE org_id = ? AND role = 'president' AND used_by IS NULL AND revoked_at IS NULL", (core.now(), oid))
        con.execute("INSERT INTO org_invites (token, org_id, role, created_by, created_at, expires_at) VALUES (?, ?, 'president', ?, ?, ?)",
                    (token, oid, v.id, core.now(), core.now() + PRESIDENT_LINK_TTL))
        log_action(con, v.id, "president_link", f"org:{oid}")
    return {"token": token, "expiresAt": core.now() + PRESIDENT_LINK_TTL}


def accept_invite(con, v: Viewer, token: str) -> dict:
    """A student opens a club's one-time link. A member link: a Member at once, no application (a pending one is settled
    by it). A President link (the admin's): they lead the club, the old President steps down to Vice."""
    need_student(v)
    r = one(con, "SELECT * FROM org_invites WHERE token = ? AND revoked_at IS NULL", token)
    o = _org(con, r["org_id"]) if r else None
    if not o or o["status"] != "active" or r["used_by"] or (r["expires_at"] or 0) < core.now():
        raise ApiError("not_found")   # every link is one person's, once; the old reusable ones (no expiry) are dead
    member = r["role"] == "member"
    if member and banned(con, o["id"], v.id):
        raise ApiError("forbidden", "banned")
    if member and one(con, "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", o["id"], v.id):
        return org_shape(con, v, o)   # already in: the link stays for the one it was meant for
    with tx(con):
        if not con.execute("UPDATE org_invites SET used_by = ? WHERE token = ? AND used_by IS NULL", (v.id, token)).rowcount:
            raise ApiError("not_found")
        if member:
            con.execute("INSERT OR IGNORE INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)", (o["id"], v.id, core.now()))
            if r["dept_id"] and dept_of(con, o["id"], v.id) is None:
                con.execute("INSERT OR IGNORE INTO member_tags (tag_id, user_id) SELECT id, ? FROM org_tags WHERE id = ? AND department = 1", (v.id, r["dept_id"]))
        else:
            oversight.set_role(con, r["created_by"], v.id, o["id"], "president", "link")
        con.execute("UPDATE join_requests SET status = 'accepted', decided_at = ? WHERE org_id = ? AND user_id = ? AND status = 'pending'", (core.now(), o["id"], v.id))
    return org_shape(con, v, o)


# ---- indoor routes (PLAN item 22): the graph the owner edits on the map; the app finds the ways over it ----
MAP_DRAFT = Path(__file__).parent.with_name("map_graph.json")  # Claude's graph from UNI-Q's plans, the only one (owner, Oct 16: the
# editor is off, his saves were by accident; the old map_graph table's row is ignored)


def map_graph(con) -> dict:
    return {**json.loads(MAP_DRAFT.read_text()), "ver": 0}


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import core, oversight  # noqa: E402
from .clubs import _official, org_shape  # noqa: E402
from .forum import asks  # noqa: E402
from .oversight import QUIET_FOR, _admin  # noqa: E402
from .seats import notify  # noqa: E402
