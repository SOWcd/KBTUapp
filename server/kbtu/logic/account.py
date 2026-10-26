"""Me: the profile, settings, the Microsoft sign-in, my photo, my schedule, deleting my data."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path

from ..db import tx

from .core import ApiError, NO_END, PERSON, RANK, Viewer, log, log_action, need_student, one, rows


SETTINGS = {"lang": "lang", "theme": "theme", "nRemind": "n_remind", "nNewEvents": "n_new_events",
            "nFriends": "n_friends", "showGoing": "show_going", "hideFirstYear": "hide_first_year"}


def ms_link(con, uid: int, who: dict) -> None:
    """A student signed in with the KBTU Microsoft account (msauth.py): confirmed, with that account's email, and its
    names over typed ones (review, Oct 19: otherwise "confirmed" proved nothing about who it is); the old portal's
    names stay (they came from KBTU already)"""
    con.execute("""UPDATE students SET ms_oid = ?, email = ?, manual = 0, verified_at = ?, ms_profile = ?,
        first_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), first_name) ELSE first_name END,
        last_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), last_name) ELSE last_name END WHERE user_id = ?""",
                (who["oid"], who["email"], core.now(), json.dumps(who.get("profile") or {}, ensure_ascii=False), who["first"], who["last"], uid))
    con.execute("DELETE FROM meta WHERE key = ?", (f"ms:{uid}",))
    link_door_guests(con, uid)


def ms_remember(con, uid: int, who: dict) -> None:
    """Signed in with Microsoft before typing the student ID and year: kept a week (MS_KEEP) for kbtu_manual"""
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (f"ms:{uid}", json.dumps({**who, "at": core.now()})))


MS_KEEP = 7 * 86400  # a Microsoft sign-in waits a week for the student ID and year (review 3: a day was too short)


def ms_pending(con, uid: int) -> dict | None:
    r = one(con, "SELECT value FROM meta WHERE key = ?", f"ms:{uid}")
    who = json.loads(r[0]) if r else None
    return who if who and who["at"] > core.now() - MS_KEEP else None


def ms_apply(con, uid: int, who: dict) -> bool:
    """The Microsoft account on this Telegram: a student already confirmed (True), or remembered for the form."""
    other = one(con, "SELECT user_id FROM students WHERE ms_oid = ?", who["oid"])
    if other and other[0] != uid:
        raise ApiError("conflict", "linked")  # this Microsoft account is someone else's student already
    mine = one(con, "SELECT ms_oid FROM students WHERE user_id = ?", uid)
    if mine and mine[0] and mine[0] != who["oid"]:
        raise ApiError("conflict", "other_ms")  # already confirmed with another KBTU account: no silent swap
    if mine:
        ms_link(con, uid, who)
        return True
    ms_remember(con, uid, who)
    return False


def ms_sweep(con) -> None:
    """Each bot round: Microsoft sign-ins never finished (they hold the Graph profile) and the used-link marks"""
    con.execute("DELETE FROM meta WHERE key LIKE 'mscode:%'")  # the return-link codes, dropped Oct 24
    con.execute("DELETE FROM meta WHERE key LIKE 'ms:%' AND (NOT json_valid(value) OR json_extract(value, '$.at') < ?)", (core.now() - MS_KEEP,))
    con.execute("DELETE FROM meta WHERE key LIKE 'ms_used:%' AND CAST(value AS INTEGER) < ?", (core.now() - 86400,))


def id_clash(con, sid: str, new: int, old: int) -> None:
    """Someone signed in with Microsoft typed a student ID another account holds: every admin hears, with both
    people's contacts, and asks them (owner, Oct 20). Once per pair, 3 a day per person (review: no admin spam). The
    holder's name and email are kept in the message: their row may be gone by the time it's sent."""
    day = core.now() // 86400
    if one(con, "SELECT COUNT(DISTINCT ref) FROM bot_outbox WHERE kind = 'id_clash' AND ref LIKE ? AND send_after >= ?",
           f"ic:%:{new}:%", day * 86400)[0] >= 3:
        return
    h = one(con, "SELECT first_name, last_name, email FROM students WHERE user_id = ?", old)
    held = json.dumps({"name": " ".join(x for x in (h["first_name"], h["last_name"]) if x), "email": h["email"]} if h else {})
    for (uid,) in rows(con, "SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL"):
        notify(con, uid, "id_clash", f"ic:{sid}:{new}:{old}", held)


def me(con, v: Viewer) -> dict:
    from .. import roster
    if v.student:
        roster.match(con, v.id)  # a club's roster row that's mine (PLAN 95): joined now, a toast below
    u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    relink = bool(s and s["manual"])  # typed in before Microsoft only: signed out until Microsoft confirms (owner, Oct 20)
    s = None if relink else s
    members = rows(con, """SELECT m.role, t.name AS title, t.rights, o.* FROM org_members m JOIN orgs o ON o.id = m.org_id
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND o.status = 'active'""", v.id) if s else []
    tickets = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status = 'going' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""", v.id, NO_END, core.now())[0]
    name_row = one(con, PERSON + " WHERE u.id = ?", v.id)
    own = one(con, "SELECT path FROM files WHERE id = ?", u["avatar_file_id"]) if u["avatar_file_id"] else None
    # the card number at the KBTU sign-in, in the order people came (owner, Oct 22 morning: "I want to see who came
    # 84th"; the first-real-step rule of the night before is off); staff (kbtu.admin staff) take none: it's the
    # students' order. A deleted account's number stays empty, never given again.
    # A number given by migration 59 (the night's sign-ins) brings its "First 500" here, on the next open.
    if s and s["consent_version"] != "staff" and (u["card_no"] is None and not u["is_founder"] or (
            (u["is_founder"] or (u["card_no"] or awards.FIRST_N + 1) <= awards.FIRST_N)
            and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'first50'", v.id))):
        first_fifty(con, v.id)  # the number and, with it, "First 500"
        u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    return {
        "id": u["id"], "tg": {"id": u["tg_id"], "username": u["tg_username"], "firstName": u["tg_first_name"], "lastName": u["tg_last_name"]},
        "avatar": avatar_of(name_row), "name": shown_name(name_row), "nick": u["nick"],
        "photo": {"telegram": bool(u["avatar_tg"]), "tg": u["tg_photo_url"], "own": f"media/{own['path']}.t.webp" if own else None},
        "student": {"studentId": s["student_id"], "firstName": s["first_name"], "lastName": s["last_name"], "email": s["email"],
                    "phone": s["phone"], "course": s["course"], "school": s["school"], "program": s["program"], "syncedAt": s["synced_at"],
                    "ms": s["ms_oid"] is not None, "consent": s["consent_version"]} if s else None,
        # signed in with Microsoft, the student ID and year still to type: the form shows the account's names
        "msPending": {k: p[k] for k in ("first", "last", "email")} if not s and not relink and (p := ms_pending(con, v.id)) else None,
        "relink": relink,
        "role": u["role"], "canDm": bool(u["can_dm"]), "founder": bool(u["is_founder"]), "mark": u["mark"], "qr": f"{v.id}_{_qr_code(con, v.id)}" if s else None,
        "no": (0 if u["is_founder"] else u["card_no"]) if s else None,
        "oversee": any(m["can_oversee"] and m["role"] != "member" for m in members),
        "bio": u["bio"], "showcase": [x for x in u["showcase"].split(",") if x],
        "settings": {k: (u[c] if k in ("lang", "theme") else bool(u[c])) for k, c in SETTINGS.items()},
        # oversee: this org is DMP and I lead in it: Studio shows the registry with it picked (owner, Oct 26)
        "memberships": [{"org": org_ref(con, m), "role": m["role"], "title": m["title"], "rights": _ordered(_rights_from(m["role"], m["rights"])),
                         "oversee": bool(m["can_oversee"] and m["role"] != "member")} for m in members],
        "counters": {"tickets": tickets, "unreadBroadcasts": unread_broadcasts(con, v),
                     "friendRequests": one(con, "SELECT COUNT(*) FROM friend_requests WHERE to_id = ? AND status = 'pending'", v.id)[0] if v.student else 0,
                     "reports": sum(_about(con, t, i) != v.id for t, i in rows(con, "SELECT DISTINCT target, target_id FROM reports WHERE status = 'open'"))
                                if v.role in ("admin", "moderator") else 0,  # as the queue: not those about me
                     "clubApps": one(con, "SELECT COUNT(*) FROM club_applications WHERE status = 'pending'")[0] if v.role == "admin" else 0},
        "unlocked": unlocked(con, v),
        "skin": _skin(con, v.id) if s else None,
        "deleteAt": u["delete_at"] if s or relink else None,  # a relink account's week shows too (review)
        "city": {"name": u["city"], "hidden": bool(u["city_hidden"])} if u["city"] else None,
        "roster": _roster_mine(con, v.id),
    }


def roster_requests(con, v: Viewer) -> list[dict]:
    """Claims I confirm (roster.requests) with the club and the student as the app shows them."""
    from .. import roster
    out = []
    for r in roster.requests(con, v):
        o, p = one(con, "SELECT * FROM orgs WHERE id = ?", r["org"]), one(con, PERSON + " WHERE u.id = ?", r["user"])
        if o and p:
            out.append({**r, "org": org_ref(con, o), "person": person_ref(p)})
    return out


def _roster_mine(con, uid: int) -> dict | None:
    """roster.mine with the clubs as the app shows them."""
    from .. import roster
    got = roster.mine(con, uid)
    if not got:
        return None
    orgs = {o["id"]: org_ref(con, o) for o in rows(con, "SELECT * FROM orgs WHERE id IN (" + ",".join(
        str(int(x["org"])) for k in got for x in got[k]) + ")")}
    return {k: [{**x, "org": orgs[x["org"]]} for x in got[k] if x["org"] in orgs] for k in got}


# the clubs with a badge of their own (web: awards.ts `skinned`)
SKINNED = ("o.official = 1 AND o.status = 'active' AND (lower(o.name) LIKE '%studex%' OR lower(o.name) LIKE '%cheer%'"
           " OR lower(o.name) LIKE '%knight%')")


def _skin(con, uid: int) -> int | str | None:
    """The badge I show (owner, Oct 13: badges as skins): a club's id, "sower" (the creator's own), None for KBTU's.
    My pick holds; a club picked holds while I'm in it. Never picked (or that club left): the newest club I joined
    that has a badge, the creator's own for the creator (owner, Oct 13: a new club's badge comes by itself); of
    several, the one where my role is highest, as the picker lists them (LookSheet)."""
    u = one(con, "SELECT skin_pick, skin_org, is_founder FROM users WHERE id = ?", uid)
    if u["skin_pick"] == "kbtu":
        return None
    if u["is_founder"] and u["skin_pick"] in ("sower", None):
        return "sower"
    if u["skin_pick"] == "org" and _skin_ok(con, uid, u["skin_org"]):
        return u["skin_org"]
    r = one(con, f"""SELECT o.id FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ? AND {SKINNED}
        ORDER BY CASE m.role WHEN 'president' THEN 4 WHEN 'vice' THEN 3 WHEN 'head' THEN 2 ELSE 1 END DESC, m.joined_at DESC LIMIT 1""", uid)
    return r[0] if r else None


def _skin_ok(con, uid: int, oid: int):
    """Any club's lanyard can be tried on, member or not (owner, Oct 20: "let everyone try on another club's"); the
    creator's own stays his. ponytail: uid unused while it's open to all; a membership check comes back if he closes it."""
    return one(con, f"SELECT 1 FROM orgs o WHERE o.id = ? AND {SKINNED}", oid)


def _qr_code(con, uid: int) -> str:
    """The secret half of my badge QR (§4.4): made on first use, random like a ticket code."""
    code = one(con, "SELECT qr_code FROM users WHERE id = ?", uid)["qr_code"]
    if not code:
        con.execute("UPDATE users SET qr_code = ? WHERE id = ? AND qr_code IS NULL",
                    ("".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(10)), uid))
        code = one(con, "SELECT qr_code FROM users WHERE id = ?", uid)["qr_code"]
    return code


def update_me(con, v: Viewer, patch: dict) -> dict:
    sets: dict[str, object] = {}
    for k, col in SETTINGS.items():
        if k not in patch:
            continue
        val = patch[k]
        if k == "lang" and val not in ("ru", "kk", "en") or k == "theme" and val not in ("light", "dark", None):
            raise ApiError("bad_input")
        sets[col] = val if k in ("lang", "theme") else int(bool(val))
    if "bio" in patch or "showcase" in patch or "nick" in patch:
        need_student(v)
    if "nick" in patch:
        sets["nick"] = clean_nick(patch["nick"])
    if "skin" in patch:  # my pick: a club with a lanyard (`_skin_ok`), "sower" for the creator, null = the KBTU one (`_skin`)
        need_student(v)
        val = patch["skin"]
        if val is None:
            sets.update(skin_pick="kbtu", skin_org=None)
        elif val == "sower" and one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)[0]:
            sets.update(skin_pick="sower", skin_org=None)
        elif type(val) is int and _skin_ok(con, v.id, val):
            sets.update(skin_pick="org", skin_org=val)
        else:
            raise ApiError("bad_input")
    if "avatarTg" in patch:  # off only with a photo of my own to show (the upload turns it off by itself)
        if not patch["avatarTg"] and not one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]:
            raise ApiError("bad_input")
        sets["avatar_tg"] = int(bool(patch["avatarTg"]))
    if "bio" in patch:
        sets["bio"] = str(patch["bio"])[:150]
    if "showcase" in patch:  # up to 6 keys: achievement codes and badges as b<event id>, in the order picked (§4.11)
        codes = {a[0] for a in ACHIEVEMENTS}
        keys = [k for k in (patch["showcase"] if isinstance(patch["showcase"], list) else [])
                if isinstance(k, str) and (k in codes or re.fullmatch(r"b\d{1,9}", k))]
        sets["showcase"] = ",".join(list(dict.fromkeys(keys))[:6])
    if "phone" in patch:  # my kept phone (Settings → My data): changed, or null deletes it
        need_student(v)
        phone = None if patch["phone"] is None else kz_phone(patch["phone"])
        if patch["phone"] is not None and not phone:
            raise ApiError("bad_input")
        con.execute("UPDATE students SET phone = ? WHERE user_id = ?", (phone, v.id))
    if "city" in patch and patch["city"] is not None:
        raise ApiError("bad_input")  # it came from the club's roster (PLAN 95): it can only be deleted
    if "city" in patch:  # Settings → My data
        sets["city"] = None
    if "cityHidden" in patch:  # off my profile, kept for me
        if not isinstance(patch["cityHidden"], bool):
            raise ApiError("bad_input")
        sets["city_hidden"] = int(patch["cityHidden"])
    if sets:
        con.execute(f"UPDATE users SET {', '.join(c + ' = ?' for c in sets)} WHERE id = ?", (*sets.values(), v.id))
    if "nRemind" in patch:  # the switch acts at once on reminders already queued: off drops them, on arms the upcoming ones
        con.execute("DELETE FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' AND sent_at IS NULL", (v.id,))
        for e in rows(con, "SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id WHERE r.user_id = ? AND r.status = 'going'", v.id):
            _remind(con, v.id, e)
    return me(con, v)


