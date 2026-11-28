"""Account: consent, legal pages, privacy, deleting an account and erasure surviving restores."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import auth, chores, config, db, logic, outbox, app as server
from test_core import BOT, delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def test_delete_my_data(env):
    """Deleting an account (H2): a week, then the student's data goes; the Telegram account stays a guest. What is over moves to a
    nameless placeholder, so every count stays; free text, receipts, names go; a President's club passes on."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    t0 = int(time.time())
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    for eid, at in ((1, t0 + 86400), (2, t0 - 2 * 86400)):  # one ahead, one over
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, created_by, created_at, updated_at)
            VALUES (?, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 1, ?, 0, 0)""", (eid, at, ali["id"]))
    A, Z = tma(21, "Ali"), tma(22, "Zhan")
    c.post("/api/events/1/registration", headers=A)     # the only seat (a guest then: the club's own can't sign up)
    c.post("/api/events/1/registration", headers=Z)     # waitlist
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'head', 0)", (ali["id"],))  # written directly: keeps the seat
    c.put("/api/events/1/saved", headers=A)
    c.put("/api/orgs/1/subscription", headers=A)
    c.patch("/api/me", headers=A, json={"bio": "hi"})
    # Ali's past: came to event 2 (paid, rated, volunteered), brought Zhan, a casting round, words as the club and his own
    with db.tx(con):
        for uid, inv in ((ali["id"], None), (zhan["id"], ali["id"])):
            con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, invited_by, created_at, updated_at, checked_in_at, note)
                VALUES (2, ?, 'going', ?, ?, 0, 0, ?, 'vegan')""", (uid, f"T{uid}", inv, t0 - 2 * 86400))
        fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('r', 'receipt', 'image/jpeg', 1, 'ab/rcpt', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) SELECT id, ?, 'app', 0 FROM registrations WHERE event_id = 2 AND user_id = ?",
                    (fid, ali["id"]))
        pic = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('p', 'event_photo', 'image/webp', 1, 'ab/pic', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (2, ?, 0, ?)", (pic, ali["id"]))
        con.execute("INSERT INTO event_ratings (event_id, user_id, score, comment, created_at) VALUES (2, ?, 5, 'great', 0)", (ali["id"],))
        con.execute("UPDATE registrations SET rating_dismissed = 1 WHERE event_id = 2 AND user_id = ?", (ali["id"],))
        con.execute("INSERT INTO volunteers (event_id, user_id, status, note, created_at) VALUES (2, ?, 'yes', 'call me', 0)", (ali["id"],))
        con.execute("INSERT INTO rounds (id, org_id, title, closes_at, status, created_at) VALUES (1, 1, 'Autumn', 0, 'done', 0)")
        app_id = con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, created_at, updated_at)
            VALUES (1, ?, 'dev', '{"why": "me"}', 0, 0)""", (ali["id"],)).lastrowid
        con.execute("INSERT INTO round_votes (app_id, user_id, verdict, note, at) VALUES (?, ?, 'next', 'strong', 0)", (app_id, pres["id"]))
        con.execute("INSERT INTO comments (event_id, user_id, as_org, body, created_at) VALUES (2, ?, 1, 'Thanks all', 0), (2, ?, 0, 'mine', 0)",
                    (ali["id"], ali["id"]))
        con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (1, ?, 0)", (ali["id"],))
        con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", tuple(sorted((ali["id"], zhan["id"]))))
    (Path(cfg.db_path).parent / "receipts" / "ab").mkdir(parents=True, exist_ok=True)
    (Path(cfg.db_path).parent / "receipts" / "ab" / "rcpt.jpg").write_bytes(b"x")
    came = lambda: con.execute("SELECT COUNT(*) FROM registrations WHERE event_id = 2 AND checked_in_at IS NOT NULL").fetchone()[0]  # noqa: E731
    zsoul = con.execute("SELECT COUNT(*) FROM registrations WHERE invited_by = ?", (ali["id"],)).fetchone()[0]

    reminders = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'remind_2h'", (ali["id"],)).fetchone()[0]  # noqa: E731
    assert reminders() == 1
    assert c.patch("/api/me", headers=A, json={"nRemind": False}).json()["settings"]["nRemind"] is False and reminders() == 0
    c.patch("/api/me", headers=A, json={"nRemind": True})
    assert reminders() == 1                                                                   # the switch acts at once

    assert c.get("/api/me/delete", headers=A).json() == {"photos": 1, "paid": False}
    delete = lambda h, **kw: c.post("/api/me/delete", headers=h, json=kw)  # noqa: E731
    assert delete(tma(23, "Guest")).status_code == 401
    at = delete(A).json()["deleteAt"]                                                    # a week to change my mind
    assert at > time.time() + 6 * 86400 and con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'delete_soon'", (ali["id"],)).fetchone()
    chores.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is not None                    # not yet
    assert c.post("/api/me/keep", headers=A).json()["deleteAt"] is None                 # changed my mind
    no = con.execute("SELECT card_no FROM users WHERE id = ?", (ali["id"],)).fetchone()[0]
    delete_now(c, cfg, A)
    left = [(t, col) for t, col, notnull in logic.account._user_fks(con) if (t, col) not in logic.account._DEL_KEEP
            if con.execute(f"SELECT 1 FROM {t} WHERE {col} = ?", (ali["id"],)).fetchone()]
    assert left == [], left                                                                   # every table, new ones too
    me = c.get("/api/me", headers=A).json()
    assert (me["student"], me["memberships"], me["bio"], me["qr"], me["no"]) == (None, [], "", None, None)    # a guest again
    u = con.execute("SELECT tg_username, tg_first_name, card_no, delete_at FROM users WHERE id = ?", (ali["id"],)).fetchone()
    assert tuple(u) == (None, "Ali", None, None)       # Telegram's name comes back only because he opened the app again
    assert c.get("/api/events/1", headers=Z).json()["my"]["status"] == "going"               # the seat went on
    # what is over stays counted, without him and without words
    ph = con.execute("SELECT * FROM users WHERE id = (SELECT user_id FROM event_ratings WHERE event_id = 2)").fetchone()
    assert ph["tg_id"] < 0 and ph["tg_id"] != -ali["id"]                                   # random: nothing leads back
    assert ph and (ph["tg_first_name"], ph["tg_username"], ph["seen_at"], ph["can_dm"]) == ("", None, 0, 0)
    assert came() == 2 and con.execute("SELECT note FROM registrations WHERE user_id = ?", (ph["id"],)).fetchone()[0] is None
    assert con.execute("SELECT rating_dismissed FROM registrations WHERE user_id = ?", (ph["id"],)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM registrations WHERE invited_by = ?", (ali["id"],)).fetchone()[0] == 0 and zsoul == 1
    assert tuple(con.execute("SELECT user_id, score, comment FROM event_ratings WHERE event_id = 2").fetchone()) == (ph["id"], 5, "")
    assert tuple(con.execute("SELECT user_id, note FROM volunteers").fetchone()) == (ph["id"], "")
    assert tuple(con.execute("SELECT user_id, answers FROM round_apps").fetchone()) == (ph["id"], "{}")
    assert con.execute("SELECT note FROM round_votes").fetchone()[0] == ""                  # others' words about him go too
    # his words stay, nameless (owner, Nov 2: as Telegram and Reddit), the club's comment and his own alike
    assert sorted(tuple(r) for r in con.execute("SELECT user_id, body FROM comments")) == [(ph["id"], "Thanks all"), (ph["id"], "mine")]
    assert con.execute("SELECT 1 FROM org_bans WHERE user_id = ?", (ali["id"],)).fetchone()
    assert con.execute("SELECT added_by FROM event_photos").fetchone()[0] is None            # the photo stays, nameless
    assert con.execute("SELECT owner_id FROM files WHERE id = ?", (pic,)).fetchone()[0] is None
    assert con.execute("SELECT created_by FROM events WHERE id = 2").fetchone()[0] is None
    assert not con.execute("SELECT 1 FROM receipts").fetchone() and not (Path(cfg.db_path).parent / "receipts" / "ab" / "rcpt.jpg").exists()
    # a returning Ali gets a new number, never his burnt one
    login(c, 21, "ali")
    assert c.get("/api/me", headers=A).json()["no"] not in (None, no)

    # a President leaving: the club passes to the highest rank left (Zhan; Ali, its head, left with his account); alone, to the admin
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (zhan["id"],))
    assert delete(tma(20, "Pres"), photos=True).status_code == 200
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (pres["id"],))
    chores.purge(cfg, con)
    assert con.execute("SELECT user_id FROM org_members WHERE org_id = 1 AND role = 'president'").fetchone()[0] == zhan["id"]
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'solo', 'club', 'Solo', 'S', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (2, ?, 'president', 0)", (zhan["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (pres["id"],))     # a deleted admin can't take it: no student
    boss = login(c, 30, "boss")
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    delete_now(c, cfg, Z)
    assert con.execute("SELECT user_id FROM org_members WHERE org_id = 2 AND role = 'president'").fetchone()[0] == boss["id"]
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'club_handover' AND ref = 'ho:2'", (boss["id"],)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM users WHERE tg_id < 0").fetchone()[0] == 3


def test_delete_lists_cover_schema(env):
    """Every column pointing at a person is in delete_me's lists or nullable: a new table can't keep someone by being
    forgotten (H2)."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    missing = [(t, col) for t, col, notnull in logic.account._user_fks(con) if notnull and (t, col) not in logic.account._DEL_GONE | logic.account._DEL_KEEP]
    assert missing == [], missing


