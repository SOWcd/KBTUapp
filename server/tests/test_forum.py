"""The student forum: find people, bot cards, the moderator queue."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time

import pytest
from fastapi.testclient import TestClient

from kbtu import ai, bot, db, logic, app as server, texts
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def test_forum_find_people(env, monkeypatch):
    """F1 find people (PLAN "F1 spec" + "Forum adversarial review"): the gate; the skills catalog; who is matched (open to
    projects, never the author, staff, DMP's people or guests); pings (top 5, 1 a day, 2 a week, project only, never
    twice); nobody's Telegram before Accept; blocks; expiry; a report hides only with 3 old accounts and the AI;
    deleting an account takes all of it."""
    import dataclasses
    from kbtu import ai
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    con = db.connect(cfg.db_path)
    L = lambda uid, name: logic.Viewer(login(c, uid, name)["id"], "user", True)  # noqa: E731
    mod = L(80, "mod")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod.id,))
    mod = logic.Viewer(mod.id, "moderator", True)
    M, S = tma(80), tma(81)
    stu = L(81, "stu")
    assert c.get("/api/forum/me", headers=S).status_code == 403                                     # students: not yet
    assert TestClient(server.create(cfg)).get("/api/forum/me", headers=M).status_code == 404         # the flag off: no forum
    # the catalog: normalised names, the same one found, close ones offered, the AI's no refused
    web = c.post("/api/forum/skills", headers=M, json={"name": "  WEB!! "}).json()["skill"]
    assert web["name"] == "web" and web["public"]
    assert [x["name"] for x in c.post("/api/forum/skills", headers=M, json={"name": "webb"}).json()["didYouMean"]] == ["web"]
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=False))
    assert c.post("/api/forum/skills", headers=M, json={"name": "nasty word"}).json()["message"] == "ai"
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=None))                    # no AI: made, but private
    figma = c.post("/api/forum/skills", headers=M, json={"name": "Figma"}).json()["skill"]
    assert not figma["public"] and "figma" not in [x["name"] for x in logic.skills(con, stu, "fig")]
    assert logic.set_my_forum(con, mod, {"skills": [web["id"], figma["id"]] * 3})["skills"] == [{"id": figma["id"], "name": "figma"}, {"id": web["id"], "name": "web"}]
    with pytest.raises(logic.ApiError):
        logic.set_my_forum(con, mod, {"skills": list(range(1, 7))})                                  # 6: more than 5

    # people: open ones with the skill; never the author, staff, DMP's people, guests or anyone not open
    people = {n: L(82 + i, n) for i, n in enumerate(("bob", "cat", "dmp", "eve", "fay", "gus", "hal", "ivy", "jon"))}
    for n, v in people.items():
        logic.set_my_forum(con, v, {"skills": [web["id"]], "open": n != "cat", "pings": True})
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (9, ?, 'member', 0)", (people["dmp"].id,))
    guest = c.get("/api/me", headers=tma(99, "Guest")).json()["id"]                                # Telegram only, no KBTU
    con.execute("UPDATE users SET open_projects = 1 WHERE id = ?", (guest,))
    con.execute("INSERT INTO user_skills (user_id, skill_id) VALUES (?, ?)", (guest, web["id"]))
    logic.set_my_forum(con, mod, {"open": True, "pings": True})
    found = {x["person"]["id"] for x in logic.search_people(con, stu, web["id"])}
    profile = c.get(f"/api/users/{people['bob'].id}", headers=M).json()["forum"]
    assert profile == {"skills": [{"id": web["id"], "name": "web"}], "open": True}
    assert "forum" not in c.get(f"/api/users/{people['cat'].id}", headers=M).json()
    want = {people[n].id for n in ("bob", "eve", "fay", "gus", "hal", "ivy", "jon")}
    assert found == want                                                                             # not cat, dmp, the guest, the moderator

    # a project request pings the best 5 with pings on, once; the rest of the day nobody gets another
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=True))
    ask = c.post("/api/forum/asks", headers=M, json={"kind": "project", "title": "A site for the jam", "body": "React", "skills": [web["id"]]}).json()
    assert ask["matches"] == 7 and ask["status"] == "live"
    pinged = [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'ask_match'")]
    assert len(pinged) == 5 and set(pinged) <= want
    ask2 = c.post("/api/forum/asks", headers=M, json={"kind": "project", "title": "A logo too", "skills": [web["id"]]}).json()
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'ask_match' AND ref = ?", (f"am:{ask2['id']}",))} == want - set(pinged)
    con.execute("UPDATE ask_pings SET at = at - 2 * 86400")                                          # two days on: a second this week
    help_ = c.post("/api/forum/asks", headers=M, json={"kind": "help", "title": "Who has a charger?", "days": 1}).json()
    assert help_["skills"] == [] and not con.execute("SELECT 1 FROM bot_outbox WHERE ref = ?", (f"am:{help_['id']}",)).fetchone()  # help: no pings
    assert c.post("/api/forum/asks", headers=M, json={"kind": "help", "title": "Fourth"}).json()["message"] == "asks"  # 3 open at most
    logic.close_ask(con, mod, help_["id"], True)
    ask3 = logic.create_ask(con, mod, {"kind": "project", "title": "A third", "skills": [web["id"]]}, True)
    week = [r[0] for r in con.execute("SELECT user_id FROM ask_pings WHERE ask_id = ?", (ask3["id"],))]
    assert len(week) == 5
    con.execute("UPDATE ask_pings SET at = at - 3600 WHERE ask_id = ?", (ask3["id"],))
    logic.close_ask(con, mod, ask3["id"], False)
    ask4 = logic.create_ask(con, mod, {"kind": "project", "title": "A fourth", "skills": [web["id"]]}, True)
    assert not set(r[0] for r in con.execute("SELECT user_id FROM ask_pings WHERE ask_id = ?", (ask4["id"],))) & set(week)  # 2 this week
    logic.close_ask(con, mod, ask4["id"], None)
    held = logic.create_ask(con, mod, {"kind": "help", "title": "No AI answer"}, None)                 # no AI: a moderator first
    assert (held["status"], held["why"]) == ("held", "check") and all(a["id"] != held["id"] for a in logic.asks(con, stu))

    # an offer: nothing of either side's Telegram before Accept, then each gets the other's
    bob = people["bob"]
    con.execute("UPDATE users SET tg_username = 'bob_tg' WHERE id = ?", (bob.id,))
    con.execute("UPDATE users SET tg_username = 'mod_tg' WHERE id = ?", (mod.id,))
    assert logic.contact(con, bob, aid=ask["id"]) == {"status": "pending"}
    before = json.dumps([logic.contacts(con, mod), logic.contacts(con, bob), logic.asks(con, bob), logic.asks(con, mod), logic.search_people(con, stu, web["id"])])
    assert "bob_tg" not in before and "mod_tg" not in before and "telegram" not in before
    cid = con.execute("SELECT id FROM contacts").fetchone()[0]
    tok = con.execute("SELECT token FROM contacts").fetchone()[0]
    assert logic.decide_contact(con, bob.id, cid, True, tok) is None                                 # only the asked side decides
    assert logic.decide_contact(con, mod.id, cid, True) is None                                      # never without the offer's token
    assert logic.decide_contact(con, mod.id, cid, True, tok) == "accepted"
    assert logic.contacts(con, bob)[0]["telegram"] == "https://t.me/mod_tg" and logic.contacts(con, mod)[0]["telegram"] == "https://t.me/bob_tg"
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'contact_ok'")} == {bob.id, mod.id}

    # a block: no offers either way, out of each other's matches and lists
    eve = people["eve"]
    logic.block(con, eve, mod.id)
    with pytest.raises(logic.ApiError):
        logic.contact(con, eve, aid=ask["id"])
    assert all(a["id"] != ask["id"] for a in logic.asks(con, eve))
    assert eve.id not in {x["person"]["id"] for x in logic.ask_people(con, mod, ask["id"])}

    # expiry: gone from the lists
    con.execute("UPDATE asks SET expires_at = ? WHERE id = ?", (logic.now() - 1, ask2["id"]))
    assert ask2["id"] not in [a["id"] for a in logic.asks(con, bob)]

    # reports: three from accounts over two weeks old AND the AI agreeing hide it; younger accounts or no AI: it stays
    rep = lambda h: c.post("/api/reports", headers=h, json={"target": "ask", "id": ask["id"], "reason": "spam"}).status_code  # noqa: E731
    hs = [tma(82 + i) for i in (1, 3, 4)]                                                             # cat, eve, fay
    # FORUM=1 is the staff's: only who passes its gate reports its requests (forum.may_touch_ask), so the three are staff here
    con.execute("UPDATE users SET role = 'moderator' WHERE id IN (?, ?, ?)", tuple(people[n].id for n in ("cat", "eve", "fay")))
    monkeypatch.setattr(ai, "screen", lambda *a, **k: asyncio.sleep(0, result=False))
    assert all(rep(h) == 204 for h in hs)
    assert logic.one(con, "SELECT status FROM asks WHERE id = ?", ask["id"])[0] == "live"             # new accounts don't count
    con.execute("UPDATE reports SET status = 'dismissed' WHERE target = 'ask' AND target_id = ?", (ask["id"],))
    con.execute("UPDATE users SET created_at = created_at - 15 * 86400")
    con.execute("UPDATE students SET consent_version = ? WHERE user_id != ?", (c.app.state.policy, mod.id))
    screened = []
    async def rescreen(*args, only):
        screened.append(only)
        return False
    monkeypatch.setattr(ai, "screen", rescreen)
    assert all(rep(h) == 204 for h in hs) and screened == [ai.EU_ONLY]
    assert tuple(con.execute("SELECT status, why FROM asks WHERE id = ?", (ask["id"],)).fetchone()) == ("hidden", "reports")
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'ask_hidden' AND user_id = ?", (mod.id,)).fetchone()  # the author is told

    # deleting an account takes its skills, requests, offers, blocks and pings
    delete_now(c, cfg, tma(85))                                                                       # eve
    for t, col in (("user_skills", "user_id"), ("blocks", "user_id"), ("ask_pings", "user_id"), ("contacts", "from_id")):
        assert not con.execute(f"SELECT 1 FROM {t} WHERE {col} = ?", (eve.id,)).fetchone(), t


def test_forum_bot_cards(env, monkeypatch):
    """The forum's cards in the bot: an offer with Accept / Decline (only the asked side's tap counts), a ping with a
    link to the request, and support for the stop button on older pings."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    a, b = (logic.Viewer(login(c, uid, n)["id"], "user", True) for uid, n in ((90, "ann"), (91, "ben")))
    web = con.execute("SELECT id FROM skills WHERE name = 'web'").fetchone()[0]
    logic.set_my_forum(con, b, {"skills": [web], "open": True, "pings": True})
    ask = logic.create_ask(con, a, {"kind": "project", "title": "A site", "skills": [web]}, True)
    row = lambda kind: {**dict(con.execute("SELECT * FROM bot_outbox WHERE kind = ?", (kind,)).fetchone()), "lang": "en"}  # noqa: E731
    text, button, start = bot._render(con, row("ask_match"))
    assert text == texts.bot_message("en", "ask_match")[0] and "A site" not in text   # their words stay in the app
    assert button == texts.bot_message("en", "ask_match")[1] and start == f"fa_{ask['id']}"
    logic.contact(con, b, aid=ask["id"])
    text, _, keys = bot._render(con, row("contact_ask"))
    cid, tok = con.execute("SELECT id, token FROM contacts").fetchone()
    assert "Ben" in text and "A site" in text and [k["callback_data"] for k in keys[0]] == [f"ct:{cid}:{tok}:y", f"ct:{cid}:{tok}:n"]
    sent = []
    async def tg(cfg, http, method, body, files=None):
        sent.append(body)
    monkeypatch.setattr(bot, "_tg", tg)
    class Http:
        async def post(self, *a, **k):
            return None
    tap = lambda who, data: asyncio.run(bot._tapped(cfg, Http(), con, {"id": "q", "from": {"id": who}, "data": data,  # noqa: E731
                                                                    "message": {"message_id": 5, "chat": {"id": who}}}))
    tap(91, f"ct:{cid}:{tok}:y")                                                                      # Ben can't accept his own offer
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "pending" and sent[-1]["text"] == texts.bot_message("ru", "contact_gone")[0]
    tap(90, f"ct:{cid}:y")                                                                            # a button without its token: nothing
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "pending"
    tap(90, f"ct:{cid}:{tok}:y")
    assert con.execute("SELECT status FROM contacts").fetchone()[0] == "accepted"
    assert bot._render(con, {**row("contact_ok"), "ref": f"co:{cid}:to:{tok}"})[2][0][0]["url"].startswith("tg://user?id=")  # no username: by ID
    tap(91, "ps:0")
    assert con.execute("SELECT ask_pings FROM users WHERE id = ?", (b.id,)).fetchone()[0] == 0
    assert bot._render(con, row("ask_match")) is None                                                 # pings off: quiet


