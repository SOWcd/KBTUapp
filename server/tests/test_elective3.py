"""Admin one-offs: a casting from an event, the elective post's Yes/No taps, a DMP leaders meeting."""
from __future__ import annotations

import asyncio
import time

from kbtu import admin, bot, config, db, texts
from test_core import env, login  # noqa: F401  (env: the fixture)


def test_casting_from_event(env, monkeypatch):
    """An event turned into an offline casting: on now, in the strip, its followers not messaged; one at a time."""
    import pytest
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    ann, bob = login(c, 62, "ann"), login(c, 63, "bob")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (91, 'jc', 'club', 'JC', 'JC', 'megaphone_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (91, ?, 'president', 0)", (ann["id"],))
    con.execute("INSERT INTO subscriptions (org_id, user_id, created_at) VALUES (91, ?, 0)", (bob["id"],))
    con.execute("""INSERT INTO events (id, org_id, title, description, place, starts_at, ends_at, status, visibility, created_by, created_at, updated_at, emoji, color)
        VALUES (500, 91, 'Casting!', 'Come', 'Hall 1', 1, 2, 'published', 'public', ?, 0, 0, 'megaphone_3d', '#2F5BEA')""", (ann["id"],))
    until = time.strftime("%Y-%m-%d 23:59", time.gmtime(time.time() + 5 * 3600 + 86400))
    admin.main(["casting", "from-event", "500", until])
    p = con.execute("SELECT * FROM posts WHERE org_id = 91").fetchone()
    assert (p["title"], p["body"], p["casting_place"], p["author_id"], p["audience"]) == ("Casting!", "Come", "Hall 1", ann["id"], "public")
    assert p["casting_from"] <= time.time() < p["casting_to"]
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'casting_open'").fetchone()[0] == 0
    with pytest.raises(SystemExit):
        admin.main(["casting", "from-event", "500", until])


def test_announce_taps(env, monkeypatch):
    """The elective post (Nov 7, sent): its "more like it?" Yes/No (an:) still answer on the messages people have."""
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    ids = {n: login(c, tg, n)["id"] for tg, n in ((30, "ann"), (31, "ben"), (33, "dan"))}
    rows = [[{"text": "post", "url": "https://t.me/KBTUstartup/2016"}], [{"text": "y", "callback_data": "an:y"}, {"text": "n", "callback_data": "an:n"}]]

    edits = []

    async def edit(cfg, http, method, body, files=None):
        edits.append(body)
    monkeypatch.setattr(bot, "_tg", edit)

    class Http:
        async def post(self, *a, **k):
            return None
    tap = lambda who, data: asyncio.run(bot._tapped(cfg, Http(), con, {"id": "q", "from": {"id": who}, "data": data,  # noqa: E731
                                                                    "message": {"message_id": 5, "chat": {"id": 30}, "text": "post",
                                                                                "reply_markup": {"inline_keyboard": rows}}}))
    ok = lambda: {r[0]: r[1] for r in con.execute("SELECT id, announce_ok FROM users")}  # noqa: E731
    tap(30, "an:y")
    tap(30, "an:y")                                                                  # idempotent
    assert ok()[ids["ann"]] == 1 and edits[-1]["text"] == "post\n\n" + texts.bot_message("ru", "announce_yes")[0]
    assert edits[-1]["reply_markup"]["inline_keyboard"] == rows[:1]  # the link stays, the buttons go
    tap(31, "an:n")      # a forged tap on ann's message: only ben's own answer changes
    assert ok()[ids["ann"]] == 1 and ok()[ids["ben"]] == 0
    tap(30, "an:n")
    assert ok()[ids["ann"]] == 0 and ok()[ids["dan"]] is None


def test_meeting_new_and_call(env, monkeypatch):
    """A DMP leaders meeting: club boards alone hear "in an hour", once each, an hour before; an ordinary student never."""
    import pytest
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    boss, ann, bob = login(c, 60, "boss"), login(c, 62, "ann"), login(c, 63, "bob")
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (90, 'dmp', 'office', 'DMP', 'DM', 'megaphone_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (91, 'chess', 'club', 'Chess', 'CH', 'megaphone_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (91, ?, 'head', 0)", (ann["id"],))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (91, ?, 'member', 0)", (bob["id"],))
    at = time.gmtime(time.time() + 5 * 3600 + 86400)
    admin.main(["meeting", "new", "Law and order", time.strftime("%Y-%m-%d 17:00", at), "60", "Independence Hall", "Topics"])
    e = con.execute("SELECT e.id, e.status, e.visibility, e.leaders_from, e.starts_at, o.slug FROM events e JOIN orgs o ON o.id = e.org_id WHERE e.title = 'Law and order'").fetchone()
    assert (e["status"], e["visibility"], e["leaders_from"], e["slug"]) == ("published", "leaders", "head", "dmp")
    q = lambda: con.execute("SELECT user_id, send_after FROM bot_outbox WHERE kind = 'meet_call'").fetchall()  # noqa: E731
    admin.main(["meeting", "call", str(e["id"])])
    assert q() == []
    admin.main(["meeting", "call", str(e["id"]), "--send"]); admin.main(["meeting", "call", str(e["id"]), "--send"])
    assert [tuple(r) for r in q()] == [(ann["id"], e["starts_at"] - 3600)]
    with pytest.raises(SystemExit):
        admin.main(["meeting", "call", "99999", "--send"])
