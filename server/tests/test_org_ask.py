"""An organizer reaching an attendee: a rejected receipt's reason in the bot's message, and "Write in Telegram" on a
seated person's row (one @username at a time, audited, capped; never in the list)."""
from __future__ import annotations

import json
import re
import time

import pytest

from kbtu import bot, logic, receipt, texts
from kbtu.logic import organizing, seats
from kbtu import auth
from test_core import BOT, env, login, set_clock, tma  # noqa: F401 (env is a fixture)
from test_event_teams import _event, _go
from test_paid_teams import _rid
from test_review_seats import _shot
from test_team_guests import PAID, _club, _uid


@pytest.fixture
def paid(env, monkeypatch):
    c, cfg = env
    con = _club(c, cfg)  # tg 20 the president of club 1; 10, 11, 12 students
    now = int(time.time())
    set_clock(monkeypatch, lambda: now)
    eid = _event(c, **PAID)
    monkeypatch.setattr(receipt, "read", lambda im: {"amount": 1500, "recipient": "Arman A.", "no": "1", "paid_at": now})
    return c, con, eid, now


def _seat(c, con, eid, tg):
    """tg signs up and sends a receipt (short): a ticket waiting on the organizer's look."""
    assert _go(c, eid, tg).json()["my"]["status"] == "hold"
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(tg), content=_shot(200 + tg)).json()["my"]["status"] == "going"
    return _rid(con, eid, tg)


def _review(c, rid, **body):
    return c.post(f"/api/receipts/{rid}/review", headers=tma(20), json=body)


def _rejected(con, tg):
    m = con.execute("""SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id
        WHERE b.user_id = ? AND b.kind = 'receipt_rejected'""", (_uid(con, tg),)).fetchone()
    assert m
    return m


# ---- A: the reason on a rejected receipt

def test_reject_with_a_reason_names_it(paid):
    c, con, eid, _ = paid
    rid = _seat(c, con, eid, 10)
    assert _review(c, rid, reject=True, why="short").status_code == 204
    m = _rejected(con, 10)
    assert json.loads(m["payload"]) == {"why": "short"}
    text, button, _ = bot._render(con, m)
    assert texts.REJECT_WHY["ru"]["short"] in text and button == texts.BOT["ru"]["receipt_rejected"][1]
    for lang in ("kk", "en"):
        assert texts.REJECT_WHY[lang]["short"] in bot._render(con, {**dict(m), "lang": lang})[0]
    a = con.execute("SELECT data FROM audit_log WHERE action = 'receipt_reject' AND target = ?", (f"receipt:{rid}",)).fetchone()
    assert json.loads(a["data"]) == {"why": "short"}
    assert con.execute("SELECT status, cancel_reason FROM registrations WHERE event_id = ? AND user_id = ?", (eid, _uid(con, 10))).fetchone()[1] == "receipt_rejected"


def test_reject_without_a_reason_keeps_the_old_text(paid):
    c, con, eid, _ = paid
    rid = _seat(c, con, eid, 10)
    assert _review(c, rid, reject=True).status_code == 204
    m = _rejected(con, 10)
    assert m["payload"] == "{}"
    assert bot._render(con, m)[0] == texts.bot_message("ru", "receipt_rejected", title="Case Cup", org="IT Club")[0]


@pytest.mark.parametrize("body", [{"reject": True, "why": "rude"}, {"reject": True, "why": 1}, {"reject": False, "why": "short"},
                                  {"reject": True, "why": ""}])
def test_reason_codes_are_checked(paid, body):
    c, con, eid, _ = paid
    rid = _seat(c, con, eid, 10)
    r = _review(c, rid, **body)
    assert r.status_code == 400 and r.json()["error"] == "bad_input"
    assert con.execute("SELECT status FROM receipts WHERE id = ?", (rid,)).fetchone()[0] == "accepted"  # nothing changed


def test_a_member_cant_reject_with_a_reason(paid):
    c, con, eid, _ = paid
    rid = _seat(c, con, eid, 10)
    logic.set_role(con, None, _uid(con, 11), 1, "member", "test")
    assert c.post(f"/api/receipts/{rid}/review", headers=tma(11), json={"reject": True, "why": "used"}).status_code == 403


