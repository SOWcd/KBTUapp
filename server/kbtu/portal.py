"""Sign in with KBTU (SPEC §4.1; temporary until KBTU IT gives us an official OIDC client).

The portal uninet.kbtu.kz sits behind Keycloak (realm `uninet`, public client `uninet-frontend`), which
allows only authorization_code + PKCE. Keycloak's login form is server-rendered, so the whole flow is a
few HTTP requests: GET the form → POST the credentials → follow the redirect to the callback with
`code` → exchange it for tokens. The password exists only inside `sign_in` and is never logged, and the
Keycloak session ends as soon as the request has read what it needs (`session`): no KBTU access outlives a
request, so nothing of it is ever stored (SPEC §4.1).

Profile field names come from the portal's own frontend bundle (PersonalDataPage: `code`, `firstName`,
`lastName`, `email`, `phone`, `entranceYearValue`). The live answer (key names logged on Oct 5) has the program as
`specialityName` and no school at all, so school stays empty; the course comes from the entrance year. When the program
or the course can't be read, only the response's key names are logged. IIN and GPA are in the response and are never
kept."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace

import httpx

log = logging.getLogger("kbtu.portal")

REALM = "https://key.kbtu.kz/realms/uninet/protocol/openid-connect"
CLIENT_ID = "uninet-frontend"
REDIRECT_URI = "https://uninet.kbtu.kz/callback"
API = "https://uninet.kbtu.kz/api"
TIMEOUT = httpx.Timeout(20, connect=8)


class PortalError(Exception):
    """The portal or Keycloak didn't answer as expected."""


class BadCredentials(PortalError):
    """Keycloak showed the login form again: wrong login or password."""


class TwoFactor(PortalError):
    """The account asks for a one-time code; this flow can't do it (SPEC §4.1)."""


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str


@dataclass(frozen=True)
class Profile:
    student_id: str
    first_name: str
    last_name: str
    middle_name: str | None
    email: str | None
    phone: str | None
    course: int | None
    school: str | None
    program: str | None


@dataclass(frozen=True)
class Lesson:
    weekday: int        # 1 = Monday … 7 = Sunday
    begins: str         # 'HH:MM' Almaty
    ends: str
    subject: str
    code: str | None
    kind: str | None
    room: str | None
    teacher: str | None
    names: dict | None = None  # the subject in ru / kk / en (the app shows the one in its language)


def _client() -> httpx.AsyncClient:
    # a fresh client per sign-in: Keycloak cookies from a previous session would skip the form
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "KBTU-App/1.0 (+https://t.me/KBTUappBot)"})


def _tokens(body: dict) -> Tokens:
    access, refresh = body.get("access_token"), body.get("refresh_token")
    if not access or not refresh:
        raise PortalError("token response without tokens")
    return Tokens(access, refresh)


async def sign_in(login: str, password: str) -> Tokens:
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    async with _client() as http:
        try:
            page = await http.get(f"{REALM}/auth", params={
                "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "openid profile",
                "state": base64.urlsafe_b64encode(os.urandom(12)).rstrip(b"=").decode(),
                "code_challenge": challenge, "code_challenge_method": "S256"})
            form = re.search(r'id="kc-form-login"[^>]*\baction="([^"]+)"', page.text)
            if page.status_code != 200 or not form:
                raise PortalError(f"login form: HTTP {page.status_code}")
            sent = await http.post(form.group(1).replace("&amp;", "&"), follow_redirects=False,
                                   data={"username": login, "password": password, "credentialId": ""})
            where = sent.headers.get("location", "")
            if sent.status_code not in (302, 303) or "code=" not in where:
                if re.search(r'name="otp"|id="kc-otp-login-form"', sent.text):
                    raise TwoFactor()
                raise BadCredentials()
            code = urllib.parse.parse_qs(urllib.parse.urlparse(where).query)["code"][0]
            got = await http.post(f"{REALM}/token", data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID, "code_verifier": verifier})
        except httpx.HTTPError as exc:
            raise PortalError(f"network: {type(exc).__name__}") from exc
    if got.status_code != 200:
        raise PortalError(f"token exchange: HTTP {got.status_code}")
    return _tokens(got.json())


_up: list = [0.0, True]  # [checked at, answered]


async def reachable() -> bool:
    """Does Keycloak show us its login form right now? Asked at most once a minute. A refusal (Oct 16: KBTU's nginx
    answers 403 to our requests) counts as down, like a timeout."""
    if time.monotonic() - _up[0] > 60:
        async with _client() as http:
            try:
                page = await http.get(f"{REALM}/auth", params={"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code",
                                                                "scope": "openid", "code_challenge": "x" * 43, "code_challenge_method": "S256"})
                ok = page.status_code == 200 and 'id="kc-form-login"' in page.text
            except httpx.HTTPError:
                ok = False
        _up[:] = [time.monotonic(), ok]
    return _up[1]


async def sign_out(refresh_token: str) -> bool:
    """Ends the Keycloak session, and with it every token it gave out. False only when Keycloak can't be reached; a
    session that is already over (400) counts as ended."""
    async with _client() as http:
        try:
            got = await http.post(f"{REALM}/logout", data={"client_id": CLIENT_ID, "refresh_token": refresh_token})
        except httpx.HTTPError:
            return False
    if got.status_code not in (200, 204, 400):
        log.warning("KBTU sign-out: HTTP %s", got.status_code)
        return False
    return True