def _drop_photo(con, fid: int | None) -> list[str]:
    """A photo of mine nobody shows any more: its row goes, and its files on disk (returned) unless another row has
    the same picture (files are named by their content)."""
    f = one(con, "SELECT id, path FROM files WHERE id = ?", fid) if fid else None
    if not f:
        return []
    con.execute("DELETE FROM files WHERE id = ?", (f["id"],))
    return [] if one(con, "SELECT 1 FROM files WHERE path = ?", f["path"]) else [f["path"]]


def _drop_unused(con, fid: int | None) -> list[str]:
    """_drop_photo for a file nothing shows any more (no avatar, logo, cover, receipt, album, post or slide names it);
    one still shown is left alone."""
    if fid and con.execute("""SELECT 1 FROM users WHERE avatar_file_id = :f UNION ALL SELECT 1 FROM orgs WHERE logo_file_id = :f
            UNION ALL SELECT 1 FROM events WHERE cover_file_id = :f UNION ALL SELECT 1 FROM receipts WHERE file_id = :f
            UNION ALL SELECT 1 FROM event_photos WHERE file_id = :f UNION ALL SELECT 1 FROM posts WHERE photo_file_id = :f
            UNION ALL SELECT 1 FROM event_slides WHERE file_id = :f UNION ALL SELECT 1 FROM takedowns WHERE file_id = :f""", {"f": fid}).fetchone():
        return []
    return _drop_photo(con, fid)


