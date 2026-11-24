"""The people of the app (logic/credits.py): who is named and who is "Student", the order, the bot's one ask, the
consent's record, and that the API's JSON never carries a Telegram id, a name or a face of someone without a yes."""
from __future__ import annotations

import json

import pytest

from kbtu import admin, bot, db, logic, texts
from kbtu.logic import credits
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)

NO = {"show": False, "consent": credits.CONSENT}


def _con(cfg):
    return db.connect(cfg.db_path)


def _line(con, tg, kind="idea", day="2026-11-01", word=None):
    cid = credits.add(con, tg, kind, f"ru {word or 'w' + str(tg)[-3:]}", f"kk {word or 'w' + str(tg)[-3:]}", f"en {word or 'w' + str(tg)[-3:]}")
    if day:
        credits.ship(con, cid, day)
    return cid


def _get(c, tg=900):
    r = c.get("/api/credits", headers=tma(tg))
    assert r.status_code == 200, r.text
    return r.json()


def _yes(c, tg, rev="read"):
    """A yes as the app sends it: on top of the latest answer it saw."""
    if rev == "read":
        rev = (_get(c, tg)["mine"] or {}).get("rev")
    return c.put("/api/credits/consent", headers=tma(tg), json={"show": True, "consent": credits.CONSENT, "rev": rev})


def _no(c, tg):
    return c.put("/api/credits/consent", headers=tma(tg), json=NO)


def _who(got):
    """the list as (name or None, [en lines])"""
    return [(p["person"] and p["person"]["name"], [i["text"]["en"] for i in p["items"]]) for p in got["people"]]


def _names(got):
    return {p["person"]["name"] for p in got["people"] if p["person"]}


def test_visibility_matrix(env):
    """Named only with a shipped line AND their own yes; every other state keeps the line, nameless."""
    c, cfg = env
    con = _con(cfg)
    login(c, 900, "viewer")
    states = ("quiet", "yes", "no", "back", "gone", "banned", "guest")
    tgs = dict(zip(states, range(7000101, 7000108)))
    for s in states[:-1]:
        login(c, tgs[s], s)
    c.get("/api/me", headers=tma(tgs["guest"], "Guestname"))  # opened the app, never signed in as a student
    tgs["nobody"] = 7000199  # never opened the app
    for s, tg in tgs.items():
        _line(con, tg, word=s)
        _line(con, tg, day=None, word=f"{s}-suggested")
    for s in ("yes", "back", "gone", "banned"):
        assert _yes(c, tgs[s]).status_code == 200
    assert _no(c, tgs["no"]).status_code == 200
    assert _no(c, tgs["back"]).status_code == 200  # withdrawn
    assert _yes(c, tgs["guest"], None).json()["error"] == "need_student"
    # even a yes on record doesn't name someone who isn't a student here
    con.execute("INSERT INTO credit_consents (user_id, show, version, at) SELECT id, 1, ?, 1 FROM users WHERE tg_id = ?", (credits.CONSENT, tgs["guest"]))
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = ?", (tgs["banned"],))
    con.commit()
    delete_now(c, cfg, tma(tgs["gone"]))

    got = _get(c)
    by_line = {p["items"][0]["text"]["en"]: p for p in got["people"]}
    assert set(by_line) == {f"en {s}" for s in tgs}  # every shipped line listed, no suggested one
    assert all(len(p["items"]) == 1 for p in got["people"])
    assert {k for k, p in by_line.items() if p["person"]} == {"en yes"}
    assert by_line["en yes"]["person"]["name"] == "Yes T"
    # the JSON itself: no Telegram id, no name, no avatar, no user id of anyone but the one who said yes
    raw = json.dumps(got, ensure_ascii=False)
    yes_id = con.execute("SELECT id FROM users WHERE tg_id = ?", (tgs["yes"],)).fetchone()[0]
    for s, tg in tgs.items():
        assert str(tg) not in raw, s
        if s not in ("yes", "nobody", "gone"):
            assert s.title() not in raw.replace(f"en {s}", ""), s
    assert "Guestname" not in raw and "tg_id" not in raw and "whose" not in raw
    assert [p["person"]["id"] for p in got["people"] if p["person"]] == [yes_id]
    assert set(got) == {"founder", "idea", "team", "people", "mine", "version"} and got["team"] == []
    assert all(set(p) == {"person", "items"} and all(set(i) == {"kind", "text", "on"} for i in p["items"]) for p in got["people"])
    # the deleted account: its line stays, with no Telegram id left on it, and its answers are gone
    assert con.execute("SELECT tg_id FROM credits WHERE en = 'en gone'").fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM credit_consents c JOIN users u ON u.id = c.user_id WHERE u.tg_id < 0").fetchone()[0] == 0
    assert ("credit_consents", "user_id") in logic._DEL_GONE
    # a yes again after a withdrawal names them again
    assert _yes(c, tgs["back"]).status_code == 200
    assert _names(_get(c)) == {"Yes T", "Back T"}


