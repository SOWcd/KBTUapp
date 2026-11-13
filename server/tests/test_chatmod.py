"""A club's group's swear filter (swear.py, logic/chatmod.py, bot._swear): the word list's clean and dirty tables, the
bot's flow (delete, warn 1-2-3, mute, admins never muted, the 7-day window, edits, off = nothing), the switch's and the
report's rights, the nightly cleanup, account deletion, and /all in a chat no club holds."""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from kbtu import bot, db, logic, swear, texts, tgc
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)

CLEAN = [  # innocent words that hold a stem, names, Kazakh, English
    "\u0417\u0430\u0441\u0442\u0440\u0430\u0445\u0443\u0439 \u043c\u0430\u0448\u0438\u043d\u0443", "\u043d\u0435 \u043f\u0441\u0438\u0445\u0443\u0439", "\u043e\u0441\u043a\u043e\u0440\u0431\u043b\u044f\u0442\u044c \u043d\u0435\u043b\u044c\u0437\u044f", "\u0445\u043b\u0435\u0431 \u0441 \u043c\u0430\u0441\u043b\u043e\u043c", "\u043d\u0430\u0448\u0430 \u043a\u043e\u043c\u0430\u043d\u0434\u0430", "\u0440\u0443\u043b\u044c \u043a\u043e\u0440\u0430\u0431\u043b\u044f", "\u0431\u0435\u0437 \u0440\u0443\u0431\u043b\u044f",
    "\u0443\u043f\u043e\u0442\u0440\u0435\u0431\u043b\u044f\u0442\u044c", "\u043c\u0430\u043d\u0434\u0430\u0440\u0438\u043d \u0438 \u043c\u0430\u043d\u0434\u0430\u0442", "\u0442\u0438\u0445\u0443\u044e \u043d\u043e\u0447\u044c", "\u043d\u0438\u0447\u0435\u0433\u043e \u0441\u0435\u0431\u0435", "\u043d\u0435\u0431\u043e", "\u0441\u0443\u043a\u043d\u043e", "\u0440\u0435\u0431\u0451\u043d\u043e\u043a", "\u0415\u0431\u043e\u043b\u0430", "\u0421\u0435\u0431\u0430\u0441\u0442\u044c\u044f\u043d",
    "\u0421\u0443\u043a\u0430\u0447\u0451\u0432", "\u0431\u043b\u044f\u0445\u0430-\u043c\u0443\u0445\u0430", "\u043a\u043e\u043b\u0435\u0431\u043b\u044f\u0441\u044c", "\u0433\u0440\u0435\u0431\u043b\u044f", "\u0410\u0441\u0443\u043a\u0430", "\u0441\u0443\u043a \u0434\u0435\u0440\u0435\u0432\u0430", "\u043d\u0435\u0431\u043e\u043b\u044c\u0448\u043e\u0439", "\u043f\u043e\u0433\u0440\u0435\u0431", "\u0425\u0443\u0430\u043d",
    "\u0421\u0435\u043d \u043a\u04e9\u0442\u0435\u0440\u0456\u04a3\u0456\u0437\u0448\u0456", "\u049a\u0430\u043d\u0448\u0430 \u0442\u04b1\u0440\u0430\u0434\u044b?", "\u0436\u0430\u043b\u0430\u049b\u044b", "\u0436\u0430\u043b\u043f\u044b", "\u0421\u0456\u0437 \u043a\u0435\u043b\u0435\u0441\u0456\u0437 \u0431\u0435", "\u049b\u043e\u0442\u0430\u043d", "\u0421\u04d9\u043b\u0435\u043c, \u049b\u0430\u043b\u0430\u0439\u0441\u044b\u04a3", "\u0435\u0431\u0456\u043d \u0442\u0430\u043f", "\u0435\u0431\u0456\u043d\u0435 \u049b\u0430\u0440\u0430\u0439",
    "\u0431\u0430\u043b\u043c\u04b1\u0437\u0434\u0430\u049b\u0442\u044b \u0436\u0430\u043b\u0430\u043f \u0442\u04b1\u0440", "Scunthorpe", "shiitake mushrooms", "class assignment", "Dickens", "pass the cocktail", "Niger and Nigeria",
    "oxyacetylene", "I scored 100 and 300", "@all meeting", "a b c d", "\u044f \u0438 \u0442\u044b", "Mitsubishi", "Sukarno", "Huynh", "Kotaku",
    "\u0412\u0441\u0442\u0440\u0435\u0447\u0430 \u0432 18:00, \u043a\u0430\u0431\u0438\u043d\u0435\u0442 301", "",
    # the review's false positives (Nov 13): Kazakh, surnames and initials in an announcement, names in Latin
    "\u049a\u0430\u0437\u0456\u0440\u0433\u0456 \u0437\u0430\u043c\u0430\u043d\u0434\u0430", "\u0411\u0456\u0437\u0434\u0456\u04a3 \u0437\u0430\u043c\u0430\u043d\u0434\u0430\u0441\u0442\u0430\u0440", "\u041e\u043c\u0430\u043d\u0434\u0430 \u0431\u043e\u043b\u0434\u044b", "\u0441\u04b1\u049b\u0430\u043d \u043a\u04e9\u0437", "\u0441\u0430\u0443\u0441\u0430\u0493\u044b\u043d \u0441\u04b1\u049b\u049b\u0430\u043d", "\u0421\u0443\u043a\u0438\u0430\u0441\u044f\u043d", "\u0421\u0443\u043a\u0430\u0440\u043d\u043e", "\u0425\u0443\u0438\u0437\u0438\u043d\u0433\u0430", "\u0410\u0445\u043c\u0435\u0442\u043e\u0432\u0430 \u0415.\u0411.", "\u0415. \u0411. \u041d\u0443\u0440\u0442\u0430\u0435\u0432", "Kishitani", "Nishitani", "Yoshitomo", "Shital", "Nguyen Van Huy", "Hui Ling",
]
# each holds a stem's letters (checked below): the hard cases for a word list
INNOCENT = ["\u0443\u043f\u043e\u0442\u0440\u0435\u0431\u043b\u044f\u0442\u044c", "\u043e\u0441\u043a\u043e\u0440\u0431\u043b\u044f\u0442\u044c", "\u043a\u043e\u0440\u0430\u0431\u043b\u044f", "\u0440\u0443\u0431\u043b\u044f", "\u0441\u0430\u0431\u043b\u044f", "\u043a\u043e\u043b\u0435\u0431\u043b\u044f\u0441\u044c", "\u0434\u0438\u0440\u0438\u0436\u0430\u0431\u043b\u044f", "\u0430\u043d\u0441\u0430\u043c\u0431\u043b\u044f", "\u0441\u0442\u0435\u0431\u043b\u044f", "\u0443\u0433\u043b\u0443\u0431\u043b\u044f\u044f", "\u0438\u0441\u0442\u0440\u0435\u0431\u043b\u044f\u044f", "\u0431\u043b\u044f\u0448\u043a\u0430", "\u0431\u043b\u044f\u0445\u0430", "\u0437\u0430\u0441\u0442\u0440\u0430\u0445\u0443\u0439", "\u043f\u0441\u0438\u0445\u0443\u0439", "\u0442\u0438\u0445\u0443\u044e", "\u0433\u043b\u0443\u0445\u0443\u044e", "\u0441\u0443\u0445\u0443\u044e", "\u043f\u043b\u043e\u0445\u0443\u044e", "\u043b\u0438\u0445\u0443\u044e", "\u0441\u0442\u0440\u0430\u0445\u0443\u0435\u0442\u0441\u044f", "\u043d\u0435\u0431\u043e", "\u043d\u0435\u0431\u043e\u043b\u044c\u0448\u043e\u0439", "\u0440\u0435\u0431\u0451\u043d\u043e\u043a", "\u0445\u043b\u0435\u0431\u043e\u0431\u0443\u043b\u043e\u0447\u043d\u044b\u0435", "\u043f\u043e\u0433\u0440\u0435\u0431", "\u0421\u0435\u0431\u0430\u0441\u0442\u044c\u044f\u043d", "\u0421\u0443\u043a\u0430\u0447\u0451\u0432", "\u0441\u0443\u043a\u0438\u044f\u043a\u0438", "\u043c\u0430\u043d\u0434\u0430\u0440\u0438\u043d", "\u043c\u0430\u043d\u0434\u0430\u0442", "\u043c\u0430\u043d\u0434\u0430\u043b\u0430", "\u041c\u0430\u043d\u0434\u0430\u043b\u043e\u0440\u0435\u0446", "\u043a\u043e\u043c\u0430\u043d\u0434\u0430", "\u0410\u043c\u0430\u043d\u0434\u0430", "\u043c\u0430\u04a3\u0434\u0430\u0439", "\u043c\u0430\u04a3\u0434\u0430\u0439\u0448\u044b", "\u0441\u04b1\u049b\u0438\u044b\u043f", "Scunthorpe", "snigger", "Kshitij", "ashita", "niggard"]
DIRTY = [  # the plain words and the usual evasions
    "\u0431\u043b\u044f", "\u0411\u043b\u044f\u0442\u044c \u043e\u043f\u044f\u0442\u044c", "\u0411\u041b\u042f\u042f\u042f\u042f", "\u0431 \u043b \u044f", "\u0431.\u043b.\u044f.\u0442.\u044c", "\u0431*\u044f", "6\u043b\u044f", "x\u0443\u0439", "\u043d\u0430\u0445\u0443\u0439", "\u043f\u043e\u0445\u0443\u0439", "\u043d\u0438\u0445\u0443\u044f", "\u043e\u0445\u0443\u0435\u0442\u044c", "\u0430\u0445\u0443\u0435\u043d\u043d\u043e",
    "\u043f\u0438\u0437\u0434\u0435\u0446", "\u0441\u043f\u0438\u0437\u0434\u0438\u043b", "\u0440\u0430\u0441\u043f\u0438\u0437\u0434\u044f\u0439", "\u0435\u0431\u0430\u0442\u044c", "\u0437\u0430\u0435\u0431\u0430\u043b", "\u0437\u0430\u0435\u0431\u0438\u0441\u044c", "\u0443\u0435\u0431\u043e\u043a", "\u0441\u044a\u0435\u0431\u0430\u043b\u0441\u044f", "\u043e\u0442\u044a\u0435\u0431\u0438\u0441\u044c", "\u0434\u043e\u043b\u0431\u043e\u0451\u0431", "\u0451\u0431 \u0442\u0432\u043e\u044e",
    "\u0441\u0443\u043a\u0430", "cyka", "\u0441\u0443\u043a\u0430!!!", "\u043f\u0438\u0434\u043e\u0440\u0430\u0441", "\u043c\u0443\u0434\u0430\u043a", "\u0433\u0430\u043d\u0434\u043e\u043d", "\u0448\u043b\u044e\u0445\u0430", "\u0437\u0430\u043b\u0443\u043f\u0430", "\u043f*\u0437\u0434\u0430", "\u0445 \u0443 \u0439", "\u043f\u04383\u0434\u0430", "\u0445\u200b\u0443\u0439", "\u0422\u044b \u0445*\u0439",
    "\u0441\u0456\u043a\u0442\u0456\u043c", "\u0441\u0438\u043a\u0442\u0438\u0440", "\u049b\u043e\u0442\u0430\u049b", "\u049b\u0430\u043d\u0448\u044b\u049b",
    "fuck", "FUUUCK", "f*ck", "motherfucker", "sh1t", "bullshit", "bitch", "asshole", "blyat", "fu\u0441k",
    "blya", "nahuy", "pidor", "xuy",  # Russian in Latin letters
    "\u0431-\u043b-\u044f", "\u0441\u0441\u0443\u043a\u0430", "\u0445\u0445\u0443\u0439", "\u0441\u0443\u0443\u0443\u043a\u0430, \u043f\u0438\u0437\u0434\u0430\u0430", "ffuck", "xy\u0439\u043d\u044f",  # look-alikes, doubled and spaced letters
]


