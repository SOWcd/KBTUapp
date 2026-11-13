"""Appeals to the Student Government (logic/appeals.py, APPEALS): the switch, the section's consent on the first send,
who reads the queue (a granted right only: not a club's President, not a plain student; revoked at once), an anonymous
author never reaching SG, the quota, deleting one, retention, deleting the account, the answer's template message, the
AI's tips that never block, and the funnel counters carrying no words."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, llm, logic, texts
from kbtu.logic import appeals, assistant, stats
from kbtu.logic.core import ApiError
from test_core import delete_now, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)

ANN, BEK, SG, PRES = 1, 2, 3, 4
SECRET = "the canteen on floor 2 has had no hot water since Monday"


def _uid(c, tg):
    return c.get("/api/me", headers=tma(tg)).json()["id"]


@pytest.fixture
def ap(env):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, appeals="all")))
    con = db.connect(cfg.db_path)
    for tg, name in ((ANN, "ann"), (BEK, "bek"), (SG, "sec"), (PRES, "pres")):
        login(c, tg, name)
    appeals.grant(con, None, _uid(c, SG), True)
    # the Student Government club with its President: a club role gives no access
    org = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('studentgovernment', 'club', 'SG', 'S', 'trophy_3d', 0)").lastrowid
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", (org, _uid(c, PRES)))
    yield c, cfg, con
    con.close()


def _send(c, tg, text=SECRET, **kw):
    return c.post("/api/appeals", headers=tma(tg), json={"text": text, "consent": appeals.CONSENT, **kw})


def test_off_without_the_switch(env):
    c, _ = env
    login(c, ANN, "ann")
    assert c.get("/api/appeals", headers=tma(ANN)).status_code == 404 and "appeals" not in c.get("/api/me", headers=tma(ANN)).json()


def test_staff_pilot(env):
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, appeals="staff")))
    con = db.connect(cfg.db_path)
    login(c, ANN, "ann"); login(c, SG, "sec")
    assert c.get("/api/appeals", headers=tma(ANN)).status_code == 404                    # a student: not in the pilot
    appeals.grant(con, None, _uid(c, SG), True)
    assert c.get("/api/appeals", headers=tma(SG)).status_code == 200
    assert c.get("/api/me", headers=tma(SG)).json()["appeals"] == {"consent": False, "sg": True}
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (_uid(c, ANN),))
    assert c.get("/api/appeals", headers=tma(ANN)).status_code == 200                    # staff try it
    con.close()


def test_consent_on_the_first_send(ap):
    c, _, con = ap
    assert c.post("/api/appeals", headers=tma(ANN), json={"text": "hi"}).status_code == 403   # not agreed yet
    assert c.get("/api/me", headers=tma(ANN)).json()["appeals"]["consent"] is False
    assert _send(c, ANN, "x").status_code == 200                                       # any form, one letter too
    assert c.post("/api/appeals", headers=tma(ANN), json={"text": "again"}).status_code == 200  # asked once
    assert con.execute("SELECT version FROM appeal_consents").fetchone()[0] == appeals.CONSENT
    assert _send(c, ANN, "y" * (appeals.MAX + 1)).status_code == 400 and _send(c, ANN, "   ").status_code == 400


def test_guest_cannot_send(ap):
    c, _, _ = ap
    c.get("/api/me", headers=tma(77))
    assert _send(c, 77).status_code in (400, 401, 403)  # need_student


def test_rights_and_anonymity(ap):
    c, _, con = ap
    a = _send(c, ANN, anon=True, topic="food").json()
    b = _send(c, BEK, "named one").json()
    assert a["anon"] and a["status"] == "new" and a["topic"] == "food"
    for tg in (ANN, PRES):                                                            # a student, SG's club President
        assert c.get("/api/sg/appeals", headers=tma(tg)).status_code == 403
        assert c.get(f"/api/sg/appeals/{a['id']}", headers=tma(tg)).status_code == 403
        assert c.post(f"/api/sg/appeals/{a['id']}", headers=tma(tg), json={"status": "work"}).status_code == 403
    q = c.get("/api/sg/appeals", headers=tma(SG))
    assert q.status_code == 200
    items = {x["id"]: x for x in q.json()["items"]}
    assert "author" not in items[a["id"]] and items[b["id"]]["author"] == "Bek T"     # a named one: the short name only
    d = c.get(f"/api/sg/appeals/{a['id']}", headers=tma(SG))
    # nothing of the anonymous author anywhere SG reads: name, ids, student ID, Telegram
    ann = con.execute("SELECT u.id, u.tg_id FROM users u WHERE tg_id = ?", (ANN,)).fetchone()
    for body in (q.text, d.text):
        assert "Ann" not in body and "24Bann" not in body and f'"userId"' not in body
    assert set(d.json()) == {'id', 'topic', 'text', 'anon', 'status', 'answer', 'at', 'due', 'answeredAt', 'closedAt', 'overdue'}  # no author field at all
    # every look in the audit log, never the words
    acts = [r[0] for r in con.execute("SELECT action FROM audit_log WHERE action LIKE 'appeal_%'")]
    assert "appeal_queue" in acts and "appeal_view" in acts
    assert not con.execute("SELECT 1 FROM audit_log WHERE data LIKE '%canteen%' OR target LIKE ?", (f"user:{ann['id']}",)).fetchone()
    # revoked: at once
    appeals.grant(con, None, _uid(c, SG), False)
    assert c.get("/api/sg/appeals", headers=tma(SG)).status_code == 403
    assert c.get("/api/me", headers=tma(SG)).json()["appeals"]["sg"] is False
    # the creator's reveal, audited
    p = appeals.reveal(con, _uid(c, BEK), a["id"])  # (admin.py passes the creator)
    assert p["id"] == ann["id"] and con.execute("SELECT 1 FROM audit_log WHERE action = 'appeal_reveal' AND target = ?", (f"appeal:{a['id']}",)).fetchone()


def test_status_answer_overdue_and_message(ap, monkeypatch):
    c, _, con = ap
    a = _send(c, ANN).json()
    assert a["due"] == appeals.due(a["at"]) and not a["overdue"]
    act = lambda **b: c.post(f"/api/sg/appeals/{a['id']}", headers=tma(SG), json=b)  # noqa: E731
    assert act(status="closed").status_code == 400                                   # closing needs an answer
    assert act(status="work").json()["status"] == "work"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'appeal_answer'").fetchone()   # a status alone: no message
    monkeypatch.setattr(logic.core, "now", lambda: a["due"] + 60)                      # past due, still open: overdue
    assert c.get("/api/appeals", headers=tma(ANN)).json()["items"][0]["overdue"]
    r = act(status="closed", answer="Fixed on Wednesday").json()
    assert r["status"] == "closed" and r["answer"] == "Fixed on Wednesday" and r["overdue"]   # closing doesn't reset it
    act(status="work"); act(status="closed")
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'appeal_answer'").fetchall()
    assert len(m) == 1 and m[0]["user_id"] == _uid(c, ANN)                           # once, to the author
    text, button, start = bot._render(con, {**dict(m[0]), "lang": "en"})
    assert start == "apl" and "Fixed" not in text and text == texts.bot_message("en", "appeal_answer")[0]
    mine = c.get("/api/appeals", headers=tma(ANN)).json()["items"][0]
    assert mine["status"] == "closed" and mine["answer"] == "Fixed on Wednesday"
    assert {r[0] for r in con.execute("SELECT action FROM audit_log WHERE action LIKE 'appeal_%'")} >= {"appeal_answer", "appeal_status"}


def test_due_counts_working_days():
    fri = 1762495200  # Fri 2025-11-07 11:00 Almaty
    assert appeals.due(fri) == fri + 7 * 86400   # Mon..Fri next week


def test_quota_retry_and_delete(ap):
    c, _, con = ap
    first = _send(c, ANN, key="k-12345678").json()
    assert _send(c, ANN, key="k-12345678").json()["id"] == first["id"]               # a retry: no twin
    _send(c, ANN, "two"); _send(c, ANN, "three")
    assert _send(c, ANN, "four").status_code == 429
    assert c.delete(f"/api/appeals/{first['id']}", headers=tma(BEK)).status_code == 404   # not mine
    assert c.delete(f"/api/appeals/{first['id']}", headers=tma(ANN)).status_code == 204
    assert _send(c, ANN, "five").status_code == 429                                  # deleting gives nothing back
    assert not con.execute("SELECT 1 FROM appeals WHERE id = ?", (first["id"],)).fetchone()
    assert all(x["id"] != first["id"] for x in c.get("/api/sg/appeals", headers=tma(SG)).json()["items"])


def test_retention(ap, monkeypatch):
    c, _, con = ap
    old = _send(c, ANN, "old").json()["id"]
    closed = _send(c, BEK, "closed").json()["id"]
    c.post(f"/api/sg/appeals/{closed}", headers=tma(SG), json={"status": "closed", "answer": "ok"})
    t = logic.core.now()
    monkeypatch.setattr(logic.core, "now", lambda: t + 91 * 86400)
    appeals.forget(con)
    assert {r[0] for r in con.execute("SELECT id FROM appeals")} == {old}
    monkeypatch.setattr(logic.core, "now", lambda: t + 181 * 86400)
    appeals.forget(con)
    assert not con.execute("SELECT 1 FROM appeals").fetchone() and not con.execute("SELECT 1 FROM appeal_authors").fetchone()


def test_account_deletion_covers_it(ap):
    c, cfg, con = ap
    a = _send(c, ANN, anon=True).json()
    c.post(f"/api/sg/appeals/{a['id']}", headers=tma(SG), json={"answer": "on it"})
    _send(c, SG, "mine as SG")
    uid, sg = _uid(c, ANN), _uid(c, SG)
    delete_now(c, cfg, tma(ANN))
    delete_now(c, cfg, tma(SG))
    for t in ("appeals", "appeal_authors", "appeal_sends", "appeal_consents", "appeal_staff"):
        assert not con.execute(f"SELECT 1 FROM {t}").fetchone(), t
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id IN (?, ?) AND kind = 'appeal_answer'", (uid, sg)).fetchone()


def test_ai_help_suggests_never_blocks(ap, monkeypatch):
    c, _, _ = ap
    assistant._HITS.clear()
    said = {"tips": ["Where exactly?", "Since when?", "What outcome do you want?", "a fourth"], "care": False}

    async def model(cfg_, http, msgs, **kw):
        assert "never rewrite" in msgs[0]["content"] and kw.get("race") is True and msgs[1]["content"] == SECRET
        return json.dumps(said), "x"
    monkeypatch.setattr(llm, "chat", model)
    help_ = lambda text=SECRET, **b: c.post("/api/appeals/help", headers=tma(ANN), json={"text": text, "lang": "en", **b})  # noqa: E731
    assert help_().status_code == 403                                                # the section first
    r = help_(consent=appeals.CONSENT).json()
    assert r == {"tips": said["tips"][:3]}
    said["care"] = True
    assert help_().json()["help"] == texts.HELP_CARD["en"]

    async def down(*a, **k):
        raise llm.Busy()
    monkeypatch.setattr(llm, "chat", down)
    assert help_().status_code == 503
    assert help_("\u0445\u043e\u0447\u0443 \u0443\u043c\u0435\u0440\u0435\u0442\u044c").json()["care"]   # ru: I want to die: the helplines without the model
    assert _send(c, ANN).status_code == 200                                          # sending works with the AI down


def test_funnel_counters_carry_no_words(ap):
    c, _, con = ap
    stats._spent.clear(); stats._uniq.clear()
    body = {k: 1 for k in stats.APPEALS} | {"apl.text": 1, SECRET: 1, "apl.sent": "draft words"}
    assert c.post("/api/stats", headers=tma(ANN), json=body).status_code in (200, 204)
    got = {r[0]: r[1] for r in con.execute("SELECT key, n FROM usage_days")}
    assert set(got) == set(stats.APPEALS) - {"apl.sent"} and all(n == 1 for n in got.values())
    assert [c[1] for c in con.execute("PRAGMA table_info(usage_days)")] == ["day", "key", "n"]


def test_ids_never_reused(ap):
    """An author deletes the newest appeal; the next one (another student's) gets a new id, so SG's answer meant for
    the deleted one can't land on it."""
    c, _, con = ap
    gone = _send(c, ANN, anon=True).json()["id"]
    assert c.delete(f"/api/appeals/{gone}", headers=tma(ANN)).status_code == 204
    new = _send(c, BEK, anon=True).json()["id"]
    assert new != gone
    assert c.post(f"/api/sg/appeals/{gone}", headers=tma(SG), json={"answer": "for the deleted one"}).status_code == 404
    assert c.get("/api/appeals", headers=tma(BEK)).json()["items"][0]["answer"] is None


def test_months_never_link_authors(ap):
    """A named and an anonymous appeal of one person count as two, exactly as two people's would."""
    c, _, con = ap
    _send(c, ANN, "named", topic="food"); _send(c, ANN, "anon", topic="food", anon=True)
    one_person = c.get("/api/sg/appeals", headers=tma(SG)).json()["months"]
    con.execute("DELETE FROM appeals")
    _send(c, BEK, "named", topic="food"); _send(c, SG, "anon", topic="food", anon=True)
    two_people = c.get("/api/sg/appeals", headers=tma(SG)).json()["months"]
    assert one_person == two_people == [{"month": one_person[0]["month"], "total": 2, "topics": {"other": 2}}]


def test_distress_before_any_limit(ap, monkeypatch):
    """Over the AI allowance and without the section agreed: a crisis text still gets the helplines."""
    c, _, con = ap
    assistant._HITS.clear()
    for _ in range(assistant.A_DAY):
        con.execute("INSERT INTO assist_uses (user_id, at) VALUES (?, ?)", (_uid(c, BEK), logic.now()))
    r = c.post("/api/appeals/help", headers=tma(BEK), json={"text": "I want to die", "lang": "en"})
    assert r.status_code == 200 and r.json()["help"] == texts.HELP_CARD["en"]
    assert c.post("/api/appeals/help", headers=tma(BEK), json={"text": "where", "lang": "en", "consent": appeals.CONSENT}).status_code == 429


def test_staff_pilot_asks_consent_too(env):
    """APPEALS=staff: the section's own consent is asked and kept as with APPEALS=1; /api/me says so honestly."""
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, appeals="staff")))
    login(c, SG, "sec")
    con = db.connect(cfg.db_path)
    appeals.grant(con, None, _uid(c, SG), True)
    assert c.get("/api/me", headers=tma(SG)).json()["appeals"]["consent"] is False
    assert c.post("/api/appeals", headers=tma(SG), json={"text": "pilot"}).status_code == 403
    assert _send(c, SG, "pilot").status_code == 200
    assert c.get("/api/me", headers=tma(SG)).json()["appeals"]["consent"] is True
    con.close()