def test_routes_are_never_cached(env):
    """Who is named changes with one person's answer: neither route may be kept by a cache."""
    c, cfg = env
    login(c, 7000901, "ann")
    _line(_con(cfg), 7000901)
    assert c.get("/api/credits", headers=tma(7000901)).headers["cache-control"] == "private, no-store"
    assert _yes(c, 7000901).headers["cache-control"] == "private, no-store"


def test_order_and_grouping(env):
    """Newest shipped first; a NAMED person's lines together, the person where their newest line stands; never by
    amount. Nameless lines: each a row of its own, so nothing says two of them are one person's, and same-day ones
    stand in an order that is not the order they were entered in."""
    c, cfg = env
    con = _con(cfg)
    for tg, name in ((7000201, "many"), (7000202, "late"), (7000203, "old"), (7000204, "shy")):
        login(c, tg, name)
    for day in ("2026-09-01", "2026-09-03", "2026-10-10", "2026-09-02", "2026-09-04"):
        _line(con, 7000201, "find", day, f"many {day}")
    _line(con, 7000202, "code", "2026-11-05")
    _line(con, 7000203, "idea", "2026-08-01")
    _line(con, 7000299, "idea", "2026-10-20", "stranger a")  # no account, two lines
    _line(con, 7000299, "find", "2026-10-21", "stranger b")
    _line(con, 7000204, "idea", "2026-10-19", "shy a")       # an account without a yes, two lines
    _line(con, 7000204, "find", "2026-10-18", "shy b")
    for tg in (7000201, 7000202, 7000203):
        assert _yes(c, tg).status_code == 200
    assert _who(_get(c, 7000203)) == [
        ("Late T", ["en w202"]),
        (None, ["en stranger b"]), (None, ["en stranger a"]), (None, ["en shy a"]), (None, ["en shy b"]),
        ("Many T", [f"en many 2026-{d}" for d in ("10-10", "09-04", "09-03", "09-02", "09-01")]),
        ("Old T", ["en w203"])]
    assert _get(c, 7000201)["people"][5]["items"][0] == {"kind": "find", "text": {"ru": "ru many 2026-10-10", "kk": "kk many 2026-10-10", "en": "en many 2026-10-10"}, "on": "2026-10-10"}
    # twelve nameless lines of one day: not in the order (nor the reverse) they were written in
    for i in range(12):
        _line(con, 7000300 + i % 2, "idea", "2026-07-07", f"same {i:02d}")
    same = [p["items"][0]["text"]["en"] for p in _get(c, 7000203)["people"] if p["items"][0]["on"] == "2026-07-07"]
    assert sorted(same) == [f"en same {i:02d}" for i in range(12)] and same not in (sorted(same), sorted(same, reverse=True))


