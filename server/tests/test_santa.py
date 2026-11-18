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
    return c.post(f"/api/orgs/{org}/santa", headers=tma(tg), json={"title": "Secret Santa", "startsAt": int(time.time()) + 20 * 86400, **body})


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
    assert (e["status"], e["visibility"], e["santa"], e["title"]) == ("published", "members", {"drawn": False}, "Secret Santa")
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
    for bad in ({"budget": 50}, {"budget": True}, {"budget": "5000"}, {"budget": 2_000_000},
                {"regUntil": int(time.time()) - 60}, {"regUntil": starts + 60}):
        r = _start(c, 20, startsAt=starts, **bad)
        assert r.status_code == 400, (bad, r.text)
    assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0  # nothing left behind
    e = _start(c, 20, startsAt=starts).json()  # no budget, the default deadline: a week before the gifts day
    assert e["santa"] == {"drawn": False} and e["regUntil"] == starts - 7 * DAY
    eid = e["id"]
    put = lambda tg, **b: c.put(f"/api/events/{eid}/santa", headers=tma(tg), json=b)  # noqa: E731
    assert put(10, budget=5000).status_code == 403  # not who runs it
    until = int(time.time()) + 3 * DAY
    x = put(20, budget=5000, regUntil=until).json()
    assert x["santa"] == {"drawn": False, "budget": 5000} and x["regUntil"] == until
    assert put(20, regUntil=starts + 1).status_code == 400
    assert put(20, budget=None).json()["santa"] == {"drawn": False}  # cleared
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
    assert _page(c, eid, 20)["santa"] == {"drawn": False}
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
    assert _page(c, eid, 20)["santa"] == {"drawn": False} and len(_out(con, "santa_few")) == 1
    con.execute("UPDATE registrations SET status = 'cancelled' WHERE user_id = ?", (_uid(con, 13),))  # the hold ran out
    logic.santa.tick(con)
    assert _page(c, eid, 20)["santa"] == {"drawn": True}
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
    assert _to(con, "santa_soon") == [11, 12, 20]
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
    # after the draw, leaving the club takes the seat (its page no longer opens for them): their Santa gets their person, and hears it
    gives = _gives(c, con, eid, (10, 11, 12))
    con.execute("DELETE FROM org_members WHERE user_id = ?", (_uid(con, 11),))
    rest = [tg for tg in (10, 12) if tg != 11]
    assert _gives(c, con, eid, rest) == {10: 12, 12: 10}
    assert [m["user_id"] for m in _out(con, "santa_changed")] == [_uid(con, {v: k for k, v in gives.items()}[11])]
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
    delete_now(c, cfg, tma(x))
    assert [m["user_id"] for m in _out(con, "santa_changed")][1:] == [_uid(con, who)]
    # down to two, one more leaves: the one left alone isn't told of a person (there is none)
    rest = [tg for tg in left if tg != x]
    c.delete(f"/api/events/{eid}/registration", headers=tma(rest[1]))
    assert len(_out(con, "santa_changed")) == 2


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
