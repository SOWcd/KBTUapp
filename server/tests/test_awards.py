"""Awards: achievements and their unlock moment, badges, grants, streaks, course days, premium emoji."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from kbtu import bot, db, logic, outbox, app as server, texts
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def test_unlock_moment(env):
    """A check-in that brings a new achievement level: the date it was reached, the bot's message once, and the
    app's unlock moment until it has been celebrated."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T91ABC', 0, 0)", (ali["id"],))
    P, A = tma(90, "Pres"), tma(91, "Ali")
    assert c.get("/api/me", headers=A).json()["unlocked"] == []
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "ok"
    assert c.get("/api/me", headers=A).json()["unlocked"] == [{"code": "first_in", "level": 1}]       # the first one in
    sent = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'achievement'").fetchall()
    assert [(r["user_id"], r["ref"]) for r in sent] == [(ali["id"], "ach:first_in:1")] and outbox._render(con, sent[0])[2] == "aw_first_in"
    first = next(a for a in c.get(f"/api/users/{ali['id']}", headers=A).json()["awards"]["achievements"] if a["code"] == "first_in")
    assert first["level"] == 1 and first["at"]                                                     # the earned date
    assert c.post("/api/me/unlocked", headers=A, json={"code": "first_in", "level": 1}).json()["unlocked"] == []
    assert c.post("/api/events/1/checkin", headers=P, json={"userId": ali["id"]}).json()["result"] == "already"
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'achievement'").fetchone()[0] == 1  # once


def test_first_fifty(env, monkeypatch):
    """Card numbers and "First 500": the number is the order of first KBTU sign-in and stays the person's;
    the Creator's card shows 0 and takes no place, so the grant goes to cards 1..FIRST_N; a deleted account's number
    stays empty, never given again: a return gets a new one."""
    c, cfg = env
    monkeypatch.setattr(logic.profiles, "FIRST_N", 2)
    con = db.connect(cfg.db_path)
    c.get("/api/me", headers=tma(69, "Boss"))
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 69")
    first = [{"code": "first50", "level": 1}]
    f = login(c, 69, "ff")
    assert f["no"] == 0 and f["unlocked"] == first
    a, b = login(c, 70, "aa"), login(c, 71, "bb")
    assert (a["no"], b["no"]) == (1, 2) and a["unlocked"] == b["unlocked"] == first
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE ref = 'ach:first50:1'").fetchone()  # no push: the app shows it
    delete_now(c, cfg, tma(70, "Aa"))
    cc = login(c, 72, "cc")
    assert cc["no"] == 3 and cc["unlocked"] == []                       # past the 2; number 1 stays empty
    again = login(c, 70, "aa")
    assert again["no"] == 4 and again["unlocked"] == []                 # back after deleting: a new card, the old one burnt
    assert c.get(f"/api/users/{b['id']}", headers=tma(72, "Cc")).json()["no"] == 2
    assert c.get("/api/me", headers=tma(73, "Guest")).json()["no"] is None
    # migration 36: a card within the 500 that missed the award gets it quietly; then everyone has it = 100%
    monkeypatch.setattr(logic.profiles, "FIRST_N", 500)
    con.execute("DELETE FROM achievement_grants WHERE user_id = ?", (cc["id"],))
    con.execute("DELETE FROM achievement_levels WHERE user_id = ?", (cc["id"],))
    con.executescript(dict(db.MIGRATIONS)[36])
    logic.profiles._RARITY[0] = 0                                       # rarity is kept a minute per worker
    ach = next(a for a in logic.achievements(con, cc["id"]) if a["code"] == "first50")
    assert ach["level"] == 1 and ach["rarity"] == 1
    # migration 59: a night sign-in left without a number gets the next one, and its "First 500" on the next open
    for k, x in enumerate((b["id"], cc["id"], again["id"])):                # signed in in this order
        con.execute("UPDATE students SET verified_at = ? WHERE user_id = ?", (1792600000 + k, x))
        con.execute("UPDATE users SET card_no = NULL WHERE id = ?", (x,))
        con.execute("DELETE FROM achievement_grants WHERE user_id = ?", (x,))
        con.execute("DELETE FROM achievement_levels WHERE user_id = ?", (x,))
    con.executescript(dict(db.MIGRATIONS)[59])
    late = c.get("/api/me", headers=tma(71, "Bb")).json()
    assert late["no"] == 5 and late["unlocked"] == first
    assert [c.get("/api/me", headers=tma(t)).json()["no"] for t in (72, 70)] == [6, 7]


