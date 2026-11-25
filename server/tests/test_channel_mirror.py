"""The events channel and the channel mirror read by the userbot."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time

from kbtu import bot, config, db, logic, media, outbox, app as server, tgc, video
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def test_events_channel(env, monkeypatch):
    """The events channel: a published public event is due once; an edit makes it due again; a cancel
    marks its post; a team-only one never goes."""
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)  # the channel is official clubs'
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], oid, "president", "test")
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    t = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json={**ev, "title": "Team", "visibility": "members"}).json()
    assert logic.channel_due(con) == []                                                         # drafts don't go
    for x in (e, t):
        c.post(f"/api/events/{x['id']}/publish", headers=tma(20))
    (row, text, cover, sig), = logic.channel_due(con)
    assert row["id"] == e["id"] and "Open day" in text and "Atrium" in text
    con.execute("UPDATE events SET channel_msg = 7, channel_sig = ? WHERE id = ?", (sig, e["id"]))
    assert logic.channel_due(con) == []
    c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**ev, "place": "Hall"})
    assert "Hall" in logic.channel_due(con)[0][1]
    assert 'startapp=ev_%d">' % e["id"] in logic.channel_due(con, "KBTUappBot")[0][1]           # sign up: a link, not a button
    con.execute("UPDATE events SET channel_msg = NULL WHERE id = ?", (e["id"],))
    # Telegram's copy of post 7 in the discussion group: the bot comments the rules under it, the app links that comment.
    # The copy comes before post_channel has stored the post's id: the bot waits for it
    real_sleep = asyncio.sleep

    async def sleep(s):
        con.execute("UPDATE events SET channel_msg = 7 WHERE id = ?", (e["id"],))
        await real_sleep(0)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    import httpx
    cfg2 = dataclasses.replace(cfg, events_channel="@KBTUevents")
    copy = {"message_id": 70, "chat": {"id": -100, "type": "supergroup"}, "is_automatic_forward": True,
            "sender_chat": {"id": -200, "type": "channel", "username": "KBTUevents"}, "forward_origin": {"type": "channel", "message_id": 7}}
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1, "message": copy}, {"update_id": 2, "message": copy}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 71}})

    async def go():  # the wait for the post's id runs beside the ears (tgc.spawn), one copy after the other
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            n = await bot.hear(cfg2, http, 0)
            await tgc.settle()
            return n
    asyncio.run(go())
    assert len(sent) == 1 and sent[0]["chat_id"] == -100 and sent[0]["reply_parameters"] == {"message_id": 70}  # once
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["discuss"] == "https://t.me/kbtuevents/7?comment=71"
    con.execute("UPDATE events SET comments_on = 0 WHERE id = ?", (e["id"],))
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["discuss"] is None              # comments off: no talk
    con.execute("UPDATE events SET comments_on = 1 WHERE id = ?", (e["id"],))
    c.post(f"/api/events/{e['id']}/cancel", headers=tma(20))
    assert logic.channel_due(con)[0][1].startswith("❌")
    # deleting the cancelled event deletes its post and the post's copy in the group (it stayed)
    assert c.delete(f"/api/events/{e['id']}", headers=tma(20)).status_code == 204
    assert logic.channel_gone(con) == [(7, "-100 70")]
    sent.clear()

    async def drop():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.post_channel(cfg2, http, con)
    asyncio.run(drop())
    gone = [(x["chat_id"], x["message_id"]) for x in sent if "text" not in x and "caption" not in x]
    assert gone == [("@KBTUevents", 7), ("-100", 70)] and logic.channel_gone(con) == []


def test_channel_refused_post_skipped(env):
    """A post Telegram refuses for itself (a caption too long) is skipped, so the ones after it still go;
    no rights stops the round instead, every post waits."""
    import httpx
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 20").fetchone()[0], oid, "president", "test")
    ev = {"place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
    ids = [c.post(f"/api/orgs/{oid}/events", headers=tma(20), json={**ev, "title": t}).json()["id"] for t in ("Long", "Fine")]
    for i in ids:
        c.post(f"/api/events/{i}/publish", headers=tma(20))
    con.execute("UPDATE events SET published_at = published_at - 60 WHERE id = ?", (ids[0],))  # Long goes first
    cfg2 = dataclasses.replace(cfg, events_channel="@KBTUevents")
    why = {"Long": "Bad Request: message is too long"}

    def telegram(request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content)["text"]
        for k, d in why.items():
            if k in text:
                return httpx.Response(400, json={"ok": False, "error_code": 400, "description": d})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await bot.post_channel(cfg2, http, con)
    why["Fine"] = "Bad Request: not enough rights to send text messages to the chat"
    asyncio.run(go())
    assert len(logic.channel_due(con, cfg.bot_username)) == 1           # no rights: Fine waits, Long was skipped
    del why["Fine"]
    asyncio.run(go())
    assert logic.channel_due(con, cfg.bot_username) == [] and con.execute("SELECT channel_msg FROM events WHERE id = ?", (ids[1],)).fetchone()[0] == 9


def test_channel_mirror(env, tmp_path):
    """PLAN 86 part 2: an org's main public channel in its news (mirror.py, fed by userbot.py with fake messages here):
    a post's first line is its title, its photo copied; an album is one post; an edit follows and reads "edited"; a
    video is a link; Telegram's views and reactions show and ours are refused, and so are edits in the app; a deletion
    takes the post down once all its messages went; nobody is notified. Off in Studio, or another main channel: the
    userbot leaves and the posts already there stay."""
    import io
    from PIL import Image
    from kbtu import media, mirror
    c, cfg = env
    pres, ali = login(c, 80, "pres"), login(c, 81, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO chats (id, title, kind, url, created_at, status, org_id, main) VALUES
        (1, 'Open Mic News', 'channel', 'https://t.me/Mic_News', 0, 'org', 1, 1), (2, 'Open Mic Team', 'channel', 'https://t.me/+Secret1', 0, 'org', 1, 0)""")
    assert mirror.wanted(con) == {"mic_news": 1} and mirror.to_join(con) == ["mic_news"]   # the main public channel only
    assert mirror.take(con, 500, mirror.Msg(id=1, date=1000, text="Not joined")) is None    # a channel we don't mirror: dropped
    mirror.joined(con, 500, "mic_news")
    assert mirror.to_join(con) == [] and mirror.last(con, 500) == 0
    png = io.BytesIO(); Image.new("RGB", (64, 48), "red").save(png, "PNG")
    pic = media.save(png.getvalue(), tmp_path)
    outbox = con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0]

    # The title split and trimming preserve the Telegram offsets, including the title's emoji.
    text = "  \U0001F3A4 Stand-up night on Friday  \n  Sign up by Thursday.\nFree entry."
    url = "https://example.com/signup"
    p1 = mirror.take(con, 500, mirror.Msg(id=10, date=logic.now() - 60, text=text, photo=pic,
                                        entities=[("bold", 5, 8, None), ("bold", 34, 7, None), ("text_link", 45, 8, url),
                                                  ("text_link", 55, 4, "tg://resolve?domain=mic_news")],
                                        views=120, reactions=[("\U0001F525", 7), ("\u2764", 3), ("\u2605", 0)]))
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[p1]
    assert (got["title"], got["body"]) == ("\U0001F3A4 Stand-up night on Friday", "Sign up by Thursday.\nFree entry.")
    assert got["titleFmt"] == [["bold", 3, 8, None]] and got["fmt"] == [["bold", 0, 7, None], ["text_link", 11, 8, url]]
    assert got["photo"] and got["tg"] == {"url": "https://t.me/mic_news/10", "views": 120, "reactions": [["\U0001F525", 7], ["\u2764", 3]], "media": None}
    assert got["commentsOn"] is False and got["canEdit"] is False
    assert c.get("/api/posts?scope=org:1", headers=tma(80)).json()[0]["canEdit"] is False   # not even its President: Telegram's
    assert c.put(f"/api/posts/{p1}/reactions/fire", headers=tma(81)).status_code == 400
    assert c.patch(f"/api/posts/{p1}", headers=tma(80), json={"title": "Changed here"}).status_code == 400
    assert c.patch(f"/api/posts/{p1}", headers=tma(80), json={"pinned": True}).json()["pinned"] is True  # a pin is the club's own
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == outbox                      # nobody notified

    # A formatting-only edit replaces both sets of ranges. Removing every entity clears the field.
    assert mirror.take(con, 500, mirror.Msg(id=10, date=0, text=text, entities=[("italic", 34, 7, None)])) == p1
    got = c.get("/api/posts?scope=org:1", headers=tma(81)).json()[0]
    assert got["fmt"] == [["italic", 0, 7, None]] and "titleFmt" not in got and got["editedAt"]
    assert mirror.take(con, 500, mirror.Msg(id=10, date=0, text="Stand-up night moved to Saturday", views=300, reactions=[("\U0001F525", 9)])) == p1
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[p1]
    assert (got["title"], got["body"], got["tg"]["views"], got["tg"]["reactions"]) == ("Stand-up night moved to Saturday", "", 300, [["\U0001F525", 9]])
    assert got["editedAt"] and got["photo"] and "fmt" not in got

    # an album: three messages, one post; its caption on the second; a video only a link
    a = [mirror.Msg(id=20, date=logic.now(), grouped=77, photo=pic), mirror.Msg(id=21, date=logic.now(), grouped=77, text="Photos from the night"),
         mirror.Msg(id=22, date=logic.now(), grouped=77, media="video")]
    (ap,) = {mirror.take(con, 500, m) for m in a}
    album = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()}[ap]
    assert (album["title"], album["tg"]["url"], album["tg"]["media"], album["editedAt"]) == ("Photos from the night", "https://t.me/mic_news/20", "video", None)
    assert album["photo"]
    assert mirror.needs_photo(con, 500, 23, 77) is False and mirror.needs_photo(con, 500, 30, None) is True
    long = mirror.take(con, 500, mirror.Msg(id=30, date=logic.now(), text="word " * 60))
    lp = con.execute("SELECT title, body FROM posts WHERE id = ?", (long,)).fetchone()
    assert len(lp["title"]) <= 120 and lp["title"].endswith("\u2026") and lp["body"] == ("word " * 60).strip()   # nothing lost
    assert mirror.last(con, 500) == 30 and sorted(mirror.recent(con, 500)) == [10, 20, 21, 22, 30]

    # deletions: an album's post goes when all its messages went
    assert mirror.gone(con, 500, [20, 21]) == [] and mirror.gone(con, 500, [22]) == [album["id"]]
    assert album["id"] not in [x["id"] for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()]
    assert mirror.take(con, 500, mirror.Msg(id=22, date=0, text="back?")) != album["id"]                  # a deleted post isn't revived

    # off in Studio: no more posts, the userbot leaves; the posts stay
    assert c.put("/api/orgs/1/chats/1/mirror", headers=tma(81), json={"on": False}).status_code == 403    # not Ali's club
    studio = c.put("/api/orgs/1/chats/1/mirror", headers=tma(80), json={"on": False}).json()
    assert studio[0]["mirror"] is False and mirror.wanted(con) == {} and mirror.to_leave(con) == [(500, "mic_news")]
    assert mirror.take(con, 500, mirror.Msg(id=40, date=logic.now(), text="Unseen")) is None
    assert p1 in [x["id"] for x in c.get("/api/posts?scope=org:1", headers=tma(81)).json()]
    mirror.left(con, 500)
    # another main channel: that one is joined next
    c.put("/api/orgs/1/chats/1/mirror", headers=tma(80), json={"on": True})
    con.execute("INSERT INTO chats (id, title, kind, url, created_at, status, org_id) VALUES (3, 'Mic Live', 'channel', 'https://t.me/mic_live', 0, 'org', 1)")
    c.put("/api/orgs/1/chats/3/main", headers=tma(80))
    assert mirror.to_join(con) == ["mic_live"]


