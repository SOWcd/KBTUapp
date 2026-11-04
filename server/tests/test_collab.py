"""Collabs with an official club (owner, Nov 4; .claude/reports/collab-review.md): an initiative's free event in the
channel while an official club co-hosts it, signed official first, gone when that club leaves or loses the check mark;
the invite limits; the names. Temporary door helpers (logic/crew.py). "For whom" apart from "required"."""
from __future__ import annotations

import json

from kbtu import bot, db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)

EV = {"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
INI, OFF, OFF_HEAD, FRIEND, FRIEND2, FRIEND3, FRIEND4, GUEST = 20, 21, 22, 30, 31, 32, 33, 34


def _clubs(c, cfg):
    """Anime Crew (an initiative, President tg 20) and JCC (official, President 21, Head 22)."""
    for tg in (INI, OFF, OFF_HEAD, FRIEND, FRIEND2, FRIEND3, FRIEND4, GUEST):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    ini = logic.create_org(con, None, "Anime Crew", "AC", "crown_3d", False)
    off = logic.create_org(con, None, "JCC", "JC", "crown_3d", True)
    logic.set_role(con, None, uid(INI), ini, "president", "test")
    logic.set_role(con, None, uid(OFF), off, "president", "test")
    logic.set_role(con, None, uid(OFF_HEAD), off, "head", "test")
    return con, ini, off, uid


def _event(c, org, who=INI, start=86400, **kw):
    e = c.post(f"/api/orgs/{org}/events", headers=tma(who), json={**EV, "title": "Anime Quiz", "startsAt": logic.core.now() + start, **kw}).json()
    return c.post(f"/api/events/{e['id']}/publish", headers=tma(who)).json()


def _collab(c, eid, off):
    assert c.put(f"/api/events/{eid}/cohost", headers=tma(INI), json={"orgId": off}).status_code == 200
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(OFF), json={"yes": True}).status_code == 200


def _posted(con, eid, sig):
    con.execute("UPDATE events SET channel_msg = 77, channel_sig = ? WHERE id = ?", (sig, eid))


def _gone(con) -> list[int]:
    return [p for p, _ in logic.channel_gone(con)]


def test_collab_goes_to_the_channel_and_back(env):
    """No post alone; accepted: "JCC × Anime Crew"; the official club leaves: the post goes; a new yes brings it back;
    the official club loses the check mark: the post goes; an archived initiative's future post goes too."""
    c, cfg = env
    con, ini, off, _ = _clubs(c, cfg)
    eid = _event(c, ini)["id"]
    assert logic.channel_due(con) == []
    _collab(c, eid, off)
    (row, text, _, sig), = logic.channel_due(con)
    assert row["id"] == eid and "JCC × Anime Crew" in text  # official first
    _posted(con, eid, sig)
    assert logic.channel_due(con) == [] and con.execute("SELECT channel_via FROM events WHERE id = ?", (eid,)).fetchone()[0] == off
    # any change is told to the official club (the description too)
    body = {**EV, "title": "Anime Quiz", "startsAt": row["starts_at"], "description": "new words"}
    assert c.patch(f"/api/events/{eid}", headers=tma(INI), json=body).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'cohost_changed'").fetchone()[0] == 1
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(OFF)).status_code == 204  # "Leave"
    assert logic.channel_due(con) == [] and _gone(con) == [77]
    assert tuple(con.execute("SELECT channel_msg, channel_via FROM events WHERE id = ?", (eid,)).fetchone()) == (None, None)
    con.execute("DELETE FROM meta WHERE key LIKE 'channel_gone:%'")
    _collab(c, eid, off)
    (_, _, _, sig), = logic.channel_due(con)
    _posted(con, eid, sig)
    logic.channel_due(con)
    con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (off,))
    assert logic.channel_due(con) == [] and _gone(con) == [77]
    # review X3: an archived club's future events leave the channel (an official one's own post too)
    con.execute("DELETE FROM meta WHERE key LIKE 'channel_gone:%'")
    own = _event(c, off, who=OFF)["id"]
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (off,))
    (r, _, _, sig), = [x for x in logic.channel_due(con) if x[0]["id"] == own]
    _posted(con, own, sig)
    con.execute("UPDATE orgs SET status = 'archived' WHERE id = ?", (off,))
    logic.channel_due(con)
    assert _gone(con) == [77]