@pytest.mark.parametrize("text", CLEAN)
def test_clean_passes(text):
    assert swear.find(text) is None


def test_innocent_words_with_a_stem():
    stems = [*swear.RU, *swear.EN, *swear.RU_WORDS, *swear.EN_WORDS]
    assert len(INNOCENT) >= 40
    for w in INNOCENT:
        lo = w.lower()
        assert any(st in lo or st in lo.translate(swear._TO_CYR) for st in stems), w  # really a hard case
        assert swear.find(w) is None, w


@pytest.mark.parametrize("text", DIRTY)
def test_dirty_caught(text):
    stem = swear.find(text)
    assert stem and (stem in swear.RU or stem in swear.EN or stem in swear.RU_WORDS or stem in swear.EN_WORDS)


@pytest.fixture(autouse=True)
def _fresh_list():
    """chatmod's list of chats with the filter on is per process: none of it leaks into the next test's database."""
    logic.chatmod.stale()
    yield
    logic.chatmod.stale()


class _Resp:
    def __init__(self, body):
        self.body, self.status_code = body, 200

    def json(self):
        return self.body


class _Http:
    """Telegram: `admins` are the chat's admins; the bot (123) may delete and restrict unless `nodelete`."""
    def __init__(self, admins=(), nodelete=False, updates=()):
        self.admins, self.nodelete, self.updates, self.calls, self.n = set(admins), nodelete, list(updates), [], 1000

    async def post(self, url, json=None, **_):
        m = url.rsplit("/", 1)[1]
        self.calls.append((m, json))
        if m == "getChat":
            return _Resp({"ok": True, "result": {}})
        if m == "getChatMember" and json["user_id"] == 123:
            return _Resp({"ok": True, "result": {"status": "administrator", "can_delete_messages": not self.nodelete, "can_restrict_members": True}})
        if m == "getChatMember":
            return _Resp({"ok": True, "result": {"status": "administrator" if json["user_id"] in self.admins else "member", "user": {"id": json["user_id"]}}})
        if m == "deleteMessage" and self.nodelete:
            return _Resp({"ok": False, "description": "Bad Request: message can't be deleted"})
        if m == "sendMessage":
            self.n += 1
            return _Resp({"ok": True, "result": {"message_id": self.n}})
        return _Resp({"ok": True, "result": True})

    async def get(self, url, params=None, **_):
        out, self.updates = self.updates, []
        return _Resp({"ok": True, "result": out})

    def said(self, method):
        return [j for m, j in self.calls if m == method]