def test_channel_video_own_player(env, monkeypatch):
    """A mirrored video post plays in the app's own player: the server reads ONLY the post's own t.me embed page (from
    our row, never the client's URL), gives back the CDN file and poster, keeps it a few minutes, limits a user's
    taps; anything else (not a video post, a page without a CDN file, Telegram down) is 404 and the app frames the
    widget. Telegram is mocked."""
    import httpx
    from kbtu import mirror
    c, cfg = env
    login(c, 90, "vid")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    for pid, url, kind in [(1, "https://t.me/mic_news/442", "video"), (2, "https://t.me/mic_news/443", "file"),
                           (3, "https://evil.example/x/1", "video"), (4, "https://t.me/mic_news/444", "video"),
                           (5, "https://t.me/mic_news/445", "video")]:
        con.execute("""INSERT INTO posts (id, org_id, audience, title, body, comments_on, created_at, tg_url, tg_media)
            VALUES (?, 1, 'public', 't', '', 0, 0, ?, ?)""", (pid, url, kind))
    page = ('<div class="tgme_widget_message_video_thumb" style="background-image:url(\'https://cdn4.telesco.pe/file/p.jpg?a=1\')"></div>'
            '<video src="https://cdn1.telesco.pe/file/v.mp4?token=a&amp;b=2" class="tgme_widget_message_video" width="100%">')
    asked = []

    def telegram(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.path == "/mic_news/446":
            con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
        if request.url.path == "/mic_news/444":
            return httpx.Response(200, text='<video src="https://evil.example/file/v.mp4">')  # not Telegram's CDN
        if request.url.path == "/mic_news/445":
            raise httpx.ConnectTimeout("down")
        return httpx.Response(200, text=page)
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))
    monkeypatch.setattr(mirror, "_videos", {})
    monkeypatch.setattr(mirror, "_asks", {})
    H = tma(90, "Vid")
    assert c.get("/api/posts/1/video", headers=H).json() == {"src": "https://cdn1.telesco.pe/file/v.mp4?token=a&b=2",
                                                             "poster": "https://cdn4.telesco.pe/file/p.jpg?a=1"}
    assert c.get("/api/posts/1/video", headers=H).status_code == 200 and asked == ["https://t.me/mic_news/442?embed=1"]  # cached
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert c.get("/api/posts/1/video", headers=H).status_code == 404 and len(asked) == 1
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 1")
    for pid in (2, 3, 99):                                                                  # a file, not t.me, no such post
        assert c.get(f"/api/posts/{pid}/video", headers=H).status_code == 404
    assert c.get("/api/posts/4/video", headers=H).status_code == 404 and len(asked) == 2      # only a CDN file plays
    assert c.get("/api/posts/5/video", headers=H).status_code == 404                          # Telegram down
    assert c.get("/api/posts/1/video").status_code == 403                                     # signed in only
    assert mirror.video_page("https://t.me/mic_news/442/../x") is None and mirror.video_page("https://t.me.evil.io/abcd/1") is None
    assert mirror.parse_video("<p>Telegram changed the page</p>") is None
    monkeypatch.setattr(mirror, "VIDEO_PER_MIN", 3)
    assert c.get("/api/posts/4/video", headers=H).status_code == 429                         # a user's taps, a minute
    monkeypatch.setattr(mirror, "VIDEO_PER_MIN", 20)
    con.execute("UPDATE posts SET tg_url = 'https://t.me/mic_news/446' WHERE id = 1")
    assert c.get("/api/posts/1/video", headers=H).status_code == 404
    assert asked[-1] == "https://t.me/mic_news/446?embed=1"