def test_creator_and_idea_author(env):
    """The creator is named without a consent row, on purpose: he is public as the creator everywhere (person.founder),
    and only his person reference is here, none of his lines. The idea's author is named only after her own yes; until
    then her other lines stand as nameless rows, not under the idea."""
    c, cfg = env
    con = _con(cfg)
    boss, muse = login(c, 7000301, "boss"), login(c, 7000302, "muse")
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("UPDATE users SET mark = 'idea' WHERE id = ?", (muse["id"],))
    con.commit()
    _line(con, 7000301, "code", word="boss")
    _line(con, 7000302, "find", word="muse")
    assert con.execute("SELECT COUNT(*) FROM credit_consents").fetchone()[0] == 0
    got = _get(c, 7000302)
    assert got["founder"]["id"] == boss["id"] and set(got["founder"]) <= {"id", "name", "nick", "avatar", "founder", "mark", "staff", "realName", "i18n"}
    assert "en boss" not in json.dumps(got)
    item = {"kind": "find", "text": {"ru": "ru muse", "kk": "kk muse", "en": "en muse"}, "on": "2026-11-01"}
    assert got["idea"] == {"person": None, "items": []} and got["people"] == [{"person": None, "items": [item]}]
    assert "Muse" not in json.dumps(_get(c, 7000301))
    assert got["mine"] == {"consent": None, "rev": None, "idea": True, "items": [item]}
    got = _yes(c, 7000302).json()
    assert got["idea"] == {"person": got["idea"]["person"], "items": [item]} and got["idea"]["person"]["id"] == muse["id"]
    assert got["people"] == [] and got["mine"]["consent"] is True


def _team(got):
    """the Team block as (name, [en lines])"""
    return [(p["person"]["name"], [i["text"]["en"] for i in p["items"]]) for p in got["team"]]


def test_team_order_and_consent(env, monkeypatch, capsys):
    """The Team (`kbtu.admin team add|del`, audited): first added first; a member's lines under their card and not
    again below; only after their own yes (before it: not in the block, their lines nameless below); a member with
    no line can say yes too (the bot asks them); off the Team, their lines go back to the list."""
    c, cfg = env
    con = _con(cfg)
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    login(c, 900, "viewer")
    ada, bo, shy, new = (login(c, tg, n) for tg, n in ((7000801, "ada"), (7000802, "bo"), (7000803, "shy"), (7000804, "new")))
    _line(con, 7000801, "code", "2026-11-01", "ada a")
    _line(con, 7000801, "find", "2026-11-03", "ada b")
    _line(con, 7000803, "code", "2026-11-02", "shy")
    _line(con, 7000805, "find", "2026-11-04", "other")
    for i, tg in enumerate(("7000802", "7000801", "7000803", "7000804")):  # bo first, then ada (a lower user id)
        admin.main(["team", "add", tg])
        con.execute("UPDATE credit_team SET added_at = ? WHERE user_id = (SELECT id FROM users WHERE tg_id = ?)", (1000 + i, int(tg)))
        con.commit()
    admin.main(["team", "add", "7000801"])
    assert capsys.readouterr().out.strip().endswith("already")
    assert [tuple(r) for r in con.execute("SELECT action, target FROM audit_log WHERE action LIKE 'team_%' ORDER BY id")] == [
        ("team_add", f"user:{u['id']}") for u in (bo, ada, shy, new)]
    # nobody has said yes: no Team, every line nameless in the list
    got = _get(c)
    assert got["team"] == [] and _who(got) == [(None, ["en other"]), (None, ["en ada b"]), (None, ["en shy"]), (None, ["en ada a"])]
    assert "Ada" not in json.dumps(got) and "Bo T" not in json.dumps(got)
    # the Team is something of mine to answer for, lines or not
    assert _get(c, 7000802)["mine"] == {"consent": None, "rev": None, "idea": False, "items": [], "team": True}
    assert credits.ask(con, dry=True) == 4
    for tg in (7000801, 7000802, 7000804):
        assert _yes(c, tg).status_code == 200
    assert _no(c, 7000803).status_code == 200
    got = _get(c)
    assert _team(got) == [("Bo T", []), ("Ada T", ["en ada b", "en ada a"]), ("New T", [])]
    assert _who(got) == [(None, ["en other"]), (None, ["en shy"])]  # ada's lines are not repeated; shy's stay nameless
    assert all(set(p) == {"person", "items"} for p in got["team"])
    # off the Team: ada is a named person in the list again, the order of the rest unchanged
    admin.main(["team", "del", "7000801"])
    got = _get(c)
    assert _team(got) == [("Bo T", []), ("New T", [])]
    assert _who(got) == [(None, ["en other"]), ("Ada T", ["en ada b", "en ada a"]), (None, ["en shy"])]
    assert con.execute("SELECT action FROM audit_log WHERE action LIKE 'team_%' ORDER BY id DESC LIMIT 1").fetchone()[0] == "team_del"
    # a withdrawal takes them out of the block; deleting the account takes the row
    assert _no(c, 7000802).status_code == 200
    assert _team(_get(c)) == [("New T", [])]
    delete_now(c, cfg, tma(7000804))
    assert _get(c)["team"] == [] and con.execute("SELECT COUNT(*) FROM credit_team").fetchone()[0] == 2  # bo's and shy's
    assert ("credit_team", "user_id") in logic._DEL_GONE


