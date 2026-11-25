"""Casting: recruitment rounds, in parts and for the whole club."""
from __future__ import annotations

import time

from kbtu import bot, casting, db, logic, texts
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_casting(env):
    """Casting (PLAN "Casting"): a club opens a round with its tags as departments and a few questions; its
    followers hear it; students apply (a department's own question only if they picked it); the casting team (Head+ by
    default) sees the applications with what only the app knows, votes, takes one into a department; the results in one
    tap make the accepted members with the department's tag and tell everyone."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "head"), (10, "ann"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 10, 11, 12)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'head', 0)", (uid[20], uid[21]))
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (1, 1, 'SMM', '#FF4FA3', 0), (2, 1, 'HR', '#2FBF71', 0)")
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (uid[12],))
    body = {"title": "Recruitment 2026", "picks": 2, "closesAt": int(time.time()) + 7 * 86400,
            "departments": [{"tagId": 1, "about": "Posts and reels", "places": 3}, {"tagId": 2, "about": "People"}],
            "questions": [{"kind": "one", "text": "Hours a week", "options": ["1-4", "5-8"]}, {"kind": "long", "text": "Why us?"},
                          {"kind": "link", "text": "Portfolio", "tagId": 1}]}
    assert c.post("/api/orgs/1/round", headers=tma(10), json=body).status_code == 403                # not the team
    r = c.post("/api/orgs/1/round", headers=tma(21), json=body).json()                               # a Head may (casting right)
    assert r["team"] and [d["name"] for d in r["departments"]] == ["SMM", "HR"] and len(r["questions"]) == 3
    assert c.post("/api/orgs/1/round", headers=tma(20), json=body).status_code == 409                # one round at a time
    assert [tuple(x) for x in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'round_open'")] == [(uid[12],)]  # the follower hears it
    rid, q = r["id"], {x["text"]: str(x["id"]) for x in r["questions"]}

    seen = c.get("/api/orgs/1/round", headers=tma(10)).json()
    assert "counts" not in seen and seen["open"] and seen["mine"] is None
    apply = lambda tg, deps, answers: c.post(f"/api/rounds/{rid}/apply", headers=tma(tg), json={"departments": deps, "answers": answers})  # noqa: E731
    assert apply(10, [1, 2], {q["Hours a week"]: "5-8", q["Why us?"]: "I post daily"}).status_code == 400  # SMM wants the portfolio
    assert apply(10, [1, 2], {q["Hours a week"]: "9-12", q["Why us?"]: "x", q["Portfolio"]: "behance.net/ann"}).status_code == 400  # not an option
    mine = apply(10, [1, 2], {q["Hours a week"]: "5-8", q["Why us?"]: "I post daily", q["Portfolio"]: "behance.net/ann"}).json()["mine"]
    assert mine["departments"] == [1, 2] and mine["stage"] == "sent"
    assert apply(11, [2], {q["Hours a week"]: "1-4", q["Why us?"]: "I like people"}).status_code == 200  # HR only: no portfolio asked
    assert apply(21, [2], {q["Why us?"]: "x"}).status_code == 409                                    # already in the club
    assert c.get("/api/orgs/1", headers=tma(10)).json()["round"] == {"id": rid, "closesAt": body["closesAt"], "applied": True, "quick": False}

    assert c.get(f"/api/rounds/{rid}/apps", headers=tma(10)).status_code == 403
    apps = {a["fullName"]: a for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(21)).json()}
    ann, bob = apps["Testov Ann"], apps["Testov Bob"]
    assert ann["person"]["id"] == c.get("/api/me", headers=tma(10)).json()["id"]                  # the student, not the application's id
    assert ann["answers"][q["Portfolio"]] == "behance.net/ann" and ann["came"] == 0 and not ann["before"]
    assert c.post(f"/api/round-apps/{ann['id']}/vote", headers=tma(21), json={"verdict": "next", "stars": 4, "note": "Strong reels"}).json()["stage"] == "next"
    c.post(f"/api/round-apps/{bob['id']}/vote", headers=tma(20), json={"verdict": "no"})
    votes = {a["fullName"]: a for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(20)).json()}["Testov Ann"]["votes"]
    assert votes == [{"by": "Head T", "mine": False, "verdict": "next", "stars": 4, "note": "Strong reels"}]
    # interviews: slots, the shortlisted invited, a time booked (reminders queued), who came
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 2 * 86400 + 5 * 3600))
    assert c.post(f"/api/rounds/{rid}/invite", headers=tma(21)).status_code == 409                          # no slots yet
    got = c.post(f"/api/rounds/{rid}/slots", headers=tma(21), json={"date": day, "from": "15:00", "to": "16:00", "minutes": 20, "place": "Room 305"}).json()
    assert len(got) == 3 and got[0]["left"] == 1
    # an open window: the whole from..to as one slot for everyone at once; it goes again while nobody booked it
    wide = c.post(f"/api/rounds/{rid}/slots", headers=tma(21), json={"date": day, "from": "17:00", "to": "21:00", "minutes": 240, "capacity": 500}).json()
    assert len(wide) == 4 and wide[3]["minutes"] == 240 and wide[3]["left"] == 500
    assert c.post(f"/api/rounds/{rid}/slots", headers=tma(21), json={"date": day, "from": "17:00", "to": "21:00", "minutes": 200, "capacity": 500}).status_code == 400  # not the whole window
    assert len(c.delete(f"/api/round-slots/{wide[3]['id']}", headers=tma(21)).json()) == 3
    assert c.get(f"/api/rounds/{rid}/slots", headers=tma(10)).status_code == 403                              # not invited yet
    assert c.post(f"/api/rounds/{rid}/invite", headers=tma(21)).json() == {"invited": 1}                      # Ann only: next
    assert c.get("/api/orgs/1/round", headers=tma(10)).json()["mine"]["invited"]
    w = c.post(f"/api/rounds/{rid}/slots", headers=tma(21), json={"date": day, "from": "17:00", "to": "21:00", "minutes": 240, "capacity": 500}).json()[3]
    took = c.post(f"/api/rounds/{rid}/book", headers=tma(10), json={"slotId": w["id"]})                   # an open window is booked like any time
    assert took.status_code == 200 and [x["id"] for x in took.json() if x.get("mine")] == [w["id"]]
    c.post(f"/api/rounds/{rid}/book", headers=tma(10), json={"slotId": None})
    assert casting.nudge_now(con, rid, dry=True) == 1 and casting.nudge_now(con, rid) == 1 and casting.nudge_now(con, rid) == 0   # admin round-nudge: now, once
    assert con.execute("SELECT send_after <= ? FROM bot_outbox WHERE kind = 'round_iv_nudge'", (logic.now(),)).fetchone()[0] == 1
    assert len(c.delete(f"/api/round-slots/{w['id']}", headers=tma(21)).json()) == 3
    mine = c.post(f"/api/rounds/{rid}/book", headers=tma(10), json={"slotId": got[1]["id"]}).json()
    assert [x["id"] for x in mine if x.get("mine")] == [got[1]["id"]]
    refs = [x[0] for x in con.execute("SELECT ref FROM bot_outbox WHERE kind = 'round_iv_remind' AND sent_at IS NULL")]
    assert sorted(x.split(":")[-1] for x in refs) == ["eve", "hour"]                                           # the evening before, an hour before
    assert c.post(f"/api/rounds/{rid}/book", headers=tma(11), json={"slotId": got[1]["id"]}).status_code == 403  # Bob wasn't invited
    assert c.delete(f"/api/round-slots/{got[1]['id']}", headers=tma(21)).status_code == 409                   # booked: it stays
    assert len(c.delete(f"/api/round-slots/{got[2]['id']}", headers=tma(21)).json()) == 2
    assert c.get(f"/api/rounds/{rid}/slots", headers=tma(21)).json()[1]["people"][0]["fullName"] == "Testov Ann"
    assert c.post(f"/api/round-apps/{ann['id']}/came", headers=tma(21), json={"came": True}).json() == {"showed": True}
    nudge = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_iv_nudge'").fetchone()
    assert bot._render(con, nudge) is None                                                                      # she picked a time
    remind = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_iv_remind'").fetchone()
    assert "Room 305" in bot._render(con, remind)[0]

    assert c.post(f"/api/round-apps/{ann['id']}/decide", headers=tma(20), json={"stage": "yes", "tagId": 1}).json()["takenTag"] == 1
    assert c.get("/api/orgs/1/round", headers=tma(20)).json()["counts"] == {"yes": 1, "no": 1}

    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": True}).json() == {"accepted": 1, "declined": 1}
    assert con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (uid[10],)).fetchone()[0] == "member"
    assert [tuple(x) for x in con.execute("SELECT tag_id FROM member_tags WHERE user_id = ?", (uid[10],))] == [(1,)]
    assert con.execute("SELECT 1 FROM org_members WHERE org_id = 1 AND user_id = ?", (uid[11],)).fetchone() is None
    sent = {x[0]: x[1] for x in con.execute("SELECT kind, user_id FROM bot_outbox WHERE kind IN ('round_yes', 'round_no')")}
    assert sent == {"round_yes": uid[10], "round_no": uid[11]}
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_yes'").fetchone()
    assert "SMM" in bot._render(con, row)[0]
    assert c.get("/api/orgs/1/round", headers=tma(11)).json() is None
    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": True}).status_code == 409
    # sixty days after the results the answers and notes go; who applied and how it ended stay
    con.execute("UPDATE rounds SET sent_at = ? WHERE id = ?", (int(time.time()) - 61 * 86400, rid))
    casting.forget(con)
    assert [x[0] for x in con.execute("SELECT answers FROM round_apps WHERE round_id = ?", (rid,))] == ["{}", "{}"]
    assert con.execute("SELECT COUNT(*) FROM round_votes").fetchone()[0] == 0
    assert sorted(x[0] for x in con.execute("SELECT stage FROM round_apps WHERE round_id = ?", (rid,))) == ["no", "yes"]


def test_casting_in_parts(env):
    """Results in parts (club presidents, Nov 6): a send tells only those decided and not told yet, the round stays open
    and keeps taking applications; nobody hears twice; a later send covers the new decisions only; the told can't be
    changed or re-applied. The group invite (https://t.me/... only) reaches the accepted in the app, never the declined;
    the bot's message only says it's there."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ann"), (11, "bob"), (12, "cat"), (13, "dan")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (10, 11, 12, 13)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'jp', 'club', 'Japan', 'JP', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    body = {"title": "Recruiting", "picks": 1, "closesAt": int(time.time()) + 7 * 86400, "departments": [], "questions": []}
    for bad in ("http://t.me/+abc", "https://evil.com/t.me/x", "https://t.me/", "https://t.me/+a b", "t.me/+abc"):
        assert c.post("/api/orgs/1/round", headers=tma(20), json={**body, "groupLink": bad}).status_code == 400, bad
    link = "https://t.me/+AbC_d-12"
    r = c.post("/api/orgs/1/round", headers=tma(20), json={**body, "groupLink": link}).json()
    rid = r["id"]
    assert r["groupLink"] == link
    for tg in (10, 11, 12):
        c.post(f"/api/rounds/{rid}/apply", headers=tma(tg), json={"departments": [], "answers": {}})
    apps = {a["fullName"]: a["id"] for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(20)).json()}
    decide = lambda name, stage: c.post(f"/api/round-apps/{apps[name]}/decide", headers=tma(20), json={"stage": stage})  # noqa: E731
    decide("Testov Ann", "yes"), decide("Testov Bob", "no")                   # Cat: still undecided

    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": False}).json() == {"accepted": 1, "declined": 1}
    live = c.get("/api/orgs/1/round", headers=tma(20)).json()
    assert live["status"] == "open" and live["open"]                             # the round goes on
    told = lambda: sorted((x[0], x[1]) for x in con.execute("SELECT kind, user_id FROM bot_outbox WHERE kind IN ('round_yes', 'round_no')"))  # noqa: E731
    assert told() == sorted([("round_yes", uid[10]), ("round_no", uid[11])])
    assert con.execute("SELECT 1 FROM org_members WHERE org_id = 1 AND user_id = ?", (uid[10],)).fetchone()
    ann = c.get("/api/orgs/1/round", headers=tma(10)).json()
    assert ann["mine"]["stage"] == "yes" and ann["groupLink"] == link            # the accepted see the group
    bob = c.get("/api/orgs/1/round", headers=tma(11)).json()
    assert bob["mine"]["stage"] == "no" and "groupLink" not in bob
    cat = c.get("/api/orgs/1/round", headers=tma(12)).json()
    assert cat["mine"]["stage"] == "sent" and "groupLink" not in cat
    assert c.get("/api/orgs/1", headers=tma(10)).json()["groupLink"] == link     # and in the club's card, as a member
    assert c.get("/api/orgs/1", headers=tma(11)).json()["groupLink"] is None
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'round_yes'").fetchone()
    text, button, start = bot._render(con, row)
    assert link not in text and start == "cl_1" and button == texts.bot_message(row["lang"], "round_yes_group", org="")[1]  # a template and a button into the app
    # a told result stands: no change, no re-applying, no withdrawing
    assert decide("Testov Bob", "yes").status_code == 409
    assert c.post(f"/api/rounds/{rid}/apply", headers=tma(11), json={"departments": [], "answers": {}}).status_code == 409
    c.delete(f"/api/rounds/{rid}/apply", headers=tma(11))
    assert c.get("/api/orgs/1/round", headers=tma(11)).json()["mine"]["stage"] == "no"

    # nothing new decided: a send tells nobody; then Dan applies late, Cat and Dan are decided, a later send covers them alone
    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": False}).json() == {"accepted": 0, "declined": 0}
    c.post(f"/api/rounds/{rid}/apply", headers=tma(13), json={"departments": [], "answers": {}})
    apps = {a["fullName"]: a["id"] for a in c.get(f"/api/rounds/{rid}/apps", headers=tma(20)).json()}
    decide("Testov Cat", "no"), decide("Testov Dan", "yes")
    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": False}).json() == {"accepted": 1, "declined": 1}
    assert len(told()) == 4 and len(set(told())) == 4                              # each one heard exactly once
    # finishing: the round is over, nobody hears again
    assert c.post(f"/api/rounds/{rid}/send", headers=tma(20), json={"final": True}).json() == {"accepted": 0, "declined": 0}
    assert len(told()) == 4 and c.get("/api/orgs/1/round", headers=tma(20)).json() is None


