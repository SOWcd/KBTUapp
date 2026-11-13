"""Admin → "an event for a club" as the creator (users.is_founder): a President's every option on that club's new event
and on the ones he made so (core.can, lent_full); the money stays the club's (its own Kaspi details, receipts its own);
every other admin keeps the plain public free event, and nobody else gets anything from the headers."""
from __future__ import annotations

import json

from test_admin_create_event import _body, _lines, _org
from test_admin_events import _as, _setup
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

PAY = {"price": 500, "payToName": "Boss Himself", "payPhone": "87770000000"}  # what he types is never used
MEMO = {"room": {"any": True, "projector": False, "capacity": None}}


def _full_setup(env):
    """_setup, club 1 official, 60 the creator; 65 another admin; club 1's own paid event (its Kaspi details)."""
    c, con, ids = _setup(env)
    ids["adm"] = login(c, 65, "adm")["id"]
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 65")
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    con.execute("UPDATE orgs SET official = 1 WHERE id IN (1, 2)")
    return c, con, ids


def _club_kaspi(con, ids, oid: int = 1, eid: int = 10) -> None:
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at,
        price, pay_to_name, pay_phone) VALUES (?, ?, 'published', 'Paid', '305', strftime('%s') + 86400, 'laptop_3d', '#3B6BFF', ?, 0, 0,
        1000, 'Dana S', '+77011234567')""", (eid, oid, ids["pres"] if oid == 1 else ids["other"]))


def test_creator_has_every_option_for_any_club(env):
    c, con, ids = _full_setup(env)
    # no Kaspi details of the club's own yet: the price is refused, never set to his
    r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**PAY))
    assert (r.status_code, r.json()["message"]) == (403, "kaspi")
    _club_kaspi(con, ids)
    _club_kaspi(con, ids, 2, 11)
    for oid in (1, 2):  # any club
        r = c.post(f"/api/orgs/{oid}/events", headers=_org(60, oid), json=_body(**PAY, freeFirst=3, volunteers=5, memo=MEMO))
        assert r.status_code == 200, r.text
        e = r.json()
        assert (e["price"], e["payToName"], e["payPhone"], e["freeFirst"], e["lentFull"]) == (500, "Dana S", "+77011234567", 3, True)
        assert e["memo"] == MEMO and e["volunteers"]["need"] == 5
        assert _lines(con, "staff_full")[-1] == (ids["boss"], f"org:{oid}", {"event": e["id"], "price": 500, "freeFirst": 3, "volunteers": 5, "memo": MEMO})
    eid = e["id"]
    # a members' meeting, a partner's event, a video: as its President
    r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(visibility="members", meeting=True))
    assert r.status_code == 200 and r.json()["meeting"]
    r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(guestHost="Astana Hub", externalUrl="https://astanahub.com/e/1"))
    assert r.status_code == 200 and r.json()["guestHost"] == "Astana Hub"
    assert _lines(con, "staff_full")[-1] == (ids["boss"], "org:1", {"event": r.json()["id"], "guestHost": "Astana Hub"})
    assert c.post("/api/videos", headers=_org(60, 2), json={"size": 10}).status_code == 200
    assert _lines(con, "staff_video") == [(ids["boss"], "org:2", {})]
    # then he runs it as its President: the price again (the club's details kept), the door, a co-host
    r = c.patch(f"/api/events/{eid}", headers=_as(60, eid), json=_body(price=700, payToName="Me", payPhone="87770000000", volunteers=6))
    assert r.status_code == 200 and (r.json()["price"], r.json()["payToName"]) == (700, "Dana S")
    assert _lines(con, "staff_full")[-1] == (ids["boss"], "org:2", {"event": eid, "price": 700, "volunteers": 6})
    assert json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'staff_event' ORDER BY id DESC").fetchone()[0])["full"]
    assert c.get(f"/api/events/{eid}/door", headers=_as(60, eid)).status_code == 200
    # never a seat or a role faked
    assert not con.execute("SELECT 1 FROM org_members WHERE user_id = ?", (ids["boss"],)).fetchone()


def test_the_money_stays_the_clubs(env):
    c, con, ids = _full_setup(env)
    _club_kaspi(con, ids)
    eid = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**PAY)).json()["id"]
    assert c.post(f"/api/events/{eid}/publish", headers=_as(60, eid)).status_code == 200
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', 'TCK9', 0, 0)", (eid, ids["ali"]))
    con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, created_at) VALUES (900, 'x', 'receipt', 'image/webp', 1, 'r/x', 0)")
    rid = con.execute("""INSERT INTO receipts (registration_id, file_id, via, amount, receipt_no, recipient_name, created_at)
        VALUES ((SELECT id FROM registrations WHERE event_id = ?), 900, 'app', 500, 'R-1', 'Dana S', 0)""", (eid,)).lastrowid
    # the payee is the club's; once paid, the details are fixed for him as for anyone
    assert con.execute("SELECT pay_to_name, pay_phone FROM events WHERE id = ?", (eid,)).fetchone()[:] == ("Dana S", "+77011234567")
    assert c.patch(f"/api/events/{eid}", headers=_as(60, eid), json=_body(price=900)).status_code == 409
    # receipts: reviewed by the club's people alone; their routes never take the headers, the list hides them
    assert c.get(f"/api/events/{eid}/attendees", headers=_as(60, eid)).json()[0]["receipt"] is None
    for h in (_as(60, eid), _org(60), tma(60)):
        assert c.post(f"/api/receipts/{rid}/review", headers=h, json={"reject": True}).status_code in (403, 404)
    assert con.execute("SELECT reviewed_by FROM receipts WHERE id = ?", (rid,)).fetchone()[0] is None
    assert c.post(f"/api/receipts/{rid}/review", headers=tma(62), json={"reject": False}).status_code == 204  # the President


def test_other_admins_keep_the_plain_rule(env):
    c, con, ids = _full_setup(env)
    _club_kaspi(con, ids)
    for more, why in ((PAY, "price"), ({"freeFirst": 3}, "price"), ({"volunteers": 5}, "plain"),
                      ({"visibility": "members", "meeting": True}, "plain"), ({"visibility": "members"}, "plain")):
        r = c.post("/api/orgs/1/events", headers=_org(65), json=_body(**more))
        assert (r.status_code, r.json()["message"]) == (403, why), more
    assert c.post("/api/videos", headers=_org(65), json={"size": 10}).json()["message"] == "staff"
    eid = c.post("/api/orgs/1/events", headers=_org(65), json=_body(memo=MEMO)).json()["id"]
    assert con.execute("SELECT memo FROM events WHERE id = ?", (eid,)).fetchone()[0] is None and "lentFull" not in c.get(f"/api/events/{eid}", headers=_as(65, eid)).json()
    # the creator's own event, run by another admin: plain still
    mine = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**PAY)).json()["id"]
    for more in (PAY | {"price": 900}, {"volunteers": 5}, {"memo": MEMO}):
        c.patch(f"/api/events/{mine}", headers=_as(65, mine), json=_body(**more))
    row = con.execute("SELECT price, volunteers, memo FROM events WHERE id = ?", (mine,)).fetchone()
    assert tuple(row) == (500, None, None)
    assert c.get(f"/api/events/{mine}/door", headers=_as(65, mine)).status_code == 403
    v = c.get(f"/api/events/{mine}", headers=_as(65, mine)).json()
    assert v["payToName"] is None and "lentFull" not in v
    assert not [x for x in _lines(con, "staff_full") if x[0] == ids["adm"]]
    # and the creator on a club's event its President made: plain too (he made only his own so)
    assert c.patch("/api/events/1", headers=_as(60, 1), json=_body(**PAY)).status_code == 403
    assert c.get("/api/events/1/door", headers=_as(60, 1)).status_code == 403


def test_headers_lend_nothing_else(env):
    c, con, ids = _full_setup(env)
    _club_kaspi(con, ids)
    mine = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**PAY)).json()["id"]
    n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    for uid in (61, 63, 64, 62):  # a moderator, a student, another club's President, even this club's: not theirs
        assert c.post("/api/orgs/1/events", headers=_org(uid), json=_body(**PAY)).status_code == 403
        assert c.post("/api/videos", headers=_org(uid), json={"size": 10}).status_code == 403
        assert c.patch(f"/api/events/{mine}", headers=_as(uid, mine), json=_body(price=1)).status_code == 403
    # the creator: another club's flag, another event's flag, the club's other routes, the memo sheet
    assert c.post("/api/orgs/1/events", headers=_org(60, 2), json=_body()).status_code == 403
    assert c.patch("/api/events/1", headers=_as(60, mine), json=_body(price=1)).status_code == 403
    assert c.get("/api/events/10/attendees", headers=_as(60, mine)).status_code == 403
    for method, path in (("GET", "/api/orgs/1/memo"), ("POST", "/api/orgs/1/memo/sent"), ("PATCH", "/api/orgs/1"), ("GET", "/api/orgs/1/events")):
        assert c.request(method, path, headers=_org(60), json=[mine]).status_code == 403, path
    assert c.get("/api/events/10", headers=_as(60, 10)).json()["payToName"] is None  # the club's own event: no money shown
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == n