def test_consent_record(env):
    """Every answer is kept: who, when, yes or no, to which text; a yes needs the version shown; nothing of mine:
    nothing offered."""
    c, cfg = env
    con = _con(cfg)
    me = login(c, 7000401, "ann")
    assert _get(c, 7000401)["mine"] is None
    _line(con, 7000401, day=None)
    assert _get(c, 7000401)["mine"] is None  # suggested only
    assert _yes(c, 7000401, None).json()["error"] == "conflict"  # no line shown, no yes
    _line(con, 7000401)
    assert _get(c, 7000401)["mine"]["consent"] is None and _get(c, 7000401)["version"] == credits.CONSENT
    for bad in ({}, {"show": True}, {"show": True, "consent": "cr0", "rev": None}, {"show": "yes", "consent": credits.CONSENT},
                {"show": True, "consent": credits.CONSENT, "rev": "1"}):
        assert c.put("/api/credits/consent", headers=tma(7000401), json=bad).json()["error"] == "bad_input", bad
    assert con.execute("SELECT COUNT(*) FROM credit_consents").fetchone()[0] == 0
    assert _yes(c, 7000401).json()["mine"]["consent"] is True
    assert _no(c, 7000401).json()["mine"]["consent"] is False
    assert c.put("/api/credits/consent", headers=tma(7000401), json={"show": False}).status_code == 200  # an old app's no: never refused
    got = con.execute("SELECT user_id, show, version, at FROM credit_consents ORDER BY id").fetchall()
    assert [tuple(r)[:3] for r in got] == [(me["id"], 1, credits.CONSENT), (me["id"], 0, credits.CONSENT), (me["id"], 0, credits.CONSENT)]
    assert all(r[3] > 0 for r in got)
    # a yes to an older text is not a yes to this one: nameless, asked again
    con.execute("INSERT INTO credit_consents (user_id, show, version, at) VALUES (?, 1, 'cr0', 1)", (me["id"],))
    con.commit()
    got = _get(c, 7000401)
    assert got["mine"]["consent"] is None and got["people"][0]["person"] is None


def test_stale_yes_never_undoes_a_withdrawal(env):
    """The review's P1: a yes repeated, or sent late from an older sheet, after a withdrawal changes nothing."""
    c, cfg = env
    con = _con(cfg)
    login(c, 7000701, "ann")
    _line(con, 7000701)
    first = {"show": True, "consent": credits.CONSENT, "rev": None}  # what the sheet sends on a first answer
    assert c.put("/api/credits/consent", headers=tma(7000701), json=first).json()["mine"]["consent"] is True
    assert _no(c, 7000701).json()["mine"]["consent"] is False
    again = c.put("/api/credits/consent", headers=tma(7000701), json=first).json()
    assert again["error"] == "conflict" and again["message"] == "stale"
    seen = _get(c, 7000701)
    assert seen["mine"]["consent"] is False and seen["people"][0]["person"] is None
    assert con.execute("SELECT COUNT(*) FROM credit_consents").fetchone()[0] == 2
    assert _yes(c, 7000701).json()["mine"]["consent"] is True  # a fresh sheet, on top of the no: a yes again


