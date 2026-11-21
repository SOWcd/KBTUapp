"""Secret Santa on an event (logic/santa.py): the wishlist is required at sign-up and kept from the organizers; the draw
needs three, runs once, is one cycle with nobody giving to themselves, and closes sign-up; a pair is read by its giver
alone (not the organizer, the app's admin from Admin, another participant); who steps out or deletes their account is
passed over, so nobody still in is left without a Santa."""
from __future__ import annotations

import time

from kbtu import admin, bot, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)
from test_team_guests import _club, _event, _uid

PLAYERS = (10, 11, 12, 13, 14)


def _go(c, eid, tg, wish=None):
    return c.post(f"/api/events/{eid}/registration", headers=tma(tg), json={"wish": wish} if wish else {})


def _page(c, eid, tg, **headers):
    return c.get(f"/api/events/{eid}", headers={**tma(tg), **headers}).json()


def _draw(c, eid, tg=20):
    return c.post(f"/api/events/{eid}/santa/draw", headers=tma(tg))


def _game(c, cfg, n=5):
    con = _club(c, cfg)
    for tg in (13, 14, 15):
        login(c, tg, f"p{tg}")
    eid = _event(c, santa=True)
    for tg in PLAYERS[:n]:
        assert _go(c, eid, tg, f"wish of {tg}").json()["my"]["status"] == "going"
    return con, eid


def _gives(c, con, eid, tgs):
    """tg -> the tg they give to, as each one's own page says."""
    back = {_uid(con, tg): tg for tg in tgs}
    return {tg: back[_page(c, eid, tg)["mySanta"]["to"]["person"]["id"]] for tg in tgs}


def test_sign_up_draw_and_who_reads_what(env):
    c, cfg = env
    con, eid = _game(c, cfg, 2)
    assert _page(c, eid, 15)["santa"] == {"drawn": False}
    for bad in (None, " ", "x" * 301):
        r = _go(c, eid, 15, bad)
        assert r.status_code == 400 and r.json()["message"] == "wish", r.text  # no wishlist, no sign-up
    assert con.execute("SELECT 1 FROM registrations WHERE user_id = ?", (_uid(con, 15),)).fetchone() is None
    assert _draw(c, eid).json()["message"] == "few"  # two are not a game
    assert _draw(c, eid, 10).status_code == 403  # a participant doesn't draw
    for tg in PLAYERS[2:]:
        _go(c, eid, tg, f"wish of {tg}")
    assert _page(c, eid, 20)["santaN"] == 5 and "santaN" not in _page(c, eid, 10)
    assert _page(c, eid, 10)["mySanta"] == {"wish": "wish of 10"}
    c.delete(f"/api/events/{eid}/registration", headers=tma(14))  # changed their mind before the draw: not in it
    assert _draw(c, eid).json()["santa"] == {"drawn": True}
    assert _draw(c, eid).json()["message"] == "drawn"  # once
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={"title": "Case", "place": "Hall", "startsAt": _page(c, eid, 20)["startsAt"],
                                                                  "emoji": "laptop_3d", "color": "#3B6BFF", "santa": False}).json()["message"] == "santa"
    r = _go(c, eid, 15, "late")
    assert r.status_code == 409 and r.json()["error"] == "closed"  # sign-up closed with the draw
    con.execute("UPDATE events SET reg_until = NULL WHERE id = ?", (eid,))  # reopened by hand: still nobody new
    assert _go(c, eid, 15, "late").status_code == 409
    # one cycle through the four still in, nobody themselves
    gives = _gives(c, con, eid, PLAYERS[:4])
    at, ring = 10, []
    for _ in range(4):
        ring.append(at)
        at = gives[at]
    assert at == 10 and sorted(ring) == list(PLAYERS[:4]) and all(a != b for a, b in gives.items())
    assert _page(c, eid, 10)["mySanta"]["to"]["wish"] == f"wish of {gives[10]}"
    # nobody else reads a pair or a wishlist: the organizer, a stranger, the one who left, the app's admin from Admin
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 15")
    for who in (_page(c, eid, 20), _page(c, eid, 15), _page(c, eid, 14), _page(c, eid, 15, **{"X-Staff-Event": str(eid)})):
        assert "mySanta" not in who and "wish of" not in str(who)
    seen = c.get(f"/api/events/{eid}/attendees", headers=tma(20))
    assert seen.status_code == 200 and "wish of" not in seen.text and "gives" not in seen.text
    assert con.execute("SELECT answers FROM registrations WHERE event_id = ? AND answers IS NOT NULL", (eid,)).fetchone() is None
    assert "wish of" not in str([tuple(r) for r in con.execute("SELECT * FROM bot_outbox").fetchall() + con.execute("SELECT * FROM audit_log").fetchall()])
    # the bot tells each one once, a template into the event
    sent = con.execute("SELECT *, 'en' AS lang FROM bot_outbox WHERE kind = 'santa_drawn'").fetchall()
    assert sorted(m["user_id"] for m in sent) == sorted(_uid(con, tg) for tg in PLAYERS[:4])
    order = [m["user_id"] for m in sorted(sent, key=lambda m: m["id"])]
    assert order == sorted(order)  # queued by user id: the outbox's ids don't spell out the ring (review, P1)
    text, _, start = bot._render(con, sent[0])
    assert start == f"ev_{eid}" and "Testov" not in text and "wish of" not in text


