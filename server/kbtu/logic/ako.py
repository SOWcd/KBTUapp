"""Admissions to an org's programs: the first is KBTU's Academy of Corporate Education (AKO). An applicant (40 to 60,
often without Telegram) opens one link, picks a program, attaches the documents it asks for, books an online interview
when the program has one, and sends. The same link opens the package later to add what came after (a medical
certificate, a signed application) or to move the interview.

The link is the credential: /ako/<secret>, 256 bits, kept here only as its SHA-256 (ako_apps.token). With it one adds
and replaces files and never downloads them; the files go only to the org's own people (org_members: head and up
manage, a member reads: the Academic Programs department reviewing a package). No account, no Telegram.

A public start link (/ako/o/<org slug>, for the org's website) makes a draft on the first real step, never on a GET
(WhatsApp's link previews fetch every link). Drafts never sent go after DRAFT_KEEP; sent packages after KEEP."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import secrets
import tempfile
import time
import zipfile
from pathlib import Path

from PIL import Image

from .. import media, pdfpages, texts
from ..db import tx
from . import core
from .core import ApiError, Viewer, at_least, now, one, role_in, rows
from .organizing import kz_phone
from .seats import _calendar, _ics_text

CONSENT = "ako-1"           # the applicant's own notice (web i18n ako.consent*): a new wording, a new version
DOCS = ("cv", "diploma", "application", "id", "photo", "med", "fluoro", "work", "extra")
MAX_FILES = 24              # an application's files: ~9 documents, a few with several pages (ponytail: replacing is
                            # unlimited within it; a per-day cap on uploads if a link is ever abused)
FILE_BYTES = 10 * 1024 * 1024
SIDE = 2400                 # a photographed page is kept at most this long: a diploma's small print stays readable
STARTS_A_DAY = 20           # drafts one address may start from the public link in a day
CUTOFF = 6 * 3600           # a slot closes for booking this long before it starts
DRAFT_KEEP = 7 * 86400      # a draft nobody sent, from its last change
KEEP = 365 * 86400          # a sent package, from sending: ponytail, a year flat; the upgrade is N months after the intake starts
IP_KEEP = 86400
STATUSES = ("draft", "sent", "review", "accepted", "declined")
LANGS = ("ru", "kk", "en")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_DAY = re.compile(r"20[2-9][0-9]-[01][0-9]-[0-3][0-9]")
_HM = re.compile(r"[0-2][0-9]:[0-5][0-9]")
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]")
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,24}")
_MEET = re.compile(r"https://(?:teams\.microsoft\.com|teams\.live\.com)/\S{1,600}")
DATA = Path(__file__).resolve().parents[1] / "i18n" / "ako.json"


# ---------------------------------------------------------------- shared

def _line(x: object, most: int) -> str:
    return " ".join(_CTRL.sub(" ", x).split())[:most] if isinstance(x, str) else ""


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def new_token() -> tuple[str, bytes]:
    t = secrets.token_urlsafe(32)
    return t, _digest(t)


def root_of(con) -> Path:
    """The private folder for documents: beside the database, never under /media (served only through the API)."""
    return Path(one(con, "PRAGMA database_list")["file"]).resolve().parent / "ako"


def _unlink(root: Path, paths) -> None:
    for p in paths:
        try:
            (root / p).unlink()
        except FileNotFoundError:
            pass


def _keys(csv: str) -> list[str]:
    return [k for k in csv.split(",") if k]


def _program(r) -> dict:
    return {"id": r["id"], "key": r["key"], "kind": r["kind"], "info": json.loads(r["info"]), "url": r["url"],
            "interview": bool(r["interview"]), "first": _keys(r["first"]), "later": _keys(r["later"]), "optional": _keys(r["optional"])}


def _programs(con, oid: int, all_: bool = False) -> list[dict]:
    return [_program(r) for r in rows(con, f"""SELECT * FROM ako_programs WHERE org_id = ? {'' if all_ else 'AND open = 1'}
        ORDER BY sort, id""", oid)]


def _org(con, oid: int) -> dict:
    o = one(con, "SELECT id, slug, name, i18n FROM orgs WHERE id = ?", oid)
    tr = json.loads(o["i18n"]) if o["i18n"] else {}
    return {"slug": o["slug"], "name": {"ru": o["name"], **{k: x["name"] for k, x in tr.items() if x.get("name")}}}


def _teams(con, oid: int, s) -> str | None:
    """A slot's meeting link: its own, else its day's in Almaty."""
    if s["teams"]:
        return s["teams"]
    d = one(con, "SELECT teams FROM ako_days WHERE org_id = ? AND day = ?", oid, time.strftime("%Y-%m-%d", time.gmtime(s["starts_at"] + core.TZ)))
    return d["teams"] if d else None


def _booked(con, ids) -> dict[int, int]:
    ids = list(ids)
    return {r[0]: r[1] for r in rows(con, f"SELECT slot_id, COUNT(*) FROM ako_apps WHERE slot_id IN ({core._qs(ids)}) GROUP BY slot_id", *ids)} if ids else {}


# ---------------------------------------------------------------- the applicant (the link is the credential)

def _app(con, token: object):
    a = one(con, "SELECT * FROM ako_apps WHERE token = ?", _digest(token)) if isinstance(token, str) and _TOKEN.fullmatch(token) else None
    if not a:
        raise ApiError("not_found")
    return a


def _needs(con, a) -> tuple[dict | None, bool]:
    p = one(con, "SELECT * FROM ako_programs WHERE id = ?", a["program_id"]) if a["program_id"] else None
    return (_program(p) if p else None), bool(p and p["interview"])


def public(con, slug: str) -> dict:
    """The start page of an org's admissions (its website's link): its name and open programs; nothing is made."""
    o = one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", slug) if isinstance(slug, str) and len(slug) <= 40 else None
    programs = _programs(con, o["id"]) if o else []
    if not programs:
        raise ApiError("not_found")
    return {"org": _org(con, o["id"]), "programs": programs}


def start(con, slug: str, body: dict, ip: str, key: bytes) -> dict:
    """The public link's first real step: a draft with the program picked. The secret goes back once, here."""
    o = one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", slug) if isinstance(slug, str) and len(slug) <= 40 else None
    p = one(con, "SELECT id FROM ako_programs WHERE org_id = ? AND key = ? AND open = 1", o["id"], body.get("program")) if o else None
    if not p:
        raise ApiError("not_found")
    lang = body.get("lang") if body.get("lang") in LANGS else "ru"
    who = hmac.new(key, f"ako-ip:{ip}".encode(), hashlib.sha256).hexdigest()[:24]
    token, digest = new_token()
    with tx(con):
        if one(con, "SELECT COUNT(*) FROM ako_apps WHERE ip = ? AND created_at > ?", who, now() - 86400)[0] >= STARTS_A_DAY:
            raise ApiError("rate_limited", "ako_starts")
        con.execute("""INSERT INTO ako_apps (org_id, token, program_id, lang, ip, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (o["id"], digest, p["id"], lang, who, now(), now()))
    return {"token": token}


def view(con, token: str) -> dict:
    """What the applicant's page shows: the org, its programs, my answers and documents (names only: never their
    contents), my interview with its meeting link, and the times I may book."""
    a = _app(con, token)
    program, interview = _needs(con, a)
    files = rows(con, "SELECT id, doc, mime, bytes, created_at FROM ako_files WHERE app_id = ? ORDER BY id", a["id"])
    slot = one(con, "SELECT * FROM ako_slots WHERE id = ?", a["slot_id"]) if a["slot_id"] else None
    return {"org": _org(con, a["org_id"]), "programs": _programs(con, a["org_id"]), "program": program["key"] if program else None,
            "name": a["name"], "phone": a["phone"], "email": a["email"], "lang": a["lang"], "status": a["status"],
            "consent": a["consent"] == CONSENT, "sentAt": a["sent_at"], "rebook": a["rebook"],
            "files": [{"id": f["id"], "doc": f["doc"], "mime": f["mime"], "bytes": f["bytes"], "at": f["created_at"]} for f in files],
            "slot": {"id": slot["id"], "at": slot["starts_at"], "minutes": slot["minutes"], "teams": _teams(con, a["org_id"], slot)} if slot else None,
            "slots": _free(con, a) if interview and a["status"] in ("draft", "sent", "review") else [],
            "maxFiles": MAX_FILES, "maxBytes": FILE_BYTES}


def _free(con, a) -> list[dict]:
    """The times one may book: from CUTOFF on, with a seat left (my own time stays in the list, full or not)."""
    ss = rows(con, "SELECT id, starts_at, minutes, cap FROM ako_slots WHERE org_id = ? AND starts_at > ? ORDER BY starts_at, id LIMIT 400",
              a["org_id"], now() + CUTOFF)
    taken = _booked(con, [s["id"] for s in ss])
    out: dict[int, dict] = {}
    for s in ss:
        if (taken.get(s["id"], 0) < s["cap"] or s["id"] == a["slot_id"]) and s["starts_at"] not in out:  # two interviewers at one time: one choice
            out[s["starts_at"]] = {"id": s["id"], "at": s["starts_at"], "minutes": s["minutes"]}
    return list(out.values())


def _editable(a) -> None:
    if a["status"] in ("accepted", "declined"):
        raise ApiError("closed", "ako_decided")


def patch(con, token: str, body: dict) -> None:
    """The applicant's answers: program, name, phone, email, language, and the notice agreed to (consent: true)."""
    with tx(con):
        a = _app(con, token)
        _editable(a)
        sets: dict[str, object] = {}
        if "program" in body:
            p = one(con, "SELECT id, interview FROM ako_programs WHERE org_id = ? AND key = ? AND open = 1", a["org_id"], body["program"])
            if not p:
                raise ApiError("bad_input", "program")
            if a["status"] != "draft" and p["id"] != a["program_id"]:
                raise ApiError("closed", "ako_sent")  # a sent package changes program through the managers
            sets["program_id"] = p["id"]
            if not p["interview"]:
                sets["slot_id"] = None
        if "name" in body:
            sets["name"] = _line(body["name"], 120)
        if "phone" in body:
            ph = str(body["phone"] or "").strip()
            sets["phone"] = "" if not ph else kz_phone(ph) or (_line(ph, 24) if re.fullmatch(r"\+?[0-9 ()-]{7,24}", ph) else None)
            if sets["phone"] is None:
                raise ApiError("bad_input", "phone")
        if "email" in body:
            e = _line(body["email"], 254)
            if e and not _EMAIL.fullmatch(e):
                raise ApiError("bad_input", "email")
            sets["email"] = e
        if body.get("lang") in LANGS:
            sets["lang"] = body["lang"]
        if body.get("consent") is True and a["consent"] != CONSENT:
            sets["consent"], sets["consent_at"] = CONSENT, now()
        if sets:
            con.execute(f"UPDATE ako_apps SET {', '.join(f'{k} = ?' for k in sets)}, updated_at = ? WHERE id = ?",
                        (*sets.values(), now(), a["id"]))