def test_delete_with_a_ticket_out_of_sight(env):
    """A future seat at an event he can no longer see (the club hidden) doesn't block the deletion; the seat frees up.
    His unsent invites to friends go; deletions.log keeps "delete my photos too" and forgets lines after 40 days."""
    c, cfg = env
    ali, zhan = login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 1, 0, 0)""", (int(time.time()) + 86400,))
    A, Z = tma(21, "Ali"), tma(22, "Zhan")
    c.post("/api/events/1/registration", headers=A)
    c.post("/api/events/1/registration", headers=Z)                                      # waitlist
    con.execute("UPDATE orgs SET status = 'hidden'")
    logic.notify(con, zhan["id"], "friend_invite", f"fi:1:{ali['id']}")
    c.post("/api/me/delete", headers=A, json={"photos": True})
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (ali["id"],))
    chores.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is None
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (zhan["id"],)).fetchone()[0] == "going"
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE kind = 'friend_invite'").fetchone()
    log_ = Path(cfg.db_path).parent / "deletions.log"
    assert log_.read_text().split()[2] == "photos"
    log_.write_text(f"{int(time.time()) - 41 * 86400} {'0' * 32}\n" + log_.read_text() + "12")    # an old line, a torn one
    logic.account._prune_deletion_log(con)
    assert len(log_.read_text().splitlines()) == 1


def test_delete_waits_for_a_paid_ticket(env):
    """A ticket paid for an event still ahead: the deletion waits until it has passed."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, created_at, updated_at)
        VALUES (1, 1, 'published', 'Gala', '305', ?, 'laptop_3d', '#3B6BFF', '#2C50BF', 0, 0)""", (int(time.time()) + 86400,))
    with db.tx(con):
        con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T1', 0, 0)", (ali["id"],))
        fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, owner_id, created_at) VALUES ('r', 'receipt', 'image/jpeg', 1, 'ab/r', ?, 0)",
                          (ali["id"],)).lastrowid
        con.execute("INSERT INTO receipts (registration_id, file_id, via, created_at) SELECT id, ?, 'app', 0 FROM registrations", (fid,))
    A = tma(21, "Ali")
    assert c.get("/api/me/delete", headers=A).json()["paid"] is True
    delete_now(c, cfg, A)
    assert c.get("/api/me", headers=A).json()["student"] is not None                    # waits for the event
    con.execute("UPDATE events SET starts_at = ?", (int(time.time()) - 5 * 3600,))
    chores.purge(cfg, con)
    assert c.get("/api/me", headers=A).json()["student"] is None


def test_consent_again(env):
    """The privacy policy changed: a student agrees again once; the version is kept, staff keep theirs."""
    c, cfg = env
    login(c, 21, "ali")
    A = tma(21, "Ali")
    assert c.get("/api/me", headers=A).json()["student"]["consent"] == "1"
    assert c.post("/api/me/consent", headers=A, json={"version": ""}).status_code == 400
    assert c.post("/api/me/consent", headers=A, json={"version": "2026-10-v3"}).status_code == 400  # before the nick rule (v9): agree again
    assert c.post("/api/me/consent", headers=A, json={"version": logic.CONSENT}).json()["student"]["consent"] == logic.CONSENT == "2026-11-unified1"
    assert c.post("/api/me/consent", headers=tma(22, "Guest"), json={"version": logic.CONSENT}).status_code == 401
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET consent_version = 'staff'")
    assert c.post("/api/me/consent", headers=A, json={"version": logic.CONSENT}).json()["student"]["consent"] == "staff"


def test_legal_pages(env):
    """The privacy policy, the terms and how to delete an account (the stores' deletion link): public pages in three
    languages, linked to each other."""
    c, _ = env
    for doc in ("privacy", "terms", "delete"):
        for lang in ("ru", "kk", "en"):
            r = c.get(f"/{doc}?lang={lang}")
            assert r.status_code == 200 and f'lang="{lang}"' in r.text and "@Sowers" in r.text
            assert "{{" not in r.text and "<!--" not in r.text and 'class="ver"' in r.text  # the unified texts: no flag markers, nothing to fill in
    assert 'href="privacy?lang=kk"' in c.get("/delete?lang=kk").text
    assert 'href="privacy?lang=en"' in c.get("/terms?lang=en").text and c.get("/privacy?lang=xx").text.count('lang="ru"') == 1


def test_nick_and_photo(env):
    """A nickname and my own photo: lists show the nick, and anyone the short name beside it (the nick rule); my photo
    turns "Photo from Telegram" off, on again is Telegram's; a report takes the nick, photo and "about me" down."""
    import dataclasses
    import io
    from pathlib import Path

    from PIL import Image
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({94}))))
    pres, ali = login(c, 90, "pres"), login(c, 91, "ali")
    login(c, 94, "boss")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'NNN234', 0, 0)", (ali["id"],))
    P, B = tma(90, "Pres"), tma(94, "Boss")
    A = {"Authorization": "tma " + auth.sign_init_data({"id": 91, "first_name": "Ali", "photo_url": "https://t.me/i/userpic/320/ali.jpg"}, BOT)}
    real = c.get("/api/me", headers=A).json()["name"]
    for bad in ("x", "y" * 25, "@ali", "t.me/ali", "see https://x.kz"):
        assert c.patch("/api/me", headers=A, json={"nick": bad}).status_code == 400
    me = c.patch("/api/me", headers=A, json={"nick": "  Ali \u200b the   Great "}).json()
    assert (me["nick"], me["name"], me["avatar"], me["photo"]["telegram"]) == ("Ali the Great", "Ali the Great", "https://t.me/i/userpic/320/ali.jpg", True)
    c.post("/api/events/1/comments", headers=A, json={"body": "Hi"})
    who = c.get("/api/events/1/comments", headers=P).json()["items"][0]["person"]
    assert (who["name"], who["realName"]) == ("Ali the Great", real)  # everyone: the nick first, the short name beside it
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0)", (ali["id"],))
    lead = lambda h: next(x["person"] for x in c.get("/api/orgs/1", headers=h).json()["leaders"] if x["person"]["id"] == ali["id"])  # noqa: E731
    assert lead(tma(96, "Guest"))["name"] == "Ali the Great" and "realName" not in lead(tma(96, "Guest"))  # a visitor who isn't a student: the nick alone
    assert lead(P)["realName"] == real
    con.execute("DELETE FROM org_members WHERE user_id = ?", (ali["id"],))
    login(c, 95, "zed")
    stranger = c.get(f"/api/users/{ali['id']}", headers=tma(95, "Zed")).json()  # the nick rule: the lanyard shows the name to anyone
    assert (stranger["name"], stranger["nick"], stranger["realName"]) == ("Ali the Great", "Ali the Great", real)
    att = c.get("/api/events/1/attendees", headers=P).json()[0]
    assert att["person"]["nick"] == "Ali the Great" and "Ali" in att["fullName"] and "Great" not in att["fullName"]  # organizers: both
    assert c.get("/api/events/1/door", headers=P).json()[0]["person"]["realName"] == real
    assert c.patch("/api/me", headers=A, json={"avatarTg": False}).status_code == 400   # no photo of my own yet
    raw = io.BytesIO()
    Image.new("RGB", (300, 300), (30, 160, 90)).save(raw, "JPEG")
    me = c.post("/api/me/photo", headers=A, content=raw.getvalue()).json()
    own = me["photo"]["own"]
    assert me["avatar"] == own and own.startswith("media/") and me["photo"]["telegram"] is False
    assert (Path(cfg.db_path).parent / own).exists()                                     # served from /media/
    assert c.get(f"/api/users/{ali['id']}", headers=P).json()["avatar"] == own
    assert c.patch("/api/me", headers=A, json={"avatarTg": True}).json()["avatar"] == "https://t.me/i/userpic/320/ali.jpg"  # back
    assert c.patch("/api/me", headers=A, json={"avatarTg": False}).json()["avatar"] == own                                 # mine kept
    raw2 = io.BytesIO()
    Image.new("RGB", (300, 300), (200, 60, 60)).save(raw2, "JPEG")
    newer = c.post("/api/me/photo", headers=A, content=raw2.getvalue()).json()["photo"]["own"]
    assert newer != own and not (Path(cfg.db_path).parent / own).exists()               # the one it replaced left the disk
    gone = c.delete("/api/me/photo", headers=A).json()["photo"]                             # "Delete my photo": off the disk, Telegram's back
    assert gone["own"] is None and gone["telegram"] and not (Path(cfg.db_path).parent / newer).exists()
    newer = c.post("/api/me/photo", headers=A, content=raw2.getvalue()).json()["photo"]["own"]
    assert c.post("/api/reports", headers=A, json={"target": "user", "id": ali["id"], "reason": "spam"}).status_code == 404  # not myself
    assert c.post("/api/reports", headers=P, json={"target": "user", "id": ali["id"], "reason": "insult"}).status_code == 204
    q = c.get("/api/admin/reports", headers=B).json()
    assert [(x["target"], x["text"], x["where"]) for x in q] == [("user", "Ali the Great", {"kind": "person", "id": ali["id"]})]
    assert c.post(f"/api/admin/reports/user/{ali['id']}", headers=B, json={"remove": True}).status_code == 204
    assert (Path(cfg.db_path).parent / newer).exists()                                     # kept 30 days for an undo
    me = c.get("/api/me", headers=A).json()
    assert (me["nick"], me["name"], me["avatar"], me["photo"]) == (None, real, "https://t.me/i/userpic/320/ali.jpg",
                                                                   {"telegram": True, "tg": "https://t.me/i/userpic/320/ali.jpg", "own": None})
    assert c.post(f"/api/admin/taken-down/user/{ali['id']}/restore", headers=B).status_code == 204   # a wrong call undone
    me = c.get("/api/me", headers=A).json()
    assert (me["nick"], me["avatar"]) == ("Ali the Great", newer)
    assert c.post(f"/api/admin/taken-down/user/{ali['id']}/restore", headers=B).status_code == 404   # once
    assert c.post(f"/api/admin/reports/user/{ali['id']}", headers=B, json={"remove": True}).status_code == 409   # decided: no report open
    c.post("/api/reports", headers=P, json={"target": "user", "id": ali["id"], "reason": "insult"})
    c.post(f"/api/admin/reports/user/{ali['id']}", headers=B, json={"remove": True})                  # down again, kept again
    assert con.execute("SELECT COUNT(*) FROM takedowns WHERE user_id = ?", (ali["id"],)).fetchone()[0] == 1
    c.patch("/api/me", headers=A, json={"nick": "Ali again"})
    c.post("/api/me/photo", headers=A, content=raw.getvalue())
    assert delete_now(c, cfg, A) is None
    # deleting the account takes the kept copy at once: the nick and words, the photo off the disk
    assert not con.execute("SELECT 1 FROM takedowns WHERE user_id = ?", (ali["id"],)).fetchone() and not (Path(cfg.db_path).parent / newer).exists()
    u = con.execute("SELECT nick, avatar_tg, avatar_file_id FROM users WHERE id = ?", (ali["id"],)).fetchone()
    assert tuple(u) == (None, 1, None) and not con.execute("SELECT 1 FROM files WHERE kind = 'avatar' AND owner_id = ?", (ali["id"],)).fetchone()


