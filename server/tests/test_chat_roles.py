"""Studio → Chats → Roles and admins (logic/chatroles.py): both lists, the admins without the app as a count, never a
Telegram id, who may open it, the bot's missing rights, the cap and the cache."""
from __future__ import annotations

import httpx

from kbtu import bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class _Tg:
    """httpx.AsyncClient: the group's admins and members as set here; every call counted."""
    admins: list = []
    members: set = set()
    me = "administrator"
    calls: list = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, **_):
        method = url.rsplit("/", 1)[1]
        _Tg.calls.append(method)
        if _Tg.me == "busy":
            return _Resp({"ok": False, "parameters": {"retry_after": 0}}, 429)
        if method == "getChatAdministrators":
            return _Resp({"ok": True, "result": _Tg.admins})
        uid = json["user_id"]
        if uid == BOT_ID:
            return _Resp({"ok": True, "result": {"status": _Tg.me, "user": {"id": uid}}})
        if any(a["user"]["id"] == uid for a in _Tg.admins):
            return _Resp({"ok": True, "result": {"status": "administrator", "user": {"id": uid}}})
        if uid in _Tg.members:
            return _Resp({"ok": True, "result": {"status": "member", "user": {"id": uid}}})
        return _Resp({"ok": True, "result": {"status": "left", "user": {"id": uid}}})


BOT_ID = 0


def _admin(tg, **kw):
    return {"status": "administrator", "user": {"id": tg, "is_bot": False, **kw.pop("user", {})}, **kw}


def _setup(c, cfg, monkeypatch):
    global BOT_ID
    BOT_ID = int(cfg.bot_token.split(":")[0])
    monkeypatch.setattr(bot._call, "__defaults__", (0,))
    monkeypatch.setattr(logic.chatroles, "_seen", {})
    monkeypatch.setattr(httpx, "AsyncClient", _Tg)
    for tg in (20, 21, 22, 31, 32, 33, 41):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, uid(21), oid, "president", "test")
    logic.set_role(con, None, uid(22), oid, "vice", "test")
    logic.set_role(con, None, uid(20), oid, "head", "test")
    logic.set_role(con, None, uid(31), oid, "member", "test")
    logic.set_role(con, None, uid(32), oid, "member", "test")
    rid = con.execute("INSERT INTO org_roles (org_id, name, color, level, created_at) VALUES (?, 'Designer', '#000000', 'member', 0)", (oid,)).lastrowid
    con.execute("UPDATE org_members SET role_id = ? WHERE org_id = ? AND user_id = ?", (rid, oid, uid(32)))
    other = logic.create_org(con, None, "Go", "GO", "crown_3d", False)
    logic.set_role(con, None, uid(41), other, "president", "test")
    cid = con.execute("""INSERT INTO chats (title, kind, url, tg_chat_id, created_at, status, org_id)
        VALUES ('Chess', 'group', 'https://t.me/+c', -100, 0, 'org', ?)""", (oid,)).lastrowid
    # admins: the President (matches), a plain member, an app user outside the club, two without the app, a bot and an anonymous one
    _Tg.admins = [_admin(21, status="creator"), _admin(31), _admin(33), _admin(7770001), _admin(7770002),
                  _admin(5550001, user={"is_bot": True}), _admin(6660001, is_anonymous=True), _admin(BOT_ID, user={"is_bot": True})]
    _Tg.members, _Tg.me, _Tg.calls = {22, 32, 31, 33}, "administrator", []
    return con, oid, other, cid, uid


def test_both_lists(env, monkeypatch):
    c, cfg = env
    con, oid, other, cid, uid = _setup(c, cfg, monkeypatch)
    get = lambda tg, o=oid, ch=cid: c.get(f"/api/orgs/{o}/chats/{ch}/roles", headers=tma(tg))  # noqa: E731
    assert get(31).status_code == 403 and get(20).status_code == 403                # a member, a Head
    assert get(41).status_code == 403 and get(41, other).status_code == 404         # another club's President, by either club
    assert not _Tg.calls                                                            # refused before Telegram
    r = get(21)
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["state"] == "ok" and x["others"] == 2 and x["capped"] is False
    assert [(a["id"], a["name"] is not None) for a in sorted(x["admins"], key=lambda a: a["id"] or 0)] == [(None, True), (uid(31), True)]
    assert [(p["id"], p["inGroup"]) for p in x["leaders"]] == [(uid(22), True), (uid(20), False), (uid(32), True)]
    assert set(x) == {"state", "admins", "others", "leaders", "capped"} and all(set(a) == {"id", "name"} for a in x["admins"])
    for tg in ("7770001", "7770002", "5550001", "6660001", "-100", str(BOT_ID)):
        assert tg not in r.text                                                     # never a Telegram id
    assert _Tg.calls.count("getChatMember") == 4                                    # the bot, then the three non-admins with a role
    assert get(22).json() == x and len(_Tg.calls) == 5                              # the Vice too; the cache, no new call
    logic.set_role(con, None, uid(31), oid, "head", "test")                        # a new role: asked again
    y = get(21).json()
    assert len(_Tg.calls) > 5 and [a["id"] for a in y["admins"]] == [None] and uid(31) not in [p["id"] for p in y["leaders"]]


def test_cap_and_states(env, monkeypatch):
    c, cfg = env
    con, oid, other, cid, uid = _setup(c, cfg, monkeypatch)
    get = lambda: c.get(f"/api/orgs/{oid}/chats/{cid}/roles", headers=tma(21)).json()  # noqa: E731
    monkeypatch.setattr(logic.chatroles, "ASK_CAP", 1)
    x = get()
    assert x["capped"] is True and [p["id"] for p in x["leaders"]] == [uid(22)] and _Tg.calls.count("getChatMember") == 2
    monkeypatch.setattr(logic.chatroles, "FRESH", 0)                                # nothing kept
    logic.chatroles._seen.clear()
    _Tg.calls = []
    get()
    assert _Tg.calls
    for me, state in (("member", "notAdmin"), ("left", "gone"), ("kicked", "gone"), ("busy", "unavailable")):
        _Tg.me = me
        assert get() == {"state": state}, me
    _Tg.me = "administrator"
    _Tg.admins = []
    assert get()["admins"] == [] and get()["others"] == 0                          # nothing to match: still the second list
    con.execute("DELETE FROM org_members WHERE org_id = ? AND (role != 'member' OR role_id IS NOT NULL) AND user_id != ?", (oid, uid(21)))
    _Tg.admins = [_admin(21, status="creator")]
    assert get() == {"state": "ok", "admins": [], "others": 0, "leaders": [], "capped": False}  # everything matches
