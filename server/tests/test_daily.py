"""The nightly and weekly jobs: the DMP memo, admin stats, backups."""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from fastapi.testclient import TestClient

from kbtu import ai, auth, chores, db, logic, outbox, app as server, texts
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def test_admin_stats(env, monkeypatch):
    """The admin's stats: online in 10 minutes, active day/week/month, students, new today; a row a night
    just after midnight from seen_at, none later in the day; counts only."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    t = int(time.time())
    assert c.get("/api/admin/stats", headers=tma(61, "Ali")).status_code == 403
    con.execute("UPDATE users SET seen_at = ?, created_at = ? WHERE id = ?", (t - 3 * 86400, t - 40 * 86400, ali["id"]))
    st = c.get("/api/admin/stats", headers=tma(60, "Boss")).json()
    assert (st["online"], st["day"], st["week"], st["month"], st["users"], st["students"], st["newToday"]) == (1, 1, 2, 2, 2, 2, 1)
    midnight = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    set_clock(monkeypatch, lambda: midnight + 3600 * 5)                          # 05:00: too late, today's visits would count
    logic.stats_day(con)
    assert not con.execute("SELECT 1 FROM stats_days").fetchone()
    set_clock(monkeypatch, lambda: midnight + 600)                               # 00:10
    logic.stats_day(con)
    logic.stats_day(con)
    assert [tuple(r) for r in con.execute("SELECT day, active, students FROM stats_days")] == [((t + 5 * 3600) // 86400 - 1, 1, 0)]  # both signed in today


def test_nightly_pending_lists_and_unresolved_map_notes_expire(env, monkeypatch):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    con = db.connect(cfg.db_path)
    t = (logic.now() + 5 * 3600) // 86400 * 86400 - 5 * 3600 + 600
    set_clock(monkeypatch, lambda: t)
    monkeypatch.setattr(logic.mapflaws, "now", lambda: t)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'club', 'club', 'Club', 'C', 'laptop_3d', 0)")
    for offset in (-1, 0, 1):
        con.execute("""INSERT INTO roster_pending (key, org_id, sheet, role, full_name, claimed_by, created_at)
            VALUES (?, 1, 'sheet', 'member', 'Example person', ?, ?)""", (str(offset), uid, t - 90 * 86400 + offset))
        for table in ("prefill", "prefill_rest"):
            con.execute(f"INSERT INTO {table} (email, student_id, loaded_at) VALUES (?, ?, ?)",
                        (f"test{offset}@example.test", str(offset), t - logic.account.PREFILL_KEEP + offset))
        for done in (False, True):
            con.execute("""INSERT INTO map_flaws (user_id, ver, floor, u, v, body, created_at, done_at)
                VALUES (?, 'kbtu', 1, 0.5, 0.5, ?, ?, ?)""", (uid, f"{done}:{offset}",
                    t - logic.mapflaws.OPEN_KEEP + offset, t - logic.mapflaws.KEEP + offset if done else None))
    for table in ("prefill", "prefill_rest"):
        con.execute(f"INSERT INTO {table} (email, student_id) VALUES ('undated@example.test', 'undated')")
    logic.stats_day(con)
    logic.stats_day(con)  # a retry on the same night is harmless
    assert [r[0] for r in con.execute("SELECT key FROM roster_pending")] == ["1"]
    for table in ("prefill", "prefill_rest"):
        assert [r[0] for r in con.execute(f"SELECT student_id FROM {table}")] == ["1"]
    assert {r[0] for r in con.execute("SELECT body FROM map_flaws")} == {"False:1", "True:1"}


def test_memo(env, monkeypatch):
    """The memo in one tap: next week's events that ask DMP for something become DMP's complex memos in one
    email, signed by whoever opens it; Wednesday morning the President and Vices hear it's ready. A place may be left
    to be confirmed: the memo then asks for any room, the organizer hears 7/3/1/0 days before, and typing the room in
    later sends nobody a message (the 2-hour reminder says it)."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ali")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    con.execute("UPDATE students SET middle_name = 'Erlanovich', phone = '87012345678' WHERE user_id = (SELECT id FROM users WHERE tg_id = 20)")
    monday = logic._next_week()
    base = {"emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    asks = {"room": {"any": True, "projector": True}, "guests": {"side": "tole", "list": "Ivanov Ivan, Satbayev University\n"}}
    a = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, **base, "title": "Hackday", "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "memo": asks}).json()
    assert a["memo"] == asks                                                                  # the editor gets it back (Head+)
    b = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, **base, "title": "Quiz", "place": "", "startsAt": monday + 3 * 86400 + 13 * 3600, "memo": {"room": {}}}).json()
    c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, **base, "title": "Talk", "place": "Atrium", "startsAt": monday + 2 * 86400})
    assert c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, **base, "title": "X", "place": "", "startsAt": monday, "memo": {"cake": {}}}).status_code == 400
    for e in (a, b):
        c.post(f"/api/events/{e['id']}/publish", headers=tma(20))
    assert c.get(f"/api/events/{a['id']}", headers=tma(10)).json()["memo"] is None             # students never see it

    m = c.get("/api/orgs/1/memo", headers=tma(20)).json()
    assert m["to"] == "youth_policy@kbtu.kz" and "IT Club" in m["subject"] and [x["title"] for x in m["events"]] == ["Hackday", "Quiz"]
    assert [x["title"] for x in m["without"]] == ["Talk"]
    text = m["text"]
    assert text.startswith(f"{texts.MEMO2_TO}\n{texts.MEMO2_TITLE[1]}\n")                   # one memo for the week
    assert "«Hackday»" in text.split("\n")[3] and "«Quiz»" in text.split("\n")[3]
    assert "№305" in text and "Ivanov Ivan, Satbayev University" in text and texts.memo_day(a["startsAt"]) in text
    numbered = [x for x in text.split("\n") if x[:3] in ("1) ", "2) ", "3) ")]
    assert len(numbered) == 3 and "305" in numbered[0] and "50" in numbered[2]               # numbered through the memo
    assert text.count("Pres Testov") == 3 and "Pres Testov\n+7 (701) 234 56 78\n-------" in text       # kk and ru, then the Latin one
    pos = texts.MEMO2_POS["president"]
    assert "\n".join((texts.MEMO2_SIGN["kk"][0], texts.MEMO2_SIGN["kk"][1].format(org="IT Club", pos=pos["kk"]))) in text
    assert "Kind regards,\nPresident of the student organization “IT Club”\nPres Testov" in text
    assert c.get("/api/orgs/1/memo", headers=tma(10)).status_code == 403

    # Wednesday 10:00 in Almaty: the President hears it once
    wed = monday - 5 * 86400 + 10 * 3600
    set_clock(monkeypatch, lambda: wed)
    logic.memo_week(con)
    logic.memo_week(con)
    sent = con.execute("SELECT kind, ref FROM bot_outbox WHERE kind = 'memo_ready'").fetchall()
    assert [tuple(r) for r in sent] == [("memo_ready", f"memo:1:{monday}")]
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'memo_ready'").fetchone()
    text, button, start = outbox._render(con, row)
    assert "IT Club" in text and start == "memo_1"

    # the place still to be confirmed: the organizer hears it 3 days before (Friday 10:00 for the Monday after)
    set_clock(monkeypatch, lambda: b["startsAt"] - 3 * 86400 - 3 * 3600)
    logic.tba_day(con)
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'place_tba'").fetchone()
    assert row and "Quiz" in outbox._render(con, row)[0]
    # DMP gave a room: typed in, nobody is told now
    c.post(f"/api/events/{b['id']}/registration", headers=tma(10), json={})
    before = con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'event_changed'").fetchone()[0]
    upd = c.patch(f"/api/events/{b['id']}", headers=tma(20), json={"seats": None, **base, "title": "Quiz", "place": "Aud. 412", "startsAt": b["startsAt"]})
    assert upd.status_code == 200 and con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'event_changed'").fetchone()[0] == before