def test_card_number_never_given_twice(env):
    """Card numbers: the last card's account purged, the next student still gets a new number."""
    c, cfg = env
    for tg in (31, 32):
        login(c, tg, f"s{tg}")
    con = db.connect(cfg.db_path)
    no = dict(con.execute("SELECT tg_id, card_no FROM users WHERE tg_id IN (31, 32)").fetchall())
    assert no[32] == no[31] + 1
    con.execute("DELETE FROM users WHERE tg_id = 32")
    login(c, 33, "s33")
    assert con.execute("SELECT card_no FROM users WHERE tg_id = 33").fetchone()[0] == no[32] + 1


def test_deletion_retries_when_the_journal_is_unwritable(env):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (uid,))
    path = Path(cfg.db_path).parent / "deletions.log"
    path.mkdir()  # simulate a storage failure without relying on OS permissions
    logic.delete_due(con)
    assert con.execute("SELECT delete_at FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0
    assert con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    path.rmdir()
    logic.delete_due(con)
    assert path.is_file() and not con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()


def test_deleted_stay_deleted_after_restore(env, monkeypatch, capsys):
    c, cfg = env
    now = int(time.time()) // 86400 * 86400 + 3600
    set_clock(monkeypatch, lambda: now)
    zhan = login(c, 22, "zhan")
    delete_now(c, cfg, tma(22))
    login(c, 22, "zhan")  # a new incarnation verified in the very same second
    ali = login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    home = Path(cfg.db_path).parent
    restored = home / "restored.db"
    con.execute("VACUUM INTO ?", (str(restored),))
    delete_now(c, cfg, tma(21))
    # Starting on the older file replays only the deletion absent from that snapshot.
    server.create(dataclasses.replace(cfg, db_path=str(restored)))
    rcon = db.connect(str(restored))
    assert [r[0] for r in rcon.execute("SELECT user_id FROM students")] == [zhan["id"]]
    assert not rcon.execute("SELECT 1 FROM schedule_classes WHERE user_id = ?", (ali["id"],)).fetchone()
    for k, v in (("BOT_TOKEN", BOT), ("TOKEN_KEY", "A" * 43 + "="), ("DB_PATH", str(restored))):
        monkeypatch.setenv(k, v)
    from kbtu import admin
    admin.main(["redelete", "--yes"])
    assert capsys.readouterr().out.strip() == "0 deleted again (2 in deletions.log)"


def test_restore_erases_account_moved_to_another_telegram(env, monkeypatch):
    from kbtu import admin
    c, cfg = env
    student = login(c, 21, "ali")
    guest = c.get("/api/me", headers=tma(23, "Guest")).json()
    con = db.connect(cfg.db_path)
    restored = Path(cfg.db_path).with_name("before-move.db")
    con.execute("VACUUM INTO ?", (str(restored),))
    monkeypatch.setattr(config, "load", lambda: cfg)
    admin.main(["move", "21", "23", "--yes"])
    delete_now(c, cfg, tma(23))
    server.create(dataclasses.replace(cfg, db_path=str(restored)))
    old = db.connect(str(restored))
    assert not old.execute("SELECT 1 FROM students WHERE user_id = ?", (student["id"],)).fetchone()
    assert old.execute("SELECT tg_first_name FROM users WHERE id = ?", (guest["id"],)).fetchone()[0] == "Guest"


def test_replay_after_crash_before_erasure_commit(env, monkeypatch):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET delete_at = 0 WHERE id = ?", (uid,))
    write = logic.account._deletion_log

    def interrupted(*args):
        write(*args)
        raise OSError("interrupted before commit")

    monkeypatch.setattr(logic.account, "_deletion_log", interrupted)
    logic.delete_due(con)
    assert con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    server.create(cfg)
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    path = Path(cfg.db_path).with_name("deletions.log")
    path.write_text("")  # a stale journal alongside a database with a recent checkpoint
    with pytest.raises(RuntimeError, match="latest deletions.log"):
        server.create(cfg)


def test_legacy_deletion_day_requires_evidence(env):
    c, cfg = env
    uid = login(c, 21, "ali")["id"]
    home = Path(cfg.db_path).parent
    salt = "a" * 32
    h = hashlib.sha256(f"{salt}:21".encode()).hexdigest()[:32]
    day = logic.now() // 86400 * 86400
    (home / "deletions.salt").write_text(salt)
    (home / "deletions.log").write_text(f"{day} {h}\n")
    with pytest.raises(RuntimeError, match="same-day verification"):
        server.create(cfg)
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET verified_at = ? WHERE user_id = ?", (day - 10, uid))
    snapshot = home / "before-legacy.db"
    con.execute("VACUUM INTO ?", (str(snapshot),))
    server.create(cfg)
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    login(c, 21, "ali")
    delete_now(c, cfg, tma(21))
    # The same snapshot can predate both a legacy and a new-format erasure of this row.
    restored = db.connect(str(snapshot))
    assert logic.replay_deletions(restored) == (1, 2)
    assert not restored.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()


def test_forgetting(env, monkeypatch):
    """H2 minimisation: the bot's copies of messages lose their words after 30 days (the row keeps its key, so it
    never goes twice); DMP's registry searches lose the typed text; a migration's .bak goes after 14 days."""
    c, cfg = env
    ali = login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    t = int(time.time())
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after, sent_at) VALUES (?, 'x', 'old', '{\"t\": 1}', ?, ?), (?, 'x', 'new', '{\"t\": 1}', ?, ?)",
                (ali["id"], t - 31 * 86400, t - 31 * 86400, ali["id"], t, t))
    con.execute("INSERT INTO audit_log (actor_id, action, target, data, at) VALUES (?, 'registry_search', 'registry', '{\"q\": \"Ali\"}', ?)", (ali["id"], t - 31 * 86400))
    midnight = (t + 5 * 3600) // 86400 * 86400 - 5 * 3600
    set_clock(monkeypatch, lambda: midnight + 600)
    logic.stats_day(con)
    assert [tuple(r) for r in con.execute("SELECT ref, payload FROM bot_outbox WHERE kind = 'x' ORDER BY ref")] == [("new", '{"t": 1}'), ("old", "{}")]
    assert con.execute("SELECT data FROM audit_log WHERE action = 'registry_search'").fetchone()[0] == "{}"
    db_path = Path(cfg.db_path).resolve()
    old, new = db_path.with_name(db_path.name + ".v1-1.bak"), db_path.with_name(db_path.name + ".v2-2.bak")
    for f, age in ((old, 15), (new, 1)):
        f.write_bytes(b"x")
        os.utime(f, (t - age * 86400, t - age * 86400))
    chores.backup_day(cfg, con)
    assert not old.exists() and new.exists()


