"""Me: the profile, settings, the Microsoft sign-in, my photo, my schedule, deleting my data."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
from collections import Counter
from itertools import combinations
from math import comb
from pathlib import Path

from .. import media, portal
from .. import db
from ..db import tx

from . import appchats, notifications, pymk
from .core import (_LAT, LATIN_NAME, NAME, STUDENT_ID, ApiError, NO_END, PERSON, RANK, Viewer, _rights_from, avatar_of, clean_nick, log, log_action,
    name_i18n, need_student, one, org_ref, person_ref, rows, shown_name)


SETTINGS = {"lang": "lang", "theme": "theme", "nDoor": "n_door", "showGoing": "show_going", "hideFirstYear": "hide_first_year",
            "canFriend": "can_friend", **{k: col for k, (col, _) in notifications.CATEGORIES.items()}}


def ms_link(con, uid: int, who: dict) -> None:
    """A student signed in with the KBTU Microsoft account (msauth.py): confirmed, with that account's email, and its
    names over typed ones (otherwise "confirmed" proved nothing about who it is); the old portal's
    names stay (they came from KBTU already). Whoever's invite link brought them now counts it (awards.brought)."""
    from .. import checkin  # imports logic: here, not at the top
    by = one(con, """SELECT u.referred_by FROM users u JOIN students s ON s.user_id = u.id AND s.manual = 1 WHERE u.id = ?""", uid)
    before = _levels(con, by[0]) if by and by[0] else None
    con.execute("""UPDATE students SET ms_oid = ?, email = ?, manual = 0, verified_at = ?, ms_profile = ?,
        first_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), first_name) ELSE first_name END,
        last_name = CASE WHEN manual = 1 THEN COALESCE(NULLIF(?, ''), last_name) ELSE last_name END WHERE user_id = ?""",
                (who["oid"], who["email"], core.now(), json.dumps(who.get("profile") or {}, ensure_ascii=False), who["first"], who["last"], uid))
    con.execute("DELETE FROM meta WHERE key = ?", (f"ms:{uid}",))
    chatsync.check_later(con, uid)  # verified: a club chat they're in already counts (once they agree to the policy in force)
    # the freshmen list's row for this mail (typed at registration, so a classmate's by mistake is possible): mine only
    # when the name matches too. Mine: what my row lacks, the initiation badge, then gone. Not mine: nothing, it stays.
    # Mine, the owner hears (ids only) what to check: another ID than the row's, the row's ID held. Not mine, silence: nothing
    # was used, and an alert he can't act on is noise
    p = one(con, "SELECT * FROM prefill WHERE email = ?", str(who["email"] or "").lower())
    s = one(con, "SELECT first_name, last_name, student_id FROM students WHERE user_id = ?", uid)
    if p:
        mine = prefill_mine(p, s["first_name"], s["last_name"])
        held = one(con, "SELECT user_id FROM students WHERE student_id = ? AND user_id != ?", p["student_id"], uid)
        alert = (None if not mine else ("prefill_id_held", f"ph:{uid}:{held[0]}") if held
                 else ("prefill_other_id", f"pf:{uid}") if s["student_id"] != p["student_id"] else None)
        for (owner,) in rows(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND tg_id > 0") if alert else []:
            notify(con, owner, *alert)
    listed = {}
    if p and mine:
        con.execute("DELETE FROM prefill WHERE email = ?", (p["email"],))
        listed = _from_list(con, uid, p)
    # the rest of that list (prefill_rest_import): a row with my KBTU mail or my student ID, and my name. Never the ID
    # (it is mine already); what my row lacks, the badge; then gone. No alert: nothing of it is used unchecked
    for r in rows(con, "SELECT * FROM prefill_rest WHERE email = ? OR student_id = ?", str(who["email"] or "").lower(), s["student_id"]):
        if prefill_mine(r, s["first_name"], s["last_name"]):
            con.execute("DELETE FROM prefill_rest WHERE id = ?", (r["id"],))
            listed = {**_from_list(con, uid, r), **listed}  # the main list's row first
    _fill_lat(con, uid, who.get("profile") or {}, listed)
    guests.claim(con, uid)
    link_door_guests(con, uid)
    checkin.became_student(con, uid)  # a QR scan waiting for the sign-up counts now (the form's and the relink's path)
    if before is not None:
        _celebrate(con, by[0], before)


SID_LOOKS = str.maketrans({"\u0412": "B", "\u0418": "B", "\u041c": "M"})  # Cyrillic Ve, I, Em typed for Latin B, B, M (I is B's key on the Russian layout)
_ZERO = str.maketrans("O\u041e", "00")  # an O, Latin or Cyrillic, where a digit goes
SID_SHAPE = re.compile("([0-9O\u041e]{2})([A-NP-Z]{1,2})([0-9O\u041e]{4,7})")  # core.STUDENT_ID, an O in a digit's place allowed (so never a letter)


def norm_sid(raw: object) -> str | None:
    """A list's student ID as the app writes it, or None: no guessing beyond the fixed table."""
    m = SID_SHAPE.fullmatch("".join(str(raw or "").split()).upper().translate(SID_LOOKS))
    sid = m and m[1].translate(_ZERO) + m[2] + m[3].translate(_ZERO)
    return sid if sid and STUDENT_ID.fullmatch(sid) and isinstance(c := core.course_of(sid), int) and 1 <= c <= 6 else None  # 4 digits: two letters only


def prefill_mine(p, first: str | None, last: str | None) -> bool:
    """The freshmen list's row is this KBTU account's: its name matches too, as a club roster's row (roster.same_person:
    Cyrillic or Latin, two words shared)."""
    from .. import roster  # imports logic: here, not at the top
    return roster.same_person(f"{p['last_name'] or ''} {p['first_name'] or ''} {p['middle_name'] or ''}", first or "", last or "")


def _from_list(con, uid: int, p) -> dict:
    """A freshmen list's row that is mine (ms_link): what my row lacks, the initiation badge if I came. Returns its names
    that are in Latin, for _fill_lat: a Latin middle name goes to middle_lat, never into the Cyrillic column."""
    lat = {c: p[k] for c, k in (("last_lat", "last_name"), ("first_lat", "first_name"), ("middle_lat", "middle_name"))
           if p[k] and LATIN_NAME.fullmatch(p[k])}
    con.execute("""UPDATE students SET middle_name = COALESCE(NULLIF(middle_name, ''), ?), school = COALESCE(NULLIF(school, ''), ?),
        phone = COALESCE(NULLIF(phone, ''), ?) WHERE user_id = ?""", (None if "middle_lat" in lat else p["middle_name"], p["school"], p["phone"], uid))
    if p["came"] and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'init26f'", uid):
        profiles._grant(con, None, uid, "init26f")
    return lat


LAT_COLS = ("last_lat", "first_lat", "middle_lat")
_LAT_WORD = re.compile(f"[{_LAT}]+(?:[-'][{_LAT}]+)*")


def latin_from_ms(profile: dict, middle: str | None = None) -> tuple[dict | None, str]:
    """My name in Latin from Microsoft's displayName, read word by word against its givenName and surname (Cyrillic in
    KBTU's directory): every word Latin letters only (no login, mail, initial, digits or
    note), each word one side's alone, both sides whole; one word more is the middle name only when it is my known one,
    else dropped; two more: nothing. A wrong Latin name would reach the university's lists, a missing one shows blank.
    (columns or None, why)"""
    from .. import roster  # imports logic: here, not at the top
    toks = str(profile.get("displayName") or "").split()
    given, sur = roster._words(profile.get("givenName")), roster._words(profile.get("surname"))
    if not toks or not given or not sur:
        return None, "empty"
    if not all(_LAT_WORD.fullmatch(t) for t in toks):
        return None, "script"
    side: dict[str, list[str]] = {"first": [], "last": [], "rest": []}
    for t in toks:
        w = roster._words(t)
        if w <= given and w <= sur:
            return None, "ambiguous"
        side["first" if w <= given else "last" if w <= sur else "rest"].append(t)
    if roster._words(" ".join(side["first"])) != given or roster._words(" ".join(side["last"])) != sur \
            or any(len(side[k]) != len({frozenset(roster._words(t)) for t in side[k]}) for k in ("first", "last")):
        return None, "side"  # a side missing, or a word written twice (Aidos Aidos)
    if len(side["rest"]) > 1:
        return None, "rest"
    mid = side["rest"][0] if side["rest"] and middle and roster._words(side["rest"][0]) == roster._words(middle) else None
    return {"first_lat": " ".join(side["first"]), "last_lat": " ".join(side["last"]), "middle_lat": mid}, "ok"


def _fill_lat(con, uid: int, profile: dict, listed: dict) -> int:
    """The Latin name columns still empty that I never corrected: from KBTU's directory, else my freshmen list row's.
    Never over a value or a fix of mine (a relink, the backfill). Returns how many columns it filled."""
    s = one(con, "SELECT middle_name, last_lat, first_lat, middle_lat, fixed FROM students WHERE user_id = ?", uid)
    ms = latin_from_ms(profile, s["middle_name"])[0] or {}
    sets = {c: v for c in LAT_COLS if (v := ms.get(c) or listed.get(c)) and s[c] is None and c not in s["fixed"].split(",")}
    if sets:
        con.execute(f"UPDATE students SET {', '.join(c + ' = ?' for c in sets)} WHERE user_id = ?", (*sets.values(), uid))
    return len(sets)


def latin_names(con, apply: bool = False) -> Counter:
    """admin latin-names: the shape of what KBTU's directory gives (counts only, never a value), and with
    `apply` the backfill of the students linked before the Latin columns, in one transaction (idempotent: empty columns only)."""
    from .. import roster
    n: Counter = Counter()
    cyr = re.compile("[\u0400-\u04ff]")
    with tx(con) if apply else contextlib.nullcontext():
        for s in rows(con, f"SELECT * FROM students s WHERE NOT {core.staff_sql()}"):
            n["students"] += 1
            ms = json.loads(s["ms_profile"] or "{}")
            n["ms_profile"] += bool(ms)
            n["middle_name_latin"] += bool(s["middle_name"] and LATIN_NAME.fullmatch(s["middle_name"]))
            n["name_cols_latin"] += any(s[c] and LATIN_NAME.fullmatch(s[c]) for c in ("first_name", "last_name"))
            for c in s["fixed"].split(","):
                n[f"fixed_{c}"] += bool(c)
            dn = str(ms.get("displayName") or "")
            if not dn.strip():
                continue
            n["display_name"] += 1
            toks = dn.split()
            n["script_" + ("junk" if re.search(r"[@_\d.]", dn) else "mixed" if cyr.search(dn) and re.search("[A-Za-z]", dn)
                           else "cyrillic" if cyr.search(dn) else "latin")] += 1
            n[f"tokens_{min(len(toks), 4)}"] += 1
            w0 = roster._words(toks[0])
            n["first_token_" + ("surname" if w0 and w0 <= roster._words(ms.get("surname")) else
                                "given" if w0 and w0 <= roster._words(ms.get("givenName")) else "neither")] += 1
            n["hyphen"] += "-" in dn
            n["apostrophe"] += "'" in dn
            n["accent"] += any(ord(ch) > 127 and not cyr.match(ch) for ch in dn)
            got, why = latin_from_ms(ms, s["middle_name"])
            n[f"parse_{why}"] += 1
            if got:
                n["parse_with_middle"] += bool(got["middle_lat"])
                n["would_fill"] += s["first_lat"] is None and "first_lat" not in s["fixed"].split(",")
            if apply:
                n["filled_columns"] += _fill_lat(con, s["user_id"], ms, {})
        for p in rows(con, "SELECT last_name, first_name, middle_name FROM prefill"):
            lat = [bool(p[k] and LATIN_NAME.fullmatch(p[k])) for k in ("last_name", "first_name")]
            n["prefill_" + ("latin" if all(lat) else "mixed" if any(lat) else "other")] += 1
            n["prefill_middle_latin"] += bool(p["middle_name"] and LATIN_NAME.fullmatch(p["middle_name"]))
    return n


PREFILL_COLS = ("email", "student_id", "last", "first", "middle", "school", "phone", "came")
_text = lambda x, k: " ".join(str(x or "").split())[:k] or None  # noqa: E731


def _prefill_sort(got: list[dict]) -> tuple[Counter, dict[str, dict], list[dict]]:
    """The freshmen list's rows sorted: the good ones by KBTU mail (one ID each, the ID one mail's), and the rest, each
    with its parsed mail (or "") and ID (or None)."""
    n = Counter(rows=len(got))
    good: dict[str, dict] = {}
    rest: list[dict] = []
    by_email: dict[str, list[dict]] = {}
    for r in got:  # each row lands in exactly one count: they add up to `rows` (bad_phone aside: the row stays)
        email, sid = "".join(str(r.get("email") or "").split()).lower(), norm_sid(r.get("student_id"))
        x = {**r, "raw_id": r.get("student_id"), "email": email, "student_id": sid, "came": int(str(r.get("came") or "").strip() == "1")}
        if not re.fullmatch(r"[a-z0-9._%+-]+@kbtu\.kz", email):
            n["bad_email"] += 1
            rest.append(x)
        elif not sid:
            n["bad_id"] += 1
            rest.append(x)
        else:
            by_email.setdefault(email, []).append(x)
            n["same"] += email in good  # the same mail again: one row, "came" if any of them says so
            good.setdefault(email, {**x, "came": 0})["came"] |= x["came"]
    for e in [e for e, xs in by_email.items() if len({x["student_id"] for x in xs}) > 1]:  # one mail, two IDs: which one is it
        n["dup_email"] += len(by_email[e])
        n["same"] -= len(by_email[e]) - 1
        rest += by_email[e]
        del good[e]
    ids = Counter(r["student_id"] for r in good.values())
    for e in [e for e, r in good.items() if ids[r["student_id"]] > 1]:  # one ID, two mails: a typo somewhere
        n["dup_id"] += 1
        rest.append(good.pop(e))
    return n, good, rest


def prefill_rest_import(con, got: list[dict], name: str) -> dict[str, int]:
    """The rest of a freshmen list (admin prefill-rest, the same CSV as prefill-import): the rows the main import didn't
    keep. A confirmed student whose KBTU mail or student ID the row has, and
    whose name it is: the badge if they came, nothing else (their profile is theirs: a phone they deleted must not
    come back), nothing stored. Otherwise the row waits in
    prefill_rest for ms_link: a KBTU mail only (else NULL), the ID only when it is valid and the list's one person's,
    the phone only well-formed; the ID as typed stays for the owner (never shown, never matched). A row with neither
    mail nor ID just sits (the owner keeps everything). Rows still in prefill, or kept once and gone since (used, or an
    account deleted: no student has its mail, and its ID wasn't held when the main import ran), are skipped. Each
    `name` once, after prefill-import ran it. Counts only. ValueError: ran already, or the main import never did."""
    _, good, rest = _prefill_sort(got)
    n = Counter(rows=len(got))
    # an ID given to two mails, or a mail given two IDs: which person is it? Those rows match by their mail only
    same = {(x["email"], x["student_id"], _text(x.get("last"), 40), _text(x.get("first"), 40)) for x in [*good.values(), *rest] if x["student_id"]}
    per_sid = Counter(sid for _, sid, *_ in same)
    per_mail = Counter(e for e, _ in {(e, sid) for e, sid, *_ in same} if e)
    shared = {sid for e, sid, *_ in same if per_sid[sid] > 1 or e and per_mail[e] > 1}
    with tx(con):
        main = one(con, "SELECT value FROM meta WHERE key = ?", f"prefill_list:{name}")
        if not main or one(con, "SELECT 1 FROM meta WHERE key = ?", f"prefill_rest:{name}"):
            raise ValueError(name)  # a typo'd name would count every kept row gone, or store it again
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"prefill_rest:{name}", str(core.now())))
        for x in [*good.values(), *rest]:
            kbtu = x["email"] if re.fullmatch(r"[a-z0-9._%+-]+@kbtu\.kz", x["email"]) else None
            sid = x["student_id"] if x["student_id"] not in shared else None
            p = {"last_name": _text(x.get("last"), 40), "first_name": _text(x.get("first"), 40), "middle_name": _text(x.get("middle"), 40),
                 "school": _text(x.get("school"), 120), "phone": kz_phone(x.get("phone")), "came": x["came"]}
            s = kbtu and one(con, "SELECT * FROM students WHERE lower(email) = ? AND ms_oid IS NOT NULL", kbtu) \
                or sid and one(con, "SELECT * FROM students WHERE student_id = ? AND ms_oid IS NOT NULL", sid)
            if x["email"] in good and one(con, "SELECT 1 FROM prefill WHERE email = ?", x["email"]):
                n["in_prefill"] += 1
            elif s and prefill_mine(p, s["first_name"], s["last_name"]):
                if p["came"] and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'init26f'", s["user_id"]):
                    profiles._grant(con, None, s["user_id"], "init26f")
                    n["badged"] += 1
                n["matched"] += 1
            elif x["email"] in good and not one(con, "SELECT 1 FROM students WHERE lower(email) = ?", x["email"]) \
                    and not one(con, """SELECT 1 FROM students WHERE student_id = ? AND verified_at <= ?
                        UNION ALL SELECT 1 FROM prefill WHERE student_id = ? AND email != ?""", x["student_id"], int(main[0]), x["student_id"], x["email"]):
                n["gone"] += 1  # kept by the main import (its ID free then), used or deleted since: never back
            else:
                con.execute("""INSERT INTO prefill_rest (email, student_id, raw_id, last_name, first_name, middle_name, school, phone, came)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (kbtu, sid, _text(x.get("raw_id"), 40), p["last_name"], p["first_name"],
                                                         p["middle_name"], p["school"], p["phone"], p["came"]))
                n["stored"] += 1
                n["sits"] += not kbtu and not sid
    return dict(n)


def prefill_import(con, got: list[dict], name: str) -> dict[str, int]:
    """The freshmen list (admin prefill-import): one row per KBTU mail. Each list `name` runs once (meta), so a row
    whose account was deleted never comes back. Dropped: a bad mail or ID, an ID given to two mails, a mail given two
    IDs, a mail or ID a student already has; a student already confirmed with the row's ID and name who came gets the badge
    now (badged). Counts only: the caller prints them, never a value. ValueError: this list ran already."""
    n, good, _ = _prefill_sort(got)
    with tx(con):
        if one(con, "SELECT 1 FROM meta WHERE key = ?", f"prefill_list:{name}"):
            raise ValueError(name)
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"prefill_list:{name}", str(core.now())))
        for r in good.values():
            s = one(con, "SELECT user_id, student_id, ms_oid, first_name, last_name FROM students WHERE lower(email) = ?", r["email"])
            if s and r["came"] and s["ms_oid"] and s["student_id"] == r["student_id"] \
                    and prefill_mine({"last_name": r.get("last"), "first_name": r.get("first"), "middle_name": r.get("middle")}, s["first_name"], s["last_name"]) \
                    and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'init26f'", s["user_id"]):
                profiles._grant(con, None, s["user_id"], "init26f")  # signed up before the list came: the badge, not the row
                n["badged"] += 1
            elif s:
                n["signed_up"] += 1
            elif one(con, "SELECT 1 FROM students WHERE student_id = ? UNION ALL SELECT 1 FROM prefill WHERE student_id = ? AND email != ?",
                     r["student_id"], r["student_id"], r["email"]):
                n["id_held"] += 1
            else:
                phone = kz_phone(r.get("phone"))
                n["bad_phone"] += bool(_text(r.get("phone"), 40) and not phone)  # kept without it: a bad export shows here
                con.execute("""INSERT INTO prefill (email, student_id, last_name, first_name, middle_name, school, phone, came)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (email) DO UPDATE SET student_id = excluded.student_id,
                    last_name = excluded.last_name, first_name = excluded.first_name, middle_name = excluded.middle_name,
                    school = excluded.school, phone = excluded.phone, came = excluded.came""",
                            (r["email"], r["student_id"], _text(r.get("last"), 40), _text(r.get("first"), 40), _text(r.get("middle"), 40),
                             _text(r.get("school"), 120), phone, r["came"]))
                n["kept"] += 1
    return dict(n)


def refer(con, v: Viewer, code: object) -> None:
    """Opened by someone's invite link (r_<their link code>, never a user ID) or their profile QR (u_<id>_<badge code>,
    the same QR the invite sheet shows; both halves must match): the first link wins, and only before I signed in with
    KBTU; it counts for them once I have (ms_link)."""
    m = re.fullmatch(r"(?:(\d{1,12})_)?([A-Z2-7]{10})", code) if isinstance(code, str) else None
    if not m:
        raise ApiError("bad_input")
    by = (one(con, "SELECT id FROM users WHERE id = ? AND qr_code = ? AND id != ?", int(m[1]), m[2], v.id) if m[1]
          else one(con, "SELECT id FROM users WHERE link_code = ? AND id != ?", m[2], v.id))
    if by and not one(con, "SELECT 1 FROM students WHERE user_id = ? AND manual = 0", v.id):
        con.execute("UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL", (by["id"], v.id))


def ms_remember(con, uid: int, who: dict) -> None:
    """Signed in with Microsoft before typing the student ID and year: kept a week (MS_KEEP) for kbtu_manual"""
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (f"ms:{uid}", json.dumps({**who, "at": core.now()})))


MS_KEEP = 7 * 86400  # a Microsoft sign-in waits a week for the student ID and year (a day is too short)


def ms_pending(con, uid: int) -> dict | None:
    r = one(con, "SELECT value FROM meta WHERE key = ?", f"ms:{uid}")
    who = json.loads(r[0]) if r else None
    return who if who and who["at"] > core.now() - MS_KEEP else None


def ms_check(con, uid: int, who: dict):
    """Whether this Microsoft account may go on this Telegram (raises why not); my student row, if any."""
    other = one(con, "SELECT user_id FROM students WHERE ms_oid = ?", who["oid"])
    if other and other[0] != uid:
        raise ApiError("conflict", "linked")  # this Microsoft account is someone else's student already
    mine = one(con, "SELECT ms_oid FROM students WHERE user_id = ?", uid)
    if mine and mine[0] and mine[0] != who["oid"]:
        raise ApiError("conflict", "other_ms")  # already confirmed with another KBTU account: no silent swap
    return mine


MS_CLAIM_TTL = 15 * 60  # the browser's way back into the Mini App (msauth.TTL, the link's own life)


def ms_hold(con, uid: int, who: dict) -> str:
    """A Microsoft sign-in done in a browser waits for the Mini App of the Telegram that started it: the browser gets a
    one-time secret for the app's start link, so a sign-in link sent to someone else can't tie their account to the
    sender's Telegram (only their own app opens, and it is not his)."""
    ms_check(con, uid, who)  # the browser hears "linked" / "other_ms" at once
    secret = secrets.token_urlsafe(18)
    con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"ms_claim:{secret}", json.dumps({"uid": uid, "who": who, "at": core.now()})))
    return secret