def test_reasons_and_placeholders_match_in_three_languages():
    fields = lambda s: set(re.findall(r"{(\w+)}", s))  # noqa: E731
    ru = texts.BOT["ru"]["receipt_rejected_why"][0]
    assert fields(ru) == {"title", "org", "why"}
    for lang in ("ru", "kk", "en"):
        assert fields(texts.BOT[lang]["receipt_rejected_why"][0]) == fields(ru)
        assert set(texts.REJECT_WHY[lang]) == set(seats.REJECT_WHY)


# ---- B: "Write in Telegram" on an attendee's row

def _contact(c, eid, uid, tg=20):
    return c.get(f"/api/events/{eid}/people/{uid}/contact", headers=tma(tg))


def _named(con, tg, name):
    con.execute("UPDATE users SET tg_username = ? WHERE tg_id = ?", (name, tg))


def _reveals(con):
    return con.execute("SELECT actor_id, target, data FROM audit_log WHERE action = 'attendee_contact'").fetchall()


def test_organizer_gets_one_username_audited_once(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    _go(c, eid, 11)  # a hold: waiting on its receipt
    _named(con, 10, "ali_k")
    _named(con, 11, "bob_k")
    assert _contact(c, eid, _uid(con, 10)).json() == {"username": "ali_k"}
    assert _contact(c, eid, _uid(con, 10)).json() == {"username": "ali_k"}  # again the same day: one line
    assert _contact(c, eid, _uid(con, 11)).json() == {"username": "bob_k"}
    assert [(r["actor_id"], r["target"], json.loads(r["data"])) for r in _reveals(con)] == [
        (_uid(con, 20), f"user:{_uid(con, 10)}", {"event": eid}), (_uid(con, 20), f"user:{_uid(con, 11)}", {"event": eid})]
    # the list never carries usernames
    body = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).text
    assert "ali_k" not in body and "bob_k" not in body