def test_app_team(env):
    """The app's team: the owner alone gives or takes the admin role; an admin gives the moderator role
    and bans, never touching the owner, himself or another admin; a moderator only filters content; a ban needs a
    reason, drops the role, shows him why, and the bot stops writing; the owner reads the audit log."""
    import httpx
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({30}))))
    who = lambda uid, username: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": username.title(), "username": username}, BOT)}
    O, A, M, U, X = who(30, "owner_x"), who(31, "admin_x"), who(32, "mod_x"), who(33, "user_x"), who(34, "other_x")
    ids = {k: c.get("/api/me", headers=h).json()["id"] for k, h in dict(O=O, A=A, M=M, U=U, X=X).items()}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["O"],))
    role = lambda h, k, r: c.post("/api/admin/staff", headers=h, json={"userId": ids[k], "role": r})
    ban = lambda h, k, on, reason=None: c.post("/api/admin/ban", headers=h, json={"userId": ids[k], "on": on, "reason": reason})

    assert c.get("/api/admin/staff", headers=U).status_code == 403
    assert role(O, "A", "admin").status_code == 200                       # the owner makes an admin; it survives the next sign-in
    assert c.get("/api/me", headers=A).json()["role"] == "admin"
    assert role(A, "X", "admin").status_code == 403                       # an admin can't make admins
    assert role(A, "M", "moderator").status_code == 403                   # nor moderators: roles are the owner's alone (Nov 3)
    assert role(O, "M", "moderator").json()["team"][-1]["person"]["id"] == ids["M"]
    assert role(A, "O", "user").status_code == 403 and ban(A, "O", True, "nope").status_code == 403   # nobody touches the owner
    assert role(A, "A", "user").status_code == 403                        # nor himself
    assert role(M, "U", "moderator").status_code == 403 and c.get("/api/admin/staff", headers=M).status_code == 403
    assert c.get("/api/admin/reports", headers=M).status_code == 200     # the moderator's own work
    assert c.get("/api/admin/stats", headers=M).status_code == 403
    assert not [x for x in c.get("/api/admin/inbox", headers=M).json()["items"] if x["kind"] == "capp"]   # clubs are the admin's
    assert c.post("/api/admin/feature", headers=M, json={"postId": 1, "days": 1}).status_code == 403
    assert c.get("/api/me", headers=M).json()["counters"]["inbox"] == 0
    assert ban(A, "X", True, "testing an admin ban").status_code == 200 and ban(A, "X", False).status_code == 200   # an admin bans users
    assert c.post("/api/admin/ban", headers=O, json={"userId": ids["X"], "on": 1, "reason": "nope"}).status_code == 400   # a real bool
    assert ban(O, "X", True, "x" * 301).status_code == 400
    assert logic.one(con, "SELECT ban_reason FROM users WHERE id = ?", ids["X"])["ban_reason"] is None   # unban cleared it
    assert role(O, "A", "moderator").status_code == 200 and role(O, "A", "admin").status_code == 200
    assert ban(A, "X", True, "nope") .status_code == 200 and role(O, "X", "user").status_code == 200 and ban(O, "X", False).status_code == 200
    assert role(O, "X", "admin").status_code == 200 and ban(A, "X", True, "nope").status_code == 403   # an admin can't ban an admin
    assert role(O, "X", "user").status_code == 200
    assert role(O, "A", "moderator").status_code == 200 and ban(O, "A", True, "spam links").status_code == 200   # the owner may
    assert role(O, "A", "admin").status_code == 409                       # banned: no role back until unbanned

    assert ban(O, "U", True).status_code == 400                           # a reason is required
    assert ban(O, "M", True, "  insults   in chats ").json()["banned"][0]["banReason"] == "insults in chats"
    r = c.get("/api/me", headers=M)
    assert r.status_code == 403 and r.json()["message"] == "banned" and r.json()["reason"] == "insults in chats" and r.json()["contact"] == "owner_x"
    assert logic.one(con, "SELECT role FROM users WHERE id = ?", ids["M"])["role"] == "user"
    con.execute("UPDATE users SET can_dm = 1")
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'new_event', 'event:1', 0)", (ids["M"],))
    sent = []

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda q: sent.append(q) or httpx.Response(200, json={"ok": True, "result": {}}))) as http:
            await outbox.send_due(cfg, http)
    asyncio.run(go())
    # The bot skips the banned user's chat.
    assert not [q for q in sent if json.loads(q.content).get("chat_id") == 32]
    assert logic.one(con, "SELECT error FROM bot_outbox WHERE user_id = ?", ids["M"])["error"] == "banned"
    assert ban(O, "M", False).status_code == 200 and c.get("/api/me", headers=M).status_code == 200

    log = c.get("/api/admin/audit", headers=O).json()
    assert [a["action"] for a in log][:3] == ["unban", "ban", "ban"] and log[1]["data"] == {"reason": "insults in chats"}
    assert c.get("/api/admin/audit", headers=A).status_code == 403      # the owner's only (A is banned anyway)
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ids["A"],))
    assert role(O, "A", "admin").status_code == 200 and c.get("/api/admin/audit", headers=A).status_code == 403

    # an ADMIN_TG_IDS admin banned by the owner stays a plain user while banned (the ban outranks the env)
    con.execute("UPDATE users SET is_founder = 0 WHERE id = ?", (ids["O"],))
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids["A"],))
    assert ban(A, "O", True, "env admin test").status_code == 200
    assert c.get("/api/me", headers=O).status_code == 403 and logic.one(con, "SELECT role FROM users WHERE id = ?", ids["O"])["role"] == "user"
    assert ban(A, "O", False).status_code == 200 and c.get("/api/me", headers=O).json()["role"] == "admin"   # back at the next sign-in


