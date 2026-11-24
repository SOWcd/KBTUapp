"""/all in a group: verified group admins and club role holders call; five mentions a message under the caller's: the app's list, the
seen ones, then the members Telegram lists to our bot over MTProto (mtbot.members, faked here: no Telethon)."""
from __future__ import annotations

import asyncio
import os
import stat
import time
import types

from kbtu import bot, db, logic, tgc
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class _Http:
    """Telegram: everyone is in the chat but `gone`; the first `busy` sendMessages answer 429."""
    def __init__(self, gone=(), busy=0, admins=()):
        self.gone, self.busy, self.sent, self.admins, self.asked = set(gone), busy, [], set(admins), []

    async def post(self, url, json=None, **_):
        if url.endswith("/getChatMember"):
            self.asked.append(json["user_id"])
            return _Resp({"ok": True, "result": {"status": "left" if json["user_id"] in self.gone else "administrator" if json["user_id"] in self.admins else "member", "user": {"id": json["user_id"]}}})
        if self.busy:
            self.busy -= 1
            return _Resp({"ok": False, "parameters": {"retry_after": 0}}, 429)
        self.sent.append(json)
        return _Resp({"ok": True, "result": {}})


def _setup(c, cfg, monkeypatch):
    monkeypatch.setattr(bot, "TAG_GAP", 0)
    monkeypatch.setattr(bot, "TAG_FAST", 0)
    monkeypatch.setattr(bot, "ALL_NO_TTL", 0)
    monkeypatch.setattr(bot, "SYNC_GAP", 0)
    monkeypatch.setattr(bot._call, "__defaults__", (0,))
    monkeypatch.setattr(bot, "ALL_AGAIN", 0)
    monkeypatch.setattr(bot, "_tagged", {})
    monkeypatch.setattr(bot, "_denied", {})
    monkeypatch.setattr(bot, "_tagging", set())
    monkeypatch.setattr(bot, "_moved", {})
    _live(monkeypatch, None)  # no member list (not configured): the app's and the seen ones, as before
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
            bot._seen(con, m)  # as hear does, before the swear filter
            await bot._group(cfg, http, con, m)
        await asyncio.gather(*list(tgc._tasks))
    asyncio.run(go())
    return http.sent


def _run_fresh(cfg, con, http, m, monkeypatch):
    """A run with the chat's wait after the last /all lifted."""
    bot._tagged.clear()
    return _run(cfg, con, http, m)


def test_head_tags_in_fives(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    sent = _run(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text=f"/tag@{cfg.bot_username} meeting at 6"))
    ids = [[int(p.split('">')[0]) for p in s["text"].split("tg://user?id=")[1:]] for s in sent]
    assert ids == [[21, 31, 32, 33, 34], [35, 36]]                                   # the caller and the one who left skipped
    assert all(s["reply_parameters"]["message_id"] == 7 and s["chat_id"] == -100 for s in sent)
    # the caller's own words over each five (a push then says why), as plain text
    assert all(x["text"].startswith("meeting at 6\n\n") for x in sent) and any(m in sent[0]["text"] for m in bot.TAG_MARKS)
    sent = _run_fresh(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text="/all <b>x</b> & co"), monkeypatch)
    assert sent[0]["text"].startswith("&lt;b&gt;x&lt;/\u2060b&gt; &amp; co\n\n")              # escaped, never markup
    sent = _run_fresh(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text="/all ask @durov or t.me/kbtu #news /start"), monkeypatch)
    head = sent[0]["text"].split("\n\n")[0]                                             # their words: never a mention, link, tag, command
    assert head == "ask @\u2060durov or t.\u2060me/\u2060kbtu #\u2060news /\u2060start" and sent[0]["link_preview_options"] == {"is_disabled": True}
    assert not bot._tagging
    assert len(_run(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text="@all come"))) == 2          # the plain word: ours where another bot has /all too
    for t in ("\u041a\u0430\u043b\u043b", "\u043a\u043e\u043b\u043b \u0432 6", "Call!"):                             # the words people type instead of a command
        assert len(_run(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text=t))) == 2, t
    sent = _run(cfg, con, _Http(gone={37}, admins={20}), _msg(20, text="meeting at 6, \u043a\u0430\u043b\u043b"))                 # the word last, after their own words
    assert len(sent) == 2 and sent[0]["text"].startswith("meeting at 6\n\n")
    assert _run(cfg, con, _Http(admins={20}), _msg(20, text="\u044d\u0442\u043e\u0442 \u043a\u0430\u043b\u043b \u0431\u044b\u043b \u0434\u043e\u043b\u0433\u0438\u043c")) == [] and _run(cfg, con, _Http(admins={20}), _msg(20, text="give me a call")) == []
    assert _run(cfg, con, _Http(admins={20}), _msg(20, text="call me later")) == [] and _run(cfg, con, _Http(admins={20}), _msg(20, text="\u043a\u0430\u043b")) == []
    # as a reply: under the message replied to
    sent = _run(cfg, con, _Http(admins={20, 21}), _msg(21, reply_to_message={"message_id": 3}))
    assert {s["reply_parameters"]["message_id"] for s in sent} == {3}