def _picture(data: bytes) -> tuple[bytes, str]:
    """A document as kept: a photo upright as a JPEG (no other bytes of the upload survive), or a PDF that opens."""
    if data[:5] == b"%PDF-":
        with tempfile.TemporaryDirectory(prefix="ako-pdf-") as out:
            try:
                pdfpages.run(data, Path(out), 1, 200, 10, 1 << 30, cut=True)  # a real, unlocked PDF, in a child with limits
            except ValueError:
                raise ApiError("bad_input", "bad_file") from None
        return data, "application/pdf"
    try:
        im = media.decode(data)
    except media.BadImage:
        raise ApiError("bad_input", "bad_file") from None
    im.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=86, optimize=True)
    return out.getvalue(), "image/jpeg"


def add_file(con, token: str, doc: str, data: bytes) -> dict:
    """One page or file of a document. The page is converted before the write lock; a refused write leaves no file."""
    if doc not in DOCS:
        raise ApiError("bad_input", "doc")
    a = _app(con, token)
    if a["consent"] != CONSENT:
        raise ApiError("forbidden", "ako_consent")
    _editable(a)
    body, mime = _picture(data)
    root = root_of(con)
    name = secrets.token_hex(16)
    rel = f"{name[:2]}/{name}.{'pdf' if mime == 'application/pdf' else 'jpg'}"
    (root / name[:2]).mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(body)
    try:
        with tx(con):
            a = _app(con, token)
            if one(con, "SELECT COUNT(*) FROM ako_files WHERE app_id = ?", a["id"])[0] >= MAX_FILES:
                raise ApiError("rate_limited", "ako_files")
            fid = con.execute("INSERT INTO ako_files (app_id, doc, path, mime, bytes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (a["id"], doc, rel, mime, len(body), now())).lastrowid
            con.execute("UPDATE ako_apps SET updated_at = ? WHERE id = ?", (now(), a["id"]))
    except BaseException:
        _unlink(root, [rel])
        raise
    return {"id": fid, "doc": doc, "mime": mime, "bytes": len(body), "at": now()}


def drop_file(con, token: str, fid: int) -> None:
    """A page taken back (a blurry photo): the applicant replaces, never reads."""
    with tx(con):
        a = _app(con, token)
        _editable(a)
        f = one(con, "SELECT path FROM ako_files WHERE id = ? AND app_id = ?", fid, a["id"])
        if not f:
            raise ApiError("not_found")
        con.execute("DELETE FROM ako_files WHERE id = ?", (fid,))
        con.execute("UPDATE ako_apps SET updated_at = ? WHERE id = ?", (now(), a["id"]))
    _unlink(root_of(con), [f["path"]])


def _take(con, a, slot: object) -> None:
    """Book (or move to) a slot in this transaction: a seat must be left, from CUTOFF on; the old one frees in the same write."""
    s = one(con, "SELECT id, starts_at, cap FROM ako_slots WHERE id = ? AND org_id = ?", slot, a["org_id"]) \
        if isinstance(slot, int) and not isinstance(slot, bool) else None
    if not s:
        raise ApiError("not_found", "ako_slot")
    if s["id"] == a["slot_id"]:
        return
    if s["starts_at"] <= now() + CUTOFF:
        raise ApiError("closed", "ako_slot_late")
    if one(con, "SELECT COUNT(*) FROM ako_apps WHERE slot_id = ?", s["id"])[0] >= s["cap"]:
        raise ApiError("full", "ako_slot_taken")
    con.execute("UPDATE ako_apps SET slot_id = ?, rebook = NULL, updated_at = ? WHERE id = ?", (s["id"], now(), a["id"]))


def book(con, token: str, slot: object) -> dict:
    """The interview time picked, moved, or (None) given back. Two people on one last seat: the write lock lets one in."""
    with tx(con):
        a = _app(con, token)
        _editable(a)
        _, interview = _needs(con, a)
        if not interview:
            raise ApiError("bad_input", "ako_no_interview")
        if slot is None:
            cur = one(con, "SELECT starts_at FROM ako_slots WHERE id = ?", a["slot_id"]) if a["slot_id"] else None
            if cur and cur["starts_at"] <= now() + CUTOFF:
                raise ApiError("closed", "ako_slot_late")  # too close to give back by hand: the managers move it
            con.execute("UPDATE ako_apps SET slot_id = NULL, updated_at = ? WHERE id = ?", (now(), a["id"]))
        else:
            if a["slot_id"]:
                cur = one(con, "SELECT starts_at FROM ako_slots WHERE id = ?", a["slot_id"])
                if cur and cur["starts_at"] <= now() + CUTOFF:
                    raise ApiError("closed", "ako_slot_late")
            _take(con, a, slot)
    return view(con, token)


def submit(con, token: str) -> dict:
    """Sent with what there is: the program, a name and a phone, the first documents, and an interview time when the
    program has one and there is a time to pick. What comes later never holds it up. Sending again changes nothing."""
    with tx(con):
        a = _app(con, token)
        program, interview = _needs(con, a)
        if a["status"] != "draft":
            return view(con, token)
        have = {r[0] for r in rows(con, "SELECT DISTINCT doc FROM ako_files WHERE app_id = ?", a["id"])}
        missing = [d for d in (program["first"] if program else []) if d not in have]
        if not program or not a["name"] or not a["phone"] or a["consent"] != CONSENT or missing:
            raise ApiError("bad_input", "ako_incomplete", {"missing": missing})
        if interview and not a["slot_id"] and _free(con, a):
            raise ApiError("bad_input", "ako_slot_needed")
        con.execute("UPDATE ako_apps SET status = 'sent', sent_at = ?, updated_at = ?, ip = NULL WHERE id = ?", (now(), now(), a["id"]))
    return view(con, token)


def ics(con, token: str) -> str:
    """My interview as a calendar invite, its meeting link inside and two alarms (a day and an hour before): the phone
    reminds even when our server is down."""
    a = _app(con, token)
    s = one(con, "SELECT * FROM ako_slots WHERE id = ?", a["slot_id"]) if a["slot_id"] else None
    if not s:
        raise ApiError("not_found")
    program, _ = _needs(con, a)
    org, lang = _org(con, a["org_id"]), a["lang"]
    info = (program or {}).get("info", {}).get(lang) or (program or {}).get("info", {}).get("ru") or {}
    words = texts.AKO_ICS[lang]
    teams = _teams(con, a["org_id"], s)
    utc = lambda ts: time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))  # noqa: E731
    title = words["title"].format(program=" ".join(filter(None, (info.get("title"), info.get("sub")))), org=org["name"].get(lang) or org["name"]["ru"])
    lines = ["BEGIN:VEVENT", f"UID:ako{a['id']}-{s['id']}@kbtu-app", f"DTSTAMP:{utc(now())}", f"DTSTART:{utc(s['starts_at'])}",
             f"DTEND:{utc(s['starts_at'] + s['minutes'] * 60)}", "SUMMARY:" + _ics_text(title), "LOCATION:" + _ics_text(teams or "Microsoft Teams"),
             "DESCRIPTION:" + _ics_text(words["body"] + (f"\n{teams}" if teams else "")), *([f"URL:{teams}"] if teams else [])]
    for before in ("-P1D", "-PT1H"):
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _ics_text(title), f"TRIGGER:{before}", "END:VALARM"]
    return _calendar([*lines, "END:VEVENT"])