def test_one_eligibility_rule(env):
    """Listing, answering and asking share one rule: a typed-in (manual) student row, a ban or an unlink ends the name
    even with a yes on record, refuses a new yes, and is never asked."""
    c, cfg = env
    con = _con(cfg)
    ids = {n: login(c, tg, n)["id"] for n, tg in (("typed", 7000801), ("fine", 7000802), ("later", 7000803))}
    con.execute("UPDATE users SET can_dm = 1")
    for tg in (7000801, 7000802, 7000803):
        _line(con, tg)
    assert _yes(c, 7000801).status_code == 200 and _yes(c, 7000802).status_code == 200
    assert _names(_get(c, 7000802)) == {"Typed T", "Fine T"}
    con.execute("UPDATE students SET manual = 1 WHERE user_id IN (?, ?)", (ids["typed"], ids["later"]))
    con.commit()
    assert _names(_get(c, 7000802)) == {"Fine T"}  # the old yes no longer names a typed-in row
    assert _yes(c, 7000801, None).json()["error"] == "need_student"
    assert credits.ask(con, dry=True) == 0  # "later" never answered, but could not answer now: not asked
    # the write transaction reads the person again: a ban landing after the request was let in
    v = logic.Viewer(ids["fine"], "user", True)
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids["fine"],))
    con.commit()
    with pytest.raises(logic.ApiError) as e:
        credits.answer(con, v, {"show": True, "consent": credits.CONSENT, "rev": con.execute("SELECT MAX(id) FROM credit_consents WHERE user_id = ?", (ids["fine"],)).fetchone()[0]})
    assert e.value.code == "need_student"
    # the bot, taking a queued ask to send: quiet once the person can no longer answer
    con.execute("UPDATE students SET manual = 0 WHERE user_id = ?", (ids["later"],))
    con.commit()
    assert credits.ask(con) == 1
    m = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE b.kind = 'credit_ask'").fetchone()
    assert bot._render(con, m) is not None
    con.execute("DELETE FROM students WHERE user_id = ?", (ids["later"],))  # unlinked
    con.commit()
    assert bot._render(con, m) is None


def test_switch_stays_while_a_yes_stands(env):
    """My last shipped line deleted with my yes still on record: `mine` stays, so Settings still offers the way to
    take it back (it would name me on a later line)."""
    c, cfg = env
    con = _con(cfg)
    login(c, 7001001, "ann")
    cid = _line(con, 7001001)
    assert _yes(c, 7001001).status_code == 200
    credits.delete(con, cid)
    mine = _get(c, 7001001)["mine"]
    assert mine["consent"] is True and mine["items"] == []
    assert _no(c, 7001001).json()["mine"] is None  # taken back, nothing of mine left: nothing offered


