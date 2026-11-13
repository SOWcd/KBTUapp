"""HTTP layer (SPEC §6): FastAPI routes over logic.py, the Telegram initData check, sign-in with KBTU, share
cards, and the built frontend with an SPA fallback.

Run from server/:  .venv/bin/uvicorn kbtu.app:create --factory --port 8080
Routes cover what the frontend's Api interface calls (web/src/lib/api/index.ts); the rest of SPEC §6 comes
with the screens that need it. Handlers that only touch SQLite are plain functions (FastAPI runs them in its
thread pool); those that wait on the network (Telegram) are async."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import mimetypes
import re
import secrets
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Annotated, Any

import anyio
import httpx
from fastapi import Body, Depends, FastAPI, Header, Query, Request
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.utils import get_typed_return_annotation
from fastapi.routing import APIRoute
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import ai, auth, bot, calpage, casting, checkin as qr, config, db, docs, llm, logic, media, mirror, msauth, receipt, roster, texts, video
from .logic import ApiError, Viewer

log = logging.getLogger("kbtu.app")
# httpx logs every request URL at INFO, and Telegram's URL carries the bot token
logging.getLogger("httpx").setLevel(logging.WARNING)
# pictures queue here for one of two threads, not in the shared pool: a burst of uploads waiting on media's lock
# inside pool threads would hold all 40 and stall every other request
_imgs = anyio.CapacityLimiter(2)


async def _img(fn, *args):
    return await anyio.to_thread.run_sync(fn, *args, limiter=_imgs)


async def _picture(fn, *args):
    """An uploaded picture through fn (media.save, receipt.take) in _img's threads; not a picture: bad_input."""
    try:
        return await _img(fn, *args)
    except media.BadImage:
        raise ApiError("bad_input", "not_an_image") from None

THREADS = 16               # see lifespan
SEEN_EVERY = 600            # refresh users.seen_at and Telegram names at most every 10 min
NAME, STUDENT_ID = logic.NAME, logic.STUDENT_ID  # typed in by the student (the KBTU-password sign-in is gone since Oct 19)


async def read_upload(request: Request) -> bytes:
    """An upload's bytes: the file itself is the body (no multipart), at most media.MAX_BYTES."""
    if int(request.headers.get("content-length") or 0) > media.MAX_BYTES:
        raise ApiError("bad_input", "too_big")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > media.MAX_BYTES:
            raise ApiError("bad_input", "too_big")
    return bytes(data)


class _Route(APIRoute):
    """Answers go out through pydantic's JSON writer (Rust) instead of FastAPI's jsonable_encoder, which walks every value
    in Python: two thirds of the Afisha's time on a big database (load test). Our answers are plain JSON
    already, so `Any` checks nothing and only changes who writes the bytes."""

    def __init__(self, path: str, endpoint, *, response_model=Default(None), status_code: int | None = None, **kw) -> None:
        if isinstance(response_model, DefaultPlaceholder) and get_typed_return_annotation(endpoint) is None and status_code != 204:
            response_model = Any
        super().__init__(path, endpoint, response_model=response_model, status_code=status_code, **kw)


# ------------------------------------------------------------ who is calling

async def conn(request: Request) -> AsyncIterator[sqlite3.Connection]:
    # async: taking a kept connection and giving it back are a queue's get and put, so they run on the loop; as a plain
    # generator FastAPI sent each into the thread pool, two of a request's four thread hops (perf round 4: -9% server CPU
    # per request under load)
    logic.core.CALLER.set({})  # on the loop, so the route's threads share it (viewer fills it in)
    with request.app.state.pool.conn() as con:
        yield con


# every route's connection and caller (create() keeps the pool and the config in app.state)
Con = Annotated[sqlite3.Connection, Depends(conn)]

def viewer(request: Request, con: Con) -> Iterator[Viewer]:
    cfg = request.app.state.cfg
    head = request.headers.get("authorization", "")
    tg = auth.check_init_data(head[4:], cfg.bot_token) if head.startswith("tma ") else None
    if not tg:
        raise ApiError("forbidden", "init_data")
    request.state.tg = tg
    v = _upsert(con, tg, cfg.admins)
    if (caller := logic.core.CALLER.get()) is not None:
        caller["student"] = v.student  # person_ref: the real name beside a nick only for students
    if (oid := request.headers.get("x-staff-org")) is not None:
        # Admin → "an event for a club": the app's admin (never a moderator) makes a club's draft and uploads its cover
        # without a role in it, and may fill it from the club's announcement (the AI, nothing stored). Only these routes; the draft is then run through X-Staff-Event like any other
        o = logic.one(con, "SELECT id FROM orgs WHERE id = ? AND status = 'active'", int(oid)) if oid.isascii() and oid.isdigit() and len(oid) < 12 else None
        route = (request.method, request.scope["route"].path)
        # the creator alone acts as the club's President there (core.can, lent_full), so his video uploads too
        full = v.role == "admin" and bool(logic.one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)[0])
        if v.role != "admin" or not o or "x-staff-event" in request.headers or not (
                route == ("POST", "/api/photos") or full and route == ("POST", "/api/videos")
                or route in (("POST", "/api/orgs/{oid}/events"), ("POST", "/api/orgs/{oid}/events/fill")) and str(request.path_params.get("oid")) == oid):
            raise ApiError("forbidden", "staff")
        yield Viewer(v.id, v.role, v.student, staff_org=o["id"], lent_full=full)
        if route[1] in ("/api/photos", "/api/videos"):  # reached only when the upload was kept; the draft itself: logic.staff_create_event
            logic.log_action(con, v.id, "staff_photo" if route[1] == "/api/photos" else "staff_video", f"org:{oid}")
        return
    if (eid := request.headers.get("x-staff-event")) is None:
        yield v
        return
    # Admin → an event: the app's admin acts as its organizers (logic.can, STAFF_RIGHTS), only on that event's own
    # routes and only for this request; anyone else sending it, or on another route, is refused
    e = logic.one(con, "SELECT org_id, created_by FROM events WHERE id = ?", int(eid)) if eid.isascii() and eid.isdigit() and len(eid) < 12 else None
    if v.role != "admin" or not e or str(request.path_params.get("eid")) != eid:
        raise ApiError("forbidden", "staff")
    # the creator runs the events he made for a club (Admin's "an event for a club") as their President would (core.can)
    full = e["created_by"] == v.id and bool(logic.one(con, "SELECT is_founder FROM users WHERE id = ?", v.id)[0])
    v = Viewer(v.id, v.role, v.student, staff_org=e["org_id"], lent_full=full)
    yield v
    # reached only when the route answered: every write and every list of people (attendees, a meeting's answers, the
    # volunteers) the owner's log names; the event's own card alone isn't
    if v.used and (request.method != "GET" or request.scope["route"].path != "/api/events/{eid}"):
        logic.log_action(con, v.id, "staff_event", f"event:{eid}", json.dumps({"do": f"{request.method} {request.scope['route'].path}", **({"full": True, "org": v.staff_org} if v.lent_full else {})}))

def _upsert(con, tg: dict, admins: frozenset[int]) -> Viewer:
    """The Telegram user as our user: created on the first call, names and photo kept fresh (SPEC §5)."""
    t = logic.now()
    photo = tg.get("photo_url") if str(tg.get("photo_url") or "").startswith("https://t.me/") else None
    fresh = (tg.get("username"), tg.get("first_name") or "", tg.get("last_name") or "", photo)
    dm = int(bool(tg.get("allows_write_to_pm")))
    u = logic.one(con, "SELECT * FROM users WHERE tg_id = ?", tg["id"])
    if u is None:
        lang = str(tg.get("language_code") or "")[:2]
        con.execute("""INSERT OR IGNORE INTO users (tg_id, tg_username, tg_first_name, tg_last_name, tg_photo_url, lang, role, can_dm, created_at, seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (tg["id"], *fresh, lang if lang in ("ru", "kk", "en") else "ru",
                                                     "admin" if tg["id"] in admins else "user", dm, t, t))
        u = logic.one(con, "SELECT * FROM users WHERE tg_id = ?", tg["id"])
        logic.visit(con, u["id"], t)
    else:
        # ADMIN_TG_IDS are always admins; everyone else's role is given in the app
        env = tg["id"] in admins
        role = "admin" if env and not u["banned_at"] else u["role"]  # a ban outranks the env
        dm = max(dm, u["can_dm"])  # only the bot turns it off (when Telegram says it's blocked)
        if (u["tg_username"], u["tg_first_name"], u["tg_last_name"], u["tg_photo_url"]) != fresh or (role, dm) != (u["role"], u["can_dm"]) \
                or t - u["seen_at"] > SEEN_EVERY or logic.day_of(t) != logic.day_of(u["seen_at"]):
            def fresh_seen() -> None:  # one short transaction, skipped while a burst holds the lock: every GET comes here
                # role and can_dm from the row as it is now, never from the read above: a demotion or ban (or the bot's
                # "blocked") landing in between must not be written back
                con.execute("""UPDATE users SET tg_username = ?, tg_first_name = ?, tg_last_name = ?, tg_photo_url = ?,
                    role = CASE WHEN ? AND banned_at IS NULL THEN 'admin' ELSE role END, can_dm = MAX(can_dm, ?), seen_at = ?
                    WHERE id = ?""", (*fresh, int(env), int(bool(tg.get("allows_write_to_pm"))), t, u["id"]))
                logic.visit(con, u["id"], t)
            db.maybe(con, fresh_seen)
            u = logic.one(con, "SELECT * FROM users WHERE id = ?", u["id"])
    if u["banned_at"]:
        raise ApiError("forbidden", "banned", logic.ban_info(con, u["id"]))
    # a typed-in row (manual, no Microsoft yet) acts as nobody until Microsoft confirms it (Microsoft only)
    return Viewer(u["id"], u["role"], logic.one(con, "SELECT 1 FROM students WHERE user_id = ? AND manual = 0", u["id"]) is not None)


Me = Annotated[Viewer, Depends(viewer)]


def forum_viewer(request: Request, v: Me, con: Con) -> Viewer:
    """The forum (logic/forum.py) while it's tried out: FORUM=1 the app's staff, FORUM=founder the Creator alone
    (no new policy version then: nobody else is asked anything)."""
    cfg = request.app.state.cfg
    if not (cfg.forum or cfg.forum_founder):
        raise ApiError("not_found")
    if cfg.forum and v.role in ("admin", "moderator"):
        return v
    if cfg.forum_founder and logic.one(con, "SELECT 1 FROM users WHERE id = ? AND is_founder = 1", v.id):
        return v
    raise ApiError("forbidden")


Forum = Annotated[Viewer, Depends(forum_viewer)]


def board_on(cfg, v: Viewer) -> bool:
    """The policy's section 12 is in force for this person (BOARD=1 everyone, BOARD=staff the admins and moderators):
    the assistant, an event's sign-up questions, the map's flaws. Its old in-app forum is off for good (its code removed):
    the forum channel replaced it (Nov 1), migration 103 deleted its threads."""
    return cfg.board == "all" or cfg.board == "staff" and v.role in ("admin", "moderator")


def board_viewer(request: Request, v: Me) -> Viewer:
    if not board_on(request.app.state.cfg, v):
        raise ApiError("not_found")
    return v


Board = Annotated[Viewer, Depends(board_viewer)]


def _eu_only() -> None:
    """This request's student agreed to an earlier policy, not the one in force. Nobody is asked to accept again (owner,
    Nov 13: no policy screen at all, until he says), so they write as before, and their text is looked at only on the EU
    host (ai.EU_ONLY: what every earlier policy named), never by the other providers the policy in force added."""
    (logic.core.CALLER.get() or {})["eu"] = True


def _ai_only(usual: tuple[str, ...]) -> tuple[str, ...]:
    return ai.EU_ONLY if (logic.core.CALLER.get() or {}).get("eu") else usual


def _ai_eu() -> dict:
    """For the forum's checks: nothing to add on the usual day."""
    return {"only": ai.EU_ONLY} if (logic.core.CALLER.get() or {}).get("eu") else {}


def board_writer(request: Request, v: Board, con: Con) -> Viewer:
    """Writing on the forum, asking the assistant: someone on an earlier policy is not refused (_eu_only).
    Staff trying it (BOARD=staff) are on the policy they have."""
    s = logic.one(con, "SELECT consent_version FROM students WHERE user_id = ?", v.id)
    if request.app.state.cfg.board == "all" and s and not logic.account.on_policy(s[0], request.app.state.policy) and s[0] not in ("staff", "admin"):
        _eu_only()
    return v


BoardWrite = Annotated[Viewer, Depends(board_writer)]


def fchan_viewer(request: Request, v: Me) -> Viewer:
    """The forum channel (FORUM_CHANNEL): off, none of it is here."""
    if not request.app.state.cfg.forum_channel:
        raise ApiError("not_found")
    return v


FChan = Annotated[Viewer, Depends(fchan_viewer)]


def fchan_writer(request: Request, v: FChan, con: Con) -> Viewer:
    """Posting to the channel: a student Microsoft confirmed (a typed-in ID could be anyone's), on the policy in force
    (public posts, the AI's cross-border look)."""
    logic.need_student(v)
    s = logic.one(con, "SELECT manual, consent_version FROM students WHERE user_id = ?", v.id)
    if not s or s["manual"]:
        raise ApiError("need_student")
    if not logic.account.on_policy(s["consent_version"], request.app.state.policy) and s["consent_version"] != "admin":
        _eu_only()
    return v


FChanWrite = Annotated[Viewer, Depends(fchan_writer)]


def policy_for(con, v: Viewer, policy: str) -> str:
    """The policy version this person is asked to agree to: with the volunteers ledger's section only for those it concerns."""
    return policy + logic.account.CONSENT_VOL if logic.vol.concerned(con, v) else policy


def vol_viewer(request: Request, v: Me, con: Con) -> Viewer:
    """The volunteers ledger (logic/vol.py): someone it concerns uses it only once agreed to its part of the policy (+vol1)."""
    s = logic.one(con, "SELECT consent_version FROM students WHERE user_id = ?", v.id)
    want = policy_for(con, v, request.app.state.policy)
    if s and want != request.app.state.policy and s[0] not in (want, "staff", "admin"):
        raise ApiError("forbidden", "consent")
    return v


VolMe = Annotated[Viewer, Depends(vol_viewer)]


def appeals_viewer(request: Request, v: Me, con: Con) -> Viewer:
    """Appeals to SG (logic/appeals.py): APPEALS=1 everyone, staff the admins, moderators and SG's people; off: not here."""
    if not logic.appeals.on(con, request.app.state.cfg.appeals, v):
        raise ApiError("not_found")
    return v


Appeals = Annotated[Viewer, Depends(appeals_viewer)]


def reports_viewer(request: Request, v: Me) -> Viewer:
    """Clubs' event reports (logic/evreports.py): REPORTS=1; off, not here (their policy clause comes first)."""
    if not request.app.state.cfg.reports:
        raise ApiError("not_found")
    return v


Reports = Annotated[Viewer, Depends(reports_viewer)]