# ---------------------------------------------------------------- the org's people (Studio)

def _team(con, v: Viewer, oid: int, manage: bool = False) -> None:
    """Head and up run admissions; any member reads them (a reviewer from Academic Programs)."""
    r = role_in(con, v, oid)
    if r is None or manage and not at_least(r, "head") or not one(con, "SELECT 1 FROM ako_programs WHERE org_id = ? LIMIT 1", oid):
        raise ApiError("forbidden")


def manages(con, oid: int, role: str) -> str | None:
    """/api/me's membership: "manage" or "review" when the org takes applications."""
    if not one(con, "SELECT 1 FROM ako_programs WHERE org_id = ? LIMIT 1", oid):
        return None
    return "manage" if at_least(role, "head") else "review"


def _row(a, have: set[str], program: dict | None, slot) -> dict:
    need = (program["first"] + program["later"]) if program else []
    return {"id": a["id"], "name": a["name"], "phone": a["phone"], "program": program["key"] if program else None,
            "status": a["status"], "sentAt": a["sent_at"], "updatedAt": a["updated_at"], "mine": a["created_by"] is not None,
            "slot": {"id": slot["id"], "at": slot["starts_at"], "minutes": slot["minutes"], "who": slot["who"]} if slot else None,
            "rebook": a["rebook"], "missing": [d for d in need if d not in have], "docs": len(have)}