def test_distress_keeps_a_first_consent(ap):
    """The helplines' answer with a first consent: kept, so the next send works without asking again."""
    c, _, con = ap
    assistant._HITS.clear()
    r = c.post("/api/appeals/help", headers=tma(BEK), json={"text": "I want to die", "lang": "en", "consent": appeals.CONSENT})
    assert r.status_code == 200 and r.json()["care"]
    assert c.post("/api/appeals", headers=tma(BEK), json={"text": "next"}).status_code == 200


def test_months_merge_small_topics(ap):
    c, _, con = ap
    _send(c, ANN, topic="food"); _send(c, BEK, topic="dorm")
    m = c.get("/api/sg/appeals", headers=tma(SG)).json()["months"][0]
    assert m["total"] == 2 and m["topics"] == {"other": 2}                           # under 5 authors: merged
    uids = [con.execute("INSERT INTO users (tg_id, tg_first_name, created_at, seen_at) VALUES (?, 'X', 0, 0)", (900 + i,)).lastrowid for i in range(5)]
    for u in uids:
        aid = con.execute("INSERT INTO appeals (topic, body, created_at, due_at) VALUES ('food', 'x', ?, 0)", (logic.now(),)).lastrowid
        con.execute("INSERT INTO appeal_authors (appeal_id, user_id) VALUES (?, ?)", (aid, u))
    m = appeals.months(con)[0]
    assert m["topics"] == {"food": 6, "other": 1} and m["total"] == 7

