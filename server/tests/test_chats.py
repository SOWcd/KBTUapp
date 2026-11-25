"""Group chats: linking a chat to a club or event, the chats directory, org chats and the catalog."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import types

from fastapi.testclient import TestClient

from kbtu import bot, bot_dm, bot_groups, db, logic, media, outbox, app as server, texts
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def test_chat_pick(env):
    """Studio's "Link a group": Telegram's picker, then our bot added there by the same person within ten minutes links
    it to the club; someone else's add, a stale pick, a plain member: nothing."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], ali["id"]))
    assert c.post("/api/orgs/1/chats/pick", headers=tma(21, "Ali"), json={"kind": "group"}).status_code == 403
    r = c.post("/api/orgs/1/chats/pick", headers=tma(20, "Pres"), json={"kind": "group"}).json()
    assert "startgroup=" in r["url"] and "invite_users" in r["url"]
    group = {"id": -100500, "type": "supergroup", "title": "IT Club chat"}
    assert logic.pick_claim(con, 21, group, "https://t.me/+abcdefgh") is None          # not the one who picked
    cid = logic.pick_claim(con, 20, group, "https://t.me/+abcdefgh")
    row = con.execute("SELECT org_id, tg_chat_id, status, title FROM chats WHERE id = ?", (cid,)).fetchone()
    assert tuple(row) == (1, -100500, "org", "IT Club chat")
    assert logic.pick_claim(con, 20, {**group, "id": -100501}, "https://t.me/+zzzzzzzz") is None   # the pick is spent
    con.close()


class _ChatHttp:
    """Telegram for my_chat_member: getChat tells an admin bot the chat's invite link."""
    async def post(self, url, json=None, **_):
        m = url.rsplit("/", 1)[1]
        body = {"invite_link": f"https://t.me/+inv{-json['chat_id']}"} if m == "getChat" else 5 if m == "getChatMemberCount" else True
        return types.SimpleNamespace(json=lambda: {"ok": True, "result": body})


def _bot_in(cfg, con, tg, chat_id, status="administrator", kind="supergroup", title=None):
    """Our bot added to a chat by `tg` (Telegram's action performer); whose card it is now, if any."""
    asyncio.run(bot_groups._member(cfg, _ChatHttp(), con, {"chat": {"id": chat_id, "type": kind, "title": title or f"chat {chat_id}"},
                                                     "from": {"id": tg}, "new_chat_member": {"status": status, "user": {"id": 123}}}))
    r = con.execute("SELECT org_id FROM chats WHERE tg_chat_id = ?", (chat_id,)).fetchone()
    return r and r[0]


def _two_clubs(c, cfg):
    pres, ali, bob = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "bob")
    con = db.connect(cfg.db_path)
    for i, slug in ((1, "it"), (2, "art")):
        con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (?, ?, 'club', ?, ?, 'laptop_3d', 0)", (i, slug, slug, slug))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0), (2, ?, 'president', 0)",
                (pres["id"], ali["id"], bob["id"]))
    return con, pres