def test_ask_once(env, capsys, monkeypatch):
    """`credit ask`: once per person and text version with a shipped line, an account the bot can write to and no
    answer; --dry counts; the count is of rows queued; an old yes is asked once for the new text, a no never."""
    c, cfg = env
    con = _con(cfg)
    names = ("two", "said", "draft", "mute", "boss", "muse", "old")
    tg = dict(zip(names, range(7000501, 7000508)))
    ids = {n: login(c, t, n)["id"] for n, t in tg.items()}
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (ids["mute"],))
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["boss"],))
    con.execute("UPDATE users SET mark = 'idea' WHERE id = ?", (ids["muse"],))
    con.commit()
    _line(con, tg["two"]), _line(con, tg["two"], "find")
    _line(con, tg["said"]), _line(con, tg["mute"]), _line(con, tg["boss"]), _line(con, 7000599), _line(con, tg["old"])
    _line(con, tg["draft"], day=None)
    _no(c, tg["said"])
    assert _yes(c, tg["old"]).status_code == 200
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    sent = lambda: sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'credit_ask'"))  # noqa: E731
    admin.main(["credit", "ask", "--dry"])
    assert capsys.readouterr().out.strip() == "would queue 2" and sent() == []
    admin.main(["credit", "ask"])
    assert capsys.readouterr().out.strip() == "queued 2" and sent() == sorted([ids["two"], ids["muse"]])
    admin.main(["credit", "ask"])
    assert capsys.readouterr().out.strip() == "queued 0" and len(sent()) == 2
    # the template: no line of ours, no user's words, one button into the app
    m = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE b.kind = 'credit_ask' AND b.user_id = ?", (ids["two"],)).fetchone()
    text, button, start = bot._render(con, m)
    assert start == "people" and button and "ru w50" not in text and (text, button) == texts.bot_message("ru", "credit_ask")
    assert _yes(c, tg["two"]).status_code == 200
    assert bot._render(con, m) is None  # answered before it went out: quiet
    # a reworded sheet: those with a yes to the old text are asked once for the new one; the no stays unasked
    monkeypatch.setattr(credits, "CONSENT", "cr2")
    monkeypatch.setattr(credits, "_ASKABLE", credits._ASKABLE.replace("'cr1'", "'cr2'"))
    assert credits.ask(con, dry=True) == 3 and credits.ask(con) == 3  # two, old, muse (her ask was for cr1)
    assert credits.ask(con) == 0
    assert ids["said"] not in sent() and sent().count(ids["old"]) == 1 and sent().count(ids["two"]) == 2
    # the count is of rows queued, not of people looked at: a row already there (another run got in first) is not counted
    con.execute("DELETE FROM bot_outbox WHERE kind = 'credit_ask' AND ref = 'cra:cr2' AND user_id != ?", (ids["old"],))
    con.commit()
    monkeypatch.setattr(credits, "rows", lambda con_, sql, *a: [{"id": ids["old"]}, {"id": ids["two"]}] if "bot_outbox" in sql else logic.rows(con_, sql, *a))
    assert credits.ask(con) == 1


def test_account_move(env, capsys, monkeypatch):
    """`admin move`: the lines follow the account, its yes ends (a withdrawal row), and a target Telegram with lines
    of its own is refused unless --merge-credits."""
    c, cfg = env
    con = _con(cfg)
    a = login(c, 7001101, "ann")
    c.get("/api/me", headers=tma(7001102, "Fresh"))
    c.get("/api/me", headers=tma(7001103, "Other"))
    _line(con, 7001101, word="hers")
    _line(con, 7001103, word="theirs")
    assert _yes(c, 7001101).status_code == 200
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    with pytest.raises(SystemExit) as e:
        admin.main(["move", "7001101", "7001103"])
    assert "merge-credits" in str(e.value)
    assert con.execute("SELECT tg_id FROM users WHERE id = ?", (a["id"],)).fetchone()[0] == 7001101  # nothing moved
    assert _names(_get(c, 7001101)) == {"Ann T"}
    admin.main(["move", "7001101", "7001102"])
    assert con.execute("SELECT tg_id FROM credits WHERE en = 'en hers'").fetchone()[0] == 7001102
    assert [tuple(r) for r in con.execute("SELECT show, version FROM credit_consents WHERE user_id = ? ORDER BY id", (a["id"],))] == [(1, credits.CONSENT), (0, credits.CONSENT)]
    got = _get(c, 7001102)  # the account, on its new Telegram: its line, nameless until a new yes
    assert _names(got) == set() and got["mine"]["consent"] is False and [i["text"]["en"] for i in got["mine"]["items"]] == ["en hers"]
    assert _yes(c, 7001102).status_code == 200
    admin.main(["move", "7001102", "7001103", "--merge-credits"])
    assert {r[0] for r in con.execute("SELECT tg_id FROM credits")} == {7001103}
    assert _names(_get(c, 7001103)) == set()  # merged, and the yes ended again