def test_forum_moderator_queue(env):
    """What waits for the forum's moderators: requests the AI didn't pass and skills not public yet; release puts a
    request live (and its pings out), hide takes it down and tells its author; only moderators see or act."""
    import dataclasses
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, forum=True)))
    con = db.connect(cfg.db_path)
    mod = logic.Viewer(login(c, 95, "mod")["id"], "moderator", True)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod.id,))
    stu = logic.Viewer(login(c, 96, "stu")["id"], "user", True)
    held = logic.create_ask(con, stu, {"kind": "help", "title": "Held one"}, None)
    other = logic.create_ask(con, stu, {"kind": "help", "title": "Flagged one"}, False)
    new = logic.add_skill(con, stu, "lockpicking")
    q = c.get("/api/forum/mod", headers=tma(95)).json()
    assert [a["id"] for a in q["held"]] == [held["id"], other["id"]] and [s["name"] for s in q["skills"]] == ["lockpicking"]
    assert c.get("/api/forum/mod", headers=tma(96)).status_code == 403
    with pytest.raises(logic.ApiError):
        logic.mod_queue(con, stu)
    assert c.post(f"/api/forum/asks/{held['id']}/release", headers=tma(95)).status_code == 200
    assert con.execute("SELECT status FROM asks WHERE id = ?", (held["id"],)).fetchone()[0] == "live"
    assert c.post(f"/api/forum/asks/{other['id']}/hide", headers=tma(95)).status_code == 204
    assert con.execute("SELECT status, why FROM asks WHERE id = ?", (other["id"],)).fetchone()[:] == ("hidden", "moderator")
    assert con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'ask_hidden' AND user_id = ?", (stu.id,)).fetchone()
    assert c.patch(f"/api/forum/skills/{new['id']}", headers=tma(95), json={"approve": True}).json()["public"] is True
    assert c.get("/api/forum/mod", headers=tma(95)).json() == {"held": [], "skills": [], "holds": []}
    # three reports from old accounts, no AI word: a moderator's day, counted from the third report
    t0 = int(time.time())
    for i, uid in enumerate((97, 98, 99)):
        rid = login(c, uid, f"r{uid}")["id"]
        con.execute("UPDATE users SET created_at = ? WHERE id = ?", (t0 - 30 * 86400, rid))
        con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, status, created_at) VALUES (?, 'ask', ?, 'spam', 'open', ?)",
                    (rid, held["id"], t0 - 3600 + i * 60))
        q = c.get("/api/forum/mod", headers=tma(95)).json()["held"]
        assert q == [] if i < 2 else [(a["id"], a["status"], a["dueAt"]) for a in q] == [(held["id"], "reported", t0 - 3600 + 120 + 86400)]
    # what the privacy policy promises: a request 30 days after it ran out, a ping's record after 30 days
    con.execute("UPDATE asks SET expires_at = ? WHERE id = ?", (t0 - 31 * 86400, held["id"]))
    con.execute("INSERT INTO ask_pings (ask_id, user_id, at) VALUES (?, ?, ?), (?, ?, ?)", (held["id"], mod.id, t0, other["id"], mod.id, t0 - 31 * 86400))
    logic.forum.forum_sweep(con)
    assert [r[0] for r in con.execute("SELECT id FROM asks")] == [other["id"]] and not con.execute("SELECT 1 FROM ask_pings").fetchone()