def test_anthem_award(env):
    """The anthem heard start to finish (the sheet tracks skips): one grant per student, again a no-op; the app's unlock
    moment, no bot message; a guest can't have it."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    s = login(c, 80, "an")
    assert c.post("/api/me/anthem", headers=tma(80, "An")).json()["unlocked"] == [{"code": "anthem", "level": 1}]
    assert c.post("/api/me/anthem", headers=tma(80, "An")).json()["unlocked"] == [{"code": "anthem", "level": 1}]  # idempotent
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'anthem'", (s["id"],)).fetchone()[0] == 1
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE ref = 'ach:anthem:1'").fetchone()
    assert c.post("/api/me/unlocked", headers=tma(80, "An"), json={"code": "anthem", "level": 1}).json()["unlocked"] == []
    assert c.post("/api/me/anthem", headers=tma(80, "An")).json()["unlocked"] == []                   # seen stays seen
    ach = next(a for a in logic.achievements(con, s["id"]) if a["code"] == "anthem")
    assert ach["level"] == 1 and ach["emoji"] == "headphone_3d"
    assert c.post("/api/me/anthem", headers=tma(81, "Guest")).status_code == 401


def test_grants(env):
    """Manual achievements: the admin only; "Bug hunter" adds up, a secret one is given once; each new level is
    celebrated (the bot's card, the unlock moment) and audited."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    give = lambda code, h=B: c.post("/api/admin/grants", headers=h, json={"userId": ali["id"], "code": code})
    assert give("bugs", A).status_code == 403 and give("first50").status_code == 400
    prof = lambda: c.get(f"/api/users/{ali['id']}", headers=B).json()  # noqa: E731
    bugs = lambda p: next(a for a in p["awards"]["achievements"] if a["code"] == "bugs")
    g = give("bugs").json()
    assert g["code"] == "bugs" and g["person"]["id"] == ali["id"] and bugs(prof())["level"] == 1  # the item, undone by its id
    assert c.get("/api/me", headers=A).json()["unlocked"] == [{"code": "bugs", "level": 1}]
    give("bugs")
    twice = bugs(prof())
    assert twice["count"] == 2                                                                    # adds up
    assert twice["rarity"] == 0.5 and [x["rarity"] for x in twice["levels"]] == [0.5, 0, 0, 0]   # 1 of the 2 students has level 1
    assert give("creator_laugh").status_code == 403                                               # the creator's own: him alone
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    assert give("creator_laugh").status_code == 200 and give("creator_laugh").status_code == 409  # a secret one: once
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'grant'").fetchone()[0] == 3
    # one given by mistake comes back off the profile at any time, all of it at once; never "First 500"
    back = lambda code, h=B: c.post("/api/admin/grants/take-back", headers=h, json={"userId": ali["id"], "code": code})
    assert back("bugs", A).status_code == 403 and back("first50").status_code == 400
    assert back("bugs").json()["has"] == ["creator_laugh"]
    left = bugs(prof())
    assert left["count"] == 0 and left["level"] == 0
    assert back("bugs").status_code == 404
    assert give("creator_laugh").status_code == 409 and back("creator_laugh").status_code == 200 and give("creator_laugh").status_code == 200


def test_grant_scanner(env):
    """The owner's batch scanner: a badge QR is one grant, a wrong code finds nobody, a
    secret one only once; undo within a minute takes the level and its unsent card back; "You gave" lists them."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    qr = "https://t.me/kbtu_bot/app?startapp=u_" + c.get("/api/me", headers=A).json()["qr"]
    scan = lambda code, raw=qr, h=B, run="r1": c.post("/api/admin/grants/scan", headers=h, json={"qr": raw, "code": code, "run": run})  # noqa: E731
    assert scan("init26", h=A).status_code == 403 and scan("init26", raw=qr[:-1] + ("Q" if qr[-1] != "Q" else "R")).status_code == 404 and scan("first50").status_code == 400
    assert scan("bugs").status_code == 400                                                       # adds up: never by a scan
    assert scan("init26", run="no spaces").status_code == 400
    assert scan("creator_found").status_code == 403                                              # the creator's own
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    one_ = scan("init26").json()
    assert one_["person"]["id"] == ali["id"] and one_["person"]["name"] and scan("init26").status_code == 409
    gave = [scan("creator_found").json()]
    assert gave[0]["person"]["id"] == ali["id"] and scan("creator_found").status_code == 409
    assert c.delete(f"/api/admin/grants/{one_['id']}", headers=B).status_code == 204
    con.execute("UPDATE achievement_grants SET created_at = created_at - 3600")                  # undo has no clock: it's mine
    assert c.delete(f"/api/admin/grants/{gave[0]['id']}", headers=B).status_code == 204
    assert not con.execute("SELECT 1 FROM achievement_levels WHERE user_id = ? AND code = 'creator_found'", (ali["id"],)).fetchone()
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref LIKE 'ach:creator_found:%'", (ali["id"],)).fetchone()
    # "Undo all from this run": one call, mine only
    scan("init26p", run="r2"); scan("creator_laugh", run="r2"); scan("init26f", run="r3")
    undo = lambda b, h=B: c.post("/api/admin/grants/undo", headers=h, json={"batch": b})  # noqa: E731
    assert undo("s_r2", A).status_code == 403 and undo("s_r2").json() == {"undone": 2} and undo("s_r2").json() == {"undone": 0}
    assert c.get(f"/api/admin/grants/of/{ali['id']}", headers=B).json()["has"] == ["init26f"]


def test_badge_variants(env):
    """Admin → Badges (owner, Nov 2): the initiation badge is one award with three variants (guest, volunteer,
    performer); the admin finds a student and gives or takes a variant: admins only, giving twice is a no-op, each
    change audited; the profile shows one entry with my highest variant, counted once; its moment once for all."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali"); login(c, 62, "bea")
    B, A = tma(60, "Boss"), tma(61, "Ali")
    put = lambda code, h=B: c.post("/api/admin/grants", headers=h, json={"userId": ali["id"], "code": code})          # noqa: E731
    drop = lambda code, h=B: c.post("/api/admin/grants/take-back", headers=h, json={"userId": ali["id"], "code": code})  # noqa: E731
    has = lambda: c.get(f"/api/admin/grants/of/{ali['id']}", headers=B).json()["has"]  # noqa: E731
    # not staff: no grant, no take-back, no sessions
    assert put("init26p", A).status_code == 403 and drop("init26p", A).status_code == 403
    assert c.get("/api/admin/badges/sessions", headers=A).status_code == 403
    assert put("first50").status_code == 400 and c.get("/api/admin/grants/of/999999", headers=B).status_code == 404
    # give: once, audited once, celebrated once
    assert put("init26p").status_code == 200 and has() == ["init26p"]
    assert put("init26p").status_code == 409 and has() == ["init26p"]
    con = db.connect(cfg.db_path)
    log = lambda a: con.execute("SELECT COUNT(*) FROM audit_log WHERE action = ? AND target = ?", (a, f"user:{ali['id']}")).fetchone()[0]  # noqa: E731
    assert log("grant") == 1 and con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'init26p'", (ali["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:init26p:1'", (ali["id"],)).fetchone()
    # one entry, my highest variant's medal, counted once
    assert put("init26f").status_code == 200
    me = c.get(f"/api/users/{ali['id']}", headers=A).json()
    ini = [a for a in me["awards"]["achievements"] if a["code"].startswith("init26")]
    assert len(ini) == 1 and ini[0]["code"] == "init26" and ini[0]["variant"] == "init26p" and ini[0]["emoji"] == "medal_init26p_2"
    assert [(v["code"], v["have"]) for v in ini[0]["variants"]] == [("init26p", True), ("init26", False), ("init26f", True)]
    assert ini[0]["level"] == 1 and ini[0]["count"] == 2 and ini[0]["rarity"] == 1 / 3
    assert c.get("/api/me", headers=A).json()["unlocked"] == [{"code": "init26", "level": 1}] * 2
    assert c.post("/api/me/unlocked", headers=A, json={"code": "init26", "level": 1}).json()["unlocked"] == []
    # take back: audited, the medal falls to the next variant; again: nothing to take
    assert drop("init26p").json()["has"] == ["init26f"] and log("ungrant") == 1
    assert drop("init26p").status_code == 404 and log("ungrant") == 1
    ini = next(a for a in c.get(f"/api/users/{ali['id']}", headers=A).json()["awards"]["achievements"] if a["code"] == "init26")
    assert ini["variant"] == "init26f" and ini["emoji"] == "medal_init26f_2"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:init26p:1' AND sent_at IS NULL", (ali["id"],)).fetchone()
    # an old showcase pick of a variant is the badge
    con.execute("UPDATE users SET showcase = 'init26f' WHERE id = ?", (ali["id"],))
    assert c.get(f"/api/users/{ali['id']}", headers=A).json()["shelf"] == ["init26"]
    # the batch grant's sessions: the owner's alone, not any admin's
    assert c.get("/api/admin/badges/sessions", headers=B).status_code == 403
    con.execute("UPDATE users SET is_founder = 1 WHERE tg_id = 60")
    assert c.get("/api/admin/badges/sessions", headers=B).json() == []
    # a one-time link for a variant (Admin -> Badges' "Send a link"): staff make it, the first to open it gets the
    # badge, the link is spent; who made it and who used it are on record; its own bot card ("Get it")
    boss = c.get("/api/me", headers=B).json()
    with pytest.raises(logic.ApiError):
        logic.grant_link(con, logic.Viewer(ali["id"], "user", True), "init26p")
    token = logic.grant_link(con, logic.Viewer(boss["id"], "admin", True), "init26p")
    bea = tma(62, "Bea")
    assert c.post(f"/api/grant-links/{token}", headers=bea).json() == {"code": "init26p"}
    assert c.post(f"/api/grant-links/{token}", headers=bea).json() == {"code": "init26p"}         # again: fine, nothing more
    assert c.post(f"/api/grant-links/{token}", headers=A).json()["error"] == "closed"
    assert next(a for a in c.get("/api/me", headers=bea).json()["unlocked"] if a["code"] == "init26")
    acts = [r[0] for r in con.execute("SELECT action FROM audit_log WHERE target = ? ORDER BY id", (f"link:{token[:8]}",))]
    assert acts == ["grant_link", "grant_link_used"]
    stale = logic.grant_link(con, logic.Viewer(boss["id"], "admin", True), "init26")
    con.execute("UPDATE grant_links SET expires_at = ? WHERE token = ?", (int(time.time()) - 1, stale))
    assert c.post(f"/api/grant-links/{stale}", headers=bea).json()["error"] == "closed"            # 7 days, then closed
    title, text, button = texts.share_invite("gb", "en", award=texts.BADGE_TITLES["en"]["init26p"], until="Nov 10")
    assert "Initiation 2026 · Performer" in text and button.endswith("Get it")
    con.close()


