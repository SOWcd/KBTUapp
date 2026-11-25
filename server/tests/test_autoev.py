"""Events found in a club's channel (logic/autoev.py): the free filter, one model call to a draft, no event, the
duplicates, the President's one bot message, Studio's and Admin's views, the dismiss (Admin's event delete) and who
may see or do what."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time

import pytest
from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, llm, logic, mirror, texts
from kbtu.logic import autoev
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

RU = "\u041f\u0440\u0438\u0445\u043e\u0434\u0438\u0442\u0435 \u043d\u0430 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0439 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d"  # "come to the open mic"


@pytest.mark.parametrize("text, ok", [
    (RU + " 21 \u043d\u043e\u044f\u0431\u0440\u044f, \u0430\u0443\u0434\u0438\u0442\u043e\u0440\u0438\u044f 305, \u0431\u0443\u0434\u0435\u0442 \u043c\u043d\u043e\u0433\u043e \u043c\u0443\u0437\u044b\u043a\u0438", True),  # 21 November
    (RU + " \u0437\u0430\u0432\u0442\u0440\u0430, \u0430\u0443\u0434\u0438\u0442\u043e\u0440\u0438\u044f 305, \u0431\u0443\u0434\u0435\u0442 \u043c\u043d\u043e\u0433\u043e \u043c\u0443\u0437\u044b\u043a\u0438", True),  # tomorrow
    (RU + " \u0432 \u043f\u044f\u0442\u043d\u0438\u0446\u0443, \u0430\u0443\u0434\u0438\u0442\u043e\u0440\u0438\u044f 305, \u0431\u0443\u0434\u0435\u0442 \u043c\u043d\u043e\u0433\u043e \u043c\u0443\u0437\u044b\u043a\u0438", True),  # on Friday
    ("\u0415\u0440\u0442\u0435\u04a3 \u0441\u0430\u0493\u0430\u0442 18.00-\u0434\u0435 \u043a\u0435\u0437\u0434\u0435\u0441\u0443, \u0431\u0430\u0440\u043b\u044b\u0493\u044b\u043d \u0448\u0430\u049b\u044b\u0440\u0430\u043c\u044b\u0437, \u043a\u0435\u043b\u0456\u04a3\u0456\u0437\u0434\u0435\u0440!", True),  # kk: tomorrow at 18.00
    ("\u049a\u0430\u0440\u0430\u0448\u0430\u043d\u044b\u04a3 21-\u0456 \u043a\u04af\u043d\u0456 \u0445\u0430\u043a\u0430\u0442\u043e\u043d \u0431\u0430\u0441\u0442\u0430\u043b\u0430\u0434\u044b, \u0431\u0430\u0440\u043b\u044b\u0493\u044b\u04a3\u044b\u0437\u0434\u044b \u043a\u04af\u0442\u0435\u043c\u0456\u0437 21 \u049b\u0430\u0440\u0430\u0448\u0430", True),
    ("Join us on November 21 for the hackathon kickoff in the main hall, free pizza for everyone", True),
    ("Hackathon kickoff at 19:00 in the main hall, free pizza for everyone who comes along", True),
    ("Thanks to everyone who came to our evening, it was great, the photos are in the album already", False),  # no date
    ("Open mic 21.11 19:00", False),  # too short to be an announcement
])
def test_worth(text, ok):
    assert autoev.worth(text) is ok


def _setup(env):
    """Club 1 with its public channel mirrored; President 20, member 30, outsider 40, admin 60, moderator 61."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    ids = {k: login(c, uid, k)["id"] for uid, k in ((20, "pres"), (30, "mem"), (40, "out"), (60, "boss"), (61, "mod"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 61")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (ids["pres"], ids["mem"]))
    con.execute("INSERT INTO chats (title, kind, url, created_at, status, org_id, main) VALUES ('Open Mic', 'channel', 'https://t.me/mic_news', 0, 'org', 1, 1)")
    mirror.joined(con, 500, "mic_news")
    return c, cfg, con, ids


def _day(days: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + autoev.TZ + days * 86400))