def set_photo(con, v: Viewer, saved: dict) -> list[str]:
    """My own photo (a processed upload, media.save) instead of Telegram's: the "Photo from Telegram" switch goes off
    (owner, Oct 5). The one it replaces is deleted; returns its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'avatar' AND owner_id = ?", saved["sha256"], v.id)
    fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'avatar', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                saved["path"], v.id, core.now(), saved["color"])).lastrowid
    con.execute("UPDATE users SET avatar_file_id = ?, avatar_tg = 0 WHERE id = ?", (fid, v.id))
    return _drop_photo(con, old) if old and old != fid else []


def drop_my_photo(con, v: Viewer) -> list[str]:
    """My own photo deleted (owner's list, Oct 10: the upload shouldn't stay on the server): Telegram's is back; returns
    its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    con.execute("UPDATE users SET avatar_file_id = NULL, avatar_tg = 1 WHERE id = ?", (v.id,))
    return _drop_photo(con, old) if old else []


DELETE_WAIT = 7 * 86400


def _paid_ahead(con, uid: int) -> bool:
    """A ticket paid for (a receipt sent or accepted) to an event still ahead: the deletion waits until it passes, so
    the money's only record isn't erased before the door (owner, Oct 22)."""
    return one(con, """SELECT 1 FROM registrations r JOIN events e ON e.id = r.event_id JOIN receipts c ON c.registration_id = r.id
        WHERE r.user_id = ? AND r.status IN ('going', 'hold') AND c.status != 'rejected' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""",
               uid, NO_END, core.now()) is not None


