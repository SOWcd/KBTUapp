"""Events: sign-up, the door, comments and questions, ratings, calendar, team-only events, seats and changes."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from kbtu import ai, bot, calpage, db, logic, app as server, texts
from test_core import _board_on, _club_runs, delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def test_walk_in(env):
    """A badge QR at the door (§4.4): free events register and check in on the spot; made-up or paid: no."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P = tma(20, "Pres")
    start = int(time.time()) - 1800   # started half an hour ago: the door is open, a walk-in is late
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    qr = c.get("/api/me", headers=tma(21, "Ali")).json()["qr"]
    assert re.fullmatch(r"\d+_[A-Z2-7]{10}", qr) and c.get("/api/me", headers=tma(21, "Ali")).json()["qr"] == qr   # made once, stable
    scan = lambda raw: c.post("/api/events/1/checkin", headers=P, json={"code": raw}).json()
    link = lambda q: f"https://t.me/KBTUappBot?startapp=u_{q}"

    assert scan(link(f"{ali['id']}_AAAAAAAAAA"))["result"] == "not_found"          # a QR made from a user id
    r = scan(link(qr))
    assert (r["result"], r["walkIn"], r["late"] >= 29, r["person"]["id"]) == ("ok", True, True, ali["id"])
    assert scan(link(qr))["result"] == "already"
    assert [a["walkIn"] for a in c.get("/api/events/1/attendees", headers=P).json()] == [True]
    con.execute("UPDATE events SET price = 2000, pay_to_name = 'Pres', pay_phone = '+77000000000' WHERE id = 1")
    assert scan(link(c.get("/api/me", headers=tma(22, "Zhan")).json()["qr"]))["result"] == "paid"   # paid: a ticket only


def test_attendees_csv(env):
    """The attendee file (SPEC §6): the club's Head+ only, Excel-friendly (BOM, ';'), a cell a spreadsheet would run
    as a formula defused, every export in the audit log."""
    import codecs
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, created_by, created_at, updated_at, needs_phone)
        VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0, 1)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("UPDATE students SET phone = '+77001234567' WHERE user_id = ?", (ali["id"],))  # the event asks for it
    c.post("/api/events/1/registration", headers=tma(21, "Ali"))
    con.execute("UPDATE students SET phone = '+77001234567', email = '=HYPERLINK(1)' WHERE user_id = ?", (ali["id"],))
    assert c.post("/api/events/1/attendees/export", headers=tma(21, "Ali")).status_code == 403   # not the club's team
    e, people = logic.attendees_export(con, logic.Viewer(pres["id"], "user", True), 1)
    name, data, caption = texts.attendees_csv("en", e["title"], people)
    assert data.startswith(codecs.BOM_UTF8) and caption == "Attendees: Talk"
    head, row = data.decode("utf-8-sig").splitlines()
    assert head.split(";") == list(texts.CSV_HEAD["en"])
    assert row.split(";")[:13] == ["Testov", "Ali", "", "", "", "", "", "24Bali", "2", "SITE", "'=HYPERLINK(1)", "'+77001234567", "going"]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'attendees_export'").fetchone()[0] == 1


def test_checkin_by_name(env):
    """No QR at the door (a dead phone, §4.4): a Member checks a going person in from the door list (short names only),
    marked "by hand" for the organizer and the CSV; a wrong tap is taken back within 10 minutes; not going: refused."""
    c, cfg = env
    pres, mem, ali, zhan = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali"), login(c, 73, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'TTT234', 0, 0)", (ali["id"],))
    M = tma(71, "Mem")
    assert c.get("/api/events/1/door", headers=tma(73, "Zhan")).status_code == 403             # the team only
    door = c.get("/api/events/1/door", headers=M).json()
    assert [(d["person"]["name"], d["checkedInAt"]) for d in door] == [("Ali T", None)]       # a short name
    r = c.post("/api/events/1/checkin", headers=M, json={"userId": ali["id"]}).json()
    assert (r["result"], r["person"]["id"], r["came"]) == ("ok", ali["id"], 1)
    assert c.post("/api/events/1/checkin", headers=M, json={"userId": zhan["id"]}).json()["result"] == "not_found"
    assert c.post("/api/events/1/checkin", headers=M, json={"userId": mem["id"]}).status_code == 403  # not myself at the door
    assert [a["manual"] for a in c.get("/api/events/1/attendees", headers=tma(70, "Pres")).json()] == [True]
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 204       # a wrong tap
    assert c.get("/api/events/1/door", headers=M).json()[0]["checkedInAt"] is None
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 409       # nothing to take back
    con.execute("UPDATE registrations SET checked_in_at = ?, checkin_manual = 1", (int(time.time()) - 3600,))
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 409       # too late to undo
    e, people = __import__("kbtu.logic", fromlist=["x"]).attendees_export(con, __import__("kbtu.logic", fromlist=["x"]).Viewer(pres["id"], "user", True), 1)
    assert texts.attendees_csv("ru", e["title"], people)[1].decode("utf-8-sig").splitlines()[1].endswith(";" + texts.CSV_STATUS["ru"]["yes"])


