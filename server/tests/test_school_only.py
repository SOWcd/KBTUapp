"""A school's own event only for its students (events.school, seats.school_ok): every way an event reaches someone is
walked as a student of another school, an unverified account, a guest and nobody, and none of them sees it; its own
students, its organisers and an accepted co-host's team do. Not access control: "not advertised to others"."""
from __future__ import annotations

import re
import time

from kbtu import bot, db, logic
from kbtu.logic.core import Viewer
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

TITLE = "Zxq School Night"
BUSINESS = "Business School"


def _uid(con, tg):
    return con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]


def _setup(c, cfg):
    """SITE's school org (1, tg 20 its President), IT Club (2, tg 15 its President, of the Business School); tg 10 a
    SITE student, 11 and 14 (the app's admin) Business School students, 12 unverified, 13 a guest."""
    for tg in (20, 10, 11, 12, 14, 15):
        login(c, tg, f"p{tg}")
    c.get("/api/me", headers=tma(13))
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'site', 'school', 'SITE', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'itc', 'club', 'IT Club', 'IC', 'laptop_3d', 1, 0)")
    for oid, tg in ((1, 20), (2, 15)):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", (oid, _uid(con, tg)))
    con.execute(f"UPDATE students SET school = ? WHERE user_id IN ({_uid(con, 11)}, {_uid(con, 14)}, {_uid(con, 15)})", (BUSINESS,))
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (_uid(con, 12),))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (_uid(con, 14),))
    for tg in (10, 11):  # both follow SITE; friends
        con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (_uid(con, tg),))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", tuple(sorted((_uid(con, 10), _uid(con, 11)))))
    return con


START = int(time.time()) + 5 * 3600


def _body(**extra):
    return {"title": TITLE, "place": "Hall", "startsAt": START, "endsAt": START + 7200, "emoji": "laptop_3d", "color": "#3B6BFF", **extra}


def _event(c, oid=1, tg=20, **extra):
    return c.post(f"/api/orgs/{oid}/events", headers=tma(tg), json=_body(**extra))


def _school_event(c, con):
    r = _event(c, schoolOnly=True)
    assert r.status_code == 200 and r.json()["school"] == "site", r.text
    eid = r.json()["id"]
    assert c.post(f"/api/events/{eid}/publish", headers=tma(20)).status_code == 200
    return eid


def _sweep(c, eid, uid, headers, admin=False):
    """Every GET route of the API (a new list included), its path filled with this event, club 1 or person 10, asked
    with a search for the title: the bodies that name the event. admin: Admin's own routes are where the admin sees it."""
    seen = []
    for route in c.app.routes:
        if "GET" not in getattr(route, "methods", ()) or not route.path.startswith(("/api/", "/cal/")):
            continue
        names = set(re.findall(r"{(\w+)}", route.path))
        if names - {"eid", "oid", "uid"} or admin and route.path.startswith("/api/admin/"):
            continue
        path = route.path.replace("{eid}", str(eid)).replace("{oid}", "1").replace("{uid}", str(uid))
        try:
            r = c.get(path + "?q=Zxq&org=1&mine=true", headers=headers)
        except Exception:  # noqa: BLE001  a route this made-up call breaks names nothing
            continue
        if TITLE in r.text:
            seen.append(path)
    return seen


