"""A round's interview place changes (a club lead, Nov 19: the venue moved and nobody could be told): the casting team
edits a slot's place; the shortlisted it concerns get one fixed notice a couple of minutes later, rendered from what
is current then; three such notices a round a day, more edits save quietly."""
from __future__ import annotations

import calendar
import dataclasses
import string

from fastapi.testclient import TestClient

from kbtu import app as server, casting, db, logic, outbox, texts
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)

PRES, ANN, BOB, CAT, DAN, EVE = 80, 81, 82, 83, 84, 85
HOUR = 3600
T0 = calendar.timegm((2033, 5, 18, 12, 0, 0)) - 5 * HOUR  # noon in Almaty


def _setup(env, monkeypatch):
    """Ann booked slot A, Cat slot B, Bob was invited and picked nothing, Eve is shortlisted but not invited, Dan a maybe."""
    _, cfg = env
    clock = [T0]
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(casting, "now", lambda: clock[0])
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset())))
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (PRES, ANN, BOB, CAT, DAN, EVE)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, ids[PRES], oid, "president", "test")
    boss = logic.Viewer(ids[PRES], "user", True)
    rid = casting.open_round(con, boss, oid, {"title": "Fall", "closesAt": T0 + 86400, "departments": []})["id"]
    you = {tg: logic.Viewer(ids[tg], "user", True) for tg in (ANN, BOB, CAT, DAN, EVE)}
    apps = {}
    for tg in (ANN, BOB, CAT, DAN, EVE):
        casting.apply(con, you[tg], rid, {"departments": [], "answers": {}})
        apps[tg] = con.execute("SELECT id FROM round_apps WHERE user_id = ?", (ids[tg],)).fetchone()[0]
    add = "INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, ?, 50, 'Room 305')"
    a, b = con.execute(add, (rid, T0 + 2 * HOUR, 120)).lastrowid, con.execute(add, (rid, T0 + 5 * HOUR, 60)).lastrowid
    for tg in (ANN, BOB, CAT):
        casting.decide(con, boss, apps[tg], {"stage": "next"})
    casting.invite(con, boss, rid)
    casting.decide(con, boss, apps[EVE], {"stage": "next"})  # shortlisted after the invitations went
    casting.decide(con, boss, apps[DAN], {"stage": "maybe"})
    casting.book(con, you[ANN], rid, {"slotId": a})
    casting.book(con, you[CAT], rid, {"slotId": b})
    return c, con, clock, rid, apps, {"a": a, "b": b}


def _patch(c, sid, place, who=PRES):
    return c.patch(f"/api/round-slots/{sid}", headers=tma(who), json={"place": place})


def _notices(con):
    return con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_place' ORDER BY b.id").fetchall()


def _app_of(row):
    return int(row["ref"].split(":")[1])


