"""The people of the app (logic/credits.py): who is named and who is "Student", the order, the bot's one ask, the
consent's record, and that the API's JSON never carries a Telegram id, a name or a face of someone without a yes."""
from __future__ import annotations

import json

import pytest

from kbtu import admin, bot, db, logic, texts
from kbtu.logic import credits
from test_core import delete_now, env, login, tma  # noqa: F401  (env is a fixture)

YES = {"show": True, "consent": credits.CONSENT}
NO = {"show": False}


def _con(cfg):
    return db.connect(cfg.db_path)


def _line(con, tg, kind="idea", day="2026-11-01", word=None):
    cid = credits.add(con, tg, kind, f"ru {word or tg}", f"kk {word or tg}", f"en {word or tg}")
    if day:
        credits.ship(con, cid, day)
    return cid


def _get(c, tg=900):
    r = c.get("/api/credits", headers=tma(tg))
    assert r.status_code == 200, r.text
    return r.json()


def _who(got):
    """the list as (name or None, [en lines])"""
    return [(p["person"] and p["person"]["name"], [i["text"]["en"] for i in p["items"]]) for p in got["people"]]


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
        assert c.put("/api/credits/consent", headers=tma(tgs[s]), json=YES).status_code == 200
    assert c.put("/api/credits/consent", headers=tma(tgs["no"]), json=NO).status_code == 200
    assert c.put("/api/credits/consent", headers=tma(tgs["back"]), json=NO).status_code == 200  # withdrawn
    assert c.put("/api/credits/consent", headers=tma(tgs["guest"]), json=YES).json()["error"] == "need_student"
    # even a yes on record doesn't name someone who isn't a student here
    con.execute("INSERT INTO credit_consents (user_id, version, at) SELECT id, ?, 1 FROM users WHERE tg_id = ?", (credits.CONSENT, tgs["guest"]))
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
    assert set(got) == {"founder", "idea", "people", "mine", "version"}
    assert all(set(p) == {"person", "items"} and all(set(i) == {"kind", "text", "on"} for i in p["items"]) for p in got["people"])
    # the deleted account: its line stays, with no Telegram id left on it, and its answers are gone
    assert con.execute("SELECT tg_id FROM credits WHERE en = 'en gone'").fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM credit_consents c JOIN users u ON u.id = c.user_id WHERE u.tg_id < 0").fetchone()[0] == 0
    assert ("credit_consents", "user_id") in logic._DEL_GONE
    # a yes again after a withdrawal names them again
    assert c.put("/api/credits/consent", headers=tma(tgs["back"]), json=YES).status_code == 200
    assert {p["person"]["name"] for p in _get(c)["people"] if p["person"]} == {"Yes T", "Back T"}


def test_order_and_grouping(env):
    """Newest shipped first; a person's lines together, the person where their newest line stands; never by amount."""
    c, cfg = env
    con = _con(cfg)
    for tg, name in ((7000201, "many"), (7000202, "late"), (7000203, "old")):
        login(c, tg, name)
    for day in ("2026-09-01", "2026-09-03", "2026-10-10", "2026-09-02", "2026-09-04"):
        _line(con, 7000201, "find", day, f"many {day}")
    _line(con, 7000202, "code", "2026-11-05")
    _line(con, 7000203, "idea", "2026-08-01")
    _line(con, 7000299, "idea", "2026-10-20", "stranger")  # no account
    for tg in (7000201, 7000202, 7000203):
        assert c.put("/api/credits/consent", headers=tma(tg), json=YES).status_code == 200
    assert _who(_get(c, 7000203)) == [
        ("Late T", ["en 7000202"]),
        (None, ["en stranger"]),
        ("Many T", [f"en many 2026-{d}" for d in ("10-10", "09-04", "09-03", "09-02", "09-01")]),
        ("Old T", ["en 7000203"])]
    assert _get(c, 7000201)["people"][2]["items"][0] == {"kind": "find", "text": {"ru": "ru many 2026-10-10", "kk": "kk many 2026-10-10", "en": "en many 2026-10-10"}, "on": "2026-10-10"}


def test_creator_and_idea_author(env):
    """The creator is named as he is everywhere; the idea's author only after her own yes; neither stands in the list."""
    c, cfg = env
    con = _con(cfg)
    boss, muse = login(c, 7000301, "boss"), login(c, 7000302, "muse")
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("UPDATE users SET mark = 'idea' WHERE id = ?", (muse["id"],))
    con.commit()
    _line(con, 7000301, "code", word="boss")
    _line(con, 7000302, "find", word="muse")
    got = _get(c, 7000302)
    assert got["founder"]["id"] == boss["id"] and got["people"] == []
    assert got["idea"] == {"person": None, "items": [{"kind": "find", "text": {"ru": "ru muse", "kk": "kk muse", "en": "en muse"}, "on": "2026-11-01"}]}
    assert "Muse" not in json.dumps(_get(c, 7000301))
    assert got["mine"] == {"consent": None, "idea": True, "items": got["idea"]["items"]}
    got = c.put("/api/credits/consent", headers=tma(7000302), json=YES).json()
    assert got["idea"]["person"]["id"] == muse["id"] and got["mine"]["consent"] is True
    assert _get(c, 7000301)["mine"] is None or _get(c, 7000301)["mine"]["idea"] is False


