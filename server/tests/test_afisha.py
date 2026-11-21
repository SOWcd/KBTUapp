"""A student initiative's events and the general afisha (seats.on_afisha, owner, Nov 6): not there by themselves; on
the club's page, for its members, for whoever signed up or saved, by link, and with an official co-host. Three
people's reports of an event ring the moderators at once (moderation._urgent_event); it stays up."""
from __future__ import annotations

from kbtu import bot, db, logic, texts
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

EV = {"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF", "seats": 50}
INIT, OFF, MEMBER, SIGNED, SAVER, OTHER, MOD = 20, 21, 22, 23, 24, 25, 90


def _setup(c, cfg):
    for tg, name in ((INIT, "init"), (OFF, "off"), (MEMBER, "memb"), (SIGNED, "sign"), (SAVER, "save"), (OTHER, "other"),
                     (MOD, "mod"), (31, "rone"), (32, "rtwo"), (33, "rthree")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    init = logic.create_org(con, None, "Initiative", "IN", "crown_3d", False)
    off = logic.create_org(con, None, "Official", "OF", "crown_3d", True)
    logic.set_role(con, None, uid(INIT), init, "president", "test")
    logic.set_role(con, None, uid(MEMBER), init, "member", "test")
    logic.set_role(con, None, uid(OFF), off, "president", "test")
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = ?", (MOD,))
    return con, init, off


def _event(c, org, who, title):
    e = c.post(f"/api/orgs/{org}/events", headers=tma(who), json={**EV, "title": title, "startsAt": logic.core.now() + 86400}).json()
    return c.post(f"/api/events/{e['id']}/publish", headers=tma(who)).json()["id"]


def _afisha(c, who, **q):
    return {e["id"] for e in c.get("/api/events", headers=tma(who), params=q).json()}


def test_initiative_events_stay_off_the_afisha(env):
    c, cfg = env
    con, init, off = _setup(c, cfg)
    mine, collab, theirs = _event(c, init, INIT, "Ours"), _event(c, init, INIT, "Collab"), _event(c, off, OFF, "Theirs")
    assert _afisha(c, OTHER) == {theirs}  # the official club's only
    assert c.get(f"/api/events/{mine}", headers=tma(OTHER)).status_code == 200  # by link
    assert _afisha(c, OTHER, org=init) == {mine, collab}  # the club's own page
    assert _afisha(c, MEMBER) == {mine, collab, theirs}  # its members
    assert c.post(f"/api/events/{mine}/registration", headers=tma(SIGNED)).status_code == 200
    assert c.put(f"/api/events/{mine}/saved", headers=tma(SAVER)).status_code == 204
    assert _afisha(c, SIGNED) == _afisha(c, SAVER) == {mine, theirs}
    # an official co-host takes it to the afisha
    assert c.put(f"/api/events/{collab}/cohost", headers=tma(INIT), json={"orgId": off}).status_code == 200
    assert c.post(f"/api/events/{collab}/cohost/answer", headers=tma(OFF), json={"yes": True}).status_code == 200
    assert _afisha(c, OTHER) == {theirs, collab}
    # the past list and the assistant's "coming events" follow the same rule
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id IN (?, ?)", (logic.core.now() - 7200, logic.core.now() - 3600, mine, theirs))
    assert {e["id"] for e in c.get("/api/events/past", headers=tma(OTHER)).json()} == {theirs}
    assert {e["id"] for e in c.get("/api/events/past", headers=tma(MEMBER)).json()} == {mine, theirs}
    # 60 newer past events of the initiative don't push the official one out of the 50 (filtered before the LIMIT)
    for _ in range(60):
        con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
            SELECT org_id, status, title, place, starts_at + 60, ends_at + 60, emoji, color, created_by, created_at, updated_at FROM events WHERE id = ?""", (mine,))
    assert {e["id"] for e in c.get("/api/events/past", headers=tma(OTHER)).json()} == {theirs}
    other = logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = ?", (OTHER,)).fetchone()[0], "user", True)
    assert logic.assistant.brief(con, other)[2] == {collab, theirs}  # both started within its window


def test_past_is_the_last_month_for_everyone_mine_marked(env):
    """Afisha's "Past" (issue #72): every afisha event that ended in the last 30 days, not only mine; the card's `my`
    says I was there (signed up, or checked in); a club's page and "mine" still reach further back."""
    c, cfg = env
    con, init, off = _setup(c, cfg)
    went, came, missed, old = (_event(c, off, OFF, t) for t in ("Went", "Came", "Missed", "Old"))
    for eid in (went, came, old):
        assert c.post(f"/api/events/{eid}/registration", headers=tma(SIGNED)).status_code == 200
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ?", (logic.core.now() - 86400, came))
    now, day = logic.core.now(), 86400
    for eid, ago in ((went, 2), (came, 29), (missed, 10), (old, 31)):
        con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (now - ago * day - 3600, now - ago * day, eid))
    con.execute("UPDATE events SET ends_at = NULL WHERE id = ?", (missed,))  # no end: counts as 3 h long

    past = {e["id"]: e for e in c.get("/api/events/past", headers=tma(SIGNED)).json()}
    assert list(past) == [went, missed, came]  # newest first; a month and a day ago is gone
    assert past[went]["my"]["status"] == "going" and past[came]["my"]["checkedInAt"] and past[missed]["my"] is None
    assert [e["id"] for e in c.get("/api/events/past", headers=tma(OTHER)).json()] == [went, missed, came]  # for everyone
    assert all(e["my"] is None for e in c.get("/api/events/past", headers=tma(OTHER)).json())
    assert {e["id"] for e in c.get("/api/events/past?mine=1", headers=tma(SIGNED)).json()} == {went, came, old}
    assert [e["id"] for e in c.get("/api/events/past?attended=1", headers=tma(SIGNED)).json()] == [came]
    assert c.get("/api/events/past?attended=1", headers=tma(OTHER)).json() == []
    assert old in {e["id"] for e in c.get(f"/api/events/past?org={off}", headers=tma(OTHER)).json()}


def _report(c, who, eid):
    return c.post("/api/reports", headers=tma(who), json={"target": "event", "id": eid, "reason": "danger"})


def test_three_reports_ring_the_moderators(env):
    c, cfg = env
    con, init, _ = _setup(c, cfg)
    eid = _event(c, init, INIT, "Party")
    rung = lambda: con.execute("SELECT *, 'ru' AS lang FROM bot_outbox WHERE kind = 'event_reported'").fetchall()  # noqa: E731
    for tg in (31, 32):
        assert _report(c, tg, eid).status_code == 204
    assert _report(c, 31, eid).status_code == 204  # the same person again: still two
    assert not rung()
    assert _report(c, 33, eid).status_code == 204
    m = rung()
    assert [r["user_id"] for r in m] == [con.execute("SELECT id FROM users WHERE tg_id = ?", (MOD,)).fetchone()[0]]
    assert bot._render(con, m[0]) == (*texts.bot_message("ru", "event_reported"), "capps")
    assert c.get(f"/api/events/{eid}", headers=tma(OTHER)).status_code == 200  # not hidden: a moderator decides
    assert [(x["target"], x["id"], x["count"]) for x in c.get("/api/admin/reports", headers=tma(MOD)).json()] == [("event", eid, 3)]
    assert c.post(f"/api/admin/reports/event/{eid}", headers=tma(MOD), json={"remove": False}).status_code == 204
    assert bot._render(con, m[0]) is None  # decided: nothing to ring about
    for tg in (31, 32, 33):  # a new round rings again
        _report(c, tg, eid)
    assert len(rung()) == 2
