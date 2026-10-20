"""Pilot setup by hand: the owner creates clubs and presidents himself (CONTEXT, priority 6). From server/:

  .venv/bin/python -m kbtu.admin users                                  who opened the app
  .venv/bin/python -m kbtu.admin orgs                                   clubs and their teams
  .venv/bin/python -m kbtu.admin org <slug> "<name>" <short> <emoji> [--official] [--school]   a school is official, never closes
  .venv/bin/python -m kbtu.admin role <@username | telegram id> <slug> <member | head | vice | president | none>
  .venv/bin/python -m kbtu.admin links <slug> [https://… …]                 the club's socials (none = clear), up to 6
  .venv/bin/python -m kbtu.admin founder <@username | telegram id>          the Creator status (one person; card number 00000)
  .venv/bin/python -m kbtu.admin mark <@username | telegram id> <idea | none>  the idea author's blue seal (one person)
  .venv/bin/python -m kbtu.admin unlink <@username | telegram id>           the KBTU account off this Telegram (a changed student ID,
                                                                         someone else's sign-in): the next sign-in links afresh
  .venv/bin/python -m kbtu.admin staff <@username | telegram id> <first> <last> [<unit>]
                                staff, not students (DMP, KBTU's IT testing the app): verified by hand,
                                they act as students but take no card number and aren't counted in stats; `unlink` takes it back
  .venv/bin/python -m kbtu.admin staff <@username | telegram id>
                                one already signed in as a student turns staff: its card number goes back and every card
                                after it moves down one, so the numbers count students only (owner, Oct 13: KBTU's IT testers)
  .venv/bin/python -m kbtu.admin confirm <@username | telegram id>        a typed-in student checked by hand (e.g. their
                                student card): marked confirmed (the number and First 500 come at sign-in already)
  .venv/bin/python -m kbtu.admin student <@username | telegram id> <student id> <first> <last> <course>
                                a student with no KBTU Microsoft account, checked by hand (their student card): the only
                                way in besides Microsoft (owner, Oct 20)
  .venv/bin/python -m kbtu.admin stats                                  usage in numbers (counts only), e.g. for a pitch

A role counts once the person has signed in with KBTU or is staff (only students act, SPEC §2). Role changes go to
the audit log. Prints Telegram names only, never the KBTU profile."""
from __future__ import annotations

import json
import re
import sys

from . import config, db
from .logic import RANK, create_org, find_user, first_fifty, now, one, rows, set_role


def _user(con, who: str):
    u = find_user(con, who)
    if not u:
        sys.exit(f"{who}: not found — they must open the app once")
    return u