def test_leavers_are_passed_over(env):
    c, cfg = env
    con, eid = _game(c, cfg, 4)
    assert _draw(c, eid).status_code == 200
    gives = _gives(c, con, eid, PLAYERS[:4])
    a = 10
    b, x, y = gives[a], gives[gives[a]], gives[gives[gives[a]]]
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))  # b steps out: a gives to b's person
    assert "mySanta" not in _page(c, eid, b)
    assert _gives(c, con, eid, (a, x, y)) == {a: x, x: y, y: a}
    # out for good (review, P2): a seat given back (a walk-in at the door) brings no Santa back and undoes no relink
    con.execute("UPDATE registrations SET status = 'going', cancel_reason = NULL WHERE event_id = ? AND user_id = ?", (eid, _uid(con, b)))
    assert _page(c, eid, b)["my"]["status"] == "going" and "mySanta" not in _page(c, eid, b)
    assert _gives(c, con, eid, (a, x, y)) == {a: x, x: y, y: a}
    delete_now(c, cfg, tma(x))  # x deletes the account: a gives to x's person
    assert con.execute("SELECT 1 FROM santa_people WHERE user_id = ? OR gives_to = ?", (_uid(con, x) or 0,) * 2).fetchone() is None
    assert _gives(c, con, eid, (a, y)) == {a: y, y: a}
    c.delete(f"/api/events/{eid}/registration", headers=tma(y))
    assert _page(c, eid, a)["mySanta"]["to"] is None  # alone: "ask the organizer"


def test_nobody_lands_in_a_drawn_game(env):
    """Review, P2: no draw over a seat still being paid for; no promotion from the waitlist after it; no switching it
    on over people already signed up."""
    c, cfg = env
    con = _club(c, cfg)
    login(c, 13, "p13")
    eid = _event(c, santa=True, seats=3)
    for tg in PLAYERS[:4]:
        _go(c, eid, tg, f"wish of {tg}")
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (_uid(con, 13),)).fetchone()[0] == "waitlist"
    con.execute("UPDATE registrations SET status = 'hold' WHERE user_id = ?", (_uid(con, 13),))
    assert _draw(c, eid).json()["message"] == "holds"
    con.execute("UPDATE registrations SET status = 'waitlist' WHERE user_id = ?", (_uid(con, 13),))
    assert _draw(c, eid).status_code == 200
    c.delete(f"/api/events/{eid}/registration", headers=tma(10))
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (_uid(con, 13),)).fetchone()[0] == "waitlist"  # the seat stays empty
    assert _gives(c, con, eid, (11, 12)) == {11: 12, 12: 11}
    plain = _event(c)
    c.post(f"/api/events/{plain}/registration", headers=tma(10), json={})
    body = {"title": "Case", "place": "Hall", "startsAt": _page(c, plain, 20)["startsAt"], "emoji": "laptop_3d", "color": "#3B6BFF"}
    r = c.patch(f"/api/events/{plain}", headers=tma(20), json={**body, "santa": True})
    assert r.status_code == 409 and r.json()["message"] == "santa_signed"
    c.delete(f"/api/events/{plain}/registration", headers=tma(10))
    assert c.patch(f"/api/events/{plain}", headers=tma(20), json={**body, "santa": True}).json()["santa"] == {"drawn": False}


def _start(c, tg, org=1, **body):
    return c.post(f"/api/orgs/{org}/santa", headers=tma(tg), json={"title": "Secret Santa", "startsAt": int(time.time()) + 20 * 86400, "budget": 3000, **body})


