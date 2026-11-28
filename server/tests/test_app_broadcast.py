"""The creator's app-wide announcements go through the regular bot outbox."""
import asyncio
import json

import httpx
import pytest

from kbtu import admin, bot_dm, db, outbox, texts
from test_core import env  # noqa: F401  (env: the fixture)

NAME = "app_home"
URL = "https://t.me/example_channel/42"


@pytest.fixture
def audience(env, monkeypatch):
    _, cfg = env
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    try:
        con.execute("""INSERT INTO users (tg_id, tg_username, lang, can_dm, role, is_founder, banned_at, created_at, seen_at) VALUES
            (10, 'reader', 'en', 1, 'admin', 1, NULL, 0, 0),
            (11, NULL, 'kk', 1, 'user', 0, NULL, 0, 0),
            (12, NULL, 'ru', 1, 'user', 0, NULL, 0, 0),
            (13, 'unreachable', 'ru', 0, 'user', 0, NULL, 0, 0),
            (14, 'banned', 'ru', 1, 'user', 0, 1, 0, 0)""")
        yield con, cfg
    finally:
        con.close()


def test_broadcast_dry_preview_and_delivery(audience, capsys, monkeypatch):
    con, cfg = audience
    cmd = ["broadcast", NAME, URL]
    messages = []
    monkeypatch.setattr(outbox, "_chores", lambda *_: None)
    monkeypatch.setattr(outbox, "GAP", 0)

    def telegram(request):
        assert request.url.path.endswith("/sendMessage")
        messages.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    async def send():
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            await outbox.send_due(cfg, http)

    admin.main([*cmd, "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 3"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 0
    admin.main([*cmd, "@unreachable"])
    assert capsys.readouterr().out.strip() == "queued 0"
    admin.main([*cmd, "@Reader"])
    assert capsys.readouterr().out.strip() == "queued 1"
    asyncio.run(send())
    assert [m["chat_id"] for m in messages] == [10]

    admin.main([*cmd, "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 2"
    admin.main([*cmd, "10"])  # a preview goes again (the owner checks a changed text)
    assert capsys.readouterr().out.strip() == "queued 1"
    asyncio.run(send())
    assert [m["chat_id"] for m in messages] == [10, 10]
    admin.main(cmd)
    assert capsys.readouterr().out.strip() == "queued 2"
    admin.main(cmd)
    assert capsys.readouterr().out.strip() == "queued 0"
    asyncio.run(send())

    assert [m["chat_id"] for m in messages] == [10, 10, 11, 12]
    for message, lang, button in zip(messages[1:], ("en", "kk", "ru"), ("\U0001f3ac Watch", "\U0001f3ac \u041a\u04e9\u0440\u0443", "\U0001f3ac \u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c")):
        assert message["text"] == texts.bot_message(lang, NAME)[0]
        votes = [{"text": texts.bot_message(lang, f"vote_{v}")[0], "callback_data": f"bv:{v}:{NAME}"} for v in (1, 0)]
        assert message["reply_markup"] == {"inline_keyboard": [[{"text": button, "url": URL}], votes]}
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE sent_at IS NOT NULL").fetchone()[0] == 3


@pytest.mark.parametrize("url", [
    "http://t.me/channel/42", "https://example.org/channel/42", "https://t.me.example.org/channel/42",
    "https://t.me@example.org/channel/42", "https://example.org@t.me/channel/42", "https://t.me/line\nbreak",
])
def test_broadcast_rejects_other_urls(audience, url):
    con, _ = audience
    with pytest.raises(SystemExit, match=r"expected an https://t\.me/ URL"):
        admin.main(["broadcast", NAME, url])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 0


def test_broadcast_refuses_unsafe_requests(audience):
    con, _ = audience
    for name in ("unknown_template", "santa_news", "all_none"):
        with pytest.raises(SystemExit, match="expected a translated bot template"):
            admin.main(["broadcast", name, URL])
    con.execute("UPDATE users SET tg_username = 'READER' WHERE tg_id = 13")
    with pytest.raises(SystemExit, match="no unique preview recipient"):
        admin.main(["broadcast", NAME, URL, "@reader"])
    con.execute("UPDATE users SET is_founder = 0")
    with pytest.raises(SystemExit, match="needs the active creator admin"):
        admin.main(["broadcast", NAME, URL])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 0


def test_broadcast_to_one_platform(audience, capsys):
    """--platform android: only people seen on Android (user_platforms), the usual rules too; a preview goes regardless,
    and a later broadcast of the same name to another platform skips whoever already got it."""
    con, _ = audience
    con.execute("INSERT INTO user_platforms (user_id, kind, seen_at) SELECT id, 'android', 0 FROM users WHERE tg_id IN (11, 13, 14)")
    con.execute("INSERT INTO user_platforms (user_id, kind, seen_at) SELECT id, 'ios', 0 FROM users WHERE tg_id IN (11, 12)")
    android = ["broadcast", NAME, URL, "--platform", "android"]
    admin.main([*android, "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 1"        # 11; 13 can't be written to, 14 is banned
    admin.main([*android, "@reader"])                                 # the creator has no row: a preview still goes
    assert capsys.readouterr().out.strip() == "queued 1"
    admin.main(android)
    assert capsys.readouterr().out.strip() == "queued 1"
    admin.main(["broadcast", NAME, URL, "--platform", "ios"])
    assert capsys.readouterr().out.strip() == "queued 1"             # 12; 11 already has it
    assert [r[0] for r in con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id ORDER BY u.tg_id")] == [10, 11, 12]
    assert {json.loads(r[0]).get("p") for r in con.execute("SELECT payload FROM bot_outbox")} == {1}  # marked for the 90-day sweep
    for bad in (["--platform", "linux"], ["--platform"], ["--platform", "--dry"], ["--platform", "ios", "--platform", "web"]):
        with pytest.raises(SystemExit):
            admin.main(["broadcast", NAME, URL, *bad])
    with pytest.raises(SystemExit):
        admin.main(["broadcast", "--platform", "ios", NAME, URL])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 3


def test_broadcast_android(audience, capsys):
    """broadcast-android: people seen on Android who never opened the installed app, the button to android.html in
    each one's language; a preview goes regardless."""
    con, _ = audience
    con.execute("INSERT INTO users (tg_id, lang, can_dm, role, is_founder, created_at, seen_at) VALUES (15, 'en', 1, 'user', 0, 0, 0)")
    con.execute("INSERT INTO user_platforms (user_id, kind, seen_at) SELECT id, 'android', 0 FROM users WHERE tg_id IN (11, 12, 15)")
    con.execute("INSERT INTO android_app (user_id, seen_at) SELECT id, 0 FROM users WHERE tg_id = 12")  # already has the app
    cmd = ["broadcast-android", "android_test"]
    admin.main([*cmd, "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 2"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 0
    admin.main([*cmd, "@reader"])
    assert capsys.readouterr().out.strip() == "queued 1"
    admin.main(cmd)
    assert capsys.readouterr().out.strip() == "queued 2"
    urls = {r[0]: json.loads(r[1])["url"] for r in con.execute("SELECT u.tg_id, b.payload FROM bot_outbox b JOIN users u ON u.id = b.user_id")}
    assert urls == {10: "https://kbtu.sow.kz/android.html?lang=en", 11: "https://kbtu.sow.kz/android.html?lang=kk",
                    15: "https://kbtu.sow.kz/android.html?lang=en"}
    with pytest.raises(SystemExit):
        admin.main(["broadcast-android", "no_such_template"])


def test_a_failed_preview_can_go_again(audience, capsys):
    con, _ = audience
    admin.main(["broadcast", NAME, URL, "@reader"])
    con.execute("UPDATE bot_outbox SET error = 'gone'")
    admin.main(["broadcast", NAME, URL, "@reader"])
    assert capsys.readouterr().out.split() == ["queued", "1", "queued", "1"]


def test_broadcast_votes(audience, capsys):
    """Interesting / Not interesting under a broadcast: one vote per person, changeable, the link row stays."""
    con, cfg = audience
    calls = []

    class Http:
        async def post(self, url, json):
            calls.append((url.rsplit("/", 1)[1], json))
    kb = [[{"text": "x", "url": URL}], [{"text": "y", "callback_data": "bv:1:" + NAME}]]
    tap = lambda tg, v: asyncio.run(bot_dm._tapped(cfg, Http(), con, {"id": "q", "from": {"id": tg}, "data": f"bv:{v}:{NAME}",  # noqa: E731
                                                                    "message": {"message_id": 5, "chat": {"id": tg}, "reply_markup": {"inline_keyboard": kb}}}))
    tap(11, 1)
    tap(12, 0)
    tap(12, 1)                                                     # changed their mind
    tap(999, 0)                                                    # not in the app: nothing kept
    assert sorted(r[0] for r in con.execute("SELECT vote FROM broadcast_votes WHERE name = ?", (NAME,))) == [1, 1]
    tap(11, 0)                                                     # "don't send these": broadcasts off for them
    assert con.execute("SELECT n_broadcasts FROM users WHERE tg_id = 11").fetchone()[0] == 0
    admin.main(["broadcast", NAME, URL, "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 2"        # the admin and 12; 11 turned them off
    assert ("editMessageReplyMarkup", {"chat_id": 11, "message_id": 5, "reply_markup": {"inline_keyboard": kb[:1]}}) in calls