def ms_release(con, secret: str) -> None:
    """The browser's "it didn't open": the start link never reached the Mini App (Telegram's own browser on Android shows
    t.me as a web page), so the one who signed in agrees, seeing the Telegram's name, that its app may take the sign-in
    by itself (ms_claim with no secret). The same guard the page's "Link to <name>?" tap was: a forwarded link still
    binds nothing unseen."""
    if not re.fullmatch(r"[\w-]{24}", secret) or not con.execute(
            "UPDATE meta SET value = json_set(value, '$.open', 1) WHERE key = ? AND json_extract(value, '$.at') >= ?",
            (f"ms_claim:{secret}", core.now() - MS_CLAIM_TTL)).rowcount:
        raise ApiError("forbidden", "ms")


def ms_claim(con, v: Viewer, secret: str) -> bool:
    """The Mini App's own step after the browser: only the Telegram that started the sign-in takes it (ms_apply's bool).
    No secret: my newest sign-in the browser released (ms_release), when the start link didn't bring it. The secret from
    another Telegram proves the link was forwarded: the hold is gone for good (were it kept, the page's
    "Doesn't open?" would lead the one who signed in to release it to the link's sender)."""
    if not secret:  # read first: no write lock for the usual "nothing waits"
        mine = one(con, """SELECT key FROM meta WHERE key >= 'ms_claim:' AND key < 'ms_claim;' AND json_extract(value, '$.uid') = ?
            AND json_extract(value, '$.open') = 1 ORDER BY json_extract(value, '$.at') DESC LIMIT 1""", v.id)
        secret = mine[0][len("ms_claim:"):] if mine else ""
    with tx(con):
        row = one(con, "DELETE FROM meta WHERE key = ? RETURNING value", f"ms_claim:{secret}") if re.fullmatch(r"[\w-]{24}", secret) else None
        held = json.loads(row[0]) if row else None
        if held and held["uid"] == v.id and held["at"] >= core.now() - MS_CLAIM_TTL:
            return ms_apply(con, v.id, held["who"])
    raise ApiError("forbidden", "ms")


def staff_row(con, uid: int, first: str, last: str, school: str | None = None, consent: str = "staff") -> None:
    """A KBTU staff member acts as a student (SPEC §1): no student ID of theirs exists, so a placeholder no real one can
    match (`staff<id>`). consent 'staff': typed in by the creator (kbtu.admin staff), no policy gate; else the version
    the person accepted at the sign-in (staff_ok's way)."""
    t = core.now()
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, school, consent_version, consent_at,
        verified_at, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (uid, f"staff{uid}", first, last, school, consent, t, t, t))


def staff_ok(con, uid: int, who: dict | None) -> bool:
    """The creator said this account is KBTU staff (kbtu.admin staff-ok), and Microsoft doesn't call it a student: its
    sign-in asks no student ID; DMP's list (kbtu.admin dmp) is the same word given ahead. Office membership, roles,
    audit lines: never a reason."""
    if not one(con, "SELECT 1 FROM staff_ok WHERE user_id = ?", uid) and not dmp_listed(con, uid):
        return False
    # ponytail: KBTU's directory field read as is; "student" anywhere in it wins (exact values unmeasured)
    return "student" not in str(((who or {}).get("profile") or {}).get("companyName") or "").lower()


_DMP_MINE = "FROM dmp_list d JOIN users u ON u.id = ? AND d.tg_id = u.tg_id"  # the id alone: a stored username can be stale


def dmp_listed(con, uid: int):
    """This Telegram on DMP's list (kbtu.admin dmp), by its id (a username row binds to one first: dmp_bind)."""
    return one(con, "SELECT d.* " + _DMP_MINE, uid)


def dmp_bind(con, tg: dict) -> None:
    """A username on DMP's list binds to the Telegram whose own signed data (a Mini App open, never a browser session's
    stored name) shows it first; from then on only that id counts, whoever holds the name next. The same person listed
    by id too: one row."""
    name = tg.get("username")
    if not isinstance(name, str) or not name or not one(con, "SELECT 1 FROM dmp_list WHERE tg_username = ? AND tg_id IS NULL", name):
        return  # the usual open: one indexed read
    # ponytail: a handle given away before its owner's first open binds to its new holder; `dmp list` shows whom
    with tx(con):
        if one(con, "SELECT 1 FROM dmp_list WHERE tg_id = ?", tg["id"]):
            con.execute("DELETE FROM dmp_list WHERE tg_username = ? AND tg_id IS NULL", (name,))
            con.execute("UPDATE dmp_list SET tg_username = ? WHERE tg_id = ? AND tg_username IS NULL", (name, tg["id"]))
        else:
            con.execute("UPDATE dmp_list SET tg_id = ? WHERE tg_username = ? AND tg_id IS NULL", (tg["id"], name))


def dmp_greeted(con, v: Viewer) -> None:
    """The one-time "Hi, DMP" left for Microsoft: never shown again to this Telegram."""
    with tx(con):
        con.execute(f"UPDATE dmp_list SET greeted_at = ? WHERE greeted_at IS NULL AND id IN (SELECT d.id {_DMP_MINE})", (core.now(), v.id))


def dmp_ids(row) -> list[str]:
    """A grant's names in the deletion journal: a restored copy can hold it by id, or still as the invitation's username."""
    return ([f"dmp:{row['tg_id']}"] if row["tg_id"] else []) + ([f"dmp:@{row['tg_username'].lower()}"] if row["tg_username"] else [])


def ms_apply(con, uid: int, who: dict) -> bool:
    """The Microsoft account on this Telegram: a student already confirmed (True), or remembered for the form."""
    mine = ms_check(con, uid, who)
    if mine:
        ms_link(con, uid, who)
        return True
    ms_remember(con, uid, who)
    return False