def desk(con, v: Viewer, oid: int) -> dict:
    """The admissions in Studio: programs, every applicant with what is missing, and the interview days ahead."""
    _team(con, v, oid)
    programs = {p["id"]: p for p in _programs(con, oid, all_=True)}
    apps = rows(con, "SELECT * FROM ako_apps WHERE org_id = ? ORDER BY COALESCE(sent_at, updated_at) DESC LIMIT 500", oid)
    ids = [a["id"] for a in apps]
    have: dict[int, set[str]] = {}
    for r in rows(con, f"SELECT DISTINCT app_id, doc FROM ako_files WHERE app_id IN ({core._qs(ids)})", *ids) if ids else []:
        have.setdefault(r[0], set()).add(r[1])
    slots = rows(con, "SELECT * FROM ako_slots WHERE org_id = ? AND starts_at > ? ORDER BY starts_at, id LIMIT 600", oid, now() - 86400)
    by_id = {s["id"]: s for s in slots}
    for s in rows(con, f"""SELECT * FROM ako_slots WHERE id IN (SELECT slot_id FROM ako_apps WHERE org_id = ? AND slot_id IS NOT NULL)""", oid):
        by_id.setdefault(s["id"], s)
    taken: dict[int, list[int]] = {}
    for a in apps:
        if a["slot_id"]:
            taken.setdefault(a["slot_id"], []).append(a["id"])
    days = {r["day"]: r["teams"] for r in rows(con, "SELECT day, teams FROM ako_days WHERE org_id = ?", oid)}
    return {"manage": role_in(con, v, oid) is not None and at_least(role_in(con, v, oid), "head"),
            "programs": list(programs.values()),
            "apps": [_row(a, have.get(a["id"], set()), programs.get(a["program_id"]), by_id.get(a["slot_id"])) for a in apps],
            "slots": [{"id": s["id"], "at": s["starts_at"], "minutes": s["minutes"], "cap": s["cap"], "who": s["who"], "teams": s["teams"],
                       "apps": taken.get(s["id"], [])} for s in slots],
            "days": days, "cutoff": CUTOFF}