def _model(monkeypatch, answers: list):
    """The AI chain faked as the other AI tests do: each call takes the next answer (an exception is raised); the calls kept."""
    calls = []
    monkeypatch.setattr(llm, "available", lambda cfg: True)

    async def chat(cfg, http, msgs, **kw):
        calls.append(msgs)
        assert kw["check"] is autoev.answered
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        assert kw["check"](a)
        return a, "fake"
    monkeypatch.setattr(llm, "chat", chat)
    return calls


def _post(con, n: int, text: str) -> int:
    return mirror.take(con, 500, mirror.Msg(id=n, date=logic.now(), text=text))


def _look(con, cfg, pid: int, text: str):
    return asyncio.run(autoev.propose(con, cfg, None, pid, text, logic.now()))


TEXT = "Open mic night tomorrow at 19:00 in hall 305, bring your guitar and your best songs for everyone"


def _form(title="Open mic night", day=1, start="19:00", **kw) -> str:
    return json.dumps({"title": title, "date": _day(day), "start": start, "end": None, "place": "305", "description": "Songs.",
                       "price": None, "emoji": "microphone_3d", "color": "violet", "lang": None, "tr": None, **kw})


def test_one_call_to_a_draft(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    calls = _model(monkeypatch, [_form()])
    pid = _post(con, 1, TEXT)
    eid = _look(con, cfg, pid, TEXT)
    assert eid and len(calls) == 1
    assert "Today is " in calls[0][0]["content"] and '{"event": false}' in calls[0][0]["content"] and calls[0][1]["content"] == TEXT
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    assert (e["status"], e["org_id"], e["title"], e["place"], e["emoji"], e["color"], e["created_by"]) == ("draft", 1, "Open mic night", "305", "microphone_3d", "#7C4DFF", None)
    assert time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["starts_at"] + autoev.TZ)) == f"{_day(1)} 19:00"
    # looked at once: an edit or a second look calls no model
    assert _look(con, cfg, pid, TEXT) is None and len(calls) == 1
    # the President hears it once, a button into the club's Studio; quiet once published
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'auto_event'").fetchall()
    assert [(r["user_id"], r["ref"]) for r in m] == [(ids["pres"], f"ae:{eid}")]
    row = {**dict(m[0]), "lang": "en"}
    assert bot._render(con, row) == (*texts.bot_message("en", "auto_event", org="Open Mic"), "st_1")
    # Studio: its leaders see where it came from; a plain member doesn't, an outsider sees no Studio at all
    studio = c.get("/api/orgs/1/events", headers=tma(20)).json()
    assert [(x["id"], x.get("fromPost")) for x in studio] == [(eid, "https://t.me/mic_news/1")]
    assert all("fromPost" not in x for x in c.get("/api/orgs/1/events", headers=tma(30)).json())
    assert c.get("/api/orgs/1/events", headers=tma(40)).status_code == 403
    assert c.get(f"/api/events/{eid}", headers=tma(40)).status_code == 404  # a draft: never in Afisha
    # published by the club: out of Admin's queue, the bot's message quiet
    assert c.post(f"/api/events/{eid}/publish", headers=tma(20)).json()["status"] == "published"
    assert bot._render(con, row) is None
    assert not [x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["items"] if x["kind"] == "autoev"]


def test_not_an_event_past_or_failed(env, monkeypatch):
    c, cfg, con, _ = _setup(env)
    calls = _model(monkeypatch, ['{"event": false}', _form(day=-2), _form(start=None), llm.Busy()])
    for n in range(1, 5):
        assert _look(con, cfg, _post(con, n, f"{n} " + TEXT), f"{n} " + TEXT) is None
    assert len(calls) == 4 and not con.execute("SELECT 1 FROM events").fetchone()
    assert con.execute("SELECT COUNT(*) FROM auto_events WHERE event_id IS NULL").fetchone()[0] == 4  # each looked at once: no retries
    # no date or time in it: no model at all
    assert _look(con, cfg, _post(con, 9, "Thanks to everyone who came, it was a lovely evening and the photos are up"), "Thanks") is None
    assert len(calls) == 4