def ms_sweep(con) -> None:
    """Every 5 minutes (the bot's round): Microsoft sign-ins never finished (they hold the Graph profile), the used-link
    marks, and share cards past their hour (core.share_hold). Key ranges, not LIKE: LIKE (case-blind, `_` a wildcard)
    can't use meta's primary key."""
    if not core._once(con, "ms_sweep", str(core.now() // 300)):
        return
    con.execute("DELETE FROM meta WHERE key >= 'ms:' AND key < 'ms;' AND (NOT json_valid(value) OR json_extract(value, '$.at') < ?)", (core.now() - MS_KEEP,))
    con.execute("DELETE FROM meta WHERE key >= 'ms_used:' AND key < 'ms_used;' AND CAST(value AS INTEGER) < ?", (core.now() - 86400,))
    con.execute("DELETE FROM meta WHERE key >= 'ms_claim:' AND key < 'ms_claim;' AND json_extract(value, '$.at') < ?", (core.now() - MS_CLAIM_TTL,))
    con.execute("DELETE FROM meta WHERE key >= 'chpick:' AND key < 'chpick;' AND CAST(substr(value, instr(value, ':') + 1) AS INTEGER) < ?", (core.now(),))
    con.execute("DELETE FROM chat_waits WHERE until < ?", (core.now(),))
    con.execute("DELETE FROM meta WHERE key >= 'share:' AND key < 'share;' AND json_extract(value, '$.at') < ?", (core.now() - core.SHARE_TTL,))


SID_WAIT = 30 * 86400  # how long the one turned away waits to hear the ID is free (then the parked message lapses)


def id_clash(con, sid: str, new: int, old: int) -> None:
    """Someone signed in with Microsoft gave a student ID another student holds (no hand work on IDs:
    two people can be one digit apart, the holder with the typo). No admin: the holder is asked to check
    theirs (once per ID), and the newcomer gets a parked message that migration 127's triggers send the moment the ID
    is freed, however (a fix, an unlink, a deleted account); unfreed, it lapses unsent. Three IDs per newcomer, so
    nobody can ping every holder by trying numbers. The rare real dispute (a holder keeping someone else's ID) stays
    the support's: both sides are real KBTU Microsoft accounts."""
    if one(con, "SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'sid_free' AND sent_at IS NULL", new)[0] >= 3:
        return
    notify(con, old, "sid_check", f"sc:{sid}")
    notify(con, new, "sid_free", f"sf:{sid}", after=core.now() + SID_WAIT)


def _channel(c) -> dict | None:
    """An org's main chat for Studio's tile: its name, and whether its posts reach the news (a public channel, the switch on)."""
    from .. import mirror  # it imports this package
    return {"title": c["title"], "mirror": bool(c["mirror"] and c["kind"] == "channel" and mirror.username(c["url"]))} if c else None


def _membership(con, m, mains: dict, logos: dict) -> dict:
    """One of /api/me's memberships (and the creator's lent one, lent_studio)."""
    return {"org": org_ref(con, m, logos), "role": m["role"], **core.titled(m), "rights": _ordered(core.club_rights(m["role"], m["rights"], m)),
            "oversee": bool(m["can_oversee"] and m["role"] != "member"),
            **({"channel": _channel(mains.get(m["id"]))} if "profile" in _rights_from(m["role"], m["rights"]) else {}),
            # the composer's locked state (clubs.stories_open): read only for a writer of a student initiative
            **({"storiesLocked": True} if "posts" in _rights_from(m["role"], m["rights"]) and not m["official"]
               and m["kind"] == "club" and not stories_open(con, m) else {})}


def lent_studio(con, v: Viewer, oid: int) -> dict:
    """The creator's Studio of a club he isn't in (Admin, X-Staff-Org, app.viewer): its President's membership as /api/me
    would give it, and every role of the club's model for his "view as" (the levels, then the club's own roles): each
    one's rights as the server lends them with X-Staff-Role. Never its reports: their consent names the club's team alone (evreports.py)."""
    o = one(con, "SELECT * FROM orgs WHERE id = ?", oid)
    if not (v.lent_full and v.staff_org == oid and o):
        raise ApiError("forbidden", "staff")
    main = one(con, "SELECT org_id, title, kind, url, mirror FROM chats WHERE main = 1 AND org_id = ?", oid)
    m = {**dict(o), "role": "president", "rights": None, "title": None, "title_kk": None, "title_en": None}
    out = _membership(con, m, {oid: main} if main else {}, core._by_id(con, "files", [o["logo_file_id"]]))
    lent = lambda lv, r: [x for x in _ordered(core.club_rights(lv, r, o)) if x != "reports"]  # noqa: E731
    out["rights"] = lent("president", None)
    own = rows(con, "SELECT id, name, name_kk, name_en, level, rights FROM org_roles WHERE org_id = ? ORDER BY id", oid)
    return {"membership": out, "roles": [{"key": lv, "level": lv, "title": None, "titleKk": None, "titleEn": None, "rights": lent(lv, None)}
                                         for lv in ("president", "vice", "head", "member")]
            + [{"key": f"r{r['id']}", "level": r["level"], "title": r["name"], "titleKk": r["name_kk"], "titleEn": r["name_en"],
                "rights": lent(r["level"], r["rights"])} for r in sorted(own, key=lambda r: -RANK[r["level"]])]}


PLATFORMS = ("android", "ios", "desktop", "web")  # the coarse device kinds kept (user_platforms); the web app picks one


def seen_platform(con, uid: int, kind: str | None, app: str | None = None) -> None:
    """The device kind someone opened the app on, from /api/me: a read first, then a write (never waited for) at most
    once a day per kind, so the creator can write to the people of one platform (admin broadcast --platform).
    app='play': it was the installed Android app (android_app), so its install row and sheet stop."""
    if kind not in PLATFORMS:
        return
    at = one(con, "SELECT seen_at FROM user_platforms WHERE user_id = ? AND kind = ?", uid, kind)
    if at is None or at[0] <= core.now() - 86400:
        db.maybe(con, con.execute, """INSERT INTO user_platforms (user_id, kind, seen_at) VALUES (?, ?, ?)
            ON CONFLICT (user_id, kind) DO UPDATE SET seen_at = excluded.seen_at""", (uid, kind, core.now()))
    if app == "play" and kind == "android":
        at = one(con, "SELECT seen_at FROM android_app WHERE user_id = ?", uid)
        if at is None or at[0] <= core.now() - 86400:
            db.maybe(con, con.execute, """INSERT INTO android_app (user_id, seen_at) VALUES (?, ?)
                ON CONFLICT (user_id) DO UPDATE SET seen_at = excluded.seen_at""", (uid, core.now()))


def me(con, v: Viewer) -> dict:
    from .. import checkin, push, roster
    if v.student and roster.due(con, v.id):  # a read first: the write lock only when a row would join
        db.maybe(con, roster.match, con, v.id)  # A matching club roster row can add a membership. Skip the match if the database is busy.
    u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    s = one(con, "SELECT * FROM students WHERE user_id = ?", v.id)
    relink = bool(s and s["manual"])  # typed in before Microsoft only: signed out until Microsoft confirms
    s = None if relink else s
    dmp = dmp_listed(con, v.id) if not s and not relink else None
    members = rows(con, f"""SELECT m.role, {core.TITLES}, t.rights, o.* FROM org_members m JOIN orgs o ON o.id = m.org_id
        LEFT JOIN org_roles t ON t.id = m.role_id WHERE m.user_id = ? AND o.status = 'active'""", v.id) if s else []
    # Studio's "Channel → news" tile (Vice+, who link chats): each org's main chat, one read for all of them
    mains = {c["org_id"]: c for c in rows(con, f"SELECT org_id, title, kind, url, mirror FROM chats WHERE main = 1 AND org_id IN ({','.join('?' * len(members))})",
                                          *(m["id"] for m in members))} if members else {}
    logos = core._by_id(con, "files", (m["logo_file_id"] for m in members))  # every club's logo in one read, not one per membership
    tickets = one(con, """SELECT COUNT(*) FROM registrations r JOIN events e ON e.id = r.event_id
        WHERE r.user_id = ? AND r.status = 'going' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""", v.id, NO_END, core.now())[0]
    name_row = one(con, PERSON + " WHERE u.id = ?", v.id)
    own = one(con, "SELECT path FROM files WHERE id = ?", u["avatar_file_id"]) if u["avatar_file_id"] else None
    # the card number at the KBTU sign-in, in the order people came (so one sees who came
    # 84th); staff (kbtu.admin staff) take none: it's the
    # students' order. A deleted account's number stays empty, never given again.
    # Grant the award on open if a qualifying card number already exists without its grant.
    if s and not core.is_staff(s) and (u["card_no"] is None and not u["is_founder"] or (
            (u["is_founder"] or (u["card_no"] or profiles.FIRST_N + 1) <= profiles.FIRST_N)
            and not one(con, "SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'first50'", v.id))):
        if u["card_no"] is None and not u["is_founder"]:
            with tx(con):  # the number in the order people came: it waits for the lock, once per person
                first_fifty(con, v.id)
        else:
            db.maybe(con, first_fifty, con, v.id)  # a missing "First 500" repaired (skipped in a burst: the next open)
        u = one(con, "SELECT * FROM users WHERE id = ?", v.id)
    return {
        "id": u["id"], "tg": {"id": u["tg_id"], "username": u["tg_username"], "firstName": u["tg_first_name"], "lastName": u["tg_last_name"]},
        "avatar": avatar_of(name_row), "name": shown_name(name_row), **name_i18n(name_row), "nick": u["nick"],
        "photo": {"telegram": bool(u["avatar_tg"]), "tg": avatar_of({**name_row, "own_photo": None}), "own": f"media/{own['path']}.t.webp" if own else None},
        "student": {"studentId": s["student_id"], "firstName": s["first_name"], "lastName": s["last_name"], "middleName": s["middle_name"], "email": s["email"],
                    "lastLat": s["last_lat"], "firstLat": s["first_lat"], "middleLat": s["middle_lat"],
                    "phone": s["phone"], "course": s["course"], "courseMin": core.course_of(s["student_id"]), "school": s["school"], "program": s["program"], "syncedAt": s["synced_at"],
                    "ms": s["ms_oid"] is not None, "manual": bool(s["manual"]), "consent": s["consent_version"],
                    "freeFirst": core.first_year_free(con, v.id),  # the event sheet's "Go free" (_free_seat's rule)
                    # what My data still lets me correct myself (fix_identity, _spend): for staff only the school
                    "fixable": [k for k, c in ONCE.items() if (c not in s["fixed"].split(",") or c in ("school", "course") and s[c] is None) and (c == "school" or not core.is_staff(s))],
                    # spent, yet the value before it can come back once (_spend)
                    "undo": {k: x for k, x in json.loads(s["once_was"] or "{}").items() if k in s["fixed"].split(",")}} if s else None,
        # signed in with Microsoft, the student ID and year still to type: the form shows the account's names
        # prefill: the student ID an organizers' check-in list, or the freshmen list when the name matches, has for this KBTU mail (checkin.py)
        "msPending": {**{k: p[k] for k in ("first", "last", "email")}, "prefill": checkin.prefill(con, p["email"], p)}
                     if not s and not relink and (p := ms_pending(con, v.id)) else None,
        "relink": relink,
        # the creator's staff (staff_ok): Microsoft and the policy, no student ID (the welcome's sign-in, the form without it)
        **({"msOnly": True} if not s and not relink and staff_ok(con, v.id, ms_pending(con, v.id)) else {}),
        "referrals": {"count": brought(con, v.id), "code": _qr_code(con, v.id, "link_code")} if s else None,
        "role": u["role"], "canDm": bool(u["can_dm"]),
        # notifications on one channel (push.py): my pick, and app: a live app token of mine (Settings shows the pick then)
        "notify": {"via": u["notify_via"], "app": bool(one(con, f"SELECT {push.LIVE.format('?')}", v.id, *push.bounds(core.now()))[0])},
        "founder": bool(u["is_founder"]), "mark": u["mark"], "qr": f"{v.id}_{_qr_code(con, v.id)}" if s else None,
        "evRef": ev_ref(v.id) if s else None,  # "My link"'s code (seats.ev_ref): the plain t.me share carries it, never the badge's
        "no": (0 if u["is_founder"] else u["card_no"]) if s else None,
        "oversee": any(m["can_oversee"] and m["role"] != "member" for m in members),
        "bio": u["bio"], "showcase": [x for x in u["showcase"].split(",") if x],
        "settings": {**{k: (u[c] if k in ("lang", "theme") else bool(u[c])) for k, c in SETTINGS.items()}, "suggestMe": pymk.is_on(con, v.id)},
        # oversee: this org is DMP and I lead in it: Studio shows the registry with it picked
        "memberships": [_membership(con, m, mains, logos) for m in members],
        # an office's own person before the KBTU sign-in: the app greets them as the team once (web App teamHi); no rights in it
        # (DMP's own hello already left on another phone: not again as the office's)
        "office": org_ref(con, o) if not s and (o := one(con, """SELECT o.* FROM org_members m JOIN orgs o ON o.id = m.org_id
            WHERE m.user_id = ? AND o.kind = 'office' AND o.status = 'active'""", v.id)) and not (o["slug"] == "dmp" and dmp and dmp["greeted_at"]) else None,
        # on DMP's list, not signed in, not greeted yet: the office's one-time hello, then Microsoft (web App teamHi)
        "dmpHi": org_ref(con, d) if dmp and dmp["greeted_at"] is None
                 and (d := one(con, "SELECT * FROM orgs WHERE slug = 'dmp' AND status = 'active'")) else None,
        "counters": {"tickets": tickets, "unreadBroadcasts": unread_broadcasts(con, v),
                     "friendRequests": one(con, "SELECT COUNT(*) FROM friend_requests WHERE to_id = ? AND status = 'pending'", v.id)[0] if v.student else 0,
                     "inbox": inbox.count(con, v)},  # Admin's shield: everything waiting for the staff (logic/inbox.py)
        "unlocked": unlocked(con, v),
        **appchats.mine(con, v.id),  # in the app's channel / group: Profile hides their rows
        "skin": _skin(con, v.id) if s else None,
        "frame": u["frame"] if s and u["frame"] in FRAMES else None,
        "deleteAt": u["delete_at"],  # my week to change my mind, whoever may ask it (a student, relink, an Apple account)
        "city": {"name": u["city"], "hidden": bool(u["city_hidden"])} if u["city"] else None,
        "roster": _roster_mine(con, v.id),
        # the capsule's running check-in, and the check-in page's way in: "pair" for who runs a club's events (Studio's
        # "Check-in" row; Profile's too while nothing in Studio leads there: a door handed over by the volunteers ledger,
        # only while its session is open; never the app's admin for every club: that's Admin), "qr" for a helper's own QR
        "checkin": (c := checkin.running(con, v)),
        "bigScreen": "pair" if any("events" in _rights_from(m["role"], m["rights"]) for m in members) or one(con, """SELECT 1 FROM vol_hands h
            JOIN qr_sessions s ON s.id = h.session_id WHERE h.user_id = ? AND h.revoked_at IS NULL AND s.ended_at IS NULL""", v.id)
            else "qr" if c and c["helper"] else None,
        "androidApp": bool(one(con, "SELECT 1 FROM android_app WHERE user_id = ?", v.id)),  # Profile's Google Play row goes
    }


def roster_requests(con, v: Viewer, org: int | None = None) -> list[dict]:
    """Claims I confirm (roster.requests) with the club and the student as the app shows them."""
    from .. import roster
    out, got = [], roster.requests(con, v, org)
    orgs = core._by_id(con, "orgs", (r["org"] for r in got))  # the clubs, their logos and the people: one read each for the list
    logos = core._by_id(con, "files", (o["logo_file_id"] for o in orgs.values()))
    uids = list({r["user"] for r in got})
    people = {p["id"]: p for p in rows(con, PERSON + f" WHERE u.id IN ({','.join('?' * len(uids))})", *uids)} if uids else {}
    for r in got:
        o, p = orgs.get(r["org"]), people.get(r["user"])
        if o and p:
            out.append({**r, "org": org_ref(con, o, logos), "person": person_ref(p)})
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


# the frames over a photo on the lanyard, anyone's to pick, apart from the lanyard (web: public/frames/<id>.svg)
# ponytail: one list for everyone; a club's own frame for its members alone comes with the first club that draws one
FRAMES = ("flowers", "space", "hearts", "sparkles", "laurel", "leaves", "snow", "notes", "neon", "blossom", "gold")  # web: SettingsList FRAMES, public/frames/<id>.svg (test_frames)


# the clubs with a lanyard of their own, by slug (stable, the same in prod and tests); any club may have one, official or
# not. The web's list is awards.ts `SKINS` + `CLUB_LOOKS`: tests/test_lanyards.py holds the two equal
LANYARDS = ("studex", "kbtucheerleadingclub", "kbtuknights", "moments", "faceskbtu",
            "mountainkingskbtu", "crystalkbtu", "spekbtu", "aichekbtu", "arthousekbtu", "qairymdylyqkbtu", "shadekbtu", "japanesecultureclub",
            "choice", "teentertainmentkbtu", "klubanimeshnikov",
            "kbtumag",  # kbtu.mag: matched by its name (SKINNED)
            "enactuskbtu", "caseclubkbtu", "knlknolimits", "literatureclub", "tumarorchestrakbtu", "web", "zhylyzhurekkbtu",
            "kbtucinema", "nisalumnikbtuchapter",
            "cybersportkbtu",
            "diceanddestinykbtu",
            "thebayharborsociety",
            "qoloner")
# the archive: looks made and not in use (owner, Nov 25), anyone's to try on in the picker (the web alone), the creator's
# alone to wear; stored as skin_pick 'sower' with skin_look. The web's list is awards.ts ARCHIVE_LOOKS (test_lanyards)
ARCHIVE = ("dota_ancient", "dota_clash", "dota_rune")
_LIST = "(" + ", ".join(f"'{x}'" for x in LANYARDS) + ")"
# by slug, or by the name without dots, spaces and dashes ("kbtu.mag" is kbtumag: made in the app under another slug),
# as the web's awards.ts lookKey
# other names a drawn club goes by (kbtu.mag is just "Mag"); as the web's awards.ts ALIASES
LANYARD_NAMES = ("mag", "kbtumag", "kbtumagazine", "\u043c\u0430\u0433", "\u043a\u0431\u0442\u0443\u043c\u0430\u0433")
_NAMES = "(" + ", ".join(f"'{x}'" for x in (*LANYARDS, *LANYARD_NAMES)) + ")"
SKINNED = (f"o.status = 'active' AND (o.slug IN {_LIST} OR o.kind != 'school' AND "
           f"lower(replace(replace(replace(replace(o.name, '.', ''), ' ', ''), '-', ''), '_', '')) IN {_NAMES})")


# the schools' lanyards (their official shields and colours): each its own students' alone, by students.school,
# with no joining; web: awards.ts SCHOOL_LOOKS
SCHOOL_LANYARDS = ("site", "seogi", "geology", "business", "ise", "kma", "law", "sam", "sce", "smsgt", "sss")
# how prod's students.school writes a school beyond schools.json's names (the portal's older abbreviations)
_SCHOOL_ALIAS = {"\u0448\u044d\u0438\u043d\u0433\u0438": "seogi"}  # ShEiNGI


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("\u0451", "\u0435").split())


def school_slug(school: str | None) -> str | None:
    """The school org's slug a student's school is, as the portal or Settings wrote it: its full name or abbreviation in
    any of the three languages (schools.json), its own slug or short name; None for none or not a KBTU school ("DIT")."""
    from .clubs import SCHOOLS  # the schools' names: clubs imports this module
    k = _norm(school or "")
    if not k:
        return None
    for s in SCHOOLS:
        names = {s["slug"], s["short"], *(s[lang][f] for lang in ("ru", "kk", "en") for f in ("name", "abbr") if s[lang].get(f))}
        if k in {_norm(n) for n in names}:
            return s["slug"]
    return _SCHOOL_ALIAS.get(k)


def _my_school_org(con, uid: int) -> int | None:
    """My school's org, when it has a lanyard (school_slug of students.school)."""
    s = one(con, "SELECT school FROM students WHERE user_id = ?", uid)
    slug = school_slug(s["school"] if s else None)
    if slug not in SCHOOL_LANYARDS:
        return None
    o = one(con, "SELECT id FROM orgs WHERE kind = 'school' AND status = 'active' AND slug = ?", slug)
    return o[0] if o else None


def _skin(con, uid: int) -> int | str | None:
    """The badge I show (badges as skins): a club's id, "sower" (the creator's own), None for KBTU's.
    My pick holds; a club picked holds while I'm in it. Never picked (or that club left): the creator's own for the
    creator; else the club I joined that has a badge (of several, where my role is highest, then the newest); else my
    school's; else KBTU's. A new club's badge or a school set comes by itself."""
    u = one(con, "SELECT skin_pick, skin_org, skin_look, is_founder FROM users WHERE id = ?", uid)
    if u["skin_pick"] == "kbtu":
        return None
    if u["is_founder"] and u["skin_pick"] in ("sower", None):
        return creator_look(u)
    if u["skin_pick"] == "org" and _skin_ok(con, uid, u["skin_org"]):
        return u["skin_org"]
    r = one(con, f"""SELECT o.id FROM org_members m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = ? AND {SKINNED}
        ORDER BY CASE m.role WHEN 'president' THEN 4 WHEN 'vice' THEN 3 WHEN 'head' THEN 2 ELSE 1 END DESC, m.joined_at DESC LIMIT 1""", uid)
    if r:
        return r[0]
    # no club with a lanyard: my school's, once I have a school (KBTU's -> my school's -> my club's -> special)
    s = one(con, "SELECT school FROM students WHERE user_id = ?", uid)
    slug = school_slug(s["school"]) if s else None
    o = slug and one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", slug)
    return o[0] if o else None


def creator_look(u) -> str:
    """The creator's own lanyard: an archived look he picked (`skin_look`, read only for him), else SOWER."""
    return u["skin_look"] if u["skin_look"] in ARCHIVE else "sower"


def _one_off(w: str, ref: set[str]) -> bool:
    """`w` is one of `ref`, or of 4+ letters and one letter added, dropped or changed from one of them."""
    if w in ref:
        return True
    for r in ref:
        if len(w) >= 4 and len(r) >= 4 and abs(len(w) - len(r)) <= 1:
            a, b = (w, r) if len(w) >= len(r) else (r, w)
            if len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1:
                return True
            if len(a) == len(b) + 1 and any(a[:i] + a[i + 1:] == b for i in range(len(a))):
                return True
    return False


def _skin_ok(con, uid: int, oid: int):
    """A club's lanyard is its members' alone, a school's its students' alone;
    read on every look, so a pick of a club I'm not in (or left), or of a school no longer mine, falls back by itself
    (`_skin`). The creator wears any."""
    if one(con, "SELECT 1 FROM users WHERE id = ? AND is_founder = 1", uid):
        return bool(one(con, f"SELECT 1 FROM orgs o WHERE o.id = ? AND ({SKINNED} OR o.status = 'active' AND o.kind = 'school' AND o.slug IN ("
                        + ", ".join(f"'{x}'" for x in SCHOOL_LANYARDS) + "))", oid))
    return bool(one(con, f"SELECT 1 FROM orgs o JOIN org_members m ON m.org_id = o.id AND m.user_id = ? WHERE o.id = ? AND {SKINNED}",
                    uid, oid)) or (oid is not None and oid == _my_school_org(con, uid))


def _qr_code(con, uid: int, col: str = "qr_code") -> str:
    """The secret half of my badge QR (§4.4), or with "link_code" my links' code (r_, ev_: posted in chats, so never the
    badge's): made on first use, random like a ticket code."""
    assert col in ("qr_code", "link_code")
    code = one(con, f"SELECT {col} FROM users WHERE id = ?", uid)[col]
    if not code:
        con.execute(f"UPDATE users SET {col} = ? WHERE id = ? AND {col} IS NULL",
                    ("".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(10)), uid))
        code = one(con, f"SELECT {col} FROM users WHERE id = ?", uid)[col]
    return code