def test_chat_link_bot_first(env, monkeypatch):
    """Owner, Nov 14: our bot made admin first, Studio afterwards. Nothing links by itself: the chat is remembered for
    the one who made it admin, Studio → Chats lists it to him alone, and «Link» (Telegram saying now that the bot and
    he are its admins) makes it the club's; the record is spent. A plain member's add remembers nothing; the bot
    demoted: forgotten; at most five a person; a deleted account's go."""
    c, cfg = env
    con, pres = _two_clubs(c, cfg)
    status = {"bot": "administrator", "me": "creator"}

    async def call(_cfg, _http, method, params, gap=0):
        assert method == "getChatMember"
        return {"ok": True, "result": {"status": status["bot" if params["user_id"] == int(cfg.bot_token.split(":")[0]) else "me"]}}
    monkeypatch.setattr(bot, "_call", call)
    waits = lambda tg=20, oid=1: c.get(f"/api/orgs/{oid}/chats/waiting", headers=tma(tg)).json()  # noqa: E731
    link = lambda w, tg=20, oid=1: c.post(f"/api/orgs/{oid}/chats/waiting/{w}", headers=tma(tg))  # noqa: E731

    assert _bot_in(cfg, con, 20, -100600, "member") is None and waits() == []     # a plain member's add: nothing
    assert _bot_in(cfg, con, 20, -100601, title="IT <b>chat</b>") is None          # made admin: nothing linked by itself
    (w,) = waits()
    assert w["title"] == "IT <b>chat</b>" and w["kind"] == "group" and set(w) == {"id", "title", "kind"}   # no Telegram id, no invite
    assert c.get("/api/orgs/1/chats/waiting", headers=tma(21)).status_code == 403   # a plain club member
    assert waits(22, 2) == []                                                      # someone else's: never listed
    assert link(w["id"], 22, 2).status_code == 404                                 # nor his to link
    status["bot"] = "member"
    assert link(w["id"]).status_code == 409                                        # our bot no longer an admin there
    status.update(bot="administrator", me="member")
    assert link(w["id"]).status_code == 409                                        # nor I
    status["me"] = "administrator"
    r = link(w["id"])
    assert r.status_code == 200 and [x["title"] for x in r.json()] == ["IT <b>chat</b>"]
    assert con.execute("SELECT org_id, url FROM chats WHERE tg_chat_id = -100601").fetchone()[:] == (1, "https://t.me/+inv100601")
    assert link(w["id"]).status_code == 404 and waits() == []                      # spent
    _bot_in(cfg, con, 20, -100602)
    _bot_in(cfg, con, 20, -100602, "member")                                       # demoted: no proof left
    assert waits() == []
    for i in range(7):
        _bot_in(cfg, con, 20, -100610 - i)
    assert len(waits()) == 5                                                       # the newest five
    con.execute("UPDATE chat_waits SET until = 0 WHERE chat_id = -100610 - 6")
    assert len(waits()) == 4                                                       # ten minutes passed
    delete_now(c, cfg, tma(20))
    assert not con.execute("SELECT 1 FROM chat_waits").fetchone()
    con.close()


def test_chat_link_picker_first(env):
    """Studio's picker first, then our bot made admin by the same person: linked at once (the pick spent); made admin
    by someone else, or only added as a plain member: the pick waits."""
    c, cfg = env
    con, pres = _two_clubs(c, cfg)
    c.post("/api/orgs/1/chats/pick", headers=tma(20), json={"kind": "group"})
    assert _bot_in(cfg, con, 22, -100620) is None                                 # not the one who picked
    assert _bot_in(cfg, con, 20, -100621, "member") is None                       # a plain member
    assert _bot_in(cfg, con, 20, -100621) == 1
    assert not con.execute("SELECT 1 FROM meta WHERE key = 'chpick:20'").fetchone()
    con.close()


def test_chat_claims_respect_other_clubs(env):
    """Codex, Nov 14: a chat another club holds by an event or a sync link stays theirs on every path (the picker, a
    remembered chat, an event's /start); a channel is never matched to a card by its title alone; a card with the
    chat's invite link isn't taken by a plain member's add."""
    c, cfg = env
    con, pres = _two_clubs(c, cfg)
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at, chat_id)
        VALUES (5, 2, 'published', 'Art night', 'Hall', 0, 'x', '#000', 0, 0, -300)""")
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, created_at) VALUES (-301, 2, 'main', 0)")
    for chat in (-300, -301):
        logic.chat_pick(con, logic.Viewer(pres["id"], "user", True), 1)
        assert logic.pick_claim(con, 20, {"id": chat, "type": "supergroup", "title": "x"}, "https://t.me/+abcdefgh") is None
        assert _bot_in(cfg, con, 20, chat) is None and not con.execute("SELECT 1 FROM chat_waits").fetchone()  # never remembered
    assert con.execute("SELECT org_id FROM events WHERE chat_id = -300").fetchone()[0] == 2
    con.execute("INSERT INTO chats (title, kind, url, status, org_id, created_at) VALUES ('Duplicate title', 'channel', 'https://t.me/+ijklmnop', 'org', 1, 0)")
    assert logic.bot_added(con, 20, {"id": -400, "type": "channel", "title": "Duplicate title"}) is None
    con.execute("INSERT INTO chats (title, kind, url, status, org_id, created_at) VALUES ('IT chat', 'group', 'https://t.me/+inv500', 'org', 1, 0)")
    assert _bot_in(cfg, con, 20, -500, "member") is None                          # its invite link, but a plain member's add
    assert _bot_in(cfg, con, 20, -500) == 1                                       # made admin: the card is it
    e = {"id": 6, "token": "tok"}
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at, chat_token)
        VALUES (6, 1, 'published', 'IT night', 'Hall', 0, 'x', '#000', 0, 0, 'tok')""")
    assert logic.chat_claim(con, e["token"], 20, -301) is None                    # another club's synced chat
    con.close()