def _setup(c, cfg, monkeypatch, on=True):
    monkeypatch.setattr(bot, "SYNC_GAP", 0)
    monkeypatch.setattr(bot, "WARN_FOR", 0)
    monkeypatch.setattr(bot._call, "__defaults__", (0,))
    bot._swore.clear()
    bot._unlinked.clear()
    logic.chatmod.stale()
    for tg in (20, 21, 22, 31, 41):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, uid(21), oid, "president", "test")
    logic.set_role(con, None, uid(22), oid, "vice", "test")
    logic.set_role(con, None, uid(20), oid, "head", "test")
    logic.set_role(con, None, uid(31), oid, "member", "test")
    other = logic.create_org(con, None, "Go", "GO", "crown_3d", False)
    logic.set_role(con, None, uid(41), other, "president", "test")
    cid = con.execute("""INSERT INTO chats (title, kind, url, tg_chat_id, created_at, status, org_id, swear)
        VALUES ('Chess', 'group', 'https://t.me/+c', -100, 0, 'org', ?, ?)""", (oid, int(on))).lastrowid
    return con, oid, other, cid, uid


def _msg(tg, text="\u0442\u044b \u0441\u0443\u043a\u0430", chat=-100, mid=7, **kw):
    return {"chat": {"id": chat, "type": "supergroup"}, "message_id": mid, "text": text, "date": int(time.time()), "from": {"id": tg}, **kw}


