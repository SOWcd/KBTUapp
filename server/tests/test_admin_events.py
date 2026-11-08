"""Admin → an event: the app's admin finds any event and runs it as its organizers do (X-Staff-Event), only there,
never its money or door, every write in the owner's log; "Close registration" and its reopening."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, db
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_review_moderation import _club_event


def _setup(env):
    """An admin (60), a moderator (61), club 1's President (62) with event 1, a student (63), club 2's President (64)."""
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    ids = {k: login(c, uid, k)["id"] for uid, k in ((60, "boss"), (61, "mod"), (62, "pres"), (63, "ali"), (64, "other"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 61")
    _club_event(con, ids["pres"])
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'b', 'club', 'B Club', 'B', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'president', 0)", (ids["other"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (2, 2, 'published', 'B night', '305', strftime('%s') + 86400, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (ids["other"],))
    return c, con, ids


def _as(uid: int, eid: object = 1) -> dict:
    return {**tma(uid), "X-Staff-Event": str(eid)}


def _staff_lines(con) -> list:
    return con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'staff_event' ORDER BY id").fetchall()


def test_staff_path_refused_to_everyone_else(env):
    c, con, ids = _setup(env)
    close = {"until": "now"}
    for uid in (61, 63, 64):  # a moderator, a student, another club's President: the flag lends nothing
        assert c.put("/api/events/1/reg-until", headers=_as(uid), json=close).status_code == 403
    assert c.put("/api/events/1/reg-until", headers=tma(64), json=close).status_code == 403   # club B on club A's event
    assert c.put("/api/events/1/reg-until", headers=tma(60), json=close).status_code == 403   # the admin without the flag
    assert c.put("/api/events/1/reg-until", headers=_as(60, 2), json=close).status_code == 403  # the flag for another event
    assert c.put("/api/events/1/reg-until", headers=_as(60, "1 "), json=close).status_code == 403
    assert c.post("/api/orgs/1/events", headers=_as(60), json={}).status_code == 403  # not an event's own route
    assert c.get("/api/events/1/door", headers=_as(60)).status_code == 403            # never the door
    assert con.execute("SELECT reg_until FROM events WHERE id = 1").fetchone()[0] is None
    assert not _staff_lines(con)


def test_admin_finds_and_runs_an_event_audited(env):
    c, con, ids = _setup(env)
    found = c.get("/api/search?q=HAC", headers=tma(60)).json()["events"]
    assert [e["id"] for e in found] == [1]
    assert c.get("/api/search?q=night", headers=tma(60)).json()["events"][0]["id"] == 2
    # reading the event isn't logged; the attendee list (personal data) and every write are
    assert c.get("/api/events/1", headers=_as(60)).status_code == 200
    assert c.get("/api/events/1/attendees", headers=_as(60)).status_code == 200
    r = c.put("/api/events/1/reg-until", headers=_as(60), json={"until": "now"})
    assert r.status_code == 200 and r.json()["regUntil"]
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 409   # closed
    assert c.put("/api/events/1/reg-until", headers=_as(60), json={"until": None}).json()["regUntil"] is None
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 200   # open again
    lines = _staff_lines(con)
    assert [(a, t) for a, t, _ in lines] == [(ids["boss"], "event:1")] * 3
    assert [x for _, _, x in lines] == ['{"do": "GET /api/events/{eid}/attendees"}'] + ['{"do": "PUT /api/events/{eid}/reg-until"}'] * 2
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    assert c.get("/api/admin/audit", headers=tma(60)).json()[0]["targetName"] == "Hack"  # the owner's log names the event
    # a refused write leaves no line
    assert c.put("/api/events/1/reg-until", headers=_as(60), json={"until": 1 << 40}).status_code == 400
    assert len(_staff_lines(con)) == 3


def test_organizers_own_event_not_logged_and_bounds(env):
    c, con, ids = _setup(env)
    # the same "Close registration" in the organizers' own Studio screen
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": "now"}).status_code == 200
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 409
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": True}).status_code == 400
    assert c.put("/api/events/1/reg-until", headers=tma(62), json={"until": None}).status_code == 200
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 200
    assert not _staff_lines(con)


def test_staff_gets_none_of_the_clubs_own(env):
    """The admin runs the event but gets no Kaspi details, DMP memo, rating comments or receipts, can't rotate the
    organizers' chat link or invite a co-host (review, Nov 7)."""
    c, con, ids = _setup(env)
    con.execute("""UPDATE events SET price = 2000, pay_to_name = 'Dana S', pay_phone = '+77011234567', memo = '{"room": "305"}' WHERE id = 1""")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'TCK001', 0, 0)", (ids["ali"],))
    con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, created_at) VALUES (900, 'x', 'receipt', 'image/webp', 1, 'r/x', 0)")
    con.execute("""INSERT INTO receipts (registration_id, file_id, via, amount, receipt_no, sender_name, recipient_name, created_at)
        VALUES ((SELECT id FROM registrations WHERE event_id = 1), 900, 'app', 2000, 'R-1', 'Ali T', 'Dana S', 0)""")
    for uid in (ids["ali"], ids["mod"], ids["other"]):
        con.execute("INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (1, ?, 4, 'nice', 0)", (uid,))
    org = c.get("/api/events/1", headers=tma(62)).json()
    assert org["payPhone"] and org["memo"] and org["ratings"]["comments"]  # control: the club's own team
    adm = c.get("/api/events/1", headers=_as(60)).json()
    assert adm["payToName"] is None and adm["payPhone"] is None and adm["memo"] is None
    assert adm["ratings"]["count"] == 3 and adm["ratings"]["comments"] == []
    assert c.get("/api/events/1/attendees", headers=tma(62)).json()[0]["receipt"]["no"] == "R-1"
    a = c.get("/api/events/1/attendees", headers=_as(60)).json()[0]
    assert a["receipt"] is None and a["fullName"]  # the people, as organizers see them; not the money
    assert c.post("/api/events/1/chat", headers=_as(60)).status_code == 403
    assert c.put("/api/events/1/cohost", headers=_as(60), json={"orgId": 2}).status_code == 403
    assert con.execute("SELECT chat_token FROM events WHERE id = 1").fetchone()[0] is None