def ask_delete(con, v: Viewer, photos: bool = False) -> dict:
    """"Delete my account" (§4.8) waits a week, then `delete_due` runs it (owner, Oct 13: a change of heart, or someone
    holding my phone, shouldn't cost the awards; the KBTU password asked before shut out whoever no longer has it).
    The bot says so at once, with the way back; nothing is hidden meanwhile. `photos`: the album photos I added go
    too (by default they stay, without my name). A President's club passes on at the deletion (delete_due)."""
    need_student(v)
    at = core.now() + DELETE_WAIT
    if con.execute("UPDATE users SET delete_at = ? WHERE id = ? AND delete_at IS NULL", (at, v.id)).rowcount:
        notify(con, v.id, "delete_soon", f"del:{at}")
    con.execute("DELETE FROM meta WHERE key = ?", (f"delphotos:{v.id}",))
    if photos:
        con.execute("INSERT INTO meta (key, value) VALUES (?, '1')", (f"delphotos:{v.id}",))
    return me(con, v)


def delete_info(con, v: Viewer) -> dict:
    """What the delete sheet tells before: the album photos I added (they stay without my name unless I say so), and
    whether a paid ticket ahead makes the deletion wait."""
    need_student(v)
    return {"photos": one(con, "SELECT COUNT(*) FROM event_photos WHERE added_by = ?", v.id)[0], "paid": _paid_ahead(con, v.id)}