def test_no_username_is_null_and_unlogged(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    assert _contact(c, eid, _uid(con, 10)).json() == {"username": None, "asked": False}
    assert _reveals(con) == []


def test_only_the_host_clubs_organizer(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    _named(con, 10, "ali_k")
    login(c, 30, "dan")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (2, 'art', 'club', 'Art', 'A', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'president', 0)", (_uid(con, 30),))
    logic.set_role(con, None, _uid(con, 11), 1, "member", "test")
    for tg in (11, 30, 12, 10):  # a plain member, another club's president, a stranger, the attendee
        assert _contact(c, eid, _uid(con, 10), tg).status_code == 403, tg
    assert _reveals(con) == []


def test_only_a_live_seat_on_this_event(paid):
    c, con, eid, now = paid
    other = _event(c, title="Other")
    _go(c, other, 12)  # seated on another event of the same club only
    _seat(c, con, eid, 10)
    _named(con, 12, "cat_k")
    _named(con, 10, "ali_k")
    assert _contact(c, eid, _uid(con, 12)).status_code == 404
    assert _contact(c, eid, _uid(con, 20)).status_code == 404  # myself
    c.delete(f"/api/events/{eid}/people/{_uid(con, 10)}", headers=tma(20))  # removed
    assert _contact(c, eid, _uid(con, 10)).status_code == 404
    _go(c, eid, 11)
    con.execute("UPDATE registrations SET status = 'cancelled', cancel_reason = 'self' WHERE user_id = ?", (_uid(con, 11),))
    assert _contact(c, eid, _uid(con, 11)).status_code == 404
    con.execute("UPDATE registrations SET status = 'waitlist', cancel_reason = NULL WHERE user_id = ?", (_uid(con, 11),))
    assert _contact(c, eid, _uid(con, 11)).status_code == 404
    con.execute("UPDATE registrations SET status = 'hold', hold_until = ? WHERE user_id = ?", (now - 1, _uid(con, 11)))
    assert _contact(c, eid, _uid(con, 11)).status_code == 404  # a hold that ran out
    assert _reveals(con) == []


def test_a_week_after_the_end_its_closed(paid, monkeypatch):
    c, con, eid, now = paid
    _seat(c, con, eid, 10)
    _named(con, 10, "ali_k")
    end = con.execute("SELECT ends_at FROM events WHERE id = ?", (eid,)).fetchone()[0]
    set_clock(monkeypatch, lambda: end + organizing.REVEAL_AFTER - 60)
    assert _contact(c, eid, _uid(con, 10)).json() == {"username": "ali_k"}
    set_clock(monkeypatch, lambda: end + organizing.REVEAL_AFTER + 60)
    assert _contact(c, eid, _uid(con, 10)).json()["error"] == "closed"


@pytest.mark.parametrize("who", ["attendee", "organizer"])
def test_a_block_either_way_reads_as_no_username(paid, who):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    _named(con, 10, "ali_k")
    a, o = _uid(con, 10), _uid(con, 20)
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (a, o) if who == "attendee" else (o, a))
    assert _contact(c, eid, a).json() == {"username": None, "asked": False}
    assert _reveals(con) == []
    assert _ask(c, eid, a).json() == {"asked": True}  # as if sent: the block isn't shown
    assert _asks(con) == [] and _reveals(con) == []


def test_forty_a_day(paid, monkeypatch):
    c, con, eid, now = paid
    _seat(c, con, eid, 10)
    _named(con, 10, "ali_k")
    o = _uid(con, 20)
    for i in range(organizing.REVEALS_A_DAY):
        logic.log_action(con, o, "attendee_contact", f"user:{100000 + i}", json.dumps({"event": eid}))
    r = _contact(c, eid, _uid(con, 10))
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    con.execute("UPDATE audit_log SET at = ? WHERE action = 'attendee_contact'", (now - 86401,))  # a day on: room again
    assert _contact(c, eid, _uid(con, 10)).json() == {"username": "ali_k"}


# ---- no username: the bot asks them to write to the organizer

def _ask(c, eid, uid, tg=20, nick="pres_k"):
    """The organizer's own @username comes with his sign-in (Telegram's init data), as in the app."""
    init = {"id": tg, "first_name": "Test", **({"username": nick} if nick else {})}
    return c.post(f"/api/events/{eid}/people/{uid}/ask", headers={"Authorization": "tma " + auth.sign_init_data(init, BOT)})


def _asks(con):
    return con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'org_ask'").fetchall()


def test_ask_to_write_goes_once(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    a = _uid(con, 10)
    assert _contact(c, eid, a).json() == {"username": None, "asked": False}
    assert _ask(c, eid, a).json() == {"asked": True}
    assert _ask(c, eid, a).json() == {"asked": True}  # a repeat: nothing more
    m = _asks(con)
    assert [(x["user_id"], x["ref"]) for x in m] == [(a, f"oa:{eid}:{_uid(con, 20)}")]
    assert [r["target"] for r in con.execute("SELECT target FROM audit_log WHERE action = 'attendee_ask'")] == [f"user:{a}"]
    text, button, keys = bot._render(con, m[0])
    assert text == texts.bot_message("ru", "org_ask", title="Case Cup", org="IT Club")[0]
    assert keys == [[{"text": texts.BOT["ru"]["org_ask"][1], "url": "https://t.me/pres_k"}]]
    assert "pres_k" not in text  # only behind the button
    assert _contact(c, eid, a).json() == {"username": None, "asked": True}
    _named(con, 20, "pres_k")  # (the plain test sign-in above carried no username)
    logic.set_role(con, None, _uid(con, 20), 1, "member", "test")  # no longer the organizer: the message stays unsent
    assert bot._render(con, m[0]) is None


def test_ask_needs_my_own_username_and_the_same_checks(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    a = _uid(con, 10)
    r = _ask(c, eid, a, nick=None)
    assert r.status_code == 400 and r.json()["message"] == "own_username"
    logic.set_role(con, None, _uid(con, 11), 1, "member", "test")
    assert _ask(c, eid, a, 11).status_code == 403
    assert _ask(c, eid, _uid(con, 12)).status_code == 404  # no seat
    assert _asks(con) == []


def test_asks_count_toward_the_forty(paid):
    c, con, eid, _ = paid
    _seat(c, con, eid, 10)
    for i in range(organizing.REVEALS_A_DAY):
        logic.log_action(con, _uid(con, 20), "attendee_contact", f"user:{100000 + i}", json.dumps({"event": eid}))
    assert _ask(c, eid, _uid(con, 10)).json()["error"] == "rate_limited"
    assert _asks(con) == []


def test_org_ask_placeholders_match():
    for lang in ("kk", "en"):
        assert set(re.findall(r"{(\w+)}", texts.BOT[lang]["org_ask"][0])) == {"title", "org"}
