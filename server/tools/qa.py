"""Screens on the real server with made-up people (the in-browser demo went on Oct 11: its copy of the server's rules
drifted and doubled every feature). Seeds a fresh database with a few made-up students and an official club with a
paid event, starts the real server on it with the postman off, and prints a link per person that opens the app as
them: Telegram's initData rides in the link's hash, signed with a made-up bot token, the way Telegram passes it, so
the real telegram-web-app.js reads it. Nothing leaves this machine.

    cd server && .venv/bin/python tools/qa.py [--port 8790] [--db /tmp/qa.db]

OCR of receipts runs if tesseract with the rus and kaz models is installed (TESSDATA_PREFIX for a local copy)."""
from __future__ import annotations

import argparse
import base64
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

BOT = "1:qa"
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
            VALUES (?, ?, ?, ?, ?, 'ru', 1, ?, ?, ?, ?)""", (uid, tg, first.lower(), first, last, now - 30 * day, now, f"QA{uid:06d}", uid))
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, email, course, school, consent_version, consent_at, verified_at, synced_at)
            VALUES (?, ?, ?, ?, ?, 2, 'SITE', 'qa', ?, ?, ?)""", (uid, f"24B{100000 + uid}", first, last, f"{first.lower()}@kbtu.kz", now, now, now))
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, description, emoji, official, created_at)
        VALUES (1, 'openmic', 'club', 'Open Mic Club', 'OM', 'Stand-up and music nights.', 'microphone_3d', 1, ?)""", (now - 60 * day,))
    for rn, color, lv in logic.OFFICIAL_ROLES:  # what create_org makes
        con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (1, ?, ?, ?, 1, ?)", (rn, color, lv, now))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at, role_id) VALUES (1, 1, 'vice', ?, (SELECT id FROM org_roles WHERE org_id = 1 AND level = 'vice'))", (now - 50 * day,))
    start = (now // day + 2) * day + 13 * 3600 + 1800  # the day after tomorrow, 18:30 in Almaty
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, price, pay_to_name, pay_phone,
            created_by, created_at, updated_at, published_at) VALUES (1, 1, 'published', 'Open Mic: stand-up and music', 'Atrium', ?, ?, 'microphone_3d',
            '#7A4A22', '#5C3719', 80, 2000, 'Arman A.', '+77071234567', 1, ?, ?, ?)""", (start, start + 3 * 3600, now - day, now - day, now - day))
    # Dana's friends go to a free event: her Friends page has its "where friends are going" cards
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (1, 2, ?), (1, 3, ?)", (now - 20 * day, now - 10 * day))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, created_by, created_at,
            updated_at, published_at) VALUES (2, 1, 'published', 'Board games night', 'Room 305', ?, ?, 'popcorn_3d', '#2B4C9A', '#1E3770', 40, 1,
            ?, ?, ?)""", (start - day, start - day + 3 * 3600, now - day, now - day, now - day))
    for uid in (2, 3):
        con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at)
            VALUES (2, ?, 'going', ?, ?, ?)""", (uid, f"QA-T{uid}", now, now))
    # Ali has today's timetable (made up), so the List's live stack shows its class card: one on now, two after it
    t0 = time.gmtime(now + 5 * 3600)  # Almaty, UTC+5
    base = min(max(t0.tm_hour * 60 + t0.tm_min, 20), 24 * 60 - 180)  # late at night the day still fits (classes end 23:59 at most)
    hm = lambda m: f"{(base + m) // 60:02d}:{(base + m) % 60:02d}"
    for b, e, subj, kind, room, who in ((-20, 30, "Algorithms and Data Structures", "practice", "403", "Kim D."),
                                       (40, 90, "Physics", "lab", "162a", None), (120, 170, "Linear Algebra", "lecture", "256", None)):
        con.execute("INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, kind, room, teacher) VALUES (2, ?, ?, ?, ?, ?, ?, ?)",
                    (t0.tm_wday + 1, hm(b), hm(e), subj, kind, room, who))
    # yesterday's event with an album: Ali and Bota came; Ali added two shots, Bota one (pictures drawn here)
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, tint, seats, created_by, created_at,
            updated_at, published_at) VALUES (3, 1, 'published', 'Karaoke night', 'Atrium', ?, ?, 'microphone_3d', '#7A2253', '#5C193E', 60, 1,
            ?, ?, ?)""", (now - day - 3 * 3600, now - day, now - 3 * day, now - 3 * day, now - 3 * day))
    for n, (uid, rgb) in enumerate(((2, (230, 90, 60)), (2, (60, 140, 220)), (3, (90, 200, 120)))):
        con.execute("""INSERT OR IGNORE INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at)
            VALUES (3, ?, 'going', ?, ?, ?, ?)""", (uid, f"QA-K{uid}", now - 2 * day, now - 2 * day, now - day - 3 * 3600))
        im = Image.linear_gradient("L").resize((1200, 900)).convert("RGB")
        im = Image.composite(Image.new("RGB", im.size, rgb), Image.new("RGB", im.size, (20, 20, 30)), Image.linear_gradient("L").resize(im.size))
        f = media.store(im, f"qa-photo-{n}".encode(), Path(path).resolve().parent / "media")
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
            VALUES (?, 'event_photo', 'image/webp', ?, ?, ?, ?, ?, ?, ?)""", (f["sha256"], f["bytes"], f["width"], f["height"], f["path"], uid, now, f["color"])).lastrowid
        con.execute("INSERT INTO event_photos (event_id, file_id, sort, added_by) VALUES (3, ?, ?, ?)", (fid, n + 1, uid))
    # a draft next week asking DMP for a room, guests and a speaker: Studio's memo card has a week to show
    memo = {"room": {"any": True, "projector": True, "board": True}, "guests": {"side": "tole", "list": "Ivanov Ivan, Satbayev University"},
            "provide": {"jbl": True, "chairs": 20}}
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, tint, seats, memo, created_by, created_at, updated_at)
        VALUES (4, 1, 'draft', 'Stand-up workshop', 'Room 412', ?, 'microphone_3d', '#2B4C9A', '#1E3770', 40, ?, 1, ?, ?)""",
                (logic._next_week() + 86400 + 13 * 3600, json.dumps(memo), now, now))
    con.close()


def link(port: int, tg: int, first: str) -> str:
    data = auth.sign_init_data({"id": tg, "first_name": first, "language_code": "ru"}, BOT)
    theme = json.dumps({"bg_color": "#000000", "text_color": "#ffffff"})
    return f"http://127.0.0.1:{port}/#" + urllib.parse.urlencode({"tgWebAppData": data, "tgWebAppVersion": "9.1", "tgWebAppPlatform": "ios",
                                                                   "tgWebAppThemeParams": theme})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--db", default=str(Path(os.environ.get("TMPDIR", "/tmp")) / "kbtu-qa.db"))
    a = ap.parse_args()
    seed(a.db)
    for _, tg, first, _ in PEOPLE:
        print(f"{first}: {link(a.port, tg, first)}", flush=True)
    env = {**os.environ, "DB_PATH": a.db, "BOT_TOKEN": BOT, "TOKEN_KEY": base64.b64encode(os.urandom(32)).decode(), "BACKGROUND": "0",
           "ADMIN_TG_IDS": os.environ.get("QA_ADMIN_TG_IDS", ""), "WEB_DIST": str(SERVER.parent / "web" / "dist"),
           "BOARD": os.environ.get("BOARD", "1")}  # the student forum on, as it will be after its policy part
    subprocess.run([sys.executable, "-m", "uvicorn", "kbtu.app:create", "--factory", "--host", "127.0.0.1", "--port", str(a.port),
                    "--log-level", "warning"], cwd=SERVER, env=env)


if __name__ == "__main__":
    main()