def test_profile_privacy(env, monkeypatch):
    """Audit M2: a stranger sees the card, bio and achievements but not clubs, past roles, event badges or a club's
    badge that came by itself, and at most PROFILES_A_DAY profiles a day (the same one again is free); friends,
    clubmates see the full profile except achievement dates and are never counted."""
    c, cfg = env
    ann, bob, cat, dan, eve = (login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat"), (13, "dan"), (14, "eve")))
    con = db.connect(cfg.db_path)
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0),
        (2, 'studex', 'club', 'StudEx', 'SE', 'star_3d', 1, 0), (3, 'chess', 'club', 'Chess', 'CH', 'crown_3d', 1, 0)""")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0), (1, ?, 'member', 0), (2, ?, 'member', 0)", (ann, cat, ann))
    con.execute("INSERT INTO org_history (user_id, org_id, role, since, until) VALUES (?, 3, 'head', 0, 5 * 86400)", (ann,))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, badge_name, created_at, updated_at)
        VALUES (9, 1, 'published', 'Hack', '305', 1000, 'laptop_3d', '#3B6BFF', 'Hacker', 0, 0)""")
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
        VALUES (9, ?, 'going', 'T9', 0, 0, 1000)""", (ann,))
    con.execute("UPDATE users SET showcase = 'b9', tg_username = 'ann_tg' WHERE id = ?", (ann,))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ann, bob), max(ann, bob)))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (eve,))
    full = lambda tg: c.get(f"/api/users/{ann}", headers=tma(tg)).json()  # noqa: E731
    for tg in (10, 11, 12):  # herself, a friend, a clubmate
        p = full(tg)
        assert {m["org"]["id"] for m in p["clubs"]} == {1, 2} and [h["org"]["id"] for h in p["past"]] == [3] and "limited" not in p
        assert [b["eventId"] for b in p["awards"]["badges"]] == [9] and p["shelf"] == ["b9"] and p["skin"] == 2
    for gone in ("hidden", "archived"):  # a club taken down or archived leaves every profile (owner, Nov 13)
        con.execute("UPDATE orgs SET status = ? WHERE id = 2", (gone,))
        assert {m["org"]["id"] for m in full(11)["clubs"]} == {1}
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 2")
    p = full(13)
    assert p["clubs"] == [] and p["past"] == [] and p["awards"]["badges"] == [] and p["shelf"] == [] and p["limited"] is True
    assert p["skin"] is None and p["username"] is None and p["name"] and p["course"] == 2               # StudEx's badge came by itself
    con.execute("UPDATE users SET skin_pick = 'org', skin_org = 2 WHERE id = ?", (ann,))
    assert full(13)["skin"] == 2                                                                       # picked to be shown: shows
    con.execute("INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'first_in', 1, 1000)", (ann,))
    con.execute("INSERT INTO org_flags (org_id, guests_private) VALUES (1, 1)")
    con.execute("UPDATE users SET showcase = 'first_in' WHERE id = ?", (ann,))
    own = full(10)
    assert next(a for a in own["awards"]["achievements"] if a["code"] == "first_in")["at"] == 1000
    assert own["showcase"][0]["at"] == 1000 and [b["eventId"] for b in own["awards"]["badges"]] == [9]
    for tg in (11, 12, 13, 14):  # even friends, clubmates and staff cannot date a private check-in
        p = full(tg)
        assert all(a["at"] is None for a in p["awards"]["achievements"])
        assert [a["code"] for a in p["showcase"]] == ["first_in"] and p["showcase"][0]["at"] is None
        assert p["awards"]["badges"] == []
    for role in ("moderator", "admin"):
        con.execute("UPDATE users SET role = ? WHERE id = ?", (role, eve))
        staff = full(14)
        assert staff["limited"] and not staff["clubs"] and not staff["past"] and not staff["awards"]["badges"]
    assert c.get("/api/users/999999", headers=tma(13)).status_code == 404                             # nobody there: not counted
    assert set(map(tuple, con.execute("SELECT viewer_id, user_id FROM profile_views"))) == {(dan, ann), (eve, ann)}
    monkeypatch.setattr(logic.profiles, "PROFILES_A_DAY", 2)
    assert c.get(f"/api/users/{ann}", headers=tma(13)).status_code == 200                              # the same one again: free
    assert c.get(f"/api/users/{bob}", headers=tma(13)).status_code == 200
    assert c.get(f"/api/users/{cat}", headers=tma(13)).json()["error"] == "rate_limited"
    assert c.get(f"/api/users/{ann}", headers=tma(12)).status_code == 200                              # a clubmate is never counted
    later = ((int(time.time()) + 5 * 3600) // 86400 + 2) * 86400 - 4 * 3600
    set_clock(monkeypatch, lambda: later)                                                   # two days on, 01:00 Almaty
    assert c.get(f"/api/users/{cat}", headers=tma(13)).status_code == 200
    logic.stats_day(con)                                                                    # the night's job clears old days
    assert con.execute("SELECT COUNT(*) FROM profile_views WHERE day < ?", ((later + 5 * 3600) // 86400 - 1,)).fetchone()[0] == 0
    c.get(f"/api/users/{dan}", headers=tma(10))                                                        # dan is someone's stranger too
    logic.account.delete_me(con, logic.Viewer(dan, "user", True))
    assert con.execute("SELECT COUNT(*) FROM profile_views WHERE ? IN (viewer_id, user_id)", (dan,)).fetchone()[0] == 0


@pytest.mark.parametrize("blocker", (10, 11))
def test_blocked_clubmate_profile(env, blocker):
    """A block in either direction removes clubmate access, including the Telegram username."""
    c, cfg = env
    ann, bob = login(c, 10, "ann")["id"], login(c, 11, "bob")["id"]
    con = db.connect(cfg.db_path)
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at)
        VALUES (1, 'studex', 'club', 'StudEx', 'SE', 'star_3d', 1, 0)""")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0), (1, ?, 'member', 0)", (ann, bob))
    con.execute("INSERT INTO org_history (user_id, org_id, role, since, until) VALUES (?, 1, 'head', 0, 86400)", (ann,))
    con.execute("""INSERT INTO events (id, org_id, status, title, starts_at, badge_name, created_at, updated_at)
        VALUES (1, 1, 'published', 'Talk', 1000, 'Guest', 0, 0)""")
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
        VALUES (1, ?, 'going', 'T1', 0, 0, 1000)""", (ann,))
    con.execute("UPDATE users SET tg_username = 'ann_tg', showcase = 'b1' WHERE id = ?", (ann,))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ann, bob), max(ann, bob)))
    headers = {10: {"Authorization": "tma " + auth.sign_init_data({"id": 10, "first_name": "Ann", "username": "ann_tg"}, BOT)}, 11: tma(11)}
    profile = lambda tg=11: c.get(f"/api/users/{ann}", headers=headers[tg]).json()  # noqa: E731
    before = profile()
    assert "limited" not in before and before["username"] == "ann_tg"
    assert before["clubs"] and before["past"] and before["awards"]["badges"] and before["shelf"] == ["b1"] and before["skin"] == 1
    target = bob if blocker == 10 else ann
    assert c.post("/api/forum/blocks", headers=headers[blocker], json={"user": target, "on": True}).status_code == 204
    p = profile()
    assert p["limited"] and p["closed"] and p["friendship"] == "none" and p["username"] is None
    assert p["clubs"] == [] and p["past"] == [] and p["awards"]["badges"] == [] and p["shelf"] == [] and p["skin"] is None
    assert p.get("blocked", False) == (blocker == 11)
    assert "limited" not in profile(10) and profile(10)["clubs"]  # the owner's view stays full
    assert [tuple(r) for r in con.execute("SELECT viewer_id, user_id FROM profile_views")] == [(bob, ann)]
    assert c.post("/api/forum/blocks", headers=headers[blocker], json={"user": target, "on": False}).status_code == 204
    assert "limited" not in profile() and profile()["username"] == "ann_tg"


@pytest.mark.parametrize("status", ("hidden", "archived"))
@pytest.mark.parametrize("lookup", (False, True), ids=("profile", "username"))
def test_inactive_clubmates_profile_limit(env, monkeypatch, status, lookup):
    """An inactive shared club grants neither private profile access nor an exemption from the lookup limit."""
    c, cfg = env
    ann, bob, cat = (login(c, tg, name)["id"] for tg, name in ((10, "ann"), (11, "bob"), (12, "cat")))
    con = db.connect(cfg.db_path)
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at)
        VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)""")
    for uid, name in ((ann, "ann_tg"), (bob, "bob_tg"), (cat, "cat_tg")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (uid,))
        con.execute("UPDATE users SET tg_username = ? WHERE id = ?", (name, uid))
    get = lambda uid, name: c.get(f"/api/friends/find?username={name}" if lookup else f"/api/users/{uid}", headers=tma(11))  # noqa: E731
    assert get(ann, "ann_tg").status_code == 200
    assert not con.execute("SELECT 1 FROM profile_views").fetchone()
    if not lookup:
        p = get(ann, "ann_tg").json()
        assert "limited" not in p and p["username"] == "ann_tg" and p["clubs"]
    con.execute("UPDATE orgs SET status = ? WHERE id = 1", (status,))
    monkeypatch.setattr(logic.profiles, "PROFILES_A_DAY", 1)
    r = get(ann, "ann_tg")
    assert r.status_code == 200
    if not lookup:
        assert r.json()["limited"] and r.json()["username"] is None and r.json()["clubs"] == []
    assert [tuple(r) for r in con.execute("SELECT viewer_id, user_id FROM profile_views")] == [(bob, ann)]
    assert get(ann, "ann_tg").status_code == 200  # reopening the same profile is still free
    assert get(cat, "cat_tg").json()["error"] == "rate_limited"
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 1")
    assert get(cat, "cat_tg").status_code == 200  # active clubmates still bypass the cap