def _of(con, oid: int, aid: int):
    a = one(con, "SELECT * FROM ako_apps WHERE id = ? AND org_id = ?", aid, oid)
    if not a:
        raise ApiError("not_found")
    return a


def package(con, v: Viewer, oid: int, aid: int) -> dict:
    """One applicant's whole package for the team: answers, files (by id, to open), the interview."""
    _team(con, v, oid)
    a = _of(con, oid, aid)
    program, _ = _needs(con, a)
    files = rows(con, "SELECT id, doc, mime, bytes, created_at FROM ako_files WHERE app_id = ? ORDER BY doc, id", aid)
    slot = one(con, "SELECT * FROM ako_slots WHERE id = ?", a["slot_id"]) if a["slot_id"] else None
    by = one(con, f"{core.PERSON} WHERE u.id = ?", a["created_by"]) if a["created_by"] else None
    return {**_row(a, {f["doc"] for f in files}, program, slot), "email": a["email"], "lang": a["lang"], "note": a["note"],
            "consentAt": a["consent_at"], "createdAt": a["created_at"], "by": core.person_ref(by) if by else None,
            "teams": _teams(con, oid, slot) if slot else None,
            "files": [{"id": f["id"], "doc": f["doc"], "mime": f["mime"], "bytes": f["bytes"], "at": f["created_at"]} for f in files]}


def _names(con, a) -> tuple[str, dict]:
    program, _ = _needs(con, a)
    base = re.sub(r"[^\w .-]+", "", a["name"] or f"applicant {a['id']}").strip()[:60] or f"applicant {a['id']}"
    return base, program or {}


LINK_TTL = 300  # a download link the team's app opens at once (Telegram's downloadFile, a browser tab): five minutes