def test_a_post_made_with_the_mark_stays_in_step(env):
    """A club's own post (no co-host) kept in step after the check mark went, as before; a past collab's post goes when
    its official club leaves after the event."""
    c, cfg = env
    con, ini, off, _ = _clubs(c, cfg)
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (ini,))
    eid = _event(c, ini)["id"]
    (_, _, _, sig), = logic.channel_due(con)
    _posted(con, eid, sig)
    con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (ini,))
    _collab(c, eid, off)
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(OFF)).status_code == 204
    logic.channel_due(con)
    assert _gone(con) == [] and con.execute("SELECT channel_msg FROM events WHERE id = ?", (eid,)).fetchone()[0] == 77
    past = _event(c, ini, start=3600)["id"]
    _collab(c, past, off)
    (_, _, _, sig), = [x for x in logic.channel_due(con) if x[0]["id"] == past]
    _posted(con, past, sig)
    logic.channel_due(con)
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (logic.core.now() - 3600, past))
    assert c.delete(f"/api/events/{past}/cohost", headers=tma(OFF)).status_code == 204
    logic.channel_due(con)
    assert _gone(con) == [77]


def test_invite_limits_and_mute(env):
    """An initiative: 3 invites a week (taking one back frees nothing); "Don't suggest again" answers as a no, the
    undo opens it again; a priced event never; a declined club not twice."""
    c, cfg = env
    con, ini, off, _ = _clubs(c, cfg)
    others = [logic.create_org(con, None, f"Club{i}", "C", "crown_3d", True) for i in range(4)]
    codes = [c.put(f"/api/events/{_event(c, ini)['id']}/cohost", headers=tma(INI), json={"orgId": o}).status_code for o in others]
    assert codes == [200, 200, 200, 429]
    con.execute("DELETE FROM meta WHERE key LIKE 'cohost_wk:%'")
    eid = _event(c, ini)["id"]
    assert c.put(f"/api/events/{eid}/cohost", headers=tma(INI), json={"orgId": off}).status_code == 200
    asks = c.get(f"/api/orgs/{off}/cohosts", headers=tma(OFF)).json()
    assert asks[0]["channel"] is True and asks[0]["event"]["price"] is None and "description" in asks[0]["event"]
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(OFF), json={"yes": True, "mute": True}).status_code == 400
    assert c.post(f"/api/events/{eid}/cohost/answer", headers=tma(OFF), json={"yes": False, "mute": True}).status_code == 200
    again = _event(c, ini)["id"]
    r = c.put(f"/api/events/{again}/cohost", headers=tma(INI), json={"orgId": off})
    assert r.status_code == 409 and r.json()["message"] == "declined"
    assert c.delete(f"/api/orgs/{off}/mutes/{ini}", headers=tma(OFF_HEAD)).status_code == 403
    assert c.delete(f"/api/orgs/{off}/mutes/{ini}", headers=tma(OFF)).status_code == 204
    assert c.put(f"/api/events/{again}/cohost", headers=tma(INI), json={"orgId": off}).status_code == 200
    # free only: the initiative can't price (as before), and a priced event of a club that lost the mark can't invite
    body = {**EV, "title": "Paid", "startsAt": logic.core.now() + 86400, "price": 1000, "payToName": "A B", "payPhone": "+77010000000"}
    assert c.post(f"/api/orgs/{ini}/events", headers=tma(INI), json=body).status_code in (400, 403)
    con.execute("DELETE FROM meta WHERE key LIKE 'cohost_wk:%'")
    priced = _event(c, ini)["id"]
    con.execute("UPDATE events SET price = 1000, pay_to_name = 'A B', pay_phone = '+77010000000' WHERE id = ?", (priced,))
    assert c.put(f"/api/events/{priced}/cohost", headers=tma(INI), json={"orgId": others[0]}).status_code == 400