def test_course_day(env, monkeypatch):
    """The year of study moves on every September 1 (Almaty), once, whatever year it was written in: the portal's lag
    (a repeater) stays, the degree's last year is the top (bachelor 4, master 2; a portal 6 is not lowered), an August
    ID of the coming intake starts at 1, a missed year is caught up."""
    import calendar
    c, cfg = env
    ids = [login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve"))]
    con = db.connect(cfg.db_path)
    sept = calendar.timegm((2027, 9, 1, 0, 0, 0)) - 5 * 3600                                # Sept 1, 2027, 00:00 Almaty
    for uid, sid, course, synced in zip(ids, ("26B000001", "24B000002", "21B000003", "27B000004", "26M000005"), (1, 2, 6, 1, 1),
                                        (sept - 300 * 86400,) * 3 + (sept - 10 * 86400, sept - 300 * 86400)):
        con.execute("UPDATE students SET student_id = ?, course = ?, synced_at = ? WHERE user_id = ?", (sid, course, synced, uid))
    courses = lambda: [con.execute("SELECT course FROM students WHERE user_id = ?", (u,)).fetchone()[0] for u in ids]  # noqa: E731
    set_clock(monkeypatch, lambda: sept - 60)                                    # Aug 31, 23:59: not yet
    logic.course_day(con)
    assert courses() == [1, 2, 6, 1, 1]
    set_clock(monkeypatch, lambda: sept + 60)
    logic.course_day(con)
    logic.course_day(con)
    assert courses() == [2, 3, 6, 1, 2]
    set_clock(monkeypatch, lambda: sept + 731 * 86400)                           # Sept 2029, 2028 missed
    logic.course_day(con)
    assert courses() == [4, 4, 6, 3, 2] and courses()[0] == logic.course_of("26B000001")
    assert logic.course_of("19B000006") == 4 and logic.course_of("20M000007") == 2 and logic.course_of("20X000008") == 6
    # migration 62 (its UPDATEs; the column exists already): course_year from synced_at (or an August ID's own year);
    # a typed-in year (written since the portal closed) past the degree's last is capped, the portal's and staff's never
    oct20, oct10, spring26 = (calendar.timegm(d) for d in ((2026, 10, 20, 0, 0, 0), (2026, 10, 10, 0, 0, 0), (2026, 4, 1, 0, 0, 0)))
    for uid, sid, course, synced, ver in zip(ids, ("21B000001", "20B000002", "20M000003", "27B000004", "24M000005"), (6, 5, 4, 1, 3),
                                             (oct20, spring26, oct20, oct10, oct20), ("v3", "v3", "v3", "v3", "staff")):
        con.execute("UPDATE students SET student_id = ?, course = ?, course_year = NULL, synced_at = ?, manual = 0, consent_version = ? WHERE user_id = ?",
                    (sid, course, synced, ver, uid))
    con.executescript(dict(db.MIGRATIONS)[62].split(";", 1)[1])
    got = [tuple(con.execute("SELECT course, course_year FROM students WHERE user_id = ?", (u,)).fetchone()) for u in ids]
    assert got == [(4, 2026), (5, 2025), (2, 2026), (1, 2027), (3, 2026)]


def test_course_raise(env, monkeypatch):
    """Settings -> My data: a transfer's new ID says year 1, they're in year 2: the course goes up from the ID's year,
    never below it (free 1st-year seats), to 6 at most; September moves the raised one on and never back down."""
    import calendar
    c, cfg = env
    ali, stf = login(c, 10, "ali"), login(c, 12, "stf")
    con = db.connect(cfg.db_path)
    oct26 = calendar.timegm((2026, 10, 1, 0, 0, 0))
    set_clock(monkeypatch, lambda: oct26)
    con.execute("UPDATE students SET student_id = '26B031234', course = 1, course_year = 2026 WHERE user_id = ?", (ali["id"],))
    con.execute("UPDATE students SET consent_version = 'staff' WHERE user_id = ?", (stf["id"],))
    up = lambda n, uid=10: c.patch("/api/me", headers=tma(uid), json={"course": n})  # noqa: E731
    assert c.get("/api/me", headers=tma(10)).json()["student"]["courseMin"] == 1
    assert all(up(n).status_code == 400 for n in (0, 7, "2", True, None))
    me = up(2).json()["student"]
    assert me["course"] == 2 and not me["freeFirst"] and "course" not in me["fixable"]
    assert up(1).json()["message"] == "fixed"                                   # once (review once-edit 3): 2, then 1 for a free seat
    assert up(2).status_code == 200                                             # the same year again: nothing to spend
    con.execute("UPDATE students SET student_id = '25B031234', course = 2, fixed = '' WHERE user_id = ?", (ali["id"],))
    assert up(1).status_code == 400                                             # below the ID's year: never
    assert up(1, 12).status_code == 403                                         # staff: the ID is a placeholder
    con.execute("UPDATE students SET student_id = '26B031234', course = 2, course_year = 2026 WHERE user_id = ?", (ali["id"],))
    set_clock(monkeypatch, lambda: calendar.timegm((2027, 9, 2, 0, 0, 0)))
    logic.course_day(con)
    assert con.execute("SELECT course FROM students WHERE user_id = ?", (ali["id"],)).fetchone()[0] == 3  # on, not back to the ID's 2


def test_streak_pauses():
    # weeks with a check-in, weeks that had public events, this week
    assert logic.profiles._streak({1, 2, 4}, {1, 2, 4}, 6) == (3, 3)     # 3 and 5 had no events: no break; 6 is still on
    assert logic.profiles._streak({1, 2, 4}, {1, 2, 3, 4}, 6) == (2, 1)  # 3 had events and I missed them
    assert logic.profiles._streak({1, 2}, {1, 2, 5}, 6) == (2, 0)        # 5 went by without me
    assert logic.profiles._streak(set(), {1}, 6) == (0, 0)


def test_streak_flame(env):
    """The weeks-in-a-row medal is on the list (in the app only, no bot card); its current run, the flame, goes to the
    person and their friends: on the Friends page (one read for the list) and on the page, never to a stranger."""
    c, cfg = env
    ali, bea, cat = login(c, 92, "ali"), login(c, 93, "bea"), login(c, 94, "cat")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ali["id"], bea["id"]), max(ali["id"], bea["id"])))
    now = int(time.time())
    for i, at in enumerate((now - 7 * 86400, now - 600)):  # last week and this week
        e = con.execute("""INSERT INTO events (org_id, status, title, starts_at, created_at, updated_at)
            VALUES (1, 'published', 't', ?, 0, 0)""", (at,)).lastrowid
        con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at)
            VALUES (?, ?, 'going', ?, ?, 0, 0)""", (e, bea["id"], f"TS{i}", at + 60))
    assert ("streak", "fire_3d", (2, 4, 8, 16), False) in logic.profiles.ACHIEVEMENTS and "streak" in logic.profiles.QUIET
    want = logic.profiles._streak({logic.profiles._week(t) for t in logic.profiles.attended(con, bea["id"])}, logic.profiles._busy(con, now - 7 * 86400), logic.profiles._week(now))[1]
    assert want >= 1 and logic.profiles.streaks_now(con, [ali["id"], bea["id"]]) == {bea["id"]: want}
    row = next(r for r in c.get("/api/friends", headers=tma(92, "Ali")).json()["friends"] if r["person"]["id"] == bea["id"])
    assert row["streak"] == want
    page = lambda who: next(a for a in c.get(f"/api/users/{bea['id']}", headers=who).json()["awards"]["achievements"] if a["code"] == "streak")  # noqa: E731
    assert page(tma(93, "Bea"))["now"] == want and page(tma(92, "Ali"))["now"] == want
    assert "now" not in page(tma(94, "Cat"))                                                         # a stranger: the medal alone
    assert cat["id"] and not con.execute("SELECT 1 FROM bot_outbox WHERE ref LIKE 'ach:streak:%'").fetchone()
    # an earned level stays though the live count drops (a past week's public event published or unpublished since)
    con.execute("INSERT OR REPLACE INTO achievement_levels (user_id, code, level, reached_at, seen) VALUES (?, 'streak', 3, 0, 3)", (bea["id"],))
    con.commit()
    mine = page(tma(93, "Bea"))
    assert mine["level"] == 3 and [x["reached"] for x in mine["levels"]] == [True, True, True, False] and mine["count"] >= 8
    logic.profiles._celebrate(con, bea["id"], {**logic.profiles._levels(con, bea["id"]), "streak": 0})  # a lower live level never overwrites it
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'streak'", (bea["id"],)).fetchone()[0] == 3


def test_badge_skin(env):
    """Badge skins: I show the lanyard of a club I'm in (by slug, official or not), or the KBTU one; never picked, a club
    with a badge shows by itself; my pick holds, and others see it. A club's is its members' alone (Oct 31); the
    creator's own is his alone."""
    c, cfg = env
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'studex', 'club', 'StudEx', 'SX', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'x', 'club', 'Side', 'X', 'laptop_3d', 0)")
    for o in (1, 2):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (o, pres["id"]))
    con.commit()
    P, A = tma(90, "Pres"), tma(91, "Ali")
    assert c.get("/api/me", headers=P).json()["skin"] == 1                        # never picked: StudEx's by itself
    assert c.patch("/api/me", headers=P, json={"skin": None}).json()["skin"] is None  # picked KBTU: it holds
    for bad in (2, 3, "1", True, "sower"):  # no lanyard, not a club, not an id, not the creator
        assert c.patch("/api/me", headers=P, json={"skin": bad}).status_code == 400
    assert c.patch("/api/me", headers=A, json={"skin": 1}).status_code == 400  # not in it: not his to wear
    con.execute("UPDATE users SET skin_pick = 'org', skin_org = 1 WHERE id = ?", (ali["id"],))  # one picked while it was open
    con.commit()
    assert c.get("/api/me", headers=A).json()["skin"] is None                     # falls back to the KBTU one
    assert c.get(f"/api/users/{ali['id']}", headers=P).json()["skin"] is None
    con.execute("UPDATE users SET skin_pick = NULL, skin_org = NULL WHERE id = ?", (ali["id"],))
    con.commit()
    assert c.patch("/api/me", headers=P, json={"skin": 1}).json()["skin"] == 1
    assert c.get(f"/api/users/{pres['id']}", headers=A).json()["skin"] == 1
    con.execute("DELETE FROM org_members WHERE org_id = 1")
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] is None  # left the club: its lanyard goes with it
    con.execute("UPDATE users SET skin_pick = NULL WHERE id = ?", (pres["id"],))
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] is None  # never picked: only a club I'm in comes by itself
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (3, 'kbtuknights', 'club', 'KBTU Knights', 'KN', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (3, ?, 'member', 0)", (pres["id"],))
    con.commit()
    assert c.patch("/api/me", headers=P, json={"skin": 3}).json()["skin"] == 3  # Knights have one too
    con.execute("UPDATE users SET skin_pick = NULL WHERE id = ?", (pres["id"],))
    con.commit()
    assert c.get("/api/me", headers=P).json()["skin"] == 3                        # and it comes by itself
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (4, 'crystalkbtu', 'club', 'Crystal', 'CR', 'gem_3d', 0, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (4, ?, 'member', 0)", (pres["id"],))
    con.commit()
    assert c.patch("/api/me", headers=P, json={"skin": 4}).json()["skin"] == 4  # not official: a lanyard all the same (Nov 2)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ali["id"],))
    con.commit()
    assert c.get("/api/me", headers=A).json()["skin"] == "sower"
    assert c.patch("/api/me", headers=A, json={"skin": None}).json()["skin"] is None
    assert c.patch("/api/me", headers=A, json={"skin": "sower"}).json()["skin"] == "sower"


def test_grant_link(env):
    """The admin's one-time award link: one student, once, celebrated (Bug hunter comes from a chat)."""
    c, cfg = env
    boss, ali = login(c, 60, "boss"), login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))  # a link works while its maker is an admin
    with pytest.raises(logic.ApiError):
        logic.grant_link(con, logic.Viewer(ali["id"], "user", True), "bugs")      # not the admin
    token = logic.grant_link(con, logic.Viewer(boss["id"], "admin", True), "bugs")
    login(c, 62, "bea")
    assert c.post(f"/api/grant-links/{token}", headers=tma(61)).json() == {"code": "bugs"}
    assert c.post(f"/api/grant-links/{token}", headers=tma(61)).json() == {"code": "bugs"}    # again: nothing more
    assert c.post(f"/api/grant-links/{token}", headers=tma(62)).json()["error"] == "closed"   # one person
    assert con.execute("SELECT granted_by FROM achievement_grants WHERE user_id = ? AND code = 'bugs'", (ali["id"],)).fetchone()[0] == boss["id"]