def test_one_button_starts_the_game(env):
    """Studio's button (santa.start): a published team-only Santa event at once; a second tap returns the running one."""
    c, cfg = env
    con = _club(c, cfg)
    assert _start(c, 10).status_code == 403  # not of the club
    logic.set_role(con, None, _uid(con, 10), 1, "member", "test")
    assert _start(c, 10).status_code == 403  # a member has no events right
    con.execute("UPDATE users SET can_dm = 1")  # they opened the bot
    assert _start(c, 20, startsAt=1).status_code == 409  # a day in the past: nothing published, no draft left behind
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    e = _start(c, 20).json()
    assert (e["status"], e["visibility"], e["santa"], e["title"]) == ("published", "members", {"drawn": False, "budget": 3000}, "Secret Santa")
    assert _start(c, 20).json()["id"] == e["id"]
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    # the team hears once (a team-only event tells nobody by itself), the starter doesn't
    told = [r[0] for r in con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'santa_open'")]
    assert told == [10]
    assert _go(c, e["id"], 10, "tea").json()["my"]["status"] == "going"  # the team joins; a stranger doesn't see it
    assert _page(c, e["id"], 11).get("error") == "not_found"
    logic.daily.tba_day(con)  # no room to confirm: its maker isn't nagged
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'place_tba'").fetchone() is None


def test_santa_news(env, capsys, monkeypatch):
    """`kbtu.admin santa-news`: once to each President and Vice of an active org the bot can write to; --dry only counts."""
    c, cfg = env
    con = _club(c, cfg)
    for tg in (10, 11, 12, 20):
        logic.set_role(con, None, _uid(con, tg), 1, {10: "vice", 11: "member", 12: "vice", 20: "president"}[tg], "test")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'laptop_3d', 0)")
    logic.set_role(con, None, _uid(con, 20), 2, "president", "test")  # two clubs: one message
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("UPDATE users SET can_dm = 0 WHERE tg_id = 12")  # never opened the bot
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    sent = lambda: sorted(r[0] for r in con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'santa_news'"))  # noqa: E731
    admin.main(["santa-news", "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 2" and sent() == []
    admin.main(["santa-news", "20"])  # one person first; the full run then skips them
    assert capsys.readouterr().out.strip() == "queued 1" and sent() == [20]
    admin.main(["santa-news"])
    assert capsys.readouterr().out.strip() == "queued 1" and sent() == [10, 20]
    admin.main(["santa-news"])
    assert capsys.readouterr().out.strip() == "queued 0" and sent() == [10, 20]  # again: nothing new
    admin.main(["santa-news", "20"])  # reworded: the one-person send reads it again
    assert capsys.readouterr().out.strip() == "queued 1"
    m = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'santa_news' AND u.tg_id = 20").fetchone()
    text, button, start = bot._render(con, m)
    assert start == "sn_1" and "IT Club" in text and button
    logic.set_role(con, None, _uid(con, 20), 1, "member", "test")
    assert bot._render(con, m) is None  # no longer its President: quiet


# ---------------------------------------------------------------- round 2: budget, deadline, the clock, reminders

DAY = 86400


def _team_game(c, cfg, members=(10, 11, 12), **body):
    """A team-only game started from Studio (tg 20 its President); `members` in the club, the bot can write to all."""
    con = _club(c, cfg)
    for tg in (13, 14, 15):
        login(c, tg, f"p{tg}")
    for tg in members:
        logic.set_role(con, None, _uid(con, tg), 1, "member", "test")
    con.execute("UPDATE users SET can_dm = 1")
    e = _start(c, 20, **body).json()
    return con, e["id"]


def _out(con, kind):
    return con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = ? ORDER BY id", (kind,)).fetchall()


def _to(con, kind):
    return sorted(r[0] for r in con.execute("SELECT u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = ?", (kind,)))


def _past(con, eid, at=None):
    """The wishlists' deadline moved into the past by hand (the API refuses a past one)."""
    con.execute("UPDATE events SET reg_until = ? WHERE id = ?", (at or int(time.time()) - 5, eid))


def test_budget_and_deadline(env):
    c, cfg = env
    starts = int(time.time()) + 20 * DAY
    con = _club(c, cfg)
    for bad in ({"budget": None}, {"budget": 0}, {"budget": 50}, {"budget": True}, {"budget": "5000"}, {"budget": 2_000_000},
                {"regUntil": int(time.time()) - 60}, {"regUntil": starts + 60}):
        r = _start(c, 20, startsAt=starts, **bad)
        assert r.status_code == 400, (bad, r.text)
        assert ("budget" not in bad) or r.json()["message"] == "budget"  # no sum is refused by name: the gift's limit is required
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0  # nothing left behind
    e = _start(c, 20, startsAt=starts).json()  # the default deadline: a week before the gifts day
    assert e["santa"] == {"drawn": False, "budget": 3000} and e["regUntil"] == starts - 7 * DAY
    eid = e["id"]
    put = lambda tg, **b: c.put(f"/api/events/{eid}/santa", headers=tma(tg), json=b)  # noqa: E731
    assert put(10, budget=5000).status_code == 403  # not who runs it
    until = int(time.time()) + 3 * DAY
    x = put(20, budget=5000, regUntil=until).json()
    assert x["santa"] == {"drawn": False, "budget": 5000} and x["regUntil"] == until
    assert put(20, regUntil=starts + 1).status_code == 400
    assert put(20, budget=None).json()["message"] == "budget"  # never cleared
    assert put(20, budget=7000).json()["santa"]["budget"] == 7000
    # a game from before the sum was required: it shows none, its deadline alone still changes
    con.execute("UPDATE santa_games SET budget = NULL WHERE event_id = ?", (eid,))
    assert put(20, regUntil=until + 60).json()["santa"] == {"drawn": False}
    put(20, budget=7000)
    # the invite, as the bot renders it: the budget a number, the date the server's
    logic.set_role(con, None, _uid(con, 10), 1, "member", "test")
    logic.santa.notify(con, _uid(con, 10), "santa_open", f"event:{eid}")
    text, button, start = bot._render(con, _out(con, "santa_open")[0])
    assert "7 000 ₽" not in text and "7 000 ₸" in text and "IT Club" in text and start == f"ev_{eid}"
    # a game closer than a week: the deadline halfway there, never past, never after the gifts day
    near = int(time.time()) + 2 * DAY
    assert logic.santa.default_until(near) - int(time.time()) in range(DAY - 5, DAY + 5)


def test_deadline_draws_by_itself(env):
    c, cfg = env
    con, eid = _team_game(c, cfg)
    for tg in (10, 11):
        _go(c, eid, tg, f"wish of {tg}")
    _past(con, eid)
    logic.santa.tick(con)  # two: no draw; the President hears it once
    assert _page(c, eid, 20)["santa"]["drawn"] is False
    assert _to(con, "santa_few") == [20]
    text, _, start = bot._render(con, _out(con, "santa_few")[0])
    assert start == f"mg_{eid}" and " 2" in text
    logic.santa.tick(con)
    assert len(_out(con, "santa_few")) == 1  # once per deadline, the round doesn't read it again
    # the President extends the deadline: a third joins, and the new deadline draws
    assert c.put(f"/api/events/{eid}/santa", headers=tma(20), json={"regUntil": int(time.time()) + 3600}).status_code == 200
    assert _go(c, eid, 12, "wish of 12").json()["my"]["status"] == "going"
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'hold', 'h13', 0, 0)",
                (eid, _uid(con, 13)))  # someone paying for a seat (as on a paid game)
    _past(con, eid, int(time.time()) - 100)  # another deadline than the one acted on
    logic.santa.tick(con)  # a seat being paid for: no draw yet, no message, the next round tries again
    assert _page(c, eid, 20)["santa"]["drawn"] is False and len(_out(con, "santa_few")) == 1
    con.execute("UPDATE registrations SET status = 'cancelled' WHERE user_id = ?", (_uid(con, 13),))  # the hold ran out
    logic.santa.tick(con)
    assert _page(c, eid, 20)["santa"]["drawn"] is True
    assert _to(con, "santa_drawn") == [10, 11, 12]
    assert bot._render(con, _out(con, "santa_few")[0]) is None  # drawn since: the old message is quiet
    logic.santa.tick(con)
    assert len(_out(con, "santa_drawn")) == 3


def test_draw_happens_once_under_concurrency(env):
    """Two workers' rounds and a hand on the button at the same moment: one draw (BEGIN IMMEDIATE serialises them)."""
    import threading
    from kbtu import db
    c, cfg = env
    con, eid = _team_game(c, cfg)
    for tg in (10, 11, 12):
        _go(c, eid, tg, f"wish of {tg}")
    _past(con, eid)
    gate, out = threading.Barrier(3), []

    def worker():
        mine = db.connect(cfg.db_path)
        gate.wait()
        out.append(logic.santa._deadline(mine, eid))

    def hand():
        gate.wait()
        out.append(_draw(c, eid).status_code)
    th = [threading.Thread(target=worker), threading.Thread(target=worker), threading.Thread(target=hand)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert sum(x is None or x == 200 for x in out) == 1, out  # exactly one drew
    assert len(_out(con, "santa_drawn")) == 3
    gives = _gives(c, con, eid, (10, 11, 12))
    assert gives[gives[gives[10]]] == 10 and len(set(gives.values())) == 3


def test_reminders_once_each(env):
    c, cfg = env
    con, eid = _team_game(c, cfg, members=(10, 11, 12, 13, 14), budget=3000)
    _go(c, eid, 10, "wish of 10")
    con.execute("UPDATE users SET can_dm = 0 WHERE tg_id = 13")  # never opened the bot
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 14")
    # the President's list and button before anyone was reminded
    team = _page(c, eid, 20)["santaTeam"]
    assert [p["id"] for p in team["in"]] == [_uid(con, 10)] and team["remind"] == 2  # 11 and 12: never who presses it; 13 unreachable, 14 banned
    assert {p["id"] for p in team["out"]} == {_uid(con, tg) for tg in (11, 12, 13, 20)} and "wish" not in str(team)
    assert "santaTeam" not in _page(c, eid, 10) and c.post(f"/api/events/{eid}/santa/remind", headers=tma(10)).status_code == 403
    r = c.post(f"/api/events/{eid}/santa/remind", headers=tma(20)).json()
    assert r["n"] == 2 and r["nudgeAt"] > time.time()
    assert c.post(f"/api/events/{eid}/santa/remind", headers=tma(20)).json()["message"] == "soon"  # once a day
    assert _to(con, "santa_nudge") == [11, 12]
    assert _page(c, eid, 20)["santaTeam"]["remind"] == 0 and _page(c, eid, 20)["santaTeam"]["remindAt"]
    con.execute("UPDATE santa_games SET nudged_at = 1 WHERE event_id = ?", (eid,))  # a day later: nobody twice
    assert c.post(f"/api/events/{eid}/santa/remind", headers=tma(20)).json()["n"] == 0
    # a day before the deadline: those not in yet, once
    con.execute("UPDATE events SET reg_until = ? WHERE id = ?", (int(time.time()) + 3600, eid))
    logic.santa.tick(con)
    logic.santa.tick(con)
    assert _to(con, "santa_soon") == [11, 12]  # never to who started the game (20): they set the deadline
    soon = {m["user_id"]: m for m in _out(con, "santa_soon")}
    text, _, start = bot._render(con, soon[_uid(con, 11)])
    assert start == f"ev_{eid}" and "3 000 ₸" in text
    _go(c, eid, 11, "wish of 11")  # joined since: quiet
    assert bot._render(con, soon[_uid(con, 11)]) is None
    con.execute("DELETE FROM org_members WHERE user_id = ?", (_uid(con, 12),))  # left the club: quiet
    assert bot._render(con, soon[_uid(con, 12)]) is None
    # the gifts day's eve, to those playing, once
    _go(c, eid, 20, "wish of 20")
    _go(c, eid, 15, "x")  # not of the club: a team-only event refuses
    _past(con, eid)
    logic.santa.tick(con)
    assert _page(c, eid, 20)["santa"]["drawn"]
    con.execute("UPDATE santa_events SET drawn_at = ? WHERE event_id = ?", (int(time.time()) - 5 * DAY, eid))
    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (int(time.time()) + 3600, eid))  # gifts day moved after the draw
    logic.santa.tick(con)
    logic.santa.tick(con)
    assert _to(con, "santa_eve") == [10, 11, 20]
    text, _, start = bot._render(con, _out(con, "santa_eve")[0])
    assert start == f"ev_{eid}" and "\u0417\u0430\u0432\u0442\u0440\u0430" in text  # "Tomorrow" in Russian
    assert [m["user_id"] for m in _out(con, "santa_eve")] == sorted(m["user_id"] for m in _out(con, "santa_eve"))  # never the ring's order


def test_list_after_the_draw_and_leavers_before_it(env):
    """Before the draw a banned person and one who left the club are not drawn; after it the organizer sees a count."""
    c, cfg = env
    con, eid = _team_game(c, cfg, members=(10, 11, 12, 13, 14))
    for tg in (10, 11, 12, 13, 14):
        _go(c, eid, tg, f"wish of {tg}")
    con.execute("DELETE FROM org_members WHERE user_id = ?", (_uid(con, 13),))
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 14")
    assert _page(c, eid, 20)["santaN"] == 3
    assert _draw(c, eid).status_code == 200
    p = _page(c, eid, 20)
    assert p["santaN"] == 3 and "santaTeam" not in p
    assert "mySanta" not in _page(c, eid, 13)
    assert sorted(_gives(c, con, eid, (10, 11, 12))) == [10, 11, 12]
    # after the draw, leaving the club takes the seat (its page no longer opens for them): the ring relinks, and with
    # two left both hear they give to each other
    logic.set_role(con, None, _uid(con, 11), 1, "none", "test")
    assert _gives(c, con, eid, (10, 12)) == {10: 12, 12: 10}
    assert sorted(m["user_id"] for m in _out(con, "santa_two")) == [_uid(con, 10), _uid(con, 12)] and not _out(con, "santa_changed")
    assert c.put(f"/api/events/{eid}/santa", headers=tma(20), json={"budget": 1000}).json()["message"] == "drawn"


def test_their_santa_hears_the_person_changed(env):
    c, cfg = env
    con, eid = _game(c, cfg, 4)
    assert _draw(c, eid).status_code == 200
    gives = _gives(c, con, eid, PLAYERS[:4])
    giver = {b: a for a, b in gives.items()}
    b = gives[10]
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))
    sent = _out(con, "santa_changed")
    assert [m["user_id"] for m in sent] == [_uid(con, giver[b])]
    assert str(_uid(con, b)) not in sent[0]["ref"].split(":")[2:] and len(sent[0]["ref"].split(":")) == 3  # no leaver in it
    text, _, start = bot._render(con, sent[0])
    assert start == f"ev_{eid}" and "Testov" not in text
    # deleting an account: the same
    left = [tg for tg in PLAYERS[:4] if tg != b]
    gives = _gives(c, con, eid, left)
    x = next(tg for tg in left if tg != 10)
    who = {v: k for k, v in gives.items()}[x]
    assert who  # x's Santa, before x goes
    delete_now(c, cfg, tma(x))  # three were left, now two: both hear they give to each other, nobody "changed"
    rest = [tg for tg in left if tg != x]
    assert len(_out(con, "santa_changed")) == 1
    assert sorted(m["user_id"] for m in _out(con, "santa_two")) == sorted(_uid(con, tg) for tg in rest)