def test_names_that_pose_as_a_collab_or_an_official_club(env):
    c, cfg = env
    con, ini, off, _ = _clubs(c, cfg)
    for bad in ("JCC × Crystal", "Crystal x Anime", "JCC Hub", "JCC-Fans", "Anime \uff58 Crew", "Anime \u2a09 Crew"):
        r = c.patch(f"/api/orgs/{ini}", headers=tma(INI), json={"name": bad})
        assert r.status_code in (400, 409), bad
    assert c.patch(f"/api/orgs/{ini}", headers=tma(INI), json={"name": "Anime Society"}).status_code == 200


def _crew(c, eid, tg, uid, kind="scan", who=INI):
    return c.put(f"/api/events/{eid}/crew", headers=tma(who), json={"userId": uid, "kind": kind})


def test_door_helpers(env):
    """A running club's President or Vice gives a KBTU student the scanner (tickets of people going, no list, no walk-in)
    or the whole door; max 3; banned or unverified: no; gone with the co-host that gave it; logged; account deletion."""
    c, cfg = env
    con, ini, off, uid = _clubs(c, cfg)
    eid = _event(c, ini, start=600)["id"]  # the door is open
    _collab(c, eid, off)
    assert _crew(c, eid, FRIEND, uid(FRIEND), who=OFF_HEAD).status_code == 403  # a Head can't
    assert _crew(c, eid, FRIEND, uid(FRIEND), kind="boss").status_code == 400
    assert _crew(c, eid, INI, uid(INI)).status_code == 400  # not myself
    c.get("/api/me", headers=tma(999))
    assert _crew(c, eid, 999, uid(999)).status_code == 400  # not a confirmed student
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (off, uid(GUEST)))
    assert _crew(c, eid, GUEST, uid(GUEST)).status_code == 403  # banned by the co-host
    assert _crew(c, eid, FRIEND, uid(FRIEND)).status_code == 200
    assert _crew(c, eid, FRIEND2, uid(FRIEND2), kind="door", who=OFF).status_code == 200
    assert _crew(c, eid, FRIEND3, uid(FRIEND3)).status_code == 200
    assert _crew(c, eid, FRIEND4, uid(FRIEND4)).status_code == 429  # 3 an event
    assert _crew(c, eid, FRIEND2, uid(FRIEND2), kind="scan").status_code == 409  # the co-host's helper is theirs
    view = c.get(f"/api/events/{eid}", headers=tma(INI)).json()
    assert len(view["crew"]) == 3 and c.get(f"/api/events/{eid}", headers=tma(FRIEND)).json()["crew"] is None
    assert c.get(f"/api/events/{eid}", headers=tma(FRIEND)).json()["myCrew"] == "scan"
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'crew_put'").fetchone()[0] == 3
    row = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'crew_added' AND user_id = ?", (uid(FRIEND),)).fetchone()) | {"lang": "en"}
    assert "Anime Quiz" in bot._render(con, row)[0]
    # the scanner helper: a ticket yes, a badge of someone not going no, the list no, their own ticket no
    code = c.post(f"/api/events/{eid}/registration", headers=tma(FRIEND4), json={}).json()["my"]["ticketCode"]
    S = tma(FRIEND)
    assert c.post(f"/api/events/{eid}/checkin", headers=S, json={"code": code}).json()["result"] == "ok"
    badge = "u_" + c.get("/api/me", headers=tma(FRIEND3)).json()["qr"]
    assert c.post(f"/api/events/{eid}/checkin", headers=S, json={"code": badge}).json()["result"] == "not_found"
    assert not con.execute("SELECT 1 FROM registrations WHERE event_id = ? AND user_id = ?", (eid, uid(FRIEND3))).fetchone()
    assert c.get(f"/api/events/{eid}/door", headers=S).status_code == 403
    assert c.post(f"/api/events/{eid}/checkin", headers=S, json={"userId": uid(FRIEND4)}).status_code == 403
    assert c.get(f"/api/events/{eid}/attendees", headers=S).status_code == 403
    mine = c.post(f"/api/events/{eid}/registration", headers=S, json={}).json()["my"]["ticketCode"]
    assert c.post(f"/api/events/{eid}/checkin", headers=S, json={"code": mine}).status_code == 403
    # the whole door: the list of short names and a badge walk-in
    D = tma(FRIEND2)
    assert c.get(f"/api/events/{eid}/door", headers=D).status_code == 200
    assert c.post(f"/api/events/{eid}/checkin", headers=D, json={"code": badge}).json()["result"] == "ok"
    assert c.get(f"/api/events/{eid}/attendees", headers=D).status_code == 403
    # the co-host leaves: its helper's right goes with it; the host's stays
    assert c.delete(f"/api/events/{eid}/cohost", headers=tma(OFF)).status_code == 204
    assert c.get(f"/api/events/{eid}/door", headers=D).status_code == 403
    assert c.get(f"/api/events/{eid}", headers=S).json()["myCrew"] == "scan"
    # banned later by the host: gone at once; taken back: gone
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (ini, uid(FRIEND3)))
    assert c.get(f"/api/events/{eid}", headers=tma(FRIEND3)).json()["myCrew"] is None
    assert c.delete(f"/api/events/{eid}/crew/{uid(FRIEND)}", headers=tma(OFF)).status_code == 403  # no longer running it
    assert c.delete(f"/api/events/{eid}/crew/{uid(FRIEND)}", headers=tma(INI)).status_code == 200
    assert c.get(f"/api/events/{eid}", headers=S).json()["myCrew"] is None
    assert bot._render(con, row) is None
    # over: no right, no new helper
    assert _crew(c, eid, FRIEND, uid(FRIEND)).status_code == 200
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (logic.core.now() - 7200, logic.core.now() - 60, eid))
    assert c.get(f"/api/events/{eid}", headers=S).json()["myCrew"] is None
    assert _crew(c, eid, FRIEND4, uid(FRIEND4)).status_code == 409
    delete_now(c, cfg, S)
    assert con.execute("SELECT COUNT(*) FROM event_crew").fetchone()[0] == 2  # FRIEND2's and FRIEND3's rows stay; FRIEND's went
    assert json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'crew_drop'").fetchone()[0]) == {}  # the log forgets the deleted helper