def test_memo_reminder_excludes_memo_only_and_deleted_events(env, monkeypatch):
    c, cfg = env
    uid = login(c, 20, "pres")["id"]
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)
    logic.set_role(con, None, uid, oid, "president", "test")
    monday = logic._next_week()
    set_clock(monkeypatch, lambda: monday - 5 * 86400 + 10 * 3600)
    con.executemany("""INSERT INTO events (id, org_id, title, starts_at, memo, memo_only, created_at, updated_at)
        VALUES (?, ?, 'Quiz', ?, '{"room":{}}', ?, 0, 0)""", [(1, oid, monday, 1), (2, oid, monday, 0)])
    con.execute("INSERT INTO meta (key, value) VALUES ('evdel:2', '{}')")
    logic.memo_week(con)
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'memo_ready'").fetchone()
    queued = {"kind": "memo_ready", "user_id": uid, "lang": "en", "ref": f"memo:{oid}:{monday}"}
    assert outbox._render(con, queued) is None
    con.execute("DELETE FROM meta WHERE key = 'evdel:2'")
    assert outbox._render(con, queued) == (*texts.bot_message("en", "memo_ready", org="Chess", n=1), f"memo_{oid}")


def test_place_reminder_skips_online_and_santa_events(env, monkeypatch):
    c, cfg = env
    uid = login(c, 20, "pres")["id"]
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)
    morning = logic.core.day_start(logic.core.now()) + 10 * 3600
    set_clock(monkeypatch, lambda: morning)
    starts = morning + 86400 + 3600
    sql = """INSERT INTO events (id, org_id, title, status, starts_at, online, created_by, created_at, updated_at)
        VALUES (?, ?, ?, 'published', ?, ?, ?, 0, 0)"""
    con.executemany(sql, [(1, oid, "Webinar", starts, "https://example.com", uid),
                         (2, oid, "Stream", starts, "", uid), (3, oid, "Secret Santa", starts, None, uid)])
    con.execute("INSERT INTO santa_events (event_id) VALUES (3)")
    logic.tba_day(con)
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'place_tba'").fetchone()

    con.execute(sql, (4, oid, "Quiz", starts, None, uid))
    set_clock(monkeypatch, lambda: morning + 86400)
    logic.tba_day(con)
    row = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE kind = 'place_tba'").fetchone()
    text, _, link = outbox._render(con, row)
    assert link == "ev_4" and "Quiz" in text and all(title not in text for title in ("Webinar", "Stream", "Secret Santa"))