async def _drain():
    while tgc._tasks:
        await asyncio.gather(*list(tgc._tasks))


def _run(cfg, con, http, *msgs):
    async def go():
        got = [await bot._swear(cfg, http, con, m) for m in msgs]
        await _drain()
        return got
    return asyncio.run(go())


def _hits(con, cid):
    return con.execute("SELECT tg_id, user_id, stem, warn, muted FROM swear_hits WHERE chat_id = ? ORDER BY id", (cid,)).fetchall()


def test_warn_warn_mute_and_start_over(env, monkeypatch):
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    http = _Http()
    assert _run(cfg, con, http, _msg(31, mid=1)) == [True]
    bot._swore.clear()  # a minute on
    _run(cfg, con, http, _msg(31, "\u0431 \u043b \u044f", mid=2))
    assert [j["message_id"] for j in http.said("deleteMessage")] == [1, 1001, 2, 1002]  # the message, then its warning a minute on
    texts_ = [j["text"] for j in http.said("sendMessage")]
    # the warning names nobody and counts nothing in public: the same template each time
    assert texts_ == [texts.swear("ru", "warn")] * 2 and not any(x in texts_[0] for x in ("tg://", "31", "1", "2", "3", "<a"))
    assert all("\u0441\u0443\u043a" not in t and "\u0431\u043b\u044f" not in t for t in texts_)  # never the words
    assert [tuple(h) for h in _hits(con, cid)] == [(31, uid(31), "\u0441\u0443\u043a\u0430", 1, 0), (31, uid(31), "\u0431\u043b\u044f", 2, 0)]
    bot._swore.clear()
    http = _Http()
    _run(cfg, con, http, _msg(31, mid=3))
    assert http.said("restrictChatMember")[0]["user_id"] == 31
    assert abs(http.said("restrictChatMember")[0]["until_date"] - time.time() - 3600) < 5
    assert not any(http.said("restrictChatMember")[0]["permissions"].values())
    assert http.said("sendMessage")[0]["text"] == texts.swear("ru", "mute") and "tg://" not in texts.swear("ru", "mute")
    assert tuple(_hits(con, cid)[-1])[3:] == (3, 1)
    # a flood within the minute: only deleted, nothing counted or said
    http = _Http()
    _run(cfg, con, http, _msg(31, mid=4), _msg(31, mid=5))
    assert [j["message_id"] for j in http.said("deleteMessage")] == [4, 5] and not http.said("sendMessage") and len(_hits(con, cid)) == 3
    bot._swore.clear()  # a minute on: the count starts over after the mute
    http = _Http()
    _run(cfg, con, http, _msg(31, mid=6))
    assert _hits(con, cid)[-1]["warn"] == 1 and not http.said("restrictChatMember")


