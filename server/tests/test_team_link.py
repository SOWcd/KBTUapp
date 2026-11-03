"""A club's member link for the whole team (logic.team_link): who belongs
to what, so each test tries to abuse them."""
from __future__ import annotations

import base64
import json

import httpx

from kbtu import app as server, db, logic, msauth
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def _club(cfg, pres: int, **people: str):
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres,))
    for uid, role in people.items():
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", (int(uid[1:]), role))
    return con


def test_team_link(env, monkeypatch):
    """Many join by one link, as plain Members only; Vice+ make it; one per club (shared again, not replaced); 7 days;
    turned off early it's closed at once; guests, the banned and other clubs' tokens get nothing; every join audited."""
    c, cfg = env
    pres, vice, mem = login(c, 20, "pres"), login(c, 21, "vice"), login(c, 22, "mem")
    a, b, d, x = (login(c, 30 + i, n) for i, n in enumerate(("aaa", "bbb", "ddd", "xxx")))
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice", f"u{mem['id']}": "member"})
    P, V, M = tma(20, "Pres"), tma(21, "Vice"), tma(22, "Mem")
    assert c.post("/api/orgs/1/team-link", headers=M).status_code == 403                 # a plain member can't
    assert c.post("/api/orgs/1/team-link", headers=tma(30)).status_code == 403           # nor an outsider
    assert c.delete("/api/orgs/1/team-link", headers=M).status_code == 403               # nor turn it off
    link = c.post("/api/orgs/1/team-link", headers=V).json()
    assert link["expiresAt"] - logic.now() == logic.TEAM_LINK_TTL
    assert c.post("/api/orgs/1/team-link", headers=P).json() == link                     # one per club: the live one again
    assert c.get("/api/orgs/1/team", headers=P).json()["teamLink"] == {"expiresAt": link["expiresAt"]}
    assert "teamLink" not in c.get("/api/orgs/1/team", headers=M).json()            # members don't see it
    tok = link["token"]
    assert c.post(f"/api/invites/{tok}", headers=tma(99, "Guest")).status_code == 401   # signed-in KBTU students only
    for h in (tma(30), tma(31), tma(32)):                                              # many, not the first one only
        assert c.post(f"/api/invites/{tok}", headers=h).json()["id"] == 1
    assert c.post(f"/api/invites/{tok}", headers=tma(30)).status_code == 200            # opened twice: fine, nothing more
    roles = dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())
    assert [roles[p["id"]] for p in (a, b, d)] == ["member"] * 3 and roles[vice["id"]] == "vice"
    assert con.execute("SELECT used_by FROM org_invites WHERE token = ?", (tok,)).fetchone()[0] is None
    log = con.execute("SELECT actor_id, data FROM audit_log WHERE action = 'team_link_join' ORDER BY id").fetchall()
    assert [r[0] for r in log] == [a["id"], b["id"], d["id"]] and all(json.loads(r[1])["by"] == vice["id"] for r in log)
    assert [tuple(r) for r in con.execute("SELECT actor_id FROM audit_log WHERE action = 'team_link'")] == [(vice["id"],)]
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 0              # nobody pinged
    # a member's role isn't given by a link, even if a row were tampered to say so
    con.execute("UPDATE org_invites SET role = 'president' WHERE token = ?", (tok,))
    assert c.post(f"/api/invites/{tok}", headers=tma(33)).status_code == 404
    con.execute("UPDATE org_invites SET role = 'member' WHERE token = ?", (tok,))
    # a ban outranks the link
    con.execute("INSERT OR IGNORE INTO org_bans (org_id, user_id, created_at) VALUES (1, ?, 0)", (d["id"],))
    con.execute("DELETE FROM org_members WHERE org_id = 1 AND user_id = ?", (d["id"],))
    assert c.post(f"/api/invites/{tok}", headers=tma(32)).status_code == 403
    # turned off: closed now, those in stay; the next one is a new token
    assert c.delete("/api/orgs/1/team-link", headers=P).status_code == 204
    assert c.post(f"/api/invites/{tok}", headers=tma(33)).status_code == 404
    assert c.get("/api/orgs/1/team", headers=P).json()["teamLink"] is None
    assert con.execute("SELECT COUNT(*) FROM org_members WHERE org_id = 1 AND user_id = ?", (a["id"],)).fetchone()[0] == 1
    fresh = c.post("/api/orgs/1/team-link", headers=P).json()["token"]
    assert fresh != tok
    assert con.execute("SELECT COUNT(*) FROM org_invites WHERE multi = 1 AND revoked_at IS NULL").fetchone()[0] == 1
    # 7 days
    later = logic.now() + logic.TEAM_LINK_TTL + 1
    set_clock(monkeypatch, lambda: later)
    assert c.post(f"/api/invites/{fresh}", headers=tma(33)).status_code == 404
    assert c.post("/api/orgs/1/team-link", headers=P).json()["token"] != fresh           # an old one isn't "live"
    assert x["id"] not in dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())


def test_team_link_card(env, monkeypatch):
    """The card says it's for the whole team and until when; its button carries the club's one live link."""
    c, cfg = env
    pres, mem = login(c, 20, "pres"), login(c, 22, "mem")
    _club(cfg, pres["id"], **{f"u{mem['id']}": "member"})
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))
    tok = c.post("/api/orgs/1/team-link", headers=tma(20)).json()["token"]
    assert c.post("/api/share", headers=tma(20), json={"kind": "join", "id": 1, "many": True}).status_code == 200
    card = sent[-1]["result"]
    assert card["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(f"startapp=join_1_{tok}")
    text = card["input_message_content"]["message_text"]
    assert "IT Club" in text and "\u0434\u043e" in text.lower() and "http" not in text      # "until" its day, no bare link
    assert c.post("/api/share", headers=tma(22), json={"kind": "join", "id": 1, "many": True}).status_code == 403
    assert c.post("/api/share", headers=tma(20), json={"kind": "join", "id": 1}).status_code == 200   # the one-time card stays
    assert sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"].split("_")[-1] != tok


def _ms(c, cfg, monkeypatch):
    """A Microsoft sign-in from Telegram `tg` with the account `oid` (as test_ms_sign_in fakes it)."""
    graph = {}

    async def get(self, url, **kw):
        return httpx.Response(200, json=graph)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    part = base64.urlsafe_b64encode(json.dumps({"tid": msauth.KBTU, "appid": msauth.CLIENT}).encode()).decode().rstrip("=")

    def finish(tg: int, oid: str):
        graph.update({"id": oid, "givenName": "Bek", "surname": "Real", "userPrincipalName": f"{oid}@kbtu.kz"})
        uid = c.get("/api/me", headers=tma(tg)).json()["id"]
        return c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid), "token": f"h.{part}.s"})
    return finish
