"""Co-hosted events (logic/cohosts.py; the review: .claude/reports/cohost-review.md): the invite, the answer, ending
it; nothing public before the yes; the co-host's event team at the door but nowhere else; one message per follower and
the weekly limit for both clubs; a plain member's rights; account deletion."""
from __future__ import annotations

import time

from kbtu import bot, db, logic
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env is a fixture)

EV = {"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
HOST, CO, CO_HEAD, CO_MEMBER, FAN, BOTH, OTHER = 20, 21, 22, 23, 30, 31, 32


def _clubs(c, cfg, official=True):
    """Crystal (President tg 20, the host) and JCC (President 21, Head 22, Member 23); fan 30 follows JCC, 31 both."""
    for uid, name in ((HOST, "host"), (CO, "pres"), (CO_HEAD, "head"), (CO_MEMBER, "memb"), (FAN, "fan"), (BOTH, "both"), (OTHER, "other")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    host = logic.create_org(con, None, "Crystal", "CR", "crown_3d", official)
    co = logic.create_org(con, None, "JCC", "JC", "crown_3d", official)
    logic.set_role(con, None, uid(HOST), host, "president", "test")
    for tg, role in ((CO, "president"), (CO_HEAD, "head"), (CO_MEMBER, "member")):
        logic.set_role(con, None, uid(tg), co, role, "test")
    for tg, o in ((FAN, co), (BOTH, co), (BOTH, host)):
        assert c.put(f"/api/orgs/{o}/subscription", headers=tma(tg)).status_code == 200
    return con, host, co


def _event(c, host, publish=True, **kw):
    e = c.post(f"/api/orgs/{host}/events", headers=tma(HOST), json={**EV, "title": "Anime Quiz", "startsAt": logic.core.now() + 86400, **kw}).json()
    return c.post(f"/api/events/{e['id']}/publish", headers=tma(HOST)).json() if publish else e


def test_invite_accept_decline_leave(env):
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    e = _event(c, host)
    eid = e["id"]
    invite = lambda who=HOST, org=co: c.put(f"/api/events/{eid}/cohost", headers=tma(who), json={"orgId": org})  # noqa: E731
    assert invite(org=host).status_code == 400  # not ourselves
    assert invite(who=CO).status_code == 403  # the co-host can't invite itself in
    r = invite()
    assert r.status_code == 200 and r.json()["cohost"]["status"] == "pending" and r.json()["coHost"] is None
    assert invite().status_code == 409  # one co-host
    told = con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'cohost_invite'").fetchall()
    assert [t[0] for t in told] == [CO]  # its President (and Vices), not the Head or a Member
    row = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'cohost_invite'").fetchone()) | {"lang": "en"}
    text, _, start = bot._render(con, row)
    assert "Crystal" in text and "JCC" in text and "Anime Quiz" not in text and "Atrium" not in text and start == f"st_{co}"  # no words of the host's draft
    # the co-host's Head can't answer; its President sees it in Studio and declines
    assert c.get(f"/api/orgs/{co}/cohosts", headers=tma(CO_HEAD)).status_code == 403
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO_HEAD), json={"yes": True}).status_code == 404
    assert [x["event"]["id"] for x in c.get(f"/api/orgs/{co}/cohosts", headers=tma(CO)).json()] == [eid]
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": False}).json() == []
    assert c.get(f"/api/events/{eid}", headers=tma(HOST)).json()["cohost"]["status"] == "declined"
    assert invite().status_code == 409  # never asked twice for one event
    # another event: accepted, then the co-host leaves; the host may invite again and then removes
    eid = _event(c, host)["id"]
    assert invite().status_code == 200
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True}).status_code == 200
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True}).status_code == 409  # answered
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["coHost"]["id"] == co
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(CO_HEAD)).status_code == 403  # a Head can't leave for the club
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(CO)).status_code == 204
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["coHost"] is None
    left = con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'cohost_left'").fetchall()
    assert [t[0] for t in left] == [HOST]  # the host club's leaders now
    assert invite().status_code == 200
    c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True})
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(HOST)).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'cohost_removed'").fetchone()[0] == 1
    # only on a public event; and a co-hosted one stays public
    team = _event(c, host, visibility="members")
    assert c.put(f"/api/events/{team['id']}/cohost", headers=tma(HOST), json={"orgId": co}).status_code == 400
    assert invite().status_code == 200
    body = {**EV, "title": "Anime Quiz", "startsAt": logic.core.now() + 86400, "visibility": "members"}
    assert c.patch(f"/api/events/{eid}", headers=tma(HOST), json=body).status_code == 400