def test_duplicates(env, monkeypatch):
    c, cfg, con, _ = _setup(env)
    calls = _model(monkeypatch, [_form(), _form(title="OPEN MIC NIGHT!"), _form(title="Chess club meeting"), _form(day=2)])
    assert _look(con, cfg, _post(con, 1, TEXT), TEXT)
    assert _look(con, cfg, _post(con, 2, "2 " + TEXT), "2 " + TEXT) is None          # the same day, a like title
    assert _look(con, cfg, _post(con, 3, "3 " + TEXT), "3 " + TEXT)                  # the same day, another event
    assert _look(con, cfg, _post(con, 4, "4 " + TEXT), "4 " + TEXT)                  # another day
    assert len(calls) == 4 and con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3


def test_admin_queue_and_dismiss(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form()])
    con.execute("""INSERT INTO events (org_id, status, title, starts_at, emoji, color, created_at, updated_at)
        VALUES (1, 'cancelled', 'Old', 1, 'laptop_3d', '#3B6BFF', 0, 0)""")  # the draft's id is no org's id
    pid = _post(con, 1, TEXT)
    eid = _look(con, cfg, pid, TEXT)
    assert eid == 2
    adm = c.get("/api/admin/inbox", headers=tma(60)).json()["items"]
    card = next(x for x in adm if x["kind"] == "autoev")
    assert (card["data"]["id"], card["data"]["org"]["id"], card["data"]["title"], card["data"]["url"]) == (eid, 1, "Open mic night", "https://t.me/mic_news/1")
    assert c.get("/api/me", headers=tma(60)).json()["counters"]["inbox"] == 0  # optional, the club's own: never the Admin badge
    # a moderator can't open a club's draft: not his card; nobody but the admin dismisses it
    assert not [x for x in c.get("/api/admin/inbox", headers=tma(61)).json()["items"] if x["kind"] == "autoev"]
    for uid in (61, 20, 40):
        assert c.delete(f"/api/admin/events/{eid}", headers=tma(uid)).status_code == 403
    # dismissed: the draft hidden at once (deleted a day later), the queue and the bot's message quiet; Undo brings it back
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(60)).status_code == 204
    assert not [x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["items"] if x["kind"] == "autoev"]
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'auto_event'").fetchone()
    assert bot._render(con, {**dict(m), "lang": "ru"}) is None
    logic.undo_delete_event(con, logic.Viewer(ids["boss"], "admin", None), eid)
    assert [x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["items"] if x["kind"] == "autoev"]
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(60)).status_code == 204
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = ?", (f"evdel:{eid}",))
    logic.events_gone(con)
    # gone for good, the post remembered: never proposed again
    assert con.execute("SELECT event_id FROM auto_events WHERE post_id = ?", (pid,)).fetchone()[0] is None
    assert _look(con, cfg, pid, TEXT) is None


def test_club_deletes_its_draft(env, monkeypatch):
    c, cfg, con, _ = _setup(env)
    calls = _model(monkeypatch, [_form()])
    pid = _post(con, 1, TEXT)
    eid = _look(con, cfg, pid, TEXT)
    assert c.delete(f"/api/events/{eid}", headers=tma(30)).status_code == 403   # a plain member
    assert c.delete(f"/api/events/{eid}", headers=tma(20)).status_code == 204
    assert _look(con, cfg, pid, TEXT) is None and len(calls) == 1


def test_day_cap(env, monkeypatch):
    c, cfg, con, _ = _setup(env)
    monkeypatch.setattr(autoev, "DAY_MAX", 1)
    calls = _model(monkeypatch, ['{"event": false}'])
    assert _look(con, cfg, _post(con, 1, TEXT), TEXT) is None
    assert _look(con, cfg, _post(con, 2, "2 " + TEXT), "2 " + TEXT) is None and len(calls) == 1


# ---------------------------------------------------------------- the post's picture as the draft's cover

def _pic(cfg, w=400, h=500, rgb=(200, 40, 40)):
    """A real picture through the real media code, where the app keeps its photos."""
    import io
    from pathlib import Path
    from PIL import Image
    from kbtu import media
    out = io.BytesIO()
    Image.new("RGB", (w, h), rgb).save(out, "PNG")
    root = Path(cfg.db_path).resolve().parent / "media"
    root.mkdir(exist_ok=True)
    return media.save(out.getvalue(), root), root