def test_userbot_reads_telethon_messages(env):
    """userbot.Mirror with Telethon-shaped messages (a fake client): a photo is downloaded once and copied, a video and
    a file are named, Telegram's reactions read (a custom emoji as a star), service messages and anything from a chat
    that isn't mirrored dropped unread (a group's message never reaches the database), a saved photo nobody uses removed."""
    import datetime
    import io
    from PIL import Image
    from types import SimpleNamespace as NS
    from kbtu import mirror, userbot
    c, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic News', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    png = io.BytesIO(); Image.new("RGB", (40, 30), "blue").save(png, "PNG")
    downloads = []

    class Client:
        async def download_media(self, m, kind):
            downloads.append(m.id)
            return png.getvalue()

    def msg(i, chan=500, text="", photo=None, video=None, document=None, grouped=None, reactions=None, action=None):
        return NS(id=i, peer_id=NS(channel_id=chan) if chan else NS(user_id=5), action=action, message=text, grouped_id=grouped,
                  date=datetime.datetime.now(datetime.timezone.utc), photo=photo, video=video, gif=None, video_note=None,
                  media=photo or video or document, web_preview=None, views=42, reactions=reactions)
    work = userbot.Mirror(cfg, Client(), con)
    run = lambda m: asyncio.run(work.guard(work.post(m)))  # noqa: E731
    likes = NS(results=[NS(reaction=NS(emoticon="\U0001F44D"), count=5), NS(reaction=NS(document_id=1), count=2)])
    run(msg(1, text="Open mic tonight", photo=object(), grouped=9, reactions=likes))
    run(msg(2, photo=object(), grouped=9))                    # the album's second photo: the post has one, not downloaded
    run(msg(3, text="Teaser", video=object()))
    run(msg(4, text="Rules", document=object()))
    run(msg(5, text="pinned a message", action=object()))     # a service message
    run(msg(6, chan=777, text="a group's chatter"))           # not a mirrored chat
    run(msg(7, chan=None, text="a private message"))
    got = {r["title"]: r for r in con.execute("SELECT * FROM posts").fetchall()}
    assert sorted(got) == ["Open mic tonight", "Rules", "Teaser"] and downloads == [1]
    assert got["Open mic tonight"]["photo_file_id"] and json.loads(got["Open mic tonight"]["tg_reactions"]) == [["\U0001F44D", 5], ["\u2605", 2]]
    assert (got["Teaser"]["tg_media"], got["Rules"]["tg_media"], got["Teaser"]["tg_views"]) == ("video", "file", 42)
    assert con.execute("SELECT COUNT(*) FROM tg_post_msgs").fetchone()[0] == 4


