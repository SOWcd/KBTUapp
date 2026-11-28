"""Screens on the real server with made-up people (the in-browser demo went on Oct 11: its copy of the server's rules
drifted and doubled every feature). Seeds a fresh database with a few made-up students and an official club with a
paid event, starts the real server on it with the postman off, and prints a link per person that opens the app as
them: Telegram's initData rides in the link's hash, signed with a made-up bot token, the way Telegram passes it, so
the real telegram-web-app.js reads it. Nothing leaves this machine.

    cd server && .venv/bin/python tools/qa.py [--port 8790] [--db /tmp/qa.db] [--fake-ai] [--big] [--clubs] [--now 1795582800]

--now sets the clock (the seed's and the server's) to that moment, running on from there: the same "in 2 days, 18:30"
on every run, for the web's screen snapshots (web/e2e/snap.spec.ts).

OCR of receipts runs if tesseract with the rus and kaz models is installed (TESSDATA_PREFIX for a local copy)."""
from __future__ import annotations

import argparse
import base64
import colorsys
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402

from kbtu import auth, db, logic, media  # noqa: E402

BOT = "1:" + "qa" * 18
SERVER = Path(__file__).resolve().parents[1]
PEOPLE = [(1, 1001, "Dana", "Seitova"), (2, 1002, "Ali", "Nurlanov"), (3, 1003, "Bota", "Askarova")]  # Dana runs the club