CONSENT = "2026-10-v3"  # web/src/lib/legal.ts says the same
CONSENT_FORUM = "2026-10-v4"  # with FORUM=1: the policy's forum part is in force, everyone agrees again (app.py)


def consent(con, v: Viewer, version: object, now: str = CONSENT) -> dict:
    """The privacy policy changed (H2, Oct 22: what a deletion keeps): a student agrees again once; staff and students
    added by hand keep their marks."""
    need_student(v)
    if version != now:
        raise ApiError("bad_input")
    con.execute("UPDATE students SET consent_version = ?, consent_at = ? WHERE user_id = ? AND consent_version NOT IN ('staff', 'admin')",
                (version, core.now(), v.id))
    return me(con, v)


def dm_on(con, v: Viewer, eid: object) -> dict:
    """Telegram's "allow messages" said yes inside the app: the bot may write from now on, not from the next launch
    (the launch data said no). The event just signed up for gets its confirmation with the ticket (owner, Oct 24). A
    false yes costs nothing: the bot's first 403 turns it off again."""
    con.execute("UPDATE users SET can_dm = 1 WHERE id = ?", (v.id,))
    if type(eid) is int and one(con, "SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ? AND status = 'going'", eid, v.id):
        notify(con, v.id, "going_ok", f"event:{eid}")
    return me(con, v)


def keep_me(con, v: Viewer) -> dict:
    con.execute("UPDATE users SET delete_at = NULL WHERE id = ?", (v.id,))
    con.execute("DELETE FROM meta WHERE key = ?", (f"delphotos:{v.id}",))
    return me(con, v)


def _hand_over(con, uid: int) -> None:
    """A President leaving with the account: each club passes to its highest-ranked member (the earliest of them), a
    club with nobody else to the admin (owner, Oct 22: deleting it would erase other people's events and photos)."""
    for (oid,) in rows(con, "SELECT org_id FROM org_members WHERE user_id = ? AND role = 'president'", uid):
        con.execute("UPDATE org_members SET role = 'member' WHERE org_id = ? AND user_id = ?", (oid, uid))
        heir = one(con, f"""SELECT user_id FROM org_members WHERE org_id = ? AND user_id != ? ORDER BY CASE role
            {" ".join(f"WHEN '{r}' THEN {n}" for r, n in RANK.items())} END DESC, joined_at, user_id LIMIT 1""", oid, uid)
        admin = one(con, """SELECT id FROM users WHERE role = 'admin' AND banned_at IS NULL AND id != ? AND tg_id > 0
            AND id IN (SELECT user_id FROM students) ORDER BY id LIMIT 1""", uid)
        new = heir["user_id"] if heir else admin["id"] if admin else None
        if new is None:
            continue  # no admin to take it: it waits for one (the admin panel's "Assign")
        con.execute("""INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', ?)
            ON CONFLICT (org_id, user_id) DO UPDATE SET role = 'president', role_id = NULL, probation = 0""", (oid, new, core.now()))
        log_action(con, None, "president_handover", f"org:{oid}")
        notify(con, new, "club_handover", f"ho:{oid}")


def delete_due(con) -> tuple[list[str], list[str]]:
    """The accounts whose week ran out, deleted; their files to remove from disk, as delete_me's. One that fails is
    logged and tried again next round; the rest go on."""
    gone: tuple[list[str], list[str]] = ([], [])
    for u in rows(con, "SELECT id, role FROM users WHERE delete_at <= ?", core.now()):
        if _paid_ahead(con, u["id"]):
            continue  # waits until that event has passed
        photos_too = one(con, "SELECT 1 FROM meta WHERE key = ?", f"delphotos:{u['id']}") is not None  # delete_me takes the mark
        try:
            receipts, photos = delete_me(con, Viewer(u["id"], u["role"], True))
        except Exception:
            log.exception("deleting account %s failed", u["id"])
            continue
        # after it, never before: a failed one that the person then keeps mustn't come back after a restore
        _deletion_log(con, u["id"], photos_too)
        gone[0].extend(receipts)
        gone[1].extend(photos)
    return gone


