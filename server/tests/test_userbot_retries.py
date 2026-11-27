"""Failed mirror reads survive cursor advances; quiet channels and refused leaves keep moving."""
import asyncio
import datetime
import io
from types import SimpleNamespace as NS

import pytest
from PIL import Image
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import PeerChannel

from kbtu import db, logic, mirror, userbot
from helpers import env  # noqa: F401


def message(mid, *, photo=False, days=0, topic=None):
    return NS(id=mid, peer_id=PeerChannel(500), action=None, message=f"Club update {mid}", grouped_id=None,
              date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days),
              photo=photo, video=None, gif=None, video_note=None, media=photo or None, web_preview=None,
              views=1, reactions=None, from_id=PeerChannel(500),
              reply_to=NS(forum_topic=True, reply_to_msg_id=topic, reply_to_top_id=None) if topic else None)


class Client:
    def __init__(self):
        self.messages, self.errors, self.handlers = {}, {}, []
        self.downloads, self.fetched, self.history = [], [], []
        png = io.BytesIO()
        Image.new("RGB", (40, 30), "blue").save(png, "PNG")
        self.photo = png.getvalue()

    def add_event_handler(self, handler, _event):
        self.handlers.append(handler)

    async def get_input_entity(self, peer):
        return peer

    async def iter_messages(self, _ent, **kw):
        self.history.append(kw)
        ids = sorted((mid for mid in self.messages if mid > kw.get("min_id", 0)), reverse=not kw.get("reverse", False))
        for mid in ids[:kw["limit"]]:
            yield self.messages[mid]

    async def get_messages(self, _ent, *, ids):
        self.fetched.extend(ids)
        return [self.messages.get(mid) for mid in ids]

    async def download_media(self, m, _kind):
        self.downloads.append(m.id)
        if m.id in self.errors:
            raise self.errors[m.id]
        return self.photo


@pytest.fixture
def work(env, monkeypatch):
    _, cfg = env
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic News', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    result = userbot.Mirror(cfg, Client(), con)
    result.listen()

    async def nothing(*_):
        pass

    monkeypatch.setattr(logic.autoev, "worth", lambda _: False)
    monkeypatch.setattr(result, "list_topics", nothing)
    monkeypatch.setattr(result, "translations", nothing)
    yield result
    con.close()


def sweep(work, monkeypatch):
    delays = []

    async def sleep(seconds):
        if seconds == userbot.SWEEP_GAP:
            raise asyncio.CancelledError
        delays.append(seconds)

    with monkeypatch.context() as patch:
        patch.setattr(userbot.asyncio, "sleep", sleep)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(work.sweeps())
    return delays


def pick_topic(work, topic):
    work.con.execute("UPDATE chats SET kind = 'group', tg_chat_id = -100500, news_topic = ?", (topic,))
    work.con.execute("UPDATE tg_channels SET username = '#500'")


@pytest.mark.parametrize("entry", ["new", "edit", "first", "sweep"])
@pytest.mark.parametrize("topic", [None, 5])
@pytest.mark.parametrize("flood", [False, True])
def test_failed_post_is_refetched_after_later_posts(work, monkeypatch, entry, topic, flood):
    if topic:
        pick_topic(work, topic)
    client = work.client
    client.messages[11] = message(11, photo=True, topic=topic)
    client.errors[11] = FloodWaitError(None, capture=61) if flood else OSError("download interrupted")
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(userbot.asyncio, "sleep", sleep)
    if entry == "sweep":
        mirror.seen(work.con, 500, 10)
        sleeps = sweep(work, monkeypatch)
        assert client.fetched == []
    elif entry == "first":
        asyncio.run(work.first(PeerChannel(500), topic, 500))
    else:
        asyncio.run(client.handlers[entry == "edit"](NS(message=client.messages[11])))
    assert mirror.last(work.con, 500) == (10 if entry == "sweep" else 0)
    assert work.retry == {(500, 11)}
    assert not work.con.execute("SELECT 1 FROM tg_post_msgs").fetchone()
    assert sleeps.count(66) == int(flood)

    client.messages[12] = message(12, topic=topic)
    asyncio.run(client.handlers[0](NS(message=client.messages[12])))
    sleeps = sweep(work, monkeypatch)  # still failing, even after another post passed it
    assert sleeps.count(66) == int(flood)
    assert mirror.last(work.con, 500) == 12 and work.retry == {(500, 11)}
    client.errors.clear()
    sweep(work, monkeypatch)
    assert 11 in client.fetched and client.downloads.count(11) >= 2
    assert work.retry == set() and mirror.last(work.con, 500) == 12
    assert [r[0] for r in work.con.execute("SELECT msg_id FROM tg_post_msgs ORDER BY msg_id")] == [11, 12]
    assert work.con.execute("SELECT count(*) FROM posts").fetchone()[0] == 2