def main(args: list[str]) -> None:
    con = db.connect(config.load().db_path)
    cmd = args[0] if args else ""
    if cmd == "users":
        for u in rows(con, """SELECT u.tg_id, u.tg_username, u.tg_first_name, u.role, s.user_id IS NOT NULL AS student
                FROM users u LEFT JOIN students s ON s.user_id = u.id ORDER BY u.created_at"""):
            print(f"{u['tg_id']:>12}  @{u['tg_username'] or '-':<20} {u['tg_first_name']:<16} {'student' if u['student'] else 'guest':<8} {u['role']}")
    elif cmd == "orgs":
        for o in rows(con, "SELECT * FROM orgs ORDER BY id"):
            team = rows(con, """SELECT m.role, u.tg_username, u.tg_first_name FROM org_members m JOIN users u ON u.id = m.user_id
                WHERE m.org_id = ?""", o["id"])
            team = sorted(team, key=lambda m: -RANK[m["role"]])
            print(f"{o['slug']:<12} {o['name']}{' ✓' if o['official'] else ''}: " +
                  (", ".join(f"{m['role']} @{m['tg_username'] or m['tg_first_name']}" for m in team) or "nobody yet"))
    elif cmd == "org" and len(args) >= 5:
        slug, name, short, emoji = args[1:5]
        if not re.fullmatch(r"[a-z0-9]{2,24}", slug) or not 1 <= len(short) <= 2 or not re.fullmatch(r"[a-z0-9_]{1,40}", emoji):
            sys.exit("slug: [a-z0-9]{2,24}; short: 1–2 letters; emoji: a key of the 3D set, e.g. laptop_3d")
        if one(con, "SELECT 1 FROM orgs WHERE slug = ?", slug):
            sys.exit(f"{slug}: taken")
        create_org(con, None, name, short, emoji, "--official" in args, slug, "school" if "--school" in args else "club")
        print(f"created {slug}")
    elif cmd == "role" and len(args) == 4:
        u, role = _user(con, args[1]), args[3]
        o = one(con, "SELECT * FROM orgs WHERE slug = ?", args[2]) or sys.exit(f"{args[2]}: no such club")
        if role not in (*RANK, "none"):
            sys.exit("role: member, head, vice, president or none")
        set_role(con, None, u["id"], o["id"], role, "cli")  # one president per club: the old one steps down to vice
        student = one(con, "SELECT 1 FROM students WHERE user_id = ?", u["id"])
        print(f"@{u['tg_username'] or u['tg_id']} → {role} in {o['slug']}" + ("" if student else " (counts after they sign in with KBTU)"))
    elif cmd == "links" and len(args) >= 2:
        links = args[2:]
        if len(links) > 6 or any(not re.fullmatch(r"https://[^\s]{4,300}", x) for x in links):
            sys.exit("links: up to 6, each https://…")
        if not con.execute("UPDATE orgs SET links = ? WHERE slug = ?", (json.dumps(links), args[1])).rowcount:
            sys.exit(f"{args[1]}: no such club")
        print(f"{args[1]}: {len(links)} link(s)")
    elif cmd == "founder" and len(args) == 2:
        u = _user(con, args[1])
        con.execute("UPDATE users SET is_founder = (id = ?)", (u["id"],))  # one Creator
        print(f"@{u['tg_username'] or u['tg_id']} is the Creator")
    elif cmd == "mark" and len(args) == 3 and args[2] in ("idea", "none"):
        u = _user(con, args[1])
        with db.tx(con):
            if args[2] != "none":
                con.execute("UPDATE users SET mark = NULL WHERE mark = ?", (args[2],))  # one person each
            con.execute("UPDATE users SET mark = ? WHERE id = ?", (None if args[2] == "none" else args[2], u["id"]))
        print(f"@{u['tg_username'] or u['tg_id']}: mark {args[2]}")
    elif cmd == "unlink" and len(args) == 2:  # the card number stays (users.card_no): signing in again gets it back
        u = _user(con, args[1])
        with db.tx(con):
            n = con.execute("DELETE FROM students WHERE user_id = ?", (u["id"],)).rowcount
            con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (u["id"],))
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("unlinked, signing in with KBTU links again" if n else "wasn't linked"))
    elif cmd == "confirm" and len(args) == 2:
        u = _user(con, args[1])
        with db.tx(con):
            n = con.execute("UPDATE students SET manual = 0, verified_at = ? WHERE user_id = ? AND manual = 1", (now(), u["id"])).rowcount
            if n:
                first_fifty(con, u["id"])
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("confirmed" if n else "nothing typed in to confirm"))
    elif cmd == "staff" and len(args) in (4, 5):  # SPEC §1: the student ID can't be a real one, so a KBTU sign-in is refused
        u, t = _user(con, args[1]), now()
        if one(con, "SELECT 1 FROM students WHERE user_id = ?", u["id"]):
            sys.exit(f"@{u['tg_username'] or u['tg_id']}: already signed in with KBTU or staff")
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, school, consent_version, consent_at,
            verified_at, synced_at) VALUES (?, ?, ?, ?, ?, 'staff', ?, ?, ?)""", (u["id"], f"staff{u['id']}", args[2], args[3], args[4] if len(args) == 5 else None, t, t, t))
        print(f"@{u['tg_username'] or u['tg_id']}: staff, acts as a student")
    elif cmd == "staff" and len(args) == 2:
        u = _user(con, args[1])
        s = one(con, "SELECT consent_version FROM students WHERE user_id = ?", u["id"])
        if not s or s["consent_version"] == "staff":
            sys.exit(f"@{u['tg_username'] or u['tg_id']}: " + ("already staff" if s else "not signed in: use staff <who> <first> <last>"))
        no = u["card_no"]
        with db.tx(con):
            con.execute("UPDATE students SET consent_version = 'staff' WHERE user_id = ?", (u["id"],))
            con.execute("UPDATE users SET card_no = NULL WHERE id = ?", (u["id"],))
            con.execute("DELETE FROM achievement_grants WHERE user_id = ? AND code = 'first50'", (u["id"],))
            if no:
                con.execute("UPDATE users SET card_no = card_no - 1 WHERE card_no > ?", (no,))
                con.execute("UPDATE meta SET value = CAST(value AS INTEGER) - 1 WHERE key = 'card_last'")  # the counter moves down too
        print(f"@{u['tg_username'] or u['tg_id']}: staff now, card {no} given back, the later ones moved down one")
    elif cmd == "student" and len(args) == 6:
        u, sid, t = _user(con, args[1]), args[2].upper(), now()
        if not re.fullmatch(r"\d{2}[A-Z]{1,2}\d{5,7}", sid) or args[5] not in "123456" or len(args[5]) != 1:
            sys.exit("student id like 24B031234; course 1-6")
        if one(con, "SELECT 1 FROM students WHERE user_id = ? OR student_id = ?", u["id"], sid):
            sys.exit("this person or this student ID is linked already: unlink first")
        with db.tx(con):
            con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at,
                verified_at, synced_at) VALUES (?, ?, ?, ?, ?, 'admin', ?, ?, ?)""", (u["id"], sid, args[3], args[4], int(args[5]), t, t, t))
            first_fifty(con, u["id"])
        print(f"@{u['tg_username'] or u['tg_id']}: student {sid}")
    elif cmd == "stats":  # people are students only: staff aren't counted
        real = "user_id NOT IN (SELECT user_id FROM students WHERE consent_version = 'staff')"
        for name, sql in (("opened the app", "SELECT count(*) FROM users"),
                          ("signed in with KBTU", f"SELECT count(*) FROM students WHERE {real}"),
                          ("staff (by hand)", "SELECT count(*) FROM students WHERE consent_version = 'staff'"),
                          ("clubs", "SELECT count(*) FROM orgs WHERE kind = 'club' AND status = 'active'"),
                          ("official clubs", "SELECT count(*) FROM orgs WHERE kind = 'club' AND status = 'active' AND official"),
                          ("people in a club's team", f"SELECT count(DISTINCT user_id) FROM org_members WHERE {real}"),
                          ("events published", "SELECT count(*) FROM events WHERE status = 'published' AND hidden_at IS NULL"),
                          ("sign-ups (going)", f"SELECT count(*) FROM registrations WHERE status = 'going' AND {real}"),
                          ("came (checked in)", f"SELECT count(*) FROM registrations WHERE checked_in_at IS NOT NULL AND {real}"),
                          ("posts", "SELECT count(*) FROM posts WHERE hidden_at IS NULL"),
                          ("first KBTU sign-in", f"SELECT date(min(verified_at), 'unixepoch', '+5 hours') FROM students WHERE {real}")):
            print(f"{one(con, sql)[0]!s:>10}  {name}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