def test_chats_directory(env, monkeypatch):
    """The chats directory (§4.11): the admin adds t.me links; "for you" = aimed at my school and course, then those for
    everyone; a tick once opened; a bad link is refused. The avatar, members and (if left empty) the title come from the
    chat's t.me page; a topics group is its own kind."""
    import dataclasses
    import io
    from PIL import Image
    c, cfg = env
    png = io.BytesIO(); Image.new("RGB", (64, 64), "red").save(png, "PNG")

    async def peek(http, url):
        return {"title": "KBTU &official", "image": png.getvalue(), "members": 1234} if "official" in url else {"title": None, "image": None, "members": None}
    monkeypatch.setattr(media, "chat_peek", peek)
    page = '<meta property="og:title" content="KBTU app Topics&#33;">\n<div class="tgme_page_extra">15 members, 9 online</div>'
    assert media._OG.findall(page) == [("title", "KBTU app Topics&#33;")] and media._EXTRA.search(page).group(1) == "15"
    assert media._EXTRA.search('<div class="tgme_page_extra">no members</div>').group(1) == "no"  # a hidden count is still a group
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"), login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    add = lambda **kw: c.post("/api/admin/chats", headers=B, json={"kind": "group", **kw})
    assert c.post("/api/admin/chats", headers=A, json={"title": "X", "url": "https://t.me/x", "kind": "group"}).status_code == 403
    assert add(title="Bad", url="http://evil.example/x").status_code == 400
    everyone = add(url="https://t.me/kbtu_official", kind="channel").json()                     # no title: the chat's own
    assert everyone["title"] == "KBTU &official" and everyone["photo"] and everyone["members"] == 1234
    assert add(title="Talk", url="https://t.me/talk", kind="forum").json()["kind"] == "forum"
    assert add(url="https://t.me/nameless").status_code == 400                                 # no title anywhere
    mine = add(title="SITE 2nd year", url="https://t.me/+AbCdEf123", school="SITE", course=2).json()
    add(title="SITE 4th year", url="https://t.me/+Zz901234", school="SITE", course=4)
    old = add(title="Legacy invite", url="https://t.me/joinchat/MixedCase12").json()
    assert old["url"] == "https://t.me/+MixedCase12"
    con = db.connect(cfg.db_path)
    con.execute("UPDATE chats SET url = 'https://t.me/joinchat/MixedCase12' WHERE id = ?", (old["id"],))
    guest = c.get("/api/chats", headers=tma(62)).json()
    assert all(x["id"] != old["id"] for x in guest["forYou"] + guest["all"])
    con.execute("DELETE FROM chats WHERE id = ?", (old["id"],))
    got = c.get("/api/chats", headers=A).json()
    assert [x["id"] for x in got["forYou"]] == [mine["id"], everyone["id"], got["forYou"][2]["id"]] and len(got["all"]) == 4
    assert c.post(f"/api/chats/{mine['id']}/opened", headers=A).status_code == 204
    assert next(x for x in c.get("/api/chats", headers=A).json()["forYou"] if x["id"] == mine["id"])["opened"] is True
    assert len(c.get("/api/chats", headers=tma(62, "Guest")).json()["forYou"]) == 2  # a guest: those for everyone