def test_pending_shows_nowhere(env):
    """Until the yes the co-host's name is nowhere: the card, its page's list, the counts, the followers."""
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    eid = _event(c, host)["id"]
    c.put(f"/api/events/{eid}/cohost", headers=tma(HOST), json={"orgId": co})
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["coHost"] is None
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["cohost"] is None  # the host's view only
    assert eid not in [x["id"] for x in c.get("/api/events", headers=tma(OTHER), params={"org": co}).json()]
    assert next(o for o in c.get("/api/orgs", headers=tma(OTHER)).json() if o["id"] == co)["upcoming"] == 0
    assert con.execute("SELECT COUNT(*) FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'new_event' AND u.tg_id = ?", (FAN,)).fetchone()[0] == 0
    c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True})
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["coHost"]["name"] == "JCC"
    assert eid in [x["id"] for x in c.get("/api/events", headers=tma(OTHER), params={"org": co}).json()]
    assert c.get("/api/events", headers=tma(OTHER)).json()[0]["coHost"]["id"] == co  # Afisha's shared card, at once
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = ?", (co,))
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["coHost"] is None  # an archived co-host is gone


def test_cohost_can_scan_but_not_run(env):
    """The co-host's event team works the door and reads the list (no receipts, no CSV); never edits, prices, seats,
    cancels or deletes. Its plain Member sees it in Studio and nothing more."""
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    eid = _event(c, host)["id"]
    c.put(f"/api/events/{eid}/cohost", headers=tma(HOST), json={"orgId": co})
    assert c.get(f"/api/events/{eid}/attendees", headers=tma(CO)).status_code == 403  # pending: nothing yet
    c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True})
    code = c.post(f"/api/events/{eid}/registration", headers=tma(OTHER), json={}).json()["my"]["ticketCode"]
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (logic.core.now() + 600, eid))
    for who in (CO, CO_HEAD):
        assert c.get(f"/api/events/{eid}/attendees", headers=tma(who)).status_code == 200
        assert c.get(f"/api/events/{eid}/door", headers=tma(who)).status_code == 200
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(CO_HEAD), json={"code": code}).json()["result"] == "ok"
    assert c.post(f"/api/events/{eid}/screen", headers=tma(CO_HEAD)).status_code == 200  # /show
    sid = c.post(f"/api/events/{eid}/screen", headers=tma(HOST)).json()["session"]
    assert c.post(f"/api/screens/{sid}/csv", headers=tma(CO)).status_code == 403  # the session's names and mails: the host's
    assert c.post(f"/api/screens/{sid}/start", headers=tma(CO)).status_code == 200  # the co-host starts it ...
    for act in ("finish", "unpair"):  # ... ending it for good is the host's
        assert c.post(f"/api/screens/{sid}/{act}", headers=tma(CO)).status_code == 403
    # the list for the co-host: short names, no answers; a change of time tells its leaders once
    a = c.get(f"/api/events/{eid}/attendees", headers=tma(CO)).json()[0]
    assert a["fullName"] == "Other T" and a["answers"] is None and a["receipt"] is None
    body = {**EV, "title": "Anime Quiz", "startsAt": logic.core.now() + 7200}
    assert c.patch(f"/api/events/{eid}", headers=tma(HOST), json=body).status_code == 200
    assert c.patch(f"/api/events/{eid}", headers=tma(HOST), json={**body, "startsAt": body["startsAt"] + 60}).status_code == 200
    told = con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'cohost_changed'").fetchall()
    assert [t[0] for t in told] == [CO]
    assert c.post(f"/api/events/{eid}/attendees/export", headers=tma(CO)).status_code == 403
    body = {**EV, "title": "Taken over", "startsAt": logic.core.now() + 86400}
    for r in (c.patch(f"/api/events/{eid}", headers=tma(CO), json={**body, "price": 5000, "payToName": "Me", "payPhone": "87011234567"}),
              c.patch(f"/api/events/{eid}", headers=tma(CO), json=body), c.post(f"/api/events/{eid}/seats", headers=tma(CO), json={"add": 5}),
              c.post(f"/api/events/{eid}/cancel", headers=tma(CO)), c.delete(f"/api/events/{eid}", headers=tma(CO)),
              c.post(f"/api/events/{eid}/updates", headers=tma(CO), json={"body": "hello all"}),
              c.post(f"/api/events/{eid}/place", headers=tma(CO), json={"place": "101"}),
              c.put(f"/api/events/{eid}/cohost", headers=tma(CO), json={"orgId": co})):
        assert r.status_code == 403, (r.request.method, r.request.url, r.text)
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).json()["title"] == "Anime Quiz"
    # a plain member of the co-host: no door, no list
    for r in (c.get(f"/api/events/{eid}/attendees", headers=tma(CO_MEMBER)), c.get(f"/api/events/{eid}/door", headers=tma(CO_MEMBER)),
              c.post(f"/api/events/{eid}/checkin", headers=tma(CO_MEMBER), json={"code": code}), c.post(f"/api/events/{eid}/screen", headers=tma(CO_MEMBER))):
        assert r.status_code == 403
    # the co-host's Studio lists it for its whole team as its own, without the host's counters; the host's drafts stay
    # hidden, and a pending invite's event isn't there
    draft = _event(c, host, publish=False)["id"]
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (draft, co))
    pending = _event(c, host)["id"]
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'pending', 0)", (pending, co))
    for who in (CO_HEAD, CO_MEMBER):
        listed = {x["id"]: x for x in c.get(f"/api/orgs/{co}/events", headers=tma(who)).json()}
        assert eid in listed and draft not in listed and pending not in listed, who
        assert all(listed[eid][k] == 0 for k in ("questions", "toCheck", "savedBy", "volunteersAsked", "teamAsks"))
    assert c.get(f"/api/orgs/{co}/events", headers=tma(OTHER)).status_code == 403  # not in the club: nothing
    # ended: the door closes at once
    c.delete(f"/api/events/{eid}/cohost", headers=tma(HOST))
    assert c.get(f"/api/events/{eid}/door", headers=tma(CO)).status_code == 403