def _deletion_log(con, uid: int, photos: bool) -> None:
    """A line per deletion in deletions.log beside the database, outside it: a restored copy brings the deleted
    back, and `kbtu.admin redelete` runs them again (DEPLOY.md, restore). The Telegram ID only as a salted hash; the
    salt is a file there too, so a copy from before it still matches."""
    try:
        home = Path(one(con, "SELECT file FROM pragma_database_list WHERE name = 'main'")[0]).parent
        tg = one(con, "SELECT tg_id FROM users WHERE id = ?", uid)[0]
        with (home / "deletions.log").open("a") as f:  # the day, not the second: the line can't be matched to a placeholder's order
            f.write(f"{core.now() // 86400 * 86400} {deletion_hash(home, tg)}{' photos' if photos else ''}\n")
    except OSError:
        log.exception("deletions.log: account %s not written", uid)


DELETION_LOG_DAYS = 40  # longer than any copy lives (R2 ~30 days): an older line can't be needed


def _prune_deletion_log(con) -> None:
    path = Path(one(con, "SELECT file FROM pragma_database_list WHERE name = 'main'")[0]).with_name("deletions.log")
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    keep = [ln for ln in lines if ln.split()[:1] and ln.split()[0].isdigit() and int(ln.split()[0]) > core.now() - DELETION_LOG_DAYS * 86400]
    if len(keep) != len(lines):
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(ln + "\n" for ln in keep))
        tmp.replace(path)


def deletion_hash(home: Path, tg_id: int) -> str:
    salt = home / "deletions.salt"
    if not salt.exists():
        salt.write_text(secrets.token_hex(16))
    return hashlib.sha256(f"{salt.read_text().strip()}:{tg_id}".encode()).hexdigest()[:32]


# Every column that points at a person (the foreign keys to users, read from the schema at each deletion) is in one
# of these, or deleting an account refuses to run: a new table can't keep someone by being forgotten
# (tests/test_core.py checks the lists cover the schema). The nullable rest just lose the link.
_DEL_KEEP = {("org_bans", "user_id")}  # a club's ban stays on the Telegram account
_DEL_GONE = {
    ("students", "user_id"), ("schedule_classes", "user_id"), ("org_members", "user_id"), ("join_requests", "user_id"),
    ("club_applications", "user_id"), ("subscriptions", "user_id"), ("registrations", "user_id"), ("saved_events", "user_id"),
    ("post_reactions", "user_id"), ("post_reads", "user_id"), ("friend_links", "user_id"), ("achievement_grants", "user_id"),
    ("achievement_levels", "user_id"), ("chat_opens", "user_id"), ("bot_outbox", "user_id"), ("event_ratings", "user_id"), ("roster_toasts", "user_id"),
    ("member_tags", "user_id"), ("removal_requests", "user_id"), ("comment_reads", "user_id"), ("visits", "user_id"),
    ("volunteers", "user_id"), ("round_apps", "user_id"), ("round_votes", "user_id"), ("comments", "user_id"),
    ("friendships", "a"), ("friendships", "b"), ("friend_requests", "from_id"), ("friend_requests", "to_id"),
    ("friend_invites", "from_id"), ("friend_invites", "to_id"), ("grant_links", "created_by"), ("door_guests", "user_id"),
    ("takedowns", "user_id"), ("user_skills", "user_id"), ("asks", "user_id"), ("contacts", "from_id"), ("contacts", "to_id"),
    ("blocks", "user_id"), ("blocks", "blocked_id"), ("ask_pings", "user_id"),
    ("org_history", "user_id"),  # last: org_members' trigger writes it
}


def _user_fks(con) -> list[tuple[str, str, bool]]:
    """(table, column, NOT NULL) of every foreign key to users."""
    out = []
    for (t,) in rows(con, "SELECT name FROM sqlite_master WHERE type = 'table'"):
        notnull = {r["name"]: bool(r["notnull"]) for r in rows(con, f"PRAGMA table_info({t})")}
        out += [(t, fk["from"], notnull[fk["from"]]) for fk in rows(con, f"PRAGMA foreign_key_list({t})") if fk["table"] == "users"]
    return out