# ------------------------------------------------------------ "Solved by your appeals" (appeals.solved*): the shapes that
# could point at an anonymous author never pass, SG's people alone write and delete, 10 a month, students see it from 3
# entries, the audit keeps ids only, the author never leaves the server and goes with their account; no appeal link

OK_R, OK_C = "Cold water in the dorm showers", "The boiler was repaired and checked weekly"


def _add(c, tg=SG, raised=OK_R, changed=OK_C, **kw):
    return c.post("/api/sg/solved", headers=tma(tg), json={"raised": raised, "changed": changed, **kw})


@pytest.mark.parametrize("text, why", json.loads(pathlib.Path(__file__).with_name("solved_rules.json").read_text())["cases"])
def test_solved_rules(text, why):
    """The cases the app agrees on (web/src/lib/solved.test.ts)."""
    if why is None:
        assert appeals.solved_line(text)
        return
    with pytest.raises(ApiError) as e:
        appeals.solved_line(text)
    assert (e.value.code, e.value.message) == ("bad_input", why)


def test_cleaned():
    assert appeals.solved_line("  Wi-Fi \n\n in the  library\x07 was slow ") == "Wi-Fi in the library was slow"
    assert appeals.solved_line("Floor 3 got a new microwave") == "Floor 3 got a new microwave"  # one digit is fine