def _sig(key: bytes, what: str, exp: int) -> str:
    return hmac.new(key, f"ako-dl:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def link(con, v: Viewer, oid: int, what: str, xid: int, key: bytes) -> dict:
    """A download link for one file ("f") or a whole package ("z") of this org: signed, five minutes, no session in it
    (Telegram's webview and a browser tab can't send our headers on a download)."""
    _team(con, v, oid)
    ok = one(con, "SELECT 1 FROM ako_files f JOIN ako_apps a ON a.id = f.app_id WHERE f.id = ? AND a.org_id = ?", xid, oid) if what == "f" \
        else one(con, "SELECT 1 FROM ako_apps WHERE id = ? AND org_id = ?", xid, oid)
    if not ok:
        raise ApiError("not_found")
    exp = now() + LINK_TTL
    core.log_action(con, v.id, "ako_download", f"ako:{what}{xid}")
    return {"url": f"/api/ako/{what}/{xid}?e={exp}&s={_sig(key, f'{what}{xid}', exp)}"}


def signed(what: str, xid: int, e: object, s: object, key: bytes) -> None:
    if not (isinstance(e, str) and e.isdigit() and len(e) < 12 and isinstance(s, str)
            and hmac.compare_digest(s, _sig(key, f"{what}{xid}", int(e))) and int(e) >= now()):
        raise ApiError("not_found")


def file_for(con, fid: int) -> tuple[Path, str, str]:
    """A document's file (its link checked by signed()), as an attachment: (path, media type, download name)."""
    f = one(con, "SELECT f.*, a.org_id, a.name, a.id AS aid FROM ako_files f JOIN ako_apps a ON a.id = f.app_id WHERE f.id = ?", fid)
    if not f:
        raise ApiError("not_found")
    n = one(con, "SELECT COUNT(*) FROM ako_files WHERE app_id = ? AND doc = ? AND id <= ?", f["aid"], f["doc"], fid)[0]
    base = re.sub(r"[^\w .-]+", "", f["name"] or "").strip()[:60] or f"applicant {f['aid']}"
    return root_of(con) / f["path"], f["mime"], f"{base} - {f['doc']}-{n}.{'pdf' if f['mime'] == 'application/pdf' else 'jpg'}"


def zip_of(con, aid: int) -> tuple[bytes, str]:
    """The whole package (its link checked by signed()) as one ZIP, each file named by its document and page."""
    a = one(con, "SELECT * FROM ako_apps WHERE id = ?", aid)
    if not a:
        raise ApiError("not_found")
    base, _ = _names(con, a)
    out, root, seen = io.BytesIO(), root_of(con), {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:  # JPEGs and PDFs are compressed already
        for f in rows(con, "SELECT doc, path, mime FROM ako_files WHERE app_id = ? ORDER BY doc, id", aid):
            seen[f["doc"]] = seen.get(f["doc"], 0) + 1
            try:
                z.writestr(f"{f['doc']}-{seen[f['doc']]}.{'pdf' if f['mime'] == 'application/pdf' else 'jpg'}", (root / f["path"]).read_bytes())
            except FileNotFoundError:
                continue
    return out.getvalue(), f"{base}.zip"


def new_app(con, v: Viewer, oid: int, body: dict) -> dict:
    """After a consultation: a package prefilled with the program, name and phone, and its link to send in WhatsApp.
    The secret is shown once; a lost one is replaced (update_app newLink)."""
    _team(con, v, oid, manage=True)
    p = one(con, "SELECT id FROM ako_programs WHERE org_id = ? AND key = ?", oid, body.get("program"))
    if not p:
        raise ApiError("bad_input", "program")
    name, phone = _line(body.get("name"), 120), str(body.get("phone") or "").strip()
    ph = kz_phone(phone) or (_line(phone, 24) if re.fullmatch(r"\+?[0-9 ()-]{7,24}", phone) else "") if phone else ""
    if phone and not ph:
        raise ApiError("bad_input", "phone")
    token, digest = new_token()
    with tx(con):
        aid = con.execute("""INSERT INTO ako_apps (org_id, token, program_id, name, phone, lang, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (oid, digest, p["id"], name, ph, body.get("lang") if body.get("lang") in LANGS else "ru",
                                                    v.id, now(), now())).lastrowid
        core.log_action(con, v.id, "ako_new", f"ako:{aid}")
    return {"id": aid, "token": token}


def update_app(con, v: Viewer, oid: int, aid: int, body: dict) -> dict:
    """The team's moves on a package: its status (passed to Academic Programs: review), a note, a new link (the old one
    stops), the interview moved or taken back with a reason the applicant reads on their page."""
    _team(con, v, oid, manage=True)
    out: dict = {}
    with tx(con):
        a = _of(con, oid, aid)
        if "status" in body:
            s = body["status"]
            if s not in STATUSES or s == "draft" or a["status"] == "draft":
                raise ApiError("bad_input", "status")  # a draft becomes a package only when its applicant sends it
            con.execute("UPDATE ako_apps SET status = ?, updated_at = ? WHERE id = ?", (s, now(), aid))
        if "note" in body:
            con.execute("UPDATE ako_apps SET note = ? WHERE id = ?", (str(body["note"] or "")[:2000].replace("\r", ""), aid))
        if "program" in body:
            p = one(con, "SELECT id, interview FROM ako_programs WHERE org_id = ? AND key = ?", oid, body["program"])
            if not p:
                raise ApiError("bad_input", "program")
            con.execute("UPDATE ako_apps SET program_id = ?, slot_id = CASE WHEN ? THEN slot_id END, updated_at = ? WHERE id = ?",
                        (p["id"], p["interview"], now(), aid))
        if "slot" in body:
            if body["slot"] is None:
                reason = _line(body.get("reason"), 200)
                if a["slot_id"] and not reason:
                    raise ApiError("bad_input", "reason")
                con.execute("UPDATE ako_apps SET slot_id = NULL, rebook = ?, updated_at = ? WHERE id = ?",
                            (reason or None if a["slot_id"] else a["rebook"], now(), aid))
            else:
                s = one(con, "SELECT id, cap FROM ako_slots WHERE id = ? AND org_id = ?", body["slot"], oid) \
                    if isinstance(body["slot"], int) and not isinstance(body["slot"], bool) else None
                if not s:
                    raise ApiError("not_found", "ako_slot")
                if s["id"] != a["slot_id"] and one(con, "SELECT COUNT(*) FROM ako_apps WHERE slot_id = ?", s["id"])[0] >= s["cap"]:
                    raise ApiError("full", "ako_slot_taken")  # the team may book inside the cutoff, never over a seat
                con.execute("UPDATE ako_apps SET slot_id = ?, rebook = NULL, updated_at = ? WHERE id = ?", (s["id"], now(), aid))
        if body.get("newLink") is True:
            token, digest = new_token()
            con.execute("UPDATE ako_apps SET token = ? WHERE id = ?", (digest, aid))
            out["token"] = token
        core.log_action(con, v.id, "ako_update", f"ako:{aid}", json.dumps({k: body[k] for k in ("status", "slot", "program") if k in body}))
    return out


def drop_app(con, v: Viewer, oid: int, aid: int) -> None:
    """The package and its files gone for good (asked to, or done with): the link stops."""
    _team(con, v, oid, manage=True)
    with tx(con):
        _of(con, oid, aid)
        paths = [r[0] for r in rows(con, "SELECT path FROM ako_files WHERE app_id = ?", aid)]
        con.execute("DELETE FROM ako_apps WHERE id = ?", (aid,))
        core.log_action(con, v.id, "ako_drop", f"ako:{aid}")
    _unlink(root_of(con), paths)


def add_slots(con, v: Viewer, oid: int, body: dict) -> None:
    """A day's interview times in one go: {day, times: ["10:00", ...], minutes, cap?, who?, teams?}. The day's Teams
    link is kept for the day (each slot may have its own later). A time already there for that interviewer is skipped."""
    _team(con, v, oid, manage=True)
    day, times = body.get("day"), body.get("times")
    minutes, cap = body.get("minutes", 30), body.get("cap", 1)
    if not isinstance(day, str) or not _DAY.fullmatch(day) or not isinstance(times, list) or not 1 <= len(times) <= 48 \
            or not all(isinstance(t, str) and _HM.fullmatch(t) for t in times) \
            or not isinstance(minutes, int) or not 5 <= minutes <= 240 or not isinstance(cap, int) or not 1 <= cap <= 50:
        raise ApiError("bad_input")
    teams = _meet(body.get("teams"))
    who = _line(body.get("who"), 80)
    try:
        starts = sorted({core.at(day, t) for t in times})
    except ValueError:
        raise ApiError("bad_input") from None
    if starts[0] <= now():
        raise ApiError("bad_input", "past")
    with tx(con):
        for t in starts:
            con.execute("""INSERT OR IGNORE INTO ako_slots (org_id, starts_at, minutes, cap, who, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (oid, t, minutes, cap, who, v.id, now()))
        if teams:
            con.execute("""INSERT INTO ako_days (org_id, day, teams) VALUES (?, ?, ?)
                ON CONFLICT (org_id, day) DO UPDATE SET teams = excluded.teams""", (oid, day, teams))


def _meet(x: object) -> str | None:
    """A Teams meeting link, or nothing: only Microsoft's hosts (the applicant taps it)."""
    s = x.strip() if isinstance(x, str) else ""
    if not s:
        return None
    if not _MEET.fullmatch(s) or core.online_url(s) is None:
        raise ApiError("bad_input", "teams")
    return s


def set_day(con, v: Viewer, oid: int, body: dict) -> None:
    """A day's Teams link (none: cleared)."""
    _team(con, v, oid, manage=True)
    day = body.get("day")
    if not isinstance(day, str) or not _DAY.fullmatch(day):
        raise ApiError("bad_input")
    teams = _meet(body.get("teams"))
    with tx(con):
        if teams:
            con.execute("""INSERT INTO ako_days (org_id, day, teams) VALUES (?, ?, ?)
                ON CONFLICT (org_id, day) DO UPDATE SET teams = excluded.teams""", (oid, day, teams))
        else:
            con.execute("DELETE FROM ako_days WHERE org_id = ? AND day = ?", (oid, day))


def update_slot(con, v: Viewer, oid: int, sid: int, body: dict) -> None:
    """A slot's own Teams link, interviewer, or seats (never under those booked)."""
    _team(con, v, oid, manage=True)
    with tx(con):
        s = one(con, "SELECT * FROM ako_slots WHERE id = ? AND org_id = ?", sid, oid)
        if not s:
            raise ApiError("not_found")
        if "teams" in body:
            con.execute("UPDATE ako_slots SET teams = ? WHERE id = ?", (_meet(body["teams"]), sid))
        if "who" in body:
            con.execute("UPDATE ako_slots SET who = ? WHERE id = ?", (_line(body["who"], 80), sid))
        if "cap" in body:
            cap = body["cap"]
            if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 50 \
                    or cap < one(con, "SELECT COUNT(*) FROM ako_apps WHERE slot_id = ?", sid)[0]:
                raise ApiError("bad_input", "cap")
            con.execute("UPDATE ako_slots SET cap = ? WHERE id = ?", (cap, sid))


def drop_slot(con, v: Viewer, oid: int, sid: int, force: bool = False, reason: object = None) -> int:
    """A time removed: gone for applicants at once. A booked one only with force (the app asked first); its
    applicants read the reason on their page and pick again. Returns how many were booked."""
    _team(con, v, oid, manage=True)
    with tx(con):
        s = one(con, "SELECT id FROM ako_slots WHERE id = ? AND org_id = ?", sid, oid)
        if not s:
            raise ApiError("not_found")
        n = one(con, "SELECT COUNT(*) FROM ako_apps WHERE slot_id = ?", sid)[0]
        if n and not force:
            raise ApiError("conflict", "ako_slot_booked", {"booked": n})
        con.execute("UPDATE ako_apps SET rebook = ?, updated_at = ? WHERE slot_id = ?", (_line(reason, 200) or "-", now(), sid))
        con.execute("DELETE FROM ako_slots WHERE id = ?", (sid,))
        core.log_action(con, v.id, "ako_slot_drop", f"org:{oid}", json.dumps({"booked": n}))
    return n


# ---------------------------------------------------------------- data and the night

def seed(con, oid: int) -> int:
    """The programs from i18n/ako.json for this org (admin CLI, qa.py): new ones added, known ones updated in place
    (their packages keep pointing at them). Returns how many."""
    data = json.loads(DATA.read_text(encoding="utf-8"))["programs"]
    with tx(con):
        for n, p in enumerate(data):
            for k in ("first", "later", "optional"):
                if not set(p[k]) <= set(DOCS):
                    raise ValueError(f"{p['key']}: unknown document in {k}")
            info = json.dumps({lang: p[lang] for lang in LANGS}, ensure_ascii=False)
            con.execute("""INSERT INTO ako_programs (org_id, key, kind, info, url, interview, first, later, optional, sort)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (org_id, key) DO UPDATE SET kind = excluded.kind, info = excluded.info,
                url = excluded.url, interview = excluded.interview, first = excluded.first, later = excluded.later,
                optional = excluded.optional, sort = excluded.sort""",
                        (oid, p["key"], p["kind"], info, p["url"], int(p["interview"]), ",".join(p["first"]), ",".join(p["later"]),
                         ",".join(p["optional"]), n))
    return len(data)


def sweep(con) -> None:
    """Nightly (daily.stats_day): drafts never sent go DRAFT_KEEP after their last change, sent packages KEEP after
    sending, with their files; a starter's address hash after a day; past slots nobody holds."""
    t = now()
    with tx(con):
        gone = rows(con, """SELECT id FROM ako_apps WHERE (status = 'draft' AND updated_at < ?) OR (sent_at IS NOT NULL AND sent_at < ?)""",
                    t - DRAFT_KEEP, t - KEEP)
        ids = [r[0] for r in gone]
        paths = [r[0] for r in rows(con, f"SELECT path FROM ako_files WHERE app_id IN ({core._qs(ids)})", *ids)] if ids else []
        if ids:
            con.execute(f"DELETE FROM ako_apps WHERE id IN ({core._qs(ids)})", ids)
        con.execute("UPDATE ako_apps SET ip = NULL WHERE ip IS NOT NULL AND created_at < ?", (t - IP_KEEP,))
        con.execute("""DELETE FROM ako_slots WHERE starts_at < ? AND id NOT IN (SELECT slot_id FROM ako_apps WHERE slot_id IS NOT NULL)""",
                    (t - 30 * 86400,))
    _unlink(root_of(con), paths)