def test_cancelled_game_and_two_clubs(env):
    c, cfg = env
    con, eid = _team_game(c, cfg)
    for tg in (10, 11, 12):
        _go(c, eid, tg, f"wish of {tg}")
    logic.santa.notify(con, _uid(con, 13), "santa_open", f"event:{eid}")
    # a second club's game: tg 10 plays both, each its own ring
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'laptop_3d', 0)")
    logic.set_role(con, None, _uid(con, 13), 2, "president", "test")
    for tg in (10, 14, 15):
        logic.set_role(con, None, _uid(con, tg), 2, "member", "test")
    other = _start(c, 13, org=2).json()["id"]
    for tg in (10, 14, 15):
        _go(c, other, tg, f"chess {tg}")
    assert _draw(c, eid).status_code == 200 and _draw(c, other, 13).status_code == 200
    assert _page(c, eid, 10)["mySanta"]["wish"] == "wish of 10" and _page(c, other, 10)["mySanta"]["wish"] == "chess 10"
    assert _page(c, other, 10)["mySanta"]["to"]["wish"].startswith("chess")
    # cancelled: everyone in hears it once (event_cancelled); the game's own messages go quiet
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).status_code == 200
    assert _to(con, "event_cancelled") == [10, 11, 12]
    assert all(bot._render(con, m) is None for m in _out(con, "santa_drawn") if m["ref"] == f"event:{eid}")
    assert bot._render(con, _out(con, "santa_open")[0]) is None



