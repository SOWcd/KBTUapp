"""Nov 6: club socials without Telegram, "Message the club" to the President, no emoji in org names."""
from __future__ import annotations

from kbtu import bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_team_link import _club


def test_no_telegram_socials(env):
    """t.me, telegram.me, tg:// refused on edit and application; old stored ones stay stored, unseen."""
    c, cfg = env
    pres = login(c, 20, "pres")
    con = _club(cfg, pres["id"])
    P = tma(20, "Pres")
    for bad in ("https://t.me/itclub", "https://telegram.me/x", "https://www.T.me/x", "tg://resolve?domain=x"):
        assert c.patch("/api/orgs/1", headers=P, json={"links": [bad]}).status_code == 400, bad
    assert c.patch("/api/orgs/1", headers=P, json={"links": ["https://instagram.com/it"]}).status_code == 200
    con.execute("""UPDATE orgs SET links = '["https://t.me/old", "https://instagram.com/it"]' WHERE id = 1""")
    assert c.get("/api/orgs/1", headers=P).json()["links"] == ["https://instagram.com/it"]
    assert all("t.me" not in x for o in c.get("/api/orgs", headers=P).json() if o["id"] == 1 for x in o["links"])
    login(c, 30, "ali")
    body = {"name": "Go Players", "short": "GP", "description": "We play go every week.", "emoji": "trophy_3d", "cover": 1}
    assert c.post("/api/club-applications", headers=tma(30), json={**body, "links": ["https://t.me/go"]}).status_code == 400


def test_contact_by_rank(env):
    """The President's @username, else a Vice's, else a Head's; none: null; a guest (no KBTU sign-in) gets none."""
    c, cfg = env
    pres, vice, head = login(c, 20, "pres"), login(c, 21, "vice"), login(c, 22, "head")
    login(c, 30, "ali")
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice", f"u{head['id']}": "head"})
    name = lambda uid, u: con.execute("UPDATE users SET tg_username = ? WHERE id = ?", (u, uid))  # noqa: E731
    contact = lambda h=tma(30): c.get("/api/orgs/1", headers=h).json()["contact"]  # noqa: E731
    for uid in (pres, vice, head):
        name(uid["id"], None)
    assert contact() is None
    name(head["id"], "head_u")
    assert contact() == "head_u"
    name(vice["id"], "vice_u")
    assert contact() == "vice_u"
    name(pres["id"], "pres_u")
    assert contact() == "pres_u"
    assert c.get("/api/orgs/1", headers=tma(99, "Guest")).json()["contact"] is None


def test_no_emoji_in_names(env):
    """Refused at rename, application and the admin's create, with "emoji" for the app's text."""
    c, cfg = env
    pres = login(c, 20, "pres")
    con = _club(cfg, pres["id"])
    r = c.patch("/api/orgs/1", headers=tma(20, "Pres"), json={"name": "IT \U0001f525"})
    assert r.status_code == 400 and "emoji" in r.text
    login(c, 30, "ali")
    body = {"name": "Chess larpers\U0001f976", "short": "CL", "description": "We play chess all day.", "emoji": "trophy_3d", "cover": 1}
    assert "emoji" in c.post("/api/club-applications", headers=tma(30), json=body).text
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (pres["id"],))
    r = c.post("/api/admin/orgs", headers=tma(20, "Pres"), json={"name": "Art \u2728", "short": "AR", "emoji": "trophy_3d"})
    assert r.status_code == 400 and "emoji" in r.text
    assert c.post("/api/admin/orgs", headers=tma(20, "Pres"), json={"name": "Caf\u00e9 \u00d8rsted", "short": "CO", "emoji": "trophy_3d"}).status_code == 200


def test_strip_emoji_names_once(env):
    """Old names lose their emoji once (letters like \u00f3 stay), slug kept, audited, the President told in a template."""
    c, cfg = env
    pres = login(c, 20, "pres")
    con = _club(cfg, pres["id"])
    con.execute("UPDATE orgs SET name = ?, i18n = ? WHERE id = 1", ("\u0442\u0438\u043a\u0442\u043e\u043a \u0445\u0430\u0443\u0441 kbTTu\U0001f919\U0001f3ff\U0001f919\U0001f3ff",
                                                                    '{"en": {"name": "tiktok house kbTTu\U0001f919"}}'))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'sol', 'club', 'Sol\u00f3 \u00d8', 'SO', 'trophy_3d', 0)")
    logic.strip_emoji_names(con)
    o = con.execute("SELECT name, slug, i18n FROM orgs WHERE id = 1").fetchone()
    assert (o["name"], o["slug"]) == ("\u0442\u0438\u043a\u0442\u043e\u043a \u0445\u0430\u0443\u0441 kbTTu", "it") and "\\ud83e" not in o["i18n"] and "\U0001f919" not in o["i18n"]
    assert con.execute("SELECT name FROM orgs WHERE id = 2").fetchone()[0] == "Sol\u00f3 \u00d8"
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'org_edit' AND target = 'org:1'").fetchone()[0] == 1
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'club_emoji'").fetchone()
    assert m["user_id"] == pres["id"] and m["ref"] == "emo:1"
    for lang in ("ru", "kk", "en"):
        text, button, start = bot._render(con, {**dict(m), "lang": lang})
        assert "kbTTu" in text and button and start == "cl_1"
    con.execute("UPDATE orgs SET name = 'X \U0001f976' WHERE id = 2")
    logic.strip_emoji_names(con)  # once: the meta key
    assert con.execute("SELECT name FROM orgs WHERE id = 2").fetchone()[0] == "X \U0001f976"