def test_phone_not_asked_after_signups(env):
    """needsPhone can't be switched on once people are in: the export would hand out phones they gave elsewhere."""
    c, con, ids = _setup(env)
    start = con.execute("SELECT starts_at FROM events WHERE id = 1").fetchone()[0]
    body = {"title": "Hack", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "needsPhone": True}
    assert c.post("/api/events/1/registration", headers=tma(63), json={}).status_code == 200
    r = c.patch("/api/events/1", headers=tma(62), json=body)
    assert r.status_code == 409 and r.json()["message"] == "needs_phone"
    assert c.patch("/api/events/1", headers=tma(62), json={**body, "needsPhone": False}).status_code == 200
    assert c.delete("/api/events/1/registration", headers=tma(63)).status_code in (200, 204)
    assert c.patch("/api/events/1", headers=tma(62), json=body).status_code == 200  # nobody in: fine


def test_one_search_every_name_scoped_by_who(env):
    """The one search (logic/search.py): an event by a translated title, any case in Cyrillic, yo as ye; a club by its
    translated name; the admin finds drafts, hidden events and hidden clubs, a student only what they may open."""
    import json
    c, con, ids = _setup(env)
    ru = "\u041a\u043e\u0448\u043c\u0430\u0440 \u043d\u0430 \u0443\u043b\u0438\u0446\u0435 \u0422\u043e\u043b\u0435 \u0411\u0438"  # Koshmar na ulice Tole Bi
    con.execute("UPDATE events SET title = 'A Nightmare on Tole Bi Street', i18n = ? WHERE id = 2", (json.dumps({"ru": {"title": ru}}),))
    con.execute("UPDATE orgs SET i18n = ? WHERE id = 2", (json.dumps({"ru": {"name": "\u0411\u0438 \u041a\u043b\u0451\u0431"}}),))  # Bi Klyob
    find = lambda q, uid=60: c.get("/api/search", params={"q": q}, headers=tma(uid)).json()  # noqa: E731
    up = "\u041a\u041e\u0428\u041c\u0410\u0420"  # KOSHMAR, upper case
    for q in (ru, up, "\u0442\u043e\u043b\u0435 \u0431\u0438", "nightmare"):  # the Russian title, upper, lower, the English
        assert [e["id"] for e in find(q)["events"]] == [2], q
    assert [o["id"] for o in find("\u043a\u043b\u0435\u0431")["clubs"]] == [2]      # yo typed as ye
    assert [e["id"] for e in find(up, 63)["events"]] == [2]                          # a student finds a public one too
    con.execute("UPDATE events SET status = 'draft' WHERE id = 1")
    assert [e["id"] for e in find("hack")["events"]] == [1]                         # the admin: a draft
    assert find("hack", 63)["events"] == [] and find("hack", 61)["events"] == []     # a student, a moderator: no
    assert [e["id"] for e in find("hack", 62)["events"]] == [1]                     # its own club's team: yes
    con.execute("UPDATE events SET status = 'published', hidden_at = 1 WHERE id = 1")
    assert find("hack", 63)["events"] == [] and [e["id"] for e in find("hack")["events"]] == [1]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'member', 0)", (ids["ali"],))
    assert [o["id"] for o in find("b club", 63)["clubs"]] == [2]
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 2")
    assert find("b club", 63) == {"events": [], "clubs": []}                        # a hidden club and its events: gone
    assert [o["id"] for o in find("b club")["clubs"]] == [2] and [e["id"] for e in find("nightmare")["events"]] == [2]
    assert find("x")["events"] == []                                                # one letter: nothing
    # people (Admin, Awards, the DMP registry): a Cyrillic name in any case, yo as ye, either order
    con.execute("UPDATE students SET first_name = ?, last_name = ? WHERE user_id = ?", ("\u0410\u043b\u0438\u044f", "\u0401\u043b\u043a\u0438\u043d\u0430", ids["ali"]))  # Aliya Yolkina
    for path in ("/api/admin/people", "/api/admin/badges/people"):
        got = c.get(path, params={"q": "\u0435\u043b\u043a\u0438\u043d\u0430 \u0430\u043b\u0438"}, headers=tma(60)).json()  # "elkina ali"
        assert [p["person"]["id"] for p in got] == [ids["ali"]], path