def test_premium_emoji(monkeypatch):
    """The pack's emoji: the plain ones our texts use become <tg-emoji>, with or without U+FE0F; the rest stay."""
    import re as _re
    from kbtu import bot
    monkeypatch.setattr(bot, "_custom", {"🎉": "1", "⚠": "2"})
    monkeypatch.setattr(bot, "_custom_re", _re.compile("🎉️?|⚠️?"))
    assert bot.premium("🎉 <b>IDC</b> ⚠️ 😔") == '<tg-emoji emoji-id="1">🎉</tg-emoji> <b>IDC</b> <tg-emoji emoji-id="2">⚠️</tg-emoji> 😔'
    monkeypatch.setattr(bot, "_custom_re", None)
    assert bot.premium("🎉") == "🎉"


def test_premium_emoji_everywhere(env, monkeypatch):
    """The pack's emoji in every HTML text the bot sends, channel and groups too; refused: once more plain."""
    import httpx
    _, cfg = env
    monkeypatch.setattr(bot, "_custom", {"💬": "42"})
    monkeypatch.setattr(bot, "_custom_re", re.compile("💬️?"))
    got = []

    def telegram(request: httpx.Request) -> httpx.Response:
        b = json.loads(request.content)
        got.append(b["text"])
        return httpx.Response(400 if "tg-emoji" in b["text"] and len(got) > 2 else 200, json={"ok": False, "description": "custom emoji not allowed"})

    async def go(body):
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot._tg(cfg, http, "sendMessage", body)
    asyncio.run(go({"chat_id": 1, "text": "💬 hi", "parse_mode": "HTML"}))
    asyncio.run(go({"chat_id": 1, "text": "💬 plain"}))                         # no HTML: left as it is
    assert got == ['<tg-emoji emoji-id="42">💬</tg-emoji> hi', "💬 plain"]
    asyncio.run(go({"chat_id": 1, "text": "💬 again", "parse_mode": "HTML"}))    # refused: plain, and the pack goes off
    assert got[2:] == ['<tg-emoji emoji-id="42">💬</tg-emoji> again', "💬 again"] and bot._custom_re is None


