"""The app's own channel and group (logic/appchats.py): joins and leaves heard from the bot become /api/me's two flags,
a stranger is never kept, the daily look is claimed once, Telegram's answers, and deletion."""
from __future__ import annotations

import asyncio

from kbtu import db
from kbtu.logic import appchats
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)

A, STRANGER = 1, 77


def _upd(name: str, tg: int, status: str) -> dict:
    return {"chat": {"id": -100123, "username": name}, "new_chat_member": {"user": {"id": tg}, "status": status}}


def test_joins_and_leaves_drive_the_flags(env):
    c, cfg = env
    uid = login(c, A, "ali")["id"]
    con = db.connect(cfg.db_path)
    me = lambda: c.get("/api/me", headers=tma(A)).json()  # noqa: E731
    assert (me()["inChannel"], me()["inGroup"]) == (False, False)
    assert appchats.heard(con, _upd("kbtuappnews", A, "member"))  # Telegram's name in any case
    assert appchats.heard(con, _upd("KBTUappTop", A, "administrator"))
    assert (me()["inChannel"], me()["inGroup"]) == (True, True)
    assert appchats.heard(con, _upd("KBTUappNews", A, "left"))  # left: the row is back
    assert (me()["inChannel"], me()["inGroup"]) == (False, True)
    assert appchats.heard(con, _upd("KBTUappTop", A, "restricted")) and not me()["inGroup"]  # restricted, not a member
    # another chat is not ours; a stranger in ours is not kept
    assert not appchats.heard(con, _upd("SomeClub", A, "member"))
    assert appchats.heard(con, _upd("KBTUappNews", STRANGER, "member"))
    assert con.execute("SELECT COUNT(*) FROM app_chats").fetchone()[0] == 1
    delete_now(c, cfg, tma(A))
    assert con.execute("SELECT COUNT(*) FROM app_chats WHERE user_id = ?", (uid,)).fetchone()[0] == 0


def test_the_daily_look(env):
    c, cfg = env
    uid = login(c, A, "ali")["id"]
    con = db.connect(cfg.db_path)
    with db.tx(con):
        assert appchats.due(con, uid, 1000) == A
    with db.tx(con):
        assert appchats.due(con, uid, 1000 + appchats.DAY - 1) is None  # claimed: once a day
        assert appchats.due(con, uid, 1000 + appchats.DAY) == A
    answers = {"@KBTUappNews": {"ok": True, "result": {"status": "member"}},
               "@KBTUappTop": {"ok": False, "error_code": 400, "description": "Bad Request: user not found"}}

    async def call(method, params):
        assert method == "getChatMember" and params["user_id"] == A
        return answers[params["chat_id"]]
    got = asyncio.run(appchats.look(call, A))
    assert got == {"channel": True, "group": False}
    appchats.save(con, uid, got)
    assert appchats.mine(con, uid) == {"inChannel": True, "inGroup": False}
    # the network or the bot's rights: that chat is left as it was
    answers["@KBTUappNews"] = None
    answers["@KBTUappTop"] = {"ok": False, "error_code": 400, "description": "Bad Request: member list is inaccessible"}
    assert asyncio.run(appchats.look(call, A)) == {}