def test_for_whom_apart_from_required(env):
    """"For whom" (a department or the whole team) and "required" are independent: all four combinations. A
    department's event: its people see it and are on the door list, the club's Vice+ see it but aren't expected, others
    don't see it; only a required one sends the invitations."""
    c, cfg = env
    pres, head, mem, mem2 = login(c, 80, "pres"), login(c, 81, "head"), login(c, 82, "mem"), login(c, 83, "mem2")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at, probation) VALUES (1, ?, ?, 0, 0)",
                    [(pres["id"], "president"), (head["id"], "head"), (mem["id"], "member"), (mem2["id"], "member")])
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (5, 1, 'SMM', '#FF4FA3', 0)")
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (5, ?)", (mem2["id"],))
    H = tma(81, "Head")
    start = logic.core.now() + 3600
    base = {"title": "Sync", "place": "305", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF",
            "seats": None, "visibility": "members"}
    assert c.post("/api/orgs/1/events", headers=H, json={**base, "visibility": "public", "meetingTag": 5}).status_code == 400  # team-only only
    assert c.post("/api/orgs/1/events", headers=H, json={**base, "meetingTag": 5, "forBoard": True}).status_code == 400  # one "for whom"
    P, Hd, Mm, M2 = pres["id"], head["id"], mem["id"], mem2["id"]
    # "for whom" -> (who sees it, who is expected); a meeting invites the expected but the publisher
    cases = {"all": ({P, Hd, Mm, M2}, {P, Hd, Mm, M2}), "tag": ({P, Hd, M2}, {M2}), "board": ({P, Hd}, {P, Hd})}
    for meeting in (False, True):
        for who, (seen, expected) in cases.items():
            con.execute("DELETE FROM bot_outbox")
            ev = c.post("/api/orgs/1/events", headers=H, json={**base, "meeting": meeting, "meetingTag": 5 if who == "tag" else None,
                                                                "forBoard": who == "board"}).json()
            assert (ev["meeting"], ev["meetingTag"], ev["forBoard"]) == (meeting, 5 if who == "tag" else None, who == "board")
            c.post(f"/api/events/{ev['id']}/publish", headers=H)
            sees = {u["id"] for u, tg, n in ((pres, 80, "Pres"), (head, 81, "Head"), (mem, 82, "Mem"), (mem2, 83, "Mem2"))
                    if c.get(f"/api/events/{ev['id']}", headers=tma(tg, n)).status_code == 200}
            assert sees == seen, (meeting, who)
            studio = {u["id"] for u, tg, n in ((pres, 80, "Pres"), (head, 81, "Head"), (mem, 82, "Mem"), (mem2, 83, "Mem2"))
                      if ev["id"] in [x["id"] for x in c.get("/api/orgs/1/events", headers=tma(tg, n)).json()]}
            assert studio == seen, (meeting, who)  # Studio's list says no more (adversarial review 2)
            invited = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'meeting_invite'")}
            assert invited == (expected - {Hd} if meeting else set()), (meeting, who)
            door = {d["person"]["id"] for d in c.get(f"/api/events/{ev['id']}/door", headers=H).json()}
            assert door == expected, (meeting, who)
            if who != "all":  # a member it isn't for has no door to it either
                assert c.get(f"/api/events/{ev['id']}/door", headers=tma(82, "Mem")).status_code == 403
    # the board follows the roles: mem made a Head is on it now
    con.execute("UPDATE org_members SET role = 'head' WHERE user_id = ?", (Mm,))
    assert Mm in {d["person"]["id"] for d in c.get(f"/api/events/{ev['id']}/door", headers=H).json()}