FIXABLE = {"studentId": "student_id", "lastName": "last_name", "firstName": "first_name", "middleName": "middle_name",
           "lastLat": "last_lat", "firstLat": "first_lat", "middleLat": "middle_lat"}
# a city typed in: letters (Kazakh's too), spaces, hyphens, a slash for "Taraz/Sarykemer"; the picker offers the big ones
CITY_RE = re.compile(r"[A-Za-z\u0400-\u04ff][A-Za-z\u0400-\u04ff ./-]{1,39}")
ONCE = {**FIXABLE, "course": "course", "school": "school"}  # what My data lists as still mine to correct once (update_me)


class _Taken(ApiError):
    """sid_taken, with the ID and its holder for the admins (update_me); never in the reply, which carries `extra`."""
    def __init__(self, sid: str, holder: int | None):
        super().__init__("conflict", "sid_taken")
        self.sid, self.holder = sid, holder


def sid_tries(con, uid: int) -> int:
    """Student IDs tried on this account in a day, from Settings or a schedule page (bot_dm._page_sid): one count of 5, or
    "taken" would tell anyone which IDs are registered. Read it and add to it under one write lock."""
    return one(con, """SELECT COUNT(*) FROM audit_log WHERE target = ? AND at > ? AND (action IN ('sid_try', 'sid_page_taken', 'sid_page_year', 'sid_page_fixed')
        OR action = 'identity_fix' AND json_extract(data, '$.field') = 'student_id')""", f"user:{uid}", core.now() - 86400)[0]


def fix_identity(con, uid: int, col: str, raw: object, admin: bool = False) -> None:
    """Settings → My data: a student corrects their student ID or a name once each (it came in wrong: a classmate's ID
    from the freshmen list, a typo at sign-up, the name in another script); the Latin name the same way, Latin letters
    only, and an empty one filled doesn't spend the once (no displayName to read it from); after that only support, the admin
    (`kbtu.admin fix`: no once, no year rule, no tolerance). The email is never changed: it is the KBTU Microsoft login
    (ms_link writes it from the token), what ties this row to a real person."""
    from .. import roster  # imports logic: here, not at the top
    v = " ".join(str(raw or "").split())
    if col == "student_id":
        v = v.replace(" ", "").upper()
        course = core.course_of(v)
        if not STUDENT_ID.fullmatch(v) or not isinstance(course, int) or not 1 <= course <= 6:
            raise ApiError("bad_input")
    elif col in LAT_COLS:  # Latin letters only: what goes to the university's lists in Latin
        if v and not LATIN_NAME.fullmatch(v) or not v and col != "middle_lat":
            raise ApiError("bad_input")
    elif v and not NAME.fullmatch(v) or not v and col != "middle_name":
        raise ApiError("bad_input")
    v = v or None
    # the row and its once read under the write lock (BEGIN IMMEDIATE): two taps at once can't both spend it
    with tx(con):
        s = one(con, "SELECT * FROM students WHERE user_id = ?", uid)
        if not s or not admin and (s["manual"] or core.is_staff(s)):
            raise ApiError("forbidden")  # unconfirmed: Microsoft's names come first; staff: the ID is a placeholder
        if not admin and col in s["fixed"].split(","):
            raise ApiError("conflict", "fixed")
        if v == s[col]:
            return  # nothing changes: the once isn't spent
        # only year 1 earns anything (free seats, first_year_free): an ID that would make me a 1st-year bachelor when I'm
        # not one is support's; any other year, earlier or later, is mine to correct once.
        # ponytail: deleting the account and joining again starts a fresh row (no year rule at sign-up, `fixed` empty):
        # a senior can come back a week later with a 1st-year's ID; MS_AGE_CUTOFF on closes it
        sid_moves = col == "student_id" and re.sub(r"\d+$", "", s["student_id"]) != re.sub(r"\d+$", "", v)
        if sid_moves and not admin and course == 1 and v[2] == "B" and not (s["course"] == 1 and s["student_id"][2:3] == "B"):
            raise ApiError("bad_input", "sid_year")
        if col == "student_id" and not admin and sid_tries(con, uid) >= 5:  # every ID tried counts, taken or not
            raise ApiError("rate_limited", "sid_tries")
        if col in ("first_name", "last_name", "first_lat", "last_lat") and not admin:
            # first and last stay KBTU's (Microsoft's) name, in another spelling at most (Latin/Cyrillic, -ayev/-aev):
            # two of its words kept and none added, or one could rename into someone else ("Serikbayev Aidos" then
            # first "Bekzat") or a title, and fool every organizer's list, the door and the club rosters
            ms = json.loads(s["ms_profile"] or "{}")
            ref = (ms.get("givenName") or s["first_name"], ms.get("surname") or s["last_name"])
            # the Latin pair: the other half's Latin, else its Cyrillic (_words reads both scripts as one)
            new = " ".join(v if c == col else s[c] or s[c[:-4] + "_name"] for c in (("first_lat", "last_lat") if col in LAT_COLS else ("first_name", "last_name")))
            # a word of 4+ letters one letter off KBTU's own is the same word (Ameli/Amelie, Aidos/Aydos)
            if not roster.same_person(new, *ref) or not all(_one_off(w, roster._words(" ".join(ref))) for w in roster._words(new)):
                raise ApiError("bad_input", "name_far")
        # an ID is free when no student has it and no list keeps it for another mail: the freshmen list (that student's
        # sign-up form would offer it) or a check-in's expected list (its CSV matches by ID: an absent friend would
        # show as "came")
        mail = (s["email"] or "").lower()
        held = col == "student_id" and (one(con, "SELECT user_id FROM students WHERE student_id = ? AND user_id != ?", v, uid)
                                        or one(con, "SELECT NULL FROM prefill WHERE student_id = ? AND email != ?", v, mail)
                                        or one(con, "SELECT NULL FROM qr_expected WHERE upper(student_id) = ? AND email != ?", v, mail))
        if held:
            raise _Taken(v, held[0])  # the once isn't spent; update_me counts the try and asks the holder (id_clash)
        con.execute(f"UPDATE students SET {col} = ?, fixed = ? WHERE user_id = ?",
                    (v, s["fixed"] if admin or col in LAT_COLS and s[col] is None  # an empty Latin one filled: not spent
                     else ",".join(filter(None, [*s["fixed"].split(","), col])), uid))
        # the course follows the year and degree letter only: a typo in the number keeps the stored one (a repeater's)
        if sid_moves:
            con.execute("UPDATE students SET course = ?, course_year = ? WHERE user_id = ?", (course, core.academic_year(), uid))
        log_action(con, None if admin else uid, "identity_fix", f"user:{uid}", json.dumps({"field": col, "old": s[col], "new": v}, ensure_ascii=False))