def seed(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    db.init(path)
    con = db.connect(path)
    now, day = int(time.time()), 86400
    for uid, tg, first, last in PEOPLE:
        con.execute("""INSERT INTO users (id, tg_id, tg_username, tg_first_name, tg_last_name, lang, can_dm, created_at, seen_at, qr_code, card_no)
            VALUES (?, ?, ?, ?, ?, 'ru', 1, ?, ?, ?, ?)""", (uid, tg, first.lower(), first, last, now - 30 * day, now, f"QAQAQAQAQ{'ABC'[uid - 1]}", uid))  # a badge code as the app makes them (10 of A-Z2-7: core.PROFILE_QR), so the door can scan it
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, email, course, school, consent_version, consent_at, verified_at, synced_at)
            VALUES (?, ?, ?, ?, ?, 2, 'SITE', 'qa', ?, ?, ?)""", (uid, f"24B{100000 + uid}", first, last, f"{first.lower()}@kbtu.kz", now, now, now))
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, description, emoji, official, created_at)
        VALUES (1, 'openmic', 'club', 'Open Mic Club', 'OM', 'Stand-up and music nights.', 'microphone_3d', 1, ?)""", (now - 60 * day,))
    for rn, color, lv in logic.OFFICIAL_ROLES:  # what create_org makes
        con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (1, ?, ?, ?, 1, ?)", (rn, color, lv, now))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at, role_id) VALUES (1, 1, 'vice', ?, (SELECT id FROM org_roles WHERE org_id = 1 AND level = 'vice'))", (now - 50 * day,))
    start = (now // day + 2) * day + 13 * 3600 + 1800  # the day after tomorrow, 18:30 in Almaty
    con.execute("""INSERT INTO events (id, org_id, status, title, description, place, starts_at, ends_at, emoji, color, tint, seats, price, pay_to_name, pay_phone,
            created_by, created_at, updated_at, published_at) VALUES (1, 1, 'published', 'Open Mic: stand-up and music',
            'Stand-up, songs and poetry by students. Come to listen, or take five minutes on stage: sign up at the door.', 'Atrium', ?, ?, 'microphone_3d',
            '#7A4A22', '#5C3719', 80, 2000, 'Arman A.', '+77071234567', 1, ?, ?, ?)""", (start, start + 3 * 3600, now - day, now - day, now - day))
    # Dana's friends go to a free event: her Friends page has its "where friends are going" cards
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (1, 2, ?), (1, 3, ?)", (now - 20 * day, now - 10 * day))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, created_by, created_at,
            updated_at, published_at) VALUES (2, 1, 'published', 'Board games night', 'Room 305', ?, ?, 'popcorn_3d', '#2B4C9A', '#1E3770', 40, 1,
            ?, ?, ?)""", (start - day, start - day + 3 * 3600, now - day, now - day, now - day))
    for uid in (2, 3):
        con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at)
            VALUES (2, ?, 'going', ?, ?, ?)""", (uid, f"QA-T{uid}", now, now))
    # appeals to SG (APPEALS): the third person has SG's queue; an anonymous appeal overdue, a named one answered
    con.execute("INSERT INTO appeal_staff (user_id, at) VALUES (3, ?)", (now,))
    con.execute("INSERT INTO help_staff (user_id, at) VALUES (3, ?)", (now,))  # and the help desk (ASK)
    for aid, uid, topic, body, anon, at, status, answer in (
            (1, 2, "dorm", "\u0412 \u043e\u0431\u0449\u0435\u0436\u0438\u0442\u0438\u0438 \u2116 2 \u043d\u0435\u0442 \u0433\u043e\u0440\u044f\u0447\u0435\u0439 \u0432\u043e\u0434\u044b \u0441 \u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a\u0430.", 1, now - 9 * day, "work", None),
            (2, 1, "food", "\u0412 \u0441\u0442\u043e\u043b\u043e\u0432\u043e\u0439 \u043d\u0430 2 \u044d\u0442\u0430\u0436\u0435 \u043d\u0435\u0442 \u0432\u0435\u0433\u0435\u0442\u0430\u0440\u0438\u0430\u043d\u0441\u043a\u0438\u0445 \u0431\u043b\u044e\u0434.", 0, now - 2 * day, "closed", "\u0421\u043f\u0430\u0441\u0438\u0431\u043e! \u0421 \u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a\u0430 \u0431\u0443\u0434\u0435\u0442 \u043e\u0432\u043e\u0449\u043d\u043e\u0439 \u0441\u0443\u043f.")):
        con.execute("""INSERT INTO appeals (id, topic, body, anon, status, answer, created_at, due_at, answered_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (aid, topic, body, anon, status, answer, at, logic.appeals.due(at),
                                                   at + day if answer else None, at + day if status == "closed" else None))
        con.execute("INSERT INTO appeal_authors (appeal_id, user_id) VALUES (?, ?)", (aid, uid))
    # Ali has today's timetable (made up), so the List's live stack shows its class card: one on now, two after it
    t0 = time.gmtime(now + 5 * 3600)  # Almaty, UTC+5
    base = min(max(t0.tm_hour * 60 + t0.tm_min, 20), 24 * 60 - 180)  # late at night the day still fits (classes end 23:59 at most)
    hm = lambda m: f"{(base + m) // 60:02d}:{(base + m) % 60:02d}"
    for b, e, subj, kind, room, who in ((-20, 30, "Algorithms and Data Structures", "practice", "403", "Kim D."),
                                       (40, 90, "Physics", "lab", "162a", None), (120, 170, "Linear Algebra", "lecture", "256", None)):
        con.execute("INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, kind, room, teacher) VALUES (2, ?, ?, ?, ?, ?, ?, ?)",
                    (t0.tm_wday + 1, hm(b), hm(e), subj, kind, room, who))
    # yesterday's event with an album: Ali and Bota came and added 22 shots between them, wide, tall and square, so the
    # grid scrolls (pictures drawn here)
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, created_by, created_at,
            updated_at, published_at) VALUES (3, 1, 'published', 'Karaoke night', 'Atrium', ?, ?, 'microphone_3d', '#7A2253', '#5C193E', 60, 1,
            ?, ?, ?)""", (now - day - 3 * 3600, now - day, now - 3 * day, now - 3 * day, now - 3 * day))
    shots = [(2 if n % 3 else 3, tuple(int(c * 255) for c in colorsys.hsv_to_rgb(n / 22, 0.65, 0.9)), ((1200, 900), (900, 1200), (1000, 1000))[n % 3]) for n in range(22)]
    for n, (uid, rgb, size) in enumerate(shots):
        con.execute("""INSERT OR IGNORE INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
            VALUES (3, ?, 'going', ?, ?, ?, ?)""", (uid, f"QA-K{uid}", now - 2 * day, now - 2 * day, now - day - 3 * 3600))
        im = Image.linear_gradient("L").resize(size).convert("RGB")
        im = Image.composite(Image.new("RGB", im.size, rgb), Image.new("RGB", im.size, (20, 20, 30)), Image.linear_gradient("L").resize(im.size))
        f = media.store(im, f"qa-photo-{n}".encode(), Path(path).resolve().parent / "media")
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (f["sha256"], f["bytes"], f["width"], f["height"], f["path"], uid, now, f["color"])).lastrowid
        con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (3, ?, ?, ?)", (fid, n + 1, uid))
    # the Gallery's own (GALLERY on below): KBTU photos Dana and Bota posted over the last days, most with a place
    for n in range(8):
        uid, rgb = (1, 3)[n % 2], tuple(int(c * 255) for c in colorsys.hsv_to_rgb(0.55 + n / 12, 0.5, 0.85))
        im = Image.composite(Image.new("RGB", (1200, 900), rgb), Image.new("RGB", (1200, 900), (240, 240, 245)), Image.radial_gradient("L").resize((1200, 900)))
        f = media.store(im, f"qa-gallery-{n}".encode(), Path(path).resolve().parent / "media")
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (f["sha256"], f["bytes"], f["width"], f["height"], f["path"], uid, now, f["color"])).lastrowid
        con.execute("INSERT INTO gallery_photos (file_id, user_id, created_at, place) VALUES (?, ?, ?, ?)",
                    (fid, uid, now - n * 20 * 3600, ("main", "main", "b2", "dorm", "main", "away", "b2", None)[n]))
    # a draft next week asking DMP for a room, guests and a speaker: Studio's memo card has a week to show
    memo = {"room": {"any": True, "projector": True, "board": True}, "guests": {"side": "tole", "list": "Ivanov Ivan, Satbayev University"},
            "provide": {"jbl": True, "chairs": 20}}
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, memo, created_by, created_at, updated_at)
        VALUES (4, 1, 'draft', 'Stand-up workshop', 'Room 412', ?, 'microphone_3d', '#2B4C9A', '#1E3770', 40, ?, 1, ?, ?)""",
                (logic._next_week() + 86400 + 13 * 3600, json.dumps(memo), now, now))
    # the event editor's check (Nov 2): a trip left free while its text asks 7500 tenge and names 40 seats, no cover
    con.execute("""INSERT INTO events (id, org_id, status, title, description, place, starts_at, emoji, color, tint, created_by, created_at, updated_at)
        VALUES (5, 1, 'draft', ?, ?, 'Shymbulak', ?, 'camping_3d', '#2F7D6B', '#235E50', 1, ?, ?)""",
                ("\u041f\u043e\u0435\u0437\u0434\u043a\u0430 \u043d\u0430 \u0428\u044b\u043c\u0431\u0443\u043b\u0430\u043a",
                 "\u0415\u0434\u0435\u043c \u043d\u0430 \u0428\u044b\u043c\u0431\u0443\u043b\u0430\u043a \u0432\u0441\u0435\u043c \u043a\u043b\u0443\u0431\u043e\u043c! "
                 "\u0410\u0432\u0442\u043e\u0431\u0443\u0441 \u043e\u0442 \u0433\u043b\u0430\u0432\u043d\u043e\u0433\u043e \u043a\u043e\u0440\u043f\u0443\u0441\u0430 \u0432 9:00, "
                 "\u0432 \u0430\u0432\u0442\u043e\u0431\u0443\u0441\u0435 40 \u043c\u0435\u0441\u0442. \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c 7 500 \u20b8: "
                 "\u0434\u043e\u0440\u043e\u0433\u0430 \u0438 \u043f\u043e\u0434\u044a\u0451\u043c\u043d\u0438\u043a.",
                 now + 9 * day + 4 * 3600, now, now))
    # the Forum tab (FORUM_CHANNEL on below): a few made-up channel posts, one of them Dana's anonymous one with its copy
    # in the group (her "Reply anonymously"), comments, faces and reactions
    for pid, uid, anon, body, ago, comments, rx in (
            (1, 2, 0, "Who wants to team up for the hackathon next weekend? We need a designer and one more backend person.", 3 * 3600, 4,
             '{"\\ud83d\\udd25": 7, "\\ud83d\\udc4d": 3}'),
            (2, 1, 1, "Is the library open on Sunday during the exam weeks? The site says nothing.", 2 * 3600, 2, '{"\\ud83d\\udc4d": 5}'),
            (3, 3, 0, "Lost a black umbrella in room 256 yesterday. If you found it, leave it at the front desk please.", 40 * 60, 0, None)):
        con.execute("""INSERT INTO fchan_posts (id, user_id, body, anon, status, tg_msg, created_at, sign, comments, rules_msg, rules_for, reactions, nick_a, nick_n)
            VALUES (?, ?, ?, ?, 'live', ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (pid, uid, body, anon, 100 + pid, now - ago, None if anon else PEOPLE[uid - 1][2],
                                                                  comments, 500 + pid, 100 + pid, rx, 3 if anon else None, 7 if anon else None))
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"fchcopy:{100 + pid}", str(400 + pid)))
    for mid, pid, uid in ((601, 1, 1), (602, 1, 3), (603, 2, 2), (604, 2, 3)):
        con.execute("INSERT INTO fchan_comments (msg_id, post_id, user_id, at) VALUES (?, ?, ?, ?)", (mid, pid, uid, now - 1800))
    # Admin's forum queue (Bota moderates): Ali's named post the AI held for naming a person, with its reason; Dana's
    # anonymous one the AI refused and she appealed; her anonymous reply the AI held
    con.execute("UPDATE users SET role = 'moderator' WHERE id = 3")
    for pid, uid, anon, body, why, reason in (
            (4, 2, 0, "Our physics teacher never comes on time and then blames us for being late.", "person",
             "It points at one teacher, so a person reads it first."),
            (5, 1, 1, "test of the new coffee machine on the 2nd floor: it finally works", "noise", None)):
        con.execute("""INSERT INTO fchan_posts (id, user_id, body, anon, status, why, created_at, sign, nick_a, nick_n, ai_reason, appealed_at)
            VALUES (?, ?, ?, ?, 'held', ?, ?, ?, ?, ?, ?, ?)""", (pid, uid, body, anon, why, now - 900, None if anon else PEOPLE[uid - 1][2],
                                                                   5 if anon else None, 11 if anon else None, reason, now - 600 if why == "noise" else None))
    con.execute("""INSERT INTO fchan_replies (post_id, comment_msg, body, status, why, created_at, ai_reason)
        VALUES (2, 603, 'Thanks! And the reading room on the third floor, is it open too?', 'held', 'ai', ?, 'It may read as a jab at someone.')""", (now - 700,))
    con.execute("UPDATE fchan_posts SET posted_at = created_at WHERE status = 'live'")  # when the channel got them (the feed's time)
    con.execute("UPDATE fchan_posts SET ai_quote = 'physics teacher', ai_fix = 'Say what happened, not who it was.' WHERE id = 4")
    # photos on the forum: Bota's umbrella post, one picture (an umbrella-ish shape on a desk colour), and one on Ali's
    for pid, n, bg, fg in ((3, 0, (52, 58, 72), (20, 22, 30)), (1, 0, (90, 140, 220), (240, 240, 245)), (1, 1, (240, 200, 90), (60, 60, 70))):
        im = Image.new("RGB", (1200, 900), bg)
        im.paste(Image.new("RGB", (500, 300), fg), (350, 300))
        raw = io.BytesIO()
        im.save(raw, "JPEG")
        saved = media.save(raw.getvalue(), Path(path).resolve().parent / "media", os.urandom(32))
        con.execute("INSERT INTO fchan_photos (post_id, n, path, width, height, color, msg, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, n, saved["path"], saved["width"], saved["height"], saved["color"], 100 + pid if n == 0 else 900 + pid, now))
    con.close()


def big(path: str, n: int = 2000) -> None:
    """--big: n more made-up students, so every long list has a stress case: the guests of an event whose door is open
    now (going, holds, waitlist, cancelled; a third checked in), Open Mic's members in four departments (the club's
    people, its DMP roster, the door's team list), Dana's friends, a volunteers' session that ended an hour ago with
    nobody checked out (its door: VOLUNTEERS=openmic below), and a quarter of them banned (Admin's team list)."""
    con = db.connect(path)
    now, day = int(time.time()), 86400
    first = ("Aruzhan", "Dias", "Madina", "Nursultan", "Aigerim", "Temirlan", "Kamila", "Yerlan", "Zhansaya", "Arman", "Dilnaz", "Sanzhar")
    last = ("Akhmetov", "Bekova", "Zhanova", "Sadykov", "Omarova", "Tulegenov", "Ismailova", "Kenzhebekov", "Serikova", "Nurpeisov")
    ids = range(100, 100 + n)
    name = lambda i: (first[i % len(first)], last[i // len(first) % len(last)])  # noqa: E731
    con.executemany("""INSERT INTO users (id, tg_id, tg_first_name, tg_last_name, created_at, seen_at, banned_at, ban_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [(i, 10000 + i, *name(i), now - 40 * day, now, now - i * 60 if i % 4 == 0 else None, "QA: spam" if i % 4 == 0 else None) for i in ids])
    con.executemany("""INSERT INTO students (user_id, student_id, first_name, last_name, course, school, consent_version, consent_at, verified_at, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, 'qa', ?, ?, ?)""", [(i, f"23B{200000 + i}", *name(i), 1 + i % 4, ("SITE", "BS", "SEOGI", "ISE")[i % 4], now, now, now) for i in ids])
    start = now - 3600  # on now: the door is open (Attendees' Mark, the door's People)
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, created_by, created_at, updated_at, published_at)
        VALUES (6, 1, 'published', 'Winter concert', 'Main hall', ?, ?, 'party_popper_3d', '#2B4C9A', '#1E3770', ?, 1, ?, ?, ?)""",
                (start, start + 4 * 3600, n, now - 7 * day, now - 7 * day, now - 7 * day))
    status = ("going",) * 14 + ("hold", "waitlist", "waitlist", "cancelled")  # one in 18 of each but going
    con.executemany("""INSERT INTO registrations (event_id, user_id, status, ticket_code, hold_until, created_at, updated_at, checked_in_at, checkin_manual)
        VALUES (6, ?, ?, ?, ?, ?, ?, ?, ?)""", [(i, s, f"QA-B{i}", now + day if s == "hold" else None, now - 7 * day + i * 60, now - day,
                                               start + i % 3000 if s == "going" and i % 3 == 0 else None, int(i % 9 == 0))
                                              for i in ids for s in [status[i % len(status)]]])
    for k, dept in enumerate(("Stand-up", "Music", "Media", "Hosts")):
        con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at, department) VALUES (?, 1, ?, '#2B4C9A', ?, 1)", (k + 1, dept, now))
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at, role_id) VALUES (1, ?, 'member', ?, (SELECT id FROM org_roles WHERE org_id = 1 AND level = 'member'))",
                    [(i, now - i * 3600) for i in ids])
    con.executemany("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", [(1 + i % 4, i) for i in ids])
    con.executemany("INSERT INTO friendships (a, b, created_at) VALUES (1, ?, ?)", [(i, now - i * 600) for i in ids])
    # the volunteers' session: finished an hour ago, everyone checked in, a tenth already answered for (the migration's cutoff is "now")
    con.execute("REPLACE INTO meta (key, value) VALUES (?, ?)", (logic.vol.FROM, str(now - 30 * day)))
    con.execute("INSERT INTO qr_sessions (id, title, pin_hash, started_at, ended_at, created_at, org_id) VALUES (1, 'Volunteers: Saturday', 'qa-big', ?, ?, ?, 1)",
                (now - 6 * 3600, now - 3600, now - 6 * 3600))
    con.execute("INSERT INTO vol_meets (session_id, org_id, created_at) VALUES (1, 1, ?)", (now - 6 * 3600,))
    con.executemany("INSERT INTO vol_people (id, org_id, user_id, name, created_at) VALUES (?, 1, ?, ?, ?)", [(i, i, " ".join(name(i)), now - 30 * day) for i in ids])
    con.executemany("INSERT INTO vol_shifts (id, vol_id, session_id, in_at, out_at) VALUES (?, ?, 1, ?, ?)",
                    [(i, i, now - 6 * 3600 + i * 5, now - 2 * 3600 if i % 10 == 0 else None) for i in ids])
    con.executemany("INSERT INTO vol_edits (vol_id, what, ref, by, at) VALUES (?, 'resolve', ?, 1, ?)", [(i, i, now - 1800) for i in ids if i % 10 == 0])
    # the ledger's part of the policy agreed to, so its gate doesn't cover the lists
    con.execute("UPDATE students SET consent_version = ?", (logic.account.CONSENT + logic.account.CONSENT_VOL,))
    con.commit()
    con.close()


