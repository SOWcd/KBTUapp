"""/all in a club's group: only its President, Vice and Heads; five mentions a message under the caller's; silence otherwise."""
from __future__ import annotations

import asyncio
import time

from kbtu import bot, db, logic, tgc
from test_core import env, login  # noqa: F401  (env: the fixture)


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class _Http:
    """Telegram: everyone is in the chat but `gone`; the first `busy` sendMessages answer 429."""
    def __init__(self, gone=(), busy=0, admins=()):
        self.gone, self.busy, self.sent, self.admins = set(gone), busy, [], set(admins)

    async def post(self, url, json=None, **_):
        if url.endswith("/getChatMember"):
            return _Resp({"ok": True, "result": {"status": "left" if json["user_id"] in self.gone else "administrator" if json["user_id"] in self.admins else "member", "user": {"id": json["user_id"]}}})
        if self.busy:
            self.busy -= 1
            return _Resp({"ok": False, "parameters": {"retry_after": 0}}, 429)
        self.sent.append(json)
        return _Resp({"ok": True, "result": {}})


def _setup(c, cfg, monkeypatch):
    monkeypatch.setattr(bot, "TAG_GAP", 0)
    monkeypatch.setattr(bot, "ALL_NO_TTL", 0)
    monkeypatch.setattr(bot, "SYNC_GAP", 0)
    monkeypatch.setattr(bot._call, "__defaults__", (0,))
    for tg in (20, 21, 31, 32, 33, 34, 35, 36, 37, 99):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    logic.set_role(con, None, uid(21), oid, "president", "test")
    logic.set_role(con, None, uid(20), oid, "head", "test")
    for tg in range(31, 38):
        logic.set_role(con, None, uid(tg), oid, "member", "test")
    con.execute("INSERT INTO chats (title, kind, url, tg_chat_id, created_at, status, org_id) VALUES ('Chess', 'group', 'https://t.me/+c', -100, 0, 'org', ?)", (oid,))
    return con


def _msg(tg, chat=-100, text="/all", **kw):
    return {"chat": {"id": chat, "type": "supergroup"}, "message_id": 7, "text": text, "date": int(time.time()), "from": {"id": tg}, **kw}


def _run(cfg, con, http, *msgs):
    async def go():
        for m in msgs:
            await bot._group(cfg, http, con, m)
        await asyncio.gather(*list(tgc._tasks))
    asyncio.run(go())
    return http.sent


def test_head_tags_in_fives(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    sent = _run(cfg, con, _Http(gone={37}), _msg(20, text=f"/tag@{cfg.bot_username} meeting at 6"))
    ids = [[int(p.split('">')[0]) for p in s["text"].split("tg://user?id=")[1:]] for s in sent]
    assert ids == [[21, 31, 32, 33, 34], [35, 36]]                                   # the caller and the one who left skipped
    assert all(s["reply_parameters"]["message_id"] == 7 and s["chat_id"] == -100 for s in sent)
    assert "meeting" not in sent[0]["text"] and any(m in sent[0]["text"] for m in bot.TAG_MARKS)   # never the caller's words
    assert not bot._tagging
    assert len(_run(cfg, con, _Http(gone={37}), _msg(20, text="@all come"))) == 2          # the plain word: ours where another bot has /all too
    for t in ("\u041a\u0430\u043b\u043b", "\u043a\u043e\u043b\u043b \u0432 6", "Call!"):                             # the words people type instead of a command
        assert len(_run(cfg, con, _Http(gone={37}), _msg(20, text=t))) == 2, t
    assert _run(cfg, con, _Http(), _msg(20, text="call me later")) == [] and _run(cfg, con, _Http(), _msg(20, text="\u043a\u0430\u043b")) == []
    # as a reply: under the message replied to
    sent = _run(cfg, con, _Http(), _msg(21, reply_to_message={"message_id": 3}))
    assert {s["reply_parameters"]["message_id"] for s in sent} == {3}


def test_silence_for_others(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    http = _Http()
    _run(cfg, con, http, _msg(31), _msg(99), _msg(20, chat=-555),                   # a member, a stranger, an unlinked chat
         _msg(20, text="/all@SomeOtherBot"),
         _msg(20, sender_chat={"id": -100}), {**_msg(1087968824), "from": {"id": 1087968824, "is_bot": True}},  # anonymous admin
         _msg(20, forward_origin={"type": "user"}), _msg(20, date=int(time.time()) - bot.FRESH - 5))
    # nobody is tagged; the member and the stranger in the club's chat are told it isn't theirs, the rest is silence
    assert not any("tg://" in x.get("text", "") for x in http.sent) and sum("text" in x for x in http.sent) == 2


def test_one_run_at_a_time_and_429(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    sent = _run(cfg, con, _Http(busy=2), _msg(20), _msg(21))                        # the second /all while the first runs: ignored
    assert len(sent) == 2 and sum(s["text"].count("tg://") for s in sent) == 8      # 429 twice: waited, then went
    sent = _run(cfg, con, _Http(busy=9), _msg(20))                                  # still too fast: gives up, the chat free again
    assert sent == [] and not bot._tagging


def test_group_admin_tags(env, monkeypatch):
    """A plain member who is the group's own Telegram admin may call too; a plain member not."""
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    http = _Http()
    _run(cfg, con, http, _msg(31))   # no rights: told so, then the command and the answer are deleted
    assert len(http.sent) == 2 and "tg://" not in http.sent[0]["text"] and http.sent[1] == {"chat_id": -100, "message_id": 7}
    assert len(_run(cfg, con, _Http(admins={31}), _msg(31))) == 2
