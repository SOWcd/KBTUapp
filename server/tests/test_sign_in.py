"""Signing in: by hand and with Microsoft."""
from __future__ import annotations

import hashlib
import json
import re

from fastapi.testclient import TestClient

from kbtu import bot, config, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_manual_sign_in(env, monkeypatch):
    """Microsoft only: the ID and year are typed only after a Microsoft sign-in; a row typed in before
    acts as nobody until Microsoft confirms it; an ID held by such a row goes to the Microsoft one, held by a confirmed
    one it's refused, the holder asked to check theirs and the other told once it's free (no admin). The admin adds someone with no Microsoft by hand."""
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    login(c, 20, "ali")  # confirmed: "24Bali"
    body = {"firstName": "\u041c\u0430\u0433\u0430", "lastName": "\u0422\u0435\u043c\u0438\u0440", "studentId": "24b031234", "course": 2, "consentVersion": logic.CONSENT}
    manual = lambda uid, b=body: c.post("/api/kbtu/manual", headers=tma(uid), json=b)  # noqa: E731
    for bad in ({"firstName": "M4ga"}, {"studentId": "hello"}, {"studentId": "99B031234"}, {"consentVersion": ""}, {"consentVersion": "v1"}):  # the year: from the ID (M3), never ahead
        assert manual(21, {**body, **bad}).status_code == 400
    assert manual(21).json()["message"] == "ms_first"                                     # no Microsoft, no account
    assert manual(20).json()["message"] == "ms_first"                                     # confirmed already: nothing to type either
    ids = {tg: c.get("/api/me", headers=tma(tg)).json()["id"] for tg in (21, 22, 23, 24, 25)}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', tg_username = 'squat' WHERE id = ?", (ids[25],))
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B031234', 'Squat', 'Ter', 2, '1', 0, 0, 0, 1)""", (ids[23],))  # typed in before Oct 20
    me = c.get("/api/me", headers=tma(23)).json()
    assert me["student"] is None and me["relink"] and me["msPending"] is None              # signed out until Microsoft
    assert c.get("/api/friends/joined", headers=tma(23)).json()["error"] == "need_student"
    who = lambda n: {"oid": f"oid-{n}", "email": f"s_{n}@kbtu.kz", "first": "Maga", "last": f"N{n}", "employeeId": "", "profile": {}}  # noqa: E731
    for tg in (21, 22, 24):
        logic.ms_remember(con, ids[tg], who(tg))
    me = manual(21).json()                                                                 # the ID held by a typed-in row: it gives way
    assert me["student"]["studentId"] == "24B031234" and me["student"]["ms"] and me["no"] is not None
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (ids[23],)).fetchone()
    r = manual(22)                                                                         # held by a Microsoft one: refused
    assert r.status_code == 409 and r.json()["message"] == "sid_taken"
    assert c.get("/api/me", headers=tma(22)).json()["msPending"]                           # can type another
    out = {r["kind"]: r for r in con.execute("SELECT * FROM bot_outbox WHERE kind IN ('id_clash', 'sid_check', 'sid_free')")}
    assert set(out) == {"sid_check", "sid_free"}                                         # no admin; the typed-in row gave way quietly
    assert out["sid_check"]["user_id"] == ids[21] and out["sid_free"]["user_id"] == ids[22]
    assert "24B031234" in bot._render(con, {**dict(out["sid_check"]), "lang": "ru"})[0]   # the holder: check yours
    assert bot._render(con, {**dict(out["sid_free"]), "lang": "ru"}) is None              # still held: nothing to tell
    assert out["sid_free"]["send_after"] > logic.now() + 86400                            # parked
    con.execute("UPDATE students SET student_id = '24B031299' WHERE user_id = ?", (ids[21],))  # the holder fixes a typo
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'sid_free'").fetchone()
    assert m["send_after"] == 0 and "24B031234" in bot._render(con, {**dict(m), "lang": "ru"})[0]  # woken: it's free
    assert bot._render(con, {**dict(out["sid_check"]), "lang": "ru"}) is None             # the holder's ask is moot now
    con.execute("UPDATE students SET student_id = '24B031234' WHERE user_id = ?", (ids[21],))  # back, for the rest
    for i in range(5):                                                                     # three IDs per newcomer: no pinging every holder
        logic.id_clash(con, f"24B00000{i}", ids[24], ids[21])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'sid_check' AND ref LIKE 'sc:24B00000%'").fetchone()[0] == 3
    assert manual(22, {**body, "studentId": "24B031235", "firstName": "x1"}).json()["student"]["firstName"] == "Maga"  # Microsoft's names win
    logic.delete_me(con, logic.Viewer(ids[24], "user", True))                            # an unfinished sign-in leaves with the account
    assert not con.execute("SELECT 1 FROM meta WHERE key = ?", (f"ms:{ids[24]}",)).fetchone()
    con.execute("INSERT INTO meta (key, value) VALUES ('ms:999', ?), ('ms_used:abc', '1')", (json.dumps({"at": 1}),))
    logic.ms_sweep(con)
    assert not con.execute("SELECT 1 FROM meta WHERE key IN ('ms:999', 'ms_used:abc')").fetchone()
    from kbtu import admin                                                                # no Microsoft account: by hand
    admin.main(["student", "23", "24B031299", "Squat", "Ter", "3"])
    me = c.get("/api/me", headers=tma(23)).json()
    assert me["student"]["studentId"] == "24B031299" and me["no"] is not None and not me["relink"]
    for gone in ("/api/kbtu/login", "/api/kbtu/status"):                                  # the password sign-in is gone
        assert c.post(gone, headers=tma(21), json={"login": "a", "password": "b"}).status_code in (404, 405)


