"""Secret Santa on an event (logic/santa.py): the wishlist is required at sign-up and kept from the organizers; the draw
needs three, runs once, is one cycle with nobody giving to themselves, and closes sign-up; a pair is read by its giver
alone (not the organizer, the app's admin from Admin, another participant); who steps out or deletes their account is
passed over, so nobody still in is left without a Santa."""
from __future__ import annotations

from kbtu import bot
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