# ---------------------------------------------------------------- the review's findings (Nov 18)

def test_santa_is_for_the_whole_team(env):
    """A Santa game is for the whole club: the editor refuses "the board" on it; and should an audience ever narrow it,
    the list, the reminder and the bot's invites keep to whom it is for."""
    c, cfg = env
    con, eid = _team_game(c, cfg, members=(10, 11, 12))
    p = _page(c, eid, 20)
    body = {"title": p["title"], "place": "", "startsAt": p["startsAt"], "emoji": "sparkles_3d", "color": "#D7263D",
            "visibility": "members", "forBoard": True, "regUntil": p["regUntil"]}
    r = c.patch(f"/api/events/{eid}", headers=tma(20), json=body)
    assert r.status_code == 400 and r.json()["message"] == "santa_audience"
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "forBoard": False}).status_code == 200
    con.execute("UPDATE events SET for_board = 1, reg_until = ? WHERE id = ?", (int(time.time()) + 3600, eid))  # some other way
    logic.set_role(con, None, _uid(con, 11), 1, "head", "test")
    team = _page(c, eid, 20)["santaTeam"]
    assert [x["id"] for x in team["out"]] == [_uid(con, 20), _uid(con, 11)] or {x["id"] for x in team["out"]} == {_uid(con, 20), _uid(con, 11)}
    assert team["remind"] == 1  # the head; plain members 10 and 12 can't open it
    logic.santa.tick(con)
    assert _to(con, "santa_soon") == [11]
    logic.santa.notify(con, _uid(con, 10), "santa_nudge", f"sr:1:{eid}")
    assert bot._render(con, [m for m in _out(con, "santa_nudge") if m["user_id"] == _uid(con, 10)][0]) is None