def test_a_helper_loses_the_door_when_the_event_turns_team_only(env):
    """Adversarial review 1: a helper's right is for a public event; made team-only, the door is the team's."""
    c, cfg = env
    con, ini, off, uid = _clubs(c, cfg)
    e = _event(c, ini, start=600)
    assert _crew(c, e["id"], FRIEND, uid(FRIEND), kind="door").status_code == 200
    body = {**EV, "title": "Anime Quiz", "startsAt": e["startsAt"], "visibility": "members", "seats": None}
    assert c.patch(f"/api/events/{e['id']}", headers=tma(INI), json=body).status_code == 200
    assert c.get(f"/api/events/{e['id']}/door", headers=tma(FRIEND)).status_code == 403


def test_a_hidden_collab_leaves_the_channel(env):
    """Adversarial review 3: a moderator hides a collab: the official club's name leaves the channel with it."""
    c, cfg = env
    con, ini, off, _ = _clubs(c, cfg)
    eid = _event(c, ini)["id"]
    _collab(c, eid, off)
    (_, _, _, sig), = logic.channel_due(con)
    _posted(con, eid, sig)
    logic.channel_due(con)
    con.execute("UPDATE events SET hidden_at = 1 WHERE id = ?", (eid,))
    logic.channel_due(con)
    assert _gone(con) == [77]