def test_event_chat(env):
    """An event's group without a userbot: "Create chat" gives a startgroup link with a one-time token;
    the bot's /start in the group from an organizer links it; join requests: those going and the team in, others not."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ali"), (22, "bota")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    logic.set_role(con, None, ids[20], oid, "president", "test")
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    assert c.post(f"/api/events/{e['id']}/chat", headers=tma(21)).status_code == 403
    url = c.post(f"/api/events/{e['id']}/chat", headers=tma(20)).json()["url"]
    token = url.split("startgroup=ec_")[1].split("&")[0]
    assert logic.chat_claim(con, token, 21, -100) is None                     # not an organizer
    assert logic.chat_claim(con, token, 20, -100)["id"] == e["id"]
    assert logic.chat_claim(con, token, 20, -100) is None                     # spent
    assert c.post(f"/api/events/{e['id']}/registration", headers=tma(21)).status_code == 200
    assert logic.chat_join(con, -100, 21) is True and logic.chat_join(con, -100, 22) is False and logic.chat_join(con, -100, 20) is True
    assert logic.chat_join(con, -999, 21) is None
    con.execute("UPDATE events SET chat_link = 'https://t.me/+x' WHERE id = ?", (e["id"],))
    assert c.get(f"/api/events/{e['id']}", headers=tma(21)).json()["chat"] == "https://t.me/+x"
    assert c.get(f"/api/events/{e['id']}", headers=tma(22)).json()["chat"] is None


def test_suggest_chat(env, monkeypatch):
    """Any student suggests a chat through the bot (PLAN item 45): picked in Telegram's picker or sent as @name; public
    only, a person or a bot refused, nothing twice, 3 a day; waiting it shows nowhere but the admin's list; approved,
    it joins the catalog and its suggester hears so."""
    from kbtu import media
    c, cfg = env
    ali = login(c, 30, "ali")
    adm = c.get("/api/me", headers=tma(31)).json()
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (adm["id"],))  # an admin's role comes from the config
    assert [logic.chat_handle(x) for x in ("@KBTU_news", "https://t.me/kbtu_news/", "t.me/s/Kbtu_news", "https://t.me/+AbCdEf", "hi")] \
        == ["kbtu_news", "kbtu_news", "kbtu_news", None, None]
    pages = {"https://t.me/kbtu_news": {"title": "KBTU News", "image": None, "members": 4900, "channel": True},
             "https://t.me/some_person": {"title": "Some Person", "image": None, "members": None}}
    async def peek(http, url):
        return {"ok": True, **(pages.get(url) or {"title": "Chat", "image": None, "members": 10, "channel": False})}
    monkeypatch.setattr(media, "chat_peek", peek)
    def say(tg, **m):  # each a while after the last (one t.me look per 10 s per student)
        con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
        return asyncio.run(bot_dm._suggest(cfg, None, con, {"chat": {"id": tg, "type": "private"}, "date": logic.now(), **m}))["text"]
    picked = {"chat_shared": {"request_id": 1, "chat_id": -100777, "username": "KBTU_news", "title": "KBTU News"}}
    assert say(99, **picked) == texts.bot_message("ru", "chat_signin")[0]          # not a student
    assert say(30, **picked) == texts.chat_reply("ru", [("sent", "KBTU News", "channel")])
    assert say(30, text="@kbtu_news") == texts.chat_reply("ru", [("waiting", "KBTU News", "channel")])  # same chat, typed: already waiting
    assert say(30, text="@some_person") == texts.bot_message("ru", "chat_notchat")[0]
    assert say(30, text="hello") == texts.bot_message("ru", "chat_private")[0]
    assert say(30, **{"chat_shared": {"request_id": 2, "chat_id": -100555, "title": "Closed"}}) == texts.bot_message("ru", "chat_invite")[0]
    assert [logic.chat_link(x) for x in ("@A_chat", "t.me/+AbCdEf12", "https://t.me/joinchat/AbCdEf12", "t.me/+x")] \
        == ["https://t.me/a_chat", "https://t.me/+AbCdEf12", "https://t.me/+AbCdEf12", None]
    assert say(30, text="https://t.me/+AbCdEf12").startswith("✅")                  # a closed chat by its invite link
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "t.me/joinchat/AbCdEf12"}).json()["status"] == "waiting"  # the app's sheet
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "nope"}).json()["status"] == "bad"
    assert c.post("/api/chats/suggest", headers=tma(99), json={"link": "@x_chat"}).status_code == 403
    # one clock for the two: the gate counts 10-second slots (now() // 10), and two calls a few ms apart that straddle a
    # slot's end were two slots, so "sent" came back where "slow" was asserted (was: failed now and then, more under load)
    real_now, frozen = bot_dm.now, bot_dm.now()
    monkeypatch.setattr(bot_dm, "now", lambda: frozen)
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "@typed_once"}).json()["status"] == "sent"
    assert c.post("/api/chats/suggest", headers=tma(30), json={"link": "@typed_fast"}).json()["status"] == "slow"  # within 10 s of the last
    monkeypatch.setattr(bot_dm, "now", real_now)
    con.execute("DELETE FROM chats WHERE url = 'https://t.me/typed_once'")
    assert say(30, text="@second_chat").startswith("✅") and say(30, text="@third_chat").startswith("✅")
    assert asyncio.run(bot_dm._suggest(cfg, None, con, {"chat": {"id": 30, "type": "private"}, "date": logic.now(), "text": "@quick_one"}))["text"] \
        == texts.bot_message("ru", "chat_later")[0]                                    # within 10 s of the last
    for i in range(6):
        assert say(30, text=f"@more_chat_{i}").startswith("✅")
    assert say(30, text="@eleventh_chat") == texts.bot_message("ru", "chat_limit")[0]  # 10 a day
    assert c.get("/api/chats", headers=tma(30)).json()["all"] == []                  # waiting: nowhere to see
    assert "pending" not in c.get("/api/chats", headers=tma(30)).json()
    waiting = c.get("/api/chats", headers=tma(31)).json()["pending"]
    assert [x["kind"] for x in waiting][-3:] == ["group", "group", "channel"] and len(waiting) == 10  # newest first
    ping = con.execute("SELECT * FROM bot_outbox WHERE kind = 'chat_suggested'").fetchall()
    assert len(ping) == 1 and outbox._render(con, {**dict(ping[0]), "lang": "ru"})[2] == "achats"   # one a day
    news = waiting[-1]["id"]
    assert c.post(f"/api/chats/{news}/opened", headers=tma(30)).status_code == 404
    assert c.post(f"/api/admin/chats/{news}/approve", headers=tma(30)).status_code == 403
    assert c.post(f"/api/admin/chats/{news}/approve", headers=tma(31)).json()["title"] == "KBTU News"
    assert [x["title"] for x in c.get("/api/chats", headers=tma(30)).json()["all"]] == ["KBTU News"]
    told = con.execute("SELECT * FROM bot_outbox WHERE kind = 'chat_approved' AND user_id = ?", (ali["id"],)).fetchone()
    assert outbox._render(con, {**dict(told), "lang": "ru"})[2] == "chats"
    assert c.delete(f"/api/admin/chats/{waiting[0]['id']}", headers=tma(31)).status_code == 204   # declined
    assert len(c.get("/api/chats", headers=tma(31)).json()["pending"]) == 8
    assert say(30, text="@kbtu_news") == texts.chat_reply("ru", [("exists", "KBTU News", "channel")])   # live now
    inv = next(x for x in c.get("/api/chats", headers=tma(31)).json()["pending"] if "/+" in x["url"])
    c.post(f"/api/admin/chats/{inv['id']}/approve", headers=tma(31))
    assert inv["url"] in [x["url"] for x in c.get("/api/chats", headers=tma(30)).json()["all"]]       # a student sees the invite
    assert inv["url"] not in [x["url"] for x in c.get("/api/chats", headers=tma(99)).json()["all"]]   # a guest doesn't
    keys = bot_dm._welcome(con, cfg, {"chat": {"id": 30, "type": "private"}, "date": logic.now(), "text": "/start chat"})["reply_markup"]["keyboard"]
    assert [k[0]["request_chat"]["chat_is_channel"] for k in keys] == [True, False] and "chat_has_username" not in keys[0][0]["request_chat"]  # any chat


def test_org_chats(env, monkeypatch):
    """An org's own Telegram chats (PLAN 86): its Vice+ link them in Studio by @name, a t.me link or an invite link; the
    first public channel is the main one; a closed chat shows on the page without its invite link; another org's chat
    is refused, a catalog chat becomes the org's and stays in the catalog with whose it is; the admin links any catalog
    chat; our bot, added by someone who may edit the club, keeps the card, and a suggestion or a catalog delete never
    takes a chat off its club's page."""
    import dataclasses
    from kbtu import media
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({89}))))
    pres, vice, ali, boss = (login(c, 80 + i, n) for i, n in enumerate(("pres", "vice", "ali", "boss")))
    login(c, 89, "admin")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice"), (ali["id"], "member")])
    pages = {"https://t.me/mic_news": {"title": "Open Mic News", "members": 900, "channel": True, "about": "Every Friday"},
             "https://t.me/mic_talk": {"title": "Open Mic Talk", "members": 120, "channel": False},
             "https://t.me/+Secret123": {"title": "Open Mic Team", "members": 14, "channel": False},
             "https://t.me/kbtusite": {"title": "KBTU | SITE", "members": 5000, "channel": True},
             "https://t.me/some_person": {"title": "Someone", "members": None}}
    async def peek(http, url):
        return {"ok": True, "image": None, **pages.get(url, {"title": None, "members": None})}
    monkeypatch.setattr(media, "chat_peek", peek)
    add = lambda uid, link, oid=1: c.post(f"/api/orgs/{oid}/chats", headers=tma(uid), json={"link": link})  # noqa: E731

    assert add(82, "@mic_news").status_code == 403                                     # a member can't
    assert add(81, "@some_person").status_code == 400 and add(81, "hello").status_code == 400
    got = add(81, "https://t.me/mic_news").json()                                       # the Vice can
    assert [(x["title"], x["main"], x["about"], x["bot"]) for x in got] == [("Open Mic News", True, "Every Friday", False)]
    add(80, "@mic_talk"), add(80, "t.me/+Secret123")
    page = c.get("/api/orgs/1", headers=tma(82)).json()["chats"]
    assert [(x["title"], x["kind"], x["closed"], x["url"]) for x in page] == [
        ("Open Mic News", "channel", False, "https://t.me/mic_news"), ("Open Mic Talk", "group", False, "https://t.me/mic_talk"),
        ("Open Mic Team", "group", True, None)]                                         # no way into a closed one from the page
    studio = c.get("/api/orgs/1/chats", headers=tma(80)).json()
    assert studio[2]["url"] == "https://t.me/+Secret123" and c.get("/api/orgs/1/chats", headers=tma(82)).status_code == 403
    assert c.get("/api/chats", headers=tma(82)).json()["all"] == []                     # linked from Studio: not in the catalog
    talk = studio[1]["id"]
    assert c.put(f"/api/orgs/1/chats/{talk}/main", headers=tma(80)).status_code == 400  # a group is no main channel

    # the catalog's chat: SITE's by the admin's hand, and then no club takes it
    site = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/kbtusite", "kind": "channel"}).json()
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(80), json={"orgId": 2}).status_code == 403
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(89), json={"orgId": 2}).json()["org"]["slug"] == "site"
    assert c.get("/api/chats", headers=tma(82)).json()["all"][0]["org"]["id"] == 2      # the catalog says whose
    assert c.get("/api/orgs/2", headers=tma(82)).json()["chats"][0]["main"] is True
    assert add(80, "@kbtusite").status_code == 409

    # a student suggests the club's own chat: that row waits (still the club's); declined, it stays on the page
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "@mic_talk"}).json()["status"] == "sent"
    pending = c.get("/api/chats", headers=tma(89)).json()["pending"]
    assert [x["id"] for x in pending] == [talk]
    assert c.delete(f"/api/admin/chats/{talk}", headers=tma(89)).status_code == 204
    assert talk in [x["id"] for x in c.get("/api/orgs/1", headers=tma(82)).json()["chats"]]

    # our bot: a group added by Studio's link, by someone who may edit the club; a stranger's /start claims nothing
    assert logic.bot_added(con, 99999, {"id": -100500, "type": "supergroup"}, cid=talk) is None
    assert logic.bot_added(con, 82, {"id": -100500, "type": "supergroup"}, cid=talk) is None    # Ali is only a member
    assert logic.bot_added(con, 81, {"id": -100500, "type": "supergroup"}, cid=talk) == talk
    news = studio[0]["id"]
    assert logic.bot_added(con, 80, {"id": -100600, "type": "channel", "username": "Mic_News"}) == news  # a channel by its @name
    assert logic.chat_card(con, news, {"title": "Open Mic", "about": "", "members": 950}) is None
    first = c.get("/api/orgs/1", headers=tma(82)).json()["chats"][0]
    assert (first["title"], first["members"], first["about"]) == ("Open Mic", 950, None)          # Telegram's card; an empty about clears it
    assert [x["bot"] for x in c.get("/api/orgs/1/chats", headers=tma(80)).json()][:2] == [True, True]
    logic.bot_left(con, -100600)
    assert c.get("/api/orgs/1/chats", headers=tma(80)).json()[0]["bot"] is False

    # off the page: the club's own row goes, the catalog's stays in the catalog
    secret = next(x["id"] for x in studio if x["closed"])
    assert [x["title"] for x in c.delete(f"/api/orgs/1/chats/{secret}", headers=tma(81)).json()] == ["Open Mic", "Open Mic Talk"]
    assert not con.execute("SELECT 1 FROM chats WHERE id = ?", (secret,)).fetchone()
    assert c.put(f"/api/admin/chats/{site['id']}/org", headers=tma(89), json={"orgId": None}).json()["org"] is None
    assert c.get("/api/orgs/2", headers=tma(82)).json()["chats"] == [] and len(c.get("/api/chats", headers=tma(82)).json()["all"]) == 1