def test_short_game_no_double_message(env):
    """A deadline under a day away: the invite is the reminder; no "closes tomorrow" seconds after it."""
    c, cfg = env
    con = _club(c, cfg)
    for tg in (10, 11):
        logic.set_role(con, None, _uid(con, tg), 1, "member", "test")
    con.execute("UPDATE users SET can_dm = 1")
    eid = _start(c, 20, startsAt=int(time.time()) + int(1.5 * DAY)).json()["id"]
    logic.santa.tick(con)
    assert _to(con, "santa_open") == [10, 11] and _to(con, "santa_soon") == []
    # a deadline moved to within a day by hand: none either
    c2 = _start(c, 20)  # the running game comes back
    assert c2.json()["id"] == eid
    other = _event(c, santa=True, start=int(time.time()) + 10 * DAY)
    assert c.put(f"/api/events/{other}/santa", headers=tma(20), json={"regUntil": int(time.time()) + 3600}).status_code == 200
    logic.santa.tick(con)
    assert _to(con, "santa_soon") == []


def test_idle_rounds_write_nothing(env):
    """Nothing due: no write, no write lock. A game closed early with too few (told once), a game from before deadlines,
    a game waiting on a seat being paid for."""
    c, cfg = env
    con = _club(c, cfg)
    login(c, 13, "p13")
    few, legacy, held = (_event(c, santa=True) for _ in range(3))
    _go(c, few, 10, "wish of 10")
    assert c.put(f"/api/events/{few}/reg-until", headers=tma(20), json={"until": "now"}).status_code == 200
    con.execute("UPDATE events SET reg_until = NULL WHERE id = ?", (legacy,))
    for tg in (10, 11, 12):
        _go(c, held, tg, f"wish of {tg}")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'hold', 'h13', 0, 0)",
                (held, _uid(con, 13)))
    _past(con, held)
    logic.santa.tick(con)  # the few game: its President told, once
    assert len(_out(con, "santa_few")) == 1
    seen = []
    con.set_trace_callback(lambda q: seen.append(q) if q.lstrip().upper().startswith(("BEGIN", "INSERT", "UPDATE", "DELETE")) else None)
    for _ in range(5):
        logic.santa.tick(con)
    con.set_trace_callback(None)
    assert seen == [] and len(_out(con, "santa_few")) == 1


def test_deadline_an_hour_before_gifts_day(env):
    c, cfg = env
    con, eid = _team_game(c, cfg)
    p = _page(c, eid, 20)
    starts = p["startsAt"]
    put = lambda **b: c.put(f"/api/events/{eid}/santa", headers=tma(20), json=b)  # noqa: E731
    assert put(regUntil=starts).status_code == 400 and put(regUntil=starts - 3599).status_code == 400
    assert put(regUntil=starts - 3600).status_code == 200
    body = {"title": p["title"], "place": "", "startsAt": starts, "emoji": "sparkles_3d", "color": "#D7263D", "visibility": "members"}
    r = c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "regUntil": starts - 60})
    assert r.status_code == 400 and r.json()["message"] == "santa_until"  # the editor too
    assert c.put(f"/api/events/{eid}/reg-until", headers=tma(20), json={"until": starts - 60}).status_code == 400  # and Admin's
    assert _start(c, 20, org=1).json()["id"] == eid
    # cleared in the editor (sign-up until the start): the gifts day comes undrawn, the President hears it once
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**body, "regUntil": None}).json()["regUntil"] is None
    for tg in (10, 11, 12):
        _go(c, eid, tg, f"wish of {tg}")
    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (int(time.time()) - 10, eid))
    logic.santa.tick(con)
    logic.santa.tick(con)
    assert _to(con, "santa_late") == [20]
    text, _, start = bot._render(con, _out(con, "santa_late")[0])
    assert start == f"mg_{eid}" and text
    assert not con.execute("SELECT drawn_at FROM santa_events WHERE event_id = ?", (eid,)).fetchone()[0]  # nothing drawn on its own


def test_start_refuses_a_deadline_at_the_gifts_day(env):
    c, cfg = env
    _club(c, cfg)
    starts = int(time.time()) + 20 * DAY
    assert _start(c, 20, startsAt=starts, regUntil=starts).status_code == 400
    assert _start(c, 20, startsAt=starts, regUntil=starts - 3600).json()["regUntil"] == starts - 3600