def test_forum_founder_only(env):
    """FORUM=founder: the Creator alone gets the forum; the staff get 403; the policy and consent stay as they are."""
    import dataclasses
    c, cfg = env
    login(c, 90, "stu")
    c.get("/api/me", headers=tma(91))
    c.get("/api/me", headers=tma(92))
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 91")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 92")
    on = TestClient(server.create(dataclasses.replace(cfg, forum_founder=True)))
    assert on.get("/api/forum/me", headers=tma(91)).status_code == 200
    assert on.get("/api/forum/me", headers=tma(92)).status_code == 403
    assert on.get("/api/forum/me", headers=tma(90)).status_code == 403
    assert on.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT


def test_student_forum_flag(env):
    """BOARD (section 12: the assistant, sign-up questions, the map) off, staff or all: the old in-app forum is gone in
    every case (the forum channel replaced it, Nov 1); BOARD=1 shows section 12 and asks the new version."""
    import dataclasses
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 1")
    login(c, 2, "bob")
    for board, bob, version in (("", False, logic.CONSENT), ("staff", False, logic.CONSENT), ("all", True, logic.CONSENT)):
        app = server.create(dataclasses.replace(cfg, board=board))
        with TestClient(app) as x:
            assert x.get("/api/threads", headers=tma(1)).status_code == 404 and x.post("/api/threads", headers=tma(2), json={}).status_code in (404, 405)
            me = x.get("/api/me", headers=tma(2)).json()
            assert me["consentNow"] == version and me["board"] is bob
            assert x.post("/api/reports", headers=tma(2), json={"target": "thread", "id": 1, "reason": "spam"}).status_code == 400  # no such target any more
    with TestClient(server.create(dataclasses.replace(cfg, board="all", forum=True))) as x:
        assert x.get("/api/me", headers=tma(2)).json()["consentNow"] == logic.CONSENT
    con.close()