def test_ms_sign_in(env, monkeypatch):
    """The KBTU Microsoft sign-in (PLAN item 44): a link whose state only this server signs; the verifier for it; a
    token Graph accepts but issued elsewhere is refused; a typed-in student is confirmed; someone new types only the
    ID and year after; one Microsoft account never links to two Telegram users."""
    import base64
    import httpx
    from kbtu import msauth
    c, cfg = env
    login(c, 20, "ali")
    con = db.connect(cfg.db_path)  # typed in before Oct 20 (Microsoft only since): confirmed by Microsoft below
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B099001', 'Bek', 'Typed', 2, 'v2', 0, 0, 0, 1)""", (c.get("/api/me", headers=tma(21)).json()["id"],))
    url = c.post("/api/ms/start", headers=tma(21)).json()["url"]
    assert "/ms/go?state=" in url and msauth.KBTU not in url  # our page first: it keeps the verifier in the browser
    state = re.search(r"state=([^&]+)", url).group(1).replace("%2E", ".").replace("%3D", "=")
    # PKCE (Aldiyar's report): the verifier is random and only in the cookie of the browser that opened the link, so
    # the state (in the address, beside the code) gives nobody else the verifier
    browser, other = (TestClient(c.app, base_url="https://testserver") for _ in range(2))
    assert other.get("/api/ms/verifier", params={"state": state}).status_code == 404
    assert browser.get("/ms/go", params={"state": "1.2.3.x"}, follow_redirects=False).headers["location"] == "/ms.html"
    go = browser.get("/ms/go", params={"state": state}, follow_redirects=False)
    to = go.headers["location"]
    assert go.status_code == 302 and msauth.KBTU in to and "code_challenge=" in to and "state=" in to
    v = browser.get("/api/ms/verifier", params={"state": state}).json()
    challenge = re.search(r"code_challenge=([^&]+)", to).group(1)
    assert challenge == base64.urlsafe_b64encode(hashlib.sha256(v["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert v["name"] == "Test" and len(v["verifier"]) >= 43  # ms.html asks "link to Test?" first
    assert other.get("/api/ms/verifier", params={"state": state}).status_code == 404  # the state alone: still nothing
    assert c.get("/api/ms/verifier", params={"state": "1.2.\u00e9"}).status_code == 404      # not a 500
    assert c.get("/api/ms/verifier", params={"state": state[:-2] + "xx"}).status_code == 404

    def token(tid=msauth.KBTU, app=msauth.CLIENT):
        part = base64.urlsafe_b64encode(json.dumps({"tid": tid, "appid": app}).encode()).decode().rstrip("=")
        return f"h.{part}.s"
    graph = {"id": "oid-1", "givenName": "Bek", "surname": "Real", "mail": "bek@gmail.com", "userPrincipalName": "B_REAL@kbtu.kz"}
    async def get(self, url, **kw):
        return httpx.Response(200, json=graph)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    uid = lambda tg: c.get("/api/me", headers=tma(tg)).json()["id"]  # noqa: E731 (states carry our user id, not Telegram's)
    def finish(tg, tok, st=None):  # the browser's step, then the Mini App's claim from the Telegram that started it
        r = c.post("/api/ms/finish", json={"state": st or msauth.state_for(cfg.token_key, uid(tg)), "token": tok})
        return c.post("/api/ms/claim", headers=tma(tg), json=r.json()) if r.status_code == 200 else r
    assert finish(21, token(tid="other-tenant")).status_code == 403           # someone else's directory
    assert finish(21, token(app="other-app")).status_code == 403              # a token made for another app
    assert finish(21, token(), st="21.1.x.bad").status_code == 403              # a state we never signed
    graph["userPrincipalName"] = "bek@gmail.com"
    assert finish(21, token()).status_code == 403                             # not a kbtu.kz sign-in name
    graph["userPrincipalName"] = "B_REAL@kbtu.kz"                             # "mail" may be a gmail: the sign-in name counts
    st = msauth.state_for(cfg.token_key, uid(21))
    assert finish(21, token(), st=st).json() == {"ok": True}                  # linked at once (no return code)
    assert finish(21, token(), st=st).status_code == 403                      # each link once
    # someone else's sign-in link (a look-alike name on it): the browser's claim opens only its starter's Mini App
    graph["id"] = "oid-7"
    held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(23)), "token": token()}).json()
    assert set(held) == {"claim"}
    assert c.post("/api/ms/claim", headers=tma(24), json=held).status_code == 403   # not the Telegram that asked
    assert c.post("/api/ms/claim", headers=tma(24), json={"claim": "x"}).status_code == 403
    assert c.get("/api/me", headers=tma(24)).json()["msPending"] is None
    # ... and that proved the link was forwarded: the hold is gone, nothing left to release to its sender
    assert c.post("/api/ms/release", json=held).status_code == 403
    assert c.post("/api/ms/claim", headers=tma(23), json=held).status_code == 403
    held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(23)), "token": token()}).json()
    assert c.post("/api/ms/claim", headers=tma(23), json=held).json() == {"ok": True}  # its starter's own app
    assert c.post("/api/ms/claim", headers=tma(23), json=held).status_code == 403      # once
    # the start link opened nothing (Telegram's own browser on Android): nothing is taken without the secret until the
    # browser releases it ("Link to <name>?"), then only its starter's app takes it, once
    graph["id"] = "oid-8"
    held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(25)), "token": token()}).json()
    assert c.post("/api/ms/claim", headers=tma(25), json={"claim": ""}).status_code == 403
    assert c.post("/api/ms/release", json={"claim": "x" * 24}).status_code == 403
    assert c.post("/api/ms/release", json=held).status_code == 204
    assert c.post("/api/ms/claim", headers=tma(24), json={"claim": ""}).status_code == 403   # released for 25 alone
    assert c.get("/api/me", headers=tma(24)).json()["msPending"] is None
    assert c.post("/api/ms/claim", headers=tma(25), json={"claim": ""}).json() == {"ok": True}
    assert c.post("/api/ms/claim", headers=tma(25), json={"claim": ""}).status_code == 403
    assert c.post("/api/ms/release", json=held).status_code == 403                           # taken: nothing to release
    # released, then the start link opens after all: the secret still takes it, once; a released one past its 15 minutes: no
    graph["id"] = "oid-9"
    held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(26)), "token": token()}).json()
    assert c.post("/api/ms/release", json=held).status_code == 204
    assert c.post("/api/ms/claim", headers=tma(26), json=held).json() == {"ok": True}
    assert c.post("/api/ms/claim", headers=tma(26), json={"claim": ""}).status_code == 403
    graph["id"] = "oid-10"
    held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(27)), "token": token()}).json()
    assert c.post("/api/ms/release", json=held).status_code == 204
    con.execute("UPDATE meta SET value = json_set(value, '$.at', json_extract(value, '$.at') - 901) WHERE key = ?", (f"ms_claim:{held['claim']}",))
    assert c.post("/api/ms/claim", headers=tma(27), json={"claim": ""}).status_code == 403
    graph["id"] = "oid-1"
    me = c.get("/api/me", headers=tma(21)).json()
    assert "msCode" not in me
    assert me["student"]["ms"] and me["student"]["email"] == "b_real@kbtu.kz"
    assert me["student"]["lastName"] == "Real"                                # the account's names over typed ones
    graph["id"] = "oid-9"
    assert finish(21, token()).json()["message"] == "other_ms"                # no silent swap to another account
    graph["id"] = "oid-1"
    assert finish(22, token()).json()["message"] == "linked"                  # the same account, another Telegram
    graph = {"id": "oid-2", "givenName": "Dana", "surname": "New", "userPrincipalName": "d_new@kbtu.kz"}
    assert finish(22, token()).json() == {"ok": True}                         # new: remembered for the form
    assert c.get("/api/me", headers=tma(22)).json()["msPending"] == {"first": "Dana", "last": "New", "email": "d_new@kbtu.kz", "prefill": None}
    c.post("/api/kbtu/manual", headers=tma(22), json={"consentVersion": logic.CONSENT, "firstName": "Dana", "lastName": "New", "studentId": "24B099002", "course": 1})
    me = c.get("/api/me", headers=tma(22)).json()
    assert me["student"]["ms"] and me["msPending"] is None and me["no"]
    assert me["student"]["course"] == logic.course_of("24B099002") != 1                 # the ID's year, not the typed 1 (M3)