def _live(monkeypatch, ids, seen_cap=None, hidden=False, skip=()):
    """The chat's members as Telegram would list them to our bot (None: no list)."""
    async def members(cfg, chat, cap):
        if seen_cap is not None:
            seen_cap.append(cap)
        return None if ids is None else bot.mtbot.Roster(ids[:cap], hidden, set(skip))
    monkeypatch.setattr(bot.mtbot, "members", members)


def test_silence_for_others(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    http = _Http()
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 99")
    _run(cfg, con, http, _msg(20, text="/all@SomeOtherBot"),
         _msg(20, sender_chat={"id": -100}), {**_msg(1087968824), "from": {"id": 1087968824, "is_bot": True}},  # anonymous admin
         _msg(20, forward_origin={"type": "user"}), _msg(20, date=int(time.time()) - bot.FRESH - 5),
         _msg(99))                                                                      # banned in the app
    assert http.sent == [] and not bot._tagging


def test_discussion_group_never_calls(env, monkeypatch):
    """A channel's discussion group: a commenter needn't join, so nobody calls there; an ordinary group is unaffected."""
    from dataclasses import replace
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _live(monkeypatch, [500, 501])
    forum = replace(cfg, tgc_chat=-555)
    http = _Http()
    _run(forum, con, http, _msg(31, chat=-555),                                      # the forum's group
         _msg(31, reply_to_message={"message_id": 3, "is_automatic_forward": True}))   # a comment under a channel post
    assert http.sent == [] and not bot._tagging and not bot._tagged
    assert _tagged(_run(forum, con, _Http(admins={31}), _msg(31))) == [20, 21, 32, 33, 34, 35, 36, 37, 500, 501]   # an ordinary group: as before


def test_call_requires_verification_and_current_group_or_club_authority(env, monkeypatch):
    """Only authorized callers may start the roster read."""
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    reads = []
    _live(monkeypatch, [], reads)
    assert not _tagged(_run(cfg, con, _Http(), _msg(31))) and not reads
    assert not _tagged(_run(cfg, con, _Http(), _msg(20, chat=-555))) and not reads
    assert _tagged(_run(cfg, con, _Http(admins={31}), _msg(31))) == [20, 21, 32, 33, 34, 35, 36, 37]
    bot._tagged.clear()
    http = _Http()
    assert _tagged(_run(cfg, con, http, _msg(800))) == []                     # not in the app: nobody is called, told why
    assert http.sent[0]["text"] == bot.texts.bot_message("ru", "all_app")[0]
    login(c, 801, "u801")
    con.execute("DELETE FROM students WHERE user_id = (SELECT id FROM users WHERE tg_id = 801)")  # opened the app, never signed up
    assert _tagged(_run(cfg, con, _Http(), _msg(801))) == []
    con.execute("UPDATE students SET manual = 1 WHERE user_id = (SELECT id FROM users WHERE tg_id = 21)")
    assert not _tagged(_run(cfg, con, _Http(admins={21}), _msg(21)))  # verification applies even to a group admin



def test_live_list_union_order_and_cap(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    monkeypatch.setattr(bot, "TAG_MAX", 50)
    _run(cfg, con, _Http(admins={20}), _msg(500, text="hi"))                                  # seen
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 36")
    caps = []
    _live(monkeypatch, [33, 600, 500, 601, 36, 20, 777000, 600], caps, skip={32})  # Telegram's list: the app's, seen, new, banned, the caller; 32 deleted
    http = _Http(admins={20, 21})
    sent = _run(cfg, con, http, _msg(20))
    ids = [int(p.split('">')[0]) for s in sent for p in s["text"].split("tg://user?id=")[1:]]
    assert ids == [21, 31, 33, 34, 35, 37, 500, 600, 601] and caps == [50]          # the app's, the seen, then the rest; each once
    assert sorted(http.asked) == [20, 21, 31, 34, 35, 37]                            # the caller once; whom Telegram just listed isn't asked
    bot._tagged.clear()
    monkeypatch.setattr(bot, "TAG_MAX", 8)
    assert [s["text"].count("tg://") for s in _run(cfg, con, _Http(admins={20}), _msg(20))] == [5, 3]   # the cap, the app's first


def test_caller_not_in_the_chat_and_hidden_members(env, monkeypatch):
    """Telegram says the caller isn't in the chat (a guest in comments): silence. Members hidden: Telegram's list only
    when an admin calls; a member gets the app's and the seen ones."""
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    http = _Http(gone={31})
    _run(cfg, con, http, _msg(31))
    assert http.sent == [] and not bot._tagged and not bot._tagging
    _live(monkeypatch, [600, 601], hidden=True)
    assert 600 not in _tagged(_run(cfg, con, _Http(), _msg(20)))
    bot._tagged.clear()
    assert {600, 601} <= set(_tagged(_run(cfg, con, _Http(admins={31}), _msg(31))))


def test_nobody_to_call_answers_once(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    monkeypatch.setattr(bot, "ALL_NO_TTL", 0.5)
    monkeypatch.setattr(bot, "ALL_AGAIN", 300)
    reads = []
    _live(monkeypatch, [20], reads)                                                # alone there
    http = _Http(admins={20, 21})

    async def go():
        for m in (_msg(20, chat=-555), _msg(20, chat=-555, text="@all")):
            await bot._group(cfg, http, con, m)
            await tgc._last["all:-555"]  # the run, not the answer's deletion (ALL_NO_TTL on)
        await asyncio.gather(*list(tgc._tasks))
    asyncio.run(go())
    assert http.sent == [{"chat_id": -555, "text": bot.texts.bot_message("ru", "all_none")[0], "parse_mode": "HTML",
                          "reply_parameters": {"message_id": 7, "allow_sending_without_reply": True}}, {"chat_id": -555, "message_id": 7}]
    assert time.time() - bot._tagged[-555] >= 239 and not bot._tagging and len(reads) == 1   # a short wait: no rescan each message


class _Client:
    """Telethon's client as mtbot uses it."""
    made = 0

    def __init__(self):
        _Client.made += 1
        self.authed = self.connected = False
        self.session = types.SimpleNamespace(save=lambda: "")  # nothing to keep: no file written

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return self.authed

    async def sign_in(self, bot_token):
        self.authed = True

    async def disconnect(self):
        self.connected = False


def test_mtbot_session(env, monkeypatch):
    """No api pair: no list, no error. Signed in once, in memory (no meta row), disconnected between reads, reused; an
    auth error drops it (a fresh sign-in after RETRY); a hung read is given up after TIMEOUT."""
    from dataclasses import replace
    from telethon.errors import AuthKeyUnregisteredError
    from kbtu import mtbot
    c, cfg = env
    for k, v in (("_memo", {}), ("_client", None), ("_loop", None), ("_down_until", 0.0)):
        monkeypatch.setattr(mtbot, k, v)
    assert asyncio.run(mtbot.members(cfg, -100, 5)) is None
    cfg = replace(cfg, tg_api_id="1", tg_api_hash="x")
    monkeypatch.setattr(mtbot, "_new_client", lambda cfg: _Client())
    _Client.made = 0
    fail = []

    async def read(client, chat, cap):
        assert client.connected and client.authed
        if fail:
            raise fail.pop()
        return mtbot.Roster([chat], False, set())
    monkeypatch.setattr(mtbot, "_read", read)

    async def go(*chats):
        return [await mtbot.members(cfg, ch, 5) for ch in chats]
    got = asyncio.run(go(-100, -200, -100))
    assert [g.ids for g in got] == [[-100], [-200], [-100]] and _Client.made == 1 and not mtbot._client.connected
    con = db.connect(cfg.db_path)
    assert con.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'mtbot%'").fetchone()[0] == 0   # never persisted

    async def again():
        mtbot._memo.clear()
        fail.append(AuthKeyUnregisteredError(request=None))
        first = await mtbot.members(cfg, -100, 5)
        gone = mtbot._client is None
        mtbot._down_until = 0
        mtbot._memo.clear()
        return first, gone, await mtbot.members(cfg, -100, 5)
    first, gone, second = asyncio.run(again())
    assert first is None and gone and second.ids == [-100] and _Client.made == 3   # 2: a new loop, 3: after the drop

    async def hang(client, chat, cap):
        await asyncio.sleep(60)
    monkeypatch.setattr(mtbot, "_read", hang)
    monkeypatch.setattr(mtbot, "TIMEOUT", 0.05)
    monkeypatch.setattr(mtbot, "_memo", {})
    assert asyncio.run(mtbot.members(cfg, -300, 5)) is None


def test_one_run_at_a_time_and_429(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    sent = _run(cfg, con, _Http(busy=2, admins={20}), _msg(20), _msg(21))                        # the second /all while the first runs: told to wait
    tags = [s for s in sent if "tg://" in s.get("text", "")]
    assert len(tags) == 2 and sum(s["text"].count("tg://") for s in tags) == 8      # 429 twice: waited, then went
    soon = [s for s in sent if s.get("text") == bot.texts.bot_message("ru", "all_soon")[0]]
    assert len(soon) == 1 and soon[0]["reply_parameters"]["message_id"] == 7
    sent = _run(cfg, con, _Http(busy=9, admins={20}), _msg(20))                                  # still too fast: gives up, the chat free again
    assert sent == [] and not bot._tagging


# ---------------------------------------------------------------- chat_seen: whom the bot saw in a club's chat

def _clean(monkeypatch):
    monkeypatch.setattr(logic.chatlist, "_unheld", {})


def _seen(con, chat=-100):
    return [r[0] for r in con.execute("SELECT tg_id FROM chat_seen WHERE chat_id = ? ORDER BY tg_id", (chat,))]


def _tagged(sent):
    return sorted(int(p.split('">')[0]) for s in sent for p in s.get("text", "").split("tg://user?id=")[1:])


def test_seen_stranger_is_called_and_forgotten_on_leaving(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    _run(cfg, con, _Http(), _msg(500, text="hi"), _msg(20, text="ok", new_chat_members=[{"id": 501}, {"id": 502, "is_bot": True}]))
    assert _seen(con) == [20, 500, 501]                                      # no app account needed; never a bot
    sent = _run(cfg, con, _Http(admins={21}), _msg(21))
    assert {500, 501} <= set(_tagged(sent)) and 21 not in _tagged(sent)
    _run(cfg, con, _Http(), _msg(500, text="", left_chat_member={"id": 501}))  # 501 left
    assert _seen(con) == [20, 21, 500]                                        # 21 wrote too (its /all)
    sent = _run(cfg, con, _Http(gone={500}), _msg(21))                        # Telegram says 500 isn't there: not called, forgotten
    assert 500 not in _tagged(sent) and _seen(con) == [20, 21]
    # banned in the app: never called
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 20")
    assert 20 not in logic.tag_all(con, -100, 21)


def test_seen_never_anonymous_or_unlinked(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    _run(cfg, con, _Http(), _msg(600, text="x", sender_chat={"id": -100}),                 # an anonymous admin, a channel
         {**_msg(1087968824, text="x"), "from": {"id": 1087968824, "is_bot": True}},
         _msg(601, chat=-555, text="x"))                                                  # a chat no club holds
    assert con.execute("SELECT COUNT(*) FROM chat_seen").fetchone()[0] == 0


def test_seen_once_a_day_and_purge(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    logic.chatlist.seen(con, -100, {"id": 700})
    fresh = int(time.time()) - 100
    con.execute("UPDATE chat_seen SET seen_at = ?", (fresh,))
    logic.chatlist.seen(con, -100, {"id": 700})                                   # written today: no write
    assert con.execute("SELECT seen_at FROM chat_seen").fetchone()[0] == fresh
    con.execute("UPDATE chat_seen SET seen_at = 5")                               # a day on: written again
    logic.chatlist.seen(con, -100, {"id": 700})
    assert con.execute("SELECT seen_at FROM chat_seen").fetchone()[0] > 5
    night = (int(time.time()) + 5 * 3600) // 86400 * 86400 - 5 * 3600 + 3600       # 1 am in Almaty: the nightly run
    con.execute("INSERT INTO chat_seen SELECT -100, 701, org_id, ? FROM chat_seen", (night - logic.chatlist.SEEN_KEEP - 10,))
    monkeypatch.setattr(logic.core, "now", lambda: night)
    logic.stats_day(con)
    assert _seen(con) == [700]


def test_seen_gone_with_account_bot_and_migration(env, monkeypatch):
    from test_core import delete_now, tma
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    for tg in (31, 800):
        logic.chatlist.seen(con, -100, {"id": tg})
    con.execute("INSERT INTO chat_seen SELECT -200, 31, org_id, 1 FROM chat_seen LIMIT 1")
    delete_now(c, cfg, tma(31, "u31"))                                            # deleting the account: its rows, by tg_id
    assert con.execute("SELECT COUNT(*) FROM chat_seen WHERE tg_id = 31").fetchone()[0] == 0
    _run(cfg, con, _Http(), _msg(800, text="", migrate_to_chat_id=-1009))        # group to supergroup: moved
    assert _seen(con, -100) == [] and _seen(con, -1009) == [800]
    asyncio.run(bot._member(cfg, _Http(), con, {"chat": {"id": -1009, "type": "supergroup"}, "new_chat_member": {"status": "kicked"}}))
    assert _seen(con, -1009) == []                                                # the bot removed: the chat's rows go


def test_seen_chat_member_updates(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    cm = lambda st, i: {"chat_member": {"chat": {"id": -100}, "new_chat_member": {"status": st, "user": {"id": 900}}, "date": 1}, "update_id": i}  # noqa: E731

    class H(_Http):
        def __init__(self, ups):
            super().__init__()
            self.ups = ups

        async def get(self, url, **_):
            u, self.ups = self.ups, []
            return _Resp({"ok": True, "result": u})
    asyncio.run(bot.hear(cfg, H([cm("member", 1)]), 0))
    assert _seen(con) == [900]
    asyncio.run(bot.hear(cfg, H([cm("left", 2)]), 0))
    assert _seen(con) == []


def test_all_again_waits_and_cap(env, monkeypatch):
    """A chat's next /all waits ALL_AGAIN after the last one ended (told so, then both go); one run calls TAG_MAX at most."""
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    monkeypatch.setattr(bot, "ALL_AGAIN", 300)
    assert len(_tagged(_run(cfg, con, _Http(admins={20}), _msg(20)))) == 8
    http = _Http(admins={20, 21})
    _run(cfg, con, http, _msg(21, text="/all"))                                    # a minute on: not again
    assert not _tagged(http.sent) and http.sent[0]["text"] == bot.texts.bot_message("ru", "all_soon")[0]
    assert {"chat_id": -100, "message_id": 7} in http.sent                         # the command and the answer deleted
    bot._tagged[-100] -= 301
    monkeypatch.setattr(bot, "TAG_MAX", 7)
    sent = _run(cfg, con, _Http(admins={20, 21}), _msg(21))
    assert [s["text"].count("tg://") for s in sent] == [5, 2]                      # the cap: the rest not called this run


def test_seen_rows_go_when_the_chat_stops_being_the_clubs(env, monkeypatch):
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    oid = con.execute("SELECT org_id FROM chats WHERE tg_chat_id = -100").fetchone()[0]
    other = logic.create_org(con, None, "Go", "GO", "crown_3d", False)

    def fill():
        for tg in (500, 501):
            con.execute("INSERT OR REPLACE INTO chat_seen VALUES (-100, ?, ?, 1)", (tg, oid))
    fill()
    con.execute("UPDATE chats SET org_id = ? WHERE tg_chat_id = -100", (other,))   # moved to another club
    assert _seen(con) == []
    logic.chatlist.seen(con, -100, {"id": 502})
    assert con.execute("SELECT org_id FROM chat_seen").fetchone()[0] == other       # written for the new holder
    con.execute("UPDATE chats SET org_id = ? WHERE tg_chat_id = -100", (oid,))
    fill()
    con.execute("UPDATE chats SET org_id = NULL WHERE tg_chat_id = -100")           # unlinked in Studio
    assert _seen(con) == []
    con.execute("UPDATE chats SET org_id = ? WHERE tg_chat_id = -100", (oid,))
    fill()
    con.execute("UPDATE chats SET tg_chat_id = NULL WHERE tg_chat_id = -100")       # the card's chat changed
    assert _seen(con) == []
    con.execute("UPDATE chats SET tg_chat_id = -100")
    fill()
    con.execute("DELETE FROM chats")                                                # the card gone
    assert _seen(con) == []
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, created_at) VALUES (-100, ?, 'main', 0)", (oid,))
    fill()
    con.execute("UPDATE chats SET title = 'x'")                                     # an unrelated change keeps them
    assert _seen(con) == [500, 501]
    con.execute("DELETE FROM chat_sync")                                            # the sync link removed
    assert _seen(con) == []
    eid = con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, emoji, color, chat_id, created_at, updated_at)
        VALUES (?, 'published', 'Ev', 'A', 0, 'x', 'blue', -100, 0, 0)""", (oid,)).lastrowid    # an event's chat alone
    fill()
    con.execute("UPDATE events SET chat_id = -300 WHERE id = ?", (eid,))            # the event's chat changed
    assert _seen(con) == []
    con.execute("UPDATE events SET chat_id = -100 WHERE id = ?", (eid,))
    fill()
    con.execute("DELETE FROM events WHERE id = ?", (eid,))                          # the event deleted
    assert _seen(con) == []


def test_seen_who_is_never_kept(env, monkeypatch):
    """Forwarded authors, replied-to people, inline bots, Telegram's service accounts, the app's banned: never kept;
    a person who left and came back the same day: kept again; another club's rows never called."""
    c, cfg = env
    con = _setup(c, cfg, monkeypatch)
    _clean(monkeypatch)
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 36")
    _run(cfg, con, _Http(),
         _msg(510, text="x", forward_origin={"type": "user", "sender_user": {"id": 511}}, reply_to_message={"message_id": 1, "from": {"id": 512}},
              via_bot={"id": 513, "is_bot": True}),
         *[{**_msg(tg, text="x"), "from": {"id": tg}} for tg in logic.chatlist.TG_SERVICE],
         _msg(36, text="x"))
    assert _seen(con) == [510]
    _run(cfg, con, _Http(), _msg(1, text="", left_chat_member={"id": 510}), _msg(1, text="", new_chat_members=[{"id": 510}]))
    assert _seen(con) == [1, 510]                                                   # 1: the admin who did it
    other = logic.create_org(con, None, "Go", "GO", "crown_3d", False)
    con.execute("INSERT INTO chat_seen VALUES (-100, 514, ?, 1)", (other,))
    assert 514 not in logic.tag_all(con, -100, 21) and 510 in logic.tag_all(con, -100, 21)


class _Telethon:
    """telethon.TelegramClient as mtbot builds it, over the real session class: sign_in gives it a DC and an auth key."""
    signed = 0

    def __init__(self, session, api_id, api_hash, **kw):
        self.session, self.connected = session, False
        assert kw["receive_updates"] is False and kw["catch_up"] is False

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return self.session.auth_key is not None

    async def sign_in(self, bot_token):
        from telethon.crypto import AuthKey
        _Telethon.signed += 1
        self.session.set_dc(2, "149.154.167.51", 443)
        self.session.auth_key = AuthKey(os.urandom(256))

    async def disconnect(self):
        self.connected = False


def test_mtbot_session_survives_a_restart(env, monkeypatch):
    """The auth goes to mtbot.session beside the database (0600, the string alone, no names); the next process start
    loads it and doesn't sign in; a dead key deletes it; the bot's own shutdown keeps it."""
    from dataclasses import replace
    import telethon
    from telethon.errors import AuthKeyDuplicatedError
    from telethon.sessions import StringSession
    from kbtu import mtbot
    c, cfg = env
    cfg = replace(cfg, tg_api_id="1", tg_api_hash="x")
    for k, v in (("_memo", {}), ("_client", None), ("_loop", None), ("_down_until", 0.0)):
        monkeypatch.setattr(mtbot, k, v)
    monkeypatch.setattr(telethon, "TelegramClient", _Telethon)
    _Telethon.signed = 0
    fail = []

    async def read(client, chat, cap):
        client.session.process_entities(object())  # what Telethon calls with every user it sees: kept nowhere
        if fail:
            raise fail.pop()
        return mtbot.Roster([chat], False, set())
    monkeypatch.setattr(mtbot, "_read", read)
    path = mtbot._path(cfg)
    assert str(path) == f"{cfg.db_path}.mtbot-123.session" and not path.exists()   # named as the lock is, and after the bot

    def start(chat):  # a new event loop: a new process as far as mtbot knows (its client is made afresh)
        mtbot._memo.clear()
        mtbot._down_until = 0
        return asyncio.run(mtbot.members(cfg, chat, 5))
    assert start(-100).ids == [-100] and _Telethon.signed == 1
    saved = path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and not list(path.parent.glob("*.tmp"))
    s = StringSession(saved)                                   # nothing but the auth: it parses whole as a session string
    assert (s.dc_id, s.server_address, s.port) == (2, "149.154.167.51", 443) and s.auth_key and saved == s.save()
    assert start(-200).ids == [-200] and _Telethon.signed == 1 and path.read_text() == saved   # loaded, no sign-in
    asyncio.run(mtbot.close())                                 # the bot's shutdown keeps it
    assert path.exists()

    fail.append(AuthKeyDuplicatedError(request=None))
    assert start(-300) is None and not path.exists() and mtbot._client is None   # a dead key: gone, a fresh sign-in next
    assert start(-300).ids == [-300] and _Telethon.signed == 2 and path.read_text() != saved

    path.write_text("not a session")                           # a broken file: a fresh sign-in, not a crash
    assert start(-400).ids == [-400] and _Telethon.signed == 3 and StringSession(path.read_text()).auth_key


def _mt(env, monkeypatch, fail=None):
    """mtbot over _Telethon; start(chat) is a fresh process start."""
    from dataclasses import replace
    import telethon
    from kbtu import mtbot
    cfg = replace(env[1], tg_api_id="1", tg_api_hash="x")
    for k, v in (("_memo", {}), ("_client", None), ("_loop", None), ("_down_until", 0.0)):
        monkeypatch.setattr(mtbot, k, v)
    monkeypatch.setattr(telethon, "TelegramClient", _Telethon)
    _Telethon.signed = 0
    fail = [] if fail is None else fail

    async def read(client, chat, cap):
        if fail:
            raise fail.pop()
        return mtbot.Roster([chat], False, set())
    monkeypatch.setattr(mtbot, "_read", read)

    def start(chat):
        mtbot._memo.clear()
        mtbot._down_until = 0
        return asyncio.run(mtbot.members(cfg, chat, 5))
    return cfg, mtbot, start, mtbot._path(cfg)


def test_mtbot_session_never_follows_a_planted_link(env, monkeypatch, tmp_path):
    """Review: a link where the file is, or a file others may read, is refused (deleted, a fresh sign-in); the write
    never goes through a link: a fresh temp name, and the rename replaces a link itself."""
    cfg, mtbot, start, path = _mt(env, monkeypatch)
    target = tmp_path / "victim"
    target.write_text("keep me")
    path.symlink_to(target)
    assert start(-100).ids == [-100] and _Telethon.signed == 1
    assert target.read_text() == "keep me" and not path.is_symlink() and path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    planted = path.with_name(path.name + ".tmp")                  # the old fixed temp name: never written now
    planted.symlink_to(target)
    path.unlink()
    assert start(-100).ids == [-100] and target.read_text() == "keep me" and path.is_file() and not path.is_symlink()
    os.chmod(path, 0o640)                                         # readable by its group: not trusted
    assert start(-200).ids == [-200] and _Telethon.signed == 3 and stat.S_IMODE(path.stat().st_mode) == 0o600
    os.unlink(path)
    os.mkfifo(path, 0o600)                                        # not a regular file: refused at once, never waited on
    assert start(-300).ids == [-300] and _Telethon.signed == 4 and path.is_file()


def test_mtbot_forgets_an_unknown_key(env, monkeypatch):
    """Review: AuthKeyNotFound (the connection's own error, not an RPCError) forgets the file too; a file that can't be
    deleted is logged, and the client is dropped all the same."""
    from pathlib import Path
    from telethon.errors import AuthKeyNotFound
    fail = []
    cfg, mtbot, start, path = _mt(env, monkeypatch, fail)
    assert start(-100).ids == [-100] and path.exists()
    fail.append(AuthKeyNotFound())
    assert start(-100) is None and not path.exists() and mtbot._client is None
    assert start(-100).ids == [-100] and _Telethon.signed == 2 and path.exists()

    def stuck(self, missing_ok=False):
        raise PermissionError("read-only")
    monkeypatch.setattr(Path, "unlink", stuck)
    fail.append(AuthKeyNotFound())

    async def dead():
        out = await mtbot.members(cfg, -200, 5)
        return out, mtbot._client
    mtbot._memo.clear()
    assert asyncio.run(dead()) == (None, None) and path.exists()   # no exception out of /all


def test_mtbot_session_per_database_and_bot(env, monkeypatch):
    """Review: two databases in one directory, or another bot's token, never share a file; no id: no file."""
    from dataclasses import replace
    from kbtu import mtbot
    cfg = env[1]
    paths = {mtbot._path(replace(cfg, db_path=d, bot_token=t)) for d in ("/v/a.db", "/v/b.db") for t in ("11:x", "22:x")}
    assert len(paths) == 4 and all("x" not in p.name.split("mtbot")[1] for p in paths)    # the id, never the secret
    assert mtbot._path(replace(cfg, bot_token="secret")) is None and mtbot._path(replace(cfg, db_path=":memory:")) is None