def test_move_makes_every_pending_yes_stale(env, monkeypatch):
    """Review 2: a yes sent from the old Telegram and landing after the move is refused whatever the last answer was
    (none here, then a no): the move always writes a row, so the rev it names is no longer the latest."""
    c, cfg = env
    con = _con(cfg)
    a = login(c, 7001201, "ann")
    c.get("/api/me", headers=tma(7001202, "Fresh"))
    c.get("/api/me", headers=tma(7001203, "Fresh"))
    _line(con, 7001201)
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    pending = {"show": True, "consent": credits.CONSENT, "rev": _get(c, 7001201)["mine"]["rev"]}  # null: never answered
    admin.main(["move", "7001201", "7001202"])
    v = logic.Viewer(a["id"], "user", True)  # the request let in before the move, committing after it
    with pytest.raises(logic.ApiError) as e:
        credits.answer(con, v, pending)
    assert (e.value.code, e.value.message) == ("conflict", "stale") and _names(_get(c, 7001202)) == set()
    pending["rev"] = _get(c, 7001202)["mine"]["rev"]  # the last answer is a no now: the same again
    admin.main(["move", "7001202", "7001203"])
    with pytest.raises(logic.ApiError) as e:
        credits.answer(con, v, pending)
    assert e.value.message == "stale"
    assert credits.asking(con, a["id"]) is None  # that no is on record: the bot doesn't ask


def test_listing_is_one_snapshot(env, monkeypatch):
    """Review 2: the idea's author's consent and the lines are read in one transaction, so an answer between the reads
    can't pair an old yes with a newer line."""
    c, cfg = env
    con = _con(cfg)
    me = login(c, 7001301, "ann")
    seen = []
    real = credits.rows
    monkeypatch.setattr(credits, "rows", lambda con_, *a: (seen.append(con_.in_transaction), real(con_, *a))[1])
    credits.listing(con, logic.Viewer(me["id"], "user", True))
    assert seen == [True, True] and not con.in_transaction


def test_rev_is_never_reused(env):
    """Review 2: consent row ids are never handed out again after an account deletion took the newest ones, so an old
    yes can't match a later answer's rev."""
    c, cfg = env
    con = _con(cfg)
    login(c, 7001401, "one"), login(c, 7001402, "two")
    _line(con, 7001401), _line(con, 7001402)
    assert _no(c, 7001401).status_code == 200 and _no(c, 7001402).status_code == 200
    top = con.execute("SELECT MAX(id) FROM credit_consents").fetchone()[0]
    delete_now(c, cfg, tma(7001402))  # the newest row goes with its account
    assert _no(c, 7001401).json()["mine"]["rev"] > top


def test_bot_asks_the_account_where_it_is_now(env, monkeypatch):
    """Review 2: an unanswered contributor moved after the outbox was read: the ask goes to the new Telegram id."""
    c, cfg = env
    con = _con(cfg)
    a = login(c, 7001501, "ann")
    c.get("/api/me", headers=tma(7001502, "Fresh"))
    con.execute("UPDATE users SET can_dm = 1")
    con.commit()
    _line(con, 7001501)
    assert credits.ask(con) == 1 and credits.asking(con, a["id"]) == 7001501
    con.execute("DELETE FROM credit_consents")
    con.execute("UPDATE users SET tg_id = -5 WHERE tg_id = 7001502")
    con.execute("UPDATE users SET tg_id = 7001502 WHERE id = ?", (a["id"],))
    con.execute("UPDATE credits SET tg_id = 7001502")
    con.commit()
    assert credits.asking(con, a["id"]) == 7001502


