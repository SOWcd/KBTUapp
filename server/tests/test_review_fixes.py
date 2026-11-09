"""The cloud review's fixes (Nov 1, .claude/reports/cloud-review.md): what each one guards, as small as it can be."""
from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from kbtu import bot, db, logic, texts, tgc
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)
from test_tgcomments import COPY, Telegram, hear, msg, report, setup, student, tick


def test_delete_covers_tables_keyed_by_mail_or_id(env, monkeypatch):
    """1: account deletion reaches the tables keyed by a mail, a student ID or a Telegram id (no foreign key to users):
    a new one fails here until delete_me handles it; a check-in screen's expected list goes with my account, and 30
    days after its session ended for everyone."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    keyed = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
             if {r[1] for r in con.execute(f"PRAGMA table_info({t})")} & {"email", "student_id", "tg_id", "author_tg", "phone"}}
    # handled in delete_me (or the account row itself); roster_pending: a club's one-off sheet, only the row I claimed goes
    assert keyed == {"users", "students", "prefill", "prefill_rest", "qr_expected", "tgc_saved", "tgc_strangers", "tgc_comments",
                     "roster_pending"}, keyed

    ali = login(c, 21, "ali")
    con.execute("UPDATE students SET email = 'ali@kbtu.kz' WHERE user_id = ?", (ali["id"],))
    from kbtu import checkin
    s1 = checkin.new(con, "Fair", [{"email": "ALI@kbtu.kz", "name": "Ali T"}, {"email": "x@kbtu.kz", "name": "Ali Testov", "studentId": "24Bali"},
                                   {"email": "y@kbtu.kz", "name": "Bek Omarov", "studentId": "24Bali"}, {"email": "dan@kbtu.kz", "name": "Dan"}])
    aid = ali["id"]
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    mail = con.execute("SELECT lower(email) FROM students WHERE user_id = ?", (aid,)).fetchone()[0]
    for key, claimed, rejected, email in (("claimed", aid, None, mail), ("my_word", aid, None, None), ("turned_down", None, aid, None), ("someone", None, None, None)):
        con.execute("""INSERT INTO roster_pending (key, org_id, sheet, role, full_name, phone, email, claimed_by, rejected_by, created_at)
            VALUES (?, 1, 's', 'vice', 'A Name', '+77000000000', ?, ?, ?, 0)""", (key, email, claimed, rejected))
    con.execute("INSERT INTO meta (key, value) VALUES (?, '1'), ('fsearch:999:1', '1'), ('rclaim:1', ?), ('rclaim:2', '999')", (f"fsearch:{aid}:1", str(aid)))
    for action, by in (("team_link_join", aid), ("grant_link_used", aid), ("team_link_join", 999)):
        con.execute("INSERT INTO audit_log (action, target, data, at) VALUES (?, 'x', ?, 0)", (action, f'{{"link": "ab", "by": {by}}}'))
    bob = login(c, 22, "bob")["id"]
    mine_ = {"friend_new": f"fn:{aid}:1", "friend_request": f"fq:{aid}:1", "join_request": f"jr:1:{aid}:1", "team_ask": f"ta:1:{aid}:1", "friend_invite": f"fi:1:{aid}",
             "roster_claim": f"rq:1:{aid}", "tgc_good": f"gr:{aid}"}
    for kind, ref in mine_.items():  # sent ones too: other people's queues
        con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after, sent_at) VALUES (?, ?, ?, 0, 1)", (bob, kind, ref))
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after, sent_at) VALUES (?, 'join_request', ?, 0, 1)", (bob, f"jr:{aid}:999:1"))  # a club's number, not mine
    con.execute("UPDATE users SET announce_ok = 1 WHERE id = ?", (aid,))
    delete_now(c, cfg, tma(21, "Ali"))
    assert con.execute("SELECT announce_ok FROM users WHERE id = ?", (aid,)).fetchone()[0] is None
    assert [r[0] for r in con.execute("SELECT ref FROM bot_outbox WHERE user_id = ?", (bob,))] == [f"jr:{aid}:999:1"]
    # who made the link leaves the line, the line stays
    assert [(r[0], r[1]) for r in con.execute("SELECT json_extract(data, '$.link'), json_extract(data, '$.by') FROM audit_log WHERE target = 'x' ORDER BY id")] == [
        ("ab", None), ("ab", None), ("ab", 999)]
    assert [r[0] for r in con.execute("SELECT key FROM meta WHERE key LIKE 'fsearch:%' OR key LIKE 'rclaim:%' ORDER BY key")] == ["fsearch:999:1", "rclaim:2"]
    # the row with my verified mail goes and a reload doesn't bring it back; one I only said was mine, turned down or never claimed is the club's
    assert [tuple(r) for r in con.execute("SELECT key, claimed_by, rejected_by FROM roster_pending ORDER BY key")] == [
        ("my_word", None, None), ("someone", None, None), ("turned_down", None, None)]
    assert [r[0] for r in con.execute("SELECT key FROM meta WHERE key LIKE 'roster_done:%'")] == ["roster_done:claimed"]
    # by mail; by my ID only with my name (Bek's row with a typo of my ID is his)
    assert [r[0] for r in con.execute("SELECT email FROM qr_expected WHERE session_id = ? ORDER BY email", (s1,))] == ["dan@kbtu.kz", "y@kbtu.kz"]

    s2 = checkin.new(con, "Old", [{"email": "dan@kbtu.kz", "name": "Dan"}])
    con.execute("UPDATE qr_sessions SET started_at = 1, ended_at = ? WHERE id = ?", (int(time.time()) - 32 * 86400, s2))  # 32: "night" can be a day back (19:00-24:00 UTC)
    s3 = checkin.new(con, "Left running", [{"email": "dan@kbtu.kz", "name": "Dan"}])
    con.execute("UPDATE qr_sessions SET started_at = 1, created_at = ? WHERE id = ?", (int(time.time()) - 92 * 86400, s3))
    night = int(time.time()) // 86400 * 86400 - 5 * 3600 + 3600  # 01:00 in Almaty: the nightly round's hour
    set_clock(monkeypatch, lambda: night)
    logic.stats_day(con)
    assert con.execute("SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", (s2,)).fetchone()[0] == 0  # ended a month ago
    assert con.execute("SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", (s3,)).fetchone()[0] == 0  # never ended, 3 months
    assert con.execute("SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", (s1,)).fetchone()[0] == 2  # new: kept
    assert con.execute("SELECT 1 FROM qr_sessions WHERE id = ?", (s2,)).fetchone()                       # the session stays


def _png(color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (600, 1200), color).save(out, "PNG")
    return out.getvalue()


def test_replaced_receipt(env):
    """2, 3: a replaced receipt's picture leaves the disk, but its fingerprint stays: someone else uploading it later is
    flagged as a duplicate. Three replacements, then the organizer looks at the last one."""
    c, cfg = env
    for uid, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    eid = c.post("/api/orgs/1/events", headers=tma(20), json={"title": "Gala", "place": "Hall", "startsAt": int(time.time()) + 3600, "emoji": "laptop_3d",
                                                              "color": "#3B6BFF", "seats": 5, "price": 2000, "payToName": "Arman A",
                                                              "payPhone": "87071234567"}).json()["id"]
    c.post(f"/api/events/{eid}/publish", headers=tma(20))
    root = Path(cfg.db_path).parent / "receipts"
    path = lambda: con.execute("SELECT f.path FROM receipts r JOIN files f ON f.id = r.file_id ORDER BY r.id DESC").fetchone()[0]  # noqa: E731
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    first = _png((250, 0, 0))
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=first).json()["my"]["status"] == "going"
    was = path()
    assert (root / f"{was}.webp").exists()
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_png((0, 0, 250))).json()["my"]["receiptFlags"] == []
    assert not (root / f"{was}.webp").exists() and (root / f"{path()}.webp").exists()          # the replaced one left the disk
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=first).json()["my"]["receiptFlags"] == ["duplicate"]
    for color in ((0, 250, 0), (250, 250, 0)):
        assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_png(color)).status_code == 200
    r = c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_png((0, 250, 250)))
    assert r.status_code == 429 and len(list(root.rglob("*.webp"))) == 2 * 2                     # refused; on disk: Bob's and Ali's last


def test_close_counts_abuse_only(env, monkeypatch):
    """5: /report closes after two abuse findings in 30 days (the policy's "twice"); reports a moderator simply kept
    (overturned) don't count toward it."""
    c, cfg, con, _ = setup(env, monkeypatch, {})
    student(c, con, 20, "ali")
    r = student(c, con, 21, "bek")
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (student(c, con, 24, "mod"),))
    tg = Telegram()
    hear(cfg, tg, COPY, *(report(60 + i, 21, msg(50 + i, 20, f"words {i}")) for i in range(3)))
    a, b, d = [x for (x,) in con.execute("SELECT id FROM tgc_comments ORDER BY id")]
    assert c.post(f"/api/admin/reports/tgc/{a}", headers=tma(24), json={"keep": True}).status_code == 204
    assert c.post(f"/api/admin/reports/tgc/{b}", headers=tma(24), json={"abuse": True}).status_code == 204
    assert not con.execute("SELECT 1 FROM tgc_closed").fetchone()             # one kept, one abuse: open still
    assert c.post(f"/api/admin/reports/tgc/{d}", headers=tma(24), json={"abuse": True}).status_code == 204
    assert con.execute("SELECT user_id FROM tgc_closed").fetchone()[0] == r