def test_new_levels_come_quietly(env):
    """"Recruiter" went from 4 levels to 9 (Nov 2): at the start, the levels people had already passed are recorded with
    no bot message and no unlock moment, stored levels move to the level of the same need; real progress afterwards is
    celebrated as usual."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann, bob = login(c, 300, "ann"), login(c, 301, "bob")
    def bring(uid, n):
        for _ in range(n):
            tg = 400000 + con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            u = c.get("/api/me", headers=tma(tg)).json()["id"]
            con.execute("UPDATE users SET referred_by = ? WHERE id = ?", (uid, u))
            con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, manual, synced_at, verified_at)
                VALUES (?, ?, 'X', 'Testov', 1, '1', 0, 0, 0, 0)""", (u, f"25B{tg:06d}"))
    bring(ann["id"], 18)
    bring(bob["id"], 2)
    # as before the change: ann had II (10 of the old 3/10/25/50) and saw it, bob had nothing
    logic.sync_levels(con)
    old = [[code, [3, 10, 25, 50] if code == "referral" else list(needs)] for code, _, needs, _ in logic.ACHIEVEMENTS]
    con.execute("UPDATE meta SET value = ? WHERE key = 'achievements'", (json.dumps(old),))
    con.execute("DELETE FROM achievement_levels WHERE code = 'referral'")
    con.execute("INSERT INTO achievement_levels (user_id, code, level, reached_at, seen) VALUES (?, 'referral', 2, 0, 2)", (ann["id"],))
    con.execute("DELETE FROM bot_outbox")
    logic.sync_levels(con)
    lv = lambda uid: con.execute("SELECT level, seen FROM achievement_levels WHERE user_id = ? AND code = 'referral'", (uid,)).fetchone()[:]  # noqa: E731
    assert lv(ann["id"]) == (5, 5) and lv(bob["id"]) == (1, 1)                         # 18 of 1/3/5/10/15: V; 2: I
    assert not con.execute("SELECT 1 FROM bot_outbox").fetchone()
    assert not [u for u in c.get("/api/me", headers=tma(300)).json()["unlocked"] if u["code"] == "referral"]
    tg, code = 500, c.get("/api/me", headers=tma(301)).json()["referrals"]["code"]     # the third one, after the start
    c.get("/api/me", headers=tma(tg))
    assert c.post("/api/referral", headers=tma(tg), json={"code": code}).status_code == 204
    uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, manual, synced_at, verified_at)
        VALUES (?, ?, 'X', 'Testov', 1, '1', 0, 1, 0, 0)""", (uid, f"25B{tg:06d}"))
    logic.ms_link(con, uid, {"oid": f"o{tg}", "email": f"x{tg}@kbtu.kz", "first": "X", "last": "Testov"})
    assert lv(bob["id"]) == (2, 1)
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:referral:2'", (bob["id"],)).fetchone()
    assert texts.tier_name("en", 2, 9) == "II" and texts.tier_name("en", 9, 9) == "Legend" and texts.tier_name("en", 3, 3) == "III"
