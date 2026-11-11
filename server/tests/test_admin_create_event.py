"""Admin → "an event for a club": the app's admin makes a club's draft without a role in it (X-Staff-Org, on the
create-event and cover-upload routes alone), never its money, in the owner's log; the same from the server
(`kbtu.admin event create | publish`)."""
from __future__ import annotations

import base64
import io
import json
import time

import pytest

from kbtu import admin, config
from test_admin_events import _as, _setup
from test_core import env, tma  # noqa: F401  (env: the fixture)
from test_review_fixes import _png


def _org(uid: int, oid: object = 1) -> dict:
    return {**tma(uid), "X-Staff-Org": str(oid)}


def _body(**more) -> dict:
    return {"title": "Guest night", "place": "Hall 1", "description": "Come", "startsAt": int(time.time()) + 86400,
            "emoji": "laptop_3d", "color": "#3B6BFF", **more}


def _lines(con, action: str = "staff_create") -> list:
    return [(a, t, json.loads(d)) for a, t, d in con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = ? ORDER BY id", (action,))]


def test_admin_creates_for_a_club_he_is_not_in(env):
    c, con, ids = _setup(env)
    assert c.post("/api/orgs/1/events", headers=tma(60), json=_body()).status_code == 403  # no flag: he's nobody there
    cover = c.post("/api/photos", headers=_org(60), content=_png((200, 30, 30)))
    assert cover.status_code == 200 and _lines(con, "staff_photo") == [(ids["boss"], "org:1", {})]
    r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(coverId=cover.json()["id"]))
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    e = con.execute("SELECT org_id, status, created_by, cover_file_id, price FROM events WHERE id = ?", (eid,)).fetchone()
    assert tuple(e) == (1, "draft", ids["boss"], cover.json()["id"], None)
    assert _lines(con) == [(ids["boss"], f"event:{eid}", {"org": 1, "via": "admin"})]  # ids only
    assert not con.execute("SELECT 1 FROM org_members WHERE user_id = ?", (ids["boss"],)).fetchone()  # no role faked
    # the club's own President sees it in Studio and edits it as any of theirs
    assert eid in [x["id"] for x in c.get("/api/orgs/1/events", headers=tma(62)).json()]
    assert c.patch(f"/api/events/{eid}", headers=tma(62), json=_body(title="Ours now")).json()["title"] == "Ours now"
    # the admin goes on through X-Staff-Event: edits, publishes
    assert c.patch(f"/api/events/{eid}", headers=_as(60, eid), json=_body(title="Guest night 2")).status_code == 200
    assert c.post(f"/api/events/{eid}/publish", headers=_as(60, eid)).json()["status"] == "published"
    assert c.get(f"/api/events/{eid}", headers=tma(63)).json()["org"]["id"] == 1  # shown from the club


def test_the_flag_lends_nothing_else(env):
    c, con, ids = _setup(env)
    for uid in (61, 63, 64):  # a moderator, a student, another club's President
        assert c.post("/api/orgs/1/events", headers=_org(uid), json=_body()).status_code == 403
        assert c.post("/api/photos", headers=_org(uid), content=_png((1, 2, 3))).status_code == 403
    assert c.post("/api/orgs/1/events", headers=_org(62), json=_body()).status_code == 403  # even the club's own President: not his flag
    for oid in (2, 999, "1 ", "", "x"):  # another club's flag, no such club, not a number
        assert c.post("/api/orgs/1/events", headers=_org(60, oid), json=_body()).status_code == 403
    assert c.post("/api/orgs/1/events", headers={**_org(60), "X-Staff-Event": "1"}, json=_body()).status_code == 403
    # the admin with the flag on every other route: refused before the route runs
    for method, path, body in (
            ("PATCH", f"/api/orgs/1/members/{ids['ali']}", {"role": "president"}), ("POST", "/api/orgs/1/roles", {"title": "X"}),
            ("PATCH", "/api/orgs/1", {"description": "mine"}), ("POST", "/api/orgs/1/transfer", {"to": ids["boss"]}),
            ("POST", "/api/orgs/1/posts", {"body": "hi"}), ("POST", "/api/orgs/1/invites", {}), ("DELETE", "/api/orgs/1", None),
            ("PATCH", "/api/events/1", _body(price=500, payToName="Me Me", payPhone="87011234567")), ("DELETE", "/api/events/1", None),
            ("POST", "/api/events/1/publish", None), ("GET", "/api/events/1/attendees", None), ("GET", "/api/orgs/1/events", None),
            ("POST", "/api/videos", {"size": 10}), ("GET", "/api/me", None)):
        r = c.request(method, path, headers=_org(60), json=body)
        assert (r.status_code, r.json().get("message")) == (403, "staff"), (method, path)
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2 and not _lines(con) and not _lines(con, "staff_photo")
    assert con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (ids["pres"],)).fetchone()[0] == "president"