def test_event_updates(env):
    """An organizer's update: Head+ only, pinned on the event for everyone, the bot tells the people going
    (our template, never the organizer's words), three a day at most; deleting it drops the queued message."""
    c, cfg = env
    pres, mem, ali = login(c, 80, "pres"), login(c, 81, "mem"), login(c, 82, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    c.post("/api/events/1/registration", headers=tma(82, "Ali"))
    P = tma(80, "Pres")
    assert c.post("/api/events/1/updates", headers=tma(81, "Mem"), json={"body": "Side door"}).status_code == 403   # Head+
    ups = c.post("/api/events/1/updates", headers=P, json={"body": "Entrance by the side door"}).json()
    assert [u["body"] for u in ups] == ["Entrance by the side door"]
    assert c.get("/api/events/1", headers=tma(82, "Ali")).json()["updates"][0]["canDelete"] is False
    msg = con.execute("SELECT user_id, kind, ref FROM bot_outbox WHERE kind = 'event_update'").fetchall()
    assert [(m[0], m[1]) for m in msg] == [(ali["id"], "event_update")]
    text = bot._render(con, {"kind": "event_update", "ref": msg[0][2], "lang": "en", "user_id": ali["id"]})
    assert text[2] == "ev_1" and "Side door" not in text[0] and "Hack" in text[0]          # the template, not the words
    c.post("/api/events/1/updates", headers=P, json={"body": "Bring a laptop"})
    c.post("/api/events/1/updates", headers=P, json={"body": "We start at 19:15"})
    assert c.post("/api/events/1/updates", headers=P, json={"body": "One more"}).status_code == 429   # three a day
    assert c.delete(f"/api/events/1/updates/{ups[0]['id']}", headers=P).status_code == 204
    assert bot._render(con, {"kind": "event_update", "ref": msg[0][2], "lang": "en", "user_id": ali["id"]}) is None


def test_ratings(env):
    """One tap after the event: only people checked in, from the end until 7 days later; anonymous to the club
    (average, counts, comments without names; from three ratings on); the bot asks an hour after the end unless reminders are off."""
    c, cfg = env
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    for uid in (ali["id"], zhan["id"]):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', ?, 0, 0)", (uid, f"T{uid}AB"))
    P, A, Z = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan")
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "ok"
    ask = con.execute("SELECT send_after FROM bot_outbox WHERE kind = 'rate' AND user_id = ?", (ali["id"],)).fetchone()
    assert ask and ask[0] == start + 3600 + 3600                                          # an hour after the end
    dismiss = "/api/events/1/rating/dismiss"
    assert c.put(dismiss, headers=A).status_code == 403                                   # not over yet
    assert c.put("/api/events/1/rating", headers=A, json={"score": 5}).status_code == 403    # not over yet
    con.execute("UPDATE events SET ends_at = ? WHERE id = 1", (int(time.time()) - 60,))
    assert c.get("/api/events/past?mine=1", headers=A).json()[0]["my"]["ratingDismissed"] is False
    assert c.put(dismiss, headers=Z).status_code == 403                                   # didn't come
    assert c.put(dismiss, headers={**A, "X-Staff-Event": "1"}).status_code == 403
    assert c.put(dismiss, headers=A).status_code == c.put(dismiss, headers=A).status_code == 204
    assert c.get("/api/events/past?mine=1", headers=A).json()[0]["my"]["ratingDismissed"] is True
    assert c.get("/api/events/1", headers=Z).json()["my"]["ratingDismissed"] is False
    assert c.get("/api/events/1", headers=A).json()["canRate"] is True
    assert c.get("/api/events/1", headers=Z).json()["canRate"] is False                   # didn't come
    assert c.put("/api/events/1/rating", headers=Z, json={"score": 1}).status_code == 403
    assert c.put("/api/events/1/rating", headers=A, json={"score": 9}).status_code == 400
    e = c.put("/api/events/1/rating", headers=A, json={"score": 4, "comment": "Great jury"}).json()
    assert e["myRating"] == 4 and e["ratings"] is None                                    # a student never sees the summary
    assert con.execute("SELECT public_after FROM event_ratings WHERE event_id = 1").fetchone()[0] == e["endsAt"] + logic.organizing.RATE_FOR
    s = c.get("/api/events/1", headers=P).json()["ratings"]
    assert s == {"avg": None, "count": 1, "dist": [], "comments": []}                  # under three: how many, nothing more
    for uid in (pres["id"], zhan["id"]):                                                  # two more (straight in: the rules are above)
        con.execute("INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (1, ?, 5, '', 0)", (uid,))
    s = c.get("/api/events/1", headers=P).json()["ratings"]
    assert s == {"avg": 4.7, "count": 3, "dist": [0, 0, 0, 1, 2], "comments": [{"score": 4, "body": "Great jury", "at": s["comments"][0]["at"]}]}
    assert "name" not in json.dumps(s) if (json := __import__("json")) else True        # anonymous
    m = {"kind": "rate", "ref": "rate:1", "lang": "en", "user_id": ali["id"]}
    assert bot._render(con, m) is None                                                    # rated already: no question


def test_calendar_file(env):
    """"To calendar" on the ticket: the going get a signed link the phone's browser opens with no session."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club, KBTU', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack; night', '305', ?, NULL, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, pres["id"]))
    A = tma(91, "Ali")
    assert c.get("/api/events/1", headers=A).json()["my"] is None
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', 0, 0)", (ali["id"],))
    link = c.get("/api/events/1", headers=A).json()["my"]["ics"]
    r = c.get(link)                                                                       # no Telegram headers
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Hack\\; night" in r.text and "DESCRIPTION:IT Club\\, KBTU\\nhttps://t.me/" in r.text
    assert time.strftime("DTEND:%Y%m%dT%H%M%SZ", time.gmtime(start + 3 * 3600)) in r.text  # no end: three hours
    assert "LOCATION:305" in r.text
    # an online event: the word where the place was, the club and the app's link kept, never the meeting's link
    con.execute("UPDATE events SET place = '', online = 'https://zoom.us/j/123?pwd=secret' WHERE id = 1")
    r = c.get(link)
    assert "LOCATION:Online" in r.text and "DESCRIPTION:IT Club\\, KBTU\\nhttps://t.me/" in r.text and "zoom" not in r.text
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (ali["id"],))
    for audience in ("members", "leaders"):
        con.execute("UPDATE events SET visibility = ? WHERE id = 1", (audience,))
        assert c.get(link).status_code == 404
        assert c.get("/api/events/1", headers=A).json()["my"]["ics"] is None
    assert c.get(link.replace("events/1/", "events/2/")).status_code == 404               # the signature is per event
    assert c.get("/api/events/1/ics").status_code == 404
    assert c.get("/api/events/1/ics?k=%C3%A9").status_code == 404                             # non-ASCII: refused, not a 500
    assert c.get("/api/me", headers={"Authorization": "tma auth_date=1&hash=%C3%A9"}).status_code == 403


def test_bring_a_friend(env):
    """"Bring a friend": my friends and where they stand; one bot card per friend and event; the friend's
    registration credits the first one who asked ("Life of the party"); the card goes quiet once they're in."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 93, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("INSERT INTO friendships VALUES (?, ?, 0)", (min(ali["id"], zhan["id"]), max(ali["id"], zhan["id"])))
    A, Z = tma(91, "Ali"), tma(92, "Zhan")
    assert [(x["person"]["id"], x["state"]) for x in c.get("/api/events/1/invites", headers=A).json()] == [(zhan["id"], "none")]
    assert c.post("/api/events/1/invites", headers=A, json={"userId": dana["id"]}).status_code == 403   # not a friend
    assert c.post("/api/events/1/invites", headers=A, json={"userId": zhan["id"]}).json()[0]["state"] == "invited"
    c.post("/api/events/1/invites", headers=A, json={"userId": zhan["id"]})                            # twice: one card
    cards = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'friend_invite' AND user_id = ?", (zhan["id"],)).fetchall()
    assert len(cards) == 1 and bot._render(con, cards[0])[2] == "ev_1"
    c.post("/api/events/1/registration", headers=Z)
    assert con.execute("SELECT invited_by FROM registrations WHERE user_id = ?", (zhan["id"],)).fetchone()[0] == ali["id"]
    assert bot._render(con, cards[0]) is None                                                           # in already
    assert c.get("/api/events/1/invites", headers=A).json()[0]["state"] == "going"


def test_comments(env):
    """Comments under events and posts (§4.10): students write (500 characters, 10 a minute), the club's Head+ answer
    as the club, take any down and turn the thread off; reports go to the admin's queue, once per person and thing."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali, zhan = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, official) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0, 1)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    P, A, Z, B = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(94, "Boss")
    assert c.get("/api/events/1/comments", headers=tma(95, "Guest")).status_code == 401                # students only
    t = c.post("/api/events/1/comments", headers=A, json={"body": "  Where is the entrance?  "}).json()
    assert [(x["body"], x["person"]["id"], x["canDelete"]) for x in t["items"]] == [("Where is the entrance?", ali["id"], True)]
    assert c.get("/api/events/1", headers=Z).json()["comments"] == 1
    assert c.get("/api/orgs/1/events", headers=P).json()[0]["questions"] == 1                          # waits in Studio
    ping = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_question'").fetchall()
    assert [r["user_id"] for r in ping] == [pres["id"]] and bot._render(con, ping[0])[2] == "cm_1"     # the club's Head+
    assert c.get("/api/events/1/comments", headers=Z).json()["items"][0]["canDelete"] is False
    assert c.post("/api/events/1/comments", headers=Z, json={"body": "x", "asOrg": True}).status_code == 403  # not the club's Head+
    t = c.post("/api/events/1/comments", headers=P, json={"body": "Round the side", "asOrg": True}).json()
    assert t["items"][1]["person"] is None and t["items"][1]["org"]["id"] == 1 and t["canModerate"] is True
    assert c.get("/api/orgs/1/events", headers=P).json()[0]["questions"] == 0                          # answered
    assert bot._render(con, ping[0]) is None                                                            # quiet once answered
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_answer'").fetchall()
    assert [r["user_id"] for r in told] == [ali["id"]] and "answered your question" in bot._render(con, told[0])[0]
    for bad in ("", " ", "x" * 501):
        assert c.post("/api/events/1/comments", headers=Z, json={"body": bad}).status_code == 400
    for n in range(10):
        c.post("/api/events/1/comments", headers=Z, json={"body": f"spam {n}"})
    assert c.post("/api/events/1/comments", headers=Z, json={"body": "one more"}).status_code == 429     # ten a minute
    first = t["items"][0]["id"]
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "spam"}).status_code == 204
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "insult"}).status_code == 204  # quiet repeat
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "boring"}).status_code == 400
    for bad in ("x" * 501, 5, ["a"]):
        assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "other", "note": bad}).status_code == 400
    # the open report is updated, not doubled: the latest reason, the words kept
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "other", "note": "  Rude to the host "}).status_code == 204
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "spam", "note": ""}).status_code == 204
    mine = next(x["id"] for x in c.get("/api/events/1/comments", headers=Z).json()["items"] if x["mine"])
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": mine, "reason": "spam"}).status_code == 404  # my own: delete it
    assert c.get("/api/admin/reports", headers=P).status_code == 403
    assert c.get("/api/me", headers=B).json()["counters"]["inbox"] == 1 and c.get("/api/me", headers=P).json()["counters"]["inbox"] == 0
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(x["target"], x["id"], x["text"], x["count"], x["reasons"]) for x in q] == [("comment", first, "Where is the entrance?", 1, {"spam": 1})]
    assert [(n["reason"], n["note"]) for n in q[0]["notes"]] == [("spam", "Rude to the host")] and "reporter" not in str(q[0])
    assert c.delete(f"/api/comments/{first}", headers=Z).status_code == 403                             # not hers
    assert c.post(f"/api/admin/reports/comment/{first}", headers=B, json={"remove": True}).status_code == 204
    assert c.get("/api/admin/reports", headers=B).json() == [] and c.get("/api/me", headers=B).json()["counters"]["inbox"] == 0
    assert first not in [x["id"] for x in c.get("/api/events/1/comments", headers=A).json()["items"]]
    # a wrong call undone (§2): the admin's take-downs of the last 30 days, and Restore
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=P).status_code == 403
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=B).status_code == 204
    assert first in [x["id"] for x in c.get("/api/events/1/comments", headers=A).json()["items"]]
    # decided once, it may be reported again (it is back); kept this time
    assert c.post("/api/reports", headers=Z, json={"target": "comment", "id": first, "reason": "danger"}).status_code == 204
    assert [(x["id"], x["reasons"], x["notes"]) for x in c.get("/api/admin/reports", headers=B).json()] == [(first, {"danger": 1}, [])]
    assert c.post(f"/api/admin/reports/comment/{first}", headers=B, json={"remove": False}).status_code == 204
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=B).status_code == 404               # nothing to undo
    assert c.post(f"/api/admin/taken-down/user/{first}/restore", headers=B).status_code == 404   # nothing of theirs kept

    assert c.delete(f"/api/comments/{first}", headers=P).status_code == 204                                    # gone again (the club)
    assert c.post(f"/api/admin/taken-down/comment/{first}/restore", headers=B).status_code == 404               # the club's call, not the admin's
    assert c.patch("/api/events/1/comments", headers=A, json={"on": False}).status_code == 403
    assert c.patch("/api/events/1/comments", headers=P, json={"on": False}).json()["on"] is False
    assert c.post("/api/events/1/comments", headers=A, json={"body": "hello?"}).status_code == 409         # turned off
    con.execute("INSERT INTO posts (id, org_id, author_id, audience, title, body, created_at) VALUES (1, 1, ?, 'public', 'News', 'Text', 0)", (pres["id"],))
    pid = c.post("/api/posts/1/comments", headers=A, json={"body": "Nice"}).json()["items"][0]["id"]
    assert c.delete(f"/api/comments/{pid}", headers=P).status_code == 204                               # the club's Head+
    assert c.get("/api/posts", headers=A, params={"scope": "all"}).json()[0]["comments"] == 0


def test_question_badges(env):
    """Studio's "questions waiting" (they stayed after he read and answered): a Head+'s answer as themselves
    counts like the club's, their own words are never questions, and reading the thread clears it for the reader only."""
    c, cfg = env
    pres, vice, ali = login(c, 90, "pres"), login(c, 91, "vice"), login(c, 92, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (vice["id"], "vice")])
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    P, V, A = tma(90, "Pres"), tma(91, "Vice"), tma(92, "Ali")
    waiting = lambda h: c.get("/api/orgs/1/events", headers=h).json()[0]["questions"]
    say = lambda h, body: c.post("/api/events/1/comments", headers=h, json={"body": body}).json()
    say(A, "Where is it?"); say(A, "And when?")
    assert waiting(P) == 2 and waiting(V) == 2
    say(P, "Room 305, at six")                                     # as himself: an answer, not a question
    assert waiting(P) == 0 and waiting(V) == 0
    assert [r["user_id"] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'comment_question'")] == [pres["id"], vice["id"]]  # not for his
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_answer'").fetchall()
    assert [r["user_id"] for r in told] == [ali["id"]] and "answered your question" in bot._render(con, told[0])[0]
    say(A, "Can I bring a friend?")
    assert waiting(P) == 1 and waiting(V) == 1
    c.get("/api/events/1/comments", headers=V)                     # the Vice has read it: gone for her, not for the President
    assert waiting(V) == 0 and waiting(P) == 1
    asks = {r["user_id"]: r for r in con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'comment_question'")}
    assert bot._render(con, asks[vice["id"]]) is None and bot._render(con, asks[pres["id"]])[2] == "cm_1"
    c.get("/api/events/1/comments", headers=A)                     # a student reading changes nothing
    assert waiting(P) == 1


def test_calendar_feed(env):
    """My calendar feed: one secret address per student, kept; everything I go to (a cancelled event struck
    through); the page hands webcal:// to an Apple calendar, leads Android to Google, fetches nothing; gone with my data."""
    import base64
    import hashlib
    import urllib.parse
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    for eid, status, title in ((1, "published", "Hack\rDTSTART:19700101T000000Z"), (2, "cancelled", "Talk"), (3, "published", "Not mine")):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
            VALUES (?, 1, ?, ?, '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (eid, status, title, start, pres["id"]))
    # a team-only event of a club Ali isn't (or no longer is) in: the app hides it from him, so does the feed
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at, visibility)
        VALUES (4, 1, 'published', 'Team only', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0, 'members')""", (start, pres["id"]))
    for eid in (1, 2, 4):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, 0, 0)", (eid, ali["id"], f"T{eid}ABCD"))
    A = tma(91, "Ali")
    links = c.post("/api/me/calendar", headers=A).json()
    assert links == c.post("/api/me/calendar", headers=A).json()                                 # the same address, kept
    token = links["page"].rsplit("/", 1)[1]
    assert links["feed"] == f"webcal://{cfg.domain}/cal/{token}.ics"
    feed = c.get(f"/cal/{token}.ics")                                                            # no Telegram headers
    assert feed.headers["content-type"].startswith("text/calendar") and "X-WR-CALNAME:KBTU App" in feed.text
    assert "\r" not in feed.text.replace("\r\n", "") and "HackDTSTART" in feed.text.replace("\r\n ", "")  # a bare CR can't start a property
    assert "Team only" not in feed.text                                                         # what the app hides from him
    assert "SUMMARY:Hack" in feed.text and "SUMMARY:Talk\r\nLOCATION" in feed.text and "STATUS:CANCELLED" in feed.text and "Not mine" not in feed.text
    webcal, https = f"webcal://{cfg.domain}/cal/{token}.ics", f"https://{cfg.domain}/cal/{token}.ics"
    google = "https://calendar.google.com/calendar/render?cid=" + urllib.parse.quote(webcal, safe="")
    iphone = c.get(f"/cal/{token}", headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"})
    android = c.get(f"/cal/{token}", headers={"user-agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8)", "accept-language": "kk-KZ,kk;q=0.9"})
    assert iphone.status_code == android.status_code == 200
    assert f'data-auto href="{webcal}"' in iphone.text and f'href="{google}"' in iphone.text   # subscribes at once; Google too
    assert "data-auto href" not in android.text and webcal not in android.text              # webcal:// does nothing there
    assert f'href="{google}"' in android.text and f'data-url="{https}"' in android.text and texts.CAL_PAGE["kk"][3] in android.text
    for page in (iphone, android):
        # the token is in the address: no Referer, nothing fetched from anywhere, only the page's own style and script run
        assert page.headers["referrer-policy"] == "no-referrer" and page.headers["cache-control"] == "no-store"
        assert set(re.findall(r"https?://[^\s\"'<>]+", page.text)) <= {google, https} and not re.search(r"\bsrc=|<link|@import|url\(", page.text)
        csp = page.headers["content-security-policy"]
        assert csp.startswith("default-src 'none';")
        for tag in ("style", "script"):
            body = re.search(f"<{tag}>(.*?)</{tag}>", page.text, re.S).group(1)
            assert f"'sha256-{base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()}'" in csp, tag
    assert "<x-y>" not in calpage.render("d", '"><x-y>', "en", "") and {len(x) for x in texts.CAL_PAGE.values()} == {6}  # all escaped
    assert "@media (prefers-reduced-motion:reduce){*,::after{animation:none!important;transition:none!important}" in calpage.CSS  # no motion asked: none
    assert c.get("/cal/nobody.ics").status_code == 404 and c.get("/cal/nobody").status_code == 404
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ali["id"],))
    assert c.get(f"/cal/{token}.ics").status_code == c.get(f"/cal/{token}").status_code == 404
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ali["id"],))
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (ali["id"],))
    assert c.get(f"/cal/{token}.ics").status_code == 404
    con.execute("UPDATE students SET manual = 0 WHERE user_id = ?", (ali["id"],))
    # a leaked address can be reset: the old one is dead at once, the next tap makes another
    old = c.post("/api/me/calendar", headers=A).json()["page"].rsplit("/", 1)[1]
    assert c.delete("/api/me/calendar", headers=A).status_code == 204
    assert c.get(f"/cal/{old}.ics").status_code == 404 and c.get(f"/cal/{old}").status_code == 404
    token = c.post("/api/me/calendar", headers=A).json()["page"].rsplit("/", 1)[1]
    assert token not in ("", old)
    assert delete_now(c, cfg, A) is None
    assert c.get(f"/cal/{token}.ics").status_code == 404                                        # gone with my data


def test_team_only_event(env):
    """A team-only event (§4.10): the club's members see it and sign up; nobody else finds it; subscribers aren't told."""
    c, cfg = env
    pres, mem, ali = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (ali["id"],))
    P, M, A = tma(70, "Pres"), tma(71, "Mem"), tma(72, "Ali")
    body = {"title": "Team sync", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "visibility": "members"}
    assert c.post("/api/orgs/1/events", headers=P, json={**body, "visibility": "leaders"}).status_code == 400
    e = c.post("/api/orgs/1/events", headers=P, json=body).json()
    assert e["visibility"] == "members"
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert [x["id"] for x in c.get("/api/events", headers=M).json()] == [e["id"]]
    assert c.get("/api/events", headers=A).json() == [] and c.get(f"/api/events/{e['id']}", headers=A).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event'").fetchone()[0] == 0     # subscribers aren't told


def test_shared_cards_never_leak(env):
    """The Afisha's and Clubs' shared part is kept per worker (core.shared): warm from a member's request, a team-only
    event still never reaches a non-member, and nobody's own marks (ticket, saved, role) reach anyone else."""
    c, cfg = env
    pres, mem, ali, bob = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali"), login(c, 73, "bob")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (bob["id"], "member")])
    P, M, A = tma(70, "Pres"), tma(71, "Mem"), tma(72, "Ali")
    body = {"title": "Sync", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF"}
    team = c.post("/api/orgs/1/events", headers=P, json={**body, "visibility": "members"}).json()
    pub = c.post("/api/orgs/1/events", headers=P, json={**body, "title": "Open day"}).json()
    for e in (team, pub):
        c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert c.post(f"/api/events/{pub['id']}/registration", headers=M, json={}).json()["my"]["status"] == "going"
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (mem["id"],))  # joined after (directly: keeps it)
    assert c.put(f"/api/events/{pub['id']}/saved", headers=M).status_code == 204
    warm = {x["id"]: x for x in c.get("/api/events", headers=M).json()}
    assert warm.keys() == {team["id"], pub["id"]} and warm[pub["id"]]["saved"] and warm[pub["id"]]["my"]["ticketCode"]
    assert c.get("/api/orgs", headers=M).json()[0]["myRole"] == "member"
    seen = c.get("/api/events", headers=A).json()
    assert [x["id"] for x in seen] == [pub["id"]] and seen[0]["my"] is None and seen[0]["saved"] is False
    assert c.get("/api/orgs", headers=A).json()[0]["myRole"] is None
    con.execute("DELETE FROM org_members WHERE user_id = ?", (mem["id"],))                         # left the club: gone at once
    assert [x["id"] for x in c.get("/api/events", headers=M).json()] == [pub["id"]]
    assert c.get("/api/orgs", headers=M).json()[0]["myRole"] is None


def test_teambuilding_thunder(env):
    """"Teambuilding thunder" (§4.11): a club's own events count (a public one doesn't), with no top: the count goes on.
    A new achievement or level is recorded at start for whoever already reached it, without a bot message; the app's
    unlock moment shows it. The reminder before a club's own event has no ticket in it."""
    c, cfg = env
    pres, mem = login(c, 90, "pres"), login(c, 91, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    P, M = tma(90, "Pres"), tma(91, "Mem")
    start = int(time.time()) + 86400

    def came(visibility: str) -> None:
        e = c.post("/api/orgs/1/events", headers=P, json={"title": "Sync", "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                            "color": "#3B6BFF", "visibility": visibility}).json()
        c.post(f"/api/events/{e['id']}/publish", headers=P)
        if visibility == "public":  # a seat from before he joined (the club's own can't sign up to its public events)
            con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (?, ?, 'going', ?, 0, 0)",
                        (e["id"], mem["id"], f"T{e['id']}"))
        else:
            assert c.post(f"/api/events/{e['id']}/registration", headers=M, json={}).json()["my"]["status"] == "going"
        if visibility == "members":
            ref = con.execute("SELECT kind, ref FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h' ORDER BY id DESC", (mem["id"],)).fetchone()
            text, button, link = bot._render(con, {"user_id": mem["id"], "kind": ref[0], "ref": ref[1], "lang": "ru"})
            assert "\u0411\u0438\u043b\u0435\u0442" not in text and link == f"ev_{e['id']}"   # no "Ticket": it opens the event
        con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, e["id"]))
        assert c.post(f"/api/events/{e['id']}/checkin", headers=P, json={"userId": mem["id"]}).json()["result"] == "ok"

    team = lambda: next(a for a in logic.achievements(con, mem["id"]) if a["code"] == "team")
    came("public")
    assert team()["count"] == 0
    for _ in range(3):
        came("members")
    assert (team()["count"], team()["level"]) == (3, 1)
    # no tickets: the door has the whole team, and someone who didn't sign up is let in by name
    e = c.post("/api/orgs/1/events", headers=P, json={"title": "Pizza", "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                        "color": "#3B6BFF", "visibility": "members"}).json()
    c.post(f"/api/events/{e['id']}/publish", headers=P)
    assert {d["person"]["id"] for d in c.get(f"/api/events/{e['id']}/door", headers=P).json()} == {pres["id"], mem["id"]}
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, e["id"]))
    assert c.post(f"/api/events/{e['id']}/checkin", headers=P, json={"userId": mem["id"]}).json()["result"] == "ok"
    assert team()["count"] == 4
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'achievement' AND ref = 'ach:team:1'").fetchone()[0] == 1
    # as if "team" were new today: the start records what was already reached, quietly, once
    con.execute("DELETE FROM achievement_levels WHERE code = 'team'")
    con.execute("DELETE FROM meta")
    sent = con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0]
    logic.sync_levels(con)
    assert con.execute("SELECT level, seen FROM achievement_levels WHERE user_id = ? AND code = 'team'", (mem["id"],)).fetchone()[:] == (1, 0)
    assert con.execute("SELECT COUNT(*) FROM bot_outbox").fetchone()[0] == sent
    con.execute("DELETE FROM achievement_levels WHERE code = 'team'")
    logic.sync_levels(con)                                                               # the list hasn't changed since
    assert con.execute("SELECT COUNT(*) FROM achievement_levels WHERE code = 'team'").fetchone()[0] == 0


def test_message_teammate(env):
    """"Message on Telegram": a profile carries the @username to the same club's team only."""
    c, cfg = env
    pres, mem, out = login(c, 95, "pres"), login(c, 96, "mem"), login(c, 97, "out")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (mem["id"], "member")])
    con.execute("UPDATE users SET tg_username = 'mem_handle' WHERE id = ?", (mem["id"],))
    assert c.get(f"/api/users/{mem['id']}", headers=tma(95)).json()["username"] == "mem_handle"
    assert c.get(f"/api/users/{mem['id']}", headers=tma(97)).json()["username"] is None      # not their club
    assert c.get(f"/api/users/{mem['id']}", headers=tma(96)).json()["username"] is None      # nor their own card