def test_ban_takes_the_seat(env):
    """A ban after the draw: they can't open their person any more, so their seat goes (the ring relinks, their Santa
    hears it); lifting it gives nothing back."""
    from kbtu.logic.core import Viewer
    c, cfg = env
    con, eid = _game(c, cfg, 4)
    assert _draw(c, eid).status_code == 200
    gives = _gives(c, con, eid, PLAYERS[:4])
    x = 11
    santa_of_x = {v: k for k, v in gives.items()}[x]
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 20")
    admin = Viewer(_uid(con, 20), "admin", True)
    logic.set_ban(con, admin, _uid(con, x), True, "spam and abuse")
    assert con.execute("SELECT status FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, x))).fetchone()[0] == "cancelled"
    rest = [tg for tg in PLAYERS[:4] if tg != x]
    g = _gives(c, con, eid, rest)
    assert g[santa_of_x] == gives[x] and [m["user_id"] for m in _out(con, "santa_changed")] == [_uid(con, santa_of_x)]
    logic.set_ban(con, admin, _uid(con, x), False)
    assert con.execute("SELECT status FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, x))).fetchone()[0] == "cancelled"
    assert not con.execute("SELECT 1 FROM santa_people WHERE user_id = ?", (_uid(con, x),)).fetchone()


def test_invite_and_reminder_once_a_day_per_club(env):
    """A game stopped and started again: the team isn't invited twice within a day, the start says so; the reminder
    button is once a day per club, whatever the game."""
    c, cfg = env
    con, eid = _team_game(c, cfg)
    assert _to(con, "santa_open") == [10, 11, 12]
    assert c.post(f"/api/events/{eid}/santa/remind", headers=tma(20)).json()["n"] == 3
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).status_code == 200
    again = _start(c, 20).json()
    assert again["id"] != eid and again["santaTold"] == 0 and _to(con, "santa_open") == [10, 11, 12]
    r = c.post(f"/api/events/{again['id']}/santa/remind", headers=tma(20))
    assert r.status_code == 409 and r.json()["message"] == "soon"
    assert _page(c, again["id"], 20)["santaTeam"]["remindAt"] > time.time()


def test_leaving_the_club_moves_the_waitlist(env):
    """Out of the club before the draw: the seat goes the way seats.joined takes one, so the waitlist moves into it."""
    c, cfg = env
    con, eid = _team_game(c, cfg)
    con.execute("UPDATE events SET seats = 2 WHERE id = ?", (eid,))
    for tg in (10, 11, 12):
        _go(c, eid, tg, f"wish of {tg}")
    status = lambda tg: con.execute("SELECT status FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, tg))).fetchone()[0]  # noqa: E731
    assert status(12) == "waitlist"
    logic.set_role(con, None, _uid(con, 11), 1, "none", "test")
    assert (status(11), status(12)) == ("cancelled", "going")
    assert _page(c, eid, 12)["mySanta"] == {"wish": "wish of 12"}


def test_two_left_then_one(env):
    """A drawn game of three loses one: the two left are told they give to each other (each knows it anyway), never
    who left; then one more: the last one is told the game is over for them."""
    c, cfg = env
    con, eid = _game(c, cfg, 3)
    assert _draw(c, eid).status_code == 200
    leaver = _gives(c, con, eid, PLAYERS[:3])[10]
    c.delete(f"/api/events/{eid}/registration", headers=tma(leaver))
    rest = [tg for tg in PLAYERS[:3] if tg != leaver]
    assert not _out(con, "santa_changed")
    two = _out(con, "santa_two")
    assert sorted(m["user_id"] for m in two) == sorted(_uid(con, tg) for tg in rest)
    assert all(str(_uid(con, leaver)) not in m["ref"] for m in two)
    text, _, start = bot._render(con, two[0])
    assert start == f"ev_{eid}" and "Testov" not in text
    c.delete(f"/api/events/{eid}/registration", headers=tma(rest[0]))
    assert [m["user_id"] for m in _out(con, "santa_alone")] == [_uid(con, rest[1])]
    assert bot._render(con, two[0]) is None  # the ring moved on: the old "two of you" stays quiet
    assert bot._render(con, _out(con, "santa_alone")[0])


def test_eve_follows_the_gifts_day(env):
    """The eve's message again when the gifts day moves after it went; never to one whose ring closed on themselves."""
    c, cfg = env
    con, eid = _game(c, cfg, 3)
    assert _draw(c, eid).status_code == 200
    con.execute("UPDATE santa_events SET drawn_at = ? WHERE event_id = ?", (int(time.time()) - 5 * DAY, eid))
    day1 = int(time.time()) + 3600
    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (day1, eid))
    logic.santa.tick(con)
    first = _out(con, "santa_eve")
    assert len(first) == 3
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (day1 + 7200, eid))
    logic.santa.tick(con)
    logic.santa.tick(con)
    assert len(_out(con, "santa_eve")) == 6 and bot._render(con, first[0]) is None
    # two leave: the last one has nobody to give to and gets no "who I give to"
    a, b = PLAYERS[:2]
    c.delete(f"/api/events/{eid}/registration", headers=tma(a))
    c.delete(f"/api/events/{eid}/registration", headers=tma(b))
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (day1 + 9000, eid))
    logic.santa.tick(con)
    assert len(_out(con, "santa_eve")) == 6


