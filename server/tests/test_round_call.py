"""A window's "come over" (a club lead, Nov 19: at the venue, the only way to call the shortlisted was editing the place):
the casting team calls everyone shortlisted without a result to a window that is on or within two hours; the bot sends
a fixed template once per person and window."""
from __future__ import annotations

import string

from kbtu import bot, casting, logic, texts
from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_round_place import ANN, BOB, CAT, EVE, HOUR, PRES, T0, _setup

FAY, GUS, HAL = 86, 87, 88


def _more(env, monkeypatch):
    """On top of round place's people: Fay booked a window that's past and never came, Gus came, Hal's result went."""
    c, con, clock, rid, apps, slot = _setup(env, monkeypatch)
    boss = logic.Viewer(con.execute("SELECT user_id FROM org_members WHERE role = 'president'").fetchone()[0], "user", True)
    for tg in (FAY, GUS, HAL):
        uid = login(c, tg, f"p{tg}")["id"]
        casting.apply(con, logic.Viewer(uid, "user", True), rid, {"departments": [], "answers": {}})
        apps[tg] = con.execute("SELECT id FROM round_apps WHERE user_id = ?", (uid,)).fetchone()[0]
        casting.decide(con, boss, apps[tg], {"stage": "next"})
    con.execute("UPDATE round_apps SET invited_at = ? WHERE id IN (?, ?, ?)", (T0, apps[FAY], apps[GUS], apps[HAL]))
    past = con.execute("INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, 60, 50, 'Room 1')", (rid, T0 - 3 * HOUR)).lastrowid
    con.execute("UPDATE round_apps SET slot_id = ? WHERE id IN (?, ?)", (past, apps[FAY], apps[GUS]))
    con.execute("UPDATE round_apps SET came = 1 WHERE id = ?", (apps[GUS],))
    con.execute("UPDATE round_apps SET sent_at = ? WHERE id = ?", (T0, apps[HAL]))
    con.commit()
    return c, con, clock, rid, apps, slot


def _call(c, sid, who=PRES):
    return c.post(f"/api/round-slots/{sid}/call", headers=tma(who))


def _calls(con):
    return con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_call' ORDER BY b.id").fetchall()


def test_who_is_called(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    a = next(s for s in c.get(f"/api/rounds/{rid}/slots", headers=tma(PRES)).json() if s["id"] == slot["a"])
    assert a["call"] == {"told": 0, "waiting": 0, "tried": 0, "left": 4}
    r = _call(c, slot["a"])
    assert r.status_code == 200 and r.json()["queued"] == 4
    # booked on it (Ann), on a later one (Cat), on a past one and never came (Fay), no time (Bob); not who came (Gus),
    # whose result went (Hal), a maybe (Dan), the shortlisted never invited (Eve)
    assert sorted(int(x["ref"].split(":")[1]) for x in _calls(con)) == sorted(apps[t] for t in (ANN, BOB, CAT, FAY))
    assert next(s for s in r.json()["slots"] if s["id"] == slot["a"])["call"] == {"told": 0, "waiting": 4, "tried": 4, "left": 0}  # queued, none sent yet
    for x in _calls(con):
        text, button, start = bot._render(con, x)
        assert "Room 305" in text and "14:00–16:00" in text and "<b>Chess" in text and start.startswith("iv_")
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'round_call'").fetchone()[0] == 1


def test_once_per_window(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    assert _call(c, slot["a"]).json()["queued"] == 4
    assert _call(c, slot["a"]).json()["queued"] == 0  # a second tap tells nobody new
    con.execute("UPDATE round_apps SET invited_at = ? WHERE id = ?", (T0, apps[EVE]))
    con.commit()
    assert _call(c, slot["a"]).json()["queued"] == 1  # only who joined since
    assert len(_calls(con)) == 5


def test_the_time_gate_and_the_team_only(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    assert _call(c, slot["a"], who=ANN).status_code == 403
    assert _call(c, slot["b"]).status_code == 409  # starts in five hours
    assert "call" not in next(s for s in c.get(f"/api/rounds/{rid}/slots", headers=tma(PRES)).json() if s["id"] == slot["b"])
    assert _call(c, 999999).status_code == 404
    clock[0] = T0 + 4 * HOUR  # A (14:00-16:00) is over, B starts in an hour
    assert _call(c, slot["a"]).status_code == 409 and _call(c, slot["b"]).status_code == 200
    con.execute("UPDATE rounds SET status = 'done' WHERE id = ?", (rid,))
    con.commit()
    assert _call(c, slot["b"]).status_code == 409


def test_quiet_once_it_no_longer_holds(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    _call(c, slot["a"])
    by = {int(x["ref"].split(":")[1]): x for x in _calls(con)}
    con.execute("UPDATE round_apps SET came = 1 WHERE id = ?", (apps[ANN],))
    con.execute("UPDATE round_apps SET sent_at = ? WHERE id = ?", (T0, apps[BOB]))
    assert bot._render(con, by[apps[ANN]]) is None and bot._render(con, by[apps[BOB]]) is None and bot._render(con, by[apps[CAT]])
    clock[0] = T0 + 4 * HOUR
    assert bot._render(con, by[apps[CAT]]) is None  # the window is over


def test_a_dropped_slot_takes_its_waiting_calls(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    new = con.execute("INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, 60, 50, 'Room 2')", (rid, T0 + HOUR)).lastrowid
    con.commit()
    _call(c, new)
    assert len(_calls(con)) == 4
    assert c.delete(f"/api/round-slots/{new}", headers=tma(PRES)).status_code == 200
    assert not _calls(con)


def test_the_texts_name_the_same_fields():
    fields = [{f for _, f, _, _ in string.Formatter().parse(texts.BOT[lang]["round_call"][0]) if f} for lang in ("ru", "kk", "en")]
    assert fields[0] == fields[1] == fields[2] == {"org", "when", "place"}


def test_told_is_what_went(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    _call(c, slot["a"])
    by = {int(x["ref"].split(":")[1]): x["id"] for x in _calls(con)}
    con.execute("UPDATE bot_outbox SET sent_at = ? WHERE id IN (?, ?)", (T0, by[apps[ANN]], by[apps[BOB]]))
    con.execute("UPDATE bot_outbox SET error = 'blocked' WHERE id = ?", (by[apps[CAT]],))  # never reached them
    con.commit()
    a = next(s for s in c.get(f"/api/rounds/{rid}/slots", headers=tma(PRES)).json() if s["id"] == slot["a"])
    assert a["call"] == {"told": 2, "waiting": 1, "tried": 4, "left": 0}


def test_an_invited_applicant_still_sees_the_round_after_the_intake_closed(env, monkeypatch):
    c, con, clock, rid, apps, slot = _more(env, monkeypatch)
    con.execute("UPDATE rounds SET status = 'closed', closes_at = ? WHERE id = ?", (T0 - 1, rid))
    con.commit()
    oid = con.execute("SELECT org_id FROM rounds WHERE id = ?", (rid,)).fetchone()[0]
    you = lambda tg: logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0], "user", True)  # noqa: E731
    seen = casting.view(con, you(BOB), oid)
    assert seen and not seen["open"] and seen["mine"]["invited"]  # invited, no result: their time and the call, no new applications
    assert casting.view(con, you(EVE), oid) is None  # shortlisted, never invited
    assert c.post(f"/api/rounds/{rid}/apply", headers=tma(BOB), json={"departments": [], "answers": {}}).status_code != 200