def test_paid_receipts_stay_with_the_host(env):
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    con.execute("UPDATE users SET role = 'user'")
    e = _event(c, host, publish=False, price=2000, payToName="Crystal Treasurer", payPhone="87011234567")
    c.post(f"/api/events/{e['id']}/publish", headers=tma(HOST))
    c.put(f"/api/events/{e['id']}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{e['id']}/cohost/answer", headers=tma(CO), json={"yes": True})
    reg = con.execute("SELECT id FROM users WHERE tg_id = ?", (OTHER,)).fetchone()[0]
    c.post(f"/api/events/{e['id']}/registration", headers=tma(OTHER), json={})
    rid = con.execute("SELECT id FROM registrations WHERE user_id = ?", (reg,)).fetchone()[0]
    con.execute("INSERT INTO files (sha256, kind, mime, bytes, width, height, path, created_at) VALUES ('x', 'receipt', 'image/webp', 1, 1, 1, 'r', 0)")
    con.execute("INSERT INTO receipts (registration_id, file_id, via, amount, sender_name, created_at) VALUES (?, last_insert_rowid(), 'app', 2000, 'Ali T', 0)", (rid,))
    con.execute("UPDATE registrations SET status = 'going' WHERE id = ?", (rid,))
    co_view = c.get(f"/api/events/{e['id']}/attendees", headers=tma(CO)).json()
    assert co_view and co_view[0]["receipt"] is None  # the co-host sees the person, not the payment
    assert c.get(f"/api/events/{e['id']}/attendees", headers=tma(HOST)).json()[0]["receipt"]["sender"] == "Ali T"
    cid = con.execute("SELECT id FROM receipts").fetchone()[0]
    assert c.post(f"/api/receipts/{cid}/review", headers=tma(CO), json={"reject": True}).status_code == 403
    assert c.get(f"/api/events/{e['id']}", headers=tma(CO)).json()["payPhone"] is None