def _spend(con, uid: int, s, col: str, val) -> None:
    """Course and school: corrected once, then support (`kbtu.admin fix <user> reset`); an empty one filled is free.
    The school before the once is kept: going back to it is free, once (a mis-tap undone), and it stays spent."""
    was = json.loads(s["once_was"] or "{}")
    if s[col] is None:  # an empty one filled: free, even after the once (a school cleared before clearing was refused)
        return
    if col in s["fixed"].split(","):
        if col not in was or was[col] != val:
            raise ApiError("conflict", "fixed")
        del was[col]  # the undo used: no flipping back and forth
        con.execute("UPDATE students SET once_was = ? WHERE user_id = ?", (json.dumps(was, ensure_ascii=False), uid))
    elif s[col] is not None:  # the school's undo alone: a course back down would be the free-seat trick
        con.execute("UPDATE students SET fixed = ?, once_was = ? WHERE user_id = ?",
                    (",".join(filter(None, [*s["fixed"].split(","), col])), json.dumps({**was, col: s[col]} if col == "school" else was, ensure_ascii=False), uid))


def update_me(con, v: Viewer, patch: dict) -> dict:
    """Settings' save, all or nothing: one transaction, so a refused field leaves the others unsaved."""
    err = None
    held = lambda: con.execute("SELECT student_id FROM students WHERE user_id = ?", (v.id,)).fetchall()  # noqa: E731
    with tx(con):
        was = held()
        con.execute("SAVEPOINT patch")
        try:
            _update_me(con, v, patch)
        except _Taken as e:  # undone, yet the try counts under the same lock (sid_tries) and the admins hear, as at sign-up
            con.execute("ROLLBACK TO patch")
            log_action(con, v.id, "sid_try", f"user:{v.id}")
            if e.holder:
                id_clash(con, e.sid, v.id, e.holder)
            err = e
        except ApiError as e:  # a free ID found, then another field refused: undone, and that look-up counts as well
            looked = [tuple(r) for r in held()] != [tuple(r) for r in was]
            con.execute("ROLLBACK TO patch")
            if looked:
                log_action(con, v.id, "sid_try", f"user:{v.id}")
            err = e
        con.execute("RELEASE patch")
    if err:
        raise err
    return me(con, v)


def _update_me(con, v: Viewer, patch: dict) -> None:
    sets: dict[str, object] = {}
    for k, col in SETTINGS.items():
        if k not in patch:
            continue
        if k in notifications.CATEGORIES:
            notifications.set_preference(con, v.id, k, bool(patch[k]))
            continue
        val = patch[k]
        if k == "lang" and val not in ("ru", "kk", "en") or k == "theme" and val not in ("light", "dark", None):
            raise ApiError("bad_input")
        sets[col] = val if k in ("lang", "theme") else int(bool(val))
    if "bio" in patch or "showcase" in patch or "nick" in patch:
        need_student(v)
    if "suggestMe" in patch:  # People you may know: my yes to its text, or gone both ways (logic/pymk.py)
        need_student(v)
        if not isinstance(patch["suggestMe"], bool):  # a consent: an explicit yes only
            raise ApiError("bad_input")
        pymk.switch(con, v.id, patch["suggestMe"])
    if "nick" in patch:
        sets["nick"] = clean_nick(patch["nick"])
    if "skin" in patch:  # my pick: a club with a lanyard (`_skin_ok`), "sower" or an archived look for the creator, null = the KBTU one (`_skin`)
        need_student(v)
        val = patch["skin"]
        founder = one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)[0]
        if val is None:
            sets.update(skin_pick="kbtu", skin_org=None, skin_look=None)
        elif val == "sower" and founder:
            sets.update(skin_pick="sower", skin_org=None, skin_look=None)
        elif val in ARCHIVE and founder:  # an archived look: anyone tries it on in the picker, the creator alone wears it
            sets.update(skin_pick="sower", skin_org=None, skin_look=val)
        elif type(val) is int and _skin_ok(con, v.id, val):
            sets.update(skin_pick="org", skin_org=val, skin_look=None)
        else:
            raise ApiError("bad_input")
    if "frame" in patch:  # a frame over my photo (FRAMES), null for none; combined with any lanyard
        need_student(v)
        if patch["frame"] is not None and patch["frame"] not in FRAMES:
            raise ApiError("bad_input")
        sets["frame"] = patch["frame"]
    if "avatarTg" in patch:  # off only with a photo of my own to show (the upload turns it off by itself)
        if not patch["avatarTg"] and not one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]:
            raise ApiError("bad_input")
        sets["avatar_tg"] = int(bool(patch["avatarTg"]))
    if "bio" in patch:
        sets["bio"] = str(patch["bio"])[:150]
    if "showcase" in patch:  # up to 6 keys: achievement codes and badges as b<event id>, in the order picked (§4.11)
        codes = {a[0] for a in ACHIEVEMENTS} - {"activist"}
        keys = [k for k in (patch["showcase"] if isinstance(patch["showcase"], list) else [])
                if isinstance(k, str) and (k in codes or re.fullmatch(r"b\d{1,9}", k))]
        sets["showcase"] = ",".join(list(dict.fromkeys(keys))[:6])
    if "phone" in patch:  # my kept phone (Settings → My data): changed, or null deletes it
        need_student(v)
        phone = None if patch["phone"] is None else kz_phone(patch["phone"])
        if patch["phone"] is not None and not phone:
            raise ApiError("bad_input")
        con.execute("UPDATE students SET phone = ? WHERE user_id = ?", (phone, v.id))
    if "school" in patch:  # Settings: mine over the list's (_from_list can be wrong): a KBTU school's name as the app keeps it, or none
        need_student(v)
        val = patch["school"]
        s = one(con, "SELECT school, fixed, once_was FROM students WHERE user_id = ?", v.id)
        o = val is not None and one(con, "SELECT name FROM orgs WHERE kind = 'school' AND status = 'active' AND name = ?", val if type(val) is str else None)
        back = "school" in s["fixed"].split(",") and json.loads(s["once_was"] or "{}").get("school", 0) == val  # as the portal wrote it
        if val is not None and not o and not back:
            raise ApiError("bad_input")
        new = o[0] if o else val if back else None
        if new is None and s["school"] is not None:  # no clearing: cleared by mistake, the once would go with it
            raise ApiError("bad_input")
        # once, as the ID (switched and back: another school's lanyard, chats and CSV lines);
        # filling an empty one is free. The lanyard reads the school live: it follows by itself
        if new != s["school"]:
            _spend(con, v.id, s, "school", new)
            con.execute("UPDATE students SET school = ? WHERE user_id = ?", (new, v.id))
    if "course" in patch:  # Settings → My data: a transfer's new ID says a year too low; up from the ID's year only, never
        need_student(v)  # below it (a lower one would take free 1st-year seats). course_year now: September moves it on
        s = one(con, "SELECT student_id, consent_version, course, fixed, once_was FROM students WHERE user_id = ?", v.id)
        lo, val = core.course_of(s["student_id"]), patch["course"]
        if core.is_staff(s):
            raise ApiError("forbidden")  # the ID is a placeholder
        if lo is None or type(val) is not int or not lo <= val <= 6:
            raise ApiError("bad_input")
        if val != s["course"]:  # once (else 2 to pass volunteers_senior, then 1 for a free seat); September's isn't one
            _spend(con, v.id, s, "course", val)
        con.execute("UPDATE students SET course = ?, course_year = ? WHERE user_id = ?", (val, core.academic_year(), v.id))
    for k, col in FIXABLE.items():  # once each (fix_identity); the email isn't here: it's the Microsoft login
        if k in patch:
            need_student(v)
            fix_identity(con, v.id, col, patch[k])
    if "city" in patch:  # Settings → Privacy also covers data supplied by a club roster.
        city = patch["city"]
        if city is not None and (not isinstance(city, str) or not CITY_RE.fullmatch(city := " ".join(city.split()))):
            raise ApiError("bad_input")
        sets["city"] = city
    if "notifyVia" in patch:  # one channel for my notifications (push.py): the app's push or Telegram's bot
        if patch["notifyVia"] not in ("app", "telegram"):
            raise ApiError("bad_input")
        sets["notify_via"] = patch["notifyVia"]
    if "cityHidden" in patch:  # off my profile, kept for me
        if not isinstance(patch["cityHidden"], bool):
            raise ApiError("bad_input")
        sets["city_hidden"] = int(patch["cityHidden"])
    if sets:
        con.execute(f"UPDATE users SET {', '.join(c + ' = ?' for c in sets)} WHERE id = ?", (*sets.values(), v.id))


def _drop_photo(con, fid: int | None) -> list[str]:
    """A photo of mine nobody shows any more: its row goes, and its files on disk (returned) unless another row has
    the same picture (files are named by their content)."""
    f = one(con, "SELECT id, path, kind FROM files WHERE id = ?", fid) if fid else None
    if not f:
        return []
    con.execute("DELETE FROM files WHERE id = ?", (f["id"],))
    # its reports go with it: the next file may get this id (a plain INTEGER PRIMARY KEY), and must not inherit them
    con.execute("DELETE FROM reports WHERE target = 'photo' AND target_id = ?", (f["id"],))
    # Private receipts and public photos live in different directories, even with the same digest.
    return [] if one(con, "SELECT 1 FROM files WHERE path = ? AND (kind = 'receipt') = ?", f["path"], f["kind"] == "receipt") else [f["path"]]


_FILE_REFS = (("users", "avatar_file_id"), ("orgs", "logo_file_id"), ("events", "cover_file_id"),
              ("donations", "file_id"), ("receipts", "file_id"), ("event_photos", "file_id"), ("posts", "photo_file_id"),
              ("event_slides", "file_id"), ("takedowns", "file_id"), ("gallery_photos", "file_id"), ("event_covers", "file_id"))
_FILE_USED = " UNION ALL ".join(f"SELECT 1 FROM {table} WHERE {col} = {{fid}}" for table, col in _FILE_REFS)
UNUSED_COVERS = 20  # room for an editor's unsaved cover and slides


def _drop_unused(con, fid: int | None) -> list[str]:
    """_drop_photo for a file nothing shows any more."""
    if fid and con.execute(_FILE_USED.format(fid=":f"), {"f": fid}).fetchone():
        return []
    return _drop_photo(con, fid)


def trim_covers(con, uid: int, keep: int) -> list[str]:
    """After a cover upload, retire only the oldest unreferenced uploads, preserving the one just requested."""
    used = _FILE_USED.format(fid="f.id")
    stale = rows(con, f"""SELECT f.id FROM files f WHERE f.owner_id = ? AND f.kind = 'event_cover'
        AND NOT EXISTS ({used}) ORDER BY f.id = ? DESC, f.id DESC LIMIT -1 OFFSET ?""", uid, keep, UNUSED_COVERS)
    return [p for row in stale for p in _drop_photo(con, row[0]) if chatlist.photo_free(con, p)]