def test_nobody_else_sees_it_anywhere(env):
    c, cfg = env
    con = _setup(c, cfg)
    eid = _school_event(c, con)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).json()["my"]["status"] == "going"
    uid10 = _uid(con, 10)
    for who in (tma(11), tma(12), tma(13), {}):  # another school, unverified, a guest, nobody
        assert _sweep(c, eid, uid10, who) == [], who
    assert _sweep(c, eid, uid10, tma(14), admin=True) == []  # the admin outside Admin
    for tg in (10, 20):  # its student and its organiser
        assert any(e["id"] == eid and e["school"] == "site" for e in c.get("/api/events", headers=tma(tg)).json())
        assert c.get(f"/api/events/{eid}", headers=tma(tg)).json()["title"] == TITLE
    # by its link: whose it is, and nothing else
    r = c.get(f"/api/events/{eid}", headers=tma(11))
    assert r.status_code == 403 and r.json() == {"error": "forbidden", "message": "school", "school": "site"}
    assert c.get(f"/api/events/{eid}", headers=tma(12)).json()["message"] == "school"
    # the admin from Admin
    assert c.get(f"/api/events/{eid}", headers={**tma(14), "X-Staff-Event": str(eid)}).json()["title"] == TITLE
    # sign-up with the id, saving it, bringing a friend of another school
    assert c.post(f"/api/events/{eid}/registration", headers=tma(11), json={}).json()["message"] == "school"
    assert c.get(f"/api/events/{eid}/invites", headers=tma(10)).json() == []
    assert c.post(f"/api/events/{eid}/invites", headers=tma(10), json={"userId": _uid(con, 11)}).status_code == 403
    # the calendar file has no viewer: none; my own feed has it
    assert c.get(f"/api/events/{eid}/ics?k={logic.ics_sig(eid)}").status_code == 404
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["ics"] is None
    feed = c.post("/api/me/calendar", headers=tma(10)).json()["feed"].rsplit("/", 1)[1]
    assert TITLE in c.get(f"/cal/{feed}").text
    # never the news channel, never the assistant (even its own student's)
    assert all(e["id"] != eid for e, *_ in logic.channel_due(con, "bot"))
    assert TITLE not in logic.assistant.brief(con, Viewer(uid10, "user", True))[0]
    assert logic.assistant.card(con, {"kind": "event", "id": eid}) is None
    # its followers of another school don't hear of it
    told = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'new_event' AND ref = ?", (f"event:{eid}",))}
    assert uid10 in told and _uid(con, 11) not in told
    logic.notify(con, _uid(con, 11), "new_event", f"event:{eid}")  # one queued anyway: the bot stays quiet
    row = lambda tg: dict(con.execute("SELECT * FROM bot_outbox WHERE user_id = ? AND kind = 'new_event'", (_uid(con, tg),)).fetchone()) | {"lang": "en"}  # noqa: E731
    assert bot._render(con, row(11)) is None and TITLE in bot._render(con, row(10))[0]


def test_who_may_set_it_and_after(env):
    c, cfg = env
    con = _setup(c, cfg)
    assert _event(c, oid=2, tg=15, schoolOnly=True).json()["message"] == "school"   # a club: never
    assert _event(c, oid=2, tg=15).json().get("school") is None
    eid = _school_event(c, con)
    # an accepted co-host's team (another school) runs it too
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, 2, 'accepted', 0)", (eid,))
    assert c.get(f"/api/events/{eid}", headers=tma(15)).json()["title"] == TITLE
    # a student who changes school after signing up keeps the event and the ticket
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    con.execute("UPDATE students SET school = ? WHERE user_id = ?", (BUSINESS, _uid(con, 10)))
    assert c.get(f"/api/events/{eid}", headers=tma(10)).json()["my"]["status"] == "going"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json=_body()).json()["school"] == "site"  # left out: kept
    # switched off later: for everyone; on again: its own school, whatever is sent
    p = c.patch(f"/api/events/{eid}", headers=tma(20), json=_body(schoolOnly=False)).json()
    assert p.get("school") is None and p.get("title") == TITLE, p
    r = c.get(f"/api/events/{eid}", headers=tma(11)).json()
    assert r.get("title") == TITLE, r
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json=_body(schoolOnly="business")).status_code == 400
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json=_body(schoolOnly=True)).json()["school"] == "site"
    # a school org whose slug is no school of schools.json: refused, not hidden from everyone
    con.execute("UPDATE orgs SET slug = 'site2' WHERE id = 1")
    assert _event(c, schoolOnly=True).json()["message"] == "school"