def test_forum_topic(env, monkeypatch):
    """A group with topics: the warning goes into the deleted message's topic and removes itself there; General has none."""
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    con.execute("UPDATE chats SET forum = 1")
    assert next(x for x in c.get(f"/api/orgs/{oid}/chats", headers=tma(21)).json() if x["id"] == cid)["kind"] == "forum"
    http = _Http()
    _run(cfg, con, http, _msg(31, mid=1, message_thread_id=77, is_topic_message=True))
    bot._swore.clear()
    _run(cfg, con, http, _msg(22, mid=2), _msg(20, mid=3, message_thread_id=1))  # General; a plain reply's thread in a group
    sent = http.said("sendMessage")
    assert sent[0]["message_thread_id"] == 77 and all("message_thread_id" not in j for j in sent[1:]) and len(sent) == 3
    assert sorted(j["message_id"] for j in http.said("deleteMessage")) == [1, 2, 3, 1001, 1002, 1003]  # each warning goes too


def test_one_warning_a_minute(env, monkeypatch):
    """A swearing flood: one warning a person a minute, at most SWEAR_CHAT_CAP a minute in the chat; every message goes."""
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    http = _Http()
    _run(cfg, con, http, *(_msg(31, mid=i) for i in range(10)), *(_msg(tg, mid=100 + tg - 1000) for tg in range(1000, 1015)))
    assert len([j for j in http.said("deleteMessage") if j["message_id"] < 1001]) == 25
    assert len(http.said("sendMessage")) == bot.SWEAR_CHAT_CAP and len(_hits(con, cid)) == bot.SWEAR_CHAT_CAP
    assert [h["tg_id"] for h in _hits(con, cid)].count(31) == 1


