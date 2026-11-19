"""An online event (owner, Nov 19): a toggle in the editor, its meeting link shown to every student as a button, so a
trust boundary: https only, a plain host, the known meeting hosts for what the code or the AI finds, any https host
when the organizer types it."""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from fastapi.testclient import TestClient

from kbtu import app as server, db, llm
from kbtu.logic import assistant, core
from test_core import _board_on, _club_runs, env, login, tma  # noqa: F401  (env: the fixture)

MEET = "https://meet.google.com/abc-defg-hij"


@pytest.mark.parametrize("url", [MEET, "https://us02web.zoom.us/j/123456?pwd=xyz", "https://zoom.us/j/1",
                                 "https://teams.microsoft.com/l/meetup-join/19%3ameeting_x%40thread.v2/0?context=%7b%7d",
                                 "https://teams.live.com/meet/9", "https://MEET.google.com/abc", "https://telemost.yandex.ru/j/1"])
def test_known_hosts_pass(url):
    assert core.online_url(url) == url.replace("MEET.google.com", "meet.google.com")


@pytest.mark.parametrize("url", ["http://meet.google.com/abc", "javascript:alert(1)", "data:text/html,x", "meet.google.com/abc",
                                 "https://user:pw@meet.google.com/abc", "https://meet.google.com@evil.com/x", "https://meet.google.com:8443/x",
                                 "https://1.2.3.4/x",
                                 "https://meet.google.com/a b", "https://meet.google.com/\u0430", "https://m\u0435et.google.com/x",
                                 "https://meet.google.com\\@evil.com/", "https://meet.google.com/" + "a" * 500, "", None, 5,
                                 " javascript://meet.google.com/%0aalert(1)"])
def test_bad_links_refused(url):
    assert core.online_url(url) is None and core.online_url(url, typed=True) is None


def test_typed_any_https_host():
    for look_alike in ("https://example.org/room", "https://meet.google.com.evil.com/x", "https://evilmeet.google.com.ru/x"):
        assert core.online_url(look_alike) is None and core.online_url(look_alike, typed=True) == look_alike  # its host shown
    assert core.online_url("https://example.org/room", typed=True) == "https://example.org/room"


def test_finder_on_a_russian_announcement():
    # "Online lecture on Friday at 19:00! Join: meet.google.com/abc-defg-hij. Questions: @club"
    text = ("\u041e\u043d\u043b\u0430\u0439\u043d-\u043b\u0435\u043a\u0446\u0438\u044f \u0432 \u043f\u044f\u0442\u043d\u0438\u0446\u0443 "
            "\u0432 19:00! \u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0430\u0439\u0442\u0435\u0441\u044c: http://example.com/x "
            "meet.google.com/abc-defg-hij. \u0412\u043e\u043f\u0440\u043e\u0441\u044b: @club")
    assert core.meet_link(text) == MEET
    assert core.meet_link(f"({MEET}), then https://zoom.us/j/2") == MEET  # the first one, its brackets left out
    assert core.meet_link("mail me: x@meet.google.com/abc, or see https://notmeet.google.com.evil.io/x") is None
    assert core.meet_link("https://example.org/meet") is None and core.meet_link("") is None
    # the fill takes it beside the model's form; the model's own words never make a link
    assert assistant.filled(json.dumps({"title": "Talk", "description": f"See {MEET}"}), text) == {"onlineUrl": MEET, "title": "Talk", "description": f"See {MEET}"}
    assert "onlineUrl" not in assistant.filled(json.dumps({"title": "Talk", "online_url": "https://evil.io/x"}), "no link here")


