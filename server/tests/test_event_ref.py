""""My link" to an event carries a code of its own: it credits the sign-up, and is no friend invite."""
from __future__ import annotations

import json
import re
import time

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_event_link_is_no_friend_invite(env, monkeypatch):
    import httpx
    from kbtu import app as server
    real, sent = httpx.AsyncClient, []

    def answer(r):
        sent.append(r.content.decode())
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer)))
    c, cfg = env
    pres, zhan = login(c, 90, "pres"), login(c, 92, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    assert c.post("/api/share", headers=tma(90), json={"kind": "ev", "id": 1, "mine": True}).status_code == 200
    code = re.search(r"startapp=ev_1_([A-Z2-7]{10})", json.dumps(json.loads(sent[-1]))).group(1)
    assert code != logic._qr_code(con, pres["id"], "link_code")
    assert c.get(f"/api/invite/{code}", headers=tma(92)).status_code == 404       # no friend card by it
    assert c.post(f"/api/invite/{code}", headers=tma(92)).status_code == 404      # and no friendship
    c.post("/api/events/1/registration", headers=tma(92), json={"ref": code})
    assert con.execute("SELECT invited_by FROM registrations WHERE user_id = ?", (zhan["id"],)).fetchone()[0] == pres["id"]
    # the plain t.me share (no cards in this Telegram) builds the same link from /api/me: never the badge's code
    me = c.get("/api/me", headers=tma(90)).json()
    assert me["evRef"] == code and code not in me["qr"]
