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
    monkeypatch.setattr(bot, "TAG_FAST", 0)
    monkeypatch.setattr(bot, "ALL_NO_TTL", 0)
    monkeypatch.setattr(bot, "SYNC_GAP", 0)
    monkeypatch.setattr(bot._call, "__defaults__", (0,))
    monkeypatch.setattr(bot, "ALL_AGAIN", 0)
    monkeypatch.setattr(bot, "_tagged", {})
    monkeypatch.setattr(bot, "_denied", {})
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
    sent = _run(cfg, con, _Http(gone={37}), _msg(20, text=f"/tag@{cfg.bot_username} meeting at 6"))
    ids = [[int(p.split('">')[0]) for p in s["text"].split("tg://user?id=")[1:]] for s in sent]
    assert ids == [[21, 31, 32, 33, 34], [35, 36]]                                   # the caller and the one who left skipped
    assert all(s["reply_parameters"]["message_id"] == 7 and s["chat_id"] == -100 for s in sent)
    # the caller's own words over each five (a push then says why), as plain text
    assert all(x["text"].startswith("meeting at 6\n\n") for x in sent) and any(m in sent[0]["text"] for m in bot.TAG_MARKS)
    sent = _run_fresh(cfg, con, _Http(gone={37}), _msg(20, text="/all <b>x</b> & co"), monkeypatch)
    assert sent[0]["text"].startswith("&lt;b&gt;x&lt;/b&gt; &amp; co\n\n")                    # escaped, never markup
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
    sent = _run(cfg, con, _Http(busy=2), _msg(20), _msg(21))                        # the second /all while the first runs: told to wait
    tags = [s for s in sent if "tg://" in s.get("text", "")]
    assert len(tags) == 2 and sum(s["text"].count("tg://") for s in tags) == 8      # 429 twice: waited, then went
    soon = [s for s in sent if s.get("text") == bot.texts.bot_message("ru", "all_soon")[0]]
    assert len(soon) == 1 and soon[0]["reply_parameters"]["message_id"] == 7
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
    sent = _run(cfg, con, _Http(), _msg(21))
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
    assert len(_tagged(_run(cfg, con, _Http(), _msg(20)))) == 8
    http = _Http()
    _run(cfg, con, http, _msg(21, text="/all"))                                    # a minute on: not again
    assert not _tagged(http.sent) and http.sent[0]["text"] == bot.texts.bot_message("ru", "all_soon")[0]
    assert {"chat_id": -100, "message_id": 7} in http.sent                         # the command and the answer deleted
    bot._tagged[-100] -= 301
    monkeypatch.setattr(bot, "TAG_MAX", 7)
    sent = _run(cfg, con, _Http(), _msg(21))
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