@asynccontextmanager
async def session(login: str, password: str) -> AsyncIterator[str]:
    """An access token for the block; the session is ended when the block exits, however it exits."""
    tokens = await sign_in(login, password)
    try:
        yield tokens.access
    finally:
        if not await sign_out(tokens.refresh):
            log.warning("KBTU sign-out failed: the session ends by itself at Keycloak's timeout")


async def _get(access: str, path: str, lang: str) -> object:
    async with _client() as http:
        try:
            r = await http.get(f"{API}{path}", headers={"Authorization": f"Bearer {access}", "Accept": "application/json", "Accept-Language": lang})
        except httpx.HTTPError as exc:
            raise PortalError(f"network: {type(exc).__name__}") from exc
    if r.status_code == 401:
        raise BadCredentials()
    if r.status_code != 200:
        raise PortalError(f"{path}: HTTP {r.status_code}")
    return r.json()


def _text(v: object, lang: str = "ru") -> str | None:
    """Portal strings come plain or localized ({ru, kk, en})."""
    if isinstance(v, dict):
        v = v.get(lang) or v.get("ru") or v.get("en") or next((x for x in v.values() if isinstance(x, str) and x), None)
    return " ".join(v.split()) if isinstance(v, str) and v.strip() else None


def _claims(access: str) -> dict:
    try:
        body = access.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError):
        return {}


def _course(raw: dict, now: float | None = None) -> int | None:
    for key in ("yearOfStudy", "course", "courseNumber"):
        try:
            if raw.get(key) is not None:
                return int(raw[key])
        except (TypeError, ValueError):
            pass
    try:  # from the entrance year: the academic year starts in September
        entered = int(str(raw.get("entranceYearValue") or raw.get("entranceYear"))[:4])
    except ValueError:
        return None
    t = time.gmtime(now or time.time())
    return max(1, t.tm_year - entered + (1 if t.tm_mon >= 9 else 0))


async def profile(access: str, lang: str = "ru") -> Profile:
    raw = await _get(access, "/student/basic/me", lang)
    if not isinstance(raw, dict) or not str(raw.get("code") or "").strip():
        raise PortalError("no student profile")
    claims = _claims(access)
    school = next((_text(raw.get(k), lang) for k in ("faculty", "facultyName", "school", "schoolName") if raw.get(k)), None)
    program = next((_text(raw.get(k), lang) for k in ("program", "programName", "educationalProgram", "specialityName") if raw.get(k)), None)
    course = _course(raw)
    if program is None or course is None:
        log.warning("portal profile: course/school/program not found among keys %s", sorted(raw))  # key names only
    return Profile(
        student_id=str(raw["code"]).strip(),
        first_name=_text(raw.get("firstName")) or claims.get("given_name") or "",
        last_name=_text(raw.get("lastName")) or claims.get("family_name") or "",
        middle_name=_text(raw.get("patronymic") or raw.get("middleName")),
        email=_text(raw.get("email")), phone=_text(raw.get("phone")),
        course=course, school=school, program=program,
    )


async def schedule(access: str, lang: str = "ru") -> list[Lesson] | None:
    """The weekly classes, or None when the portal hides or has no schedule (then the old one stays). The subjects come
    in all three languages (owner, Oct 11: the app switched to English, the classes stayed Russian): from one answer when
    the portal gives {ru, kk, en}, else from two more asks in the other languages (a sign-in is once a semester)."""
    raw = await _get(access, "/schedule/student/student/me", lang)
    out = _lessons(raw, lang)
    if not out:
        return None
    if all(x.names and len(x.names) == 3 for x in out):
        return out
    names = {_key(x): {lang: x.subject} for x in out}
    others = [x for x in ("ru", "kk", "en") if x != lang]
    for other, got in zip(others, await asyncio.gather(*(_get(access, "/schedule/student/student/me", x) for x in others), return_exceptions=True)):
        for x in _lessons(got, other) if not isinstance(got, BaseException) else []:
            if _key(x) in names:
                names[_key(x)][other] = x.subject
    return [replace(x, names=names[_key(x)]) for x in out]


def _key(x: "Lesson") -> tuple:
    return (x.weekday, x.begins, x.ends, x.code, x.room)


def _lessons(raw: object, lang: str) -> list["Lesson"]:
    if not isinstance(raw, dict) or raw.get("scheduleHidden") or not raw.get("schedules"):
        return []
    out = []
    for s in raw["schedules"]:
        try:
            name = s.get("semesterSubjectName")
            out.append(Lesson(weekday=int(s["weekId"]), begins=str(s["beginTime"])[:5], ends=str(s["endTime"])[:5],
                              subject=_text(name, lang) or str(s.get("subjectCode") or "?"),
                              code=_text(s.get("subjectCode")), kind=_text(s.get("lessonType"), lang),
                              room=_text(s.get("room"), lang), teacher=_text(s.get("teacher"), lang),
                              names={k: _text(name, k) for k in ("ru", "kk", "en") if _text(name.get(k))} if isinstance(name, dict) else None))
        except (KeyError, TypeError, ValueError):
            continue
    # Sunday classes at KBTU are online self-study (UniX): nobody has to be anywhere, so the app never shows
    # them (owner, Oct 4)
    return [x for x in out if 1 <= x.weekday <= 6]