def set_photo(con, v: Viewer, saved: dict) -> list[str]:
    """My own photo (a processed upload, media.save) instead of Telegram's: the "Photo from Telegram" switch goes off
   . The one it replaces is deleted; returns its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    f = one(con, "SELECT id FROM files WHERE sha256 = ? AND kind = 'avatar' AND owner_id = ?", saved["sha256"], v.id)
    fid = f["id"] if f else con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
        VALUES (?, 'avatar', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (saved["sha256"], saved["bytes"], saved["width"], saved["height"],
                                                                saved["path"], v.id, core.now(), saved["color"])).lastrowid
    con.execute("UPDATE users SET avatar_file_id = ?, avatar_tg = 0 WHERE id = ?", (fid, v.id))
    return _drop_unused(con, old) if old and old != fid else []  # a take-down's undo may still hold it


def drop_my_photo(con, v: Viewer) -> list[str]:
    """My own photo deleted (the upload shouldn't stay on the server): Telegram's is back; returns
    its files to remove from disk."""
    need_student(v)
    old = one(con, "SELECT avatar_file_id FROM users WHERE id = ?", v.id)[0]
    con.execute("UPDATE users SET avatar_file_id = NULL, avatar_tg = 1 WHERE id = ?", (v.id,))
    return _drop_unused(con, old) if old else []  # a take-down's undo may still hold it


DELETE_WAIT = 7 * 86400


def _paid_ahead(con, uid: int) -> bool:
    """A ticket paid for (a receipt sent or accepted) to an event still ahead: the deletion waits until it passes, so
    the money's only record isn't erased before the door."""
    return one(con, """SELECT 1 FROM registrations r JOIN events e ON e.id = r.event_id JOIN receipts c ON c.registration_id = r.id
        WHERE r.user_id = ? AND r.status IN ('going', 'hold') AND c.status != 'rejected' AND COALESCE(e.ends_at, e.starts_at + ?) > ?""",
               uid, NO_END, core.now()) is not None


def _may_delete(con, v: Viewer) -> None:
    """A student's account, or one an Apple sign-in made or reaches (App Store 5.1.1(v): an account the app creates can
    be deleted in it), or a Telegram-only donor's (their linked payment data must be erasable too); any other Telegram
    guest has nothing of an account to delete."""
    if not v.student and not one(con, """SELECT 1 FROM identities WHERE user_id = ? UNION ALL SELECT 1 FROM donations WHERE user_id = ?
                                         UNION ALL SELECT 1 FROM sponsor_consents WHERE user_id = ?""", v.id, v.id, v.id):
        need_student(v)


def ask_delete(con, v: Viewer, photos: bool = False) -> dict:
    """"Delete my account" (§4.8) waits a week, then `delete_due` runs it (a change of heart, or someone
    holding my phone, shouldn't cost the awards; asking the KBTU password would shut out whoever no longer has it).
    The bot says so at once, with the way back; nothing is hidden meanwhile. `photos`: the album photos I added go
    too (by default they stay, without my name). A President's club passes on at the deletion (delete_due)."""
    _may_delete(con, v)
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
    _may_delete(con, v)
    return {"photos": one(con, "SELECT COUNT(*) FROM event_photos WHERE added_by = ?", v.id)[0], "paid": _paid_ahead(con, v.id)}


CONSENT = "2026-11-unified1"  # web/src/lib/legal.ts says the same. One policy by data categories, one version, whatever the flags;
# a new category of personal data asks its own consent inside its feature (appeals.CONSENT), never a suffix here


def ai_on(cfg) -> bool:
    """A feature that sends students' texts to the AI providers of the policy's section 9 is open to everyone."""
    return cfg.forum or cfg.board == "all" or bool(cfg.tgc_chat) or bool(cfg.forum_channel)


CONSENT_VOL = "+vol1"  # with VOLUNTEERS: the ledger's part of the policy, agreed to only by the people it concerns (logic/vol.py concerned)


def on_policy(version: object, current: str) -> bool:
    """A consent to the policy in force: with or without the volunteers ledger's section, which only some are asked."""
    return version in (current, current + CONSENT_VOL)


def agreed(s) -> bool:
    """This student row is on the policy in force (or an admin's own row)."""
    return bool(s) and (on_policy(s["consent_version"], CONSENT) or s["consent_version"] == "admin")


def consent(con, v: Viewer, version: object, current: str = CONSENT) -> dict:
    """The privacy policy changed: a student agrees again once; staff and students
    added by hand keep their marks."""
    need_student(v)
    if version != current:
        raise ApiError("bad_input")
    con.execute("UPDATE students SET consent_version = ?, consent_at = ? WHERE user_id = ? AND consent_version NOT IN ('staff', 'admin')",
                (version, core.now(), v.id))
    chatsync.check_later(con, v.id)  # agreed: a club chat they're in already counts now
    return me(con, v)


def dm_on(con, v: Viewer, eid: object) -> dict:
    """Telegram's "allow messages" said yes inside the app: the bot may write from now on, not from the next launch
    (the launch data said no). The event just signed up for gets its confirmation with the ticket. A
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
    club with nobody else to the admin (deleting it would erase other people's events and photos)."""
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
        joined(con, oid, new)
        log_action(con, None, "president_handover", f"org:{oid}")
        notify(con, new, "club_handover", f"ho:{oid}")


def delete_due(con) -> tuple[list[str], list[str]]:
    """The accounts whose week ran out, deleted; their files to remove from disk, as delete_me's. One that fails is
    logged and tried again next round; the rest go on."""
    gone: tuple[list[str], list[str]] = ([], [])
    for (uid,) in rows(con, "SELECT id FROM users WHERE delete_at <= ?", core.now()):
        try:
            with tx(con):
                u = one(con, "SELECT role FROM users WHERE id = ? AND delete_at <= ?", uid, core.now())
                if not u or _paid_ahead(con, uid):
                    continue
                photos_too = one(con, "SELECT 1 FROM meta WHERE key = ?", f"delphotos:{uid}") is not None
                dmp = dmp_listed(con, uid)  # a copy from before the first open holds the grant with no account
                receipts, photos = delete_me(con, Viewer(uid, u["role"], True))
                # The journal must survive a crash before SQLite can commit the matching checkpoint.
                _deletion_log(con, uid, photos_too, dmp_ids(dmp) if dmp else [])
        except Exception:
            log.exception("deleting account %s failed", uid)
            continue
        gone[0].extend(receipts)
        gone[1].extend(photos)
    return gone


def drain_deleted_files(con) -> None:
    """Retry committed account erasures, including a crash before the caller could unlink their files."""
    home = _journal(con).parent
    with tx(con):  # a new reference cannot appear between the check and unlink
        for (key,) in rows(con, "SELECT key FROM meta WHERE key GLOB 'del-file:*'"):
            _, folder, path = key.split(":", 2)
            free = not one(con, "SELECT 1 FROM files WHERE path = ? AND kind = 'receipt'", path) if folder == "receipts" else chatlist.photo_free(con, path)
            if free:
                media.drop(home / folder, [path])
            con.execute("DELETE FROM meta WHERE key = ?", (key,))


DELETION_LOG_DAYS = 40  # longer than any copy lives (R2 ~30 days): an older line can't be needed


def _journal(con) -> Path:
    return Path(one(con, "SELECT file FROM pragma_database_list WHERE name = 'main'")[0]).with_name("deletions.log")


def _durable_text(path: Path, value: str) -> None:
    """The SQLite writer lock serializes writers. Backups can read either complete file during replacement."""
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        f.write(value)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _salt(path: Path) -> str:
    salt = path.with_suffix(".salt")
    if not salt.exists():
        if path.exists():
            raise RuntimeError("restore deletions.salt beside deletions.log before starting")
        _durable_text(salt, secrets.token_hex(16))
    value = salt.read_text().strip()
    if not re.fullmatch("[a-f0-9]{32}", value):
        raise RuntimeError("invalid deletions.salt")
    return value


def _deletion_hash(salt: str, identity: str) -> str:
    return hashlib.sha256(f"{salt}:{identity}".encode()).hexdigest()[:32]


def _deletion_log(con, uid: int, photos: bool = False, dmp: list[str] | tuple = (), *, reports: bool = False) -> None:
    path = _journal(con)
    if not path.exists() and one(con, "SELECT 1 FROM meta WHERE key GLOB 'delreplay:*'"):
        raise RuntimeError("restore deletions.log before deleting accounts")
    salt = _salt(path)
    created = one(con, "SELECT created_at FROM users WHERE id = ?", uid)[0]
    # Moving an account swaps its Telegram identity but preserves the database row.
    kind = "reports" if reports else "user"
    day = core.now() // 86400 * 86400
    scope = " reports" if reports else " photos" if photos else ""
    tag = hashlib.sha256(salt.encode()).hexdigest()[:16]
    lines = []  # the account's own record, then its DMP grant's (dmp_ids), each with its own generation
    for h, sc in [(_deletion_hash(salt, f"{kind}:{uid}:{created}"), scope), *((_deletion_hash(salt, x), " dmp") for x in dmp)]:
        previous = one(con, "SELECT value FROM meta WHERE key = ?", f"delreplay:{h}")
        # The first new-format generation follows any day-only record. Two deletions in a day still differ.
        lines.append((h, sc, max(day + 1, int(previous[0]) + 1 if previous else 0)))
    old = path.read_text() if path.exists() else ""
    _durable_text(path, old + "".join(f"{day} {h}{sc} v2:{g}:{tag}\n" for h, sc, g in lines))
    con.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", ((f"delreplay:{h}", str(g)) for h, _, g in lines))


def _prune_deletion_log(con) -> None:
    with tx(con):
        path = _journal(con)
        if not path.exists():
            return
        lines = path.read_text().splitlines()
        cutoff = core.now() - DELETION_LOG_DAYS * 86400
        keep = [ln for ln in lines if ln.split()[:1] and ln.split()[0].isdigit() and int(ln.split()[0]) > cutoff]
        if len(keep) != len(lines):
            _durable_text(path, "".join(ln + "\n" for ln in keep))
        con.execute("DELETE FROM meta WHERE key GLOB 'delreplay:*' AND CAST(value AS INTEGER) < ?", (cutoff,))


def replay_deletions(con) -> tuple[int, int]:
    """Replay the journal before serving a snapshot. Each snapshot remembers the erasures it already applied."""
    path = _journal(con)
    with tx(con):
        drain_deleted_files(con)
        applied = {key.removeprefix("delreplay:"): int(value) for key, value in
                   rows(con, "SELECT key, value FROM meta WHERE key GLOB 'delreplay:*'")}
        if not path.exists():
            if applied:
                raise RuntimeError("restore deletions.log beside the database before starting")
            return 0, 0
        salt = _salt(path)
        records = {}
        latest = {}
        salt_tag = hashlib.sha256(salt.encode()).hexdigest()[:16]
        for line in path.read_text().splitlines():
            m = re.fullmatch(r"([0-9]+) ([0-9a-f]{32})(?: (photos|reports|dmp))?(?: v2:([0-9]+):([0-9a-f]{16}))?", line)
            if not m:
                raise RuntimeError("invalid deletions.log record")
            day, h, scope, version, tag = m.groups()
            if scope in ("reports", "dmp") and version is None:
                raise RuntimeError("invalid report withdrawal in deletions.log")
            if tag and tag != salt_tag:
                raise RuntimeError("deletions.salt does not match deletions.log")
            generation = int(version or day)
            latest[h] = max(generation, latest.get(h, -1))
            if generation > applied.get(h, -1):
                records.setdefault(h, []).append((generation, scope or "", version is None))
        cutoff = core.now() - DELETION_LOG_DAYS * 86400
        if any(g // 86400 * 86400 > cutoff and g > latest.get(h, -1) for h, g in applied.items()):
            raise RuntimeError("restore the latest deletions.log before starting")
        if not records:
            return 0, len(latest)
        files = []
        from . import evreports
        for u in rows(con, """SELECT u.id, u.tg_id, u.created_at, u.role, s.verified_at FROM users u
                LEFT JOIN students s ON s.user_id = u.id WHERE u.tg_id > 0"""):
            reports_key = _deletion_hash(salt, f"reports:{u['id']}:{u['created_at']}")
            if any(scope == "reports" for _, scope, _ in records.get(reports_key, [])):
                evreports.erase(con, u["id"])
            # Both journal formats may refer to this row. Apply its earliest outstanding erasure once.
            legacy_key = _deletion_hash(salt, str(u["tg_id"]))
            row_key = _deletion_hash(salt, f"user:{u['id']}:{u['created_at']}")
            for generation, scope, legacy in sorted(records.get(legacy_key, []) + records.get(row_key, [])):
                if scope in ("reports", "dmp"):
                    continue
                if legacy:
                    verified = u["verified_at"]
                    if verified is None or verified >= generation + 86400:
                        continue
                    if verified >= generation:
                        raise RuntimeError("same-day verification in a legacy deletion record; reconcile the snapshot before starting")
                # Use the photo choice for the incarnation present in the snapshot.
                con.execute("DELETE FROM meta WHERE key = ?", (f"delphotos:{u['id']}",))
                if scope == "photos":
                    con.execute("INSERT INTO meta (key, value) VALUES (?, '1')", (f"delphotos:{u['id']}",))
                files.append(delete_me(con, Viewer(u["id"], u["role"], True)))
                break
        # an erased person's DMP grant, also in a copy from before their first open (no account in it to match)
        for d in rows(con, "SELECT * FROM dmp_list"):
            if any(scope == "dmp" for x in dmp_ids(d) for _, scope, _ in records.get(_deletion_hash(salt, x), [])):
                con.execute("DELETE FROM dmp_list WHERE id = ?", (d["id"],))
        con.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                        ((f"delreplay:{h}", str(latest[h])) for h in records))
        # All account decisions and SQL succeeded. An unlink failure rolls the checkpoints back for retry.
        drain_deleted_files(con)
        return len(files), len(latest)


# Every column that points at a person (the foreign keys to users, read from the schema at each deletion) is in one
# of these, or deleting an account refuses to run: a new table can't keep someone by being forgotten
# (tests/test_core.py checks the lists cover the schema). The nullable rest just lose the link.
_DEL_KEEP = {("org_bans", "user_id")}  # a club's ban stays on the Telegram account
_DEL_GONE = {
    ("donations", "user_id"), ("sponsor_consents", "user_id"),
    ("fchan_feed_pages", "user_id"), ("broadcast_votes", "user_id"), ("user_platforms", "user_id"), ("android_app", "user_id"),
    ("web_sessions", "user_id"),
    ("identities", "user_id"), ("push_devices", "user_id"),  # my Apple sign-in and my iPhones' push tokens (logic/apple.py)
    ("students", "user_id"), ("staff_ok", "user_id"), ("santa_people", "user_id"), ("santa_msgs", "giver_id"), ("santa_msgs", "to_id"), ("santa_sends", "user_id"), ("schedule_classes", "user_id"), ("org_members", "user_id"), ("join_requests", "user_id"),
    ("club_applications", "user_id"), ("subscriptions", "user_id"), ("registrations", "user_id"), ("saved_events", "user_id"),
    ("post_reactions", "user_id"), ("post_reads", "user_id"), ("achievement_grants", "user_id"),
    ("achievement_levels", "user_id"), ("chat_opens", "user_id"), ("chat_waits", "user_id"), ("bot_outbox", "user_id"), ("event_ratings", "user_id"), ("roster_toasts", "user_id"),
    ("member_tags", "user_id"), ("removal_requests", "user_id"), ("comment_reads", "user_id"), ("visits", "user_id"),
    ("volunteers", "user_id"), ("qr_marks", "user_id"), ("round_apps", "user_id"), ("round_votes", "user_id"), ("comments", "user_id"),
    ("friendships", "a"), ("friendships", "b"), ("friend_requests", "from_id"), ("friend_requests", "to_id"),
    ("friend_invites", "from_id"), ("friend_invites", "to_id"), ("grant_links", "created_by"), ("door_guests", "user_id"), ("door_misses", "user_id"),
    ("takedowns", "user_id"), ("user_skills", "user_id"), ("asks", "user_id"), ("contacts", "from_id"), ("contacts", "to_id"),
    ("blocks", "user_id"), ("blocks", "blocked_id"), ("ask_pings", "user_id"),
    ("thread_replies", "user_id"), ("thread_joins", "user_id"), ("threads", "user_id"), ("assist_uses", "user_id"),  # the forum: mine go (a thread with its replies)
    ("appeal_authors", "user_id"), ("appeal_sends", "user_id"), ("appeal_consents", "user_id"), ("appeal_staff", "user_id"), ("help_staff", "user_id"), ("help_consents", "user_id"),  # my appeals go first (delete_me)
    ("tgc_comments", "author_id"), ("tgc_reports", "reporter_id"), ("tgc_closed", "user_id"),  # the channel's comments: copies of mine, my reports
    ("chat_asks", "user_id"),  # the chats I suggested, waiting to tell me
    ("event_crew", "user_id"),  # my door-helper rights (crew.py)
    ("qr_helpers", "user_id"),  # my right to help run a check-in (checkin.py)
    ("qr_meet_scans", "user_id"),  # every scan of a team meetup, including membership exceptions
    ("fchan_hearts", "user_id"),
    ("fchan_coming", "user_id"),  # my "I'm coming" under others' asks for help
    ("fchan_signed", "user_id"),  # who my signed comments under channel posts are (the comments are deleted above, with their messages in the group)
    ("fchan_comments", "user_id"),  # my face under channel posts (the comments stay in Telegram, Telegram's own)
    ("fchan_reply_reports", "user_id"),  # my /report on an anonymous author's reply
    ("staff_mutes", "user_id"),  # the staff notifications I muted
    ("research_requests", "user_id"),  # signed research proposals
    ("research_answers", "user_id"),  # delete signed answer contents; anonymous answers have no account link
    ("research_participants", "user_id"),  # only the fact that I answered, never a link to an answer
    ("app_chats", "user_id"),  # whether I am in the app's channel and group (logic/appchats.py)
    ("helper_offers", "user_id"),  # my offers to help the app (helpus.py)
    ("team_asks", "user_id"),  # my asks to come to my club's event as a guest
    ("credit_team", "user_id"),  # my place in People of the app's Team
    ("credit_consents", "user_id"),  # my answers to "shall we name you?" (credits.py); my lines stay nameless (credits.gone)
    ("fchan_photos", "user_id"),  # my photos picked for a post and never posted (posted ones go with their post)
    ("fchan_posts", "user_id"),  # what's left of my channel posts: held, hidden or deleted ones (the live ones moved on)
    ("vol_people", "user_id"), ("vol_access", "user_id"), ("vol_ties", "user_id"), ("vol_hands", "user_id"),  # my record in a club's volunteers ledger (its shifts, misses, edits go with it), my right to read it, a session's door handed to me
    ("gallery_photos", "user_id"),  # my Gallery posts (delete_me took them out of the albums, their files from disk)
    ("gallery_consents", "user_id"),
    ("chat_sync_todo", "user_id"), ("chat_sync_ask", "user_id"),  # a chat sync's finding about me, waiting for its sweep's end
    ("club_report_marks", "user_id"), ("report_consents", "user_id"),  # my marks, their comments and my consent; nullable author and editor links are cleared below
    ("event_team_members", "user_id"), ("team_consents", "user_id"),  # my place in an event's team (evteams.py; captaincy passes to who came next), my consent to teams
    ("subject_holds", "user_id"),  # a moderator's take-down of my listing on a subject (logic/subjects.py)
    ("kri_consents", "user_id"),  # my yes to Google answering the assistant first (assistant.GOOGLE_YES)
    ("appeal_ai_consents", "user_id"),  # my last opt-in to send an appeal draft abroad
    ("pymk_consents", "user_id"), ("pymk", "user_id"), ("pymk", "other_id"), ("pymk_dismissed", "user_id"), ("pymk_dismissed", "other_id"),  # People you may know: my switch, suggestions to me and of me, dismissals both ways
    ("swear_hits", "user_id"),  # the bot's swear warnings to me in clubs' groups (chatmod.py; by my Telegram id too, below)
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
    """The stand-in a deleted account's past leaves with: no name, no Telegram, never seen, a random negative
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
        con.execute("DELETE FROM donations WHERE user_id = ?", (v.id,))
        # money: the receipts go, theirs is personal (the club saw them); the paid seat it was for, if over, moves on
        paid = [r[0] for r in rows(con, """SELECT c.file_id FROM receipts c JOIN registrations r ON r.id = c.registration_id
            WHERE r.user_id = ?""", v.id)]
        con.execute("DELETE FROM receipts WHERE registration_id IN (SELECT id FROM registrations WHERE user_id = ?)", (v.id,))
        con.execute("DELETE FROM receipt_replaced WHERE registration_id IN (SELECT id FROM registrations WHERE user_id = ?)", (v.id,))
        # Ended registrations move to an anonymous account, so their age marks need explicit deletion.
        con.execute("DELETE FROM reg_age WHERE registration_id IN (SELECT id FROM registrations WHERE user_id = ?)", (v.id,))
        from . import guests
        guests.erase_pending(con, v.id)
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
        for rid, eid in con.execute(f"SELECT id, event_id FROM registrations WHERE user_id = :u AND status = 'going' AND event_id IN ({ended})", me_).fetchall():
            con.execute("""UPDATE registrations SET user_id = ?, note = NULL, answers = NULL, team_want = NULL,
                phone_shared = 0, rating_dismissed = 0, ticket_code = ? WHERE id = ?""", (pid, _ticket_code(con, eid), rid))
        con.execute("UPDATE event_ratings SET user_id = :p, comment = '' WHERE user_id = :u", me_)
        con.execute(f"UPDATE volunteers SET user_id = :p, note = '' WHERE user_id = :u AND event_id IN ({ended})", me_)
        done = "SELECT id FROM rounds WHERE status = 'done'"
        con.execute(f"UPDATE round_votes SET note = '' WHERE app_id IN (SELECT id FROM round_apps WHERE user_id = :u AND round_id IN ({done}))", me_)
        con.execute(f"UPDATE round_apps SET user_id = :p, answers = '{{}}', source = NULL WHERE user_id = :u AND round_id IN ({done})", me_)
        con.execute(f"""UPDATE round_votes SET user_id = :p, note = '' WHERE user_id = :u
            AND app_id IN (SELECT id FROM round_apps WHERE round_id IN ({done}))""", me_)
        # what I wrote stays, the person goes (as Telegram and Reddit): comments and the forum channel's live
        # posts move to the nameless placeholder, shown as a deleted account; a named post's signature in the channel
        # is rewritten (fch_resign), an anonymous one stays as it was, so nothing tells which posts were one person's
        # my anonymous replies (fchan_replies: no user id, through my posts): sent ones under a post that stays live
        # follow it to the placeholder; those under a post that goes now (held, hidden, deleted) leave the group too
        # (the bot's round, with an edit fallback for old messages), and what never went out goes now
        con.execute("""INSERT OR REPLACE INTO meta (key, value) SELECT 'fchdrop:' || r.tg_msg, ? FROM fchan_replies r JOIN fchan_posts p ON p.id = r.post_id
            WHERE p.user_id = ? AND p.status != 'live' AND r.tg_msg > 0""", (core.now(), v.id))
        con.execute("DELETE FROM fchan_replies WHERE tg_msg IS NULL AND post_id IN (SELECT id FROM fchan_posts WHERE user_id = ?)", (v.id,))
        # my signed comments (fchan_signed, signed with my name): out of the group in the same round, then the rows go
        signed = "FROM fchan_replies r JOIN fchan_signed s ON s.reply_id = r.id WHERE s.user_id = ?"
        con.execute("INSERT OR REPLACE INTO meta (key, value) SELECT 'tgcdel:' || r.tg_msg, ? " + signed + " AND r.tg_msg > 0", (core.now(), v.id))
        con.execute("DELETE FROM fchan_replies WHERE id IN (SELECT r.id " + signed + ")", (v.id,))
        con.execute("DELETE FROM comments WHERE user_id = :u AND deleted_at IS NOT NULL", me_)  # deleted or taken down: gone for good
        con.execute("UPDATE comments SET user_id = :p WHERE user_id = :u", me_)
        for (msg,) in rows(con, "SELECT tg_msg FROM fchan_posts WHERE user_id = ? AND status = 'live' AND anon = 0 AND tg_msg > 0", v.id):
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"fch_resign:{msg}",))
        # my edits of my posts (no user id: through the posts), waiting or kept for the pace: gone with me, their photos too
        con.execute("DELETE FROM fchan_photos WHERE edit_id IN (SELECT e.id FROM fchan_edits e JOIN fchan_posts p ON p.id = e.post_id WHERE p.user_id = ?)", (v.id,))
        con.execute("DELETE FROM fchan_edits WHERE post_id IN (SELECT id FROM fchan_posts WHERE user_id = ?)", (v.id,))
        # who came to my asks for help: a list for my eyes alone, nobody's once I'm gone
        con.execute("DELETE FROM fchan_coming WHERE post_id IN (SELECT id FROM fchan_posts WHERE user_id = ?)", (v.id,))
        # and my asks for help end now (the next round takes them down): nobody is left to come to
        con.execute("UPDATE fchan_posts SET help_until = ? WHERE user_id = ? AND help_until > ?", (core.now(), v.id, core.now()))
        con.execute("UPDATE fchan_posts SET user_id = :p, sign = :gone WHERE user_id = :u AND status = 'live' AND anon = 0", {**me_, "gone": core.GONE["ru"]})
        # the anonymous ones to one placeholder all deleted accounts share: never the named ones' (that would pair them)
        ghost = one(con, "SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'anon_ghost'")
        anon = one(con, "SELECT 1 FROM fchan_posts WHERE user_id = ? AND status = 'live' AND anon = 1", v.id)
        if anon and (not ghost or not one(con, "SELECT 1 FROM users WHERE id = ?", ghost[0])):
            ghost = (_placeholder(con),)
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('anon_ghost', ?)", (str(ghost[0]),))
        if anon:
            con.execute("UPDATE fchan_posts SET user_id = ? WHERE user_id = ? AND status = 'live' AND anon = 1", (ghost[0], v.id))
        # album photos: without my name, or gone if I asked (ask_delete)
        drop = one(con, "DELETE FROM meta WHERE key = ? RETURNING 1", f"delphotos:{v.id}") is not None
        mine = [r[0] for r in rows(con, "SELECT file_id FROM event_photos WHERE added_by = ?", v.id)] if drop else []
        mine += gallery.mine_gone(con, v.id)  # posted under my name: they go whatever I chose, with their reports
        if drop:
            con.execute("DELETE FROM event_photos WHERE added_by = ?", (v.id,))
        uploads = [r[0] for r in rows(con, "SELECT id FROM files WHERE kind != 'receipt' AND owner_id = ?", v.id)]
        tgpic = one(con, "SELECT tg_photo_path FROM users WHERE id = ?", v.id)[0]  # our copy of the Telegram photo
        con.execute(f"DELETE FROM dmp_list WHERE id IN (SELECT d.id {_DMP_MINE})", (v.id,))  # off DMP's list: its own row, by id
        con.execute("""UPDATE users SET bio = '', showcase = '', qr_code = NULL, link_code = NULL, cal_token = NULL, nick = NULL, avatar_tg = 1,
            avatar_file_id = NULL, tg_username = NULL, tg_first_name = '', tg_last_name = '', tg_photo_url = NULL, tg_photo_path = NULL, tg_photo_src = NULL, tg_photo_at = NULL, mark = NULL,
            skin_org = NULL, skin_pick = NULL, skin_look = NULL, frame = NULL, card_no = NULL, delete_at = NULL, city = NULL, city_hidden = 0, referred_by = NULL, announce_ok = NULL,
            role = 'user', is_founder = 0, forum_seen_msg = 0, notification_undo = '{}' WHERE id = ?""", (v.id,))  # a burnt number isn't given again
        # A claimed row with my email or a verified email and name match goes, and a reimport skips it.
        for (key,) in rows(con, """DELETE FROM roster_pending WHERE email = (SELECT lower(email) FROM students WHERE user_id = ?)
                AND (claimed_by = ? OR EXISTS (SELECT 1 FROM students s WHERE s.user_id = ?
                AND expected_name(full_name, s.ms_oid, s.ms_profile, s.manual, s.first_name, s.last_name)))
                RETURNING key""", v.id, v.id, v.id):
            con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", (f"roster_done:{key}", str(core.now())))
        con.execute("UPDATE roster_pending SET claimed_by = NULL WHERE claimed_by = ?", (v.id,))
        con.execute("UPDATE roster_pending SET rejected_by = NULL WHERE rejected_by = ?", (v.id,))
        # what a moderator took down of mine, kept for an undo: gone now with its files, no 30 days
        kept = [r[0] for r in rows(con, "DELETE FROM takedowns WHERE user_id = ? RETURNING file_id", v.id)]
        photos = [p for f in mine + uploads + kept for p in _drop_unused(con, f)]
        photos += [tgpic] if tgpic and chatlist.photo_free(con, tgpic) else []
        # the freshmen list's row for my mail or my unfinished Microsoft sign-in's (keyed by email: no foreign key)
        con.execute("""DELETE FROM prefill WHERE email IN (SELECT lower(email) FROM students WHERE user_id = ?
            UNION SELECT lower(json_extract(value, '$.email')) FROM meta WHERE key = ? AND json_valid(value))""", (v.id, f"ms:{v.id}"))
        # the list's rest: by those mails, and by my student ID only where the name is mine (the ID may be a typo for mine)
        con.execute("""DELETE FROM prefill_rest WHERE email IN (SELECT lower(email) FROM students WHERE user_id = ?
            UNION SELECT lower(json_extract(value, '$.email')) FROM meta WHERE key = ? AND json_valid(value))""", (v.id, f"ms:{v.id}"))
        # the check-in screens' expected lists an organizer uploaded: my name, mail, phone (keyed by mail or ID, no foreign key)
        con.execute("""DELETE FROM qr_expected WHERE email IN (SELECT lower(email) FROM students WHERE user_id = ?
            UNION SELECT lower(json_extract(value, '$.email')) FROM meta WHERE key = ? AND json_valid(value))""", (v.id, f"ms:{v.id}"))
        if s_ := one(con, "SELECT student_id, first_name, last_name FROM students WHERE user_id = ?", v.id):
            from .. import roster  # imports logic: here, not at the top
            # by my student ID only where the name is mine too (a typed ID may be a classmate's)
            for r in rows(con, "SELECT session_id, email, full_name FROM qr_expected WHERE student_id = ?", s_["student_id"]):
                if roster.same_person(r["full_name"], s_["first_name"] or "", s_["last_name"] or ""):
                    con.execute("DELETE FROM qr_expected WHERE session_id = ? AND email = ?", (r["session_id"], r["email"]))
            # by my ID, or with neither a mail nor an ID (they match nothing), where the name is mine
            for r in rows(con, "SELECT * FROM prefill_rest WHERE student_id = ? OR (email IS NULL AND student_id IS NULL)", s_["student_id"]):
                if prefill_mine(r, s_["first_name"], s_["last_name"]):
                    con.execute("DELETE FROM prefill_rest WHERE id = ?", (r["id"],))
        # the channel's comments by my Telegram id (no foreign key: kept before anyone signed in): my saved text, a
        # warning or a ban on record, a copy of mine reported before the account knew it
        tg = one(con, "SELECT tg_id FROM users WHERE id = ?", v.id)[0]
        for t in ("tgc_saved", "tgc_strangers", "chat_seen", "chat_seen_free"):  # chat_seen: /all's memory of me in clubs' chats
            con.execute(f"DELETE FROM {t} WHERE tg_id = ?", (tg,))
        # one still to come out of the group (deleting, or in the moderators' queue) still does: its ids, nothing more
        con.execute("""INSERT OR IGNORE INTO tgc_undel (chat_id, msg_id, at) SELECT chat_id, msg_id, ? FROM tgc_comments
            WHERE author_tg = ? AND status IN ('deleting', 'open', 'queued')""", (core.now(), tg))
        con.execute("DELETE FROM tgc_comments WHERE author_tg = ?", (tg,))
        con.execute("DELETE FROM swear_hits WHERE tg_id = ?", (tg,))
        credits.gone(con, tg)  # Keep the contribution while removing its link to the deleted account.
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"tgcedit:{tg}:%",))  # today's count of my edits' AI looks
        con.execute("DELETE FROM meta WHERE key = ?", (f"chpick:{tg}",))  # a club chat pick not used yet
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"qrshow:%:{v.id}",))  # the door QRs I showed (checkin.mark's "own")
        from . import vol
        vol.gone(con, v.id)  # my volunteers-ledger records, including ones unlinked since
        santa.gone(con, v.id)  # Secret Santa: my Santa gives to my person instead
        fks = _user_fks(con)
        # my appeals to SG, their words and answers with them (their author links go in the loop below)
        con.execute("DELETE FROM appeals WHERE id IN (SELECT appeal_id FROM appeal_authors WHERE user_id = ?)", (v.id,))
        for t, c in sorted(_DEL_GONE, key=lambda x: x[0] == "org_history"):
            con.execute(f"DELETE FROM {t} WHERE {c} = ?", (v.id,))
        for t, c, notnull in fks:
            if not notnull and (t, c) not in _DEL_GONE:
                con.execute(f"UPDATE {t} SET {c} = NULL WHERE {c} = ?", (v.id,))
            elif (t, c) not in _DEL_KEEP and one(con, f"SELECT 1 FROM {t} WHERE {c} = ?", v.id):
                raise RuntimeError(f"deleting account {v.id}: {t}.{c} is in no list")  # the transaction rolls back
        con.execute("UPDATE map_graph SET updated_by = NULL WHERE updated_by = ?", (v.id,))  # no foreign key there
        con.execute("DELETE FROM profile_views WHERE viewer_id = ? OR user_id = ?", (v.id, v.id))  # no foreign keys either
        con.execute("DELETE FROM meta WHERE key = ?", (f"ms:{v.id}",))  # an unfinished Microsoft sign-in: its profile too
        con.execute("""DELETE FROM meta WHERE key >= 'ms_claim:' AND key < 'ms_claim;'
            AND json_extract(value, '$.uid') = ?""", (v.id,))
        con.execute("""DELETE FROM meta WHERE key >= 'share:' AND key < 'share;'
            AND json_extract(value, '$.uid') = ?""", (v.id,))  # cards waiting for the bot (core.share_hold)
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"fsearch:{v.id}:%",))  # this hour's count of my searches for people
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"flook:{v.id}:%",))
        con.execute("DELETE FROM meta WHERE key = ?", (f"pymk_live:{v.id}",))  # today's own People you may know (pymk.switch)
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"subj:{v.id}:%",))  # this hour's count of my subject listings (logic/subjects)
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"upload:{v.id}:%",))
        con.execute("DELETE FROM meta WHERE key LIKE ?", (f"fchup:{v.id}:%",))  # this hour's count of my forum photo uploads
        con.execute("DELETE FROM meta WHERE key LIKE 'rclaim:%' AND value = ?", (str(v.id),))  # a roster claim that let me in
        # the admins' "two people gave this student ID" messages carry my name and email
        con.execute("DELETE FROM bot_outbox WHERE kind = 'id_clash' AND (ref LIKE ? OR ref LIKE ?)", (f"ic:%:{v.id}:%", f"ic:%:%:{v.id}"))
        con.execute("""DELETE FROM bot_outbox WHERE kind LIKE 'prefill_%' AND (ref = ? OR ref LIKE ? OR ref LIKE ?)""",
                    (f"pf:{v.id}", f"ph:{v.id}:%", f"ph:%:{v.id}"))  # the owner's freshmen-list alerts name me by id
        con.execute("DELETE FROM bot_outbox WHERE kind = 'sid_page_clash' AND ref LIKE ?", (f"sp:{v.id}:%",))  # so does his schedule-page alert
        # other people's queues that name me by id, sent or not; who he was in the role history
        for kind, ref in (("friend_invite", f"fi:%:{v.id}"), ("friend_new", f"fn:{v.id}:%"), ("friend_request", f"fq:{v.id}:%"), ("join_request", f"jr:%:{v.id}:%"),
                          ("team_ask", f"ta:%:{v.id}:%"), ("roster_claim", f"rq:%:{v.id}"), ("tgc_good", f"gr:{v.id}"), ("org_ask", f"oa:%:{v.id}")):
            con.execute("DELETE FROM bot_outbox WHERE kind = ? AND ref LIKE ?", (kind, ref))
        con.execute("UPDATE audit_log SET target = 'user', data = '{}' WHERE target IN (?, ?)", (f"user:{v.id}", f"tgreport:{v.id}"))
        con.execute("""UPDATE audit_log SET data = json_remove(data, '$.who') WHERE action IN ('checkin_hand', 'checkin_unhand')
            AND json_extract(data, '$.who') = ?""", (f"u{v.id}",))
        con.execute("UPDATE audit_log SET data = '{}' WHERE action = 'presidency_transfer' AND json_extract(data, '$.to') = ?", (v.id,))
        con.execute("""UPDATE audit_log SET data = '{}' WHERE action IN ('checkin_hand', 'checkin_unhand')
            AND json_extract(data, '$.who') = ?""", (f"u{v.id}",))
        con.execute("""UPDATE audit_log SET data = '{}' WHERE action IN ('seat_remove', 'came_by_hand', 'unseat_by_hand')
            AND json_extract(data, '$.user') = ?""", (v.id,))
        # a lifted take-down of my subject listing (logic/subjects.lift) names me and the subject: it and its undo go
        con.execute("""DELETE FROM audit_log WHERE action IN ('subject_lift', 'subject_unlift') AND target IN (SELECT target FROM audit_log
            WHERE action = 'subject_lift' AND json_extract(data, '$.user_id') = ?)""", (v.id,))
        con.execute("UPDATE audit_log SET data = json_remove(data, '$.by') WHERE action IN ('team_link_join', 'grant_link_used') AND json_extract(data, '$.by') = ?", (v.id,))  # who made the link
        con.execute("UPDATE reports SET note = NULL WHERE (target = 'user' AND target_id = ?) OR reporter_id IS NULL", (v.id,))
        log_action(con, None, "delete_my_data", "user")
        con.executemany("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')",
                        ((f"del-file:{folder}:{path}",) for folder, paths in (("receipts", receipts), ("media", photos)) for path in paths))
    return receipts, photos


def class_ends(hm: str) -> str:
    """When a class really ends: the portal gives the hour's slot ("14:00-15:00"), a class lasts 50 minutes of it:
    an end on the hour is ten minutes earlier. Any other end is the portal's own."""
    h, m = hm.split(":")
    return f"{int(h) - 1:02d}:50" if m == "00" and int(h) else hm


def schedule(con, v: Viewer) -> list[dict]:
    if not v.student:
        return []
    got = rows(con, "SELECT * FROM schedule_classes WHERE user_id = ? ORDER BY weekday, begins", v.id)
    return [{"weekday": c["weekday"], "begins": c["begins"], "ends": class_ends(c["ends"]), "subject": c["subject"], "kind": c["kind"],
             "room": c["room"], "teacher": c["teacher"], "names": n or None} for c, n in zip(got, _names(got))]


SCHED_LANGS = ("ru", "kk", "en")


def _names(saved, guess: bool = True) -> list[dict]:
    """Each saved class's names by language. A week the bot saved before it kept them has its subject
    alone: with `guess`, in the language its letters tell (portal.guess_lang), the same for the whole week (one page).
    The guess is for showing and matching only, never written: a wrong one would stick."""
    out = [json.loads(c["names"]) if c["names"] else {} for c in saved]
    bare = [(c["subject"], n) for c, n in zip(saved, out) if c["subject"] not in n.values()]
    if guess and (lang := portal.guess_lang([s for s, _ in bare])):
        for s, n in bare:
            n.setdefault(lang, s)
    return out


def sched_langs(names: list[dict]) -> list[str]:
    """The languages a week is in: those at least half its classes have a name in (a class new in the last page has
    that page's alone)."""
    return [x for x in SCHED_LANGS if names and 2 * sum(x in n for n in names) >= len(names)]


def _at(c: dict) -> int:
    """A class's start in minutes from Monday 00:00."""
    h, m = c["begins"].split(":")
    return (c["weekday"] * 24 + int(h)) * 60 + int(m)


def _room(c: dict) -> str:
    return (c["room"] or "").strip().casefold()


def _who(c: dict) -> str:
    """The teacher as the page in any language writes them, down to the consonants of each name (Akhmetov A. and its
    Cyrillic spelling: "mtv"; TRANSLIT, then kh = h, ts = c, q = k, j = zh, x = ks; vowels, y and h out, a doubled
    letter once); "" without one."""
    words = re.findall(r"[a-z]{2,}", (c["teacher"] or "").lower().translate(TRANSLIT))
    bones = (re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiouyh]", "", w.replace("kh", "h").replace("ts", "c").replace("q", "k")
                                                                .replace("j", "zh").replace("x", "ks"))) for w in words)
    return " ".join(sorted({b for b in bones if b}))