def test_add_seats(env):
    """"+N seats" (§4.2): the club's Head+ only; the waitlist moves in at once, in order."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 70, "pres"), login(c, 71, "ali"), login(c, 72, "zhan"), login(c, 73, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, seats, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', 1, ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    for uid in (71, 72, 73):
        c.post("/api/events/1/registration", headers=tma(uid, "X"))
    st = lambda uid: con.execute("SELECT status FROM registrations WHERE user_id = ?", (uid,)).fetchone()[0]
    assert [st(ali["id"]), st(zhan["id"]), st(dana["id"])] == ["going", "waitlist", "waitlist"]
    assert c.post("/api/events/1/seats", headers=tma(71, "Ali"), json={"add": 1}).status_code == 403
    assert c.post("/api/events/1/seats", headers=tma(70, "Pres"), json={"add": 0}).status_code == 400
    e = c.post("/api/events/1/seats", headers=tma(70, "Pres"), json={"add": 1}).json()
    assert e["seats"] == 2 and [st(zhan["id"]), st(dana["id"])] == ["going", "waitlist"]          # in order


def test_place_changes(env, monkeypatch):
    """PLAN "Place and time": one KBTU room for another tells only those with reminders off (the 2-hour reminder
    shows it); another venue tells everyone, edits within 10 minutes in one message; within 2 hours of the start, at
    once and only to who isn't checked in; Studio's "Change room" during the event; each new place a line in Updates."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ali"), (11, "zhan"), (12, "bota")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 10, 11, 12)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (uid[20],))
    con.execute("UPDATE users SET n_remind = 0 WHERE id = ?", (uid[11],))                     # Zhan turned reminders off
    start = int(time.time()) + 2 * 86400
    body = {"title": "Hack", "place": "Aud. 305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    e = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    for tg in (10, 11, 12):
        c.post(f"/api/events/{e['id']}/registration", headers=tma(tg), json={})
    told = lambda: {r[0]: r[1] for r in con.execute("SELECT user_id, send_after FROM bot_outbox WHERE kind = 'event_changed' AND sent_at IS NULL")}  # noqa: E731

    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 412"}).status_code == 200  # room -> room
    assert set(told()) == {uid[11]}                                                         # only reminders-off hears it now
    assert c.get(f"/api/events/{e['id']}", headers=tma(10)).json()["updates"][0]["body"] == "📍 → Aud. 412"
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(10), json={"place": "Aud. 1"}).status_code == 403   # not the team
    con.execute("DELETE FROM bot_outbox")
    venue = {**body, "place": "Abu Dhabi Plaza", "placeUrl": "https://2gis.kz/almaty/firm/1"}
    assert c.patch(f"/api/events/{e['id']}", headers=tma(20), json=venue).status_code == 200  # another venue: everyone
    first = told()
    assert set(first) == {uid[10], uid[11], uid[12]} and all(t >= int(time.time()) + 500 for t in first.values())  # in 10 minutes
    c.patch(f"/api/events/{e['id']}", headers=tma(20), json={**venue, "place": "Abu Dhabi Plaza, floor 2"})
    assert told() == first                                                                  # merged: the bot reads the event when it sends

    # within 2 hours of the start: at once, only to who isn't in yet
    con.execute("DELETE FROM bot_outbox")
    con.execute("UPDATE events SET starts_at = ?, place = 'Aud. 305', place_url = NULL WHERE id = ?", (int(time.time()) - 600, e["id"]))
    con.execute("UPDATE registrations SET checked_in_at = ? WHERE event_id = ? AND user_id = ?", (int(time.time()), e["id"], uid[10]))
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 202"}).status_code == 200
    soon = told()
    assert set(soon) == {uid[11], uid[12]} and all(t <= int(time.time()) for t in soon.values())
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, e["id"]))
    assert c.post(f"/api/events/{e['id']}/place", headers=tma(20), json={"place": "Aud. 1"}).status_code == 409   # over