def test_memo_v2(env, monkeypatch):
    """Memo v2: one memo for the week with every request, a meeting's own line, the signature in
    kk, ru, en with the Latin name (fixed once); the secretary's "memo" right; sent events leave it until an edit;
    later events behind a switch; Wednesday's message to everyone with the right."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "sec"), (22, "head"), (10, "ali")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'stx', 'club', 'StudEx', 'SX', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_roles (id, org_id, name, color, level, created_at, rights) VALUES (1, 1, ?, '#888888', 'vice', 0, 'door,events,memo')",
                ("\u0421\u0435\u043a\u0440\u0435\u0442\u0430\u0440\u044c",))  # the role typed in Russian: "Secretary"

    con.execute("INSERT INTO org_members (org_id, user_id, role, role_id, joined_at) VALUES (1, ?, 'president', NULL, 0), (1, ?, 'vice', 1, 0), (1, ?, 'head', NULL, 0)",
                (uid[20], uid[21], uid[22]))
    cyr = ("\u0410\u0439\u0433\u0435\u0440\u0438\u043c", "\u0421\u0430\u043f\u0430\u0440\u043e\u0432\u0430")  # her portal name in Cyrillic
    con.execute("UPDATE students SET first_name = ?, last_name = ?, phone = '87001112233' WHERE user_id = ?", (*cyr, uid[21]))
    monday = logic._next_week()
    every = {"room": {"any": False, "projector": True, "board": True, "capacity": 40, "slots": [{"date": time.strftime("%Y-%m-%d", time.gmtime(monday + 4 * 86400 + 5 * 3600)), "from": "15:00", "to": "17:00"}]},
             "guests": {"side": "turgut", "list": "Ivanov Ivan, Satbayev University"},
             "provide": {"jbl": True, "tables": 2, "chairs": 10, "mixer": True, "cooler": 30, "other": "extension cord"},
             "promo": {"place": "Floor 1", "dates": ["2026-10-13", "2026-10-14", "2026-11-03"], "from": "12:00", "to": "18:00"},
             "gear": {"items": "Speaker", "outDate": "2026-10-20", "outTime": "17:00", "side": "kazybek"},
             "print": {"items": [{"name": "Poster", "count": 5, "format": "A3", "bw": False, "density": 2}]},
             "film": {"date": "2026-10-21", "from": "10:00", "to": "12:00", "note": "interview"}}
    base = {"emoji": "laptop_3d", "color": "#3B6BFF", "seats": 50}
    a = c.post("/api/orgs/1/events", headers=tma(21), json={"seats": None, **base, "title": "Hackday", "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "memo": every})
    assert a.status_code == 200
    a = a.json()
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, visibility, meeting, memo, created_by, created_at, updated_at)
        VALUES (90, 1, 'draft', 'General meeting', '', ?, 'laptop_3d', '#3B6BFF', 'members', 1, '{"room": {"capacity": 80}}', ?, 0, 0)""",
                (monday + 2 * 86400 + 14 * 3600, uid[20]))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, memo, created_by, created_at, updated_at)
        VALUES (91, 1, 'draft', 'Big fair', '', ?, 'laptop_3d', '#3B6BFF', '{"room": {"dorm": true, "dormPlace": "gym"}}', ?, 0, 0)""",
                (monday + 15 * 86400, uid[20]))
    assert c.get("/api/orgs/1/memo", headers=tma(22)).status_code == 403                    # a Head without "memo"
    m = c.get("/api/orgs/1/memo", headers=tma(21)).json()                                   # the secretary has it
    assert [x["title"] for x in m["events"]] == ["Hackday", "General meeting"] and [x["title"] for x in m["later"]] == ["Big fair"]
    t = m["text"]
    assert texts.MEMO2_FOR["meeting"].split("{")[0] + "General meeting»" in t
    assert texts.MEMO2_FOR["event"].split("{")[0] + "Hackday»" in t
    provide = [texts.MEMO2_PROVIDE[k].format(n=n) for k, n in (("jbl", 1), ("tables", 2), ("chairs", 10), ("mixer", 1), ("cooler", 30))]
    sec = texts.MEMO2_POS["secretary"]
    for bit in ("305 ", texts.MEMO2_ROOM_EXTRA["projector"], texts.MEMO2_ROOM_EXTRA["board"], " 40 ", f"{texts.memo_day(monday + 4 * 86400 + 43200)}\n",
                "15:00-17:00", texts.MEMO2_GUESTS_DORM.format(side=texts.MEMO2_DORM_SIDES["turgut"]),
                texts.MEMO2_PROVIDE_HEAD.format(items="; ".join([*provide, "extension cord"])), texts.MEMO2_QUIET,
                texts.MEMO2_DATES.format(dates=texts._dates(every["promo"]["dates"])),
                f"{texts.MEMO2_FILM}\n", "10:00-12:00", "interview", texts.MEMO2_SIGN["ru"][1].format(org="StudEx", pos=sec["ru"]) + f"\n{' '.join(cyr)}\n+7 (700) 111 22 33",
                texts.MEMO2_SIGN["kk"][1].format(org="StudEx", pos=sec["kk"]), "Secretary of the student organization “StudEx”\nAigerim Saparova"):
        assert bit in t, bit
    assert texts._dates(["2026-10-14", "2026-10-13", "2026-11-03"]) == f"13, 14 {texts.MONTHS['ru'][9]} \u0438 3 {texts.MONTHS['ru'][10]} 2026"
    seventh = next(x for x in t.split("\n") if x.startswith("7) "))
    assert "80" in seventh and "Poster" not in t                                            # the meeting's room: numbered on
    # printing goes in its own letter to the Publishing Center, signed in Russian
    pr = m["print"]
    assert pr["to"] == "ic@kbtu.kz" and "Hackday" in pr["subject"] and "General meeting" not in pr["subject"]
    for bit in ("1) ", "Poster", "A3", f"{texts.MEMO2_DENSITY[2]} ", texts.MEMO2_SIGN["ru"][1].format(org="StudEx", pos=sec["ru"]), "+7 (700) 111 22 33"):
        assert bit in pr["text"], bit
    assert m["guests"] and m["sign"]["nameEn"] == "Aigerim Saparova" and not m["sign"]["fixed"]
    assert "Big fair" in c.get("/api/orgs/1/memo?later=true", headers=tma(21)).json()["text"]   # the switch
    m = c.put("/api/orgs/1/memo/sign", headers=tma(21), json={"nameEn": "Aigerim Saparova-Lee", "kk": "", "ru": "", "en": ""}).json()
    assert "Aigerim Saparova-Lee" in m["text"] and m["sign"]["fixed"] and m["sign"]["ru"] == texts.MEMO2_POS["secretary"]["ru"]

    # opened, then "Sent it?" -> yes: they leave the memo; an edit of the requests brings Hackday back
    assert c.post("/api/orgs/1/memo/opened", headers=tma(21)).status_code == 204
    assert c.get("/api/orgs/1/memo", headers=tma(20)).json()["opened"]["by"]
    assert c.post("/api/orgs/1/memo/sent", headers=tma(21), json={"ids": [a["id"], 90]}).status_code == 204
    m = c.get("/api/orgs/1/memo", headers=tma(20)).json()
    assert m["events"] == [] and texts.MEMO2_BLANK.format(org="StudEx") in m["text"] and {x["id"] for x in m["sent"]} == {a["id"], 90} and m["sent"][0]["sentBy"]
    # DMP sees it in the app: the club, its events, who said "sent"; others may not look
    assert c.get("/api/registry/memos", headers=tma(20)).status_code == 403
    login(c, 29, "dmp")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 9, id, 'head', 0 FROM users WHERE tg_id = 29")
    con.commit()
    sent = c.get("/api/registry/memos", headers=tma(29)).json()
    assert len(sent) == 1 and sent[0]["org"]["id"] == 1 and sent[0]["by"] and {x["id"] for x in sent[0]["events"]} == {a["id"], 90}
    c.patch(f"/api/events/{a['id']}", headers=tma(20), json={"seats": None, **base, "title": "Hackday", "place": "Aud. 305", "startsAt": a["startsAt"], "memo": {"room": {}}})
    assert [x["title"] for x in c.get("/api/orgs/1/memo", headers=tma(20)).json()["events"]] == ["Hackday"]
    one_ = c.get("/api/orgs/1/memo", headers=tma(20)).json()["text"]
    assert one_.split("\n")[1] == texts.MEMO2_TITLE[0] and texts.MEMO2_FOR["event"].split("{")[0] not in one_  # one event: no per-event line
    assert c.post("/api/orgs/1/memo/again/90", headers=tma(20)).status_code == 204
    assert len(c.get("/api/orgs/1/memo", headers=tma(20)).json()["events"]) == 2

    # Wednesday 10:00: the President and the secretary hear it, the Head doesn't
    set_clock(monkeypatch, lambda: monday - 5 * 86400 + 10 * 3600)
    logic.memo_week(con)
    told = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'memo_ready'")}
    assert told == {uid[20], uid[21]}

    # with nothing asked, the blank with the signature and the templates
    con.execute("UPDATE events SET memo = NULL WHERE org_id = 1")
    m = c.get("/api/orgs/1/memo", headers=tma(21)).json()
    assert m["text"].startswith(texts.MEMO2_TO) and texts.MEMO2_BLANK.format(org="StudEx") in m["text"] and m["signFrom"] in m["text"]
    item = {"seats": None, "kind": "room", "fields": {"any": True, "projector": True}, "place": "Aud. 305", "startsAt": monday + 86400 + 13 * 3600, "endsAt": monday + 86400 + 15 * 3600}
    r = c.post("/api/orgs/1/memo/item", headers=tma(21), json=item)
    assert r.status_code == 200 and "305" in r.json()["text"] and "13:00-15:00" in r.json()["text"]
    assert c.post("/api/orgs/1/memo/item", headers=tma(22), json=item).status_code == 403   # a Head without "memo"
    assert c.post("/api/orgs/1/memo/item", headers=tma(21), json={**item, "kind": "print"}).status_code == 400


def test_nightly_backup(env, monkeypatch):
    """A copy of the database each night after 04:00 Almaty, once, the last 14 kept (there were none)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    day0 = 20000 * 86400 - 5 * 3600                                    # 00:00 Almaty
    for d in range(16):
        for hour in (3, 5, 6):                                         # before 04:00 nothing; after, once
            monkeypatch.setattr(chores.time, "time", lambda: day0 + d * 86400 + hour * 3600)
            chores.backup_day(cfg, con)
    kept = sorted((Path(cfg.db_path).resolve().parent / "backups").glob("kbtu-*.db"))
    assert len(kept) == 14 and kept[-1].name == "kbtu-2024-10-19.db"
    copy = db.connect(str(kept[-1]))
    assert copy.execute("SELECT COUNT(*) FROM users").fetchone()[0] == con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_offsite_backup(env, monkeypatch):
    """The off-site copy: SigV4 as AWS's own example signs it; after the night's copy, it and the receipts
    go up once (Sundays the media too), a failure is tried again an hour later, never while one is running."""
    from kbtu import offsite
    auth = offsite.sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt",
                        {"range": "bytes=0-9", "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                         "x-amz-date": "20130524T000000Z"}, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "20130524T000000Z")
    assert auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    _, cfg = env
    con = db.connect(cfg.db_path)
    sent, fail = [], [True]
    def up(paths, name, work):
        if fail[0]:
            raise RuntimeError("R2 503")
        sent.append((name, [p.name for p in paths]))
        return 1024
    monkeypatch.setattr(offsite, "ready", lambda: True)
    monkeypatch.setattr(offsite, "upload", up)
    sunday = 20002 * 86400                                              # 05:00 Almaty, Sunday 2024-10-06
    clock = [sunday]
    monkeypatch.setattr(chores.time, "time", lambda: clock[0])
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(chores, "now", lambda: clock[0])
    jobs = []
    class Loop:
        def create_task(self, coro):
            coro.close()
            return None
    monkeypatch.setattr(chores.asyncio, "get_running_loop", lambda: Loop())
    monkeypatch.setattr(chores.asyncio, "to_thread", lambda fn, *a: (jobs.append(a), fn(*a), _noop())[2])
    chores.backup_day(cfg, con)
    chores.offsite_round(cfg, con)                                         # the first try fails
    assert sent == [] and len(jobs) == 1
    fail[0] = False
    chores.offsite_round(cfg, con)                                         # within the hour: not again
    assert len(jobs) == 1
    clock[0] += 3600
    chores.offsite_round(cfg, con)
    assert [n.split("/")[0] for n, _ in sent] == ["db", "media"] and sent[0][1] == ["kbtu-2024-10-06.db", "receipts", "deletions.log", "deletions.salt"]
    assert sent[1][1] == ["media"]  # never "ako": the admissions' documents are in no backup (privacy policy, section 17)
    clock[0] += 3600
    chores.offsite_round(cfg, con)                                         # done for the day
    assert len(sent) == 2
    con.execute("INSERT INTO users (tg_id, role, created_at, seen_at) VALUES (9001, 'admin', 0, 0)")
    alerts = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'backup_failed'").fetchone()[0]  # noqa: E731
    fail[0] = True
    clock[0] = sunday + 86400 + 6 * 3600                                # Monday 11:00, failing: Sunday's copy is there
    chores.offsite_round(cfg, con)
    assert alerts() == 0
    clock[0] += 86400                                                   # Tuesday 11:00: two nights without one
    chores.offsite_round(cfg, con)
    clock[0] += 3600
    chores.offsite_round(cfg, con)                                         # once per outage, not once a day
    clock[0] += 86400
    chores.offsite_round(cfg, con)                                         # Wednesday, still failing: no second alert
    assert alerts() == 1
    oks = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'backup_ok'").fetchone()[0]  # noqa: E731
    fail[0] = False
    clock[0] += 3600
    chores.backup_day(cfg, con)                                            # the night's local copy, as the bot makes it
    chores.offsite_round(cfg, con)                                         # tonight's copy gets through
    assert oks() == 0                                                   # (counted once R2 said 200)
    clock[0] += 60
    chores.offsite_round(cfg, con)
    clock[0] += 3600
    chores.offsite_round(cfg, con)
    assert oks() == 1 and not con.execute("SELECT 1 FROM meta WHERE key = 'offsite_alert'").fetchone()
    fail[0] = True                                                      # a new outage: alerted again, once
    clock[0] += 2 * 86400
    chores.offsite_round(cfg, con)
    clock[0] += 3600
    chores.offsite_round(cfg, con)
    assert alerts() == 2
    payload = con.execute("SELECT payload, ref FROM bot_outbox WHERE kind IN ('backup_failed', 'backup_ok')").fetchall()
    assert all("key" not in (p or "").lower() and "secret" not in (p or "").lower() for p, _ in payload)  # nothing of the R2 credentials


async def _noop():
    return None


def test_admin_day_and_ai(env):
    """The admin's chart opens a day: who came in, newcomers marked. The AI page counts
    what was translated, what waits and what failed, and gives the failed three more tries."""
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({1}))))
    adm = c.get("/api/me", headers=tma(1)).json()
    ali = login(c, 30, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (adm["id"],))
    today = logic.day_of(logic.now())
    assert c.get(f"/api/admin/stats/{today}", headers=tma(30)).status_code == 403
    day = c.get(f"/api/admin/stats/{today}", headers=tma(1)).json()
    assert {p["id"] for p in day["people"]} >= {adm["id"], ali["id"]} and day["active"] == len(day["people"])
    assert c.get("/api/admin/stats", headers=tma(1)).json()["today"] == day["active"]
    assert c.get(f"/api/admin/stats/{today - 400}", headers=tma(1)).json()["people"] is None   # before the log
    # only opened the app: no profile to open (it was "Something went wrong"), the row goes to Telegram instead
    guest = c.get("/api/me", headers=tma(31)).json()
    prof = {p["id"]: p["profile"] for p in c.get(f"/api/admin/stats/{today}", headers=tma(1)).json()["people"]}
    assert prof[ali["id"]] and not prof[guest["id"]]
    assert c.get(f"/api/users/{guest['id']}", headers=tma(30)).status_code == 404
    ai = c.get("/api/admin/ai", headers=tma(1)).json()
    assert set(ai) >= {"on", "today", "chain", "usage", "events", "clubs", "failed"}
    assert c.post("/api/admin/ai/retry", headers=tma(30)).status_code == 403
    assert c.post("/api/admin/ai/retry", headers=tma(1)).status_code == 204