def test_mirrored_album_caption_removal(env, monkeypatch):
    from types import SimpleNamespace as NS
    from kbtu import mirror, userbot

    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic News', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    messages = {}

    class Client:
        async def get_messages(self, _peer, *, ids):
            return [messages[i] for i in ids]

    work = userbot.Mirror(cfg, Client(), con)

    async def read(_channel, m):
        return m.post

    monkeypatch.setattr(work, "read", read)

    def sync(mid, text, edited=False, entities=None):
        m = NS(id=mid, peer_id=NS(channel_id=500), action=None, edit_date=logic.now() if edited else None,
               message=text, post=mirror.Msg(id=mid, date=logic.now(), text=text, grouped=7, entities=entities or []))
        messages[mid] = m
        asyncio.run(work.post(m))
        return con.execute("SELECT title, body FROM posts").fetchone()

    sync(10, "")
    sync(11, "Meet tonight\nRoom 123", entities=[("bold", 0, 4, None)])
    sync(11, "Meet tonight\nRoom 123", edited=True)  # stripping entities keeps the caption owner
    assert tuple(sync(10, "", edited=True)) == ("Meet tonight", "Room 123")
    assert tuple(sync(11, "", edited=True)) == ("Open Mic News", "")

    sync(11, "Meet tomorrow")
    con.execute("UPDATE posts SET tg_fmt = NULL")  # an unformatted album already in production
    assert tuple(sync(10, "", edited=True)) == ("Meet tomorrow", "")
    con.execute("UPDATE posts SET tg_fmt = NULL")
    assert tuple(sync(11, "", edited=True)) == ("Open Mic News", "")