def test_rights(ap):
    c, _, con = ap
    mod = 9
    login(c, mod, "mod")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (_uid(c, mod),))
    for tg in (ANN, PRES, mod):                                       # a student, SG's club President, a moderator
        assert _add(c, tg).status_code == 403
    sid = _add(c).json()["id"]
    for tg in (ANN, PRES, mod):
        assert c.delete(f"/api/sg/solved/{sid}", headers=tma(tg)).status_code == 403
        assert c.post(f"/api/sg/solved/{sid}/restore", headers=tma(tg)).status_code == 403
    assert _add(c, raised="room 405 had no heating").status_code == 400
    other = 8
    login(c, other, "sec2")
    appeals.grant(con, None, _uid(c, other), True)
    assert c.delete(f"/api/sg/solved/{sid}", headers=tma(other)).status_code == 204   # any of SG's people, any entry
    assert c.delete(f"/api/sg/solved/{sid}", headers=tma(other)).status_code == 404
    assert c.post(f"/api/sg/solved/{sid}/restore", headers=tma(SG)).json()["id"] == sid  # undo
    acts = [tuple(r) for r in con.execute("SELECT action, target, data FROM audit_log WHERE action LIKE 'solved_%' ORDER BY id")]
    assert acts == [("solved_add", f"solved:{sid}", "{}"), ("solved_delete", f"solved:{sid}", "{}"), ("solved_restore", f"solved:{sid}", "{}")]