def test_memo_is_a_recognised_clubs_alone(env):
    """Owner, Nov 11: a club DMP has not accepted yet has no memos at all: no right in Studio, no memo kept on its
    event, the memo routes refuse; an official club keeps them."""
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    for oid, slug, official in ((1, "new", 0), (2, "old", 1)):
        con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (?, ?, 'club', ?, ?, 'laptop_3d', ?, 0)", (oid, slug, slug, slug, official))
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT ?, id, 'president', 0 FROM users WHERE tg_id = 20", (oid,))
    con.commit()
    rights = {m["org"]["id"]: m["rights"] for m in c.get("/api/me", headers=tma(20)).json()["memberships"]}
    assert "memo" not in rights[1] and "memo" in rights[2] and "events" in rights[1]
    monday = logic._next_week()
    ev = {"seats": None, "emoji": "laptop_3d", "color": "#3B6BFF", "title": "Talk", "place": "", "startsAt": monday + 86400 + 13 * 3600, "memo": {"room": {"any": True}}}
    assert c.post("/api/orgs/1/events", headers=tma(20), json=ev).json()["memo"] is None
    assert c.post("/api/orgs/2/events", headers=tma(20), json=ev).json()["memo"] == {"room": {"any": True}}
    assert c.get(f"/api/orgs/1/memo?week={monday}", headers=tma(20)).status_code == 403
    assert c.get(f"/api/orgs/2/memo?week={monday}", headers=tma(20)).status_code == 200