def test_mirror_languages(env):
    """A school's channel in three languages: the same announcement posted in kk, ru and en within half an
    hour is one post with the other two as its translations (an album whose caption comes after its photos too); two
    posts in one language stay two; a translation's edit and deletion touch only its language. A one-language post takes
    the translations the channel wrote in its comments; only without any, after 2 h, our AI, and the channel's own
    replace it later."""
    from kbtu import mirror
    c, cfg = env
    login(c, 80, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('KBTU | SITE', 'channel', 'https://t.me/kbtusite', 0, 'org', 1, 1)")
    mirror.joined(con, 700, "kbtusite")
    t0 = logic.now() - 5 * 3600
    kk = "\u0414\u04d9\u0440\u0456\u0441 \u0443\u0430\u049b\u044b\u0442\u044b \u04e9\u0437\u0433\u0435\u0440\u0434\u0456\n\u0421\u04d9\u0440\u0441\u0435\u043d\u0431\u0456 \u043a\u04af\u043d\u0456"  # Kazakh (letters Russian lacks)
    ru = "\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u043e\u0441\u044c\n\u0412 \u0441\u0440\u0435\u0434\u0443"
    pid = mirror.take(con, 700, mirror.Msg(id=10, date=t0, text=kk, views=50))
    assert mirror.take(con, 700, mirror.Msg(id=11, date=t0 + 60, text=ru, views=7)) == pid
    assert mirror.take(con, 700, mirror.Msg(id=12, date=t0 + 120, text="Timetable changed\nOn Wednesday",
                                          entities=[("italic", 21, 9, None)])) == pid
    got = {x["id"]: x for x in c.get("/api/posts?scope=org:1", headers=tma(80)).json()}
    assert list(got) == [pid] and got[pid]["title"].startswith("\u0414\u04d9\u0440\u0456\u0441") and got[pid]["tg"]["views"] == 50  # the first message's counts
    assert got[pid]["i18n"] == {"ru": {"title": ru.split("\n")[0], "body": ru.split("\n")[1]},
                               "en": {"title": "Timetable changed", "body": "On Wednesday", "fmt": [["italic", 3, 9, None]]}}
    two = mirror.take(con, 700, mirror.Msg(id=13, date=t0 + 180, text="Another announcement"))    # English again: another post
    late = mirror.take(con, 700, mirror.Msg(id=14, date=t0 + 7200, text=ru))                     # two hours later: another post
    assert len({pid, two, late}) == 3

    # a translation's edit and deletion touch only its language; the post's own edit stays the post's
    mirror.take(con, 700, mirror.Msg(id=12, date=0, text="Timetable changed again\nOn Thursday"))
    p = con.execute("SELECT title, i18n FROM posts WHERE id = ?", (pid,)).fetchone()
    assert p["title"].startswith("\u0414\u04d9\u0440\u0456\u0441") and json.loads(p["i18n"])["en"]["title"] == "Timetable changed again"
    assert mirror.gone(con, 700, [11]) == []
    assert set(json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (pid,)).fetchone()[0])) == {"en"}

    # an album whose caption comes after its photos, in another language than a post a minute before
    first = mirror.take(con, 700, mirror.Msg(id=20, date=t0 + 4000, text=kk + " 2"))
    temp = mirror.take(con, 700, mirror.Msg(id=21, date=t0 + 4020, grouped=5))
    assert temp != first
    assert mirror.take(con, 700, mirror.Msg(id=22, date=t0 + 4020, grouped=5, text="Photos from the day")) == first
    assert con.execute("SELECT 1 FROM posts WHERE id = ?", (temp,)).fetchone() is None
    assert json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (first,)).fetchone()[0])["en"]["title"] == "Photos from the day"

    # a photo on its own, then the same text in kk, ru and en (SITE): one post, all three its languages
    pic = mirror.take(con, 700, mirror.Msg(id=40, date=t0 + 5000, media="video"))
    for i, x in enumerate((kk, ru, "Football, but agentic\nOn Friday")):
        assert mirror.take(con, 700, mirror.Msg(id=41 + i, date=t0 + 5000, text=x)) == pic
    assert set(json.loads(con.execute("SELECT i18n FROM posts WHERE id = ?", (pic,)).fetchone()[0])) == {"kk", "ru", "en"}

    # the channel's own comments: the post `two` (English only) gets kk and ru from them, nothing else
    assert 13 in mirror.to_comment(con, 700) and 10 in mirror.to_comment(con, 700)              # pid still lacks ru
    assert mirror.comments(con, 700, 13, [kk, ru, "Another one in English"]) == 2
    tw = con.execute("SELECT i18n, tr_by FROM posts WHERE id = ?", (two,)).fetchone()
    assert set(json.loads(tw["i18n"])) == {"kk", "ru"} and tw["tr_by"] == "tg" and 13 not in mirror.to_comment(con, 700)

    # our AI only for a post with none of its own, after 2 h; the channel's comments replace it
    assert logic.ai_next(con) == ("post", late, {"title": ru.split("\n")[0], "body": ru.split("\n")[1]})
    fresh = mirror.take(con, 700, mirror.Msg(id=30, date=logic.now() - 600, text="Just now"))
    logic.ai_save(con, "post", late, {"title": ru.split("\n")[0], "body": ru.split("\n")[1]}, "ru",
                  {"kk": {"title": "k", "body": "kb"}, "en": {"title": "e", "body": "eb"}})
    assert con.execute("SELECT tr_by FROM posts WHERE id = ?", (late,)).fetchone()[0] == "ai"
    assert logic.ai_next(con) is None                                                             # the fresh one waits its 2 h
    mirror.comments(con, 700, 14, ["Schedule changed, official"])
    lt = con.execute("SELECT i18n, tr_by FROM posts WHERE id = ?", (late,)).fetchone()
    assert json.loads(lt["i18n"]) == {"en": {"title": "Schedule changed, official", "body": ""}} and lt["tr_by"] == "tg"
    assert fresh


def test_userbot_reads_only_the_channels_comments(env):
    """userbot.Mirror.translations: the replies under a post are read in memory and only those sent as the channel itself
    kept; a student's comment never reaches the database."""
    import datetime
    from types import SimpleNamespace as NS
    from telethon.tl.types import PeerChannel, PeerUser
    from kbtu import mirror, userbot
    c, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'site', 'school', 'SITE', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('KBTU | SITE', 'channel', 'https://t.me/kbtusite', 0, 'org', 1, 1)")
    mirror.joined(con, 700, "kbtusite")
    mirror.take(con, 700, mirror.Msg(id=10, date=logic.now() - 3600, text="Open day on Saturday"))
    ru = "\u0414\u0435\u043d\u044c \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0445 \u0434\u0432\u0435\u0440\u0435\u0439"
    secret = "\u043c\u043e\u0439 \u043d\u043e\u043c\u0435\u0440 +7 700 000 0000"  # a student's comment in Russian

    class Client:
        def iter_messages(self, ent, reply_to=None, limit=None):
            assert reply_to == 10
            async def gen():
                for m in (NS(from_id=PeerUser(5), message=secret), NS(from_id=PeerChannel(700), message=ru), NS(from_id=PeerChannel(999), message="other channel")):
                    yield m
            return gen()
    work = userbot.Mirror(cfg, Client(), con)
    asyncio.run(work.translations(None, 700))
    p = con.execute("SELECT i18n FROM posts").fetchone()
    assert json.loads(p["i18n"]) == {"ru": {"title": ru, "body": ""}}
    dump = "\n".join(con.iterdump())
    assert "+7 700 000 0000" not in dump and "other channel" not in dump
    asyncio.run(work.translations(None, 700))                                                     # asked again within 2 h: no call