def test_fill_route_finds_the_link(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    login(c, 1, "ann")
    _board_on(c, cfg)

    async def fake(cfg_, http, msgs, **kw):
        return json.dumps({"title": "Talk", "place": "Online"}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    r = c.post(f"/api/orgs/{org}/events/fill", headers=tma(9), json={"text": f"A talk tomorrow at 19:00, join here {MEET} please"})
    assert r.status_code == 200 and r.json()["onlineUrl"] == MEET


def test_editor_save_clear_and_public_card(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    login(c, 1, "ann")
    start = int(time.time()) + 86400
    body = {"title": "Talk", "place": "305", "placeUrl": None, "startsAt": start, "endsAt": None, "emoji": "laptop_3d", "color": "#3B6BFF",
            "seats": None, "online": True, "onlineUrl": MEET}
    ev = c.post(f"/api/orgs/{org}/events", headers=tma(9), json=body).json()
    assert ev["online"] is True and ev["onlineUrl"] == MEET and ev["place"] == ""  # online: no place
    eid = ev["id"]
    assert c.post(f"/api/events/{eid}/publish", headers=tma(9)).json()["status"] == "published"
    card = c.get(f"/api/events/{eid}", headers=tma(1)).json()  # a student sees it as the description showed it
    assert card["online"] is True and card["onlineUrl"] == MEET
    assert any(e["id"] == eid and e["onlineUrl"] == MEET for e in c.get(f"/api/events?org={org}", headers=tma(1)).json())
    # any https host by hand; bad ones refused on the server
    put = lambda **kw: c.patch(f"/api/events/{eid}", headers=tma(9), json={**body, **kw})  # noqa: E731
    assert put(onlineUrl="https://example.org/r").json()["onlineUrl"] == "https://example.org/r"
    for bad in ("http://meet.google.com/a", "javascript:alert(1)", "https://u:p@meet.google.com/a"):
        assert put(onlineUrl=bad).json()["error"] == "bad_input"
    # online with no link yet; then off: the link is gone, the place back
    got = put(onlineUrl="  ").json()
    assert got["online"] is True and got["onlineUrl"] is None
    got = put(online=False, onlineUrl=MEET).json()
    assert got["online"] is False and got["onlineUrl"] is None and got["place"] == "305"
    # an older client leaving the toggle out keeps it as it is
    put(onlineUrl=MEET)
    old = {k: v for k, v in body.items() if k not in ("online", "onlineUrl")}
    assert c.patch(f"/api/events/{eid}", headers=tma(9), json=old).json()["onlineUrl"] == MEET


def test_finder_takes_whole_links_only():
    # a meeting inside another link (a redirect's query) is not this event's link
    assert core.meet_link("https://example.org/redirect?url=https://zoom.us/j/1 and more") is None
    assert core.meet_link("x@meet.google.com/abc or zoom.us alone, https://zoom.us/") is None  # an address, the bare site
    assert core.meet_link("\u00abhttp://zoom.us/j/9\u00bb, \u043f\u043e\u0442\u043e\u043c") == "https://zoom.us/j/9"  # quotes and the comma left out
    # Discord: a server's invite only
    assert core.meet_link("https://discord.gg/abcd") == "https://discord.gg/abcd"
    assert core.meet_link("discord.com/invite/xyz.") == "https://discord.com/invite/xyz"
    for bad in ("https://discord.com/channels/123/456", "https://promo.discord.gg/abc", "https://discord.gg/abc/def", "https://discord.com/abc"):
        assert core.meet_link(bad) is None and core.online_url(bad) is None


def test_telegram_links_refused():
    # Telegram's own hosts open inside Telegram as a deep link (tg.openTelegramLink): never a meeting, typed or found
    for bad in ("https://t.me/example_bot?start=room", "https://T.ME/x", "https://a.t.me/x", "https://telegram.me/x", "https://telegram.dog/x"):
        assert core.online_url(bad, typed=True) is None and core.meet_link(bad) is None
    assert core.online_url("https://" + "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com/x", typed=True) is None  # >253


def _online_event(c, con):
    org = _club_runs(c, con, 9, "dana")
    start = int(time.time()) + 86400
    body = {"title": "Talk", "place": "305", "placeUrl": None, "startsAt": start, "endsAt": None, "emoji": "laptop_3d", "color": "#3B6BFF",
            "seats": None, "online": True, "onlineUrl": MEET}
    eid = c.post(f"/api/orgs/{org}/events", headers=tma(9), json=body).json()["id"]
    return org, eid, body


def test_patch_rules(env):
    """online: true without onlineUrl keeps the saved link; onlineUrl without online is refused; a body with neither
    keeps the event online and its place empty."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    org, eid, body = _online_event(c, con)
    patch = lambda b: c.patch(f"/api/events/{eid}", headers=tma(9), json=b).json()  # noqa: E731
    got = patch({k: v for k, v in body.items() if k != "onlineUrl"})
    assert got["online"] is True and got["onlineUrl"] == MEET
    assert patch({**{k: v for k, v in body.items() if k != "online"}, "onlineUrl": "https://zoom.us/j/9"})["error"] == "bad_input"
    legacy = {**{k: v for k, v in body.items() if k not in ("online", "onlineUrl")}, "place": "305", "placeUrl": "https://2gis.kz/almaty/geo/1"}
    got = patch(legacy)
    assert got["online"] is True and got["onlineUrl"] == MEET and got["place"] == "" and got["placeUrl"] is None
    assert patch({**body, "onlineUrl": None})["onlineUrl"] is None  # cleared on purpose: online, no link yet
    assert patch({**body, "onlineUrl": 5})["error"] == "bad_input"
    assert patch({**body, "onlineUrl": "https://t.me/x_bot?start=1"})["error"] == "bad_input"


def test_deleted_event_serves_no_link(env):
    """Under the admin's delete (its Undo still open) the event, its link with it, is gone for the club's team too."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss")
    con = db.connect(cfg.db_path)
    org, eid, _ = _online_event(c, con)
    mem = login(c, 2, "mem")["id"]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, mem))
    assert c.post(f"/api/events/{eid}/publish", headers=tma(9)).json()["status"] == "published"
    assert c.get(f"/api/events/{eid}", headers=tma(2)).json()["onlineUrl"] == MEET
    assert c.delete(f"/api/admin/events/{eid}", headers=tma(60)).status_code == 204
    for uid in (2, 9):  # a member, the Head
        assert c.get(f"/api/events/{eid}", headers=tma(uid)).status_code == 404
        r = c.get(f"/api/orgs/{org}/events", headers=tma(uid))
        assert MEET not in r.text
