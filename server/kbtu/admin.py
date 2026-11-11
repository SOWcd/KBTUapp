"""Pilot setup by hand: the owner creates clubs and presidents himself (CONTEXT, priority 6). From server/:

  .venv/bin/python -m kbtu.admin users                                  who opened the app
  .venv/bin/python -m kbtu.admin orgs                                   clubs and their teams
  .venv/bin/python -m kbtu.admin rename <slug> "<name>"                 an org's name as is (its slug and lanyard stay)
  .venv/bin/python -m kbtu.admin org <slug> "<name>" <short> <emoji> [--official] [--school]   a school is official, never closes
  .venv/bin/python -m kbtu.admin org-role <role id> "<ru>" ["<kk>"]     a club role's title corrected: those languages count as typed
                                by hand, so the AI translator never overwrites them; English, level and rights stay; not Vice or Head
  .venv/bin/python -m kbtu.admin role <@username | telegram id> <slug> <member | head | vice | president | none>
  .venv/bin/python -m kbtu.admin links <slug> [https://… …]                 the club's socials (none = clear), up to 6
  .venv/bin/python -m kbtu.admin founder <@username | telegram id>          the Creator status (one person; card number 00000)
  .venv/bin/python -m kbtu.admin mark <@username | telegram id> <idea | none>  the idea author's blue seal (one person)
  .venv/bin/python -m kbtu.admin unlink <@username | telegram id>           the KBTU account off this Telegram (a changed student ID,
                                                                         someone else's sign-in): the next sign-in links afresh
  .venv/bin/python -m kbtu.admin move <@from | telegram id> <@to | telegram id>   a student signed in from a wrong Telegram:
                                the whole account (card, friends, clubs, tickets) moves to their real one, which must have
                                opened the app and hold nothing yet; check with the student that both are theirs first
  .venv/bin/python -m kbtu.admin staff <@username | telegram id> <first> <last> [<unit>]
                                staff, not students (DMP, KBTU's IT testing the app): verified by hand,
                                they act as students but take no card number and aren't counted in stats; `unlink` takes it back
  .venv/bin/python -m kbtu.admin staff <@username | telegram id>
                                one already signed in as a student turns staff: its card number is retired (a gap; until Oct 22
                                the later cards moved down, but that would hand out a deleted account's burnt number)
  .venv/bin/python -m kbtu.admin confirm <@username | telegram id>        a typed-in student checked by hand (e.g. their
                                student card): marked confirmed (the number and First 500 come at sign-in already)
  .venv/bin/python -m kbtu.admin student <@username | telegram id> <student id> <first> <last> <course>
                                a student with no KBTU Microsoft account, checked by hand (their student card): the only
                                way in besides Microsoft
  .venv/bin/python -m kbtu.admin fix <@username | telegram id> <sid | last | first | middle | last-lat | first-lat | middle-lat> "<value>"
                                support: the student ID or a name changed (no once, no year rule, no name tolerance;
                                the old value to the audit log); "" clears the middle name
  .venv/bin/python -m kbtu.admin fix <@username | telegram id> reset   My data's one-time corrections allowed again
  .venv/bin/python -m kbtu.admin stats                                  usage in numbers (counts only), e.g. for a pitch
  .venv/bin/python -m kbtu.admin stats-usage [days]                     anonymous usage (default 7 days, today included): screens,
                                sources, errors, open time; the numbers of the Monday message to the creator
  .venv/bin/python -m kbtu.admin achstats                               each achievement's counter over the students (counts
                                only): the share reaching every level and the typical values, to set the levels by
  .venv/bin/python -m kbtu.admin roster load <rows.json> <map.json>    the clubs' rosters from DMP's sheet (PLAN 95): rows from
                                tools/roster_convert.py, the map sheet -> slug or {"new": {"name", "short", "emoji"}};
                                a second run adds nothing; those already in the app whose rows they are join at once
  .venv/bin/python -m kbtu.admin grant session <sid> init26   the badge to everyone counted in a check-in session
  .venv/bin/python -m kbtu.admin mapflaws          the map's open flaws marked in the app (floor, plan units, words)
  .venv/bin/python -m kbtu.admin places            the assistant's campus facts, STALE where never checked or 180+ days
                                ago (the admin and moderators edit them: /api/admin/places, the admin screen)
  .venv/bin/python -m kbtu.admin checkin new "<title>" <people.json> [club-slug]   a QR check-in session (checkin.py) with
                                its expected people from tools/checkin_convert.py, run by the club's organizers (who run
                                events there) and the admin; /show is paired from their phone
  .venv/bin/python -m kbtu.admin channel-ask [--send]   the active clubs with no public main channel and whether their
                                President can get the ask (counts, club names); --send asks each by the bot to link it
                                (once per club: a second run reaches only those who started the bot since)
  .venv/bin/python -m kbtu.admin prefill-import --list <name> < list.csv   the freshmen list (Oct 31 2026 initiation)
                                for their sign-up form: a CSV with the header email,student_id,last,first,middle,school,phone,came
                                (came 0/1); each <name> runs once; came=1 of a student signed up already (same ID and name): the badge;
                                prints counts only, never a value
  .venv/bin/python -m kbtu.admin latin-names [--apply]   the Latin names KBTU's directory gives (Microsoft's displayName):
                                its shape in counts only; --apply fills the empty Latin columns of those linked already
  .venv/bin/python -m kbtu.admin prefill-rest --list <name> < list.csv   the same list's rows prefill-import didn't keep:
                                a student confirmed with the row's KBTU mail or ID and its name gets the badge (came) and
                                what their row lacks now; the rest wait in prefill_rest for their student's sign-in (the
                                mail or a valid ID, and the name; never the ID itself); counts only
  .venv/bin/python -m kbtu.admin claim new <code> --until YYYY-MM-DD   a link many open for an award (the volunteers'
                                init26 in their chat): each signed-in student gets it once, at once, until that day ends
                                (Almaty); prints the t.me link. claim close <token>: it stops now
  .venv/bin/python -m kbtu.admin announce3 [--send|--test]   owner's one-off (Nov 7): the incubator's elective post (bot.ELECTIVE)
                                to the 3rd years the bot can write to, with "more like it?" Yes/No; counts only; --send queues
                                it (once per person: a second run reaches only the new ones)
  .venv/bin/python -m kbtu.admin meeting new "<title>" "<YYYY-MM-DD HH:MM>" <minutes> "<place>" "<description>"   a DMP leaders meeting
                                (Heads and up of every club; Almaty time), published as DMP by the creator, which invites them at once; prints its id
  .venv/bin/python -m kbtu.admin meeting call <event id> [--test|--send]   "in an hour" (bot meet_call) to the club boards it invites (never ordinary
                                students), once each, an hour before; --test: to the creator now; no flag: counts
  .venv/bin/python -m kbtu.admin event create <club slug> < event.json   a club's event made for it, no role given: one JSON object,
                                the editor's own fields (title, place, description, startsAt, endsAt, emoji, color, guestHost,
                                externalUrl, ...) and "cover": "<base64 jpg/png>"; a DRAFT by the creator, never a price (the
                                club sets it in Studio), in the audit log; prints `draft <id>`
  .venv/bin/python -m kbtu.admin event publish <event id>   that draft (any draft) out by the usual rules (followers hear by
                                the weekly rule), in the audit log; prints `published <id>`
  .venv/bin/python -m kbtu.admin casting from-event <event id> "<YYYY-MM-DD HH:MM>"   its text, cover and place as the club's offline casting, from now to that time (Almaty); tells nobody
  .venv/bin/python -m kbtu.admin fill-categories               clubs with no category get one from the AI (name and description only)
  .venv/bin/python -m kbtu.admin photo-call <event id> [--send]   "add your photos to the album" (bot photo_call) to everyone
                                who came, once each (ref ph2:<event>); a dry run prints how many
  .venv/bin/python -m kbtu.admin vol import <file.xlsx> [--balance "<hours column>"] [--apply --source "<who gave it, when>"]
                                the volunteers ledger's club (VOLUNTEERS): its members and hours sheets (logic/vol.py MEMBERS, HOURS), every
                                column kept as is, people without an account too. Without --apply a dry run: counts, headers,
                                problems by row number (never a value). --balance: that column of the hours sheet (hours) is the
                                starting balance; nothing else is computed. The same file twice adds nothing
  .venv/bin/python -m kbtu.admin vol autolink       the import's records linked to the club's members by their current Telegram username
  .venv/bin/python -m kbtu.admin vol batches | vol undo <batch>   the imports; one undone (records used since stay)
  .venv/bin/python -m kbtu.admin appeals grant|revoke <@username | telegram id>   SG's queue of appeals (logic/appeals.py):
                                a right of its own, never a club role; at once, in the audit log
  .venv/bin/python -m kbtu.admin appeals list                    who has it
  .venv/bin/python -m kbtu.admin appeals reveal <appeal id>      the author (an anonymous one's too): the creator alone, audited
  .venv/bin/python -m kbtu.admin appeals funnel [days]           the composer's anonymous counters and the months' topics
  .venv/bin/python -m kbtu.admin chatsync link <club slug> <chat id> main | dept "<department tag>"   a club's Telegram chat
                                mirrored into its members (CHAT_SYNC=1; the bot an admin there): main = the membership, dept =
                                that department (logic/chatsync.py). chatsync list | chatsync unlink <chat id>
  .venv/bin/python -m kbtu.admin chatsync run <chat id> [--apply]   a sweep by the server's bot (resumes after a restart; a
                                paused link runs again): without --apply a dry run; waits and prints counts only, never names
  .venv/bin/python -m kbtu.admin redelete                        after restoring a copy: the accounts deleted since
                                (deletions.log beside the database) are deleted again (DEPLOY.md, restore)

A role counts once the person has signed in with KBTU or is staff (only students act, SPEC §2). Role changes go to
the audit log. Prints Telegram names only, never the KBTU profile."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import sys
import time

from . import config, db, texts
from pathlib import Path

from .logic.account import _DEL_GONE
from .logic import RANK, STUDENT_ID, ApiError, Viewer, fix_identity, log_action, _slug_free, create_org, delete_me, deletion_hash, find_user, notify, now, one, rows, set_role

# names and notes are users' words: no control or bidi characters reach the admin's terminal (escape codes, a title,
# text that reads backwards)
_UNSAFE, _print = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]"), print


def print(*a, **k) -> None:  # noqa: A001
    _print(*(_UNSAFE.sub("?", str(x)) for x in a), **k)


EVENT_STDIN = 8 << 20  # `event create`: the JSON with its cover in base64


def _user(con, who: str):
    u = find_user(con, who)
    if not u:
        sys.exit(f"{who}: not found — they must open the app once")
    return u


def _vol_import(con, rest: list[str]) -> None:
    from . import xlsx
    from .logic import vol
    path, opts = rest[0], rest[1:]
    flags = {"--apply": False}
    vals: dict[str, str] = {}
    while opts:
        o = opts.pop(0)
        if o == "--apply":
            flags["--apply"] = True
        elif o in ("--balance", "--source") and opts:
            vals[o] = opts.pop(0)
        else:
            sys.exit(__doc__)
    vol.ORG = config.load().volunteers
    org = vol.org_id(con) or sys.exit("VOLUNTEERS is off or names no club")
    try:
        p = vol.plan(Path(path).read_bytes(), vals.get("--balance"))
    except (OSError, xlsx.Bad) as exc:
        sys.exit(f"can't read it: {exc}")
    for name, info in p["sheets"].items():
        print(f"sheet {name!r}: {info['rows']} rows, {info['new']} new people, {info['matched']} matched to the first sheet")
        for head, role in info["headers"]:
            print(f"   {head!r} -> {role or 'kept raw'}")
    c = vol.counts(p)
    print(f"people {c['people']}, with a starting balance {c['withBalance']}, formula cells (their saved value taken) {c['formulas']}")
    for x in p["problems"]:
        print("problem:", x)
    if not flags["--apply"]:
        print("dry run: nothing written (--apply --source \"...\" to import)")
        return
    if not vals.get("--source", "").strip():
        sys.exit('--apply needs --source "<who gave the list, when>"')
    got = vol.apply(con, org, p, vals["--source"].strip())
    print(f"batch {got['batch']}: " + ("this file was imported already, nothing added" if got["again"] else f"{got['added']} added, {got['there']} already there"))


def _chatsync(con, cfg, rest: list[str]) -> None:
    from .logic import account, chatsync
    if not cfg.chat_sync:
        sys.exit("CHAT_SYNC is off")
    chatsync.POLICY = account.policy(cfg)
    sub, ids = rest[:1], [int(x) for x in rest[1:3] if re.fullmatch(r"-?\d+", x)]
    try:
        if sub == ["list"] and len(rest) == 1:
            for c in chatsync.links(con):
                print(c["chat_id"], c["slug"], c["kind"], c["tag"] or "", f"paused ({c['paused']})" if c["paused"] else "live",
                      f"sweep {c['sweep']} at {c['sweep_pos']}" if c["sweep"] else "", c["result"] or "")
        elif sub == ["link"] and len(rest) in (4, 5) and re.fullmatch(r"-?\d+", rest[2]) and (rest[3:] == ["main"] or rest[3] == "dept" and rest[4:]):
            chatsync.link(con, rest[1], int(rest[2]), rest[3], rest[4] if rest[4:] else None)
            print("linked: chatsync run", rest[2], "for a dry run")
        elif sub == ["unlink"] and len(rest) == 2 and ids:
            print("unlinked" if chatsync.unlink(con, ids[0]) else "no such link")
        elif sub == ["run"] and ids and rest[2:] in ([], ["--apply"]):
            if not chatsync.start(con, ids[0], bool(rest[2:])):
                sys.exit("no such link")
            print("queued: the server's bot runs it (Ctrl-C stops waiting, not the sweep)")
            while (c := one(con, "SELECT sweep, result FROM chat_sync WHERE chat_id = ?", ids[0])) and c["sweep"]:
                time.sleep(5)
            print(c["result"] if c else "unlinked meanwhile")
        else:
            sys.exit(__doc__)
    except ApiError as e:
        sys.exit(f"{e.code} {e.message}".strip())


def main(args: list[str]) -> None:
    cfg = config.load()
    con = db.connect(cfg.db_path)
    from .logic import vol
    vol.ORG, vol.KEY = cfg.volunteers, hmac.new(cfg.token_key, b"kbtu-vol", hashlib.sha256).digest()  # as app.create: a deletion here hashes the same
    cmd = args[0] if args else ""
    if cmd == "roster" and len(args) == 4 and args[1] == "load":
        from . import roster
        try:
            got = roster.load(con, json.loads(Path(args[2]).read_text(encoding="utf-8")), json.loads(Path(args[3]).read_text(encoding="utf-8")))
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"rows {got['rows']}, new {got['added']}, clubs made {len(got['orgs_made'])}, joined now {got['joined']}, "
              f"a President on the sheet made Vice (the club has one in the app) {got['president_as_vice']}")  # counts only
    elif cmd == "checkin" and len(args) in (4, 5) and args[1] == "new":
        from . import checkin
        org = None
        if len(args) == 5:
            o = con.execute("SELECT id FROM orgs WHERE slug = ?", (args[4],)).fetchone()
            if not o:
                sys.exit(f"no club {args[4]!r} (see `orgs`)")
            org = o[0]
        sid = checkin.new(con, args[2], json.loads(Path(args[3]).read_text(encoding="utf-8")), org)
        n = con.execute("SELECT COUNT(*) FROM qr_expected WHERE session_id = ?", (sid,)).fetchone()[0]
        who = f"{args[4]}'s organizers and the admin" if org else "the admin only"
        print(f"session {sid}, {n} expected; run by {who} (pair /show from the app)")
    elif cmd == "grant" and len(args) == 4 and args[1] == "session":  # a badge to everyone counted in a check-in session
        from . import checkin
        owner = one(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin'")
        if not owner:
            sys.exit("no owner (the founder admin) yet")
        print(f"granted {args[3]} to {checkin.grant_all(con, Viewer(owner[0], 'admin', True), int(args[2]), args[3])['granted']} people")
    elif cmd == "mapflaws":  # the map's open flaws for a map session: floor, the plan's units, the words
        for r in rows(con, "SELECT * FROM map_flaws WHERE done_at IS NULL ORDER BY floor, created_at"):
            at = f"plan {r['px']:.1f},{r['py']:.1f}" if r["px"] is not None else f"sheet {r['u']:.4f},{r['v']:.4f}"
            print(f"#{r['id']}  {r['ver']} floor {r['floor']}  {at}  {r['body']}")
    elif cmd == "places":  # the assistant's campus facts: what to check on campus
        from .logic import assistant
        got = assistant.places(con, Viewer(0, "admin", False))
        for f in got:
            names = " / ".join(x for x in (f["nameEn"], f["nameRu"], f["nameKk"]) if x) + (f" (also: {f['aliases']})" if f["aliases"] else "")
            checked = time.strftime("%Y-%m-%d", time.gmtime(f["verifiedAt"] + 5 * 3600)) if f["verifiedAt"] else "never"
            print(f"{'STALE' if f['stale'] else '':<5}  {f['code']:<12} {f['kind']:<6} {f['school'] or '':<6} {assistant.where(f):<28} checked {checked:<10}  {names}")
        print(f"{len(got)} facts, {sum(f['stale'] for f in got)} stale")
    elif cmd == "users":
        for u in rows(con, """SELECT u.tg_id, u.tg_username, u.tg_first_name, u.role, s.user_id IS NOT NULL AS student
                FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.tg_id > 0 ORDER BY u.created_at"""):
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
        if not _slug_free(con, slug, None):  # nor a short link's, nor an old one's
            sys.exit(f"{slug}: taken")
        create_org(con, None, name, short, emoji, "--official" in args, slug, "school" if "--school" in args else "club")
        print(f"created {slug}")
    elif cmd == "rename" and len(args) == 3 and args[2].strip():  # owner, Nov 2: "Moments" without its sparkles
        o = one(con, "SELECT id, name FROM orgs WHERE slug = ?", args[1]) or sys.exit(f"{args[1]}: no such club")
        con.execute("UPDATE orgs SET name = ? WHERE id = ?", (args[2].strip(), o["id"]))
        print(f"{args[1]}: {o['name']} -> {args[2].strip()}")
    elif cmd == "org-role" and len(args) in (3, 4) and args[1].isdigit():
        from .logic.teams import SLOT, _also, normalize_role, role_tr
        try:
            titles = {k: _also({k: x}, k) for k, x in zip(("ru", "kk"), args[2:])}
        except ApiError:
            sys.exit("a title is 24 characters at most")
        if not all(titles.values()):
            sys.exit("a title can't be empty")
        rid = int(args[1])
        with db.tx(con):
            r = one(con, "SELECT * FROM org_roles WHERE id = ?", rid) or sys.exit(f"{rid}: no such role")
            if r["fixed"]:
                sys.exit(f"{rid}: Vice and Head keep their names")
            if r["src"] is None:
                normalize_role(con, r)
                r = one(con, "SELECT * FROM org_roles WHERE id = ?", rid)
            src, hand = role_tr(r)  # the typed language is never the translator's already (queues.ai_save)
            try:
                con.execute(f"UPDATE org_roles SET {', '.join(SLOT[k] + ' = ?' for k in titles)}, hand = ? WHERE id = ?",
                            (*titles.values(), ",".join(sorted(hand | set(titles) - {src})), rid))
            except sqlite3.IntegrityError:
                sys.exit(f"{titles['ru']}: another role of this club has this title")
            log_action(con, None, "org_role_fix", f"org:{r['org_id']}", json.dumps({"role": rid, "old": {k: r[SLOT[k]] for k in titles}, "new": titles}, ensure_ascii=False))
        print(f"role {rid}: " + ", ".join(f"{k} {r[SLOT[k]]} -> {x}" for k, x in titles.items()))
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
    elif cmd == "move" and len(args) == 3:  # the owner checked both Telegrams with the student: no in-app proof to phish
        a, b = _user(con, args[1]), _user(con, args[2])
        why = ("the same person" if a["id"] == b["id"] else "staff roles move by hand" if a["role"] != "user" or a["is_founder"] or b["role"] != "user" or b["is_founder"]
               else "the target is banned" if b["banned_at"] else next((f"the target has its own {t}" for t, c in sorted(_DEL_GONE)
               if t not in ("visits", "chat_opens", "bot_outbox", "post_reads", "comment_reads")  # opening the app is no data
               if one(con, f"SELECT 1 FROM {t} WHERE {c} = ?", b["id"])), None))
        if why:
            sys.exit(f"refused: {why}")
        cols = ("tg_id", "tg_username", "tg_first_name", "tg_last_name", "tg_photo_url", "tg_photo_path", "tg_photo_src", "can_dm")
        ra, rb = (tuple(one(con, f"SELECT {', '.join(cols)} FROM users WHERE id = ?", x["id"])) for x in (a, b))
        sets = ", ".join(f"{c} = ?" for c in cols)
        with db.tx(con):  # swap the Telegram side of the two rows; tg_id is UNIQUE, so one steps aside first
            con.execute("UPDATE users SET tg_id = (SELECT min(tg_id) FROM users) - 1 WHERE id = ?", (a["id"],))
            con.execute(f"UPDATE users SET {sets} WHERE id = ?", (*ra, b["id"]))
            con.execute(f"UPDATE users SET {sets} WHERE id = ?", (*rb, a["id"]))
            con.execute("UPDATE tgc_comments SET author_tg = ? WHERE author_tg = ?", (rb[0], ra[0]))  # his channel comments go too
            con.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"ms:{a['id']}", f"ms:{b['id']}"))
            log_action(con, None, "account_move", f"user:{a['id']}", json.dumps({"other": b["id"]}))
        print(f"moved: the account is on @{b['tg_username'] or b['tg_id']} now (run move again the other way to undo)")
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
        # its number stays a gap: moving the later ones down would hand someone a deleted account's burnt number
        print(f"@{u['tg_username'] or u['tg_id']}: staff now, card {no} retired")
    elif cmd == "student" and len(args) == 6:
        u, sid, t = _user(con, args[1]), args[2].upper(), now()
        if not STUDENT_ID.fullmatch(sid) or args[5] not in "123456" or len(args[5]) != 1:
            sys.exit("student id like 24B031234; course 1-6")
        if one(con, "SELECT 1 FROM students WHERE user_id = ? OR student_id = ?", u["id"], sid):
            sys.exit("this person or this student ID is linked already: unlink first")
        with db.tx(con):
            con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at,
                verified_at, synced_at) VALUES (?, ?, ?, ?, ?, 'admin', ?, ?, ?)""", (u["id"], sid, args[3], args[4], int(args[5]), t, t, t))
        print(f"@{u['tg_username'] or u['tg_id']}: student {sid}")
    elif cmd == "fix" and len(args) == 3 and args[2] == "reset":  # support: My data's one-time corrections again
        u = _user(con, args[1])
        with db.tx(con):
            n = con.execute("UPDATE students SET fixed = '', once_was = '{}' WHERE user_id = ?", (u["id"],)).rowcount
            if n:
                log_action(con, None, "identity_fix_reset", f"user:{u['id']}")
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("can correct the student ID and name once more" if n else "not a student"))
    elif cmd == "fix" and len(args) == 4 and args[2] in ("sid", "last", "first", "middle", "last-lat", "first-lat", "middle-lat"):
        u = _user(con, args[1])
        col = {"sid": "student_id", "last": "last_name", "first": "first_name", "middle": "middle_name",
               "last-lat": "last_lat", "first-lat": "first_lat", "middle-lat": "middle_lat"}[args[2]]
        try:
            fix_identity(con, u["id"], col, args[3], admin=True)  # no once, no year rule, no name tolerance; the old value to the audit log
        except ApiError as e:
            sys.exit(f"refused: {e.code} {e.message}".strip())  # sid_taken: unlink the holder first
        print(f"@{u['tg_username'] or u['tg_id']}: {args[2]} changed")
    elif cmd == "stats":  # people are students only: staff aren't counted
        real = "user_id NOT IN (SELECT user_id FROM students WHERE consent_version = 'staff')"
        for name, sql in (("opened the app", "SELECT count(*) FROM users WHERE tg_id > 0"),
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
    elif cmd == "achstats":  # levels set by real numbers, not guesses (owner, Oct 30: some need too many, some too few)
        from .logic.profiles import ACHIEVEMENTS, _counts
        counts = [_counts(con, uid) for (uid,) in rows(con, "SELECT user_id FROM students WHERE consent_version != 'staff'")]
        came = [c for c in counts if c["regular"]]
        print(f"{len(counts)} students, {len(came)} came to an event at least once; each level: share of all / of those who came")
        for code, _, needs, _ in ACHIEVEMENTS:
            if code in ("first50", "creator_laugh", "creator_found", "bugs", "dmp", "init26", "init26f"):
                continue  # given by hand or at sign-in: no counter to tune
            vals = sorted(c[code] for c in counts)
            at = lambda q: vals[min(len(vals) - 1, int(q * len(vals)))] if vals else 0  # noqa: E731
            share = lambda n, of: f"{sum(c[code] >= n for c in of) * 100 / max(1, len(of)):.1f}%"  # noqa: E731
            print(f"{code:>8}  p50 {at(.5)}  p90 {at(.9)}  p99 {at(.99)}  max {vals[-1] if vals else 0}  |  "
                  + "  ".join(f"{n}: {share(n, counts)} / {share(n, came)}" for n in needs))
    elif cmd == "channel-ask" and args[1:] in ([], ["--send"]):  # run it only while meta userbot_ok is fresh
        from . import mirror
        clubs = [o for o in rows(con, """SELECT o.id, o.name, u.id AS uid, u.can_dm, u.banned_at FROM orgs o
                LEFT JOIN org_members m ON m.org_id = o.id AND m.role = 'president' LEFT JOIN users u ON u.id = m.user_id
                WHERE o.kind = 'club' AND o.status = 'active' AND o.can_broadcast = 0 ORDER BY o.name""") if not mirror.has_channel(con, o["id"])]
        nobody = [o["name"] for o in clubs if not o["uid"]]
        mute = [o["name"] for o in clubs if o["uid"] and (not o["can_dm"] or o["banned_at"])]
        asked = {o["id"] for o in clubs if o["uid"] and one(con, "SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'channel_ask' AND ref = ?",
                                                             o["uid"], f"ca:{o['id']}")}
        todo = [o for o in clubs if o["uid"] and o["can_dm"] and not o["banned_at"] and o["id"] not in asked]
        print(f"clubs without a public channel {len(clubs)}: to ask {len(todo)}, asked before {len(asked)}, "
              f"President can't get DMs {len(mute)}, no President {len(nobody)}")
        for title, names in (("to ask", [o["name"] for o in todo]), ("no DMs (Studio shows them the row)", mute), ("no President", nobody)):
            if names:
                print(f"{title}: " + ", ".join(names))
        if "--send" in args:
            for o in todo:
                notify(con, o["uid"], "channel_ask", f"ca:{o['id']}")
            print(f"queued {len(todo)}")
        else:
            print("nothing sent (add --send)")
    elif cmd in ("prefill-import", "prefill-rest") and len(args) == 3 and args[1] == "--list" and re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", args[2]):
        # values never printed: an error names the line, not what's on it
        import csv
        import io
        from .logic.account import PREFILL_COLS, prefill_import, prefill_rest_import
        reader = csv.reader(io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig", newline=""))
        try:
            got = list(reader)
        except (csv.Error, UnicodeDecodeError):
            sys.exit(f"line {reader.line_num + 1}: not a UTF-8 CSV line; nothing imported")
        if not got or tuple(c.strip().lower() for c in got[0]) != PREFILL_COLS:
            sys.exit("the first line must be: " + ",".join(PREFILL_COLS))
        for i, r in enumerate(got[1:], 2):
            if len(r) != len(PREFILL_COLS) or r[-1].strip() not in ("0", "1", ""):
                sys.exit(f"line {i}: {len(PREFILL_COLS)} columns wanted, came 0 or 1; nothing imported")
        if len(got) < 2:
            sys.exit("no rows")
        if cmd == "prefill-rest":
            try:
                n = prefill_rest_import(con, [dict(zip(PREFILL_COLS, r)) for r in got[1:]], args[2])
            except ValueError:
                sys.exit(f"list {args[2]!r}: its rest was stored already, or prefill-import never ran it (run that first)")
            print("  ".join(f"{k} {n.get(k, 0)}" for k in ("rows", "in_prefill", "gone", "matched", "badged", "stored", "sits")))
            print(f"{one(con, 'SELECT COUNT(*) FROM prefill_rest')[0]} rows wait in prefill_rest")
            return
        try:
            n = prefill_import(con, [dict(zip(PREFILL_COLS, r)) for r in got[1:]], args[2])
        except ValueError:
            sys.exit(f"list {args[2]!r} was imported already: each list runs once (a deleted account's row must not come back)")
        print("  ".join(f"{k} {n.get(k, 0)}" for k in ("rows", "kept", "same", "badged", "bad_email", "bad_id", "dup_email", "dup_id",
                                                     "signed_up", "id_held", "bad_phone")))
        print(f"{one(con, 'SELECT COUNT(*) FROM prefill')[0]} rows wait in prefill")
    elif cmd == "latin-names" and args[1:] in ([], ["--apply"]):  # counts only, never a name
        from .logic.account import latin_names
        n = latin_names(con, "--apply" in args)
        for k in sorted(n):
            print(f"{n[k]:>8}  {k}")
        print("written" if "--apply" in args else "nothing written (add --apply)")
    elif cmd == "claim" and len(args) == 5 and args[1] == "new" and args[3] == "--until":
        import calendar
        from .logic.profiles import claim_link
        try:  # the end of that day in Almaty (UTC+5)
            token = claim_link(con, args[2], calendar.timegm(time.strptime(args[4], "%Y-%m-%d")) + 86400 - 5 * 3600)
        except (ValueError, ApiError):
            sys.exit("claim new <init26 | creator_laugh | creator_found> --until YYYY-MM-DD (today or later; the owner set: founder)")
        print(f"https://t.me/{config.load().bot_username}?startapp=gl_{token}")
        print(f"until {args[4]} 23:59 Almaty; to stop it early: claim close {token}")
    elif cmd == "claim" and len(args) == 3 and args[1] == "close":
        n = con.execute("UPDATE grant_links SET expires_at = ? WHERE token = ? AND multi = 1 AND expires_at > ?", (now(), args[2], now())).rowcount
        print("closed" if n else "no open claim link with that token")
    elif cmd == "announce3" and args[1:] == ["--test"]:  # a preview to the creator alone (its own ref: the real run still reaches him)
        with db.tx(con):
            for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1"):
                notify(con, uid, "elective3", f"elective3:test:{int(time.time())}")
        print("queued to the creator")
    elif cmd == "announce3" and args[1:] in ([], ["--send"]):
        to = [r[0] for r in rows(con, """SELECT u.id FROM users u JOIN students s ON s.user_id = u.id WHERE s.course = 3
            AND s.consent_version != 'staff' AND u.can_dm = 1 AND u.banned_at IS NULL AND u.tg_id > 0
            AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = u.id AND b.kind = 'elective3' AND b.ref = 'elective3:2016')""")]
        if args[1:]:
            with db.tx(con):
                for uid in to:
                    notify(con, uid, "elective3", "elective3:2016")
        print(f"3rd years the bot can write to, not sent yet: {len(to)}" + (" (queued)" if args[1:] else " (dry run; --send queues)"))
    elif cmd == "meeting" and len(args) == 7 and args[1] == "new" and args[3:] and args[4].isdigit():
        import calendar
        from .logic import create_event, publish_event
        boss = one(con, "SELECT id FROM users WHERE is_founder = 1")
        org = one(con, "SELECT id FROM orgs WHERE slug = 'dmp'")
        if not boss or not org:
            sys.exit("needs the creator and the dmp office")
        v, at = Viewer(boss[0], "admin", True, staff_org=org[0]), calendar.timegm(time.strptime(args[3], "%Y-%m-%d %H:%M")) - 5 * 3600
        e = create_event(con, v, org[0], {"title": args[2], "startsAt": at, "endsAt": at + int(args[4]) * 60, "place": args[5],
                                          "description": args[6], "emoji": "megaphone_3d", "color": "#2F5BEA", "visibility": "leaders", "leadersFrom": "head"})
        publish_event(con, v, e["id"])
        print(f"published event {e['id']}")
    elif cmd == "event" and len(args) == 3 and args[1] in ("create", "publish"):
        import base64
        from . import media
        from .logic import add_photo, publish_event, staff_create_event
        boss = one(con, "SELECT id FROM users WHERE is_founder = 1")
        if not boss:
            sys.exit("needs the creator (`founder`)")
        try:
            if args[1] == "publish":
                e = one(con, "SELECT org_id FROM events WHERE id = ?", int(args[2])) if args[2].isascii() and args[2].isdigit() else None
                if not e:
                    sys.exit("no such event")
                with db.tx(con):
                    publish_event(con, Viewer(boss[0], "admin", True, staff_org=e["org_id"]), int(args[2]))
                    log_action(con, boss[0], "staff_event", f"event:{int(args[2])}", json.dumps({"do": "publish", "via": "server"}))
                print(f"published {int(args[2])}")
                return
            org = one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", args[2])
            if not org:
                sys.exit(f"no active club {args[2]!r} (see `orgs`)")
            raw = sys.stdin.buffer.read(EVENT_STDIN + 1)
            try:
                body = json.loads(raw) if len(raw) <= EVENT_STDIN else None
            except ValueError:  # not JSON, not UTF-8
                body = None
            if not isinstance(body, dict):
                sys.exit(f"stdin: one JSON object, {EVENT_STDIN >> 20} MB at most")
            v, cover = Viewer(boss[0], "admin", True, staff_org=org[0]), body.pop("cover", None)
            saved = None
            if cover is not None:  # as an upload: POST /api/photos, then the editor's coverId
                try:
                    data = base64.b64decode(cover, validate=True)
                    if not data or len(data) > media.MAX_BYTES:
                        raise ValueError
                    saved = media.save(data, Path(cfg.db_path).resolve().parent / "media")
                except (TypeError, ValueError, media.BadImage):
                    sys.exit("cover: not a base64 picture")
            with db.tx(con):  # a refused event keeps no cover row
                if saved:
                    body["coverId"] = add_photo(con, v, saved)["id"]
                eid = staff_create_event(con, v, org[0], body, "server")["id"]
            print(f"draft {eid}")
        except ApiError as exc:  # the code alone: its message may be a field's name, never the event's words
            sys.exit(f"refused: {exc.code} {exc.message or ''}".rstrip())
    elif cmd == "casting" and len(args) == 4 and args[1] == "from-event" and args[2].isdigit():
        # a club that made its offline casting an event (owner, Nov 9): the same words, cover and place as a casting post, from now on.
        # Silent: a club's own casting tells its followers, this one was never asked to
        import calendar
        from .logic.newsfeed import _casting_input
        e = one(con, "SELECT * FROM events WHERE id = ?", int(args[2]))
        if not e or not e["place"]:
            sys.exit("no such event, or it has no place")
        boss = one(con, "SELECT user_id FROM org_members WHERE org_id = ? AND role = 'president'", e["org_id"]) or one(con, "SELECT id FROM users WHERE is_founder = 1")
        start, end, place = _casting_input({"from": now(), "to": calendar.timegm(time.strptime(args[3], "%Y-%m-%d %H:%M")) - 5 * 3600, "place": e["place"]})
        with db.tx(con):
            if one(con, "SELECT 1 FROM posts WHERE org_id = ? AND hidden_at IS NULL AND casting_cancelled_at IS NULL AND casting_to > ?", e["org_id"], now()):
                sys.exit("this club already has a casting on")
            pid = con.execute("""INSERT INTO posts (org_id, author_id, audience, title, body, photo_file_id, created_at, casting_from, casting_to, casting_place)
                VALUES (?, ?, 'public', ?, ?, ?, ?, ?, ?, ?)""", (e["org_id"], boss[0], e["title"], e["description"][:2000], e["cover_file_id"], now(), start, end, place)).lastrowid
        print(f"casting post {pid}")
    elif cmd == "meeting" and len(args) in (3, 4) and args[1] == "call" and args[2].isdigit() and args[3:] in ([], ["--test"], ["--send"]):
        from .logic.organizing import _invited_leaders
        e = one(con, """SELECT e.* FROM events e JOIN orgs o ON o.id = e.org_id AND o.slug = 'dmp'
            WHERE e.id = ? AND e.status = 'published' AND e.visibility = 'leaders' AND e.starts_at > ?""", int(args[2]), now())
        if not e:
            sys.exit("no upcoming DMP leaders meeting with that id")
        if args[3:] == ["--test"]:
            with db.tx(con):
                for (uid,) in rows(con, "SELECT id FROM users WHERE is_founder = 1"):
                    notify(con, uid, "meet_call", f"mc:{e['id']}:test{int(time.time())}")
            print("queued to the creator")
        else:
            ref = f"mc:{e['id']}"
            told = {r[0] for r in rows(con, "SELECT user_id FROM bot_outbox WHERE kind = 'meet_call' AND ref = ?", ref)}
            to = [r[0] for r in _invited_leaders(con, e) if r[0] not in told]
            if args[3:]:
                with db.tx(con):
                    for uid in to:
                        notify(con, uid, "meet_call", ref, after=max(now(), e["starts_at"] - 3600))
            print(f"club boards invited, not told yet: {len(to)}" + (" (queued for an hour before)" if args[3:] else " (dry run)"))
    elif cmd == "fill-categories" and len(args) == 1:
        import asyncio
        import httpx
        from . import ai

        async def fill():
            async with httpx.AsyncClient() as http:
                return await ai.fill_categories(con, config.load(), http)
        print("filled %d, left empty %d" % asyncio.run(fill()))
    elif cmd == "photo-call" and len(args) in (2, 3) and args[1].isdigit() and args[2:] in ([], ["--send"]):
        e = one(con, "SELECT id, title FROM events WHERE id = ? AND status = 'published'", int(args[1]))
        if not e:
            sys.exit("no published event with that id")
        to = [r[0] for r in rows(con, """SELECT r.user_id FROM registrations r JOIN users u ON u.id = r.user_id WHERE r.event_id = ?
            AND r.checked_in_at IS NOT NULL AND u.can_dm = 1 AND u.banned_at IS NULL AND u.tg_id > 0
            AND NOT EXISTS (SELECT 1 FROM bot_outbox b WHERE b.user_id = u.id AND b.kind = 'photo_call' AND b.ref = ?)""", e["id"], f"ph2:{e['id']}")]
        if args[2:]:
            with db.tx(con):
                for uid in to:
                    notify(con, uid, "photo_call", f"ph2:{e['id']}")
        print(f"{e['title']!r}: came and not called yet {len(to)}" + (" (queued)" if args[2:] else " (dry run; --send queues)"))
    elif cmd == "stats-usage" and len(args) <= 2 and all(a.isdigit() for a in args[1:]):
        from .logic import stats
        print(texts.bot_message("en", "usage_week", **stats.fields(con, int(args[1]) if args[1:] else 7))[0])
    elif cmd == "vol" and args[1:2] == ["import"] and len(args) >= 3:
        _vol_import(con, args[2:])
    elif cmd == "vol" and args[1:] == ["autolink"]:
        org = vol.org_id(con) or sys.exit("VOLUNTEERS is off or names no club")
        print(f"linked {vol.autolink(con, org)}")
    elif cmd == "vol" and args[1:] == ["batches"]:
        for b in rows(con, "SELECT * FROM vol_batches ORDER BY id"):
            print(b["id"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(b["created_at"] + 5 * 3600)), "undone" if b["undone_at"] else "", b["source"], b["counts"])
    elif cmd == "vol" and len(args) == 3 and args[1] == "undo" and args[2].isdigit():
        from .logic import vol
        cfg = config.load()
        vol.ORG = cfg.volunteers
        org = vol.org_id(con) or sys.exit("VOLUNTEERS is off or names no club")
        try:
            print(vol.undo(con, org, int(args[2])))
        except ApiError:
            sys.exit(f"no batch {args[2]} to undo")
    elif cmd == "appeals" and len(args) >= 2:
        from .logic import appeals, stats
        owner = one(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin'")
        if not owner:
            sys.exit("no owner (the founder admin) yet: the audit log needs who did it")
        if args[1] in ("grant", "revoke") and len(args) == 3:
            u = _user(con, args[2])
            appeals.grant(con, owner[0], u["id"], args[1] == "grant")
            print(f"{args[1]}: @{u['tg_username'] or '-'} {u['tg_first_name']}")
        elif args[1] == "list":
            for u in rows(con, "SELECT u.tg_id, u.tg_username, u.tg_first_name FROM appeal_staff a JOIN users u ON u.id = a.user_id ORDER BY a.at"):
                print(f"{u['tg_id']:>12}  @{u['tg_username'] or '-':<20} {u['tg_first_name']}")
        elif args[1] == "reveal" and len(args) == 3 and args[2].isdigit():
            p = appeals.reveal(con, owner[0], int(args[2])) or sys.exit(f"appeal {args[2]}: none (deleted, or its author deleted the account)")
            u = one(con, "SELECT tg_id, tg_username FROM users WHERE id = ?", p["id"])
            print(f"appeal {args[2]}: {p['first_name'] or p['tg_first_name']} {p['last_name'] or ''}  @{u['tg_username'] or '-'}  tg {u['tg_id']}")
        elif args[1] == "funnel" and len(args) <= 3 and all(a.isdigit() for a in args[2:]):
            days = int(args[2]) if args[2:] else 30
            day = stats._today() + 1
            for k in stats.APPEALS:
                print(f"{k:<10} {one(con, 'SELECT COALESCE(SUM(n), 0) FROM usage_days WHERE key = ? AND day >= ?', k, day - days)[0]}")
            for m in appeals.months(con):
                print(m["month"], m["total"], " ".join(f"{k} {n}" for k, n in sorted(m["topics"].items())))
        else:
            sys.exit(__doc__)
    elif cmd == "chatsync":
        _chatsync(con, cfg, args[1:])
    elif cmd == "redelete":
        home = Path(config.load().db_path).resolve().parent
        log = home / "deletions.log"
        if log.exists() and not (home / "deletions.salt").exists():
            sys.exit("deletions.salt is missing: copy it back beside the database first (without it nothing matches)")
        when: dict[str, int] = {}
        want_photos: set[str] = set()
        for line in log.read_text().splitlines() if log.exists() else []:
            f = line.split()
            if len(f) < 2 or not f[0].isdigit():
                continue  # a line cut short
            when[f[1]] = max(when.get(f[1], 0), int(f[0]))
            if "photos" in f[2:]:
                want_photos.add(f[1])
        n = 0
        for u in rows(con, "SELECT u.id, u.tg_id, u.role, s.verified_at FROM users u JOIN students s ON s.user_id = u.id WHERE u.tg_id > 0"):
            h = deletion_hash(home, u["tg_id"])
            t = when.get(h)
            if t and u["verified_at"] < t:  # signed in again after the deletion: that's a new account, it stays
                if h in want_photos:  # "delete my photos too", asked after this copy was made
                    con.execute("INSERT OR IGNORE INTO meta (key, value) VALUES (?, '1')", (f"delphotos:{u['id']}",))
                receipts, photos = delete_me(con, Viewer(u["id"], u["role"], True))
                for root, rels in ((home / "receipts", receipts), (home / "media", photos)):
                    for rel in rels:
                        for ext in (".webp", ".t.webp", ".jpg"):
                            (root / f"{rel}{ext}").unlink(missing_ok=True)
                n += 1
        print(f"{n} deleted again ({len(when)} in deletions.log)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