def _chats_club(env, monkeypatch):
    """A club (Pres 80, Vice 81, member 82), the admin 89, a moderator 88, and t.me pages made up for the chats tests."""
    import dataclasses
    from kbtu import media
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({89}))))
    pres, vice, ali = (login(c, 80 + i, n) for i, n in enumerate(("pres", "vice", "ali")))
    login(c, 89, "admin"), login(c, 88, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 88")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice"), (ali["id"], "member")])
    pages = {"https://t.me/+Secret123": {"title": "Open Mic Team", "members": 14, "channel": False},
             "https://t.me/+Waiting99": {"title": "Some Closed Group", "members": 40, "channel": False},
             "https://t.me/kbtu_talk": {"title": "KBTU Talk", "members": 3000, "channel": False}}
    async def peek(http, url):
        return {"ok": True, "image": None, **pages.get(url, {"title": None, "members": None})}
    monkeypatch.setattr(media, "chat_peek", peek)
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    return c, con


def test_org_closed_chat_stays_off_catalog(env, monkeypatch):
    """Review finding 1: a club's closed chat (an invite link) never reaches the catalog: a student's suggestion and the
    admin's add are refused as "already in the app"; the moderator's list says whose a waiting chat is."""
    c, con = _chats_club(env, monkeypatch)
    secret = c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "https://t.me/+Secret123"}).json()[0]["id"]
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "t.me/+Secret123"}).json()["status"] == "org"
    r = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/+Secret123", "kind": "group"})
    assert r.status_code == 409 and r.json()["message"] == "org"
    assert con.execute("SELECT status FROM chats WHERE id = ?", (secret,)).fetchone()[0] == "org"
    assert c.get("/api/chats", headers=tma(82)).json()["all"] == []
    # a public chat of the club may be suggested: it waits with its owner shown, and comes back owned when approved
    c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "@kbtu_talk"})
    con.execute("DELETE FROM meta WHERE key LIKE 'suggest_at:%'")
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "@kbtu_talk"}).json()["status"] == "sent"
    waiting = c.get("/api/chats", headers=tma(88)).json()["pending"]
    assert [(x["title"], x["org"]["slug"]) for x in waiting] == [("KBTU Talk", "mic")]
    assert c.post(f"/api/admin/chats/{waiting[0]['id']}/approve", headers=tma(88)).json()["org"]["slug"] == "mic"


