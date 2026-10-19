"""Signing in with the KBTU Microsoft account (PLAN item 44; owner, Oct 19). The app "KBTU App" lives in the owner's own
Entra directory (not KBTU's), as a single-page app with PKCE and no secret. The Mini App asks start() for a link and
opens it outside Telegram; Microsoft sends the student back to /ms.html, which takes this server's PKCE verifier for
the state, trades the code for tokens in the browser (Microsoft redeems a single-page app's code only from a browser)
and hands the access token to finish(). We check it by calling Graph with it (Graph checks the signature, so no crypto
package here), then that it was issued to our app in KBTU's directory. We keep the account's id and email only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx

log = logging.getLogger("kbtu.ms")

CLIENT = "7487a9a6-fe85-4d01-882b-ac48b42f45e4"   # "KBTU App" in the owner's directory
KBTU = "57081b5e-e66a-4993-8eaf-15b0b309293f"     # kbtu.kz's directory: the only one let in
SCOPE = "openid profile email User.Read"
TTL = 15 * 60
# all of the signed-in user's own profile that User.Read lets us read; we keep whatever KBTU filled in (ms_profile)
FIELDS = ("id,displayName,givenName,surname,mail,userPrincipalName,userType,employeeId,employeeType,department,jobTitle,"
          "companyName,officeLocation,city,country,mobilePhone,businessPhones,preferredLanguage,usageLocation,createdDateTime")                                     # a link is good for 15 minutes


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _mac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def state_for(key: bytes, uid: int) -> str:
    body = f"{uid}.{int(time.time()) + TTL}.{secrets.token_urlsafe(6)}"  # the nonce: two links in one second differ
    return f"{body}.{_b64(_mac(key, 'ms-state ' + body))}"


def state_uid(key: bytes, state: str) -> int | None:
    """The user a state was made for, if it is ours and still fresh"""
    try:
        uid, exp, nonce, sig = state.split(".")
        ok = hmac.compare_digest(sig, _b64(_mac(key, f"ms-state {uid}.{exp}.{nonce}"))) and int(exp) > time.time()
        return int(uid) if ok else None
    except (ValueError, TypeError):  # TypeError: compare_digest on a non-ASCII string
        return None


def verifier(key: bytes, state: str) -> str:
    """PKCE's verifier, derived from the state: nothing to store between the link and the way back"""
    return _b64(_mac(key, "ms-pkce " + state))


def link(key: bytes, uid: int, domain: str) -> str:
    state = state_for(key, uid)
    challenge = _b64(hashlib.sha256(verifier(key, state).encode()).digest())
    return f"https://login.microsoftonline.com/{KBTU}/oauth2/v2.0/authorize?" + urlencode({
        "client_id": CLIENT, "response_type": "code", "redirect_uri": f"https://{domain}/ms.html", "scope": SCOPE,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
        "response_mode": "fragment"})  # after "#": the code never reaches this server's logs


def claims(token: str) -> dict:
    """The token's claims, unchecked: read only after Graph has accepted the token"""
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


async def identity(token: str) -> dict | None:
    """Who the token is for, when Graph accepts it, it was issued to our app in KBTU's directory, and it is a KBTU
    member with a @kbtu.kz address (a guest in KBTU's directory carries its own outside address: review, Oct 19)"""
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get("https://graph.microsoft.com/v1.0/me", headers={"authorization": f"Bearer {token}"},
                               params={"$select": FIELDS})
        if r.status_code != 200:
            log.warning("ms: graph %s", r.status_code)
            return None
        c, me = claims(token), r.json()
        # the sign-in name is always the directory's own (s_nurmatov@kbtu.kz); "mail" can be a student's own outside
        # address (owner's test, Oct 20: refused because of it)
        email = (me.get("userPrincipalName") or "").lower()
        why = ("tenant" if c.get("tid") != KBTU else "app" if c.get("appid", c.get("azp")) != CLIENT
               else "guest" if me.get("userType", "Member") != "Member" else "domain" if not email.endswith("@kbtu.kz") else "")
        if why:
            log.warning("ms: refused (%s)", why)  # which check, never who
            return None
        profile = {k: v for k, v in me.items() if not k.startswith("@") and v not in (None, "", [])}
        return {"profile": profile, "oid": me["id"], "email": email, "first": (me.get("givenName") or "").strip(), "last": (me.get("surname") or "").strip(),
                "employeeId": (me.get("employeeId") or "").strip().upper()}
    except Exception as exc:  # a timeout, a malformed token: no sign-in, never a 500
        log.warning("ms: %s", type(exc).__name__)
        return None