def test_comment_replies(env):
    """Comment replies (PLAN): a reply quotes the comment it answers (only one still up in the same thread), and
    its author hears it once an hour per thread; not for answering oneself, not twice for an asker the club answers."""
    c, cfg = env
    for tg, name in ((20, "pres"), (10, "ali"), (11, "zhan")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 10, 11)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (uid[20],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, uid[20]))
    first = c.post("/api/events/1/comments", headers=tma(10), json={"body": "Is there pizza?"}).json()["items"][0]
    t = c.post("/api/events/1/comments", headers=tma(11), json={"body": "I hope so", "replyTo": first["id"]}).json()
    assert t["items"][1]["replyTo"] == {"id": first["id"], "name": first["person"]["name"], "body": "Is there pizza?"} and t["items"][0]["replyTo"] is None
    c.post("/api/events/1/comments", headers=tma(11), json={"body": "Me too", "replyTo": first["id"]})
    told = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'comment_reply'").fetchall()
    assert [r["user_id"] for r in told] == [uid[10]]                                         # two replies, one message this hour
    text, _, start = bot._render(con, told[0])
    assert "Hack" in text and start == "cm_1"
    assert c.post("/api/events/1/comments", headers=tma(11), json={"body": "x", "replyTo": 999}).status_code == 400
    c.post("/api/events/1/comments", headers=tma(10), json={"body": "Self", "replyTo": first["id"]})
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_reply'").fetchone()[0] == 1   # not to myself
    c.post("/api/events/1/comments", headers=tma(20), json={"body": "Yes, pizza", "asOrg": True, "replyTo": first["id"]})
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_answer' AND user_id = ?", (uid[10],)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'comment_reply'").fetchone()[0] == 1   # the answer's card covers it
    c.delete(f"/api/comments/{first['id']}", headers=tma(10))
    assert all(x["replyTo"] is None for x in c.get("/api/events/1/comments", headers=tma(11)).json()["items"])  # gone: no quote