def _placeholder(con) -> int:
    """The stand-in a deleted account's past leaves with (H2): no name, no Telegram, never seen, a random negative
    tg_id (nothing derived from the account, a new one for each deletion). What it holds keeps every count right (who
    came, ratings, casting stages, a friend's "brought N"), and nothing leads back."""
    while True:
        tg = -1 - secrets.randbelow(2**62)
        if not one(con, "SELECT 1 FROM users WHERE tg_id = ?", tg):
            return con.execute("""INSERT INTO users (tg_id, created_at, seen_at, can_dm, n_remind, n_new_events, n_friends, show_going)
                VALUES (?, 0, 0, 0, 0, 0, 0, 0)""", (tg,)).lastrowid


def delete_me(con, v: Viewer) -> tuple[list[str], list[str]]:
    """Delete my data (§4.8, consent withdrawn), run by delete_due after the week. The Telegram account stays a guest:
    its settings and a club's ban stay on the Telegram ID. Future tickets are given up first, so
    seats free up and the waitlist moves. My part of what is over moves to a nameless placeholder, its free text
    blanked: who came to an ended event, ratings, volunteering, done casting rounds, comments written as the club.
    Album photos I added stay without my name unless I asked them gone; everything else of mine is deleted.
    Returns the receipt images and photos to remove from disk."""
    me_, ended = {"u": v.id}, "SELECT id FROM events WHERE COALESCE(ends_at, starts_at + :end) <= :now"
    with tx(con):
        _hand_over(con, v.id)
        # money: the receipts go, theirs is personal (the club saw them); the paid seat it was for, if over, moves on
        paid = [r[0] for r in rows(con, """SELECT c.file_id FROM receipts c JOIN registrations r ON r.id = c.registration_id
            WHERE r.user_id = ?""", v.id)]
        con.execute("DELETE FROM receipts WHERE registration_id IN (SELECT id FROM registrations WHERE user_id = ?)", (v.id,))
        receipts = [p for f in paid + [r[0] for r in rows(con, "SELECT id FROM files WHERE owner_id = ? AND kind = 'receipt'", v.id)]
                    for p in _drop_unused(con, f)]
        # future seats first, so the waitlist moves: directly, an event he can no longer see (hidden, members-only) too
        for e in rows(con, """SELECT e.* FROM registrations r JOIN events e ON e.id = r.event_id
                WHERE r.user_id = ? AND r.status IN ('going', 'hold', 'waitlist') AND e.starts_at > ?""", v.id, core.now()):
            con.execute("DELETE FROM registrations WHERE event_id = ? AND user_id = ?", (e["id"], v.id))
            if e["status"] == "published" and not e["hidden_at"]:  # a cancelled or hidden event offers nobody a seat
                promote(con, e)
        pid = _placeholder(con)
        me_.update(p=pid, end=NO_END, now=core.now())
        for (rid,) in con.execute(f"SELECT id FROM registrations WHERE user_id = :u AND status = 'going' AND event_id IN ({ended})", me_).fetchall():
            con.execute("UPDATE registrations SET user_id = ?, note = NULL, ticket_code = ? WHERE id = ?", (pid, _ticket_code(con), rid))
        con.execute("UPDATE event_ratings SET user_id = :p, comment = '' WHERE user_id = :u", me_)
        con.execute(f"UPDATE volunteers SET user_id = :p, note = '' WHERE user_id = :u AND event_id IN ({ended})", me_)
        done = "SELECT id FROM rounds WHERE status = 'done'"
        con.execute(f"UPDATE round_votes SET note = '' WHERE app_id IN (SELECT id FROM round_apps WHERE user_id = :u AND round_id IN ({done}))", me_)
        con.execute(f"UPDATE round_apps SET user_id = :p, answers = '{{}}', source = NULL WHERE user_id = :u AND round_id IN ({done})", me_)
        con.execute(f"""UPDATE round_votes SET user_id = :p, note = '' WHERE user_id = :u
            AND app_id IN (SELECT id FROM round_apps WHERE round_id IN ({done}))""", me_)
        con.execute("UPDATE comments SET user_id = :p WHERE user_id = :u AND as_org = 1", me_)
        # album photos: without my name, or gone if I asked (ask_delete)
        drop = one(con, "DELETE FROM meta WHERE key = ? RETURNING 1", f"delphotos:{v.id}") is not None
        mine = [r[0] for r in rows(con, "SELECT file_id FROM event_photos WHERE added_by = ?", v.id)] if drop else []
        if drop:
            con.execute("DELETE FROM event_photos WHERE added_by = ?", (v.id,))
        avatars = [r[0] for r in rows(con, "SELECT id FROM files WHERE kind = 'avatar' AND owner_id = ?", v.id)]
        con.execute("""UPDATE users SET bio = '', showcase = '', qr_code = NULL, cal_token = NULL, nick = NULL, avatar_tg = 1,
            avatar_file_id = NULL, tg_username = NULL, tg_first_name = '', tg_last_name = '', tg_photo_url = NULL, mark = NULL,
            skin_org = NULL, skin_pick = NULL, card_no = NULL, delete_at = NULL, city = NULL, city_hidden = 0,
            role = CASE WHEN role = 'moderator' THEN 'user' ELSE role END WHERE id = ?""", (v.id,))  # a burnt number isn't given again
        con.execute("UPDATE roster_pending SET claimed_by = NULL WHERE claimed_by = ?", (v.id,))  # PLAN 95: the claim goes with me
        con.execute("UPDATE roster_pending SET rejected_by = NULL WHERE rejected_by = ?", (v.id,))
        # what a moderator took down of mine, kept for an undo: gone now with its files, no 30 days (owner, Oct 25)
        kept = [r[0] for r in rows(con, "DELETE FROM takedowns WHERE user_id = ? RETURNING file_id", v.id)]
        photos = [p for f in mine + avatars + kept for p in _drop_unused(con, f)]
        fks = _user_fks(con)
        for t, c in sorted(_DEL_GONE, key=lambda x: x[0] == "org_history"):
            con.execute(f"DELETE FROM {t} WHERE {c} = ?", (v.id,))
        for t, c, notnull in fks:
            if not notnull and (t, c) not in _DEL_GONE:
                con.execute(f"UPDATE {t} SET {c} = NULL WHERE {c} = ?", (v.id,))
            elif (t, c) not in _DEL_KEEP and one(con, f"SELECT 1 FROM {t} WHERE {c} = ?", v.id):
                raise RuntimeError(f"deleting account {v.id}: {t}.{c} is in no list")  # the transaction rolls back
        con.execute("UPDATE map_graph SET updated_by = NULL WHERE updated_by = ?", (v.id,))  # no foreign key there
        con.execute("DELETE FROM profile_views WHERE viewer_id = ? OR user_id = ?", (v.id, v.id))  # no foreign keys either
        con.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"ms:{v.id}", f"mscode:{v.id}"))  # an unfinished Microsoft sign-in: its profile too
        # the admins' "two people gave this student ID" messages carry my name and email
        con.execute("DELETE FROM bot_outbox WHERE kind = 'id_clash' AND (ref LIKE ? OR ref LIKE ?)", (f"ic:%:{v.id}:%", f"ic:%:%:{v.id}"))
        # his unsent invites in friends' queues; who he was in the role history
        con.execute("DELETE FROM bot_outbox WHERE kind = 'friend_invite' AND ref LIKE ? AND sent_at IS NULL", (f"fi:%:{v.id}",))
        con.execute("UPDATE audit_log SET target = 'user', data = '{}' WHERE target = ?", (f"user:{v.id}",))
        con.execute("UPDATE audit_log SET data = '{}' WHERE action = 'presidency_transfer' AND json_extract(data, '$.to') = ?", (v.id,))
        con.execute("UPDATE reports SET note = NULL WHERE (target = 'user' AND target_id = ?) OR reporter_id IS NULL", (v.id,))
        log_action(con, None, "delete_my_data", "user")
    return receipts, photos