def test_org_drop_closed_pending_chat(env, monkeypatch):
    """Review finding 2: a closed chat waiting for the catalog and given to the club, when the club removes it, goes:
    never left waiting with nobody's name (its invite link would land in the catalog)."""
    c, con = _chats_club(env, monkeypatch)
    assert c.post("/api/chats/suggest", headers=tma(82), json={"link": "t.me/+Waiting99"}).json()["status"] == "sent"
    cid = c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "t.me/+Waiting99"}).json()[0]["id"]   # the admin gives it to the club
    assert tuple(con.execute("SELECT status, org_id FROM chats WHERE id = ?", (cid,)).fetchone()) == ("pending", 1)
    assert c.delete(f"/api/orgs/1/chats/{cid}", headers=tma(81)).json() == []
    assert con.execute("SELECT 1 FROM chats WHERE id = ?", (cid,)).fetchone() is None
    assert "pending" in c.get("/api/chats", headers=tma(88)).json() and c.get("/api/chats", headers=tma(88)).json()["pending"] == []


def test_org_catalog_chat_is_the_admins_to_give(env, monkeypatch):
    """Review finding 3: a catalog chat nobody owns isn't a Vice's to take (conflict catalog: ask the app's team); the
    admin gives it, and a claimed chat counts toward the club's 12."""
    c, con = _chats_club(env, monkeypatch)
    talk = c.post("/api/admin/chats", headers=tma(89), json={"url": "https://t.me/kbtu_talk", "kind": "group"}).json()["id"]
    r = c.post("/api/orgs/1/chats", headers=tma(81), json={"link": "@kbtu_talk"})
    assert r.status_code == 409 and r.json()["message"] == "catalog"
    assert con.execute("SELECT org_id FROM chats WHERE id = ?", (talk,)).fetchone()[0] is None
    con.executemany("INSERT INTO chats (title, kind, url, created_at, status, org_id) VALUES (?, 'group', ?, 0, 'org', 1)",
                    [(f"Chat {i}", f"https://t.me/chat_{i}") for i in range(12)])
    r = c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "@kbtu_talk"})   # the admin, but the club is full
    assert r.status_code == 409 and r.json()["message"] == "limit"
    con.execute("DELETE FROM chats WHERE url = 'https://t.me/chat_0'")
    assert "KBTU Talk" in [x["title"] for x in c.post("/api/orgs/1/chats", headers=tma(89), json={"link": "@kbtu_talk"}).json()]
    assert tuple(con.execute("SELECT org_id, status FROM chats WHERE id = ?", (talk,)).fetchone()) == (1, "live")  # still in the catalog
    con.execute("UPDATE chats SET kind = 'channel' WHERE url = 'https://t.me/chat_1'")
    assert logic.bot_added(con, 89, {"id": -100700, "type": "channel", "title": "Chat 1"}) is None   # never by a title (Codex, Nov 14)
    assert logic.bot_added(con, 81, {"id": -100700, "type": "channel", "title": "Chat 1"}) is None