def test_userbot_lists_group_members(env, monkeypatch):
    """userbot.Mirror.members (a fake Telethon client): each group it shares with our bot listed once at sign-in, Bot API
    ids (-100<id> a megagroup, -<id> a basic group), a broadcast channel and a group without our bot skipped; a held
    chat's members go to chat_seen with its club, an unheld one's to chat_seen_free; a bot, a deleted account and the
    userbot itself never; whoever left forgotten, but not when the list is capped. The userbot or our bot joining a group
    (Telegram's join message, ChatAction) lists it then."""
    from types import SimpleNamespace as NS
    from telethon.tl.types import Channel, Chat, ChatPhotoEmpty
    from kbtu import userbot
    from kbtu.logic import chatlist
    c, cfg = env
    con = db.connect(cfg.db_path)
    bot = int(cfg.bot_token.split(":")[0])
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, tg_chat_id) VALUES ('Mic', 'group', 'https://t.me/mic', 0, 'org', 1, -1005)")
    con.execute("INSERT INTO chat_seen (chat_id, tg_id, org_id, seen_at) VALUES (-1005, 99, 1, 0)")  # left since
    con.execute("INSERT INTO chat_seen_free (chat_id, tg_id, seen_at) VALUES (-7, 98, 0)")           # left, but the list is capped
    mega = Channel(id=5, title="m", photo=ChatPhotoEmpty(), date=None, megagroup=True)
    news = Channel(id=6, title="n", photo=ChatPhotoEmpty(), date=None, broadcast=True)
    basic = Chat(id=7, title="b", photo=ChatPhotoEmpty(), participants_count=3, date=None, version=1)
    lone = Chat(id=8, title="l", photo=ChatPhotoEmpty(), participants_count=2, date=None, version=1)  # no bot of ours
    u = lambda i, b=False, d=False: NS(id=i, bot=b, deleted=d)  # noqa: E731

    class Total(list):
        total = 0

    def got(items, total=None):
        out = Total(items); out.total = len(items) if total is None else total
        return out
    people = {5: got([u(11), u(12), u(bot, b=True), u(13, d=True), u(500)]), 7: got([u(21), u(bot, b=True)], total=40), 8: got([u(31)])}
    asked = []

    class Client:
        async def iter_dialogs(self):
            for e in (mega, news, basic, lone):
                yield NS(entity=e)

        async def get_participants(self, ent, filter=None, limit=None):
            asked.append(ent.id)
            return got([x for x in people[ent.id] if x.bot]) if filter else people[ent.id]

    work = userbot.Mirror(cfg, Client(), con, me=500)

    monkeypatch.setattr(userbot, "GROUP_GAP", 0)
    asyncio.run(work.catch_up())
    assert sorted(r[0] for r in logic.rows(con, "SELECT tg_id FROM chat_seen WHERE chat_id = -1005 AND org_id = 1")) == [11, 12]
    assert sorted(r[0] for r in logic.rows(con, "SELECT tg_id FROM chat_seen_free WHERE chat_id = -7")) == [21, 98]
    assert not logic.rows(con, "SELECT 1 FROM chat_seen_free WHERE chat_id IN (-8, -1006)")
    assert chatlist.listed(con) == {-1005, -7} and 6 not in asked
    asked.clear()
    asyncio.run(work.catch_up())  # a new sign-in: nothing listed twice
    assert asked == [8]           # (the group without our bot is looked at again: nothing kept)
    asked.clear()

    async def chat(e):
        return e
    action = lambda e, ids, joined=True: NS(user_joined=joined, user_added=False, user_ids=ids, get_chat=lambda: chat(e))  # noqa: E731
    asyncio.run(work.met(action(basic, [77])))               # someone else joined: nothing asked
    asyncio.run(work.met(action(basic, [bot], joined=False)))  # not a join (our bot promoted, say): nothing
    asyncio.run(work.met(action(news, [500])))               # a broadcast channel: nothing
    assert asked == []
    people[7] = got([u(22), u(bot, b=True)])  # our bot re-added: the group listed again, whole now
    asyncio.run(work.met(action(basic, [bot])))
    assert sorted(r[0] for r in logic.rows(con, "SELECT tg_id FROM chat_seen_free WHERE chat_id = -7")) == [22]


def test_userbot_off(env, caplog):
    """The userbot stays off, saying why in one line, while any of its three settings is missing (nothing else changes)."""
    import dataclasses
    import logging
    from kbtu import userbot
    c, cfg = env
    assert userbot.missing(cfg) == "no TG_API_ID / TG_API_HASH / TG_SESSION"
    assert userbot.missing(dataclasses.replace(cfg, tg_api_id="12", tg_api_hash="h")) == "no TG_API_ID / TG_API_HASH / TG_SESSION"
    assert userbot.missing(dataclasses.replace(cfg, tg_api_id="x", tg_api_hash="h", tg_session="s")) == "TG_API_ID is not a number"
    assert "tg_session" not in repr(dataclasses.replace(cfg, tg_session="secret")) and "secret" not in repr(dataclasses.replace(cfg, tg_session="secret"))
    with caplog.at_level(logging.WARNING, logger="kbtu.userbot"):
        asyncio.run(userbot.run(cfg))
    assert [r.getMessage() for r in caplog.records] == ["userbot: off (no TG_API_ID / TG_API_HASH / TG_SESSION)"]


def test_userbot_heartbeat_alert(env, monkeypatch):
    """The userbot's heartbeat (meta userbot_ok, each sweep): quiet for over two hours, the owner alone hears it once per
    outage, across rounds and restarts, and once when it's back; with no heartbeat at all (qa, tests) nothing is said."""
    from kbtu import mirror
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO users (tg_id, role, is_founder, created_at, seen_at) VALUES (9001, 'admin', 1, 0, 0)")
    con.execute("INSERT INTO users (tg_id, role, created_at, seen_at) VALUES (9002, 'admin', 0, 0)")      # another admin: not told
    rows_of = lambda kind: [tuple(r) for r in con.execute(  # noqa: E731
        "SELECT u.tg_id, b.ref FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = ?", (kind,))]
    clock = [10**9]
    for mod in (bot, mirror):
        monkeypatch.setattr(mod, "now", lambda: clock[0])
    set_clock(monkeypatch, lambda: clock[0])
    for _ in range(3):
        bot.userbot_round(con)                                          # no heartbeat key: silent
    assert not rows_of("userbot_off")
    mirror.alive(con)
    clock[0] += bot.USERBOT_QUIET - 60
    bot.userbot_round(con)                                              # quiet, but not long enough
    assert not rows_of("userbot_off")
    clock[0] += 120
    bot.userbot_round(con)
    clock[0] += 3600
    bot.userbot_round(con)                                              # still down: no second alert
    assert rows_of("userbot_off") == [(9001, f"uo:{10**9}")]
    m = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'userbot_off'").fetchone()
    text, button, start = outbox._render(con, m)
    assert "userbot" in text and button is None and start == ""
    mirror.alive(con)                                                   # back
    bot.userbot_round(con)
    bot.userbot_round(con)
    assert len(rows_of("userbot_ok")) == 1 and not con.execute("SELECT 1 FROM meta WHERE key = 'userbot_alert'").fetchone()
    clock[0] += bot.USERBOT_QUIET + 1                                   # a new outage: told again, once
    bot.userbot_round(con)
    bot.userbot_round(con)
    assert len(rows_of("userbot_off")) == 2