def schedule(con, v: Viewer) -> list[dict]:
    if not v.student:
        return []
    return [{"weekday": c["weekday"], "begins": c["begins"], "ends": c["ends"], "subject": c["subject"], "kind": c["kind"],
             "room": c["room"], "teacher": c["teacher"], "names": json.loads(c["names"]) if c["names"] else None}
            for c in rows(con, "SELECT * FROM schedule_classes WHERE user_id = ? ORDER BY weekday, begins", v.id)]


def save_schedule(con, uid: int, lessons: list) -> None:
    """Replaces the student's weekly classes (inside the caller's transaction)."""
    con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (uid,))
    con.executemany("""INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, code, kind, room, teacher, names)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [(uid, x.weekday, x.begins, x.ends, x.subject, x.code, x.kind, x.room, x.teacher,
                                                     json.dumps(x.names, ensure_ascii=False) if getattr(x, "names", None) else None) for x in lessons])


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import awards, core  # noqa: E402
from .awards import ACHIEVEMENTS, first_fifty, unlocked  # noqa: E402
from .clubs import orgs  # noqa: E402
from .moderation import _about  # noqa: E402
from .newsfeed import unread_broadcasts  # noqa: E402
from .organizing import kz_phone, link_door_guests  # noqa: E402
from .seats import _remind, _ticket_code, notify, promote, tickets  # noqa: E402
from .shapes import _rights_from, avatar_of, clean_nick, org_ref, person_ref, shown_name  # noqa: E402
from .teams import _ordered  # noqa: E402