def clubs(path: str) -> None:
    """--clubs: a Clubs tab worth looking at (the screen snapshots): KBTU's clubs by their real names, lanyard slugs and
    logos (the app's own assets), each over the registry's size bar, with open rounds, quiet ones, Dana in two of them
    (Ali's friend, so her face is on their rows). Open Mic stays under the bar, as in the flows, which keep the plain seed."""
    con = db.connect(path)
    now, day = int(time.time()), 86400
    people = range(5000, 5050)  # clear of --big's 100..2099
    con.executemany("INSERT INTO users (id, tg_id, tg_first_name, tg_last_name, created_at, seen_at) VALUES (?, ?, 'Guest', ?, ?, ?)",
                    [(i, 20000 + i, str(i), now - 40 * day, now) for i in people])
    marks, root = SERVER.parent / "web" / "src" / "assets" / "lanyards", Path(path).resolve().parent / "media"
    # slug, name, its mark (and the ground a see-through one stands on, as a club's own logo would), category, official,
    # members, recruiting any time, a round closing in N days, with Dana
    for n, (slug, name, logo, ground, cat, official, size, anytime, due, dana) in enumerate((
            ("cybersportkbtu", "KBTU Cybersport", "cyber", None, "sport", 1, 46, 0, 2, 1),
            ("enactuskbtu", "Enactus KBTU", "enactus", "#0A0F55", "business", 1, 38, 0, 9, 0),
            ("tumarorchestrakbtu", "Tumar Orchestra", "tumar", "#0B2470", "art", 1, 31, 0, 0, 1),
            ("caseclubkbtu", "Case Club KBTU", "case", "#111A4B", "business", 1, 27, 1, 0, 0),
            ("diceanddestinykbtu", "Dice and Destiny", "dd", None, "art", 1, 22, 0, 0, 0),
            ("shadekbtu", "Shade", "shade", "#F6EEE2", "art", 1, 19, 0, 5, 0),
            ("web", "Web3 Club", None, None, "it", 1, 16, 1, 0, 0),
            ("literatureclub", "Literature Club", "literature", "#EDE6DC", "art", 1, 14, 0, 0, 0),
            ("qoloner", "Qoloner", "qoloner", None, "volunteer", 1, 12, 1, 0, 0),
            ("knlknolimits", "K|NO LIMITS", "knl", "#071A4A", "sport", 0, 9, 0, 0, 0),
            ("kbtucinema", "Cinema Club", None, None, "art", 0, 7, 0, 0, 0))):
        fid = None
        if logo:
            im = Image.open(marks / f"{logo}-logo.webp").convert("RGBA")
            if ground:
                im.thumbnail((340, 340))
                sq = Image.new("RGBA", (512, 512), ground)
                sq.alpha_composite(im, ((512 - im.width) // 2, (512 - im.height) // 2))
                im = sq
            f = media.store(im.convert("RGB"), f"qa-logo-{slug}".encode(), root)
            fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
                VALUES (?, 'org_logo', 'image/webp', ?, ?, ?, ?, 1, ?, ?)""", (f["sha256"], f["bytes"], f["width"], f["height"], f["path"], now, f["color"])).lastrowid
        oid = con.execute("""INSERT INTO orgs (slug, kind, name, short, emoji, cover, logo_file_id, official, recruiting, category, created_at)
            VALUES (?, 'club', ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (slug, name, name[:2].upper(), "clapper_board_3d" if slug == "kbtucinema" else "laptop_3d",
                                                               n, fid, official, anytime, cat, now - 90 * day)).lastrowid
        for rn, color, lv in logic.OFFICIAL_ROLES:
            con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (?, ?, ?, ?, 1, ?)", (oid, rn, color, lv, now))
        con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                        [(oid, u, now - 30 * day) for u in [*people][:size - dana] + [1] * dana])
        if due:
            con.execute("INSERT INTO rounds (org_id, title, closes_at, created_by, created_at) VALUES (?, 'Winter recruitment', ?, 1, ?)", (oid, now + due * day - 3600, now - day))
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) VALUES (2, (SELECT id FROM orgs WHERE slug = 'enactuskbtu'), ?)", (now - day,))  # Ali follows Enactus
    con.commit()
    con.close()