def test_mirror_gone_wipes_the_post(env, tmp_path):
    """A channel post deleted: its post here is taken down with its text emptied and its copied photo deleted, the row
    and the files on disk; a picture another post still shows stays."""
    import io
    from PIL import Image
    from kbtu import mirror
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic News', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    pics = []
    for color in ("red", "green"):
        png = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(png, "PNG")
        pics.append(media.save(png.getvalue(), tmp_path))
    a = mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text="Open mic tonight\nAt 7", photo=pics[0]))
    b = mirror.take(con, 500, mirror.Msg(id=2, date=logic.now(), text="Same poster", photo=pics[1]))
    c2 = mirror.take(con, 500, mirror.Msg(id=3, date=logic.now(), text="Poster again", photo=pics[1]))  # the same picture: one file
    on_disk = lambda p: (tmp_path / f"{p['path']}.webp").exists()  # noqa: E731
    assert on_disk(pics[0]) and on_disk(pics[1])
    assert sorted(mirror.gone(con, 500, [1, 2], tmp_path)) == sorted([a, b])
    gone = con.execute("SELECT title, body, i18n, photo_file_id, hidden_at FROM posts WHERE id = ?", (a,)).fetchone()
    assert (gone["title"], gone["body"], gone["i18n"], gone["photo_file_id"]) == ("", "", None, None) and gone["hidden_at"]
    assert not on_disk(pics[0]) and not con.execute("SELECT 1 FROM files WHERE path = ?", (pics[0]["path"],)).fetchone()
    assert on_disk(pics[1]) and con.execute("SELECT photo_file_id FROM posts WHERE id = ?", (c2,)).fetchone()[0]   # still shown
    mirror.gone(con, 500, [3], tmp_path)
    assert not on_disk(pics[1]) and not con.execute("SELECT 1 FROM files WHERE kind = 'post_photo'").fetchone()


def test_channel_ask(env, monkeypatch, capsys):
    """admin channel-ask: the active clubs with no public main channel; their President is asked by the bot (only with
    --send, only one who gets DMs, once per club, also one leading two clubs); clubs without a President are named; the
    ask is dropped once the club has its channel. Studio's tile: the main channel to Vice+, from /api/me."""
    from kbtu import admin
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    pres, mute, head = login(c, 80, "pres"), login(c, 81, "mute"), login(c, 82, "head")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET can_dm = 1 WHERE id IN (?, ?)", (pres["id"], head["id"]))
    for i, (slug, kind, name, status) in enumerate([("ch", "club", "Has Channel", "active"), ("a", "club", "Alpha", "active"),
                                                    ("b", "club", "Beta", "active"), ("p", "club", "Private Only", "active"),
                                                    ("x", "club", "Nobody", "active"), ("h", "club", "Hidden", "hidden"),
                                                    ("s", "school", "School", "active")], 1):
        con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, status, created_at) VALUES (?, ?, ?, ?, 'X', 'laptop_3d', ?, 0)",
                    (i, slug, kind, name, status))
    for oid, uid in ((1, pres["id"]), (2, pres["id"]), (3, pres["id"]), (4, mute["id"]), (6, pres["id"]), (7, pres["id"])):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", (oid, uid))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'head', 0)", (head["id"],))
    con.execute("""INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES
        ('Has', 'channel', 'https://t.me/has_ch', 0, 'org', 1, 1), ('Secret', 'channel', 'https://t.me/+Secret1', 0, 'org', 4, 1)""")
    asks = lambda: sorted(r[0] for r in con.execute("SELECT ref FROM bot_outbox WHERE kind = 'channel_ask'"))  # noqa: E731
    capsys.readouterr()
    admin.main(["channel-ask"])
    out = capsys.readouterr().out
    assert asks() == [] and "nothing sent" in out
    assert "to ask 2" in out and "President can't get DMs 1" in out and "no President 1" in out and "Nobody" in out
    assert "Has Channel" not in out and "Hidden" not in out and "School" not in out and "24B" not in out
    admin.main(["channel-ask", "--send"])
    admin.main(["channel-ask", "--send"])                               # a second run: nobody asked twice
    assert asks() == ["ca:2", "ca:3"]
    assert "asked before 2" in capsys.readouterr().out
    m = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE ref = 'ca:2'").fetchone()
    text, button, start = outbox._render(con, m)
    assert "Alpha" in text and button and start == "ce_2"
    tiles = {x["org"]["id"]: x for x in c.get("/api/me", headers=tma(80)).json()["memberships"]}
    assert tiles[1]["channel"] == {"title": "Has", "mirror": True} and tiles[2]["channel"] is None
    assert "channel" not in c.get("/api/me", headers=tma(82)).json()["memberships"][0]   # a Head doesn't link chats
    assert c.get("/api/me", headers=tma(81)).json()["memberships"][0]["channel"] == {"title": "Secret", "mirror": False}
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Alpha', 'channel', 'https://t.me/alpha_ch', 0, 'org', 2, 1)")
    assert outbox._render(con, m) is None                                  # linked meanwhile: not sent