def test_report_limit(env, monkeypatch):
    """The day's limit counts new reports only: updating one still waiting is free (the one report sheet)."""
    c, cfg = env
    ann, bob, cat = (login(c, uid, n)["id"] for uid, n in ((10, "ann"), (11, "bob"), (12, "cat")))
    monkeypatch.setattr(logic.moderation, "REPORTS_A_DAY", 1)
    rep = lambda uid, note=None: c.post("/api/reports", headers=tma(10), json={"target": "user", "id": uid, "reason": "spam", "note": note})  # noqa: E731
    assert rep(bob).status_code == 204 and rep(cat).json()["error"] == "rate_limited"
    assert rep(bob, "Fake name").status_code == 204                                                    # the open one, updated: free
    con = db.connect(cfg.db_path)
    assert [tuple(r) for r in con.execute("SELECT target_id, note FROM reports")] == [(bob, "Fake name")]
    logic.account.delete_me(con, logic.Viewer(ann, "user", True))                                              # her words go with her data
    assert [tuple(r) for r in con.execute("SELECT reporter_id, target_id, note FROM reports")] == [(None, bob, None)]


def test_staff_badge_and_chat_order(env):
    """A9: everyone sees who is the app's moderator or admin; A8: the chats directory lists the biggest first."""
    c, cfg = env
    ali, mod = login(c, 61, "ali"), login(c, 62, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    A = tma(61, "Ali")
    assert (c.get(f"/api/users/{mod['id']}", headers=A).json()["staff"], c.get(f"/api/users/{ali['id']}", headers=A).json()["staff"]) == ("moderator", None)
    for title, n, sort in (("Small", 10, 0), ("Big", 900, 5), ("Unknown", None, 0)):
        con.execute("INSERT INTO chats (title, kind, url, members, sort, status, created_at) VALUES (?, 'group', 'https://t.me/x', ?, ?, 'live', 0)", (title, n, sort))
    assert [x["title"] for x in c.get("/api/chats", headers=A).json()["all"]] == ["Big", "Small", "Unknown"]


def test_dm_on(env):
    """Telegram's "allow messages" from inside the app: the bot may write at once, and the event just
    signed up for gets its confirmation with the ticket; nothing for an event I'm not going to."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    start = int(time.time()) + 86400
    for i in (1, 2):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, created_by, created_at, updated_at)
            VALUES (?, 1, 'published', 'Talk', '305', ?, ?, 'laptop_3d', '#3B6BFF', '#2C50BF', ?, 0, 0)""", (i, start, start + 7200, pres["id"]))
    A = tma(21, "Ali")
    con.execute("UPDATE users SET can_dm = 0 WHERE id = ?", (ali["id"],))
    assert c.get("/api/me", headers=A).json()["canDm"] is False
    assert c.post("/api/events/1/registration", headers=A, json={}).json()["my"]["status"] == "going"
    assert c.post("/api/me/dm", headers=A, json={"event": 1}).json()["canDm"] is True
    c.post("/api/me/dm", headers=A, json={"event": 2})   # not going there: no message
    c.post("/api/me/dm", headers=A, json={"event": 1})   # twice: one message
    sent = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'going_ok'").fetchall()
    assert [s["ref"] for s in sent] == ["event:1"] and outbox._render(con, sent[0])[2] == "tk_1"
    assert c.post("/api/me/dm", headers=tma(30, "Guest"), json={}).status_code == 200   # a guest too: the bot may write