def test_feed_dedupe_and_weekly_limit(env, monkeypatch):
    """Both clubs' followers hear once each, someone following both once; an initiative co-host under its own week."""
    c, cfg = env
    t0 = int(time.time())
    clock = [t0]
    set_clock(monkeypatch, lambda: clock[0])
    con, host, co = _clubs(c, cfg, official=False)
    heard = lambda tg: con.execute("""SELECT COUNT(*) FROM bot_outbox b JOIN users u ON u.id = b.user_id
        WHERE b.kind = 'new_event' AND u.tg_id = ?""", (tg,)).fetchone()[0]  # noqa: E731
    e = _event(c, host, publish=False)  # invited and accepted as a draft: its publish tells both clubs' followers
    c.put(f"/api/events/{e['id']}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{e['id']}/cohost/answer", headers=tma(CO), json={"yes": True})
    assert heard(FAN) == 0
    c.post(f"/api/events/{e['id']}/publish", headers=tma(HOST))
    assert heard(FAN) == 1 and heard(BOTH) == 1
    # a second one the same week: JCC's week is used, so its fan hears nothing (and Crystal's too)
    clock[0] += 3600
    x = _event(c, host)
    c.put(f"/api/events/{x['id']}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{x['id']}/cohost/answer", headers=tma(CO), json={"yes": True})  # accepted once out: told now, if at all
    assert heard(FAN) == 1 and heard(BOTH) == 1
    clock[0] = t0 + 7 * 86400 + 1
    y = _event(c, host)
    c.put(f"/api/events/{y['id']}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{y['id']}/cohost/answer", headers=tma(CO), json={"yes": True})
    assert heard(FAN) == 2 and heard(BOTH) == 2  # a new week: once each, not twice for the one who follows both


def test_withdrawing_doesnt_reset_the_limit(env):
    """Invite and take back, 15 times: refused after 10 (the count isn't the rows a withdrawal deletes)."""
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    eid = _event(c, host)["id"]
    codes = []
    for _ in range(15):
        codes.append(c.put(f"/api/events/{eid}/cohost", headers=tma(HOST), json={"orgId": co}).status_code)
        c.delete(f"/api/events/{eid}/cohost", headers=tma(HOST))
    assert codes == [200] * 10 + [429] * 5


def test_left_cohost_followers_hear_nothing(env):
    """A follower of the co-host alone, queued when it accepted, hears nothing once it left before the message went."""
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    eid = _event(c, host)["id"]
    c.put(f"/api/events/{eid}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True})
    q = "SELECT b.* FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'new_event' AND u.tg_id = ?"
    row = lambda: dict(con.execute(q, (FAN,)).fetchone()) | {"lang": "en"}  # noqa: E731
    assert "JCC" in bot._render(con, row())[0]
    c.delete(f"/api/events/{eid}/cohost", headers=tma(CO))
    assert bot._render(con, row()) is None


def test_invites_rate_limited_and_closed(env):
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    others = [logic.create_org(con, None, f"Club{i}", "C", "crown_3d", True) for i in range(logic.cohosts.COHOST_INVITES_A_DAY + 1)]
    codes = [c.put(f"/api/events/{_event(c, host)['id']}/cohost", headers=tma(HOST), json={"orgId": o}).status_code for o in others]
    assert codes[:-1] == [200] * logic.cohosts.COHOST_INVITES_A_DAY and codes[-1] == 429
    gone = _event(c, host)
    c.post(f"/api/events/{gone['id']}/cancel", headers=tma(HOST))
    con.execute("DELETE FROM event_cohosts")
    assert c.put(f"/api/events/{gone['id']}/cohost", headers=tma(HOST), json={"orgId": co}).status_code == 409  # cancelled
    hidden = logic.create_org(con, None, "Gone", "G", "crown_3d", True)
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (hidden,))
    assert c.put(f"/api/events/{_event(c, host)['id']}/cohost", headers=tma(HOST), json={"orgId": hidden}).status_code == 400


def test_deleting_an_account_keeps_the_cohost(env):
    c, cfg = env
    con, host, co = _clubs(c, cfg)
    eid = _event(c, host)["id"]
    c.put(f"/api/events/{eid}/cohost", headers=tma(HOST), json={"orgId": co})
    c.post(f"/api/events/{eid}/cohost/answer", headers=tma(CO), json={"yes": True})
    delete_now(c, cfg, tma(CO))
    assert [tuple(r) for r in con.execute("SELECT status, invited_by IS NOT NULL, decided_by FROM event_cohosts")] == [("accepted", 1, None)]