def test_admins_left_alone_and_window(env, monkeypatch):
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    http = _Http(admins={21})
    _run(cfg, con, http, *(_msg(21, mid=i) for i in (1, 2, 3)))
    assert not http.said("deleteMessage") and not http.said("sendMessage") and _hits(con, cid) == []
    # 7 days: older warnings don't count
    _run(cfg, con, _Http(), _msg(22, mid=9))
    bot._swore.clear()
    _run(cfg, con, _Http(), _msg(22, mid=10))
    con.execute("UPDATE swear_hits SET at = at - 8 * 86400 WHERE tg_id = 22")
    bot._swore.clear()
    _run(cfg, con, _Http(), _msg(22, mid=11))
    assert _hits(con, cid)[-1]["warn"] == 1


def test_off_and_ignored(env, monkeypatch):
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch, on=False)
    http = _Http()
    assert _run(cfg, con, http, _msg(31)) == [False]
    con.execute("UPDATE chats SET swear = 1")
    assert _run(cfg, con, http, _msg(31)) == [False]  # another worker's switch: seen within FRESH
    logic.chatmod.stale()
    assert _run(cfg, con, http, _msg(31, "good morning"), _msg(31, "\u0441\u0443\u043a\u0430", chat=-555),           # clean; another chat
                {**_msg(1087968824), "from": {"id": 1087968824, "is_bot": True}, "sender_chat": {"id": -100}},  # anonymous admin
                {**_msg(5), "from": {"id": 5, "is_bot": True}},                                   # a bot
                _msg(31, text=None, new_chat_members=[{"id": 9}])) == [False] * 5                 # a service message
    assert http.calls == [] and _hits(con, cid) == []
    assert _run(cfg, con, http, _msg(31, text=None, caption="\u0444\u043e\u0442\u043e, \u0431\u043b\u044f")) == [True]                # a caption counts
    # a message in any group costs no query: the list of chats with the filter on is read once a FRESH
    asked = []
    con.set_trace_callback(asked.append)
    assert _run(cfg, con, http, *(_msg(31, "hello", chat=ch) for ch in (-100, -555, -556))) == [False] * 3
    con.set_trace_callback(None)
    assert asked == []


def test_bot_without_rights(env, monkeypatch):
    """A refused delete: the bot's rights asked, the filter paused there and Studio told which; given back (my_chat_member),
    on again by itself."""
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    http = _Http(nodelete=True)
    _run(cfg, con, http, _msg(31))
    assert not http.said("sendMessage") and _hits(con, cid) == []
    studio = lambda: next(x for x in c.get(f"/api/orgs/{oid}/chats", headers=tma(21)).json() if x["id"] == cid)  # noqa: E731
    assert studio()["swear"] is True and studio()["swearMiss"] == ["delete"]
    http = _Http()
    assert _run(cfg, con, http, _msg(31)) == [False] and http.calls == []  # paused: nothing read
    upd = {"chat": {"id": -100, "type": "supergroup"}, "from": {"id": 21},
           "new_chat_member": {"status": "administrator", "user": {"id": 123}, "can_delete_messages": True, "can_restrict_members": False}}
    asyncio.run(bot._member(cfg, http, con, upd))
    assert studio()["swearMiss"] == ["ban"]
    asyncio.run(bot._member(cfg, http, con, {**upd, "new_chat_member": {**upd["new_chat_member"], "can_restrict_members": True}}))
    assert studio()["swearMiss"] == []
    assert _run(cfg, con, _Http(), _msg(31)) == [True]


def test_edited_message(env, monkeypatch):
    """Telegram is asked for edits always; an edit that smuggles a word in goes like a new message."""
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    assert '"edited_message"' in bot._wanted(cfg)
    http = _Http(updates=[{"update_id": 5, "edited_message": _msg(31, "\u043d\u0443 \u0438 \u0441\u0443\u043a\u0430", mid=3)}])

    async def go():
        n = await bot.hear(cfg, http, 0)
        await _drain()
        return n
    assert asyncio.run(go()) == 6
    assert http.said("deleteMessage")[0]["message_id"] == 3 and _hits(con, cid)[0]["stem"] == "\u0441\u0443\u043a\u0430"


class _Client:
    """httpx.AsyncClient for the app's switch: the bot's own rights in the chat; whatever it sends."""
    rights = {"status": "administrator", "can_delete_messages": True, "can_restrict_members": True}
    sent: list = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, **_):
        if url.endswith("/getChatMember"):
            return _Resp({"ok": True, "result": _Client.rights})
        _Client.sent.append(json)
        return _Resp({"ok": True, "result": {"message_id": 1}})