def _cov(con, eid):
    return con.execute("SELECT e.cover_file_id, e.cover_focus, f.kind, f.owner_id, f.path FROM events e LEFT JOIN files f ON f.id = e.cover_file_id WHERE e.id = ?", (eid,)).fetchone()


def _save(c, con, eid, **extra):
    """The editor's save of the draft by its President."""
    e = con.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    body = {"seats": None, "title": e["title"], "place": e["place"], "startsAt": e["starts_at"], "emoji": e["emoji"], "color": e["color"], **extra}
    r = c.patch(f"/api/events/{eid}", headers=tma(20), json=body)
    assert r.status_code == 200, r.text
    con.execute("UPDATE events SET updated_at = updated_at + 5 WHERE id = ?", (eid,))  # saved a moment after it was made


def _on_disk(root, path):
    return (root / f"{path}.webp").exists()


def test_cover_from_the_posts_picture(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form(), _form(title="Chess night")])
    pic, root = _pic(cfg)
    pid = mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text=TEXT, photo=pic))
    eid = _look(con, cfg, pid, TEXT)
    cv = _cov(con, eid)
    # its own event_cover row (no owner) over the post's stored picture; a tall poster's focus up high
    assert (cv["kind"], cv["owner_id"], cv["path"], cv["cover_focus"]) == ("event_cover", None, pic["path"], autoev.TALL_FOCUS)
    assert cv["cover_file_id"] != con.execute("SELECT photo_file_id FROM posts WHERE id = ?", (pid,)).fetchone()[0]
    # Admin's card and the Studio row show it
    card = next(x for x in c.get("/api/admin/inbox", headers=tma(60)).json()["items"] if x["kind"] == "autoev")["data"]
    assert card["cover"]["url"] == f"media/{pic['path']}.webp" and card["cover"]["focus"] == [0.5, 0.2] and card["emoji"] == "microphone_3d"
    assert [x["cover"]["id"] for x in c.get("/api/orgs/1/events", headers=tma(20)).json()] == [cv["cover_file_id"]]
    # a post without a picture: no cover
    t2 = "2 " + TEXT.replace("Open mic", "Chess")
    e2 = _look(con, cfg, _post(con, 2, t2), t2)
    assert e2 and _cov(con, e2)["cover_file_id"] is None


def test_cover_when_the_photo_comes_later(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form(), _form(title="Chess night")])
    pic, _ = _pic(cfg, 800, 400)
    eid = _look(con, cfg, mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text=TEXT, grouped=9)), TEXT)
    assert _cov(con, eid)["cover_file_id"] is None
    mirror.take(con, 500, mirror.Msg(id=2, date=logic.now(), grouped=9, photo=pic))  # the album's photo after its caption
    cv = _cov(con, eid)
    assert (cv["path"], cv["cover_focus"]) == (pic["path"], None)  # wide: the middle
    # a person's choice stays: a draft saved without a cover gets none later
    t2 = "2 " + TEXT
    e2 = _look(con, cfg, mirror.take(con, 500, mirror.Msg(id=3, date=logic.now(), text=t2, grouped=10)), t2)
    _save(c, con, e2, place="306")
    mirror.take(con, 500, mirror.Msg(id=4, date=logic.now(), grouped=10, photo=pic))
    assert _cov(con, e2)["cover_file_id"] is None


def test_a_persons_cover_is_never_replaced(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form()])
    pic, root = _pic(cfg)
    eid = _look(con, cfg, mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text=TEXT, grouped=9)), TEXT)
    import io
    from PIL import Image
    png = io.BytesIO()
    Image.new("RGB", (300, 200), (1, 2, 3)).save(png, "PNG")
    own = c.post("/api/photos", headers=tma(20), content=png.getvalue()).json()["id"]
    _save(c, con, eid, coverId=own)
    mirror.take(con, 500, mirror.Msg(id=2, date=logic.now(), grouped=9, photo=pic))
    assert _cov(con, eid)["cover_file_id"] == own