def test_casting_whole_club(env):
    """Casting audit (Nov 2): a club without departments recruits for the whole club (accepted join without a tag);
    one department: nothing to pick; picks never exceed the departments; the round's own "what's next" (in person,
    dates, place) is the app's to show, at most 300 characters, and it puts the audition into the student's steps."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ann")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    ann = con.execute("SELECT id FROM users WHERE tg_id = 10").fetchone()[0]
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'jp', 'club', 'Japan', 'JP', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    body = {"title": "Recruiting", "picks": 3, "closesAt": int(time.time()) + 7 * 86400, "departments": [], "questions": [{"kind": "short", "text": "Why?"}]}
    assert c.post("/api/orgs/1/round", headers=tma(20), json={**body, "nextText": "x" * 301}).status_code == 400
    nxt = "Come to the audition: Nov 3-12, Kazybek bi, 1st floor"
    r = c.post("/api/orgs/1/round", headers=tma(20), json={**body, "nextText": nxt}).json()
    assert r["departments"] == [] and r["picks"] == 1 and r["nextText"] == nxt and r["interviews"]
    seen = c.get("/api/orgs/1/round", headers=tma(10)).json()
    assert seen["nextText"] == nxt and seen["interviews"]
    q = str(r["questions"][0]["id"])
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=tma(10), json={"departments": [1], "answers": {q: "x"}}).status_code == 400
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=tma(10), json={"departments": [], "answers": {q: "Anime"}}).json()["mine"]["departments"] == []
    app = c.get(f"/api/rounds/{r['id']}/apps", headers=tma(20)).json()[0]
    assert c.post(f"/api/round-apps/{app['id']}/decide", headers=tma(20), json={"stage": "yes"}).json() == {"stage": "yes", "takenTag": None}
    assert c.post(f"/api/rounds/{r['id']}/send", headers=tma(20), json={"final": True}).json() == {"accepted": 1, "declined": 0}
    assert con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (ann,)).fetchone()[0] == "member"
    # one department: the student picks nothing, it's that one; no next text and no slots: no audition step
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (1, 1, 'Art', '#FF4FA3', 0)")
    con.execute("DELETE FROM org_members WHERE user_id = ?", (ann,))
    r = c.post("/api/orgs/1/round", headers=tma(20), json={**body, "departments": [{"tagId": 1}]}).json()
    assert r["picks"] == 1 and r["nextText"] == "" and not r["interviews"]
    q = str(r["questions"][0]["id"])
    assert c.post(f"/api/rounds/{r['id']}/apply", headers=tma(10), json={"departments": [], "answers": {q: "Draw"}}).json()["mine"]["departments"] == [1]
    assert c.patch(f"/api/rounds/{r['id']}", headers=tma(20), json={**body, "departments": [{"tagId": 1}], "nextText": nxt}).json()["nextText"] == nxt
    # quick (Nov 3): nothing to answer and one department at most, so the app sends it in one tap
    assert c.get("/api/orgs/1", headers=tma(10)).json()["round"]["quick"] is False
    con.execute("DELETE FROM round_questions WHERE round_id = ?", (r["id"],))
    assert c.get("/api/orgs/1", headers=tma(10)).json()["round"]["quick"] is True