def test_live_message_in_another_topic_keeps_the_first_read_pending(work, monkeypatch):
    pick_topic(work, 5)
    work.client.messages[11] = message(11, topic=5)
    asyncio.run(work.client.handlers[0](NS(message=message(12, topic=6))))
    assert mirror.last(work.con, 500) == 0
    sweep(work, monkeypatch)
    assert [r[0] for r in work.con.execute("SELECT msg_id FROM tg_post_msgs")] == [11]


def test_retry_ahead_of_a_history_page_keeps_the_rest_of_the_page_pending(work, monkeypatch):
    client = work.client
    mirror.seen(work.con, 500, 10)
    client.messages = {i: message(i) for i in range(11, 72)}
    client.messages[71] = message(71, photo=True)
    client.errors[71] = OSError("download interrupted")
    asyncio.run(client.handlers[0](NS(message=client.messages[71])))
    client.errors.clear()

    sweep(work, monkeypatch)
    assert work.retry == set() and mirror.last(work.con, 500) == 60
    assert work.con.execute("SELECT 1 FROM tg_post_msgs WHERE msg_id = 71").fetchone()
    sweep(work, monkeypatch)
    assert mirror.last(work.con, 500) == 71
    assert [r[0] for r in work.con.execute("SELECT msg_id FROM tg_post_msgs ORDER BY msg_id")] == list(range(11, 72))


def test_deleted_failed_post_stops_retrying(work, monkeypatch):
    client = work.client
    client.errors[11] = OSError("download interrupted")
    assert asyncio.run(work.take(message(11, photo=True))) is False
    sweep(work, monkeypatch)  # Telegram no longer has it
    assert work.retry == set() and client.fetched == [11]
    sweep(work, monkeypatch)
    assert client.fetched == [11] and not work.con.execute("SELECT 1 FROM posts").fetchone()


@pytest.mark.parametrize("start", ["first", "zero", "downtime"])
def test_quiet_channel_catches_up_past_old_history(work, monkeypatch, start):
    work.client.messages = {i: message(i, days=40) for i in range(1, 81)}
    if start == "first":
        asyncio.run(work.first(PeerChannel(500)))
    elif start == "downtime":
        mirror.seen(work.con, 500, 10)
        sweep(work, monkeypatch)
        assert mirror.last(work.con, 500) == 60
        sweep(work, monkeypatch)
    else:
        sweep(work, monkeypatch)
    assert mirror.last(work.con, 500) == 80
    assert not work.con.execute("SELECT 1 FROM posts").fetchone()
    work.client.messages[81] = message(81)
    sweep(work, monkeypatch)
    assert mirror.last(work.con, 500) == 81
    assert work.client.history[-1]["min_id"] == 80
    assert [r[0] for r in work.con.execute("SELECT msg_id FROM tg_post_msgs")] == [81]


@pytest.mark.parametrize("flood", [False, True])
@pytest.mark.parametrize("resolve", [False, True])
def test_refused_leave_does_not_block_the_queue(work, monkeypatch, flood, resolve):
    for channel in (100, 200):
        mirror.joined(work.con, channel, f"old_{channel}")
    calls, sleeps = [], []

    def fail(channel):
        calls.append(channel)
        if channel == 100:
            raise FloodWaitError(None, capture=61) if flood else ChannelPrivateError(None)

    class Leaves:
        async def iter_dialogs(self):
            for dialog in []:
                yield dialog

        async def get_input_entity(self, peer):
            if resolve:
                fail(peer.channel_id)
            return peer

        async def __call__(self, request):
            assert isinstance(request, LeaveChannelRequest)
            if not resolve:
                fail(request.channel.channel_id)

    async def sleep(seconds):
        sleeps.append(seconds)
        if flood or calls == [100, 200]:
            raise asyncio.CancelledError

    work.client = Leaves()
    monkeypatch.setattr(userbot.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(work.joins())
    assert calls == ([100] if flood else [100, 200])
    assert sleeps == ([66] if flood else [userbot.JOIN_GAP, userbot.JOIN_GAP])
    assert mirror.to_leave(work.con) == ([(100, "old_100"), (200, "old_200")] if flood else [])
