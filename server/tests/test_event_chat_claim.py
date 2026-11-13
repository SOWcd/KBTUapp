"""/start ec_<token> in a group: only that group's admin links it, and never a group another club already holds."""
from __future__ import annotations

import asyncio
import time

from kbtu import bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


class _Resp:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class _Http:
    def __init__(self, status):
        self.status, self.calls = status, []

    async def post(self, url, json=None, **_):
        self.calls.append(url.rsplit("/", 1)[1])
        if url.endswith("/getChatMember"):
            return _Resp({"ok": True, "result": {"status": self.status}})
        return _Resp({"ok": True, "result": {"invite_link": "https://t.me/+x"}})


def _club_event(c, con, tg, name):
    oid = logic.create_org(con, None, name, name[:2].upper(), "crown_3d", False)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0], oid, "president", "test")
    ev = {"title": f"{name} day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(tg), json=ev).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(tg))
    token = c.post(f"/api/events/{e['id']}/chat", headers=tma(tg)).json()["url"].split("startgroup=ec_")[1].split("&")[0]
    return oid, e["id"], token


def test_event_chat_claim_guards(env, monkeypatch):
    c, cfg = env
    for uid, name in ((20, "pres"), (30, "rival")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    _, e1, t1 = _club_event(c, con, 20, "Chess")
    _, e2, t2 = _club_event(c, con, 30, "Go")
    assert logic.chat_claim(con, t1, 20, -100)["id"] == e1
    assert logic.chat_claim(con, t2, 30, -100) is None                     # another club's group stays theirs
    assert con.execute("SELECT chat_id FROM events WHERE id = ?", (e1,)).fetchone()[0] == -100
    con.execute("INSERT INTO chats (title, kind, url, tg_chat_id, created_at, status) VALUES ('Open', 'group', 'https://t.me/open', -200, 0, 'live')")
    assert logic.chat_claim(con, t2, 30, -200) is None                     # a chat of the app's list too
    assert logic.chat_claim(con, t2, 30, -300)["id"] == e2                 # a free group: fine

    sent = []

    async def send(_cfg, _http, body):
        sent.append(body)
    monkeypatch.setattr(bot, "_send", send)
    con.execute("UPDATE events SET chat_token = 'tok2' WHERE id = ?", (e2,))
    msg = {"chat": {"id": -400}, "text": "/start ec_tok2", "date": int(time.time()), "from": {"id": 30}}
    asyncio.run(bot._group(cfg, _Http("member"), con, msg))                 # an organizer, but not the group's admin
    assert con.execute("SELECT chat_id FROM events WHERE id = ?", (e2,)).fetchone()[0] == -300 and sent[-1]["text"] == bot.texts.CHAT_BAD
    asyncio.run(bot._group(cfg, _Http("administrator"), con, msg))
    assert con.execute("SELECT chat_id FROM events WHERE id = ?", (e2,)).fetchone()[0] == -400