def test_migration_on_the_live_shape(env, tmp_path, before_door_migration):
    """Migration 184 on a database at 183 shaped like production's: one running game, undrawn, no deadline, nobody
    in, gifts day Dec 25 (here: in 37 days). It gets a week-before deadline and the next round sends nothing. A game
    whose deadline passed undrawn: its President hears once that it waits for him, and nothing draws."""
    from kbtu import db
    path = str(tmp_path / "live.db")
    db.init(path)
    con = db.connect(path)
    before_door_migration(con)
    con.execute("ALTER TABLE users DROP COLUMN tg_photo_at")  # 194's
    con.executescript("""DROP TABLE reg_age; DROP TABLE event_guests;
        ALTER TABLE events DROP COLUMN age_check; ALTER TABLE events DROP COLUMN guest_list;""")
    con.execute("ALTER TABLE events DROP COLUMN silent_publish")  # 198's
    con.execute("ALTER TABLE org_invites DROP COLUMN consumed")  # 200's
    con.execute("ALTER TABLE events DROP COLUMN door_extra")  # 208's
    con.execute("ALTER TABLE users DROP COLUMN n_forum_comments")  # 206's
    con.executescript("DROP TABLE fchan_hearts; ALTER TABLE users DROP COLUMN forum_seen_msg;")  # 205
    con.executescript("ALTER TABLE events DROP COLUMN online; ALTER TABLE credits DROP COLUMN gh; DROP TABLE santa_games; DROP TRIGGER santa_moved_upd; DROP TRIGGER santa_moved_del; PRAGMA user_version = 183;")
    t = int(time.time())
    con.execute("INSERT INTO users (id, tg_id, tg_first_name, lang, can_dm, created_at, seen_at, qr_code) VALUES (1, 501, 'P', 'ru', 1, 0, 0, 'Q1')")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, 1, 'president', 0)")
    for eid, starts, until in ((1, t + 37 * DAY, None), (2, t + 10 * DAY, t - 100)):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, reg_until, emoji, color, tint, visibility, created_by, created_at, updated_at, published_at)
            VALUES (?, 1, 'published', 'Secret Santa', '', ?, ?, 'sparkles_3d', '#D7263D', '#A01C2E', 'members', 1, 0, 0, 0)""", (eid, starts, until))
        con.execute("INSERT INTO santa_events (event_id) VALUES (?)", (eid,))
    con.close()
    db.init(path)
    con = db.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] >= 184  # and whatever came after it
    assert con.execute("SELECT reg_until FROM events WHERE id = 1").fetchone()[0] == t + 30 * DAY
    assert con.execute("SELECT soon, checked FROM santa_games WHERE event_id = 1").fetchone()[:] == (None, None)
    waits = con.execute("SELECT user_id, kind, ref FROM bot_outbox").fetchall()
    assert [tuple(r) for r in waits] == [(1, "santa_wait", "event:2")]
    logic.santa.tick(con)
    logic.santa.tick(con)
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM santa_events WHERE drawn_at IS NOT NULL").fetchone()[0] == 0


def _rewish(c, eid, tg, wish):
    return c.put(f"/api/events/{eid}/santa/wish", headers=tma(tg), json={"wish": wish})


def test_change_my_wishlist(env):
    """My own wishlist, changed while I'm in: before the draw nobody hears; after it my Santa reads the newest and hears
    it at most once a day, never with my words; nobody else may, and not after the gifts day began."""
    from kbtu.logic.core import Viewer
    c, cfg = env
    con, eid = _game(c, cfg, 4)
    for bad in (None, " ", "x" * 301):
        assert _rewish(c, eid, 10, bad).json()["message"] == "wish"  # the same limits as at sign-up
    assert _rewish(c, eid, 10, "  tea   and\n socks ").json() == {"wish": "tea and socks"}  # and the same cleaning
    assert _page(c, eid, 10)["mySanta"]["wish"] == "tea and socks" and not _out(con, "santa_wish")
    assert _rewish(c, eid, 15, "late").status_code == 403  # not in the game
    assert _draw(c, eid).status_code == 200
    gives = _gives(c, con, eid, PLAYERS[:4])
    santa = {v: k for k, v in gives.items()}[10]
    r = _rewish(c, eid, 10, "a red scarf")
    assert r.json() == {"wish": "a red scarf"} and "gives" not in r.text and str(_uid(con, santa)) not in r.text
    assert _page(c, eid, santa)["mySanta"]["to"]["wish"] == "a red scarf"  # the Santa reads the newest
    sent = _out(con, "santa_wish")
    assert [m["user_id"] for m in sent] == [_uid(con, santa)] and "scarf" not in str(tuple(sent[0]))
    text, _, start = bot._render(con, sent[0])
    assert start == f"ev_{eid}" and "scarf" not in text
    _rewish(c, eid, 10, "a blue scarf")
    assert len(_out(con, "santa_wish")) == 1  # once a day per game
    con.execute("UPDATE bot_outbox SET send_after = send_after - 86401, ref = ref || '0' WHERE kind = 'santa_wish'")
    _rewish(c, eid, 10, "a green scarf")
    assert len(_out(con, "santa_wish")) == 2  # a day on: again
    # the ring moved on (10 left): the queued news for their old Santa goes
    c.delete(f"/api/events/{eid}/registration", headers=tma(10))
    assert not [m for m in _out(con, "santa_wish") if m["sent_at"] is None]
    assert _rewish(c, eid, 10, "back").status_code == 403  # not going any more
    other = next(tg for tg in PLAYERS[:4] if tg not in (10, santa))
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 20")
    logic.set_ban(con, Viewer(_uid(con, 20), "admin", True), _uid(con, other), True, "spam and abuse")
    assert _rewish(c, eid, other, "x y").status_code == 403  # banned
    con.execute("UPDATE events SET starts_at = ?, ends_at = NULL WHERE id = ?", (int(time.time()) - 5, eid))
    assert _rewish(c, eid, santa, "too late").status_code == 409  # the gifts day began
    con.execute("UPDATE events SET starts_at = ?, status = 'cancelled' WHERE id = ?", (int(time.time()) + DAY, eid))
    assert _rewish(c, eid, santa, "cancelled").status_code == 404