def test_cli(env, capsys, monkeypatch):
    c, cfg = env
    con = _con(cfg)
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    admin.main(["credit", "add", "7000601", "find", "  ru  line ", "kk line", "en line"])
    out = capsys.readouterr().out
    assert out.startswith("credit 1 ") and "gender-neutral" in out and "Student" in out  # the reminder, every time
    admin.main(["credit", "list"])
    assert capsys.readouterr().out.strip() == "#1  suggested  find  tg 7000601 (no account), no answer  ru line | kk line | en line"
    admin.main(["credit", "ship", "1", "2026-11-02"])
    assert con.execute("SELECT shipped_on FROM credits WHERE id = 1").fetchone()[0] == "2026-11-02"
    admin.main(["credit", "ship", "1"])  # today
    assert len(con.execute("SELECT shipped_on FROM credits WHERE id = 1").fetchone()[0]) == 10
    for bad in (["credit", "ship", "1", "tomorrow"], ["credit", "ship", "9"], ["credit", "add", "7000601", "joke", "a", "b", "c"],
                ["credit", "add", "7000601", "idea", "a", "", "c"], ["credit", "add", "7000601", "idea", "x" * 91, "b", "c"], ["credit", "del", "9"],
                ["credit", "add", "7000601", "idea", "by @someone", "b", "c"], ["credit", "add", "7000601", "idea", "a", "b", "see https://x.y"],
                ["credit", "add", "7000601", "idea", "a", "id 7000601", "c"], ["credit", "add", "7000601", "idea", "a", "b", "HTTPS://T.ME/someone"],
                ["credit", "add", "7000601", "idea", "see T.me/someone", "b", "c"]):
        with pytest.raises(SystemExit):
            admin.main(bad)
    admin.main(["credit", "del", "1"])
    assert con.execute("SELECT COUNT(*) FROM credits").fetchone()[0] == 0



def test_github_login(env, capsys, monkeypatch):
    """A pull request's author: never tied to an account, listed under the login (any case: one row, the newest
    spelling), never as the creator or the idea's author; deleting an account leaves it as it is."""
    c, cfg = env
    con = _con(cfg)
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    boss = login(c, 900, "viewer")
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (boss["id"],))
    muse = login(c, 7000702, "muse")
    con.execute("UPDATE users SET mark = 'idea' WHERE id = ?", (muse["id"],))
    con.commit()
    assert "gh" in {r[1] for r in con.execute("PRAGMA table_info(credits)")}  # migration 191
    a = _line(con, "gh:Octo-Cat", kind="idea", day="2026-11-02", word="one")
    _line(con, "gh:octo-cat", kind="code", day="2026-11-01", word="two")
    _line(con, "gh:other", kind="code", word="three")
    _line(con, 7000701, word="plain")
    assert con.execute("SELECT COUNT(*) FROM credits WHERE gh IS NOT NULL AND tg_id IS NOT NULL").fetchone()[0] == 0
    got = _get(c)
    assert sorted((p.get("gh", ""), [i["text"]["en"] for i in p["items"]]) for p in got["people"] if not p["person"]) == [
        ("", ["en plain"]), ("Octo-Cat", ["en one", "en two"]), ("other", ["en three"])]
    assert got["idea"] == {"person": None, "items": []} and got["mine"] is None  # an idea line by login: not the idea's
    for bad in (["credit", "add", "gh:-bad", "code", "a", "b", "c"], ["credit", "add", "gh:a_b", "code", "a", "b", "c"],
                ["credit", "add", "gh:" + "x" * 40, "code", "a", "b", "c"], ["credit", "bind", "octo-cat", "7000702"]):
        with pytest.raises(SystemExit):
            admin.main(bad)
    admin.main(["credit", "list"])
    assert f"#{a}  2026-11-02  idea  gh Octo-Cat, no answer" in capsys.readouterr().out
    delete_now(c, cfg, tma(7000702))
    assert con.execute("SELECT COUNT(*) FROM credits WHERE gh IS NOT NULL").fetchone()[0] == 3