def test_only_the_team_and_only_plain_places(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    assert _patch(c, slot["a"], "Hall 1", who=ANN).status_code == 403
    for bad in ("", "   ", "x" * 121, "Hall\n2", "Hall\t2", "https://zoom.us/j/1", "www.kbtu.kz", "t.me/club", "@chessclub", "zoom://room",
                "HTTP hall", "example.com", "Go to site.kz", "a.kz", "Room \u202e503", "Room\u200b 5", "Hall \u2066A\u2069", "\uff45\uff58.com"):
        assert _patch(c, slot["a"], bad).status_code == 400, bad
    for good in ("\u0430\u0443\u0434. 305", "\u043a\u043e\u0440\u043f.2", "1.5 \u044d\u0442\u0430\u0436", "Eng.Lab 305", "Room 305, Main building"):
        assert _patch(c, slot["a"], good).status_code == 200, good
    assert _patch(c, slot["a"], "Room 305, Main building").json()["notice"] == "none"  # unchanged: nothing more to tell
    assert _patch(c, 999999, "Hall 1").status_code == 404


def test_who_hears_it_once_and_the_last_place_wins(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    r = _patch(c, slot["a"], "  Hall   1 ")
    assert r.status_code == 200 and r.json()["notice"] == "sent"
    assert [s["place"] for s in r.json()["slots"]] == ["Hall 1", "Room 305"]
    clock[0] += 30
    assert _patch(c, slot["a"], "Main building, 2nd floor").json()["notice"] == "sent"
    rows = _notices(con)
    assert sorted(_app_of(x) for x in rows) == sorted([apps[ANN], apps[BOB]])  # booked on it, invited with no time; not Cat, Dan, Eve
    assert all(x["send_after"] == T0 + 120 and x["ref"].split(":")[2] == str(slot["a"]) for x in rows)
    for x in rows:
        text, button, start = outbox._render(con, x)
        assert "Main building, 2nd floor" in text and "Hall 1" not in text and start.startswith("iv_")
        assert "14:00\u201316:00" in text  # slot A, Almaty time, start to end
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'round_place'").fetchone()[0] == 2
    clock[0] = T0 + 4 * HOUR + 1
    assert [outbox._render(con, x) for x in _notices(con)] == [None, None]  # slot A ended


def test_the_notice_is_about_the_edited_slot(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    _patch(c, slot["b"], "Hall 2")  # the later slot: Cat (on it) and Bob (no time yet) hear about B itself
    rows = {_app_of(x): x for x in _notices(con)}
    assert set(rows) == {apps[CAT], apps[BOB]}
    assert "17:00\u201318:00" in outbox._render(con, rows[apps[BOB]])[0] and "Hall 2" in outbox._render(con, rows[apps[BOB]])[0]
    bob = con.execute("SELECT user_id FROM round_apps WHERE id = ?", (apps[BOB],)).fetchone()[0]
    casting.book(con, logic.Viewer(bob, "user", True), rid, {"slotId": slot["a"]})  # booked elsewhere before it went
    assert outbox._render(con, rows[apps[BOB]]) is None and outbox._render(con, rows[apps[CAT]])


def test_a_dropped_slot_takes_its_waiting_notices(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    new = con.execute("INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, 60, 50, 'Room 1')", (rid, clock[0] + 8 * HOUR)).lastrowid
    con.commit()
    _patch(c, new, "Room 2")  # Bob (no time yet) is to hear about it
    assert [_app_of(x) for x in _notices(con)] == [apps[BOB]]
    assert c.delete(f"/api/round-slots/{new}", headers=tma(PRES)).status_code == 200
    assert not _notices(con)  # SQLite may give its id to the next slot made: the old notice must not speak for that one


def test_a_full_slot_tells_only_its_own(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    con.execute("UPDATE round_slots SET capacity = 1 WHERE id = ?", (slot["b"],))  # Cat fills it
    _patch(c, slot["b"], "Hall 2")
    assert [_app_of(x) for x in _notices(con)] == [apps[CAT]]
    con.execute("UPDATE round_slots SET capacity = 2 WHERE id = ?", (slot["b"],))
    _patch(c, slot["b"], "Hall 3")
    bob = next(x for x in _notices(con) if _app_of(x) == apps[BOB])
    con.execute("UPDATE round_slots SET capacity = 1 WHERE id = ?", (slot["b"],))  # full again before it went
    assert outbox._render(con, bob) is None


def test_edited_back_says_nothing(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    _patch(c, slot["a"], "Hall 1")
    _patch(c, slot["a"], "Room 305")  # back to what it was before the waiting notice
    assert [outbox._render(con, x) for x in _notices(con)] == [None, None]
    _patch(c, slot["a"], "Hall 7")
    assert all("Hall 7" in outbox._render(con, x)[0] for x in _notices(con))


def test_decided_or_withdrawn_hear_nothing(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    _patch(c, slot["a"], "Hall 1")
    boss = logic.Viewer(con.execute("SELECT user_id FROM org_members WHERE role = 'president'").fetchone()[0], "user", True)
    casting.decide(con, boss, apps[BOB], {"stage": "no"})
    ann = con.execute("SELECT user_id FROM round_apps WHERE id = ?", (apps[ANN],)).fetchone()[0]
    casting.withdraw(con, logic.Viewer(ann, "user", True), rid)
    assert [outbox._render(con, x) for x in _notices(con)] == [None, None]


def test_an_ended_slot_or_a_done_round_is_refused(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    clock[0] = T0 + 4 * HOUR  # slot A (14:00-16:00) is over
    assert _patch(c, slot["a"], "Hall 1").status_code == 409
    con.execute("UPDATE rounds SET status = 'done' WHERE id = ?", (rid,))
    assert _patch(c, slot["b"], "Hall 1").status_code == 409


def test_three_notices_a_day(env, monkeypatch):
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    for i in range(3):
        assert _patch(c, slot["a"], f"Hall {i}").json()["notice"] == "sent"
        con.execute("UPDATE bot_outbox SET sent_at = ? WHERE kind = 'round_place'", (clock[0],))  # each went out
        clock[0] += 600
    r = _patch(c, slot["a"], "Hall 9").json()
    assert r["notice"] == "limit" and r["slots"][0]["place"] == "Hall 9"
    assert len(_notices(con)) == 6 and all(x["sent_at"] for x in _notices(con))  # two people, three times; nothing new
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'round_place'").fetchone()[0] == 4
    # a waiting notice carries later edits, but not past eight saved edits a day: the ninth is refused
    for i in range(4):
        assert _patch(c, slot["a"], f"Room {i}").status_code == 200
    r = _patch(c, slot["a"], "Room 99")
    assert r.status_code == 429 and con.execute("SELECT place FROM round_slots WHERE id = ?", (slot["a"],)).fetchone()[0] == "Room 3"


def test_the_texts_name_the_same_fields():
    fields = [{f for _, f, _, _ in string.Formatter().parse(texts.BOT[lang]["round_place"][0]) if f} for lang in ("ru", "kk", "en")]
    assert fields[0] == fields[1] == fields[2] == {"org", "when", "place"}
    assert all(texts.BOT[lang]["round_place"][1] == texts.BOT[lang]["round_iv_remind"][1] for lang in ("ru", "kk", "en"))