def link(port: int, tg: int, first: str) -> str:
    data = auth.sign_init_data({"id": tg, "first_name": first, "language_code": "ru"}, BOT)
    theme = json.dumps({"bg_color": "#000000", "text_color": "#ffffff"})
    return f"http://127.0.0.1:{port}/#" + urllib.parse.urlencode({"tgWebAppData": data, "tgWebAppVersion": "9.1", "tgWebAppPlatform": "ios",
                                                                   "tgWebAppThemeParams": theme})


ABOUT = ("\u0412\u0435\u0447\u0435\u0440 \u0441\u0442\u0435\u043d\u0434\u0430\u043f\u0430 \u0438 \u0436\u0438\u0432\u043e\u0439 \u043c\u0443\u0437\u044b\u043a\u0438 \u0432 \u0410\u0442\u0440\u0438\u0443\u043c\u0435. "
         "\u041f\u044f\u0442\u044c \u043c\u0438\u043d\u0443\u0442 \u043d\u0430 \u0441\u0446\u0435\u043d\u0435 \u0434\u043b\u044f \u043a\u0430\u0436\u0434\u043e\u0433\u043e, \u043a\u0442\u043e \u0437\u0430\u043f\u0438\u0448\u0435\u0442\u0441\u044f, "
         "\u0438 \u0442\u0451\u043f\u043b\u044b\u0439 \u0437\u0430\u043b \u0434\u043b\u044f \u0442\u0435\u0445, \u043a\u0442\u043e \u043f\u0440\u0438\u0448\u0451\u043b \u043f\u043e\u0441\u043b\u0443\u0448\u0430\u0442\u044c. "
         "\u041d\u0430\u0447\u0438\u043d\u0430\u0435\u043c \u0440\u043e\u0432\u043d\u043e \u0432 18:30.")