def test_threshold_shape_and_no_author(ap):
    c, _, _ = ap
    feed = lambda tg: c.get("/api/appeals", headers=tma(tg)).json()["solved"]  # noqa: E731
    for tg in (ANN, BEK, PRES):                                         # dorm: 5 appeals (by 3 people: appeals count)
        _send(c, tg, topic="dorm")
    _add(c, topic="dorm"); _add(c, topic="nope")
    assert feed(ANN) == [] and len(feed(SG)) == 2                      # SG sees it from the first
    _send(c, ANN, topic="dorm"); _send(c, BEK, topic="dorm")
    _add(c, raised="Kind words for the dorm staff", topic="dorm")
    _send(c, ANN, topic="food")
    _add(c, raised="The canteen ran out of salads", topic="food")      # one food appeal: published, its topic not
    f, g = feed(ANN), feed(SG)
    assert len(f) == 4 and [e["raised"] for e in f] == [e["raised"] for e in g] and g[0]["id"] > g[1]["id"] > g[2]["id"]  # newest first
    assert all(set(e) == {"raised", "changed", "topic", "month"} for e in f)  # no ids for students: their gaps count deletes
    assert [e["topic"] for e in f] == [None, "dorm", None, None]        # under FEW appeals in 90 days: no topic
    assert f[0]["month"] == dt.datetime.now(appeals.ALMATY).strftime("%Y-%m")
    for e in g[:2]:
        c.delete(f"/api/sg/solved/{e['id']}", headers=tma(SG))
    assert feed(ANN) == []                                              # back under 3, at once