def test_deleted_posts_are_wiped(env, monkeypatch, tmp_path):
    """A club deleting its own post wipes it at once (text, translations, photo from disk, the comments under it);
    another club's Head can't; a moderator who heads the club wipes as the club; a moderator's delete only hides it,
    restorable, until the nightly round wipes it 30 days later (a comment or translation that came meanwhile too); a
    wiped post can't be restored or edited back; an edit in Telegram doesn't bring a deleted channel post back; a photo
    another post still shows stays."""
    import io
    from PIL import Image
    from kbtu import mirror
    c, cfg = env
    head, mod, rival = login(c, 51, "head"), login(c, 52, "mod"), login(c, 53, "rival")
    H, Mo, R = tma(51, "Head"), tma(52, "Mod"), tma(53, "Rival")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'art', 'club', 'Art Club', 'AR', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'head', 0), (2, ?, 'head', 0)", (head["id"], rival["id"]))
    disk = tmp_path / "media"   # the route's photos: next to the database
    disk.mkdir(exist_ok=True)
    for i, name in enumerate(("pa", "pb", "pc"), 1):
        (disk / f"{name}.webp").write_bytes(b"x")
        con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, owner_id, created_at) VALUES (?, ?, 'event_cover', 'image/webp', 1, ?, ?, 0)",
                    (i, name, name, head["id"]))
    own, shared, other, modded, headed = (c.post("/api/orgs/1/posts", headers=H, json={"title": t, "photoId": f}).json()["id"]
                                          for t, f in (("Own", 1), ("Shared", 2), ("Other", 2), ("Modded", 3), ("Headed", None)))
    con.execute("INSERT INTO comments (post_id, user_id, body, created_at) VALUES (?, ?, 'hi', 0)", (own, mod["id"]))
    wiped = lambda pid: tuple(con.execute("SELECT title, body, i18n, photo_file_id FROM posts WHERE id = ?", (pid,)).fetchone()) == ("", "", None, None) \
        and not con.execute("SELECT 1 FROM comments WHERE post_id = ?", (pid,)).fetchone()  # noqa: E731
    restore = lambda pid: c.post(f"/api/admin/taken-down/post/{pid}/restore", headers=Mo).status_code  # noqa: E731

    # another club's Head: refused; the club's delete: wiped at once, its photo off the disk; a photo another post shows stays
    assert c.delete(f"/api/posts/{own}", headers=R).status_code == 403
    assert c.delete(f"/api/posts/{own}", headers=H).status_code == 204
    assert wiped(own) and not con.execute("SELECT 1 FROM files WHERE id = 1").fetchone() and not (disk / "pa.webp").exists()
    assert c.delete(f"/api/posts/{shared}", headers=H).status_code == 204
    assert wiped(shared) and con.execute("SELECT photo_file_id FROM posts WHERE id = ?", (other,)).fetchone()[0] == 2 and (disk / "pb.webp").exists()
    assert restore(own) == 404                                                  # nothing left to bring back
    assert c.patch(f"/api/posts/{own}", headers=H, json={"title": "Back again"}).status_code == 404 and wiped(own)   # nor edited back

    # a moderator's delete: only hidden, restorable
    assert c.delete(f"/api/posts/{modded}", headers=Mo).status_code == 204
    assert tuple(con.execute("SELECT title, hidden_at IS NOT NULL FROM posts WHERE id = ?", (modded,)).fetchone()) == ("Modded", 1)
    assert restore(modded) == 204
    assert c.delete(f"/api/posts/{modded}", headers=Mo).status_code == 204
    # what raced the hide (a comment, a translation) is swept by the nightly round too, not before 30 days
    con.execute("INSERT INTO comments (post_id, user_id, body, created_at) VALUES (?, ?, 'late', 0)", (modded, mod["id"]))
    con.execute("""UPDATE posts SET i18n = '{"ru": {"title": "T", "body": ""}}', tr_by = 'tg' WHERE id = ?""", (modded,))
    assert logic.wipe_hidden_posts(con) == [] and not wiped(modded)
    con.execute("UPDATE posts SET title = '' WHERE id = ?", (modded,))   # even with its title already gone
    real = logic.now
    set_clock(monkeypatch, lambda: real() + 31 * 86400)
    bot.purge(cfg, con)
    assert wiped(modded) and not (disk / "pc.webp").exists()
    set_clock(monkeypatch, real)

    # a moderator who heads the club deletes as the club: wiped at once
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'head', 0)", (mod["id"],))
    assert c.delete(f"/api/posts/{headed}", headers=Mo).status_code == 204 and wiped(headed)

    # a channel post deleted in the app by its club: a later edit in Telegram neither revives it nor makes a new post
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('IT News', 'channel', 'https://t.me/it_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "it_news")
    png = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(png, "PNG")
    pic = media.save(png.getvalue(), tmp_path)
    tg = mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text="Meetup\nAt 7", photo=pic))
    assert c.delete(f"/api/posts/{tg}", headers=H).status_code == 204 and wiped(tg)
    n = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    assert mirror.needs_photo(con, 500, 1, None) is False
    assert mirror.take(con, 500, mirror.Msg(id=1, date=0, text="Meetup moved\nAt 8", photo=pic, views=9)) == tg
    assert mirror.comments(con, 500, 1, ["\u0412\u0441\u0442\u0440\u0435\u0447\u0430 \u0432 \u0441\u0435\u043c\u044c"]) == 0   # the channel's translation neither
    assert wiped(tg) and con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == n