def test_dismiss_keeps_the_posts_picture(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form()])
    pic, root = _pic(cfg)
    pid = mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text=TEXT, photo=pic))
    eid = _look(con, cfg, pid, TEXT)
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(60)).status_code == 204
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = ?", (f"evdel:{eid}",))
    _, photos = logic.events_gone(con)
    from kbtu import media
    media.drop(root, photos)
    post = con.execute("SELECT photo_file_id FROM posts WHERE id = ?", (pid,)).fetchone()[0]
    assert post and con.execute("SELECT path FROM files WHERE id = ?", (post,)).fetchone()[0] == pic["path"] and _on_disk(root, pic["path"])
    assert not con.execute("SELECT 1 FROM files WHERE kind = 'event_cover'").fetchone()  # the event's own row went with it


def test_post_taken_down_after(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form(), _form(title="Chess night")])
    pic, root = _pic(cfg)
    pic2, _ = _pic(cfg, rgb=(10, 200, 10))
    pid = mirror.take(con, 500, mirror.Msg(id=1, date=logic.now(), text=TEXT, photo=pic))
    eid = _look(con, cfg, pid, TEXT)
    assert c.post(f"/api/events/{eid}/publish", headers=tma(20)).json()["status"] == "published"
    t2 = "2 " + TEXT
    pid2 = mirror.take(con, 500, mirror.Msg(id=2, date=logic.now(), text=t2, photo=pic2))
    e2 = _look(con, cfg, pid2, t2)
    mirror.gone(con, 500, [1, 2], root)  # both deleted in the channel
    # the published event keeps its cover, the picture on disk; the untouched draft's goes with its post
    assert _cov(con, eid)["path"] == pic["path"] and _on_disk(root, pic["path"])
    assert con.execute("SELECT photo_file_id FROM posts WHERE id = ?", (pid,)).fetchone()[0] is None
    assert _cov(con, e2)["cover_file_id"] is None and not _on_disk(root, pic2["path"])
    assert not con.execute("SELECT 1 FROM files WHERE path = ?", (pic2["path"],)).fetchone()
    # the published event deleted later: now the picture leaves the disk
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(60)).status_code == 204
    con.execute("UPDATE meta SET value = json_set(value, '$.due', 0) WHERE key = ?", (f"evdel:{eid}",))
    from kbtu import media
    media.drop(root, logic.events_gone(con)[1])
    assert not _on_disk(root, pic["path"])


def test_backfill_once(env, monkeypatch):
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form(), _form(title="Chess night"), _form(title="Quiz")])
    pic, _ = _pic(cfg)
    made = []
    for n in (1, 2, 3):
        t = f"{n} " + TEXT
        pid = mirror.take(con, 500, mirror.Msg(id=n, date=logic.now(), text=t, photo=pic))
        made.append(_look(con, cfg, pid, t))
    # as on production before: drafts without a cover; the third one a person saved already
    con.execute("UPDATE events SET cover_file_id = NULL, cover_focus = NULL")
    con.execute("DELETE FROM files WHERE kind = 'event_cover'")
    con.execute("UPDATE events SET updated_at = updated_at + 60 WHERE id = ?", (made[2],))
    for _ in range(2):
        con.executescript(dict(db.MIGRATIONS)[186])
    covers = [_cov(con, e) for e in made]
    assert [x["path"] for x in covers] == [pic["path"], pic["path"], None]
    assert covers[0]["cover_focus"] == autoev.TALL_FOCUS and covers[0]["kind"] == "event_cover" and covers[0]["owner_id"] is None
    assert con.execute("SELECT COUNT(*) FROM files WHERE kind = 'event_cover'").fetchone()[0] == 1  # once, shared


def test_a_meeting_link_makes_it_online(env, monkeypatch):
    """The post's first meeting link (plain code, core.meet_link): the draft is online, no place, the link as written."""
    c, cfg, con, ids = _setup(env)
    _model(monkeypatch, [_form(place="Online")])
    text = TEXT.replace("in hall 305", "online at https://meet.google.com/abc-defg-hij")
    eid = _look(con, cfg, _post(con, 1, text), text)
    e = con.execute("SELECT place, online FROM events WHERE id = ?", (eid,)).fetchone()
    assert tuple(e) == ("", "https://meet.google.com/abc-defg-hij")
