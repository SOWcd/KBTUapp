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
import html
import hmac
import json
import logging
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import httpx
from fastapi import Body, Depends, FastAPI, Query, Request
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.utils import get_typed_return_annotation
from fastapi.routing import APIRoute
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, bot, casting, config, db, logic, media, msauth, receipt, texts, video
from .logic import ApiError, Viewer

log = logging.getLogger("kbtu.app")
# httpx logs every request URL at INFO, and Telegram's URL carries the bot token
logging.getLogger("httpx").setLevel(logging.WARNING)
# pictures queue here for one of two threads, not in the shared pool: a burst of uploads waiting on media's lock
# inside pool threads would hold all 40 and stall every other request
_imgs = anyio.CapacityLimiter(2)


async def _img(fn, *args):
    return await anyio.to_thread.run_sync(fn, *args, limiter=_imgs)

SEEN_EVERY = 600            # refresh users.seen_at and Telegram names at most every 10 min
# typed in by the student (the KBTU-password sign-in is gone since Oct 19): a name in any alphabet (hyphen, apostrophe, space), and a student ID like
# 24B031234 (year, a letter or two for the degree, the number)
NAME = re.compile(r"[^\W\d_](?:[^\W\d_]|[-' ]){0,39}")
STUDENT_ID = re.compile(r"\d{2}[A-Z]{1,2}\d{5,7}")


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
    in Python: two thirds of the Afisha's time on a big database (load test, Oct 7). Our answers are plain JSON
    already, so `Any` checks nothing and only changes who writes the bytes."""

    def __init__(self, path: str, endpoint, *, response_model=Default(None), status_code: int | None = None, **kw) -> None:
        if isinstance(response_model, DefaultPlaceholder) and get_typed_return_annotation(endpoint) is None and status_code != 204:
            response_model = Any
        super().__init__(path, endpoint, response_model=response_model, status_code=status_code, **kw)


def create(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.load()
    def after(con) -> None:
        logic.sync_levels(con)  # a new achievement or level counts what students already did
        logic.name_slugs(con)
        if cfg.seed:
            logic.seed_schools(con, Path(cfg.db_path).resolve().parent / "media")  # KBTU's schools, once
    db.init(cfg.db_path, after=after)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(bot.run(cfg)) if cfg.background else None
        yield
        if task:
            task.cancel()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.router.route_class = _Route
    dist = Path(cfg.web_dist).resolve()
    photos = Path(cfg.db_path).resolve().parent / "media"   # next to the database: one volume to back up
    receipts = Path(cfg.db_path).resolve().parent / "receipts"   # private (§4.3): never under /media, only through the API
    # the "To calendar" link is signed by one worker and may be opened on another: one key for all, from the env
    logic.ICS_KEY = hmac.new(cfg.token_key, b"kbtu-ics", hashlib.sha256).digest()

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

    # ------------------------------------------------------------ who is calling

    pool = db.Pool(cfg.db_path)

    def conn() -> Iterator:
        with pool.conn() as con:
            yield con

    def viewer(request: Request, con=Depends(conn)) -> Viewer:
        head = request.headers.get("authorization", "")
        tg = auth.check_init_data(head[4:], cfg.bot_token) if head.startswith("tma ") else None
        if not tg:
            raise ApiError("forbidden", "init_data")
        request.state.tg = tg
        return _upsert(con, tg)

    def _upsert(con, tg: dict) -> Viewer:
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
                                                         "admin" if tg["id"] in cfg.admins else "user", dm, t, t))
            u = logic.one(con, "SELECT * FROM users WHERE tg_id = ?", tg["id"])
            logic.visit(con, u["id"], t)
        else:
            # ADMIN_TG_IDS are always admins; everyone else's role is given in the app (owner, Oct 22)
            role = "admin" if tg["id"] in cfg.admins and not u["banned_at"] else u["role"]  # a ban outranks the env
            dm = max(dm, u["can_dm"])  # only the bot turns it off (when Telegram says it's blocked)
            if (u["tg_username"], u["tg_first_name"], u["tg_last_name"], u["tg_photo_url"]) != fresh or (role, dm) != (u["role"], u["can_dm"]) \
                    or t - u["seen_at"] > SEEN_EVERY or logic.day_of(t) != logic.day_of(u["seen_at"]):
                con.execute("""UPDATE users SET tg_username = ?, tg_first_name = ?, tg_last_name = ?, tg_photo_url = ?, role = ?, can_dm = ?, seen_at = ?
                    WHERE id = ?""", (*fresh, role, dm, t, u["id"]))
                logic.visit(con, u["id"], t)
                u = logic.one(con, "SELECT * FROM users WHERE id = ?", u["id"])
        if u["banned_at"]:
            raise ApiError("forbidden", "banned", logic.ban_info(con, u["id"]))
        # a typed-in row (manual, no Microsoft yet) acts as nobody until Microsoft confirms it (owner, Oct 20: Microsoft only)
        return Viewer(u["id"], u["role"], logic.one(con, "SELECT 1 FROM students WHERE user_id = ? AND manual = 0", u["id"]) is not None)

    # ------------------------------------------------------------ me and sign-in

    @app.get("/api/me")
    def get_me(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.me(con, v)

    @app.patch("/api/me")
    def patch_me(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.update_me(con, v, body)

    @app.get("/api/me/delete")
    def delete_info(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.delete_info(con, v)

    @app.post("/api/me/delete")
    def ask_delete(body: dict | None = Body(None), con=Depends(conn), v: Viewer = Depends(viewer)):
        """§4.8: in a week, with the way back meanwhile (logic.ask_delete); the bot's round runs it (bot.send_due)."""
        return logic.ask_delete(con, v, (body or {}).get("photos") is True)

    @app.post("/api/me/consent")
    def consent(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.consent(con, v, body.get("version"))

    @app.post("/api/me/dm")
    def dm_on(body: dict | None = Body(None), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.dm_on(con, v, (body or {}).get("event"))

    @app.post("/api/me/keep")
    def keep_me(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.keep_me(con, v)

    # ------------------------------------------------------------ admin: clubs and their teams (pilot)

    @app.get("/api/admin/orgs")
    def admin_orgs(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_orgs(con, v)

    @app.get("/api/admin/orgs/{oid}/events")
    def admin_org_events(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_org_events(con, v, oid)

    @app.post("/api/admin/orgs")
    def admin_create_org(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_create_org(con, v, body)

    @app.post("/api/admin/orgs/{oid}/president-link")
    def admin_president_link(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.president_link(con, v, oid)  # the QR the admin shows a President face to face (owner, Oct 16)

    @app.put("/api/admin/orgs/{oid}/hidden")
    def admin_hide_org(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_hide_org(con, v, oid, bool(body.get("hidden")))

    @app.put("/api/admin/orgs/{oid}/role")
    def admin_set_role(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_set_role(con, v, oid, body)

    @app.post("/api/kbtu/manual")
    def kbtu_manual(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        """After Microsoft, someone new types the student ID and year (Microsoft knows neither: KBTU leaves employeeId
        empty, measured Oct 20), so the ID is the student's word, tied to a real @kbtu.kz account. Microsoft only
        (owner, Oct 20): no pending Microsoft sign-in, no account. An ID held by a typed-in row with no Microsoft goes
        to the Microsoft one; held by a Microsoft-confirmed one, it's refused; the admins hear of both (id_clash)."""
        consent = str(body.get("consentVersion") or "")
        sid = str(body.get("studentId") or "").strip().upper()
        course = logic.course_of(sid)  # the ID says the year (audit M3: a typed "1" took free first-year seats); None: a year ahead
        ms = logic.ms_pending(con, v.id)
        # the account's names when Microsoft has them (ms_link writes them anyway); typed only where it has none
        names = [(" ".join(str((ms or {}).get(m) or "").split())[:40], " ".join(str(body.get(k) or "").split()))
                 for m, k in (("first", "firstName"), ("last", "lastName"))]
        first, last = (mine or typed for mine, typed in names)
        if consent != logic.CONSENT:
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
            if taken:
                logic.id_clash(con, sid, v.id, taken["user_id"])
            held = taken and not (taken["manual"] and taken["ms_oid"] is None)
            if taken and not held:
                for t in ("students", "schedule_classes"):  # typed in, never confirmed: gives way (as admin.py unlink)
                    con.execute(f"DELETE FROM {t} WHERE user_id = ?", (taken["user_id"],))
            if not held:
                con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
                        synced_at, manual) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""", (v.id, sid, first, last, course, consent, now, now, now))
                logic.ms_link(con, v.id, ms)
        if held:  # after the commit: the admins' message stays
            raise ApiError("conflict", "sid_taken")  # someone with a real account holds it: the admin sorts it out
        return logic.me(con, Viewer(v.id, v.role, True))

    @app.post("/api/ms/start")
    def ms_start(v: Viewer = Depends(viewer)):
        """The Microsoft sign-in link for me (msauth.py); the Mini App opens it outside Telegram"""
        return {"url": msauth.link(cfg.token_key, v.id, cfg.domain)}

    @app.get("/api/ms/verifier")
    def ms_verifier(state: str, con=Depends(conn)):
        """The PKCE verifier. No "link to <name>?" question (owner, Oct 23: minimum steps)"""
        uid = msauth.state_uid(cfg.token_key, state)
        if not uid or not logic.one(con, "SELECT 1 FROM users WHERE id = ?", uid):
            raise ApiError("not_found")  # a stale link: ms.html says "expired"
        return {"verifier": msauth.verifier(cfg.token_key, state)}

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
            # linked at once, no code back from the app: a forwarded sign-in link is caught by hand and unlinked (owner, Oct 24)
            logic.ms_apply(con, uid, who)
            return {"ok": True}

    @app.get("/api/me/schedule")
    def my_schedule(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.schedule(con, v)


    @app.get("/api/me/tickets")
    def my_tickets(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.tickets(con, v)

    # ------------------------------------------------------------ events

    @app.get("/api/events")
    def list_events(frm: int | None = Query(None, alias="from"), to: int | None = None, org: int | None = None,
                    con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.events(con, v, frm, to, org)

    @app.get("/api/events/past")
    def list_past(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.past_events(con, v)

    @app.post("/api/me/unlocked")
    def seen_unlock(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.seen_unlock(con, v, body.get("code"), body.get("level"))
        return {"unlocked": logic.unlocked(con, v)}

    @app.post("/api/me/calendar")
    def my_calendar(con=Depends(conn), v: Viewer = Depends(viewer)):
        """My calendar feed: the page that subscribes (Apple) and the feed itself (Google's "add by URL")."""
        t = logic.cal_token(con, v)
        return {"page": f"https://{cfg.domain}/cal/{t}", "feed": f"webcal://{cfg.domain}/cal/{t}.ics"}

    @app.get("/cal/{token}.ics")
    def calendar_feed(token: str, con=Depends(conn)):
        body = logic.cal_feed(con, token, lambda eid: f"https://t.me/{cfg.bot_username}?startapp=ev_{eid}")
        return Response(body, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.get("/cal/{token}")
    def calendar_page(token: str, request: Request, con=Depends(conn)):
        """Opened from the app in the phone's browser: hands webcal:// to the calendar at once, a button if it asks."""
        logic.cal_feed(con, token, str)  # 404 for a token that isn't (or no longer is) anyone's
        lang = next((x for x in ("ru", "kk", "en") if x in request.headers.get("accept-language", "")[:5].lower()), "ru")
        title, text, button = texts.CAL_PAGE[lang]
        url = html.escape(f"webcal://{cfg.domain}/cal/{token}.ics", quote=True)
        page = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title}</title><style>body{{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.45 -apple-system,system-ui,sans-serif;'
                f'background:#0B1020;color:#fff;text-align:center}}main{{padding:32px 24px;max-width:360px}}h1{{font-size:24px;margin:0 0 8px}}p{{opacity:.75;margin:0 0 24px}}'
                f'a{{display:inline-block;padding:14px 28px;border-radius:999px;background:#3B6BFF;color:#fff;font-weight:650;text-decoration:none}}</style></head>'
                f'<body><main><h1>📅 {title}</h1><p>{text}</p><a href="{url}">{button}</a></main><script>location.href="{url}"</script></body></html>')
        return Response(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.get("/api/events/{eid}/ics")
    def event_ics(eid: int, k: str = "", con=Depends(conn)):
        # no session: Telegram hands the link to the phone's browser, which gives the file to the calendar
        if not hmac.compare_digest(k, logic.ics_sig(eid)):
            raise ApiError("not_found")
        return Response(logic.event_ics(con, eid, f"https://t.me/{cfg.bot_username}?startapp=ev_{eid}"), media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": f'inline; filename="kbtu-event-{eid}.ics"', "Cache-Control": "no-store"})

    @app.get("/api/events/{eid}")
    def get_event(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.event(con, v, eid)

    @app.post("/api/events/{eid}/registration")
    def register(eid: int, body: dict = Body(default={}), con=Depends(conn), v: Viewer = Depends(viewer)):
        invited = body.get("invitedBy")
        return logic.register(con, v, eid, invited if isinstance(invited, int) else None)

    @app.delete("/api/events/{eid}/registration")
    def unregister(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.unregister(con, v, eid)

    @app.put("/api/events/{eid}/saved", status_code=204)
    def save(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.set_saved(con, v, eid, True)

    @app.delete("/api/events/{eid}/saved", status_code=204)
    def unsave(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.set_saved(con, v, eid, False)

    # ------------------------------------------------------------ orgs and news

    @app.get("/api/orgs")
    def list_orgs(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.orgs(con, v)

    @app.get("/api/orgs/{oid}")
    def get_org(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.org(con, v, oid)

    @app.put("/api/orgs/{oid}/subscription")
    def subscribe(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.subscribe(con, v, oid, True)

    @app.delete("/api/orgs/{oid}/subscription")
    def unsubscribe(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.subscribe(con, v, oid, False)

    @app.post("/api/orgs/{oid}/join-requests")
    def apply(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.apply(con, v, oid)

    @app.delete("/api/orgs/{oid}/join-requests/mine")
    def withdraw(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.withdraw(con, v, oid)

    @app.get("/api/posts")
    def list_posts(scope: str = "all", con=Depends(conn), v: Viewer = Depends(viewer)):
        if scope.startswith("org:") and not scope[4:].isdigit():
            raise ApiError("bad_input")
        return logic.posts(con, v, scope)

    @app.post("/api/orgs/{oid}/posts")
    def create_post(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.create_post(con, v, oid, body)

    @app.patch("/api/posts/{pid}")
    def update_post(pid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.update_post(con, v, pid, body)

    @app.delete("/api/posts/{pid}", status_code=204)
    def hide_post(pid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.hide_post(con, v, pid)

    @app.post("/api/posts/read", status_code=204)
    def read_posts(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.read_posts(con, v, body.get("ids") if isinstance(body.get("ids"), list) else [])

    @app.put("/api/posts/{pid}/reactions/{kind}")
    def react(pid: int, kind: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.react(con, v, pid, kind, True)

    @app.delete("/api/posts/{pid}/reactions/{kind}")
    def unreact(pid: int, kind: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.react(con, v, pid, kind, False)

    @app.get("/api/users/{uid}")
    def person(uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.person(con, v, uid)

    # ------------------------------------------------------------ Studio

    # ---- friends (§4.7) ----
    @app.get("/api/friends")
    def friends(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.friends(con, v)

    @app.get("/api/friends/find")
    def find_friend(username: str = "", con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.find_student(con, v, username)

    @app.post("/api/friends/requests")
    def ask_friend(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        uid = body.get("userId")
        if not isinstance(uid, int) or isinstance(uid, bool):
            raise ApiError("bad_input")
        return logic.ask_friend(con, v, uid)

    @app.post("/api/friends/requests/{uid}/{answer}")
    def answer_friend(uid: int, answer: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        if answer not in ("accept", "decline"):
            raise ApiError("not_found")
        return logic.answer_friend(con, v, uid, answer == "accept")

    @app.delete("/api/friends/requests/{uid}", status_code=204)
    def take_back_request(uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.take_back_request(con, v, uid)

    @app.delete("/api/friends/{uid}", status_code=204)
    def unfriend(uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.unfriend(con, v, uid)

    @app.post("/api/friends/link")
    def friend_link(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.friend_link(con, v)

    @app.get("/api/friends/link/{token}")
    def friend_link_used(token: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.friend_link_used(con, v, token)

    @app.post("/api/friends/link/{token}")
    def use_friend_link(token: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.use_friend_link(con, v, token)

    # ------------------------------------------------------------ casting: a club's recruitment round (casting.py)

    @app.get("/api/orgs/{oid}/round")
    def round_view(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.view(con, v, oid)

    @app.post("/api/orgs/{oid}/round")
    def round_open(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.open_round(con, v, oid, body)

    @app.patch("/api/rounds/{rid}")
    def round_update(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.update_round(con, v, rid, body)

    @app.post("/api/rounds/{rid}/apply")
    def round_apply(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.apply(con, v, rid, body)

    @app.delete("/api/rounds/{rid}/apply")
    def round_withdraw(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.withdraw(con, v, rid)

    @app.get("/api/rounds/{rid}/apps")
    def round_apps(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.apps(con, v, rid)

    @app.post("/api/round-apps/{aid}/vote")
    def round_vote(aid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.vote(con, v, aid, body)

    @app.post("/api/round-apps/{aid}/decide")
    def round_decide(aid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.decide(con, v, aid, body)

    @app.get("/api/rounds/{rid}/slots")
    def round_slots(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.slots(con, v, rid)

    @app.post("/api/rounds/{rid}/slots")
    def round_add_slots(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.add_slots(con, v, rid, body)

    @app.delete("/api/round-slots/{sid}")
    def round_drop_slot(sid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.drop_slot(con, v, sid)

    @app.post("/api/rounds/{rid}/invite")
    def round_invite(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.invite(con, v, rid)

    @app.post("/api/rounds/{rid}/book")
    def round_book(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.book(con, v, rid, body)

    @app.post("/api/round-apps/{aid}/came")
    def round_came(aid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.showed(con, v, aid, body)

    @app.post("/api/rounds/{rid}/send")
    def round_send(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return casting.send(con, v, rid)

    @app.get("/api/orgs/{oid}/memo")
    def org_memo(oid: int, later: bool = False, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.memo(con, v, oid, later)

    @app.get("/api/map/graph")
    def map_graph(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.map_graph(con)

    @app.post("/api/orgs/{oid}/memo/item")
    def memo_item(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return {"text": logic.memo_item(con, v, oid, body)}

    @app.post("/api/orgs/{oid}/memo/opened", status_code=204)
    def memo_opened(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.memo_opened(con, v, oid)

    @app.post("/api/orgs/{oid}/memo/sent", status_code=204)
    def memo_sent(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.memo_sent(con, v, oid, body.get("ids"))

    @app.post("/api/orgs/{oid}/memo/again/{eid}", status_code=204)
    def memo_again(oid: int, eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.memo_again(con, v, oid, eid)

    @app.put("/api/orgs/{oid}/memo/sign")
    def memo_sign(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.memo_sign(con, v, oid, body)

    @app.post("/api/events/{eid}/place")
    def change_place(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.change_place(con, v, eid, body.get("place"))

    @app.get("/api/orgs/{oid}/events")
    def org_events(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.org_events(con, v, oid)

    @app.post("/api/orgs/{oid}/events")
    def create_event(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.create_event(con, v, oid, body)

    @app.patch("/api/events/{eid}")
    def update_event(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.update_event(con, v, eid, body)

    @app.post("/api/events/{eid}/volunteer")
    def volunteer_apply(eid: int, body: dict = Body(default={}), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.volunteer_apply(con, v, eid, body.get("note"))

    @app.delete("/api/events/{eid}/volunteer")
    def volunteer_leave(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.volunteer_leave(con, v, eid)

    @app.get("/api/events/{eid}/volunteers")
    def volunteers(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.volunteers_list(con, v, eid)

    @app.put("/api/events/{eid}/volunteers/{uid}")
    def volunteer_decide(eid: int, uid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.volunteer_decide(con, v, eid, uid, body.get("yes"))

    @app.post("/api/events/{eid}/chat")
    def chat_start(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        token = logic.chat_start(con, v, eid)  # the bot comes in as an admin that may add people, pin and delete
        return {"url": f"https://t.me/{cfg.bot_username}?startgroup=ec_{token}&admin=invite_users+pin_messages+delete_messages+restrict_members"}

    @app.post("/api/events/{eid}/publish")
    def publish(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.publish_event(con, v, eid)

    @app.post("/api/events/{eid}/cancel")
    def cancel(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.cancel_event(con, v, eid)

    @app.delete("/api/events/{eid}", status_code=204)
    def delete_event(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        gone, photo = logic.delete_event(con, v, eid)
        for root, rels in ((receipts, gone), (photos, photo)):
            for rel in rels:
                for ext in (".webp", ".t.webp", ".jpg"):
                    (root / f"{rel}{ext}").unlink(missing_ok=True)

    @app.get("/api/events/{eid}/attendees")
    def attendees(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.attendees(con, v, eid)

    @app.post("/api/events/{eid}/checkin")
    def checkin(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        """A scanned or typed code, or {userId}: by name from the door list (no QR)."""
        uid, code = body.get("userId"), body.get("code")
        if isinstance(uid, int) and not isinstance(uid, bool):
            return logic.checkin_by_name(con, v, eid, uid)
        if not isinstance(code, str) or len(code) > 64:
            raise ApiError("bad_input")
        return logic.checkin(con, v, eid, code)

    @app.put("/api/events/{eid}/rating")
    def rate_event(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.rate_event(con, v, eid, body.get("score"), body.get("comment"))

    @app.post("/api/events/{eid}/updates")
    def post_update(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.post_update(con, v, eid, body.get("body") if isinstance(body.get("body"), str) else "")

    @app.delete("/api/events/{eid}/updates/{uid}", status_code=204)
    def delete_update(eid: int, uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.delete_update(con, v, eid, uid)

    @app.delete("/api/events/{eid}/checkin/{uid}", status_code=204)
    def undo_checkin(eid: int, uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.undo_checkin(con, v, eid, uid)

    @app.get("/api/events/{eid}/door")
    def door(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.door(con, v, eid)

    @app.get("/api/events/{eid}/door/guests")
    def door_guests(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.door_guests(con, v, eid)

    @app.post("/api/events/{eid}/door/guests")
    def add_door_guest(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        """A walk-in by the full name they typed (A19)."""
        return logic.add_door_guest(con, v, eid, body.get("name"))

    @app.delete("/api/events/{eid}/door/guests/{gid}", status_code=204)
    def undo_door_guest(eid: int, gid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.undo_door_guest(con, v, eid, gid)

    @app.post("/api/orgs/{oid}/invites")
    def invite(oid: int, body: dict | None = Body(None), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.invite(con, v, oid, body.get("dept") if isinstance(body, dict) else None)

    @app.post("/api/invites/{token}")
    def accept_invite(token: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.accept_invite(con, v, token)

    @app.get("/api/orgs/{oid}/members")
    def team(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.team(con, v, oid)

    @app.get("/api/orgs/{oid}/people")
    def people(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.people(con, v, oid)

    @app.patch("/api/orgs/{oid}/members/{uid}")
    def update_member(oid: int, uid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.update_member(con, v, oid, uid, body)

    # Team 2.0 (§2b): the club's roles and tags, probation, removal by request, bans
    @app.get("/api/orgs/{oid}/team")
    def team_setup(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.team_setup(con, v, oid)

    @app.post("/api/orgs/{oid}/roles")
    def add_role(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.save_role(con, v, oid, body)

    @app.patch("/api/orgs/{oid}/roles/{rid}")
    def edit_role(oid: int, rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.save_role(con, v, oid, body, rid)

    @app.delete("/api/orgs/{oid}/roles/{rid}")
    def delete_role(oid: int, rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.delete_role(con, v, oid, rid)

    @app.post("/api/orgs/{oid}/tags")
    def add_tag(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.save_tag(con, v, oid, body)

    @app.patch("/api/orgs/{oid}/tags/{tid}")
    def edit_tag(oid: int, tid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.save_tag(con, v, oid, body, tid)

    @app.delete("/api/orgs/{oid}/tags/{tid}")
    def delete_tag(oid: int, tid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.delete_tag(con, v, oid, tid)

    @app.post("/api/orgs/{oid}/members/{uid}/remove")
    def remove(oid: int, uid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.remove(con, v, oid, uid, body)

    @app.post("/api/removals/{rid}", status_code=204)
    def decide_removal(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.decide_removal(con, v, rid, body.get("approve"))

    @app.delete("/api/orgs/{oid}/bans/{uid}", status_code=204)
    def unban(oid: int, uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.unban(con, v, oid, uid)

    @app.delete("/api/orgs/{oid}/members/{uid}", status_code=204)
    def remove_member(oid: int, uid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.remove_member(con, v, oid, uid)

    @app.post("/api/orgs/{oid}/transfer")
    def transfer(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        try:
            uid = int(body.get("userId"))
        except (TypeError, ValueError):
            raise ApiError("bad_input") from None
        return logic.transfer(con, v, oid, uid)

    @app.get("/api/orgs/{oid}/join-requests")
    def join_requests(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.join_requests(con, v, oid)

    @app.post("/api/join-requests/{rid}/accept", status_code=204)
    def accept(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.decide_join(con, v, rid, True)

    @app.post("/api/join-requests/{rid}/reject", status_code=204)
    def reject(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.decide_join(con, v, rid, False)

    @app.patch("/api/orgs/{oid}")
    def update_org(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.update_org(con, v, oid, body)

    # ------------------------------------------------------------ photos

    @app.post("/api/photos")
    async def upload_photo(request: Request, con=Depends(conn), v: Viewer = Depends(viewer)):
        """The file itself is the body (no multipart). Decoding and re-encoding run off the event loop."""
        data = await read_upload(request)
        if not logic.organizes(con, v):  # before the work, not only after it
            raise ApiError("forbidden")
        try:
            saved = await _img(media.save, data, photos)
        except media.BadImage:
            raise ApiError("bad_input", "not_an_image") from None
        return logic.add_photo(con, v, saved)

    # an event's video (video.py): the size first, then the file in pieces at their offsets, then "done"; a piece sent
    # again after a lost answer is told where the file stands instead of being added twice
    uploads = Path(cfg.db_path).resolve().parent / "uploads"   # originals: never under /media, deleted once compressed

    @app.post("/api/videos")
    def new_video(body: dict, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.new_video(con, v, body.get("size"), body.get("wide", False))

    @app.put("/api/videos/{vid}")
    async def video_piece(vid: int, at: int, request: Request, con=Depends(conn), v: Viewer = Depends(viewer)):
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
    def video_done(vid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        f = uploads / str(vid)
        return logic.video_uploaded(con, v, vid, f.stat().st_size if f.exists() else 0)

    @app.get("/api/videos/{vid}")
    def video_state(vid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.video_shape(logic.my_video(con, v, vid))

    @app.delete("/api/me/photo")
    def drop_my_photo(con=Depends(conn), v: Viewer = Depends(viewer)):
        for rel in logic.drop_my_photo(con, v):
            for ext in (".webp", ".t.webp", ".jpg"):
                (photos / f"{rel}{ext}").unlink(missing_ok=True)
        return logic.me(con, v)

    # my own photo instead of Telegram's (owner, Oct 5): the body as in /api/photos; the one it replaces leaves the disk
    @app.post("/api/me/photo")
    async def upload_my_photo(request: Request, con=Depends(conn), v: Viewer = Depends(viewer)):
        data = await read_upload(request)
        logic.need_student(v)  # before the work, not only after it
        try:
            saved = await _img(media.save, data, photos)
        except media.BadImage:
            raise ApiError("bad_input", "not_an_image") from None
        for rel in logic.set_photo(con, v, saved):
            for ext in (".webp", ".t.webp", ".jpg"):
                (photos / f"{rel}{ext}").unlink(missing_ok=True)
        return logic.me(con, v)

    # paid events (§4.3): the receipt is the body, like /api/photos; its image only through the API, to whom may see it
    @app.post("/api/events/{eid}/receipt")
    async def upload_receipt(eid: int, request: Request, con=Depends(conn), v: Viewer = Depends(viewer)):
        data = await read_upload(request)
        logic.receipt_open(con, v, eid)  # before the work, not only after it
        try:  # Kaspi's PDF or a screenshot; read by OCR (~0.5 s) right here, no queue
            saved, read = await _img(receipt.take, data, receipts)
        except media.BadImage:
            raise ApiError("bad_input", "not_an_image") from None
        except receipt.NotReceipt:
            raise ApiError("bad_input", "not_receipt") from None
        return logic.add_receipt(con, v, eid, saved, read)

    @app.get("/api/receipts/{rid}/image")
    def receipt_image(rid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return FileResponse(receipts / f"{logic.receipt_path(con, v, rid)}.webp", media_type="image/webp", headers={"Cache-Control": "private, no-store"})

    @app.post("/api/receipts/{rid}/review", status_code=204)
    def review_receipt(rid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.review_receipt(con, v, rid, body.get("reject"))

    # comments under posts and events, reports (§4.10)
    @app.get("/api/{kind}s/{tid}/comments")
    def get_comments(kind: str, tid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.comments(con, v, kind, tid)

    @app.post("/api/{kind}s/{tid}/comments")
    def add_comment(kind: str, tid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.add_comment(con, v, kind, tid, body.get("body"), body.get("asOrg"), body.get("replyTo"))

    @app.patch("/api/{kind}s/{tid}/comments")
    def switch_comments(kind: str, tid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.set_comments_on(con, v, kind, tid, body.get("on"))

    @app.delete("/api/comments/{cid}", status_code=204)
    def delete_comment(cid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.delete_comment(con, v, cid)

    @app.post("/api/reports", status_code=204)
    def report(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.report(con, v, body.get("target"), body.get("id"), body.get("reason"), body.get("note"))

    @app.get("/api/admin/taken-down")
    def taken_down(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.taken_down(con, v)

    @app.post("/api/admin/taken-down/{target}/{tid}/restore", status_code=204)
    def restore(target: str, tid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.restore(con, v, target, tid)

    @app.get("/api/admin/reports")
    def report_queue(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.report_queue(con, v)

    @app.post("/api/admin/reports/{target}/{tid}", status_code=204)
    def resolve_report(target: str, tid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        for rel in logic.resolve_report(con, v, target, tid, bool(body.get("remove"))):  # a profile's own photo
            for ext in (".webp", ".t.webp", ".jpg"):
                (photos / f"{rel}{ext}").unlink(missing_ok=True)

    @app.post("/api/events/{eid}/seats")
    def add_seats(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.add_seats(con, v, eid, body.get("add"))

    @app.post("/api/events/{eid}/decline")
    def decline(eid: int, body: dict | None = Body(None), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.decline(con, v, eid, (body or {}).get("note"))

    @app.get("/api/events/{eid}/meeting")
    def meeting_answers(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.meeting_answers(con, v, eid)

    @app.get("/api/events/{eid}/leaders")
    def leaders_answers(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.leaders_answers(con, v, eid)

    @app.get("/api/events/{eid}/invites")
    def event_invites(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.event_invites(con, v, eid)

    @app.post("/api/events/{eid}/invites")
    def invite_friend(eid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.invite_friend(con, v, eid, body.get("userId"))

    @app.post("/api/events/{eid}/photos")
    async def add_album_photo(eid: int, request: Request, con=Depends(conn), v: Viewer = Depends(viewer)):
        """A photo for the guests' album: the file is the body, like /api/photos."""
        data = await read_upload(request)
        if not logic.can_add_album_photo(con, v, eid):  # before the work, not only after it
            raise ApiError("forbidden")
        try:
            saved = await _img(media.save, data, photos)
        except media.BadImage:
            raise ApiError("bad_input", "not_an_image") from None
        return logic.add_album_photo(con, v, eid, saved)

    @app.delete("/api/events/{eid}/photos/{fid}")
    def remove_album_photo(eid: int, fid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        ev, gone = logic.remove_album_photo(con, v, eid, fid)
        for rel in gone:
            for ext in (".webp", ".t.webp", ".jpg"):
                (photos / f"{rel}{ext}").unlink(missing_ok=True)
        return ev

    # ------------------------------------------------------------ attendee list as a file

    @app.post("/api/events/{eid}/attendees/export", status_code=204)
    async def export_attendees(eid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        """The bot sends the CSV to the organizer's own chat: it opens on any phone and can be forwarded (a download
        link would need the app's sign-in, which Telegram's downloader doesn't carry)."""
        e, people = logic.attendees_export(con, v, eid)
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
    def my_club_application(con=Depends(conn), v: Viewer = Depends(viewer)):
        return {"application": logic.my_club_application(con, v)}

    @app.post("/api/club-applications")
    def apply_club(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.apply_club(con, v, body)

    @app.get("/api/admin/club-applications")
    def club_applications(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.club_applications(con, v)

    @app.post("/api/admin/club-applications/{aid}")
    def decide_club_application(aid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.decide_club_application(con, v, aid, bool(body.get("approve")), body.get("reason"))

    # ------------------------------------------------------------ the chats directory (§4.11)

    @app.get("/api/chats")
    def list_chats(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.chats(con, v)

    @app.post("/api/chats/suggest")
    async def suggest_chat(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        """A chat suggested from the app's own sheet (owner, Oct 21: not through the bot's chat): @name, a t.me link or an
        invite link. {status: sent | waiting | exists | limit | later | slow | notchat | bad, title}."""
        if not v.student:
            raise logic.ApiError("forbidden")
        url = logic.chat_link(str(body.get("link") or "")[:200])
        if not url:
            return {"status": "bad", "title": ""}
        async with httpx.AsyncClient(timeout=10) as http:
            status, title = await bot.suggest(cfg, http, con, v.id, url)
        return {"status": status, "title": title}

    @app.post("/api/chats/{cid}/opened", status_code=204)
    def chat_opened(cid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.chat_opened(con, v, cid)

    @app.post("/api/admin/feature")
    def feature(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.feature(con, v, body.get("postId"), body.get("days"))

    @app.post("/api/admin/grants")
    def grant(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.grant(con, v, body.get("userId"), body.get("code"))

    @app.get("/api/admin/staff")
    def staff(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.staff(con, v)

    @app.get("/api/admin/staff/find")
    def staff_find(username: str = "", con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.find_anyone(con, v, username)

    @app.post("/api/admin/staff")
    def staff_set(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.set_staff(con, v, body.get("userId"), body.get("role"))

    @app.post("/api/admin/ban")
    def ban(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.set_ban(con, v, body.get("userId"), body.get("on"), body.get("reason"))

    @app.get("/api/admin/audit")
    def audit(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.audit(con, v)

    @app.get("/api/admin/stats")
    def admin_stats(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_stats(con, v)

    @app.get("/api/admin/grants")
    def my_grants(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.my_grants(con, v)

    @app.post("/api/admin/grants/scan")
    def grant_scan(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.grant_scan(con, v, body.get("qr"), body.get("code"))

    @app.post("/api/grant-links/{token}")
    def use_grant_link(token: str, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.use_grant_link(con, v, token)

    @app.post("/api/admin/grants/take-back")
    def take_back(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.take_back(con, v, body.get("userId"), body.get("code"))

    @app.delete("/api/admin/grants/{gid}", status_code=204)
    def ungrant(gid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.ungrant(con, v, gid)

    @app.get("/api/admin/stats/{day}")
    def admin_day(day: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_day(con, v, day)

    @app.get("/api/admin/ai")
    def admin_ai(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.admin_ai(con, v)

    @app.post("/api/admin/ai/retry", status_code=204)
    def admin_ai_retry(con=Depends(conn), v: Viewer = Depends(viewer)):
        logic.ai_retry(con, v)

    @app.post("/api/admin/chats")
    async def add_chat(body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        url = logic.chat_input(v, body)  # before going to Telegram
        async with httpx.AsyncClient(timeout=10) as http:
            peek = await media.chat_peek(http, url)
        if peek["image"]:
            try:
                peek["photo"] = (await _img(media.save, peek["image"], photos))["path"]
            except media.BadImage:
                pass
        return logic.add_chat(con, v, body, peek)

    @app.post("/api/admin/chats/{cid}/approve")
    def approve_chat(cid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.approve_chat(con, v, cid)

    @app.delete("/api/admin/chats/{cid}", status_code=204)
    def delete_chat(cid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        if old := logic.delete_chat(con, v, cid):
            for ext in (".webp", ".t.webp", ".jpg"):
                (photos / f"{old}{ext}").unlink(missing_ok=True)

    # ------------------------------------------------------------ the clubs registry for DMP (§4.13)

    @app.get("/api/registry/orgs")
    def registry(back: int = 0, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.registry(con, v, back)

    @app.get("/api/registry/memos")
    def registry_memos(con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.registry_memos(con, v)

    @app.get("/api/registry/orgs/{oid}/members")
    def registry_roster(oid: int, con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.registry_roster(con, v, oid)

    @app.get("/api/registry/search")
    def registry_search(q: str = "", con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.registry_search(con, v, q)

    @app.post("/api/registry/orgs/{oid}/official")
    def set_official(oid: int, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        return logic.set_official(con, v, oid, body.get("on"))

    @app.post("/api/registry/export", status_code=204)
    async def registry_export(con=Depends(conn), v: Viewer = Depends(viewer)):
        people = logic.registry_export(con, v)
        u = logic.one(con, "SELECT tg_id, lang FROM users WHERE id = ?", v.id)
        await send_file(u["tg_id"], *texts.registry_csv(u["lang"], people))

    # ------------------------------------------------------------ share card

    @app.post("/api/share")
    async def share(request: Request, body: dict = Body(...), con=Depends(conn), v: Viewer = Depends(viewer)):
        """A card for shareMessage (Bot API 8.0), built by the server from its own templates, so nothing the client
        sends ends up in a message from our bot: an event (a photo card), my friend invite, a club's invite or one of my
        achievements (a line of text and our bot's button; owner, Oct 4: no bare links in chats)."""
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
            caption, button = texts.share_event(lang, e["title"], e["startsAt"], e["place"])
            # the photo, else the video's poster (a photo of the same name)
            cover = logic.one(con, """SELECT COALESCE(f.path, x.path) AS path FROM events e LEFT JOIN files f ON f.id = e.cover_file_id
                LEFT JOIN videos x ON x.id = e.video_id AND x.status = 'ready' WHERE e.id = ? AND COALESCE(f.path, x.path) IS NOT NULL""", ref)
            # no photo: the event's own poster (its colour and emoji, as in the app), not the app's old picture (owner, Oct 13)
            photo = f"https://{cfg.domain}/media/{cover['path']}.jpg" if cover else \
                f"https://{cfg.domain}/og/poster.jpg?c={(e['color'] or e['tint'] or '#3B6BFF').lstrip('#')}&e={e['emoji'] or 'sparkles_3d'}"
            result = {"type": "photo", "id": f"ev-{ref}-{stamp}", "photo_url": photo, "thumbnail_url": photo, "caption": caption, "parse_mode": "HTML",
                      "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp=ev_{ref}"}]]}}
        elif kind in ("fr", "join", "pres", "rc", "gl"):
            if kind == "gl":  # the admin's one-time award link (logic.grant_link)
                code = body.get("code")
                start, fields = f"gl_{logic.grant_link(con, v, code)}", {"award": texts.ACH_NAMES[lang if lang in texts.ACH_NAMES else "ru"][code]}
            elif kind == "rc":  # a club's open recruitment round (casting.py): anyone may pass it on
                r = logic.one(con, "SELECT r.closes_at, o.name FROM rounds r JOIN orgs o ON o.id = r.org_id WHERE r.org_id = ? AND r.status = 'open' AND r.closes_at > ?",
                              ref, logic.now())
                if not r:
                    raise ApiError("closed")
                start, fields = f"rc_{ref}", {"club": r["name"], "until": texts.when(r["closes_at"], lang)}
            elif kind == "fr":  # my live one-time link (§4.7), the same one the QR on screen holds
                start = f"fr_{logic.friend_link(con, v)['token']}"
                fields = {"name": logic.shown_name(logic.one(con, logic.PERSON + " WHERE u.id = ?", v.id))}
            elif kind == "join":  # a one-time member link (§4.5), Vice+; each card is a fresh link
                start = f"join_{ref}_{logic.invite(con, v, ref)['token']}"
                fields = {"club": logic.one(con, "SELECT name FROM orgs WHERE id = ?", ref)["name"]}
            else:  # a new club's one-time President link (§2), the admin; each card is a fresh link
                start = f"pres_{ref}_{logic.president_link(con, v, ref)['token']}"
                fields = {"club": logic.one(con, "SELECT name FROM orgs WHERE id = ?", ref)["name"]}
            title, text, button = texts.share_invite(kind, lang, **fields)
            result = {"type": "article", "id": f"{kind}-{ref}-{stamp}", "title": title,
                      "input_message_content": {"message_text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
                      "reply_markup": {"inline_keyboard": [[{"text": button, "url": f"https://t.me/{cfg.bot_username}?startapp={start}"}]]}}
        elif kind == "aw":  # an achievement of mine (§4.11): the reader's button opens their own progress toward it
            code = body.get("code")
            a = next((x for x in logic.achievements(con, v.id) if x["code"] == code and x["level"] > 0), None) if v.student else None
            if not a:
                raise ApiError("bad_input")
            title, text, button = texts.share_award(lang, code, a["level"], len(a["levels"]), a["levels"][a["level"] - 1]["rarity"])
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

    # ------------------------------------------------------------ the frontend

    @app.get("/healthz")
    def health():
        return Response("ok", media_type="text/plain")

    @app.get("/exit")
    def exit_link():
        """kbtu.sow.kz/exit: the short "help me get out" link for posters and chats (owner, Oct 15)."""
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
        """kbtu.sow.kz/privacy and /terms (owner, Oct 16): plain pages anyone can open, in ru, kk or en; the app links
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

    def file(path: str) -> Response | None:
        f = (dist / path).resolve()
        if not path or path == "index.html" or not f.is_file() or dist not in f.parents:
            return None
        # Vite puts a content hash into every name under assets/, so those never change; nor do the map's tiles, whose
        # folder names their cut (map/u1/: a new cut gets a new folder)
        immutable = path.startswith(("assets/", "map/"))
        return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"})

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

    # HEAD too: uptime monitors (UptimeRobot) check with HEAD, and a GET-only route answered them 405 (owner, Oct 13)
    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def frontend(path: str, request: Request):
        if path.startswith("api/"):
            raise ApiError("not_found")
        start = request.query_params.get("tgWebAppStartParam")
        if start == "old" and cfg.old_dir:  # t.me/KBTUappBot?startapp=old
            return RedirectResponse(f"/{start}/?" + request.url.query, status_code=302)
        if path == "demo" or path.startswith("demo/"):  # the in-browser demo went (Oct 11): its old links open the app in Telegram
            return RedirectResponse(f"https://t.me/{cfg.bot_username}?startapp", status_code=302)
        if f := file(path):
            return f
        oid = None
        if logic.SLUG.fullmatch(path.strip("/").lower()):
            with pool.conn() as con:  # only past the files (review: every asset took a connection)
                oid = logic.org_by_slug(con, path.strip("/"))
        if oid:  # kbtu.sow.kz/<club>: an Instagram bio's link (A5)
            return RedirectResponse(f"https://t.me/{cfg.bot_username}?startapp=cl_{oid}", status_code=302)
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
<a class="btn main" id="open" hidden href="tg://"></a></main><script>
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
  const tok = await fetch("https://login.microsoftonline.com/__TENANT__/oauth2/v2.0/token", { method: "POST", body: new URLSearchParams({
    client_id: "__CLIENT__", grant_type: "authorization_code", code, redirect_uri: location.origin + "/ms.html", code_verifier: v.verifier,
    scope: "openid profile email User.Read" }) }).then((r) => r.json()).catch(() => ({}));
  if (!tok.access_token) return end(nope(tok.error, tok.error_description), "bad");
  const r = await fetch("/api/ms/finish", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ state, token: tok.access_token }) });
  const j = await r.json().catch(() => ({}));
  // linked already: plain Telegram, so the app window left open greets him there; a startapp link would open a second
  // app over it (owner, Oct 24). Tried at once (a browser may ask or refuse without a tap), the button stays for that
  if (r.ok) { end("ok", "ok"); location.href = "tg://"; return; }
  end({ linked: "linked", other_ms: "otherMs", not_kbtu: "notKbtu" }[j.message] || "fail", "bad");
})().catch(() => end("fail", "bad"));
</script></body></html>"""