def shift_clock() -> None:
    """--now: every time.time() runs QA_CLOCK seconds off the real one (the server's rules read time.time())."""
    off, real = float(os.environ.get("QA_CLOCK", "0")), time.time
    if off:
        time.time = lambda: real() + off


def real_app():
    from kbtu import app
    shift_clock()
    return app.create()


def fake_ai_app():
    """The app with a made-up assistant model (--fake-ai, no AI key here): it doesn't know, with a topic to vote on; a
    question the keyword backstop would catch comes back with the care flag, to see the help card."""
    from kbtu import app, llm
    from kbtu.logic import assistant
    shift_clock()

    async def chat(cfg, http, msgs, **kw):
        q = msgs[-1]["content"]
        if "announcement" in msgs[0]["content"]:  # the event editor's fill: a made-up description (Russian, as the seed's people)
            return json.dumps({"description": ABOUT}), "qa"
        if "public Telegram" in msgs[0]["content"]:  # the forum's look: "test" in a post is noise, "teacher" a person, the rest OK
            return ("NOISE" if "test" in q.lower() else "PERSON" if "teacher" in q.lower() else "OK"), "qa"
        if '"quote"' in msgs[0]["content"]:  # why it was refused (ai.explain): the first word, made up
            post = json.loads(q)["post"]
            return json.dumps({"quote": post.split()[0], "reason": "QA: no model here, so the first word is marked.",
                               "fix": "QA: say what you need in a sentence."}), "qa"
        if "Student Government" in msgs[0]["content"]:  # appeals' "Help me clarify": made-up tips (Russian, as the seed's people)
            return json.dumps({"tips": ["\u0413\u0434\u0435 \u0438\u043c\u0435\u043d\u043d\u043e \u044d\u0442\u043e \u0441\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c?", "\u0421 \u043a\u0430\u043a\u043e\u0433\u043e \u0434\u043d\u044f?", "\u0427\u0435\u0433\u043e \u0442\u044b \u0445\u043e\u0447\u0435\u0448\u044c \u0432 \u0438\u0442\u043e\u0433\u0435?"], "care": assistant.distress(q)}), "qa"
        care = assistant.distress(q)
        if q.lower().startswith("how"):  # "How do I ...": steps and the screens' buttons (the server keeps those this person may open)
            return json.dumps({"text": "1. Open Studio of your club.\n2. Tap New event.\n3. Paste the announcement.", "known": True, "topic": "qa how to",
                               "actions": [{"type": "new_event"}, {"type": "tickets"}, {"type": "profile"}]}), "qa"
        return json.dumps({"text": "I'm sorry it's so hard right now." if care else f"QA answer, no model: I don't know \"{q[:40]}\".",
                           "actions": [] if care else [{"type": "ask"}], "known": False, "topic": "qa made up topic", "care": care}), "qa"
    llm.chat = chat
    return app.create()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--db", default=str(Path(os.environ.get("TMPDIR", "/tmp")) / "kbtu-qa.db"))
    ap.add_argument("--fake-ai", action="store_true", help="a made-up assistant model (fake_ai_app)")
    ap.add_argument("--big", action="store_true", help="2000 more people on the long lists (big); Dana is the app's admin")
    ap.add_argument("--clubs", action="store_true", help="a dozen real-looking clubs for the Clubs tab (clubs)")
    ap.add_argument("--now", type=int, help="the clock starts at this Unix time (stable screens for snapshots)")
    a = ap.parse_args()
    if a.now:
        os.environ["QA_CLOCK"] = str(a.now - time.time())
        shift_clock()
    seed(a.db)
    if a.big:
        big(a.db)
    if a.clubs:
        clubs(a.db)
    for _, tg, first, _ in PEOPLE:
        print(f"{first}: {link(a.port, tg, first)}", flush=True)
    env = {**os.environ, "DB_PATH": a.db, "BOT_TOKEN": BOT, "TOKEN_KEY": base64.b64encode(os.urandom(32)).decode(), "BACKGROUND": "0",
           "ADMIN_TG_IDS": os.environ.get("QA_ADMIN_TG_IDS", "1001" if a.big else ""), "WEB_DIST": str(SERVER.parent / "web" / "dist"),
           "BOARD": os.environ.get("BOARD", "1"), "FORUM_CHANNEL": os.environ.get("FORUM_CHANNEL", "-1001"), "FORUM_GROUP": os.environ.get("FORUM_GROUP", "-1002"),
           "APPEALS": os.environ.get("APPEALS", "1"), "ASK": os.environ.get("ASK", "1"), "GALLERY": os.environ.get("GALLERY", "1"),  # the student forum on, as it will be after its policy part
           "VOLUNTEERS": os.environ.get("VOLUNTEERS", "openmic" if a.big else "")}  # --big: the volunteers' door (big)
    subprocess.run([sys.executable, "-m", "uvicorn", "tools.qa:fake_ai_app" if a.fake_ai else "tools.qa:real_app", "--factory", "--host", "127.0.0.1", "--port", str(a.port),
                    "--log-level", "warning"], cwd=SERVER, env=env)


if __name__ == "__main__":
    main()