def test_no_self_checkin_by_scanner(env):
    """7: a Member at the door can't scan their own ticket in (as by name): that's for whoever runs the event."""
    c, cfg = env
    pres, mem = login(c, 70, "pres"), login(c, 71, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', '1-MMM2', 0, 0)", (mem["id"],))
    assert c.post("/api/events/1/checkin", headers=tma(71, "Mem"), json={"code": "KBTUMMM2"}).status_code == 403
    assert con.execute("SELECT checked_in_at FROM registrations WHERE user_id = ?", (mem["id"],)).fetchone()[0] is None
    assert c.post("/api/events/1/checkin", headers=tma(70, "Pres"), json={"code": "KBTUMMM2"}).json()["result"] == "ok"


def test_deleted_author_still_leaves_the_group(env, monkeypatch):
    """8: a comment in the moderators' queue (or being deleted) whose author deletes the account still comes out of
    the group: its ids wait in tgc_undel, nothing personal, and the round deletes it."""
    c, cfg, con, _ = setup(env, monkeypatch, {})
    student(c, con, 20, "ali")
    student(c, con, 21, "bek")
    tg = Telegram()
    hear(cfg, tg, COPY, report(60, 21, msg(50, 20, "rude")))
    con.execute("UPDATE tgc_comments SET status = 'queued'")
    delete_now(c, cfg, tma(20))
    assert not con.execute("SELECT 1 FROM tgc_comments").fetchone()
    assert [tuple(r) for r in con.execute("SELECT chat_id, msg_id FROM tgc_undel")] == [(cfg.tgc_chat, 50)]
    tick(cfg, tg, con)
    assert {"chat_id": cfg.tgc_chat, "message_id": 50} in tg.of("deleteMessage")
    assert not con.execute("SELECT 1 FROM tgc_undel").fetchone()


def test_edits_cap_fresh_looks(env, monkeypatch):
    """10: each edit of a reported comment may cost an AI look, EDIT_LOOKS a day per author; then a moderator decides."""
    c, cfg, con, looked = setup(env, monkeypatch, {})
    student(c, con, 20, "ali")
    student(c, con, 21, "bek")
    monkeypatch.setattr(logic.tgcomments, "EDIT_LOOKS", 2)
    tg = Telegram()
    hear(cfg, tg, COPY, report(60, 21, msg(50, 20, "v0")))
    for i in range(1, 5):
        hear(cfg, tg, {"edited_message": msg(50, 20, f"v{i}")})
    assert looked == ["v0", "v1", "v2"]


def test_resolve_report_is_one_transaction(env, monkeypatch):
    """11: a take-down and its reports closing go together: a failure halfway leaves both as they were."""
    c, cfg = env
    for tg_, name in ((20, "pres"), (21, "ali"), (22, "mod")):
        login(c, tg_, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (int(time.time()) + 86400,))
    author = con.execute("SELECT id FROM users WHERE tg_id = 21").fetchone()[0]
    cid = con.execute("INSERT INTO comments (event_id, user_id, as_org, body, created_at) VALUES (1, ?, 0, 'rude', 0)", (author,)).lastrowid
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, created_at) SELECT id, 'comment', ?, 'insult', 0 FROM users WHERE tg_id = 20", (cid,))
    con.execute("UPDATE users SET role = 'moderator' WHERE tg_id = 22")

    def broken(*a, **kw):
        raise RuntimeError("audit log down")
    monkeypatch.setattr(logic.moderation, "log_action", broken)
    with pytest.raises(RuntimeError):
        logic.resolve_report(con, logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = 22").fetchone()[0], "moderator", True), "comment", cid, True)
    assert con.execute("SELECT deleted_at FROM comments WHERE id = ?", (cid,)).fetchone()[0] is None
    assert con.execute("SELECT status FROM reports").fetchone()[0] == "open"


def test_sweeps_run_with_the_forum_off(env, monkeypatch):
    """12: the forum's retention (comments' copies after 30 days, deleted posts' rows) holds even with its switches off."""
    _, cfg = env  # no FORUM_GROUP, no FORUM_CHANNEL
    con = db.connect(cfg.db_path)
    ali = login(env[0], 20, "ali")
    con.execute("INSERT INTO tgc_comments (chat_id, msg_id, author_tg, body, created_at) VALUES (1, 1, 20, 'old', 0)")
    con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, created_at) VALUES (?, '', 0, 'gone', 0)", (ali["id"],))
    con.execute("DELETE FROM meta WHERE key LIKE 'tgc_sweep%'")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(Telegram())) as http:
            await bot.send_due(cfg, http)
    asyncio.run(go())
    assert not con.execute("SELECT 1 FROM tgc_comments").fetchone() and not con.execute("SELECT 1 FROM fchan_posts").fetchone()