def test_never_the_money(env):
    c, con, ids = _setup(env)
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    pay = {"price": 500, "payToName": "Boss B.", "payPhone": "87011234567"}
    r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**pay))
    assert (r.status_code, r.json()["message"]) == (403, "price")
    assert c.post("/api/orgs/1/events", headers=_org(60), json=_body(freeFirst=5)).status_code == 403
    # an admin who is the club's own treasurer too: this path still sets no money
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0)", (ids["boss"],))
    assert c.post("/api/orgs/1/events", headers=_org(60), json=_body(**pay)).status_code == 403
    con.execute("DELETE FROM org_members WHERE user_id = ?", (ids["boss"],))
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2 and not _lines(con)
    eid = c.post("/api/orgs/1/events", headers=_org(60), json=_body(price=None)).json()["id"]  # free said out loud: fine
    assert c.patch(f"/api/events/{eid}", headers=_as(60, eid), json=_body(**pay)).status_code == 403  # nor afterwards
    assert c.patch(f"/api/events/{eid}", headers=tma(62), json=_body(**pay)).json()["price"] == 500   # the club itself


def test_a_plain_public_event_alone_and_never_the_memo(env):
    c, con, ids = _setup(env)
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    for more in ({"visibility": "members"}, {"visibility": "leaders", "leadersFrom": "head"}, {"visibility": "members", "meeting": True},
                 {"visibility": "members", "forBoard": True}, {"visibility": "members", "meetingTag": 7}, {"volunteers": 5}, {"leadersFrom": "head"}):
        r = c.post("/api/orgs/1/events", headers=_org(60), json=_body(**more))
        assert (r.status_code, r.json()["message"]) == (403, "plain"), more
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2 and not _lines(con)
    # a memo sent on this path is dropped: what DMP is asked for is the club's own
    memo = {"room": {"any": True, "projector": False, "capacity": None}}
    eid = c.post("/api/orgs/1/events", headers=_org(60), json=_body(memo=memo, visibility="public")).json()["id"]
    stored = lambda: con.execute("SELECT memo FROM events WHERE id = ?", (eid,)).fetchone()[0]  # noqa: E731
    assert stored() is None
    # the club writes its memo; the admin's later edit (the editor sends null, or anything) keeps it
    assert c.patch(f"/api/events/{eid}", headers=tma(62), json=_body(memo=memo)).status_code == 200
    theirs = stored()
    assert theirs and c.get(f"/api/events/{eid}", headers=_as(60, eid)).json()["memo"] is None  # never shown to him either
    for sent in (None, {}, {"room": {"any": False}}):
        assert c.patch(f"/api/events/{eid}", headers=_as(60, eid), json=_body(title="Edited", memo=sent)).status_code == 200
        assert stored() == theirs
    # an organization that is hidden or archived: no flag for it
    for status in ("hidden", "archived"):
        con.execute("UPDATE orgs SET status = ? WHERE id = 1", (status,))
        assert c.post("/api/orgs/1/events", headers=_org(60), json=_body()).status_code == 403
        assert c.post("/api/photos", headers=_org(60), content=_png((9, 9, 9))).status_code == 403


def test_partner_event_for_an_official_club(env):
    c, con, ids = _setup(env)
    partner = _body(guestHost="Astana Hub", externalUrl="https://astanahub.com/e/1")
    r = c.post("/api/orgs/1/events", headers=_org(60), json=partner)  # no check mark: the admin's own word isn't enough here
    assert (r.status_code, r.json()["message"]) == (403, "partner") and not _lines(con)
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    assert c.post("/api/orgs/1/events", headers=_org(60), json=_body(guestHost="KBTU friends", externalUrl="https://a.kz")).status_code == 400
    r = c.post("/api/orgs/1/events", headers=_org(60), json=partner)
    assert r.status_code == 200 and (r.json()["guestHost"], r.json()["externalUrl"]) == ("Astana Hub", "https://astanahub.com/e/1")
    eid = r.json()["id"]
    assert _lines(con) == [(ids["boss"], f"event:{eid}", {"org": 1, "via": "admin", "partner": True})]
    assert c.post(f"/api/events/{eid}/publish", headers=_as(60, eid)).json()["status"] == "published"
    assert c.post("/api/orgs/1/events", headers=_org(60), json={"title": ""}).status_code == 400  # the editor's checks, in full