def test_consent_record(env):
    """Every answer is kept: who, when, which text; a yes needs the version shown; nothing of mine: nothing offered."""
    c, cfg = env
    con = _con(cfg)
    me = login(c, 7000401, "ann")
    assert _get(c, 7000401)["mine"] is None
    _line(con, 7000401, day=None)
    assert _get(c, 7000401)["mine"] is None  # suggested only
    assert c.put("/api/credits/consent", headers=tma(7000401), json=YES).json()["error"] == "conflict"  # no line shown, no yes
    _line(con, 7000401)
    assert _get(c, 7000401)["mine"]["consent"] is None and _get(c, 7000401)["version"] == credits.CONSENT
    for bad in ({}, {"show": True}, {"show": True, "consent": "cr0"}, {"show": "yes", "consent": credits.CONSENT}):
        assert c.put("/api/credits/consent", headers=tma(7000401), json=bad).json()["error"] == "bad_input", bad
    assert con.execute("SELECT COUNT(*) FROM credit_consents").fetchone()[0] == 0
    assert c.put("/api/credits/consent", headers=tma(7000401), json=YES).json()["mine"]["consent"] is True
    assert c.put("/api/credits/consent", headers=tma(7000401), json=NO).json()["mine"]["consent"] is False
    got = con.execute("SELECT user_id, version, at FROM credit_consents ORDER BY id").fetchall()
    assert [(r[0], r[1]) for r in got] == [(me["id"], credits.CONSENT), (me["id"], credits.OFF)] and all(r[2] > 0 for r in got)
    # a yes to an older text is not a yes to this one: nameless, asked again
    con.execute("INSERT INTO credit_consents (user_id, version, at) VALUES (?, 'cr0', 1)", (me["id"],))
    con.commit()
    got = _get(c, 7000401)
    assert got["mine"]["consent"] is None and got["people"][0]["person"] is None


def test_ask_once(env, capsys, monkeypatch):
    """`credit ask`: once per person with a shipped line, an account the bot can write to and no answer; --dry counts."""
    c, cfg = env
    con = _con(cfg)
    names = ("two", "said", "draft", "mute", "boss", "muse")
    tg = dict(zip(names, range(7000501, 7000507)))
    ids = {n: login(c, t, n)["id"] for n, t in tg.items()}
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (ids["mute"],))
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["boss"],))
    con.execute("UPDATE users SET mark = 'idea' WHERE id = ?", (ids["muse"],))
    con.commit()
    _line(con, tg["two"]), _line(con, tg["two"], "find")
    _line(con, tg["said"]), _line(con, tg["mute"]), _line(con, tg["boss"]), _line(con, 7000599)
    _line(con, tg["draft"], day=None)
    c.put("/api/credits/consent", headers=tma(tg["said"]), json=NO)
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
    assert start == "people" and button and "ru 70005" not in text and (text, button) == texts.bot_message("ru", "credit_ask")
    c.put("/api/credits/consent", headers=tma(tg["two"]), json=YES)
    assert bot._render(con, m) is None  # answered before it went out: quiet


def test_cli(env, capsys, monkeypatch):
    c, cfg = env
    con = _con(cfg)
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    admin.main(["credit", "add", "7000601", "find", "  ru  line ", "kk line", "en line"])
    assert capsys.readouterr().out.startswith("credit 1 ")
    admin.main(["credit", "list"])
    assert capsys.readouterr().out.strip() == "#1  suggested  find  tg 7000601 (no account), no answer  ru line | kk line | en line"
    admin.main(["credit", "ship", "1", "2026-11-02"])
    assert con.execute("SELECT shipped_on FROM credits WHERE id = 1").fetchone()[0] == "2026-11-02"
    admin.main(["credit", "ship", "1"])  # today
    assert len(con.execute("SELECT shipped_on FROM credits WHERE id = 1").fetchone()[0]) == 10
    for bad in (["credit", "ship", "1", "tomorrow"], ["credit", "ship", "9"], ["credit", "add", "7000601", "joke", "a", "b", "c"],
                ["credit", "add", "7000601", "idea", "a", "", "c"], ["credit", "add", "7000601", "idea", "x" * 91, "b", "c"], ["credit", "del", "9"]):
        with pytest.raises(SystemExit):
            admin.main(bad)
    admin.main(["credit", "del", "1"])
    assert con.execute("SELECT COUNT(*) FROM credits").fetchone()[0] == 0