def test_saved_tomorrow(env, monkeypatch):
    """"Save" with a purpose (instead of a like): the day before, at noon, whoever saved an event and isn't going
    hears it once (with the reminders' switch); signing up meanwhile quiets it; the organizer sees how many saved it."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ann"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    day = (int(time.time()) + 5 * 3600) // 86400
    start = (day + 1) * 86400 - 5 * 3600 + 18 * 3600                       # tomorrow 18:00 in Almaty
    e = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Quiz", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    for tg in (10, 11):
        c.put(f"/api/events/{e['id']}/saved", headers=tma(tg))
    con.execute("UPDATE users SET n_remind = 0 WHERE tg_id = 11")                # Bob turned reminders off
    assert {x["id"]: x["savedBy"] for x in c.get("/api/orgs/1/events", headers=tma(20)).json()}[e["id"]] == 2
    set_clock(monkeypatch, lambda: day * 86400 - 5 * 3600 + 12 * 3600 + 60)  # today 12:01
    logic.saved_day(con)
    logic.saved_day(con)
    rows_ = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'saved_tomorrow'").fetchall()
    assert len(rows_) == 1 and "Quiz" in bot._render(con, rows_[0])[0]           # Ann only, once
    monkeypatch.undo()
    c.post(f"/api/events/{e['id']}/registration", headers=tma(10), json={})
    assert bot._render(con, rows_[0]) is None                                     # she signed up meanwhile


def test_delete_cancelled_event(env):
    """A cancelled event can be deleted unless it has payments; a live one can't."""
    c, cfg = env
    pres = login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    body = {"title": "Oops", "place": "", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 5}
    eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    assert c.delete(f"/api/events/{eid}", headers=tma(20)).status_code == 409         # live: cancel first
    assert c.post(f"/api/events/{eid}/cancel", headers=tma(20)).json()["status"] == "cancelled"
    assert c.delete(f"/api/events/{eid}", headers=tma(20)).status_code == 204
    assert not con.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone()
    # the admin deletes a live one too, from Admin's list of the club's events; nobody else sees that list
    eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    admin = logic.Viewer(pres["id"], "admin", True)
    with pytest.raises(logic.ApiError):
        logic.admin_org_events(con, logic.Viewer(pres["id"], "user", True), 1)
    assert [x["id"] for x in logic.admin_org_events(con, admin, 1)] == [eid]
    # a paid one: the receipt (personal) leaves the disk with it
    con.execute("INSERT INTO files (id, sha256, kind, mime, bytes, path, owner_id, created_at) VALUES (90, 'h', 'receipt', 'image/webp', 1, 'r/x', ?, 0)", (pres["id"],))
    con.execute("INSERT INTO registrations (id, event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (90, ?, ?, 'going', 'tk90', 0, 0)", (eid, pres["id"]))
    con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) VALUES (90, 90, 'app', 0)")
    assert logic.delete_event(con, admin, eid) == (["r/x"], [])
    assert not con.execute("SELECT 1 FROM events WHERE id = ?", (eid,)).fetchone()
    assert not con.execute("SELECT 1 FROM files WHERE id = 90").fetchone()