def test_decline_words_in_the_app_only(env):
    """6a: the club's decline words reach a declined applicant in the app (the round's sheet); the bot's DM only says
    they're there, with the button."""
    c, cfg = env
    bob = login(c, 11, "bob")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    t = int(time.time())
    rid = con.execute("""INSERT INTO rounds (org_id, title, closes_at, decline_text, status, created_at, sent_at)
        VALUES (1, 'Autumn', ?, 'Full this time <b>sorry</b>', 'done', 0, ?)""", (t - 60, t)).lastrowid
    aid = con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, stage, created_at, updated_at)
        VALUES (?, ?, '[]', '{}', 'no', 0, 0)""", (rid, bob["id"])).lastrowid
    text, button, start = bot._render(con, {"kind": "round_no", "ref": f"rn:{aid}", "lang": "en", "user_id": bob["id"]})
    assert "Full this time" not in text and "in the app" in text and start == "iv_1"
    r = c.get("/api/orgs/1/round", headers=tma(11)).json()
    assert (r["mine"]["stage"], r["declineText"]) == ("no", "Full this time <b>sorry</b>")
    con.execute("UPDATE rounds SET decline_text = ''")                          # nothing written: nothing to show
    assert c.get("/api/orgs/1/round", headers=tma(11)).json() is None
    assert bot._render(con, {"kind": "round_no", "ref": f"rn:{aid}", "lang": "en", "user_id": bob["id"]})[2] == "clubs"


def test_lost_send_found_by_its_copy(env):
    """9: a channel send whose answer never came is found when its copy reaches the discussion group: its message id
    kept (a delete or a take-down reaches it), live again; the late answer then changes nothing."""
    c, cfg = env
    ann = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    F = logic.fchannel
    pid = con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'hello all', 0, 'held', 'lost', 0)",
                      (ann["id"],)).lastrowid
    F.found(con, 77, "Ann T\n\nhello all")
    assert tuple(con.execute("SELECT status, why, tg_msg FROM fchan_posts WHERE id = ?", (pid,)).fetchone()) == ("live", None, 77)
    F.sent(con, pid, 77)                                                          # its answer, late
    assert not con.execute("SELECT 1 FROM tg_unpost").fetchone()
    F.delete(con, logic.Viewer(ann["id"], "user", True), pid)
    assert con.execute("SELECT msg_id FROM tg_unpost").fetchone()[0] == 77

    # another student's same words never become hers: the signature must match, a held message id is never taken,
    # and two equal anonymous texts are nobody's to guess
    bob = login(c, 2, "bob")
    q = lambda sql, *a: con.execute(sql, a).lastrowid  # noqa: E731
    lost = q("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'who goes tonight?', 1, 'held', 'lost', 0)", ann["id"])
    q("INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at) VALUES (?, 'who goes tonight?', 0, 'live', 500, 0)", bob["id"])
    anon = F.anon_sign("who goes tonight?")
    F.found(con, 500, "Bob T\n\nwho goes tonight?")
    F.found(con, 500, f"{anon}\n\nwho goes tonight?")
    assert con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (lost,)).fetchone()[0] is None
    q("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'who goes tonight?', 1, 'held', 'lost', 0)", bob["id"])
    F.found(con, 501, f"{anon}\n\nwho goes tonight?")
    assert not con.execute("SELECT 1 FROM fchan_posts WHERE tg_msg = 501").fetchone()
    con.execute("DELETE FROM fchan_posts WHERE user_id = ? AND anon = 1", (bob["id"],))
    F.found(con, 501, f"{anon}\n\nwho goes tonight?")                 # hers alone now: found
    assert con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (lost,)).fetchone()[0] == 501
    # a send lost across the Nov 2 deploy went out in the old format (the words, then "- name"): still found
    old = q("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'old style', 0, 'held', 'lost', 0)", bob["id"])
    F.found(con, 502, "old style\n\n— Bob T")
    assert con.execute("SELECT tg_msg FROM fchan_posts WHERE id = ?", (old,)).fetchone()[0] == 502


def test_no_self_checkin_by_typed_name(env):
    """Review 2: a door member who typed their own name as a walk-in isn't checked in by it on a Microsoft sign-in;
    whoever runs the event (events right) still is."""
    c, cfg = env
    pres, mem = login(c, 70, "pres"), login(c, 71, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], mem["id"]))
    start = int(time.time()) - 600
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 7200, pres["id"]))
    assert c.post("/api/events/1/door/guests", headers=tma(71, "Mem"), json={"name": "Mem Testov"}).status_code == 200
    assert c.post("/api/events/1/door/guests", headers=tma(70, "Pres"), json={"name": "Pres Testov"}).status_code == 200
    ms = lambda uid: logic.ms_link(con, uid, {"oid": f"o{uid}", "email": f"u{uid}@kbtu.kz", "first": "", "last": "", "profile": {}})  # noqa: E731
    came = lambda uid: con.execute("SELECT checked_in_at FROM registrations WHERE user_id = ? AND event_id = 1", (uid,)).fetchone()  # noqa: E731
    ms(mem["id"])
    assert came(mem["id"]) is None
    ms(pres["id"])
    assert came(pres["id"])[0] is not None


def test_signature_lookalikes_refused():
    """Small: a last line posing as the bot's signature with a minus sign or a fullwidth hyphen is refused too."""
    for dash in ("\u2212", "\uff0d", "\ufe58", "\u2011", "-"):
        with pytest.raises(logic.ApiError):
            logic.fchannel._clean(f"I saw it all\n{dash} Dana S")