def test_from_the_server(env, monkeypatch, capsys):
    c, con, ids = _setup(env)
    monkeypatch.setattr(config, "load", lambda: env[1])

    def run(args: list[str], stdin: bytes = b"") -> str:
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin)))
        capsys.readouterr()
        admin.main(args)
        return capsys.readouterr().out.strip()

    def refused(args: list[str], stdin: bytes = b"") -> str:
        with pytest.raises(SystemExit) as x:
            run(args, stdin)
        return str(x.value)

    assert "creator" in refused(["event", "create", "it"], json.dumps(_body()).encode())
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    out = run(["event", "create", "it"], json.dumps(_body()).encode())
    kind, eid = out.split()  # the id alone: no title, no name
    assert kind == "draft" and tuple(con.execute("SELECT org_id, status, created_by, cover_file_id FROM events WHERE id = ?", (eid,)).fetchone()) == (1, "draft", ids["boss"], None)
    cover = base64.b64encode(_png((10, 200, 10))).decode()
    with_cover = run(["event", "create", "it"], json.dumps(_body(cover=cover)).encode()).split()[1]
    f = con.execute("SELECT f.kind, f.owner_id FROM events e JOIN files f ON f.id = e.cover_file_id WHERE e.id = ?", (with_cover,)).fetchone()
    assert tuple(f) == ("event_cover", ids["boss"])
    assert _lines(con) == [(ids["boss"], f"event:{i}", {"org": 1, "via": "server"}) for i in (eid, with_cover)]
    n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert "JSON" in refused(["event", "create", "it"], b"{not json")
    assert "JSON" in refused(["event", "create", "it"], b"[1]")
    assert "JSON" in refused(["event", "create", "it"], b" " * (admin.EVENT_STDIN + 1))
    assert "no active club" in refused(["event", "create", "nope"], json.dumps(_body()).encode())
    assert refused(["event", "create", "it"], json.dumps(_body(price=500, payToName="Me Me", payPhone="87011234567")).encode()) == "refused: forbidden price"
    assert "cover" in refused(["event", "create", "it"], json.dumps(_body(cover="!!")).encode())
    assert "cover" in refused(["event", "create", "it"], json.dumps(_body(cover=base64.b64encode(b"text").decode())).encode())
    assert refused(["event", "create", "it"], json.dumps({"title": "Secret words"}).encode()) == "refused: bad_input"
    assert refused(["event", "create", "it"], json.dumps(_body(visibility="members", meeting=True)).encode()) == "refused: forbidden plain"
    assert refused(["event", "create", "it"], json.dumps(_body(guestHost="Astana Hub", externalUrl="https://a.kz")).encode()) == "refused: forbidden partner"
    files = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    assert refused(["event", "create", "it"], json.dumps({"title": "", "cover": cover}).encode()) == "refused: bad_input"
    assert con.execute("SELECT COUNT(*) FROM files").fetchone()[0] == files  # a refused event keeps no cover row
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = 2")
    assert "no active club" in refused(["event", "create", "b"], json.dumps(_body()).encode())
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == n
    # publish: that draft, by the usual rules
    con.execute("INSERT INTO subscriptions (org_id, user_id, created_at) VALUES (1, ?, 0)", (ids["ali"],))
    assert run(["event", "publish", eid]) == f"published {eid}"
    assert con.execute("SELECT status FROM events WHERE id = ?", (eid,)).fetchone()[0] == "published"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event' AND user_id = ?", (ids["ali"],)).fetchone()[0] == 1
    assert _lines(con, "staff_event") == [(ids["boss"], f"event:{eid}", {"do": "publish", "via": "server"})]
    assert refused(["event", "publish", eid]) == "refused: conflict"   # out already
    assert refused(["event", "publish", "999"]) == "no such event"
    assert len(_lines(con, "staff_event")) == 1


def test_admin_fills_it_from_the_announcement(env, monkeypatch):
    """Nov 11: the admin's new event for a club fills from the club's announcement as an organizer's own does (the
    flag on that club's fill route alone); nothing is stored, so nothing is logged."""
    from kbtu import llm
    from test_core import _board_on
    c, con, ids = _setup(env)
    _board_on(c, env[1])
    text = "Open mic on November 10 at 18:00 in room 256. Bring friends, it will be loud!"

    async def fake(cfg_, http, msgs, **kw):
        return json.dumps({"title": "Open mic", "place": "256"}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    assert c.post("/api/orgs/1/events/fill", headers=tma(60), json={"text": text}).status_code == 403  # no flag
    assert c.post("/api/orgs/1/events/fill", headers=_org(60, 2), json={"text": text}).status_code == 403  # another club's flag
    assert c.post("/api/orgs/1/events/fill", headers=_org(61), json={"text": text}).status_code == 403  # not the admin
    r = c.post("/api/orgs/1/events/fill", headers=_org(60), json={"text": text})
    assert r.status_code == 200 and r.json()["title"] == "Open mic", r.text