# How a new page's class finds itself among the saved ones, tier by tier, each class taken once. By its name in the
# page's language, when the saved class has one: the same class; then moved within its day or to another room; then to
# another day. A class with no name in that language (a page in a new language: other words, no course code) by its
# place and its teacher (a course dropped and another taken in its slot, a new semester: another teacher), never
# without one: day, time, kind, room; then another room at the same time; then another time on its day in its room.
# By place only a class alone with its key in both weeks pairs (two of one teacher's in one room on one day: course A
# swapped for B would take A's names); what could go two ways pairs none: a wrong name is worse than one in another
# language. ponytail: a teacher spelt apart in Latin and Cyrillic beyond _who's rules, or missing, carries no names
# over (the safe side); one course swapped for another of the same teacher, room and day, the only one there, does
_BY_NAME = (lambda c: (c["weekday"], c["begins"], c["ends"], c["kind"], _room(c), c["name"]),
            lambda c: (c["weekday"], c["kind"], c["name"]),
            lambda c: (c["kind"], c["name"]))
_BY_PLACE = (lambda c: (c["weekday"], c["begins"], c["ends"], c["kind"], _room(c), c["who"]),
             lambda c: (c["weekday"], c["begins"], c["ends"], c["kind"], c["who"]),
             lambda c: (c["weekday"], c["kind"], _room(c), c["who"]))