def test_switch_and_report_rights(env, monkeypatch):
    c, cfg = env
    con, oid, other, cid, uid = _setup(c, cfg, monkeypatch, on=False)
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    _Client.sent = []
    put = lambda tg, on, o=oid, ch=cid: c.put(f"/api/orgs/{o}/chats/{ch}/swear", headers=tma(tg), json={"on": on})  # noqa: E731
    assert put(31, True).status_code == 403 and put(20, True).status_code == 403   # a member, a Head
    assert put(41, True).status_code == 403 and put(41, True, other).status_code == 404  # another club's President, by either club
    assert put(21, "yes").status_code == 400
    _Client.rights = {"status": "administrator", "can_delete_messages": True, "can_restrict_members": False}
    r = put(21, True)
    assert r.status_code == 409 and r.json()["message"] == "rights" and r.json()["missing"] == ["ban"] and not _Client.sent
    _Client.rights = {"status": "administrator", "can_delete_messages": True, "can_restrict_members": True}
    r = put(22, True)
    assert r.status_code == 200 and next(x for x in r.json() if x["id"] == cid)["swear"] is True
    assert len(_Client.sent) == 1 and _Client.sent[0]["chat_id"] == -100 and _Client.sent[0]["text"] == texts.swear("ru", "on")
    put(21, True)
    assert len(_Client.sent) == 1                                                    # no change, no second notice
    assert put(21, False).status_code == 200 and len(_Client.sent) == 2
    # the report: a member by name, someone the app doesn't know as "a chat member", never their Telegram id
    con.execute("UPDATE chats SET swear = 1")
    logic.chatmod.stale()
    _run(cfg, con, _Http(), _msg(31), _msg(555777, mid=9))
    bot._swore.clear()
    _run(cfg, con, _Http(), _msg(31, "\u0431\u043b\u044f", mid=8))
    get = lambda tg, o=oid: c.get(f"/api/orgs/{o}/chats/swear", headers=tma(tg))  # noqa: E731
    assert get(31).status_code == 403 and get(41).status_code == 403
    r = get(20)
    assert r.status_code == 200 and "555777" not in r.text
    rows = r.json()
    assert rows[0]["person"]["id"] == uid(31) and rows[0]["warns"] == 2 and set(rows[0]["stems"]) == {"\u0441\u0443\u043a\u0430", "\u0431\u043b\u044f"} and rows[0]["mutes"] == 0
    assert rows[1]["person"] is None and rows[1]["warns"] == 1
    assert get(41, other).json() == []
    # the chat off the club's page: off, and its record goes
    assert c.delete(f"/api/orgs/{oid}/chats/{cid}", headers=tma(21)).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM swear_hits").fetchone()[0] == 0


def test_cleanup_and_account_deletion(env, monkeypatch):
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    _run(cfg, con, _Http(), _msg(31), _msg(20, mid=8))
    con.execute("INSERT INTO swear_hits (chat_id, tg_id, user_id, stem, at, warn) VALUES (?, 31, NULL, 'x', ?, 1)", (cid, logic.now()))  # before the app knew him
    con.execute("UPDATE swear_hits SET at = at - 91 * 86400 WHERE tg_id = 20")
    logic.chatmod.sweep(con)
    assert {h["tg_id"] for h in _hits(con, cid)} == {31}
    assert ("swear_hits", "user_id") in logic._DEL_GONE
    delete_now(c, cfg, tma(31))
    assert _hits(con, cid) == []


def test_all_in_a_chat_no_club_holds(env, monkeypatch):
    c, cfg = env
    con, oid, _, cid, uid = _setup(c, cfg, monkeypatch)
    http = _Http(admins={41})

    async def go(*msgs):
        for m in msgs:
            await bot._group(cfg, http, con, m)
        await _drain()
    asyncio.run(go(_msg(31, "/all", chat=-555), _msg(41, "/all", chat=-555), _msg(41, "@all", chat=-555)))
    sent = http.said("sendMessage")
    assert len(sent) == 1 and sent[0]["chat_id"] == -555 and "\u2192" in sent[0]["text"]   # the admin, once a minute; a member: silence