def create(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.load()
    logic.core._SHARED.clear(); logic.profiles._RARITY[0] = 0  # per-worker caches belong to one database (tests make many)
    def after(con) -> None:
        logic.sync_levels(con)  # a new achievement or level counts what students already did
        logic.name_slugs(con)
        logic.fill_abbrs(con)
        logic.refill(con)  # migration 135's freed seats to the waitlists
        if cfg.seed:
            logic.seed_schools(con, Path(cfg.db_path).resolve().parent / "media")  # KBTU's schools, once
    db.init(cfg.db_path, after=after)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        # the sync routes' thread pool: anyio's default 40 threads fought over the one GIL (SQLite lets it go on every
        # call): under load a request cost 24 ms of CPU, 10 with 16 threads, twice the requests a second (perf round 4)
        # ponytail: one number for every route; a route that blocks long belongs on its own limiter (_imgs) instead
        anyio.to_thread.current_default_thread_limiter().total_tokens = THREADS
        task = asyncio.create_task(bot.run(cfg)) if cfg.background else None
        yield
        if task:
            task.cancel()
        if http := getattr(app.state, "http", None):
            await http.aclose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)  # JSON lists; pictures and video are excluded

    def ai_http() -> httpx.AsyncClient:
        """One client for the AI calls (keep-alive: a new one per request paid DNS and TLS each time)."""
        if getattr(app.state, "http", None) is None:
            app.state.http = httpx.AsyncClient()
        return app.state.http
    app.router.route_class = _Route
    dist = Path(cfg.web_dist).resolve()
    photos = Path(cfg.db_path).resolve().parent / "media"   # next to the database: one volume to back up
    receipts = Path(cfg.db_path).resolve().parent / "receipts"   # private (§4.3): never under /media, only through the API
    # the "To calendar" link is signed by one worker and may be opened on another: one key for all, from the env
    logic.seats.ICS_KEY = hmac.new(cfg.token_key, b"kbtu-ics", hashlib.sha256).digest()
    logic.seats.REF_KEY = hmac.new(cfg.token_key, b"kbtu-event-ref", hashlib.sha256).digest()  # "My link"'s code
    logic.vol.ORG = cfg.volunteers  # the volunteers ledger's club (VOLUNTEERS); empty: off
    logic.gallery.MODE = cfg.gallery  # GALLERY: who posts to the Gallery ("all", "staff"); empty: the albums alone
    logic.chatsync.POLICY = logic.policy(cfg) if cfg.chat_sync else ""  # clubs mirrored from their chats (CHAT_SYNC); empty: off
    logic.vol.KEY = hmac.new(cfg.token_key, b"kbtu-vol", hashlib.sha256).digest()  # deleted people's import keys, hashed
    logic.core.MS_AGE_CUTOFF = cfg.ms_age_cutoff or None  # free 1st-year seats by account age: off unless set
    logic.assistant.KEY = hmac.new(cfg.token_key, b"kbtu-assist", hashlib.sha256).digest()  # an answer's topic, signed for its vote
    logic.assistant.DOCS = docs.Index(cfg.docs_db) if cfg.docs else None  # the university's documents (DOCS; kbtu/docs.py)
    if cfg.docs and not logic.assistant.DOCS.ready():
        log.warning("DOCS is on but %s doesn't open: the assistant answers without the documents", cfg.docs_db)
    logic.profiles.QR_KEY = hmac.new(cfg.token_key, b"kbtu-badge-qr", hashlib.sha256).digest()  # Admin → Awards → Show QR

    # ------------------------------------------------------------ errors

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({**exc.extra, "error": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, __: RequestValidationError) -> JSONResponse:
        # FastAPI's default answer echoes the input back, and the input may hold a KBTU password
        return JSONResponse({"error": "bad_input", "message": ""}, status_code=400)

    @app.exception_handler(OverflowError)
    async def too_big(_: Request, __: OverflowError) -> JSONResponse:
        # an id past SQLite's 64-bit integers (only a hand-made request sends one): a bad request, not a crash
        return JSONResponse({"error": "bad_input", "message": ""}, status_code=400)

    pool = db.Pool(cfg.db_path)
    app.state.pool, app.state.cfg = pool, cfg  # conn() and viewer() find them there

    # ------------------------------------------------------------ me and sign-in

    policy = logic.policy(cfg)  # the version in force (logic/account.py)
    ai_on = logic.ai_on(cfg)
    # off (BOARD=staff, FORUM=founder): the visible policy names the EU host alone, so staff-only AI stays on it
    assist_only = ai.ASSIST_PROVIDERS if ai_on else ai.EU_ONLY
    screen_only = ai.PUBLIC_PROVIDERS if ai_on else ai.EU_ONLY
    if cfg.forum_channel and not cfg.tgc_chat:  # a deleted post's copy in its discussion group would stay with the words
        log.warning("FORUM_CHANNEL is set without FORUM_GROUP: deleted posts' copies in its discussion group stay")
    app.state.policy = policy

    @app.get("/api/me")
    def get_me(con: Con, v: Me):
        return logic.me(con, v) | {"consentNow": policy_for(con, v, policy), "board": board_on(app.state.cfg, v), "support": logic.account.support(con),
                                   **({"forumChannel": True} if app.state.cfg.forum_channel else {}),
                                   **({"reports": logic.evreports.summary(con, v)} if app.state.cfg.reports else {}),  # Studio's event reports (REPORTS): my consent
                                   "teams": logic.evteams.summary(con, v),  # team events' own consent (evteams.CONSENT)
                                   # the voluntary support page's number: shown, never recorded (no env: no key, no row)
                                   **({"donate": app.state.cfg.donate_phone} if app.state.cfg.donate_phone else {}),
                                   **({"tgComment": True} if cfg.tgc_chat and logic.tgcomments.saved(con, v) else {}),
                                   **({"vol": x} if (x := logic.vol.summary(con, v)) else {}),
                                   **({"appeals": logic.appeals.summary(con, v)} if logic.appeals.on(con, cfg.appeals, v) else {})}

    @app.patch("/api/me")
    def patch_me(con: Con, v: Me, body: dict = Body(...)):
        return logic.update_me(con, v, body)

    @app.get("/api/me/delete")
    def delete_info(con: Con, v: Me):
        return logic.delete_info(con, v)

    @app.post("/api/me/delete")
    def ask_delete(con: Con, v: Me, body: dict | None = Body(None)):
        """§4.8: in a week, with the way back meanwhile (logic.ask_delete); the bot's round runs it (bot.send_due)."""
        return logic.ask_delete(con, v, (body or {}).get("photos") is True)

    @app.post("/api/me/consent")
    def consent(con: Con, v: Me, body: dict = Body(...)):
        logic.consent(con, v, body.get("version"), policy_for(con, v, policy))
        return get_me(con, v)  # all of /api/me (its vol part too): the app replaces its copy with this

    @app.post("/api/me/dm")
    def dm_on(con: Con, v: Me, body: dict | None = Body(None)):
        return logic.dm_on(con, v, (body or {}).get("event"))

    @app.post("/api/donate/stars")
    async def donate_stars(con: Con, v: Me, body: dict = Body(...)):
        lang = logic.one(con, "SELECT lang FROM users WHERE id = ?", v.id)[0]
        return {"url": await logic.stars.invoice(app.state.cfg, ai_http(), v.id, lang, body.get("amount"))}

    @app.post("/api/me/keep")
    def keep_me(con: Con, v: Me):
        return logic.keep_me(con, v)

    # ------------------------------------------------------------ admin: clubs and their teams (pilot)

    @app.get("/api/admin/orgs")
    def admin_orgs(con: Con, v: Me):
        return logic.admin_orgs(con, v)

    @app.get("/api/admin/orgs/{oid}/events")
    def admin_org_events(oid: int, con: Con, v: Me):
        return logic.admin_org_events(con, v, oid)

    @app.post("/api/admin/orgs")
    def admin_create_org(con: Con, v: Me, body: dict = Body(...)):
        return logic.admin_create_org(con, v, body)

    @app.post("/api/admin/orgs/{oid}/president-link")
    def admin_president_link(oid: int, con: Con, v: Me):
        return logic.president_link(con, v, oid)  # the QR the admin shows a President face to face

    @app.put("/api/admin/orgs/{oid}/hidden")
    def admin_hide_org(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.admin_hide_org(con, v, oid, bool(body.get("hidden")))

    @app.put("/api/admin/orgs/{oid}/role")
    def admin_set_role(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.admin_set_role(con, v, oid, body)

    @app.post("/api/kbtu/manual")
    def kbtu_manual(con: Con, v: Me, body: dict = Body(...)):
        """After Microsoft, someone new types the student ID and year (Microsoft knows neither: KBTU leaves employeeId
        empty, measured Oct 20), so the ID is the student's word, tied to a real @kbtu.kz account. Microsoft only
        no pending Microsoft sign-in, no account. An ID held by a typed-in row with no Microsoft goes
        to the Microsoft one; held by a Microsoft-confirmed one, it's refused and sorted without admins (id_clash)."""
        consent = str(body.get("consentVersion") or "")
        sid = str(body.get("studentId") or "").strip().upper()
        course = logic.course_of(sid)  # the ID says the year (audit M3: a typed "1" took free first-year seats); None: a year ahead
        ms = logic.ms_pending(con, v.id)
        # the account's names when Microsoft has them (ms_link writes them anyway); typed only where it has none
        names = [(" ".join(str((ms or {}).get(m) or "").split())[:40], " ".join(str(body.get(k) or "").split()))
                 for m, k in (("first", "firstName"), ("last", "lastName"))]
        first, last = (mine or typed for mine, typed in names)
        if not logic.account.on_policy(consent, policy):
            raise ApiError("bad_input", "consent")  # an app opened before the policy changed: it says to reopen
        if not (all(mine or NAME.fullmatch(typed) for mine, typed in names) and STUDENT_ID.fullmatch(sid)
                and isinstance(course, int) and not isinstance(course, bool) and 1 <= course <= 6):
            raise ApiError("bad_input")
        if not ms:
            raise ApiError("forbidden", "ms_first")
        if STUDENT_ID.fullmatch(ms.get("employeeId") or "") and ms["employeeId"] != sid:
            raise ApiError("conflict", "sid_mismatch")  # empty at KBTU today (measured Oct 20); kept for the day they fill it
        now = logic.now()
        with db.tx(con):
            if logic.one(con, "SELECT 1 FROM students WHERE user_id = ?", v.id):
                raise ApiError("conflict", "verified")  # a row already: Microsoft confirms it, nothing to type
            ms = logic.ms_pending(con, v.id)
            if not ms:
                raise ApiError("forbidden", "ms_first")
            if logic.one(con, "SELECT 1 FROM students WHERE ms_oid = ?", ms["oid"]):
                raise ApiError("conflict", "linked")  # that Microsoft account got linked to another Telegram meanwhile
            taken = logic.one(con, "SELECT user_id, manual, ms_oid FROM students WHERE student_id = ?", sid)
            held = taken and not (taken["manual"] and taken["ms_oid"] is None)
            if held:
                logic.id_clash(con, sid, v.id, taken["user_id"])  # the holder asked to check theirs; I hear once it's freed
            if taken and not held:
                for t in ("students", "schedule_classes"):  # typed in, never confirmed: gives way (as admin.py unlink)
                    con.execute(f"DELETE FROM {t} WHERE user_id = ?", (taken["user_id"],))
            if not held:
                con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
                        synced_at, manual) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""", (v.id, sid, first, last, course, consent, now, now, now))
                logic.ms_link(con, v.id, ms)
                qr.became_student(con, v.id)  # a QR scan waiting for the sign-up counts now
        if held:  # after the commit: the admins' message stays
            raise ApiError("conflict", "sid_taken")  # someone with a real account holds it: the admin sorts it out
        return logic.me(con, Viewer(v.id, v.role, True))

    # ------------------------------------------------------------ check-in by a QR on a big screen (checkin.py)

    # the laptop (no Telegram): a pairing code, then what to show; its secret in a header, never in a URL
    @app.post("/api/screen/pair")
    def screen_pair(request: Request, con: Con):
        # the visitor's address through Cloudflare's tunnel (the socket's peer is the tunnel itself)
        return qr.pair(con, cfg.token_key, request.headers.get("cf-connecting-ip") or (request.client.host if request.client else ""))

    @app.get("/api/screen")
    def screen_show(con: Con, x_screen: str = Header("")):
        return qr.screen(con, cfg.token_key, x_screen)

    # the organizer's phone: pair a screen, run the session, the list
    @app.get("/api/screens")
    def screen_sessions(con: Con, v: Me):
        return qr.sessions(con, cfg.token_key, v)

    @app.post("/api/screens/bind")
    def screen_bind(con: Con, v: Me, body: dict = Body(...)):
        sid = body.get("session")
        return qr.bind(con, cfg.token_key, v, str(body.get("code") or ""), int(sid) if isinstance(sid, int) else None)

    @app.post("/api/orgs/{oid}/screens")
    def club_screen(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return qr.club_new(con, cfg.token_key, v, oid, body.get("title"), body.get("who", "club"))

    @app.post("/api/events/{eid}/screen")
    def event_screen(eid: int, con: Con, v: Me):
        return qr.for_event(con, cfg.token_key, v, eid)

    # an event's team marked (checkin.crew): the one there is (GET), made with who is expected (POST)
    @app.get("/api/events/{eid}/crew-screen")
    def crew_screen(eid: int, con: Con, v: Me):
        return qr.crew(con, cfg.token_key, v, eid)

    @app.post("/api/events/{eid}/crew-screen")
    def crew_screen_new(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return qr.crew(con, cfg.token_key, v, eid, body.get("who", "club"), body.get("title"))

    @app.post("/api/screens/{sid}/grant")
    def screen_grant(sid: int, con: Con, v: Me, body: dict = Body(...)):
        return qr.grant_all(con, v, sid, body.get("code"))

    @app.post("/api/screens/{sid}/badge")
    def screen_badge(sid: int, con: Con, v: Me, body: dict = Body(...)):
        return qr.badge(con, v, sid, body.get("qr"))

    @app.get("/api/screens/{sid}/absent")
    def screen_absent(sid: int, con: Con, v: Me):
        return qr.absent(con, v, sid)

    @app.get("/api/screens/{sid}/people")
    def screen_people(sid: int, con: Con, v: Me):
        return qr.people(con, v, sid)

    @app.post("/api/screens/{sid}/csv")
    def screen_csv_link(sid: int, con: Con, v: Me):
        return qr.csv_link(con, cfg.token_key, v, sid)

    # helpers, let in by a QR (checkin.py)
    @app.post("/api/screens/helper")
    def screen_helper(con: Con, v: Me, body: dict = Body(...)):
        return qr.helper(con, cfg.token_key, v, str(body.get("p") or ""), body.get("join") is True)

    @app.post("/api/screens/{sid}/helpers")
    def screen_hand(sid: int, con: Con, v: Me):
        return qr.hand(con, cfg.token_key, v, sid)

    @app.delete("/api/screens/{sid}/helpers")
    def screen_hands_off(sid: int, con: Con, v: Me):
        return qr.hands_off(con, cfg.token_key, v, sid)

    @app.post("/api/screens/{sid}/{act}")
    def screen_act(sid: int, act: str, con: Con, v: Me):
        return qr.control(con, cfg.token_key, v, sid, act)

    @app.get("/api/screen/{sid}/csv")
    def screen_csv(sid: int, e: int, k: str, con: Con):
        return Response(qr.export(con, cfg.token_key, sid, e, k), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="checkin-{sid}.csv"', "Cache-Control": "no-store"})

    @app.post("/api/checkin")
    def checkin_scan(con: Con, v: Me, body: dict = Body(...)):
        return qr.mark(con, cfg.token_key, v, str(body.get("p") or ""))

    @app.post("/api/ms/start")
    def ms_start(v: Me):
        """The Microsoft sign-in link for me (msauth.py); the Mini App opens it outside Telegram"""
        return {"url": msauth.link(cfg.token_key, v.id, cfg.domain)}

    @app.get("/api/ms/verifier")
    def ms_verifier(state: str, con: Con):
        """The PKCE verifier and whose Telegram the link is for: ms.html asks "link to <name>?" first, so a sign-in link
        forwarded to someone else can't tie their KBTU account to the sender's Telegram unseen"""
        uid = msauth.state_uid(cfg.token_key, state)
        u = logic.one(con, "SELECT tg_first_name, tg_last_name, tg_username FROM users WHERE id = ?", uid) if uid else None
        if not u:
            raise ApiError("not_found")  # a stale link: ms.html says "expired"
        name = f"{u['tg_first_name']} {u['tg_last_name']}".strip()
        if u["tg_username"]:
            name = f"{name} (@{u['tg_username']})".strip()
        return {"verifier": msauth.verifier(cfg.token_key, state), "name": name}

    @app.post("/api/ms/finish")
    async def ms_finish(body: dict = Body(...)):
        """/ms.html's last step: the state says who asked, the token who signed in. A student already in the app is
        confirmed; someone new is remembered until they type their student ID and year (kbtu_manual)."""
        state = str(body.get("state") or "")
        uid = msauth.state_uid(cfg.token_key, state)
        who = await msauth.identity(str(body.get("token") or "")) if uid else None
        if not who or who.get("refused") == "app":
            raise ApiError("forbidden", "ms")
        if who.get("refused"):
            raise ApiError("forbidden", "not_kbtu")  # a guest in KBTU's directory, or no @kbtu.kz login
        return await run_in_threadpool(_ms_finish, uid, who, state)

    def _ms_finish(uid: int, who: dict, state: str) -> dict:
        with pool.conn() as con, db.tx(con):
            if not con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)", (f"ms_used:{state[-16:]}", str(logic.now()))).rowcount:
                raise ApiError("forbidden", "ms")  # each link once
            # not applied here: the Mini App of the Telegram that started it takes it (/api/ms/claim)
            return {"claim": logic.ms_hold(con, uid, who)}

    @app.post("/api/ms/claim")
    def ms_claim(con: Con, v: Me, body: dict = Body(...)):
        """The app's ms_<secret> start link from /ms.html: the sign-in lands only on the Telegram that asked for it"""
        logic.ms_claim(con, v, str(body.get("claim") or ""))
        return {"ok": True}

    # ------------------------------------------------------------ the clubs' rosters (PLAN 95, roster.py)

    @app.post("/api/roster/seen", status_code=204)
    def roster_seen(con: Con, v: Me):
        roster.seen(con, v.id)

    @app.post("/api/roster/{rid}/claim", status_code=204)
    def roster_claim(rid: int, con: Con, v: Me):
        logic.need_student(v)
        roster.claim(con, v.id, rid)

    @app.get("/api/roster/requests")
    def roster_requests(con: Con, v: Me, org: int | None = None):
        return logic.roster_requests(con, v, org)

    @app.post("/api/roster/requests/{rid}", status_code=204)
    def roster_decide(rid: int, con: Con, v: Me, body: dict = Body(...)):
        if not isinstance(body.get("ok"), bool):
            raise ApiError("bad_input")
        roster.decide(con, v, rid, body["ok"])

    @app.get("/api/me/schedule")
    def my_schedule(con: Con, v: Me):
        return logic.schedule(con, v)

    @app.delete("/api/me/schedule", status_code=204)
    def drop_my_schedule(con: Con, v: Me):
        logic.drop_my_schedule(con, v)

    # ------------------------------------------------------------ events

    @app.get("/api/events")
    def list_events(con: Con, v: Me, frm: int | None = Query(None, alias="from"), to: int | None = None,
            org: int | None = None):
        return logic.events(con, v, frm, to, org)

    @app.get("/api/events/past")
    def list_past(con: Con, v: Me, org: int | None = None, mine: bool = False):
        return logic.past_events(con, v, org, mine)

    @app.get("/api/gallery")
    def gallery(con: Con, v: Me, before: int | None = Query(None, ge=0, lt=1 << 62), limit: int = Query(logic.gallery.PAGE, ge=1, le=logic.gallery.PAGE),
            topic: str | None = Query(None, max_length=16)):
        return logic.gallery.feed(con, v, before, limit, topic)

    posting: set[int] = set()  # people with a Gallery upload under way

    @app.post("/api/gallery")
    async def post_gallery_photo(request: Request, con: Con, v: Me, event: int | None = Query(None, ge=1, lt=1 << 62),
            topic: str | None = Query(None, max_length=16)):
        """A photo into the Gallery (GALLERY), the file is the body as in /api/photos; `event`: into its album too;
        `topic` (gallery.TOPICS): what a photo of no event is about."""
        # one at a time per person (the picture workers are shared with receipts and avatars), counted before the work
        # ponytail: per worker process; a meta row as the lock if one person's parallel uploads over workers ever matter
        if v.id in posting:
            raise ApiError("rate_limited", "busy")
        posting.add(v.id)
        try:
            await run_in_threadpool(logic.gallery.check, con, v, event, topic)  # a plain no costs no upload
            data = await read_upload(request)
            await run_in_threadpool(logic.gallery.attempt, con, v, event, topic)
            saved = await _picture(media.save, data, photos)
            try:
                return await run_in_threadpool(logic.gallery.post, con, v, saved, event, topic)
            except ApiError:  # refused on the second look (the flag, the album filled): no file left behind without a row
                if logic.photo_free(con, saved["path"]):
                    media.drop(photos, [saved["path"]])
                raise
        finally:
            posting.discard(v.id)

    @app.delete("/api/gallery/{fid}", status_code=204)
    def drop_gallery_photo(fid: int, con: Con, v: Me):
        media.drop(photos, logic.gallery.delete_mine(con, v, fid))

    @app.post("/api/me/unlocked")
    def seen_unlock(con: Con, v: Me, body: dict = Body(...)):
        logic.seen_unlock(con, v, body.get("code"), body.get("level"))
        return {"unlocked": logic.unlocked(con, v)}

    @app.post("/api/me/anthem")  # heard start to finish without skipping (the anthem sheet): the award, once
    def anthem_heard(con: Con, v: Me):
        return {"unlocked": logic.anthem_heard(con, v)}

    @app.post("/api/referral", status_code=204)
    def refer(con: Con, v: Me, body: dict = Body(...)):
        logic.refer(con, v, body.get("code"))

    @app.post("/api/me/calendar")
    def my_calendar(con: Con, v: Me):
        """My calendar feed: the page that subscribes any phone (calpage.py) and the feed itself ("add by URL")."""
        t = logic.cal_token(con, v)
        return {"page": f"https://{cfg.domain}/cal/{t}", "feed": f"webcal://{cfg.domain}/cal/{t}.ics"}

    @app.delete("/api/me/calendar", status_code=204)
    def reset_my_calendar(con: Con, v: Me):
        logic.reset_cal_token(con, v)

    @app.get("/cal/{token}.ics")
    def calendar_feed(token: str, con: Con):
        body = logic.cal_feed(con, token, lambda eid: f"https://t.me/{cfg.bot_username}?startapp=ev_{eid}")
        return Response(body, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.get("/cal/{token}")
    def calendar_page(token: str, request: Request, con: Con):
        """Opened from the app in the phone's browser: Apple's calendar subscribes at once, the rest through Google (calpage.py)."""
        logic.cal_feed(con, token, str)  # 404 for a token that isn't (or no longer is) anyone's
        lang = next((x for x in ("ru", "kk", "en") if x in request.headers.get("accept-language", "")[:5].lower()), "ru")
        page = calpage.render(cfg.domain, token, lang, request.headers.get("user-agent", ""))
        # the token is in the address: no Referer carries it on
        return Response(page, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": calpage.CSP})

    @app.get("/api/events/{eid}/ics")
    def event_ics(eid: int, con: Con, k: str = ""):
        # no session: Telegram hands the link to the phone's browser, which gives the file to the calendar
        if not hmac.compare_digest(k.encode(), logic.ics_sig(eid).encode()):
            raise ApiError("not_found")
        return Response(logic.event_ics(con, eid, f"https://t.me/{cfg.bot_username}?startapp=ev_{eid}"), media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": f'inline; filename="kbtu-event-{eid}.ics"', "Cache-Control": "no-store"})

    @app.get("/api/events/{eid}")
    def get_event(eid: int, con: Con, v: Me):
        return logic.event(con, v, eid)

    @app.post("/api/events/{eid}/registration")
    def register(eid: int, con: Con, v: Me, body: dict = Body(default={})):
        if body.get("team") is not None:  # a team event's sign-up: create a team or join one by its link (evteams.py)
            return logic.evteams.signup(con, v, eid, body["team"], body.get("ref"), body.get("phone"), body.get("answers"))
        return logic.register(con, v, eid, body.get("ref"), body.get("phone"), body.get("answers"))

    # team events (logic/evteams.py): my team (create, join by link, leave; the captain's rename, "find us teammates",
    # a new link, remove), an invite link's team, and the organizer's list, "Form teams" and moves
    @app.post("/api/events/{eid}/team")
    def team_create(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.evteams.create(con, v, eid, body.get("name"))

    @app.post("/api/events/{eid}/team/join")
    def team_join(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.evteams.join(con, v, eid, body.get("token"))

    @app.delete("/api/events/{eid}/team")
    def team_leave(eid: int, con: Con, v: Me):
        return logic.evteams.leave(con, v, eid)

    @app.patch("/api/events/{eid}/team")
    def team_edit(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.evteams.edit(con, v, eid, body)

    @app.post("/api/teams/consent")
    def team_agree(con: Con, v: Me, body: dict = Body(...)):
        return logic.evteams.agree(con, v, body)

    @app.delete("/api/teams/consent")
    def team_withdraw(con: Con, v: Me):
        return logic.evteams.withdraw(con, v)

    @app.post("/api/events/{eid}/team/link")
    def team_new_link(eid: int, con: Con, v: Me):
        return logic.evteams.new_link(con, v, eid)

    @app.delete("/api/events/{eid}/team/members/{uid}")
    def team_remove(eid: int, uid: int, con: Con, v: Me):
        return logic.evteams.remove(con, v, eid, uid)

    @app.get("/api/team-invites/{token}")
    def team_invite(token: str, con: Con, v: Me):
        return logic.evteams.invite(con, v, token)

    @app.get("/api/events/{eid}/teams")
    def teams_list(eid: int, con: Con, v: Me):
        return logic.evteams.teams_list(con, v, eid)

    @app.post("/api/events/{eid}/teams/form")
    def teams_form(eid: int, con: Con, v: Me):
        return logic.evteams.form(con, v, eid)

    @app.put("/api/events/{eid}/teams/people/{uid}")
    def teams_move(eid: int, uid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.evteams.move(con, v, eid, uid, body.get("team"))

    @app.delete("/api/events/{eid}/registration")
    def unregister(eid: int, con: Con, v: Me):
        return logic.unregister(con, v, eid)

    @app.put("/api/events/{eid}/saved", status_code=204)
    def save(eid: int, con: Con, v: Me):
        logic.set_saved(con, v, eid, True)

    @app.delete("/api/events/{eid}/saved", status_code=204)
    def unsave(eid: int, con: Con, v: Me):
        logic.set_saved(con, v, eid, False)

    # ------------------------------------------------------------ orgs and news

    @app.get("/api/orgs")
    def list_orgs(con: Con, v: Me):
        return logic.orgs(con, v)

    @app.get("/api/orgs/{oid}")
    def get_org(oid: int, con: Con, v: Me):
        return logic.org(con, v, oid)

    # ------------------------------------------------------------ an org's own chats (PLAN 86)

    @app.get("/api/orgs/{oid}/chats")
    def org_chats(oid: int, con: Con, v: Me):
        """Studio's list: the invite links too, and whether our bot keeps each card."""
        logic.may_chats(con, v, oid)
        return logic.org_chats(con, oid, True)

    @app.post("/api/orgs/{oid}/chats")
    async def add_org_chat(oid: int, con: Con, v: Me, body: dict = Body(...)):
        """A chat for the org's page: @name, a t.me link or an invite link, looked up on t.me. Errors: bad_input (notchat:
        a person, a bot, no such chat), conflict taken (another org's) / limit, unavailable (Telegram didn't answer)."""
        logic.may_chats(con, v, oid)  # before going to Telegram
        url = logic.chat_link(str(body.get("link") or "")[:200])
        if not url:
            raise logic.ApiError("bad_input")
        async with httpx.AsyncClient(timeout=10) as http:
            peek = await media.chat_peek(http, url)
        if peek["image"]:
            try:
                peek["photo"] = (await _img(media.save, peek["image"], photos))["path"]
            except media.BadImage:
                pass
        def save() -> dict:
            try:
                out, gone = logic.add_org_chat(con, v, oid, url, peek)
            except logic.ApiError:
                media.drop(photos, [peek["photo"]] if peek.get("photo") and logic.photo_free(con, peek["photo"]) else [])
                raise
            media.drop(photos, gone)
            return out
        return await run_in_threadpool(save)

    @app.post("/api/orgs/{oid}/chats/pick")
    def pick_org_chat(oid: int, con: Con, v: Me, body: dict = Body(...)):
        """Telegram's own picker for the org's group or channel: our bot added there as an admin (inviting, so its link;
        a group's also what the guard bot needs) links it (logic.pick_claim)."""
        kind = body.get("kind")
        if kind not in ("group", "channel"):
            raise logic.ApiError("bad_input")
        with logic.tx(con):
            logic.chat_pick(con, v, oid)
        bot_url = f"https://t.me/{cfg.bot_username}"
        return {"url": f"{bot_url}?startchannel&admin=invite_users+post_messages+edit_messages+delete_messages" if kind == "channel"
                else f"{bot_url}?startgroup=pick&admin=invite_users+delete_messages+restrict_members+pin_messages"}

    @app.put("/api/orgs/{oid}/chats/{cid}/main")
    def main_org_chat(oid: int, cid: int, con: Con, v: Me):
        return logic.main_org_chat(con, v, oid, cid)

    @app.put("/api/orgs/{oid}/chats/{cid}/mirror")
    def mirror_org_chat(oid: int, cid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.mirror_org_chat(con, v, oid, cid, body.get("on"))

    @app.put("/api/orgs/{oid}/chats/{cid}/swear")
    async def swear_org_chat(oid: int, cid: int, con: Con, v: Me, body: dict = Body(...)):
        """The group's swear filter (logic/chatmod.py), its President's or Vice's. On only where our bot may delete and
        restrict (conflict rights, `missing`: "delete", "ban"); a change, and the bot tells the chat in one template line."""
        on = body.get("on")
        if not isinstance(on, bool):
            raise ApiError("bad_input")
        tg = await run_in_threadpool(logic.chatmod.target, con, v, oid, cid)
        async with httpx.AsyncClient(timeout=10) as http:
            if on:
                miss = await bot.swear_rights(cfg, http, tg)
                if miss is None:
                    raise ApiError("unavailable", "telegram")
                if miss:
                    raise ApiError("conflict", "rights", {"missing": miss})
            if await run_in_threadpool(logic.chatmod.switch, con, v, oid, cid, on):
                u = logic.one(con, "SELECT lang FROM users WHERE id = ?", v.id)
                r = (await bot._send(cfg, http, {"chat_id": tg, "text": texts.swear(u["lang"] if u else "ru", "on" if on else "off"), "parse_mode": "HTML"})).json()
                if not r.get("ok"):
                    log.warning("swear switch: %s", str(r.get("description"))[:120])
        return logic.org_chats(con, oid, True)

    @app.get("/api/orgs/{oid}/chats/swear")
    def swear_report(oid: int, con: Con, v: Me):
        """The club's groups' swear warnings, 30 days: its President, Vice and Heads."""
        return logic.chatmod.report(con, v, oid)

    @app.get("/api/orgs/{oid}/chats/{cid}/roles")
    async def chat_roles(oid: int, cid: int, con: Con, v: Me):
        """Studio → Chats → Roles and admins (logic/chatroles.py): the group's admins and the club's roles side by side,
        asked of Telegram now (paced, capped, kept a few minutes a worker); read-only, no Telegram id leaves."""
        tg = await run_in_threadpool(logic.chatroles.target, con, v, oid, cid)
        people = [p["tg_id"] for p in await run_in_threadpool(logic.chatroles.leaders, con, oid)]
        async with httpx.AsyncClient(timeout=10) as http:
            got = await logic.chatroles.ask(lambda m, p: bot._call(cfg, http, m, p), int(cfg.bot_token.split(":")[0]), tg, people)
        return await run_in_threadpool(logic.chatroles.hint, con, oid, got)

    @app.delete("/api/orgs/{oid}/chats/{cid}")
    def drop_org_chat(oid: int, cid: int, con: Con, v: Me):
        out, gone = logic.drop_org_chat(con, v, oid, cid)
        media.drop(photos, gone)
        return out

    @app.put("/api/orgs/{oid}/subscription")
    def subscribe(oid: int, con: Con, v: Me):
        return logic.subscribe(con, v, oid, True)

    @app.delete("/api/orgs/{oid}/subscription")
    def unsubscribe(oid: int, con: Con, v: Me):
        return logic.subscribe(con, v, oid, False)

    @app.delete("/api/orgs/{oid}")
    def delete_org(oid: int, con: Con, v: Me):
        """The President's own empty club, made by mistake (logic.delete_org)."""
        logic.delete_org(con, v, oid)
        return {"ok": True}

    @app.post("/api/orgs/{oid}/join-requests")
    def apply(oid: int, con: Con, v: Me, body: dict | None = Body(None)):
        return logic.apply(con, v, oid, body)

    @app.delete("/api/orgs/{oid}/join-requests/mine")
    def withdraw(oid: int, con: Con, v: Me):
        return logic.withdraw(con, v, oid)

    @app.get("/api/posts")
    def list_posts(con: Con, v: Me, scope: str = "all"):
        if scope.startswith("org:") and not scope[4:].isdigit():
            raise ApiError("bad_input")
        return logic.posts(con, v, scope)

    @app.get("/api/castings")
    def list_castings(con: Con, v: Me):
        return logic.castings(con, v)

    @app.post("/api/posts/{pid}/casting/cancel")
    def cancel_casting(pid: int, con: Con, v: Me):
        return logic.cancel_casting(con, v, pid)

    @app.get("/api/posts/{pid}/video")
    async def post_video(pid: int, con: Con, v: Me):
        """A mirrored channel post's video file for the app's own player (mirror.video); not_found: the app frames
        Telegram's widget instead."""
        async with httpx.AsyncClient(timeout=6) as http:
            return await mirror.video(con, v.id, pid, http)

    @app.post("/api/orgs/{oid}/posts")
    def create_post(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.create_post(con, v, oid, body)

    @app.patch("/api/posts/{pid}")
    def update_post(pid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.update_post(con, v, pid, body)

    @app.delete("/api/posts/{pid}", status_code=204)
    def hide_post(pid: int, con: Con, v: Me):
        media.drop(photos, [p for p in logic.hide_post(con, v, pid) if logic.photo_free(con, p)])

    @app.post("/api/posts/read", status_code=204)
    def read_posts(con: Con, v: Me, body: dict = Body(...)):
        logic.read_posts(con, v, body.get("ids") if isinstance(body.get("ids"), list) else [])

    @app.put("/api/posts/{pid}/reactions/{kind}")
    def react(pid: int, kind: str, con: Con, v: Me):
        return logic.react(con, v, pid, kind, True)

    @app.delete("/api/posts/{pid}/reactions/{kind}")
    def unreact(pid: int, kind: str, con: Con, v: Me):
        return logic.react(con, v, pid, kind, False)

    @app.get("/api/users/{uid}")
    def person(uid: int, con: Con, v: Me):
        out = logic.person(con, v, uid)
        if cfg.forum and v.role in ("admin", "moderator"):  # the forum's skills, where its people can see them
            out["forum"] = logic.my_forum(con, logic.Viewer(uid, "user", True))
        return out

    # ------------------------------------------------------------ Studio

    # ---- friends (§4.7) ----
    @app.get("/api/friends")
    def friends(con: Con, v: Me):
        return logic.friends(con, v)

    @app.get("/api/friends/find")
    def find_friend(con: Con, v: Me, username: str = ""):
        return logic.find_student(con, v, username)

    @app.post("/api/friends/requests")
    def ask_friend(con: Con, v: Me, body: dict = Body(...)):
        uid = body.get("userId")
        if not isinstance(uid, int) or isinstance(uid, bool):
            raise ApiError("bad_input")
        return logic.ask_friend(con, v, uid)

    @app.post("/api/friends/requests/{uid}/{answer}")
    def answer_friend(uid: int, answer: str, con: Con, v: Me):
        if answer not in ("accept", "decline"):
            raise ApiError("not_found")
        return logic.answer_friend(con, v, uid, answer == "accept")

    @app.delete("/api/friends/requests/{uid}", status_code=204)
    def take_back_request(uid: int, con: Con, v: Me):
        logic.take_back_request(con, v, uid)

    @app.delete("/api/friends/{uid}", status_code=204)
    def unfriend(uid: int, con: Con, v: Me):
        logic.unfriend(con, v, uid)

    @app.get("/api/friends/joined")  # my invite QR on screen: who has just become my friend
    def friend_joined(con: Con, v: Me, since: int = 0):
        return logic.friend_joined(con, v, since)

    @app.get("/api/invite/{code}")  # my one invite link r_<link code> opened: whose it is (adds nobody)
    def link_card(code: str, con: Con, v: Me):
        return logic.link_card(con, v, code)

    @app.post("/api/invite/{code}")  # its "Add as a friend": friends at once
    def add_by_link(code: str, con: Con, v: Me):
        return logic.add_by_link(con, v, code)


    # ------------------------------------------------------------ casting: a club's recruitment round (casting.py)

    @app.get("/api/orgs/{oid}/round")
    def round_view(oid: int, con: Con, v: Me):
        return casting.view(con, v, oid)

    @app.post("/api/orgs/{oid}/round")
    def round_open(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.open_round(con, v, oid, body)

    @app.patch("/api/rounds/{rid}")
    def round_update(rid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.update_round(con, v, rid, body)

    @app.post("/api/rounds/{rid}/apply")
    def round_apply(rid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.apply(con, v, rid, body)

    @app.delete("/api/rounds/{rid}/apply")
    def round_withdraw(rid: int, con: Con, v: Me):
        return casting.withdraw(con, v, rid)

    @app.get("/api/rounds/{rid}/apps")
    def round_apps(rid: int, con: Con, v: Me):
        return casting.apps(con, v, rid)

    @app.post("/api/round-apps/{aid}/vote")
    def round_vote(aid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.vote(con, v, aid, body)

    @app.post("/api/round-apps/{aid}/decide")
    def round_decide(aid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.decide(con, v, aid, body)

    @app.get("/api/rounds/{rid}/slots")
    def round_slots(rid: int, con: Con, v: Me):
        return casting.slots(con, v, rid)

    @app.post("/api/rounds/{rid}/slots")
    def round_add_slots(rid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.add_slots(con, v, rid, body)

    @app.delete("/api/round-slots/{sid}")
    def round_drop_slot(sid: int, con: Con, v: Me):
        return casting.drop_slot(con, v, sid)

    @app.post("/api/rounds/{rid}/invite")
    def round_invite(rid: int, con: Con, v: Me):
        return casting.invite(con, v, rid)

    @app.post("/api/rounds/{rid}/book")
    def round_book(rid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.book(con, v, rid, body)

    @app.post("/api/round-apps/{aid}/came")
    def round_came(aid: int, con: Con, v: Me, body: dict = Body(...)):
        return casting.showed(con, v, aid, body)

    @app.post("/api/rounds/{rid}/send")
    def round_send(rid: int, con: Con, v: Me, body: dict | None = Body(None)):
        return casting.send(con, v, rid, (body or {}).get("final", True) is not False)  # no body: the old final send

    @app.get("/api/orgs/{oid}/memo")
    def org_memo(oid: int, con: Con, v: Me, later: bool = False):
        return logic.memo(con, v, oid, later)

    @app.get("/api/map/graph")
    def map_graph(con: Con, v: Me):
        return logic.map_graph(con)

    @app.get("/api/map/rooms")
    def map_rooms(request: Request, v: Me):
        return logic.map_rooms(request.app.state.cfg.rooms_file)

    @app.post("/api/orgs/{oid}/memo/item")
    def memo_item(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return {"text": logic.memo_item(con, v, oid, body)}

    @app.post("/api/orgs/{oid}/memo/opened", status_code=204)
    def memo_opened(oid: int, con: Con, v: Me):
        logic.memo_opened(con, v, oid)

    @app.post("/api/orgs/{oid}/memo/sent", status_code=204)
    def memo_sent(oid: int, con: Con, v: Me, body: dict = Body(...)):
        logic.memo_sent(con, v, oid, body.get("ids"))

    @app.post("/api/orgs/{oid}/memo/again/{eid}", status_code=204)
    def memo_again(oid: int, eid: int, con: Con, v: Me):
        logic.memo_again(con, v, oid, eid)

    @app.put("/api/orgs/{oid}/memo/sign")
    def memo_sign(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.memo_sign(con, v, oid, body)

    @app.post("/api/events/{eid}/place")
    def change_place(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.change_place(con, v, eid, body.get("place"))

    @app.get("/api/orgs/{oid}/events")
    def org_events(oid: int, con: Con, v: Me):
        return logic.org_events(con, v, oid)

    @app.post("/api/orgs/{oid}/events")
    def create_event(oid: int, con: Con, v: Me, body: dict = Body(...)):
        body = body if board_on(app.state.cfg, v) else {k: x for k, x in body.items() if k != "form"}  # questions: BOARD's policy
        return (logic.staff_create_event if v.staff_org else logic.create_event)(con, v, oid, body)

    @app.patch("/api/events/{eid}")
    def update_event(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.update_event(con, v, eid, body if board_on(app.state.cfg, v) else {k: x for k, x in body.items() if k != "form"})

    @app.post("/api/events/{eid}/volunteer")
    def volunteer_apply(eid: int, con: Con, v: Me, body: dict = Body(default={})):
        return logic.volunteer_apply(con, v, eid, body.get("note"))

    @app.delete("/api/events/{eid}/volunteer")
    def volunteer_leave(eid: int, con: Con, v: Me):
        return logic.volunteer_leave(con, v, eid)

    @app.get("/api/events/{eid}/volunteers")
    def volunteers(eid: int, con: Con, v: Me):
        return logic.volunteers_list(con, v, eid)

    @app.put("/api/events/{eid}/volunteers/{uid}")
    def volunteer_decide(eid: int, uid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.volunteer_decide(con, v, eid, uid, body.get("yes"))

    # a host club's member asks to come as a guest; its President or a Vice answers (seats.team_ask)
    @app.post("/api/events/{eid}/team-ask")
    def team_ask(eid: int, con: Con, v: Me):
        return logic.team_ask(con, v, eid)

    @app.delete("/api/events/{eid}/team-ask")
    def team_unask(eid: int, con: Con, v: Me):
        return logic.team_unask(con, v, eid)

    @app.get("/api/events/{eid}/team-asks")
    def team_asks(eid: int, con: Con, v: Me):
        return logic.team_asks(con, v, eid)

    @app.put("/api/events/{eid}/team-asks/{uid}", status_code=204)
    def team_decide(eid: int, uid: int, con: Con, v: Me, body: dict = Body(...)):
        logic.team_decide(con, v, eid, uid, body.get("yes"))

    @app.post("/api/events/{eid}/chat")
    def chat_start(eid: int, con: Con, v: Me):
        token = logic.chat_start(con, v, eid)  # the bot comes in as an admin that may add people, pin and delete
        return {"url": f"https://t.me/{cfg.bot_username}?startgroup=ec_{token}&admin=invite_users+pin_messages+delete_messages+restrict_members"}

    @app.post("/api/events/{eid}/publish")
    def publish(eid: int, con: Con, v: Me):
        return logic.publish_event(con, v, eid)

    @app.post("/api/events/{eid}/cancel")
    def cancel(eid: int, con: Con, v: Me):
        return logic.cancel_event(con, v, eid)

    @app.delete("/api/events/{eid}", status_code=204)
    def delete_event(eid: int, con: Con, v: Me):
        if v.role == "admin":  # the app's admin: hidden now, gone in a day, audited, with its Undo (Admin → Done)
            return logic.admin_delete_event(con, v, eid)
        gone, photo = logic.delete_event(con, v, eid)
        media.drop(receipts, gone)
        media.drop(photos, photo)

    # a co-host club (logic/cohosts.py): the host invites one, its Vice+ answers in Studio, either side ends it
    @app.put("/api/events/{eid}/cohost")
    def cohost_invite(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.cohosts.invite(con, v, eid, body.get("orgId"))

    @app.delete("/api/events/{eid}/cohost", status_code=204)
    def cohost_end(eid: int, con: Con, v: Me):
        logic.cohosts.end(con, v, eid)

    @app.post("/api/events/{eid}/cohost/answer")
    def cohost_answer(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.cohosts.answer(con, v, eid, body.get("yes"), body.get("mute", False))

    @app.delete("/api/orgs/{oid}/mutes/{muted}", status_code=204)
    def cohost_unmute(oid: int, muted: int, con: Con, v: Me):
        logic.cohosts.unmute(con, v, oid, muted)

    # an event's temporary door helpers (logic/crew.py): a running club's President or Vice gives and takes back
    @app.put("/api/events/{eid}/crew")
    def crew_put(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.crew.put(con, v, eid, body.get("userId"), body.get("kind"))

    @app.delete("/api/events/{eid}/crew/{uid}")
    def crew_drop(eid: int, uid: int, con: Con, v: Me):
        return logic.crew.drop(con, v, eid, uid)

    # a club's report after its event (logic/evreports.py, REPORTS=1): the club's people with the "reports" right
    @app.get("/api/events/{eid}/report")
    def report_get(eid: int, con: Con, v: Reports, org: int | None = None):  # org: whose report (the co-host's; the host's by default)
        return logic.evreports.get(con, v, eid, org)

    @app.patch("/api/events/{eid}/report")
    def report_save(eid: int, con: Con, v: Reports, body: dict = Body(...), org: int | None = None):
        return logic.evreports.save(con, v, eid, body, org)

    @app.post("/api/reports/consent")
    def report_agree(con: Con, v: Reports, body: dict = Body(...)):
        return logic.evreports.agree(con, v, body)

    @app.delete("/api/reports/consent")
    def report_withdraw(con: Con, v: Reports):
        return logic.evreports.withdraw(con, v)

    @app.put("/api/events/{eid}/report/marks/{uid}")
    def report_mark(eid: int, uid: int, con: Con, v: Reports, body: dict = Body(...), org: int | None = None):
        return logic.evreports.mark(con, v, eid, uid, body.get("status"), org)

    @app.get("/api/orgs/{oid}/cohosts")
    def cohost_invites(oid: int, con: Con, v: Me):
        return logic.cohosts.invites(con, v, oid)

    @app.get("/api/events/{eid}/attendees")
    def attendees(eid: int, con: Con, v: Me):
        return logic.attendees(con, v, eid)

    @app.post("/api/events/{eid}/checkin")
    def checkin(eid: int, con: Con, v: Me, body: dict = Body(...)):
        """A scanned or typed code, or {userId}: by name from the door list (no QR)."""
        uid, code = body.get("userId"), body.get("code")
        if isinstance(uid, int) and not isinstance(uid, bool):
            return logic.checkin_by_name(con, v, eid, uid)
        if not isinstance(code, str) or len(code) > 64:
            raise ApiError("bad_input")
        return logic.checkin(con, v, eid, code)

    @app.put("/api/events/{eid}/rating")
    def rate_event(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.rate_event(con, v, eid, body.get("score"), body.get("comment"))

    @app.post("/api/events/{eid}/updates")
    def post_update(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.post_update(con, v, eid, body.get("body") if isinstance(body.get("body"), str) else "")

    @app.delete("/api/events/{eid}/updates/{uid}", status_code=204)
    def delete_update(eid: int, uid: int, con: Con, v: Me):
        logic.delete_update(con, v, eid, uid)

    @app.delete("/api/events/{eid}/checkin/{uid}", status_code=204)
    def undo_checkin(eid: int, uid: int, con: Con, v: Me):
        logic.undo_checkin(con, v, eid, uid)

    @app.get("/api/events/{eid}/door")
    def door(eid: int, con: Con, v: Me):
        return logic.door(con, v, eid)

    @app.get("/api/events/{eid}/door/guests")
    def door_guests(eid: int, con: Con, v: Me):
        return logic.door_guests(con, v, eid)

    @app.post("/api/events/{eid}/door/guests")
    def add_door_guest(eid: int, con: Con, v: Me, body: dict = Body(...)):
        """A walk-in by the full name they typed (A19)."""
        return logic.add_door_guest(con, v, eid, body.get("name"))

    @app.delete("/api/events/{eid}/door/guests/{gid}", status_code=204)
    def undo_door_guest(eid: int, gid: int, con: Con, v: Me):
        logic.undo_door_guest(con, v, eid, gid)

    @app.post("/api/orgs/{oid}/invites")
    def invite(oid: int, con: Con, v: Me, body: dict | None = Body(None)):
        return logic.invite(con, v, oid, body.get("dept") if isinstance(body, dict) else None)

    @app.post("/api/orgs/{oid}/team-link")  # the member link for the whole team, 7 days: the live one, else a new one
    def team_link(oid: int, con: Con, v: Me):
        return logic.team_link(con, v, oid)

    @app.delete("/api/orgs/{oid}/team-link", status_code=204)
    def team_link_off(oid: int, con: Con, v: Me):
        logic.team_link_off(con, v, oid)

    @app.post("/api/invites/{token}")
    def accept_invite(token: str, con: Con, v: Me):
        return logic.accept_invite(con, v, token)

    @app.get("/api/orgs/{oid}/members")
    def team(oid: int, con: Con, v: Me):
        return logic.team(con, v, oid)

    @app.post("/api/orgs/{oid}/members/export", status_code=204)
    async def export_members(oid: int, con: Con, v: Me):
        """The roster as a CSV into the asker's chat with the bot, like the attendees' (send_file)."""
        o, people = await run_in_threadpool(logic.members_export, con, v, oid)
        u = logic.one(con, "SELECT tg_id, lang FROM users WHERE id = ?", v.id)
        await send_file(u["tg_id"], *texts.members_csv(u["lang"], o["name"], people))

    @app.post("/api/guard")
    async def guard(con: Con, v: Me, body: dict = Body(...)):
        """A stranger's join request held by our guard bot (bot._join): signed up now, they're let in. Only the person
        the request is theirs, and only as a student."""
        chat, who, qid = logic.guard_read(bot.guard_key(cfg), str(body.get("t") or ""))
        u = logic.one(con, "SELECT tg_id FROM users WHERE id = ?", v.id)
        if not v.student or not u or u["tg_id"] != who or logic.guard_join(con, chat, who) != "approve":
            raise ApiError("forbidden")  # the same rule as at the door, again now (an event's group since, unlinked, banned)
        tg = f"https://api.telegram.org/bot{cfg.bot_token}/"
        async with httpx.AsyncClient(timeout=15) as http:
            r = (await http.post(tg + "answerChatJoinRequestQuery", json={"chat_join_request_query_id": qid, "result": "approve"})).json()
            if not r.get("ok"):  # the query ran out: the request itself may still wait
                r = (await http.post(tg + "approveChatJoinRequest", json={"chat_id": chat, "user_id": who})).json()
        if not r.get("ok"):
            log.warning("guard: %s", str(r.get("description"))[:200])
            raise ApiError("conflict", "expired")
        return {"ok": True}

    @app.get("/api/orgs/{oid}/people")
    def people(oid: int, con: Con, v: Me):
        return logic.people(con, v, oid)

    @app.patch("/api/orgs/{oid}/members/{uid}")
    def update_member(oid: int, uid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.update_member(con, v, oid, uid, body)

    # Team 2.0 (§2b): the club's roles and tags, probation, removal by request, bans
    @app.get("/api/orgs/{oid}/team")
    def team_setup(oid: int, con: Con, v: Me):
        return logic.team_setup(con, v, oid)

    @app.post("/api/orgs/{oid}/roles")
    def add_role(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.save_role(con, v, oid, body)

    @app.patch("/api/orgs/{oid}/roles/{rid}")
    def edit_role(oid: int, rid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.save_role(con, v, oid, body, rid)

    @app.put("/api/orgs/{oid}/roles/{rid}/people")
    def assign_role(oid: int, rid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.assign_role(con, v, oid, rid, body)

    @app.delete("/api/orgs/{oid}/roles/{rid}")
    def delete_role(oid: int, rid: int, con: Con, v: Me):
        return logic.delete_role(con, v, oid, rid)

    @app.post("/api/orgs/{oid}/tags")
    def add_tag(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.save_tag(con, v, oid, body)

    @app.patch("/api/orgs/{oid}/tags/{tid}")
    def edit_tag(oid: int, tid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.save_tag(con, v, oid, body, tid)

    @app.delete("/api/orgs/{oid}/tags/{tid}")
    def delete_tag(oid: int, tid: int, con: Con, v: Me):
        return logic.delete_tag(con, v, oid, tid)

    @app.post("/api/orgs/{oid}/members/{uid}/remove")
    def remove(oid: int, uid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.remove(con, v, oid, uid, body)

    @app.post("/api/removals/{rid}", status_code=204)
    def decide_removal(rid: int, con: Con, v: Me, body: dict = Body(...)):
        logic.decide_removal(con, v, rid, body.get("approve"))

    @app.delete("/api/orgs/{oid}/bans/{uid}", status_code=204)
    def unban(oid: int, uid: int, con: Con, v: Me):
        logic.unban(con, v, oid, uid)

    @app.delete("/api/orgs/{oid}/members/{uid}", status_code=204)
    def remove_member(oid: int, uid: int, con: Con, v: Me):
        logic.remove_member(con, v, oid, uid)

    @app.post("/api/orgs/{oid}/transfer")
    def transfer(oid: int, con: Con, v: Me, body: dict = Body(...)):
        try:
            uid = int(body.get("userId"))
        except (TypeError, ValueError):
            raise ApiError("bad_input") from None
        return logic.transfer(con, v, oid, uid)

    @app.get("/api/orgs/{oid}/join-requests")
    def join_requests(oid: int, con: Con, v: Me):
        return logic.join_requests(con, v, oid)

    @app.post("/api/join-requests/{rid}/accept", status_code=204)
    def accept(rid: int, con: Con, v: Me):
        logic.decide_join(con, v, rid, True)

    @app.post("/api/join-requests/{rid}/reject", status_code=204)
    def reject(rid: int, con: Con, v: Me):
        logic.decide_join(con, v, rid, False)

    @app.patch("/api/orgs/{oid}")
    def update_org(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.update_org(con, v, oid, body)

    @app.get("/api/orgs/{oid}/links")
    def org_links(oid: int, con: Con, v: Me):
        return logic.org_links(con, v, oid)

    @app.post("/api/orgs/{oid}/links")
    def add_link(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.add_link(con, v, oid, body)

    @app.delete("/api/links/{slug}", status_code=204)
    def drop_link(slug: str, con: Con, v: Me):
        logic.drop_link(con, v, slug)  # the club's Vice+, or the admin revoking it

    # ------------------------------------------------------------ photos

    @app.post("/api/photos")
    async def upload_photo(request: Request, con: Con, v: Me):
        """The file itself is the body (no multipart). Decoding and re-encoding run off the event loop."""
        data = await read_upload(request)
        if not logic.organizes(con, v):  # before the work, not only after it
            raise ApiError("forbidden")
        saved = await _picture(media.save, data, photos)
        return await run_in_threadpool(logic.add_photo, con, v, saved)  # a write: its lock wait off the event loop

    # an event's video (video.py): the size first, then the file in pieces at their offsets, then "done"; a piece sent
    # again after a lost answer is told where the file stands instead of being added twice
    uploads = Path(cfg.db_path).resolve().parent / "uploads"   # originals: never under /media, deleted once compressed

    @app.post("/api/videos")
    def new_video(body: dict, con: Con, v: Me):
        return logic.new_video(con, v, body.get("size"), body.get("wide", False))

    @app.put("/api/videos/{vid}")
    async def video_piece(vid: int, at: int, request: Request, con: Con, v: Me):
        x = logic.my_video(con, v, vid)
        if x["status"] != "uploading":
            raise ApiError("conflict")
        f = uploads / str(vid)
        have = f.stat().st_size if f.exists() else 0
        if at != have:
            return {"at": have}
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > 2 * video.PIECE or have + len(data) > x["size"]:
                raise ApiError("bad_input", "too_big")
        uploads.mkdir(exist_ok=True)
        with f.open("ab") as out:
            out.write(data)
        return {"at": have + len(data)}

    @app.post("/api/videos/{vid}/done")
    def video_done(vid: int, con: Con, v: Me):
        f = uploads / str(vid)
        return logic.video_uploaded(con, v, vid, f.stat().st_size if f.exists() else 0)

    @app.get("/api/videos/{vid}")
    def video_state(vid: int, con: Con, v: Me):
        return logic.video_shape(logic.my_video(con, v, vid))

    @app.delete("/api/me/photo")
    def drop_my_photo(con: Con, v: Me):
        media.drop(photos, logic.drop_my_photo(con, v))
        return logic.me(con, v)

    # my own photo instead of Telegram's: the body as in /api/photos; the one it replaces leaves the disk
    @app.post("/api/me/photo")
    async def upload_my_photo(request: Request, con: Con, v: Me):
        data = await read_upload(request)
        logic.need_student(v)  # before the work, not only after it
        saved = await _picture(media.save, data, photos)

        def done() -> dict:
            media.drop(photos, logic.set_photo(con, v, saved))
            return logic.me(con, v)
        return await run_in_threadpool(done)

    # paid events (§4.3): the receipt is the body, like /api/photos; its image only through the API, to whom may see it
    @app.post("/api/events/{eid}/receipt")
    async def upload_receipt(eid: int, request: Request, con: Con, v: Me):
        data = await read_upload(request)
        await run_in_threadpool(logic.receipt_open, con, v, eid)  # before the work, not only after it
        try:  # Kaspi's PDF or a screenshot; read by OCR (~0.5 s) right here, no queue
            saved, read = await _picture(receipt.take, data, receipts)
        except receipt.NotReceipt:
            raise ApiError("bad_input", "not_receipt") from None

        def keep() -> dict:
            try:
                c, gone = logic.add_receipt(con, v, eid, saved, read)
            except ApiError:  # the hold ran out meanwhile: the new picture leaves the disk too, unless a row has the same one
                media.drop(receipts, [] if logic.one(con, "SELECT 1 FROM files WHERE path = ?", saved["path"]) else [saved["path"]])
                raise
            media.drop(receipts, gone)  # the one it replaced
            return c
        return await run_in_threadpool(keep)

    @app.get("/api/receipts/{rid}/image")
    def receipt_image(rid: int, con: Con, v: Me):
        return FileResponse(receipts / f"{logic.receipt_path(con, v, rid)}.webp", media_type="image/webp", headers={"Cache-Control": "private, no-store"})

    @app.post("/api/receipts/{rid}/review", status_code=204)
    def review_receipt(rid: int, con: Con, v: Me, body: dict = Body(...)):
        logic.review_receipt(con, v, rid, body.get("reject"))

    # comments under posts and events, reports (§4.10)
    @app.get("/api/{kind}s/{tid}/comments")
    def get_comments(kind: str, tid: int, con: Con, v: Me):
        return logic.comments(con, v, kind, tid)

    @app.post("/api/{kind}s/{tid}/comments")
    def add_comment(kind: str, tid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.add_comment(con, v, kind, tid, body.get("body"), body.get("asOrg"), body.get("replyTo"))

    @app.patch("/api/{kind}s/{tid}/comments")
    def switch_comments(kind: str, tid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_comments_on(con, v, kind, tid, body.get("on"))

    @app.delete("/api/comments/{cid}", status_code=204)
    def delete_comment(cid: int, con: Con, v: Me):
        logic.delete_comment(con, v, cid)

    @app.post("/api/reports", status_code=204)
    async def report(con: Con, v: Me, body: dict = Body(...)):
        def file_it():
            logic.report(con, v, body.get("target"), body.get("id"), body.get("reason"), body.get("note"))
            # a forum request goes only with three reports and the AI agreeing (else a moderator decides)
            if body.get("target") == "ask" and logic.reported_enough(con, body["id"]):
                return logic.one(con, "SELECT title, body FROM asks WHERE id = ?", body["id"])
        a = await run_in_threadpool(file_it)
        if a and await screen(f"{a['title']}\n{a['body']}") is False:
            await run_in_threadpool(logic.hide_ask, con, body["id"], "reports")

    async def eu_ai(con, msgs: list[dict], whole: float = 30, **kw) -> str:
        """The assistant's model call: the providers the policy's section 5 names for it (ai.ASSIST_PROVIDERS); none answered: 503."""
        # a bad answer is asked once more (Oct 31: GLM was down for hours and DeepSeek's one malformed reply was "busy")
        try:
            async with asyncio.timeout(whole):  # the whole chain: a link's own timeout is 25 s, and two may be slow
                for last in (False, True):
                    try:
                        return (await llm.chat(cfg, ai_http(), msgs, con=con, only=_ai_only(assist_only), chain=ai.chain(cfg), **kw))[0]
                    except llm.BadAnswers:
                        if last:
                            raise ApiError("unavailable", "assistant") from None
                    except llm.Busy:
                        raise ApiError("unavailable", "assistant") from None
        except TimeoutError:
            raise ApiError("unavailable", "assistant") from None

    # appeals to the Student Government (logic/appeals.py): mine (with the Solved feed), a new one, delete mine; AI help on a draft; SG's queue
    @app.get("/api/appeals")
    def my_appeals(con: Con, v: Appeals):
        return logic.appeals.mine(con, v)

    @app.post("/api/appeals")
    def new_appeal(con: Con, v: Appeals, body: dict = Body(...)):
        return logic.appeals.send(con, v, body)

    @app.delete("/api/appeals/{aid}", status_code=204)
    def drop_appeal(con: Con, v: Appeals, aid: int):
        logic.appeals.delete(con, v, aid)

    @app.post("/api/appeals/help")
    async def appeal_help(con: Con, v: Appeals, request: Request, body: dict = Body(...)):
        """2-3 tips on what's missing, never a rewrite; the AI down: 503 and sending still works (the app says so).
        Signs of self-harm: the helplines, with or without the model."""
        lang = body.get("lang") if body.get("lang") in ("ru", "kk", "en") else "ru"
        if logic.assistant.distress(body.get("text")):  # first, past every limit and the consent: the helplines (nothing kept)
            await run_in_threadpool(logic.appeals.agree_given, con, v, body)
            return {"tips": [], **await run_in_threadpool(logic.assistant.care, con, lang)}
        text = await run_in_threadpool(logic.appeals.help_ok, con, v, body)
        try:
            answer = await eu_ai(con, logic.appeals.help_prompt(text, lang), whole=40, max_tokens=400, temperature=0.2,
                                 check=logic.appeals.tips_usable, timeout=20, race=True)
        except ApiError:
            if logic.assistant.distress(text):
                return {"tips": [], **await run_in_threadpool(logic.assistant.care, con, lang)}
            raise
        return await run_in_threadpool(logic.appeals.help_reply, con, answer, text, lang)

    @app.get("/api/sg/appeals")
    def sg_queue(con: Con, v: Appeals):
        return logic.appeals.queue(con, v)

    @app.get("/api/sg/appeals/{aid}")
    def sg_appeal(con: Con, v: Appeals, aid: int):
        return logic.appeals.detail(con, v, aid)

    @app.post("/api/sg/appeals/{aid}")
    def sg_act(con: Con, v: Appeals, aid: int, body: dict = Body(...)):
        return logic.appeals.act(con, v, aid, body)

    # "Solved by your appeals": SG's people add and delete (undo: restore); everyone reads it with /api/appeals
    @app.post("/api/sg/solved")
    def sg_solved_add(con: Con, v: Appeals, body: dict = Body(...)):
        return logic.appeals.solved_add(con, v, body)

    @app.delete("/api/sg/solved/{sid}", status_code=204)
    def sg_solved_drop(con: Con, v: Appeals, sid: int):
        logic.appeals.solved_delete(con, v, sid)

    @app.post("/api/sg/solved/{sid}/restore")
    def sg_solved_restore(con: Con, v: Appeals, sid: int):
        return logic.appeals.solved_restore(con, v, sid)

    async def question_vec(body: dict):
        """DOCS=hybrid: the question's embedding for the documents' search, from Cloudflare, only where the policy names
        Cloudflare for the assistant's questions (ai_on) and the docs file has vectors to compare it with; 3 s at most in
        all, else None: the words' search alone."""
        ix = logic.assistant.DOCS
        if cfg.docs != "hybrid" or not ai_on or "cf" not in assist_only or not (cfg.cf_account_id and cfg.cf_ai_token) \
                or not ix or not await run_in_threadpool(ix.ready) or not ix.vectors:
            return None
        try:
            async with asyncio.timeout(3):
                r = await ai_http().post(**docs.request([logic.assistant.docs_query(body)], cfg.cf_account_id, cfg.cf_ai_token))
            return docs.vectors(r)[0]
        except (TimeoutError, httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as exc:
            log.warning("docs: no question embedding (%s)", type(exc).__name__)
            return None

    # the students' assistant (logic/assistant.py): with the forum's switch and policy section; the EU host only
    @app.post("/api/assistant")
    async def assistant(con: Con, v: BoardWrite, request: Request, body: dict = Body(...)):
        lang = logic.one(con, "SELECT lang FROM users WHERE id = ?", v.id)[0] or "ru"
        try:
            msgs, rooms, events = await run_in_threadpool(logic.assistant.prompt, con, v, body, lang)
            if logic.assistant.DOCS:
                year = logic.assistant.intake(logic.one(con, "SELECT course FROM students WHERE user_id = ?", v.id))
                msgs = await run_in_threadpool(logic.assistant.with_docs, msgs, logic.assistant.docs_query(body), await question_vec(body), year)
            text = await eu_ai(con, msgs, max_tokens=500, temperature=0.3, check=logic.assistant.usable, timeout=25)
        except ApiError as e:  # no model answer (down, or the day's 30 used): the helplines still come to one in distress
            if e.code in ("unavailable", "rate_limited") and logic.assistant.distress(body.get("q")):
                return {"text": "", "actions": [], **await run_in_threadpool(logic.assistant.care, con, lang)}
            raise
        return await run_in_threadpool(logic.assistant.reply, con, text, rooms, events, lang, msgs[-1]["content"])

    # its feedback (logic/assistant.py): a 👍/👎 on an answer's signed topic; on 👎, the one question and answer if sent
    @app.post("/api/assistant/vote", status_code=204)
    def assistant_vote(con: Con, v: BoardWrite, body: dict = Body(...)):
        logic.assistant.vote(con, v, body)

    @app.post("/api/assistant/send", status_code=204)
    def assistant_send(con: Con, v: BoardWrite, body: dict = Body(...)):
        logic.assistant.send(con, v, body)

    # its campus facts, kept current by the admin and moderators (the stale ones marked); each call answers the list
    @app.get("/api/admin/places")
    def places(con: Con, v: Me):
        return logic.assistant.places(con, v)

    @app.post("/api/admin/places")
    def place_add(con: Con, v: Me, body: dict = Body(...)):
        return logic.assistant.save_place(con, v, body)

    @app.patch("/api/admin/places/{pid}")
    def place_edit(pid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.assistant.save_place(con, v, body, pid)

    @app.delete("/api/admin/places/{pid}")
    def place_drop(pid: int, con: Con, v: Me):
        return logic.assistant.drop_place(con, v, pid)

    # a new event filled from its announcement (logic/assistant.py, below the assistant): the same switch, host and allowance
    @app.post("/api/orgs/{oid}/events/fill")
    async def event_fill(oid: int, con: Con, v: BoardWrite, body: dict = Body(...)):
        msgs = logic.assistant.fill_prompt(con, v, oid, body.get("text"), body.get("have"))
        # a long announcement's form is long (Nov 7: cut at 1500 tokens, then no time left to ask again): room for both
        text = await eu_ai(con, msgs, whole=70, max_tokens=3500, temperature=0.1, check=logic.assistant.fill_answered, timeout=30, race=True)  # a person waits: a slow first host races another
        return logic.assistant.filled(text)

    # the volunteers ledger of one club (logic/vol.py, VOLUNTEERS): its President and whom she grants; each volunteer their own
    @app.get("/api/vol")
    def vol_ledger(con: Con, v: VolMe):
        return logic.vol.ledger(con, v)

    @app.get("/api/vol/mine")
    def vol_mine(con: Con, v: VolMe):
        return logic.vol.person(con, v, None)

    @app.get("/api/vol/people/{vid}")
    def vol_person(con: Con, v: VolMe, vid: int):
        return logic.vol.person(con, v, vid)

    @app.post("/api/vol/people/{vid}/link")
    def vol_link(con: Con, v: VolMe, vid: int, body: dict = Body(...)):
        return logic.vol.link(con, v, vid, body)

    # hours come from scans alone: no route enters a shift, its times or a balance (Nov 11); this one takes a shift out or back
    @app.patch("/api/vol/shifts/{hid}")
    def vol_edit_shift(con: Con, v: VolMe, hid: int, body: dict = Body(...)):
        return logic.vol.edit_shift(con, v, hid, body)

    @app.post("/api/vol/people/{vid}/misses")
    def vol_add_miss(con: Con, v: VolMe, vid: int, body: dict = Body(...)):
        return logic.vol.add_miss(con, v, vid, body)

    @app.post("/api/vol/misses/{mid}/drop")
    def vol_drop_miss(con: Con, v: VolMe, mid: int, body: dict = Body(...)):
        return logic.vol.drop_miss(con, v, mid, body)

    @app.post("/api/vol/meets/{sid}")
    def vol_team(con: Con, v: VolMe, sid: int, body: dict = Body(...)):
        return logic.vol.set_team(con, v, sid, body)

    # a session's door: who left without checking out (answered after Finish), and the one-time link that hands the door over
    @app.get("/api/vol/meets/{sid}/door")
    def vol_door(con: Con, v: VolMe, sid: int):
        return logic.vol.door(con, v, sid)

    @app.post("/api/vol/shifts/{hid}/resolve")
    def vol_resolve(con: Con, v: VolMe, hid: int, body: dict = Body(...)):
        return logic.vol.resolve(con, v, hid, body)

    @app.post("/api/vol/meets/{sid}/hand")
    def vol_hand(con: Con, v: VolMe, sid: int):
        return logic.vol.hand(con, v, sid)

    @app.delete("/api/vol/meets/{sid}/hand")
    def vol_unhand(con: Con, v: VolMe, sid: int):
        return logic.vol.unhand(con, v, sid)

    @app.post("/api/vol/hand")  # the link opened; the token in the body, never in a URL (the access log)
    def vol_take(con: Con, v: VolMe, body: dict = Body(...)):
        return qr.handed(con, cfg.token_key, v, body.get("token"))

    @app.post("/api/vol/access")
    def vol_access(con: Con, v: VolMe, body: dict = Body(...)):
        return logic.vol.set_access(con, v, body)

    # the map's flaws (logic/mapflaws.py): a long press on the plan reports one, the admin's list fixes them
    @app.post("/api/map/flaws", status_code=204)
    def map_flaw(con: Con, v: Me, request: Request, body: dict = Body(...)):
        student = v.role not in ("admin", "moderator")
        if student and v.student:  # students with the forum's switch and its policy section (agreed to), like a forum post (a guest: 401 below)
            board_writer(request, board_viewer(request, v), con)
        logic.mapflaws.report(con, v, body, student)

    @app.get("/api/map/flaws")
    def map_flaws(con: Con, v: Me):
        return logic.mapflaws.listing(con, v)

    @app.get("/api/map/flaws/mine")
    def map_flaws_mine(con: Con, v: Me):
        return logic.mapflaws.mine(con, v)

    @app.post("/api/map/flaws/{fid}/done", status_code=204)
    def map_flaw_done(fid: int, con: Con, v: Me, body: dict = Body(default={})):
        logic.mapflaws.done(con, v, fid, body.get("done", True))

    @app.post("/api/admin/taken-down/{target}/{tid}/restore", status_code=204)
    def restore(target: str, tid: int, con: Con, v: Me):
        media.drop(photos, logic.restore(con, v, target, tid))  # a kept photo nothing shows after the undo

    @app.get("/api/admin/reports")
    def report_queue(con: Con, v: Me):
        return logic.report_queue(con, v)

    @app.post("/api/admin/reports/{target}/{tid}", status_code=204)
    def resolve_report(target: str, tid: int, con: Con, v: Me, body: dict = Body(...)):
        if target == "tgc":  # a comment in the channel's Telegram group: remove, keep, or keep and call the reports abuse
            logic.tgcomments.resolve(con, v, tid, "remove" if body.get("remove") else "abuse" if body.get("abuse") else "keep", body.get("rule"))
            return
        media.drop(photos, logic.resolve_report(con, v, target, tid, bool(body.get("remove"))))

    # the channel's comments in Telegram (logic/tgcomments.py): whose /report is closed, the admin's switch to reopen it
    @app.delete("/api/admin/tgc-closed/{uid}", status_code=204)
    def tgc_reopen(uid: int, con: Con, v: Me):
        logic.tgcomments.reopen(con, v, uid)

    @app.post("/api/me/tg-comment")
    def tg_comment(con: Con, v: Me):
        """My own comment the bot deleted in the channel's group, under an hour old: shown to the Telegram account that
        wrote it (the signed initData), never by a link; null for anyone else, the same as for nothing."""
        return logic.tgcomments.take_saved(con, v)

    @app.post("/api/events/{eid}/seats")
    def add_seats(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.add_seats(con, v, eid, body.get("add"))

    @app.post("/api/events/{eid}/decline")
    def decline(eid: int, con: Con, v: Me, body: dict | None = Body(None)):
        return logic.decline(con, v, eid, (body or {}).get("note"))

    @app.get("/api/events/{eid}/meeting")
    def meeting_answers(eid: int, con: Con, v: Me):
        return logic.meeting_answers(con, v, eid)

    @app.get("/api/events/{eid}/leaders")
    def leaders_answers(eid: int, con: Con, v: Me):
        return logic.leaders_answers(con, v, eid)

    @app.get("/api/events/{eid}/invites")
    def event_invites(eid: int, con: Con, v: Me):
        return logic.event_invites(con, v, eid)

    @app.post("/api/events/{eid}/invites")
    def invite_friend(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.invite_friend(con, v, eid, body.get("userId"))

    @app.post("/api/events/{eid}/photos")
    async def add_album_photo(eid: int, request: Request, con: Con, v: Me):
        """A photo for the guests' album: the file is the body, like /api/photos."""
        data = await read_upload(request)
        if not logic.can_add_album_photo(con, v, eid):  # before the work, not only after it
            raise ApiError("forbidden")
        saved = await _picture(media.save, data, photos)
        return await run_in_threadpool(logic.add_album_photo, con, v, eid, saved)

    @app.delete("/api/events/{eid}/photos/{fid}")
    def remove_album_photo(eid: int, fid: int, con: Con, v: Me):
        ev, gone = logic.remove_album_photo(con, v, eid, fid)
        media.drop(photos, gone)
        return ev

    # ------------------------------------------------------------ attendee list as a file

    @app.post("/api/events/{eid}/attendees/export", status_code=204)
    async def export_attendees(eid: int, con: Con, v: Me):
        """The bot sends the CSV to the organizer's own chat: it opens on any phone and can be forwarded (a download
        link would need the app's sign-in, which Telegram's downloader doesn't carry)."""
        e, people = await run_in_threadpool(logic.attendees_export, con, v, eid)
        u = logic.one(con, "SELECT tg_id, lang FROM users WHERE id = ?", v.id)
        await send_file(u["tg_id"], *texts.attendees_csv(u["lang"], e["title"], people))

    async def send_file(tg_id: int, name: str, data: bytes, caption: str) -> None:
        """A CSV into the person's own chat with the bot (asked for by them): it opens on any phone and can be forwarded."""
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                r = await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/sendDocument", data={"chat_id": str(tg_id), "caption": caption},
                                    files={"document": (name, data, "text/csv")})
            answer = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("file: %s", type(exc).__name__)
            raise ApiError("unavailable", "telegram") from None
        if r.status_code == 403:  # never started the bot, or blocked it
            raise ApiError("forbidden", "no_dm")
        if not answer.get("ok"):
            log.warning("file: %s", answer.get("description"))
            raise ApiError("unavailable", "telegram")

    # ------------------------------------------------------------ starting a club (§4.6)

    @app.get("/api/club-applications/mine")
    def my_club_application(con: Con, v: Me):
        return {"application": logic.my_club_application(con, v)}

    @app.post("/api/club-applications")
    def apply_club(con: Con, v: Me, body: dict = Body(...)):
        return logic.apply_club(con, v, body)

    @app.get("/api/admin/club-applications")
    def club_applications(con: Con, v: Me):
        return logic.club_applications(con, v)

    @app.post("/api/admin/club-applications/{aid}")
    def decide_club_application(aid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.decide_club_application(con, v, aid, bool(body.get("approve")), body.get("reason"))

    # ------------------------------------------------------------ the path to the official ✓ (logic/clubs.py)

    @app.get("/api/orgs/{oid}/official-path")
    def official_path(oid: int, con: Con, v: Me):
        return {"path": logic.official_path(con, v, oid)}

    @app.post("/api/orgs/{oid}/official-path")
    def ask_official(oid: int, con: Con, v: Me):
        return {"path": logic.ask_official(con, v, oid)}

    @app.post("/api/admin/official-requests/{rid}")
    def decide_official(rid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.decide_official(con, v, rid, bool(body.get("approve")), body.get("reason"))

    # ------------------------------------------------------------ the chats directory (§4.11)

    @app.get("/api/chats")
    def list_chats(con: Con, v: Me):
        return logic.chats(con, v)

    @app.post("/api/chats/suggest")
    async def suggest_chat(con: Con, v: Me, body: dict = Body(...)):
        """A chat suggested from the app's own sheet (not through the bot's chat): @name, a t.me link or an
        invite link. {status: sent | waiting | exists | limit | later | slow | notchat | bad, title}."""
        if not v.student:
            raise logic.ApiError("forbidden")
        url = logic.chat_link(str(body.get("link") or "")[:200])
        if not url:
            return {"status": "bad", "title": ""}
        async with httpx.AsyncClient(timeout=10) as http:
            status, title, _ = await bot.suggest(cfg, http, con, v.id, url)
        return {"status": status, "title": title}

    @app.post("/api/chats/{cid}/opened", status_code=204)
    def chat_opened(cid: int, con: Con, v: Me):
        logic.chat_opened(con, v, cid)

    @app.post("/api/admin/feature")
    def feature(con: Con, v: Me, body: dict = Body(...)):
        return logic.feature(con, v, body.get("postId"), body.get("days"))

    @app.post("/api/admin/grants")
    def grant(con: Con, v: Me, body: dict = Body(...)):
        return logic.grant(con, v, body.get("userId"), body.get("code"), body.get("orgId"))

    @app.get("/api/admin/staff")
    def staff(con: Con, v: Me):
        return logic.staff(con, v)

    @app.post("/api/admin/staff")
    def staff_set(con: Con, v: Me, body: dict = Body(...)):
        return logic.set_staff(con, v, body.get("userId"), body.get("role"))

    @app.post("/api/admin/ban")
    def ban(con: Con, v: Me, body: dict = Body(...)):
        return logic.set_ban(con, v, body.get("userId"), body.get("on"), body.get("reason"))

    @app.get("/api/admin/audit")
    def audit(con: Con, v: Me):
        return logic.audit(con, v)

    @app.post("/api/stats", status_code=204)
    def usage_stats(con: Con, v: Me, body: dict = Body(...)):
        logic.stats.add(con, v.id, body)

    @app.get("/api/admin/stats")
    def admin_stats(con: Con, v: Me):
        return logic.admin_stats(con, v)

    @app.post("/api/admin/grants/scan")
    def grant_scan(con: Con, v: Me, body: dict = Body(...)):
        return logic.grant_scan(con, v, body.get("qr"), body.get("code"), body.get("run"))

    @app.post("/api/grant-links/{token}")
    def use_grant_link(token: str, con: Con, v: Me):
        return logic.use_grant_link(con, v, token)

    @app.post("/api/admin/grants/take-back")
    def take_back(con: Con, v: Me, body: dict = Body(...)):
        return logic.take_back(con, v, body.get("userId"), body.get("code"))

    @app.delete("/api/admin/grants/{gid}", status_code=204)
    def ungrant(gid: int, con: Con, v: Me):
        logic.ungrant(con, v, gid)

    @app.post("/api/admin/grants/undo")
    def undo_batch(con: Con, v: Me, body: dict = Body(...)):
        return {"undone": logic.undo_batch(con, v, body.get("batch"))}

    @app.get("/api/admin/grants/of/{uid}")
    def awards_of(uid: int, con: Con, v: Me):
        return logic.awards_of(con, v, uid)

    @app.get("/api/admin/awards")
    def award_counts(con: Con, v: Me):
        return logic.award_counts(con, v)

    @app.get("/api/admin/awards/{award}/people")
    def award_people(award: str, con: Con, v: Me):
        return logic.award_people(con, v, award)

    @app.get("/api/admin/grant-links")
    def my_links(con: Con, v: Me):
        return logic.my_links(con, v)

    @app.delete("/api/admin/grant-links/{token}", status_code=204)
    def revoke_link(token: str, con: Con, v: Me):
        logic.revoke_link(con, v, token)

    # Admin → Awards → Show QR: open one (its first code), then the current code every slot; closing it: revoke above
    @app.post("/api/admin/badge-qr")
    def open_qr(con: Con, v: Me, body: dict = Body(...)):
        return logic.open_qr(con, v, body.get("code"))

    @app.get("/api/admin/badge-qr/{token}")
    def qr_code(token: str, con: Con, v: Me):
        return logic.qr_code(con, v, token)

    @app.post("/api/badge-qr")
    def claim_qr(con: Con, v: Me, body: dict = Body(...)):
        return logic.claim_qr(con, v, body.get("p"))

    # Admin → Awards: find a student with their awards; everyone counted in a check-in session (the owner)
    @app.get("/api/admin/badges/sessions")
    def badge_sessions(con: Con, v: Me):
        return logic.badge_sessions(con, v)

    @app.get("/api/admin/stats/{day}")
    def admin_day(day: int, con: Con, v: Me):
        return logic.admin_day(con, v, day)

    @app.get("/api/admin/ai")
    async def admin_ai(con: Con, v: Me):
        out = logic.admin_ai(con, v, [x.name for x in llm.links(cfg)])
        async with httpx.AsyncClient() as http:
            out["accounts"] = await llm.munito_account(cfg, http)  # Munito's usage and limits per key
        return out

    @app.post("/api/admin/ai/retry", status_code=204)
    def admin_ai_retry(con: Con, v: Me):
        logic.ai_retry(con, v)

    @app.post("/api/admin/chats")
    async def add_chat(con: Con, v: Me, body: dict = Body(...)):
        url = logic.chat_input(v, body)  # before going to Telegram
        async with httpx.AsyncClient(timeout=10) as http:
            peek = await media.chat_peek(http, url)
        if peek["image"]:
            try:
                peek["photo"] = (await _img(media.save, peek["image"], photos))["path"]
            except media.BadImage:
                pass

        def save() -> dict:
            try:
                return logic.add_chat(con, v, body, peek)
            finally:  # a club's row joined the catalog with its own avatar, or the add was refused
                if peek.get("photo") and logic.photo_free(con, peek["photo"]):
                    media.drop(photos, [peek["photo"]])
        return await run_in_threadpool(save)

    @app.put("/api/admin/chats/{cid}/org")
    def chat_org(cid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_chat_org(con, v, cid, body.get("orgId"))

    @app.put("/api/admin/chats/{cid}/section")
    def chat_section(cid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_chat_section(con, v, cid, body.get("section"))

    @app.post("/api/admin/chats/{cid}/approve")
    def approve_chat(cid: int, con: Con, v: Me):
        return logic.approve_chat(con, v, cid)

    @app.delete("/api/admin/chats/{cid}", status_code=204)
    def delete_chat(cid: int, con: Con, v: Me):
        logic.delete_chat(con, v, cid)  # with an Undo: its avatar goes in the bot's round a week later (chats_gone)

    # ------------------------------------------------------------ Admin → Inbox, Done, People (logic/inbox.py)

    @app.get("/api/admin/inbox")
    def admin_inbox(con: Con, v: Me):
        return logic.inbox.inbox(con, v)

    @app.post("/api/admin/done/{aid}/undo", status_code=204)
    def admin_undo(aid: int, con: Con, v: Me):
        media.drop(photos, logic.inbox.undo(con, v, aid))

    @app.get("/api/admin/notifications")
    def admin_notifications(con: Con, v: Me):
        return logic.staff_mutes(con, v)

    @app.put("/api/admin/notifications/{kind}")
    def admin_set_notification(kind: str, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_staff_mute(con, v, kind, body.get("on"))

    @app.get("/api/admin/people")
    def admin_people(con: Con, v: Me, q: str = ""):
        return logic.find_people(con, v, q)

    # the one search (logic/search.py): events and clubs by any of their names, what the searcher may see (Admin: all)
    @app.get("/api/search")
    def find_all(con: Con, v: Me, q: str = ""):
        return {"events": logic.search.events(con, v, q[:80]), "clubs": logic.search.clubs(con, v, q[:80])}

    @app.put("/api/events/{eid}/reg-until")
    def set_reg_until(eid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_reg_until(con, v, eid, body.get("until"))

    @app.post("/api/events/{eid}/door-open")
    def open_door(eid: int, con: Con, v: Me):
        return logic.open_door(con, v, eid)

    @app.delete("/api/admin/events/{eid}", status_code=204)
    def admin_delete_event(eid: int, con: Con, v: Me):
        logic.admin_delete_event(con, v, eid)  # hidden now, gone a day later (the Undo's day)

    @app.post("/api/admin/events/{eid}/restore", status_code=204)
    def admin_undelete_event(eid: int, con: Con, v: Me):
        logic.undo_delete_event(con, v, eid)

    # ------------------------------------------------------------ the clubs registry for DMP (§4.13)

    @app.get("/api/registry/orgs")
    def registry(con: Con, v: Me, back: int = 0):
        return logic.registry(con, v, back)

    @app.get("/api/registry/memos")
    def registry_memos(con: Con, v: Me):
        return logic.registry_memos(con, v)

    @app.get("/api/registry/orgs/{oid}/members")
    def registry_roster(oid: int, con: Con, v: Me):
        return logic.registry_roster(con, v, oid)

    @app.get("/api/registry/search")
    def registry_search(con: Con, v: Me, q: str = ""):
        return logic.registry_search(con, v, q)

    @app.post("/api/registry/orgs/{oid}/official")
    def set_official(oid: int, con: Con, v: Me, body: dict = Body(...)):
        return logic.set_official(con, v, oid, body.get("on"))

    @app.post("/api/registry/export", status_code=204)
    async def registry_export(con: Con, v: Me):
        people = await run_in_threadpool(logic.registry_export, con, v)
        u = logic.one(con, "SELECT tg_id, lang FROM users WHERE id = ?", v.id)
        await send_file(u["tg_id"], *texts.registry_csv(u["lang"], people))

    # ------------------------------------------------------------ share card

    @app.post("/api/share")
    async def share(request: Request, con: Con, v: Me, body: dict = Body(...)):
        """A card for shareMessage (Bot API 8.0), built by the server from its own templates, so nothing the client
        sends ends up in a message from our bot: an event (a photo card), my friend invite, a club's invite or one of my
        achievements (a line of text and our bot's button; no bare links in chats)."""
        kind = body.get("kind")
        try:
            ref = int(body.get("id") or 0)
        except (TypeError, ValueError):
            raise ApiError("bad_input") from None
        lang = logic.one(con, "SELECT lang FROM users WHERE id = ?", v.id)[0]
        stamp = time.time_ns() // 1_000_000
        if kind == "ev":
            e = logic.event(con, v, ref)
            if e["status"] != "published":
                raise ApiError("closed")
            caption, button = texts.share_event(lang, e["title"], e["startsAt"], e["place"],
                                                  " × ".join([e["org"]["name"], *([e["coHost"]["name"]] if e["coHost"] else [])]), e["price"], e["taken"])
            # the photo, else the video's poster (a photo of the same name)
            cover = logic.one(con, """SELECT COALESCE(f.path, x.path) AS path FROM events e LEFT JOIN files f ON f.id = e.cover_file_id
                LEFT JOIN videos x ON x.id = e.video_id AND x.status = 'ready' WHERE e.id = ? AND COALESCE(f.path, x.path) IS NOT NULL""", ref)
            # no photo: the event's own poster (its colour and emoji, as in the app), not the app's old picture
            photo = f"https://{cfg.domain}/media/{cover['path']}.jpg" if cover else \
                f"https://{cfg.domain}/og/poster.jpg?c={(e['color'] or e['tint'] or '#3B6BFF').lstrip('#')}&e={e['emoji'] or 'sparkles_3d'}"
            # "My link": a member of the event's club shares it with a code of its own (never the friend link's), so who came by it is theirs
            start = f"ev_{ref}_{logic.seats.ev_ref(v.id)}" if body.get("mine") and logic.role_in(con, v, e["org"]["id"]) else f"ev_{ref}"
            result = {"type": "photo", "id": f"ev-{ref}-{stamp}", "photo_url": photo, "thumbnail_url": photo, "caption": caption, "parse_mode": "HTML",
                      "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}}
        elif kind in ("fr", "rf", "join", "pres", "rc", "gl"):
            if kind == "gl":  # the admin's award link (logic.grant_link): up to `uses` people (null: no cap) for `days`
                code = body.get("code")
                # an older app's "many": no cap, 14 days
                uses, days = (None, 14) if body.get("many") is True else (body.get("uses", 1), body.get("days", 7))
                token = logic.grant_link(con, v, code, uses, days)
                start = f"gl_{token}"
                fields = {"award": texts.pick(texts.BADGE_TITLES if code in logic.BADGE_OF else texts.ACH_NAMES, lang)[code],
                          "until": texts.when(logic.one(con, "SELECT expires_at FROM grant_links WHERE token = ?", token)[0], lang).split(",")[0]}
                # a badge's variant: its own card, "Get it"; for many, "pass it on"
                kind = ("gb" if uses == 1 else "gm") if code in logic.BADGE_OF else "gl"
            elif kind == "rc":  # a club's open recruitment round (casting.py): anyone may pass it on
                r = logic.one(con, "SELECT r.closes_at, o.name FROM rounds r JOIN orgs o ON o.id = r.org_id WHERE r.org_id = ? AND r.status = 'open' AND r.closes_at > ?",
                              ref, logic.now())
                if not r:
                    raise ApiError("closed")
                start, fields = f"rc_{ref}", {"club": r["name"], "until": texts.when(r["closes_at"], lang)}
            elif kind in ("rf", "fr"):  # my one invite link (referral and friends, Nov 2; "fr" an older app's): my link code, never my ID nor my badge's secret
                if not v.student:
                    raise ApiError("need_student")
                kind, start = "rf", f"r_{logic._qr_code(con, v.id, 'link_code')}"
                fields = {"name": logic.shown_name(logic.one(con, logic.PERSON + " WHERE u.id = ?", v.id))}
            elif kind == "join":  # a one-time member link (§4.5), Vice+; each card is a fresh link; many: the team's 7-day link
                link = logic.team_link(con, v, ref) if body.get("many") is True else logic.invite(con, v, ref)
                start = f"join_{ref}_{link['token']}"
                fields = {"club": logic.one(con, "SELECT name FROM orgs WHERE id = ?", ref)["name"]}
                if "expiresAt" in link:
                    kind, fields["until"] = "jm", texts.when(link["expiresAt"], lang).split(",")[0]
            else:  # a new club's one-time President link (§2), the admin; each card is a fresh link
                start = f"pres_{ref}_{logic.president_link(con, v, ref)['token']}"
                fields = {"club": logic.one(con, "SELECT name FROM orgs WHERE id = ?", ref)["name"]}
            title, text, button = texts.share_invite(kind, lang, **fields)
            result = {"type": "article", "id": f"{kind}-{ref}-{stamp}", "title": title,
                      "input_message_content": {"message_text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
                      "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}}
        elif kind == "aw":  # an achievement of mine (§4.11): the reader's button opens their own progress toward it
            code = body.get("code")
            a = next((x for x in logic.achievements(con, v.id) if x["code"] == code and x["level"] > 0), None) if v.student and code not in logic.PRIVATE else None
            if not a:
                raise ApiError("bad_input")
            title, text, button = texts.share_award(lang, a.get("variant") or code, a["level"], len(a["levels"]), a["levels"][a["level"] - 1]["rarity"])
            result = {"type": "article", "id": f"aw-{code}-{stamp}", "title": title,
                      "input_message_content": {"message_text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
                      "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp=aw_{code}"}]]}}
        else:
            raise ApiError("bad_input")
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                r = (await http.post(f"https://api.telegram.org/bot{cfg.bot_token}/savePreparedInlineMessage", json={
                    "user_id": request.state.tg["id"], "result": result,
                    "allow_user_chats": True, "allow_group_chats": True, "allow_channel_chats": True})).json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("share card: %s", type(exc).__name__)
            raise ApiError("unavailable", "telegram") from None
        if not r.get("ok"):
            log.warning("share card: %s", r.get("description"))
            raise ApiError("unavailable", "telegram")
        return {"id": r["result"]["id"]}

    # ------------------------------------------------------------ the forum: F1 find people (logic/forum.py)

    async def screen(text: str) -> bool | None:
        return await ai.screen(cfg, ai_http(), text, only=screen_only)

    @app.get("/api/forum/me")
    def forum_me(con: Con, v: Forum):
        return logic.my_forum(con, v)

    @app.put("/api/forum/me")
    def forum_set_me(con: Con, v: Forum, body: dict = Body(...)):
        return logic.set_my_forum(con, v, body)

    @app.get("/api/forum/skills")
    def forum_skills(con: Con, v: Forum, q: str = ""):
        return logic.skills(con, v, q[:40])

    @app.post("/api/forum/skills")
    async def forum_new_skill(con: Con, v: Forum, body: dict = Body(...)):
        """A skill by name: the one there is, close ones to pick ({didYouMean}), or a new one if the AI doesn't object
        (no answer: it's made, and stays the maker's own until three people have it or a moderator approves)."""
        found = logic.skill_lookup(con, v, body.get("name"), body.get("force") is True)
        if "name" not in found:
            return found
        if await screen(found["name"]) is False:
            raise ApiError("bad_input", "ai")
        return {"skill": await run_in_threadpool(logic.add_skill, con, v, found["name"])}

    @app.patch("/api/forum/skills/{sid}")
    def forum_skill_mod(sid: int, con: Con, v: Forum, body: dict = Body(...)):
        return logic.skill_mod(con, v, sid, body)

    @app.get("/api/forum/asks")
    def forum_asks(con: Con, v: Forum, skill: int | None = None):
        return logic.asks(con, v, skill)

    @app.post("/api/forum/asks")
    async def forum_new_ask(con: Con, v: Forum, body: dict = Body(...)):
        verdict = await screen(f"{body.get('title') or ''}\n{body.get('body') or ''}")  # no answer: held for a moderator
        return await run_in_threadpool(logic.create_ask, con, v, body, verdict)

    # ------------------------------------------------------------ the forum channel (logic/fchannel.py): posts from the app
    F = logic.fchannel

    @app.get("/api/forum-posts")
    def fchan_mine(con: Con, v: FChan):
        return F.mine(con, v)

    @app.get("/api/forum-posts/revealed")
    def fchan_revealed(con: Con, v: FChan):
        return {"revealed": F.revealed(con), "next": F.next_post(con, v.id)}  # next: when I may post again (the pace), null: now

    @app.get("/api/forum-posts/feed")
    def fchan_feed(con: Con, v: FChan, before: int | None = None):
        return F.feed(con, v, before)

    @app.post("/api/forum-posts")
    async def fchan_new(con: Con, v: FChanWrite, body: dict = Body(...)):
        pid = await run_in_threadpool(F.reserve, con, v, body)  # held, inside the day's one, before the AI is asked
        verdict = await ai.screen_post(cfg, ai_http(), logic.one(con, "SELECT body FROM fchan_posts WHERE id = ?", pid)[0], **_ai_eu())
        p = await run_in_threadpool(F.settle, con, v, pid, verdict)  # live: the bot's round publishes it within seconds
        if p["status"] == "gone":  # the AI saw no message in it, or an ad: said, never silently (the app gives the words back)
            raise ApiError("bad_input", "ad" if verdict == "ad" else "noise", {"post": pid, "appeal": await run_in_threadpool(F.appeals_left, con, v.id) > 0})
        return p | {"ai": verdict in ("person", "flag")}  # held by the AI's word: the app asks why (/why)

    @app.post("/api/forum-posts/photos")
    async def fchan_photo(request: Request, con: Con, v: FChanWrite):
        """A photo for my next post (the file itself is the body), re-encoded (no EXIF) under a random name, never the
        content hash: the same picture as an avatar must not tell an anonymous author (fchannel.add_photo)."""
        data = await read_upload(request)
        await run_in_threadpool(F.photo_room, con, v)  # the hour's slot taken before the work
        saved = await _picture(media.save, data, photos, secrets.token_bytes(32))
        try:
            return await run_in_threadpool(F.add_photo, con, v, saved)
        except BaseException:  # refused (its shape), or the write failed: no files without a row (nothing would find them)
            media.drop(photos, [saved["path"]])
            raise

    @app.post("/api/forum-posts/{pid}/appeal")
    def fchan_appeal(pid: int, con: Con, v: FChanWrite, body: dict = Body(...)):
        return F.appeal(con, v, pid, body)  # to a moderator, the words given back (the refusal wiped them)

    # why the AI refused or held my post or reply, in its own words (ai.explain, phase 2): asked by the app once the
    # outcome is on screen, so nobody waits on it; once each; null: the app keeps its template words
    @app.post("/api/forum-posts/{pid}/why")
    async def fchan_why(pid: int, con: Con, v: FChanWrite, body: dict = Body(default={})):
        text, verdict = await run_in_threadpool(F.why_post, con, v, pid, body)
        got = await ai.explain(cfg, ai_http(), text, verdict, **_ai_eu())
        await run_in_threadpool(F.said, con, "fchan_posts", pid, got)  # the moderator's queue reads it too
        return {"explain": got}

    @app.post("/api/forum-replies/{rid}/why")
    async def fchan_reply_why(rid: int, con: Con, v: FChanWrite):
        text, verdict = await run_in_threadpool(F.why_reply, con, v, rid)
        got = await ai.explain(cfg, ai_http(), text, verdict, **_ai_eu())
        await run_in_threadpool(F.said, con, "fchan_replies", rid, got)
        return {"explain": got}

    @app.delete("/api/forum-posts/{pid}", status_code=204)
    def fchan_drop(pid: int, con: Con, v: FChan):
        F.delete(con, v, pid)

    @app.get("/api/forum-posts/mod")
    def fchan_mod(con: Con, v: FChan):
        return F.mod_queue(con, v)

    @app.post("/api/forum-posts/{pid}/mod", status_code=204)
    def fchan_mod_decide(pid: int, con: Con, v: FChan, body: dict = Body(...)):
        F.mod_decide(con, v, pid, body.get("ok"))

    @app.post("/api/forum-posts/{pid}/restore", status_code=204)
    def fchan_mod_restore(pid: int, con: Con, v: FChan):
        F.mod_restore(con, v, pid)

    @app.post("/api/forum-posts/{pid}/republish", status_code=204)
    def fchan_mod_republish(pid: int, con: Con, v: FChan):
        F.mod_republish(con, v, pid)

    @app.post("/api/forum-posts/{pid}/reveal")
    def fchan_reveal(pid: int, con: Con, v: FChan):
        return F.reveal(con, v, pid)

    # the anonymous author's replies in the comments (fchannel.reply_*): the author's own view and actions; moderators'
    # in the Admin sheet (mod_queue's "replies")
    @app.get("/api/forum-posts/{pid}/replies")
    def fchan_replies(pid: int, con: Con, v: FChan):
        return F.replies(con, v, pid)

    @app.post("/api/forum-posts/{pid}/replies")
    async def fchan_reply(pid: int, con: Con, v: FChanWrite, body: dict = Body(...)):
        rid = await run_in_threadpool(F.reply_reserve, con, v, pid, body)  # held, inside the caps, before the AI is asked
        verdict = await ai.screen_reply(cfg, ai_http(), logic.one(con, "SELECT body FROM fchan_replies WHERE id = ?", rid)[0], **_ai_eu())
        return await run_in_threadpool(F.reply_settle, con, rid, verdict) | {"ai": verdict in ("person", "flag")}  # held by the AI: /why

    @app.delete("/api/forum-replies/{rid}", status_code=204)
    def fchan_reply_drop(rid: int, con: Con, v: FChan):
        F.reply_delete(con, v, rid)

    @app.post("/api/forum-replies/{rid}/mod", status_code=204)
    def fchan_reply_mod(rid: int, con: Con, v: FChan, body: dict = Body(...)):
        F.reply_mod_decide(con, v, rid, body.get("ok"), body.get("again", False))

    @app.post("/api/forum-replies/{rid}/restore", status_code=204)
    def fchan_reply_restore(rid: int, con: Con, v: FChan):
        F.reply_mod_restore(con, v, rid)

    @app.post("/api/forum/asks/{aid}/close")
    def forum_close_ask(aid: int, con: Con, v: Forum, body: dict = Body(default={})):
        return logic.close_ask(con, v, aid, body.get("found"))

    @app.get("/api/forum/mod")
    def forum_mod(con: Con, v: Forum):
        return logic.mod_queue(con, v)

    @app.post("/api/forum/asks/{aid}/hide", status_code=204)
    def forum_hide_ask(aid: int, con: Con, v: Forum):
        logic.mod_hide_ask(con, v, aid)

    @app.post("/api/forum/asks/{aid}/release")
    def forum_release_ask(aid: int, con: Con, v: Forum):
        return logic.release_ask(con, v, aid)

    @app.get("/api/forum/asks/{aid}/people")
    def forum_ask_people(aid: int, con: Con, v: Forum):
        return logic.ask_people(con, v, aid)

    @app.get("/api/forum/people")
    def forum_people(con: Con, v: Forum, skill: int | None = None, q: str = ""):
        return logic.search_people(con, v, skill, q[:40])

    @app.get("/api/forum/contacts")
    def forum_contacts(con: Con, v: Forum):
        return logic.contacts(con, v)

    @app.post("/api/forum/contacts")
    def forum_contact(con: Con, v: Forum, body: dict = Body(...)):
        return logic.contact(con, v, body.get("to"), body.get("ask"))

    @app.post("/api/forum/contacts/{cid}")
    def forum_decide_contact(cid: int, con: Con, v: Forum, body: dict = Body(...)):
        if not isinstance(body.get("yes"), bool) or not logic.decide_contact(con, v.id, cid, body["yes"]):
            raise ApiError("not_found")
        return logic.contacts(con, v)

    @app.post("/api/forum/blocks", status_code=204)
    def forum_block(con: Con, v: Me, body: dict = Body(...)):  # every student: the student forum hides blocked people too
        logic.block(con, v, body.get("user"), body.get("on", True))

    # ------------------------------------------------------------ the frontend

    @app.get("/healthz")
    def health():
        return Response("ok", media_type="text/plain")

    @app.get("/exit")
    def exit_link():
        """kbtu.sow.kz/exit: the short "help me get out" link for posters and chats."""
        return RedirectResponse(f"https://t.me/{cfg.bot_username}?startapp=exit")

    @app.get("/ms.html")
    def ms_page():
        """Where Microsoft sends a student back (msauth.py): the code is traded in this browser (a single-page app's must
        be), the token goes to /api/ms/finish, then back to Telegram"""
        return Response(MS_HTML.replace("__T__", json.dumps(texts.MS_PAGE, ensure_ascii=False)).replace("__CLIENT__", msauth.CLIENT)
                        .replace("__TENANT__", msauth.KBTU).replace("__BOT__", cfg.bot_username), media_type="text/html",
                        headers={"cache-control": "no-store", "referrer-policy": "no-referrer"})

    legal = Path(__file__).with_name("i18n") / "legal"
    LEGAL_NAMES = {"privacy": {"ru": "\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430", "kk": "\u0421\u0430\u044f\u0441\u0430\u0442", "en": "Privacy"},
                   "terms": {"ru": "\u0421\u043e\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435", "kk": "\u041a\u0435\u043b\u0456\u0441\u0456\u043c", "en": "Terms"}}

    @app.get("/privacy")
    def privacy_page(lang: str = "ru"):
        return legal_page("privacy", lang)

    @app.get("/terms")
    def terms_page(lang: str = "ru"):
        return legal_page("terms", lang)

    def legal_page(doc: str, lang: str) -> Response:
        """kbtu.sow.kz/privacy and /terms: plain pages anyone can open, in ru, kk or en; the app links
        them from the sign-in consent and Settings → Privacy."""
        lang = lang if lang in ("ru", "kk", "en") else "ru"
        body = (legal / f"{doc}.{lang}.html").read_text(encoding="utf-8").replace('href="privacy"', f'href="privacy?lang={lang}"')
        langs = " ".join(f'<a href="?lang={x}"{" class=on" if x == lang else ""}>{x.upper()}</a>' for x in ("ru", "kk", "en"))
        other = "terms" if doc == "privacy" else "privacy"
        html = f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KBTU App: {LEGAL_NAMES[doc][lang]}</title><style>
:root {{ color-scheme: light dark; --bg: #fff; --text: #14161f; --dim: #5b6170; --accent: #3B6BFF; --line: #e4e7ee; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #0b0d14; --text: #eef0f6; --dim: #9aa1b2; --accent: #7d9bff; --line: #23273a; }} }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.55 -apple-system, system-ui, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 720px; margin: 0 auto; padding: 20px 16px 48px; }}
nav {{ display: flex; gap: 12px; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid var(--line); }}
nav span {{ display: flex; gap: 8px; }} nav a {{ color: var(--dim); text-decoration: none; font-weight: 600; font-size: 14px; }} nav a.on {{ color: var(--text); }}
h1 {{ font-size: 28px; line-height: 1.2; margin: 24px 0 4px; }} h2 {{ font-size: 19px; margin: 28px 0 8px; }}
.ver {{ color: var(--dim); font-size: 14px; margin-top: 0; }} a {{ color: var(--accent); }} li {{ margin: 6px 0; }} ul {{ padding-left: 22px; }}
</style></head><body><main><nav><a href="{other}?lang={lang}">{LEGAL_NAMES[other][lang]}</a><span>{langs}</span></nav>{body}</main></body></html>"""
        return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})

    if cfg.old_dir:
        app.mount("/old", StaticFiles(directory=cfg.old_dir, html=True), name="old")

    def page() -> Response:
        return Response((dist / "index.html").read_text(encoding="utf-8"), media_type="text/html", headers={"Cache-Control": "no-cache"})

    def file(path: str, request: Request) -> Response | None:
        f = (dist / path).resolve()
        if not path or path == "index.html" or not f.is_file() or dist not in f.parents:
            return None
        # Vite puts a content hash into every name under assets/, so those never change; nor do the map's tiles, whose
        # folder names their cut (map/u1/: a new cut gets a new folder). The rest of public/ (emoji, icons, the howto
        # video) changes rarely: a day, then revalidated in the background; a page (.html) is always asked again
        cache = ("public, max-age=31536000, immutable" if path.startswith(("assets/", "map/")) else
                 "no-cache" if f.suffix == ".html" else "public, max-age=300, stale-while-revalidate=86400")  # art is sometimes replaced in place: 5 min fresh, revalidated after
        headers, send = {"Cache-Control": cache}, f
        if path.startswith("assets/"):
            # the build's ready .br / .gz (vite.config.ts precompress()): no gzip of the same bundle on the loop for
            # every new client; a response that already has Content-Encoding passes GZipMiddleware untouched
            headers["Vary"] = "Accept-Encoding"
            took = {e.strip().split(";")[0] for e in request.headers.get("accept-encoding", "").lower().split(",")}
            for enc, ext in (("br", ".br"), ("gzip", ".gz")):
                if enc in took and (z := f.with_name(f.name + ext)).is_file():
                    headers["Content-Encoding"], send = enc, z
                    break
        r = FileResponse(send, stat_result=send.stat(), headers=headers, media_type=mimetypes.guess_type(f.name)[0])
        if StaticFiles.is_not_modified(None, r.headers, request.headers):  # (it uses no self) If-None-Match / -Modified-Since
            return Response(status_code=304, headers={k: r.headers[k] for k in ("etag", "last-modified", "cache-control", "vary") if k in r.headers})
        return r

    @app.get("/og/poster.jpg")
    def og_poster(c: str = "3B6BFF", e: str = "sparkles_3d"):
        """A coverless event's share picture (media.poster_jpg); public, as Telegram fetches it without a session."""
        emoji = dist / "emoji" / f"{e}.webp"
        if not re.fullmatch(r"[0-9a-fA-F]{6}", c) or not re.fullmatch(r"[a-z0-9_]{1,40}", e) or not emoji.is_file():
            raise ApiError("not_found")
        return Response(media.poster_jpg(f"#{c}", emoji), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/media/{path:path}")
    def media_file(path: str):
        f = (photos / path).resolve()
        if not f.is_file() or photos not in f.parents:
            raise ApiError("not_found")
        return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"})  # named by content hash

    # HEAD too: uptime monitors (UptimeRobot) check with HEAD, and a GET-only route answered them 405
    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def frontend(path: str, request: Request):
        if path.startswith("api/"):
            raise ApiError("not_found")
        start = request.query_params.get("tgWebAppStartParam")
        if start == "old" and cfg.old_dir:  # t.me/KBTUappBot?startapp=old
            return RedirectResponse(f"/{start}/?" + request.url.query, status_code=302)
        if path == "demo" or path.startswith("demo/"):  # the in-browser demo went: its old links open the app in Telegram
            return RedirectResponse(f"https://t.me/{cfg.bot_username}?startapp", status_code=302)
        if f := file(path, request):
            return f
        to = None
        if logic.SHORT.fullmatch(path.strip("/").lower()):
            with pool.conn() as con:  # only past the files (every asset took a connection)
                to = logic.start_by_slug(con, path.strip("/"))
        if to:  # kbtu.sow.kz/<club>: an Instagram bio's link (A5); or a club's own link to itself, an event, its round
            return RedirectResponse(f"https://t.me/{cfg.bot_username}?startapp={to}", status_code=302)
        return page()  # SPA: the app routes itself

    return app


MS_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101633"><title>KBTU App</title><style>
*{box-sizing:border-box;margin:0}
html{background:#0b1029;color-scheme:dark}  /* Safari paints its bars with this, not body's (owner, Oct 20: white strips) */
body{background-attachment:fixed;min-height:100vh;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:24px 16px;color:#fff;
 font:500 16px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Inter",system-ui,sans-serif;-webkit-font-smoothing:antialiased;
 background:radial-gradient(90% 55% at 15% 0%,rgba(124,77,255,.55),transparent 60%),radial-gradient(70% 45% at 100% 100%,rgba(59,200,255,.18),transparent 60%),
 linear-gradient(165deg,#2443B8,#16205a 55%,#0b1029)}
.card{width:100%;max-width:380px;padding:28px 22px 22px;border-radius:30px;text-align:center;background:rgba(255,255,255,.08);
 -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
 box-shadow:inset 0 1px 0 rgba(255,255,255,.25),inset 0 0 0 1px rgba(255,255,255,.1),0 30px 60px -20px rgba(0,0,0,.6)}
.icon{position:relative;width:76px;height:76px;margin:0 auto 18px}
.icon img{width:76px;height:76px;border-radius:21px;box-shadow:0 12px 28px rgba(0,0,0,.45)}
.badge{position:absolute;right:-8px;bottom:-8px;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;
 box-shadow:0 0 0 4px #1b2566;font:800 18px/1 system-ui}
.badge.ok{background:#2FBF71}.badge.bad{background:#E5484D}.badge[hidden]{display:none}
h1{font:750 26px/1.15 -apple-system,BlinkMacSystemFont,"SF Pro Display","Inter",system-ui,sans-serif;letter-spacing:-.02em;margin-bottom:8px}
p{color:rgba(255,255,255,.78);margin-bottom:22px}
p b{color:#fff;font-weight:650}
.btn{display:block;width:100%;height:54px;border:0;border-radius:16px;font:650 17px/54px -apple-system,BlinkMacSystemFont,"Inter",system-ui,sans-serif;
 text-decoration:none;cursor:pointer;-webkit-tap-highlight-color:transparent;transition:transform .15s}
.btn:active{transform:scale(.97)}
.main{color:#fff;background:radial-gradient(120% 90% at 30% 0%,#7f9dff,#3B6BFF 55%,#2448d8);box-shadow:0 10px 24px -8px rgba(59,107,255,.8),inset 0 1px 0 rgba(255,255,255,.5)}
.ghost{margin-top:8px;color:rgba(255,255,255,.75);background:none}
.btn[hidden],small[hidden]{display:none}
small{display:block;margin-top:12px;font-size:13px;color:rgba(255,255,255,.6)}
.spin{width:30px;height:30px;margin:4px auto 6px;border:3px solid rgba(255,255,255,.2);border-top-color:#fff;border-radius:50%;animation:s .9s linear infinite}
.spin[hidden]{display:none}@keyframes s{to{transform:rotate(1turn)}}
</style></head><body><main class="card">
<div class="icon"><img src="/apple-touch-icon.png" alt=""><span class="badge" id="badge" hidden></span></div>
<h1 id="h"></h1><p id="t"></p><div class="spin" id="w"></div>
<button class="btn main" id="yes" hidden></button><a class="btn main" id="open" hidden href="tg://"></a></main><script>
const T = __T__, L = T[(navigator.language || "ru").slice(0, 2)] || T.ru, q = new URLSearchParams(location.hash.slice(1));
const $ = (id) => document.getElementById(id);
history.replaceState(null, "", "/ms.html");  // the code leaves the address bar at once
function show([h, t], mark) { $("h").textContent = h; $("t").textContent = t; $("w").hidden = !!mark || mark === "";
  if (mark) { $("badge").textContent = mark === "ok" ? "\u2713" : "!"; $("badge").className = "badge " + mark; $("badge").hidden = false; } }
function end(state, mark) { show(L[state], mark); $("open").textContent = L.open; $("open").hidden = false; }
show(L.wait);
(async () => {
  const code = q.get("code"), state = q.get("state");
  // Microsoft's own refusals come back as error=: a cancel, or an account from outside KBTU (AADSTS50020 a personal or
  // another directory's account, 50034 no such user in KBTU's)
  const nope = (e, d) => /AADSTS500(20|34)/.test(d || "") ? "notKbtu" : e === "access_denied" ? "nope" : "fail";
  if (q.get("error")) return end(nope(q.get("error"), q.get("error_description")), "bad");
  if (!code || !state) return end("fail", "bad");
  const v = await fetch("/api/ms/verifier?state=" + encodeURIComponent(state)).then((r) => r.ok ? r.json() : r.status === 404 ? 404 : null);
  if (v === 404) return end("expired", "bad");  // the link is older than 15 minutes (or not ours)
  if (!v) return end("fail", "bad");
  // no "link to <name>?" tap any more (owner, Nov 13): the claim below lands only on the Telegram that started the sign-in,
  // so a forwarded link ties nothing whoever finishes it here
  const tok = await fetch("https://login.microsoftonline.com/__TENANT__/oauth2/v2.0/token", { method: "POST", body: new URLSearchParams({
    client_id: "__CLIENT__", grant_type: "authorization_code", code, redirect_uri: location.origin + "/ms.html", code_verifier: v.verifier,
    scope: "openid profile email User.Read" }) }).then((r) => r.json()).catch(() => ({}));
  if (!tok.access_token) return end(nope(tok.error, tok.error_description), "bad");
  const r = await fetch("/api/ms/finish", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ state, token: tok.access_token }) });
  const j = await r.json().catch(() => ({}));
  // the app's start link carries a one-time claim that only the Telegram which started the sign-in can take (so a
  // forwarded sign-in link binds nothing). Tried at once (a browser may ask or refuse without a tap), the button stays for that
  if (r.ok) { const go = "https://t.me/__BOT__?startapp=ms_" + j.claim; end("ok", "ok"); $("open").href = go; location.href = go; return; }
  end({ linked: "linked", other_ms: "otherMs", not_kbtu: "notKbtu" }[j.message] || "fail", "bad");
})().catch(() => end("fail", "bad"));
</script></body></html>"""