def test_phone_asked_at_signup(env):
    """No up-front "My data" step. An event that needs a phone asks for it at sign-up and keeps it, so the next
    such sign-up is one tap; Settings changes or deletes it, and then it's asked again."""
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = int(time.time()) + 3600
    eids = []
    for title in ("Trip", "Hike"):
        ev = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, "title": title, "place": "305", "startsAt": start, "emoji": "laptop_3d",
                                                                  "color": "#3B6BFF", "needsPhone": True}).json()
        assert ev["needsPhone"] is True
        c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
        eids.append(ev["id"])
    go = lambda eid, **b: c.post(f"/api/events/{eid}/registration", headers=tma(10), json=b)  # noqa: E731
    assert ali["student"]["phone"] is None
    r = go(eids[0])                                                       # none kept: asked, no seat taken
    assert r.status_code == 400 and r.json()["message"] == "phone" and c.get(f"/api/events/{eids[0]}", headers=tma(10)).json()["my"] is None
    assert go(eids[0], phone="12345").json()["message"] == "phone"
    assert go(eids[0], phone="8 (701) 234-56-78").json()["my"]["status"] == "going"
    assert c.get("/api/me", headers=tma(10)).json()["student"]["phone"] == "+77012345678"
    assert go(eids[1]).json()["my"]["status"] == "going"                 # kept: one tap
    # a club whose event never asked doesn't get the kept phone in its guest list
    plain = c.post("/api/orgs/1/events", headers=tma(20), json={"seats": None, "title": "Talk", "place": "305", "startsAt": start, "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{plain['id']}/publish", headers=tma(20))
    go(plain["id"])
    v = logic.Viewer(pres["id"], "user", True)
    assert [r["phone"] for r in logic.attendees_export(con, v, plain["id"])[1]] == [None]
    assert [r["phone"] for r in logic.attendees_export(con, v, eids[0])[1]] == ["+77012345678"]
    assert c.patch("/api/me", headers=tma(10), json={"phone": "nope"}).status_code == 400
    assert c.patch("/api/me", headers=tma(10), json={"phone": "+7 702 000 00 00"}).json()["student"]["phone"] == "+77020000000"
    assert c.patch("/api/me", headers=tma(10), json={"phone": None}).json()["student"]["phone"] is None
    c.delete(f"/api/events/{eids[1]}/registration", headers=tma(10))
    assert go(eids[1]).json()["message"] == "phone"                      # deleted: asked again


def test_one_policy_whatever_the_flags(env):
    """One policy, one consent version: no switch changes the version asked or the page served."""
    import dataclasses
    c, cfg = env
    login(c, 90, "stu")
    assert c.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT == "2026-11-unified1"
    on = TestClient(server.create(dataclasses.replace(cfg, forum=True, board="all", appeals="1")))
    assert on.get("/api/me", headers=tma(90)).json()["consentNow"] == logic.CONSENT
    for doc in ("privacy", "terms"):
        assert on.get(f"/{doc}").text == c.get(f"/{doc}").text
    assert on.post("/api/me/consent", headers=tma(90), json={"version": logic.CONSENT}).json()["student"]["consent"] == logic.CONSENT


def test_old_versions_asked_again_marks_not(env):
    """Whatever a student agreed to before the unified policy, they are asked once more; a staff or admin mark is not
    a version: never asked, never overwritten."""
    c, cfg = env
    login(c, 90, "stu")
    con = db.connect(cfg.db_path)
    for old in ("1", "2026-10-v3", "2026-11-v13", "2026-11-v16+tgc1+fch4+chs1+ai1", "2026-11-v13+vol1"):
        con.execute("UPDATE students SET consent_version = ?", (old,))
        me = c.get("/api/me", headers=tma(90)).json()
        assert me["student"]["consent"] == old != me["consentNow"] == logic.CONSENT          # the app's gate: these differ
        assert not logic.agreed(con.execute("SELECT consent_version FROM students").fetchone())
        assert c.post("/api/me/consent", headers=tma(90), json={"version": old}).status_code == 400
    assert c.post("/api/me/consent", headers=tma(90), json={"version": logic.CONSENT}).json()["student"]["consent"] == logic.CONSENT
    assert logic.agreed(con.execute("SELECT consent_version FROM students").fetchone())
    for mark in ("staff", "admin"):  # the app's gate skips these two (App.svelte)
        con.execute("UPDATE students SET consent_version = ?", (mark,))
        assert c.post("/api/me/consent", headers=tma(90), json={"version": logic.CONSENT}).json()["student"]["consent"] == mark
    assert logic.agreed({"consent_version": "admin"})
    con.close()


def test_support_contacts(env):
    """Me's "Support & ideas": the creator first, then the main admin, by their Telegram usernames; a banned one drops."""
    c, cfg = env
    a, b = login(c, 30, "relson69"), login(c, 31, "sowers")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET tg_username = 'Relson69' WHERE id = ?", (a["id"],))
    con.execute("UPDATE users SET tg_username = 'Sowers', is_founder = 1 WHERE id = ?", (b["id"],))
    assert [p["username"] for p in logic.account.support(con)] == ["Sowers", "Relson69"]
    assert "support" in c.get("/api/me", headers=tma(32)).json()
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (a["id"],))
    assert [p["username"] for p in logic.account.support(con)] == ["Sowers"]
    con.close()


def test_erasure_removes_all_microsoft_claims_for_owner(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann, bob = (login(c, tg, name)["id"] for tg, name in ((91, "ann"), (92, "bob")))
    who = {"oid": "directory-account", "email": "test@example.org", "first": "Test", "last": "Account"}
    tokens = [logic.ms_hold(con, ann, who) for _ in range(2)]
    logic.ms_release(con, tokens[0])
    other = logic.ms_hold(con, bob, who)
    logic.account.delete_me(con, logic.Viewer(ann, "user", True))
    for token in ("", *tokens):
        assert c.post("/api/ms/claim", headers=tma(91), json={"claim": token}).status_code == 403
    assert [r[0] for r in con.execute("SELECT key FROM meta WHERE key GLOB 'ms_claim:*'")] == [f"ms_claim:{other}"]