def test_monthly_cap_and_forget(ap, monkeypatch):
    c, _, con = ap
    t = logic.core.now()
    ids = [_add(c).json()["id"] for _ in range(appeals.SOLVED_MONTH)]
    r = _add(c)
    assert r.status_code == 429
    c.delete(f"/api/sg/solved/{ids[0]}", headers=tma(SG))
    assert _add(c).status_code == 429                                   # a deleted one still counts: no delete-add loops
    assert c.post(f"/api/sg/solved/{ids[0]}/restore", headers=tma(SG)).status_code == 200   # undo
    c.delete(f"/api/sg/solved/{ids[1]}", headers=tma(SG))
    day = lambda d: monkeypatch.setattr(logic.core, "now", lambda: int(d.timestamp()))  # noqa: E731
    gone = con.execute("SELECT gone_at FROM appeal_solved WHERE id = ?", (ids[1],)).fetchone()[0]
    later = dt.datetime.fromtimestamp(gone + 86401, appeals.ALMATY)
    day(later)
    assert c.post(f"/api/sg/solved/{ids[1]}/restore", headers=tma(SG)).status_code == 404   # a day on: no undo
    appeals.forget(con)
    assert tuple(con.execute("SELECT raised, changed, created_by FROM appeal_solved WHERE id = ?", (ids[1],)).fetchone()) == ("", "", None)
    if later.month == dt.datetime.fromtimestamp(t, appeals.ALMATY).month:
        assert _add(c).status_code == 429                               # its words gone, its place in the month's ten kept
    nxt = dt.datetime.fromtimestamp(t, appeals.ALMATY).replace(day=28) + dt.timedelta(days=5)
    day(nxt)
    assert _add(c).status_code == 200                                   # a new month
    appeals.forget(con)
    assert not con.execute("SELECT 1 FROM appeal_solved WHERE id = ?", (ids[1],)).fetchone()  # last month's deleted one: gone


def test_no_appeal_words(ap):
    c, _, _ = ap
    _send(c, ANN)
    r = _add(c, raised="The canteen had had no hot water since Monday")  # six of the appeal's words in a row
    assert (r.status_code, r.json()["message"]) == (400, "quote")
    assert _add(c, raised="Hot water in the canteen kept failing").status_code == 200


def test_rights_of_others(ap):
    c, _, con = ap
    sid = _add(c).json()["id"]
    adm = 7
    login(c, adm, "adm")
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (_uid(c, adm),))
    assert _add(c, adm).status_code == 403 and c.delete(f"/api/sg/solved/{sid}", headers=tma(adm)).status_code == 403
    appeals.grant(con, None, _uid(c, SG), False)                         # removed from SG
    assert _add(c).status_code == 403 and c.delete(f"/api/sg/solved/{sid}", headers=tma(SG)).status_code == 403
    appeals.grant(con, None, _uid(c, SG), True)
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (_uid(c, SG),))
    assert _add(c).status_code == 403 and c.get("/api/appeals", headers=tma(SG)).status_code == 403


def test_account_deletion_keeps_the_entry_without_its_author(ap):
    c, cfg, con = ap
    sid = _add(c).json()["id"]
    delete_now(c, cfg, tma(SG))
    assert tuple(con.execute("SELECT raised, created_by FROM appeal_solved WHERE id = ?", (sid,)).fetchone()) == (OK_R, None)


def test_no_link_to_any_appeal(ap):
    _, _, con = ap
    cols = {r[1] for r in con.execute("PRAGMA table_info(appeal_solved)")}
    assert cols == {"id", "raised", "changed", "topic", "created_by", "created_at", "gone_at"}
    assert not con.execute("PRAGMA foreign_key_list(appeal_solved)").fetchall()[1:]   # users alone