PAIR_MAX = 200  # ways to pair one group weighed at most (a real group has 1-4 classes)


def _pair(old: list[dict], new: list[dict]) -> list[tuple[dict, dict]]:
    """One group's saved and new classes by name (each in the week's order) paired in that order, the fewest minutes
    moved: the bigger side's extra ones stay unpaired; more ways than PAIR_MAX (a made-up page) in order (the same
    names either way)."""
    few, many = sorted((old, new), key=len)
    keep = many
    if comb(len(many), len(few)) <= PAIR_MAX:
        keep = min(combinations(many, len(few)), key=lambda k: sum(abs(_at(a) - _at(b)) for a, b in zip(few, k)))
    return [(a, b) if few is old else (b, a) for a, b in zip(few, keep)]


def save_schedule(con, uid: int, lessons: list, lang: str | None = None) -> dict | None:
    """A week from the portal's page (portal.Lesson): the truth about times, rooms and which classes there are, so it
    replaces the student's rows, while each class keeps the names earlier pages in other languages gave it and gets this
    page's (`lang`, by its day names; None: matched as its words' letters tell, with nothing written under a guess).
    Matched outside the write lock, written in one short transaction (matching can hold it for seconds);
    None when the student is gone meanwhile. What changed, for the bot's answer: the page's language, the week's
    languages before and after, classes added, removed and moved."""
    q = "SELECT * FROM schedule_classes WHERE user_id = ? ORDER BY weekday, begins, id"
    saved = rows(con, q, uid)
    lessons = [x for x in lessons if x.weekday < 7]  # no Sunday classes (the online duplicates)
    got, new, names = _merge(saved, lessons, lang)
    with tx(con):
        if not one(con, "SELECT 1 FROM students WHERE user_id = ? AND manual = 0", uid):
            return None  # the account (or its KBTU sign-in) deleted while the page was matched: its week doesn't come back
        if (now := rows(con, q, uid)) != saved:  # another page landed meanwhile: matched again (the caps keep it short)
            got, new, names = _merge(now, lessons, lang)
        con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (uid,))
        con.executemany("""INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, code, kind, room, teacher, names)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [(uid, x["weekday"], x["begins"], x["ends"], x["subject"], x.get("code"), x["kind"],
                                                         x["room"], x["teacher"], json.dumps(n, ensure_ascii=False) if n else None)
                                                        for x, n in zip(new, names)])
    return got


def _merge(saved, lessons: list, lang: str | None) -> tuple[dict, list[dict], list[dict]]:
    """save_schedule's matching, no database: what changed, the new classes, each one's names."""
    page, lang = lang, lang or portal.guess_lang([x.subject for x in lessons])
    old = [{**c, "known": n, "stored": s, "name": n.get(lang)} for c, n, s in zip(map(dict, saved), _names(saved), _names(saved, False))]
    new = sorted(({**vars(x), "name": x.subject} for x in lessons), key=_at)
    for c in old + new:
        c["who"] = _who(c)
    for keys, among in ((_BY_NAME, old), (_BY_PLACE, [o for o in old if o["name"] is None and o["who"]])):
        for key in keys:
            groups: dict = {}
            for o in among:
                if not o.get("taken"):
                    groups.setdefault(key(o), ([], []))[0].append(o)
            for x in new:
                if "was" not in x and key(x) in groups:
                    groups[key(x)][1].append(x)
            if keys is _BY_PLACE:  # alone with its key in both whole weeks, taken or not
                alone = [{k for k, n in Counter(map(key, side)).items() if n == 1} for side in (old, new)]
                groups = {k: g for k, g in groups.items() if k in alone[0] and k in alone[1]}
            for o, x in (p for g in groups.values() if g[0] and g[1] for p in (_pair(*g) if keys is _BY_NAME else zip(*g))):
                o["taken"], x["was"] = True, o
    names = [{**(x["was"]["stored"] if "was" in x else {}), **({page: x["subject"]} if page else {})} for x in new]
    kept = [x for x in new if "was" in x]
    return {"lang": page, "was": len(old), "had": sched_langs([o["known"] for o in old]), "has": sched_langs(names), "added": len(new) - len(kept),
            "removed": len(old) - len(kept), "moved": sum(1 for x in kept if (_at(x), x["ends"], _room(x)) != (_at(x["was"]), x["was"]["ends"], _room(x["was"])))}, new, names


def drop_my_schedule(con, v: Viewer) -> None:
    """My week deleted (the Week sheet). These rows are all of it: the names ride in them, the page sent to the bot is
    never kept, the assistant reads the rows live. A guest has none, as with the GET."""
    if v.student:
        con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (v.id,))


# the other domains', imported last: they import this one too, and each needs the other's names only
# when a function runs
from . import chatlist, core, credits, guests, inbox, profiles, santa  # noqa: E402
from .clubs import TRANSLIT, stories_open  # noqa: E402
from .newsfeed import unread_broadcasts  # noqa: E402
from .organizing import kz_phone, link_door_guests  # noqa: E402
from .profiles import ACHIEVEMENTS, _celebrate, _levels, brought, first_fifty, unlocked  # noqa: E402
from .seats import _ticket_code, ev_ref, joined, notify, promote  # noqa: E402
from .teams import _ordered  # noqa: E402
from . import gallery  # noqa: E402


# "Support & ideas" at the bottom of Me: the creator, then the main admin (Alikhan). A new main admin:
# this line. Their Telegram usernames are the chat links; the cards are the app's own (photo as everywhere).
SUPPORT = ("Sowers", "Relson69")


def support(con) -> list[dict]:
    found = {p["tg_username"].lower(): p for p in rows(con, f"""SELECT {core.PERSON_COLS}, u.tg_username FROM users u
        LEFT JOIN students s ON s.user_id = u.id WHERE lower(u.tg_username) IN ({",".join("?" * len(SUPPORT))}) AND u.banned_at IS NULL""",
        *(n.lower() for n in SUPPORT))}
    return [{**person_ref(p), "username": p["tg_username"]} for n in SUPPORT if (p := found.get(n.lower()))]
from . import chatsync  # noqa: E402  (ms_link, consent: a look in the linked chats)