def test_door_guests(env):
    """A19: the walk-ins typed by name before the routes went (Nov 14): a student confirmed by Microsoft with that name
    counts as came, only when exactly one unlinked entry at that event has it."""
    c, cfg = env
    pres, mem, ali, bota = login(c, 70, "pres"), login(c, 71, "mem"), login(c, 72, "ali"), login(c, 74, "bota")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    for eid, price in ((1, None), (2, None), (3, 1000)):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at, price,
            pay_to_name, pay_phone) VALUES (?, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0, ?, 'Pres', '+70000000000')""",
            (eid, start, start + 7200, pres["id"], price))
    M = tma(71, "Mem")
    for eid, name in ((1, "Ali Testov"), (1, "Bota Testova"), (2, "Ali Testov"), (1, "Mem Testov")):
        con.execute("INSERT INTO door_guests (event_id, full_name, norm, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
                    (eid, name, logic._norm_name(name), mem["id"], start + 60))
    linked = lambda name: con.execute("SELECT user_id IS NOT NULL FROM door_guests WHERE event_id = 1 AND full_name = ?", (name,)).fetchone()  # noqa: E731
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = 2")                # the door's rules still hold
    ms = lambda uid: logic.ms_link(con, uid, {"oid": f"o{uid}", "email": "a@kbtu.kz", "first": "", "last": "", "profile": {}})  # noqa: E731
    ms(ali["id"])
    came = lambda uid: con.execute("SELECT event_id, checked_in_at IS NOT NULL, walk_in FROM registrations WHERE user_id = ?", (uid,)).fetchall()  # noqa: E731
    assert [tuple(r) for r in came(ali["id"])] == [(1, 1, 1)]
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'rate'", (ali["id"],)).fetchone()  # as a real check-in
    assert tuple(linked("Ali Testov")) == (1,)
    assert came(bota["id"]) == []                                                      # "Bota Testova" is not "Bota Testov"
    other = login(c, 75, "other")
    con.execute("UPDATE students SET first_name = 'Mem' WHERE user_id = ?", (other["id"],))  # two students named Mem Testov
    ms(mem["id"])
    assert came(mem["id"]) == []                                                       # nobody can tell which one came
    # the check-in a typed name made is taken back within 10 minutes: the name goes with it, and nothing links again
    assert c.delete(f"/api/events/1/checkin/{ali['id']}", headers=M).status_code == 204
    assert [tuple(r) for r in came(ali["id"])] == [(1, 0, 1)]
    assert linked("Ali Testov") is None
    logic.link_door_guests(con, ali["id"])
    assert [tuple(r) for r in came(ali["id"])] == [(1, 0, 1)]
    logic.delete_me(con, logic.Viewer(ali["id"], "user", True))
    assert not con.execute("SELECT 1 FROM door_guests WHERE event_id = 1 AND norm = 'ali testov'").fetchone()


def test_event_questions(env, monkeypatch):
    """Oct 30: an event's own questions at sign-up. The editor sets up to five (text or a choice); signing up answers
    them (a required one, a choice from its options); the organizers see the answers in Attendees and the CSV; they
    go 30 days after the event."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    off = {"title": "Quiz", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF",
           "form": [{"label": "Team?", "kind": "text", "required": True}]}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=off).json()["form"] is None   # BOARD off: questions not taken
    _board_on(c, cfg)
    base = {"title": "Hackathon", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF"}
    qs = [{"label": "Your team?", "kind": "text", "required": True}, {"label": "T-shirt", "kind": "choice", "options": ["S", "M", "L"], "required": False}]
    for bad in ([{"label": "x", "kind": "text"}], [{"label": "Size", "kind": "choice", "options": ["S"]}], [qs[0]] * 6,
                [{"label": "Size", "kind": "choice", "options": ["S", "S"]}], [{"label": "Size", "kind": "file"}],
                [{"label": "Name", "kind": "text"}, {"label": "name", "kind": "text"}]):
        assert c.post("/api/orgs/1/events", headers=tma(20), json={**base, "form": bad}).status_code == 400
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={**base, "form": qs}).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    assert [q["label"] for q in c.get(f"/api/events/{eid}", headers=tma(10)).json()["form"]] == ["Your team?", "T-shirt"]
    A = lambda a, b: [{"q": "Your team?", "a": a}, {"q": "T-shirt", "a": b}]  # noqa: E731
    for bad in (None, A("Bugs", "XL")[:1], A("", "M"), A("Bugs", "XL"), A("x" * 201, ""), A({"x": [1]}, ""),
                [{"q": "Phone", "a": "Bugs"}, {"q": "T-shirt", "a": "M"}]):                    # a question that changed: refused
        assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={"answers": bad}).status_code in (400, 409)
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={"answers": A("  Bugs  Bunny ", "M")}).json()["my"]["status"] == "going"
    seen = c.get(f"/api/events/{eid}/attendees", headers=tma(20)).json()
    assert seen[0]["answers"] == [{"q": "Your team?", "a": "Bugs Bunny"}, {"q": "T-shirt", "a": "M"}]
    assert "answers" not in c.get(f"/api/events/{eid}", headers=tma(10)).json().get("my", {})       # nobody else's view
    # an edit later leaves what was answered as it was asked
    c.patch(f"/api/events/{eid}", headers=tma(20), json={**base, "form": [{"label": "Team name", "kind": "text", "required": True}]})
    rows_ = texts.attendees_csv("en", "Hackathon", logic.attendees_export(con, logic.Viewer(pres["id"], "user", True), eid)[1])[1].decode()
    assert "Your team?" in rows_.splitlines()[0] and "Bugs Bunny" in rows_
    con.execute("UPDATE events SET starts_at = ? WHERE id = ?", (int(time.time()) - 31 * 86400, eid))
    t = int(time.time())
    set_clock(monkeypatch, lambda: (t + 5 * 3600) // 86400 * 86400 - 5 * 3600 + 600)          # 00:10, when it runs
    logic.stats_day(con)                                                                    # the nightly round
    assert con.execute("SELECT answers FROM registrations WHERE event_id = ?", (eid,)).fetchone()[0] is None
    con.close()


def test_event_fill(env, monkeypatch):
    """Oct 30: a club's organizer pastes an announcement and the new event's form fills itself: the club's own only,
    behind the forum's switch, the EU host, the assistant's day; only well-shaped fields come back."""
    from kbtu import llm
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    login(c, 1, "ann")
    text = "Open mic on November 10 at 18:00 in room 256, entry 1000 tenge. Bring friends!"
    assert c.post(f"/api/orgs/{org}/events/fill", headers=tma(9), json={"text": text}).status_code == 404   # BOARD off
    _board_on(c, cfg)

    async def fake(cfg_, http, msgs, **kw):
        assert kw["only"] == ai.EU_ONLY and msgs[1]["content"] == text and kw["race"]
        return json.dumps({"title": "Open mic", "date": "2026-11-10", "start": "18:00", "end": "25:00", "place": "256",
                           "description": "Bring friends!", "price": 1000, "seats": 5, "emoji": "microphone_3d", "color": "violet"}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    assert c.post(f"/api/orgs/{org}/events/fill", headers=tma(1), json={"text": text}).status_code == 403    # not their club
    r = c.post(f"/api/orgs/{org}/events/fill", headers=tma(9), json={"text": text}).json()
    assert r == {"title": "Open mic", "date": "2026-11-10", "start": "18:00", "place": "256", "description": "Bring friends!", "price": 1000,
                 "emoji": "microphone_3d", "color": "#7C4DFF"}
    assert c.post(f"/api/orgs/{org}/events/fill", headers=tma(9), json={"text": "short"}).status_code == 400
    from kbtu.logic import assistant
    assert assistant.filled('{"date": "2026-11-21", "end_date": "2026-11-22"}') == {"date": "2026-11-21", "endDate": "2026-11-22"}
    assert assistant.filled('{"date": "2026-11-21", "end_date": "2026-11-21"}') == {"date": "2026-11-21"}
    assert assistant.filled('{"date": "2026-02-31", "price": true, "title": 5, "emoji": "bomb", "color": "#000000"}') == {} and assistant.filled("nope") == {}
    # what counts as the model's answer (else the next model is asked): its form, even all empty; not junk
    assert [assistant.fill_answered(x) for x in ('{"title": null, "date": null}', "{}", "```json\n{\"place\": \"256\"}\n```",
                                                 '{"error": "busy"}', "[]", "sorry", '{"title": ')] == [True, True, True, False, False, False, False]
    con.close()


def test_partner_events(env):
    """Oct 29: a partner's event a club posts. An official club's organizers or DMP name the outside host (no KBTU, DMP,
    council or school in it) with an https link; no price, no sign-up here, no door; followers aren't pinged; it stays
    out of DMP's registry numbers."""
    c, cfg = env
    pres, head, dmp, ali = login(c, 20, "pres"), login(c, 21, "head"), login(c, 80, "dmp"), login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'inc', 'club', 'Incubator', 'IN', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, pres["id"], "president"), (1, head["id"], "head"), (9, dmp["id"], "head"), (1, dmp["id"], "head")])
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (?, 1, 0)", (ali["id"],))
    start = int(time.time()) + 86400
    body = {"title": "Halloween", "place": "Bar", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}
    party = {**body, "guestHost": "  Night  Owls ", "externalUrl": "https://owls.kz/halloween"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=party).json()["message"] == "partner"   # a student initiative
    ev = c.post("/api/orgs/1/events", headers=tma(80), json=party).json()                              # DMP may
    assert (ev["guestHost"], ev["externalUrl"]) == ("Night Owls", "https://owls.kz/halloween")
    con.execute("UPDATE orgs SET official = 1 WHERE id = 1")
    for bad in ("KBTU Night", "\u041a\u0411\u0422\u0423 party", "dmp crew", "\u0414\u041c\u041f", "Student Council", "\u0421\u043e\u0432\u0435\u0442",
                "Business School", "x" * 61):
        assert c.post("/api/orgs/1/events", headers=tma(21), json={**party, "guestHost": bad}).json()["message"] == "partner"
    for url in (None, "http://owls.kz", "https://owls", "javascript:alert(1)"):
        assert c.post("/api/orgs/1/events", headers=tma(21), json={**party, "externalUrl": url}).status_code == 400
    priced = {**party, "price": 2000, "payToName": "Alikhan S.", "payPhone": "87071234567"}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=priced).json()["message"] == "partner"   # no tickets, no money
    eid = c.post("/api/orgs/1/events", headers=tma(21), json=party).json()["id"]                        # a Head may
    assert c.patch(f"/api/events/{eid}", headers=tma(20), json={**priced, "guestHost": "Night Owls"}).json()["message"] == "partner"
    assert c.post(f"/api/events/{eid}/publish", headers=tma(21)).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'new_event'").fetchone()[0] == 0    # the feed only
    assert c.post(f"/api/events/{eid}/registration", headers=tma(10), json={}).status_code == 400         # signed up for on the host's site
    assert c.post(f"/api/events/{eid}/checkin", headers=tma(21), json={"code": "X"}).status_code == 409  # no door
    assert any(e["id"] == eid and e["guestHost"] == "Night Owls" for e in c.get("/api/events", headers=tma(10)).json())
    # a club's own event with people signed up can't turn into a partner's
    own = c.post("/api/orgs/1/events", headers=tma(21), json=body).json()["id"]
    c.post(f"/api/events/{own}/publish", headers=tma(21))
    c.post(f"/api/events/{own}/registration", headers=tma(10), json={})
    assert c.patch(f"/api/events/{own}", headers=tma(21), json=party).json()["message"] == "taken"
    con.execute("UPDATE events SET starts_at = ? WHERE id IN (?, ?)", (int(time.time()), eid, own))  # this month, for the registry
    month = next(x for x in c.get("/api/registry/orgs", headers=tma(80, "Dmp")).json() if x["org"]["id"] == 1)["month"]
    assert (month["events"], month["registrations"]) == (1, 1)                                         # the club's own only
    assert c.patch(f"/api/events/{eid}", headers=tma(21), json={**body, "guestHost": None}).json()["externalUrl"] is None  # off: the link goes too


def test_cancelled_event_leaves_the_afisha_after_a_day(env, monkeypatch):
    """A cancelled event shows on the Afisha, struck through, for a day; then it is gone."""
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, official) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0, 1)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, (SELECT id FROM users WHERE tg_id = 20), 'president', 0)")
    start = int(time.time()) + 5 * 86400
    body = {"title": "Movie night", "place": "", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": 5}
    eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    c.post(f"/api/events/{eid}/cancel", headers=tma(20))
    login(c, 21, "student")
    ids = lambda: [e["id"] for e in c.get("/api/events", headers=tma(21)).json()]
    assert eid in ids()
    con.execute("UPDATE events SET cancelled_at = cancelled_at - 86401 WHERE id = ?", (eid,))
    assert eid not in ids()
