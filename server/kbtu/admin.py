"""Pilot setup by hand: the owner creates clubs and presidents himself (CONTEXT, priority 6). From server/:

  .venv/bin/python -m kbtu.admin users                                  who opened the app
  .venv/bin/python -m kbtu.admin orgs                                   clubs and their teams
  .venv/bin/python -m kbtu.admin rename <slug> "<name>"                 an org's name as is (its slug and lanyard stay)
  .venv/bin/python -m kbtu.admin org <slug> "<name>" <short> <emoji> [--official] [--school]   a school is official, never closes
  .venv/bin/python -m kbtu.admin org-award <id | slug | "exact name"> <year> "<title>"   a KBTU Awards nomination it won,
                                on its card (the ceremony's English name); org-award-del with the same words removes it
  .venv/bin/python -m kbtu.admin org-role <role id> "<ru>" ["<kk>"]     a club role's title corrected: those languages count as typed
                                by hand, so the AI translator never overwrites them; English, level and rights stay; not Vice or Head
  .venv/bin/python -m kbtu.admin role <@username | telegram id> <slug> <member | head | vice | president | none>
  .venv/bin/python -m kbtu.admin links <slug> [https://… …]                 the club's socials (none = clear), up to 6
  .venv/bin/python -m kbtu.admin founder <@username | telegram id>          the Creator status (one person; card number 00000)
  .venv/bin/python -m kbtu.admin honor [--yes] <user id | @username> [reason]     give the contribution medal (reason visible on the profile)
  .venv/bin/python -m kbtu.admin honor-off [--yes] <user id | @username>          take it back; --yes confirms without stdin
  .venv/bin/python -m kbtu.admin mark <@username | telegram id> <idea | none>  the idea author's blue seal (one person)
  .venv/bin/python -m kbtu.admin unlink <@username | telegram id>           the KBTU account off this Telegram (a changed student ID,
                                                                         someone else's sign-in): the next sign-in links afresh
  .venv/bin/python -m kbtu.admin move <@from | telegram id> <@to | telegram id> [--merge-credits]   a student signed in from a wrong Telegram:
                                the whole account (card, friends, clubs, tickets) moves to their real one, which must have
                                opened the app and hold nothing yet; check with the student that both are theirs first
  .venv/bin/python -m kbtu.admin staff <@username | telegram id> <first> <last> [<unit>]
                                staff, not students (DMP, KBTU's IT testing the app): verified by hand,
                                they act as students but take no card number and aren't counted in stats; `unlink` takes it back
  .venv/bin/python -m kbtu.admin staff <@username | telegram id>
                                one already signed in as a student turns staff: its card number is retired (a gap: moving
                                the later cards down would hand out a deleted account's burnt number)
  .venv/bin/python -m kbtu.admin staff-ok <@username | telegram id>       KBTU staff without a student ID (DMP): their own
                                Microsoft sign-in, then the policy, makes the staff row with the directory's names (no ID asked;
                                not if Microsoft calls them a student). staff-ok list | staff-ok revoke <@username | telegram id>
                                (revoke also takes back a row it made; `unlink` and deleting the account clear it too)
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
  .venv/bin/python -m kbtu.admin roster load <rows.json> <map.json> | --gz <b64 of gzip {"rows", "map"}>   the clubs' rosters from DMP's sheet (PLAN 95): rows from
                                tools/roster_convert.py, the map sheet -> slug or {"new": {"name", "short", "emoji"}};
                                a second run adds nothing; those already in the app whose rows they are join at once
  .venv/bin/python -m kbtu.admin grant session <sid> init26   the badge to everyone counted in a check-in session
  .venv/bin/python -m kbtu.admin santa-news [--dry | <@who>]  (<@who>: to that one President or Vice alone, to read it first) Secret Santa's announcement: queued once to every President and Vice of an active
                                organization the bot can write to; --dry: the count only. By hand, never on deploy
  .venv/bin/python -m kbtu.admin broadcast <name> <https://t.me/...> [--dry | <@who>]
  .venv/bin/python -m kbtu.admin broadcast-votes <name>   the broadcast's Interesting / Not interesting counts
                                creator only: queue a bot template once per reachable user. --dry counts new recipients;
                                @username or Telegram ID queues it for one person first
  .venv/bin/python -m kbtu.admin team add|del <@username | telegram id>   People of the app's Team (core developers), audited
  .venv/bin/python -m kbtu.admin credit add <telegram id | gh:login> <idea | find | code> "<ru>" "<kk>" "<en>" [--gh <login>]   "People of the app"
                                (logic/credits.py): a line in OUR words about what they gave (an account isn't needed;
                                gh:login: a pull request's author, listed under the public login; --gh: the same person's
                                login beside a Telegram id, shown on their named card only after their yes);
                                credit gh <id> <login> puts a login on a line already written;
                                gender-neutral, no name, handle, link or identifying detail: it is shown under "Student";
                                credit ship <id> [YYYY-MM-DD] lists it (today), credit list, credit del <id>;
                                `move ... --merge-credits` puts the target Telegram's lines under the moved account for good:
                                moving back does not undo it (re-add the lines by hand);
                                credit ask [--dry]: the bot's "shall we name you?" once per person (and consent text) with a
                                shipped line and no answer; prints how many were queued; a no is never asked again
  .venv/bin/python -m kbtu.admin team-consent-ask [--dry]   the bot's "agree to teams" (a button to the event's consent
                                sheet) to everyone signed up to a coming team event without the teams consent, once per
                                person and event; --dry: the count only. By hand, never on deploy
  .venv/bin/python -m kbtu.admin came <@username | telegram id> <event id>   a guest the organizers let in by hand whose list
                                row the retention sweep already erased: a checked-in ticket (manual), audited as came_by_hand
  .venv/bin/python -m kbtu.admin seat <@username | telegram id> <event id>   a student seated on an event by hand, a paid
                                one too, with no receipt (the organizer vouches for the money); audited as seat_by_hand
  .venv/bin/python -m kbtu.admin guest-names <event id> --gz <b64>   the door's list by name (student_id,name,adult,username)
  .venv/bin/python -m kbtu.admin unseat <@username | telegram id> <event id>   a seat taken off by hand (an organizer's swap)
  .venv/bin/python -m kbtu.admin form new <slug> --gz <base64 gzip json>   a public form at /f/<slug>, open to anyone with no
                                account (logic/forms.py has the spec's shape); answers are anonymous. form close <slug> stops it,
                                form answers <slug> prints them as CSV (a column per question), form list counts them
  .venv/bin/python -m kbtu.admin guests <event id> < list.csv   the creator enables imported tickets and age checks.
                                CSV: student_id,adult,username,full_name (optional header, adult 1, 0 or blank).
                                The surname must match. A Telegram username is used only without a valid student ID.
                                The first import for an open event closes prior app sign-ups outside the list. Counts only.
  .venv/bin/python -m kbtu.admin guests claim <event id>   link pending tickets to matching student accounts.
                                After the event ends, only guests checked in at the door qualify. Counts only.
  .venv/bin/python -m kbtu.admin event-new <org slug or id> < event.json   publish a free guest-list event quietly.
                                (guests and event-new also take `--gz <base64 gzip>` at the end instead of stdin)
  .venv/bin/python -m kbtu.admin reg-until <event id> <ISO time with offset>   close an event's sign-up at that time (an organizer's ask)
  .venv/bin/python -m kbtu.admin event-link <event id> <https url>   change an event's "register elsewhere" link (an organizer's ask)
  .venv/bin/python -m kbtu.admin play-demo [revoke]   Google Play's reviewer link to the made-up demo account (PLAY_DEMO on;
                                android/README.md); revoke signs every demo session out (after changing PLAY_DEMO)
  .venv/bin/python -m kbtu.admin groups-draw <event id> <teams per group> <advance>   draw an event's group stage (an organizer's ask)
                                JSON: title, description, starts_at and optional ends_at (ISO with offsets), place,
                                optional poster_b64, guest_list: true, age_check: true. Prints the id and link.
  .venv/bin/python -m kbtu.admin round-nudge <round id> [--dry]   a recruitment round's "pick an interview time" nudge (due
                                48 hours after the invite) goes now to the invited without a time; --dry: the count only
  .venv/bin/python -m kbtu.admin mapflaws          the map's open flaws marked in the app (floor, plan units, words)
  .venv/bin/python -m kbtu.admin places            the assistant's campus facts, STALE where never checked or 180+ days
                                ago (edited by hand in campus_places)
  .venv/bin/python -m kbtu.admin checkin expect <sid> <base64 gzip json> [--only]   add people to a session's expected list (--only: replace it)
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
  .venv/bin/python -m kbtu.admin meeting new "<title>" "<YYYY-MM-DD HH:MM>" <minutes> "<place>" "<description>"   a DMP leaders meeting
                                (Heads and up of every club; Almaty time), published as DMP by the creator, which invites them at once; prints its id
  .venv/bin/python -m kbtu.admin meeting call <event id> [--test|--send]   "in an hour" (bot meet_call) to the club boards it invites (never ordinary
                                students), once each, an hour before; --test: to the creator now; no flag: counts
  .venv/bin/python -m kbtu.admin event create <club slug> < event.json   a club's event made for it, no role given: one JSON object,
                                the editor's own fields (title, place, description, startsAt, endsAt, emoji, color, "seats": a number or null for no limit, required, guestHost,
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
  .venv/bin/python -m kbtu.admin vol autolink       the import's records linked to the club's members by their current Telegram username and verified name
  .venv/bin/python -m kbtu.admin vol batches | vol undo <batch>   the imports; one undone (records used since stay)
  .venv/bin/python -m kbtu.admin appeals grant|revoke <@username | telegram id>   SG's queue of appeals (logic/appeals.py):
                                a right of its own, never a club role; at once, in the audit log
  .venv/bin/python -m kbtu.admin appeals list                    who has it
  .venv/bin/python -m kbtu.admin appeals reveal <appeal id>      the author (an anonymous one's too): the creator alone, audited
  .venv/bin/python -m kbtu.admin appeals funnel [days]           the composer's anonymous counters and the months' topics
  .venv/bin/python -m kbtu.admin help grant|revoke|list [<@username | telegram id>]   the help desk (KRI's questions handed to a person; ASK)
  .venv/bin/python -m kbtu.admin chatsync link <club slug> <chat id> main | dept "<department tag>"   a club's Telegram chat
                                mirrored into its members (CHAT_SYNC=1; the bot an admin there): main = the membership, dept =
                                that department (logic/chatsync.py). chatsync list | chatsync unlink <chat id>
  .venv/bin/python -m kbtu.admin chatsync run <chat id> [--apply]   a sweep by the server's bot (resumes after a restart; a
                                paused link runs again): without --apply a dry run; waits and prints counts only, never names
  .venv/bin/python -m kbtu.admin redelete                        after restoring a copy: the accounts deleted since
                                are deleted again. Restore the newest deletions.log and its matching deletions.salt beside
                                the database, even for a snapshot predating the first deletion. Startup also runs this check.

A role counts once the person has signed in with KBTU or is staff (only students act, SPEC §2). Role changes go to
the audit log. Prints Telegram names only, never the KBTU profile."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import shlex
import sqlite3
import sys
import time

from . import config, db, texts
from pathlib import Path

from .logic.account import _DEL_GONE, staff_row
from .logic import credits, guests
from .logic.core import is_staff, staff_sql
from .logic import RANK, STUDENT_ID, ApiError, Viewer, fix_identity, log_action, _slug_free, create_org, replay_deletions, find_user, notify, now, one, rows, set_role

# names and notes are users' words: no control or bidi characters reach the admin's terminal (escape codes, a title,
# text that reads backwards)
_UNSAFE, _print = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]"), print


def print(*a, **k) -> None:  # noqa: A001
    _print(*(_UNSAFE.sub("?", str(x)) for x in a), **k)


EVENT_STDIN = 8 << 20  # event JSON with a base64 picture


def _user(con, who: str):
    u = find_user(con, who)
    if not u:
        sys.exit(f"{who}: not found — they must open the app once")
    return u


def _broadcast(con, name: str, url: str, target: str | None = None) -> None:
    if not re.fullmatch(r"https://t\.me/[^\s\x00-\x1f\x7f-\x9f\\]*", url):
        sys.exit("broadcast: expected an https://t.me/ URL")
    if not all(texts.broadcast_message(lang, name) for lang in texts.BOT):
        sys.exit("broadcast: expected a translated bot template with a button and no required fields")
    dry = target == "--dry"
    with db.tx(con, write=not dry):
        if not one(con, "SELECT 1 FROM users WHERE is_founder = 1 AND role = 'admin' AND banned_at IS NULL AND tg_id > 0"):
            sys.exit("broadcast: needs the active creator admin")
        only = None
        if target is not None and not dry:
            if re.fullmatch(r"@[A-Za-z0-9_]+", target):
                matches = rows(con, "SELECT id FROM users WHERE lower(tg_username) = lower(?) LIMIT 2", target[1:])
            elif re.fullmatch(r"[0-9]+", target):
                matches = rows(con, "SELECT id FROM users WHERE tg_id = ?", target)
            else:
                sys.exit("broadcast: expected @username or Telegram ID")
            if len(matches) != 1:
                sys.exit("broadcast: no unique preview recipient; use their Telegram ID")
            only = matches[0]["id"]
        # everyone who hasn't turned broadcasts off (Settings, or the broadcast's own button); a preview goes regardless
        recipients = """FROM users u WHERE u.can_dm = 1 AND u.banned_at IS NULL AND u.tg_id > 0 AND (u.n_broadcasts = 1 OR ? IS NOT NULL)
            AND (? IS NULL OR u.id = ?) AND (? IS NOT NULL OR NOT EXISTS (SELECT 1 FROM bot_outbox b
                WHERE b.user_id = u.id AND b.kind = 'app_broadcast' AND b.ref = ? AND b.error IS NULL))"""  # a failed one, or a preview, may go again
        if dry:
            count = one(con, f"SELECT COUNT(*) {recipients}", only, only, only, only, name)[0]
        else:
            count = con.execute(f"""INSERT OR REPLACE INTO bot_outbox (user_id, kind, ref, payload, send_after)
                SELECT u.id, 'app_broadcast', ?, ?, ? {recipients} ORDER BY u.id""",
                                (name, json.dumps({"url": url}), now(), only, only, only, only, name)).rowcount
    print(f"{'would queue' if dry else 'queued'} {count}")


def _gz_arg(args: list[str]) -> bytes | None:
    """`--gz <base64 gzip>` at the end instead of stdin: the prod gate passes arguments, not stdin (ssh claude-kbtu)."""
    import base64
    import gzip
    if len(args) >= 2 and args[-2] == "--gz":
        try:
            return gzip.decompress(base64.b64decode(args[-1], validate=True))[:EVENT_STDIN + 1]
        except (ValueError, OSError, EOFError):
            sys.exit("--gz: base64 of gzip expected")
    return None


def _event_input(given: bytes | None = None) -> dict:
    raw = given if given is not None else getattr(sys.stdin, "buffer", sys.stdin).read(EVENT_STDIN + 1)
    try:
        body = json.loads(raw) if len(raw) <= EVENT_STDIN else None
    except ValueError:  # not JSON, not UTF-8
        body = None
    if not isinstance(body, dict):
        sys.exit(f"stdin: one JSON object, {EVENT_STDIN >> 20} MB at most")
    return body


def _event_picture(body: dict, field: str, root: Path) -> dict | None:
    import base64
    from . import media
    raw = body.pop(field, None)
    if raw is None:
        return None
    try:
        data = base64.b64decode(raw, validate=True)
        if not data or len(data) > media.MAX_BYTES:
            raise ValueError
        return media.save(data, root)
    except (TypeError, ValueError):
        sys.exit(f"{field}: not a base64 picture")


def _event_time(value: object, field: str) -> int:
    from datetime import datetime
    try:
        at = datetime.fromisoformat(value)
        if at.utcoffset() is not None:
            return int(at.timestamp())
    except (TypeError, ValueError, OverflowError):
        pass
    sys.exit(f"{field}: expected ISO date and time with an offset")


def _event_new(con, cfg: config.Config, org_ref: str, gz: bytes | None = None) -> None:
    from tempfile import TemporaryDirectory
    from .logic import add_photo, publish_event, staff_create_event
    boss = one(con, "SELECT id FROM users WHERE is_founder = 1")
    if not boss:
        sys.exit("needs the creator (`founder`)")
    org = one(con, "SELECT id FROM orgs WHERE slug = ? AND status = 'active'", org_ref)
    if not org and re.fullmatch(r"[0-9]{1,19}", org_ref) and int(org_ref) < 2**63:
        org = one(con, "SELECT id FROM orgs WHERE id = ? AND status = 'active'", int(org_ref))
    if not org:
        sys.exit("no active organization (see `orgs`)")
    raw = _event_input(gz)
    if raw.get("guest_list") is not True or raw.get("age_check") is not True:
        sys.exit("guest_list and age_check must be true")
    fields = ("title", "description", "place")
    if any(not isinstance(raw.get(k), str) for k in fields):
        sys.exit("title, description and place must be strings")
    body = {k: raw[k] for k in fields}
    body.update(startsAt=_event_time(raw.get("starts_at"), "starts_at"), emoji="sparkles_3d", color="#3B6BFF", seats=None)  # a guest list: no cap
    if raw.get("ends_at") is not None:
        body["endsAt"] = _event_time(raw["ends_at"], "ends_at")
    v = Viewer(boss[0], "admin", True, staff_org=org[0])
    photos = Path(cfg.db_path).resolve().parent / "media"
    try:
        with TemporaryDirectory(dir=photos.parent) as staged:
            saved = _event_picture(raw, "poster_b64", Path(staged))
            with db.tx(con):
                if saved:
                    body["coverId"] = add_photo(con, v, saved)["id"]
                eid = staff_create_event(con, v, org[0], body, "server", guest_list=True)["id"]
                publish_event(con, v, eid, announce=False)
                log_action(con, v.id, "staff_event", f"event:{eid}", json.dumps({"do": "publish", "via": "server"}))
                if saved:
                    # A refused event leaves its poster outside the public media directory.
                    src, dst = Path(staged) / saved["path"], photos / saved["path"]
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    for variant in src.parent.glob(f"{src.name}.*"):
                        variant.replace(dst.parent / variant.name)
    except ApiError as exc:
        sys.exit(f"refused: {exc.code} {exc.message or ''}".rstrip())
    print(f"published {eid}")
    print(f"https://t.me/{cfg.bot_username}?startapp=ev_{eid}")


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
    chatsync.POLICY = account.CONSENT
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
    if args == ["redelete"]:
        db.init(cfg.db_path)  # the restored file can predate tables that erasure now covers
    con = db.connect(cfg.db_path)
    from .logic import vol
    vol.ORG, vol.KEY = cfg.volunteers, hmac.new(cfg.token_key, b"kbtu-vol", hashlib.sha256).digest()  # as app.create: a deletion here hashes the same
    guests.KEY = hmac.digest(cfg.token_key, b"kbtu-guest-name", "sha256")
    cmd = args[0] if args else ""
    gz = _gz_arg(args)
    if gz is not None:
        args = args[:-2]
    if cmd == "guests" and (len(args) == 2 or (len(args) == 3 and args[1] == "claim" and gz is None)):
        if not re.fullmatch(r"[0-9]{1,19}", args[-1]):
            sys.exit(__doc__)
        eid = int(args[-1])
        if eid >= 2**63:
            sys.exit("no such event")
        if len(args) == 3:
            with db.tx(con):
                if not one(con, "SELECT 1 FROM users WHERE is_founder = 1"):
                    sys.exit("needs the creator")
                if not one(con, "SELECT 1 FROM events WHERE id = ?", eid):
                    sys.exit("no such event")
                claimed = guests.claim_event(con, eid)
            print(f"claimed {claimed}")
            return
        try:
            registered, pending, offline, bad = guests.import_csv(con, eid, gz.decode("utf-8", "replace").splitlines(keepends=True) if gz is not None else sys.stdin)
        except ApiError as exc:
            if exc.code == "bad_input":
                sys.exit(exc.message)
            sys.exit("needs the creator" if exc.code == "forbidden" else "no such event")
        except UnicodeError:
            sys.exit("guest CSV must be UTF-8")
        print(f"registered {registered}, pending {pending}, offline {offline}, bad rows {bad}")
    elif cmd == "groups-draw" and len(args) == 4 and all(re.fullmatch(r"[0-9]{1,4}", a) for a in args[1:]):
        from .logic import evgroups
        boss, e = one(con, "SELECT id FROM users WHERE is_founder = 1"), one(con, "SELECT org_id FROM events WHERE id = ?", int(args[1]))
        if not boss or not e:
            sys.exit("needs the creator (`founder`) and an existing event")
        try:
            got = evgroups.draw(con, Viewer(boss[0], "admin", True, staff_org=e[0]), int(args[1]), {"size": int(args[2]), "advance": int(args[3])})
        except ApiError as exc:
            sys.exit(f"refused: {exc.code}")
        print("groups", " ".join(f"{g['name']}:{len(g['standings'])}" for g in got["groups"]))
    elif cmd == "reg-until" and len(args) == 3 and re.fullmatch(r"[0-9]{1,19}", args[1]):
        at = _event_time(args[2], "time")
        with db.tx(con):
            if not con.execute("UPDATE events SET reg_until = ?, late_signup = 0 WHERE id = ? AND starts_at > ?", (at, int(args[1]), at)).rowcount:
                sys.exit("no such event, or it starts before that time")
        print("sign-up closes", args[2])
    elif cmd == "event-link" and len(args) == 3 and re.fullmatch(r"[0-9]{1,19}", args[1]) and re.fullmatch(r"https://\S{1,300}", args[2]):
        with db.tx(con):  # the "register elsewhere" button's link (an organizer's ask), in the audit log
            if not con.execute("UPDATE events SET external_url = ? WHERE id = ? AND external_url IS NOT NULL", (args[2], int(args[1]))).rowcount:
                sys.exit("no such event with an outside link")
            log_action(con, None, "event_link", f"event:{args[1]}", json.dumps({"url": args[2]}))
        print("link", args[2])
    elif cmd == "play-demo" and args[1:] in ([], ["revoke"]):
        from .logic import web_auth
        if not args[1:] and not cfg.play_demo:
            sys.exit("PLAY_DEMO is off: set it to 32+ random characters (python -c 'import secrets;print(secrets.token_urlsafe(32))')")
        with db.tx(con):
            if args[1:]:
                web_auth.revoke_demo(con)  # never refused: an odd demo row is when it's needed most
            else:
                web_auth.demo_user(con, now())
        print("demo sessions signed out" if args[1:] else f"https://{cfg.domain}/play-demo?k={cfg.play_demo}")
    elif cmd == "event-new" and len(args) == 2:
        _event_new(con, cfg, args[1], gz)
    elif cmd == "roster" and args[1:2] == ["load"] and (len(args) == 4 or (len(args) == 2 and gz is not None)):
        from . import roster
        try:
            if gz is not None:  # the prod gate passes arguments only: {"rows": [...], "map": {...}} as `--gz`
                given = json.loads(gz)
                items, orgmap = given["rows"], given["map"]
            else:
                items, orgmap = json.loads(Path(args[2]).read_text(encoding="utf-8")), json.loads(Path(args[3]).read_text(encoding="utf-8"))
            got = roster.load(con, items, orgmap)
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"rows {got['rows']}, new {got['added']}, clubs made {len(got['orgs_made'])}, joined now {got['joined']}, "
              f"a President on the sheet made Vice (the club has one in the app) {got['president_as_vice']}")  # counts only
    elif cmd == "checkin" and len(args) in (4, 5) and args[1] == "expect" and args[4:] in ([], ["--only"]):
        # ponytail: a session's expected list from a base64 gzip JSON argument ([{"name", "studentId"}]), for a team
        # list wanted on the spot; no file reaches the container otherwise
        import base64
        import gzip
        sid, people = int(args[2]), json.loads(gzip.decompress(base64.b64decode(args[3])))
        with db.tx(con):
            if args[4:]:  # --only: this list replaces the one frozen before (the club's roster)
                con.execute("DELETE FROM qr_expected WHERE session_id = ?", (sid,))
            for p in people:
                con.execute("INSERT OR IGNORE INTO qr_expected (session_id, email, full_name, student_id) VALUES (?, ?, ?, ?)",
                            (sid, f"id:{p['studentId']}".lower(), p["name"], p["studentId"]))
        print(f"session {sid}, {con.execute('SELECT COUNT(*) FROM qr_expected WHERE session_id = ?', (sid,)).fetchone()[0]} expected")
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
    elif cmd == "santa-news" and len(args) == 2 and args[1] != "--dry":  # to one person first
        from .logic import santa
        print(f"queued {santa.news(con, only=_user(con, args[1])['id'])}")
    elif cmd == "santa-news" and args[1:] in ([], ["--dry"]):  # Secret Santa's announcement to Presidents and Vices, queued once each
        from .logic import santa
        n = santa.news(con, dry=bool(args[1:]))
        print(f"{'would queue' if args[1:] else 'queued'} {n}")
    elif cmd == "broadcast-votes" and len(args) == 2:
        yes, no = one(con, "SELECT COALESCE(SUM(vote), 0), COALESCE(SUM(1 - vote), 0) FROM broadcast_votes WHERE name = ?", args[1])
        print(f"{args[1]}: {yes} interested, {no} not")
    elif cmd == "broadcast" and len(args) in (3, 4) and gz is None:
        _broadcast(con, *args[1:])
    elif cmd == "credit" and args[1:2] in (["add"], ["gh"], ["ship"], ["list"], ["del"], ["ask"]):  # the people of the app (logic/credits.py)
        try:
            if args[1] == "add" and (len(args) == 7 or (len(args) == 9 and args[7] == "--gh")):
                print(f"credit {credits.add(con, *args[2:7], *args[8:])} (suggested; `credit ship` lists it)")
                print(f"check before shipping: {credits.REMIND}")
            elif args[1] == "gh" and len(args) == 4:
                credits.set_gh(con, int(args[2]), args[3])
                print(f"credit {int(args[2])}: gh {args[3]}")
            elif args[1] == "ship" and len(args) in (3, 4):
                print(f"credit {int(args[2])} shipped {credits.ship(con, int(args[2]), *args[3:])}")
            elif args[1] == "del" and len(args) == 3:
                credits.delete(con, int(args[2]))
                print(f"credit {int(args[2])} deleted")
            elif args[1] == "ask" and args[2:] in ([], ["--dry"]):
                print(f"{'would queue' if args[2:] else 'queued'} {credits.ask(con, dry=bool(args[2:]))}")
            elif args[1] == "list" and len(args) == 2:
                for r in rows(con, f"""SELECT c.*, u.id AS uid, k.id AS rev, k.show, k.version FROM credits c
                        LEFT JOIN users u ON u.tg_id = c.tg_id AND u.tg_id > 0 {credits._LAST} ORDER BY c.id"""):
                    tg = None if r["tg_id"] is None else f"tg {r['tg_id']}" + ("" if r["uid"] else " (no account)")
                    who = " + ".join(x for x in (tg, r["gh"] and f"gh {r['gh']}") if x) or "deleted account"
                    said = {None: "no answer", True: "yes", False: "no"}[credits._said(r)]
                    print(f"#{r['id']}  {r['shipped_on'] or 'suggested'}  {r['kind']}  {who}, {said}  {r['ru']} | {r['kk']} | {r['en']}")
            else:
                sys.exit(__doc__)
        except ValueError as exc:
            sys.exit(str(exc))
    elif cmd == "team" and len(args) == 3 and args[1] in ("add", "del"):  # People of the app's Team (logic/credits.py)
        u = _user(con, args[2])
        changed = credits.team(con, u["id"], args[1] == "add")
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("on the Team (shown after their yes; `credit ask` asks)" if args[1] == "add" else "off the Team")
              + ("" if changed else " already"))
    elif cmd == "team-consent-ask" and args[1:] in ([], ["--dry"]):  # signed up before the sign-up became the consent
        from .logic import evteams
        n = evteams.consent_ask(con, dry=bool(args[1:]))
        print(f"{'would queue' if args[1:] else 'queued'} {n}")
    elif cmd == "came" and len(args) == 3 and args[2].isdigit():  # the creator alone, on the organizers' word
        from .db import tx
        uid, eid = _user(con, args[1])["id"], int(args[2])
        with tx(con):
            e = one(con, "SELECT starts_at FROM events WHERE id = ?", eid)
            if not e:
                raise SystemExit("no such event")
            guests._ticket(con, eid, uid, None)
            con.execute("""UPDATE registrations SET checked_in_at = COALESCE(checked_in_at, ?), checkin_manual = 1
                WHERE event_id = ? AND user_id = ?""", (e["starts_at"] or now(), eid, uid))
            log_action(con, None, "came_by_hand", f"event:{eid}", json.dumps({"user": uid}))
        print("came")
    elif cmd == "seat" and len(args) == 3 and args[2].isdigit():  # the creator alone, by hand: e.g. a bank that won't share the receipt
        from .logic import seats
        print(seats.seat_by_hand(con, _user(con, args[1])["id"], int(args[2])))
    elif cmd == "guest-names" and len(args) == 2 and args[1].isdigit():  # the door's list by name: student_id,name,adult,username
        named, added = guests.door_names(con, int(args[1]), gz.decode("utf-8", "replace").splitlines() if gz is not None else sys.stdin)
        print(f"named {named}, added {added}")
    elif cmd == "unseat" and len(args) == 3 and args[2].isdigit():  # the creator alone, by hand: an organizer's swap of a guest
        from .db import tx
        from .logic import seats
        uid, eid = _user(con, args[1])["id"], int(args[2])
        with tx(con):
            r = one(con, "SELECT * FROM registrations WHERE event_id = ? AND user_id = ? AND status != 'cancelled'", eid, uid)
            if not r:
                raise SystemExit("no seat")
            seats._seat_out(con, r, "removed")
            notify(con, uid, "seat_removed", f"event:{eid}:{now()}")  # the same template as an organizer's removal
            log_action(con, None, "unseat_by_hand", f"event:{eid}", json.dumps({"user": uid}))
        print("removed")
    elif cmd == "u18" and len(args) in (2, 3) and args[1].isdigit() and (args[2:] == [] or args[2].isdigit()):
        # the organizers' "under 18, please leave" to every checked-in minor, now or at a set unix time (the bot sends it then)
        eid, at = int(args[1]), int(args[2]) if args[2:] else now()
        with db.tx(con):
            got = rows(con, """SELECT r.user_id FROM registrations r JOIN reg_age a ON a.registration_id = r.id
                WHERE r.event_id = ? AND r.status = 'going' AND r.checked_in_at IS NOT NULL AND a.adult = 0""", eid)
            for (uid,) in got:
                notify(con, uid, "u18_leave", f"u18:{eid}:{at}", after=at)
        print(len(got))
    elif cmd == "round-nudge" and len(args) in (2, 3) and args[1].isdigit() and args[2:] in ([], ["--dry"]):
        from . import casting
        n = casting.nudge_now(con, int(args[1]), dry=bool(args[2:]))
        print(f"{'would send now' if args[2:] else 'sending now'} {n}")
    elif cmd == "form" and args[1:2] in (["new"], ["close"], ["answers"], ["list"]):  # public forms (logic/forms.py)
        from .logic import forms
        try:
            if args[1] == "new" and len(args) == 3 and gz is not None:
                forms.create(con, args[2], json.loads(gz))
                print(f"form /f/{args[2]}")
            elif args[1] == "close" and len(args) == 3:
                forms.close(con, args[2])
                print(f"closed /f/{args[2]}")
            elif args[1] == "answers" and len(args) == 3:
                sys.stdout.write(forms.export(con, args[2]))  # CSV as is: its control characters went at the door
            elif args[1] == "list" and len(args) == 2:
                for slug, is_open, n in forms.listing(con):
                    print(f"{'open' if is_open else 'closed':<6} {n:>5}  /f/{slug}")
            else:
                sys.exit(__doc__)
        except ValueError:
            sys.exit("the spec: JSON expected")
        except ApiError as exc:
            sys.exit(f"{exc.code} {exc.message}".strip())
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
    elif cmd == "rename" and len(args) == 3 and args[2].strip():  # e.g. "Moments" without its sparkles
        o = one(con, "SELECT id, name FROM orgs WHERE slug = ?", args[1]) or sys.exit(f"{args[1]}: no such club")
        con.execute("UPDATE orgs SET name = ? WHERE id = ?", (args[2].strip(), o["id"]))
        print(f"{args[1]}: {o['name']} -> {args[2].strip()}")
    elif cmd in ("org-award", "org-award-del") and len(args) == 4 and args[2].isdigit():
        from .logic.clubs import set_award
        key = args[1].strip()
        o = one(con, "SELECT id, name FROM orgs WHERE id = ?", int(key)) if key.isdigit() else \
            one(con, "SELECT id, name FROM orgs WHERE slug = ? OR name = ? ORDER BY slug = ? DESC LIMIT 1", key, key, key)
        if not o:
            sys.exit(f"{key}: no such organization (see `orgs`)")
        on = cmd == "org-award"
        try:
            done = set_award(con, None, o["id"], int(args[2]), args[3], on)
        except ApiError:
            sys.exit("year: 2000-2100; title: 1-80 characters, one line")
        print(f"{o['name']}: {'added' if on else 'removed'} {args[2]} {args[3].strip()!r}" if done else f"{o['name']}: {'already has' if on else 'has no'} {args[2]} {args[3].strip()!r}")
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
    elif cmd in ("honor", "honor-off"):
        from .logic.profiles import grant, take_back
        confirmed = args[1:2] == ["--yes"]
        if confirmed:
            args = [cmd, *args[2:]]
        if len(args) < 2 or (cmd == "honor-off" and len(args) != 2):
            sys.exit("honor <user id or @username> [reason] | honor-off <user id or @username>")
        who = args[1]
        if re.fullmatch(r"id:[0-9]+", who):
            matches = rows(con, "SELECT id FROM users WHERE id = ? AND tg_id > 0", who[3:])
        elif who.isascii() and who.isdecimal():
            matches = rows(con, "SELECT id FROM users WHERE (id = ? OR tg_id = ?) AND tg_id > 0", who, who)
        elif who.startswith("@") and len(who) > 1:
            matches = rows(con, "SELECT id FROM users WHERE tg_username = ? COLLATE NOCASE AND tg_id > 0", who[1:])
        else:
            sys.exit("expected a user id or @username")
        if len(matches) != 1:
            sys.exit("no unique match for that account; use id:<app user id> or @username")
        uid = matches[0]["id"]
        try:
            if not confirmed and input(f"{cmd} for app user {uid}? [y/N] ").strip().lower() != "y":
                sys.exit("cancelled")
        except EOFError:
            sys.exit("confirmation required")
        try:
            with db.tx(con):
                owner = one(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin' AND banned_at IS NULL AND tg_id > 0")
                if not owner:
                    sys.exit("no active creator admin")
                v = Viewer(owner[0], "admin", True)
                if cmd == "honor":
                    grant(con, v, uid, "honor", reason=" ".join(args[2:]))
                    undo = ["honor-off", f"id:{uid}"]
                else:
                    prior = take_back(con, v, uid, "honor")["reason"]
                    undo = ["honor", f"id:{uid}"] + ([prior] if prior else [])
            print("Undo with", shlex.join(undo))
        except ApiError as e:
            sys.exit(f"refused: {e.code} {e.message}".strip())
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
    elif cmd == "move" and (len(args) == 3 or args[3:] == ["--merge-credits"]):  # the owner checked both Telegrams with the student: no in-app proof to phish
        a, b = _user(con, args[1]), _user(con, args[2])
        why = ("the same person" if a["id"] == b["id"] else "staff roles move by hand" if a["role"] != "user" or a["is_founder"] or b["role"] != "user" or b["is_founder"]
               else "the target is banned" if b["banned_at"] else next((f"the target has its own {t}" for t, c in sorted(_DEL_GONE)
               if t not in ("visits", "chat_opens", "bot_outbox", "post_reads", "comment_reads", "web_sessions")
               if one(con, f"SELECT 1 FROM {t} WHERE {c} = ?", b["id"])), None))
        if why:
            sys.exit(f"refused: {why}")
        cols = ("tg_id", "tg_username", "tg_first_name", "tg_last_name", "tg_photo_url", "tg_photo_path", "tg_photo_src", "tg_photo_at", "can_dm")
        ra, rb = (tuple(one(con, f"SELECT {', '.join(cols)} FROM users WHERE id = ?", x["id"])) for x in (a, b))
        sets = ", ".join(f"{c} = ?" for c in cols)
        with db.tx(con):  # swap the Telegram side of the two rows; tg_id is UNIQUE, so one steps aside first
            con.execute("UPDATE users SET tg_id = (SELECT min(tg_id) FROM users) - 1 WHERE id = ?", (a["id"],))
            con.execute(f"UPDATE users SET {sets} WHERE id = ?", (*ra, b["id"]))
            con.execute(f"UPDATE users SET {sets} WHERE id = ?", (*rb, a["id"]))
            con.execute("UPDATE tgc_comments SET author_tg = ?, dm_id = NULL WHERE author_tg = ?", (rb[0], ra[0]))  # comments move; DMs stay in the old chat
            try:  # his lines in People of the app go too, his yes there ends; the target's own lines: refused unless --merge-credits
                credits.moved(con, a["id"], ra[0], rb[0], merge=len(args) == 4)
            except ValueError as exc:
                sys.exit(f"refused: {exc}")  # the transaction rolls back: nothing moved
            con.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"ms:{a['id']}", f"ms:{b['id']}"))
            log_action(con, None, "account_move", f"user:{a['id']}", json.dumps({"other": b["id"]}))
        print(f"moved: the account is on @{b['tg_username'] or b['tg_id']} now (run move again the other way to undo)")
    elif cmd == "unlink" and len(args) == 2:  # the card number stays (users.card_no): signing in again gets it back
        u = _user(con, args[1])
        with db.tx(con):
            n = con.execute("DELETE FROM students WHERE user_id = ?", (u["id"],)).rowcount
            con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (u["id"],))
            if con.execute("DELETE FROM staff_ok WHERE user_id = ?", (u["id"],)).rowcount:  # a fresh start: staff again only by staff-ok
                log_action(con, None, "staff_ok_revoke", f"user:{u['id']}", json.dumps({"by": "unlink"}))
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("unlinked, signing in with KBTU links again" if n else "wasn't linked"))
    elif cmd == "staff-ok" and args[1:] == ["list"]:
        for r in rows(con, """SELECT u.tg_id, u.tg_username, u.tg_first_name, k.granted_at, s.student_id FROM staff_ok k JOIN users u ON u.id = k.user_id
                LEFT JOIN students s ON s.user_id = u.id ORDER BY k.granted_at"""):
            print(f"@{r['tg_username'] or r['tg_id']} ({r['tg_first_name']}) since {time.strftime('%Y-%m-%d', time.gmtime(r['granted_at']))}: "
                  + ("signed in" if r["student_id"] else "not signed in yet"))
    elif cmd == "staff-ok" and len(args) in (2, 3) and (len(args) == 2 or args[1] == "revoke"):
        u = _user(con, args[-1])
        who = f"@{u['tg_username'] or u['tg_id']}"
        if len(args) == 2:
            s = one(con, "SELECT student_id FROM students WHERE user_id = ?", u["id"])
            if s and not s["student_id"].startswith("staff"):
                sys.exit(f"{who}: signed in as a student already (unlink first, or `staff {who}`)")
            with db.tx(con):
                if con.execute("INSERT OR IGNORE INTO staff_ok (user_id, granted_at) VALUES (?, ?)", (u["id"], now())).rowcount:
                    log_action(con, None, "staff_ok", f"user:{u['id']}")
            print(f"{who}: staff, signs in with Microsoft alone")
        else:
            with db.tx(con):
                n = con.execute("DELETE FROM staff_ok WHERE user_id = ?", (u["id"],)).rowcount
                # the row its sign-in made (a policy version, not 'staff': `staff` typed by hand stays): the next sign-in is a student's
                gone = con.execute("DELETE FROM students WHERE user_id = ? AND student_id = ? AND consent_version != 'staff'", (u["id"], f"staff{u['id']}")).rowcount
                if n or gone:
                    log_action(con, None, "staff_ok_revoke", f"user:{u['id']}", json.dumps({"row": bool(gone)}))
            print(f"{who}: " + ("revoked" + (", its sign-in undone" if gone else "") if n or gone else "had no staff-ok"))
    elif cmd == "confirm" and len(args) == 2:
        u = _user(con, args[1])
        with db.tx(con):
            n = con.execute("UPDATE students SET manual = 0, verified_at = ? WHERE user_id = ? AND manual = 1", (now(), u["id"])).rowcount
            if n:
                guests.claim(con, u["id"])
        print(f"@{u['tg_username'] or u['tg_id']}: " + ("confirmed" if n else "nothing typed in to confirm"))
    elif cmd == "staff" and len(args) in (4, 5):  # SPEC §1: the student ID can't be a real one, so a KBTU sign-in is refused
        u = _user(con, args[1])
        if one(con, "SELECT 1 FROM students WHERE user_id = ?", u["id"]):
            sys.exit(f"@{u['tg_username'] or u['tg_id']}: already signed in with KBTU or staff")
        staff_row(con, u["id"], args[2], args[3], args[4] if len(args) == 5 else None)
        print(f"@{u['tg_username'] or u['tg_id']}: staff, acts as a student")
    elif cmd == "staff" and len(args) == 2:
        u = _user(con, args[1])
        s = one(con, "SELECT student_id, consent_version FROM students WHERE user_id = ?", u["id"])
        if not s or is_staff(s):
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
            guests.claim(con, u["id"])
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
        real = f"user_id NOT IN (SELECT user_id FROM students s WHERE {staff_sql()})"
        for name, sql in (("opened the app", "SELECT count(*) FROM users WHERE tg_id > 0"),
                          ("signed in with KBTU", f"SELECT count(*) FROM students WHERE {real}"),
                          ("staff", f"SELECT count(*) FROM students s WHERE {staff_sql()}"),
                          ("clubs", "SELECT count(*) FROM orgs WHERE kind = 'club' AND status = 'active'"),
                          ("official clubs", "SELECT count(*) FROM orgs WHERE kind = 'club' AND status = 'active' AND official"),
                          ("people in a club's team", f"SELECT count(DISTINCT user_id) FROM org_members WHERE {real}"),
                          ("events published", "SELECT count(*) FROM events WHERE status = 'published' AND hidden_at IS NULL"),
                          ("sign-ups (going)", f"SELECT count(*) FROM registrations WHERE status = 'going' AND {real}"),
                          ("came (checked in)", f"SELECT count(*) FROM registrations WHERE checked_in_at IS NOT NULL AND {real}"),
                          ("posts", "SELECT count(*) FROM posts WHERE hidden_at IS NULL"),
                          ("first KBTU sign-in", f"SELECT date(min(verified_at), 'unixepoch', '+5 hours') FROM students WHERE {real}")):
            print(f"{one(con, sql)[0]!s:>10}  {name}")
    elif cmd == "achstats":  # levels set by real numbers, not guesses (some need too many, some too few)
        from .logic.profiles import ACHIEVEMENTS, _counts
        counts = [_counts(con, uid) for (uid,) in rows(con, f"SELECT user_id FROM students s WHERE NOT {staff_sql()}")]
        came = [c for c in counts if c["regular"]]
        print(f"{len(counts)} students, {len(came)} came to an event at least once; each level: share of all / of those who came")
        for code, _, needs, _ in ACHIEVEMENTS:
            if code in ("first50", "creator_laugh", "creator_found", "bugs", "dmp", "init26", "init26f", "sponsor"):
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
    elif cmd == "meeting" and len(args) == 7 and args[1] == "new" and args[3:] and args[4].isdigit():
        import calendar
        from .logic import create_event, publish_event
        boss = one(con, "SELECT id FROM users WHERE is_founder = 1")
        org = one(con, "SELECT id FROM orgs WHERE slug = 'dmp'")
        if not boss or not org:
            sys.exit("needs the creator and the dmp office")
        v, at = Viewer(boss[0], "admin", True, staff_org=org[0]), calendar.timegm(time.strptime(args[3], "%Y-%m-%d %H:%M")) - 5 * 3600
        e = create_event(con, v, org[0], {"title": args[2], "startsAt": at, "endsAt": at + int(args[4]) * 60, "place": args[5],
                                          "description": args[6], "emoji": "megaphone_3d", "color": "#2F5BEA", "visibility": "leaders", "leadersFrom": "head", "seats": None})
        publish_event(con, v, e["id"])
        print(f"published event {e['id']}")
    elif cmd == "event" and len(args) == 3 and args[1] in ("create", "publish"):
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
            body = _event_input()
            v = Viewer(boss[0], "admin", True, staff_org=org[0])
            saved = _event_picture(body, "cover", Path(cfg.db_path).resolve().parent / "media")
            with db.tx(con):  # a refused event keeps no cover row
                if saved:
                    body["coverId"] = add_photo(con, v, saved)["id"]
                eid = staff_create_event(con, v, org[0], body, "server")["id"]
            print(f"draft {eid}")
        except ApiError as exc:  # the code alone: its message may be a field's name, never the event's words
            sys.exit(f"refused: {exc.code} {exc.message or ''}".rstrip())
    elif cmd == "casting" and len(args) == 4 and args[1] == "from-event" and args[2].isdigit():
        # Reuse the casting post text, cover and place for its event without sending a follower notification.
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
    elif cmd == "help" and len(args) >= 2:
        from .logic import appeals
        owner = one(con, "SELECT id FROM users WHERE is_founder = 1 AND role = 'admin'") or sys.exit("no owner (the founder admin) yet")
        if args[1] in ("grant", "revoke") and len(args) == 3:
            u = _user(con, args[2])
            appeals.grant(con, owner[0], u["id"], args[1] == "grant", "help")
            print(f"{args[1]}: @{u['tg_username'] or '-'} {u['tg_first_name']}")
        elif args[1] == "list":
            for u in rows(con, "SELECT u.tg_id, u.tg_username, u.tg_first_name FROM help_staff a JOIN users u ON u.id = a.user_id ORDER BY a.at"):
                print(f"{u['tg_id']:>12}  @{u['tg_username'] or '-':<20} {u['tg_first_name']}")
        else:
            sys.exit(__doc__)
    elif cmd == "chatsync":
        _chatsync(con, cfg, args[1:])
    elif cmd == "redelete":
        con.execute("DELETE FROM web_sessions")  # a restored copy must not bring signed-out sessions back
        n, total = replay_deletions(con)
        print(f"{n} deleted again ({total} in deletions.log)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
